"""
=============================================================================
PlayNexus - Motor y Widget de Salvapantallas (Screensaver)
=============================================================================
Recreación y optimización para PySide6 del sistema oficial de salvapantallas
de Attract-Mode (screensaver.nut).

Modos incluidos:
1. MovieMode: Video snap a pantalla completa con logo wheel superpuesto en la
   parte inferior derecha dentro del mismo video (fade y sombra proyectada).
2. MovieCollageMode: Cuadrícula 2x2 de videos simultáneos (uno con audio),
   cada uno con su respectivo logo wheel en la esquina inferior derecha.
3. ImageCollageMode: Mosaico 4x4 de imágenes dinámicas que rotan cada 100ms.
4. RGBMovieMode: Video tripartito con modulación de color RGB y logo wheel en
   la esquina inferior derecha del video central.
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

from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QRect, QRectF, QPoint
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QFont, QFontMetrics, QPen, QImage, QTransform
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QStackedWidget, QApplication
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from playnexus.services.media import resolve_game_media
from playnexus.services.controls import (
    matches_action, ACTION_SELECT, ACTION_NAV_BACK, ACTION_CLOSE_FRONTEND
)


class ArtOverlay:
    """
    Gestiona el renderizado de un logotipo (wheel/logo) con sombra negra
    proyectada y transiciones suaves de opacidad (fade-in inicial y fade-out final).
    Ubicación: siempre en la parte inferior derecha dentro del video.
    """
    def __init__(self, overlay_type: str = "wheel"):
        self.overlay_type = overlay_type.lower().strip()
        self.pixmap: QPixmap | None = None
        self.shadow_pixmap: QPixmap | None = None
        self.title_text: str = ""
        self.start_time: float = 0.0
        self.duration: float = 10.0
        self.in_time: float = 0.2       # Fade in suave casi inmediato (0.2s)
        self.out_time: float = 9.5      # Se mantiene visible durante la reproducción
        self.alpha: float = 0.0
        self.visible: bool = False

    def setup(self, img_path: str | None, current_time: float, duration: float = 10.0, title: str = ""):
        self.title_text = title
        self.start_time = current_time
        self.duration = max(4.0, duration)
        self.in_time = current_time + 0.2
        self.out_time = current_time + self.duration - 0.4
        self.alpha = 0.0

        pix = None
        if img_path and os.path.isfile(img_path):
            loaded = QPixmap(img_path)
            if not loaded.isNull():
                pix = loaded

        # Si no hay imagen wheel disponible pero tenemos título, generamos un badge elegante
        if not pix and self.title_text:
            pix = self._render_title_badge(self.title_text)

        if not pix:
            self.pixmap = None
            self.shadow_pixmap = None
            self.visible = False
            return

        self.pixmap = pix

        # Generar silueta negra para sombra proyectada
        shadow = QPixmap(pix.size())
        shadow.fill(Qt.transparent)
        p = QPainter(shadow)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawPixmap(0, 0, pix)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(shadow.rect(), QColor(0, 0, 0, 230))
        p.end()
        self.shadow_pixmap = shadow

        self.visible = True

    def _render_title_badge(self, title: str) -> QPixmap:
        """Genera una placa gráfica estilizada si el juego no cuenta con logo wheel individual."""
        font = QFont("Arial", 16, QFont.Bold)
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(title)
        w = max(240, text_rect.width() + 40)
        h = max(58, text_rect.height() + 24)
        pix = QPixmap(w, h)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(15, 15, 24, 215))
        p.setPen(QPen(QColor(255, 180, 0, 220), 2))
        p.drawRoundedRect(2, 2, w - 4, h - 4, 8, 8)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        p.drawText(pix.rect(), Qt.AlignCenter, title)
        p.end()
        return pix

    def update_alpha(self, current_time: float):
        if not self.visible or not self.pixmap:
            self.alpha = 0.0
            return

        if current_time > self.out_time + 0.4:
            self.alpha = 0.0
            self.visible = False
            return

        if current_time > self.out_time:
            # Fade out
            progress = (current_time - self.out_time) / 0.4
            self.alpha = max(0.0, min(1.0, 1.0 - progress))
        elif current_time > self.in_time:
            # Fade in rápido y suave
            progress = (current_time - self.in_time) / 0.4
            self.alpha = max(0.0, min(1.0, progress))
        else:
            self.alpha = 0.0

    def draw(self, painter: QPainter, target_rect: QRect, shadow_offset: int = 4):
        if not self.visible or not self.pixmap or self.alpha <= 0.01:
            return

        scaled = self.pixmap.scaled(
            target_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        scaled_shadow = self.shadow_pixmap.scaled(
            target_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        # Alinear a la derecha y abajo dentro del rectángulo objetivo
        draw_x = target_rect.right() - scaled.width()
        draw_y = target_rect.bottom() - scaled.height()

        old_opacity = painter.opacity()
        painter.setOpacity(self.alpha * 0.96)

        # Sombra proyectada desplazada
        painter.drawPixmap(draw_x + shadow_offset, draw_y + shadow_offset, scaled_shadow)
        # Logotipo original
        painter.drawPixmap(draw_x, draw_y, scaled)

        painter.setOpacity(old_opacity)


class BasicMovieWidget(QWidget):
    """
    Modo 1: Video snap a pantalla completa con su logo wheel en la parte inferior derecha.
    Utiliza QVideoSink para renderizado directo en paintEvent sin capas nativas que lo ocluyan.
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

        self._current_frame: QImage | None = None
        self._fallback_pixmap: QPixmap | None = None

        self.setStyleSheet("background-color: #000000;")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.7 if self.sound else 0.0)
        self.player.setAudioOutput(self.audio_output)

        self.video_sink = QVideoSink(self)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame)

        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(33)
        self.tick_timer.timeout.connect(self._on_tick)

    def _on_video_frame(self, frame):
        if frame.isValid():
            self._current_frame = frame.toImage()
            self.update()

    def start_game(self, game: dict, overlay_img: str | None, video_path: str | None, fallback_img: str | None = None):
        self.current_game = game
        self.start_time = time.time()
        self._current_frame = None
        title = game.get("title", "") if game else ""

        dur = 12.0
        if video_path and os.path.isfile(video_path):
            self._fallback_pixmap = None
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.player.play()
        else:
            self.player.stop()
            if fallback_img and os.path.isfile(fallback_img):
                self._fallback_pixmap = QPixmap(fallback_img)
            else:
                self._fallback_pixmap = None
            dur = 6.0

        self.overlay.setup(overlay_img, self.start_time, duration=dur, title=title)
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
        elapsed = time.time() - self.start_time
        delay = max(500, int((self.min_duration - elapsed) * 1000))
        QTimer.singleShot(delay, self.mode_finished.emit)

    def _on_tick(self):
        now = time.time()
        self.overlay.update_alpha(now)
        self.update()

        if self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            if now - self.start_time >= self.min_duration:
                self.mode_finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))

        # 1. Dibujar frame de video o imagen de fallback
        video_rect = QRect(0, 0, w, h)
        if self._current_frame and not self._current_frame.isNull():
            fw = self._current_frame.width()
            fh = self._current_frame.height()
            if self.preserve_ar and fw > 0 and fh > 0:
                s = min(w / fw, h / fh)
                dw = int(fw * s)
                dh = int(fh * s)
                dx = (w - dw) // 2
                dy = (h - dh) // 2
                video_rect = QRect(dx, dy, dw, dh)
                painter.drawImage(video_rect, self._current_frame)
            else:
                painter.drawImage(QRect(0, 0, w, h), self._current_frame)
        elif self._fallback_pixmap and not self._fallback_pixmap.isNull():
            pw = self._fallback_pixmap.width()
            ph = self._fallback_pixmap.height()
            s = min(w / pw, h / ph)
            dw = int(pw * s)
            dh = int(ph * s)
            dx = (w - dw) // 2
            dy = (h - dh) // 2
            video_rect = QRect(dx, dy, dw, dh)
            painter.drawPixmap(video_rect, self._fallback_pixmap)

        # 2. Dibujar logo wheel en la parte inferior derecha dentro del área de video
        if self.overlay and self.overlay.visible:
            overlay_w = min(540, int(video_rect.width() * 0.32))
            overlay_h = min(260, int(video_rect.height() * 0.26))
            margin_right = 36
            margin_bottom = 36
            target_rect = QRect(
                video_rect.right() - overlay_w - margin_right,
                video_rect.bottom() - overlay_h - margin_bottom,
                overlay_w,
                overlay_h
            )
            self.overlay.draw(painter, target_rect, shadow_offset=4)

        painter.end()

    def stop(self):
        self.tick_timer.stop()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        self._current_frame = None
        self._fallback_pixmap = None


