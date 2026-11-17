"""
Pestaña Rom Manager para el Configurador de PlayNexus.

Permite seleccionar una lista de ROMs y un diseño visual (Layout),
auditar qué archivos de media existen y cuáles faltan según el MEDIA_REQUIREMENTS
explícito del layout, previsualizar imágenes (con soporte de transparencia) y videos,
y asignar, renombrar o eliminar archivos de media directamente.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QRect, QSize, QPoint
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPen, QPixmap, QBrush, QDragEnterEvent, QDropEvent
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QFrame, QStackedWidget, QSlider, QCheckBox, QFileDialog, QMessageBox,
    QAbstractItemView, QProgressBar, QScrollArea, QSizePolicy, QListWidget,
    QListWidgetItem, QApplication, QMenu, QLayout, QLayoutItem
)

from playnexus.db import Database
from playnexus.services.media import clear_media_cache, IMAGE_EXTS, VIDEO_EXTS
from playnexus.services.rom_manager import (
    AuditSummary,
    MediaRequirementSpec,
    OrphanMediaFile,
    RomAuditResult,
    SlotAuditResult,
    assign_media_file,
    audit_list_media,
    build_requirement_specs,
    delete_media_file,
    export_audit_csv,
    find_fuzzy_media_candidates,
    format_file_size,
    rename_orphan_media_file,
)
from playnexus.services.themes import get_layout_media_spec
from playnexus.ui.layouts import get_available_layouts
from playnexus.ui.table_utils import configure_details_table, paused_table_sorting


def _format_ms(ms: int) -> str:
    if ms <= 0:
        return "00:00"
    total_sec = ms // 1000
    mins, secs = divmod(total_sec, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours:d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _open_in_file_explorer(path: str, is_dir: bool = False):
    """Abre la ubicación del archivo o carpeta en el explorador del sistema."""
    if not path:
        return
    norm = os.path.normpath(path)
    try:
        if sys.platform.startswith("win"):
            if not is_dir and os.path.isfile(norm):
                subprocess.Popen(["explorer", "/select,", norm])
            elif os.path.isdir(norm):
                os.startfile(norm)
            elif os.path.isdir(os.path.dirname(norm)):
                os.startfile(os.path.dirname(norm))
        elif sys.platform == "darwin":
            target = norm if os.path.isdir(norm) else os.path.dirname(norm)
            subprocess.Popen(["open", target])
        else:
            target = norm if os.path.isdir(norm) else os.path.dirname(norm)
            subprocess.Popen(["xdg-open", target])
    except Exception:
        pass


class RomMediaScanWorker(QThread):
    """Ejecuta la auditoría de carpetas de media en segundo plano sin congelar la UI."""

    progress = Signal(int, int, str)
    finished_audit = Signal(object)  # AuditSummary
    failed = Signal(str)

    def __init__(
        self,
        list_row: dict[str, Any],
        games: list[dict[str, Any]],
        raw_spec: list[dict[str, Any]],
        layout_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.list_row = dict(list_row)
        self.games = [dict(g) for g in games]
        self.raw_spec = [dict(s) for s in raw_spec]
        self.layout_name = layout_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            clear_media_cache()
            summary = audit_list_media(
                list_row=self.list_row,
                games=self.games,
                raw_spec=self.raw_spec,
                layout_name=self.layout_name,
                progress_cb=lambda cur, tot, msg: self.progress.emit(cur, tot, msg),
                cancel_check=lambda: self._cancelled,
            )
            if not self._cancelled:
                self.finished_audit.emit(summary)
        except Exception as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))


class SortableTableItem(QTableWidgetItem):
    """Ítem de tabla que permite ordenar por un valor auxiliar oculto."""

    SORT_ROLE = Qt.UserRole + 10

    def __lt__(self, other: QTableWidgetItem) -> bool:
        v1 = self.data(self.SORT_ROLE)
        v2 = other.data(self.SORT_ROLE)
        if v1 is not None and v2 is not None and type(v1) is type(v2):
            return v1 < v2
        return super().__lt__(other)


class MediaCanvasWidget(QWidget):
    """
    Lienzo unificado para previsualizar imágenes (con fondo damero opcional
    para comprobar transparencias PNG), frames de video (vía QVideoSink) y zona Dropzone.
    """

    file_dropped = Signal(str)
    double_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAcceptDrops(True)

        self._mode: str = "empty"  # "empty" | "image" | "video"
        self._pixmap: QPixmap | None = None
        self._video_image: QImage | None = None
        self._checkerboard: bool = True
        self._can_drop: bool = False
        self._drag_active: bool = False
        self._empty_title: str = "Sin selección"
        self._empty_subtitle: str = ""
        self._allowed_drop_exts: tuple[str, ...] = ()

    def set_checkerboard(self, enabled: bool):
        self._checkerboard = bool(enabled)
        self.update()

    def set_drop_config(self, can_drop: bool, allowed_exts: tuple[str, ...] = ()):
        self._can_drop = bool(can_drop)
        self._allowed_drop_exts = tuple(e.lower() for e in (allowed_exts or ()))

    def show_empty(self, title: str, subtitle: str = ""):
        self._mode = "empty"
        self._pixmap = None
        self._video_image = None
        self._empty_title = title
        self._empty_subtitle = subtitle
        self.update()

    def show_image(self, pixmap: QPixmap | None, error_text: str = ""):
        if pixmap is None or pixmap.isNull():
            self.show_empty("No se pudo cargar la imagen", error_text)
            return
        self._mode = "image"
        self._video_image = None
        self._pixmap = pixmap
        self.update()

    def show_video_waiting(self, filename: str):
        self._mode = "video"
        self._pixmap = None
        self._video_image = None
        self._empty_title = "Cargando video…"
        self._empty_subtitle = filename
        self.update()

    def set_video_frame(self, frame_image: QImage | None):
        self._mode = "video"
        self._pixmap = None
        self._video_image = frame_image
        self.update()

    def _paint_checkerboard(self, painter: QPainter, rect: QRect):
        tile = 14
        c1 = QColor("#1a1e2a")
        c2 = QColor("#242a3a")
        painter.fillRect(rect, c1)
        painter.save()
        painter.setClipRect(rect)
        y = rect.top()
        row = 0
        while y < rect.bottom():
            x = rect.left() + (tile if row % 2 else 0)
            while x < rect.right():
                painter.fillRect(x, y, tile, tile, c2)
                x += tile * 2
            y += tile
            row += 1
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        full_rect = self.rect()
        bg_color = QColor("#0d1017") if self._mode == "video" else QColor("#12151f")
        painter.fillRect(full_rect, bg_color)

        inner = full_rect.adjusted(8, 8, -8, -8)
        if inner.width() <= 10 or inner.height() <= 10:
            return

        if self._mode == "image" and self._pixmap and not self._pixmap.isNull():
            scaled_size = self._pixmap.size().scaled(inner.size(), Qt.KeepAspectRatio)
            draw_x = inner.x() + (inner.width() - scaled_size.width()) // 2
            draw_y = inner.y() + (inner.height() - scaled_size.height()) // 2
            target_rect = QRect(draw_x, draw_y, scaled_size.width(), scaled_size.height())
            if self._checkerboard:
                self._paint_checkerboard(painter, target_rect)
            painter.drawPixmap(target_rect, self._pixmap)

        elif self._mode == "video":
            if self._video_image and not self._video_image.isNull():
                img_size = self._video_image.size().scaled(inner.size(), Qt.KeepAspectRatio)
                draw_x = inner.x() + (inner.width() - img_size.width()) // 2
                draw_y = inner.y() + (inner.height() - img_size.height()) // 2
                target_rect = QRect(draw_x, draw_y, img_size.width(), img_size.height())
                painter.drawImage(target_rect, self._video_image)
            else:
                painter.setPen(QColor("#94a3b8"))
                painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
                painter.drawText(
                    inner,
                    Qt.AlignCenter | Qt.TextWordWrap,
                    f"{self._empty_title}\n{self._empty_subtitle}".strip(),
                )
        else:
            pen = QPen(QColor("#31394f"), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor("#171b27")))
            painter.drawRoundedRect(inner, 10, 10)

            painter.setPen(QColor("#cbd5e1"))
            title_rect = QRect(inner.x() + 16, inner.y() + 16, inner.width() - 32, inner.height() // 2)
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            painter.drawText(title_rect, Qt.AlignHCenter | Qt.AlignBottom | Qt.TextWordWrap, self._empty_title)

            if self._empty_subtitle:
                sub_rect = QRect(
                    inner.x() + 20,
                    inner.y() + inner.height() // 2 + 8,
                    inner.width() - 40,
                    inner.height() // 2 - 20,
                )
                painter.setPen(QColor("#8894ab"))
                painter.setFont(QFont("Segoe UI", 9))
                painter.drawText(sub_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self._empty_subtitle)

        # Borde de resaltado al arrastrar un archivo válido encima
        border_col = QColor("#7c69ef") if self._drag_active else QColor("#2a3144")
        border_style = Qt.DashLine if self._drag_active else Qt.SolidLine
        painter.setPen(QPen(border_col, 2 if self._drag_active else 1, border_style))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(full_rect.adjusted(1, 1, -1, -1), 8, 8)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def _extract_valid_drop_file(self, mime_data) -> str | None:
        if not self._can_drop or not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            local = url.toLocalFile()
            if not os.path.isfile(local):
                continue
            ext = Path(local).suffix.lower()
            valid = self._allowed_drop_exts or (IMAGE_EXTS + VIDEO_EXTS)
            if ext in valid:
                return local
        return None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._extract_valid_drop_file(event.mimeData()):
            self._drag_active = True
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drag_active = False
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self._drag_active = False
        self.update()
        path = self._extract_valid_drop_file(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.file_dropped.emit(path)
        else:
            event.ignore()


class MediaPreviewWidget(QWidget):
    """
    Previsualizador dual completo para el Rom Manager:
    - Imágenes estáticas y transparentes (.png/.webp/.jpg) con dimensiones y peso.
    - Videos (.mp4/.mkv/.avi/.webm) con Play/Pausa/Stop, barra de búsqueda, tiempo, mute y volumen.
    - Acciones directas: Asignar/Reemplazar (archivo o Drag & Drop), Sugerencias difusas, Abrir carpeta, Eliminar.
    """

    assign_file_requested = Signal(str)       # source_path ("" = abrir diálogo)
    assign_folder_requested = Signal(str)     # media key
    rename_orphan_requested = Signal(str)     # source_path de archivo huérfano
    delete_file_requested = Signal(str)       # file_path actual

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_rom: RomAuditResult | None = None
        self._current_spec: MediaRequirementSpec | None = None
        self._current_slot: SlotAuditResult | None = None
        self._current_video_path: str = ""
        self._video_dims: tuple[int, int] | None = None
        self._seeking = False
        self._auto_play = True
        self._loop_video = True

        self._build_ui()
        self._setup_player()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Cabecera del slot previsualizado
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.slot_title_lbl = QLabel("Seleccioná un juego y un tipo de media")
        self.slot_title_lbl.setStyleSheet("font-weight: bold; font-size: 10.5pt; color: #e2e8f0;")
        self.slot_title_lbl.setWordWrap(True)
        header_row.addWidget(self.slot_title_lbl, 1)

        self.btn_checkerboard = QCheckBox("Fondo PNG")
        self.btn_checkerboard.setChecked(True)
        self.btn_checkerboard.setToolTip("Mostrar cuadrícula de transparencia detrás de imágenes PNG/WEBP")
        self.btn_checkerboard.setStyleSheet("font-size: 8.5pt; color: #9aa5b8;")
        self.btn_checkerboard.toggled.connect(self._on_checkerboard_toggled)
        header_row.addWidget(self.btn_checkerboard)
        layout.addLayout(header_row)

        # Lienzo unificado (Imagen / Video / Vacío)
        self.canvas = MediaCanvasWidget(self)
        self.canvas.file_dropped.connect(self._on_file_dropped)
        self.canvas.double_clicked.connect(self._on_canvas_double_clicked)
        layout.addWidget(self.canvas, 1)

        # Barra de metadatos del archivo actual
        self.meta_lbl = QLabel("—")
        self.meta_lbl.setStyleSheet("color: #9ba7bc; font-size: 8.5pt;")
        self.meta_lbl.setWordWrap(True)
        layout.addWidget(self.meta_lbl)

        # Barra de controles de video (oculta cuando es imagen o vacío)
        self.video_controls_frame = QFrame()
        self.video_controls_frame.setStyleSheet(
            "QFrame { background-color: #191d28; border: 1px solid #2a3144; border-radius: 6px; padding: 6px; }"
        )
        vc_layout = QVBoxLayout(self.video_controls_frame)
        vc_layout.setContentsMargins(8, 6, 8, 6)
        vc_layout.setSpacing(6)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        self.btn_play_pause = QPushButton("▶")
        self.btn_play_pause.setFixedWidth(36)
        self.btn_play_pause.setToolTip("Reproducir / Pausar video")
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)

        self.btn_stop = QPushButton("⏹")
        self.btn_stop.setFixedWidth(36)
        self.btn_stop.setToolTip("Detener video")
        self.btn_stop.clicked.connect(self.stop_video)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.sliderMoved.connect(self._on_seek_moved)

        self.time_lbl = QLabel("00:00 / 00:00")
        self.time_lbl.setStyleSheet("color: #cbd5e1; font-size: 8.5pt; font-family: Consolas, monospace;")

        seek_row.addWidget(self.btn_play_pause)
        seek_row.addWidget(self.btn_stop)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addWidget(self.time_lbl)
        vc_layout.addLayout(seek_row)

        audio_row = QHBoxLayout()
        audio_row.setSpacing(8)
        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setFixedWidth(36)
        self.btn_mute.setToolTip("Silenciar / Activar sonido del previsualizador")
        self.btn_mute.clicked.connect(self._toggle_mute)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.setMaximumWidth(110)
        self.vol_slider.setToolTip("Volumen de previsualización")
        self.vol_slider.valueChanged.connect(self._on_volume_changed)

        self.chk_loop = QCheckBox("Bucle")
        self.chk_loop.setChecked(True)
        self.chk_loop.toggled.connect(lambda c: setattr(self, "_loop_video", bool(c)))

        self.chk_autoplay = QCheckBox("Auto-reproducir")
        self.chk_autoplay.setChecked(True)
        self.chk_autoplay.toggled.connect(lambda c: setattr(self, "_auto_play", bool(c)))

        audio_row.addWidget(self.btn_mute)
        audio_row.addWidget(self.vol_slider)
        audio_row.addStretch()
        audio_row.addWidget(self.chk_loop)
        audio_row.addWidget(self.chk_autoplay)
        vc_layout.addLayout(audio_row)

        self.video_controls_frame.setVisible(False)
        layout.addWidget(self.video_controls_frame)

        # Panel de sugerencias difusas (visible cuando falta la media y hay archivos huérfanos parecidos)
        self.suggestions_frame = QFrame()
        self.suggestions_frame.setStyleSheet(
            "QFrame { background-color: #1b1f2d; border: 1px solid #353f59; border-radius: 6px; padding: 6px; }"
        )
        self.suggestions_layout = QVBoxLayout(self.suggestions_frame)
        self.suggestions_layout.setContentsMargins(8, 6, 8, 6)
        self.suggestions_layout.setSpacing(4)
        self.suggestions_frame.setVisible(False)
        layout.addWidget(self.suggestions_frame)

        # Botones de acción sobre el archivo del slot
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        self.btn_assign = QPushButton("📥 Asignar archivo…")
        self.btn_assign.setObjectName("primary")
        self.btn_assign.clicked.connect(lambda: self.assign_file_requested.emit(""))

        self.btn_set_folder = QPushButton("📁 Asignar carpeta…")
        self.btn_set_folder.clicked.connect(self._on_assign_folder_clicked)
        self.btn_set_folder.setVisible(False)

        self.btn_open_loc = QPushButton("📂 Abrir carpeta")
        self.btn_open_loc.clicked.connect(self._on_open_location_clicked)

        self.btn_delete = QPushButton("🗑 Eliminar")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        actions_row.addWidget(self.btn_assign, 1)
        actions_row.addWidget(self.btn_set_folder, 1)
        actions_row.addWidget(self.btn_open_loc)
        actions_row.addWidget(self.btn_delete)
        layout.addLayout(actions_row)

    def _setup_player(self):
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.70)
        self.player.setAudioOutput(self.audio_output)

        self.video_sink = QVideoSink(self)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame)

        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_player_error)

    def _on_checkerboard_toggled(self, checked: bool):
        self.canvas.set_checkerboard(checked)

    def _on_assign_folder_clicked(self):
        if self._current_spec:
            self.assign_folder_requested.emit(self._current_spec.key)

    def _on_file_dropped(self, source_path: str):
        if self._current_rom and self._current_spec and self._current_spec.folder_exists:
            self.assign_file_requested.emit(source_path)

    def _on_canvas_double_clicked(self):
        if self._current_video_path:
            self.toggle_play_pause()
        elif self._current_slot and self._current_slot.file_path:
            _open_in_file_explorer(self._current_slot.file_path, is_dir=False)

    def _on_open_location_clicked(self):
        if self._current_slot and self._current_slot.file_path and os.path.isfile(self._current_slot.file_path):
            _open_in_file_explorer(self._current_slot.file_path, is_dir=False)
        elif self._current_spec and self._current_spec.folder_exists:
            _open_in_file_explorer(self._current_spec.folder_path, is_dir=True)

    def _on_delete_clicked(self):
        if self._current_slot and self._current_slot.file_path:
            self.delete_file_requested.emit(self._current_slot.file_path)

    def stop_and_release(self, flush_events: bool = True):
        """Detiene el reproductor y libera el handle de archivo en Windows/Media Foundation."""
        self._current_video_path = ""
        self._video_dims = None
        try:
            self.player.stop()
            self.player.setSource(QUrl())
            if flush_events:
                app = QApplication.instance()
                if app:
                    app.processEvents()
        except Exception:
            pass
        self.seek_slider.setRange(0, 0)
        self.time_lbl.setText("00:00 / 00:00")
        self.btn_play_pause.setText("▶")

    def toggle_play_pause(self):
        if not self._current_video_path:
            return
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if not self.player.source().isValid() or self.player.source().toLocalFile() != self._current_video_path:
                self.player.setSource(QUrl.fromLocalFile(self._current_video_path))
            elif self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def stop_video(self):
        if not self._current_video_path:
            return
        self.player.stop()
        self.seek_slider.setValue(0)
        dur = self.player.duration()
        self.time_lbl.setText(f"00:00 / {_format_ms(dur)}")

    def _toggle_mute(self):
        muted = not self.audio_output.isMuted()
        self.audio_output.setMuted(muted)
        self.btn_mute.setText("🔇" if muted else "🔊")

    def _on_volume_changed(self, value: int):
        self.audio_output.setVolume(max(0.0, min(1.0, value / 100.0)))
        if value == 0:
            self.btn_mute.setText("🔇")
        elif not self.audio_output.isMuted():
            self.btn_mute.setText("🔊")

    def _on_seek_pressed(self):
        self._seeking = True

    def _on_seek_released(self):
        self._seeking = False
        self.player.setPosition(self.seek_slider.value())

    def _on_seek_moved(self, pos: int):
        dur = self.player.duration()
        self.time_lbl.setText(f"{_format_ms(pos)} / {_format_ms(dur)}")

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_pause.setText("⏸")
        else:
            self.btn_play_pause.setText("▶")

    def _on_position_changed(self, pos: int):
        if not self._seeking:
            self.seek_slider.setValue(pos)
            dur = self.player.duration()
            self.time_lbl.setText(f"{_format_ms(pos)} / {_format_ms(dur)}")

    def _on_duration_changed(self, dur: int):
        self.seek_slider.setRange(0, max(0, dur))
        pos = self.player.position()
        self.time_lbl.setText(f"{_format_ms(pos)} / {_format_ms(dur)}")

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._loop_video and self._current_video_path:
            self.player.setPosition(0)
            self.player.play()

    def _on_player_error(self, error, error_string=""):
        if self._current_video_path:
            self.canvas.show_empty("Error al reproducir video", error_string or "Códec o archivo no soportado")

    def _on_video_frame(self, frame):
        if not frame or not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return
        if self._video_dims is None:
            self._video_dims = (img.width(), img.height())
            self._refresh_meta_label()
        self.canvas.set_video_frame(img)

    def _refresh_meta_label(self):
        slot = self._current_slot
        if not slot or not slot.file_path:
            return
        fname = os.path.basename(slot.file_path)
        size_str = format_file_size(slot.size_bytes)
        parts = [fname, size_str]
        if self._video_dims:
            parts.insert(1, f"{self._video_dims[0]} × {self._video_dims[1]} px")
        if slot.note:
            parts.append(f"⚠ {slot.note}")
        self.meta_lbl.setText("  ·  ".join(parts))

    def _rebuild_suggestions(self, candidates: list[tuple[OrphanMediaFile, float]]):
        while self.suggestions_layout.count():
            item = self.suggestions_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        if not candidates or not self._current_rom:
            self.suggestions_frame.setVisible(False)
            return

        lbl = QLabel(
            f"✨ <b>Posibles coincidencias en la carpeta</b> (sin ROM asociada — clic para renombrar a "
            f"<code>{self._current_rom.stem}</code>):"
        )
        lbl.setStyleSheet("color: #c4b5fd; font-size: 8.5pt;")
        lbl.setWordWrap(True)
        self.suggestions_layout.addWidget(lbl)

        for orphan, score in candidates[:3]:
            pct = int(round(score * 100))
            btn = QPushButton(f"🪄 Renombrar: {orphan.filename}  ({pct}%)")
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 5px 8px; font-size: 8.5pt; "
                "background-color: #24293d; border-color: #4b5578; }"
                "QPushButton:hover { background-color: #343c5c; }"
            )
            btn.clicked.connect(lambda checked=False, p=orphan.file_path: self.rename_orphan_requested.emit(p))
            self.suggestions_layout.addWidget(btn)

        self.suggestions_frame.setVisible(True)

    def clear_preview(self, message: str = "Seleccioná una lista y escaneá para comenzar."):
        self.stop_and_release()
        self._current_rom = None
        self._current_spec = None
        self._current_slot = None
        self.slot_title_lbl.setText("Previsualizador de Media")
        self.meta_lbl.setText("—")
        self.video_controls_frame.setVisible(False)
        self.btn_checkerboard.setVisible(False)
        self.suggestions_frame.setVisible(False)
        self.btn_assign.setVisible(False)
        self.btn_set_folder.setVisible(False)
        self.btn_open_loc.setVisible(False)
        self.btn_delete.setVisible(False)
        self._set_pdf_button_path("")
        self.canvas.set_drop_config(False)
        self.canvas.show_empty("Sin selección", message)

    def display_slot(
        self,
        rom: RomAuditResult | None,
        spec: MediaRequirementSpec | None,
        slot: SlotAuditResult | None,
        fuzzy_candidates: list[tuple[OrphanMediaFile, float]] | None = None,
    ):
        self.stop_and_release()
        self._current_rom = rom
        self._current_spec = spec
        self._current_slot = slot

        if not rom or not spec or not slot:
            self.clear_preview("Seleccioná una fila en la tabla para previsualizar su media.")
            return

        req_badge = "★ Obligatorio" if spec.required else "Opcional"
        self.slot_title_lbl.setText(f"{spec.label} ({req_badge}) — {rom.title}")

        can_drop = bool(spec.folder_exists and rom.stem)
        kind_exts = VIDEO_EXTS if spec.media_kind == "video" else ((".pdf",) if spec.media_kind == "pdf" else IMAGE_EXTS)
        allowed_drop = spec.extensions + kind_exts
        self.canvas.set_drop_config(can_drop, allowed_drop)

        self.btn_set_folder.setVisible(not spec.folder_exists)
        self.btn_assign.setVisible(spec.folder_exists and bool(rom.stem))
        self.btn_open_loc.setVisible(spec.folder_exists or bool(slot.file_path))
        self._set_pdf_button_path(slot.file_path if (slot.media_kind == "pdf" and slot.file_path and os.path.isfile(slot.file_path)) else "")

        # Hay archivo existente para previsualizar
        if slot.file_path and os.path.isfile(slot.file_path):
            self.suggestions_frame.setVisible(False)
            self.btn_assign.setText("📥 Reemplazar archivo…")
            self.btn_delete.setVisible(True)

            if slot.media_kind == "video":
                self.btn_checkerboard.setVisible(False)
                self.video_controls_frame.setVisible(True)
                self._current_video_path = slot.file_path
                self._video_dims = None
                self._refresh_meta_label()
                self.canvas.show_video_waiting(os.path.basename(slot.file_path))
                self.player.setSource(QUrl.fromLocalFile(slot.file_path))
                if self._auto_play:
                    self.player.play()
            elif slot.media_kind == "pdf":
                self.video_controls_frame.setVisible(False)
                self.btn_checkerboard.setVisible(False)
                pix = self._build_pdf_preview_pixmap(slot.file_path)
                note_txt = f"  ·  ⚠ {slot.note}" if slot.note else ""
                self.meta_lbl.setText(
                    f"{os.path.basename(slot.file_path)}  ·  Documento PDF  ·  "
                    f"{format_file_size(slot.size_bytes)}{note_txt}"
                )
                self.canvas.show_image(pix, slot.file_path)
            else:
                self.video_controls_frame.setVisible(False)
                self.btn_checkerboard.setVisible(True)
                pix = QPixmap(slot.file_path)
                if not pix.isNull():
                    dims = f"{pix.width()} × {pix.height()} px"
                    note_txt = f"  ·  ⚠ {slot.note}" if slot.note else ""
                    self.meta_lbl.setText(
                        f"{os.path.basename(slot.file_path)}  ·  {dims}  ·  "
                        f"{format_file_size(slot.size_bytes)}{note_txt}"
                    )
                else:
                    self.meta_lbl.setText(f"{os.path.basename(slot.file_path)} (imagen ilegible o dañada)")
                self.canvas.show_image(pix, slot.file_path)
            return

        # Archivo faltante o sin carpeta
        self.video_controls_frame.setVisible(False)
        self.btn_checkerboard.setVisible(False)
        self.btn_delete.setVisible(False)
        self.btn_assign.setText("📥 Asignar archivo…")

        ext_list = ", ".join(spec.extensions)
        if not spec.folder_exists:
            subtitle = (
                f"La lista no tiene una carpeta válida configurada para '{spec.label}'.\n"
                f"Asigná una carpeta para que PlayNexus pueda buscar '{rom.stem}' ({ext_list})."
            )
            self.canvas.show_empty("📁 Carpeta de media no configurada", subtitle)
            self.meta_lbl.setText(slot.note or "Sin carpeta configurada")
            self.suggestions_frame.setVisible(False)
        else:
            expected_file = f"{rom.stem}{spec.extensions[0] if spec.extensions else ''}"
            subtitle = (
                f"Archivo esperado: {expected_file}\n"
                f"Extensiones admitidas por el layout: {ext_list}\n"
                f"Carpeta: {spec.folder_path}\n\n"
                f"💡 Podés arrastrar y soltar un archivo aquí para copiarlo y renombrarlo automáticamente."
            )
            title = "❌ Media obligatoria faltante" if spec.required else "⚪ Media opcional faltante"
            self.canvas.show_empty(title, subtitle)
            self.meta_lbl.setText(slot.note or f"No encontrado en {spec.folder_path}")
            self._rebuild_suggestions(fuzzy_candidates or [])

    def _set_pdf_button_path(self, pdf_path: str):
        self._current_pdf_path = str(pdf_path or "")
        if not hasattr(self, "btn_open_pdf"):
            self.btn_open_pdf = QPushButton("📖 Abrir Manual PDF…")
            self.btn_open_pdf.setStyleSheet(
                "QPushButton { background-color: #2e245c; border-color: #7c3aed; color: #f5f3ff; font-weight: 700; padding: 6px 12px; }"
                "QPushButton:hover { background-color: #4c1d95; }"
            )
            self.btn_open_pdf.clicked.connect(self._open_current_pdf)
            lay = self.layout()
            if lay is not None:
                idx = max(0, lay.count() - 1)
                lay.insertWidget(idx, self.btn_open_pdf)
        self.btn_open_pdf.setVisible(bool(self._current_pdf_path))

    def _open_current_pdf(self):
        p = getattr(self, "_current_pdf_path", "")
        if not p or not os.path.isfile(p):
            return
        from playnexus.ui.manual_viewer import ManualViewerDialog

        title = self._current_rom.title if getattr(self, "_current_rom", None) else Path(p).stem
        dlg = ManualViewerDialog(p, game_title=title, parent=self)
        dlg.exec()

    def _build_pdf_preview_pixmap(self, pdf_path: str) -> QPixmap:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QColor, QFont, QPainter
        from playnexus.ui.manual_viewer import render_pdf_first_page_pixmap

        pix, pages = render_pdf_first_page_pixmap(pdf_path, QSize(520, 400))
        if not pix.isNull():
            self.btn_open_pdf.setText(f"📖 Abrir Manual PDF ({pages} pág.)…")
            return pix
        self.btn_open_pdf.setText("📖 Abrir Manual PDF…")
        card = QPixmap(360, 440)
        card.fill(QColor("#141926"))
        painter = QPainter(card)
        painter.setPen(QColor("#7c3aed"))
        painter.drawRect(8, 8, 344, 424)
        painter.setPen(QColor("#f8fafc"))
        painter.setFont(QFont("Segoe UI", 18, QFont.Bold))
        painter.drawText(card.rect().adjusted(20, -40, -20, 0), Qt.AlignCenter, "📖\nMANUAL PDF")
        painter.setPen(QColor("#94a3b8"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(card.rect().adjusted(20, 80, -20, -20), Qt.AlignCenter | Qt.TextWordWrap, Path(pdf_path).name)
        painter.end()
        return card


class _FlowLayout(QLayout):
    """Layout adaptable que distribuye botones o chips en varias filas sin comprimir la barra."""

    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 8, v_spacing: int = 6):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_space = max(0, int(h_spacing))
        self._v_space = max(0, int(v_spacing))
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem):
        self._items.append(item)

    def addStretch(self, stretch: int = 0):  # noqa: ARG002
        return

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            w_item = item.widget()
            if w_item is not None and not w_item.isVisibleTo(self.parentWidget()):
                continue
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = eff.x()
        y = eff.y()
        line_h = 0

        for item in self._items:
            w_item = item.widget()
            if w_item is not None and not w_item.isVisible():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_space
            if line_h > 0 and next_x - self._h_space > eff.right():
                x = eff.x()
                y = y + line_h + self._v_space
                next_x = x + hint.width() + self._h_space
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_h = max(line_h, hint.height())

        return (y + line_h - rect.y()) + m.bottom()


class RomManagerWidget(QWidget):
    """
    Pestaña principal del Rom Manager dentro del Configurador de PlayNexus.
    """

    list_updated = Signal(int)        # Emite list_id cuando se actualiza layout o carpeta de una lista
    edit_list_requested = Signal(int) # Pide a MainWindow abrir ListDialog completo para esa lista
    games_metadata_updated = Signal(int)  # Emite list_id cuando el scraper actualiza metadatos de juegos

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._lists_by_id: dict[int, dict[str, Any]] = {}
        self._summary: AuditSummary | None = None
        self._visible_filtered_roms: list[RomAuditResult] = []
        self._worker: RomMediaScanWorker | None = None
        self._selected_game_id: int | None = None
        self._selected_key: str | None = None
        self._applied_table_headers: tuple[str, ...] | None = None
        self._syncing_controls = False

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(130)
        self._search_timer.timeout.connect(self._populate_table)

        self._build_ui()
        self.refresh_sources()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # -------------------------------------------------------------
        # 1. TARJETA DE CONFIGURACIÓN: SELECCIÓN, ACCIONES Y REQUERIMIENTOS
        # -------------------------------------------------------------
        top_card = QFrame()
        top_card.setStyleSheet(
            "QFrame#rmTopCard { background-color: #1b1e2a; border: 1px solid #2b3144; border-radius: 8px; }"
        )
        top_card.setObjectName("rmTopCard")
        top_vbox = QVBoxLayout(top_card)
        top_vbox.setContentsMargins(14, 10, 14, 10)
        top_vbox.setSpacing(10)

        # Fila 1: Selección de Lista y Layout
        select_row = QHBoxLayout()
        select_row.setSpacing(10)

        lbl_l = QLabel("<b>Lista de ROMs:</b>")
        self.list_combo = QComboBox()
        self.list_combo.setMinimumWidth(150)
        self.list_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.list_combo.setMinimumContentsLength(12)
        self.list_combo.currentIndexChanged.connect(self._on_list_combo_changed)

        lbl_lay = QLabel("<b>Layout a auditar:</b>")
        self.layout_combo = QComboBox()
        self.layout_combo.setMinimumWidth(160)
        self.layout_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.layout_combo.setMinimumContentsLength(12)
        self.layout_combo.currentTextChanged.connect(self._on_layout_combo_changed)

        self.btn_apply_layout = QPushButton("💾 Aplicar layout")
        self.btn_apply_layout.setMinimumHeight(32)
        self.btn_apply_layout.setToolTip("Guardar el layout seleccionado como el diseño visual de esta lista")
        self.btn_apply_layout.clicked.connect(self._apply_layout_to_list)
        self.btn_apply_layout.setVisible(False)

        self.btn_edit_folders = QPushButton("📁 Carpetas…")
        self.btn_edit_folders.setMinimumHeight(32)
        self.btn_edit_folders.setToolTip("Abrir configuración de carpetas y medios de esta lista")
        self.btn_edit_folders.clicked.connect(self._request_edit_current_list)

        select_row.addWidget(lbl_l)
        select_row.addWidget(self.list_combo, 1)
        select_row.addSpacing(4)
        select_row.addWidget(lbl_lay)
        select_row.addWidget(self.layout_combo, 1)
        select_row.addWidget(self.btn_apply_layout)
        select_row.addWidget(self.btn_edit_folders)
        top_vbox.addLayout(select_row)

        # Fila 2: Botones de acción con distribución adaptable (flujo automático sin aplastarse)
        actions_bar = QWidget()
        actions_flow = _FlowLayout(actions_bar, margin=0, h_spacing=8, v_spacing=6)

        self.btn_scan = QPushButton("🔍  Escanear Media")
        self.btn_scan.setObjectName("primary")
        self.btn_scan.setMinimumHeight(34)
        self.btn_scan.clicked.connect(self.start_scan)

        self.btn_scrape = QPushButton("🌐  Scrapear Faltantes…")
        self.btn_scrape.setMinimumHeight(34)
        self.btn_scrape.setToolTip("Buscar y descargar online la media faltante declarada en el layout")
        self.btn_scrape.clicked.connect(self._open_batch_scrape)
        self.btn_scrape.setEnabled(False)

        self.btn_scraper_cfg = QPushButton("⚙ Scraper")
        self.btn_scraper_cfg.setMinimumHeight(34)
        self.btn_scraper_cfg.setToolTip("Configurar proveedores online, regiones y credenciales ScreenScraper")
        self.btn_scraper_cfg.clicked.connect(self._open_scraper_settings)

        self.btn_toolkit = QPushButton("🛠 Pro Toolkit…")
        self.btn_toolkit.setMinimumHeight(34)
        self.btn_toolkit.setToolTip("Auto-Trim de Wheels/Logos, Normalizador de Videos (ffmpeg) y Auditor 1G1R / Duplicados")
        self.btn_toolkit.clicked.connect(self._open_pro_toolkit)

        self.btn_ra_sync = QPushButton("🏆 Logros RA…")
        self.btn_ra_sync.setMinimumHeight(34)
        self.btn_ra_sync.setToolTip("Configurar API Key y sincronizar logros de RetroAchievements")
        self.btn_ra_sync.clicked.connect(self._open_retroachievements)

        self.btn_export = QPushButton("📄 Exportar CSV")
        self.btn_export.setMinimumHeight(34)
        self.btn_export.setToolTip("Exportar reporte de auditoría y media faltante a CSV")
        self.btn_export.clicked.connect(self._export_report)
        self.btn_export.setEnabled(False)

        for btn in (
            self.btn_scan,
            self.btn_scrape,
            self.btn_scraper_cfg,
            self.btn_toolkit,
            self.btn_ra_sync,
            self.btn_export,
        ):
            actions_flow.addWidget(btn)
        top_vbox.addWidget(actions_bar)

        # Fila 3: Chips de requerimientos con salto automático de línea
        req_wrap = QHBoxLayout()
        req_wrap.setSpacing(8)
        req_lbl = QLabel("Requerimientos:")
        req_lbl.setStyleSheet("color: #9ba7bc; font-size: 8.5pt; font-weight: bold;")
        req_wrap.addWidget(req_lbl, 0, Qt.AlignTop)

        self.req_chips_container = QWidget()
        self.req_chips_layout = _FlowLayout(self.req_chips_container, margin=0, h_spacing=6, v_spacing=6)
        req_wrap.addWidget(self.req_chips_container, 1)
        top_vbox.addLayout(req_wrap)

        # Barra de progreso (solo visible durante escaneos largos)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(14)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #2e3549; border-radius: 5px; background: #141720; text-align: center; font-size: 8pt; }"
            "QProgressBar::chunk { background-color: #5d48d9; border-radius: 4px; }"
        )
        self.progress_bar.setVisible(False)
        top_vbox.addWidget(self.progress_bar)

        root.addWidget(top_card)

        # -------------------------------------------------------------
        # 2. BARRA DE RESUMEN KPI + FILTROS Y BÚSQUEDA
        # -------------------------------------------------------------
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.summary_label = QLabel("Seleccioná una lista y un layout, luego presioná <b>Escanear Media</b>.")
        self.summary_label.setStyleSheet("color: #cbd5e1; font-size: 9.5pt;")
        self.summary_label.setMinimumWidth(0)
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        filter_row.addWidget(self.summary_label, 1)

        self.filter_combo = QComboBox()
        self.filter_combo.setMinimumWidth(180)
        self.filter_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.filter_combo.setMinimumContentsLength(16)
        self.filter_combo.addItem("Mostrar: Todos", "all")
        self.filter_combo.addItem("❌ Faltan obligatorios", "missing_required")
        self.filter_combo.addItem("⚠️ Falta algún medio (oblig. u opc.)", "missing_any")
        self.filter_combo.addItem("🔶 Con extensión no sugerida", "wrong_ext")
        self.filter_combo.addItem("✅ Completos al 100%", "complete")
        self.filter_combo.addItem("🚫 ROM faltante en disco", "rom_missing")
        self.filter_combo.currentIndexChanged.connect(self._populate_table)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtrar por título o nombre de ROM…")
        self.search_edit.setMaximumWidth(280)
        self.search_edit.textChanged.connect(lambda: self._search_timer.start())

        filter_row.addWidget(self.filter_combo)
        filter_row.addWidget(self.search_edit)
        root.addLayout(filter_row)

        # -------------------------------------------------------------
        # 3. ÁREA CENTRAL DIVIDIDA: TABLA DE ROMS + INSPECTOR Y PREVIEWER
        # -------------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)

        # Izquierda: Tabla Maestra de ROMs
        table_container = QWidget()
        table_vbox = QVBoxLayout(table_container)
        table_vbox.setContentsMargins(0, 0, 0, 0)
        table_vbox.setSpacing(4)

        self.table = QTableWidget()
        configure_details_table(
            self.table,
            sorting=True,
            selection_behavior=QAbstractItemView.SelectItems,
            hide_vertical_header=True,
            alternating_rows=True,
            apply_columns=False,
        )
        self.table.setStyleSheet(
            "QTableWidget { alternate-background-color: #191d29; gridline-color: #252b3d; }"
            "QTableWidget::item { padding: 5px 8px; }"
            "QTableWidget::item:selected { background-color: #4938ab; color: #ffffff; }"
        )
        self.table.currentCellChanged.connect(self._on_table_cell_changed)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        table_vbox.addWidget(self.table, 1)

        self.visible_count_lbl = QLabel("0 ROMs mostradas")
        self.visible_count_lbl.setStyleSheet("color: #8e9bb0; font-size: 8.5pt;")
        table_vbox.addWidget(self.visible_count_lbl)
        splitter.addWidget(table_container)

        # Derecha: Inspector de Slots de la ROM + Previsualizador Dual
        right_panel = QFrame()
        right_panel.setStyleSheet(
            "QFrame#inspector_panel { background-color: #171a24; border: 1px solid #282f42; border-radius: 8px; }"
        )
        right_panel.setObjectName("inspector_panel")
        right_vbox = QVBoxLayout(right_panel)
        right_vbox.setContentsMargins(10, 10, 10, 10)
        right_vbox.setSpacing(8)

        # Cabecera de la ROM seleccionada
        info_head_row = QHBoxLayout()
        info_head_row.setSpacing(6)
        self.rom_info_title = QLabel("Ninguna ROM seleccionada")
        self.rom_info_title.setFont(QFont("Segoe UI", 11.5, QFont.Bold))
        self.rom_info_title.setWordWrap(True)
        info_head_row.addWidget(self.rom_info_title, 1)

        self.btn_scrape_single = QPushButton("🌐 Buscar online…")
        self.btn_scrape_single.setToolTip("Buscar candidatos online y descargar media puntual para esta ROM")
        self.btn_scrape_single.setEnabled(False)
        self.btn_scrape_single.clicked.connect(lambda: self._open_single_rom_scrape())
        info_head_row.addWidget(self.btn_scrape_single)
        right_vbox.addLayout(info_head_row)

        self.rom_info_sub = QLabel("—")
        self.rom_info_sub.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        self.rom_info_sub.setWordWrap(True)
        self.rom_info_sub.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right_vbox.addWidget(self.rom_info_sub)

        # Lista de slots de media del layout para esta ROM
        slots_lbl = QLabel("Medios solicitados por el layout:")
        slots_lbl.setStyleSheet("color: #cbd5e1; font-weight: 600; font-size: 9pt;")
        right_vbox.addWidget(slots_lbl)

        self.slots_list = QListWidget()
        self.slots_list.setMaximumHeight(145)
        self.slots_list.setMinimumHeight(85)
        self.slots_list.currentItemChanged.connect(self._on_slot_item_changed)
        right_vbox.addWidget(self.slots_list)

        # Previsualizador Dual (Imagen y Video)
        self.previewer = MediaPreviewWidget(self)
        self.previewer.assign_file_requested.connect(self._handle_assign_file)
        self.previewer.assign_folder_requested.connect(self._handle_assign_folder)
        self.previewer.rename_orphan_requested.connect(self._handle_rename_orphan)
        self.previewer.delete_file_requested.connect(self._handle_delete_file)
        right_vbox.addWidget(self.previewer, 1)

        right_panel.setMinimumWidth(360)
        splitter.addWidget(right_panel)
        splitter.setSizes([760, 480])

        root.addWidget(splitter, 1)

    # -----------------------------------------------------------------
    # CARGA Y SINCRONIZACIÓN DE LISTAS Y LAYOUTS
    # -----------------------------------------------------------------
    def refresh_sources(self, select_list_id: int | None = None, auto_scan: bool = False):
        """Recarga la lista de listas de la DB y los layouts disponibles."""
        prev_list_id = select_list_id if select_list_id is not None else self.list_combo.currentData()
        prev_layout = self.layout_combo.currentText()

        self._syncing_controls = True
        try:
            self.list_combo.blockSignals(True)
            self.list_combo.clear()
            self._lists_by_id.clear()

            rows = self.db.get_lists(with_counts=True)
            # Ordenar poniendo listas de juegos y filtradas primero, y menús al final
            rows_sorted = sorted(
                rows,
                key=lambda r: (1 if r.get("list_type") == "menu" else 0, str(r.get("name") or "").lower()),
            )

            for r in rows_sorted:
                rd = dict(r)
                lid = int(rd["id"])
                self._lists_by_id[lid] = rd
                ltype = rd.get("list_type", "games")
                if ltype == "menu":
                    icon = "🧭"
                    count_txt = f"{len(self.db.get_menu_items(lid))} sistemas"
                elif ltype == "filtered":
                    icon = "⚡"
                    count_txt = f"{rd.get('game_count', 0)} juegos"
                else:
                    icon = "🎮"
                    count_txt = f"{rd.get('game_count', 0)} ROMs"
                self.list_combo.addItem(f"{icon}  {rd['name']}  ({count_txt})", lid)

            if prev_list_id is not None:
                idx = self.list_combo.findData(int(prev_list_id))
                if idx >= 0:
                    self.list_combo.setCurrentIndex(idx)
            self.list_combo.blockSignals(False)

            self.layout_combo.blockSignals(True)
            self.layout_combo.clear()
            layouts = get_available_layouts()
            self.layout_combo.addItems(layouts)
            self.layout_combo.blockSignals(False)

            if prev_list_id is not None and select_list_id is None and prev_layout in layouts:
                self.layout_combo.setCurrentText(prev_layout)
            else:
                self._sync_layout_from_selected_list()
        finally:
            self._syncing_controls = False

        self._refresh_requirements_bar()
        if auto_scan and self.list_combo.currentData():
            self.start_scan()

    def focus_list(self, list_id: int, auto_scan: bool = True):
        """Selecciona una lista concreta desde otra pestaña y opcionalmente la escanea."""
        self.refresh_sources(select_list_id=list_id, auto_scan=auto_scan)

    def _current_list_row(self) -> dict[str, Any] | None:
        lid = self.list_combo.currentData()
        if lid is None:
            return None
        row = self.db.get_list(int(lid))
        return dict(row) if row else self._lists_by_id.get(int(lid))

    def _sync_layout_from_selected_list(self):
        row = self._current_list_row()
        if not row:
            return
        assigned_layout = (row.get("layout") or "").strip()
        if assigned_layout:
            idx = self.layout_combo.findText(assigned_layout, Qt.MatchFixedString)
            if idx < 0:
                from playnexus.ui.layouts import resolve_theme_name
                resolved = resolve_theme_name(assigned_layout)
                if resolved:
                    idx = self.layout_combo.findText(resolved, Qt.MatchFixedString)
            if idx >= 0:
                self.layout_combo.blockSignals(True)
                self.layout_combo.setCurrentIndex(idx)
                self.layout_combo.blockSignals(False)
        self._update_apply_layout_button()

    def _update_apply_layout_button(self):
        row = self._current_list_row()
        cur_lay = self.layout_combo.currentText().strip()
        if not row or not cur_lay:
            self.btn_apply_layout.setVisible(False)
            return
        assigned = (row.get("layout") or "").strip()
        self.btn_apply_layout.setVisible(assigned.lower() != cur_lay.lower())

    def _on_list_combo_changed(self, _index: int):
        if self._syncing_controls:
            return
        self._sync_layout_from_selected_list()
        self._refresh_requirements_bar()
        self._reset_audit_view("Lista cambiada. Presioná <b>Escanear Media</b> o iniciá el análisis.")
        if self.list_combo.currentData():
            self.start_scan()

    def _on_layout_combo_changed(self, _layout_name: str):
        if self._syncing_controls:
            return
        self._update_apply_layout_button()
        self._refresh_requirements_bar()
        if self._summary is not None and self.list_combo.currentData():
            self.start_scan()

    def _apply_layout_to_list(self):
        row = self._current_list_row()
        layout_name = self.layout_combo.currentText().strip()
        if not row or not layout_name:
            return
        lid = int(row["id"])
        self.db.update_list(lid, layout=layout_name)
        self._update_apply_layout_button()
        self.list_updated.emit(lid)
        QMessageBox.information(
            self,
            "Layout aplicado",
            f"Se asignó el diseño visual '{layout_name}' a la lista '{row['name']}'.",
        )

    def _request_edit_current_list(self):
        row = self._current_list_row()
        if row:
            self.edit_list_requested.emit(int(row["id"]))

    def _refresh_requirements_bar(self):
        """Muestra chips de requerimientos explícitos leídos de MEDIA_REQUIREMENTS."""
        while self.req_chips_layout.count():
            item = self.req_chips_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        layout_name = self.layout_combo.currentText().strip()
        row = self._current_list_row()
        raw_spec = get_layout_media_spec(layout_name) if layout_name else []
        specs = build_requirement_specs(raw_spec, row)

        if not specs:
            lbl = QLabel("Este layout no declara MEDIA_REQUIREMENTS en su theme_layout.py.")
            lbl.setStyleSheet("color: #f59e0b; font-size: 8.5pt;")
            self.req_chips_layout.addWidget(lbl)
            self.req_chips_layout.addStretch()
            return

        for s in specs:
            req_tag = "★" if s.required else "Opc."
            cov_txt = ""
            if self._summary and self._summary.layout_name == layout_name and s.key in self._summary.slot_totals:
                tot = self._summary.slot_totals[s.key]
                cov_txt = f" ({tot['present']}/{tot['total']})"

            if s.folder_exists:
                btn = QPushButton(f"{req_tag} {s.label}{cov_txt}")
                btn.setStyleSheet(
                    "QPushButton { background-color: #1f293b; border: 1px solid #334563; border-radius: 11px; "
                    "padding: 3px 10px; font-size: 8.5pt; color: #cbd5e1; }"
                    "QPushButton:hover { background-color: #29364f; }"
                )
                btn.setToolTip(
                    f"Carpeta configurada:\n{s.folder_path}\n"
                    f"Extensiones del layout: {', '.join(s.extensions)}\n"
                    f"(Clic para cambiar carpeta)"
                )
            else:
                btn = QPushButton(f"📁 {req_tag} {s.label}: Sin carpeta")
                border = "#7f1d1d" if s.required else "#4a3d20"
                bg = "#2d1a1f" if s.required else "#2a2417"
                fg = "#fca5a5" if s.required else "#fcd34d"
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {bg}; border: 1px solid {border}; border-radius: 11px; "
                    f"padding: 3px 10px; font-size: 8.5pt; color: {fg}; }}"
                    f"QPushButton:hover {{ border-color: #7c69ef; }}"
                )
                btn.setToolTip(
                    f"No hay carpeta válida configurada para '{s.label}'.\n"
                    f"Clic para seleccionar la carpeta ahora."
                )

            btn.clicked.connect(lambda checked=False, k=s.key: self._handle_assign_folder(k))
            self.req_chips_layout.addWidget(btn)

        self.req_chips_layout.addStretch()

    def _reset_audit_view(self, message: str):
        self.previewer.stop_and_release()
        self.previewer.clear_preview()
        self._summary = None
        self._visible_filtered_roms = []
        self.btn_export.setEnabled(False)
        self.btn_scrape.setEnabled(False)
        self.btn_scrape_single.setEnabled(False)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.slots_list.clear()
        self.rom_info_title.setText("Ninguna ROM seleccionada")
        self.rom_info_sub.setText("—")
        self.visible_count_lbl.setText("0 ROMs mostradas")
        self.summary_label.setText(message)

    # -----------------------------------------------------------------
    # ESCANEO ASÍNCRONO DE MEDIA
    # -----------------------------------------------------------------
    def _collect_games_for_list(self, list_row: dict[str, Any]) -> list[dict[str, Any]]:
        lid = int(list_row["id"])
        if list_row.get("list_type") == "menu":
            targets = self.db.get_menu_items(lid)
            items = []
            for t in targets:
                td = dict(t)
                items.append({
                    "id": td["id"],
                    "title": td["name"],
                    "platform": td.get("platform") or td["name"],
                    "rom_path": "",
                    "rom_name": td["name"],
                    "is_menu_target": True,
                })
            return items
        return [dict(g) for g in self.db.get_games(lid, enriched=False)]

    def start_scan(self):
        row = self._current_list_row()
        layout_name = self.layout_combo.currentText().strip()
        if not row or not layout_name:
            QMessageBox.information(self, "Datos requeridos", "Seleccioná una lista y un layout para escanear.")
            return

        # Cancelar worker previo si sigue ejecutándose
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(500)

        self.previewer.stop_and_release()

        # Resolver MEDIA_REQUIREMENTS y datos de DB siempre en el hilo principal (regla Qt/PySide6)
        raw_spec = get_layout_media_spec(layout_name)
        games = self._collect_games_for_list(row)

        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("⏳ Escaneando…")
        self.progress_bar.setRange(0, max(1, len(games)))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.summary_label.setText(f"Escaneando {len(games)} elemento(s) contra <b>{layout_name}</b>…")

        self._worker = RomMediaScanWorker(row, games, raw_spec, layout_name, self)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished_audit.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def _on_scan_progress(self, cur: int, total: int, msg: str):
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(min(cur, max(1, total)))
        self.progress_bar.setFormat(msg)

    def _on_scan_failed(self, err: str):
        self.progress_bar.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("🔍  Escanear Media")
        QMessageBox.critical(self, "Error durante el escaneo", f"No se pudo completar la auditoría:\n{err}")

    def _on_scan_finished(self, summary: AuditSummary):
        self.progress_bar.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("🔍  Escanear Media")
        self._summary = summary
        self.btn_export.setEnabled(summary.total_roms > 0)
        self.btn_scrape.setEnabled(summary.total_roms > 0 and summary.list_type != "menu")

        self._refresh_requirements_bar()
        self._update_summary_banner()
        self._populate_table()

    def _update_summary_banner(self):
        s = self._summary
        if not s:
            return
        pct = int(round((s.ready_roms / s.total_roms) * 100)) if s.total_roms else 0
        rom_disk_txt = (
            f"  |  <span style='color:#fca5a5;'>ROMs sin archivo en disco: <b>{s.roms_missing_on_disk}</b></span>"
            if s.roms_missing_on_disk > 0
            else ""
        )
        self.summary_label.setText(
            f"<b>{s.list_name}</b> vs <b>{s.layout_name}</b>: "
            f"Total <b>{s.total_roms}</b>  |  "
            f"<span style='color:#4ade80;'>Listos (oblig. OK): <b>{s.ready_roms}</b> ({pct}%)</span>  |  "
            f"<span style='color:#86efac;'>100% Completos: <b>{s.complete_roms}</b></span>  |  "
            f"<span style='color:#f87171;'>Con faltantes obligatorios: <b>{s.incomplete_required_roms}</b></span>"
            f"{rom_disk_txt}"
        )

    # -----------------------------------------------------------------
    # TABLA DE RESULTADOS Y FILTROS
    # -----------------------------------------------------------------
    def _matches_active_filters(self, item: RomAuditResult, term: str, mode: str) -> bool:
        if term:
            hay = f"{item.title} {item.stem} {item.rom_name}".lower()
            if term not in hay:
                return False

        if mode == "missing_required":
            return item.missing_required_count > 0
        if mode == "missing_any":
            return (item.missing_required_count + item.missing_optional_count) > 0
        if mode == "wrong_ext":
            return item.wrong_ext_count > 0
        if mode == "complete":
            return item.overall_status == "complete"
        if mode == "rom_missing":
            return (not item.is_menu_target) and (not item.rom_exists)
        return True

    def _slot_cell_presentation(self, slot: SlotAuditResult) -> tuple[str, QColor, int]:
        if slot.status == "ok":
            return f"✅ {slot.extension}", QColor("#86efac"), 0
        if slot.status == "wrong_ext":
            return f"⚠️ {slot.extension}", QColor("#fcd34d"), 1
        if slot.status == "no_folder":
            color = QColor("#f87171") if slot.is_required else QColor("#94a3b8")
            return "📁 Sin carpeta", color, 3 if slot.is_required else 2
        if slot.status == "missing_required":
            return "❌ Falta", QColor("#f87171"), 3
        return "⚪ Opcional", QColor("#94a3b8"), 2

    def _build_rom_row_cells(self, row_idx: int, item: RomAuditResult):
        # Col 0: Estado general
        if item.overall_status == "complete":
            st_txt, st_col, st_sort = "✅ OK", QColor("#4ade80"), 0
        elif item.overall_status == "missing_optional":
            st_txt, st_col, st_sort = f"⚪ -{item.missing_optional_count} opc.", QColor("#cbd5e1"), 1
        else:
            st_txt, st_col, st_sort = f"❌ -{item.missing_required_count} oblig.", QColor("#f87171"), 2

        it_st = SortableTableItem(st_txt)
        it_st.setForeground(st_col)
        it_st.setTextAlignment(Qt.AlignCenter)
        it_st.setData(Qt.UserRole, (item.game_id, None))
        it_st.setData(SortableTableItem.SORT_ROLE, st_sort)
        self.table.setItem(row_idx, 0, it_st)

        # Col 1: Título
        title_txt = item.title if item.rom_exists else f"{item.title}  [🚫 ROM no encontrada]"
        it_title = SortableTableItem(title_txt)
        if not item.rom_exists:
            it_title.setForeground(QColor("#fca5a5"))
        it_title.setData(Qt.UserRole, (item.game_id, None))
        it_title.setData(SortableTableItem.SORT_ROLE, item.title.lower())
        self.table.setItem(row_idx, 1, it_title)

        # Col 2: ROM stem
        it_stem = SortableTableItem(item.stem or "—")
        it_stem.setForeground(QColor("#a5b4fc"))
        it_stem.setData(Qt.UserRole, (item.game_id, None))
        it_stem.setData(SortableTableItem.SORT_ROLE, (item.stem or "").lower())
        self.table.setItem(row_idx, 2, it_stem)

        # Cols 3+: Slots dinámicos del layout
        for col_offset, spec in enumerate(self._summary.specs):
            slot = item.slots.get(spec.key)
            if not slot:
                continue
            txt, col, sort_key = self._slot_cell_presentation(slot)
            cell = SortableTableItem(txt)
            cell.setForeground(col)
            cell.setTextAlignment(Qt.AlignCenter)
            cell.setData(Qt.UserRole, (item.game_id, spec.key))
            cell.setData(SortableTableItem.SORT_ROLE, sort_key)
            if slot.note:
                cell.setToolTip(slot.note)
            elif slot.file_path:
                cell.setToolTip(slot.file_path)
            self.table.setItem(row_idx, 3 + col_offset, cell)

        # Columna final: Progreso en caché de RetroAchievements (O(1))
        ra_col = 3 + len(self._summary.specs)
        if item.is_menu_target:
            ra_cell = SortableTableItem("—")
            ra_cell.setForeground(QColor("#64748b"))
            ra_cell.setData(SortableTableItem.SORT_ROLE, -1)
        else:
            from playnexus.services.retroachievements import format_ra_badge_text, get_cached_ra_progress_summary
            ra_sum = get_cached_ra_progress_summary(self.db, {"id": item.game_id, "rom_path": item.rom_path})
            if ra_sum and ra_sum.get("matched"):
                ra_txt = format_ra_badge_text(ra_sum)
                ra_color = QColor("#fde047") if float(ra_sum.get("pct") or 0) > 0 else QColor("#93c5fd")
                ra_sort = float(ra_sum.get("pct") or 0)
            elif ra_sum:
                ra_txt = "N/D"
                ra_color = QColor("#64748b")
                ra_sort = -0.5
            else:
                ra_txt = "—"
                ra_color = QColor("#64748b")
                ra_sort = -1
            ra_cell = SortableTableItem(ra_txt)
            ra_cell.setForeground(ra_color)
            ra_cell.setData(SortableTableItem.SORT_ROLE, ra_sort)
        ra_cell.setTextAlignment(Qt.AlignCenter)
        ra_cell.setData(Qt.UserRole, (item.game_id, None))
        self.table.setItem(row_idx, ra_col, ra_cell)

    def _populate_table(self):
        s = self._summary
        if not s:
            return

        term = self.search_edit.text().strip().lower()
        mode = self.filter_combo.currentData() or "all"
        filtered = [r for r in s.results if self._matches_active_filters(r, term, mode)]
        self._visible_filtered_roms = filtered

        prev_game_id = self._selected_game_id
        prev_key = self._selected_key

        self.table.blockSignals(True)
        col_headers = ["Estado", "Juego / Título", "ROM (stem)"]
        for spec in s.specs:
            star = "★ " if spec.required else ""
            col_headers.append(f"{star}{spec.label}")
        col_headers.append("🏆 Logros RA")

        schema_key = tuple(col_headers)
        schema_changed = (schema_key != self._applied_table_headers)
        if schema_changed:
            self.table.setColumnCount(len(col_headers))
            self.table.setHorizontalHeaderLabels(col_headers)
            init_widths = [95, 240, 175] + [115] * max(0, len(col_headers) - 3)
            configure_details_table(
                self.table,
                col_widths=init_widths,
                sorting=True,
                selection_behavior=QAbstractItemView.SelectItems,
                hide_vertical_header=True,
                alternating_rows=True,
            )
            self._applied_table_headers = schema_key

        with paused_table_sorting(self.table, reenable=True):
            self.table.clearContents()
            self.table.setRowCount(len(filtered))

            target_col = 0
            if prev_key:
                for c_idx, spec in enumerate(s.specs):
                    if spec.key == prev_key:
                        target_col = 3 + c_idx
                        break

            target_item: QTableWidgetItem | None = None
            target_gid: int | None = None
            for r_idx, item in enumerate(filtered):
                self._build_rom_row_cells(r_idx, item)
                if r_idx == 0 and target_item is None:
                    target_item = self.table.item(r_idx, target_col) or self.table.item(r_idx, 0)
                    target_gid = item.game_id
                if prev_game_id is not None and item.game_id == prev_game_id:
                    target_item = self.table.item(r_idx, target_col) or self.table.item(r_idx, 0)
                    target_gid = item.game_id

        self.table.blockSignals(False)

        self.visible_count_lbl.setText(f"{len(filtered)} de {s.total_roms} elemento(s) mostrados")

        if target_item is not None and target_gid is not None:
            self.table.setCurrentItem(target_item)
            self._select_game_and_slot(target_gid, prev_key)
        else:
            self._selected_game_id = None
            self.btn_scrape_single.setEnabled(False)
            self.slots_list.clear()
            self.rom_info_title.setText("Ninguna ROM coincide con el filtro")
            self.rom_info_sub.setText("—")
            self.previewer.clear_preview("No hay elementos para mostrar con el filtro actual.")

    def _find_rom_result(self, game_id: int | None) -> RomAuditResult | None:
        if not self._summary or game_id is None:
            return None
        return next((r for r in self._summary.results if r.game_id == game_id), None)

    def _on_table_cell_clicked(self, row: int, col: int):
        item = self.table.item(row, col)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not data:
            return
        gid, slot_key = data
        self._select_game_and_slot(gid, slot_key)

    def _on_table_cell_changed(self, cur_row: int, cur_col: int, _prev_row: int, _prev_col: int):
        if cur_row < 0 or cur_col < 0:
            return
        item = self.table.item(cur_row, cur_col)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not data:
            return
        gid, slot_key = data
        if gid != self._selected_game_id or (slot_key and slot_key != self._selected_key):
            self._select_game_and_slot(gid, slot_key)

    def _on_table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not data:
            return
        gid, slot_key = data
        self._select_game_and_slot(gid, slot_key)
        rom = self._find_rom_result(gid)
        if not rom:
            return

        menu = QMenu(self)
        spec = self._get_spec(slot_key) if slot_key else None
        slot = rom.slots.get(slot_key) if slot_key else None

        act_assign = None
        act_open_media = None
        act_del = None
        if spec and slot:
            if spec.folder_exists and rom.stem:
                act_assign = menu.addAction(f"📥 Asignar/Reemplazar {spec.label}…")
            if slot.file_path:
                act_open_media = menu.addAction("📂 Abrir ubicación de este archivo")
                act_del = menu.addAction("🗑 Eliminar archivo de media")
            menu.addSeparator()

        act_scrape_single = None
        act_ra_single = None
        act_manual = None
        if not rom.is_menu_target and rom.stem:
            act_scrape_single = menu.addAction(f"🌐 Buscar media online para '{rom.title}'…")
            act_ra_single = menu.addAction("🏆 Ver / Sincronizar RetroAchievements…")
            from playnexus.services.media import resolve_game_manual_pdf
            g_row = self.db.get_game(rom.game_id) or {"id": rom.game_id, "rom_path": rom.rom_path}
            if resolve_game_manual_pdf(g_row, list_row=self._current_list_row()):
                act_manual = menu.addAction("📖 Abrir Manual PDF…")

        act_open_rom = None
        if rom.rom_path and os.path.exists(rom.rom_path):
            act_open_rom = menu.addAction("📂 Abrir ubicación de la ROM")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_assign:
            self._handle_assign_file("")
        elif chosen == act_open_media and slot and slot.file_path:
            _open_in_file_explorer(slot.file_path, is_dir=False)
        elif chosen == act_del and slot and slot.file_path:
            self._handle_delete_file(slot.file_path)
        elif act_scrape_single and chosen == act_scrape_single:
            self._open_single_rom_scrape(rom.game_id)
        elif act_ra_single and chosen == act_ra_single:
            self._open_ra_single(rom.game_id)
        elif act_manual and chosen == act_manual:
            self._open_manual_for_rom(rom.game_id)
        elif chosen == act_open_rom:
            _open_in_file_explorer(rom.rom_path, is_dir=False)

    def _get_spec(self, key: str | None) -> MediaRequirementSpec | None:
        if not self._summary or not key:
            return None
        return next((sp for sp in self._summary.specs if sp.key == key), None)

    def _select_game_and_slot(self, game_id: int, preferred_key: str | None = None):
        rom = self._find_rom_result(game_id)
        if not rom or not self._summary:
            return

        self._selected_game_id = game_id
        self.btn_scrape_single.setEnabled(not rom.is_menu_target and bool(rom.stem))
        self.rom_info_title.setText(rom.title)
        if rom.is_menu_target:
            self.rom_info_sub.setText(f"Ítem de Menú de Sistemas  ·  Nombre base: {rom.stem}")
        else:
            disk_state = "✅ ROM verificada en disco" if rom.rom_exists else "🚫 Archivo ROM no encontrado en disco"
            self.rom_info_sub.setText(f"Stem: <code>{rom.stem}</code>  ·  {disk_state}<br>{rom.rom_path}")

        target_key = preferred_key
        if not target_key or target_key not in rom.slots:
            if self._selected_key and self._selected_key in rom.slots:
                target_key = self._selected_key
            elif self._summary.specs:
                # Priorizar el primer slot faltante obligatorio o con archivo para mostrar algo útil
                missing_req = next(
                    (sp.key for sp in self._summary.specs if rom.slots.get(sp.key) and rom.slots[sp.key].status == "missing_required"),
                    None,
                )
                target_key = missing_req or self._summary.specs[0].key

        self._selected_key = target_key

        self.slots_list.blockSignals(True)
        self.slots_list.clear()
        sel_row = 0
        for spec in self._summary.specs:
            slot = rom.slots.get(spec.key)
            if not slot:
                continue
            status_txt, status_col, _ = self._slot_cell_presentation(slot)
            star = "★ " if spec.required else ""
            kind_icon = "🎬" if spec.media_kind == "video" else ("📖" if spec.media_kind == "pdf" else "🖼")
            size_txt = f" ({format_file_size(slot.size_bytes)})" if slot.file_path else ""
            li = QListWidgetItem(f"{kind_icon} {star}{spec.label}:  {status_txt}{size_txt}")
            li.setForeground(status_col)
            li.setData(Qt.UserRole, spec.key)
            self.slots_list.addItem(li)
            if spec.key == target_key:
                sel_row = self.slots_list.count() - 1
        if self.slots_list.count() > 0:
            self.slots_list.setCurrentRow(sel_row)
        self.slots_list.blockSignals(False)

        self._show_selected_slot_preview()

    def _on_slot_item_changed(self, current: QListWidgetItem | None, _previous):
        if not current:
            return
        self._selected_key = current.data(Qt.UserRole)
        self._show_selected_slot_preview()

    def _show_selected_slot_preview(self):
        rom = self._find_rom_result(self._selected_game_id)
        spec = self._get_spec(self._selected_key)
        slot = rom.slots.get(self._selected_key) if (rom and self._selected_key) else None

        candidates: list[tuple[OrphanMediaFile, float]] = []
        if rom and spec and slot and slot.status in ("missing_required", "missing_optional") and self._summary:
            orphans = self._summary.orphan_files_by_key.get(spec.key, [])
            candidates = find_fuzzy_media_candidates(rom.stem, rom.title, orphans)

        self.previewer.display_slot(rom, spec, slot, fuzzy_candidates=candidates)

    # -----------------------------------------------------------------
    # ACCIONES DE ASIGNACIÓN, RENOMBRADO, ELIMINACIÓN Y EXPORTACIÓN
    # -----------------------------------------------------------------
    def _handle_assign_folder(self, key: str):
        row = self._current_list_row()
        if not row:
            return
        specs = build_requirement_specs(get_layout_media_spec(self.layout_combo.currentText()), row)
        spec = next((sp for sp in specs if sp.key == key), None)
        if not spec:
            return

        initial_dir = spec.folder_path if spec.folder_exists else ""
        chosen = QFileDialog.getExistingDirectory(
            self,
            f"Seleccionar carpeta de '{spec.label}' para '{row['name']}'",
            initial_dir,
        )
        if not chosen:
            return

        norm = chosen.strip().replace("\\", "/")
        self.db.update_list(int(row["id"]), **{spec.db_field: norm})
        clear_media_cache()
        self.list_updated.emit(int(row["id"]))
        self.start_scan()

    def _handle_assign_file(self, source_path: str):
        rom = self._find_rom_result(self._selected_game_id)
        spec = self._get_spec(self._selected_key)
        if not rom or not spec or not spec.folder_exists:
            return

        if not source_path:
            extra_exts = VIDEO_EXTS if spec.media_kind == "video" else ((".pdf",) if spec.media_kind == "pdf" else IMAGE_EXTS)
            valid_exts = sorted(set(spec.extensions) | set(extra_exts))
            filt_str = " ".join(f"*{e}" for e in valid_exts)
            kind_lbl = "Videos" if spec.media_kind == "video" else ("Manuales PDF" if spec.media_kind == "pdf" else "Imágenes")
            source_path, _ = QFileDialog.getOpenFileName(
                self,
                f"Seleccionar {spec.label} para '{rom.title}'",
                "",
                f"{kind_lbl} ({filt_str});;Todos los archivos (*.*)",
            )
            if not source_path:
                return

        slot = rom.slots.get(spec.key)
        if slot and slot.file_path and os.path.isfile(slot.file_path):
            if os.path.abspath(source_path) == os.path.abspath(slot.file_path):
                return
            ans = QMessageBox.question(
                self,
                "Reemplazar media existente",
                f"Ya existe un archivo asignado para '{rom.title}':\n{os.path.basename(slot.file_path)}\n\n"
                f"¿Deseás reemplazarlo copiando y renombrando el nuevo archivo a '{rom.stem}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ans != QMessageBox.Yes:
                return

        # Liberar video antes de sobrescribir si el reproductor lo tiene abierto
        self.previewer.stop_and_release()

        extra_exts = VIDEO_EXTS if spec.media_kind == "video" else ((".pdf",) if spec.media_kind == "pdf" else IMAGE_EXTS)
        allowed = spec.extensions + extra_exts
        try:
            dest_path = assign_media_file(
                source_path=source_path,
                target_folder=spec.folder_path,
                target_stem=rom.stem,
                remove_existing_for_stem=True,
                allowed_exts=allowed,
                move=False,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error al asignar archivo", str(exc))
            self._show_selected_slot_preview()
            return

        self._update_single_slot_after_file_change(rom, spec, dest_path)

    def _handle_rename_orphan(self, source_path: str):
        rom = self._find_rom_result(self._selected_game_id)
        spec = self._get_spec(self._selected_key)
        if not rom or not spec or not os.path.isfile(source_path):
            return

        src_name = os.path.basename(source_path)
        ext = Path(source_path).suffix.lower()
        target_name = f"{rom.stem}{ext}"
        ans = QMessageBox.question(
            self,
            "Renombrar archivo coincidente",
            f"¿Renombrar '{src_name}' a '{target_name}' dentro de la carpeta '{spec.label}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ans != QMessageBox.Yes:
            return

        self.previewer.stop_and_release()
        try:
            new_path = rename_orphan_media_file(source_path, rom.stem)
        except Exception as exc:
            QMessageBox.critical(self, "Error al renombrar", str(exc))
            return

        # Quitar de huérfanos y actualizar el slot
        if self._summary and spec.key in self._summary.orphan_files_by_key:
            self._summary.orphan_files_by_key[spec.key] = [
                o for o in self._summary.orphan_files_by_key[spec.key]
                if os.path.abspath(o.file_path) != os.path.abspath(source_path)
            ]
        self._update_single_slot_after_file_change(rom, spec, new_path)

    def _handle_delete_file(self, file_path: str):
        rom = self._find_rom_result(self._selected_game_id)
        spec = self._get_spec(self._selected_key)
        if not rom or not spec or not os.path.isfile(file_path):
            return

        ans = QMessageBox.question(
            self,
            "Eliminar archivo de media",
            f"¿Eliminar definitivamente del disco el archivo?\n\n{file_path}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        self.previewer.stop_and_release()
        try:
            delete_media_file(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Error al eliminar", str(exc))
            self._show_selected_slot_preview()
            return

        self._update_single_slot_after_file_change(rom, spec, None)

    def _recompute_summary_counts(self):
        s = self._summary
        if not s:
            return
        s.complete_roms = 0
        s.ready_roms = 0
        s.incomplete_required_roms = 0
        for sp in s.specs:
            s.slot_totals[sp.key] = {"present": 0, "wrong_ext": 0, "missing": 0, "no_folder": 0, "total": s.total_roms}

        for r in s.results:
            miss_req = 0
            miss_opt = 0
            wrong = 0
            pres = 0
            for sp in s.specs:
                sl = r.slots[sp.key]
                tot = s.slot_totals[sp.key]
                if sl.status == "ok":
                    pres += 1
                    tot["present"] += 1
                elif sl.status == "wrong_ext":
                    pres += 1
                    wrong += 1
                    tot["present"] += 1
                    tot["wrong_ext"] += 1
                elif sl.status == "no_folder":
                    tot["no_folder"] += 1
                    tot["missing"] += 1
                    if sp.required:
                        miss_req += 1
                    else:
                        miss_opt += 1
                elif sl.status == "missing_required":
                    tot["missing"] += 1
                    miss_req += 1
                else:
                    tot["missing"] += 1
                    miss_opt += 1
            r.missing_required_count = miss_req
            r.missing_optional_count = miss_opt
            r.wrong_ext_count = wrong
            r.present_count = pres
            if miss_req > 0:
                r.overall_status = "missing_required"
                s.incomplete_required_roms += 1
            elif miss_opt > 0:
                r.overall_status = "missing_optional"
                s.ready_roms += 1
            else:
                r.overall_status = "complete"
                s.ready_roms += 1
                s.complete_roms += 1

    def _update_single_slot_after_file_change(self, rom: RomAuditResult, spec: MediaRequirementSpec, new_path: str | None):
        if new_path and os.path.isfile(new_path):
            ext = Path(new_path).suffix.lower()
            size = os.path.getsize(new_path)
            is_strict = ext in spec.extensions
            rom.slots[spec.key] = SlotAuditResult(
                key=spec.key,
                label=spec.label,
                status="ok" if is_strict else "wrong_ext",
                file_path=new_path,
                extension=ext,
                size_bytes=size,
                expected_stem=rom.stem,
                expected_folder=spec.folder_path,
                is_required=spec.required,
                media_kind=spec.media_kind,
                note="" if is_strict else f"Encontrado como '{ext}', el layout declara: {', '.join(spec.extensions)}",
            )
        else:
            rom.slots[spec.key] = SlotAuditResult(
                key=spec.key,
                label=spec.label,
                status="missing_required" if spec.required else "missing_optional",
                file_path=None,
                extension="",
                size_bytes=0,
                expected_stem=rom.stem,
                expected_folder=spec.folder_path,
                is_required=spec.required,
                media_kind=spec.media_kind,
            )

        self._recompute_summary_counts()
        self._refresh_requirements_bar()
        self._update_summary_banner()
        self._populate_table()
        self.list_updated.emit(self._summary.list_id if self._summary else 0)

    def _export_report(self):
        if not self._summary:
            return
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in self._summary.list_name).strip()
        default_name = f"media_report_{safe_name or 'lista'}.csv"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar reporte de auditoría (CSV)",
            default_name,
            "Archivos CSV (*.csv);;Todos (*.*)",
        )
        if not out_path:
            return

        ans = QMessageBox.question(
            self,
            "Opciones de exportación",
            "¿Exportar únicamente las ROMs con media faltante?\n\n"
            "• Sí = Solo incompletas (ideal para saber qué falta descargar)\n"
            "• No = Todas las ROMs de la lista",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        only_inc = (ans == QMessageBox.Yes)
        try:
            count = export_audit_csv(self._summary, out_path, only_incomplete=only_inc)
            QMessageBox.information(
                self,
                "Reporte exportado",
                f"Se exportaron {count} fila(s) correctamente a:\n{out_path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error al exportar", str(exc))

    # -----------------------------------------------------------------
    # SCRAPER ONLINE INTEGRADO
    # -----------------------------------------------------------------
    def _open_scraper_settings(self):
        from playnexus.ui.scraper_dialogs import ScraperSettingsDialog

        dlg = ScraperSettingsDialog(self.db, self)
        dlg.exec()

    def _open_batch_scrape(self):
        row = self._current_list_row()
        if not row or not self._summary:
            QMessageBox.information(self, "Escaneo requerido", "Escaneá primero una lista contra un layout.")
            return
        if self._summary.list_type == "menu":
            QMessageBox.information(
                self,
                "Lista no compatible",
                "El scraping automático aplica a listas de juegos/ROMs.",
            )
            return

        from playnexus.ui.scraper_dialogs import BatchScrapeDialog

        games_rows = self.db.get_games(int(row["id"]), enriched=False)
        games_by_id = {int(g["id"]): dict(g) for g in games_rows}
        dlg = BatchScrapeDialog(
            db=self.db,
            list_row=row,
            summary=self._summary,
            visible_roms=self._visible_filtered_roms or self._summary.results,
            games_by_id=games_by_id,
            release_media_cb=lambda: self.previewer.stop_and_release(flush_events=True),
            parent=self,
        )
        dlg.exec()

        if dlg.has_folder_changes or dlg.has_media_changes:
            clear_media_cache()
            self.list_updated.emit(int(row["id"]))
            self.start_scan()
        if dlg.has_metadata_changes:
            self.games_metadata_updated.emit(int(row["id"]))

    def _open_single_rom_scrape(self, game_id: int | None = None):
        row = self._current_list_row()
        if not row or not self._summary:
            return
        gid = game_id if game_id is not None else self._selected_game_id
        rom = self._find_rom_result(gid)
        if not rom or rom.is_menu_target or not rom.stem:
            return

        from playnexus.ui.scraper_dialogs import SingleRomScrapeDialog

        game_row = self.db.get_game(rom.game_id)
        dlg = SingleRomScrapeDialog(
            db=self.db,
            list_row=row,
            rom=rom,
            game_row=dict(game_row) if game_row else None,
            specs=self._summary.specs,
            layout_name=self._summary.layout_name,
            release_media_cb=lambda: self.previewer.stop_and_release(flush_events=True),
            parent=self,
        )
        dlg.exec()

        if dlg.downloaded_any:
            clear_media_cache()
            self.list_updated.emit(int(row["id"]))
            self.start_scan()
        if dlg.metadata_updated:
            self.games_metadata_updated.emit(int(row["id"]))

    # -----------------------------------------------------------------
    # CICLO DE VIDA Y LIMPIEZA SEGURA
    # -----------------------------------------------------------------
    def stop_media(self, flush_events: bool = True):
        """Detiene el previsualizador de video al cambiar de pestaña o lanzar juego."""
        if hasattr(self, "previewer") and self.previewer:
            self.previewer.stop_and_release(flush_events=flush_events)

    def cleanup(self):
        """Libera hilos y reproductores al cerrar el configurador."""
        self.stop_media(flush_events=False)
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(500)

    def _open_pro_toolkit(self):
        row = self._current_list_row()
        if not row:
            QMessageBox.information(self, "Lista requerida", "Seleccioná una lista primero.")
            return
        from playnexus.ui.toolkit_dialogs import RomToolkitDialog

        self.previewer.stop_and_release(flush_events=True)
        games = self.db.get_games(int(row["id"]), enriched=True) if row.get("list_type") != "menu" else []
        dlg = RomToolkitDialog(self.db, row, games, parent=self)
        dlg.media_mutated.connect(lambda: self.start_scan())
        def _on_lib_mutated():
            self.list_updated.emit(int(row["id"]))
            self.start_scan()
        dlg.library_mutated.connect(_on_lib_mutated)
        dlg.exec()

    def _open_retroachievements(self):
        row = self._current_list_row()
        if not row:
            QMessageBox.information(self, "Lista requerida", "Seleccioná una lista primero.")
            return
        if row.get("list_type") == "menu":
            QMessageBox.information(self, "No aplicable", "Los menús de sistemas no tienen ROMs directas para RetroAchievements.")
            return
        from playnexus.ui.ra_dialogs import RABatchSyncDialog

        games = self.db.get_games(int(row["id"]), enriched=True)
        dlg = RABatchSyncDialog(self.db, row, games, parent=self)
        dlg.sync_finished.connect(self._populate_table)
        dlg.exec()

    def _open_ra_single(self, game_id: int):
        g = self.db.get_game(game_id)
        if not g:
            return
        from playnexus.ui.ra_dialogs import RAGameDetailDialog

        dlg = RAGameDetailDialog(self.db, g, list_row=self._current_list_row(), parent=self)
        dlg.progress_updated.connect(lambda _d: self._populate_table())
        dlg.exec()

    def _open_manual_for_rom(self, game_id: int):
        g = self.db.get_game(game_id)
        if not g:
            return
        from playnexus.services.media import resolve_game_manual_pdf
        from playnexus.ui.manual_viewer import ManualViewerDialog

        pdf = resolve_game_manual_pdf(g, list_row=self._current_list_row())
        if not pdf:
            QMessageBox.information(self, "Sin manual", "Este juego no tiene un archivo PDF de manual asignado.")
            return
        ManualViewerDialog(pdf, game_title=g.get("title", ""), db=self.db, parent=self).exec()
