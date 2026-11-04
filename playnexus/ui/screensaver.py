"""
=============================================================================
PlayNexus - Motor y Widget de Salvapantallas (Screensaver)
=============================================================================
Recreación y optimización para PySide6 del sistema oficial de salvapantallas
de Attract-Mode (screensaver.nut).

Modos incluidos:
1. MovieMode: Video snap a pantalla completa con logo wheel superpuesto (fade y sombra).
2. MovieCollageMode: Cuadrícula 2x2 de videos simultáneos (uno con audio).
3. ImageCollageMode: Mosaico 4x4 de imágenes dinámicas que rotan cada 100ms.
4. RGBMovieMode: Video tripartito con modulación de color RGB y scroll vertical animado.
5. BlankScreen: Ahorro de energía / pantalla negra profunda tras N minutos.

Interactividad:
- Tocar cualquier tecla o mover el mouse despierta el frontend y reanuda el layout.
- Presionar la acción SELECT (Enter o Botón A del gamepad) selecciona y salta directamente
  al juego que se estaba mostrando en el salvapantallas.
"""

import os
import random
import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QRect, QRectF, QPointF
from PySide6.QtGui import QPainter, QPixmap, QColor, QFont, QImage, QTransform
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QStackedWidget
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from playnexus.services.media import resolve_game_media
from playnexus.services.controls import (
    matches_action, ACTION_SELECT, ACTION_NAV_BACK, ACTION_CLOSE_FRONTEND
)


