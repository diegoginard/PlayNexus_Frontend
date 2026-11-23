"""
=============================================================================
Layout Declarativo: NEC TurboGrafx-16
=============================================================================
"""
from pathlib import Path

from playnexus.ui.layouts.theme_base import ConsoleThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(ConsoleThemeLayout):
    LAYOUT_NAME = 'NEC TurboGrafx-16'
    LAYOUT_DESCRIPTION = 'Layout temático de NEC TurboGrafx-16 con inserción de tarjeta HuCard, TV CRT y nave espacial animada'
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
        {'key': 'video', 'label': 'Video Snaps', 'extensions': ['.mp4', '.mkv', '.avi', '.webm'], 'required': True},
        {'key': 'wheel', 'label': 'Wheel Logos', 'extensions': ['.png', '.webp'], 'required': True},
        {'key': 'cartart', 'label': 'Tarjetas HuCard', 'extensions': ['.png', '.webp'], 'required': True},
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

    BKG_IMAGE = LAYOUT_DIR / "bg.jpg"
    TV_IMAGE = LAYOUT_DIR / "tv.png"
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png"
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png"
    JOYSTICK_IMAGE = LAYOUT_DIR / "joystick.png"
    AVATAR_IMAGE = LAYOUT_DIR / "spaceship.png"
    LOGO_IMAGE = LAYOUT_DIR / "logo.png"
    DISCART_IMAGE = None
    CARTART_IMAGE = LAYOUT_DIR / "cartart.png"
    BOXART_IMAGE = None
    WHEEL_IMAGE = COMMON_DIR / "wheel" / "wheel.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers" / "default.png"

    # 4. Geometría y estilo del tema
    TV_RECT = (0.054, 0.196, 0.313, 0.430)
    SCANLINES_AUTO_LOAD = True
    SCANLINES_OPACITY = 0.35
    CART_RECT = (0.446, 0.655, 0.069, 0.200)
    CART_START_X = 0.480
    CART_END_X = 0.446
    CART_START_Y = 1.100
    CART_END_Y = 0.655
    IS_CD = False

    BOXART_X = 0.015
    BOXART_W = 0.240
    BOXART_H = 0.380
    BOXART_BOTTOM_Y = 0.928
    BOXART_ANCHOR = "bottom"
    BOXART_SLIDE_OFFSET_X = -0.30

    LAYER_ORDER = (
        "bg_image", "video_snap", "scanlines_crt", "tv_bezel", "avatar", "logo",
        "console", "cartart", "console_cover", "joystick", "boxart",
        "wheel_shadow", "wheel_list", "pointer", "footer_frame",
    )

    BOTTOM_BAR_BG_COLOR = (15, 10, 8, 235)
    BOTTOM_COUNTER_COLOR = (255, 140, 0)
    BOTTOM_UPPERCASE_TITLE = True
    BOTTOM_INCLUDE_YEAR_MANU = False
    BOTTOM_LETTER_SPACING = 1.5
    BOTTOM_TITLE_W_RATIO = 0.65
    BOTTOM_COUNTER_W_RATIO = 0.25

# --- PLAYNEXUS STUDIO OVERRIDES START ---
STUDIO_ELEMENTS = [
    {'id': 'bg_image', 'name': 'Fondo del Layout', 'type': 'image', 'x': 0.0, 'y': 0.0, 'w': 1920.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 5, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 0.0, 1920.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'video_snap', 'name': 'Pantalla TV / Video Snap', 'type': 'video', 'x': 103.0, 'y': 211.0, 'w': 600.0, 'h': 464.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 10, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [103.0, 211.0, 600.0, 464.0], 'media_key': 'video', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scanlines_crt', 'name': 'Scanlines CRT (gtc-common)', 'type': 'effect', 'x': 103.0, 'y': 211.0, 'w': 600.0, 'h': 464.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 15, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [103.0, 211.0, 600.0, 464.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'tv_bezel', 'name': 'Televisor CRT (tv.png)', 'type': 'image', 'x': 56.0, 'y': 152.0, 'w': 720.0, 'h': 728.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 20, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [56.0, 152.0, 720.0, 728.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'avatar', 'name': 'Avatar / Personaje', 'type': 'image', 'x': 652.5, 'y': 115.3, 'w': 711.6, 'h': 453.7, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 25, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [584.0, 260.0, 676.0, 408.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'avatar_float', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'logo', 'name': 'Logotipo del Sistema', 'type': 'image', 'x': 44.0, 'y': 8.0, 'w': 792.0, 'h': 156.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 30, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [44.0, 8.0, 792.0, 156.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'logo_bounce', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'console', 'name': 'Consola (console.png)', 'type': 'image', 'x': 460.0, 'y': 672.0, 'w': 676.0, 'h': 352.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 35, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [460.0, 672.0, 676.0, 352.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'cartart', 'name': 'Cartucho / Disco', 'type': 'image', 'x': 856.3, 'y': 707.4, 'w': 132.5, 'h': 216.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 40, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [856.3, 707.4, 132.5, 216.0], 'media_key': 'cartart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'disc_rise', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'console_cover', 'name': 'Tapa de Consola (console_cover.png)', 'type': 'image', 'x': 464.0, 'y': 672.0, 'w': 656.0, 'h': 328.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 45, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [464.0, 672.0, 656.0, 328.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'joystick', 'name': 'Joystick / Mando (joystick.png)', 'type': 'image', 'x': 140.0, 'y': 740.0, 'w': 424.0, 'h': 320.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 50, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [140.0, 740.0, 424.0, 320.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'boxart', 'name': 'Carátula (Box Art)', 'type': 'image', 'x': -85.4, 'y': 647.7, 'w': 460.8, 'h': 410.4, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 55, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [28.8, 591.8, 460.8, 410.4], 'media_key': 'boxart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'boxart_slide_fade', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_shadow', 'name': 'Sombra de Ruleta (gtc-common)', 'type': 'image', 'x': 1336.0, 'y': 0.0, 'w': 584.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 60, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1336.0, 0.0, 584.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_list', 'name': 'Ruleta Curva (Wheel Conveyor)', 'type': 'wheel', 'x': 1208.0, 'y': 0.0, 'w': 680.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 65, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1208.0, 0.0, 680.0, 1080.0], 'media_key': 'wheel', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'pointer', 'name': 'Puntero de Ruleta', 'type': 'image', 'x': 1768.0, 'y': 424.0, 'w': 148.0, 'h': 264.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 70, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1768.0, 424.0, 148.0, 264.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'pointer_pulse', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'footer_frame', 'name': 'Barra Inferior (Footer)', 'type': 'image', 'x': 0.0, 'y': 999.0, 'w': 1920.0, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 75, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 999.0, 1920.0, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'title_text', 'name': 'Título del Juego (Footer)', 'type': 'text', 'x': 153.6, 'y': 999.0, 'w': 1190.4, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 80, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [153.6, 999.0, 1190.4, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'counter_text', 'name': 'Contador de Juegos (Footer)', 'type': 'text', 'x': 1344.0, 'y': 999.0, 'w': 499.2, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 85, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1344.0, 999.0, 499.2, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
]
STUDIO_EFFECTS = {'shader_preset': None, 'shader_target': 'tv_rect', 'particle_preset': None}
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
# --- PLAYNEXUS STUDIO OVERRIDES END ---
