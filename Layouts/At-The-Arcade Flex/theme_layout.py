"""
=============================================================================
Layout Autónomo y Configuración: At-The-Arcade Flex
=============================================================================
Este archivo maneja en su totalidad la configuración, métricas, recursos,
reproducción de video de fondo, video snap en monitor CRT, cartel marquee,
mueble arcade frontal con transparencias, afiche publicitario (flyer) y
ruleta curva interactiva para PlayNexus.
"""
import os
import math
import random
import time
import threading
from collections import deque
from pathlib import Path
import playnexus  # Asegura configuración FFmpeg antes de importar QtMultimedia

from PySide6.QtCore import Qt, QSize, QUrl, QRect, QPoint, QTimer, QRectF, QThread, Signal
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPixmap, QIcon, QBrush, QPen,
    QFontDatabase, QTransform, QImage
)
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QSoundEffect

from playnexus.ui.layouts.base import BaseLayout
from playnexus.ui.cover_utils import load_cover
from playnexus.services.media import find_media_file as cached_find_media_file
from playnexus.services.controls import (
    matches_action, ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_PAGE_UP,
    ACTION_PAGE_DOWN, ACTION_SELECT, ACTION_MUTE, ACTION_NAV_BACK,
    ACTION_NAV_LETTER_BACK, ACTION_NAV_LETTER_FWD,
    ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD
)

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class WheelPreloadWorker(QThread):
    """
    Hilo de trabajo en segundo plano para pre-cargar y pre-escalar logotipos de rueda (wheel)
    de forma asíncrona sin bloquear jamás el renderizado de la interfaz ni la tasa de cuadros.
    """
    wheel_loaded = Signal(int, QImage)  # (game_id, scaled_qimage)

    def __init__(self, parent=None):
        """Inicializa los componentes internos, estructuras de datos y temporizadores del objeto."""
        super().__init__(parent)
        self._queue = deque()
        self._queued_ids = set()
        self._lock = threading.Lock()
        self._running = True
        self._event = threading.Event()

    def stop(self):
        """Detiene de forma segura el hilo de trabajo y espera su finalización."""
        self._running = False
        self._event.set()
        self.wait(500)

    def clear(self):
        """Limpia la lista de juegos y cachés de texturas en memoria."""
        with self._lock:
            self._queue.clear()
            self._queued_ids.clear()

    def queue_game(self, game: dict, priority: bool = False):
        """Encola un juego para precargar y escalar su logotipo de rueda en segundo plano."""
        gid = game.get("id")
        if not gid:
            return
        with self._lock:
            if gid not in self._queued_ids:
                if priority:
                    self._queue.appendleft(game)
                else:
                    self._queue.append(game)
                self._queued_ids.add(gid)
        self._event.set()

    def queue_games(self, games_list: list[dict], priority: bool = False):
        """Encola una lista de juegos para su procesamiento predictivo en segundo plano."""
        with self._lock:
            items = reversed(games_list) if priority else games_list
            for g in items:
                gid = g.get("id")
                if gid and gid not in self._queued_ids:
                    if priority:
                        self._queue.appendleft(g)
                    else:
                        self._queue.append(g)
                    self._queued_ids.add(gid)
        self._event.set()

    def run(self):
        """Bucle principal del hilo de trabajo: extrae juegos de la cola, carga sus logotipos de rueda y los emite escalados."""
        img_exts = (".png", ".webp", ".jpg", ".jpeg")
        while self._running:
            game = None
            with self._lock:
                if self._queue:
                    game = self._queue.popleft()
                else:
                    self._event.clear()

            if not game:
                self._event.wait(timeout=0.05)
                continue

            gid = game.get("id")
            try:
                w_file = None
                wheel_folder = game.get("wheel_path")
                rom = game.get("rom_path", "")
                stem = Path(rom).stem if rom else ""
                if wheel_folder and stem:
                    w_file = cached_find_media_file(wheel_folder, stem, img_exts)
                if w_file and os.path.isfile(w_file):
                    img = QImage(w_file)
                    if not img.isNull():
                        if img.width() > 480 or img.height() > 240:
                            img = img.scaled(480, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.wheel_loaded.emit(gid, img)
            except Exception:
                pass


class ThemeLayout(BaseLayout):
    LAYOUT_NAME = "At-The-Arcade Flex"
    LAYOUT_DESCRIPTION = "Layout arcade fotorrealista con mueble interactivo, video de fondo y ruleta"

    CANONICAL_W = 1920
    CANONICAL_H = 1080

    # =========================================================================
    # 1. FUENTES TIPOGRÁFICAS (Rutas directas a los archivos)
    # =========================================================================
    FONT_TITLE_FILE = LAYOUT_DIR / "BebasNeue Bold.otf"
    FONT_COUNTER_FILE = LAYOUT_DIR / "Handel Gothic BT.ttf"

    # =========================================================================
    # 2. ARCHIVOS DE IMÁGENES Y ARTES PROPIOS DEL LAYOUT
    # =========================================================================
    CABINET_IMAGE       = LAYOUT_DIR / "cabinets.png"
    MARQUEE_IMAGE       = LAYOUT_DIR / "marquee1.jpg"
    BEZEL_IMAGE         = LAYOUT_DIR / "bezels.png"
    POINTER_IMAGE       = LAYOUT_DIR / "pointers" / "default.png"
    DEFAULT_WHEEL_IMAGE = LAYOUT_DIR / "wheel.png"

    # =========================================================================
    # 3. RECURSOS COMPARTIDOS DESDE gtc-common
    # =========================================================================
    SCRATCHES_IMAGE     = COMMON_DIR / "art" / "arcade" / "scratched_cover.png"
    FALLBACK_BG_IMAGE   = COMMON_DIR / "art" / "arcade" / "bkg.jpg"
    BG_VIDEO            = COMMON_DIR / "videos" / "bkg_anim.mp4"
    STATIC_VIDEO        = COMMON_DIR / "videos" / "static.mp4"
    NAV_SOUND           = COMMON_DIR / "sounds" / "joystick.mp3"
    SELECT_SOUND        = COMMON_DIR / "sounds" / "Mame_coin.mp3"
    NAV_SOUND_VOLUME    = 0.4
    SELECT_SOUND_VOLUME = 0.5

    # =========================================================================
    # 4. GEOMETRÍA VIRTUAL DEL MUEBLE ARCADE (Base 1300 x 1080)
    # =========================================================================
    CAB_BASE_W = 1300
    CAB_BASE_H = 1080
    CAB_MAX_WIDTH_RATIO = 0.82
    SNAP_LOCAL_RECT = QRect(200, 318, 706, 526)
    MARQUEE_LOCAL_RECT = QRect(138, 0, 832, 227)
    POINTER_REST_X_RATIO = 0.905
    POINTER_PULSE_X_RATIO = 0.880

    # =========================================================================
    # 5. TIEMPOS Y ANIMACIÓN (TEMPORIZADORES EN MILISEGUNDOS)
    # =========================================================================
    ANIM_TICK_MS = 16
    VIDEO_DEBOUNCE_MS = 150
    ART_DEBOUNCE_MS = 100
    WHEEL_FADEOUT_DELAY_MS = 1400
    FLYER_DELAY_MS = 1500
    VIDEO_WATCHDOG_MS = 1200

    # =========================================================================
    # 6. TEXTOS Y COLORES DE LA BARRA INFERIOR (FOOTER)
    # =========================================================================
    FOOTER_COUNTER_PREFIX = "ARCADE:"
    COLOR_FOOTER_TITLE = QColor(255, 255, 255)
    COLOR_FOOTER_COUNTER = QColor(245, 185, 35)

    # =========================================================================
    # 7. REQUERIMIENTOS DE MEDIOS PARA ESTE LAYOUT (CREADOR DE LISTAS)
    # =========================================================================
    MEDIA_REQUIREMENTS = [
        {"key": "video", "label": "Videos", "extensions": [".mp4", ".mkv", ".avi", ".webm"], "required": True},
        {"key": "wheel", "label": "Wheel", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": True},
        {"key": "cabinet", "label": "Cabinets", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
        {"key": "flyer", "label": "Flyers", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
        {"key": "marquee", "label": "Marquees", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
        {"key": "bezel", "label": "Bezels", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
    ]

    def __init__(self, theme_name: str = "At-The-Arcade Flex", parent=None):
        """Inicializa los componentes internos, estructuras de datos y temporizadores del objeto."""
        super().__init__(parent)
        self.theme_name = theme_name
        self.layout_dir = LAYOUT_DIR

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.selected_index = 0
        self.current_media = {}
        self._wheel_pixmaps = {}
        self._art_pix_cache = {}
        self._media_cache = {}
        self._current_marquee_pix: QPixmap | None = None
        self._current_cabinet_pix: QPixmap | None = None
        self._current_bezel_pix: QPixmap | None = None
        self._current_flyer_pix: QPixmap | None = None
        self._pending_video_path: str | None = None
        p_static = Path(self.STATIC_VIDEO)
        self._static_video_path = str(p_static) if p_static.is_file() else None
        self._pending_video_is_snap = False

        self._video_debounce_timer = QTimer(self)
        self._video_debounce_timer.setSingleShot(True)
        self._video_debounce_timer.setInterval(getattr(self, "VIDEO_DEBOUNCE_MS", 150))
        self._video_debounce_timer.timeout.connect(self._play_debounced_video)

        # Temporizador para diferir la lectura en disco de artes pesadas (cabinet/marquee/bezel) durante el giro
        self._art_debounce_timer = QTimer(self)
        self._art_debounce_timer.setSingleShot(True)
        self._art_debounce_timer.setInterval(getattr(self, "ART_DEBOUNCE_MS", 250))
        self._art_debounce_timer.timeout.connect(self._load_current_game_art)
        self._last_nav_time = 0.0

        # Worker en segundo plano para pre-carga asíncrona de logotipos de rueda
        self._text_wheel_cache = {}
        self._wheel_worker = WheelPreloadWorker(self)
        self._wheel_worker.wheel_loaded.connect(self._on_wheel_image_loaded)
        self._wheel_worker.start()

        self._video_watchdog_timer = QTimer(self)
        self._video_watchdog_timer.setSingleShot(True)
        self._video_watchdog_timer.setInterval(getattr(self, "VIDEO_WATCHDOG_MS", 1200))
        self._video_watchdog_timer.timeout.connect(self._on_game_video_watchdog)

        # Estado del reproductor de video de fondo
        self._bg_video_image: QImage | None = None
        self._bg_player_initialized = False
        self.bg_player = None
        self.bg_sink = None

        # Estado del reproductor de video gameplay
        self._game_video_image: QImage | None = None
        self._game_player_initialized = False
        self._want_game_video_playing = False
        self.game_player = None
        self.game_audio = None
        self.game_sink = None
        self._media_muted = False
        self._is_emulator_running = False

        # Animación suave de la ruleta (posición interpolada a 60 FPS con precisión de temporizador)
        self._current_pos = 0.0
        self._target_pos = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.PreciseTimer)
        self._anim_timer.setInterval(getattr(self, "ANIM_TICK_MS", 16))
        self._anim_timer.timeout.connect(self._on_animation_tick)
        self._anim_timer.start()

        # Temporizador de desvanecimiento suave de la ruleta (Wheel fadeout tras inactividad)
        self._wheel_alpha = 255.0
        self._target_wheel_alpha = 255.0
        self._wheel_fade_timer = QTimer(self)
        self._wheel_fade_timer.setSingleShot(True)
        self._wheel_fade_timer.setInterval(getattr(self, "WHEEL_FADEOUT_DELAY_MS", 1400))
        self._wheel_fade_timer.timeout.connect(self._start_wheel_fadeout)

        # Animación del flyer deslizante (aparece 1.5 segundos después de detenerse la ruleta)
        self._flyer_slide = 1.0  # 0.0 = posicionado, 1.0 = fuera de pantalla
        self._flyer_alpha = 255
        self._flyer_ready = False
        self._flyer_delay_timer = QTimer(self)
        self._flyer_delay_timer.setSingleShot(True)
        self._flyer_delay_timer.setInterval(getattr(self, "FLYER_DELAY_MS", 1500))
        self._flyer_delay_timer.timeout.connect(self._on_flyer_delay_timeout)

        # Efectos de sonido
        self._sound_effect = QSoundEffect(self)
        self._sound_effect.setVolume(self.NAV_SOUND_VOLUME)
        p_nav_sound = Path(self.NAV_SOUND)
        if p_nav_sound.is_file():
            self._sound_effect.setSource(QUrl.fromLocalFile(str(p_nav_sound)))

        self._select_sound_effect = QSoundEffect(self)
        self._select_sound_effect.setVolume(self.SELECT_SOUND_VOLUME)
        p_sel_sound = Path(self.SELECT_SOUND)
        if p_sel_sound.is_file():
            self._select_sound_effect.setSource(QUrl.fromLocalFile(str(p_sel_sound)))

        # Precargar imágenes base del tema
        self._pix_cabinet = self._load_pixmap(str(self.CABINET_IMAGE))
        self._pix_marquee_default = self._load_pixmap(str(self.MARQUEE_IMAGE))
        self._current_cabinet_pix = self._pix_cabinet
        self._current_marquee_pix = self._pix_marquee_default
        self._pix_pointer = self._load_pixmap(str(self.POINTER_IMAGE))
        self._pix_wheel_default = self._load_pixmap(str(self.DEFAULT_WHEEL_IMAGE))
        self._pix_scratches = self._load_pixmap(str(self.SCRATCHES_IMAGE))
        self._pix_bg_fallback = self._load_pixmap(str(self.FALLBACK_BG_IMAGE))

        # Fuentes tipográficas
        self._font_title = "Arial"
        self._font_counter = "Arial"
        self._font_secondary = "Arial"
        self._font_bebas = "Arial"
        self._font_dots = "Arial"
        self._font_handel = "Arial"
        self._load_fonts()

        # Puntero animado (pulso y oscilación sutil)
        self._pointer_rest_x_ratio = getattr(self, "POINTER_REST_X_RATIO", 0.905)
        self._pointer_pulse_x_ratio = getattr(self, "POINTER_PULSE_X_RATIO", 0.880)
        self._pointer_current_x_ratio = self._pointer_rest_x_ratio
        self._pointer_anim_tick = 0

        # Iniciar video de fondo
        self._init_bg_player()
    # -------------------------------------------------------------------------
    # RECURSOS TIPOGRÁFICOS Y EFECTOS DE SONIDO
    # -------------------------------------------------------------------------

    def _load_fonts(self):
        """Registra directamente los archivos de fuentes especificados en la cabecera."""
        self._font_title = "Arial"
        self._font_counter = "Arial"

        # Registrar fuente de título
        p_title = Path(self.FONT_TITLE_FILE)
        if p_title.is_file():
            fid = QFontDatabase.addApplicationFont(str(p_title))
            if fid != -1:
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    self._font_title = fams[0]

        # Registrar fuente de contador
        p_counter = Path(self.FONT_COUNTER_FILE)
        if p_counter.is_file():
            fid = QFontDatabase.addApplicationFont(str(p_counter))
            if fid != -1:
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    self._font_counter = fams[0]

        # Alias de compatibilidad hacia atrás
        self._font_bebas = self._font_title
        self._font_dots = self._font_counter
        self._font_handel = self._font_counter

    def _load_pixmap(self, path: str | None) -> QPixmap | None:
        """Carga un QPixmap con caché en memoria global para acelerar la inicialización instantánea."""
        return super()._load_pixmap(path)

    # -------------------------------------------------------------------------
    # GESTIÓN DE VIDEO DE FONDO Y VIDEO SNAP
    # -------------------------------------------------------------------------
    def _init_bg_player(self):
        """Inicializa el reproductor de video ambiental de fondo (live background) en bucle infinito."""
        p_bg = Path(self.BG_VIDEO)
        if not p_bg.is_file():
            return
        target_url = QUrl.fromLocalFile(str(p_bg))

        if self.bg_player is None:
            self.bg_player = QMediaPlayer(self)
            self.bg_sink = QVideoSink(self)
            self.bg_sink.videoFrameChanged.connect(self._on_bg_frame)
            self.bg_player.setVideoSink(self.bg_sink)
            self.bg_player.setLoops(QMediaPlayer.Infinite)
            self.bg_player.mediaStatusChanged.connect(self._on_bg_media_status_changed)
            self.bg_player.errorOccurred.connect(self._on_bg_player_error)
            self._bg_player_initialized = True

        if self.bg_player.source() != target_url:
            self.bg_player.setSource(target_url)

        if not getattr(self, "_is_emulator_running", False):
            if self.bg_player.playbackState() != QMediaPlayer.PlayingState:
                self.bg_player.play()

    def _on_bg_media_status_changed(self, status):
        """Supervisa el estado del video de fondo y garantiza su bucle continuo ininterrumpido."""
        if not self.bg_player or getattr(self, "_is_emulator_running", False):
            return
        if status == QMediaPlayer.EndOfMedia:
            self.bg_player.setPosition(0)
            self.bg_player.play()
        elif status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferingMedia, QMediaPlayer.BufferedMedia):
            if not getattr(self, "_is_emulator_running", False) and self.bg_player.playbackState() != QMediaPlayer.PlayingState:
                self.bg_player.play()

    def _on_bg_player_error(self, error, error_string):
        """Maneja errores de reproducción del video de fondo reintentando la carga de la fuente."""
        bg_video_path = self.BG_VIDEO
        if self.bg_player and bg_video_path.is_file():
            self.bg_player.setSource(QUrl.fromLocalFile(str(bg_video_path)))
            self.bg_player.play()

    def _on_bg_frame(self, frame):
        """Recibe los cuadros decodificados del video de fondo y actualiza el fondo de la pantalla."""
        if not frame.isValid():
            return
        # Si la ruleta está en giro activo, no congelar el hilo de la UI extrayendo frames pesados de fondo
        is_moving = abs(self._target_pos - self._current_pos) > 0.01 or (time.perf_counter() - getattr(self, "_last_nav_time", 0.0) < 0.20)
        if is_moving and getattr(self, "_bg_video_pix", None) is not None:
            return

        img = frame.toImage()
        if not img.isNull():
            # Conservar resolución nativa original (1920x1080) sin degradación ni pixelado por vecino más próximo
            self._bg_video_pix = QPixmap.fromImage(img)
            self._bg_video_image = img
            if not is_moving:
                self.update()

    def _init_game_player(self):
        """Inicializa el reproductor de video gameplay/snap en el monitor CRT del mueble arcade."""
        if self._game_player_initialized and self.game_player is not None:
            return
        self._game_player_initialized = True
        self.game_player = QMediaPlayer(self)
        self.game_audio = QAudioOutput(self)
        self.game_audio.setVolume(0.0 if self._media_muted else 0.8)
        self.game_sink = QVideoSink(self)
        self.game_sink.videoFrameChanged.connect(self._on_game_frame)
        self.game_player.setVideoSink(self.game_sink)
        self.game_player.setAudioOutput(self.game_audio)
        self.game_player.setLoops(QMediaPlayer.Infinite)
        self.game_player.mediaStatusChanged.connect(self._on_game_media_status_changed)
        self.game_player.errorOccurred.connect(self._on_game_player_error)

    def _recreate_game_player(self):
        """Recrea limpiamente las instancias de QMediaPlayer, QAudioOutput y QVideoSink ante fallas de códec."""
        old_player = self.game_player
        old_audio = self.game_audio
        old_sink = self.game_sink
        self.game_player = None
        self.game_audio = None
        self.game_sink = None
        self._game_player_initialized = False
        if old_sink is not None:
            try:
                old_sink.videoFrameChanged.disconnect()
            except Exception:
                pass
            old_sink.deleteLater()
        if old_player is not None:
            try:
                old_player.mediaStatusChanged.disconnect()
                old_player.errorOccurred.disconnect()
            except Exception:
                pass
            old_player.deleteLater()
        if old_audio is not None:
            old_audio.deleteLater()
        self._init_game_player()

    def _on_game_media_status_changed(self, status):
        """Controla el ciclo de vida del video snap (carga, buffer, reproducción y silenciamiento)."""
        if not self.game_player or getattr(self, "_is_emulator_running", False):
            return
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferingMedia, QMediaPlayer.BufferedMedia):
            if self._want_game_video_playing and self.isVisible():
                if self.game_audio:
                    is_snap = getattr(self, "_pending_video_is_snap", True)
                    should_mute = bool(self._media_muted or not is_snap)
                    self.game_audio.setMuted(should_mute)
                    self.game_audio.setVolume(0.0 if should_mute else 0.8)
                if self.game_player.playbackState() != QMediaPlayer.PlayingState:
                    self.game_player.play()
            else:
                if self.game_audio:
                    self.game_audio.setMuted(True)
                    try:
                        self.game_audio.setMuted(True)
                        self.game_audio.setVolume(0.0)
                    except Exception:
                        pass
                if status == QMediaPlayer.BufferedMedia:
                    self.game_player.pause()
        elif status == QMediaPlayer.EndOfMedia:
            if self._want_game_video_playing and self.isVisible():
                self.game_player.setPosition(0)
                self.game_player.play()

    def _on_game_player_error(self, error, error_string=""):
        """Gestiona errores de decodificación en el video gameplay activando mecanismos de recuperación."""
        if not getattr(self, "_is_emulator_running", False):
            self._game_video_image = None

    def _on_game_video_watchdog(self):
        """Temporizador de seguridad que verifica que el video gameplay comience a reproducirse sin congelarse."""
        if getattr(self, "_is_emulator_running", False):
            return
        if not self._want_game_video_playing or not self._pending_video_path or not self.isVisible():
            return
        if not os.path.isfile(self._pending_video_path) or not self.game_player:
            return
        if self.game_player.mediaStatus() in (QMediaPlayer.LoadingMedia, QMediaPlayer.BufferingMedia) and self.game_player.playbackState() == QMediaPlayer.PlayingState:
            return
        if self._game_video_image is None or self.game_player.playbackState() != QMediaPlayer.PlayingState:
            try:
                src_url = QUrl.fromLocalFile(self._pending_video_path)
                if self.game_player.source() != src_url:
                    self.game_player.setSource(src_url)
                self.game_player.play()
            except Exception:
                pass

    def _on_game_frame(self, frame):
        """Recibe los cuadros de video del juego y los vuelca en la textura del monitor CRT."""
        if frame.isValid() and self.game_player:
            if not self._want_game_video_playing and not getattr(self, "_is_emulator_running", False):
                return
            if self._pending_video_path and self.game_player.source() != QUrl.fromLocalFile(self._pending_video_path):
                return
            is_moving = abs(self._target_pos - self._current_pos) > 0.01 or (time.perf_counter() - getattr(self, "_last_nav_time", 0.0) < 0.20)
            if is_moving and self._game_video_image is not None:
                return
            now = time.perf_counter()
            if now - getattr(self, "_last_game_frame_time", 0.0) < 0.033:  # Cap a 30 FPS para monitor CRT
                return
            self._last_game_frame_time = now
            img = frame.toImage()
            if not img.isNull():
                self._game_video_image = img
                self.update()

    # -------------------------------------------------------------------------
    # RESOLUCIÓN AUTÓNOMA DE MEDIOS DE CADA JUEGO (CON ÍNDICE EN MEMORIA O(1))
    # -------------------------------------------------------------------------
    def _find_media_file(self, folder: str | None, stem: str, exts: tuple[str, ...]) -> str | None:
        """Busca un archivo multimedia coincidente en la carpeta especificada según extensiones válidas."""
        return cached_find_media_file(folder, stem, exts)

    def _resolve_game_media(self, game_dict: dict) -> dict:
        """Resuelve la totalidad de artes y videos vinculados al juego desde la biblioteca o carpetas manuales."""
        gid = game_dict.get("id")
        if gid in self._media_cache:
            return self._media_cache[gid]

        rom_path = game_dict.get("rom_path", "")
        stem = Path(rom_path).stem if rom_path else ""

        # Extensiones de archivos
        img_exts = (".png", ".jpg", ".jpeg", ".webp")
        vid_exts = (".mp4", ".mkv", ".avi", ".webm")

        # 1. Video snap
        video_file = self._find_media_file(game_dict.get("video_path"), stem, vid_exts)

        # 2. Wheel (Logotipo)
        wheel_file = self._find_media_file(game_dict.get("wheel_path"), stem, img_exts)

        # 3. Cabinet (Mueble arcade del juego)
        cabinet_file = self._find_media_file(game_dict.get("cabinet_path"), stem, img_exts)

        # 4. Flyer (Afiche publicitario)
        flyer_file = self._find_media_file(game_dict.get("flyer_path"), stem, img_exts)

        # 5. Marquee (Marquesina iluminada)
        marquee_file = self._find_media_file(game_dict.get("marquee_path"), stem, img_exts)

        # 6. Bezel (Marco decorativo del monitor)
        bezel_file = self._find_media_file(game_dict.get("bezel_path"), stem, img_exts)

        res = {
            "video": video_file,
            "wheel": wheel_file,
            "cabinet": cabinet_file,
            "flyer": flyer_file,
            "marquee": marquee_file,
            "bezel": bezel_file,
        }
        self._media_cache[gid] = res
        return res

    # -------------------------------------------------------------------------
    # INTERFAZ BASELAYOUT
    # -------------------------------------------------------------------------
    def _on_wheel_image_loaded(self, gid: int, img: QImage):
        """Callback asíncrono disparado cuando un logotipo de ruleta ha terminado de escalarse en segundo plano."""
        if not img.isNull():
            pix = QPixmap.fromImage(img)
            self._wheel_pixmaps[gid] = pix
            # Limitar memoria RAM a un máximo de 600 logotipos cargados
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
        half_slots = 5
        curr_center = int(round(self._current_pos))
        for offset in range(-half_slots, half_slots + 1):
            idx = (curr_center + offset) % n
            if self.games[idx].get("id") == game_id:
                return True
        return False

    def _preload_around(self, center_idx: int):
        """Encola en segundo plano la precarga de los logotipos vecinos al índice actual y precarga artes adyacentes."""
        if not self.games or not hasattr(self, "_wheel_worker") or not self._wheel_worker:
            return
        n = len(self.games)
        window = []
        for i in range(-4, 12):
            idx = (center_idx + i) % n
            g = self.games[idx]
            if g.get("id") not in self._wheel_pixmaps:
                window.append(g)
        if window:
            self._wheel_worker.queue_games(window)

        # Precargar además los muebles arcade y marquesinas de los juegos vecinos (-1, 1) en memoria
        for off in (-1, 1):
            adj_game = self.games[(center_idx + off) % n]
            adj_media = self._resolve_game_media(adj_game)
            if adj_media.get("cabinet"):
                self._get_cached_art_pixmap(adj_media["cabinet"])
            if adj_media.get("marquee"):
                self._get_cached_art_pixmap(adj_media["marquee"])

    def _preload_direction(self, steps: int):
        """Encola la precarga predictiva de logotipos en la dirección en que el usuario está navegando."""
        if not self.games or not hasattr(self, "_wheel_worker") or not self._wheel_worker:
            return
        n = len(self.games)
        direction = 1 if steps > 0 else -1
        window = []
        start = self.selected_index
        count = 30 if abs(steps) <= 1 else 50
        for i in range(1, count + 1):
            idx = (start + (i * direction)) % n
            g = self.games[idx]
            if g.get("id") not in self._wheel_pixmaps:
                window.append(g)
        if window:
            self._wheel_worker.queue_games(window, priority=True)

    def _reset_flyer_state(self):
        """Reinicia el estado del flyer deslizante para que permanezca oculto fuera de pantalla."""
        self._flyer_ready = False
        self._flyer_slide = 1.0  # 1.0 = totalmente fuera de pantalla por la derecha
        self._current_flyer_pix = None
        if hasattr(self, "_flyer_delay_timer"):
            self._flyer_delay_timer.stop()
    # -------------------------------------------------------------------------
    # GESTIÓN DE JUEGOS Y PRECARGA ASÍNCRONA
    # -------------------------------------------------------------------------

    def set_games(self, games: list[dict]):
        """Establece la colección de juegos a mostrar, reinicia la posición y dispara la precarga de artes."""
        self.games = games or []
        self._media_cache.clear()
        self._wheel_pixmaps.clear()
        self._text_wheel_cache.clear()
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.clear()
        self.selected_index = 0
        self._current_pos = 0.0
        self._target_pos = 0.0
        self._reset_flyer_state()
        self._init_bg_player()
        if self.games:
            self._preload_around(0)
            self._update_current_selection(start_video=True)
            self._flyer_delay_timer.start(1500)
        else:
            self.current_media = {}
            self._current_marquee_pix = self._pix_marquee_default
            self._current_cabinet_pix = self._pix_cabinet
            self._current_bezel_pix = None
            self.stop_media()
        self.update()

    def select_game_by_id(self, game_id: int):
        """Selecciona visualmente un juego por su identificador numérico único."""
        for idx, g in enumerate(self.games):
            if g.get("id") == game_id:
                need_flyer_restart = (self.selected_index != idx or not self._flyer_ready)
                self.selected_index = idx
                self._current_pos = float(idx)
                self._target_pos = float(idx)
                if need_flyer_restart:
                    self._reset_flyer_state()
                    self._flyer_delay_timer.start(1500)
                self._preload_around(idx)
                self._update_current_selection(start_video=True)
                self.update()
                break

    def get_selected_game_id(self) -> int | None:
        """Retorna el identificador del juego actualmente seleccionado en la ruleta."""
        if self.games and 0 <= self.selected_index < len(self.games):
            return self.games[self.selected_index].get("id")
        return None
    # -------------------------------------------------------------------------
    # CONTROL DE CICLO DE VIDA Y RECURSOS DEL SISTEMA
    # -------------------------------------------------------------------------

    def set_media_muted(self, muted: bool):
        """Silencia o reactiva el audio de los videos según las preferencias del usuario."""
        self._media_muted = muted
        if self.game_audio:
            self.game_audio.setMuted(muted)
            self.game_audio.setVolume(0.0 if muted else 0.8)
        if hasattr(self, "_sound_effect") and self._sound_effect:
            try:
                self._sound_effect.setMuted(muted)
                self._sound_effect.setVolume(0.0 if muted else 0.4)
            except Exception:
                pass
        if hasattr(self, "_select_sound_effect") and self._select_sound_effect:
            try:
                self._select_sound_effect.setMuted(muted)
                self._select_sound_effect.setVolume(0.0 if muted else 0.5)
            except Exception:
                pass

    def pause_media(self):
        """Pausa el video gameplay y silencia el audio mientras el emulador está en ejecución."""
        self._is_emulator_running = True
        self._want_game_video_playing = False
        self._video_debounce_timer.stop()
        self._video_watchdog_timer.stop()
        if hasattr(self, "_art_debounce_timer"):
            self._art_debounce_timer.stop()
        if self.game_audio:
            try:
                self.game_audio.setMuted(True)
                self.game_audio.setVolume(0.0)
            except Exception:
                pass
        if self.game_player:
            try:
                self.game_player.pause()
            except Exception:
                pass
        if getattr(self, "bg_player", None):
            try:
                self.bg_player.pause()
            except Exception:
                pass
        # IMPORTANTE: NO borrar self._game_video_image para que el último frame siga visible en el monitor CRT
        self.update()

    def resume_media(self):
        """Reanuda la reproducción de video y audio cuando el emulador finaliza."""
        self._is_emulator_running = False
        self._want_game_video_playing = True
        self._init_bg_player()
        if getattr(self, "bg_player", None):
            try:
                if self.bg_player.playbackState() != QMediaPlayer.PlayingState:
                    self.bg_player.play()
            except Exception:
                pass

        if self.game_player and self._pending_video_path and os.path.isfile(self._pending_video_path):
            try:
                if self.game_audio:
                    is_snap = getattr(self, "_pending_video_is_snap", True)
                    should_mute = bool(self._media_muted or not is_snap)
                    self.game_audio.setMuted(should_mute)
                    self.game_audio.setVolume(0.0 if should_mute else 0.8)
                if self.game_player.playbackState() != QMediaPlayer.PlayingState:
                    self.game_player.play()
                self._video_watchdog_timer.start()
            except Exception:
                pass
        elif self.games and 0 <= self.selected_index < len(self.games):
            self._start_game_video()

        self.update()

    def stop_media(self):
        """Detiene completamente la reproducción de video y audio liberando recursos del sistema."""
        self._is_emulator_running = False
        self._want_game_video_playing = False
        self._video_debounce_timer.stop()
        self._video_watchdog_timer.stop()
        self._reset_flyer_state()
        if hasattr(self, "_art_debounce_timer"):
            self._art_debounce_timer.stop()
        if self.game_audio:
            self.game_audio.setVolume(0.0)
        if self.game_player and self.game_player.mediaStatus() == QMediaPlayer.BufferedMedia:
            try:
                self.game_player.pause()
            except Exception:
                pass
        self._game_video_image = None
        self.update()

    def showEvent(self, event):
        """Reanuda la reproducción y animación fluida al volver a enfocar este layout temático."""
        super().showEvent(event)
        self._reset_flyer_state()
        self._init_bg_player()
        if self.bg_player and self.bg_player.playbackState() != QMediaPlayer.PlayingState:
            self.bg_player.play()
        if getattr(self, "_is_emulator_running", False):
            return
        if self.games and 0 <= self.selected_index < len(self.games):
            self._update_current_selection(start_video=True)
            self._reset_wheel_fade()
            self._flyer_delay_timer.start(1500)
        self.update()

    def hideEvent(self, event):
        """Pausa la multimedia y animaciones cuando el layout deja de ser visible para ahorrar CPU/GPU."""
        super().hideEvent(event)
        self._reset_flyer_state()
        if not getattr(self, "_is_emulator_running", False):
            self.stop_media()
        else:
            self.pause_media()
        if getattr(self, "bg_player", None):
            try:
                self.bg_player.pause()
            except Exception:
                pass

    def closeEvent(self, event):
        """Libera los hilos de precarga, temporizadores y reproductores al cerrar la ventana."""
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.stop()
        self.stop_media()
        if getattr(self, "bg_player", None):
            try:
                self.bg_player.stop()
                self.bg_player.setSource(QUrl())
            except Exception:
                pass
            self.bg_player = None
            self.bg_sink = None
            self._bg_player_initialized = False
        if event is not None:
            super().closeEvent(event)

    # -------------------------------------------------------------------------
    # NAVEGACIÓN Y ANIMACIÓN
    # -------------------------------------------------------------------------
    def _navigate_steps(self, steps: int, fast_repeat: bool = False):
        """Avanza o retrocede N posiciones en la lista de juegos y dispara la física de la ruleta."""
        if not self.games:
            return
        n = len(self.games)
        new_idx = (self.selected_index + steps) % n
        self.selected_index = new_idx
        self._target_pos += steps
        self._flyer_ready = False
        self._flyer_slide = 1.0  # Ocultar el flyer mientras se mueve la ruleta
        self._current_flyer_pix = None
        self._flyer_delay_timer.start(1500)
        self._pointer_current_x_ratio = self._pointer_pulse_x_ratio
        self._reset_wheel_fade()
        self._play_nav_sound()

        # Encolar pre-carga en segundo plano de los juegos en la dirección de giro
        self._preload_direction(steps)

        # Iniciar timer de animación si no estaba corriendo
        if hasattr(self, "_anim_timer") and not self._anim_timer.isActive():
            self._last_anim_time = time.perf_counter()
            self._anim_timer.start(16)

        # Actualizar de inmediato el mueble, marquesina y bezel del juego enfocado
        current_game = self.games[self.selected_index]
        self.current_media = self._resolve_game_media(current_game)
        self._load_current_game_art()

        now = time.perf_counter()
        is_rapid = fast_repeat or (now - getattr(self, "_last_nav_time", 0.0) < 0.22)
        self._last_nav_time = now

        self._update_selected_media(fast_repeat=is_rapid)
        gid = self.get_selected_game_id()
        if gid:
            self.game_selected.emit(gid)
        self.update()

    def _on_flyer_delay_timeout(self):
        """Dispara la entrada suave del flyer publicitario tras transcurrir el tiempo de espera."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self._reset_flyer_state()
            return
        flyer_file = self.current_media.get("flyer") if self.current_media else None
        self._current_flyer_pix = self._get_cached_art_pixmap(flyer_file) if flyer_file else None
        if self._current_flyer_pix is not None and not self._current_flyer_pix.isNull():
            self._flyer_slide = 1.0
            self._flyer_ready = True
            if hasattr(self, "_anim_timer") and not self._anim_timer.isActive():
                self._last_anim_time = time.perf_counter()
                self._anim_timer.start(16)
            self.update()
        else:
            self._flyer_ready = False
            self._current_flyer_pix = None

    def _play_nav_sound(self):
        """Reproduce el sonido táctil de navegación al desplazarse por la ruleta."""
        if getattr(self, "_media_muted", False):
            return
        try:
            if self._sound_effect and self._sound_effect.isLoaded():
                self._sound_effect.play()
        except Exception:
            pass

    def _play_select_sound(self):
        """Reproduce el sonido característico de selección al activar o confirmar un juego."""
        if getattr(self, "_media_muted", False):
            return
        try:
            if self._select_sound_effect and self._select_sound_effect.isLoaded():
                self._select_sound_effect.play()
        except Exception:
            pass

    def _start_wheel_fadeout(self):
        """Inicia la animación de desvanecimiento suave de la ruleta tras un período de inactividad."""
        self._target_wheel_alpha = 0.0
        if hasattr(self, "_anim_timer") and not self._anim_timer.isActive():
            self._last_anim_time = time.perf_counter()
            self._anim_timer.start(16)

    def _reset_wheel_fade(self):
        """Restaura la visibilidad y opacidad plena de la ruleta al recibir interacción."""
        self._wheel_alpha = 255.0
        self._target_wheel_alpha = 255.0
        self._wheel_fade_timer.start()

    def _on_animation_tick(self):
        """Temporizador maestro a 60 FPS que coordina la interpolación física de la ruleta, puntero y flyer."""
        needs_update = False

        now = time.perf_counter()
        dt = now - getattr(self, "_last_anim_time", now)
        self._last_anim_time = now
        dt = min(max(dt, 0.001), 0.050)

        # 1. Interpolación suave de la ruleta basada en delta-time
        diff = self._target_pos - self._current_pos
        if abs(diff) > 0.004:
            ease = 1.0 - math.exp(-22.0 * dt)
            self._current_pos += diff * ease
            needs_update = True
            # Mientras el carrusel de wheels sigue girando, reiniciar los 1.5 segundos del flyer
            self._flyer_ready = False
            self._flyer_slide = 1.0
            self._flyer_delay_timer.start(1200)
        else:
            if self._current_pos != self._target_pos:
                self._current_pos = self._target_pos
                needs_update = True
                self._flyer_delay_timer.start(1000)

        # 2. Desvanecimiento suave de la ruleta (Wheel fadeout)
        a_diff = self._target_wheel_alpha - self._wheel_alpha
        if abs(a_diff) > 1.0:
            a_ease = 1.0 - math.exp(-12.0 * dt)
            self._wheel_alpha += a_diff * a_ease
            needs_update = True
        else:
            if self._wheel_alpha != self._target_wheel_alpha:
                self._wheel_alpha = self._target_wheel_alpha
                needs_update = True

        # 3. Deslizamiento suave del flyer
        if self._flyer_ready and self._current_flyer_pix is not None:
            if self._flyer_slide > 0.005:
                f_ease = 1.0 - math.exp(-14.0 * dt)
                self._flyer_slide += (0.0 - self._flyer_slide) * f_ease
                needs_update = True
            elif self._flyer_slide != 0.0:
                self._flyer_slide = 0.0
                needs_update = True

        # 4. Pulso suave del puntero al cambiar de juego
        self._pointer_anim_tick += 1
        p_diff = self._pointer_rest_x_ratio - self._pointer_current_x_ratio
        if abs(p_diff) > 0.001:
            p_ease = 1.0 - math.exp(-20.0 * dt)
            self._pointer_current_x_ratio += p_diff * p_ease
            needs_update = True
        else:
            self._pointer_current_x_ratio = self._pointer_rest_x_ratio

        if needs_update:
            self.update()
        else:
            # Si todo llegó a reposo, detener el timer de animación para liberar 100% de CPU
            flyer_at_rest = (not self._flyer_ready) or (self._flyer_slide <= 0.0)
            if flyer_at_rest and self._current_pos == self._target_pos and self._wheel_alpha == self._target_wheel_alpha:
                if hasattr(self, "_anim_timer") and self._anim_timer.isActive():
                    self._anim_timer.stop()

    def _get_cached_art_pixmap(self, path: str | None) -> QPixmap | None:
        """Obtiene una textura de arte desde la caché en memoria o la carga desde disco si no existe."""
        if not path:
            return None
        if path in self._art_pix_cache:
            return self._art_pix_cache[path]
        pix = self._load_pixmap(path)
        if len(self._art_pix_cache) >= 120:
            self._art_pix_cache.pop(next(iter(self._art_pix_cache)), None)
        self._art_pix_cache[path] = pix
        return pix

    def _load_current_game_art(self):
        """Carga de forma diferida las texturas pesadas (marquee, cabinet, bezel) del juego actual."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return
        custom_cab_file = self.current_media.get("cabinet")
        custom_cab_pix = self._get_cached_art_pixmap(custom_cab_file) if custom_cab_file else None
        has_custom_cab = custom_cab_pix is not None
        self._current_cabinet_pix = custom_cab_pix if has_custom_cab else self._pix_cabinet

        marq_file = self.current_media.get("marquee")
        marq_pix = self._get_cached_art_pixmap(marq_file) if marq_file else None
        if marq_pix is not None:
            self._current_marquee_pix = marq_pix
        else:
            self._current_marquee_pix = None if has_custom_cab else self._pix_marquee_default

        bezel_file = self.current_media.get("bezel")
        self._current_bezel_pix = self._get_cached_art_pixmap(bezel_file) if bezel_file else None
        self.update()

    def _update_selected_media(self, fast_repeat: bool = False):
        """Carga y asigna los recursos multimedia del juego seleccionado actualmente."""
        self._flyer_ready = False
        self._flyer_slide = 1.0
        self._current_flyer_pix = None
        self._flyer_delay_timer.stop()

        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self.current_media = {}
            self._current_marquee_pix = self._pix_marquee_default
            self._current_cabinet_pix = self._pix_cabinet
            self._current_bezel_pix = None
            self._pending_video_path = None
            self._want_game_video_playing = False
            self._video_debounce_timer.stop()
            self._video_watchdog_timer.stop()
            if hasattr(self, "_art_debounce_timer"):
                self._art_debounce_timer.stop()
            if self.game_audio:
                self.game_audio.setVolume(0.0)
            self._game_video_image = None
            return

        # Si el reproductor de video estaba activo, silenciar y pausar una sola vez
        if self._want_game_video_playing:
            self._want_game_video_playing = False
            if self.game_audio:
                try:
                    self.game_audio.setMuted(True)
                    self.game_audio.setVolume(0.0)
                except Exception:
                    pass
            if self.game_player:
                try:
                    self.game_player.pause()
                except Exception:
                    pass

        self._video_watchdog_timer.stop()
        self._video_debounce_timer.start()

    def _update_current_selection(self, start_video: bool = True):
        """Actualiza todos los elementos artísticos, videos y animaciones para el juego enfocado."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self.current_media = {}
            self._current_marquee_pix = self._pix_marquee_default
            self._current_cabinet_pix = self._pix_cabinet
            self._current_bezel_pix = None
            self.stop_media()
            return

        current_game = self.games[self.selected_index]
        gid = current_game.get("id")
        self.current_game_id = gid
        if gid is not None:
            self.game_selected.emit(gid)

        self.current_media = self._resolve_game_media(current_game)
        self._load_current_game_art()

        # Cargar de inmediato el logotipo wheel del juego seleccionado si no está en RAM
        if gid and gid not in self._wheel_pixmaps:
            w_file = self.current_media.get("wheel")
            if w_file and os.path.isfile(w_file):
                p = QPixmap(w_file)
                if not p.isNull():
                    self._wheel_pixmaps[gid] = p

        self._reset_wheel_fade()

        if start_video:
            self._start_game_video()
        self.update()

    def _start_game_video(self):
        """Prepara e inicia la reproducción del video snap del juego actual en el monitor."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return
        video_path = self.current_media.get("video") if self.current_media else None
        target_video = None
        is_snap = False
        if video_path and os.path.isfile(video_path):
            target_video = video_path
            is_snap = True
        elif self._static_video_path and os.path.isfile(self._static_video_path):
            target_video = self._static_video_path
            is_snap = False

        self._pending_video_path = target_video
        self._pending_video_is_snap = is_snap
        if not self.isVisible():
            return
        if target_video and os.path.isfile(target_video):
            self._init_game_player()
            if self.game_player:
                self._want_game_video_playing = True
                if self.game_audio:
                    should_mute = bool(self._media_muted or not is_snap)
                    self.game_audio.setMuted(should_mute)
                    self.game_audio.setVolume(0.0 if should_mute else 0.8)
                try:
                    src_url = QUrl.fromLocalFile(target_video)
                    if self.game_player.source() == src_url:
                        self.game_player.setPosition(0)
                    else:
                        self.game_player.setSource(src_url)
                    self.game_player.play()
                    self._video_watchdog_timer.start()
                except Exception:
                    pass
        else:
            self._want_game_video_playing = False
            if self.game_audio:
                try:
                    self.game_audio.setMuted(True)
                    self.game_audio.setVolume(0.0)
                except Exception:
                    pass
            if self.game_player:
                try:
                    self.game_player.stop()
                    self.game_player.setSource(QUrl())
                except Exception:
                    pass
            self._game_video_image = None
        self.update()

    def _play_debounced_video(self):
        """Reproduce el video snap una vez que la ruleta se ha detenido para maximizar la fluidez."""
        self._start_game_video()
        self._flyer_delay_timer.start(1500)

    # -------------------------------------------------------------------------
    # RENDERIZADO VISUAL A 60 FPS
    # -------------------------------------------------------------------------
    def paintEvent(self, event):
        """Punto central de renderizado por capas: fondo, CRT, mueble/consola, artes, ruleta interactiva y puntero."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        # 1. FONDO DE VIDEO O IMAGEN ESTÁTICA (acelerado por hardware mediante QPixmap 1:1)
        bg_pix = getattr(self, "_bg_video_pix", None)
        if bg_pix and not bg_pix.isNull():
            if bg_pix.width() == w and bg_pix.height() == h:
                painter.drawPixmap(0, 0, bg_pix)
            else:
                painter.drawPixmap(0, 0, w, h, bg_pix)
        elif self._pix_bg_fallback:
            if not hasattr(self, "_cached_bg_pix") or getattr(self, "_cached_bg_size", None) != (w, h):
                self._cached_bg_pix = self._pix_bg_fallback.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                self._cached_bg_size = (w, h)
            painter.drawPixmap(0, 0, self._cached_bg_pix)
        else:
            painter.fillRect(QRect(0, 0, w, h), QColor(10, 8, 16))

        # Calcular geometría responsiva del mueble arcade (escala a la altura)
        cab_h = h
        cab_w = int(cab_h * (self.CAB_BASE_W / float(self.CAB_BASE_H)))
        # Limitar ancho del mueble solo si la parte visible (1070/1300) supera el 68% del ancho (w * 0.82)
        max_cab_w = int(w * getattr(self, 'CAB_MAX_WIDTH_RATIO', 0.82))
        if cab_w > max_cab_w:
            cab_w = max_cab_w
        cab_x = 0
        cab_y = 0

        scale_x = cab_w / float(self.CAB_BASE_W)
        scale_y = cab_h / float(self.CAB_BASE_H)

        # Rectángulos de pantalla monitor y cartel marquee escalados
        snap_rect = QRect(
            cab_x + int(self.SNAP_LOCAL_RECT.x() * scale_x),
            cab_y + int(self.SNAP_LOCAL_RECT.y() * scale_y),
            int(self.SNAP_LOCAL_RECT.width() * scale_x),
            int(self.SNAP_LOCAL_RECT.height() * scale_y)
        )
        marquee_rect = QRect(
            cab_x + int(self.MARQUEE_LOCAL_RECT.x() * scale_x),
            cab_y + int(self.MARQUEE_LOCAL_RECT.y() * scale_y),
            int(self.MARQUEE_LOCAL_RECT.width() * scale_x),
            int(self.MARQUEE_LOCAL_RECT.height() * scale_y)
        )

        # 2. MONITOR CRT (Capa trasera del monitor)
        painter.fillRect(snap_rect, QColor(0, 0, 0))
        if self._game_video_image:
            vw, vh = self._game_video_image.width(), self._game_video_image.height()
            s = min(snap_rect.width() / vw, snap_rect.height() / vh) if vw > 0 and vh > 0 else 1.0
            dw, dh = int(vw * s), int(vh * s)
            vx = snap_rect.x() + (snap_rect.width() - dw) // 2
            vy = snap_rect.y() + (snap_rect.height() - dh) // 2
            painter.drawImage(QRect(vx, vy, dw, dh), self._game_video_image)

        # Capa de Bezel del juego (encima del video snap en el monitor CRT)
        if self._current_bezel_pix:
            painter.drawPixmap(snap_rect, self._current_bezel_pix)

        # Capa de reflejo / vidrio rayado CRT sobre el monitor
        if self._pix_scratches:
            s_size = (snap_rect.width(), snap_rect.height())
            if not hasattr(self, "_cached_scratches_pix") or getattr(self, "_cached_scratches_size", None) != s_size:
                self._cached_scratches_pix = self._pix_scratches.scaled(snap_rect.width(), snap_rect.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                self._cached_scratches_size = s_size
            painter.setOpacity(0.40)
            painter.drawPixmap(snap_rect.x(), snap_rect.y(), self._cached_scratches_pix)
            painter.setOpacity(1.0)

        # 3. MARQUEE (Capa trasera de la marquesina con caché reescalada multi-elemento)
        pix_marq = self._current_marquee_pix
        if pix_marq:
            if not hasattr(self, "_scaled_marq_cache"):
                self._scaled_marq_cache = {}
            marq_key = (id(pix_marq), marquee_rect.width(), marquee_rect.height())
            scaled_marq = self._scaled_marq_cache.get(marq_key)
            if scaled_marq is None:
                scaled_marq = pix_marq.scaled(marquee_rect.width(), marquee_rect.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                if len(self._scaled_marq_cache) >= 50:
                    self._scaled_marq_cache.pop(next(iter(self._scaled_marq_cache)), None)
                self._scaled_marq_cache[marq_key] = scaled_marq
            painter.drawPixmap(marquee_rect.x(), marquee_rect.y(), scaled_marq)
            painter.fillRect(marquee_rect, QColor(255, 255, 255, 25))

        # 4. MUEBLE ARCADE FRONTAL (Capa frontal con huecos transparentes y caché reescalada multi-elemento)
        pix_cab = self._current_cabinet_pix or self._pix_cabinet
        if pix_cab:
            if not hasattr(self, "_scaled_cab_cache"):
                self._scaled_cab_cache = {}
            cab_key = (id(pix_cab), cab_w, cab_h)
            scaled_cab = self._scaled_cab_cache.get(cab_key)
            if scaled_cab is None:
                scaled_cab = pix_cab.scaled(cab_w, cab_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                if len(self._scaled_cab_cache) >= 50:
                    self._scaled_cab_cache.pop(next(iter(self._scaled_cab_cache)), None)
                self._scaled_cab_cache[cab_key] = scaled_cab
            painter.drawPixmap(cab_x, cab_y, scaled_cab)

        # 5. FLYER DEL JUEGO (Lado derecho de la pantalla)
        self._draw_flyer(painter, w, h)

        # 6. RULETA CURVA (WHEEL CONVEYOR)
        if self._wheel_alpha > 2.0:
            painter.setOpacity(self._wheel_alpha / 255.0)
            self._draw_wheel(painter, w, h)
            painter.setOpacity(1.0)

        # 7. BARRA INFERIOR / INFORMACIÓN DE JUEGO
        self._draw_footer(painter, w, h)

    def _draw_flyer(self, painter: QPainter, w: int, h: int):
        """Dibuja el afiche publicitario (flyer) deslizante con animación suave y marco protector."""
        if not self._flyer_ready:
            return
        pix = self._current_flyer_pix
        if not pix or pix.isNull():
            return

        # Flyer 30% más grande que el tamaño original (0.22 * 1.30 y 0.52 * 1.30)
        target_w = int(w * 0.22 * 1.30)
        target_h = int(h * 0.52 * 1.30)
        target_x = int(w * 0.67) + int(self._flyer_slide * (w * 0.35))
        target_y = int(h * 0.26)

        # Si el flyer aún está fuera de pantalla a la derecha, omitir render
        if target_x >= w:
            return

        flyer_rect = QRect(target_x, target_y, target_w, target_h)

        pw, ph = pix.width(), pix.height()
        s = min(target_w / pw, target_h / ph) if pw > 0 and ph > 0 else 1.0
        dw, dh = int(pw * s), int(ph * s)
        ax = flyer_rect.x() + (flyer_rect.width() - dw) // 2
        ay = flyer_rect.y() + (flyer_rect.height() - dh) // 2
        painter.drawPixmap(QRect(ax, ay, dw, dh), pix)

    def _draw_wheel(self, painter: QPainter, w: int, h: int):
        """Renderiza la ruleta curva de logotipos arcade con deformación geométrica, perspectiva y sombreado."""
        if not self.games:
            return

        n = len(self.games)
        total_slots = 11
        half_slots = total_slots // 2

        # Puntero central (anclado al borde derecho de la pantalla, apuntando hacia la ruleta)
        if self._pix_pointer:
            ptr_size = max(24, int(h * 0.16))
            ptr_y = (h - ptr_size) // 2
            visible_w = int(ptr_size * 0.56)
            edge_margin = max(4, int(w * 0.003))
            pulse_offset = int(w * (self._pointer_rest_x_ratio - self._pointer_current_x_ratio))
            idle_oscillation = int(w * (math.sin(self._pointer_anim_tick * 0.08) * 0.002))
            ptr_x = w - edge_margin - visible_w - pulse_offset + idle_oscillation
            painter.drawPixmap(ptr_x, ptr_y, ptr_size, ptr_size, self._pix_pointer)

        # Dibujar cada slot a lo largo del arco elíptico
        for offset in range(-half_slots, half_slots + 1):
            slot_idx = int(round(self._current_pos)) + offset
            game_idx = slot_idx % n
            game = self.games[game_idx]

            # Distancia continua al centro
            dist = (slot_idx - self._current_pos)
            if abs(dist) > half_slots + 0.5:
                continue

            # Curvatura elíptica
            angle = (dist / float(half_slots + 1)) * (math.pi * 0.42)
            curv_x = math.cos(angle)
            curv_y = math.sin(angle)

            # Posición en pantalla
            center_x = int(w * 0.85) - int(curv_x * (w * 0.12))
            center_y = int(h * 0.50) + int(curv_y * (h * 0.45))

            # Escala destacada para el ítem central
            is_center = abs(dist) < 0.5
            slot_scale = 1.0 - (abs(dist) * 0.10)
            if is_center:
                slot_w = int(w * 0.22 * 1.25)
                slot_h = int(h * 0.12 * 1.25)
                alpha = 255
            else:
                slot_w = int(w * 0.18 * slot_scale)
                slot_h = int(h * 0.09 * slot_scale)
                alpha = max(60, int(220 - abs(dist) * 35))

            logo_rect = QRect(center_x - slot_w // 2, center_y - slot_h // 2, slot_w, slot_h)

            # Cargar imagen de wheel del juego
            pix_logo = self._get_wheel_pixmap(game)

            if pix_logo:
                painter.setOpacity((alpha / 255.0) * (self._wheel_alpha / 255.0))
                pw, ph = pix_logo.width(), pix_logo.height()
                s = min(logo_rect.width() / pw, logo_rect.height() / ph) if pw > 0 and ph > 0 else 1.0
                dw, dh = int(pw * s), int(ph * s)
                lx = logo_rect.x() + (logo_rect.width() - dw) // 2
                ly = logo_rect.y() + (logo_rect.height() - dh) // 2
                painter.drawPixmap(QRect(lx, ly, dw, dh), pix_logo)
                painter.setOpacity(self._wheel_alpha / 255.0)

    def _create_text_wheel_pixmap(self, title: str) -> QPixmap:
        """Crea un logotipo tipográfico estilizado en memoria y lo cachea para no recalcular texto cada frame."""
        pix = QPixmap(400, 160)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        f_title = QFont(self._font_bebas, 24, QFont.Bold)
        p.setFont(f_title)
        p.setPen(QColor(240, 240, 240))
        p.drawText(pix.rect(), Qt.AlignCenter | Qt.TextWordWrap, (title or "Arcade Game").upper())
        p.end()
        return pix

    def _get_wheel_pixmap(self, game: dict) -> QPixmap | None:
        """Obtiene el logotipo de ruleta pre-renderizado del juego o genera una representación en texto."""
        gid = game.get("id")
        # 1. Si el logotipo ya fue decodificado y pre-escalado en RAM, retorno instantáneo (0 ms)
        if gid in self._wheel_pixmaps:
            return self._wheel_pixmaps[gid]

        # 2. Si no está en RAM, solicitar carga asíncrona inmediata en segundo plano
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.queue_game(game, priority=True)

        # 3. Retornar inmediatamente un logotipo de respaldo en memoria SIN BLOQUEAR paintEvent
        if gid not in self._text_wheel_cache:
            title = game.get("title") or "Arcade Game"
            self._text_wheel_cache[gid] = self._create_text_wheel_pixmap(title)
        return self._text_wheel_cache[gid]

    def _draw_footer(self, painter: QPainter, w: int, h: int):
        """Dibuja la barra inferior de información del sistema y navegación."""
        bar_h = max(26, int(h * 0.042))
        bar_y = h - bar_h

        # Franja negra translúcida
        painter.fillRect(QRect(0, bar_y, w, bar_h), QColor(8, 6, 12, 225))

        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return

        current_game = self.games[self.selected_index]
        title = current_game.get("title") or "Desconocido"

        f_size = max(11, int(h * 0.024))
        f_title = QFont(self._font_title, f_size, QFont.Bold)
        f_title.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        painter.setFont(f_title)
        painter.setPen(getattr(self, "COLOR_FOOTER_TITLE", QColor(255, 255, 255)))
        title_rect = QRect(int(w * 0.04), bar_y, int(w * 0.65), bar_h)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, title.upper())

        counter_prefix = getattr(self, "FOOTER_COUNTER_PREFIX", "ARCADE:")
        counter_text = f"{counter_prefix} {self.selected_index + 1} / {len(self.games)}"
        f_counter = QFont(self._font_counter, max(10, int(h * 0.020)), QFont.Bold)
        painter.setFont(f_counter)
        painter.setPen(getattr(self, "COLOR_FOOTER_COUNTER", QColor(245, 185, 35)))
        counter_rect = QRect(int(w * 0.70), bar_y, int(w * 0.26), bar_h)
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter_text)

    # -------------------------------------------------------------------------
    # CONTROL DE EVENTOS DE TECLADO Y RATÓN
    # -------------------------------------------------------------------------
    def keyPressEvent(self, event):
        """Captura la navegación por teclado (flechas, enter, espacio, retroceso, página, inicio, fin)."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        key = event.key()
        fast = event.isAutoRepeat()
        if matches_action(event, ACTION_NAV_UP):
            self._navigate_steps(-1, fast_repeat=fast)
            event.accept()
        elif matches_action(event, ACTION_NAV_DOWN):
            self._navigate_steps(1, fast_repeat=fast)
            event.accept()
        elif matches_action(event, ACTION_NAV_STEP5_BACK) or matches_action(event, ACTION_PAGE_UP):
            self._navigate_steps(-5, fast_repeat=fast)
            event.accept()
        elif matches_action(event, ACTION_NAV_STEP5_FWD) or matches_action(event, ACTION_PAGE_DOWN):
            self._navigate_steps(5, fast_repeat=fast)
            event.accept()
        elif matches_action(event, ACTION_NAV_LETTER_BACK):
            self.jump_to_prev_letter()
            event.accept()
        elif matches_action(event, ACTION_NAV_LETTER_FWD):
            self.jump_to_next_letter()
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
            self.set_media_muted(not self._media_muted)
            event.accept()
        else:
            super().keyPressEvent(event)


    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        event.accept()

    def wheelEvent(self, event):
        """Permite navegar fluidamente por la lista utilizando la rueda de desplazamiento del ratón."""
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

    def mousePressEvent(self, event):
        """Permite interactuar mediante clics directos sobre los elementos de la interfaz."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        self.setFocus()
        if event.button() == Qt.LeftButton:
            # Si se hace click cerca del monitor, activar el juego
            cab_h = self.height()
            cab_w = int(cab_h * (self.CAB_BASE_W / float(self.CAB_BASE_H)))
            # Misma geometría responsiva que paintEvent (incluido el límite de ancho)
            max_cab_w = int(self.width() * getattr(self, 'CAB_MAX_WIDTH_RATIO', 0.82))
            if cab_w > max_cab_w:
                cab_w = max_cab_w
            scale_x = cab_w / float(self.CAB_BASE_W)
            scale_y = cab_h / float(self.CAB_BASE_H)
            snap_rect = QRect(
                int(self.SNAP_LOCAL_RECT.x() * scale_x),
                int(self.SNAP_LOCAL_RECT.y() * scale_y),
                int(self.SNAP_LOCAL_RECT.width() * scale_x),
                int(self.SNAP_LOCAL_RECT.height() * scale_y)
            )
            pos = event.position().toPoint()
            if snap_rect.contains(pos):
                gid = self.get_selected_game_id()
                if gid and self._can_activate_game():
                    self._play_select_sound()
                    self.game_activated.emit(gid)
                event.accept()
                return

            # Clics arriba o abajo para navegar
            if pos.y() < self.height() * 0.40:
                self._navigate_steps(-1)
            elif pos.y() > self.height() * 0.60:
                self._navigate_steps(1)
            else:
                gid = self.get_selected_game_id()
                if gid and self._can_activate_game():
                    self._play_select_sound()
                    self.game_activated.emit(gid)
            event.accept()
