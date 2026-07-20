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

# Carga .env de la raíz (pisa valores vacíos del entorno para que HF_TOKEN del archivo cuente)
load_dotenv(BASE_DIR / ".env", override=True)


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
    "Reunión de desarrollo de software en español. Tareas, features, dashboard, "
    "filtros, paginación, commits y pull requests.",
)

RECORDING_HEARTBEAT_SEC = _env_int("RECORDING_HEARTBEAT_SEC", 10)
HOTKEY = _env("HOTKEY", "ctrl+shift+r")
AUTO_GIT_COMMIT = _env_bool("AUTO_GIT_COMMIT", True)

USUARIO_LOCAL = _env("USUARIO_LOCAL", "Usuario")
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


def _cargar_rutas_proyectos() -> dict[str, Path]:
    """
    Proyectos custom desde .env. Cualquier usuario define los suyos:

      PROYECTO_mi_front=C:\\ruta\\al\\repo
      PROYECTO_mi_api=C:\\otra\\ruta

    También acepta variables legacy RUTA_<CLAVE>=ruta (opcional).
    """
    rutas: dict[str, Path] = {CLAVE_ORQUESTADOR: BASE_DIR}

    # Formato genérico: PROYECTO_<clave>=ruta
    for key, value in os.environ.items():
        if not key.startswith("PROYECTO_"):
            continue
        clave = key[len("PROYECTO_") :].strip().lower()
        ruta = (value or "").strip().strip('"').strip("'")
        if not clave or not ruta or clave in ("", CLAVE_ORQUESTADOR):
            continue
        if clave in ("general",):
            continue
        rutas[clave] = Path(ruta)

    # Legacy: RUTA_<CLAVE>=ruta (cualquier clave, no hardcodeada)
    for key, value in os.environ.items():
        if not key.startswith("RUTA_"):
            continue
        clave = key[len("RUTA_") :].strip().lower()
        ruta = (value or "").strip().strip('"').strip("'")
        if not clave or not ruta or clave in rutas or clave == CLAVE_ORQUESTADOR:
            continue
        if clave in ("general",):
            continue
        rutas[clave] = Path(ruta)

    return rutas


def _cargar_aliases(rutas: dict[str, Path]) -> dict[str, str]:
    """
    Aliases desde .env:

      ALIAS_PROYECTOS=front=mi_front,api=mi_api

    Además se generan aliases automáticos por cada clave mapeada
    (ej. mi_front → mi_front, mi front; prefijo mi_front → mi si no choca).
    """
    aliases: dict[str, str] = {"general": CLAVE_ORQUESTADOR}

    # Auto: la propia clave y versión con espacios
    for clave in rutas:
        if clave == CLAVE_ORQUESTADOR:
            continue
        aliases[clave] = clave
        aliases[clave.replace("_", " ")] = clave
        # Prefijo antes del primer _ (mi_front → mi) solo si no choca
        if "_" in clave:
            pref = clave.split("_", 1)[0]
            if pref and pref not in aliases:
                aliases[pref] = clave

    # Manual desde .env: alias=clave,alias2=clave2
    raw = _env("ALIAS_PROYECTOS")
    if raw:
        for parte in raw.split(","):
            parte = parte.strip()
            if not parte or "=" not in parte:
                continue
            alias, clave = parte.split("=", 1)
            alias_n = normalizar_clave(alias)
            clave_n = normalizar_clave(clave)
            if alias_n and clave_n:
                aliases[alias_n] = clave_n

    return aliases


# Debe existir antes de _cargar_aliases (usa normalizar_clave más abajo);
# definimos un stub y reasignamos tras la función real.
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


RUTAS_PROYECTOS: dict[str, Path] = _cargar_rutas_proyectos()
ALIAS_PROYECTOS: dict[str, str] = _cargar_aliases(RUTAS_PROYECTOS)

# Claves que el menú puede listar (todos los mapeados + General)
CLAVES_PROYECTOS_MENU: list[str] = [
    *[k for k in RUTAS_PROYECTOS if k != CLAVE_ORQUESTADOR],
    "General",
]

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
        if canonica != CLAVE_ORQUESTADOR and canonica in RUTAS_PROYECTOS:
            return canonica

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

    return slug_carpeta_proyecto(nombre), BASE_DIR


def proyectos_conocidos_para_prompt() -> str:
    """Lista legible para inyectar en el prompt del agente PM (dinámica)."""
    lineas = []
    for clave in RUTAS_PROYECTOS:
        if clave == CLAVE_ORQUESTADOR:
            continue
        aliases = sorted(
            a for a, c in ALIAS_PROYECTOS.items() if c == clave and a != clave
        )[:6]
        extra = f" (también: {', '.join(aliases)})" if aliases else ""
        lineas.append(
            f"- '{clave}' → SOLO si mencionan explícitamente ese proyecto{extra}."
        )
    lineas.extend(
        [
            "- 'General' → si NO queda claro el proyecto, o es un proyecto nuevo no mapeado (NO adivines).",
            "",
            "REGLAS ANTI-ALUCINACIÓN:",
            "- Solo elige una clave mapeada si el nombre aparece de forma explícita en el audio.",
            "- Si hablan de un proyecto desconocido o hay duda, proyecto = 'General'.",
        ]
    )
    return "\n".join(lineas)
