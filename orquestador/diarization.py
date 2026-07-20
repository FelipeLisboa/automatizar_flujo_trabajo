# diarization.py
"""
Diarización optimizada para este orquestador.

Estrategia principal (siempre activa):
  - Canal micrófono  → usuario local (USUARIO_LOCAL)
  - Canal sistema    → participante(s) remoto(s) (Teams / navegador)

Si hablas encima del remoto, los segmentos del mic se reordenan
después del tramo remoto solapado (transcripción más legible para los agentes).

Opcional (USE_PYANNOTE=True + HF_TOKEN + modelos gated aceptados):
  - pyannote.audio sobre el canal remoto para separar Remoto_1, Remoto_2, ...
"""
from __future__ import annotations

import os
import re
import warnings

import numpy as np

from config import (
    USUARIO_LOCAL,
    USE_PYANNOTE,
    WHISPER_INITIAL_PROMPT,
    WHISPER_MODEL,
)


def _peak(audio: np.ndarray) -> float:
    if audio is None or audio.size == 0:
        return 0.0
    return float(np.max(np.abs(audio)))


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _transcribir_segmentos(audio: np.ndarray, model) -> list[dict]:
    """Whisper → lista de {start, end, text}."""
    from orquestador.audio_processor import TARGET_RATE, _corregir_transcripcion

    if audio is None or audio.size == 0 or _peak(audio) < 0.001:
        return []

    resultado = model.transcribe(
        np.ascontiguousarray(audio, dtype=np.float32),
        fp16=False,
        language="es",
        initial_prompt=WHISPER_INITIAL_PROMPT,
        condition_on_previous_text=False,
        word_timestamps=False,
    )
    segs = []
    for s in resultado.get("segments") or []:
        texto = _corregir_transcripcion((s.get("text") or "").strip())
        if not texto:
            continue
        segs.append(
            {
                "start": float(s.get("start") or 0.0),
                "end": float(s.get("end") or 0.0),
                "text": texto,
            }
        )
    if not segs:
        texto = _corregir_transcripcion((resultado.get("text") or "").strip())
        if texto:
            dur = len(audio) / float(TARGET_RATE)
            segs.append({"start": 0.0, "end": dur, "text": texto})
    return segs


def _hf_token() -> str:
    token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
    try:
        from config import HF_TOKEN as CFG_TOKEN  # type: ignore

        token = token or (CFG_TOKEN or "").strip()
    except Exception:
        pass
    return token


def _annotation_desde_salida(diarization):
    """pyannote 4.x → DiarizeOutput.speaker_diarization; 3.x → Annotation directa."""
    ann = getattr(diarization, "speaker_diarization", None)
    if ann is not None:
        return ann
    ann = getattr(diarization, "exclusive_speaker_diarization", None)
    if ann is not None:
        return ann
    return diarization


def _mensaje_pyannote(err: Exception) -> str:
    txt = str(err)
    if "403" in txt or "gated" in txt.lower() or "authorized" in txt.lower():
        return (
            "pyannote: falta aceptar el modelo gated en Hugging Face → "
            "https://huggingface.co/pyannote/speaker-diarization-community-1 "
            "(y diarization-3.1 / segmentation-3.0). Usando Remoto único."
        )
    if len(txt) > 180:
        txt = txt[:180] + "…"
    return f"pyannote no disponible ({txt}). Usando Remoto único."


def _suprimir_eco_sistema(
    audio_mic: np.ndarray | None,
    audio_sys: np.ndarray | None,
    rate: int,
) -> np.ndarray | None:
    """
    Atenúa el mic cuando el sistema suena fuerte (bleed de auriculares/altavoces).
    Evita que Whisper invente basura tipo 'CPU Master / Super hero' en el canal del mic.
    """
    if audio_mic is None or audio_sys is None:
        return audio_mic
    mic = np.ascontiguousarray(audio_mic, dtype=np.float32).copy()
    sys_a = np.ascontiguousarray(audio_sys, dtype=np.float32)
    n = min(len(mic), len(sys_a))
    if n < max(rate // 5, 1):
        return mic
    mic = mic[:n]
    sys_a = sys_a[:n]
    frame = max(1, int(rate * 0.03))
    hop = max(1, frame // 2)
    for i in range(0, n - frame + 1, hop):
        w_sys = sys_a[i : i + frame]
        w_mic = mic[i : i + frame]
        rms_sys = float(np.sqrt(np.mean(w_sys * w_sys)))
        rms_mic = float(np.sqrt(np.mean(w_mic * w_mic)))
        if rms_sys > 0.015 and rms_mic < rms_sys * 2.2:
            mic[i : i + frame] *= 0.04
    return mic


def _rms_ventana(audio: np.ndarray | None, t0: float, t1: float, rate: int) -> float:
    if audio is None or audio.size == 0:
        return 0.0
    i0 = max(0, int(t0 * rate))
    i1 = min(len(audio), max(i0 + 1, int(t1 * rate)))
    w = audio[i0:i1]
    if w.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(w.astype(np.float32) ** 2)))


