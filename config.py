# config.py
"""Configuración central del asistente de reuniones."""
from pathlib import Path

# Raíz de esta herramienta (siempre absoluta, independiente del CWD)
BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
TEMP_DIR = BASE_DIR / ".tmp_audio"
FALLIDOS_DIR = DOCS_DIR / "_fallidos"

# Modelo local (Ollama vía CrewAI)
OLLAMA_LLM = "ollama/qwen2.5-coder:7b"

# Whisper: small = mejor precisión que base (más lento al cargar la 1ª vez)
WHISPER_MODEL = "small"

# Ayuda a Whisper a reconocer nombres de producto (español)
WHISPER_INITIAL_PROMPT = (
    "Reunión técnica sobre VIGO, DET_MINCO, PCE Web, PCM Api, pipelines, "
    "feature, timeout y desarrollo de software."
)

# Cada N segundos mientras graba, imprime estado en consola
RECORDING_HEARTBEAT_SEC = 10

# Hotkey global para alternar grabar/parar
HOTKEY = "ctrl+shift+r"

# Si True, tras confirmar Y/N, crea rama + commit en el repo de PRODUCTO (nunca aquí)
AUTO_GIT_COMMIT = True

# Quién eres tú en las reuniones (canal micrófono en la diarización)
USUARIO_LOCAL = "Felipe"

# Tras cada reunión: pedir nombre de cada Remoto_N mostrando qué dijo
NOMBRAR_REMOTOS = True

# Reconocimiento de voz + active learning (biblioteca en .voice_profiles/).
# 1ª vez que aparece alguien → escribes el nombre → se guarda el perfil.
# Próximas veces → si la voz coincide se asigna sola y se refuerza el perfil.
# Requiere pyannote.audio + token HF (modelo pyannote/embedding). No es 100 % fiable.
USAR_RECONOCIMIENTO_VOZ = True
VOICE_MATCH_THRESHOLD = 0.72   # mínimo para sugerir / considerar match
VOICE_AUTO_THRESHOLD = 0.78    # mínimo para asignar sin preguntar
VOICE_AUTO_APPLY = True        # True = active learning automático cuando hay confianza

# Diarización fina del canal remoto (varios speakers en Teams).
# True = intenta separar Remoto_1, Remoto_2, … (recomendado en Teams real).
# Requisitos:
# 1) $env:HF_TOKEN = "hf_..."  (no lo subas a git)
# 2) pip install pyannote.audio
# 3) Aceptar condiciones (logueado en HF) en:
#    - https://huggingface.co/pyannote/speaker-diarization-3.1
#    - https://huggingface.co/pyannote/segmentation-3.0
#    - https://huggingface.co/pyannote/speaker-diarization-community-1
#    - https://huggingface.co/pyannote/embedding  (para reconocimiento de voz)
USE_PYANNOTE = True
HF_TOKEN = ""

# Sugerencias al escribir nombres (no se asignan solos por orden de habla).
PARTICIPANTES_CONOCIDOS: list[str] = [
    "Felipe",
    # "Ana",
    # "Carlos",
]

# Si True, pregunta por consola el responsable de cada tarea sin dueño claro
CONFIRMAR_RESPONSABLES = True

# Clave del orquestador: solo docs locales, sin ramas Git en este repo
CLAVE_ORQUESTADOR = "automatizar_flujo_trabajo"

# ---------------------------------------------------------------------------
# Mapa de proyectos reales en esta máquina
# ---------------------------------------------------------------------------
RUTAS_PROYECTOS: dict[str, Path] = {
    "vigo_web": Path(
        r"C:\Users\Felipe Lisboa\Documents\PROYECTOS\VIGO\Código_fuente\DET_MINCO_PCE_Web"
    ),
    "vigo_api": Path(
        r"C:\Users\Felipe Lisboa\Documents\PROYECTOS\VIGO\Código_fuente\DET_MINCO_PCM_Api"
    ),
    "pipelines": Path(
        r"C:\Users\Felipe Lisboa\Documents\PROYECTOS\Pipelines\COMMON_pipelines"
    ),
    CLAVE_ORQUESTADOR: BASE_DIR,
}

# Alias reunión / agente / fonética Whisper → clave canónica
ALIAS_PROYECTOS: dict[str, str] = {
    # VIGO front
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
    # API
    "det_minco_pcm_api": "vigo_api",
    "det_minco_pcm": "vigo_api",
    "pcm_api": "vigo_api",
    "back_vigo": "vigo_api",
    "backend_vigo": "vigo_api",
    "vigo_back": "vigo_api",
    "api_vigo": "vigo_api",
    # Pipelines
    "common_pipelines": "pipelines",
    "pipeline": "pipelines",
    "pipelines_common": "pipelines",
    "general": CLAVE_ORQUESTADOR,
}

# Correcciones ligeras post-Whisper (errores fonéticos habituales)
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
    """
    Nombre de carpeta bajo docs/ para el proyecto.
    - Claves mapeadas → vigo_web, vigo_api, pipelines
    - General / orquestador → General
    - Nombre libre (ej. NovaTrack) → se respeta (sanitizado)
    """
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
    """
    Resuelve un nombre a (clave_para_git_o_docs, ruta_repo).
    Nombres libres desconocidos → docs con su propio slug; Git = orquestador (sin rama).
    """
    key = normalizar_clave(nombre)

    if key in RUTAS_PROYECTOS:
        return key, RUTAS_PROYECTOS[key]

    if key in ALIAS_PROYECTOS:
        canonica = ALIAS_PROYECTOS[key]
        return canonica, RUTAS_PROYECTOS[canonica]

    for alias, canonica in ALIAS_PROYECTOS.items():
        if key == alias:
            return canonica, RUTAS_PROYECTOS[canonica]
    for canonica in RUTAS_PROYECTOS:
        if key == canonica:
            return canonica, RUTAS_PROYECTOS[canonica]

    return slug_carpeta_proyecto(nombre), BASE_DIR


def proyectos_conocidos_para_prompt() -> str:
    """Lista legible para inyectar en el prompt del agente PM."""
    return "\n".join(
        [
            "- 'vigo_web' → SOLO si mencionan explícitamente VIGO / DET_MINCO / PCE Web / front VIGO.",
            "- 'vigo_api' → SOLO si mencionan API VIGO / PCM Api / backend VIGO.",
            "- 'pipelines' → SOLO si mencionan pipelines / COMMON_pipelines.",
            "- 'General' → si NO queda claro el proyecto, o es un proyecto nuevo no mapeado (NO adivines).",
            "",
            "REGLAS ANTI-ALUCINACIÓN:",
            "- Solo elige vigo_web / vigo_api / pipelines si el nombre del proyecto aparece de forma explícita.",
            "- Si hablan de un proyecto desconocido o hay duda, proyecto = 'General'.",
        ]
    )
