# config.py
"""
Configuración central: lee variables desde `.env` (ver `.env.example`).
Los aliases y helpers viven aquí; los valores editables van en `.env`.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
TEMP_DIR = BASE_DIR / ".tmp_audio"
FALLIDOS_DIR = DOCS_DIR / "_fallidos"

# Carga .env de la raíz del proyecto (no pisa variables ya definidas en el sistema)
load_dotenv(BASE_DIR / ".env", override=False)


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "y", "si", "sí", "on")


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_list(key: str, default: list[str] | None = None) -> list[str]:
    raw = _env(key, "")
    if not raw:
        return list(default or [])
    return [p.strip() for p in raw.split(",") if p.strip()]


# --- Desde .env ---
OLLAMA_LLM = _env("OLLAMA_LLM", "ollama/qwen2.5-coder:7b")
WHISPER_MODEL = _env("WHISPER_MODEL", "small")
WHISPER_INITIAL_PROMPT = _env(
    "WHISPER_INITIAL_PROMPT",
    "Reunión técnica sobre VIGO, DET_MINCO, PCE Web, PCM Api, pipelines, "
    "feature, timeout y desarrollo de software.",
)

RECORDING_HEARTBEAT_SEC = _env_int("RECORDING_HEARTBEAT_SEC", 10)
HOTKEY = _env("HOTKEY", "ctrl+shift+r")
AUTO_GIT_COMMIT = _env_bool("AUTO_GIT_COMMIT", True)

USUARIO_LOCAL = _env("USUARIO_LOCAL", "Felipe")
NOMBRAR_REMOTOS = _env_bool("NOMBRAR_REMOTOS", True)
USAR_RECONOCIMIENTO_VOZ = _env_bool("USAR_RECONOCIMIENTO_VOZ", True)
VOICE_MATCH_THRESHOLD = _env_float("VOICE_MATCH_THRESHOLD", 0.72)
VOICE_AUTO_THRESHOLD = _env_float("VOICE_AUTO_THRESHOLD", 0.78)
VOICE_AUTO_APPLY = _env_bool("VOICE_AUTO_APPLY", True)

USE_PYANNOTE = _env_bool("USE_PYANNOTE", True)
HF_TOKEN = _env("HF_TOKEN", "")

PARTICIPANTES_CONOCIDOS: list[str] = _env_list(
    "PARTICIPANTES_CONOCIDOS",
    [USUARIO_LOCAL],
)
if USUARIO_LOCAL and USUARIO_LOCAL not in PARTICIPANTES_CONOCIDOS:
    PARTICIPANTES_CONOCIDOS = [USUARIO_LOCAL, *PARTICIPANTES_CONOCIDOS]

CONFIRMAR_RESPONSABLES = _env_bool("CONFIRMAR_RESPONSABLES", True)

CLAVE_ORQUESTADOR = "automatizar_flujo_trabajo"

# Rutas de producto (opcionales; si vacías no se mapean)
_ruta_vigo_web = _env("RUTA_VIGO_WEB")
_ruta_vigo_api = _env("RUTA_VIGO_API")
_ruta_pipelines = _env("RUTA_PIPELINES")

RUTAS_PROYECTOS: dict[str, Path] = {CLAVE_ORQUESTADOR: BASE_DIR}
if _ruta_vigo_web:
    RUTAS_PROYECTOS["vigo_web"] = Path(_ruta_vigo_web)
if _ruta_vigo_api:
    RUTAS_PROYECTOS["vigo_api"] = Path(_ruta_vigo_api)
if _ruta_pipelines:
    RUTAS_PROYECTOS["pipelines"] = Path(_ruta_pipelines)

# Alias reunión / agente / fonética Whisper → clave canónica
ALIAS_PROYECTOS: dict[str, str] = {
    "vigo": "vigo_web",
    "vigó": "vigo_web",
    "det_minco": "vigo_web",
    "det_minco_pce_web": "vigo_web",
    "det_minco_pce": "vigo_web",
    "pce_web": "vigo_web",
    "front_vigo": "vigo_web",
    "frontend_vigo": "vigo_web",
    "vigo_front": "vigo_web",
    "web_vigo": "vigo_web",
    "det_minco_pcm_api": "vigo_api",
    "det_minco_pcm": "vigo_api",
    "pcm_api": "vigo_api",
    "back_vigo": "vigo_api",
    "backend_vigo": "vigo_api",
    "vigo_back": "vigo_api",
    "api_vigo": "vigo_api",
    "common_pipelines": "pipelines",
    "pipeline": "pipelines",
    "pipelines_common": "pipelines",
    "general": CLAVE_ORQUESTADOR,
}

CORRECCIONES_TRANSCRIPCION: list[tuple[str, str]] = [
    (r"\besperagotado\b", "espera agotado"),
    (r"\btiempo de esperagotado\b", "tiempo de espera agotado"),
    (r"\bregrimento\b", "requerimiento"),
    (r"\bfeature,\s*barra,", "feature/"),
    (r"\bfeature barra,", "feature/"),
    (r"\bFUTURE,", "feature/"),
    (r"\bFuture,", "feature/"),
    (r"\bRAMasFuture\b", "rama feature"),
    (r"\bguion,\s*", "-"),
    (r"\bguión,\s*", "-"),
]


def normalizar_clave(nombre: str) -> str:
    return (
        nombre.lower()
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def slug_carpeta_proyecto(nombre: str) -> str:
    """Nombre de carpeta bajo docs/ para el proyecto."""
    import re

    crudo = (nombre or "").strip()
    if not crudo:
        return "General"

    key = normalizar_clave(crudo)

    if key in ("general", CLAVE_ORQUESTADOR, "automatizar_flujo_trabajo"):
        return "General"

    if key in RUTAS_PROYECTOS and key != CLAVE_ORQUESTADOR:
        return key

    if key in ALIAS_PROYECTOS:
        canonica = ALIAS_PROYECTOS[key]
        if canonica != CLAVE_ORQUESTADOR:
            return canonica

    for alias, canonica in ALIAS_PROYECTOS.items():
        if key == alias:
            return canonica if canonica != CLAVE_ORQUESTADOR else "General"

    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", crudo)
    limpio = re.sub(r"\s+", "_", limpio.strip())
    return limpio or "General"


def resolver_proyecto(nombre: str) -> tuple[str, Path]:
    """Resuelve nombre → (clave, ruta_repo). Nombres libres → docs propios."""
    key = normalizar_clave(nombre)

    if key in RUTAS_PROYECTOS:
        return key, RUTAS_PROYECTOS[key]

    if key in ALIAS_PROYECTOS:
        canonica = ALIAS_PROYECTOS[key]
        if canonica in RUTAS_PROYECTOS:
            return canonica, RUTAS_PROYECTOS[canonica]

    for alias, canonica in ALIAS_PROYECTOS.items():
        if key == alias and canonica in RUTAS_PROYECTOS:
            return canonica, RUTAS_PROYECTOS[canonica]

    return slug_carpeta_proyecto(nombre), BASE_DIR


def proyectos_conocidos_para_prompt() -> str:
    """Lista legible para inyectar en el prompt del agente PM."""
    lineas = []
    if "vigo_web" in RUTAS_PROYECTOS:
        lineas.append(
            "- 'vigo_web' → SOLO si mencionan explícitamente VIGO / DET_MINCO / PCE Web / front VIGO."
        )
    if "vigo_api" in RUTAS_PROYECTOS:
        lineas.append(
            "- 'vigo_api' → SOLO si mencionan API VIGO / PCM Api / backend VIGO."
        )
    if "pipelines" in RUTAS_PROYECTOS:
        lineas.append(
            "- 'pipelines' → SOLO si mencionan pipelines / COMMON_pipelines."
        )
    lineas.extend(
        [
            "- 'General' → si NO queda claro el proyecto, o es un proyecto nuevo no mapeado (NO adivines).",
            "",
            "REGLAS ANTI-ALUCINACIÓN:",
            "- Solo elige claves mapeadas si el nombre del proyecto aparece de forma explícita.",
            "- Si hablan de un proyecto desconocido o hay duda, proyecto = 'General'.",
        ]
    )
    return "\n".join(lineas)
