# project_manager.py
"""Agentes CrewAI: análisis de reunión → JSON + prompt para Cursor."""
from __future__ import annotations

import json
import re

from crewai import Agent, Task, Crew, Process

from config import OLLAMA_LLM, proyectos_conocidos_para_prompt

ollama_llm = OLLAMA_LLM

analista_pm = Agent(
    role="Product Manager Técnico",
    goal=(
        "Analizar la transcripción de la reunión, identificar a qué proyecto pertenece, "
        "extraer las tareas de desarrollo y definir el nombre descriptivo de la feature."
    ),
    backstory=(
        "Experto en gestión de proyectos de software y requerimientos técnicos. "
        "Asocia el contexto solo con proyectos explícitamente mencionados "
        "(VIGO, pipelines u otros nombrados) y corrige errores fonéticos evidentes "
        "(feature/barra, etc.)."
    ),
    llm=ollama_llm,
    verbose=False,
)

desarrollador_ia = Agent(
    role="Ingeniero de Software Senior",
    goal=(
        "Redactar prompts accionables para Cursor: pasos concretos, criterios de "
        "aceptación y restricciones claras sin inventar stack ni rutas."
    ),
    backstory=(
        "Desarrollador Full-Stack senior. Escribe instrucciones imperativas, "
        "verificables y listas para pegar en Cursor."
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


def ejecutar_flujo_agentes(transcripcion_texto: str) -> dict:
    proyectos = proyectos_conocidos_para_prompt()

    tarea_analisis = Task(
        description=(
            f"Analiza detenidamente la siguiente transcripción de la reunión:\n"
            f"'''\n{transcripcion_texto}\n'''\n\n"
            "Proyectos conocidos:\n"
            f"{proyectos}\n\n"
            "Instrucciones:\n"
            "1. Identifica el proyecto SOLO si se nombra de forma explícita. "
            "Claves válidas: 'vigo_web', 'vigo_api', 'pipelines' o 'General'.\n"
            "   - VIGO / DET_MINCO / PCE Web → 'vigo_web'\n"
            "   - API/backend VIGO / PCM → 'vigo_api'\n"
            "   - pipelines / COMMON_pipelines → 'pipelines'\n"
            "   - Proyecto nuevo o poco claro → 'General'\n"
            "   - NUNCA asumas un proyecto mapeado si no se nombró.\n"
            "2. Diseña una rama Git corta: 'feature/nombre-del-cambio'. "
            "Si el audio suena a 'FUTURE' o 'feature, barra', interpreta 'feature/...'.\n"
            "3. Extrae tareas literales (compromisos acordados).\n"
            "4. Si mencionan archivos, componentes, pantallas o módulos, inclúyelos "
            "tal cual en las tareas (no inventes rutas).\n"
            "REGLA CRÍTICA: No deduzcas lenguajes, frameworks, bases de datos ni rutas "
            "de API si no se mencionaron explícitamente.\n\n"
            "Devuelve ÚNICAMENTE un objeto JSON válido con las llaves: "
            "'proyecto', 'rama', 'tareas' (array de strings) y "
            "'archivos_mencionados' (array de strings; vacío si no hubo)."
        ),
        expected_output=(
            "JSON puro con llaves proyecto, rama, tareas, archivos_mencionados."
        ),
        agent=analista_pm,
    )

    tarea_desarrollo = Task(
        description=(
            "Con el análisis del Product Manager, genera un reporte Markdown para Cursor.\n\n"
            "Estructura obligatoria:\n"
            "- # Prompts de Desarrollo para Cursor (Proyecto: [Nombre])\n"
            "- ## 1. Contexto del Cambio (agnóstico a la tecnología)\n"
            "- ## 2. Lista de tareas\n"
            "- ## 3. Criterios de aceptación\n"
            "- ## 4. Prompt listo para Cursor (Copiar y Pegar)\n\n"
            "Reglas del prompt (sección 4):\n"
            "- Tono imperativo, técnico, pasos numerados.\n"
            "- Debe empezar pidiendo revisar el workspace actual antes de codear.\n"
            "- Si el PM listó archivos/componentes mencionados, cítalos y pide "
            "localizarlos en el repo (sin inventar rutas absolutas).\n"
            "- Incluye criterios de aceptación verificables (qué debe pasar / qué no).\n"
            "- PROHIBIDO inventar tecnologías, carpetas o endpoints no presentes "
            "en las tareas del PM.\n"
            "- Si no hubo stack en la reunión, incluye: "
            "'Lee el contexto de mi espacio de trabajo actual para determinar el "
            "lenguaje y framework utilizado...'\n"
            "- Termina con: 'No inventes archivos ni rutas; si falta contexto, "
            "pregunta antes de editar.'"
        ),
        expected_output="Documento Markdown completo con las 4 secciones.",
        agent=desarrollador_ia,
        context=[tarea_analisis],
    )

    crew = Crew(
        agents=[analista_pm, desarrollador_ia],
        tasks=[tarea_analisis, tarea_desarrollo],
        process=Process.sequential,
    )

    print("🤖 Iniciando el análisis con los agentes locales (Qwen)...")
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
        tareas_raw = datos.get("tareas") or []
        if isinstance(tareas_raw, list):
            tareas = [str(t) for t in tareas_raw]
        elif isinstance(tareas_raw, str):
            tareas = [tareas_raw]
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
        "markdown": str(resultado_final),
    }
