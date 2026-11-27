"""
=============================================================================
Layout Declarativo: Super Nintendo Entertainment System
=============================================================================
"""
from pathlib import Path

from playnexus.ui.layouts.theme_base import ConsoleThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(ConsoleThemeLayout):
    LAYOUT_NAME = 'Super Nintendo Entertainment System'
    LAYOUT_DESCRIPTION = 'Layout temático de SNES fiel a Attract-Mode con TV CRT y cartucho insertándose'
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
        {'key': 'video', 'label': 'Video Snaps', 'extensions': ['.mp4', '.mkv', '.avi', '.webm'], 'required': True},
        {'key': 'wheel', 'label': 'Wheel Logos', 'extensions': ['.png', '.webp'], 'required': True},
        {'key': 'cartart', 'label': 'Cartuchos', 'extensions': ['.png', '.webp'], 'required': True},
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

    BKG_IMAGE = LAYOUT_DIR / "bkg.jpg"
    TV_IMAGE = LAYOUT_DIR / "tv.png"
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png"
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png"
    JOYSTICK_IMAGE = LAYOUT_DIR / "joystick.png"
    AVATAR_IMAGE = LAYOUT_DIR / "avatar.png"
    LOGO_IMAGE = LAYOUT_DIR / "logo.png"
    DISCART_IMAGE = None
    CARTART_IMAGE = LAYOUT_DIR / "cartart.png"
    BOXART_IMAGE = LAYOUT_DIR / "boxart.png"
    WHEEL_IMAGE = COMMON_DIR / "wheel" / "wheel.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers/default.png"

    # 4. Geometría y estilo del tema
    TV_RECT = (0.057, 0.230, 0.273, 0.390)
    CART_RECT = (0.362, 0.570, 0.148, 0.180)
    CART_END_Y = 0.570
    IS_CD = False
    AVATAR_Y_ADJUST = -30

    BOXART_X = 0.015
    BOXART_W = 0.240
    BOXART_H = 0.380
    BOXART_BOTTOM_Y = 0.928
    BOXART_ANCHOR = "bottom"
    BOXART_SLIDE_OFFSET_X = -0.30

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
    {'id': 'video_snap', 'name': 'Pantalla TV / Video Snap', 'type': 'video', 'x': 109.0, 'y': 248.0, 'w': 524.0, 'h': 421.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 10, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [109.0, 248.0, 524.0, 421.0], 'media_key': 'video', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scanlines_crt', 'name': 'Scanlines CRT (gtc-common)', 'type': 'effect', 'x': 109.0, 'y': 248.0, 'w': 524.0, 'h': 421.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 15, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [109.0, 248.0, 524.0, 421.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scratches', 'name': 'Reflejo Vidrio CRT (gtc-common)', 'type': 'effect', 'x': 109.0, 'y': 248.0, 'w': 524.0, 'h': 421.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 20, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [109.0, 248.0, 524.0, 421.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'tv_bezel', 'name': 'Televisor CRT (tv.png)', 'type': 'image', 'x': 16.0, 'y': 164.0, 'w': 852.0, 'h': 676.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 25, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [16.0, 164.0, 852.0, 676.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'avatar', 'name': 'Avatar / Personaje', 'type': 'image', 'x': 704.0, 'y': 176.0, 'w': 552.0, 'h': 576.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 30, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [704.0, 176.0, 552.0, 576.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'avatar_float', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'logo', 'name': 'Logotipo del Sistema', 'type': 'image', 'x': 72.0, 'y': 8.0, 'w': 708.0, 'h': 188.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 35, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [72.0, 8.0, 708.0, 188.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'logo_bounce', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'console', 'name': 'Consola (console.png)', 'type': 'image', 'x': 552.0, 'y': 644.0, 'w': 572.0, 'h': 392.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 40, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [552.0, 644.0, 572.0, 392.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'cartart', 'name': 'Cartucho / Disco', 'type': 'image', 'x': 695.0, 'y': 615.6, 'w': 284.2, 'h': 194.4, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 45, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [695.0, 615.6, 284.2, 194.4], 'media_key': 'cartart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'cart_drop', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'console_cover', 'name': 'Tapa de Consola (console_cover.png)', 'type': 'image', 'x': 596.0, 'y': 724.0, 'w': 512.0, 'h': 288.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 50, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [596.0, 724.0, 512.0, 288.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'joystick', 'name': 'Joystick / Mando (joystick.png)', 'type': 'image', 'x': 324.0, 'y': 748.0, 'w': 460.0, 'h': 304.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 55, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [324.0, 748.0, 460.0, 304.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'boxart', 'name': 'Carátula (Box Art)', 'type': 'image', 'x': 3.4, 'y': 668.1, 'w': 460.8, 'h': 410.4, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 60, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [28.8, 591.8, 460.8, 410.4], 'media_key': 'boxart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'boxart_slide_fade', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_shadow', 'name': 'Sombra de Ruleta (gtc-common)', 'type': 'image', 'x': 1336.0, 'y': 0.0, 'w': 584.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 65, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1336.0, 0.0, 584.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_list', 'name': 'Ruleta Curva (Wheel Conveyor)', 'type': 'wheel', 'x': 1328.0, 'y': 0.0, 'w': 544.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 70, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1328.0, 0.0, 544.0, 1080.0], 'media_key': 'wheel', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'pointer', 'name': 'Puntero de Ruleta', 'type': 'image', 'x': 1768.0, 'y': 424.0, 'w': 148.0, 'h': 264.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 75, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1768.0, 424.0, 148.0, 264.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'pointer_pulse', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'footer_frame', 'name': 'Barra Inferior (Footer)', 'type': 'image', 'x': 0.0, 'y': 999.0, 'w': 1920.0, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 80, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 999.0, 1920.0, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'title_text', 'name': 'Título del Juego (Footer)', 'type': 'text', 'x': 153.6, 'y': 999.0, 'w': 1248.0, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 85, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [153.6, 999.0, 1248.0, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'counter_text', 'name': 'Contador de Juegos (Footer)', 'type': 'text', 'x': 1344.0, 'y': 999.0, 'w': 480.0, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 90, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1344.0, 999.0, 480.0, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
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
