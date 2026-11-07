import playnexus
"""
=============================================================================
Layout Autónomo y Configuración: Main Menu
=============================================================================
Este archivo maneja en su totalidad la configuración, métricas, recursos,
reproducción de video de fondo a pantalla completa, ruleta de wheels curva
interactiva a 60 FPS y renderizado para el Menú Principal / Selección de
Sistemas en PlayNexus.
"""
import os
import time
import math
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QUrl, QRect, QPoint, QTimer, QRectF
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPixmap, QBrush, QPen,
    QFontDatabase, QImage, QLinearGradient
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
    LAYOUT_NAME = "Main Menu"
    LAYOUT_DESCRIPTION = "Menú principal de selección de sistemas con video de fondo a pantalla completa y ruleta de wheels curva"

    CANONICAL_W = 1920
    CANONICAL_H = 1080

    # -------------------------------------------------------------------------
    # REQUERIMIENTOS DE MEDIOS PARA ESTE LAYOUT
    # -------------------------------------------------------------------------
    MEDIA_REQUIREMENTS = [
        {
            "key": "video",
            "label": "Videos de Fondo / Temas",
            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
            "required": True,
        },
        {
            "key": "wheel",
            "label": "Logos Wheel",
            "extensions": [".png", ".webp"],
            "required": True,
        },
        {
            "key": "boxart",
            "label": "Artwork / Imagen decorativa",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": False,
        },
    ]

    # -------------------------------------------------------------------------
    # RECURSOS LOCALES PROPIOS DEL LAYOUT
    # -------------------------------------------------------------------------
    WHEEL_ART_IMAGE = LAYOUT_DIR / "wheel_art.png"
    POINTER_IMAGE   = LAYOUT_DIR / "pointers" / "default.png"
    FONT_FILE       = LAYOUT_DIR / "SF Slapstick Comic Bold Oblique.ttf"

    # Recursos compartidos desde gtc-common
    WHEEL_SHADOW_IMAGE = COMMON_DIR / "wheel" / "wheel_shadow.png"
    SOUND_NAV          = COMMON_DIR / "sounds" / "joystick.mp3"
    SOUND_SELECT       = COMMON_DIR / "sounds" / "hs_click.mp3"
    FONT_BEBAS         = COMMON_DIR / "fonts" / "BebasNeue Bold.otf"

    # -------------------------------------------------------------------------
    # CONFIGURACIÓN GEOMÉTRICA DE LA RULETA CURVA (14 NODOS INTERPOLADOS A 60 FPS)
    # -------------------------------------------------------------------------
    CONVEYOR_X = [0.89, 0.85, 0.83, 0.80, 0.77, 0.74, 0.71, 0.625, 0.71, 0.74, 0.77, 0.80, 0.83, 0.89]
    CONVEYOR_Y = [-0.34, -0.22, -0.105, 0.00, 0.105, 0.215, 0.325, 0.421, 0.59, 0.70, 0.81, 0.915, 0.99, 1.12]
    CONVEYOR_W = [0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.30, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18]
    CONVEYOR_H = [0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.186, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
    CONVEYOR_R = [35.0, 30.0, 25.0, 20.0, 15.0, 10.0, 5.0, 0.0, -10.0, -15.0, -20.0, -25.0, -30.0, -35.0]
    CONVEYOR_A = [0, 20, 35, 60, 90, 125, 160, 255, 160, 125, 90, 60, 35, 0]

    def __init__(self, theme_name: str = "Main Menu", parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.layout_dir = LAYOUT_DIR

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.selected_index = 0
        self.current_media = {}
        self._wheel_pixmaps = {}
        self._current_artwork_pixmap = None

        # Worker asíncrono para precarga de logotipos en segundo plano
        self._wheel_worker = WheelPreloadWorker(self)
        self._wheel_worker.wheel_loaded.connect(self._on_wheel_image_loaded)
        self._wheel_worker.start()

        # Reproductor de video acelerado por GPU
        self._player_initialized = False
        self.player = None
        self.audio_output = None
        self.video_sink = None
        self._media_muted = False
        self.db = None
        self._current_video_image: QImage | None = None

        # Efectos de sonido
        self._sound_effect = QSoundEffect(self)
        self._sound_effect.setVolume(0.45)
        if self.SOUND_NAV.is_file():
            self._sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_NAV)))

        self._select_sound_effect = QSoundEffect(self)
        self._select_sound_effect.setVolume(0.55)
        if self.SOUND_SELECT.is_file():
            self._select_sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_SELECT)))

        # Sombra de curvatura de la ruleta desde gtc-common
        self._pix_wheel_shadow = self._load_pixmap(str(self.WHEEL_SHADOW_IMAGE)) if self.WHEEL_SHADOW_IMAGE.is_file() else None

        # Precargar imágenes locales del layout
        self._pix_wheel_art = self._load_pixmap(str(self.WHEEL_ART_IMAGE))
        self._pix_pointer = self._load_pixmap(str(self.POINTER_IMAGE))

        # Tipografía temática
        self._font_slapstick = "sans-serif"
        self._font_bebas = "sans-serif"
        self._load_theme_fonts()

        # Animación de giro suave y física de la ruleta (interpolación a 60 FPS)
        self._wheel_spin_offset = 0.0
        self._target_pos = 0.0
        self._current_pos = 0.0
        self._wheel_spin_timer = QTimer(self)
        self._wheel_spin_timer.setTimerType(Qt.PreciseTimer)
        self._wheel_spin_timer.timeout.connect(self._on_wheel_spin_tick)

        # Animación y pulso del puntero
        self._pointer_rest_x_ratio = 0.905
        self._pointer_pulse_x_ratio = 0.880
        self._pointer_current_x_ratio = self._pointer_rest_x_ratio
        self._pointer_anim_tick = 0
        self._pointer_anim_timer = QTimer(self)
        self._pointer_anim_timer.timeout.connect(self._on_pointer_tick)

        # Temporizador para inicio diferido de video (debounce) y watchdog de bucle
        self._last_video_frame_time = 0.0
        self._video_debounce_timer = QTimer(self)
        self._video_debounce_timer.setSingleShot(True)
        self._video_debounce_timer.setInterval(180)
        self._video_debounce_timer.timeout.connect(self._play_debounced_video)

        self._video_watchdog_timer = QTimer(self)
        self._video_watchdog_timer.setInterval(800)
        self._video_watchdog_timer.timeout.connect(self._on_video_watchdog_tick)

        # Confirmación de selección diferida al soltar tecla o reposo (Commit on Release / Debounce)
        self._nav_pending_commit = False
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(getattr(self, "NAV_COMMIT_DEBOUNCE_MS", 180))
        self._commit_timer.timeout.connect(self._commit_selection)

    # -------------------------------------------------------------------------
    # GESTIÓN DE FUENTES Y RECURSOS
    # -------------------------------------------------------------------------
    def _load_theme_fonts(self):
        """Carga las fuentes tipográficas locales del tema."""
        if self.FONT_FILE.is_file():
            fid = QFontDatabase.addApplicationFont(str(self.FONT_FILE))
            if fid >= 0:
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    self._font_slapstick = fams[0]

        bebas = self.FONT_BEBAS
        if bebas.is_file():
            fid = QFontDatabase.addApplicationFont(str(bebas))
            if fid >= 0:
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    self._font_bebas = fams[0]

    def _load_pixmap(self, path: str | None) -> QPixmap | None:
        """Carga un QPixmap con caché en memoria global para acelerar la inicialización instantánea."""
        return super()._load_pixmap(path)

    # -------------------------------------------------------------------------
    # PIPELINE DE VIDEO Y MULTIMEDIA
    # -------------------------------------------------------------------------
    def _ensure_player_initialized(self):
        """Inicializa de forma perezosa el reproductor de video acelerado por hardware."""
        if self._player_initialized:
            return
        self.player = QMediaPlayer(self)
        self.player.setLoops(QMediaPlayer.Infinite)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setMuted(self._media_muted)
        self.audio_output.setVolume(0.0 if self._media_muted else 0.8)

        self.video_sink = QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self.player.setVideoSink(self.video_sink)

        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player_initialized = True

    def _on_video_frame_changed(self, frame):
        """Convierte y almacena el fotograma recibido directamente en GPU/memoria rápida."""
        if not frame.isValid() or not getattr(self, "_want_video_playing", True) or not self.player:
            return
        p_path = getattr(self, "_pending_video_path", None)
        if p_path and self.player.source() != QUrl.fromLocalFile(p_path):
            return

        img = frame.toImage()
        if not img.isNull():
            self._current_video_image = img
            self.update()

    def _on_media_status_changed(self, status):
        """Garantiza la reproducción en bucle continuo de los videos de fondo."""
        if status == QMediaPlayer.EndOfMedia:
            if getattr(self, "_want_video_playing", False) and self.player:
                self.player.setPosition(0)
                self.player.play()

    def _on_video_watchdog_tick(self):
        """Supervisa el reproductor y reactiva el bucle si se detuvo inesperadamente."""
        if not getattr(self, "_want_video_playing", False) or not self.player:
            return
        st = self.player.mediaStatus()
        pos = self.player.position()
        dur = self.player.duration()
        if st == QMediaPlayer.EndOfMedia or (dur > 0 and pos >= dur - 200):
            self.player.setPosition(0)
            self.player.play()

    def pause_media(self):
        """Pausa el video y silencia el audio (ej: al ejecutar un juego o sub-lista)."""
        self._video_debounce_timer.stop()
        self._video_watchdog_timer.stop()
        if self.player:
            try:
                self.player.pause()
            except Exception:
                pass
        if self.audio_output:
            try:
                self.audio_output.setVolume(0.0)
            except Exception:
                pass

    def resume_media(self):
        """Reanuda la reproducción multimedia al regresar al menú principal."""
        self._want_video_playing = True
        self._ensure_player_initialized()
        if self.audio_output:
            try:
                self.audio_output.setMuted(self._media_muted)
                self.audio_output.setVolume(0.0 if self._media_muted else 0.8)
            except Exception:
                pass
        if self.player:
            try:
                if self.player.source().isEmpty() or self.player.playbackState() != QMediaPlayer.PlayingState:
                    self._play_debounced_video()
                else:
                    self.player.play()
                    self._video_watchdog_timer.start()
            except Exception:
                pass
        elif getattr(self, "_pending_video_path", None):
            self._play_debounced_video()

    def showEvent(self, event):
        """Asegura que el video del tema comience al hacerse visible la ventana."""
        super().showEvent(event)
        if getattr(self, "_pending_video_play_on_show", False) or not self.player or self.player.source().isEmpty():
            self._play_debounced_video()
        else:
            self.resume_media()

    def stop_media(self):
        """Detiene completamente la reproducción multimedia."""
        self._want_video_playing = False
        self._video_debounce_timer.stop()
        self._video_watchdog_timer.stop()
        if hasattr(self, "_commit_timer"):
            self._commit_timer.stop()
        self._nav_pending_commit = False
        if self.player:
            try:
                self.player.stop()
                self.player.setSource(QUrl())
            except Exception:
                pass
        if self.audio_output:
            try:
                self.audio_output.setVolume(0.0)
            except Exception:
                pass
        self._current_video_image = None

    def set_media_muted(self, muted: bool):
        self._media_muted = muted
        if self.audio_output:
            self.audio_output.setMuted(muted)
            self.audio_output.setVolume(0.0 if muted else 0.8)

    # -------------------------------------------------------------------------
    # CARGA Y GESTIÓN DE JUEGOS Y MEDIOS
    # -------------------------------------------------------------------------
    def set_games(self, games: list):
        """Recibe la lista de elementos (sistemas o juegos) y reinicia el estado."""
        self.games = [dict(g) if hasattr(g, "keys") else g for g in games]
        self._wheel_pixmaps.clear()
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.clear()
        self.selected_index = 0
        self._target_pos = 0.0
        self._current_pos = 0.0
        self._wheel_spin_offset = 0.0
        if self.games:
            self._preload_around(0)
            self._update_current_selection()
        self.update()

    def select_game_by_id(self, game_id: int):
        """Selecciona el elemento con el ID especificado."""
        if not self.games:
            return
        for i, g in enumerate(self.games):
            if g.get("id") == game_id:
                self.selected_index = i
                self._target_pos = 0.0
                self._current_pos = 0.0
                self._wheel_spin_offset = 0.0
                self._preload_around(i)
                self._update_current_selection()
                self.update()
                break

    def _play_nav_sound(self):
        if hasattr(self, "_sound_effect") and self._sound_effect and not self._media_muted:
            self._sound_effect.play()

    def _play_select_sound(self):
        if hasattr(self, "_select_sound_effect") and self._select_sound_effect and not self._media_muted:
            self._select_sound_effect.play()

    def _update_current_selection(self):
        """Actualiza los recursos multimedia para el elemento seleccionado."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self.current_media = {}
            if self.player:
                self.player.stop()
            self._current_video_image = None
            self._current_artwork_pixmap = None
            return

        game = self.games[self.selected_index]
        gid = game.get("id")
        self.current_game_id = gid
        if gid is not None:
            self.game_selected.emit(gid)

        self.current_media = resolve_game_media(game)
        if not hasattr(self, "_art_pix_cache"):
            self._art_pix_cache = {}

        # Cargar imagen de artwork/fondo como fallback inmediato
        art_file = self.current_media.get("boxart") or self.current_media.get("snap") or self.current_media.get("flyer")
        if art_file and os.path.isfile(art_file):
            if art_file not in self._art_pix_cache:
                pix = QPixmap(art_file)
                self._art_pix_cache[art_file] = pix if not pix.isNull() else None
            self._current_artwork_pixmap = self._art_pix_cache.get(art_file)
        else:
            self._current_artwork_pixmap = None

        # Preparar video de fondo
        snap_video = self.current_media.get("video") or self.current_media.get("snap") or game.get("video") or game.get("snap")
        video_to_play = snap_video if (snap_video and os.path.isfile(snap_video)) else None

        self._ensure_player_initialized()
        self._pending_video_path = video_to_play
        if not video_to_play:
            self._want_video_playing = False
            if self.player:
                self.player.stop()
            self._current_video_image = None
            self.update()
            return

        self._video_debounce_timer.start(100)

    def _play_debounced_video(self):
        """Reproduce el video de fondo una vez que la ruleta se estabiliza."""
        if not self.isVisible():
            self._pending_video_play_on_show = True
            return
        self._pending_video_play_on_show = False
        video_to_play = getattr(self, "_pending_video_path", None)
        if video_to_play and os.path.isfile(video_to_play):
            self._want_video_playing = True
            if self.audio_output:
                self.audio_output.setMuted(self._media_muted)
                self.audio_output.setVolume(0.0 if self._media_muted else 0.8)
            source_url = QUrl.fromLocalFile(video_to_play)
            try:
                self.player.setLoops(QMediaPlayer.Infinite)
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

    # -------------------------------------------------------------------------
    # NAVEGACIÓN Y FÍSICA DE LA RULETA
    # -------------------------------------------------------------------------
    def _navigate_steps(self, delta_steps: int):
        """Avanza o retrocede N pasos en la ruleta con animación suave."""
        if not self.games:
            return
        n = len(self.games)
        new_idx = (self.selected_index + delta_steps) % n
        self.selected_index = new_idx
        self._target_pos += delta_steps

        # Pulso elástico del puntero
        self._pointer_current_x_ratio = self._pointer_pulse_x_ratio
        self._pointer_anim_tick = 0
        if self._pix_pointer and not self._pointer_anim_timer.isActive():
            self._pointer_anim_timer.start(16)

        self._play_nav_sound()
        self._preload_around(new_idx)

        # Diferir confirmación de medios al soltar la tecla (Commit on Release)
        # El video previo continúa reproduciéndose fluidamente sin pausarse hasta el commit
        self._video_debounce_timer.stop()
        self._video_watchdog_timer.stop()
        self._nav_pending_commit = True
        self._commit_timer.start(getattr(self, "NAV_COMMIT_DEBOUNCE_MS", 180))

        if not self._wheel_spin_timer.isActive():
            self._wheel_spin_timer.start(16)
        self.update()

    def _commit_selection(self):
        """Aplica y carga los medios del sistema seleccionado una vez detenido el desplazamiento."""
        if not getattr(self, "_nav_pending_commit", False):
            return
        self._nav_pending_commit = False
        if hasattr(self, "_commit_timer"):
            self._commit_timer.stop()
        self._update_current_selection()

    def jump_to_next_letter(self):
        """Salta al primer sistema que comience con la siguiente letra alfabética."""
        if not self.games:
            return
        n = len(self.games)
        curr_title = (self.games[self.selected_index].get("title") or "").upper()
        curr_char = curr_title[0] if curr_title else "A"
        for offset in range(1, n):
            idx = (self.selected_index + offset) % n
            t = (self.games[idx].get("title") or "").upper()
            if t and t[0] != curr_char and t[0].isalnum():
                self._navigate_steps(offset)
                self._commit_selection()
                return

    def jump_to_prev_letter(self):
        """Salta al primer sistema de la letra alfabética anterior."""
        if not self.games:
            return
        n = len(self.games)
        curr_title = (self.games[self.selected_index].get("title") or "").upper()
        curr_char = curr_title[0] if curr_title else "A"
        for offset in range(1, n):
            idx = (self.selected_index - offset) % n
            t = (self.games[idx].get("title") or "").upper()
            if t and t[0] != curr_char and t[0].isalnum():
                target_char = t[0]
                first_idx = idx
                while True:
                    prev_i = (first_idx - 1) % n
                    pt = (self.games[prev_i].get("title") or "").upper()
                    if pt and pt[0] == target_char:
                        first_idx = prev_i
                    else:
                        break
                step = (first_idx - self.selected_index)
                if step > 0:
                    step -= n
                self._navigate_steps(step)
                self._commit_selection()
                return

    def _on_wheel_spin_tick(self):
        """Interpolación de inercia a 60 FPS para el giro de la ruleta."""
        diff = self._target_pos - self._current_pos
        if abs(diff) < 0.005:
            self._current_pos = self._target_pos
            self._wheel_spin_offset = 0.0
            self._wheel_spin_timer.stop()
        else:
            self._current_pos += diff * 0.28
            self._wheel_spin_offset = self._current_pos - self._target_pos
        self.update()

    def _on_pointer_tick(self):
        """Retorna suavemente el puntero a su posición de reposo."""
        self._pointer_anim_tick += 1
        if abs(self._pointer_current_x_ratio - self._pointer_rest_x_ratio) > 0.0005:
            self._pointer_current_x_ratio += (self._pointer_rest_x_ratio - self._pointer_current_x_ratio) * 0.18
            self.update()
        else:
            self._pointer_current_x_ratio = self._pointer_rest_x_ratio
            self._pointer_anim_timer.stop()
            self.update()

    # -------------------------------------------------------------------------
    # PRECARGA ASÍNCRONA DE LOGOTIPOS
    # -------------------------------------------------------------------------
    def _on_wheel_image_loaded(self, gid: int, img: QImage):
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
        if not self.games:
            return False
        n = len(self.games)
        for offset in (-6, 6, -5, 5, -4, 4, -3, 3, -2, 2, -1, 1, 0):
            idx = (self.selected_index + offset) % n
            if self.games[idx].get("id") == game_id:
                return True
        return False

    def _preload_around(self, center_idx: int):
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

    def _get_game_wheel_pixmap(self, game: dict) -> QPixmap | None:
        gid = game.get("id")
        if gid and gid in self._wheel_pixmaps:
            return self._wheel_pixmaps[gid]
        media = resolve_game_media(game)
        wheel_file = media.get("wheel")
        if wheel_file and os.path.isfile(wheel_file):
            pix = QPixmap(wheel_file)
            if not pix.isNull():
                if gid:
                    self._wheel_pixmaps[gid] = pix
                return pix
        return None

    # -------------------------------------------------------------------------
    # RENDERIZADO VISUAL (paintEvent)
    # -------------------------------------------------------------------------
    def _get_target_rect(self) -> QRect:
        """Calcula el área canónica manteniendo una relación de aspecto 16:9 limpia."""
        w = self.width()
        h = self.height()
        target_aspect = self.CANONICAL_W / float(self.CANONICAL_H)
        curr_aspect = w / float(h) if h > 0 else target_aspect

        if curr_aspect >= target_aspect:
            sh = h
            sw = int(h * target_aspect)
            sx = (w - sw) // 2
            sy = 0
        else:
            sw = w
            sh = int(w / target_aspect)
            sx = 0
            sy = (h - sh) // 2
        return QRect(sx, sy, sw, sh)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

            w = self.width()
            h = self.height()

            # Capa 1: Fondo base negro total
            painter.fillRect(0, 0, w, h, QColor(0, 0, 0))

            sr = self._get_target_rect()
            sw = sr.width()
            sh = sr.height()
            sx = sr.x()
            sy = sr.y()

            # Capa 2: Video de fondo a pantalla completa o Artwork de respaldo
            if self._current_video_image and not self._current_video_image.isNull():
                vw = self._current_video_image.width()
                vh = self._current_video_image.height()
                if vw > 0 and vh > 0:
                    v_aspect = vw / float(vh)
                    s_aspect = sw / float(sh)
                    # Si el video coincide en aspecto o es panorámico, llenar el canvas
                    if abs(v_aspect - s_aspect) < 0.15:
                        painter.drawImage(sr, self._current_video_image)
                    else:
                        # Video 4:3 en pantalla 16:9: dibujar proporcionalmente centrado
                        scale = min(sw / float(vw), sh / float(vh))
                        dw = int(vw * scale)
                        dh = int(vh * scale)
                        dx = sx + (sw - dw) // 2
                        dy = sy + (sh - dh) // 2
                        painter.drawImage(QRect(dx, dy, dw, dh), self._current_video_image)
                else:
                    painter.drawImage(sr, self._current_video_image)
            elif self._current_artwork_pixmap and not self._current_artwork_pixmap.isNull():
                # Fallback: Artwork del sistema o juego ocupando el fondo
                pw = self._current_artwork_pixmap.width()
                ph = self._current_artwork_pixmap.height()
                if pw > 0 and ph > 0:
                    scale = max(sw / float(pw), sh / float(ph))
                    dw = int(pw * scale)
                    dh = int(ph * scale)
                    dx = sx + (sw - dw) // 2
                    dy = sy + (sh - dh) // 2
                    painter.drawPixmap(QRect(dx, dy, dw, dh), self._current_artwork_pixmap)

            # Capa 3: Sombra de curvatura de la ruleta desde gtc-common (wheel/wheel_shadow.png)
            if self._pix_wheel_shadow:
                if getattr(self, "_cached_wheel_shadow_size", None) != (sw, sh):
                    self._cached_wheel_shadow_pix = self._pix_wheel_shadow.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._cached_wheel_shadow_size = (sw, sh)
                painter.drawPixmap(sx, sy, self._cached_wheel_shadow_pix)
            else:
                gradient = QLinearGradient(sx + int(sw * 0.50), 0, sx + sw, 0)
                gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
                gradient.setColorAt(0.4, QColor(0, 0, 0, 80))
                gradient.setColorAt(1.0, QColor(0, 0, 0, 210))
                painter.fillRect(QRect(sx + int(sw * 0.50), sy, int(sw * 0.50), sh), gradient)
                if self._pix_wheel_art and not self._pix_wheel_art.isNull():
                    bg_w = int(sw * 0.36)
                    bg_x = sx + int(sw * 0.65)
                    painter.drawPixmap(QRect(bg_x, sy, bg_w, sh), self._pix_wheel_art)

            # Capa 5: Ruleta curva interactiva
            if self.games:
                self._draw_wheel_conveyor(painter, sr)

            # Capa 6: Puntero selector apuntando al ítem seleccionado
            self._draw_pointer(painter, sr)

            # Capa 7: Barra de estado / información inferior
            self._draw_bottom_bar(painter, sr)

        finally:
            painter.end()

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

                painter.setOpacity(min(1.0, max(0.0, alpha / 255.0)))
                rect = QRect(-item_w // 2, -item_h // 2, item_w, item_h)
                wheel_pix = self._get_game_wheel_pixmap(game)

                if wheel_pix and not wheel_pix.isNull():
                    pw = wheel_pix.width()
                    ph = wheel_pix.height()
                    max_w = item_w - 12
                    max_h = item_h - 8
                    s = min(max_w / pw, max_h / ph) if pw > 0 and ph > 0 else 1.0
                    dw = int(pw * s)
                    dh = int(ph * s)
                    painter.drawPixmap(QRect(-dw // 2, -dh // 2, dw, dh), wheel_pix)
                else:
                    card_path = QPainterPath()
                    card_path.addRoundedRect(rect, 8, 8)
                    bg_col = QColor(220, 50, 40, 220) if is_selected else QColor(25, 28, 45, 180)
                    border_col = QColor(255, 255, 255, 230) if is_selected else QColor(70, 80, 110, 120)
                    painter.fillPath(card_path, bg_col)
                    painter.setPen(QPen(border_col, 2 if is_selected else 1))
                    painter.drawPath(card_path)

                    title = game.get("title") or "Sistema"
                    painter.setPen(QColor(255, 255, 255))
                    f_size = max(11, int(item_h * 0.30))
                    f = QFont(self._font_slapstick, f_size, QFont.Bold)
                    painter.setFont(f)
                    painter.drawText(rect.adjusted(8, 4, -8, -4), Qt.AlignCenter | Qt.TextWordWrap, title)
            finally:
                painter.restore()

    def _draw_pointer(self, painter: QPainter, sr: QRect):
        """Dibuja la flecha indicadora señalando el elemento seleccionado."""
        if not self._pix_pointer or not self.games:
            return

        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        ptr_size = int(sh * 0.22)
        ptr_w = ptr_size
        ptr_h = ptr_size

        slot_center_y_ratio = self.CONVEYOR_Y[7] + (self.CONVEYOR_H[7] / 2.0)
        ptr_cy = sy + int(sh * slot_center_y_ratio)
        ptr_y = ptr_cy - (ptr_h // 2)

        visible_w = int(ptr_w * 0.56)
        edge_margin = max(4, int(sw * 0.003))
        base_x = sx + sw - edge_margin - visible_w

        pulse_offset = int(sw * (self._pointer_rest_x_ratio - self._pointer_current_x_ratio))
        idle_oscillation = int(sw * (math.sin(time.perf_counter() * 5.0) * 0.002))
        ptr_x = base_x - pulse_offset + idle_oscillation

        painter.save()
        painter.setOpacity(1.0)
        painter.drawPixmap(ptr_x, ptr_y, ptr_w, ptr_h, self._pix_pointer)
        painter.restore()

    def _draw_bottom_bar(self, painter: QPainter, sr: QRect):
        """Renderiza una barra inferior discreta con el título del sistema y el contador."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return

        sw = sr.width()
        sh = sr.height()
        sx = sr.x()
        sy = sr.y()

        bar_h = max(28, int(sh * 0.045))
        bar_y = sy + sh - bar_h

        # Fondo translúcido sutil
        painter.fillRect(QRect(sx, bar_y, sw, bar_h), QColor(0, 0, 0, 160))

        game = self.games[self.selected_index]
        title = (game.get("title") or "").upper()
        eff_name = game.get("effective_name") or ""

        # Título a la izquierda
        f_title = QFont(self._font_slapstick, max(11, int(sh * 0.022)), QFont.Bold)
        painter.setFont(f_title)
        painter.setPen(QColor(255, 255, 255))
        title_rect = QRect(sx + int(sw * 0.03), bar_y, int(sw * 0.60), bar_h)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, title)

        # Contador a la derecha
        counter_text = f"{eff_name.upper()}  |  SISTEMA {self.selected_index + 1} / {len(self.games)}" if eff_name else f"SISTEMA {self.selected_index + 1} / {len(self.games)}"
        f_counter = QFont(self._font_bebas, max(11, int(sh * 0.022)), QFont.Bold)
        painter.setFont(f_counter)
        painter.setPen(QColor(245, 185, 35))
        counter_rect = QRect(sx + int(sw * 0.60), bar_y, int(sw * 0.37), bar_h)
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter_text)

    # -------------------------------------------------------------------------
    # CONTROL DE EVENTOS DE TECLADO Y RATÓN
    # -------------------------------------------------------------------------
    def keyPressEvent(self, event):
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
        elif matches_action(event, ACTION_NAV_STEP5_BACK) or matches_action(event, ACTION_PAGE_UP):
            self._navigate_steps(-5)
            event.accept()
        elif matches_action(event, ACTION_NAV_STEP5_FWD) or matches_action(event, ACTION_PAGE_DOWN):
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
            self.set_media_muted(not self._media_muted)
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Al soltar la tecla de navegación, confirma la selección del sistema y actualiza medios."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if not event.isAutoRepeat() and getattr(self, "_nav_pending_commit", False):
            self._commit_selection()
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        """Captura el foco y almacena la posición del clic sin mover la ruleta ni cambiar medios."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        self.setFocus()
        if event.button() == Qt.LeftButton:
            self._mouse_pressed_pos = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Al soltar el clic, ejecuta la acción en la ruleta de wheels o activación del sistema."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if event.button() == Qt.LeftButton and hasattr(self, "_mouse_pressed_pos") and self._mouse_pressed_pos is not None:
            pos = self._mouse_pressed_pos
            self._mouse_pressed_pos = None

            sr = self._get_target_rect()
            sw = sr.width()
            sh = sr.height()
            sx = sr.x()
            sy = sr.y()

            mx, my = pos.x(), pos.y()

            # Comprobar si se hizo clic sobre algún ítem de la ruleta (se ejecuta únicamente al soltar)
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
                        ix = sx + int(sw * rx)
                        iy = sy + int(sh * ry)

                        if ix <= mx <= (ix + item_w) and iy <= my <= (iy + item_h):
                            if offset == 0:
                                gid = self.get_selected_game_id()
                                if gid and self._can_activate_game():
                                    self._play_select_sound()
                                    self.game_activated.emit(gid)
                            else:
                                self._navigate_steps(offset)
                                self._commit_selection()
                            event.accept()
                            return

            # Clics en tercio superior o inferior para navegar
            if my < self.height() * 0.40:
                self._navigate_steps(-1)
                self._commit_selection()
            elif my > self.height() * 0.60:
                self._navigate_steps(1)
                self._commit_selection()
            else:
                gid = self.get_selected_game_id()
                if gid and self._can_activate_game():
                    self._play_select_sound()
                    self.game_activated.emit(gid)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        event.accept()