_BASURA_MIC = re.compile(
    r"\b("
    r"cpu|master|super\s*hero|custom|digest|gekcue|jcw|"
    r"design|gaming|logitech|windows|microsoft"
    r")\b",
    re.IGNORECASE,
)


def _filtrar_segmentos_mic_eco(
    segs_mic: list[dict],
    segs_sys: list[dict],
    audio_mic: np.ndarray | None,
    audio_sys: np.ndarray | None,
    rate: int,
) -> list[dict]:
    """Quita segmentos del mic que son eco del sistema o alucinaciones cortas."""
    if not segs_mic:
        return []
    out: list[dict] = []
    descartados = 0
    for s in segs_mic:
        texto = (s.get("text") or "").strip()
        if not texto:
            continue
        solapa = any(
            _overlap(s["start"], s["end"], r["start"], r["end"]) > 0.25 for r in segs_sys
        )
        rms_m = _rms_ventana(audio_mic, s["start"], s["end"], rate)
        rms_s = _rms_ventana(audio_sys, s["start"], s["end"], rate)
        eco_energia = solapa and rms_s > 0.02 and rms_m < rms_s * 1.6
        basura = bool(_BASURA_MIC.search(texto)) and (
            solapa or len(texto.split()) <= 5
        )
        # Fragmentos muy cortos sin sentido durante el remoto
        corto_raro = (
            solapa
            and len(texto.split()) <= 3
            and not re.search(
                r"\b(ok|okay|sí|si|vale|yo|me|lo|tengo|encargo|perfecto)\b",
                texto,
                re.I,
            )
        )
        if eco_energia or basura or corto_raro:
            descartados += 1
            continue
        out.append(s)
    if descartados:
        print(f"🧹 Eco/mic: se descartaron {descartados} segmento(s) basura del micrófono")
    return out


def _diarizar_remoto_pyannote(audio_sys: np.ndarray | None) -> list[tuple[float, float, str]] | None:
    """
    Retorna [(start, end, 'Remoto_1'), ...] o None si está desactivado / falla.
    Usa waveform en memoria (evita depender de torchcodec/ffmpeg en Windows).
    """
    if not USE_PYANNOTE:
        return None
    token = _hf_token()
    if not token:
        print("ℹ️ USE_PYANNOTE=True pero no hay HF_TOKEN. Usando Remoto único.")
        return None
    if audio_sys is None or _peak(audio_sys) < 0.001:
        return None

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    try:
        import torch
        from orquestador.audio_processor import TARGET_RATE

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyannote.audio import Pipeline

            try:
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=token,
                )
            except TypeError:
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=token,
                )

            wave = torch.from_numpy(
                np.ascontiguousarray(audio_sys, dtype=np.float32)
            ).unsqueeze(0)
            diarization = pipeline({"waveform": wave, "sample_rate": TARGET_RATE})

        annotation = _annotation_desde_salida(diarization)
        turns: list[tuple[float, float, str]] = []
        speaker_map: dict[str, str] = {}
        next_id = 1
        # Solo etiquetas Remoto_N — los nombres reales se piden después (speaker_registry)
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            if speaker not in speaker_map:
                speaker_map[speaker] = f"Remoto_{next_id}"
                next_id += 1
            turns.append((float(turn.start), float(turn.end), speaker_map[speaker]))
        if turns:
            print(f"🎧 pyannote: {len(speaker_map)} hablante(s) remoto(s) en el canal sistema")
        return turns or None
    except Exception as e:
        print(f"ℹ️ {_mensaje_pyannote(e)}")
        return None


def _asignar_speaker_a_segmentos(
    segs: list[dict],
    turns: list[tuple[float, float, str]] | None,
    default_label: str,
) -> list[dict]:
    """Etiqueta cada segmento Whisper con el speaker de mayor solape temporal."""
    out = []
    for s in segs:
        label = default_label
        if turns:
            best_overlap = 0.0
            for t0, t1, spk in turns:
                ov = _overlap(s["start"], s["end"], t0, t1)
                if ov > best_overlap:
                    best_overlap = ov
                    label = spk
        out.append({**s, "speaker": label})
    return out


