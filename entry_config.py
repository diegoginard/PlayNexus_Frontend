"""
Punto de entrada para el ejecutable del Configurador de PlayNexus.
"""
import sys
import os
from pathlib import Path

# Asegurar que el directorio raíz de PlayNexus esté en sys.path
if getattr(sys, "frozen", False):
    app_root = Path(sys.executable).resolve().parent
else:
    app_root = Path(__file__).resolve().parent

if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

import playnexus
from playnexus.ui.main_window import run

def main():
    try:
        from playnexus.db import Database
        db = Database()
        driver = db.get_setting("video_driver", "d3d11")
        if driver:
            os.environ["QSG_RHI_BACKEND"] = driver
            os.environ["QT_RHI_BACKEND"] = driver
    except Exception:
        pass
    run()

if __name__ == "__main__":
    main()

