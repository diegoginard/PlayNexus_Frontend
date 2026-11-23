"""
=============================================================================
Plantilla Canónica y Generador de ThemeLayout Base para PlayNexus
=============================================================================
Proporciona la arquitectura base estandarizada sobre la cual se construyen
todos los nuevos layouts creados a través de Layout Studio, garantizando:
  - Regla 4 de GEMINI.md: Requerimientos de medios estrictamente explícitos.
  - Regla 5 de GEMINI.md: Commit on release / Debounce (~180ms) con video continuo.
  - Regla 6 de GEMINI.md: Fidelidad 100% en coordenadas canónicas 1920x1080.
  - Regla 8 de GEMINI.md: Orden riguroso en cabecera de clase:
      1. MEDIA_REQUIREMENTS
      2. FONT_* y FONT_FILES
      3. Recursos compartidos (gtc-common) y locales
      4. Configuración geométrica y métricas inspeccionables
  - Herencia directa desde `ConsoleThemeLayout` (ruleta curva unificada de 14 nodos).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from playnexus.i18n import tr
from playnexus.ui.layout_studio.models import LayoutElement, LayoutProject, CANONICAL_W, CANONICAL_H


def get_default_media_requirements(layout_type: str = "console", is_cd: bool = False) -> list[dict[str, Any]]:
    """Devuelve los requerimientos de medios predeterminados según el tipo de layout."""
    reqs = [
        {
            "key": "video",
            "label": tr("studio.media.video_snaps", "Video Snaps"),
            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
            "required": True,
        },
        {
            "key": "wheel",
            "label": tr("studio.media.wheel_logos", "Wheel Logos"),
            "extensions": [".png", ".webp"],
            "required": True,
        },
    ]
    if layout_type in ("console", "retro_console"):
        art_key = "discart" if is_cd else "cartart"
        art_label = (
            tr("studio.media.discs_cds", "Discs / CDs")
            if is_cd
            else tr("studio.media.cartridges", "Cartridges")
        )
        reqs.append({
            "key": art_key,
            "label": art_label,
            "extensions": [".png", ".webp"],
            "required": False,
        })
        reqs.append({
            "key": "boxart",
            "label": tr("studio.media.boxart", "Box Art / Boxes"),
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": False,
        })
    elif layout_type == "arcade":
        reqs.append({
            "key": "marquee",
            "label": tr("studio.media.marquee_full", "Marquee"),
            "extensions": [".png", ".jpg", ".webp"],
            "required": False,
        })
        reqs.append({
            "key": "flyer",
            "label": tr("studio.media.flyers", "Flyers"),
            "extensions": [".png", ".jpg", ".webp"],
            "required": False,
        })
    return reqs


def generate_canonical_theme_layout_code(
    name: str,
    description: str = "",
    layout_type: str = "console",
    is_cd: bool = False,
    elements: list[dict[str, Any]] | None = None,
    tv_rect: tuple[float, float, float, float] | None = None,
    bkg_file: str | None = None,
    tv_file: str | None = None,
    console_file: str | None = None,
    joystick_file: str | None = None,
    avatar_file: str | None = None,
    cartart_file: str | None = None,
    boxart_file: str | None = None,
    pointer_file: str | None = None,
    font_title: str | None = None,
    font_main: str | None = None,
    shader_preset: str | None = None,
    shader_target: str = "tv_rect",
    particle_preset: str | None = None,
) -> str:
    """
    Genera el código fuente declarativo de un archivo 'theme_layout.py' que hereda
    de `ConsoleThemeLayout` cumpliendo las directivas 4, 5, 6, 8, 9 y 10 de GEMINI.md.
    """
    layout_folder = Path("Layouts") / name
    if layout_folder.is_dir():
        if not bkg_file:
            for cand in ("bkg.jpg", "bg.jpg", "bkg.png", "bg.png"):
                if (layout_folder / cand).is_file():
                    bkg_file = cand
                    break
        if not tv_file:
            for cand in ("tv.png", "tv_bezel.png", "bezel.png"):
                if (layout_folder / cand).is_file():
                    tv_file = cand
                    break
        if not console_file and (layout_folder / "console.png").is_file():
            console_file = "console.png"
        if not joystick_file and (layout_folder / "joystick.png").is_file():
            joystick_file = "joystick.png"
        if not avatar_file:
            for cand in ("avatar.png", "ryu.png", "samus.png", "character.png"):
                if (layout_folder / cand).is_file():
                    avatar_file = cand
                    break
        if not cartart_file:
            for cand in (("discart.png", "cartart.png") if is_cd else ("cartart.png", "discart.png")):
                if (layout_folder / cand).is_file():
                    cartart_file = cand
                    break
        if not boxart_file and (layout_folder / "boxart.png").is_file():
            boxart_file = "boxart.png"
        if not pointer_file:
            for cand in ("pointers/default.png", "default.png"):
                if (layout_folder / cand).is_file():
                    pointer_file = cand
                    break
        if not font_title or not font_main:
            fonts = [f.name for f in layout_folder.iterdir() if f.suffix.lower() in (".ttf", ".otf")]
            if fonts:
                font_title = font_title or fonts[0]
                font_main = font_main or (fonts[1] if len(fonts) > 1 else fonts[0])

    bkg_file = bkg_file or "bg.jpg"
    tv_file = tv_file or "tv.png"
    console_file = console_file or "console.png"
    joystick_file = joystick_file or ""
    avatar_file = avatar_file or "avatar.png"
    cartart_file = cartart_file or ("discart.png" if is_cd else "cartart.png")
    boxart_file = boxart_file or "boxart.png"
    pointer_file = pointer_file or "pointers/default.png"
    font_title = font_title or "BebasNeue Bold.otf"
    font_main = font_main or "Handel Gothic BT.ttf"
    tv_rect = tv_rect or (0.054, 0.196, 0.313, 0.430)

    _raw_sp = str(shader_preset or "").strip().lower()
    norm_shader = None if not _raw_sp or _raw_sp in ("none", "off", "nil") else _raw_sp
    norm_target = "global" if str(shader_target or "").strip().lower() == "global" else "tv_rect"
    _raw_pp = str(particle_preset or "").strip().lower()
    norm_particle = None if not _raw_pp or _raw_pp in ("none", "off", "nil") else _raw_pp

    reqs = get_default_media_requirements(layout_type, is_cd)
    media_reqs_str = "\n".join(f"        {r!r}," for r in reqs)

    if elements:
        elements_block = "\n".join(f"    {elem!r}," for elem in elements)
        studio_effects = {
            "shader_preset": norm_shader,
            "shader_target": norm_target,
            "particle_preset": norm_particle,
        }
        studio_block = f'''

# --- PLAYNEXUS STUDIO OVERRIDES START ---
STUDIO_ELEMENTS = [
{elements_block}
]
STUDIO_EFFECTS = {studio_effects!r}
try:
    from playnexus.ui.layout_studio.runtime_hook import install_studio_overrides as _install_studio_overrides
    _orig_init = ThemeLayout.__init__
    def _studio_patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        _install_studio_overrides(self, STUDIO_ELEMENTS, **STUDIO_EFFECTS)
    if not getattr(ThemeLayout.__init__, '_is_studio_patched', False):
        _orig_init = ThemeLayout.__init__
        _studio_patched_init._is_studio_patched = True
        ThemeLayout.__init__ = _studio_patched_init
except Exception:
    pass
# --- PLAYNEXUS STUDIO OVERRIDES END ---'''
    else:
        studio_block = ""

    if is_cd:
        cart_rect_str = "(0.550, 0.600, 0.190, 0.300)"
        cart_end_y_str = "0.600"
        boxart_x_str = "0.400"
        boxart_y_str = "0.530"
        boxart_w_str = "0.165"
        boxart_h_str = "0.410"
        boxart_anchor_str = '"center"'
    else:
        cart_rect_str = "(0.428, 0.540, 0.121, 0.250)"
        cart_end_y_str = "0.540"
        boxart_x_str = "0.015"
        boxart_y_str = "0.548"
        boxart_w_str = "0.240"
        boxart_h_str = "0.380"
        boxart_anchor_str = '"bottom"'

    layout_desc = description or tr(
        "studio.canonical.default_description",
        "{name} interactive themed layout",
        name=name,
    )
    joystick_line = (
        f'    JOYSTICK_IMAGE = LAYOUT_DIR / {joystick_file!r} if (LAYOUT_DIR / {joystick_file!r}).is_file() else None'
        if joystick_file
        else "    JOYSTICK_IMAGE = None"
    )
    discart_line = (
        f'    DISCART_IMAGE = LAYOUT_DIR / {cartart_file!r} if (LAYOUT_DIR / {cartart_file!r}).is_file() else None\n'
        f'    CARTART_IMAGE = DISCART_IMAGE'
        if is_cd
        else f'    DISCART_IMAGE = None\n    CARTART_IMAGE = LAYOUT_DIR / {cartart_file!r} if (LAYOUT_DIR / {cartart_file!r}).is_file() else None'
    )

    code = f'''"""
