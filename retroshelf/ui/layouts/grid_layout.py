from pathlib import Path
from PySide6.QtCore import Qt, QSize, QRect, QPoint, QModelIndex
from PySide6.QtGui import (
    QFont, QColor, QLinearGradient, QBrush, QPainter,
    QPen, QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QSlider, QLabel, QStyleOptionViewItem, QStyledItemDelegate, QStyle
)
from retroshelf.ui.layouts.base import BaseLayout
from retroshelf.ui.cover_utils import load_cover


class GameCardDelegate(QStyledItemDelegate):
    """
    Delegado personalizado que pinta cada juego como una tarjeta visual
    con portada, título, badge de plataforma y emulador.
    """
    def __init__(self, card_size: QSize, parent=None):
        super().__init__(parent)
        self.card_w = card_size.width()
        self.card_h = card_size.height()
        self._cover_cache: dict[int, object] = {}  # game_id -> QPixmap

    def update_card_size(self, w: int, h: int):
        self.card_w = w
        self.card_h = h
        self._cover_cache.clear()

    def invalidate_cache(self):
        self._cover_cache.clear()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

            rect = option.rect
            is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
            is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

            game_data = index.data(Qt.UserRole + 10)
            if not game_data:
                return

            title = game_data.get("title", "Desconocido")
            platform = game_data.get("platform", None)
            emu = game_data.get("effective_name", "Sin emulador")
            game_id = game_data.get("id", 0)
            cover_path = game_data.get("cover_path", None)

            # ── Fondo de la tarjeta ──────────────────────────────────────
            card_rect = QRect(rect.x() + 6, rect.y() + 6, rect.width() - 12, rect.height() - 12)
            path = QPainterPath()
            path.addRoundedRect(card_rect.x(), card_rect.y(), card_rect.width(), card_rect.height(), 10, 10)

            if is_selected:
                bg = QColor("#5d48d9")
                border = QColor("#8b7bef")
            elif is_hover:
                bg = QColor("#262c3e")
                border = QColor("#4a5577")
            else:
                bg = QColor("#1c2030")
                border = QColor("#2e3549")

            painter.fillPath(path, QBrush(bg))
            pen = QPen(border, 1.5 if is_selected else 1)
            painter.setPen(pen)
            painter.drawPath(path)

            # ── Portada ──────────────────────────────────────────────────
            cover_area_h = int(card_rect.height() * 0.65)
            cover_rect = QRect(card_rect.x(), card_rect.y(), card_rect.width(), cover_area_h)

            cache_key = (game_id, self.card_w, self.card_h)
            if cache_key not in self._cover_cache:
                pix = load_cover(cover_path, title, platform, QSize(cover_rect.width(), cover_rect.height()))
                self._cover_cache[cache_key] = pix
            else:
                pix = self._cover_cache[cache_key]

            # Recortar portada en el área superior con esquinas redondeadas
            cover_path_clip = QPainterPath()
            cover_path_clip.addRoundedRect(cover_rect.x(), cover_rect.y(),
                                           cover_rect.width(), cover_area_h, 10, 10)
            painter.setClipPath(cover_path_clip)
            scaled_pix = pix.scaled(cover_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            draw_x = cover_rect.x() + (cover_rect.width() - scaled_pix.width()) // 2
            draw_y = cover_rect.y() + (cover_rect.height() - scaled_pix.height()) // 2
            painter.drawPixmap(draw_x, draw_y, scaled_pix)
            painter.setClipRect(rect)  # reset clip

            # Degradado sobre la portada para legibilidad del título
            overlay_grad = QLinearGradient(0, cover_rect.y(), 0, cover_rect.y() + cover_area_h)
            overlay_grad.setColorAt(0.4, QColor(0, 0, 0, 0))
            overlay_grad.setColorAt(1.0, QColor(0, 0, 0, 160))
            painter.fillRect(cover_rect, QBrush(overlay_grad))

            # ── Zona inferior de texto ───────────────────────────────────
            text_y = card_rect.y() + cover_area_h + 4
            text_h = card_rect.height() - cover_area_h - 4
            text_rect = QRect(card_rect.x() + 6, text_y, card_rect.width() - 12, text_h)

            title_font = QFont("Segoe UI", max(7, self.card_w // 18), QFont.Bold)
            painter.setFont(title_font)
            painter.setPen(QColor(240, 242, 250) if not is_selected else QColor(255, 255, 255))
            painter.drawText(QRect(text_rect.x(), text_rect.y(), text_rect.width(), text_rect.height() // 2 + 4),
                             Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
                             title[:32] + ("…" if len(title) > 32 else ""))

            # Nombre del emulador (línea inferior)
            emu_font = QFont("Segoe UI", max(6, self.card_w // 22))
            painter.setFont(emu_font)
            painter.setPen(QColor(0x4a, 0xde, 0x80, 210) if not is_selected else QColor(200, 255, 200))
            emu_short = emu[:22] + ("…" if len(emu) > 22 else "")
            painter.drawText(QRect(text_rect.x(), text_rect.y() + text_h // 2,
                                   text_rect.width(), text_h // 2),
                             Qt.AlignLeft | Qt.AlignVCenter, emu_short)
        finally:
            painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(self.card_w + 12, self.card_h + 12)


class GridLayout(BaseLayout):
    """
    Layout personalizado: Cuadrícula de Tarjetas Visuales con portadas.
    Cada juego se muestra como una tarjeta con imagen de portada generada o real,
    título y emulador. El tamaño de las tarjetas se puede ajustar con el slider.
    """
    LAYOUT_NAME = "Grid"
    LAYOUT_DESCRIPTION = "Cuadrícula de tarjetas visuales con portadas y tamaño regulable"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._platform_cache: dict[int, str | None] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Barra superior de control de zoom
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(6, 2, 6, 2)
        ctrl_bar.addStretch()

        zoom_lbl = QLabel("Tamaño de tarjetas:")
        zoom_lbl.setStyleSheet("color: #8e9bb0; font-size: 9pt;")
        ctrl_bar.addWidget(zoom_lbl)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(140, 280)
        self.zoom_slider.setValue(190)
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #2e3549; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #5d48d9; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ffffff; width: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        ctrl_bar.addWidget(self.zoom_slider)
        layout.addLayout(ctrl_bar)

        # Inicializar el delegado
        initial_w = 190
        initial_h = int(initial_w * 0.85)
        self._delegate = GameCardDelegate(QSize(initial_w, initial_h))

        # Widget de lista en modo cuadrícula
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.IconMode)
        self.list_widget.setResizeMode(QListWidget.Adjust)
        self.list_widget.setMovement(QListWidget.Static)
        self.list_widget.setSpacing(8)
        self.list_widget.setWordWrap(True)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.setItemDelegate(self._delegate)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #15171e;
                border: none;
            }
            QListWidget::item {
                background: transparent;
                border: none;
            }
            QListWidget::item:selected {
                background: transparent;
            }
        """)

        self._apply_grid_size(initial_w)

        self.list_widget.itemSelectionChanged.connect(self._on_item_selected)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.list_widget, 1)

    def _apply_grid_size(self, width: int):
        height = int(width * 0.85)
        self.list_widget.setGridSize(QSize(width + 20, height + 20))
        self._delegate.update_card_size(width, height)

    def _on_zoom_changed(self, value: int):
        self._apply_grid_size(value)
        self.render_games()

    def set_platform_cache(self, platform_cache: dict):
        """Actualiza la caché de plataformas por lista (para portadas generadas correctamente)."""
        self._platform_cache = platform_cache

    def render_games(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._delegate.invalidate_cache()

        for g in self.games:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, g["id"])
            item.setData(Qt.UserRole + 10, g)
            item.setToolTip(
                f"{g['title']}\n"
                f"Archivo: {Path(g['rom_path']).name}\n"
                f"Emulador: {g.get('effective_name', 'Sin emulador')}\n"
                f"Ruta: {g['rom_path']}"
            )
            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

        if self.current_game_id:
            self.select_game_by_id(self.current_game_id)
        elif self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def select_game_by_id(self, game_id: int):
        self.current_game_id = game_id
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == game_id:
                self.list_widget.blockSignals(True)
                self.list_widget.setCurrentItem(item)
                self.list_widget.blockSignals(False)
                break

    def _on_item_selected(self):
        items = self.list_widget.selectedItems()
        if items:
            game_id = items[0].data(Qt.UserRole)
            self.current_game_id = game_id
            self.game_selected.emit(game_id)

    def _on_item_double_clicked(self, item):
        if item:
            game_id = item.data(Qt.UserRole)
            if self._can_activate_game():
                self.game_activated.emit(game_id)

    def _on_context_menu(self, pos: QPoint):
        item = self.list_widget.itemAt(pos)
        if item:
            game_id = item.data(Qt.UserRole)
            global_pos = self.list_widget.mapToGlobal(pos)
            self.context_menu_requested.emit(game_id, global_pos)
