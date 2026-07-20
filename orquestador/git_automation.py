# git_automation.py
"""
Git solo en repos de producto mapeados en .env (PROYECTO_*).
Este orquestador NUNCA cambia de rama ni hace commit en su propio repo.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from config import AUTO_GIT_COMMIT, BASE_DIR, CLAVE_ORQUESTADOR, resolver_proyecto


def _run_git(ruta_repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(ruta_repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=check,
    )


def _es_repo_git(ruta: Path) -> bool:
    return (ruta / ".git").is_dir()


def _es_orquestador(ruta: Path) -> bool:
    return ruta.resolve() == BASE_DIR.resolve()


def normalizar_rama(rama: str) -> str:
    rama = (rama or "feature/tareas-reunion").strip().lower().replace(" ", "-")
    rama = rama.replace("future/", "feature/")
    if not rama.startswith(("feature/", "fix/", "chore/", "docs/", "hotfix/")):
        rama = f"feature/{rama}"
    rama = re.sub(r"[^a-z0-9._/\-]", "", rama)
    rama = re.sub(r"/{2,}", "/", rama)
    return rama[:80] or "feature/tareas-reunion"


def confirmar_nombre_rama(propuesta: str) -> str | None:
    """
    Pregunta: Confirmar crear rama: feature/...? Y/N
    Si N → pide escribir el nombre y vuelve a confirmar.
    Retorna el nombre final o None si cancela.
    """
    propuesta = normalizar_rama(propuesta)

    while True:
        try:
            resp = input(f"Confirmar crear rama: {propuesta}? [Y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n❌ Creación de rama cancelada.")
            return None

        if resp in ("y", "yes", "s", "si", "sí"):
            return propuesta

        if resp in ("n", "no"):
            try:
                nuevo = input(
                    "Escribe el nombre de la rama (o 'cancelar'): "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n❌ Creación de rama cancelada.")
                return None

            if not nuevo or nuevo.lower() in ("cancelar", "cancel", "n", "no"):
                print("❌ Creación de rama cancelada. El prompt queda solo en docs/ local.")
                return None

            propuesta = normalizar_rama(nuevo)
            continue

        print("  Responde Y o N.")


def aplicar_cambios_locales(
    nombre_proyecto: str,
    nombre_rama: str,
    contenido_markdown: str,
    carpeta_sesion: Path | None = None,
    auto_commit: bool | None = None,
) -> Path | None:
    """
    En el repo del PRODUCTO: confirma rama → checkout → copia docs/reuniones → commit.
    Nunca opera sobre el repo del orquestador.
    """
    if auto_commit is None:
        auto_commit = AUTO_GIT_COMMIT

    clave, ruta_repo = resolver_proyecto(nombre_proyecto)

    if _es_orquestador(ruta_repo) or clave == CLAVE_ORQUESTADOR:
        print(
            "ℹ️ Proyecto sin repo de producto mapeado. "
            "No se crea rama ni commit aquí (este repo es solo orquestador y permanece en main)."
        )
        return None

    if not ruta_repo.exists():
        print(f"⚠️ Repo no existe en disco: {ruta_repo}. Solo se guardó en docs/ local.")
        return None

    if not _es_repo_git(ruta_repo):
        print(f"⚠️ '{ruta_repo}' no es un repositorio Git. Se omite automatización Git.")
        return None

    print(f"📁 Repo destino: {ruta_repo} (clave={clave})")

    if not auto_commit:
        print("ℹ️ AUTO_GIT_COMMIT=False — se omite rama/commit en el producto.")
        return None

    nombre_rama = confirmar_nombre_rama(nombre_rama)
    if not nombre_rama:
        return None

    # Destino unificado dentro del repo del producto
    fecha_nombre = carpeta_sesion.name if carpeta_sesion else "sesion"
    rel_dir = Path("docs") / "reuniones" / clave / fecha_nombre
    abs_dir = ruta_repo / rel_dir

    try:
        print(f"🌿 Creando/cambiando a rama: {nombre_rama}")
        actual = _run_git(ruta_repo, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        rama_actual = (actual.stdout or "").strip()

        if rama_actual != nombre_rama:
            # ¿La rama ya existe?
            existe = _run_git(
                ruta_repo,
                ["show-ref", "--verify", "--quiet", f"refs/heads/{nombre_rama}"],
                check=False,
            )
            if existe.returncode == 0:
                _run_git(ruta_repo, ["checkout", nombre_rama], check=True)
                print(f"   Rama existente: checkout → {nombre_rama}")
            else:
                _run_git(ruta_repo, ["checkout", "-b", nombre_rama], check=True)
                print(f"   Rama nueva creada: {nombre_rama}")

        abs_dir.mkdir(parents=True, exist_ok=True)
        ruta_md = abs_dir / "prompt_cursor.md"
        ruta_md.write_text(contenido_markdown.strip() + "\n", encoding="utf-8")

        if carpeta_sesion:
            for extra in ("transcripcion.txt", "meta.json"):
                origen = carpeta_sesion / extra
                if origen.exists():
                    (abs_dir / extra).write_text(
                        origen.read_text(encoding="utf-8"), encoding="utf-8"
                    )

        print(f"📄 Prompt copiado al repo: {ruta_md}")

        rel_posix = rel_dir.as_posix()
        _run_git(ruta_repo, ["add", f"{rel_posix}/"], check=True)

        estado = _run_git(ruta_repo, ["status", "--porcelain", f"{rel_posix}/"], check=False)
        if not (estado.stdout or "").strip():
            print("ℹ️ No hay cambios nuevos para commit.")
            return ruta_md

        mensaje = f"docs: minuta de reunión automatizada ({nombre_rama})"
        _run_git(ruta_repo, ["commit", "-m", mensaje], check=True)
        print(f"💾 Commit local en {clave} → {nombre_rama}")
        return ruta_md

    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        print(f"❌ Error Git: {stderr or e}")
        return None
    except Exception as e:
        print(f"❌ Error inesperado en automatización Git: {e}")
        return None