class ArtOverlay:
    """
    Gestiona el renderizado de un logotipo (wheel/flyer/marquee) con sombra negra
    proyectada y transiciones suaves de opacidad (fade-in inicial y fade-out final).
    """
    def __init__(self, overlay_type: str = "wheel"):
        self.overlay_type = overlay_type.lower().strip()
        self.pixmap: QPixmap | None = None
        self.shadow_pixmap: QPixmap | None = None
        self.start_time: float = 0.0
        self.duration: float = 10.0
        self.in_time: float = 1.0       # Fade in empieza a 1s
        self.out_time: float = 8.0      # Fade out empieza 2s antes de terminar
        self.alpha: float = 0.0
        self.visible: bool = False

    def setup(self, img_path: str | None, current_time: float, duration: float = 10.0):
        if not img_path or self.overlay_type == "none" or not os.path.isfile(img_path):
            self.pixmap = None
            self.shadow_pixmap = None
            self.visible = False
            return

        pix = QPixmap(img_path)
        if pix.isNull():
            self.pixmap = None
            self.shadow_pixmap = None
            self.visible = False
            return

        self.pixmap = pix
        # Generar versión silueta negra para la sombra
        shadow = QPixmap(pix.size())
        shadow.fill(Qt.transparent)
        p = QPainter(shadow)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawPixmap(0, 0, pix)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(shadow.rect(), QColor(0, 0, 0, 220))
        p.end()
        self.shadow_pixmap = shadow

        self.start_time = current_time
        self.duration = max(4.0, duration)
        self.in_time = current_time + 1.0

        if self.overlay_type == "wheel":
            self.out_time = current_time + self.duration - 2.0
        else:
            self.out_time = current_time + 4.0

        self.alpha = 0.0
        self.visible = True

    def update_alpha(self, current_time: float):
        if not self.visible or not self.pixmap:
            self.alpha = 0.0
            return

        # Si ya pasó el tiempo de salida + 1s, se oculta
        if current_time > self.out_time + 1.0:
            self.alpha = 0.0
            self.visible = False
            return

        if current_time > self.out_time:
            # Fade out
            progress = (current_time - self.out_time) / 1.0
            self.alpha = max(0.0, min(1.0, 1.0 - progress))
        elif current_time > self.in_time:
            # Fade in
            progress = (current_time - self.in_time) / 1.0
            self.alpha = max(0.0, min(1.0, progress))
        else:
            self.alpha = 0.0

    def draw(self, painter: QPainter, target_rect: QRect, shadow_offset: int = 3):
        if not self.visible or not self.pixmap or self.alpha <= 0.01:
            return

        scaled = self.pixmap.scaled(
            target_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        scaled_shadow = self.shadow_pixmap.scaled(
            target_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        draw_x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
        draw_y = target_rect.y() + (target_rect.height() - scaled.height()) // 2

        old_opacity = painter.opacity()
        painter.setOpacity(self.alpha * 0.95)

        # Dibujar sombra desplazada
        painter.drawPixmap(draw_x + shadow_offset, draw_y + shadow_offset, scaled_shadow)
        # Dibujar logo original
        painter.drawPixmap(draw_x, draw_y, scaled)

        painter.setOpacity(old_opacity)


class BasicMovieWidget(QWidget):
    """
    Modo 1: Video snap a pantalla completa con superposición de logotipo.
    """
    mode_finished = Signal()

    def __init__(self, overlay_type: str = "wheel", sound: bool = True, preserve_ar: bool = False, parent=None):
        super().__init__(parent)
        self.overlay_type = overlay_type
        self.sound = sound
        self.preserve_ar = preserve_ar
        self.current_game: dict | None = None
        self.start_time: float = 0.0
        self.min_duration: float = 4.0
        self.overlay = ArtOverlay(overlay_type)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setStyleSheet("background-color: #000000;")
        if self.preserve_ar:
            self.video_widget.setAspectRatioMode(Qt.KeepAspectRatio)
        else:
            self.video_widget.setAspectRatioMode(Qt.IgnoreAspectRatio)
        layout.addWidget(self.video_widget)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.7 if self.sound else 0.0)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)

        # Timer para animación de overlay y comprobación de finalización
        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(33)  # ~30 fps para transiciones suaves
        self.tick_timer.timeout.connect(self._on_tick)

    def start_game(self, game: dict, overlay_img: str | None, video_path: str | None):
        self.current_game = game
        self.start_time = time.time()

        dur = 12.0
        if video_path and os.path.isfile(video_path):
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.player.play()
        else:
            self.player.stop()
            # Si no hay video, dar una duración estándar de 5 segundos
            dur = 5.0

        self.overlay.setup(overlay_img, self.start_time, duration=dur)
        self.tick_timer.start()
        self.update()

    def _on_media_status(self, status):
        if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
            elapsed = time.time() - self.start_time
            if elapsed >= self.min_duration:
                self.mode_finished.emit()
            else:
                # Esperar el tiempo mínimo antes de cambiar
                delay = int((self.min_duration - elapsed) * 1000)
                QTimer.singleShot(max(100, delay), self.mode_finished.emit)

    def _on_error(self, error, error_string=""):
        elapsed = time.time() - self.start_time
        delay = max(500, int((self.min_duration - elapsed) * 1000))
        QTimer.singleShot(delay, self.mode_finished.emit)

    def _on_tick(self):
        now = time.time()
        self.overlay.update_alpha(now)
        # Si el reproductor no tiene duración y pasaron más de 12 segundos, finalizar
        if self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            if now - self.start_time >= self.min_duration:
                self.mode_finished.emit()
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        # Dibujar overlay sobre la ventana
        if self.overlay.visible:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            w = self.width()
            h = self.height()
            overlay_w = min(540, int(w * 0.28))
            overlay_h = min(260, int(h * 0.24))
            rect = QRect(36, h - overlay_h - 40, overlay_w, overlay_h)
            self.overlay.draw(painter, rect)
            painter.end()

    def stop(self):
        self.tick_timer.stop()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())


