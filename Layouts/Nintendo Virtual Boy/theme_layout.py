"""
=============================================================================
Layout Declarativo: Nintendo Virtual Boy
=============================================================================
"""
from pathlib import Path

from playnexus.ui.layouts.theme_base import ConsoleThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(ConsoleThemeLayout):
    LAYOUT_NAME = 'Nintendo Virtual Boy'
    LAYOUT_DESCRIPTION = 'Layout temático interactivo oficial de Nintendo Virtual Boy'
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
        {'key': 'video', 'label': 'Video Snaps', 'extensions': ['.mp4', '.mkv', '.avi', '.webm'], 'required': True},
        {'key': 'wheel', 'label': 'Wheel Logos', 'extensions': ['.png', '.webp'], 'required': True},
        {'key': 'cartart', 'label': 'Cartuchos', 'extensions': ['.png', '.webp'], 'required': False},
        {'key': 'boxart', 'label': 'Box Art / Cajas', 'extensions': ['.png', '.jpg', '.jpeg', '.webp'], 'required': False},
    ]

    # 2. Fuentes tipográficas
    FONT_TITLE_FILE = COMMON_DIR / "fonts" / "BebasNeue Bold.otf"
    FONT_MAIN_FILE = LAYOUT_DIR / "Virtual Logo.ttf"
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

    BKG_IMAGE = LAYOUT_DIR / "bg.png" if (LAYOUT_DIR / "bg.png").is_file() else None
    TV_IMAGE = LAYOUT_DIR / "tv.png" if (LAYOUT_DIR / "tv.png").is_file() else None
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png" if (LAYOUT_DIR / "console.png").is_file() else None
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png" if (LAYOUT_DIR / "console_cover.png").is_file() else None
    JOYSTICK_IMAGE = LAYOUT_DIR / "joystick.png" if (LAYOUT_DIR / "joystick.png").is_file() else None
    AVATAR_IMAGE = LAYOUT_DIR / "avatar.png" if (LAYOUT_DIR / "avatar.png").is_file() else None
    LOGO_IMAGE = LAYOUT_DIR / "logo.png" if (LAYOUT_DIR / "logo.png").is_file() else None
    DISCART_IMAGE = None
    CARTART_IMAGE = LAYOUT_DIR / "cartart.png" if (LAYOUT_DIR / "cartart.png").is_file() else None
    BOXART_IMAGE = LAYOUT_DIR / "boxart.png" if (LAYOUT_DIR / "boxart.png").is_file() else None
    WHEEL_IMAGE = COMMON_DIR / "wheel" / "wheel.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers/default.png" if (LAYOUT_DIR / "pointers/default.png").is_file() else None

    # 4. Geometría y estilo del tema
    TV_RECT = (0.203, 0.451, 0.264, 0.125)
    CART_RECT = (0.428, 0.540, 0.121, 0.250)
    CART_END_Y = 0.540
    IS_CD = False

    BOXART_X = 0.015
    BOXART_Y = 0.548
    BOXART_W = 0.240
    BOXART_H = 0.380
    BOXART_ANCHOR = "bottom"
    BOXART_BOTTOM_Y = 0.928

    LAYER_ORDER = (
        "bg_image", "video_snap", "scratches", "console", "cartart",
        "boxart", "avatar", "logo", "wheel_shadow", "wheel_list", "pointer", "footer_frame",
    )

    BOTTOM_USE_FRAME = False
    BOTTOM_BAR_BG_COLOR = (10, 15, 25, 210)
    BOTTOM_TITLE_X_RATIO = 0.05
    BOTTOM_TITLE_W_RATIO = 0.65
    BOTTOM_COUNTER_X_RATIO = 0.72
    BOTTOM_COUNTER_W_RATIO = 0.24
    BOTTOM_COUNTER_PREFIX = ""
