"""
=============================================================================
Layout Declarativo: Sony PlayStation Portable
=============================================================================
"""
from pathlib import Path

from playnexus.ui.layouts.theme_base import ConsoleThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(ConsoleThemeLayout):
    LAYOUT_NAME = "Sony PlayStation Portable"
    LAYOUT_DESCRIPTION = "Layout temático interactivo oficial de Sony PlayStation Portable"
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
        {
            "key": "video",
            "label": "Video Snaps",
            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
            "required": True,
        },
        {
            "key": "wheel",
            "label": "Wheel Logos",
            "extensions": [".png", ".webp"],
            "required": True,
        },
        {
            "key": "cartart",
            "label": "Cartuchos",
            "extensions": [".png", ".webp"],
            "required": False,
        },
        {
            "key": "boxart",
            "label": "Box Art / Cajas",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": False,
        },
    ]

    # 2. Fuentes tipográficas
    FONT_TITLE_FILE = "BebasNeue Bold.otf"
    FONT_MAIN_FILE = "Handel Gothic BT.ttf"
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

    BKG_IMAGE = LAYOUT_DIR / "bg.jpg" if (LAYOUT_DIR / "bg.jpg").is_file() else None
    TV_IMAGE = LAYOUT_DIR / "tv.png" if (LAYOUT_DIR / "tv.png").is_file() else None
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png" if (LAYOUT_DIR / "console.png").is_file() else None
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png" if (LAYOUT_DIR / "console_cover.png").is_file() else None
    JOYSTICK_IMAGE = None
    AVATAR_IMAGE = LAYOUT_DIR / "avatar.png" if (LAYOUT_DIR / "avatar.png").is_file() else None
    LOGO_IMAGE = LAYOUT_DIR / "logo.png" if (LAYOUT_DIR / "logo.png").is_file() else None
    CARTART_IMAGE = LAYOUT_DIR / "cartart.png" if (LAYOUT_DIR / "cartart.png").is_file() else None
    BOXART_IMAGE = LAYOUT_DIR / "boxart.png" if (LAYOUT_DIR / "boxart.png").is_file() else None
    WHEEL_IMAGE = LAYOUT_DIR / "wheel.png" if (LAYOUT_DIR / "wheel.png").is_file() else None
    POINTER_IMAGE = LAYOUT_DIR / "pointers/default.png" if (LAYOUT_DIR / "pointers/default.png").is_file() else None

    # 4. Geometría y orden de capas
    TV_RECT = (0.149, 0.24, 0.365, 0.394)
    CART_RECT = (0.428, 0.540, 0.121, 0.250)
    CART_END_Y = 0.540
    IS_CD = False

    BOXART_X = 0.015
    BOXART_Y = 0.548
    BOXART_W = 0.240
    BOXART_H = 0.380
    BOXART_ANCHOR = "bottom"
    BOXART_BOTTOM_Y = 0.928

    AVATAR_SCALE = 1.0
    AVATAR_X = 0.0
    AVATAR_Y = 0.0
    AVATAR_Y_ADJUST = 0
    LOGO_SCALE = 1.0

    LAYER_ORDER = (
        "bg_image",
        "video_snap",
        "scratches",
        "tv_bezel",
        "console",
        "cartart",
        "console_cover",
        "joystick",
        "boxart",
        "avatar",
        "logo",
        "wheel_shadow",
        "wheel_list",
        "pointer",
        "footer_frame",
    )

    BOTTOM_USE_FRAME = False
    BOTTOM_BAR_BG_COLOR = (10, 15, 25, 210)
    BOTTOM_TITLE_X_RATIO = 0.05
    BOTTOM_TITLE_W_RATIO = 0.65
    BOTTOM_COUNTER_X_RATIO = 0.72
    BOTTOM_COUNTER_W_RATIO = 0.24
    BOTTOM_COUNTER_PREFIX = ""
