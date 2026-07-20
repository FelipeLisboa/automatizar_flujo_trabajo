# main.py
"""
Asistente de reuniones local (orquestador):
  grabar → Whisper → CrewAI → docs/ local → (opcional) rama+commit en OTRO proyecto
Este repositorio permanece siempre en main.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from audio_processor import (
    detener_grabacion_manual,
    esta_grabando,
    iniciar_grabacion_manual,
    transcribir_local,
)
from config import AUTO_GIT_COMMIT, CLAVE_ORQUESTADOR, DOCS_DIR, HOTKEY, RUTAS_PROYECTOS, WHISPER_MODEL
from docs_manager import guardar_fallo, guardar_sesion
from git_automation import aplicar_cambios_locales
from hotkeys import detener_hotkey, iniciar_hotkey
from project_input import resolver_proyecto_interactivo
from project_manager import ejecutar_flujo_agentes

_estado_lock = threading.Lock()
_grabando = False
_procesando = False
_salir = False
_pending_audio: str | None = None


def _eliminar_temporal(archivo_audio: str | None) -> None:
    if archivo_audio and os.path.exists(archivo_audio):
        try:
            os.remove(archivo_audio)
            print(f"🗑️ Audio temporal eliminado: {archivo_audio}\n")
        except OSError as e:
            print(f"⚠️ No se pudo eliminar el audio temporal: {e}\n")


def procesar_flujo_completo(archivo_audio: str) -> None:
    """Transcribe → agentes → docs local → confirmación de rama en repo de producto."""
    conservado = False
    try:
        print(f"🎙️ Transcribiendo (Whisper '{WHISPER_MODEL}')...")
        texto_reunion = transcribir_local(archivo_audio)

        if not texto_reunion or texto_reunion.startswith("Error"):
            motivo = texto_reunion or "Transcripción vacía"
            print(f"⚠️ Transcripción inválida: {motivo}")
            guardar_fallo(motivo=motivo, archivo_audio=archivo_audio)
            conservado = True
            return

        if len(texto_reunion.strip()) < 20:
            print("⚠️ Transcripción demasiado corta; se conserva el audio por si quieres reintentar.")
            guardar_fallo(
                motivo="Transcripción demasiado corta",
                archivo_audio=archivo_audio,
                transcripcion=texto_reunion,
            )
            conservado = True
            return

        print(f"📝 Transcripción ({len(texto_reunion)} chars): {texto_reunion[:200]}...")

        print("🤖 Despertando a los agentes de CrewAI (Ollama)...")
        resultado = ejecutar_flujo_agentes(texto_reunion)

        if not resultado or not isinstance(resultado, dict):
            print("❌ Los agentes no retornaron un diccionario válido.")
            guardar_fallo(
                motivo="Agentes sin resultado válido",
                archivo_audio=archivo_audio,
                transcripcion=texto_reunion,
            )
            conservado = True
            return

        nombre_proyecto = str(resultado.get("proyecto") or "General").strip()
        nombre_rama = str(resultado.get("rama") or "feature/nuevo-cambio").strip()
        contenido_markdown = str(resultado.get("markdown") or "")
        tareas = resultado.get("tareas") or []
        archivos_menc = resultado.get("archivos_mencionados") or []

        # Audio manda; si no hay proyecto claro → pregunta por consola
        nombre_proyecto = resolver_proyecto_interactivo(texto_reunion, nombre_proyecto)

        carpeta = guardar_sesion(
            nombre_proyecto=nombre_proyecto,
            nombre_rama=nombre_rama,
            transcripcion=texto_reunion,
            markdown=contenido_markdown,
            tareas=tareas if isinstance(tareas, list) else [str(tareas)],
            archivo_audio=archivo_audio,
            meta_extra={"archivos_mencionados": archivos_menc},
        )
        conservado = True  # ya hay copia en la sesión

        if AUTO_GIT_COMMIT:
            print(f"🚀 Preparando Git en el proyecto destino (propuesta: {nombre_rama})...")
            aplicar_cambios_locales(
                nombre_proyecto=nombre_proyecto,
                nombre_rama=nombre_rama,
                contenido_markdown=contenido_markdown,
                carpeta_sesion=carpeta,
            )
        else:
            print("ℹ️ AUTO_GIT_COMMIT desactivado — revisa el prompt en docs/.")

        print("✨ Flujo completado para esta sesión.")
        print(f"👉 Prompt listo: {carpeta / 'prompt_cursor.md'}\n")

    except Exception as e:
        print(f"❌ Error crítico en el pipeline: {e}")
        if not conservado:
            try:
                guardar_fallo(motivo=f"Error crítico: {e}", archivo_audio=archivo_audio)
                conservado = True
            except Exception:
                pass
    finally:
        # Solo borra el temporal si ya quedó copia en docs/ (éxito o _fallidos)
        if conservado:
            _eliminar_temporal(archivo_audio)
        elif archivo_audio and os.path.exists(archivo_audio):
            print(f"⚠️ Se conserva el audio temporal para reintento: {archivo_audio}\n")


def _iniciar_grabacion() -> None:
    global _grabando
    iniciar_grabacion_manual()
    _grabando = True


def _encolar_proceso_tras_detener() -> None:
    global _grabando, _procesando, _pending_audio

    archivo = detener_grabacion_manual()
    _grabando = False

    if not archivo:
        print("⚠️ No se generó audio válido.")
        _procesando = False
        return

    _pending_audio = archivo
    print("⏳ Presiona Enter para continuar el análisis…")


def alternar_grabacion() -> None:
    global _grabando, _procesando

    with _estado_lock:
        if _procesando or _pending_audio:
            print("⚠️ Todavía hay una sesión en curso. Espera un momento.")
            return

        if not _grabando and not esta_grabando():
            _iniciar_grabacion()
            return

        if _grabando or esta_grabando():
            _procesando = True
            _grabando = False
            threading.Thread(target=_encolar_proceso_tras_detener, daemon=True).start()
            return


def _mostrar_proyectos() -> None:
    print("\nProyectos de producto (aquí sí se pueden crear ramas):")
    for clave, ruta in RUTAS_PROYECTOS.items():
        if clave == CLAVE_ORQUESTADOR:
            continue
        existe = "OK" if ruta.exists() else "NO"
        git = " [git]" if (ruta / ".git").is_dir() else ""
        print(f"  [{existe}] {clave}: {ruta}{git}")
    print("\nProyecto nuevo / desconocido → escribe el nombre (queda en docs/<nombre>/)")
    print(f"Orquestador (siempre main): {BASE}")
    print(f"Whisper: {WHISPER_MODEL}")
    print(f"Salida local: {DOCS_DIR}/<proyecto>/<fecha_hora>/")
    print()


def _consumir_pendiente() -> bool:
    global _pending_audio, _procesando

    with _estado_lock:
        archivo = _pending_audio
        _pending_audio = None

    if not archivo:
        return False

    try:
        procesar_flujo_completo(archivo)
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
    print(f"Whisper: {WHISPER_MODEL} | Este repo permanece en main.")
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
                if _procesando or _pending_audio:
                    print("⚠️ Espera a que termine el procesamiento.")
                elif _grabando or esta_grabando():
                    print("⚠️ Ya estás grabando.")
                else:
                    _iniciar_grabacion()

        elif comando in ("parar", "stop", ""):
            with _estado_lock:
                if _procesando or _pending_audio:
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
                    print("⚠️ No hay grabación activa. Usa 'grabar' o el hotkey.")

        elif comando in ("toggle", "t"):
            alternar_grabacion()

        elif comando in ("proyectos", "projects", "map"):
            _mostrar_proyectos()

        elif comando == "docs":
            print(f"📂 {DOCS_DIR}")
            try:
                os.startfile(str(DOCS_DIR))
            except OSError:
                pass

        elif comando in ("salir", "exit", "quit"):
            with _estado_lock:
                if _grabando or esta_grabando():
                    detener_grabacion_manual()
                    _grabando = False
            _salir = True
            print("👋 Listo. ¡Buen código, Felipe!")

        else:
            print("❓ Usa: grabar | parar | toggle | proyectos | docs | salir")

    detener_hotkey()


if __name__ == "__main__":
    menu_consola()
