import ctypes
import os
from pathlib import Path


def _configure_qt_multimedia() -> None:
    """
    Asegura que las librerías de FFmpeg incluidas en PySide6 (avcodec, avformat, avutil, etc.)
    estén en el PATH de Windows antes de inicializar QtMultimedia, para que Qt6 utilice
    'ffmpegmediaplugin.dll' en lugar de 'windowsmediaplugin.dll' (WMF).
    Esto permite reproducir todos los videos H.264 High 4:4:4 (yuv444p) de MAME y evita
    congelamientos al cambiar rápido de juego.
    """
    if os.environ.get("_PLAYNEXUS_MM_INIT") == "1":
        return
    os.environ["_PLAYNEXUS_MM_INIT"] = "1"
    os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg.*=false")
    try:
        import PySide6
        pyside_dir = Path(PySide6.__file__).resolve().parent
        pyside_str = str(pyside_dir)
        current_path = os.environ.get("PATH", "")
        if pyside_str.lower() not in current_path.lower():
            os.environ["PATH"] = pyside_str + os.pathsep + current_path
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(pyside_str)
            except OSError:
                pass
        for avutil_dll in pyside_dir.glob("avutil-*.dll"):
            try:
                ctypes.CDLL(str(avutil_dll)).av_log_set_level(-8)
            except Exception:
                pass
            break
    except Exception:
        pass


_configure_qt_multimedia()

from playnexus.__version__ import __version__, __app_name__, __release_date__

__all__ = ["__version__", "__app_name__", "__release_date__"]

