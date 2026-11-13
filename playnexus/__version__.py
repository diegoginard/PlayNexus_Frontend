"""
Información centralizada de versión y metadatos de PlayNexus.
"""
import subprocess
from pathlib import Path

__version__ = "1.1.18"
__app_name__ = "PlayNexus"
__release_date__ = "Noviembre 2026"
_FALLBACK_COMMIT = "dbe34a0"


def get_git_commit(short: bool = True) -> str:
    """Obtiene el hash del commit actual de Git, o el commit de respaldo."""
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
    return _FALLBACK_COMMIT


__commit__ = get_git_commit()
__version_full__ = f"v{__version__} ({__commit__})" if __commit__ else f"v{__version__}"