class MovieCollageWidget(QWidget):
    """
    Modo 2: Cuadrícula 2x2 de videos simultáneos mediante QVideoSink.
    Cada celda cuenta con su respectivo logo wheel en la esquina inferior derecha.
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
        self.current_frames: list[QImage | None] = [None, None, None, None]
        self.get_next_game_callback = None

        self.setStyleSheet("background-color: #000000;")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

        self.players = []
        self.audios = []
        self.sinks = []

        for i in range(4):
            p = QMediaPlayer(self)
            ao = QAudioOutput(self)
            ao.setVolume(0.7 if (self.sound and i == 3) else 0.0)
            ao.setMuted(not (self.sound and i == 3))
            p.setAudioOutput(ao)

            sink = QVideoSink(self)
            sink.videoFrameChanged.connect(lambda f, sidx=i: self._on_cell_frame(sidx, f))
            p.setVideoSink(sink)

            idx = i
            p.mediaStatusChanged.connect(lambda st, sidx=idx: self._on_cell_status(sidx, st))
            p.errorOccurred.connect(lambda err, err_s="", sidx=idx: self._on_cell_error(sidx))

            self.players.append(p)
            self.audios.append(ao)
            self.sinks.append(sink)

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(33)
        self.tick_timer.timeout.connect(self._on_tick)

    def _on_cell_frame(self, idx: int, frame):
        if frame.isValid():
            self.current_frames[idx] = frame.toImage()
            self.update()

    def start_collage(self, get_next_game_callback):
        self.get_next_game_callback = get_next_game_callback
        for i in range(4):
            self._start_cell(i)
        self.tick_timer.start()

    def _start_cell(self, idx: int):
        if not self.get_next_game_callback:
            return

        game, overlay_img, video_path = self.get_next_game_callback()
        self.current_games[idx] = game
        self.start_times[idx] = time.time()
        self.current_frames[idx] = None
        title = game.get("title", "") if game else ""

        dur = 12.0
        if video_path and os.path.isfile(video_path):
            self.players[idx].setSource(QUrl.fromLocalFile(video_path))
            self.players[idx].play()
        else:
            self.players[idx].stop()
            dur = 6.0

        self.overlays[idx].setup(overlay_img, self.start_times[idx], duration=dur, title=title)
        self.update()

    def _on_cell_status(self, idx: int, status):
        if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))

        gap = 4
        cell_w = (w - gap) / 2.0
        cell_h = (h - gap) / 2.0

        coords = [(0, 0), (0, 1), (1, 0), (1, 1)]
        for i in range(4):
            r, c = coords[i]
            cx = int(c * (cell_w + gap))
            cy = int(r * (cell_h + gap))
            cw = int(cell_w)
            ch = int(cell_h)
            cell_rect = QRect(cx, cy, cw, ch)

            # 1. Dibujar frame de video
            frame = self.current_frames[i]
            if frame and not frame.isNull():
                fw = frame.width()
                fh = frame.height()
                if self.preserve_ar and fw > 0 and fh > 0:
                    s = min(cw / fw, ch / fh)
                    dw = int(fw * s)
                    dh = int(fh * s)
                    dx = cx + (cw - dw) // 2
                    dy = cy + (ch - dh) // 2
                    painter.drawImage(QRect(dx, dy, dw, dh), frame)
                else:
                    painter.drawImage(cell_rect, frame)
            else:
                painter.fillRect(cell_rect, QColor(10, 10, 15))

            # 2. Borde sutil
            painter.setPen(QColor(30, 30, 40))
            painter.drawRect(cell_rect)

            # 3. Logo wheel en la esquina inferior derecha de cada celda
            ov = self.overlays[i]
            if ov.visible:
                overlay_w = min(280, int(cw * 0.46))
                overlay_h = min(130, int(ch * 0.35))
                margin_right = 16
                margin_bottom = 16
                target_rect = QRect(
                    cell_rect.right() - overlay_w - margin_right,
                    cell_rect.bottom() - overlay_h - margin_bottom,
                    overlay_w,
                    overlay_h
                )
                ov.draw(painter, target_rect, shadow_offset=3)

        painter.end()

    def get_selected_game(self) -> dict | None:
        if self.current_games[3]:
            return self.current_games[3]
        valid = [g for g in self.current_games if g]
        return random.choice(valid) if valid else None

    def stop(self):
        self.tick_timer.stop()
        for p in self.players:
            p.stop()
            p.setSource(QUrl())
        self.current_frames = [None, None, None, None]


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
        self.duration: float = 12.0

        self.setStyleSheet("background-color: #000000;")
        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(100)
        self.tick_timer.timeout.connect(self._on_tick)

    def start_collage(self, get_next_image_fn):
        self.get_next_image_fn = get_next_image_fn
        self.start_time = time.time()

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
    Modo 4: Video en la columna central mediante QVideoSink, con paneles laterales
    y modulación de color RGB interactiva, con el logo wheel en la esquina inferior derecha.
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

        self.rgb_phase = 0.0
        self._current_frame: QImage | None = None
        self._side_pixmap: QPixmap | None = None

        self.setStyleSheet("background-color: #000000;")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.7 if self.sound else 0.0)
        self.player.setAudioOutput(self.audio_output)

        self.video_sink = QVideoSink(self)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame)

        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(33)
        self.tick_timer.timeout.connect(self._on_tick)

    def _on_video_frame(self, frame):
        if frame.isValid():
            self._current_frame = frame.toImage()
            self.update()

    def start_game(self, game: dict, overlay_img: str | None, video_path: str | None, side_art: str | None = None):
        self.current_game = game
        self.start_time = time.time()
        self.rgb_phase = 0.0
        self._current_frame = None
        title = game.get("title", "") if game else ""

        dur = 12.0
        if video_path and os.path.isfile(video_path):
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.player.play()
        else:
            self.player.stop()
            dur = 5.0

        if side_art and os.path.isfile(side_art):
            self._side_pixmap = QPixmap(side_art)
        else:
            self._side_pixmap = None

        self.overlay.setup(overlay_img, self.start_time, duration=dur, title=title)
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))

        # Columnas: Izquierda 25%, Centro 50%, Derecha 25%
        side_w = int(w * 0.25)
        center_w = w - (side_w * 2)

        left_rect = QRect(0, 0, side_w, h)
        center_rect = QRect(side_w, 0, center_w, h)
        right_rect = QRect(side_w + center_w, 0, side_w, h)

        # 1. Paneles laterales con arte y sombreado
        if self._side_pixmap and not self._side_pixmap.isNull():
            for s_rect in (left_rect, right_rect):
                pw = self._side_pixmap.width()
                ph = self._side_pixmap.height()
                s = max(s_rect.width() / pw, s_rect.height() / ph)
                dw = int(pw * s)
                dh = int(ph * s)
                dx = s_rect.x() + (s_rect.width() - dw) // 2
                dy = s_rect.y() + (s_rect.height() - dh) // 2
                painter.save()
                painter.setClipRect(s_rect)
                painter.drawPixmap(dx, dy, dw, dh, self._side_pixmap)
                # Sombreado oscuro arcade sobre las columnas
                painter.fillRect(s_rect, QColor(0, 0, 0, 140))
                painter.restore()
        else:
            painter.fillRect(left_rect, QColor(10, 10, 16))
            painter.fillRect(right_rect, QColor(10, 10, 16))

        # 2. Video central
        video_rect = center_rect
        if self._current_frame and not self._current_frame.isNull():
            fw = self._current_frame.width()
            fh = self._current_frame.height()
            if self.preserve_ar and fw > 0 and fh > 0:
                s = min(center_w / fw, h / fh)
                dw = int(fw * s)
                dh = int(fh * s)
                dx = center_rect.x() + (center_w - dw) // 2
                dy = center_rect.y() + (h - dh) // 2
                video_rect = QRect(dx, dy, dw, dh)
                painter.drawImage(video_rect, self._current_frame)
            else:
                painter.drawImage(center_rect, self._current_frame)

        # 3. Tinte de modulación RGB sobre el video central
        red = int(128 + 127 * (0.5 + 0.5 * (self.rgb_phase % 3.1415)))
        green = int(128 + 127 * (0.5 + 0.5 * ((self.rgb_phase + 2.0) % 3.1415)))
        blue = int(128 + 127 * (0.5 + 0.5 * ((self.rgb_phase + 4.0) % 3.1415)))
        tint = QColor(red, green, blue, 35)
        painter.fillRect(video_rect, tint)

        # 4. Divisores sutiles de columnas
        painter.setPen(QColor(25, 25, 35))
        painter.drawLine(side_w, 0, side_w, h)
        painter.drawLine(side_w + center_w, 0, side_w + center_w, h)

        # 5. Logo wheel en la esquina inferior derecha dentro del video central
        if self.overlay and self.overlay.visible:
            overlay_w = min(420, int(video_rect.width() * 0.44))
            overlay_h = min(200, int(video_rect.height() * 0.26))
            margin_right = 24
            margin_bottom = 24
            target_rect = QRect(
                video_rect.right() - overlay_w - margin_right,
                video_rect.bottom() - overlay_h - margin_bottom,
                overlay_w,
                overlay_h
            )
            self.overlay.draw(painter, target_rect, shadow_offset=4)

        painter.end()

    def stop(self):
        self.tick_timer.stop()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        self._current_frame = None
        self._side_pixmap = None


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
        self.enriched_pool = []

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

        # Período de gracia inicial para ignorar eventos espurios de ratón al arrancar
        self._ignore_input_until = time.time() + 0.6
        self._initial_mouse_pos: QPoint | None = None

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setStyleSheet("background-color: #000000;")

        self._build_ui()
        self._ensure_games_pool()
        self._setup_gamepad()

    def _setup_gamepad(self):
        try:
            from playnexus.services.gamepad import get_gamepad_manager
            self._gp_mgr = get_gamepad_manager(self.db)
            self._gp_mgr.action_triggered.connect(self._on_gamepad_trigger)
        except Exception:
            self._gp_mgr = None

    def _on_gamepad_trigger(self, action_id: str):
        if time.time() < self._ignore_input_until:
            return
        if action_id == ACTION_SELECT:
            target_gid = self.get_currently_displayed_game_id()
            if target_gid:
                self.game_selected_request.emit(target_gid)
                return
        self.dismiss_requested.emit()

    def _build_ui(self):
        self.stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

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
        """Asegura que haya juegos enriquecidos disponibles de todas las listas."""
        if not self.games:
            try:
                all_g = []
                lists = self.db.get_lists(with_counts=False)
                for lst in lists:
                    lid = lst.get("id")
                    if lid:
                        all_g.extend(self.db.get_games(lid, enriched=True))
                if all_g:
                    self.games = all_g
            except Exception:
                pass

        list_map = {}
        try:
            lists = self.db.get_lists(with_counts=False)
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
                    if k.endswith("_path") and (k not in g_dict or not g_dict[k]):
                        g_dict[k] = v
            self.enriched_pool.append(g_dict)

        if not self.enriched_pool and self.games:
            self.enriched_pool = [dict(g) for g in self.games]

    def _get_random_game_media(self, require_video: bool = True) -> tuple[dict | None, str | None, str | None, str | None]:
        """
        Selecciona un juego aleatorio garantizando que tenga su video y su logo wheel.
        Devuelve (game, overlay_img, video_path, fallback_art).
        """
        if not self.enriched_pool:
            return None, None, None, None

        # Priorizar juegos que tengan TANTO video como logo wheel en disco
        for _ in range(40):
            game = random.choice(self.enriched_pool)
            media = resolve_game_media(game)
            v = media.get("video") or media.get("snap")
            wheel = media.get("wheel")
            if v and os.path.isfile(v):
                if wheel and os.path.isfile(wheel):
                    fallback_art = media.get("boxart") or media.get("flyer")
                    return game, wheel, v, fallback_art

        # Segundo intento: juegos con video existente (utilizando wheel o alternativa)
        for _ in range(30):
            game = random.choice(self.enriched_pool)
            media = resolve_game_media(game)
            v = media.get("video") or media.get("snap")
            if v and os.path.isfile(v):
                overlay = media.get("wheel") or media.get("marquee") or media.get("boxart") or media.get("flyer")
                fallback_art = media.get("boxart") or media.get("flyer")
                return game, overlay, v, fallback_art

        # Fallback general
        game = random.choice(self.enriched_pool)
        media = resolve_game_media(game)
        overlay_img = media.get("wheel") or media.get("boxart") or media.get("flyer")
        video_path = media.get("video") or media.get("snap")
        fallback_art = media.get("boxart") or media.get("flyer") or media.get("wheel")
        return game, overlay_img, video_path, fallback_art

    def _get_random_image(self) -> tuple[dict | None, str | None]:
        """Obtiene un juego y una imagen fija existente (boxart/flyer/wheel) para el collage."""
        if not self.enriched_pool:
            return None, None

        for _ in range(35):
            game = random.choice(self.enriched_pool)
            media = resolve_game_media(game)
            img = media.get("boxart") or media.get("flyer") or media.get("wheel")
            if img and os.path.isfile(img):
                return game, img

        game = random.choice(self.enriched_pool)
        media = resolve_game_media(game)
        return game, media.get("boxart") or media.get("flyer") or media.get("wheel")

    def start(self):
        """Inicia el salvapantallas arrancando en el primer modo disponible."""
        self.start_screensaver_time = time.time()
        self.is_blank = False
        self._ignore_input_until = time.time() + 0.6
        self._initial_mouse_pos = None
        self._switch_to_next_mode()

    def _switch_to_next_mode(self):
        """Selecciona el siguiente modo aplicando las probabilidades de screensaver.nut."""
        if self.blank_time_min > 0:
            elapsed_min = (time.time() - self.start_screensaver_time) / 60.0
            if elapsed_min >= self.blank_time_min:
                self.stop_all()
                self.is_blank = True
                self.stack.setCurrentWidget(self.view_blank)
                return

        self.stop_all()

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
            candidates = [("basic", 100)]

        modes, weights = zip(*candidates)
        chosen = random.choices(modes, weights=weights, k=1)[0]

        if chosen == "movie_collage":
            self.stack.setCurrentWidget(self.view_movie_collage)
            self.view_movie_collage.start_collage(lambda: self._get_random_game_media(require_video=True)[:3])
        elif chosen == "image_collage":
            self.stack.setCurrentWidget(self.view_image_collage)
            self.view_image_collage.start_collage(self._get_random_image)
        elif chosen == "rgb":
            self.stack.setCurrentWidget(self.view_rgb)
            game, overlay_img, video_path, fallback_art = self._get_random_game_media(require_video=True)
            if game:
                self.current_game_id = game.get("id")
            self.view_rgb.start_game(game, overlay_img, video_path, side_art=fallback_art)
        else:
            self.stack.setCurrentWidget(self.view_basic)
            game, overlay_img, video_path, fallback_art = self._get_random_game_media(require_video=True)
            if game:
                self.current_game_id = game.get("id")
            self.view_basic.start_game(game, overlay_img, video_path, fallback_img=fallback_art)

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
        if time.time() < self._ignore_input_until:
            event.accept()
            return

        if matches_action(event, ACTION_SELECT, self.db):
            target_gid = self.get_currently_displayed_game_id()
            if target_gid:
                self.game_selected_request.emit(target_gid)
                event.accept()
                return

        self.dismiss_requested.emit()
        event.accept()

    def mousePressEvent(self, event):
        if time.time() < self._ignore_input_until:
            event.accept()
            return
        self.dismiss_requested.emit()
        event.accept()

    def mouseMoveEvent(self, event):
        if time.time() < self._ignore_input_until:
            return

        pos = event.globalPosition().toPoint()
        if self._initial_mouse_pos is None:
            self._initial_mouse_pos = pos
            return

        delta = (pos - self._initial_mouse_pos).manhattanLength()
        if delta > 15:
            self.dismiss_requested.emit()
            event.accept()

    def wheelEvent(self, event):
        if time.time() < self._ignore_input_until:
            return
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
