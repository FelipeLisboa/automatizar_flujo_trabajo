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


def detectar_nombre_libre(texto: str) -> str | None:
    """Extrae 'proyecto NovaTrack' / nombres propios mencionados como proyecto."""
    if not texto:
        return None
    m = re.search(
        r"\bproyecto\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúñ0-9]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúñ0-9]+){0,2})",
        texto,
    )
    if not m:
        # También captura minúsculas: "proyecto novatrack"
        m = re.search(
            r"\bproyecto\s+([A-Za-zÁÉÍÓÚáéíóúñ][A-Za-zÁÉÍÓÚáéíóúñ0-9_\-]{2,})",
            texto,
            flags=re.IGNORECASE,
        )
    if not m:
        return None
    nombre = m.group(1).strip().rstrip(".,;:")
    clave = normalizar_clave(nombre)
    if clave in ("general", CLAVE_ORQUESTADOR, "vigo", "pipelines", "el", "la", "un", "este"):
        return None
    if clave in RUTAS_PROYECTOS or clave in ALIAS_PROYECTOS:
        return None
    # Capitalizar estilo marca si viene todo minúsculas
    if nombre.islower():
        nombre = nombre[0].upper() + nombre[1:]
    return nombre


def inferir_proyecto_desde_texto(texto: str) -> tuple[str | None, str]:
    """
    Retorna (clave_o_None, motivo).
    None → hay que preguntar al usuario (salvo auto-aceptar sugerencia del agente).
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

    libre = detectar_nombre_libre(texto)
    if libre:
        return libre, f"nombre libre mencionado en audio ({libre})"

    return None, "no se detectó un proyecto mapeado (VIGO / pipelines) en el audio"


def _limpiar_entrada_proyecto(entrada: str) -> str:
    """
    Evita que se pegue el ejemplo del prompt:
      '1 / vigo_web / NovaTrack' → 'NovaTrack'
      '1 / NovaTrack / NovaTrack' → 'NovaTrack'
    """
    crudo = (entrada or "").strip()
    if not crudo:
        return ""

    # Si parece el ejemplo con barras, tomar el último trozo no numérico
    if "/" in crudo:
        partes = [p.strip() for p in re.split(r"\s*/\s*", crudo) if p.strip()]
        for p in reversed(partes):
            if p.isdigit():
                continue
            if p.lower() in ("ej", "ejemplo", "o", "escribe"):
                continue
            return p
        return partes[-1] if partes else crudo

    return crudo


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
        print("   → Pulsa Enter para aceptar esa sugerencia")

    _listar_opciones()

    while True:
        try:
            entrada = input(
                "Proyecto (Enter=sugerencia | número | clave | nombre): "
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

        entrada = _limpiar_entrada_proyecto(entrada)
        if not entrada:
            print("  Entrada vacía tras limpiar. Intenta de nuevo.")
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

        print(f"✅ Proyecto (nombre libre): {entrada}")
        return entrada


def _agente_mencionado_en_audio(texto: str, proyecto_agente: str) -> bool:
    """True si el nombre libre sugerido por el agente aparece en el audio."""
    nombre = (proyecto_agente or "").strip()
    if not nombre:
        return False
    clave = normalizar_clave(nombre)
    if clave in ("general", CLAVE_ORQUESTADOR, "automatizar_flujo_trabajo"):
        return False
    if clave in RUTAS_PROYECTOS or clave in ALIAS_PROYECTOS:
        return False
    # Nombre libre: buscar en transcripción (tolerante a espacios)
    patron = re.escape(nombre).replace(r"\ ", r"[\s_\-]*")
    return bool(re.search(patron, texto, flags=re.IGNORECASE))


def resolver_proyecto_interactivo(transcripcion: str, proyecto_agente: str) -> str:
    """
    Decide el proyecto:
      1) Señales explícitas en el audio (VIGO / pipelines)
      2) Nombre libre del agente si también aparece en el audio (auto)
      3) Si hay duda → pregunta por consola (Enter = sugerencia)
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

    # Nombre libre en audio (ej. NovaTrack) aunque el agente diga General
    libre = detectar_nombre_libre(transcripcion)
    if libre:
        print(f"✅ Proyecto según audio: {libre} (nombre libre en la reunión)")
        return libre

    # NovaTrack y similares: si el agente acertó y el audio lo dice, no preguntar
    if proyecto_agente and _agente_mencionado_en_audio(transcripcion, proyecto_agente):
        print(
            f"✅ Proyecto según audio + agente: {proyecto_agente.strip()} "
            f"(nombre libre mencionado en la reunión)"
        )
        return proyecto_agente.strip()

    sugerencia = proyecto_agente.strip() if proyecto_agente else None
    if sugerencia and normalizar_clave(sugerencia) in ("general", CLAVE_ORQUESTADOR):
        sugerencia = libre  # puede ser None

    return pedir_proyecto_consola(
        motivo=motivo,
        sugerido_agente=sugerencia or proyecto_agente or None,
        sugerido_audio=libre,
    )