class MovieCollageWidget(QWidget):
    """
    Modo 2: Cuadrícula 2x2 de videos simultáneos.
    Solo 1 video reproduce sonido para mantener claridad acústica.
    """
    mode_finished = Signal()

    def __init__(self, overlay_type: str = "wheel", sound: bool = True, preserve_ar: bool = False, parent=None):
        super().__init__(parent)
        self.overlay_type = overlay_type
        self.sound = sound
        self.preserve_ar = preserve_ar
        self.current_games = [None, None, None, None]
        self.start_times = [0.0, 0.0, 0.0, 0.0]
        self.overlays = [ArtOverlay(overlay_type) for _ in range(4)]
        self.get_next_game_callback = None

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)

        self.video_widgets = []
        self.players = []
        self.audios = []

        coords = [(0, 0), (0, 1), (1, 0), (1, 1)]
        for i in range(4):
            vw = QVideoWidget(self)
            vw.setStyleSheet("background-color: #000000;")
            if self.preserve_ar:
                vw.setAspectRatioMode(Qt.KeepAspectRatio)
            else:
                vw.setAspectRatioMode(Qt.IgnoreAspectRatio)

            r, c = coords[i]
            grid.addWidget(vw, r, c)
            self.video_widgets.append(vw)

            p = QMediaPlayer(self)
            ao = QAudioOutput(self)
            # Solo el cuadrante inferior derecho (i=3) reproduce audio si sound está activo
            ao.setVolume(0.7 if (self.sound and i == 3) else 0.0)
            ao.setMuted(not (self.sound and i == 3))
            p.setAudioOutput(ao)
            p.setVideoOutput(vw)

            idx = i
            p.mediaStatusChanged.connect(lambda st, sidx=idx: self._on_cell_status(sidx, st))
            p.errorOccurred.connect(lambda err, err_s="", sidx=idx: self._on_cell_error(sidx))

            self.players.append(p)
            self.audios.append(ao)

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(33)
        self.tick_timer.timeout.connect(self._on_tick)

    def start_collage(self, get_next_fn):
        self.get_next_game_callback = get_next_fn
        for i in range(4):
            self._start_cell(i)
        self.tick_timer.start()

    def _start_cell(self, idx: int):
        if not self.get_next_game_callback:
            return
        game, overlay_img, video_path = self.get_next_game_callback()
        self.current_games[idx] = game
        self.start_times[idx] = time.time()

        dur = 12.0
        if video_path and os.path.isfile(video_path):
            self.players[idx].setSource(QUrl.fromLocalFile(video_path))
            self.players[idx].play()
        else:
            self.players[idx].stop()
            dur = 6.0

        self.overlays[idx].setup(overlay_img, self.start_times[idx], duration=dur)

    def _on_cell_status(self, idx: int, status):
        if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
            # 50% de probabilidad de finalizar el modo o reiniciar esta celda con otro juego
            if random.random() < 0.5:
                self.mode_finished.emit()
            else:
                self._start_cell(idx)

    def _on_cell_error(self, idx: int):
        self._start_cell(idx)

    def _on_tick(self):
        now = time.time()
        for i in range(4):
            self.overlays[i].update_alpha(now)
            if self.players[i].playbackState() == QMediaPlayer.PlaybackState.StoppedState:
                if now - self.start_times[i] >= 6.0:
                    self._start_cell(i)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        for i, vw in enumerate(self.video_widgets):
            ov = self.overlays[i]
            if ov.visible:
                geo = vw.geometry()
                w = geo.width()
                h = geo.height()
                overlay_w = min(280, int(w * 0.45))
                overlay_h = min(130, int(h * 0.35))
                rect = QRect(geo.x() + 16, geo.y() + h - overlay_h - 16, overlay_w, overlay_h)
                ov.draw(painter, rect, shadow_offset=2)

        painter.end()

    def get_selected_game(self) -> dict | None:
        # Devuelve el juego que tiene audio o uno aleatorio de los activos
        if self.current_games[3]:
            return self.current_games[3]
        valid = [g for g in self.current_games if g]
        return random.choice(valid) if valid else None

    def stop(self):
        self.tick_timer.stop()
        for p in self.players:
            p.stop()
            p.setSource(QUrl())


