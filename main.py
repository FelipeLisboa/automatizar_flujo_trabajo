# main.py
"""
Punto de entrada del asistente de reuniones (orquestador).
Uso: python main.py
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from config import AUTO_GIT_COMMIT, CLAVE_ORQUESTADOR, DOCS_DIR, HOTKEY, RUTAS_PROYECTOS, WHISPER_MODEL
from orquestador.audio_processor import (
    detener_grabacion_manual,
    esta_grabando,
    iniciar_grabacion_manual,
)
from orquestador.diarization import transcribir_desde_captura
from orquestador.docs_manager import guardar_fallo, guardar_sesion
from orquestador.git_automation import aplicar_cambios_locales
from orquestador.hotkeys import detener_hotkey, iniciar_hotkey
from orquestador.project_input import resolver_proyecto_interactivo
from orquestador.project_manager import ejecutar_flujo_agentes
from orquestador.speaker_registry import identificar_remotos_interactivo
from orquestador.task_ownership import (
    aplicar_claims_desde_diarizacion,
    confirmar_responsables_consola,
    resumen_tareas_markdown,
)

_estado_lock = threading.Lock()
_grabando = False
_procesando = False
_salir = False
_pending_captura: dict | None = None


def _eliminar_temporales(captura: dict | None) -> None:
    if not captura:
        return
    for key in ("mix", "mic", "sys"):
        ruta = captura.get(key)
        if ruta and os.path.exists(ruta):
            try:
                os.remove(ruta)
            except OSError:
                pass
    print("🗑️ Audio temporal eliminado.\n")


def procesar_flujo_completo(captura: dict) -> None:
    """Diariza → nombrar remotos → agentes → docs → Git opcional."""
    conservado = False
    archivo_mix = captura.get("mix") or ""
    try:
        print(f"🎙️ Transcribiendo con diarización (Whisper '{WHISPER_MODEL}')...")
        resultado_tx = transcribir_desde_captura(captura)
        texto_diarizado = (resultado_tx.get("diarizada") or "").strip()
        texto_plano = (resultado_tx.get("plana") or "").strip()
        texto_reunion = texto_diarizado or texto_plano

        if not texto_reunion or texto_reunion.startswith("Error"):
            motivo = texto_reunion or "Transcripción vacía"
            print(f"⚠️ Transcripción inválida: {motivo}")
            guardar_fallo(motivo=motivo, archivo_audio=archivo_mix)
            conservado = True
            return

        if len(texto_reunion) < 20:
            print("⚠️ Transcripción demasiado corta; se conserva el audio.")
            guardar_fallo(
                motivo="Transcripción demasiado corta",
                archivo_audio=archivo_mix,
                transcripcion=texto_reunion,
            )
            conservado = True
            return

        preview = texto_reunion.replace("\n", " | ")[:220]
        print(f"📝 Diarizada ({resultado_tx.get('modo')}): {preview}...")

        resultado_tx = identificar_remotos_interactivo(
            resultado_tx,
            audio_sys=resultado_tx.get("audio_sys") or captura.get("audio_sys"),
        )
        texto_diarizado = (resultado_tx.get("diarizada") or "").strip()
        texto_plano = (resultado_tx.get("plana") or "").strip()
        texto_reunion = texto_diarizado or texto_plano

        print("🤖 Analizando con agentes…")
        resultado = ejecutar_flujo_agentes(texto_reunion)

        if not resultado or not isinstance(resultado, dict):
            print("❌ Los agentes no retornaron un diccionario válido.")
            guardar_fallo(
                motivo="Agentes sin resultado válido",
                archivo_audio=archivo_mix,
                transcripcion=texto_reunion,
            )
            conservado = True
            return

        nombre_proyecto = str(resultado.get("proyecto") or "General").strip()
        nombre_rama = str(resultado.get("rama") or "feature/nuevo-cambio").strip()
        contenido_markdown = str(resultado.get("markdown") or "")
        tareas = resultado.get("tareas") or []
        archivos_menc = resultado.get("archivos_mencionados") or []

        nombre_proyecto = resolver_proyecto_interactivo(texto_reunion, nombre_proyecto)
        tareas = aplicar_claims_desde_diarizacion(
            tareas if isinstance(tareas, list) else [],
            texto_diarizado,
        )
        tareas = confirmar_responsables_consola(tareas)
        bloque_resp = resumen_tareas_markdown(tareas)
        if bloque_resp.strip() and "## Responsables por tarea" not in contenido_markdown:
            contenido_markdown = contenido_markdown.rstrip() + "\n\n" + bloque_resp

        carpeta = guardar_sesion(
            nombre_proyecto=nombre_proyecto,
            nombre_rama=nombre_rama,
            transcripcion=texto_plano or texto_reunion,
            markdown=contenido_markdown,
            tareas=tareas,
            archivo_audio=archivo_mix,
            meta_extra={
                "archivos_mencionados": archivos_menc,
                "transcripcion_diarizada": texto_diarizado,
                "diarizacion_modo": resultado_tx.get("modo"),
                "segmentos": resultado_tx.get("segmentos") or [],
                "mapa_remotos": resultado_tx.get("mapa_remotos") or {},
            },
        )
        conservado = True

        if AUTO_GIT_COMMIT:
            print(f"🚀 Preparando Git (propuesta: {nombre_rama})...")
            aplicar_cambios_locales(
                nombre_proyecto=nombre_proyecto,
                nombre_rama=nombre_rama,
                contenido_markdown=contenido_markdown,
                carpeta_sesion=carpeta,
            )
        else:
            print("ℹ️ AUTO_GIT_COMMIT=False — solo se guardó en docs/ local.")

        print("✨ Flujo completado.")
        print(f"👉 Prompt: {carpeta / 'prompt_cursor.md'}\n")

    except Exception as e:
        print(f"❌ Error en el flujo: {e}")
        if not conservado:
            guardar_fallo(motivo=str(e), archivo_audio=archivo_mix)
            conservado = True
    finally:
        if conservado:
            _eliminar_temporales(captura)
        else:
            _eliminar_temporales(captura)


def _iniciar_grabacion() -> None:
    global _grabando
    iniciar_grabacion_manual()
    _grabando = True


def _encolar_proceso_tras_detener() -> None:
    global _pending_captura, _grabando
    captura = detener_grabacion_manual()
    _grabando = False
    if not captura or not captura.get("mix"):
        with _estado_lock:
            global _procesando
            _procesando = False
        print("⚠️ No hay audio para procesar.")
        return
    print("⏳ Presiona Enter para continuar el análisis…")
    with _estado_lock:
        _pending_captura = captura


def alternar_grabacion() -> None:
    global _grabando, _procesando
    with _estado_lock:
        if _procesando or _pending_captura:
            print("⚠️ Espera a que termine el procesamiento.")
            return
        if _grabando or esta_grabando():
            _procesando = True
            _grabando = False
            threading.Thread(target=_encolar_proceso_tras_detener, daemon=True).start()
        else:
            _iniciar_grabacion()


def _mostrar_proyectos() -> None:
    print("\nProyectos de producto (aquí sí se pueden crear ramas):")
    for clave, ruta in RUTAS_PROYECTOS.items():
        if clave == CLAVE_ORQUESTADOR:
            continue
        existe = "OK" if Path(ruta).exists() else "??"
        git = " [git]" if (Path(ruta) / ".git").exists() else ""
        print(f"  [{existe}] {clave}: {ruta}{git}")
    print("\nProyecto nuevo / desconocido → escribe el nombre (queda en docs/<nombre>/)")
    print(f"Orquestador (siempre main): {BASE}")
    print(f"Whisper: {WHISPER_MODEL}")
    print(f"Salida local: {DOCS_DIR}/<proyecto>/<fecha_hora>/")
    print()


def _consumir_pendiente() -> bool:
    global _pending_captura, _procesando

    with _estado_lock:
        captura = _pending_captura
        _pending_captura = None

    if not captura:
        return False

    try:
        procesar_flujo_completo(captura)
    finally:
        _procesando = False
    return True


def menu_consola() -> None:
    global _salir, _grabando, _procesando

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("=======================================================")
    print("  ASISTENTE DE REUNIONES (orquestador)")
    print("=======================================================")
    print("Comandos:")
    print("  grabar / parar / toggle  — control de captura")
    print("  proyectos                — ver rutas mapeadas")
    print("  docs                     — abrir carpeta docs/")
    print("  salir                    — cerrar")
    print(f"Hotkey: {HOTKEY.upper()}  (alternar grabar/parar)")
    print(f"Whisper: {WHISPER_MODEL} | Diarización: mic=tú / sistema=remotos")
    print("=======================================================")
    _mostrar_proyectos()

    iniciar_hotkey(alternar_grabacion)

    while not _salir:
        if _consumir_pendiente():
            continue

        try:
            comando = input("Audio-Bot > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo…")
            break

        if _consumir_pendiente():
            continue

        if comando in ("grabar", "start", "rec"):
            with _estado_lock:
                if _procesando or _pending_captura:
                    print("⚠️ Espera a que termine el procesamiento.")
                elif _grabando or esta_grabando():
                    print("⚠️ Ya estás grabando.")
                else:
                    _iniciar_grabacion()

        elif comando in ("parar", "stop", ""):
            with _estado_lock:
                if _procesando or _pending_captura:
                    if comando == "":
                        continue
                    print("⚠️ Ya se está procesando.")
                elif _grabando or esta_grabando():
                    _procesando = True
                    _grabando = False
                    threading.Thread(target=_encolar_proceso_tras_detener, daemon=True).start()
                elif comando == "":
                    continue
                else:
                    print("⚠️ No hay grabación activa.")

        elif comando == "toggle":
            alternar_grabacion()

        elif comando in ("proyectos", "projects"):
            _mostrar_proyectos()

        elif comando == "docs":
            os.startfile(str(DOCS_DIR)) if hasattr(os, "startfile") else print(DOCS_DIR)

        elif comando in ("salir", "exit", "quit"):
            _salir = True
            break

        else:
            print("Comandos: grabar | parar | toggle | proyectos | docs | salir")

    detener_hotkey()
    print("Hasta luego.")


if __name__ == "__main__":
    menu_consola()
