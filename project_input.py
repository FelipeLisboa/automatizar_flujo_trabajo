# project_input.py
"""Detección de proyecto desde la transcripción + pedido por consola si hay duda."""
from __future__ import annotations

import re

from config import (
    ALIAS_PROYECTOS,
    CLAVE_ORQUESTADOR,
    RUTAS_PROYECTOS,
    normalizar_clave,
    resolver_proyecto,
)

# Claves que el usuario puede elegir
CLAVES_SELECCIONABLES = [
    "vigo_web",
    "vigo_api",
    "pipelines",
    "General",
]


def _texto_norm(texto: str) -> str:
    return (
        texto.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def detectar_menciones(texto: str) -> dict[str, bool]:
    """Señales explícitas en la transcripción (VIGO / pipelines)."""
    t = _texto_norm(texto)
    return {
        "vigo": bool(
            re.search(
                r"\bvigo\b|\bdet[\s_\-]?minco\b|\bpce[\s_\-]?web\b|\bpcm[\s_\-]?api\b|"
                r"\bvigo[_\s\-]?web\b|\bvigo[_\s\-]?api\b|\bvigo[_\s\-]?front\b|\bvigo[_\s\-]?back\b",
                t,
            )
        ),
        "vigo_api": bool(
            re.search(
                r"\bvigo[_\s\-]?api\b|\bvigo[_\s\-]?back\b|\bpcm[\s_\-]?api\b|\bbackend[\s]+vigo\b",
                t,
            )
        ),
        "pipelines": bool(re.search(r"\bpipelines?\b|\bcommon[_\s\-]?pipelines\b", t)),
    }


def inferir_proyecto_desde_texto(texto: str) -> tuple[str | None, str]:
    """
    Retorna (clave_o_None, motivo).
    None → hay que preguntar al usuario.
    """
    m = detectar_menciones(texto)

    if m["pipelines"] and not m["vigo"]:
        return "pipelines", "mencionado explícitamente (pipelines)"

    if m["vigo_api"]:
        return "vigo_api", "mencionado explícitamente (API VIGO)"

    if m["vigo"]:
        return "vigo_web", "mencionado explícitamente (VIGO)"

    if m["pipelines"] and m["vigo"]:
        return None, "conflicto: se mencionó VIGO y pipelines"

    return None, "no se detectó un proyecto explícito en el audio"


def _listar_opciones() -> None:
    print("\nProyectos disponibles:")
    for i, clave in enumerate(CLAVES_SELECCIONABLES, start=1):
        if clave == "General":
            ruta = "(nombre libre / docs locales; o escribe otro nombre)"
        else:
            ruta = str(RUTAS_PROYECTOS.get(clave, ""))
        print(f"  {i}. {clave}  {ruta}")


def pedir_proyecto_consola(
    motivo: str,
    sugerido_agente: str | None = None,
    sugerido_audio: str | None = None,
) -> str:
    """Pide al usuario el proyecto por consola. Retorna clave canónica o nombre libre."""
    print("\n⚠️ No quedó claro el proyecto de trabajo.")
    print(f"   Motivo: {motivo}")
    if sugerido_audio:
        print(f"   Señal en audio: {sugerido_audio}")
    if sugerido_agente:
        print(f"   Sugerencia del agente: {sugerido_agente}")
        print("   (Enter = aceptar sugerencia | o escribe otro nombre/número)")

    _listar_opciones()

    while True:
        try:
            entrada = input(
                "Ingresa el proyecto (número, clave, o nombre). Ej: 1 / vigo_web / NovaTrack: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nUsando 'General' por cancelación.")
            return "General"

        if not entrada:
            if sugerido_agente and sugerido_agente.strip():
                print(f"✅ Proyecto elegido: {sugerido_agente.strip()}")
                return sugerido_agente.strip()
            print("  Escribe un valor o el número de la lista.")
            continue

        if entrada.isdigit():
            idx = int(entrada)
            if 1 <= idx <= len(CLAVES_SELECCIONABLES):
                elegido = CLAVES_SELECCIONABLES[idx - 1]
                print(f"✅ Proyecto elegido: {elegido}")
                return elegido
            print("  Número fuera de rango.")
            continue

        clave = normalizar_clave(entrada)
        if clave in RUTAS_PROYECTOS or clave in ALIAS_PROYECTOS or clave in {
            normalizar_clave(c) for c in CLAVES_SELECCIONABLES
        }:
            if clave == "general":
                print("✅ Proyecto elegido: General")
                return "General"
            canonica, _ = resolver_proyecto(clave)
            print(f"✅ Proyecto elegido: {canonica}")
            return canonica

        # Nombre libre (crea carpeta docs/<nombre>/)
        print(f"✅ Proyecto (nombre libre): {entrada}")
        return entrada


def resolver_proyecto_interactivo(transcripcion: str, proyecto_agente: str) -> str:
    """
    Decide el proyecto:
      1) Señales explícitas en el audio (VIGO / pipelines)
      2) Si hay duda / no hay mención → pregunta por consola
    """
    desde_audio, motivo = inferir_proyecto_desde_texto(transcripcion)
    agente_norm = normalizar_clave(proyecto_agente or "")

    if desde_audio:
        if agente_norm and agente_norm not in (
            normalizar_clave(desde_audio),
            "general",
            CLAVE_ORQUESTADOR,
            "automatizar_flujo_trabajo",
        ):
            agente_clave, _ = resolver_proyecto(proyecto_agente)
            audio_clave, _ = resolver_proyecto(desde_audio)
            if agente_clave != audio_clave and agente_clave != CLAVE_ORQUESTADOR:
                print(
                    f"ℹ️ Audio indica '{desde_audio}' pero el agente sugirió '{proyecto_agente}'. "
                    f"Se usa el audio."
                )
        print(f"✅ Proyecto según audio: {desde_audio} ({motivo})")
        return desde_audio

    return pedir_proyecto_consola(
        motivo=motivo,
        sugerido_agente=proyecto_agente or None,
        sugerido_audio=None,
    )