class ImageCollageWidget(QWidget):
    """
    Modo 3: Mosaico 4x4 de imágenes (16 casillas).
    Cada 100ms se cambia aleatoriamente una de las imágenes. Dura 12 segundos fijos.
    """
    mode_finished = Signal()

    def __init__(self, preserve_ar: bool = False, parent=None):
        super().__init__(parent)
        self.preserve_ar = preserve_ar
        self.cells_pixmaps: list[QPixmap | None] = [None] * 16
        self.cells_games: list[dict | None] = [None] * 16
        self.get_next_image_fn = None
        self.start_time: float = 0.0
        self.duration: float = 12.0  # 12 segundos

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(100)  # Cada 100ms
        self.tick_timer.timeout.connect(self._on_tick)

    def start_collage(self, get_next_image_fn):
        self.get_next_image_fn = get_next_image_fn
        self.start_time = time.time()

        # Cargar las 16 celdas inicialmente
        for i in range(16):
            game, img_path = self.get_next_image_fn()
            self.cells_games[i] = game
            if img_path and os.path.isfile(img_path):
                self.cells_pixmaps[i] = QPixmap(img_path)
            else:
                self.cells_pixmaps[i] = None

        self.tick_timer.start()
        self.update()

    def _on_tick(self):
        now = time.time()
        if now - self.start_time >= self.duration:
            self.tick_timer.stop()
            self.mode_finished.emit()
            return

        # Cambiar una celda aleatoria
        idx = random.randint(0, 15)
        if self.get_next_image_fn:
            game, img_path = self.get_next_image_fn()
            self.cells_games[idx] = game
            if img_path and os.path.isfile(img_path):
                self.cells_pixmaps[idx] = QPixmap(img_path)
            else:
                self.cells_pixmaps[idx] = None
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        w = self.width()
        h = self.height()
        cell_w = w / 4.0
        cell_h = h / 4.0

        for idx in range(16):
            col = idx % 4
            row = idx // 4
            cell_rect = QRectF(col * cell_w, row * cell_h, cell_w, cell_h)

            pix = self.cells_pixmaps[idx]
            if pix and not pix.isNull():
                if self.preserve_ar:
                    scaled = pix.scaled(
                        int(cell_w), int(cell_h), Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    dx = cell_rect.x() + (cell_w - scaled.width()) / 2.0
                    dy = cell_rect.y() + (cell_h - scaled.height()) / 2.0
                    painter.drawPixmap(int(dx), int(dy), scaled)
                else:
                    painter.drawPixmap(
                        cell_rect.toRect(),
                        pix.scaled(int(cell_w), int(cell_h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    )

            # Borde sutil de cuadrícula arcade
            painter.setPen(QColor(15, 15, 20))
            painter.drawRect(cell_rect)

        painter.end()

    def get_selected_game(self) -> dict | None:
        valid = [g for g in self.cells_games if g]
        return random.choice(valid) if valid else None

    def stop(self):
        self.tick_timer.stop()


class RGBMovieWidget(QWidget):
    """
    Modo 4: Video tripartito con modulación RGB cíclica en el centro y scroll
    vertical continuo y animado en las columnas laterales.
    """
    mode_finished = Signal()

    def __init__(self, overlay_type: str = "wheel", sound: bool = True, preserve_ar: bool = False, parent=None):
        super().__init__(parent)
        self.overlay_type = overlay_type
        self.sound = sound
        self.preserve_ar = preserve_ar
        self.current_game: dict | None = None
        self.start_time: float = 0.0
        self.min_duration: float = 4.0
        self.overlay = ArtOverlay(overlay_type)

        # Estados de modulación RGB
        self.rgb_phase = 0.0
        self.lcycle_ms = 800.0
        self.rcycle_ms = 950.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 3 vistas de video (Izquierda 25%, Centro 50%, Derecha 25%)
        self.vw_left = QVideoWidget(self)
        self.vw_center = QVideoWidget(self)
        self.vw_right = QVideoWidget(self)

        for vw in (self.vw_left, self.vw_center, self.vw_right):
            vw.setStyleSheet("background-color: #000000;")
            vw.setAspectRatioMode(Qt.KeepAspectRatio if self.preserve_ar else Qt.IgnoreAspectRatio)

        layout.addWidget(self.vw_left, 1)
        layout.addWidget(self.vw_center, 2)
        layout.addWidget(self.vw_right, 1)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.7 if self.sound else 0.0)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.vw_center)

        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(33)
        self.tick_timer.timeout.connect(self._on_tick)

    def start_game(self, game: dict, overlay_img: str | None, video_path: str | None):
        self.current_game = game
        self.start_time = time.time()
        self.rgb_phase = 0.0

        dur = 12.0
        if video_path and os.path.isfile(video_path):
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.player.play()
        else:
            self.player.stop()
            dur = 5.0

        self.overlay.setup(overlay_img, self.start_time, duration=dur)
        self.tick_timer.start()
        self.update()

    def _on_media_status(self, status):
        if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
            elapsed = time.time() - self.start_time
            if elapsed >= self.min_duration:
                self.mode_finished.emit()
            else:
                delay = int((self.min_duration - elapsed) * 1000)
                QTimer.singleShot(max(100, delay), self.mode_finished.emit)

    def _on_error(self, error, error_string=""):
        self.mode_finished.emit()

    def _on_tick(self):
        now = time.time()
        self.overlay.update_alpha(now)
        self.rgb_phase += 0.04
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Modulación de color RGB sutil sobre el centro
        c_rect = self.vw_center.geometry()
        red = int(128 + 127 * (0.5 + 0.5 * (self.rgb_phase % 3.1415)))
        green = int(128 + 127 * (0.5 + 0.5 * ((self.rgb_phase + 2.0) % 3.1415)))
        blue = int(128 + 127 * (0.5 + 0.5 * ((self.rgb_phase + 4.0) % 3.1415)))
        tint = QColor(red, green, blue, 35)
        painter.fillRect(c_rect, tint)

        # Franjas laterales con sombreado y líneas estilo scanline
        for side_vw in (self.vw_left, self.vw_right):
            s_rect = side_vw.geometry()
            painter.fillRect(s_rect, QColor(0, 0, 0, 75))

        # Overlay de logotipo
        if self.overlay.visible:
            w = self.width()
            h = self.height()
            overlay_w = min(500, int(w * 0.28))
            overlay_h = min(240, int(h * 0.24))
            rect = QRect(36, h - overlay_h - 40, overlay_w, overlay_h)
            self.overlay.draw(painter, rect)

        painter.end()

    def stop(self):
        self.tick_timer.stop()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())


