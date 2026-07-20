# docs_manager.py
"""Salida unificada bajo docs/[proyecto]/[fecha_hora]/."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from config import DOCS_DIR, FALLIDOS_DIR, resolver_proyecto, slug_carpeta_proyecto


def crear_sesion_docs(nombre_proyecto: str, fecha: datetime | None = None) -> Path:
    """Crea docs/<proyecto>/<YYYY-MM-DD_HH-MM-SS>/ (respeta nombres libres como NovaTrack)."""
    carpeta_proyecto = slug_carpeta_proyecto(nombre_proyecto)
    momento = fecha or datetime.now()
    carpeta = DOCS_DIR / carpeta_proyecto / momento.strftime("%Y-%m-%d_%H-%M-%S")
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _copiar_audio(carpeta: Path, archivo_audio: str | Path | None) -> str | None:
    if not archivo_audio:
        return None
    origen = Path(archivo_audio)
    if not origen.exists():
        return None
    destino = carpeta / "audio_reunion.wav"
    shutil.copy2(origen, destino)
    return destino.name


def guardar_sesion(
    nombre_proyecto: str,
    nombre_rama: str,
    transcripcion: str,
    markdown: str,
    tareas: list | None = None,
    meta_extra: dict | None = None,
    archivo_audio: str | Path | None = None,
) -> Path:
    """
    Persiste la sesión:
      - transcripcion.txt
      - prompt_cursor.md
      - meta.json
      - audio_reunion.wav (si se indica)
    """
    clave_docs = slug_carpeta_proyecto(nombre_proyecto)
    _, ruta_repo = resolver_proyecto(nombre_proyecto)
    carpeta = crear_sesion_docs(nombre_proyecto)

    (carpeta / "transcripcion.txt").write_text(transcripcion.strip() + "\n", encoding="utf-8")
    (carpeta / "prompt_cursor.md").write_text(markdown.strip() + "\n", encoding="utf-8")

    audio_nombre = _copiar_audio(carpeta, archivo_audio)

    meta = {
        "proyecto_detectado": nombre_proyecto,
        "proyecto_clave": clave_docs,
        "ruta_repo": str(ruta_repo),
        "rama": nombre_rama,
        "tareas": tareas or [],
        "archivos": {
            "transcripcion": "transcripcion.txt",
            "prompt": "prompt_cursor.md",
            "audio": audio_nombre,
        },
        "creado_en": datetime.now().isoformat(timespec="seconds"),
    }
    if meta_extra:
        meta.update(meta_extra)

    (carpeta / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"📂 Sesión guardada en: {carpeta}")
    print(f"   • {carpeta / 'prompt_cursor.md'}")
    print(f"   • {carpeta / 'transcripcion.txt'}")
    if audio_nombre:
        print(f"   • {carpeta / audio_nombre}")
    print(f"   • {carpeta / 'meta.json'}")
    return carpeta


def guardar_fallo(
    motivo: str,
    archivo_audio: str | Path | None = None,
    transcripcion: str | None = None,
) -> Path:
    """
    Conserva evidencia cuando falla Whisper u otra etapa temprana.
    docs/_fallidos/<timestamp>/
    """
    FALLIDOS_DIR.mkdir(parents=True, exist_ok=True)
    carpeta = FALLIDOS_DIR / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    carpeta.mkdir(parents=True, exist_ok=True)

    (carpeta / "error.txt").write_text(motivo.strip() + "\n", encoding="utf-8")
    if transcripcion:
        (carpeta / "transcripcion_parcial.txt").write_text(
            transcripcion.strip() + "\n", encoding="utf-8"
        )
    audio_nombre = _copiar_audio(carpeta, archivo_audio)

    meta = {
        "motivo": motivo,
        "audio": audio_nombre,
        "creado_en": datetime.now().isoformat(timespec="seconds"),
    }
    (carpeta / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"💾 Evidencia del fallo guardada en: {carpeta}")
    if audio_nombre:
        print(f"   Puedes reintentar con el WAV: {carpeta / audio_nombre}")
    return carpeta
