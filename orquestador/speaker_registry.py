# speaker_registry.py
"""
Biblioteca de perfiles de voz + active learning.

Flujo:
  1) pyannote separa Remoto_1, Remoto_2, …
  2) Se compara cada remoto con .voice_profiles/ (embeddings)
  3) Si la similitud es alta → se asigna el nombre SOLO (sin preguntar)
  4) Si no hay match → se muestra qué dijo y pides el nombre (persona nueva)
  5) Al etiquetar (nuevo o confirmado) se actualiza el perfil (media acumulada)

Así la biblioteca crece indefinidamente: gente nueva una vez; después se reconoce sola.
No guarda WAV crudos por defecto (privacidad/espacio): guarda un vector de voz + metadatos.
"""
from __future__ import annotations

import json
import os
import re
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np

from config import (
    BASE_DIR,
    NOMBRAR_REMOTOS,
    PARTICIPANTES_CONOCIDOS,
    USAR_RECONOCIMIENTO_VOZ,
    USUARIO_LOCAL,
    VOICE_AUTO_APPLY,
    VOICE_AUTO_THRESHOLD,
    VOICE_MATCH_THRESHOLD,
)

VOICES_DIR = BASE_DIR / ".voice_profiles"
META_FILE = VOICES_DIR / "registry.json"


def _hf_token() -> str:
    token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
    try:
        from config import HF_TOKEN as CFG_TOKEN  # type: ignore

        token = token or (CFG_TOKEN or "").strip()
    except Exception:
        pass
    return token


def _es_etiqueta_remota(speaker: str) -> bool:
    s = (speaker or "").strip()
    if not s or s == USUARIO_LOCAL:
        return False
    return s == "Remoto" or bool(re.match(r"^Remoto_\d+$", s, re.I))


def _slug_nombre(nombre: str) -> str:
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", (nombre or "").strip())
    limpio = re.sub(r"\s+", "_", limpio)
    return limpio or "desconocido"


def _snippets_por_speaker(segmentos: list[dict], speaker: str, max_frases: int = 3) -> list[str]:
    frags = []
    for s in segmentos:
        if s.get("speaker") != speaker:
            continue
        t = (s.get("text") or "").strip()
        if t:
            frags.append(t)
        if len(frags) >= max_frases:
            break
    return frags


def _reconstruir_textos(segmentos: list[dict]) -> tuple[str, str]:
    lineas = []
    for s in segmentos:
        t0 = float(s.get("start") or 0.0)
        mm, ss = divmod(int(t0), 60)
        lineas.append(f"[{s['speaker']} {mm:02d}:{ss:02d}] {s['text']}")
    diarizada = "\n".join(lineas).strip()
    plana = " ".join(s.get("text") or "" for s in segmentos).strip()
    return diarizada, plana


def _cargar_meta() -> dict:
    if not META_FILE.exists():
        return {"perfiles": {}}
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"perfiles": {}}


def _guardar_meta(meta: dict) -> None:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def listar_perfiles_voz() -> list[str]:
    meta = _cargar_meta()
    return sorted((meta.get("perfiles") or {}).keys())


def _ruta_embedding(nombre: str) -> Path:
    return VOICES_DIR / f"{_slug_nombre(nombre)}.npy"


def _recortar_audio_speaker(
    audio_sys: np.ndarray | None,
    segmentos: list[dict],
    speaker: str,
    rate: int,
    max_secs: float = 12.0,
) -> np.ndarray | None:
    if audio_sys is None or audio_sys.size == 0:
        return None
    trozos = []
    total = 0.0
    for s in segmentos:
        if s.get("speaker") != speaker:
            continue
        i0 = max(0, int(float(s["start"]) * rate))
        i1 = min(len(audio_sys), int(float(s["end"]) * rate))
        if i1 <= i0:
            continue
        trozos.append(audio_sys[i0:i1])
        total += (i1 - i0) / rate
        if total >= max_secs:
            break
    if not trozos:
        return None
    return np.concatenate(trozos).astype(np.float32)


_embedding_inference = None


