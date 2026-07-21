# glossary.py
"""
Biblioteca de términos técnicos con active learning.

Flujo:
  1) Tras cada reunión se proponen candidatos (heurística + LLM opcional)
  2) Confirmas en consola (Enter=guardar, n=saltar, o 'mal → bien')
  3) Los términos se usan en el initial_prompt de Whisper y en correcciones post-texto

Almacenamiento local (no se sube a git): .glossary/terms.json
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    BASE_DIR,
    CLAVE_ORQUESTADOR,
    CORRECCIONES_TRANSCRIPCION,
    GLOSARIO_CONFIRMAR,
    GLOSARIO_MAX_PROMPT_TERMS,
    OLLAMA_LLM,
    RUTAS_PROYECTOS,
    USAR_GLOSARIO,
    WHISPER_INITIAL_PROMPT,
)

GLOSSARY_DIR = BASE_DIR / ".glossary"
TERMS_FILE = GLOSSARY_DIR / "terms.json"

# Semillas iniciales (misma idea que CORRECCIONES_TRANSCRIPCION, en formato glosario)
_SEED_TERMS: list[dict[str, Any]] = [
    {"canonical": "espera agotado", "aliases": ["esperagotado"], "count": 1, "source": "seed"},
    {"canonical": "requerimiento", "aliases": ["regrimento"], "count": 1, "source": "seed"},
    {"canonical": "feature/", "aliases": ["feature, barra,", "feature barra,", "FUTURE,", "Future,"], "count": 1, "source": "seed"},
    {"canonical": "rama feature", "aliases": ["RAMasFuture"], "count": 1, "source": "seed"},
]


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _escape_regex(s: str) -> str:
    return re.escape(s)


def cargar_glosario() -> dict[str, Any]:
    """Carga .glossary/terms.json; si no existe, inicializa con semillas."""
    GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    if not TERMS_FILE.exists():
        data = {"terms": [dict(t) for t in _SEED_TERMS], "updated_at": _ahora_iso()}
        guardar_glosario(data)
        return data
    try:
        raw = json.loads(TERMS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    terms = raw.get("terms") if isinstance(raw, dict) else None
    if not isinstance(terms, list):
        terms = [dict(t) for t in _SEED_TERMS]
    return {"terms": terms, "updated_at": raw.get("updated_at") if isinstance(raw, dict) else _ahora_iso()}


def guardar_glosario(data: dict[str, Any]) -> None:
    GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "terms": data.get("terms") or [],
        "updated_at": _ahora_iso(),
    }
    TERMS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def _indice_por_canonical(terms: list[dict]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, t in enumerate(terms):
        key = _norm_key(str(t.get("canonical") or ""))
        if key:
            idx[key] = i
    return idx


def upsert_termino(
    canonical: str,
    aliases: list[str] | None = None,
    source: str = "manual",
    bump: int = 1,
) -> None:
    """Crea o actualiza un término; fusiona aliases y sube count."""
    can = (canonical or "").strip()
    if not can:
        return
    data = cargar_glosario()
    terms: list[dict] = list(data.get("terms") or [])
    idx = _indice_por_canonical(terms)
    key = _norm_key(can)
    alias_list = [a.strip() for a in (aliases or []) if a and a.strip() and _norm_key(a) != key]

    if key in idx:
        t = terms[idx[key]]
        existentes = {_norm_key(a): a for a in (t.get("aliases") or []) if a}
        for a in alias_list:
            existentes[_norm_key(a)] = a
        t["aliases"] = list(existentes.values())
        t["count"] = int(t.get("count") or 0) + bump
        if source and not t.get("source"):
            t["source"] = source
    else:
        terms.append(
            {
                "canonical": can,
                "aliases": alias_list,
                "count": max(1, bump),
                "source": source,
            }
        )
    data["terms"] = terms
    guardar_glosario(data)


def _terminos_ordenados(terms: list[dict]) -> list[dict]:
    return sorted(
        terms,
        key=lambda t: (-int(t.get("count") or 0), str(t.get("canonical") or "").lower()),
    )


def prompt_whisper_con_glosario(base: str | None = None) -> str:
    """
    Une el prompt base con hasta N términos canónicos más usados.
    Si USAR_GLOSARIO=false, solo el base.
    """
    base_txt = (base if base is not None else WHISPER_INITIAL_PROMPT) or ""
    base_txt = base_txt.strip()
    if not USAR_GLOSARIO:
        return base_txt

    data = cargar_glosario()
    terms = _terminos_ordenados(list(data.get("terms") or []))
    max_n = max(1, int(GLOSARIO_MAX_PROMPT_TERMS))
    canonicos: list[str] = []
    vistos: set[str] = set()
    for t in terms:
        can = str(t.get("canonical") or "").strip()
        if not can:
            continue
        k = _norm_key(can)
        if k in vistos:
            continue
        # Evitar meter regex/patrones raros demasiado largos en el prompt
        if len(can) > 48 or "," in can:
            continue
        vistos.add(k)
        canonicos.append(can)
        if len(canonicos) >= max_n:
            break

    if not canonicos:
        return base_txt

    vocab = ", ".join(canonicos)
    extra = f" Vocabulario del dominio: {vocab}."
    # Límite práctico del initial_prompt de Whisper (~224 tokens ≈ ~900 chars)
    combinado = f"{base_txt}{extra}".strip()
    if len(combinado) > 900:
        # Recortar términos hasta caber
        while canonicos and len(f"{base_txt} Vocabulario del dominio: {', '.join(canonicos)}.") > 900:
            canonicos.pop()
        if canonicos:
            combinado = f"{base_txt} Vocabulario del dominio: {', '.join(canonicos)}.".strip()
        else:
            combinado = base_txt
    return combinado


def aplicar_correcciones(texto: str) -> str:
    """Reemplaza aliases del glosario por su forma canónica (aliases largos primero)."""
    out = (texto or "").strip()
    if not out or not USAR_GLOSARIO:
        return out

    data = cargar_glosario()
    pares: list[tuple[str, str]] = []
    for t in data.get("terms") or []:
        can = str(t.get("canonical") or "").strip()
        if not can:
            continue
        for alias in t.get("aliases") or []:
            a = str(alias).strip()
            if not a or _norm_key(a) == _norm_key(can):
                continue
            pares.append((a, can))

    pares.sort(key=lambda p: len(p[0]), reverse=True)
    for alias, can in pares:
        # Si el alias parece regex (empieza con \b), úsalo tal cual; si no, escapa
        if alias.startswith(r"\b") or "\\" in alias:
            try:
                out = re.sub(alias, can, out, flags=re.IGNORECASE)
            except re.error:
                out = re.sub(_escape_regex(alias), can, out, flags=re.IGNORECASE)
        else:
            # Word-ish boundary para tokens alfanuméricos; substring para frases con espacios
            if re.fullmatch(r"[\wÁÉÍÓÚáéíóúñÑ/-]+", alias):
                pat = rf"\b{_escape_regex(alias)}\b"
            else:
                pat = _escape_regex(alias)
            out = re.sub(pat, can, out, flags=re.IGNORECASE)
    return out.strip()


def _parse_flecha(entrada: str) -> tuple[str, str] | None:
    """Parsea 'mal → bien' o 'mal -> bien'."""
    raw = (entrada or "").strip()
    if not raw:
        return None
    for sep in ("→", "->", "=>"):
        if sep in raw:
            izq, der = raw.split(sep, 1)
            izq, der = izq.strip(), der.strip()
            if izq and der:
                return izq, der
    return None


def _candidatos_proyectos(texto: str) -> list[dict[str, str]]:
    """Sugiere claves PROYECTO_* mencionadas en el audio como términos."""
    out: list[dict[str, str]] = []
    tl = texto or ""
    for clave in RUTAS_PROYECTOS:
        if clave == CLAVE_ORQUESTADOR:
            continue
        # Forma legible: mi_front → Mi Front / mi front
        variantes = {
            clave,
            clave.replace("_", " "),
            clave.replace("_", "-"),
        }
        # Capitalizado tipo producto
        partes = clave.split("_")
        if partes:
            variantes.add("".join(p.capitalize() for p in partes))
            variantes.add(" ".join(p.capitalize() for p in partes))
        for v in variantes:
            if len(v) < 3:
                continue
            if re.search(rf"\b{_escape_regex(v)}\b", tl, flags=re.IGNORECASE):
                can = "".join(p.capitalize() for p in partes) if len(partes) > 1 else clave
                out.append(
                    {
                        "kind": "term",
                        "canonical": can,
                        "alias": "",
                        "reason": "proyecto mapeado en .env",
                        "source": "project",
                    }
                )
                break
    return out


def _candidatos_heuristicos(texto: str) -> list[dict[str, str]]:
    """CamelCase, acrónimos y patrones típicos de mal oído."""
    out: list[dict[str, str]] = []
    tl = texto or ""

    # Productos / nombres CamelCase (NovaTrack, MyApp)
    for m in re.finditer(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)\b", tl):
        out.append(
            {
                "kind": "term",
                "canonical": m.group(1),
                "alias": "",
                "reason": "nombre de producto / CamelCase",
                "source": "meeting",
            }
        )

    # Acrónimos técnicos cortos en mayúsculas (API, CI, PR si contexto)
    for m in re.finditer(r"\b([A-Z]{2,6})\b", tl):
        acr = m.group(1)
        if acr in ("OK", "ENTER", "EOF", "JSON", "HTTP", "HTTPS", "URL", "UUID"):
            continue
        if acr in ("API", "CLI", "CRM", "ETL", "CI", "CD", "PR", "UI", "UX", "DB", "SQL"):
            out.append(
                {
                    "kind": "term",
                    "canonical": acr,
                    "alias": "",
                    "reason": "acrónimo técnico",
                    "source": "meeting",
                }
            )

    # Correcciones semilla que aparecen en el texto (mal oído detectado)
    for patron, reemplazo in CORRECCIONES_TRANSCRIPCION:
        try:
            if re.search(patron, tl, flags=re.IGNORECASE):
                # Extraer un alias legible del patrón si es \bpalabra\b
                alias_m = re.search(r"\\b([^\\]+)\\b", patron)
                alias = alias_m.group(1) if alias_m else patron
                alias = alias.replace(r"\s*", " ").replace(r"\s+", " ")
                out.append(
                    {
                        "kind": "correction",
                        "canonical": reemplazo,
                        "alias": alias if not alias.startswith("\\") else "",
                        "reason": "corrección conocida en la transcripción",
                        "source": "meeting",
                    }
                )
        except re.error:
            continue

    # FUTURE / future barra → feature
    if re.search(r"\bfuture\b", tl, flags=re.IGNORECASE):
        out.append(
            {
                "kind": "correction",
                "canonical": "feature",
                "alias": "FUTURE",
                "reason": "mal oído típico de 'feature'",
                "source": "meeting",
            }
        )

    return out


def _candidatos_llm(texto: str) -> list[dict[str, str]]:
    """Pide a Ollama un JSON breve de términos; si falla, lista vacía."""
    preview = (texto or "").strip()
    if len(preview) < 40:
        return []
    preview = preview[:3500]

    model = (OLLAMA_LLM or "").replace("ollama/", "").strip() or "qwen2.5-coder:7b"
    prompt = (
        "Extrae vocabulario técnico de esta transcripción de reunión (español).\n"
        "Devuelve ÚNICAMENTE un JSON array (máx 8 ítems). Cada ítem:\n"
        '  {"canonical": "forma correcta", "alias": "mal oído o vacío", '
        '"reason": "breve"}\n'
        "Incluye nombres de producto, términos de software y pares mal→bien si los hay.\n"
        "No inventes términos que no aparezcan. Sin markdown.\n\n"
        f"Transcripción:\n'''\n{preview}\n'''"
    )
    body = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "format": "json"},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    raw = (payload.get("response") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", raw)
        if not m:
            return []
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        parsed = parsed.get("terms") or parsed.get("items") or []
    if not isinstance(parsed, list):
        return []

    out: list[dict[str, str]] = []
    for item in parsed[:8]:
        if not isinstance(item, dict):
            continue
        can = str(item.get("canonical") or "").strip()
        if not can or len(can) > 60:
            continue
        alias = str(item.get("alias") or "").strip()
        reason = str(item.get("reason") or "sugerido por LLM").strip()
        out.append(
            {
                "kind": "correction" if alias else "term",
                "canonical": can,
                "alias": alias,
                "reason": reason,
                "source": "meeting",
            }
        )
    return out


def _dedupe_candidatos(cands: list[dict[str, str]], existentes: dict[str, dict]) -> list[dict[str, str]]:
    vistos: set[str] = set()
    out: list[dict[str, str]] = []
    for c in cands:
        can = str(c.get("canonical") or "").strip()
        alias = str(c.get("alias") or "").strip()
        if not can:
            continue
        key = f"{_norm_key(can)}|{_norm_key(alias)}"
        if key in vistos:
            continue
        # Ya está en glosario con mismo canonical (y alias vacío o ya listado)
        ex = existentes.get(_norm_key(can))
        if ex:
            aliases_ex = {_norm_key(a) for a in (ex.get("aliases") or [])}
            if not alias or _norm_key(alias) in aliases_ex:
                # Solo bump de uso; no proponer de nuevo
                continue
        vistos.add(key)
        out.append(c)
    return out


def _mostrar_candidato(i: int, c: dict[str, str]) -> str:
    can = c.get("canonical") or ""
    alias = c.get("alias") or ""
    reason = c.get("reason") or ""
    if alias:
        return f'  {i}. {alias} → {can}  ({reason})'
    return f'  {i}. "{can}"  ({reason})'


def proponer_y_aprender(
    transcripcion: str,
    meta: dict | None = None,
) -> int:
    """
    Tras la reunión: propone términos y confirma en consola.
    Retorna cuántos términos nuevos/actualizados se guardaron.
    """
    if not USAR_GLOSARIO:
        return 0

    texto = (transcripcion or "").strip()
    if not texto:
        return 0

    data = cargar_glosario()
    existentes = {_norm_key(str(t.get("canonical") or "")): t for t in (data.get("terms") or [])}

    # Subir count de términos ya conocidos que aparecen en el texto
    for key, t in existentes.items():
        can = str(t.get("canonical") or "")
        if can and re.search(rf"\b{_escape_regex(can)}\b", texto, flags=re.IGNORECASE):
            upsert_termino(can, bump=1, source=str(t.get("source") or "meeting"))

    cands: list[dict[str, str]] = []
    cands.extend(_candidatos_proyectos(texto))
    cands.extend(_candidatos_heuristicos(texto))
    cands.extend(_candidatos_llm(texto))

    # Meta: proyecto de la sesión como término
    if meta and meta.get("proyecto"):
        proy = str(meta["proyecto"]).strip()
        if proy and proy.lower() not in ("general", CLAVE_ORQUESTADOR):
            cands.insert(
                0,
                {
                    "kind": "term",
                    "canonical": proy,
                    "alias": "",
                    "reason": "proyecto de la sesión",
                    "source": "project",
                },
            )

    cands = _dedupe_candidatos(cands, existentes)
    if not cands:
        print("📚 Glosario: sin términos nuevos que proponer.")
        return 0

    print(f"\n📚 Glosario — {len(cands)} término(s) candidato(s):")
    print("   Enter=guardar · n=saltar · o escribe 'mal → bien' para corregir")

    guardados = 0
    for i, c in enumerate(cands, start=1):
        print(_mostrar_candidato(i, c))
        can = str(c.get("canonical") or "").strip()
        alias = str(c.get("alias") or "").strip()
        source = str(c.get("source") or "meeting")

        if not GLOSARIO_CONFIRMAR:
            upsert_termino(can, aliases=[alias] if alias else [], source=source)
            guardados += 1
            print(f"   → guardado (auto): {can}")
            continue

        try:
            entrada = input("   ¿Guardar? [Enter/n/mal→bien]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n   (cancelado; se detiene el aprendizaje de glosario)")
            break

        if entrada.lower() in ("n", "no", "skip", "salir"):
            print("   → saltado")
            continue

        parsed = _parse_flecha(entrada)
        if parsed:
            mal, bien = parsed
            upsert_termino(bien, aliases=[mal], source="manual")
            guardados += 1
            print(f"   → guardado: {mal} → {bien}")
            continue

        if entrada and entrada.lower() not in ("y", "yes", "si", "sí", "ok"):
            # Entrada = nuevo canónico (sin flecha)
            upsert_termino(entrada, aliases=[alias] if alias else [], source="manual")
            guardados += 1
            print(f"   → guardado: {entrada}")
            continue

        upsert_termino(can, aliases=[alias] if alias else [], source=source)
        guardados += 1
        if alias:
            print(f"   → guardado: {alias} → {can}")
        else:
            print(f'   → guardado: "{can}"')

    if guardados:
        print(f"📚 Glosario actualizado (+{guardados}). Archivo: {TERMS_FILE}\n")
    else:
        print("📚 Glosario: no se añadió nada nuevo.\n")
    return guardados
