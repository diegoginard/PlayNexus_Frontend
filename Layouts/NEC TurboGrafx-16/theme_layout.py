import playnexus
"""
=============================================================================
Layout Autónomo y Configuración: NEC TurboGrafx-16
=============================================================================
Este archivo maneja en su totalidad la configuración, métricas, recursos,
reproducción de video, animaciones de entrada, inserción de tarjeta HuCard
y renderizado completo del sistema NEC TurboGrafx-16 para PlayNexus.
"""
import os
import time
import math
import random
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QUrl, QRect, QPoint, QTimer, QRectF
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPixmap, QIcon, QBrush, QPen,
    QFontDatabase, QTransform, QImage
)
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QSoundEffect

from playnexus.ui.layouts.base import BaseLayout, WheelPreloadWorker
from playnexus.services.media import resolve_game_media
from playnexus.services.controls import (
    matches_action, ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_PAGE_UP,
    ACTION_PAGE_DOWN, ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD,
    ACTION_SELECT, ACTION_MUTE, ACTION_NAV_BACK
)

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(BaseLayout):
    LAYOUT_NAME = "NEC TurboGrafx-16"
    LAYOUT_DESCRIPTION = "Layout temático de NEC TurboGrafx-16 con inserción de tarjeta HuCard, TV CRT y nave espacial animada"

    CANONICAL_W = 1920
    CANONICAL_H = 1080

    # -------------------------------------------------------------------------
    # REQUERIMIENTOS DE MEDIOS PARA ESTE LAYOUT (LEÍDOS DIRECTAMENTE POR EL SISTEMA)
    # -------------------------------------------------------------------------
    MEDIA_REQUIREMENTS = [
        {
            "key": "video",
            "label": "Video Snaps",
            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
            "required": True
        },
        {
            "key": "wheel",
            "label": "Wheel Logos",
            "extensions": [".png", ".webp"],
            "required": True
        },
        {
            "key": "cartart",
            "label": "Tarjetas HuCard",
            "extensions": [".png", ".webp"],
            "required": True
        },
        {
            "key": "boxart",
            "label": "Box Art / Carátulas",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": False
        }
    ]

    # Recursos compartidos desde gtc-common
    WHEEL_SHADOW_IMAGE = COMMON_DIR / "wheel" / "wheel_shadow.png"
    COMMON_WHEEL_ART   = COMMON_DIR / "art" / "wheel_art.png"
    COMMON_FRAME       = COMMON_DIR / "art" / "frame.png"
    STATIC_VIDEO       = COMMON_DIR / "videos" / "static.mp4"
    SOUND_NAV          = COMMON_DIR / "sounds" / "joystick.mp3"
    SOUND_SELECT       = COMMON_DIR / "sounds" / "Mame_coin.mp3"
    SCRATCHES_IMAGE    = COMMON_DIR / "art" / "arcade" / "scratched_cover.png"

    # -------------------------------------------------------------------------
    # RECURSOS LOCALES PROPIOS DEL LAYOUT
    # -------------------------------------------------------------------------
    BKG_IMAGE = LAYOUT_DIR / "bg.jpg" 
    TV_IMAGE = LAYOUT_DIR / "tv.png"
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png"
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png"
    JOYSTICK_IMAGE = LAYOUT_DIR / "joystick.png"
    AVATAR_IMAGE = LAYOUT_DIR / "spaceship.png"
    LOGO_IMAGE = LAYOUT_DIR / "logo.png"
    CARTART_IMAGE = LAYOUT_DIR / "cartart.png"
    BOXART_IMAGE = None
    WHEEL_IMAGE = LAYOUT_DIR / "wheel.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers" / "default.png"
    # Tipografías del tema (declaradas al inicio para modificarlas fácilmente)
    FONT_TITLE_FILE = "BebasNeue Bold.otf"    # Fuente para títulos destacados del juego
    FONT_MAIN_FILE  = "Handel Gothic BT.ttf"   # Fuente para contadores, año, desarrollador e info general
    FONT_FILES = [FONT_TITLE_FILE, FONT_MAIN_FILE]

    # -------------------------------------------------------------------------
    # CONFIGURACIÓN GEOMÉTRICA DE NEC TURBOGRAFX-16
    # -------------------------------------------------------------------------
    # Pantalla CRT TV: (x, y, w, h) en ratios de pantalla (1920x1080)
    TV_RECT = (0.054, 0.196, 0.313, 0.430)

    # Tarjeta HuCard insertándose verticalmente desde abajo hacia la ranura frontal de la consola
    CART_RECT = (0.446, 0.655, 0.069, 0.200)
    CART_START_X = 0.480
    CART_END_X = 0.446
    CART_START_Y = 1.100
    CART_END_Y = 0.655
    IS_CD = False

    # Carátula (Boxart) anclada abajo a la izquierda debajo de la TV CRT
    BOXART_X = 0.015
    BOXART_W = 0.240
    BOXART_H = 0.380
    BOXART_BOTTOM_Y = 0.928
    BOXART_ANCHOR = "bottom"

    # Logotipo del sistema
    LOGO_SCALE = 1.0

    # Escala y posición del Avatar (Nave espacial)
    AVATAR_SCALE = 1.0
    AVATAR_X = 0.0
    AVATAR_Y = 0.0
    AVATAR_Y_ADJUST = 0

    # Curva interactiva de la ruleta (Conveyor Wheel de 14 nodos interpolados a 60 FPS)
    CONVEYOR_X = [0.89, 0.85, 0.83, 0.80, 0.77, 0.74, 0.71, 0.625, 0.71, 0.74, 0.77, 0.80, 0.83, 0.89]
    CONVEYOR_Y = [-0.34, -0.22, -0.105, 0.00, 0.105, 0.215, 0.325, 0.421, 0.59, 0.70, 0.81, 0.915, 0.99, 1.12]
    CONVEYOR_W = [0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.30, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18]
    CONVEYOR_H = [0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.186, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
    CONVEYOR_R = [35.0, 30.0, 25.0, 20.0, 15.0, 10.0, 5.0, 0.0, -10.0, -15.0, -20.0, -25.0, -30.0, -35.0]
    CONVEYOR_A = [0, 20, 35, 60, 90, 125, 160, 255, 160, 125, 90, 60, 35, 0]

    @classmethod
    def _resolve_file(cls, rel_path: str | None) -> str | None:
        """Resuelve una ruta relativa dentro de la carpeta propia del layout."""
        if not rel_path:
            return None
        p = LAYOUT_DIR / rel_path
        if p.is_file():
            return str(p)
        cand = LAYOUT_DIR / Path(rel_path).name
        if cand.is_file():
            return str(cand)
        cand_ptr = LAYOUT_DIR / "pointers" / Path(rel_path).name
        if cand_ptr.is_file():
            return str(cand_ptr)
        return None

    def __init__(self, theme_name: str = "NEC TurboGrafx-16", parent=None):
        """Inicializa los componentes internos, estructuras de datos y temporizadores del objeto."""
        super().__init__(parent)
        self.theme_name = theme_name
        self.layout_dir = LAYOUT_DIR

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.selected_index = 0
        self.current_media = {}
        self._wheel_pixmaps = {}
        self._current_box_pixmap = None
        self._current_cart_pixmap = None

        # Worker en segundo plano para pre-carga asíncrona de logotipos de rueda
        self._wheel_worker = WheelPreloadWorker(self)
        self._wheel_worker.wheel_loaded.connect(self._on_wheel_image_loaded)
        self._wheel_worker.start()

        self._player_initialized = False
        self.player = None
        self.audio_output = None
        self.video_sink = None
        self._media_muted = False
        self.db = None
        self._current_video_image: QImage | None = None

        # Efectos de sonido directos desde gtc-common
        self._sound_effect = QSoundEffect(self)
        self._sound_effect.setVolume(0.4)
        if self.SOUND_NAV.is_file():
            self._sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_NAV)))

        self._select_sound_effect = QSoundEffect(self)
        self._select_sound_effect.setVolume(0.5)
        if self.SOUND_SELECT.is_file():
            self._select_sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_SELECT)))

        # Precargar imágenes asignadas directamente en este layout
        bkg_cand = str(self.BKG_IMAGE)
        self._pix_bkg = self._load_pixmap(bkg_cand)
        self._pix_tv = self._load_pixmap(str(self.TV_IMAGE))
        self._pix_console = self._load_pixmap(str(self.CONSOLE_IMAGE))
        self._pix_console_cover = self._load_pixmap(str(self.CONSOLE_COVER_IMAGE) if self.CONSOLE_COVER_IMAGE else None)
        self._pix_joystick = self._load_pixmap(str(self.JOYSTICK_IMAGE) if self.JOYSTICK_IMAGE else None)

        self._pix_avatar = self._load_pixmap(str(self.AVATAR_IMAGE))

        self._pix_logo = self._load_pixmap(str(self.LOGO_IMAGE))
        self._pix_cartart_frame = self._load_pixmap(str(self.CARTART_IMAGE))
        self._pix_boxart_frame = self._load_pixmap(str(self.BOXART_IMAGE) if self.BOXART_IMAGE else None)

        # Recursos compartidos directos desde gtc-common
        self._pix_scanlines = None
        self._pix_wheel_art = self._load_pixmap(str(self.COMMON_WHEEL_ART))
        self._pix_frame = self._load_pixmap(str(self.COMMON_FRAME))
        self._pix_scratches = self._load_pixmap(str(self.SCRATCHES_IMAGE))
        self._static_video_path = str(self.STATIC_VIDEO) if self.STATIC_VIDEO.is_file() else None

        # Sombra de ruleta directa desde gtc-common/wheel
        self._pix_wheel_shadow = self._load_pixmap(str(self.WHEEL_SHADOW_IMAGE)) if self.WHEEL_SHADOW_IMAGE.is_file() else None

        # Puntero animado de la ruleta asignado en este layout
        pointer_path = str(self.POINTER_IMAGE)
        self._pix_pointer = self._load_pixmap(pointer_path)

        # Diccionario theme_info autogenerado internamente por el layout
        self.theme_info = {
            "name": self.theme_name,
            "folder": str(LAYOUT_DIR),
            "bkg": str(self.BKG_IMAGE),
            "tv": str(self.TV_IMAGE),
            "console": str(self.CONSOLE_IMAGE),
            "console_cover": str(self.CONSOLE_COVER_IMAGE) if self.CONSOLE_COVER_IMAGE else None,
            "joystick": str(self.JOYSTICK_IMAGE) if self.JOYSTICK_IMAGE else None,
            "avatar": str(self.AVATAR_IMAGE),
            "character": str(self.AVATAR_IMAGE),
            "logo": str(self.LOGO_IMAGE),
            "cartart": str(self.CARTART_IMAGE),
            "boxart": None,
            "wheel": str(self.WHEEL_IMAGE),
            "pointer": pointer_path,
        }

        self._pointer_rest_x_ratio = 0.905
        self._pointer_pulse_x_ratio = 0.880
        self._pointer_current_x_ratio = self._pointer_rest_x_ratio
        self._pointer_anim_tick = 0

        self._pointer_anim_timer = QTimer(self)
        self._pointer_anim_timer.timeout.connect(self._on_pointer_tick)
        if self._pix_pointer:
            self._pointer_anim_timer.start(16)

        # Tipografías
        self._font_main = "sans-serif"
        self._font_bebas = "sans-serif"
        self._load_theme_fonts()

        # Animación de giro suave de la ruleta
        self._wheel_spin_offset = 0.0
        self._wheel_spin_timer = QTimer(self)
        self._wheel_spin_timer.setTimerType(Qt.PreciseTimer)
        self._wheel_spin_timer.timeout.connect(self._on_wheel_spin_tick)

        # Animación del Avatar
        self._avatar_anim_time = 0.0
        self._avatar_offset_x = 0.0
        self._avatar_offset_y = 0.0
        self._avatar_bounce_timer = QTimer(self)
        self._avatar_bounce_timer.timeout.connect(self._on_avatar_bounce_tick)
        self._avatar_bounce_timer.start(20)

        # Animación de entrada de la HuCard (deslizándose desde abajo hacia la ranura frontal)
        self._cart_anim_timer = QTimer(self)
        self._cart_anim_timer.timeout.connect(self._on_cart_anim_tick)
        self._cart_anim_elapsed = 0
        self._cart_anim_duration = 550
        self._cart_start_x_ratio = getattr(self, "CART_START_X", self.CART_RECT[0])
        self._cart_end_x_ratio = getattr(self, "CART_END_X", self.CART_RECT[0])
        self._cart_start_y_ratio = self.CART_START_Y
        self._cart_end_y_ratio = self.CART_END_Y
        self._cart_current_x_ratio = self._cart_end_x_ratio
        self._cart_current_y_ratio = self._cart_end_y_ratio

        # Animación de caída del logo superior
        self._logo_anim_timer = QTimer(self)
        self._logo_anim_timer.timeout.connect(self._on_logo_anim_tick)
        self._logo_anim_elapsed = 0
        self._logo_anim_duration = 1200
        self._logo_current_y_offset_ratio = 0.0

        # Animación de entrada de la carátula (boxart)
        self._boxart_anim_timer = QTimer(self)
        self._boxart_anim_timer.timeout.connect(self._on_boxart_anim_tick)
        self._boxart_anim_elapsed = 0
        self._boxart_anim_duration = 450
        self._boxart_current_x_offset_ratio = 0.0
        self._boxart_alpha = 1.0

        # Reproducción diferida (debounced) del video snap para no saturar Media Foundation
        self._video_debounce_timer = QTimer(self)
        self._video_debounce_timer.setSingleShot(True)
        self._video_debounce_timer.timeout.connect(self._play_debounced_video)
        self._pending_video_path = None

        self._start_logo_animation()

    def _load_pixmap(self, path: str | None) -> QPixmap | None:
        """Carga un QPixmap desde el disco de forma segura, retornando None si el archivo es inaccesible o nulo."""
        if path and os.path.isfile(path):
            pix = QPixmap(path)
            return pix if not pix.isNull() else None
        return None

    # -------------------------------------------------------------------------
    # RECURSOS TIPOGRÁFICOS Y EFECTOS DE SONIDO
    # -------------------------------------------------------------------------

    def _load_font_family(self, font_name: str | Path | None) -> str:
        """Carga una fuente desde el archivo especificado en el layout y retorna su nombre de familia."""
        if not font_name:
            return "sans-serif"
        font_path = LAYOUT_DIR / Path(font_name).name
        if font_path.is_file():
            fid = QFontDatabase.addApplicationFont(str(font_path))
            if fid != -1:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    return families[0]
        return "sans-serif"

    def _load_theme_fonts(self):
        """Carga automáticamente las 2 fuentes declaradas en la cabecera (título e información principal)."""
        self._font_bebas = self._load_font_family(getattr(self, "FONT_TITLE_FILE", None))
        self._font_title = self._font_bebas
        self._font_main  = self._load_font_family(getattr(self, "FONT_MAIN_FILE", None))

    def _play_wheel_sound(self):
        """Reproduce el efecto de sonido de navegación si los sonidos no están silenciados."""
        if not self._media_muted and self._sound_effect and self._sound_effect.isLoaded():
            self._sound_effect.play()

    def _play_select_sound(self):
        """Reproduce el efecto de confirmación sonora al presionar un elemento en la ruleta."""
        if not self._media_muted and self._select_sound_effect and self._select_sound_effect.isLoaded():
            self._select_sound_effect.play()

    def _can_activate_game(self) -> bool:
        """Determina si las animaciones de la ruleta y carátula han culminado para permitir lanzar el juego."""
        now = time.perf_counter()
        if now - getattr(self, "_last_launch_time", 0.0) < 0.8:
            return False
        self._last_launch_time = now
        return True

    # -------------------------------------------------------------------------
    # ANIMACIONES Y TICS DE TEMPORIZADORES
    # -------------------------------------------------------------------------

    def _on_avatar_bounce_tick(self):
        """Aplica un movimiento sinusoidal oscilatorio a la nave espacial simulando flotación."""
        self._avatar_anim_time += 0.04
        self._avatar_offset_y = math.sin(self._avatar_anim_time) * 12.0
        self._avatar_offset_x = math.cos(self._avatar_anim_time * 0.5) * 4.0
        self.update()

    def _on_pointer_tick(self):
        """Genera una animación de respiración y amortiguación para el puntero de selección."""
        self._pointer_anim_tick += 1
        if abs(self._pointer_current_x_ratio - self._pointer_rest_x_ratio) > 0.0005:
            self._pointer_current_x_ratio += (self._pointer_rest_x_ratio - self._pointer_current_x_ratio) * 0.15
            self.update()

    def _navigate_steps(self, delta_steps: int):
        """Avanza o retrocede N posiciones en la lista de juegos y dispara la física de la ruleta."""
        n = len(self.games)
        if n == 0 or delta_steps == 0:
            return

        self._preload_direction(delta_steps)

        self.selected_index = (self.selected_index + delta_steps) % n
        self._wheel_spin_offset += float(delta_steps)
        self._wheel_spin_offset = max(-5.0, min(5.0, self._wheel_spin_offset))
        self._pointer_current_x_ratio = self._pointer_pulse_x_ratio

        self._play_wheel_sound()
        self._update_current_selection()
        if not self._wheel_spin_timer.isActive():
            self._wheel_spin_timer.start(16)
        self.update()

    def _on_wheel_spin_tick(self):
        """Interpola la posición continua de la ruleta hacia el objetivo a 60 FPS con suavizado exponencial."""
        self._wheel_spin_offset *= 0.72
        if abs(self._wheel_spin_offset) < 0.015:
            self._wheel_spin_offset = 0.0
            self._wheel_spin_timer.stop()
        self.update()

    def _on_cart_anim_tick(self):
        """Ejecuta la animación de inserción física de la tarjeta HuCard deslizándose desde abajo hacia la ranura."""
        dt = 16
        self._cart_anim_elapsed += dt
        t = min(self._cart_anim_elapsed / self._cart_anim_duration, 1.0)
        ease = 1.0 - (1.0 - t) ** 3
        self._cart_current_x_ratio = (
            self._cart_start_x_ratio
            + (self._cart_end_x_ratio - self._cart_start_x_ratio) * ease
        )
        self._cart_current_y_ratio = (
            self._cart_start_y_ratio
            + (self._cart_end_y_ratio - self._cart_start_y_ratio) * ease
        )
        self.update()
        if t >= 1.0:
            self._cart_anim_timer.stop()
            self._cart_current_x_ratio = self._cart_end_x_ratio
            self._cart_current_y_ratio = self._cart_end_y_ratio

    def _start_cart_animation(self):
        """Reinicia la cinemática de inserción de la tarjeta HuCard para el juego actual."""
        self._cart_anim_elapsed = 0
        self._cart_current_x_ratio = self._cart_start_x_ratio
        self._cart_current_y_ratio = self._cart_start_y_ratio
        self._cart_anim_timer.start(16)

    def _on_logo_anim_tick(self):
        """Anima la escala y opacidad de entrada del logotipo del juego o sistema en pantalla."""
        dt = 16
        self._logo_anim_elapsed += dt
        t = min(self._logo_anim_elapsed / self._logo_anim_duration, 1.0)
        p = 0.3
        s = p / 4.0
        if t == 0.0:
            ease = 0.0
        elif t >= 1.0:
            ease = 1.0
        else:
            ease = math.pow(2.0, -10.0 * t) * math.sin((t - s) * (2.0 * math.pi) / p) + 1.0

        start_offset = -0.50
        self._logo_current_y_offset_ratio = start_offset * (1.0 - ease)
        self.update()
        if t >= 1.0:
            self._logo_anim_timer.stop()
            self._logo_current_y_offset_ratio = 0.0

    def _start_logo_animation(self):
        """Dispara la animación de revelado del logotipo."""
        self._logo_anim_elapsed = 0
        self._logo_current_y_offset_ratio = -0.50
        self._logo_anim_timer.start(16)

    def _on_boxart_anim_tick(self):
        """Interpola la posición horizontal y opacidad de la carátula hacia su posición final."""
        dt = 16
        self._boxart_anim_elapsed += dt
        t = min(self._boxart_anim_elapsed / self._boxart_anim_duration, 1.0)
        ease = 1.0 - (1.0 - t) ** 2
        start_x_offset = -0.30
        self._boxart_current_x_offset_ratio = start_x_offset * (1.0 - ease)
        self._boxart_alpha = ease
        self.update()
        if t >= 1.0:
            self._boxart_anim_timer.stop()
            self._boxart_current_x_offset_ratio = 0.0
            self._boxart_alpha = 1.0

    def _start_boxart_animation(self):
        """Reinicia la transición animada de entrada de la carátula del juego seleccionado."""
        self._boxart_anim_elapsed = 0
        self._boxart_current_x_offset_ratio = -0.30
        self._boxart_alpha = 0.0
        self._boxart_anim_timer.start(16)

    def _ensure_player_initialized(self):
        """Inicializa de forma perezosa el reproductor multimedia."""
        if self._player_initialized:
            return
        self._player_initialized = True
        self._want_video_playing = False
        self._video_watchdog_timer = QTimer(self)
        self._video_watchdog_timer.setSingleShot(True)
        self._video_watchdog_timer.setInterval(1200)
        self._video_watchdog_timer.timeout.connect(self._on_video_watchdog)

        self.player = QMediaPlayer(self)
        self.player.setLoops(QMediaPlayer.Infinite)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setMuted(self._media_muted)
        self.audio_output.setVolume(0.0 if self._media_muted else 0.8)

        self.video_sink = QVideoSink(self)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_player_error)

    def _on_media_status_changed(self, status):
        """Supervisa el estado del reproductor y garantiza el bucle infinito del video snap."""
        if not self.player:
            return
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferingMedia, QMediaPlayer.BufferedMedia):
            if getattr(self, "_want_video_playing", False) and self.isVisible():
                if self.audio_output:
                    self.audio_output.setMuted(self._media_muted)
                    self.audio_output.setVolume(0.0 if self._media_muted else 0.8)
                if self.player.playbackState() != QMediaPlayer.PlayingState:
                    self.player.play()
            else:
                if self.audio_output:
                    try:
                        self.audio_output.setMuted(True)
                        self.audio_output.setVolume(0.0)
                    except Exception:
                        pass
                if status == QMediaPlayer.BufferedMedia:
                    self.player.pause()
        elif status == QMediaPlayer.EndOfMedia:
            if getattr(self, "_want_video_playing", False) and self.isVisible():
                self.player.setPosition(0)
                self.player.play()

    def _on_video_watchdog(self):
        """Temporizador de seguridad que verifica que el video no se quede congelado tras navegar."""
        if not getattr(self, "_want_video_playing", False) or not getattr(self, "_pending_video_path", None) or not self.isVisible():
            return
        if not os.path.isfile(self._pending_video_path) or not self.player:
            return
        if self.player.mediaStatus() == QMediaPlayer.LoadingMedia:
            return
        if self._current_video_image is None or self.player.playbackState() != QMediaPlayer.PlayingState:
            try:
                src_url = QUrl.fromLocalFile(self._pending_video_path)
                if self.player.source() != src_url:
                    self.player.setSource(src_url)
                self.player.play()
            except Exception:
                pass

    def _on_video_frame_changed(self, frame):
        """Recibe el frame decodificado desde QVideoSink y solicita el repintado de la TV CRT."""
        if frame.isValid() and getattr(self, "_want_video_playing", True) and self.player:
            p_path = getattr(self, "_pending_video_path", None)
            if p_path and self.player.source() != QUrl.fromLocalFile(p_path):
                return
            if hasattr(self, "_wheel_spin_timer") and self._wheel_spin_timer.isActive() and self._current_video_image is not None:
                return
            now = time.perf_counter()
            if now - getattr(self, "_last_video_frame_time", 0.0) < 0.033:
                return
            self._last_video_frame_time = now
            img = frame.toImage()
            if not img.isNull():
                self._current_video_image = img
                self.update()

    def _on_player_error(self, error, error_string=""):
        """Maneja errores de decodificación o códecs de video reintentando la carga."""
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self._current_video_image = None

    def set_db(self, db):
        """Asocia la base de datos de PlayNexus para consultas de metadatos o emuladores."""
        self.db = db
        if self.games and 0 <= self.selected_index < len(self.games):
            self._update_current_selection()

    # -------------------------------------------------------------------------
    # GESTIÓN DE JUEGOS Y PRECARGA ASÍNCRONA
    # -------------------------------------------------------------------------

    def set_games(self, games: list):
        """Establece la colección de juegos a mostrar, reinicia la posición y dispara la precarga de artes."""
        self.games = [dict(g) if hasattr(g, "keys") else g for g in games]
        self.selected_index = 0
        self._wheel_pixmaps.clear()
        if hasattr(self, '_wheel_worker') and self._wheel_worker:
            self._wheel_worker.clear()
        if self.games:
            self._update_current_selection()
            self._start_cart_animation()
            self._start_boxart_animation()
            self._start_logo_animation()
            self._preload_around(0)
        else:
            self.current_media = {}
            self._current_box_pixmap = None
            self._current_cart_pixmap = None
            if self.player:
                try:
                    self.player.stop()
                    self.player.setSource(QUrl())
                except Exception:
                    pass
            self._current_video_image = None
        self.update()

    def render_games(self):
        """Solicita la actualización y re-renderizado de los elementos gráficos en pantalla."""
        self.update()

    def select_game_by_id(self, game_id: int):
        """Selecciona visualmente un juego por su identificador numérico único."""
        for i, g in enumerate(self.games):
            if g.get("id") == game_id:
                if self.selected_index != i:
                    self.selected_index = i
                    self._update_current_selection()
                    self._start_cart_animation()
                    self._start_boxart_animation()
                    self._preload_around(i)
                    self.update()
                break

    def get_selected_game_id(self) -> int | None:
        """Retorna el identificador del juego actualmente seleccionado en la ruleta."""
        if self.games and 0 <= self.selected_index < len(self.games):
            return self.games[self.selected_index].get("id")
        return None

    def pause_media(self):
        """Pausa el video y silencia el audio mientras el emulador está en ejecución."""
        self._want_video_playing = False
        if hasattr(self, "_video_debounce_timer"):
            self._video_debounce_timer.stop()
        if hasattr(self, "_video_watchdog_timer"):
            self._video_watchdog_timer.stop()
        if self.audio_output:
            try:
                self.audio_output.setMuted(True)
                self.audio_output.setVolume(0.0)
            except Exception:
                pass
        if self.player:
            try:
                self.player.pause()
            except Exception:
                pass
        self.update()

    def resume_media(self):
        """Reanuda la reproducción de video y audio cuando el emulador finaliza."""
        self._want_video_playing = True
        if self.player and getattr(self, "_pending_video_path", None) and os.path.isfile(self._pending_video_path):
            try:
                if self.audio_output:
                    self.audio_output.setMuted(self._media_muted)
                    self.audio_output.setVolume(0.0 if self._media_muted else 0.8)
                self.player.play()
            except Exception:
                pass
        self.update()

    def stop_media(self):
        """Detiene completamente la reproducción de video y audio liberando recursos del sistema."""
        self._want_video_playing = False
        self._pending_video_path = None
        if hasattr(self, '_video_debounce_timer'):
            self._video_debounce_timer.stop()
        if hasattr(self, '_video_watchdog_timer'):
            self._video_watchdog_timer.stop()
        if hasattr(self, 'audio_output') and self.audio_output:
            try:
                self.audio_output.setMuted(True)
                self.audio_output.setVolume(0.0)
            except Exception:
                pass
        if hasattr(self, 'player') and self.player:
            try:
                self.player.stop()
                self.player.setSource(QUrl())
            except Exception:
                pass
        self._current_video_image = None
        self.update()

    # -------------------------------------------------------------------------
    # CONTROL DE CICLO DE VIDA Y RECURSOS DEL SISTEMA
    # -------------------------------------------------------------------------

    def set_media_muted(self, muted: bool):
        """Silencia o reactiva el audio de los videos y efectos sonoros."""
        self._media_muted = muted
        for eff_name in ("_sound_effect", "_select_sound_effect"):
            if hasattr(self, eff_name):
                eff = getattr(self, eff_name)
                if eff:
                    try:
                        eff.setMuted(muted)
                        eff.setVolume(0.0 if muted else 0.5)
                    except Exception:
                        pass
        if self.audio_output:
            self.audio_output.setMuted(muted)
            self.audio_output.setVolume(0.0 if muted else 0.8)

    def set_muted(self, muted: bool):
        """Compatibilidad con API de mute."""
        self.set_media_muted(muted)

    def is_muted(self) -> bool:
        """Indica si el sonido se encuentra actualmente silenciado."""
        return self._media_muted

    def _update_current_selection(self):
        """Actualiza todos los elementos artísticos, videos y animaciones para el juego enfocado."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self.current_media = {}
            if hasattr(self, "_video_debounce_timer"):
                self._video_debounce_timer.stop()
            self._pending_video_path = None
            if self.player:
                try:
                    self.player.stop()
                    self.player.setSource(QUrl())
                except Exception:
                    pass
            self._current_video_image = None
            return

        game = self.games[self.selected_index]
        gid = game.get("id")
        self.current_game_id = gid
        if gid is not None:
            self.game_selected.emit(gid)

        self.current_media = resolve_game_media(game)
        if not hasattr(self, "_art_pix_cache"):
            self._art_pix_cache = {}
        box_file = self.current_media.get("boxart") or game.get("cover_path") or game.get("boxart_path")
        self._pending_box_file = box_file if (box_file and os.path.isfile(box_file)) else None

        cart_file = self.current_media.get("cartart") or game.get("cartart_path")
        self._pending_cart_file = cart_file if (cart_file and os.path.isfile(cart_file)) else None

        self._load_pending_art()

        self._start_cart_animation()
        self._start_boxart_animation()

        snap_video = self.current_media.get("snap")
        video_to_play = None
        if snap_video and os.path.isfile(snap_video):
            video_to_play = snap_video
        elif self._static_video_path and os.path.isfile(self._static_video_path):
            video_to_play = self._static_video_path

        self._pending_video_path = video_to_play
        self._want_video_playing = False
        if hasattr(self, "_video_watchdog_timer"):
            self._video_watchdog_timer.stop()
        if self.audio_output:
            self.audio_output.setVolume(0.0)
        if self.player and self.player.mediaStatus() == QMediaPlayer.BufferedMedia:
            try:
                self.player.pause()
            except Exception:
                pass
        self._current_video_image = None
        if hasattr(self, "_video_debounce_timer"):
            self._video_debounce_timer.stop()
            self._video_debounce_timer.start(350)
        else:
            self._play_debounced_video()

    def _load_pending_art(self):
        """Carga en memoria las imágenes de carátula y HuCard sin bloquear el hilo principal."""
        if not hasattr(self, "_art_pix_cache"):
            self._art_pix_cache = {}
        if len(self._art_pix_cache) > 100:
            self._art_pix_cache.clear()
        b_file = getattr(self, "_pending_box_file", None)
        if b_file and os.path.isfile(b_file):
            if b_file not in self._art_pix_cache:
                p = QPixmap(b_file)
                self._art_pix_cache[b_file] = p if not p.isNull() else None
            self._current_box_pixmap = self._art_pix_cache.get(b_file)
        else:
            self._current_box_pixmap = None

        c_file = getattr(self, "_pending_cart_file", None)
        if c_file and os.path.isfile(c_file):
            if c_file not in self._art_pix_cache:
                p = QPixmap(c_file)
                self._art_pix_cache[c_file] = p if not p.isNull() else None
            self._current_cart_pixmap = self._art_pix_cache.get(c_file)
        else:
            self._current_cart_pixmap = None

    def _play_debounced_video(self):
        """Reproduce el video snap una vez que la ruleta se ha detenido para maximizar la fluidez."""
        if not self.isVisible():
            self._pending_video_play_on_show = True
            return
        self._pending_video_play_on_show = False
        self._load_pending_art()
        self.update()
        video_to_play = getattr(self, "_pending_video_path", None)
        self._ensure_player_initialized()
        if video_to_play and os.path.isfile(video_to_play):
            self._want_video_playing = True
            if self.audio_output:
                self.audio_output.setMuted(self._media_muted)
                self.audio_output.setVolume(0.0 if self._media_muted else 0.8)
            source_url = QUrl.fromLocalFile(video_to_play)
            try:
                if self.player.source() == source_url:
                    self.player.setPosition(0)
                else:
                    self.player.setSource(source_url)
                self.player.play()
                self._video_watchdog_timer.start()
            except Exception:
                pass
        else:
            self._want_video_playing = False
            if self.audio_output:
                try:
                    self.audio_output.setMuted(True)
                    self.audio_output.setVolume(0.0)
                except Exception:
                    pass
            if self.player:
                try:
                    self.player.stop()
                    self.player.setSource(QUrl())
                except Exception:
                    pass
            self._current_video_image = None
            self.update()

    def _on_wheel_image_loaded(self, gid: int, img: QImage):
        """Callback asíncrono disparado cuando un logotipo de ruleta ha terminado de escalarse en segundo plano."""
        if not img.isNull():
            pix = QPixmap.fromImage(img)
            self._wheel_pixmaps[gid] = pix
            if len(self._wheel_pixmaps) > 600:
                for old_gid in list(self._wheel_pixmaps.keys()):
                    if not self._is_game_visible_in_wheel(old_gid):
                        del self._wheel_pixmaps[old_gid]
                        break
            if self._is_game_visible_in_wheel(gid):
                self.update()

    def _is_game_visible_in_wheel(self, game_id: int) -> bool:
        """Comprueba si un juego se encuentra actualmente dentro del campo visual visible de la ruleta curva."""
        if not self.games:
            return False
        n = len(self.games)
        for offset in (-6, 6, -5, 5, -4, 4, -3, 3, -2, 2, -1, 1, 0):
            idx = (self.selected_index + offset) % n
            if self.games[idx].get("id") == game_id:
                return True
        return False

    def _preload_around(self, center_idx: int):
        """Encola en segundo plano la precarga de los logotipos vecinos al índice actual."""
        if not self.games or not hasattr(self, "_wheel_worker") or not self._wheel_worker:
            return
        n = len(self.games)
        window = [
            self.games[(center_idx + i) % n]
            for i in range(-6, 35)
            if self.games[(center_idx + i) % n].get("id") not in self._wheel_pixmaps
        ]
        if window:
            self._wheel_worker.queue_games(window)
        if not hasattr(self, "_art_pix_cache"):
            self._art_pix_cache = {}
        for off in (-2, -1, 1, 2, 3):
            gm = self.games[(center_idx + off) % n]
            gmedia = resolve_game_media(gm)
            bf = gmedia.get("boxart") or gm.get("cover_path")
            if bf and bf not in self._art_pix_cache and os.path.isfile(bf):
                bp = QPixmap(bf)
                if not bp.isNull():
                    self._art_pix_cache[bf] = bp
            cf = gmedia.get("cartart")
            if cf and cf not in self._art_pix_cache and os.path.isfile(cf):
                cp = QPixmap(cf)
                if not cp.isNull():
                    self._art_pix_cache[cf] = cp

    def _preload_direction(self, steps: int):
        """Encola la precarga predictiva de logotipos en la dirección en que el usuario está navegando."""
        if not self.games or not hasattr(self, "_wheel_worker") or not self._wheel_worker:
            return
        n = len(self.games)
        direction = 1 if steps > 0 else -1
        start = self.selected_index
        count = 30 if abs(steps) <= 1 else 50
        window = [
            self.games[(start + (i * direction)) % n]
            for i in range(1, count + 1)
            if self.games[(start + (i * direction)) % n].get("id") not in self._wheel_pixmaps
        ]
        if window:
            self._wheel_worker.queue_games(window, priority=True)

    def _get_game_wheel_pixmap(self, game: dict) -> QPixmap | None:
        """Obtiene el QPixmap del logotipo de rueda."""
        gid = game.get("id")
        if gid in self._wheel_pixmaps:
            return self._wheel_pixmaps[gid]

        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.queue_game(game, priority=True)

        return None

    def _get_target_rect(self) -> QRect:
        """Calcula el rectángulo con relación de aspecto 16:9 centrado en el widget."""
        w = self.width()
        h = self.height()
        target_ar = self.CANONICAL_W / self.CANONICAL_H
        curr_ar = w / h if h > 0 else target_ar

        if curr_ar > target_ar:
            sh = h
            sw = int(h * target_ar)
            sx = (w - sw) // 2
            sy = 0
        else:
            sw = w
            sh = int(w / target_ar)
            sx = 0
            sy = (h - sh) // 2
        return QRect(sx, sy, sw, sh)

    def paintEvent(self, event):
        """Punto central de renderizado por capas: fondo, CRT, consola, HuCard, ruleta y puntero."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        try:
            # Fondo negro para letterboxing/pillarboxing
            painter.fillRect(self.rect(), QColor(0, 0, 0))

            sr = self._get_target_rect()
            sw = sr.width()
            sh = sr.height()
            sx = sr.x()
            sy = sr.y()

            # Capa 1: Fondo temático de NEC TurboGrafx-16
            if self._pix_bkg:
                if getattr(self, "_cached_bkg_size", None) != (sw, sh):
                    self._cached_bkg_pix = self._pix_bkg.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_bkg_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_bkg_pix)

            # Capa 2: Snap Video dentro del marco CRT
            vx, vy, vw, vh = self.TV_RECT
            tv_rect = QRect(sx + int(sw * vx), sy + int(sh * vy), int(sw * vw), int(sh * vh))

            if self._current_video_image:
                painter.drawImage(tv_rect, self._current_video_image)
            else:
                painter.fillRect(tv_rect, QColor(10, 10, 15))

            # Capa 3: Scanlines CRT
            if not self._pix_scanlines:
                scan_path = COMMON_DIR / "art" / "scanlines_1920.png"
                if scan_path.is_file():
                    self._pix_scanlines = self._load_pixmap(str(scan_path))
            if self._pix_scanlines:
                painter.save()
                painter.setOpacity(0.35)
                painter.drawPixmap(tv_rect, self._pix_scanlines)
                painter.restore()

            # Capa 4: Marco de Televisor CRT
            if self._pix_tv:
                if getattr(self, "_cached_tv_size", None) != (sw, sh):
                    self._cached_tv_pix = self._pix_tv.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_tv_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_tv_pix)

            # Capa 5: Avatar (Nave espacial animada)
            self._draw_avatar(painter, sr)

            # Capa 6: Logotipo animado superior
            self._draw_logo(painter, sr)

            # Capa 7: Chasis de la Consola NEC TurboGrafx-16
            if self._pix_console:
                if getattr(self, "_cached_console_size", None) != (sw, sh):
                    self._cached_console_pix = self._pix_console.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_console_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_console_pix)

            # Capa 8: Tarjeta HuCard insertándose verticalmente
            self._draw_cart_or_disc(painter, sr)

            # Capa 9: Tapa frontal de la ranura de HuCard (cubre la base de la tarjeta)
            if self._pix_console_cover:
                if getattr(self, "_cached_console_cover_size", None) != (sw, sh):
                    self._cached_console_cover_pix = self._pix_console_cover.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_console_cover_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_console_cover_pix)

            # Capa 10: Joystick TurboGrafx-16
            if self._pix_joystick:
                if getattr(self, "_cached_joystick_size", None) != (sw, sh):
                    self._cached_joystick_pix = self._pix_joystick.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_joystick_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_joystick_pix)

            # Capa 11: Carátula del juego (Boxart)
            self._draw_boxart(painter, sr)

            # Capa 12: Sombra / fondo de la ruleta (desde gtc-common)
            if self._pix_wheel_shadow:
                if getattr(self, "_cached_wheel_shadow_size", None) != (sw, sh):
                    self._cached_wheel_shadow_pix = self._pix_wheel_shadow.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_wheel_shadow_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_wheel_shadow_pix)

            # Capa 13: Ruleta curva interactiva
            if self.games:
                self._draw_wheel_conveyor(painter, sr)

            # Capa 14: Puntero selector de la ruleta
            self._draw_pointer(painter, sr)

            # Capa 15: Barra inferior con título
            self._draw_bottom_bar(painter, sr)

        finally:
            painter.end()

    def _draw_avatar(self, painter: QPainter, sr: QRect):
        """Dibuja la nave espacial con su oscilación sinusoidal."""
        avatar_pix = self._pix_avatar
        if not avatar_pix:
            return
        sw, sh = sr.width(), sr.height()
        sx, sy = sr.x(), sr.y()
        scale = getattr(self, "AVATAR_SCALE", 1.0)
        aw = int(sw * scale)
        ah = int(sh * scale)
        y_adj = getattr(self, "AVATAR_Y_ADJUST", 0)
        pos_x = int(getattr(self, "AVATAR_X", 0.0) * sw)
        pos_y = int(getattr(self, "AVATAR_Y", 0.0) * sh)
        anim_x = int(self._avatar_offset_x * (sw / self.CANONICAL_W))
        anim_y = int((self._avatar_offset_y + y_adj) * (sh / self.CANONICAL_H))
        draw_x = sx + pos_x + anim_x
        draw_y = sy + pos_y + anim_y
        painter.drawPixmap(draw_x, draw_y, aw, ah, avatar_pix)

    def _draw_logo(self, painter: QPainter, sr: QRect):
        """Dibuja el logotipo del sistema con su desplazamiento interpolado."""
        if not self._pix_logo:
            return
        sw, sh = sr.width(), sr.height()
        sx, sy = sr.x(), sr.y()
        logo_y = sy + int(sh * self._logo_current_y_offset_ratio)
        if self.LOGO_SCALE != 1.0:
            lw = int(sw * self.LOGO_SCALE)
            lh = int(sh * self.LOGO_SCALE)
            painter.drawPixmap(sx, logo_y, lw, lh, self._pix_logo)
        else:
            painter.drawPixmap(sx, logo_y, sw, sh, self._pix_logo)

    def _draw_cart_or_disc(self, painter: QPainter, sr: QRect):
        """Renderiza la tarjeta HuCard simulando la inserción en la consola desde abajo."""
        sw, sh = sr.width(), sr.height()
        sx, sy = sr.x(), sr.y()

        _, _, cw, ch = self.CART_RECT
        cur_x = getattr(self, "_cart_current_x_ratio", self.CART_RECT[0])
        cur_y = getattr(self, "_cart_current_y_ratio", self.CART_RECT[1])
        cart_x = sx + int(sw * cur_x)
        cart_w = int(sw * cw)
        cart_h = int(sh * ch)
        cart_y = sy + int(sh * cur_y)

        cart_pix = getattr(self, "_current_cart_pixmap", None) if getattr(self, "_pending_cart_file", None) else self._pix_cartart_frame
        if cart_pix and not cart_pix.isNull():
            painter.save()
            pw = cart_pix.width()
            ph = cart_pix.height()
            s = min(cart_w / pw, cart_h / ph) if pw > 0 and ph > 0 else 1.0
            dw = int(pw * s)
            dh = int(ph * s)
            draw_cx = cart_x + (cart_w - dw) // 2
            draw_cy = cart_y + (cart_h - dh) // 2
            painter.drawPixmap(QRect(draw_cx, draw_cy, dw, dh), cart_pix)
            painter.restore()

    def _draw_boxart(self, painter: QPainter, sr: QRect):
        """Dibuja la carátula del juego con sombreado y animación de deslizamiento."""
        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        box_w = int(sw * self.BOXART_W)
        box_h = int(sh * self.BOXART_H)
        box_x = sx + int(sw * self.BOXART_X)

        box_pix = getattr(self, "_current_box_pixmap", None) if getattr(self, "_pending_box_file", None) else self._pix_boxart_frame
        if box_pix and not box_pix.isNull():
            painter.save()
            painter.setOpacity(self._boxart_alpha)

            anim_x = box_x + int(sw * self._boxart_current_x_offset_ratio)
            pw = box_pix.width()
            ph = box_pix.height()
            s = min(box_w / pw, box_h / ph) if pw > 0 and ph > 0 else 1.0
            dw = int(pw * s)
            dh = int(ph * s)
            draw_bx = anim_x + (box_w - dw) // 2

            anchor_y = sy + int(sh * self.BOXART_BOTTOM_Y)
            draw_by = anchor_y - dh

            painter.drawPixmap(QRect(draw_bx, draw_by, dw, dh), box_pix)
            painter.restore()

    def _draw_wheel_conveyor(self, painter: QPainter, sr: QRect):
        """Calcula la perspectiva curva en 14 nodos interpolando posición, escala, rotación y opacidad."""
        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        n_games = len(self.games)
        if n_games == 0:
            return

        draw_offsets = [-6, 6, -5, 5, -4, 4, -3, 3, -2, 2, -1, 1, 0]

        for offset in draw_offsets:
            game_idx = (self.selected_index + offset) % n_games
            game = self.games[game_idx]

            pos = (7.0 + offset) + self._wheel_spin_offset
            if pos < 0.0 or pos >= 13.0:
                continue

            i0 = int(math.floor(pos))
            i1 = min(i0 + 1, 13)
            p = pos - i0

            rx = self.CONVEYOR_X[i0] + p * (self.CONVEYOR_X[i1] - self.CONVEYOR_X[i0])
            ry = self.CONVEYOR_Y[i0] + p * (self.CONVEYOR_Y[i1] - self.CONVEYOR_Y[i0])
            rw = self.CONVEYOR_W[i0] + p * (self.CONVEYOR_W[i1] - self.CONVEYOR_W[i0])
            rh = self.CONVEYOR_H[i0] + p * (self.CONVEYOR_H[i1] - self.CONVEYOR_H[i0])
            rot = self.CONVEYOR_R[i0] + p * (self.CONVEYOR_R[i1] - self.CONVEYOR_R[i0])
            alpha_val = int(self.CONVEYOR_A[i0] + p * (self.CONVEYOR_A[i1] - self.CONVEYOR_A[i0]))
            alpha_val = max(0, min(255, alpha_val))

            if alpha_val <= 0:
                continue

            target_w = int(sw * rw)
            target_h = int(sh * rh)
            center_x = sx + int(sw * rx) + target_w // 2
            center_y = sy + int(sh * ry) + target_h // 2

            pix = self._get_game_wheel_pixmap(game)

            painter.save()
            painter.setOpacity(alpha_val / 255.0)

            t = QTransform()
            t.translate(center_x, center_y)
            t.rotate(rot)
            painter.setTransform(t, True)

            if pix and not pix.isNull():
                pw = pix.width()
                ph = pix.height()
                scale = min(target_w / pw, target_h / ph) if pw > 0 and ph > 0 else 1.0
                draw_w = max(1, int(pw * scale))
                draw_h = max(1, int(ph * scale))
                rect = QRect(-draw_w // 2, -draw_h // 2, draw_w, draw_h)
                painter.drawPixmap(rect, pix)
            else:
                title = game.get("title", "Juego")
                rect = QRect(-target_w // 2, -target_h // 2, target_w, target_h)
                painter.fillRect(rect, QColor(25, 25, 30, 200))
                painter.setPen(QColor(255, 140, 0))
                font = QFont(self._font_main, max(10, int(sh * 0.022)), QFont.Bold)
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, title)

            painter.restore()

    def _draw_pointer(self, painter: QPainter, sr: QRect):
        """Renderiza el puntero de rueda apuntando hacia el slot central."""
        if not self._pix_pointer or not self.games:
            return

        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        ptr_size = int(sh * 0.24)
        ptr_w = ptr_size
        ptr_h = ptr_size

        slot_center_y_ratio = self.CONVEYOR_Y[7] + (self.CONVEYOR_H[7] / 2.0)
        ptr_cy = sy + int(sh * slot_center_y_ratio)
        ptr_y = ptr_cy - (ptr_h // 2)

        visible_w = int(ptr_w * 0.56)
        edge_margin = max(4, int(sw * 0.003))
        base_x = sx + sw - edge_margin - visible_w

        pulse_offset = int(sw * (self._pointer_rest_x_ratio - self._pointer_current_x_ratio))
        idle_oscillation = int(sw * (math.sin(self._pointer_anim_tick * 0.08) * 0.002))
        ptr_x = base_x - pulse_offset + idle_oscillation

        painter.save()
        painter.setOpacity(1.0)
        painter.drawPixmap(ptr_x, ptr_y, ptr_w, ptr_h, self._pix_pointer)
        painter.restore()

    def _draw_bottom_bar(self, painter: QPainter, sr: QRect):
        """Dibuja la barra inferior de metadatos con título, año y contador."""
        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        bar_h = int(sh * 0.075)
        bar_y = sy + sh - bar_h

        if self._pix_frame:
            painter.drawPixmap(sx, bar_y, sw, bar_h, self._pix_frame)
        else:
            painter.fillRect(QRect(sx, bar_y, sw, bar_h), QColor(15, 10, 8, 235))

        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return

        current_game = self.games[self.selected_index]
        title = current_game.get("title") or "Desconocido"

        f_size = max(13, int(sh * 0.032))
        f_title = QFont(self._font_bebas, f_size, QFont.Bold)
        f_title.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        painter.setFont(f_title)
        painter.setPen(QColor(255, 255, 255))
        title_rect = QRect(sx + int(sw * 0.08), bar_y, int(sw * 0.65), bar_h)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, title.upper())

        counter_text = f"GAME: {self.selected_index + 1} / {len(self.games)}"
        f_counter = QFont(self._font_main, max(11, int(sh * 0.024)), QFont.Bold)
        painter.setFont(f_counter)
        # Resalte en naranja TurboGrafx
        painter.setPen(QColor(255, 140, 0))
        counter_rect = QRect(sx + int(sw * 0.70), bar_y, int(sw * 0.25), bar_h)
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter_text)

    # -------------------------------------------------------------------------
    # MANEJO DE ENTRADAS (TECLADO, MOUSE, MANDOS)
    # -------------------------------------------------------------------------

    def keyPressEvent(self, event):
        """Captura la navegación por teclado con verificación de emulador activo."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return

        key = event.key()
        if matches_action(event, ACTION_NAV_UP) or key in (Qt.Key_Up,):
            self._navigate_steps(-1)
            event.accept()
        elif matches_action(event, ACTION_NAV_DOWN) or key in (Qt.Key_Down,):
            self._navigate_steps(1)
            event.accept()
        elif matches_action(event, ACTION_PAGE_UP) or matches_action(event, ACTION_NAV_STEP5_BACK):
            self._navigate_steps(-5)
            event.accept()
        elif matches_action(event, ACTION_PAGE_DOWN) or matches_action(event, ACTION_NAV_STEP5_FWD):
            self._navigate_steps(5)
            event.accept()
        elif matches_action(event, ACTION_SELECT) or key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if event.isAutoRepeat():
                event.accept()
                return
            gid = self.get_selected_game_id()
            if gid and self._can_activate_game():
                self._play_select_sound()
                self.game_activated.emit(gid)
            event.accept()
        elif matches_action(event, ACTION_NAV_BACK):
            self.nav_back_requested.emit()
            event.accept()
        elif matches_action(event, ACTION_MUTE) or key == Qt.Key_M:
            self.set_muted(not self.is_muted())
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Permite seleccionar juegos haciendo clic directamente sobre los elementos de la ruleta."""
        if event.button() == Qt.LeftButton and self.games:
            pos = event.position()
            mx = pos.x()
            my = pos.y()

            sr = self._get_target_rect()
            sw = sr.width()
            sh = sr.height()
            sx = sr.x()
            sy = sr.y()

            n_games = len(self.games)
            if n_games > 0:
                for offset in range(-6, 7):
                    pos_idx = (7.0 + offset) + self._wheel_spin_offset
                    if 0.0 <= pos_idx < 13.0:
                        i0 = int(math.floor(pos_idx))
                        i1 = min(i0 + 1, 13)
                        p = pos_idx - i0
                        rx = self.CONVEYOR_X[i0] + p * (self.CONVEYOR_X[i1] - self.CONVEYOR_X[i0])
                        ry = self.CONVEYOR_Y[i0] + p * (self.CONVEYOR_Y[i1] - self.CONVEYOR_Y[i0])
                        rw = self.CONVEYOR_W[i0] + p * (self.CONVEYOR_W[i1] - self.CONVEYOR_W[i0])
                        rh = self.CONVEYOR_H[i0] + p * (self.CONVEYOR_H[i1] - self.CONVEYOR_H[i0])

                        item_w = int(sw * rw)
                        item_h = int(sh * rh)
                        item_x = sx + int(sw * rx)
                        item_y = sy + int(sh * ry)
                        hit_rect = QRect(item_x, item_y, item_w, item_h)

                        if hit_rect.contains(int(mx), int(my)):
                            target_game_idx = (self.selected_index + offset) % n_games
                            if target_game_idx == self.selected_index:
                                gid = self.get_selected_game_id()
                                if gid and self._can_activate_game():
                                    self._play_select_sound()
                                    self.game_activated.emit(gid)
                            else:
                                self._navigate_steps(offset)
                            event.accept()
                            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        event.accept()

    def wheelEvent(self, event):
        """Permite navegar fluidamente por la lista utilizando la rueda del ratón."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._navigate_steps(-1)
        elif delta < 0:
            self._navigate_steps(1)
        event.accept()

    def hideEvent(self, event):
        """Pausa la multimedia cuando el layout deja de ser visible."""
        if self.player:
            self.player.pause()
        super().hideEvent(event)

    def showEvent(self, event):
        """Reanuda la animación al volver a enfocar este layout."""
        super().showEvent(event)
        self._start_logo_animation()

    def closeEvent(self, event):
        """Libera los hilos de precarga y reproductores al cerrar la ventana."""
        self.stop_media()
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.stop()
        if event is not None:
            super().closeEvent(event)

    def clear(self):
        """Limpia la lista de juegos y cachés de texturas en memoria."""
        self._wheel_spin_offset = 0.0
        if hasattr(self, '_wheel_spin_timer') and self._wheel_spin_timer.isActive():
            self._wheel_spin_timer.stop()
        self._current_video_image = None
        self.stop_media()
        super().clear()
        self._wheel_pixmaps.clear()
        if hasattr(self, '_wheel_worker') and self._wheel_worker:
            self._wheel_worker.clear()

