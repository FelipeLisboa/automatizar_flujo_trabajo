# task_ownership.py
"""Normalización y confirmación de responsables por tarea."""
from __future__ import annotations

import re

from config import CONFIRMAR_RESPONSABLES, PARTICIPANTES_CONOCIDOS, USUARIO_LOCAL

_CLAIM_LOCAL = re.compile(
    r"\b("
    r"yo me encargo|me encargo|yo (lo )?implemento|yo (lo )?hago|"
    r"lo tengo|ok[,.]?\s*lo tengo|lo dejo para|yo lo dejo|"
    r"lo resuelvo|yo lo veo|cuenta conmigo"
    r")\b",
    re.IGNORECASE,
)


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


def _lineas_hablante(diarizada: str, hablante: str) -> list[str]:
    if not diarizada:
        return []
    pref = f"[{hablante} "
    out = []
    for linea in diarizada.splitlines():
        l = linea.strip()
        if l.startswith(pref) or l.lower().startswith(f"[{hablante.lower()} "):
            # Quitar etiqueta [Nombre mm:ss]
            texto = re.sub(r"^\[[^\]]+\]\s*", "", l).strip()
            if texto:
                out.append(texto)
    return out


def aplicar_claims_desde_diarizacion(tareas: list[dict], diarizada: str) -> list[dict]:
    """
    Si el usuario local se autoasigna en voz alta ('yo me encargo', etc.),
    rellena tareas sin responsable con USUARIO_LOCAL.
    """
    if not tareas or not diarizada:
        return tareas

    local_txt = " ".join(_lineas_hablante(diarizada, USUARIO_LOCAL))
    if not local_txt or not _CLAIM_LOCAL.search(local_txt):
        return tareas

    out = []
    for t in tareas:
        nt = dict(t)
        if _es_sin_responsable(nt.get("responsable")):
            nt["responsable"] = USUARIO_LOCAL
            if not nt.get("evidencia"):
                nt["evidencia"] = f"{USUARIO_LOCAL} se autoasignó en la reunión"
            elif "remoto" in nt["evidencia"].lower() and "autoasign" not in nt["evidencia"].lower():
                nt["evidencia"] = f"{USUARIO_LOCAL} se autoasignó en la reunión"
        out.append(nt)
    return out


def confirmar_responsables_consola(tareas: list[dict]) -> list[dict]:
    """
    Si falta responsable, pregunta por consola.
    Si hay varias pendientes, ofrece asignar todas a ti de una vez.
    Enter = USUARIO_LOCAL (tú). 's' / 'skip' = dejar sin asignar.
    """
    if not CONFIRMAR_RESPONSABLES or not tareas:
        return tareas

    pendientes_idx = [
        i for i, t in enumerate(tareas) if _es_sin_responsable(t.get("responsable"))
    ]
    if not pendientes_idx:
        print("✅ Todas las tareas tienen responsable asignado.")
        return tareas

    print("\n👤 Asignación de responsables")
    print(f"   Tú eres: {USUARIO_LOCAL}")
    if PARTICIPANTES_CONOCIDOS:
        print(f"   Participantes conocidos: {', '.join(PARTICIPANTES_CONOCIDOS)}")

    # Atajo: varias sin dueño → una sola pregunta
    if len(pendientes_idx) > 1:
        print(f"   Hay {len(pendientes_idx)} tareas sin responsable.")
        try:
            atajo = input(
                f"   ¿Asignarlas todas a {USUARIO_LOCAL}? [Y/n/s=una a una]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            atajo = "y"
            print()

        if atajo in ("", "y", "yes", "sì", "si"):
            out = []
            for t in tareas:
                nt = dict(t)
                if _es_sin_responsable(nt.get("responsable")):
                    nt["responsable"] = USUARIO_LOCAL
                out.append(nt)
            print(f"   → Las {len(pendientes_idx)} tareas quedan a cargo de {USUARIO_LOCAL}")
            return out
        if atajo not in ("s", "skip", "n", "no"):
            # nombre único para todas
            match = next(
                (
                    p
                    for p in PARTICIPANTES_CONOCIDOS
                    if p.lower() == atajo or atajo in p.lower()
                ),
                None,
            )
            quien = match or atajo
            out = []
            for t in tareas:
                nt = dict(t)
                if _es_sin_responsable(nt.get("responsable")):
                    nt["responsable"] = quien
                out.append(nt)
            print(f"   → Las {len(pendientes_idx)} tareas quedan a cargo de {quien}")
            return out
        # s / n → una a una
        print("   Enter = tú | escribe un nombre | 's' = sin asignar\n")
    else:
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
