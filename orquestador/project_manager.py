# project_manager.py
"""Agentes CrewAI: análisis de reunión → JSON + prompt para Cursor."""
from __future__ import annotations

import json
import re

from crewai import Agent, Task, Crew, Process

from config import OLLAMA_LLM, PARTICIPANTES_CONOCIDOS, USUARIO_LOCAL, proyectos_conocidos_para_prompt
from orquestador.task_ownership import normalizar_tareas

ollama_llm = OLLAMA_LLM

analista_pm = Agent(
    role="Product Manager Técnico",
    goal=(
        "Analizar la transcripción, identificar proyecto, rama, tareas y "
        "quién es responsable de cada compromiso."
    ),
    backstory=(
        "Experto en gestión de proyectos. Extrae dueños de tarea solo cuando "
        "el audio lo indica (nombres, 'yo me encargo', 'tú haz…'). "
        "No inventa responsables."
    ),
    llm=ollama_llm,
    verbose=False,
)

desarrollador_ia = Agent(
    role="Ingeniero de Software Senior",
    goal=(
        "Redactar prompts accionables para Cursor con tareas, responsables "
        "y criterios de aceptación, sin inventar stack ni rutas. "
        "Escribe ÚNICAMENTE en español de España/Latinoamérica (alfabeto latino)."
    ),
    backstory=(
        "Desarrollador Full-Stack senior hispanohablante. Escribe instrucciones "
        "imperativas, verificables y listas para pegar en Cursor. "
        "Nunca mezcla ruso, chino u otros alfabetos; usa solo español."
    ),
    llm=ollama_llm,
    verbose=False,
)


