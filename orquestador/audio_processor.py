# audio_processor.py
"""
Captura dual en Windows:
  - Micrófono (sounddevice / WASAPI)
  - Audio del sistema vía WASAPI Loopback (PyAudioWPatch)

Stereo Mix suele fallar con audio del navegador (ElevenLabs, Teams en Edge/Chrome).
El loopback WASAPI captura lo que realmente sale por el dispositivo de reproducción.
"""
import os
import queue
import threading
import wave
import time

import numpy as np
import sounddevice as sd
import whisper
from scipy import signal

try:
    import pyaudiowpatch as pyaudio
except ImportError as e:
    raise ImportError(
        "Falta PyAudioWPatch. Instálalo con:\n"
        "  python -m pip install PyAudioWPatch scipy"
    ) from e

from config import RECORDING_HEARTBEAT_SEC, TEMP_DIR, WHISPER_INITIAL_PROMPT, WHISPER_MODEL

try:
    from config import HOTKEY as _HOTKEY

    HOTKEY_HINT = f"{_HOTKEY.upper()} o 'parar' para detener"
except Exception:
    HOTKEY_HINT = "Ctrl+Shift+R o 'parar' para detener"

# Whisper trabaja mejor a 16 kHz mono
TARGET_RATE = 16000
FILENAME = "output_reunion.wav"

q_mic: queue.Queue = queue.Queue()
q_sys: queue.Queue = queue.Queue()
grabando = False
hilo_grabacion = None
_whisper_model = None


