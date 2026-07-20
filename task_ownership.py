# task_ownership.py
"""Normalización y confirmación de responsables por tarea."""
from __future__ import annotations

from config import CONFIRMAR_RESPONSABLES, PARTICIPANTES_CONOCIDOS, USUARIO_LOCAL


def _es_sin_responsable(valor: str | None) -> bool:
    if valor is None:
        return True
    v = valor.strip().lower()
    return v in ("", "null", "none", "n/a", "na", "desconocido", "sin definir", "pendiente", "-")


def normalizar_tareas(tareas_raw) -> list[dict]:
    """
    Unifica tareas a: {descripcion, responsable, evidencia}.
    Acepta strings legacy o dicts del agente.
    """
    if tareas_raw is None:
        return []
    if isinstance(tareas_raw, str):
        tareas_raw = [tareas_raw]
    if not isinstance(tareas_raw, list):
        return []

    out: list[dict] = []
    for item in tareas_raw:
        if isinstance(item, str):
            desc = item.strip()
            if not desc:
                continue
            out.append({"descripcion": desc, "responsable": None, "evidencia": ""})
            continue
        if isinstance(item, dict):
            desc = str(
                item.get("descripcion")
                or item.get("tarea")
                or item.get("titulo")
                or item.get("text")
                or ""
            ).strip()
            if not desc:
                continue
            resp = item.get("responsable")
            if resp is not None:
                resp = str(resp).strip() or None
            if _es_sin_responsable(resp):
                resp = None
            # Mapear "yo" / usuario local
            if resp and resp.lower() in ("yo", "mi", "me", "mío", "mio", USUARIO_LOCAL.lower()):
                resp = USUARIO_LOCAL
            evidencia = str(item.get("evidencia") or item.get("cita") or "").strip()
            out.append(
                {
                    "descripcion": desc,
                    "responsable": resp,
                    "evidencia": evidencia,
                }
            )
    return out


def confirmar_responsables_consola(tareas: list[dict]) -> list[dict]:
    """
    Si falta responsable, pregunta por consola.
    Enter = USUARIO_LOCAL (tú). 's' / 'skip' = dejar sin asignar.
    """
    if not CONFIRMAR_RESPONSABLES or not tareas:
        return tareas

    pendientes = [t for t in tareas if _es_sin_responsable(t.get("responsable"))]
    if not pendientes:
        print("✅ Todas las tareas tienen responsable asignado.")
        return tareas

    print("\n👤 Asignación de responsables")
    print(f"   Tú eres: {USUARIO_LOCAL}")
    if PARTICIPANTES_CONOCIDOS:
        print(f"   Participantes conocidos: {', '.join(PARTICIPANTES_CONOCIDOS)}")
    print("   Enter = tú | escribe un nombre | 's' = sin asignar\n")

    resultado: list[dict] = []
    for i, tarea in enumerate(tareas, start=1):
        t = dict(tarea)
        if not _es_sin_responsable(t.get("responsable")):
            print(f"  {i}. [{t['responsable']}] {t['descripcion']}")
            resultado.append(t)
            continue

        print(f"  {i}. (sin responsable) {t['descripcion']}")
        if t.get("evidencia"):
            print(f"      pista: {t['evidencia'][:120]}")
        try:
            entrada = input(f"      Responsable [{USUARIO_LOCAL}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n      → {USUARIO_LOCAL}")
            t["responsable"] = USUARIO_LOCAL
            resultado.append(t)
            continue

        if not entrada:
            t["responsable"] = USUARIO_LOCAL
        elif entrada.lower() in ("s", "skip", "ninguno", "na", "n/a"):
            t["responsable"] = None
        else:
            # Match aproximado con participantes conocidos
            match = next(
                (
                    p
                    for p in PARTICIPANTES_CONOCIDOS
                    if p.lower() == entrada.lower() or entrada.lower() in p.lower()
                ),
                None,
            )
            t["responsable"] = match or entrada
        print(f"      → {t['responsable'] or 'sin asignar'}")
        resultado.append(t)

    return resultado


def resumen_tareas_markdown(tareas: list[dict]) -> str:
    """Bloque Markdown con responsables (para enriquecer el prompt si hace falta)."""
    if not tareas:
        return "_Sin tareas._\n"
    lineas = ["## Responsables por tarea\n"]
    for i, t in enumerate(tareas, start=1):
        quien = t.get("responsable") or "sin asignar"
        lineas.append(f"{i}. **{quien}** — {t.get('descripcion', '')}")
    return "\n".join(lineas) + "\n"
