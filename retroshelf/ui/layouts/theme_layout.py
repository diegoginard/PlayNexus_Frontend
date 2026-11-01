"""
=============================================================================
Cargador Dinámico y Despachador de Layouts Temáticos de RetroShelf
=============================================================================
Cada sistema (Sega Genesis, Super Nintendo, Sony Playstation, Sega CD, Sega Saturn,
Sega 32X, etc.) posee su propia carpeta dentro de 'Layouts/<Nombre>/' con su propio
archivo 'theme_layout.py' totalmente autónomo e independiente que maneja el 100%
de su renderizado, animaciones, geometría, audio y controles.

Este archivo actúa exclusivamente como un cargador liviano y despachador dinámico
para instanciar el layout correspondiente según el sistema seleccionado.
"""
import os
import sys
import importlib.util
from pathlib import Path
from typing import Any

from retroshelf.ui.layouts.base import BaseLayout
from retroshelf.services.themes import get_theme_info

# Alias de compatibilidad
BaseThemeLayout = BaseLayout

# Cache de clases de layouts cargadas por mtime para recarga inmediata al editar
_THEME_CLASS_CACHE: dict[str, tuple[float, type[Any]]] = {}


def get_theme_layout_class(theme_name: str) -> type[Any]:
    """
    Carga dinámicamente la clase 'ThemeLayout' desde 'Layouts/<Sistema>/theme_layout.py'.
    Cada carpeta maneja la totalidad de su configuración y renderizado de forma autónoma.
    """
    if not theme_name:
        return BaseLayout

    theme_info = get_theme_info(theme_name)
    folder = Path(theme_info["folder"]) if theme_info and theme_info.get("folder") else None
    if not folder or not folder.is_dir():
        from retroshelf.services.themes import get_layouts_root
        cand = get_layouts_root() / theme_name
        if cand.is_dir():
            folder = cand
        else:
            return BaseLayout

    theme_file = folder / "theme_layout.py"
    if not theme_file.is_file():
        return BaseLayout

    cache_key = str(theme_file.resolve())
    try:
        mtime = theme_file.stat().st_mtime
    except OSError:
        mtime = 0.0

    if cache_key in _THEME_CLASS_CACHE:
        cached_mtime, cached_cls = _THEME_CLASS_CACHE[cache_key]
        if cached_mtime == mtime:
            return cached_cls

    try:
        safe_name = "".join(c if c.isalnum() else "_" for c in folder.name).lower()
        mod_name = f"retroshelf_theme_{safe_name}"
        spec = importlib.util.spec_from_file_location(mod_name, str(theme_file))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)

            # Buscar la clase 'ThemeLayout' u otras variantes comunes en el archivo
            for attr in ("ThemeLayout", "Layout", "SystemThemeLayout", "SystemLayout"):
                if hasattr(mod, attr):
                    cls = getattr(mod, attr)
                    if isinstance(cls, type) and issubclass(cls, BaseLayout):
                        _THEME_CLASS_CACHE[cache_key] = (mtime, cls)
                        return cls

            # Buscar cualquier subclase de BaseLayout definida en el archivo
            for attr_name in dir(mod):
                val = getattr(mod, attr_name)
                if isinstance(val, type) and issubclass(val, BaseLayout) and val is not BaseLayout:
                    _THEME_CLASS_CACHE[cache_key] = (mtime, val)
                    return val
    except Exception as e:
        print(f"[RetroShelf] Error al cargar layout desde {theme_file}: {e}")

    return BaseLayout


class SystemThemeLayout(BaseLayout):
    """
    Fábrica compatible hacia atrás. Instancia la clase autónoma
    'ThemeLayout' definida en la carpeta de cada sistema.
    """
    def __new__(cls, theme_name: str = "Super Nintendo Entertainment System", parent=None):
        """Gestiona la operación '__new__' de este layout temático."""
        target_cls = get_theme_layout_class(theme_name)
        if target_cls is not cls and target_cls is not BaseLayout:
            try:
                return target_cls(theme_name=theme_name, parent=parent)
            except TypeError:
                return target_cls(parent=parent)
        return super().__new__(cls)

    def __init__(self, theme_name: str = "Super Nintendo Entertainment System", parent=None):
        """Inicializa los componentes internos, estructuras de datos y temporizadores del objeto."""
        super().__init__(parent=parent, theme_name=theme_name)

