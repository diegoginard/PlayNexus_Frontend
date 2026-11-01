import retroshelf
"""
=============================================================================
Layout Autónomo y Configuración: Atari Jaguar CD
=============================================================================
Este archivo maneja en su totalidad la configuración, métricas, recursos,
reproducción de video, animaciones de entrada, giro de disco CD y renderizado
completo del sistema Atari Jaguar CD para RetroShelf.
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

from retroshelf.ui.layouts.base import BaseLayout, WheelPreloadWorker
from retroshelf.services.media import resolve_game_media
from retroshelf.ui.cover_utils import load_cover
from retroshelf.services.controls import (
    matches_action, ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_PAGE_UP,
    ACTION_PAGE_DOWN, ACTION_SELECT, ACTION_MUTE, ACTION_NAV_BACK
)

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(BaseLayout):
    LAYOUT_NAME = "Atari Jaguar CD"
    LAYOUT_DESCRIPTION = "Layout temático de Atari Jaguar CD fiel a Attract-Mode con CD giratorio, TV CRT y avatar animado"

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
            "label": "Discos",
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

    # -------------------------------------------------------------------------
    # ASIGNACIÓN DE ARCHIVOS PROPIOS DEL LAYOUT (ADMINISTRADOS POR ESTE ARCHIVO)
    # -------------------------------------------------------------------------
    BKG_IMAGE = LAYOUT_DIR / "bkg.jpg"
    TV_IMAGE = LAYOUT_DIR / "tv.png"
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png"
    CONSOLE_COVER_IMAGE = None
    JOYSTICK_IMAGE = None
    AVATAR_IMAGE = LAYOUT_DIR / "avatar.png"
    LOGO_IMAGE = LAYOUT_DIR / "logo.png"
    CARTART_IMAGE = LAYOUT_DIR / "cartart.png"
    BOXART_IMAGE = None
    WHEEL_IMAGE = LAYOUT_DIR / "wheel.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers/default.png"
    FONT_FILES = [
        "Handel Gothic BT.ttf",
        "BebasNeue Bold.otf",
    ]

    # -------------------------------------------------------------------------
    # CONFIGURACIÓN GEOMÉTRICA DE ATARI JAGUAR CD (FIEL A ATTRACT-MODE)
    # -------------------------------------------------------------------------
    # Pantalla CRT TV: (x, y, w, h) en ratios de pantalla (1920x1080)
    TV_RECT = (0.054, 0.196, 0.313, 0.430)

    # Disco CD giratorio al lado de la carátula
    CART_RECT = (0.550, 0.600, 0.190, 0.300)
    CART_END_Y = 0.600
    IS_CD = True

    # Carátula (Boxart) al lado del CD
    BOXART_X = 0.400
    BOXART_Y = 0.530
    BOXART_W = 0.165
    BOXART_H = 0.410
    BOXART_ANCHOR = "center"

    # Logotipo del sistema
    LOGO_SCALE = 1.0

    # Escala y posición del Avatar
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
    # -------------------------------------------------------------------------
    # GESTIÓN Y RESOLUCIÓN DE RECURSOS PROPIOS
    # -------------------------------------------------------------------------
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

    def __init__(self, theme_name: str = "Atari Jaguar CD", parent=None):
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
        if not bkg_cand:
            bkg_cand = str(LAYOUT_DIR / "bg.jpg") or str(LAYOUT_DIR / "bkg.png")
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
        self._pix_wheel_art = self._load_pixmap(str(COMMON_DIR / "art" / "wheel_art.png"))
        self._pix_frame = self._load_pixmap(str(COMMON_DIR / "art" / "frame.png"))
        static_vid = COMMON_DIR / "videos" / "static.mp4"
        self._static_video_path = str(static_vid) if static_vid.is_file() else None

        # Sombra de ruleta directa desde gtc-common/wheels o gtc-common/wheel
        shadow_file = COMMON_DIR / "wheels" / "wheel_shadow.png"
        if not shadow_file.is_file():
            shadow_file = COMMON_DIR / "wheel" / "wheel_shadow.png"
        self._pix_wheel_shadow = self._load_pixmap(str(shadow_file)) if shadow_file.is_file() else None

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
            "console_cover": None,
            "joystick": None,
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

        # Animación de entrada del disco CD
        self._cart_anim_timer = QTimer(self)
        self._cart_anim_timer.timeout.connect(self._on_cart_anim_tick)
        self._cart_anim_elapsed = 0
        self._cart_anim_duration = 600
        self._cart_start_y_ratio = 1.6
        self._cart_end_y_ratio = self.CART_END_Y
        self._cart_current_y_ratio = self._cart_end_y_ratio

        # Animación de rotación continua del CD
        self._cd_rotation_angle = 0.0
        self._cd_spin_timer = QTimer(self)
        self._cd_spin_timer.timeout.connect(self._on_cd_spin_tick)
        self._cd_spin_timer.start(16)

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

    def _load_theme_fonts(self):
        """Registra las fuentes tipográficas TrueType/OpenType del sistema en la base de datos de fuentes de Qt."""
        font_paths = []
        for f_rel in getattr(self, "FONT_FILES", []):
            resolved = str(LAYOUT_DIR / f_rel)
            if Path(resolved).is_file():
                font_paths.append(resolved)

        for f_path in font_paths:
            if os.path.isfile(f_path):
                fid = QFontDatabase.addApplicationFont(f_path)
                if fid != -1:
                    families = QFontDatabase.applicationFontFamilies(fid)
                    if families:
                        fname = os.path.basename(f_path).lower()
                        if "handel" in fname:
                            self._font_main = families[0]
                        elif "bebas" in fname:
                            self._font_bebas = families[0]
                        elif "trajan" in fname:
                            self._font_main = families[0]
                        else:
                            self._font_main = families[0]

    def _play_wheel_sound(self):
        """Reproduce el efecto de sonido táctil de giro o navegación de la ruleta."""
        if getattr(self, "_media_muted", False):
            return
        try:
            if self._sound_effect.source().isValid():
                self._sound_effect.play()
            else:
                if self.SOUND_NAV.is_file():
                    self._sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_NAV)))
                    self._sound_effect.play()
        except Exception:
            pass

    def _play_select_sound(self):
        """Reproduce el sonido característico de selección al activar o confirmar un juego."""
        if getattr(self, "_media_muted", False):
            return
        try:
            if self._select_sound_effect.source().isValid():
                self._select_sound_effect.play()
            else:
                if self.SOUND_SELECT.is_file():
                    self._select_sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_SELECT)))
                    self._select_sound_effect.play()
        except Exception:
            pass
    # -------------------------------------------------------------------------
    # CONTROLADORES DE ANIMACIÓN Y CINEMÁTICA
    # -------------------------------------------------------------------------

    def _on_pointer_tick(self):
        """Controla la animación de pulso y retracción del puntero indicador de selección."""
        self._pointer_anim_tick += 1
        diff = self._pointer_rest_x_ratio - self._pointer_current_x_ratio
        if abs(diff) > 0.0005:
            self._pointer_current_x_ratio += diff * 0.20
            self.update()
        else:
            self._pointer_current_x_ratio = self._pointer_rest_x_ratio
            if self._pointer_anim_tick % 2 == 0:
                self.update()

    def _on_avatar_bounce_tick(self):
        """Calcula el movimiento sinusoidal suave de flotación y oscilación del avatar o personaje decorativo."""
        self._avatar_anim_time += 0.04
        t = self._avatar_anim_time
        self._avatar_offset_x = math.sin(t * 0.9) * 8.0
        self._avatar_offset_y = (math.sin(t * 1.8) * 12.0) + (math.cos(t * 0.45) * 5.0)
        if self._pix_avatar:
            self.update()

    def _on_cd_spin_tick(self):
        """Gestiona la operación '_on_cd_spin_tick' de este layout temático."""
        self._cd_rotation_angle = (self._cd_rotation_angle + 1.2) % 360.0
        if self._cart_current_y_ratio <= 1.0:
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
        """Ejecuta la animación de descenso e inserción física del cartucho o rotación del disco en la consola."""
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
        """Reinicia la cinemática de inserción del cartucho/disco para el juego actual."""
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
        """Interpola la posición horizontal y opacidad de la carátula (boxart) hacia su posición final."""
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
        """Gestiona la operación '_ensure_player_initialized' de este layout temático."""
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
        """Supervisa el estado del reproductor y garantiza el bucle infinito automático del video snap."""
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
        """Recibe el frame decodificado desde QVideoSink y solicita el repintado del televisor CRT."""
        if frame.isValid() and getattr(self, "_want_video_playing", True) and self.player:
            p_path = getattr(self, "_pending_video_path", None)
            if p_path and self.player.source() != QUrl.fromLocalFile(p_path):
                return
            # Si la ruleta esta girando activamente, no extraer frames pesados por PCIe para mantener 60 FPS
            if hasattr(self, "_wheel_spin_timer") and self._wheel_spin_timer.isActive() and self._current_video_image is not None:
                return
            now = time.perf_counter()
            if now - getattr(self, "_last_video_frame_time", 0.0) < 0.033:  # Cap a 30 FPS para CRT
                return
            self._last_video_frame_time = now
            img = frame.toImage()
            if not img.isNull():
                self._current_video_image = img
                self.update()

    def _on_player_error(self, error, error_string=""):
        """Maneja errores de decodificación o códecs de video reintentando la carga o aplicando respaldo estático."""
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self._current_video_image = None

    def set_db(self, db):
        """Asocia la base de datos de RetroShelf para consultas de metadatos o emuladores."""
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
        """Silencia o reactiva el audio de los videos según las preferencias del usuario."""
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
        """Gestiona la operación 'set_muted' de este layout temático."""
        self.set_media_muted(muted)

    def is_muted(self) -> bool:
        """Gestiona la operación 'is_muted' de este layout temático."""
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

        cart_file = self.current_media.get("cartart") or self.current_media.get("discart") or game.get("cartart_path") or game.get("discart_path")
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
        """Carga en memoria las imágenes de carátula y cartucho sin bloquear el hilo principal de renderizado."""
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
            return
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
        # Preload adjacent boxart/cartart into cache for zero-lag immediate display
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
            cf = gmedia.get("cartart") or gmedia.get("discart")
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
        """Obtiene el QPixmap del logotipo de rueda, generando un reemplazo tipográfico si no posee imagen."""
        gid = game.get("id")
        if gid in self._wheel_pixmaps:
            return self._wheel_pixmaps[gid]

        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.queue_game(game, priority=True)

        return None

    def _get_target_rect(self) -> QRect:
        """Gestiona la operación '_get_target_rect' de este layout temático."""
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
        """Punto central de renderizado por capas: fondo, CRT, mueble/consola, artes, ruleta interactiva y puntero."""
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

            # Capa 1: Fondo temático de Atari Jaguar CD
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
            if self._pix_scanlines:
                painter.setOpacity(0.35)
                painter.drawPixmap(tv_rect, self._pix_scanlines)
                painter.setOpacity(1.0)

            # Capa 4: Marco exterior de la TV CRT
            if self._pix_tv:
                if getattr(self, "_cached_tv_size", None) != (sw, sh):
                    self._cached_tv_pix = self._pix_tv.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_tv_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_tv_pix)

            # Capa 5: Avatar (Mascota animada con rebote)
            self._draw_avatar(painter, sr)

            # Capa 6: Logotipo animado superior
            self._draw_logo(painter, sr)

            # Capa 7: Chasis de la Consola Atari Jaguar CD
            if self._pix_console:
                if getattr(self, "_cached_console_size", None) != (sw, sh):
                    self._cached_console_pix = self._pix_console.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_console_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_console_pix)

            # Capa 8: Tapa / Cubierta de consola (si la tuviese)
            if self._pix_console_cover:
                if getattr(self, "_cached_console_cover_size", None) != (sw, sh):
                    self._cached_console_cover_pix = self._pix_console_cover.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_console_cover_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_console_cover_pix)

            # Capa 9: Carátula del juego (Boxart)
            self._draw_boxart(painter, sr)

            # Capa 10: Disco CD girando a 60 FPS
            self._draw_cart_or_disc(painter, sr)

            # Capa 11: Joystick (si estuviese presente)
            if self._pix_joystick:
                if getattr(self, "_cached_joystick_size", None) != (sw, sh):
                    self._cached_joystick_pix = self._pix_joystick.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_joystick_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_joystick_pix)

            # Capa 12: Sombra / fondo de la ruleta (desde gtc-common)
            if self._pix_wheel_shadow:
                if getattr(self, "_cached_wheel_shadow_size", None) != (sw, sh):
                    self._cached_wheel_shadow_pix = self._pix_wheel_shadow.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_wheel_shadow_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_wheel_shadow_pix)

            # Capa 13: Ruleta curva interactiva
            if self.games:
                self._draw_wheel_conveyor(painter, sr)

            # Capa 14: Puntero selector de la ruleta (fiel a Attract-Mode)
            self._draw_pointer(painter, sr)

            # Capa 15: Barra inferior con título
            self._draw_bottom_bar(painter, sr)

        finally:
            painter.end()

    def _draw_avatar(self, painter: QPainter, sr: QRect):
        """Dibuja el personaje decorativo con su oscilación sinusoidal."""
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
        """Dibuja el logotipo del sistema o del juego con su escala y opacidad interpoladas."""
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
        """Renderiza el cartucho o disco físico simulando la inserción tridimensional en la consola."""
        sw, sh = sr.width(), sr.height()
        sx, sy = sr.x(), sr.y()

        cx, cy_ratio, cw, ch = self.CART_RECT
        disc_cx_abs = sx + int(sw * cx)
        disc_cy_abs = sy + int(sh * self._cart_current_y_ratio)
        disc_w = int(sw * cw)
        disc_h = int(sh * ch)

        disc_pix = getattr(self, "_current_cart_pixmap", None) if getattr(self, "_pending_cart_file", None) else self._pix_cartart_frame

        if disc_pix and not disc_pix.isNull():
            side = min(disc_w, disc_h)
            center_x = disc_cx_abs + disc_w // 2
            center_y = disc_cy_abs + disc_h // 2

            painter.save()
            if self._cart_anim_timer.isActive() and self._cart_anim_duration > 0:
                alpha_factor = min(1.0, max(0.0, self._cart_anim_elapsed / (self._cart_anim_duration * 0.6)))
                painter.setOpacity(alpha_factor)

            painter.translate(center_x, center_y)
            painter.rotate(self._cd_rotation_angle)
            painter.drawPixmap(QRect(-side // 2, -side // 2, side, side), disc_pix)
            painter.restore()

    def _draw_boxart(self, painter: QPainter, sr: QRect):
        """Dibuja la carátula del juego con sombreado y transición animada."""
        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        box_w = int(sw * self.BOXART_W)
        box_h = int(sh * self.BOXART_H)
        box_x = sx + int(sw * self.BOXART_X)

        box_pix = getattr(self, "_current_box_pixmap", None) if getattr(self, "_pending_box_file", None) else self._pix_boxart_frame
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
                box_y = sy + int(sh * getattr(self, "BOXART_Y", 0.53))
                draw_by = box_y + (box_h - dh) // 2

            painter.drawPixmap(QRect(draw_bx, draw_by, dw, dh), box_pix)
            painter.restore()

    def _draw_wheel_conveyor(self, painter: QPainter, sr: QRect):
        """Calcula la perspectiva curva en 14 nodos interpolando posición, escala, rotación y opacidad de cada logo."""
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

            dist_from_center = abs(pos - 7.0)
            is_selected = (dist_from_center < 0.5)

            item_w = int(sw * rw)
            item_h = int(sh * rh)
            item_cx = sx + int(sw * rx) + item_w // 2
            item_cy = sy + int(sh * ry) + item_h // 2

            painter.save()
            try:
                painter.translate(item_cx, item_cy)
                if angle != 0:
                    painter.rotate(angle)

                # Transparencia: 1.0 para el seleccionado, y un poco más de transparencia para los de arriba y abajo
                base_opacity = alpha / 255.0
                node_opacity = min(1.0, max(0.0, base_opacity if is_selected else base_opacity * 0.70))
                painter.setOpacity(node_opacity)

                rect = QRect(-item_w // 2, -item_h // 2, item_w, item_h)
                wheel_pix = self._get_game_wheel_pixmap(game)

                if wheel_pix and not wheel_pix.isNull():
                    pw = wheel_pix.width()
                    ph = wheel_pix.height()
                    # +20% más grande cuando está seleccionado
                    if is_selected:
                        max_w = int((item_w - 12) * 1.20)
                        max_h = int((item_h - 8) * 1.20)
                    else:
                        max_w = item_w - 12
                        max_h = item_h - 8
                    s = min(max_w / pw, max_h / ph) if pw > 0 and ph > 0 else 1.0
                    dw = int(pw * s)
                    dh = int(ph * s)
                    painter.drawPixmap(QRect(-dw // 2, -dh // 2, dw, dh), wheel_pix)
                else:
                    card_path = QPainterPath()
                    card_path.addRoundedRect(rect, 8, 8)
                    bg_col = QColor(180, 25, 25, 210) if is_selected else QColor(30, 20, 25, 180)
                    border_col = QColor(255, 255, 255, 220) if is_selected else QColor(100, 40, 45, 120)
                    painter.fillPath(card_path, bg_col)
                    painter.setPen(QPen(border_col, 2 if is_selected else 1))
                    painter.drawPath(card_path)

                    title = game.get("title") or "Juego"
                    painter.setPen(QColor(255, 255, 255))
                    f_size = max(11, int(item_h * 0.32))
                    f = QFont(self._font_main, f_size, QFont.Bold)
                    painter.setFont(f)
                    painter.drawText(rect.adjusted(8, 4, -8, -4), Qt.AlignCenter | Qt.TextWordWrap, title)
            finally:
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
        idle_oscillation = int(sw * (math.sin(self._pointer_anim_tick * 0.08) * 0.002))
        ptr_x = base_x - pulse_offset + idle_oscillation

        painter.save()
        painter.setOpacity(1.0)
        painter.drawPixmap(ptr_x, ptr_y, ptr_w, ptr_h, self._pix_pointer)
        painter.restore()

    def _draw_bottom_bar(self, painter: QPainter, sr: QRect):
        """Dibuja la barra inferior de metadatos con título, año, fabricante y contador de posición."""
        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        bar_h = int(sh * 0.075)
        bar_y = sy + sh - bar_h

        if self._pix_frame:
            painter.drawPixmap(sx, bar_y, sw, bar_h, self._pix_frame)
        else:
            painter.fillRect(QRect(sx, bar_y, sw, bar_h), QColor(15, 8, 10, 235))

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
        # Resalte en rojo Atari característico
        painter.setPen(QColor(235, 35, 35))
        counter_rect = QRect(sx + int(sw * 0.70), bar_y, int(sw * 0.25), bar_h)
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter_text)
    # -------------------------------------------------------------------------
    # MANEJO DE ENTRADAS (TECLADO, MOUSE, MANDOS)
    # -------------------------------------------------------------------------

    def keyPressEvent(self, event):
        """Captura la navegación por teclado (flechas, enter, espacio, retroceso, página, inicio, fin)."""
        from retroshelf.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        key = event.key()
        if matches_action(event, ACTION_NAV_UP):
            self._navigate_steps(-1)
            event.accept()
        elif matches_action(event, ACTION_NAV_DOWN):
            self._navigate_steps(1)
            event.accept()
        elif matches_action(event, ACTION_PAGE_UP):
            self._navigate_steps(-5)
            event.accept()
        elif matches_action(event, ACTION_PAGE_DOWN):
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
        """Permite interactuar mediante clics directos sobre los elementos de la interfaz."""
        from retroshelf.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        self.setFocus()
        if event.button() == Qt.LeftButton:
            sr = self._get_target_rect()
            sw = sr.width()
            sh = sr.height()
            sx = sr.x()
            sy = sr.y()

            pos = event.position()
            mx, my = pos.x(), pos.y()

            # Comprobar si se hizo click sobre algún ítem de la ruleta
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
        """Permite navegar fluidamente por la lista utilizando la rueda de desplazamiento del ratón."""
        from retroshelf.services.emulator_manager import EMULATOR_MANAGER
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
        """Pausa la multimedia y animaciones cuando el layout deja de ser visible para ahorrar CPU/GPU."""
        if self.player:
            self.player.pause()
        super().hideEvent(event)

    def showEvent(self, event):
        """Reanuda la reproducción y animación fluida al volver a enfocar este layout temático."""
        super().showEvent(event)
        self._start_logo_animation()

    def closeEvent(self, event):
        """Libera los hilos de precarga, temporizadores y reproductores al cerrar la ventana."""
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