def _extraer_json(texto: str) -> dict:
    if not texto:
        raise ValueError("Salida vacía del agente")

    limpio = texto.strip()
    limpio = re.sub(r"^```(?:json)?\s*", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\s*```$", "", limpio)

    try:
        return json.loads(limpio)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", limpio)
    if not match:
        raise ValueError("No se encontró un objeto JSON en la salida")
    return json.loads(match.group(0))


def _normalizar_rama(rama: str) -> str:
    rama = (rama or "feature/tareas-reunion").strip().lower().replace(" ", "-")
    rama = rama.replace("future/", "feature/")
    if not rama.startswith(("feature/", "fix/", "chore/", "docs/", "hotfix/")):
        rama = f"feature/{rama}"
    rama = re.sub(r"[^a-z0-9._/\-]", "", rama)
    rama = re.sub(r"/{2,}", "/", rama)
    return rama[:80] or "feature/tareas-reunion"


def _participantes_para_prompt() -> str:
    nombres = list(dict.fromkeys([USUARIO_LOCAL, *PARTICIPANTES_CONOCIDOS]))
    return ", ".join(nombres)


def _sanear_markdown_es(texto: str) -> str:
    """Quita mezclas típicas de otros alfabetos que a veces inventa el LLM."""
    if not texto:
        return texto
    # Sustituciones frecuentes (ruso / chino → español)
    reemplazos = {
        "фильтр": "filtro",
        "Фильтр": "Filtro",
        "страница": "página",
        "дашборд": "dashboard",
        "проект": "proyecto",
        "前端": "frontend",
        "后端": "backend",
        "项目": "proyecto",
        "功能": "funcionalidad",
    }
    out = texto
    for mal, bien in reemplazos.items():
        out = out.replace(mal, bien)
    # Cirílico
    out = re.sub(r"[\u0400-\u04FF]+", "", out)
    # CJK (chino/japonés/coreano)
    out = re.sub(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"proyecto\s*\(frontend\)", "frontend", out, flags=re.IGNORECASE)
    return out


def ejecutar_flujo_agentes(transcripcion_texto: str) -> dict:
    proyectos = proyectos_conocidos_para_prompt()
    participantes = _participantes_para_prompt()

    tarea_analisis = Task(
        description=(
            f"Analiza detenidamente la siguiente transcripción de la reunión:\n"
            f"'''\n{transcripcion_texto}\n'''\n\n"
            "Proyectos conocidos:\n"
            f"{proyectos}\n\n"
            f"Participantes conocidos (el usuario local / canal mic es '{USUARIO_LOCAL}'): {participantes}\n\n"
            "La transcripción puede venir DIARIZADA con etiquetas:\n"
            f"  [{USUARIO_LOCAL} mm:ss] … → habló el usuario local (micrófono)\n"
            "  [Remoto mm:ss] … → habló alguien de la reunión (audio del PC)\n"
            "  [Remoto_N mm:ss] o un nombre → hablante remoto separado\n\n"
            "Instrucciones:\n"
            "1. Identifica el proyecto SOLO si se nombra de forma explícita. "
            "Usa una de las claves listadas arriba, un nombre libre si aparece en el audio, "
            "o 'General' si no queda claro.\n"
            "2. Diseña una rama Git corta: 'feature/nombre-del-cambio'. "
            "Si suena a 'FUTURE' o 'feature, barra', interpreta 'feature/...'.\n"
            "3. Extrae compromisos como lista de OBJETOS. Cada objeto tiene:\n"
            "   - 'descripcion': qué hay que hacer\n"
            "   - 'responsable': nombre O null\n"
            "   - 'evidencia': frase corta que justifica el responsable\n"
            "4. Cómo inferir responsable (prioridad):\n"
            f"   a) Si el compromiso lo declara [{USUARIO_LOCAL}] "
            f"('yo me encargo', 'lo implemento') → '{USUARIO_LOCAL}'\n"
            "   b) Si un [Remoto] pide explícitamente a alguien por nombre → ese nombre\n"
            f"   c) Si un [Remoto] dice 'tú haz X' dirigiéndose al local → '{USUARIO_LOCAL}'\n"
            "   d) Si un [Remoto_N]/Nombre] se autoasigna → ese speaker\n"
            "   e) Sin pista clara → responsable null\n"
            "5. archivos_mencionados (array) si citan archivos/componentes.\n"
            "REGLA CRÍTICA: No inventes stack, rutas ni responsables.\n\n"
            "Devuelve ÚNICAMENTE JSON con: "
            "'proyecto', 'rama', 'tareas' (array de objetos), 'archivos_mencionados'."
        ),
        expected_output=(
            "JSON puro con proyecto, rama, tareas[{descripcion,responsable,evidencia}], "
            "archivos_mencionados."
        ),
        agent=analista_pm,
    )

    tarea_desarrollo = Task(
        description=(
            "Con el análisis del Product Manager, genera un reporte Markdown para Cursor.\n\n"
            "Estructura obligatoria:\n"
            "- # Prompts de Desarrollo para Cursor (Proyecto: [Nombre])\n"
            "- ## 1. Contexto del Cambio (agnóstico a la tecnología)\n"
            "- ## 2. Lista de tareas (con responsable: Nombre — tarea)\n"
            "- ## 3. Criterios de aceptación\n"
            "- ## 4. Prompt listo para Cursor (Copiar y Pegar)\n\n"
            "Reglas:\n"
            "- IDIOMA: todo el documento en español. PROHIBIDO cirílico u otros alfabetos "
            "(escribe 'filtro', nunca 'фильтр').\n"
            "- En la sección 2, cada ítem debe verse como: "
            "`- **Responsable:** … — descripción` "
            "(usa 'sin asignar' si responsable era null).\n"
            "- El prompt (sección 4) debe ser imperativo y, si hay tareas para "
            f"'{USUARIO_LOCAL}', enfócate en esas; menciona las de otros como contexto/"
            "dependencias.\n"
            "- Debe empezar pidiendo revisar el workspace actual antes de codear.\n"
            "- PROHIBIDO inventar tecnologías o rutas no presentes en las tareas del PM.\n"
            "- Termina con: 'No inventes archivos ni rutas; si falta contexto, "
            "pregunta antes de editar.'"
        ),
        expected_output="Documento Markdown completo en español con las 4 secciones.",
        agent=desarrollador_ia,
        context=[tarea_analisis],
    )

    crew = Crew(
        agents=[analista_pm, desarrollador_ia],
        tasks=[tarea_analisis, tarea_desarrollo],
        process=Process.sequential,
    )

    print("🤖 Analizando reunión (proyecto, tareas y responsables)...")
    resultado_final = crew.kickoff()

    proyecto = "General"
    rama = "feature/tareas-reunion"
    tareas: list = []
    archivos_mencionados: list = []

    try:
        raw_output = tarea_analisis.output.raw if tarea_analisis.output else ""
        datos = _extraer_json(str(raw_output))
        proyecto = str(datos.get("proyecto") or proyecto)
        rama = _normalizar_rama(str(datos.get("rama") or rama))
        tareas = normalizar_tareas(datos.get("tareas"))
        arch_raw = datos.get("archivos_mencionados") or []
        if isinstance(arch_raw, list):
            archivos_mencionados = [str(a) for a in arch_raw]
        elif isinstance(arch_raw, str) and arch_raw.strip():
            archivos_mencionados = [arch_raw]
    except Exception as json_err:
        print(
            f"⚠️ Fallback: no se pudo parsear el JSON del PM ({json_err}). "
            "Usando valores genéricos."
        )

    return {
        "proyecto": proyecto,
        "rama": rama,
        "tareas": tareas,
        "archivos_mencionados": archivos_mencionados,
        "markdown": _sanear_markdown_es(str(resultado_final)),
    }
