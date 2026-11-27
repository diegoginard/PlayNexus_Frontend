"""
Información centralizada de versión y metadatos de PlayNexus.
"""
import subprocess
import sys
from pathlib import Path

__version__ = "1.7.0"
__app_name__ = "PlayNexus"
__release_date__ = "Noviembre 2026"
_FALLBACK_COMMIT = ""


def _read_embedded_build_commit() -> str:
    """Lee el commit incrustado durante la compilación del ejecutable, si existe."""
    candidates = [Path(__file__).resolve().parent / "_build_commit.txt"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "playnexus" / "_build_commit.txt")
    for cand in candidates:
        try:
            if cand.is_file():
                val = cand.read_text(encoding="utf-8").strip()
                if val:
                    return val
        except OSError:
            continue
    return ""


def get_git_commit(short: bool = True) -> str:
    """Obtiene el hash del commit actual de Git, o el incrustado en el build."""
    if getattr(sys, "frozen", False):
        return _read_embedded_build_commit() or _FALLBACK_COMMIT

    try:
        repo_dir = Path(__file__).resolve().parent.parent
        cmd = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=1,
            creationflags=creationflags
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return _read_embedded_build_commit() or _FALLBACK_COMMIT


__commit__ = get_git_commit()
__version_full__ = f"v{__version__} ({__commit__})" if __commit__ else f"v{__version__}"