def _reordenar_solapes(segmentos: list[dict]) -> list[dict]:
    """
    Si el local habla encima del remoto, mueve esos segmentos del mic
    justo después del tramo remoto solapado (mejor lectura para LLM).
    Conserva el end original si la frase terminó después del remoto.
    """
    if not segmentos:
        return []

    remotos = [s for s in segmentos if s.get("speaker") != USUARIO_LOCAL]
    locales = [s for s in segmentos if s.get("speaker") == USUARIO_LOCAL]

    ajustados: list[dict] = []
    for s in locales:
        solapados = [
            r
            for r in remotos
            if _overlap(s["start"], s["end"], r["start"], r["end"]) > 0.15
        ]
        if solapados:
            nuevo_start = max(r["end"] for r in solapados)
            nuevo_end = s["end"] if s["end"] > nuevo_start else nuevo_start + max(
                0.05, s["end"] - s["start"]
            )
            ajustados.append(
                {
                    **s,
                    "start": nuevo_start,
                    "end": nuevo_end,
                    "_reordenado": True,
                }
            )
        else:
            ajustados.append(dict(s))

    todos = remotos + ajustados
    todos.sort(
        key=lambda x: (
            x["start"],
            0 if x.get("speaker") != USUARIO_LOCAL else 1,
            x["end"],
        )
    )
    return todos


def construir_transcripcion_diarizada(
    audio_mic: np.ndarray | None,
    audio_sys: np.ndarray | None,
    ruta_sys_wav: str | None = None,
) -> dict:
    """
    Transcribe por canal y arma texto etiquetado + plano.

    Retorna:
      {
        "diarizada": str,
        "plana": str,
        "segmentos": list,
        "modo": "mic_sys" | "mic_sys+pyannote" | "mix_fallback"
      }
    """
    from orquestador.audio_processor import TARGET_RATE, _cargar_whisper

    _ = ruta_sys_wav  # legacy; pyannote usa array en memoria
    model = _cargar_whisper()
    print("🧠 Diarización: transcribiendo micrófono (tú) y sistema (remotos)…")

    mic_limpio = _suprimir_eco_sistema(audio_mic, audio_sys, TARGET_RATE)

    segs_sys = _transcribir_segmentos(audio_sys, model)
    segs_mic = _transcribir_segmentos(mic_limpio, model)
    segs_mic = _filtrar_segmentos_mic_eco(
        segs_mic, segs_sys, mic_limpio, audio_sys, TARGET_RATE
    )

    turns_remoto = _diarizar_remoto_pyannote(audio_sys)
    modo = "mic_sys+pyannote" if turns_remoto else "mic_sys"

    labeled_mic = _asignar_speaker_a_segmentos(segs_mic, None, USUARIO_LOCAL)
    if turns_remoto:
        labeled_sys = _asignar_speaker_a_segmentos(segs_sys, turns_remoto, "Remoto_1")
    else:
        labeled_sys = [{**s, "speaker": "Remoto"} for s in segs_sys]

    todos = _reordenar_solapes(labeled_mic + labeled_sys)

    lineas = []
    for s in todos:
        t0 = s["start"]
        mm, ss = divmod(int(t0), 60)
        lineas.append(f"[{s['speaker']} {mm:02d}:{ss:02d}] {s['text']}")

    diarizada = "\n".join(lineas).strip()
    plana = " ".join(s["text"] for s in todos).strip()

    if not diarizada:
        return {
            "diarizada": "",
            "plana": "",
            "segmentos": [],
            "modo": "vacio",
        }

    print(f"✅ Diarización lista ({modo}): {len(todos)} segmentos")
    return {
        "diarizada": diarizada,
        "plana": plana,
        "segmentos": todos,
        "modo": modo,
        "audio_sys": audio_sys,
    }


def transcribir_desde_captura(captura: dict) -> dict:
    """
    Entrada: dict de detener_grabacion_manual()
      {mix, mic, sys, audio_mic, audio_sys}
    """
    from orquestador.audio_processor import _cargar_wav_float32

    audio_mic = captura.get("audio_mic")
    audio_sys = captura.get("audio_sys")

    if audio_mic is None and captura.get("mic"):
        try:
            audio_mic = _cargar_wav_float32(captura["mic"])
        except Exception:
            audio_mic = None
    if audio_sys is None and captura.get("sys"):
        try:
            audio_sys = _cargar_wav_float32(captura["sys"])
        except Exception:
            audio_sys = None

    if (audio_mic is None or _peak(audio_mic) < 0.001) and (
        audio_sys is None or _peak(audio_sys) < 0.001
    ):
        mix = captura.get("mix")
        if mix:
            from orquestador.audio_processor import transcribir_local

            texto = transcribir_local(mix)
            return {
                "diarizada": texto,
                "plana": texto,
                "segmentos": [],
                "modo": "mix_fallback",
            }

    return construir_transcripcion_diarizada(
        audio_mic,
        audio_sys,
        ruta_sys_wav=captura.get("sys"),
    )