=============================================================================
Layout Declarativo: {name}
Generado sobre la Arquitectura Base Canónica de PlayNexus (`ConsoleThemeLayout`)
=============================================================================
Cumple con las directivas 4, 5, 6, 8, 9 y 10 de GEMINI.md.
"""
from pathlib import Path

from playnexus.ui.layouts.theme_base import ConsoleThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(ConsoleThemeLayout):
    LAYOUT_NAME = {name!r}
    LAYOUT_DESCRIPTION = {layout_desc!r}
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
{media_reqs_str}
    ]

    # 2. Fuentes tipográficas
    FONT_TITLE_FILE = {font_title!r}
    FONT_MAIN_FILE = {font_main!r}
    FONT_FILES = [FONT_TITLE_FILE, FONT_MAIN_FILE]

    # 3. Recursos compartidos (gtc-common) y locales
    WHEEL_SHADOW_IMAGE = COMMON_DIR / "wheel" / "wheel_shadow.png"
    COMMON_WHEEL_ART = COMMON_DIR / "art" / "wheel_art.png"
    COMMON_FRAME = COMMON_DIR / "art" / "frame.png"
    STATIC_VIDEO = COMMON_DIR / "videos" / "static.mp4"
    SOUND_NAV = COMMON_DIR / "sounds" / "joystick.mp3"
    SOUND_SELECT = COMMON_DIR / "sounds" / "Mame_coin.mp3"
    SCANLINES_IMAGE = COMMON_DIR / "art" / "scanlines_1920.png"
    SCRATCHES_IMAGE = COMMON_DIR / "art" / "arcade" / "scratched_cover.png"

    BKG_IMAGE = LAYOUT_DIR / {bkg_file!r} if (LAYOUT_DIR / {bkg_file!r}).is_file() else None
    TV_IMAGE = LAYOUT_DIR / {tv_file!r} if (LAYOUT_DIR / {tv_file!r}).is_file() else None
    CONSOLE_IMAGE = LAYOUT_DIR / {console_file!r} if (LAYOUT_DIR / {console_file!r}).is_file() else None
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png" if (LAYOUT_DIR / "console_cover.png").is_file() else None
{joystick_line}
    AVATAR_IMAGE = LAYOUT_DIR / {avatar_file!r} if (LAYOUT_DIR / {avatar_file!r}).is_file() else None
    LOGO_IMAGE = LAYOUT_DIR / "logo.png" if (LAYOUT_DIR / "logo.png").is_file() else None
{discart_line}
    BOXART_IMAGE = LAYOUT_DIR / {boxart_file!r} if (LAYOUT_DIR / {boxart_file!r}).is_file() else None
    WHEEL_IMAGE = LAYOUT_DIR / "wheel.png" if (LAYOUT_DIR / "wheel.png").is_file() else None
    POINTER_IMAGE = LAYOUT_DIR / {pointer_file!r} if (LAYOUT_DIR / {pointer_file!r}).is_file() else None

    # 4. Configuración geométrica y efectos
    TV_RECT = {tv_rect!r}
    SHADER_PRESET = {norm_shader!r}
    SHADER_TARGET = {norm_target!r}
    PARTICLE_PRESET = {norm_particle!r}

    DISC_RECT = {cart_rect_str}
    CART_RECT = DISC_RECT
    CART_END_Y = {cart_end_y_str}
    IS_CD = {"True" if is_cd else "False"}

    BOXART_X = {boxart_x_str}
    BOXART_Y = {boxart_y_str}
    BOXART_W = {boxart_w_str}
    BOXART_H = {boxart_h_str}
    BOXART_ANCHOR = {boxart_anchor_str}

    AVATAR_SCALE = 1.0
    AVATAR_X = 0.0
    AVATAR_Y = 0.0
    AVATAR_Y_ADJUST = 0
    LOGO_SCALE = 1.0

    BOTTOM_USE_FRAME = False
    BOTTOM_BAR_BG_COLOR = (10, 15, 25, 210)
    BOTTOM_TITLE_X_RATIO = 0.05
    BOTTOM_TITLE_W_RATIO = 0.65
    BOTTOM_COUNTER_X_RATIO = 0.72
    BOTTOM_COUNTER_W_RATIO = 0.24
    BOTTOM_COUNTER_PREFIX = ""{studio_block}
'''
    return code


def setup_new_layout_files(layout_dir: Path, layout_type: str, name: str) -> None:
    """
    Crea la carpeta de un nuevo layout y copia los recursos iniciales esenciales
    (o crea punteros/fondo por defecto) para que el layout sea 100% operativo de inmediato.
    """
    layout_dir.mkdir(parents=True, exist_ok=True)
    pointers_dir = layout_dir / "pointers"
    pointers_dir.mkdir(parents=True, exist_ok=True)

    gtc_common = layout_dir.parent / "gtc-common"

    # 1. Puntero por defecto
    default_ptr = pointers_dir / "default.png"
    if not default_ptr.is_file():
        # Buscar puntero existente en otros layouts
        found_ptr = False
        for sibling in layout_dir.parent.iterdir():
            cand = sibling / "pointers" / "default.png"
            if cand.is_file():
                try:
                    shutil.copy2(cand, default_ptr)
                    found_ptr = True
                    break
                except Exception:
                    pass
        if not found_ptr:
            # Crear un puntero transparente básico si no existe ninguno
            from PySide6.QtGui import QImage, QPainter, QColor, QPolygon
            from PySide6.QtCore import QPoint
            img = QImage(64, 64, QImage.Format_ARGB32_Premultiplied)
            img.fill(0)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setBrush(QColor(245, 185, 35))
            p.setPen(QColor(255, 255, 255))
            poly = QPolygon([QPoint(10, 10), QPoint(54, 32), QPoint(10, 54), QPoint(20, 32)])
            p.drawPolygon(poly)
            p.end()
            img.save(str(default_ptr))

    # 2. Fondo por defecto
    bg_file = layout_dir / "bg.jpg"
    if not bg_file.is_file():
        common_bkg = gtc_common / "art" / "arcade" / "bkg.jpg"
        if common_bkg.is_file():
            try:
                shutil.copy2(common_bkg, bg_file)
            except Exception:
                pass
        else:
            # Buscar bg.jpg en layouts hermanos
            for sibling in layout_dir.parent.iterdir():
                cand = sibling / "bg.jpg"
                if cand.is_file():
                    try:
                        shutil.copy2(cand, bg_file)
                        break
                    except Exception:
                        pass

    # 3. Wheel de muestra si no existe
    wheel_file = layout_dir / "wheel.png"
    if not wheel_file.is_file():
        common_wheel = gtc_common / "art" / "wheel_art.png"
        if common_wheel.is_file():
            try:
                shutil.copy2(common_wheel, wheel_file)
            except Exception:
                pass
