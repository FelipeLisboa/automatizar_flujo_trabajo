# hotkeys.py
"""Hotkey global para alternar grabación (Ctrl+Shift+R por defecto)."""
from __future__ import annotations

import threading
from typing import Callable

from config import HOTKEY

_listener = None
_lock = threading.Lock()


def iniciar_hotkey(callback: Callable[[], None], combinacion: str | None = None) -> bool:
    """
    Registra un hotkey global. Retorna True si quedó activo.
    En Windows puede requerir ejecutar la consola como administrador.
    """
    global _listener
    combo = (combinacion or HOTKEY).lower().strip()

    try:
        import keyboard  # type: ignore
    except ImportError:
        print(
            "⚠️ Paquete 'keyboard' no instalado. Hotkey desactivado. "
            "Instala con: python -m pip install keyboard"
        )
        return False

    with _lock:
        detener_hotkey()

        def _wrapper():
            try:
                callback()
            except Exception as e:
                print(f"❌ Error en callback del hotkey: {e}")

        try:
            keyboard.add_hotkey(combo, _wrapper, suppress=False)
            _listener = ("keyboard", combo)
            print(f"⌨️  Hotkey activo: {combo.upper()} (alternar grabar/parar)")
            return True
        except Exception as e:
            print(
                f"⚠️ No se pudo registrar el hotkey '{combo}': {e}\n"
                "   Prueba ejecutar la terminal como Administrador, o usa los comandos de consola."
            )
            _listener = None
            return False


def detener_hotkey() -> None:
    global _listener
    if _listener is None:
        return
    tipo, combo = _listener
    try:
        if tipo == "keyboard":
            import keyboard  # type: ignore

            keyboard.remove_hotkey(combo)
    except Exception:
        try:
            import keyboard  # type: ignore

            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
    _listener = None
