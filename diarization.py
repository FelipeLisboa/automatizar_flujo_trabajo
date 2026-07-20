# diarization.py
"""
Diarización optimizada para este orquestador.

Estrategia principal (siempre activa):
  - Canal micrófono  → usuario local (USUARIO_LOCAL)
  - Canal sistema    → participante(s) remoto(s) (Teams / navegador)

Opcional (si HF_TOKEN está configurado):
  - pyannote.audio sobre el canal remoto para separar Remoto_1, Remoto_2, ...
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from config import (
    PARTICIPANTES_CONOCIDOS,
    USUARIO_LOCAL,
    WHISPER_INITIAL_PROMPT,
    WHISPER_MODEL,
)


def _peak(audio: np.ndarray) -> float:
    if audio is None or audio.size == 0:
        return 0.0
    return float(np.max(np.abs(audio)))


def _transcribir_segmentos(audio: np.ndarray, model) -> list[dict]:
    """Whisper → lista de {start, end, text}."""
    from audio_processor import TARGET_RATE, _corregir_transcripcion

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
    # Fallback si no hay segments pero sí texto plano
    if not segs:
        texto = _corregir_transcripcion((resultado.get("text") or "").strip())
        if texto:
            dur = len(audio) / 16000.0
            segs.append({"start": 0.0, "end": dur, "text": texto})
    return segs


def _diarizar_remoto_pyannote(ruta_wav: str) -> list[tuple[float, float, str]] | None:
    """
    Retorna [(start, end, 'Remoto_1'), ...] o None si no hay token / falla.
    Requiere: pip install pyannote.audio  y HF_TOKEN con acceso al modelo.
    """
    token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
    try:
        from config import HF_TOKEN as CFG_TOKEN  # type: ignore

        token = token or (CFG_TOKEN or "").strip()
    except Exception:
        pass

    if not token:
        return None
    if not ruta_wav or not Path(ruta_wav).exists():
        return None

    try:
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
        diarization = pipeline(ruta_wav)
        turns: list[tuple[float, float, str]] = []
        speaker_map: dict[str, str] = {}
        next_id = 1
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if speaker not in speaker_map:
                # Intentar mapear al siguiente participante conocido (excepto usuario local)
                remotos = [p for p in PARTICIPANTES_CONOCIDOS if p.lower() != USUARIO_LOCAL.lower()]
                if next_id <= len(remotos):
                    speaker_map[speaker] = remotos[next_id - 1]
                else:
                    speaker_map[speaker] = f"Remoto_{next_id}"
                next_id += 1
            turns.append((float(turn.start), float(turn.end), speaker_map[speaker]))
        return turns
    except Exception as e:
        print(f"ℹ️ Diarización pyannote no disponible ({e}). Usando Remoto único.")
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
                overlap = max(0.0, min(s["end"], t1) - max(s["start"], t0))
                if overlap > best_overlap:
                    best_overlap = overlap
                    label = spk
        out.append({**s, "speaker": label})
    return out


def construir_transcripcion_diarizada(
    audio_mic: np.ndarray | None,
    audio_sys: np.ndarray | None,
    ruta_sys_wav: str | None = None,
) -> dict:
    """
    Transcribe por canal y arma texto etiquetado + plano.

    Retorna:
      {
        "diarizada": str,   # para agentes
        "plana": str,       # concatenación simple
        "segmentos": list,
        "modo": "mic_sys" | "mic_sys+pyannote" | "mix_fallback"
      }
    """
    from audio_processor import _cargar_whisper

    model = _cargar_whisper()
    print("🧠 Diarización: transcribiendo micrófono (tú) y sistema (remotos)…")

    segs_mic = _transcribir_segmentos(audio_mic, model)
    segs_sys = _transcribir_segmentos(audio_sys, model)

    turns_remoto = _diarizar_remoto_pyannote(ruta_sys_wav) if ruta_sys_wav else None
    modo = "mic_sys+pyannote" if turns_remoto else "mic_sys"

    labeled_mic = _asignar_speaker_a_segmentos(segs_mic, None, USUARIO_LOCAL)
    labeled_sys = _asignar_speaker_a_segmentos(
        segs_sys, turns_remoto, "Remoto" if not turns_remoto else "Remoto_1"
    )

    # Si pyannote no corrió, un solo label Remoto está bien
    if not turns_remoto:
        labeled_sys = [{**s, "speaker": "Remoto"} for s in labeled_sys]

    todos = labeled_mic + labeled_sys
    todos.sort(key=lambda x: (x["start"], x["end"]))

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
    }


def transcribir_desde_captura(captura: dict) -> dict:
    """
    Entrada: dict de detener_grabacion_manual()
      {mix, mic, sys, audio_mic, audio_sys}
    """
    from audio_processor import _cargar_wav_float32

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

    # Fallback: solo mix
    if (audio_mic is None or _peak(audio_mic) < 0.001) and (
        audio_sys is None or _peak(audio_sys) < 0.001
    ):
        mix = captura.get("mix")
        if mix:
            from audio_processor import transcribir_local

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
