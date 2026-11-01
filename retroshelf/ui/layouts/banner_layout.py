from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QRect, QModelIndex, QSize
from PySide6.QtGui import (
    QFont, QColor, QLinearGradient, QBrush, QPainter,
    QPen, QPainterPath, QPixmap
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QStyleOptionViewItem, QStyledItemDelegate, QStyle
)
from retroshelf.ui.layouts.base import BaseLayout
from retroshelf.ui.cover_utils import load_cover, palette_for_title


class BannerItemDelegate(QStyledItemDelegate):
    """Delegado personalizado que pinta cada juego como un banner horizontal rico."""

    ITEM_H = 84

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumb_cache: dict = {}

    def invalidate_cache(self):
        self._thumb_cache.clear()

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
            platform = game_data.get("platform")
            emu = game_data.get("effective_name", "Sin emulador")
            source = game_data.get("source", "")
            game_id = game_data.get("id", 0)
            cover_path = game_data.get("cover_path")
            rom_path = game_data.get("rom_path", "")
            p = Path(rom_path)
            ext = p.suffix.upper() if p.suffix else ".ROM"

            # Fondo del banner
            banner_rect = QRect(rect.x() + 4, rect.y() + 3, rect.width() - 8, rect.height() - 6)
            path = QPainterPath()
            path.addRoundedRect(banner_rect.x(), banner_rect.y(), banner_rect.width(), banner_rect.height(), 8, 8)

            if is_selected:
                bg = QColor("#2a2060")
                border = QColor("#7b6be8")
            elif is_hover:
                bg = QColor("#1e2435")
                border = QColor("#3a4468")
            else:
                bg = QColor("#191d29")
                border = QColor("#252c3e")

            painter.fillPath(path, QBrush(bg))
            painter.setPen(QPen(border, 1 if not is_selected else 1.5))
            painter.drawPath(path)

            # Barra de color lateral (basada en el titulo del juego)
            dark_hex, bright_hex = palette_for_title(title)
            accent = QColor(bright_hex)
            accent_path = QPainterPath()
            accent_path.addRoundedRect(banner_rect.x(), banner_rect.y(), 5, banner_rect.height(), 3, 3)
            painter.fillPath(accent_path, QBrush(accent))

            thumb_x = banner_rect.x() + 12
            thumb_w = 60
            thumb_h = banner_rect.height() - 10
            thumb_rect = QRect(thumb_x, banner_rect.y() + 5, thumb_w, thumb_h)

            # Miniatura de la portada
            cache_key = (game_id, thumb_w, thumb_h)
            if cache_key not in self._thumb_cache:
                pix = load_cover(cover_path, title, platform, QSize(thumb_w, thumb_h))
                self._thumb_cache[cache_key] = pix
            pix = self._thumb_cache[cache_key]

            thumb_path = QPainterPath()
            thumb_path.addRoundedRect(thumb_rect.x(), thumb_rect.y(), thumb_rect.width(), thumb_rect.height(), 6, 6)
            painter.setClipPath(thumb_path)
            scaled = pix.scaled(thumb_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            dx = thumb_rect.x() + (thumb_rect.width() - scaled.width()) // 2
            dy = thumb_rect.y() + (thumb_rect.height() - scaled.height()) // 2
            painter.drawPixmap(dx, dy, scaled)
            painter.setClipRect(rect)

            # Area de texto
            text_x = thumb_x + thumb_w + 12
            text_w = banner_rect.right() - text_x - 8

            # Titulo principal
            title_font = QFont("Segoe UI", 10, QFont.Bold)
            painter.setFont(title_font)
            painter.setPen(QColor(235, 240, 255) if not is_selected else QColor(255, 255, 255))
            painter.drawText(QRect(text_x, banner_rect.y() + 8, text_w, 22),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             title[:50] + ("..." if len(title) > 50 else ""))

            # Badge de extension y plataforma
            badge_font = QFont("Segoe UI", 7, QFont.Bold)
            painter.setFont(badge_font)
            badge_text = ext
            if platform:
                badge_text += f"  |  {platform[:16]}"
            painter.setPen(QColor(bright_hex) if not is_selected else QColor(200, 190, 255))
            painter.drawText(QRect(text_x, banner_rect.y() + 32, text_w, 18),
                             Qt.AlignLeft | Qt.AlignVCenter, badge_text)

            # Emulador (linea inferior)
            emu_font = QFont("Segoe UI", 8)
            painter.setFont(emu_font)
            source_icon = "★" if source == "juego" else "◆" if source == "lista" else "○"
            emu_color = QColor(0x4a, 0xde, 0x80) if not is_selected else QColor(180, 255, 200)
            painter.setPen(emu_color)
            painter.drawText(QRect(text_x, banner_rect.y() + 52, text_w, 18),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             f"{source_icon}  {emu[:40]}" + ("..." if len(emu) > 40 else ""))

            # Tamano del archivo (derecha)
            if p.exists():
                mb = p.stat().st_size / (1024 * 1024)
                size_str = f"{mb:.1f} MB"
            else:
                size_str = "?"
            painter.setPen(QColor(100, 110, 130))
            size_font = QFont("Segoe UI", 7)
            painter.setFont(size_font)
            painter.drawText(QRect(banner_rect.right() - 70, banner_rect.y(), 65, banner_rect.height()),
                             Qt.AlignRight | Qt.AlignVCenter, size_str)

        finally:
            painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ITEM_H)


class BannerLayout(BaseLayout):
    """
    Layout personalizado: Lista estilo Banner con miniaturas, colores de acento y datos ricos.
    Cada juego se muestra como una tarjeta horizontal amplia con miniatura de portada,
    barra de color lateral unica, titulo, plataforma, emulador y tamano.
    """
    LAYOUT_NAME = "Banners"
    LAYOUT_DESCRIPTION = "Lista de tarjetas horizontales con miniaturas y datos ricos"

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._delegate = BannerItemDelegate()
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.setItemDelegate(self._delegate)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setStyleSheet("""
            QListWidget { background-color: #14161f; border: none; }
            QListWidget::item { background: transparent; border: none; }
            QListWidget::item:selected { background: transparent; }
        """)

        self.list_widget.itemSelectionChanged.connect(self._on_item_selected)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.list_widget)

    def render_games(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._delegate.invalidate_cache()

        for g in self.games:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, g["id"])
            item.setData(Qt.UserRole + 10, g)
            item.setToolTip(f"{g['title']}\n{g['rom_path']}")
            item.setSizeHint(QSize(0, BannerItemDelegate.ITEM_H))
            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

        if self.current_game_id:
            self.select_game_by_id(self.current_game_id)
        elif self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def select_game_by_id(self, game_id):
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
        if item and self._can_activate_game():
            self.game_activated.emit(item.data(Qt.UserRole))

    def _on_context_menu(self, pos: QPoint):
        item = self.list_widget.itemAt(pos)
        if item:
            game_id = item.data(Qt.UserRole)
            global_pos = self.list_widget.mapToGlobal(pos)
            self.context_menu_requested.emit(game_id, global_pos)
