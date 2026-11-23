"""
=============================================================================
Layout Declarativo: Sega Saturn
=============================================================================
"""
from pathlib import Path

from playnexus.ui.layouts.theme_base import ConsoleThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(ConsoleThemeLayout):
    LAYOUT_NAME = 'Sega Saturn'
    LAYOUT_DESCRIPTION = 'Layout temático de Sega Saturn fiel a Attract-Mode con CD giratorio y TV CRT'
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
        {'key': 'video', 'label': 'Video Snaps', 'extensions': ['.mp4', '.mkv', '.avi', '.webm'], 'required': True},
        {'key': 'wheel', 'label': 'Wheel Logos', 'extensions': ['.png', '.webp'], 'required': True},
        {'key': 'discart', 'label': 'Discos', 'extensions': ['.png', '.webp'], 'required': True},
        {'key': 'boxart', 'label': 'Box Art / Cajas', 'extensions': ['.png', '.jpg', '.jpeg', '.webp'], 'required': True},
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
    CONSOLE_COVER_IMAGE = None
    JOYSTICK_IMAGE = None
    AVATAR_IMAGE = LAYOUT_DIR / "avatar.png"
    LOGO_IMAGE = LAYOUT_DIR / "logo.png"
    DISCART_IMAGE = LAYOUT_DIR / "discart.png"
    CARTART_IMAGE = DISCART_IMAGE
    BOXART_IMAGE = None
    WHEEL_IMAGE = COMMON_DIR / "wheel" / "wheel.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers/default.png"

    # 4. Geometría y estilo del tema
    TV_RECT = (0.044, 0.235, 0.315, 0.430)
    DISC_RECT = (0.550, 0.600, 0.190, 0.300)
    CART_RECT = DISC_RECT
    DISC_END_Y = 0.600
    CART_END_Y = DISC_END_Y
    IS_CD = True
    CD_SPIN_SPEED = 1.152

    BOXART_X = 0.400
    BOXART_Y = 0.530
    BOXART_W = 0.165
    BOXART_H = 0.410
    BOXART_ANCHOR = "center"
    BOXART_SLIDE_OFFSET_X = -0.50

    BOTTOM_BAR_BG_COLOR = (8, 10, 20, 235)
    BOTTOM_COUNTER_COLOR = (180, 210, 255)
    BOTTOM_UPPERCASE_TITLE = True
    BOTTOM_INCLUDE_YEAR_MANU = False
    BOTTOM_LETTER_SPACING = 1.5
    BOTTOM_TITLE_W_RATIO = 0.65
    BOTTOM_COUNTER_W_RATIO = 0.25

# --- PLAYNEXUS STUDIO OVERRIDES START ---
STUDIO_ELEMENTS = [
    {'id': 'bg_image', 'name': 'Fondo del Layout', 'type': 'image', 'x': 0.0, 'y': 0.0, 'w': 1920.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 5, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 0.0, 1920.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'video_snap', 'name': 'Pantalla TV / Video Snap', 'type': 'video', 'x': 84.0, 'y': 253.0, 'w': 604.0, 'h': 464.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 10, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [84.0, 253.0, 604.0, 464.0], 'media_key': 'video', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scanlines_crt', 'name': 'Scanlines CRT (gtc-common)', 'type': 'effect', 'x': 84.0, 'y': 253.0, 'w': 604.0, 'h': 464.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 15, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [84.0, 253.0, 604.0, 464.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scratches', 'name': 'Reflejo Vidrio CRT (gtc-common)', 'type': 'effect', 'x': 84.0, 'y': 253.0, 'w': 604.0, 'h': 464.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 20, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [84.0, 253.0, 604.0, 464.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'tv_bezel', 'name': 'Televisor CRT (tv.png)', 'type': 'image', 'x': 32.0, 'y': 192.0, 'w': 724.0, 'h': 728.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 25, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [32.0, 192.0, 724.0, 728.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'avatar', 'name': 'Avatar / Personaje', 'type': 'image', 'x': 656.0, 'y': 132.0, 'w': 508.0, 'h': 644.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 30, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [656.0, 132.0, 508.0, 644.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'avatar_float', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'logo', 'name': 'Logotipo del Sistema', 'type': 'image', 'x': 48.0, 'y': 16.0, 'w': 792.0, 'h': 236.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 35, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [48.0, 16.0, 792.0, 236.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'logo_bounce', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'console', 'name': 'Consola (console.png)', 'type': 'image', 'x': 48.6, 'y': 696.4, 'w': 760.0, 'h': 376.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 40, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [168.0, 704.0, 760.0, 376.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'cartart', 'name': 'Cartucho / Disco', 'type': 'image', 'x': 1028.1, 'y': 668.3, 'w': 364.8, 'h': 324.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 45, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1056.0, 648.0, 364.8, 324.0], 'media_key': 'cartart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'disc_rise,disc_spin', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'boxart', 'name': 'Carátula (Box Art)', 'type': 'image', 'x': 717.2, 'y': 587.6, 'w': 316.8, 'h': 442.8, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 50, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [768.0, 572.4, 316.8, 442.8], 'media_key': 'boxart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'boxart_slide_fade', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_shadow', 'name': 'Sombra de Ruleta (gtc-common)', 'type': 'image', 'x': 1336.0, 'y': 0.0, 'w': 584.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 55, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1336.0, 0.0, 584.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_list', 'name': 'Ruleta Curva (Wheel Conveyor)', 'type': 'wheel', 'x': 1268.0, 'y': 0.0, 'w': 544.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 60, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1268.0, 0.0, 544.0, 1080.0], 'media_key': 'wheel', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'pointer', 'name': 'Puntero de Ruleta', 'type': 'image', 'x': 1768.0, 'y': 424.0, 'w': 152.0, 'h': 264.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 65, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1768.0, 424.0, 152.0, 264.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'pointer_pulse', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'footer_frame', 'name': 'Barra Inferior (Footer)', 'type': 'image', 'x': 0.0, 'y': 999.0, 'w': 1920.0, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 70, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 999.0, 1920.0, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'title_text', 'name': 'Título del Juego (Footer)', 'type': 'text', 'x': 153.6, 'y': 999.0, 'w': 1190.4, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 75, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [153.6, 999.0, 1190.4, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'counter_text', 'name': 'Contador de Juegos (Footer)', 'type': 'text', 'x': 1344.0, 'y': 999.0, 'w': 499.2, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 80, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1344.0, 999.0, 499.2, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
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