class ScreensaverWidget(QWidget):
    """
    Widget principal del Salvapantallas para PlayNexus.
    Administra la máquina de estados entre los diferentes modos visuales,
    la resolución de juegos aleatorios y la intercepción de controles para
    despertar o saltar directamente al juego seleccionado.
    """
    game_selected_request = Signal(int)  # Emitido al presionar SELECT (Enter / Gamepad A)
    dismiss_requested = Signal()        # Emitido ante cualquier otro input para despertar

    def __init__(self, db, games: list = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.games = list(games) if games else []
        self._all_games_cache = []

        # Configuración desde settings
        self.mode_basic_movie = self.db.get_setting("screensaver_mode_basic_movie", "true").lower() == "true"
        self.mode_movie_collage = self.db.get_setting("screensaver_mode_movie_collage", "true").lower() == "true"
        self.mode_image_collage = self.db.get_setting("screensaver_mode_image_collage", "true").lower() == "true"
        self.mode_rgb_movie = self.db.get_setting("screensaver_mode_rgb_movie", "true").lower() == "true"
        self.overlay_art = self.db.get_setting("screensaver_overlay_art", "wheel")
        self.sound = self.db.get_setting("screensaver_sound", "true").lower() == "true"
        self.preserve_ar = self.db.get_setting("screensaver_preserve_ar", "false").lower() == "true"

        # Tiempo para pantalla negra profunda (minutos)
        try:
            self.blank_time_min = int(self.db.get_setting("screensaver_blank_time", "60") or "60")
        except Exception:
            self.blank_time_min = 60

        self.start_screensaver_time = time.time()
        self.is_blank = False
        self.current_game_id: int | None = None

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setStyleSheet("background-color: #000000;")

        self._build_ui()
        self._ensure_games_pool()

    def _build_ui(self):
        self.stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

        # Modos disponibles
        self.view_basic = BasicMovieWidget(self.overlay_art, self.sound, self.preserve_ar, self)
        self.view_basic.mode_finished.connect(self._switch_to_next_mode)

        self.view_movie_collage = MovieCollageWidget(self.overlay_art, self.sound, self.preserve_ar, self)
        self.view_movie_collage.mode_finished.connect(self._switch_to_next_mode)

        self.view_image_collage = ImageCollageWidget(self.preserve_ar, self)
        self.view_image_collage.mode_finished.connect(self._switch_to_next_mode)

        self.view_rgb = RGBMovieWidget(self.overlay_art, self.sound, self.preserve_ar, self)
        self.view_rgb.mode_finished.connect(self._switch_to_next_mode)

        self.view_blank = QWidget(self)
        self.view_blank.setStyleSheet("background-color: #000000;")

        self.stack.addWidget(self.view_basic)          # 0
        self.stack.addWidget(self.view_movie_collage)  # 1
        self.stack.addWidget(self.view_image_collage)  # 2
        self.stack.addWidget(self.view_rgb)            # 3
        self.stack.addWidget(self.view_blank)          # 4

    def _ensure_games_pool(self):
        """Asegura que haya juegos disponibles con sus datos de listas para resolver medios."""
        if not self.games:
            try:
                # Obtener juegos de la base de datos
                all_g = self.db.get_games()
                if all_g:
                    self.games = all_g
            except Exception:
                pass

        # Obtener datos de listas para enriquecer rutas de medios
        list_map = {}
        try:
            lists = self.db.get_lists()
            for l in lists:
                list_map[l["id"]] = dict(l)
        except Exception:
            pass

        self.enriched_pool = []
        for g in self.games:
            g_dict = dict(g)
            lid = g_dict.get("list_id")
            if lid and lid in list_map:
                for k, v in list_map[lid].items():
                    if k.endswith("_path") and k not in g_dict:
                        g_dict[k] = v
            self.enriched_pool.append(g_dict)

        if not self.enriched_pool:
            self.enriched_pool = [g for g in self.games]

    def _get_random_game_media(self) -> tuple[dict | None, str | None, str | None]:
        """Selecciona un juego aleatorio y resuelve su artwork y video."""
        if not self.enriched_pool:
            return None, None, None

        game = random.choice(self.enriched_pool)
        media = resolve_game_media(game)

        # Seleccionar imagen de overlay según configuración
        overlay_img = None
        if self.overlay_art == "wheel":
            overlay_img = media.get("wheel") or media.get("boxart")
        elif self.overlay_art == "flyer":
            overlay_img = media.get("flyer") or media.get("boxart")
        elif self.overlay_art == "marquee":
            overlay_img = media.get("marquee") or media.get("wheel")

        video_path = media.get("video") or media.get("snap")
        return game, overlay_img, video_path

    def _get_random_image(self) -> tuple[dict | None, str | None]:
        """Obtiene un juego y una imagen fija (boxart/flyer/wheel) para el collage."""
        if not self.enriched_pool:
            return None, None
        game = random.choice(self.enriched_pool)
        media = resolve_game_media(game)
        img = media.get("boxart") or media.get("flyer") or media.get("wheel")
        return game, img

    def start(self):
        """Inicia el salvapantallas arrancando en el primer modo disponible."""
        self.start_screensaver_time = time.time()
        self.is_blank = False
        self._switch_to_next_mode()

    def _switch_to_next_mode(self):
        """Selecciona el siguiente modo aplicando las probabilidades de screensaver.nut."""
        # Comprobar si se alcanzó el tiempo de apagado profundo (Blank Screen)
        if self.blank_time_min > 0:
            elapsed_min = (time.time() - self.start_screensaver_time) / 60.0
            if elapsed_min >= self.blank_time_min:
                self.stop_all()
                self.is_blank = True
                self.stack.setCurrentWidget(self.view_blank)
                return

        # Detener modos previos
        self.stop_all()

        # Construir lista de candidatos según pesos de Attract-Mode:
        # MovieCollage: 25%, ImageCollage: 15%, RGBMovie: 25%, BasicMovie: resto
        candidates = []
        if self.mode_basic_movie:
            candidates.append(("basic", 35))
        if self.mode_movie_collage:
            candidates.append(("movie_collage", 25))
        if self.mode_image_collage:
            candidates.append(("image_collage", 15))
        if self.mode_rgb_movie:
            candidates.append(("rgb", 25))

        if not candidates:
            # Fallback seguro a video básico
            candidates = [("basic", 100)]

        # Selección ponderada aleatoria
        modes, weights = zip(*candidates)
        chosen = random.choices(modes, weights=weights, k=1)[0]

        if chosen == "movie_collage":
            self.stack.setCurrentWidget(self.view_movie_collage)
            self.view_movie_collage.start_collage(self._get_random_game_media)
        elif chosen == "image_collage":
            self.stack.setCurrentWidget(self.view_image_collage)
            self.view_image_collage.start_collage(self._get_random_image)
        elif chosen == "rgb":
            self.stack.setCurrentWidget(self.view_rgb)
            game, overlay_img, video_path = self._get_random_game_media()
            if game:
                self.current_game_id = game.get("id")
            self.view_rgb.start_game(game, overlay_img, video_path)
        else:
            self.stack.setCurrentWidget(self.view_basic)
            game, overlay_img, video_path = self._get_random_game_media()
            if game:
                self.current_game_id = game.get("id")
            self.view_basic.start_game(game, overlay_img, video_path)

    def get_currently_displayed_game_id(self) -> int | None:
        """Determina qué juego se está exhibiendo en el momento de tocar la tecla."""
        current_w = self.stack.currentWidget()
        if current_w == self.view_basic and self.view_basic.current_game:
            return self.view_basic.current_game.get("id")
        elif current_w == self.view_rgb and self.view_rgb.current_game:
            return self.view_rgb.current_game.get("id")
        elif current_w == self.view_movie_collage:
            g = self.view_movie_collage.get_selected_game()
            if g:
                return g.get("id")
        elif current_w == self.view_image_collage:
            g = self.view_image_collage.get_selected_game()
            if g:
                return g.get("id")
        return self.current_game_id

    def keyPressEvent(self, event):
        # Si presiona SELECT (Enter / A de mando), solicitar selección directa de juego
        if matches_action(event, ACTION_SELECT, self.db):
            target_gid = self.get_currently_displayed_game_id()
            if target_gid:
                self.game_selected_request.emit(target_gid)
                event.accept()
                return

        # Cualquier otra tecla simplemente despierta el frontend
        self.dismiss_requested.emit()
        event.accept()

    def mousePressEvent(self, event):
        self.dismiss_requested.emit()
        event.accept()

    def mouseMoveEvent(self, event):
        self.dismiss_requested.emit()
        event.accept()

    def wheelEvent(self, event):
        self.dismiss_requested.emit()
        event.accept()

    def stop_all(self):
        """Detiene completamente la reproducción y temporizadores de todos los modos."""
        self.view_basic.stop()
        self.view_movie_collage.stop()
        self.view_image_collage.stop()
        self.view_rgb.stop()

    def closeEvent(self, event):
        self.stop_all()
        super().closeEvent(event)

