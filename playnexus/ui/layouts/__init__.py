from playnexus.ui.layouts.base import BaseLayout
from playnexus.ui.layouts.wheel_layout import WheelLayout
from playnexus.ui.layouts.grid_layout import GridLayout
from playnexus.ui.layouts.showcase_layout import ShowcaseLayout
from playnexus.ui.layouts.banner_layout import BannerLayout
from playnexus.ui.layouts.table_layout import TableLayout
from playnexus.ui.layouts.theme_layout import SystemThemeLayout, BaseThemeLayout, get_theme_layout_class
from playnexus.services.themes import get_all_theme_layouts

# Registro de layouts estándar disponibles en PlayNexus
STANDARD_LAYOUTS: dict[str, type[BaseLayout]] = {
    "Wheel": WheelLayout,
    "Showcase": ShowcaseLayout,
    "Grid": GridLayout,
    "Banners": BannerLayout,
    "Detalles": TableLayout,
}

# Diccionario unificado
LAYOUT_REGISTRY: dict[str, type[BaseLayout]] = dict(STANDARD_LAYOUTS)


def resolve_theme_name(name: str, themes: dict[str, dict] | None = None) -> str | None:
    """Resuelve un nombre o alias de layout temático (ej: 'Super Nintendo' -> 'Super Nintendo Entertainment System')."""
    if not name:
        return None
    if themes is None:
        themes = get_all_theme_layouts()
    if name in themes:
        return name
    KNOWN_ALIASES = {
        "n64": "Nintendo 64",
        "snes": "Super Nintendo Entertainment System",
        "super nintendo": "Super Nintendo Entertainment System",
        "genesis": "Sega Genesis",
        "megadrive": "Sega Genesis",
        "mega drive": "Sega Genesis",
        "saturn": "Sega Saturn",
        "segacd": "Sega CD",
        "32x": "Sega 32X",
        "ps1": "Sony Playstation",
        "psx": "Sony Playstation",
        "playstation": "Sony Playstation",
        "main menu": "Main Menu",
        "mainmenu": "Main Menu",
        "menu principal": "Main Menu",
        "menu": "Main Menu",
        "sistemas": "Main Menu",
    }
    n_lower = name.lower().strip()
    if n_lower in KNOWN_ALIASES:
        cand = KNOWN_ALIASES[n_lower]
        if cand in themes:
            return cand
    for t_name in themes:
        if n_lower == t_name.lower():
            return t_name
    for t_name in themes:
        if n_lower in t_name.lower() or t_name.lower() in n_lower:
            return t_name
    # Normalización alfanumérica (elimina espacios y guiones, ej: 'segacd' -> 'Sega CD')
    n_alpha = "".join(c for c in n_lower if c.isalnum())
    if n_alpha:
        for t_name in themes:
            t_alpha = "".join(c for c in t_name.lower() if c.isalnum())
            if n_alpha == t_alpha or n_alpha in t_alpha or t_alpha in n_alpha:
                return t_name
    return None


def get_available_layouts(for_frontend: bool = False) -> list[str]:
    """
    Retorna los nombres de todos los layouts registrados:
    primero los layouts temáticos de sistemas de la carpeta 'Layouts/',
    seguidos por los layouts genéricos (Wheel, Showcase, Grid, Banners, Detalles).

    Si for_frontend es True, excluye los layouts exclusivos de configuración como 'Detalles'.
    """
    themes = get_all_theme_layouts()
    theme_names = list(themes.keys())
    if for_frontend:
        standard_names = [name for name in STANDARD_LAYOUTS.keys() if name != "Detalles"]
    else:
        standard_names = list(STANDARD_LAYOUTS.keys())
    return theme_names + standard_names


def get_layout_class(name: str) -> type[BaseLayout]:
    """Obtiene la clase del layout por su nombre (o GridLayout por defecto)."""
    if name in STANDARD_LAYOUTS:
        return STANDARD_LAYOUTS[name]
    themes = get_all_theme_layouts()
    resolved = resolve_theme_name(name, themes)
    if resolved:
        return get_theme_layout_class(resolved)
    return GridLayout


def create_layout(name: str, parent=None) -> BaseLayout:
    """Instancia y retorna un layout según el nombre especificado."""
    themes = get_all_theme_layouts()
    resolved = resolve_theme_name(name, themes)
    if resolved:
        layout_cls = get_theme_layout_class(resolved)
        return layout_cls(theme_name=resolved, parent=parent)
    cls = get_layout_class(name)
    return cls(parent=parent)