def _get_embedding_inference():
    global _embedding_inference
    if _embedding_inference is not None:
        return _embedding_inference if _embedding_inference is not False else None
    if not USAR_RECONOCIMIENTO_VOZ:
        return None
    token = _hf_token()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyannote.audio import Inference, Model

            kwargs = {"token": token} if token else {}
            try:
                model = Model.from_pretrained("pyannote/embedding", **kwargs)
            except TypeError:
                model = Model.from_pretrained(
                    "pyannote/embedding",
                    use_auth_token=token or True,
                )
            _embedding_inference = Inference(model, window="whole")
            return _embedding_inference
    except Exception as e:
        print(
            f"ℹ️ Reconocimiento de voz no disponible ({e}). "
            "Sugerencia: pip install omegaconf pyannote.audio "
            "y acepta https://huggingface.co/pyannote/embedding"
        )
        _embedding_inference = False  # type: ignore
        return None


def _embedding_de_audio(audio: np.ndarray | None, rate: int) -> np.ndarray | None:
    inf = _get_embedding_inference()
    if inf is None or inf is False:
        return None
    if audio is None or not isinstance(audio, np.ndarray) or audio.size < rate:
        return None
    try:
        import torch

        wave = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)).unsqueeze(0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            emb = inf({"waveform": wave, "sample_rate": rate})
        if hasattr(emb, "numpy"):
            emb = emb.numpy()
        # Algunos backends devuelven (1, D) o (frames, D): unificar a vector 1D
        emb = np.asarray(emb, dtype=np.float32)
        if emb.ndim > 1:
            emb = np.mean(emb.reshape(-1, emb.shape[-1]), axis=0)
        emb = emb.reshape(-1)
        norm = float(np.linalg.norm(emb))
        if norm < 1e-8:
            return None
        return emb / norm
    except Exception:
        return None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    n = min(a.size, b.size)
    if n == 0:
        return 0.0
    a, b = a[:n], b[:n]
    denom = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    return float(np.dot(a, b) / denom)


def _mejor_match(
    emb: np.ndarray,
    excluir_nombres: set[str] | None = None,
) -> tuple[str | None, float]:
    excluir = {n.lower() for n in (excluir_nombres or set())}
    meta = _cargar_meta()
    best_name, best_sim = None, 0.0
    for nombre in meta.get("perfiles") or {}:
        if nombre.lower() in excluir:
            continue
        path = _ruta_embedding(nombre)
        if not path.exists():
            continue
        try:
            ref = np.load(path)
            sim = _cosine(emb, ref)
            if sim > best_sim:
                best_sim, best_name = sim, nombre
        except Exception:
            continue
    return best_name, best_sim


def reconocer_remoto(
    audio_sys: np.ndarray | None,
    segmentos: list[dict],
    speaker: str,
    rate: int,
    ya_asignados: set[str] | None = None,
) -> tuple[str | None, float, np.ndarray | None]:
    """
    Retorna (nombre_si_supera_umbral_match, similitud, embedding_actual).
    nombre es None si no hay biblioteca o no llega al umbral de sugerencia.
    """
    if not USAR_RECONOCIMIENTO_VOZ:
        return None, 0.0, None
    clip = _recortar_audio_speaker(audio_sys, segmentos, speaker, rate)
    emb = _embedding_de_audio(clip, rate)
    if emb is None:
        return None, 0.0, None
    nombre, sim = _mejor_match(emb, excluir_nombres=ya_asignados)
    if nombre and sim >= VOICE_MATCH_THRESHOLD:
        return nombre, sim, emb
    return None, sim, emb


def _registrar_nombre_en_meta(
    nombre: str,
    *,
    con_voz: bool,
    citas: list[str] | None = None,
    n_muestras: int | None = None,
) -> None:
    """Siempre deja el nombre en registry.json (con o sin embedding)."""
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    meta = _cargar_meta()
    perfiles = meta.setdefault("perfiles", {})
    prev = perfiles.get(nombre) or {}
    perfiles[nombre] = {
        "archivo": _ruta_embedding(nombre).name if con_voz else prev.get("archivo"),
        "tiene_embedding": bool(con_voz or prev.get("tiene_embedding")),
        "n_muestras": int(
            n_muestras
            if n_muestras is not None
            else prev.get("n_muestras") or (1 if con_voz else 0)
        ),
        "actualizado": datetime.now().isoformat(timespec="seconds"),
        "ultimas_citas": (citas or prev.get("ultimas_citas") or [])[:3],
    }
    _guardar_meta(meta)


def enrolar_voz(
    nombre: str,
    audio_sys: np.ndarray | None,
    segmentos: list[dict],
    speaker_label: str,
    rate: int,
    emb_nuevo: np.ndarray | None = None,
    citas: list[str] | None = None,
) -> bool:
    """
    Active learning: registra el nombre siempre; guarda embedding si el modelo responde.
    Retorna True si hay embedding nuevo/actualizado; False si solo quedó el nombre.
    """
    if not nombre or _es_etiqueta_remota(nombre):
        return False

    # Aunque falle la voz, el nombre entra a la biblioteca (sugerencias futuras)
    if not USAR_RECONOCIMIENTO_VOZ:
        _registrar_nombre_en_meta(nombre, con_voz=False, citas=citas)
        print(f"      📝 Nombre guardado (sin voz; USAR_RECONOCIMIENTO_VOZ=false): {nombre}")
        return False

    if emb_nuevo is None:
        clip = _recortar_audio_speaker(audio_sys, segmentos, speaker_label, rate)
        emb_nuevo = _embedding_de_audio(clip, rate)
    if emb_nuevo is None:
        _registrar_nombre_en_meta(nombre, con_voz=False, citas=citas)
        print(
            f"      📝 Nombre guardado sin huella de voz: {nombre}\n"
            f"         Causa habitual: falta dependencia (omegaconf) o modelo embedding.\n"
            f"         Prueba: python -m pip install omegaconf"
        )
        return False

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    path = _ruta_embedding(nombre)
    meta = _cargar_meta()
    perfiles = meta.setdefault("perfiles", {})
    info = perfiles.get(nombre) or {}
    n = int(info.get("n_muestras") or 0)

    if path.exists() and n > 0:
        try:
            prev = np.load(path)
            emb = (prev * n + emb_nuevo) / (n + 1.0)
            emb = emb / (float(np.linalg.norm(emb)) + 1e-8)
        except Exception:
            emb = emb_nuevo
            n = 0
    else:
        emb = emb_nuevo

    n += 1
    np.save(path, np.asarray(emb, dtype=np.float32).reshape(-1))
    _registrar_nombre_en_meta(nombre, con_voz=True, citas=citas, n_muestras=n)
    return True


def _sugerencias_lista() -> list[str]:
    conocidos = [p for p in PARTICIPANTES_CONOCIDOS if p.lower() != USUARIO_LOCAL.lower()]
    perfiles = listar_perfiles_voz()
    return list(dict.fromkeys([*perfiles, *conocidos]))


def _resolver_nombre_entrada(entrada: str, sugerencias: list[str], fallback: str) -> str:
    if not entrada:
        return fallback
    if entrada.lower() in ("s", "skip", "remoto"):
        return fallback if _es_etiqueta_remota(fallback) else fallback
    match = next((p for p in sugerencias if p.lower() == entrada.lower()), None)
    if not match:
        match = next((p for p in sugerencias if entrada.lower() in p.lower()), None)
    return match or entrada


def _guardar_perfil_tras_nombrar(
    nombre: str,
    spk: str,
    audio_sys: np.ndarray | None,
    segmentos: list[dict],
    rate: int,
    emb,
    citas: list[str],
    perfiles: list[str],
) -> list[str]:
    es_nuevo = nombre not in perfiles
    ok_voz = enrolar_voz(
        nombre, audio_sys, segmentos, spk, rate, emb_nuevo=emb, citas=citas
    )
    if ok_voz:
        print(
            f"      💾 {'Nuevo perfil de voz' if es_nuevo else 'Perfil de voz actualizado'}: "
            f"{nombre} → .voice_profiles/"
        )
    if es_nuevo and nombre not in perfiles:
        perfiles.append(nombre)
    return perfiles


def identificar_remotos_interactivo(
    resultado_tx: dict,
    audio_sys: np.ndarray | None = None,
) -> dict:
    """
    Active learning de remotos:

    - Match fuerte (≥ VOICE_AUTO_THRESHOLD) + VOICE_AUTO_APPLY → asigna solo y refuerza perfil
    - Match débil / desconocido → pregunta con citas; al responder enrola (persona nueva o corrección)
    """
    from orquestador.audio_processor import TARGET_RATE

    if not NOMBRAR_REMOTOS:
        return resultado_tx

    segmentos = list(resultado_tx.get("segmentos") or [])
    if not segmentos:
        return resultado_tx

    remotos = []
    for s in segmentos:
        spk = s.get("speaker") or ""
        if _es_etiqueta_remota(spk) and spk not in remotos:
            remotos.append(spk)

    if not remotos:
        return resultado_tx

    perfiles = listar_perfiles_voz()
    sugerencias = _sugerencias_lista()

    print("\n👤 Biblioteca de voces / identificar remotos")
    if perfiles:
        print(f"   Perfiles conocidos: {', '.join(perfiles)}")
    else:
        print("   Aún no hay perfiles. La primera vez hay que nombrar a cada Remoto_N.")
    print("   Auto = voz reconocida | si no reconoce, escribe el nombre (se agrega a la biblioteca).")
    print("   's' = dejar Remoto_N sin nombre\n")

    mapa: dict[str, str] = {}
    ya_asignados: set[str] = set()
    auto_n = 0
    manual_n = 0

    for spk in remotos:
        citas = _snippets_por_speaker(segmentos, spk)
        try:
            sug, sim, emb = reconocer_remoto(
                audio_sys, segmentos, spk, TARGET_RATE, ya_asignados=ya_asignados
            )
        except Exception as e:
            print(f"  ⚠️ Reconocimiento de voz falló para {spk} ({e}). Nombrado manual.")
            sug, sim, emb = None, 0.0, None
        sim = float(sim) if sim is not None else 0.0

        # --- Active learning: auto-aplicar si hay confianza alta ---
        if (
            USAR_RECONOCIMIENTO_VOZ
            and VOICE_AUTO_APPLY
            and isinstance(sug, str)
            and sug
            and sim >= VOICE_AUTO_THRESHOLD
        ):
            mapa[spk] = sug
            ya_asignados.add(sug)
            auto_n += 1
            print(f"  ✅ {spk} → {sug} (voz {sim:.0%} · automático)")
            if citas:
                preview = citas[0] if len(citas[0]) <= 90 else citas[0][:87] + "…"
                print(f"      «{preview}»")
            if enrolar_voz(sug, audio_sys, segmentos, spk, TARGET_RATE, emb_nuevo=emb, citas=citas):
                print(f"      💾 Perfil de voz reforzado: {sug} → .voice_profiles/")
            continue

        # --- Persona nueva o match dudoso: preguntar ---
        print(f"  ▸ {spk}  (voz nueva o poco segura)")
        if citas:
            for c in citas:
                preview = c if len(c) <= 120 else c[:117] + "…"
                print(f"      «{preview}»")
        else:
            print("      (sin texto)")

        prompt = "      Nombre"
        if isinstance(sug, str) and sug:
            prompt += f" [{sug} · voz {sim:.0%} · Enter=aceptar]"
        prompt += " (o escribe persona nueva): "

        try:
            entrada = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n      → se mantiene {spk}")
            mapa[spk] = spk
            continue

        if not entrada:
            nombre = sug if isinstance(sug, str) and sug else spk
        elif entrada.lower() in ("s", "skip", "remoto"):
            nombre = spk
        else:
            nombre = _resolver_nombre_entrada(entrada, sugerencias, spk)

        mapa[spk] = nombre
        manual_n += 1
        print(f"      → {nombre}")

        if nombre != spk and not _es_etiqueta_remota(nombre):
            ya_asignados.add(nombre)
            perfiles = _guardar_perfil_tras_nombrar(
                nombre, spk, audio_sys, segmentos, TARGET_RATE, emb, citas, perfiles
            )
            sugerencias = _sugerencias_lista()

    for s in segmentos:
        old = s.get("speaker")
        if old in mapa:
            s["speaker"] = mapa[old]

    diarizada, plana = _reconstruir_textos(segmentos)
    resultado_tx["segmentos"] = segmentos
    resultado_tx["diarizada"] = diarizada
    resultado_tx["plana"] = plana
    resultado_tx["mapa_remotos"] = mapa
    resultado_tx["voz_auto"] = auto_n
    resultado_tx["voz_manual"] = manual_n

    print(f"\n   Resumen: {auto_n} auto · {manual_n} manual · biblioteca: {len(listar_perfiles_voz())} perfiles\n")
    return resultado_tx