def _resample_mono(audio: np.ndarray, orig_rate: int, target_rate: int = TARGET_RATE) -> np.ndarray:
    """Convierte audio float mono a target_rate."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if orig_rate == target_rate or audio.size == 0:
        return audio
    n_out = int(round(audio.size * target_rate / orig_rate))
    return signal.resample(audio, n_out).astype(np.float32)


def _to_mono(indata: np.ndarray) -> np.ndarray:
    if indata.ndim > 1 and indata.shape[1] > 1:
        return indata.mean(axis=1).astype(np.float32)
    return indata.reshape(-1).astype(np.float32)


def _refrescar_dispositivos_audio() -> None:
    """
    Reinicia PortAudio para que Windows reporte el mic/salida actuales
    tras conectar o desconectar audífonos.
    """
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def _es_entrada_util(nombre: str, max_input: int) -> bool:
    if max_input <= 0:
        return False
    n = nombre.lower()
    if "stereo mix" in n or "mezcla" in n or "loopback" in n:
        return False
    return True


def _indice_wasapi() -> int | None:
    for i, h in enumerate(sd.query_hostapis()):
        if "wasapi" in h["name"].lower():
            return i
    return None


def _parece_auricular(nombre: str) -> bool:
    n = nombre.lower()
    claves = (
        "headset",
        "headphone",
        "auricular",
        "audífono",
        "audifono",
        "logitech",
        "bluetooth",
        "hands-free",
        "hands free",
    )
    return any(k in n for k in claves)


def _parece_salida_pc(nombre: str) -> bool:
    n = nombre.lower()
    if _parece_auricular(n):
        return False
    return any(k in n for k in ("altavoz", "speaker", "realtek", "display audio"))


def _buscar_mic_integrado(dispositivos, wasapi_idx: int) -> tuple[int, int] | None:
    """Mic del portátil (Intel/Realtek/array), excluyendo audífonos."""
    preferidos = []
    otros = []
    for i, d in enumerate(dispositivos):
        if d["hostapi"] != wasapi_idx or not _es_entrada_util(d["name"], d["max_input_channels"]):
            continue
        if _parece_auricular(d["name"]):
            continue
        n = d["name"].lower()
        score = 0
        if "intel" in n or "smart sound" in n:
            score += 3
        if "realtek" in n and "mic" in n:
            score += 2
        if "varios mic" in n or "array" in n:
            score += 2
        if "mic" in n or "micró" in n or "micro" in n:
            score += 1
        if score:
            preferidos.append((score, i, int(d["default_samplerate"])))
        else:
            otros.append((i, int(d["default_samplerate"])))

    if preferidos:
        preferidos.sort(key=lambda x: -x[0])
        _, idx, rate = preferidos[0]
        return idx, rate
    if otros:
        return otros[0]
    return None


def _nombre_salida_default_wasapi(dispositivos, wasapi_idx: int | None) -> str:
    if wasapi_idx is None:
        return ""
    def_out = sd.query_hostapis()[wasapi_idx].get("default_output_device", -1)
    if isinstance(def_out, int) and 0 <= def_out < len(dispositivos):
        return dispositivos[def_out]["name"]
    return ""


def _buscar_microfono_wasapi() -> tuple[int, int, str]:
    """
    Micrófono de captura ACTUAL de Windows (WASAPI default).
    Si el default sigue siendo el de audífonos pero la salida ya es Altavoces del PC,
    usa el micrófono integrado (caso típico al desconectar/apagar headset).
    Retorna (índice, sample_rate, nombre).
    """
    _refrescar_dispositivos_audio()
    dispositivos = sd.query_devices()
    wasapi_idx = _indice_wasapi()

    idx_default = None
    rate_default = TARGET_RATE

    # 1) Default de entrada WASAPI
    if wasapi_idx is not None:
        def_in = sd.query_hostapis()[wasapi_idx].get("default_input_device", -1)
        if isinstance(def_in, int) and 0 <= def_in < len(dispositivos):
            d = dispositivos[def_in]
            if _es_entrada_util(d["name"], d["max_input_channels"]):
                idx_default, rate_default = def_in, int(d["default_samplerate"])

    # 2) Emparejar por nombre del default global
    if idx_default is None:
        default_in = sd.default.device[0]
        if isinstance(default_in, int) and 0 <= default_in < len(dispositivos):
            nombre_ref = dispositivos[default_in]["name"]
            nombre_base = nombre_ref.split("(")[0].strip().lower()
            if wasapi_idx is not None:
                for i, d in enumerate(dispositivos):
                    if (
                        d["hostapi"] == wasapi_idx
                        and _es_entrada_util(d["name"], d["max_input_channels"])
                        and (
                            d["name"] == nombre_ref
                            or nombre_base
                            and nombre_base in d["name"].lower()
                        )
                    ):
                        idx_default, rate_default = i, int(d["default_samplerate"])
                        break
            if idx_default is None and _es_entrada_util(
                nombre_ref, dispositivos[default_in]["max_input_channels"]
            ):
                idx_default, rate_default = default_in, int(
                    dispositivos[default_in]["default_samplerate"]
                )

    # 3) Desajuste audífonos (mic) vs altavoces PC (salida) → mic integrado
    if idx_default is not None and wasapi_idx is not None:
        nombre_mic = dispositivos[idx_default]["name"]
        nombre_out = _nombre_salida_default_wasapi(dispositivos, wasapi_idx)
        if _parece_auricular(nombre_mic) and _parece_salida_pc(nombre_out):
            integrado = _buscar_mic_integrado(dispositivos, wasapi_idx)
            if integrado is not None:
                idx_int, rate_int = integrado
                return idx_int, rate_int, dispositivos[idx_int]["name"]

    if idx_default is not None:
        return idx_default, rate_default, dispositivos[idx_default]["name"]

    # 4) Fallback: mic integrado o primera entrada WASAPI útil
    if wasapi_idx is not None:
        integrado = _buscar_mic_integrado(dispositivos, wasapi_idx)
        if integrado is not None:
            idx_int, rate_int = integrado
            return idx_int, rate_int, dispositivos[idx_int]["name"]
        for i, d in enumerate(dispositivos):
            if d["hostapi"] == wasapi_idx and _es_entrada_util(d["name"], d["max_input_channels"]):
                return i, int(d["default_samplerate"]), d["name"]

    raise RuntimeError("No se encontró un micrófono de entrada válido.")


def _buscar_loopback_sistema(p: pyaudio.PyAudio) -> dict:
    """
    Loopback del dispositivo de REPRODUCCIÓN por defecto actual
    (audífonos o altavoces, según lo que Windows tenga activo).
    """
    try:
        info = p.get_default_wasapi_loopback()
        return dict(info)
    except Exception:
        pass

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info.get("isLoopbackDevice") and info.get("maxInputChannels", 0) > 0:
            out = dict(info)
            out["index"] = i
            return out

    raise RuntimeError(
        "No se encontró un dispositivo WASAPI Loopback. "
        "Comprueba que hay un dispositivo de reproducción activo (Altavoces/Auriculares)."
    )


def _firma_dispositivos(refrescar: bool = False) -> tuple:
    """Firma de los defaults actuales (uso al iniciar grabación)."""
    if refrescar:
        _refrescar_dispositivos_audio()
    dispositivos = sd.query_devices()
    wasapi_idx = _indice_wasapi()
    def_in = -1
    def_out = -1
    if wasapi_idx is not None:
        h = sd.query_hostapis()[wasapi_idx]
        def_in = h.get("default_input_device", -1)
        def_out = h.get("default_output_device", -1)

    nombre_in = (
        dispositivos[def_in]["name"]
        if isinstance(def_in, int) and 0 <= def_in < len(dispositivos)
        else ""
    )
    nombre_out = (
        dispositivos[def_out]["name"]
        if isinstance(def_out, int) and 0 <= def_out < len(dispositivos)
        else ""
    )
    return (def_in, def_out, nombre_in, nombre_out)


def _cerrar_stream_mic(stream_mic) -> None:
    if stream_mic is None:
        return
    try:
        stream_mic.stop()
        stream_mic.close()
    except Exception:
        pass


def _cerrar_stream_sys(stream_sys) -> None:
    if stream_sys is None:
        return
    try:
        stream_sys.stop_stream()
        stream_sys.close()
    except Exception:
        pass


def _record_loop():
    """
    Graba mic + sistema de forma continua hasta que grabando=False.
    Sin reabrir streams a mitad (eso cortaba la voz).
    Logs mínimos: solo el latido 🔴 mientras graba.
    """
    global grabando

    rate_mic = TARGET_RATE
    rate_sys = TARGET_RATE
    ch_sys = 2

    def callback_mic(indata, frames, time_info, status):
        # Sin logs por chunk (evita spam)
        q_mic.put((rate_mic, _to_mono(indata)))

    def callback_sys(in_data, frame_count, time_info, status):
        audio = np.frombuffer(in_data, dtype=np.float32)
        if ch_sys > 1:
            audio = audio.reshape(-1, ch_sys).mean(axis=1)
        q_sys.put((rate_sys, audio.astype(np.float32)))
        return (None, pyaudio.paContinue)

    p = pyaudio.PyAudio()
    stream_mic = None
    stream_sys = None
    try:
        idx_mic, rate_mic, nombre_mic = _buscar_microfono_wasapi()
        dispositivos = sd.query_devices()
        max_ch_mic = max(1, min(2, int(dispositivos[idx_mic]["max_input_channels"])))

        loop = _buscar_loopback_sistema(p)
        idx_loop = int(loop["index"])
        rate_sys = int(loop["defaultSampleRate"])
        ch_sys = max(1, int(loop["maxInputChannels"]))
        nombre_sys = loop["name"]

        stream_mic = sd.InputStream(
            samplerate=rate_mic,
            device=idx_mic,
            channels=max_ch_mic,
            dtype="float32",
            callback=callback_mic,
            blocksize=1024,
        )
        stream_sys = p.open(
            format=pyaudio.paFloat32,
            channels=ch_sys,
            rate=rate_sys,
            input=True,
            input_device_index=idx_loop,
            stream_callback=callback_sys,
            frames_per_buffer=1024,
        )
        stream_mic.start()
        stream_sys.start_stream()

        print(f"🔴 GRABANDO — mic: {nombre_mic} | sistema: {nombre_sys}")
        print(f"   ({HOTKEY_HINT})")

        inicio = time.time()
        ultimo_latido = inicio
        while grabando:
            time.sleep(0.25)
            ahora = time.time()
            if ahora - ultimo_latido >= RECORDING_HEARTBEAT_SEC:
                segs = int(ahora - inicio)
                mins, secs = divmod(segs, 60)
                print(f"🔴 {mins:02d}:{secs:02d}")
                ultimo_latido = ahora

    except Exception as e:
        print(f"❌ Error al grabar: {e}")
        grabando = False
    finally:
        _cerrar_stream_mic(stream_mic)
        _cerrar_stream_sys(stream_sys)
        try:
            p.terminate()
        except Exception:
            pass


def _vaciar_colas():
    while not q_mic.empty():
        try:
            q_mic.get_nowait()
        except queue.Empty:
            break
    while not q_sys.empty():
        try:
            q_sys.get_nowait()
        except queue.Empty:
            break


def iniciar_grabacion_manual():
    global grabando, hilo_grabacion
    if grabando:
        return

    _vaciar_colas()
    grabando = True
    hilo_grabacion = threading.Thread(target=_record_loop, daemon=True)
    hilo_grabacion.start()


def _unir_chunks(cola: queue.Queue) -> tuple[np.ndarray | None, int | None]:
    chunks = []
    rate = None
    while not cola.empty():
        r, data = cola.get()
        rate = r
        if data is not None and len(data) > 0:
            chunks.append(data)
    if not chunks:
        return None, None
    return np.concatenate(chunks), rate


def _guardar_wav_mono(audio: np.ndarray, ruta: str) -> None:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak * 0.95
    audio_int16 = (audio * 32767.0).astype(np.int16)
    with wave.open(ruta, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_RATE)
        wf.writeframes(audio_int16.tobytes())


def detener_grabacion_manual() -> dict:
    """
    Detiene y guarda:
      - mix  (mezcla para respaldo)
      - mic  (solo tu voz)
      - sys  (solo audio del PC / reunión)
    Retorna dict con rutas + arrays (para diarización sin releer disco).
    """
    global grabando, hilo_grabacion
    if not grabando:
        return {}

    print("🛑 Deteniendo…")
    grabando = False
    if hilo_grabacion:
        hilo_grabacion.join(timeout=15)
        hilo_grabacion = None
    time.sleep(0.15)

    audio_mic_raw, rate_mic = _unir_chunks(q_mic)
    audio_sys_raw, rate_sys = _unir_chunks(q_sys)

    if audio_mic_raw is None and audio_sys_raw is None:
        print("❌ Sin audio capturado.")
        return {}

    mic = (
        _resample_mono(audio_mic_raw, rate_mic or TARGET_RATE)
        if audio_mic_raw is not None
        else None
    )
    sys_a = (
        _resample_mono(audio_sys_raw, rate_sys or TARGET_RATE)
        if audio_sys_raw is not None
        else None
    )

    if mic is not None and sys_a is not None:
        max_len = max(len(mic), len(sys_a))
        if len(mic) < max_len:
            mic = np.pad(mic, (0, max_len - len(mic)))
        if len(sys_a) < max_len:
            sys_a = np.pad(sys_a, (0, max_len - len(sys_a)))
        audio_final = (mic * 1.0) + (sys_a * 0.85)
    elif mic is not None:
        audio_final = mic
    else:
        audio_final = sys_a

    peak = float(np.max(np.abs(audio_final))) if audio_final.size else 0.0
    if peak <= 0:
        print("❌ Audio en silencio.")
        return {}

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ruta_mix = str((TEMP_DIR / FILENAME).resolve())
    ruta_mic = str((TEMP_DIR / "mic_reunion.wav").resolve())
    ruta_sys = str((TEMP_DIR / "sys_reunion.wav").resolve())

    _guardar_wav_mono(audio_final.copy(), ruta_mix)
    if mic is not None and float(np.max(np.abs(mic))) > 0.001:
        _guardar_wav_mono(mic.copy(), ruta_mic)
    else:
        ruta_mic = ""
        mic = None
    if sys_a is not None and float(np.max(np.abs(sys_a))) > 0.001:
        _guardar_wav_mono(sys_a.copy(), ruta_sys)
    else:
        ruta_sys = ""
        sys_a = None

    dur = len(audio_final) / TARGET_RATE
    print(f"✅ Grabación lista ({dur:.1f}s)")
    return {
        "mix": ruta_mix,
        "mic": ruta_mic or None,
        "sys": ruta_sys or None,
        "audio_mic": mic,
        "audio_sys": sys_a,
    }


def _cargar_whisper():
    global _whisper_model
    if _whisper_model is None:
        print(f"🧠 [WHISPER] Cargando modelo '{WHISPER_MODEL}' (solo la primera vez)...")
        _whisper_model = whisper.load_model(WHISPER_MODEL)
    return _whisper_model


def _cargar_wav_float32(archivo_audio: str) -> np.ndarray:
    """
    Carga un WAV PCM que nosotros generamos (mono 16 kHz).
    Evita depender de ffmpeg (que Whisper usa si le pasas solo la ruta).
    """
    with wave.open(archivo_audio, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Formato WAV no soportado (sampwidth={sampwidth})")

    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)

    if rate != TARGET_RATE:
        audio = _resample_mono(audio, rate, TARGET_RATE)

    return np.ascontiguousarray(audio, dtype=np.float32)


def transcribir_local(archivo_audio: str) -> str:
    print(f"🧠 [WHISPER] Transcribiendo: {archivo_audio}...")
    try:
        time.sleep(0.3)
        if not os.path.exists(archivo_audio):
            return f"Error: No se encontró el archivo {archivo_audio}"

        audio = _cargar_wav_float32(archivo_audio)
        if audio.size == 0:
            return "Error: El archivo de audio está vacío."

        model = _cargar_whisper()
        resultado = model.transcribe(
            audio,
            fp16=False,
            language="es",
            initial_prompt=WHISPER_INITIAL_PROMPT,
            condition_on_previous_text=False,
        )
        texto = (resultado.get("text") or "").strip()
        return _corregir_transcripcion(texto)
    except Exception as e:
        return f"Error en Whisper: {str(e)}"


def _corregir_transcripcion(texto: str) -> str:
    """Ajustes ligeros de fonética / nombres de producto."""
    import re
    from config import CORRECCIONES_TRANSCRIPCION

    out = texto
    for patron, reemplazo in CORRECCIONES_TRANSCRIPCION:
        out = re.sub(patron, reemplazo, out, flags=re.IGNORECASE)
    return out


def esta_grabando() -> bool:
    return grabando
