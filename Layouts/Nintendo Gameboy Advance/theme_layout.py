import playnexus
"""
=============================================================================
Layout Autónomo y Configuración: Nintendo Gameboy Advance
=============================================================================
Este archivo maneja en su totalidad la configuración, métricas, recursos,
reproducción de video en pantalla LCD, animaciones de entrada, carátula,
cartucho, avatar animado y renderizado completo del sistema Nintendo Gameboy
Advance para PlayNexus.
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
from playnexus.ui.cover_utils import load_cover
from playnexus.services.controls import (
    matches_action, ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_PAGE_UP,
    ACTION_PAGE_DOWN, ACTION_SELECT, ACTION_MUTE, ACTION_NAV_BACK
)

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(BaseLayout):
    LAYOUT_NAME = "Nintendo Gameboy Advance"
    LAYOUT_DESCRIPTION = "Layout temático de Game Boy Advance con consola portátil, LCD snap, carátula, cartucho y avatar animado"

    CANONICAL_W = 1920
    CANONICAL_H = 1080

    # -------------------------------------------------------------------------
    # 1. REQUERIMIENTOS DE MEDIOS PARA ESTE LAYOUT (LEÍDOS DIRECTAMENTE POR EL SISTEMA)
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
            "label": "Cartuchos",
            "extensions": [".png", ".webp"],
            "required": False
        },
        {
            "key": "boxart",
            "label": "Box Art / Cajas",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": False
        }
    ]

    # -------------------------------------------------------------------------
    # 2. FUENTES TIPOGRÁFICAS DEL TEMA
    # -------------------------------------------------------------------------
    FONT_TITLE_FILE = "FuturaBoldItalic.ttf"   # Fuente destacada para títulos
    FONT_MAIN_FILE  = "BebasNeue Bold.otf"     # Fuente para contadores, año e info técnica
    FONT_FILES = [FONT_TITLE_FILE, FONT_MAIN_FILE]

    # -------------------------------------------------------------------------
    # 3. RECURSOS COMPARTIDOS DESDE gtc-common
    # -------------------------------------------------------------------------
    WHEEL_SHADOW_IMAGE = COMMON_DIR / "wheel" / "wheel_shadow.png"
    COMMON_WHEEL_ART   = COMMON_DIR / "art" / "wheel_art.png"
    COMMON_FRAME       = COMMON_DIR / "art" / "frame.png"
    STATIC_VIDEO       = COMMON_DIR / "videos" / "static.mp4"
    SOUND_NAV          = COMMON_DIR / "sounds" / "joystick.mp3"
    SOUND_SELECT       = COMMON_DIR / "sounds" / "Mame_coin.mp3"
    SCANLINES_IMAGE    = COMMON_DIR / "art" / "scanlines_1920.png"
    SCRATCHES_IMAGE    = COMMON_DIR / "art" / "arcade" / "scratched_cover.png"

    # -------------------------------------------------------------------------
    # 4. ASIGNACIÓN DE ARCHIVOS PROPIOS DEL LAYOUT
    # -------------------------------------------------------------------------
    BKG_IMAGE = LAYOUT_DIR / "bg.jpg"
    TV_IMAGE = None                           # Consola portátil (pantalla integrada en console.png)
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png"
    CONSOLE_COVER_IMAGE = None
    JOYSTICK_IMAGE = None
    AVATAR_IMAGE = LAYOUT_DIR / "avatar.png"
    LOGO_IMAGE = LAYOUT_DIR / "logo.png"
    CARTART_IMAGE = LAYOUT_DIR / "cartart.png"
    BOXART_IMAGE = LAYOUT_DIR / "boxart.png"
    WHEEL_IMAGE = LAYOUT_DIR / "wheel.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers" / "default.png"

    # -------------------------------------------------------------------------
    # 5. CONFIGURACIÓN GEOMÉTRICA DE NINTENDO GAMEBOY ADVANCE
    # -------------------------------------------------------------------------
    # Pantalla LCD dentro del chasis de Game Boy Advance: (x, y, w, h) en ratios de pantalla (1920x1080)
    TV_RECT = (0.184, 0.274, 0.222, 0.284)

    # Cartucho GBA a la derecha abajo
    CART_RECT = (0.850, 0.710, 0.130, 0.280)
    CART_END_Y = 0.710
    IS_CD = False

    # Carátula (Boxart) a la derecha
    BOXART_X = 0.690
    BOXART_Y = 0.430
    BOXART_W = 0.190
    BOXART_H = 0.650
    BOXART_ANCHOR = "center"

    # Logotipo del sistema
    LOGO_SCALE = 1.0

    # Escala y posición del Avatar (Link animado)
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

    def __init__(self, theme_name: str = "Nintendo Gameboy Advance", parent=None):
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
        if not bkg_cand or not os.path.isfile(bkg_cand):
            bkg_cand = str(LAYOUT_DIR / "bg.jpg")
        self._pix_bkg = self._load_pixmap(bkg_cand)
        self._pix_tv = None
        self._pix_console = self._load_pixmap(str(self.CONSOLE_IMAGE))
        self._pix_console_cover = None
        self._pix_joystick = None

        self._pix_avatar = self._load_pixmap(str(self.AVATAR_IMAGE))
        self._pix_logo = self._load_pixmap(str(self.LOGO_IMAGE))
        self._pix_cartart_frame = self._load_pixmap(str(self.CARTART_IMAGE)) if self.CARTART_IMAGE else None
        self._pix_boxart_frame = self._load_pixmap(str(self.BOXART_IMAGE)) if self.BOXART_IMAGE else None

        # Recursos compartidos directos desde gtc-common
        self._pix_scanlines = None
        self._pix_wheel_art = self._load_pixmap(str(self.COMMON_WHEEL_ART))
        self._pix_frame = self._load_pixmap(str(self.COMMON_FRAME))
        self._pix_scratches = self._load_pixmap(str(self.SCRATCHES_IMAGE))
        self._static_video_path = str(self.STATIC_VIDEO) if self.STATIC_VIDEO.is_file() else None

        # Sombra de ruleta directa desde gtc-common/wheel
        self._pix_wheel_shadow = self._load_pixmap(str(self.WHEEL_SHADOW_IMAGE)) if self.WHEEL_SHADOW_IMAGE and self.WHEEL_SHADOW_IMAGE.is_file() else None

        # Puntero animado de la ruleta asignado en este layout
        pointer_path = str(self.POINTER_IMAGE)
        self._pix_pointer = self._load_pixmap(pointer_path)

        # Diccionario theme_info autogenerado internamente por el layout
        self.theme_info = {
            "name": self.theme_name,
            "folder": str(LAYOUT_DIR),
            "bkg": str(self.BKG_IMAGE),
            "tv": None,
            "console": str(self.CONSOLE_IMAGE),
            "console_cover": None,
            "joystick": None,
            "avatar": str(self.AVATAR_IMAGE),
            "character": str(self.AVATAR_IMAGE),
            "logo": str(self.LOGO_IMAGE),
            "cartart": str(self.CARTART_IMAGE) if self.CARTART_IMAGE else None,
            "boxart": str(self.BOXART_IMAGE) if self.BOXART_IMAGE else None,
            "wheel_shadow": str(self.WHEEL_SHADOW_IMAGE) if self.WHEEL_SHADOW_IMAGE else None,
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
        self._font_title = "sans-serif"
        self._font_main = "sans-serif"
        self._font_bebas = "sans-serif"
        self._load_theme_fonts()

        # Animación de giro suave de la ruleta
        self._wheel_spin_offset = 0.0
        self._wheel_spin_timer = QTimer(self)
        self._wheel_spin_timer.setTimerType(Qt.PreciseTimer)
        self._wheel_spin_timer.timeout.connect(self._on_wheel_spin_tick)

        # Confirmación de selección diferida al soltar tecla o reposo (Commit on Release / Debounce)
        self._nav_pending_commit = False
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(getattr(self, "NAV_COMMIT_DEBOUNCE_MS", 180))
        self._commit_timer.timeout.connect(self._commit_selection)

        # Animación del Avatar (Link flotante)
        self._avatar_anim_time = 0.0
        self._avatar_offset_x = 0.0
        self._avatar_offset_y = 0.0
        self._avatar_bounce_timer = QTimer(self)
        self._avatar_bounce_timer.timeout.connect(self._on_avatar_bounce_tick)
        self._avatar_bounce_timer.start(20)

        # Animación de inserción de cartucho
        self._cart_anim_timer = QTimer(self)
        self._cart_anim_timer.timeout.connect(self._on_cart_anim_tick)
        self._cart_anim_elapsed = 0
        self._cart_anim_duration = 500
        self._cart_start_y_ratio = 1.3
        self._cart_end_y_ratio = self.CART_END_Y
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
        """Carga un QPixmap con caché en memoria global para acelerar la inicialización instantánea."""
        return super()._load_pixmap(path)

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
        """Carga automáticamente las fuentes declaradas en la cabecera."""
        self._font_title = self._load_font_family(getattr(self, "FONT_TITLE_FILE", None))
        self._font_main  = self._load_font_family(getattr(self, "FONT_MAIN_FILE", None))
        self._font_bebas = self._font_main

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
        """Aplica un movimiento sinusoidal oscilatorio a Link simulando respiración y flotación."""
        self._avatar_anim_time += 0.04
        self._avatar_offset_y = math.sin(self._avatar_anim_time) * 12.0
        self._avatar_offset_x = math.cos(self._avatar_anim_time * 0.5) * 4.0
        self.update()

    def _on_pointer_tick(self):
        """Controla la animación de pulso y retracción del puntero indicador de selección."""
        self._pointer_anim_tick += 1
        diff = self._pointer_rest_x_ratio - self._pointer_current_x_ratio
        if abs(diff) > 0.0005:
            self._pointer_current_x_ratio += diff * 0.20
        else:
            self._pointer_current_x_ratio = self._pointer_rest_x_ratio
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

        # Diferir confirmación de medios al soltar la tecla (Commit on Release)
        # El video previo continúa reproduciéndose fluidamente sin pausarse hasta el commit
        if hasattr(self, "_video_debounce_timer"):
            self._video_debounce_timer.stop()
        if hasattr(self, "_video_watchdog_timer"):
            self._video_watchdog_timer.stop()
        self._nav_pending_commit = True
        self._commit_timer.start(getattr(self, "NAV_COMMIT_DEBOUNCE_MS", 180))

        if not self._wheel_spin_timer.isActive():
            self._wheel_spin_timer.start(16)
        self.update()

    def _commit_selection(self):
        """Aplica y carga los medios del juego seleccionado una vez detenido el desplazamiento."""
        if not getattr(self, "_nav_pending_commit", False):
            return
        self._nav_pending_commit = False
        if hasattr(self, "_commit_timer"):
            self._commit_timer.stop()
        self._update_current_selection()

    def _on_wheel_spin_tick(self):
        """Interpola la posición continua de la ruleta hacia el objetivo a 60 FPS con suavizado exponencial."""
        self._wheel_spin_offset *= 0.72
        if abs(self._wheel_spin_offset) < 0.015:
            self._wheel_spin_offset = 0.0
            self._wheel_spin_timer.stop()
        self.update()

    def _on_cart_anim_tick(self):
        """Ejecuta la animación de entrada suave del cartucho."""
        dt = 16
        self._cart_anim_elapsed += dt
        t = min(self._cart_anim_elapsed / self._cart_anim_duration, 1.0)
        ease = 1.0 - (1.0 - t) ** 3
        self._cart_current_y_ratio = (
            self._cart_start_y_ratio
            + (self._cart_end_y_ratio - self._cart_start_y_ratio) * ease
        )
        self.update()
        if t >= 1.0:
            self._cart_anim_timer.stop()
            self._cart_current_y_ratio = self._cart_end_y_ratio

    def _start_cart_animation(self):
        """Reinicia la cinemática de entrada del cartucho."""
        self._cart_anim_elapsed = 0
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
        """Interpola la posición vertical y opacidad de la carátula hacia su posición final."""
        dt = 16
        self._boxart_anim_elapsed += dt
        t = min(self._boxart_anim_elapsed / self._boxart_anim_duration, 1.0)
        ease = 1.0 - (1.0 - t) ** 2
        start_x_offset = 0.30
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
        self._boxart_current_x_offset_ratio = 0.30
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
        """Recibe el frame decodificado desde QVideoSink y solicita el repintado de la TV/LCD."""
        if frame.isValid() and getattr(self, "_want_video_playing", True) and self.player:
            p_path = getattr(self, "_pending_video_path", None)
            if p_path and self.player.source() != QUrl.fromLocalFile(p_path):
                return
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
        """Reanuda la reproducción de video y audio cuando el emulador finaliza o se restaura la ventana."""
        self._want_video_playing = True
        if not getattr(self, "_pending_video_path", None) or not os.path.isfile(self._pending_video_path):
            self._update_current_selection()
        else:
            self._play_debounced_video()
        self.update()

    def stop_media(self):
        """Detiene completamente la reproducción de video y audio liberando recursos del sistema."""
        self._want_video_playing = False
        self._pending_video_path = None
        if hasattr(self, "_commit_timer"):
            self._commit_timer.stop()
        self._nav_pending_commit = False
        if hasattr(self, '_video_debounce_timer'):
            self._video_debounce_timer.stop()
        if hasattr(self, '_video_watchdog_timer'):
            self._video_watchdog_timer.stop()
        if hasattr(self, '_studio_anim_timer'):
            try:
                self._studio_anim_timer.stop()
            except Exception:
                pass
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

    def cleanup(self):
        """Libera todos los recursos multimedia y temporizadores."""
        self.stop_media()
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            try:
                self._wheel_worker.stop()
            except Exception:
                pass

    def closeEvent(self, event=None):
        """Libera los hilos de precarga, temporizadores y reproductores al cerrar la ventana."""
        self.cleanup()
        if event is not None:
            super().closeEvent(event)

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

        self._ensure_player_initialized()
        self._pending_video_path = video_to_play
        if not video_to_play:
            self._want_video_playing = False
            if self.player:
                self.player.stop()
            self._current_video_image = None
            self.update()
            return

        if hasattr(self, "_video_debounce_timer"):
            self._video_debounce_timer.stop()
            self._video_debounce_timer.start(100)
        else:
            self._play_debounced_video()

    def _load_pending_art(self):
        """Carga en memoria las imágenes de carátula y cartucho sin bloquear el hilo principal."""
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
                    if self.player.playbackState() != QMediaPlayer.PlayingState:
                        self.player.play()
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
            for i in range(-4, 12)
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
        """Punto central de renderizado por capas: fondo, CRT/LCD, consola GBA, artes, ruleta interactiva y puntero."""
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

            # Capa 1: Fondo temático de Game Boy Advance
            if self._pix_bkg:
                if getattr(self, "_cached_bkg_size", None) != (sw, sh):
                    self._cached_bkg_pix = self._pix_bkg.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_bkg_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_bkg_pix)

            # Capa 2: Snap Video dentro de la pantalla LCD de la consola
            vx, vy, vw, vh = self.TV_RECT
            tv_rect = QRect(sx + int(sw * vx), sy + int(sh * vy), int(sw * vw), int(sh * vh))

            if self._current_video_image:
                painter.drawImage(tv_rect, self._current_video_image)
            else:
                painter.fillRect(tv_rect, QColor(10, 10, 15))

            # Capa 3: Scanlines / LCD grid
            if not self._pix_scanlines:
                scan_path = COMMON_DIR / "art" / "scanlines_1920.png"
                if scan_path.is_file():
                    self._pix_scanlines = self._load_pixmap(str(scan_path))
            if self._pix_scanlines:
                painter.save()
                painter.setOpacity(0.30)
                painter.drawPixmap(tv_rect, self._pix_scanlines)
                painter.restore()

            # Capa 3b: Reflejo en pantalla LCD (scratches desde gtc-common)
            if self._pix_scratches:
                s_size = (tv_rect.width(), tv_rect.height())
                if getattr(self, "_cached_scratches_size", None) != s_size:
                    self._cached_scratches_pix = self._pix_scratches.scaled(s_size[0], s_size[1], Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_scratches_size = s_size
                painter.save()
                painter.setOpacity(0.35)
                painter.drawPixmap(tv_rect.x(), tv_rect.y(), self._cached_scratches_pix)
                painter.restore()

            # Capa 4: Chasis de la Consola Game Boy Advance (enmarca la pantalla LCD)
            if self._pix_console:
                if getattr(self, "_cached_console_size", None) != (sw, sh):
                    self._cached_console_pix = self._pix_console.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_console_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_console_pix)

            # Capa 5: Avatar (Link animado)
            self._draw_avatar(painter, sr)

            # Capa 6: Logotipo animado superior
            self._draw_logo(painter, sr)

            # Capa 7: Sombra / fondo de la ruleta (si está habilitada en el tema)
            if self._pix_wheel_shadow:
                if getattr(self, "_cached_wheel_shadow_size", None) != (sw, sh):
                    self._cached_wheel_shadow_pix = self._pix_wheel_shadow.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_wheel_shadow_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_wheel_shadow_pix)

            # Capa 8: Ruleta curva interactiva (detrás de boxart y cartart según zorder=10 de layout.nut)
            if self.games:
                self._draw_wheel_conveyor(painter, sr)

            # Capa 9: Carátula del juego (Boxart, zorder 10 en primer plano)
            self._draw_boxart(painter, sr)

            # Capa 10: Cartucho de Game Boy Advance (zorder 10 en primer plano)
            self._draw_cart_or_disc(painter, sr)

            # Capa 11: Puntero selector de la ruleta
            self._draw_pointer(painter, sr)

            # Capa 12: Barra inferior con título
            self._draw_bottom_bar(painter, sr)

        finally:
            painter.end()

    def _draw_avatar(self, painter: QPainter, sr: QRect):
        """Dibuja el personaje decorativo (Link) con su oscilación sinusoidal."""
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
        """Renderiza el cartucho físico con su desplazamiento vertical."""
        sw, sh = sr.width(), sr.height()
        sx, sy = sr.x(), sr.y()

        cx, cy_ratio, cw, ch = self.CART_RECT
        cart_cx_abs = sx + int(sw * cx)
        cart_cy_abs = sy + int(sh * self._cart_current_y_ratio)
        cart_w = int(sw * cw)
        cart_h = int(sh * ch)

        cart_pix = getattr(self, "_current_cart_pixmap", None) or self._pix_cartart_frame
        if cart_pix and not cart_pix.isNull():
            pw = cart_pix.width()
            ph = cart_pix.height()
            s = min(cart_w / pw, cart_h / ph) if pw > 0 and ph > 0 else 1.0
            dw = int(pw * s)
            dh = int(ph * s)

            draw_cx = cart_cx_abs + (cart_w - dw) // 2
            draw_cy = cart_cy_abs + (cart_h - dh) // 2

            painter.drawPixmap(QRect(draw_cx, draw_cy, dw, dh), cart_pix)

    def _draw_boxart(self, painter: QPainter, sr: QRect):
        """Dibuja la carátula del juego con sombreado y animación de deslizamiento."""
        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        box_w = int(sw * self.BOXART_W)
        box_h = int(sh * self.BOXART_H)
        box_x = sx + int(sw * self.BOXART_X)

        box_pix = getattr(self, "_current_box_pixmap", None) or self._pix_boxart_frame
        if box_pix and not box_pix.isNull():
            pw = box_pix.width()
            ph = box_pix.height()
            s = min(box_w / pw, box_h / ph) if pw > 0 and ph > 0 else 1.0
            dw = int(pw * s)
            dh = int(ph * s)

            painter.save()
            painter.setOpacity(self._boxart_alpha)

            anim_x = box_x + int(sw * self._boxart_current_x_offset_ratio)
            draw_bx = anim_x + (box_w - dw) // 2

            if getattr(self, "BOXART_ANCHOR", "center") == "bottom":
                anchor_y = sy + int(sh * getattr(self, "BOXART_BOTTOM_Y", 0.92))
                draw_by = anchor_y - dh
            else:
                box_y = sy + int(sh * getattr(self, "BOXART_Y", 0.43))
                draw_by = box_y + (box_h - dh) // 2

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
            angle = self.CONVEYOR_R[i0] + p * (self.CONVEYOR_R[i1] - self.CONVEYOR_R[i0])
            alpha = int(self.CONVEYOR_A[i0] + p * (self.CONVEYOR_A[i1] - self.CONVEYOR_A[i0]))

            if alpha <= 0:
                continue

            item_w = int(sw * rw)
            item_h = int(sh * rh)
            item_cx = sx + int(sw * rx) + item_w // 2
            item_cy = sy + int(sh * ry) + item_h // 2

            pix = self._get_game_wheel_pixmap(game)

            painter.save()
            painter.setOpacity(alpha / 255.0)
            painter.translate(item_cx, item_cy)
            painter.rotate(angle)

            if pix and not pix.isNull():
                pw = pix.width()
                ph = pix.height()
                s = min(item_w / pw, item_h / ph) if pw > 0 and ph > 0 else 1.0
                dw = int(pw * s)
                dh = int(ph * s)
                painter.drawPixmap(QRect(-dw // 2, -dh // 2, dw, dh), pix)
            else:
                rect = QRect(-item_w // 2, -item_h // 2, item_w, item_h)
                painter.fillRect(rect, QColor(0, 0, 0, 160))
                painter.setPen(QPen(QColor(255, 255, 255, alpha), 1.5))
                painter.drawRect(rect)
                painter.setFont(QFont(self._font_title, max(8, int(item_h * 0.22)), QFont.Bold))
                title = game.get("title", f"Game {game.get('id', '')}")
                painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, title)

            painter.restore()

    def _draw_pointer(self, painter: QPainter, sr: QRect):
        """Dibuja la flecha indicadora o puntero que señala el juego seleccionado en la ruleta."""
        if not self._pix_pointer or not self.games:
            return

        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        ptr_size = int(sh * 0.24)
        ptr_w = ptr_size
        ptr_h = ptr_size

        # Alineación vertical exacta con el centro del slot seleccionado de la ruleta (índice 7)
        slot_center_y_ratio = self.CONVEYOR_Y[7] + (self.CONVEYOR_H[7] / 2.0)
        ptr_cy = sy + int(sh * slot_center_y_ratio)
        ptr_y = ptr_cy - (ptr_h // 2)

        # Ancho visible del puntero (~56% del ancho de 326)
        visible_w = int(ptr_w * 0.56)
        # Casi pegado al borde derecho de la pantalla (margen mínimo de ~4px)
        edge_margin = max(4, int(sw * 0.003))
        base_x = sx + sw - edge_margin - visible_w

        # Pulso elástico al cambiar de juego + micro oscilación en reposo
        pulse_offset = int(sw * (self._pointer_rest_x_ratio - self._pointer_current_x_ratio))
        idle_oscillation = int(sw * (math.sin(self._pointer_anim_tick * (8.0 / 60.0)) * 0.009375))
        ptr_x = base_x - pulse_offset + idle_oscillation

        painter.save()
        painter.setOpacity(1.0)
        painter.drawPixmap(ptr_x, ptr_y, ptr_w, ptr_h, self._pix_pointer)
        painter.restore()

    def _draw_bottom_bar(self, painter: QPainter, sr: QRect):
        """Dibuja el marco inferior decorativo con el título del juego y el contador."""
        sw, sh = sr.width(), sr.height()
        sx, sy = sr.x(), sr.y()

        bar_h = int(sh * 0.075)
        bar_y = sy + sh - bar_h

        if self._pix_frame:
            painter.drawPixmap(sx, bar_y, sw, bar_h, self._pix_frame)
        else:
            painter.fillRect(QRect(sx, bar_y, sw, bar_h), QColor(15, 15, 20, 220))

        if not self.games:
            return

        game = self.games[self.selected_index]
        title = game.get("title", "")
        year = game.get("year", "")
        manu = game.get("manufacturer", "")
        txt_parts = [p for p in (title, year, manu) if p]
        full_title = " - ".join(txt_parts) if txt_parts else "Nintendo Gameboy Advance"

        painter.save()
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont(self._font_title, max(10, int(bar_h * 0.40)), QFont.Bold))
        text_rect = QRect(sx + int(sw * 0.08), bar_y, int(sw * 0.62), bar_h)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, full_title)

        counter_text = f"GBA: {self.selected_index + 1} / {len(self.games)}"
        painter.setPen(QColor(245, 185, 35))
        painter.setFont(QFont(self._font_main, max(9, int(bar_h * 0.35)), QFont.Bold))
        counter_rect = QRect(sx + int(sw * 0.70), bar_y, int(sw * 0.26), bar_h)
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter_text)
        painter.restore()

    def resizeEvent(self, event):
        """Invalida la caché de escalado cuando la ventana cambia de tamaño."""
        super().resizeEvent(event)
        self._cached_bkg_size = None
        self._cached_console_size = None
        self._cached_wheel_shadow_size = None
        self._cached_scratches_size = None

# --- PLAYNEXUS STUDIO OVERRIDES START ---
STUDIO_ELEMENTS = [
    {'id': 'bg_image', 'name': 'Fondo del Layout', 'type': 'image', 'x': 0.0, 'y': 0.0, 'w': 1920.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 5, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 0.0, 1920.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'video_snap', 'name': 'Pantalla TV / Video Snap', 'type': 'video', 'x': 353.0, 'y': 295.0, 'w': 426.0, 'h': 306.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 10, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [353.0, 295.0, 426.0, 306.0], 'media_key': 'video', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scanlines_crt', 'name': 'Scanlines CRT (gtc-common)', 'type': 'effect', 'x': 353.0, 'y': 295.0, 'w': 426.0, 'h': 306.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 15, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [353.0, 295.0, 426.0, 306.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scratches', 'name': 'Reflejo Vidrio CRT (gtc-common)', 'type': 'effect', 'x': 353.0, 'y': 295.0, 'w': 426.0, 'h': 306.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 20, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [353.0, 295.0, 426.0, 306.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'console', 'name': 'Consola (console.png)', 'type': 'image', 'x': 92.0, 'y': 188.0, 'w': 948.0, 'h': 576.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 25, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [92.0, 188.0, 948.0, 576.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'avatar', 'name': 'Avatar / Personaje', 'type': 'image', 'x': 848.3, 'y': 132.3, 'w': 588.0, 'h': 588.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 30, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [912.0, 404.0, 588.0, 588.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'avatar_float', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'logo', 'name': 'Logotipo del Sistema', 'type': 'image', 'x': 40.0, 'y': 32.0, 'w': 1168.0, 'h': 144.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 35, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [40.0, 32.0, 1168.0, 144.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'logo_bounce', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_shadow', 'name': 'Sombra de Ruleta (gtc-common)', 'type': 'image', 'x': 1336.0, 'y': 0.0, 'w': 584.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 40, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1336.0, 0.0, 584.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_list', 'name': 'Ruleta Curva (Wheel Conveyor)', 'type': 'wheel', 'x': 1208.0, 'y': 0.0, 'w': 628.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 45, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1208.0, 0.0, 628.0, 1080.0], 'media_key': 'wheel', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'boxart', 'name': 'Carátula (Box Art)', 'type': 'image', 'x': 42.3, 'y': 454.2, 'w': 364.8, 'h': 702.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 50, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1324.8, 464.4, 364.8, 702.0], 'media_key': 'boxart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'boxart_slide_fade', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'cartart', 'name': 'Cartucho / Disco', 'type': 'image', 'x': 562.5, 'y': 671.5, 'w': 412.1, 'h': 393.9, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 55, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1632.0, 766.8, 249.6, 302.4], 'media_key': 'cartart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'flyer_slide_right', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'pointer', 'name': 'Puntero de Ruleta', 'type': 'image', 'x': 1768.0, 'y': 424.0, 'w': 148.0, 'h': 264.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 60, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1768.0, 424.0, 148.0, 264.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'pointer_pulse', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'footer_frame', 'name': 'Barra Inferior (Footer)', 'type': 'image', 'x': 0.0, 'y': 999.0, 'w': 1920.0, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 65, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 999.0, 1920.0, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'title_text', 'name': 'Título del Juego (Footer)', 'type': 'text', 'x': 153.6, 'y': 999.0, 'w': 1190.4, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 70, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [153.6, 999.0, 1190.4, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'counter_text', 'name': 'Contador de Juegos (Footer)', 'type': 'text', 'x': 1344.0, 'y': 999.0, 'w': 499.2, 'h': 81.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 75, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1344.0, 999.0, 499.2, 81.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
]
try:
    from playnexus.ui.layout_studio.runtime_hook import install_studio_overrides as _install_studio_overrides
    _orig_init = ThemeLayout.__init__
    def _studio_patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        _install_studio_overrides(self, STUDIO_ELEMENTS)
    if not getattr(ThemeLayout.__init__, '_is_studio_patched', False):
        _orig_init = ThemeLayout.__init__
        _studio_patched_init._is_studio_patched = True
        ThemeLayout.__init__ = _studio_patched_init
except Exception:
    pass
# --- PLAYNEXUS STUDIO OVERRIDES END ---
