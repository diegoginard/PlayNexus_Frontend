"""
=============================================================================
Layout Autónomo: Sega Dreamcast
Generado sobre la Arquitectura Base Canónica de PlayNexus
=============================================================================
Este archivo es 100% autónomo y maneja la totalidad de su renderizado,
geometría, animaciones, fuentes tipográficas y ciclo de vida de multimedia.
Cumple rigurosamente con las directivas 4, 5, 6 y 8 de GEMINI.md.
"""
import os
import sys
import math
from pathlib import Path

from PySide6.QtCore import (
    Qt, QRect, QRectF, QPoint, QPointF, QTimer, QUrl, Signal
)
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QPixmap,
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
    LAYOUT_NAME = "Sega Dreamcast"
    LAYOUT_DESCRIPTION = "Layout temático interactivo oficial de Sega Dreamcast"

    CANONICAL_W = 1920
    CANONICAL_H = 1080

    # -------------------------------------------------------------------------
    # 1. REQUERIMIENTOS DE MEDIOS (DIRECTIVA 4 Y 8 DE GEMINI.md)
    # -------------------------------------------------------------------------
    MEDIA_REQUIREMENTS = [
        {
            'key': 'video',
            'label': 'Video Snaps',
            'extensions': ['.mp4', '.mkv', '.avi', '.webm'],
            'required': True
        },
        {
            'key': 'wheel',
            'label': 'Wheel Logos',
            'extensions': ['.png', '.webp'],
            'required': True
        },
        {
            'key': 'discart',
            'label': 'Discos / CDs',
            'extensions': ['.png', '.webp'],
            'required': False
        },
        {
            'key': 'boxart',
            'label': 'Box Art / Cajas',
            'extensions': ['.png', '.jpg', '.jpeg', '.webp'],
            'required': False
        },
    ]

    # -------------------------------------------------------------------------
    # 2. FUENTES TIPOGRÁFICAS DEL TEMA (DIRECTIVA 8 DE GEMINI.md)
    # -------------------------------------------------------------------------
    FONT_TITLE_FILE = "BebasNeue Bold.otf"   # Títulos destacados
    FONT_MAIN_FILE  = "Handel Gothic BT.ttf"     # Textos generales e información técnica
    FONT_FILES = [FONT_TITLE_FILE, FONT_MAIN_FILE]

    # -------------------------------------------------------------------------
    # 3. RECURSOS COMPARTIDOS (gtc-common) Y LOCALES (DIRECTIVA 8 DE GEMINI.md)
    # -------------------------------------------------------------------------
    # Compartidos desde gtc-common
    WHEEL_SHADOW_IMAGE = COMMON_DIR / "wheel" / "wheel_shadow.png"
    COMMON_WHEEL_ART   = COMMON_DIR / "art" / "wheel_art.png"
    COMMON_FRAME       = COMMON_DIR / "art" / "frame.png"
    STATIC_VIDEO       = COMMON_DIR / "videos" / "static.mp4"
    SOUND_NAV          = COMMON_DIR / "sounds" / "joystick.mp3"
    SOUND_SELECT       = COMMON_DIR / "sounds" / "Mame_coin.mp3"
    SCANLINES_IMAGE    = COMMON_DIR / "art" / "scanlines_1920.png"
    SCRATCHES_IMAGE    = COMMON_DIR / "art" / "arcade" / "scratched_cover.png"

    # Recursos propios locales del layout
    BKG_IMAGE = LAYOUT_DIR / "bg.jpg" if (LAYOUT_DIR / "bg.jpg").is_file() else None
    TV_IMAGE = LAYOUT_DIR / "tv.png" if (LAYOUT_DIR / "tv.png").is_file() else None
    CONSOLE_IMAGE = LAYOUT_DIR / "console.png" if (LAYOUT_DIR / "console.png").is_file() else None
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png" if (LAYOUT_DIR / "console_cover.png").is_file() else None
    JOYSTICK_IMAGE = LAYOUT_DIR / "" if (LAYOUT_DIR / "").is_file() else None
    AVATAR_IMAGE = LAYOUT_DIR / "avatar.png" if (LAYOUT_DIR / "avatar.png").is_file() else None
    LOGO_IMAGE = LAYOUT_DIR / "logo.png" if (LAYOUT_DIR / "logo.png").is_file() else None
    DISCART_IMAGE = LAYOUT_DIR / "discart.png" if (LAYOUT_DIR / "discart.png").is_file() else (LAYOUT_DIR / "discart.png" if (LAYOUT_DIR / "discart.png").is_file() else None)
    CARTART_IMAGE = DISCART_IMAGE
    BOXART_IMAGE = LAYOUT_DIR / "boxart.png" if (LAYOUT_DIR / "boxart.png").is_file() else None
    WHEEL_IMAGE = LAYOUT_DIR / "wheel.png" if (LAYOUT_DIR / "wheel.png").is_file() else None
    POINTER_IMAGE = (LAYOUT_DIR / "pointers" / "default.png") if (LAYOUT_DIR / "pointers" / "default.png").is_file() else ((LAYOUT_DIR / "default.png") if (LAYOUT_DIR / "default.png").is_file() else None)

    # -------------------------------------------------------------------------
    # 4. CONFIGURACIÓN GEOMÉTRICA Y MÉTRICAS (DIRECTIVA 8 DE GEMINI.md)
    # -------------------------------------------------------------------------
    # Pantalla CRT o monitor LCD: (x, y, w, h) en ratios de pantalla canónica (1920x1080)
    TV_RECT = (0.054, 0.196, 0.313, 0.43)

    # Disco CD giratorio al lado de la carátula
    CART_RECT = (0.550, 0.600, 0.190, 0.300)
    CART_END_Y = 0.600
    IS_CD = True

    # Carátula (Boxart) al lado del CD (10% más chica)
    BOXART_X = 0.400
    BOXART_Y = 0.530
    BOXART_W = 0.165
    BOXART_H = 0.410
    BOXART_ANCHOR = "center"

    # Avatar y Logo
    AVATAR_SCALE = 1.0
    AVATAR_X = 0.0
    AVATAR_Y = 0.0
    AVATAR_Y_ADJUST = 0
    LOGO_SCALE = 1.0

    # Ruleta Curva Conveyor (14 nodos a 60 FPS)
    CONVEYOR_X = [0.89, 0.85, 0.83, 0.80, 0.77, 0.74, 0.71, 0.625, 0.71, 0.74, 0.77, 0.80, 0.83, 0.89]
    CONVEYOR_Y = [-0.34, -0.22, -0.105, 0.00, 0.105, 0.215, 0.325, 0.421, 0.59, 0.70, 0.81, 0.915, 0.99, 1.12]
    CONVEYOR_W = [0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.30, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18]
    CONVEYOR_H = [0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.186, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
    CONVEYOR_R = [35.0, 30.0, 25.0, 20.0, 15.0, 10.0, 5.0, 0.0, -10.0, -15.0, -20.0, -25.0, -30.0, -35.0]
    CONVEYOR_A = [0, 20, 35, 60, 90, 125, 160, 255, 160, 125, 90, 60, 35, 0]

    def __init__(self, theme_name: str = "Sega Dreamcast", parent=None):
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

        # Efectos de sonido desde gtc-common
        self._sound_effect = QSoundEffect(self)
        self._sound_effect.setVolume(0.4)
        if self.SOUND_NAV.is_file():
            self._sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_NAV)))

        self._select_sound_effect = QSoundEffect(self)
        self._select_sound_effect.setVolume(0.5)
        if self.SOUND_SELECT.is_file():
            self._select_sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_SELECT)))

        # Precargar imágenes
        bkg_cand = str(self.BKG_IMAGE) if self.BKG_IMAGE and self.BKG_IMAGE.is_file() else None
        self._pix_bkg = self._load_pixmap(bkg_cand) if bkg_cand else None
        self._pix_tv = self._load_pixmap(str(self.TV_IMAGE)) if self.TV_IMAGE and self.TV_IMAGE.is_file() else None
        self._pix_console = self._load_pixmap(str(self.CONSOLE_IMAGE)) if self.CONSOLE_IMAGE and self.CONSOLE_IMAGE.is_file() else None
        self._pix_console_cover = self._load_pixmap(str(self.CONSOLE_COVER_IMAGE)) if self.CONSOLE_COVER_IMAGE and self.CONSOLE_COVER_IMAGE.is_file() else None
        self._pix_joystick = self._load_pixmap(str(self.JOYSTICK_IMAGE)) if self.JOYSTICK_IMAGE and self.JOYSTICK_IMAGE.is_file() else None

        self._pix_avatar = self._load_pixmap(str(self.AVATAR_IMAGE)) if self.AVATAR_IMAGE and self.AVATAR_IMAGE.is_file() else None
        self._pix_logo = self._load_pixmap(str(self.LOGO_IMAGE)) if self.LOGO_IMAGE and self.LOGO_IMAGE.is_file() else None
        self._pix_discart_frame = self._load_pixmap(str(self.DISCART_IMAGE)) if self.DISCART_IMAGE and self.DISCART_IMAGE.is_file() else None
        self._pix_cartart_frame = self._pix_discart_frame or (self._load_pixmap(str(self.CARTART_IMAGE)) if self.CARTART_IMAGE and self.CARTART_IMAGE.is_file() else None)
        self._pix_boxart_frame = self._load_pixmap(str(self.BOXART_IMAGE)) if self.BOXART_IMAGE and self.BOXART_IMAGE.is_file() else None

        # Recursos compartidos
        self._pix_scanlines = None
        self._pix_wheel_art = self._load_pixmap(str(self.COMMON_WHEEL_ART))
        self._pix_frame = self._load_pixmap(str(self.COMMON_FRAME))
        self._pix_scratches = self._load_pixmap(str(self.SCRATCHES_IMAGE))
        self._static_video_path = str(self.STATIC_VIDEO) if self.STATIC_VIDEO.is_file() else None
        self._pix_wheel_shadow = self._load_pixmap(str(self.WHEEL_SHADOW_IMAGE)) if self.WHEEL_SHADOW_IMAGE and self.WHEEL_SHADOW_IMAGE.is_file() else None

        pointer_path = str(self.POINTER_IMAGE) if self.POINTER_IMAGE and self.POINTER_IMAGE.is_file() else None
        self._pix_pointer = self._load_pixmap(pointer_path)
        self._pix_wheel = self._load_pixmap(str(self.WHEEL_IMAGE)) if self.WHEEL_IMAGE and self.WHEEL_IMAGE.is_file() else None

        # Diccionario theme_info
        self.theme_info = {
            "name": self.theme_name,
            "folder": str(LAYOUT_DIR),
            "bg": str(self.BKG_IMAGE),
            "tv": str(self.TV_IMAGE) if self.TV_IMAGE else None,
            "console": str(self.CONSOLE_IMAGE) if self.CONSOLE_IMAGE else None,
            "console_cover": str(self.CONSOLE_COVER_IMAGE) if self.CONSOLE_COVER_IMAGE else None,
            "joystick": str(self.JOYSTICK_IMAGE) if self.JOYSTICK_IMAGE else None,
            "avatar": str(self.AVATAR_IMAGE) if self.AVATAR_IMAGE else None,
            "character": str(self.AVATAR_IMAGE) if self.AVATAR_IMAGE else None,
            "logo": str(self.LOGO_IMAGE) if self.LOGO_IMAGE else None,
            "discart": str(self.DISCART_IMAGE) if self.DISCART_IMAGE else None,
            "boxart": str(self.BOXART_IMAGE) if self.BOXART_IMAGE else None,
            "wheel_shadow": str(self.WHEEL_SHADOW_IMAGE) if self.WHEEL_SHADOW_IMAGE else None,
            "wheel": str(self.WHEEL_IMAGE) if self.WHEEL_IMAGE else None,
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

        # Efecto de rotación continua 360° del CD
        self._cd_rotation_angle = 0.0
        self._cd_spin_timer = QTimer(self)
        self._cd_spin_timer.timeout.connect(self._on_cd_spin_tick)
        self._cd_spin_timer.start(16)

        self._wheel_spin_timer = QTimer(self)
        self._wheel_spin_timer.timeout.connect(self._on_wheel_spin_tick)

        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(180)
        self._commit_timer.timeout.connect(self._commit_selection)

        self._avatar_anim_time = 0.0
        self._avatar_offset_x = 0.0
        self._avatar_offset_y = 0.0
        self._avatar_bounce_timer = QTimer(self)
        self._avatar_bounce_timer.timeout.connect(self._on_avatar_bounce_tick)
        self._avatar_bounce_timer.start(20)

        self._cart_anim_timer = QTimer(self)
        self._cart_anim_timer.timeout.connect(self._on_cart_anim_tick)
        self._cart_anim_elapsed = 0
        self._cart_anim_duration = 200
        self._cart_current_y = self.CART_END_Y
        self._cart_start_y = -0.30

        self._logo_anim_timer = QTimer(self)
        self._logo_anim_timer.timeout.connect(self._on_logo_anim_tick)
        self._logo_anim_elapsed = 0
        self._logo_anim_duration = 300
        self._logo_current_y_offset_ratio = 0.0

        self._boxart_slide_offset = 0.0
        self._boxart_alpha = 255.0
        self._boxart_anim_timer = QTimer(self)
        self._boxart_anim_timer.timeout.connect(self._on_boxart_anim_tick)
        self._boxart_anim_elapsed = 0
        self._boxart_anim_duration = 260

        self._nav_key_pressed = False
        self._nav_pending_commit = False
        self._key_released_waiting_rest = False
        self._pending_video_path = None
        self._want_video_playing = False
        self._is_emulator_running = False

        self._video_debounce_timer = QTimer(self)
        self._video_debounce_timer.setSingleShot(True)
        self._video_debounce_timer.setInterval(220)
        self._video_debounce_timer.timeout.connect(self._play_debounced_video)

        self._video_watchdog_timer = QTimer(self)
        self._video_watchdog_timer.setInterval(1000)
        self._video_watchdog_timer.timeout.connect(self._on_video_watchdog_tick)

        self._font_title = "Segoe UI"
        self._font_main = "Segoe UI"
        self._load_fonts()

        self._cached_bkg_size = None
        self._cached_bkg_pixmap = None
        self._mouse_press_pos = None

    def _load_fonts(self):
        """Carga las fuentes tipográficas del layout."""
        for font_file in getattr(self, "FONT_FILES", []):
            if font_file:
                fp = LAYOUT_DIR / font_file
                if fp.is_file():
                    fid = QFontDatabase.addApplicationFont(str(fp))
                    if fid >= 0:
                        fams = QFontDatabase.applicationFontFamilies(fid)
                        if fams:
                            if font_file == self.FONT_TITLE_FILE:
                                self._font_title = fams[0]
                            else:
                                self._font_main = fams[0]

    def _load_pixmap(self, path: str | None) -> QPixmap | None:
        """Carga un QPixmap estático en memoria."""
        if not path or not os.path.isfile(path):
            return None
        pix = QPixmap(path)
        return pix if not pix.isNull() else None

    def _on_wheel_image_loaded(self, game_id: int, qimage: QImage):
        """Callback cuando WheelPreloadWorker escala un logo en segundo plano."""
        if not qimage.isNull():
            self._wheel_pixmaps[game_id] = QPixmap.fromImage(qimage)
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

    def _on_wheel_spin_tick(self):
        diff = self._wheel_target_offset - self._wheel_offset
        if abs(diff) < 0.01:
            self._wheel_offset = self._wheel_target_offset
            self._wheel_spin_timer.stop()
        else:
            self._wheel_offset += diff * 0.35
        self.update()

    def _on_avatar_bounce_tick(self):
        self._avatar_anim_time += 0.04
        t = self._avatar_anim_time
        self._avatar_offset_x = math.sin(t * 0.9) * 8.0
        self._avatar_offset_y = (math.sin(t * 1.8) * 12.0) + (math.cos(t * 0.45) * 4.0)
        self.update()

    def _on_cart_anim_tick(self):
        self._cart_anim_elapsed += 16
        prog = min(1.0, self._cart_anim_elapsed / max(1, self._cart_anim_duration))
        ease = 1.0 - (1.0 - prog) ** 3
        self._cart_current_y = self._cart_start_y + (self.CART_END_Y - self._cart_start_y) * ease
        if prog >= 1.0:
            self._cart_current_y = self.CART_END_Y
            self._cart_anim_timer.stop()
        self.update()

    def _on_cd_spin_tick(self):
        """Avanza la rotación continua a 360° del disco CD."""
        self._cd_rotation_angle = (self._cd_rotation_angle + 1.152) % 360.0
        self.update()

    def _on_logo_anim_tick(self):
        self._logo_anim_elapsed += 16
        prog = min(1.0, self._logo_anim_elapsed / max(1, self._logo_anim_duration))
        self._logo_current_y_offset_ratio = math.sin(prog * math.pi) * -0.025
        if prog >= 1.0:
            self._logo_current_y_offset_ratio = 0.0
            self._logo_anim_timer.stop()
        self.update()

    def _on_boxart_anim_tick(self):
        self._boxart_anim_elapsed += 16
        prog = min(1.0, self._boxart_anim_elapsed / max(1, self._boxart_anim_duration))
        ease = 1.0 - (1.0 - prog) ** 3
        self._boxart_slide_offset = -0.15 * (1.0 - ease)
        self._boxart_alpha = 255.0 * prog
        if prog >= 1.0:
            self._boxart_slide_offset = 0.0
            self._boxart_alpha = 255.0
            self._boxart_anim_timer.stop()
        self.update()

    def _init_player(self):
        """Inicializa de forma diferida el reproductor QMediaPlayer."""
        if self._player_initialized:
            return
        self._player_initialized = True
        self.player = QMediaPlayer(self)
        self.player.setLoops(QMediaPlayer.Infinite)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setMuted(self._media_muted)
        self.audio_output.setVolume(0.0 if self._media_muted else 0.8)
        self.video_sink = QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self.player.setVideoSink(self.video_sink)
        self.player.mediaStatusChanged.connect(self._on_video_media_status_changed)

    def _on_video_frame_changed(self, frame):
        if not self._want_video_playing or not self.isVisible() or self._is_emulator_running:
            return
        if frame.isValid():
            img = frame.toImage()
            if not img.isNull():
                self._current_video_image = img
                self.update()

    def _on_video_media_status_changed(self, status):
        if not self.isVisible() or self._is_emulator_running:
            return
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferingMedia, QMediaPlayer.BufferedMedia):
            if getattr(self, "_want_video_playing", False) and self.isVisible():
                if self.audio_output:
                    self.audio_output.setVolume(0.0 if self._media_muted else 0.8)
                if self.player.playbackState() != QMediaPlayer.PlayingState:
                    self.player.play()
        elif status == QMediaPlayer.EndOfMedia:
            if getattr(self, "_want_video_playing", False) and self.isVisible():
                self.player.setPosition(0)
                self.player.play()

    def _on_video_watchdog_tick(self):
        if not self._want_video_playing or not self.isVisible() or not self._pending_video_path or self._is_emulator_running:
            return
        if not self.player:
            return
        if self._current_video_image is None or self.player.playbackState() != QMediaPlayer.PlayingState:
            try:
                src_url = QUrl.fromLocalFile(self._pending_video_path)
                if self.player.source() != src_url:
                    self.player.setSource(src_url)
                self.player.play()
            except Exception:
                pass

    def _play_game_video(self, video_path: str):
        if self._is_emulator_running:
            return
        self._init_player()
        self._pending_video_path = video_path
        self._want_video_playing = True
        self._video_debounce_timer.stop()
        self._video_debounce_timer.start()

    def _play_debounced_video(self):
        if not self._want_video_playing or not self._pending_video_path or not self.isVisible() or self._is_emulator_running:
            return
        try:
            source_url = QUrl.fromLocalFile(self._pending_video_path)
            if self.player.source() == source_url:
                if self.player.playbackState() != QMediaPlayer.PlayingState:
                    self.player.play()
            else:
                self.player.setSource(source_url)
                self.player.play()
            if self.audio_output:
                self.audio_output.setMuted(self._media_muted)
                self.audio_output.setVolume(0.0 if self._media_muted else 0.8)
            if not self._video_watchdog_timer.isActive():
                self._video_watchdog_timer.start()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # CONTROL DE CICLO DE VIDA (DIRECTIVA 5 Y REGLAS DE SEGURIDAD)
    # -------------------------------------------------------------------------
    def stop_media(self):
        """Detiene completamente la reproducción multimedia."""
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

    def set_media_muted(self, muted: bool):
        self._media_muted = muted
        if hasattr(self, "_sound_effect") and self._sound_effect:
            self._sound_effect.setMuted(muted)
        if hasattr(self, "_select_sound_effect") and self._select_sound_effect:
            self._select_sound_effect.setMuted(muted)
        if self.audio_output:
            self.audio_output.setMuted(muted)
            self.audio_output.setVolume(0.0 if muted else 0.8)

    def cleanup(self):
        """Libera de forma segura y síncrona el worker de pre-carga y temporizadores antes de la destrucción."""
        self.stop_media()
        for timer_name in (
            "_wheel_spin_timer", "_avatar_anim_timer", "_logo_anim_timer",
            "_pointer_anim_timer", "_cart_anim_timer", "_boxart_anim_timer",
            "_cd_spin_timer",
            "_commit_timer", "_video_debounce_timer", "_video_watchdog_timer",
            "_studio_anim_timer"
        ):
            if hasattr(self, timer_name):
                try:
                    getattr(self, timer_name).stop()
                except Exception:
                    pass
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            try:
                self._wheel_worker.stop()
                self._wheel_worker.wait(120)
            except Exception:
                pass
        super().cleanup()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # GESTIÓN Y CARGA DE JUEGOS
    # -------------------------------------------------------------------------
    def set_games(self, games: list):
        self.games = [dict(g) if hasattr(g, "keys") else g for g in games]
        self._wheel_pixmaps.clear()
        if hasattr(self, '_wheel_worker') and self._wheel_worker:
            self._wheel_worker.clear()
        if self.games:
            self._update_current_selection()
            self._start_animations()
        self.update()

    def _start_animations(self):
        self._cart_anim_elapsed = 0
        self._cart_anim_timer.start(16)
        self._logo_anim_elapsed = 0
        self._logo_anim_timer.start(16)
        self._boxart_anim_elapsed = 0
        self._boxart_anim_timer.start(16)

    def select_game_by_id(self, game_id: int):
        for idx, g in enumerate(self.games):
            if g.get("id") == game_id:
                if self.selected_index != idx:
                    self.selected_index = idx
                    self._update_current_selection()
                    self._start_animations()
                    self.update()
                break

    def get_selected_game_id(self) -> int | None:
        if self.games and 0 <= self.selected_index < len(self.games):
            return self.games[self.selected_index].get("id")
        return None

    def _update_current_selection(self):
        if not self.games:
            return
        g = self.games[self.selected_index]
        self.current_media = resolve_game_media(g)
        # Cargar arte de cartucho o disco
        c_path = self.current_media.get("discart") or self.current_media.get("cartart") or g.get("discart") or g.get("cartart") or g.get("discart_path") or g.get("cartart_path")
        self._current_cart_pixmap = self._load_pixmap(c_path) if c_path else None
        # Cargar boxart de forma directa y segura con self._load_pixmap
        b_path = self.current_media.get("boxart") or g.get("boxart") or g.get("cover_path") or g.get("boxart_path")
        self._current_box_pixmap = self._load_pixmap(b_path) if b_path else None
        # Encolar video
        v_path = self.current_media.get("video")
        if v_path and os.path.isfile(v_path):
            self._play_game_video(v_path)
        else:
            self.stop_media()
        self._preload_wheel_window()

    def _get_game_wheel_pixmap(self, game: dict) -> QPixmap | None:
        """Obtiene el QPixmap del logotipo de rueda, consultando la caché o encolando en el worker."""
        gid = game.get("id")
        if gid in self._wheel_pixmaps:
            return self._wheel_pixmaps[gid]

        wheel_file = game.get("wheel") or game.get("wheel_path") or (self.current_media.get("wheel") if gid == self.get_selected_game_id() else None)
        if wheel_file and os.path.isfile(wheel_file):
            pix = self._load_pixmap(wheel_file)
            if pix and not pix.isNull():
                self._wheel_pixmaps[gid] = pix
                return pix

        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.queue_game(game, priority=True)

        return None

    def _preload_wheel_window(self):
        if not self.games or not hasattr(self, "_wheel_worker") or not self._wheel_worker:
            return
        n = len(self.games)
        window = [self.games[(self.selected_index + off) % n] for off in range(-7, 8)]
        self._wheel_worker.queue_games(window, priority=True)

    def _commit_selection(self):
        """Emite game_selected tras el debounce al soltar tecla o temporizador (Directiva 5)."""
        self._nav_pending_commit = False
        gid = self.get_selected_game_id()
        if gid:
            self._update_current_selection()
            self._start_animations()
            self.game_selected.emit(gid)

    # -------------------------------------------------------------------------
    # NAVEGACIÓN Y EVENTOS (DIRECTIVA 5: COMMIT ON RELEASE / MOUSE)
    # -------------------------------------------------------------------------
    def _navigate_steps(self, steps: int):
        if not self.games:
            return
        self.selected_index = (self.selected_index + steps) % len(self.games)
        if hasattr(self, "_sound_effect") and self._sound_effect and not self._media_muted:
            self._sound_effect.play()
        self._wheel_target_offset = 0.0
        self._wheel_offset = float(-steps)
        self._pointer_current_x_ratio = self._pointer_pulse_x_ratio
        if not self._wheel_spin_timer.isActive():
            self._wheel_spin_timer.start(16)
        self.update()

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            self._nav_key_pressed = True
            if matches_action(event, ACTION_NAV_UP):
                self._navigate_steps(-1)
                event.accept()
                return
            elif matches_action(event, ACTION_NAV_DOWN):
                self._navigate_steps(1)
                event.accept()
                return
        if matches_action(event, ACTION_NAV_UP):
            self._nav_key_pressed = True
            self._navigate_steps(-1)
            self._commit_timer.stop()
            self._commit_timer.start(180)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_DOWN):
            self._nav_key_pressed = True
            self._navigate_steps(1)
            self._commit_timer.stop()
            self._commit_timer.start(180)
            event.accept()
            return
        elif matches_action(event, ACTION_PAGE_UP):
            self._navigate_steps(-5)
            self._commit_timer.stop()
            self._commit_timer.start(180)
            event.accept()
            return
        elif matches_action(event, ACTION_PAGE_DOWN):
            self._navigate_steps(5)
            self._commit_timer.stop()
            self._commit_timer.start(180)
            event.accept()
            return
        elif matches_action(event, ACTION_SELECT):
            gid = self.get_selected_game_id()
            if gid:
                if hasattr(self, "_select_sound_effect") and self._select_sound_effect and not self._media_muted:
                    self._select_sound_effect.play()
                self.game_activated.emit(gid)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_BACK):
            self.nav_back_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self._nav_key_pressed = False
            self._commit_timer.stop()
            self._commit_selection()
        super().keyReleaseEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self._navigate_steps(-1)
        elif delta < 0:
            self._navigate_steps(1)
        self._commit_timer.stop()
        self._commit_timer.start(180)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._mouse_press_pos = event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Interacción con Mouse: commit y activación única y exclusivamente al soltar (Directiva 5)."""
        if event.button() == Qt.LeftButton and self._mouse_press_pos is not None:
            dy = event.pos().y() - self._mouse_press_pos.y()
            self._mouse_press_pos = None
            if abs(dy) < 15:
                # Clic sin arrastre
                gid = self.get_selected_game_id()
                if gid:
                    if hasattr(self, "_select_sound_effect") and self._select_sound_effect and not self._media_muted:
                        self._select_sound_effect.play()
                    self.game_activated.emit(gid)
            elif dy < -25:
                self._navigate_steps(1)
                self._commit_selection()
            elif dy > 25:
                self._navigate_steps(-1)
                self._commit_selection()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------------------
    # RENDERIZADO Y DIBUJADO A 60 FPS (DIRECTIVA 6)
    # -------------------------------------------------------------------------
    def _get_target_rect(self) -> QRect:
        w, h = self.width(), self.height()
        target_aspect = self.CANONICAL_W / self.CANONICAL_H
        current_aspect = w / h if h > 0 else target_aspect
        if current_aspect > target_aspect:
            sw = int(h * target_aspect)
            sx = (w - sw) // 2
            return QRect(sx, 0, sw, h)
        else:
            sh = int(w / target_aspect)
            sy = (h - sh) // 2
            return QRect(0, sy, w, sh)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))
        sr = self._get_target_rect()
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        rx = sw / self.CANONICAL_W
        ry = sh / self.CANONICAL_H

        # Capa 0: Fondo
        if self._pix_bkg:
            painter.drawPixmap(sx, sy, sw, sh, self._pix_bkg)

        # Capa 1: Video Snap / CRT
        tv_x = sx + int(self.TV_RECT[0] * sw)
        tv_y = sy + int(self.TV_RECT[1] * sh)
        tv_w = int(self.TV_RECT[2] * sw)
        tv_h = int(self.TV_RECT[3] * sh)
        if self._current_video_image:
            painter.drawImage(QRect(tv_x, tv_y, tv_w, tv_h), self._current_video_image)
        elif self._pix_frame:
            painter.drawPixmap(QRect(tv_x, tv_y, tv_w, tv_h), self._pix_frame)

        # Capa 2: Scanlines y Reflejo CRT
        if self._pix_scratches:
            painter.drawPixmap(QRect(tv_x, tv_y, tv_w, tv_h), self._pix_scratches)

        # Capa 3: TV Bezel / Mueble
        if self._pix_tv:
            if self._pix_tv.width() >= 1200:
                painter.drawPixmap(sx, sy, sw, sh, self._pix_tv)
            else:
                painter.drawPixmap(sx + int(0.02 * sw), sy + int(0.18 * sh), int(0.38 * sw), int(0.55 * sh), self._pix_tv)

        # Capa 4: Avatar animado
        self._draw_avatar(painter, sr)

        # Capa 5: Consola
        if self._pix_console:
            if self._pix_console.width() >= 1200:
                painter.drawPixmap(sx, sy, sw, sh, self._pix_console)
            else:
                painter.drawPixmap(sx + int(0.38 * sw), sy + int(0.60 * sh), int(0.32 * sw), int(0.35 * sh), self._pix_console)

        # Capa 6: Cartucho / Disco animado
        self._draw_cart_or_disc(painter, sr)

        # Capa 7: Tapa de consola
        if self._pix_console_cover:
            painter.drawPixmap(sx + int(0.40 * sw), sy + int(0.62 * sh), int(0.28 * sw), int(0.20 * sh), self._pix_console_cover)

        # Capa 8: Carátula (Boxart)
        self._draw_boxart(painter, sr)

        # Capa 9: Logo del sistema
        self._draw_logo(painter, sr)

        # Capa 10: Sombra de Ruleta
        if self._pix_wheel_shadow:
            painter.drawPixmap(sx + int(0.65 * sw), sy, int(0.35 * sw), sh, self._pix_wheel_shadow)

        # Capa 11: Ruleta Curva Conveyor
        self._draw_wheel_conveyor(painter, sr)

        # Capa 12: Puntero
        self._draw_pointer(painter, sr)

        # Capa 13: Barra Inferior HUD
        self._draw_bottom_bar(painter, sr)
        painter.end()

    def _draw_cart_or_disc(self, painter: QPainter, sr: QRect):
        sw, sh = sr.width(), sr.height()
        sx, sy = sr.x(), sr.y()

        cx, cy_ratio, cw, ch = getattr(self, "DISC_RECT", getattr(self, "CART_RECT", (0.550, 0.600, 0.190, 0.300)))
        disc_cx_abs = sx + int(sw * cx)
        disc_cy_abs = sy + int(sh * getattr(self, "_cart_current_y", cy_ratio))
        disc_w = int(sw * cw)
        disc_h = int(sh * ch)

        disc_pix = getattr(self, "_current_disc_pixmap", None) or getattr(self, "_current_cart_pixmap", None) or getattr(self, "_pix_discart_frame", None) or getattr(self, "_pix_cartart_frame", None)

        if disc_pix and not disc_pix.isNull():
            side = min(disc_w, disc_h)
            center_x = disc_cx_abs + disc_w // 2
            center_y = disc_cy_abs + disc_h // 2

            painter.save()
            painter.translate(center_x, center_y)
            painter.rotate(getattr(self, "_cd_rotation_angle", 0.0))
            painter.drawPixmap(QRect(-side // 2, -side // 2, side, side), disc_pix)
            painter.restore()

    def _draw_boxart(self, painter: QPainter, sr: QRect):
        box_pix = getattr(self, "_current_box_pixmap", None) or getattr(self, "_pix_boxart_frame", None)
        if not box_pix or box_pix.isNull():
            return
        sw, sh = sr.width(), sr.height()
        sx, sy = sr.x(), sr.y()

        box_w = int(sw * self.BOXART_W)
        box_h = int(sh * self.BOXART_H)
        box_x = sx + int(sw * self.BOXART_X)

        pw = box_pix.width()
        ph = box_pix.height()
        s = min(box_w / pw, box_h / ph) if pw > 0 and ph > 0 else 1.0
        dw = int(pw * s)
        dh = int(ph * s)

        box_x_offset = int(sw * getattr(self, "_boxart_slide_offset", 0.0))
        draw_x = box_x + (box_w - dw) // 2 + box_x_offset
        if getattr(self, "BOXART_ANCHOR", "bottom") == "center":
            box_y = sy + int(sh * self.BOXART_Y)
            draw_y = box_y + (box_h - dh) // 2
        else:
            bottom_y = sy + int(sh * getattr(self, "BOXART_BOTTOM_Y", 0.95))
            draw_y = bottom_y - dh
        painter.save()
        painter.setOpacity(getattr(self, "_boxart_alpha", 255) / 255.0)
        painter.drawPixmap(QRect(draw_x, draw_y, dw, dh), box_pix)
        painter.restore()

    def _draw_avatar(self, painter: QPainter, sr: QRect):
        if not self._pix_avatar:
            return
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        rx = sw / self.CANONICAL_W
        ry = sh / self.CANONICAL_H
        if self._pix_avatar.width() >= 1200:
            ax = sx + int(self._avatar_offset_x * rx)
            ay = sy + int(self._avatar_offset_y * ry)
            painter.drawPixmap(ax, ay, sw, sh, self._pix_avatar)
        else:
            ax = sx + int((0.68 + self.AVATAR_X) * sw + self._avatar_offset_x * rx)
            ay = sy + int((0.08 + self.AVATAR_Y) * sh + self._avatar_offset_y * ry)
            aw = int(0.25 * sw * self.AVATAR_SCALE)
            ah = int(0.50 * sh * self.AVATAR_SCALE)
            painter.drawPixmap(ax, ay, aw, ah, self._pix_avatar)

    def _draw_logo(self, painter: QPainter, sr: QRect):
        if not self._pix_logo:
            return
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        if self._pix_logo.width() >= 1200:
            painter.drawPixmap(sx, sy, sw, sh, self._pix_logo)
        else:
            lx = sx + int(0.04 * sw)
            ly = sy + int((0.02 + self._logo_current_y_offset_ratio) * sh)
            lw = int(0.35 * sw * self.LOGO_SCALE)
            lh = int(0.18 * sh * self.LOGO_SCALE)
            painter.drawPixmap(lx, ly, lw, lh, self._pix_logo)

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

        # Pulso elástico al cambiar de juego + micro oscilación en reposo sincronizada con Atari Jaguar (8.0 rad/s, 18px)
        pulse_offset = int(sw * (self._pointer_rest_x_ratio - self._pointer_current_x_ratio))
        idle_oscillation = int(sw * (math.sin(self._pointer_anim_tick * (8.0 / 60.0)) * 0.009375))
        ptr_x = base_x - pulse_offset + idle_oscillation

        painter.save()
        painter.setOpacity(1.0)
        painter.drawPixmap(ptr_x, ptr_y, ptr_w, ptr_h, self._pix_pointer)
        painter.restore()

    def _draw_wheel_conveyor(self, painter: QPainter, sr: QRect):
        if not self.games:
            return
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        n = len(self.games)
        center_node = 7

        for i in range(len(self.CONVEYOR_X)):
            slot_idx = i - center_node
            game_idx = (self.selected_index + slot_idx) % n
            game = self.games[game_idx]

            alpha = self.CONVEYOR_A[i]
            if alpha <= 0:
                continue

            nx = sx + int(self.CONVEYOR_X[i] * sw)
            ny = sy + int(self.CONVEYOR_Y[i] * sh)
            nw = int(self.CONVEYOR_W[i] * sw)
            nh = int(self.CONVEYOR_H[i] * sh)
            rot = self.CONVEYOR_R[i]
            is_selected = (i == center_node)

            # Prioridad de logo: 1) Wheel propio de la ROM, 2) wheel.png del layout, 3) wheel_art de gtc-common
            pix = self._get_game_wheel_pixmap(game) or getattr(self, "_pix_wheel", None) or self._pix_wheel_art

            painter.save()
            painter.setOpacity(alpha / 255.0)
            painter.translate(nx + nw / 2, ny + nh / 2)
            if rot != 0.0:
                painter.rotate(rot)

            if pix and not pix.isNull():
                pw = pix.width()
                ph = pix.height()
                max_w = int((nw - 12) * (1.15 if is_selected else 1.0))
                max_h = int((nh - 8) * (1.15 if is_selected else 1.0))
                s = min(max_w / pw, max_h / ph) if pw > 0 and ph > 0 else 1.0
                dw = int(pw * s)
                dh = int(ph * s)
                painter.drawPixmap(QRect(-dw // 2, -dh // 2, dw, dh), pix)
            else:
                rect = QRect(-nw // 2, -nh // 2, nw, nh)
                bg_col = QColor(230, 95, 20, 210) if is_selected else QColor(25, 30, 45, 180)
                border_col = QColor(255, 255, 255, 220) if is_selected else QColor(70, 80, 110, 120)
                painter.setPen(QPen(border_col, 2 if is_selected else 1))
                painter.setBrush(QBrush(bg_col))
                painter.drawRoundedRect(rect, 8, 8)

                title = game.get("title") or "Juego"
                painter.setPen(QColor(255, 255, 255))
                f_size = max(11, int(nh * 0.30))
                painter.setFont(QFont(self._font_main, f_size, QFont.Bold))
                painter.drawText(rect.adjusted(8, 4, -8, -4), Qt.AlignCenter | Qt.TextWordWrap, title)

            painter.restore()

    def _draw_bottom_bar(self, painter: QPainter, sr: QRect):
        if not self.games:
            return
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        bar_h = int(sh * 0.075)
        bar_y = sy + sh - bar_h

        # Fondo barra
        painter.fillRect(sx, bar_y, sw, bar_h, QColor(10, 15, 25, 210))

        game = self.games[self.selected_index]
        title = game.get("title", "")
        year = game.get("year", "")
        manu = game.get("manufacturer", "")
        parts = [p for p in (title, year, manu) if p]
        full_title = " - ".join(parts) if parts else self.theme_name

        painter.save()
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont(self._font_title, max(10, int(bar_h * 0.40)), QFont.Bold))
        text_rect = QRect(sx + int(sw * 0.05), bar_y, int(sw * 0.65), bar_h)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, full_title)

        counter_text = f"{self.selected_index + 1} / {len(self.games)}"
        painter.setPen(QColor(245, 185, 35))
        painter.setFont(QFont(self._font_main, max(9, int(bar_h * 0.35)), QFont.Bold))
        counter_rect = QRect(sx + int(sw * 0.72), bar_y, int(sw * 0.24), bar_h)
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter_text)
        painter.restore()

# --- PLAYNEXUS STUDIO OVERRIDES START ---
STUDIO_ELEMENTS = [
    {'id': 'bg_image', 'name': 'Fondo del Layout', 'type': 'image', 'x': 0.0, 'y': 0.0, 'w': 1920.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 5, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 0.0, 1920.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'video_snap', 'name': 'Pantalla TV / Video Snap', 'type': 'video', 'x': 103.0, 'y': 211.0, 'w': 600.0, 'h': 464.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 10, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [103.0, 211.0, 600.0, 464.0], 'media_key': 'video', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scratches', 'name': 'Reflejo Vidrio CRT (gtc-common)', 'type': 'effect', 'x': 103.0, 'y': 211.0, 'w': 600.0, 'h': 464.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 15, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [103.0, 211.0, 600.0, 464.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'tv_bezel', 'name': 'Televisor CRT (tv.png)', 'type': 'image', 'x': 56.0, 'y': 148.0, 'w': 720.0, 'h': 728.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 20, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [56.0, 148.0, 720.0, 728.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'console', 'name': 'Consola (console.png)', 'type': 'image', 'x': -14.5, 'y': 648.8, 'w': 896.0, 'h': 496.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 25, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [336.0, 584.0, 896.0, 496.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'cartart', 'name': 'Cartucho / Disco', 'type': 'image', 'x': 1056.0, 'y': 648.0, 'w': 364.8, 'h': 324.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 30, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1056.0, 648.0, 364.8, 324.0], 'media_key': 'cartart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'disc_rise,disc_spin', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'boxart', 'name': 'Carátula (Box Art)', 'type': 'image', 'x': 768.0, 'y': 572.4, 'w': 316.8, 'h': 442.8, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 35, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [768.0, 572.4, 316.8, 442.8], 'media_key': 'boxart', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'boxart_slide_fade', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'avatar', 'name': 'Avatar / Personaje', 'type': 'image', 'x': 672.0, 'y': 88.0, 'w': 652.0, 'h': 720.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 22, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [672.0, 88.0, 652.0, 720.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'avatar_float', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'logo', 'name': 'Logotipo del Sistema', 'type': 'image', 'x': 72.0, 'y': 12.0, 'w': 656.0, 'h': 120.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 45, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [72.0, 12.0, 656.0, 120.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'logo_bounce', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_shadow', 'name': 'Sombra de Ruleta (gtc-common)', 'type': 'image', 'x': 1336.0, 'y': 0.0, 'w': 584.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 50, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1336.0, 0.0, 584.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_list', 'name': 'Ruleta Curva (Wheel Conveyor)', 'type': 'wheel', 'x': 1200.0, 'y': 0.0, 'w': 720.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 55, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1200.0, 0.0, 720.0, 1080.0], 'media_key': 'wheel', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'pointer', 'name': 'Puntero de Ruleta', 'type': 'image', 'x': 1772.0, 'y': 428.0, 'w': 140.0, 'h': 256.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 60, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1772.0, 428.0, 140.0, 256.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'pointer_pulse', 'anim_delay': 0.0, 'anim_duration': 0.8},
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
