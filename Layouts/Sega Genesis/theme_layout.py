"""
=============================================================================
Layout Declarativo: Sega Genesis
=============================================================================
"""
from pathlib import Path

from playnexus.ui.layouts.theme_base import ConsoleThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(ConsoleThemeLayout):
    LAYOUT_NAME = 'Sega Genesis'
    LAYOUT_DESCRIPTION = 'Layout temático de Sega Genesis fiel a Attract-Mode con TV CRT y cartucho insertándose'
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
        {'key': 'video', 'label': 'Video Snaps', 'extensions': ['.mp4', '.mkv', '.avi', '.webm'], 'required': True},
        {'key': 'wheel', 'label': 'Wheel Logos', 'extensions': ['.png', '.webp'], 'required': True},
        {'key': 'cartart', 'label': 'Cartuchos', 'extensions': ['.png', '.webp'], 'required': True},
        {'key': 'boxart', 'label': 'Box Art / Cajas', 'extensions': ['.png', '.jpg', '.jpeg', '.webp'], 'required': False},
    ]

    # 2. Fuentes tipográficas
    FONT_TITLE_FILE = COMMON_DIR / "fonts" / "BebasNeue Bold.otf"
    FONT_MAIN_FILE = COMMON_DIR / "fonts" / "Handel Gothic BT.ttf"
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

    BKG_IMAGE = LAYOUT_DIR / "bg.jpeg"
    TV_IMAGE = LAYOUT_DIR / "tv.png"
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png"
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png"
    JOYSTICK_IMAGE = None
    AVATAR_IMAGE = LAYOUT_DIR / "avatar.png"
    LOGO_IMAGE = LAYOUT_DIR / "logo.png"
    DISCART_IMAGE = None
    CARTART_IMAGE = LAYOUT_DIR / "cartart.png"
    BOXART_IMAGE = LAYOUT_DIR / "boxart.png"
    WHEEL_IMAGE = COMMON_DIR / "wheel" / "wheel.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers/default.png"

    # 4. Geometría y estilo del tema
    TV_RECT = (0.049, 0.189, 0.322, 0.440)
    CART_RECT = (0.443, 0.540, 0.125, 0.250)
    CART_END_Y = 0.540
    IS_CD = False

    BOXART_X = -0.05
    BOXART_W = 0.240
    BOXART_H = 0.380
    BOXART_BOTTOM_Y = 0.960
    BOXART_ANCHOR = "bottom"
    BOXART_SLIDE_OFFSET_X = -0.50

    BOTTOM_BAR_BG_COLOR = (8, 10, 20, 235)
    BOTTOM_COUNTER_COLOR = (180, 210, 255)
    BOTTOM_UPPERCASE_TITLE = True
    BOTTOM_INCLUDE_YEAR_MANU = False
    BOTTOM_LETTER_SPACING = 1.5
    BOTTOM_TITLE_W_RATIO = 0.65
    BOTTOM_COUNTER_W_RATIO = 0.25
