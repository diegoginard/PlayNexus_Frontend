import sys
import os
import random
from pathlib import Path

# Directorio raíz del proyecto PlayNexus (todo dentro de la carpeta de PlayNexus)
if getattr(sys, "frozen", False):
    REPO_ROOT = Path(sys.executable).resolve().parent
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent

APP_DATA_DIR = REPO_ROOT


def get_layouts_root() -> Path:
    """
    Retorna la ruta a la carpeta 'Layouts' principal dentro de la carpeta de PlayNexus.
    """
    repo_layouts = REPO_ROOT / "Layouts"
    repo_layouts.mkdir(parents=True, exist_ok=True)
    return repo_layouts


_THEMES_CACHE: dict[str, dict] | None = None


def get_all_theme_layouts(force_reload: bool = False) -> dict[str, dict]:
    """
    Escanea la carpeta 'Layouts' y registra las subcarpetas de sistemas emulados.
    Cada carpeta de layout maneja de manera 100% autónoma sus propios archivos y recursos.
    """
    global _THEMES_CACHE
    if _THEMES_CACHE is not None and not force_reload:
        return _THEMES_CACHE

    layouts_dir = get_layouts_root()
    themes = {}

    if not layouts_dir.is_dir():
        _THEMES_CACHE = themes
        return themes

    for entry in os.scandir(layouts_dir):
        if not entry.is_dir():
            continue
        if entry.name.startswith((".", "_")):
            continue
        folder = Path(entry.path)
        # Solo registrar carpetas que contengan theme_layout.py
        if not (folder / "theme_layout.py").is_file():
            continue

        themes[entry.name] = {
            "name": entry.name,
            "folder": str(folder),
        }

    _THEMES_CACHE = themes
    return themes


def get_theme_info(theme_name: str) -> dict | None:
    """Obtiene la información básica (nombre y carpeta) de un tema específico."""
    if not theme_name:
        return None
    themes = get_all_theme_layouts()
    if theme_name in themes:
        return themes[theme_name]
    tn_lower = theme_name.lower().strip()
    for name, info in themes.items():
        if tn_lower == name.lower():
            return info
    for name, info in themes.items():
        if tn_lower in name.lower() or name.lower() in tn_lower:
            return info
    return None


GENERIC_MEDIA_SPECS: dict[str, list[dict]] = {
    "Grid": [
        {
            "key": "boxart",
            "label": "Box Art / Carátulas",
            "folder": "boxart",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": True
        }
    ],
    "Showcase": [
        {
            "key": "boxart",
            "label": "Box Art / Carátulas",
            "folder": "boxart",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": True
        },
        {
            "key": "video",
            "label": "Video Snaps",
            "folder": "videos",
            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
            "required": False
        }
    ],
    "Wheel": [
        {
            "key": "wheel",
            "label": "Wheel Logos",
            "folder": "wheel",
            "extensions": [".png", ".webp"],
            "required": True
        },
        {
            "key": "video",
            "label": "Video Snaps",
            "folder": "videos",
            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
            "required": False
        },
        {
            "key": "boxart",
            "label": "Box Art / Carátulas",
            "folder": "boxart",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": False
        }
    ],
    "Banners": [
        {
            "key": "wheel",
            "label": "Logos o Banners",
            "folder": "wheel",
            "extensions": [".png", ".webp"],
            "required": True
        },
        {
            "key": "boxart",
            "label": "Box Art / Carátulas",
            "folder": "boxart",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": False
        }
    ],
    "Detalles": [
        {
            "key": "boxart",
            "label": "Box Art / Carátulas",
            "folder": "boxart",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": True
        }
    ]
}


def get_layout_media_spec(layout_name: str) -> list[dict]:
    """
    Obtiene la especificación de medios requeridos por un layout:
    1. Si es un layout genérico estándar, retorna su especificación predefinida.
    2. Si es un tema de sistema, lee los requerimientos directamente desde su 'theme_layout.py'
       (mediante MEDIA_REQUIREMENTS o deducción autónoma de sus recursos).
    3. Si no existe especificación, retorna lista vacía.
    """
    if not layout_name:
        return []

    # 1. Layouts genéricos estándar
    for name, spec in GENERIC_MEDIA_SPECS.items():
        if layout_name.lower() == name.lower():
            return spec

    # 2. Temas autónomos: leer directamente desde ThemeLayout en theme_layout.py
    info = get_theme_info(layout_name)
    if info and info.get("folder"):
        th_folder = Path(info["folder"])
        th_file = th_folder / "theme_layout.py"
        if th_file.is_file():
            try:
                from playnexus.ui.layouts.theme_layout import get_theme_layout_class
                cls = get_theme_layout_class(layout_name)
                if cls:
                    # Atributo explícito MEDIA_REQUIREMENTS
                    if hasattr(cls, "MEDIA_REQUIREMENTS") and cls.MEDIA_REQUIREMENTS:
                        return list(cls.MEDIA_REQUIREMENTS)
                    if hasattr(cls, "get_media_requirements") and callable(cls.get_media_requirements):
                        return list(cls.get_media_requirements())

                    # Auto-detección desde los componentes declarados en ThemeLayout
                    detected = []
                    if getattr(cls, "TV_RECT", None) or getattr(cls, "TV_IMAGE", None):
                        detected.append({
                            "key": "video",
                            "label": "Video Snaps",
                            "folder": "videos",
                            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
                            "required": True
                        })
                    if getattr(cls, "WHEEL_IMAGE", None):
                        detected.append({
                            "key": "wheel",
                            "label": "Wheel Logos",
                            "folder": "wheel",
                            "extensions": [".png", ".webp"],
                            "required": True
                        })
                    if getattr(cls, "CARTART_IMAGE", None):
                        is_cd = getattr(cls, "IS_CD", False) or "disc" in str(getattr(cls, "CARTART_IMAGE", "")).lower()
                        lbl = "Discos" if is_cd else "Cartuchos"
                        detected.append({
                            "key": "cartart",
                            "label": lbl,
                            "folder": "cartart",
                            "extensions": [".png", ".webp"],
                            "required": True
                        })
                    if getattr(cls, "BOXART_IMAGE", None):
                        detected.append({
                            "key": "boxart",
                            "label": "Box Art / Carátulas",
                            "folder": "boxart",
                            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
                            "required": False
                        })
                    if detected:
                        return detected
            except Exception as e:
                print(f"[PlayNexus] Error al leer requerimientos de {th_file}: {e}")

    return []


