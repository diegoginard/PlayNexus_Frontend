from pathlib import Path
from PySide6.QtCore import Qt, QSize, QPoint, QRect
from PySide6.QtGui import QFont, QColor, QLinearGradient, QBrush, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QFrame
)
from playnexus.ui.layouts.base import BaseLayout
from playnexus.ui.cover_utils import load_cover


class CoverLabel(QLabel):
    """Label que renderiza la portada de juego con esquinas redondeadas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self.setFixedSize(180, 160)

    def set_cover(self, pix):
        self._pixmap = pix
        self.update()

    def paintEvent(self, event):
        if not self._pixmap:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 10, 10)
        painter.setClipPath(path)
        scaled = self._pixmap.scaled(QSize(w, h), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = (w - scaled.width()) // 2
        y = (h - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()


class ShowcaseLayout(BaseLayout):
    """
    Layout personalizado: Modo Cinematico / Showcase.
    Muestra el juego seleccionado en un banner heroe con portada a la izquierda
    e informacion detallada a la derecha. Carrusel de seleccion inferior.
    """
    LAYOUT_NAME = "Showcase"
    LAYOUT_DESCRIPTION = "Modo Cinematico con banner principal y carrusel inferior"

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(10)

        # 1. Panel Superior: Hero Showcase Banner
        self.hero_card = QFrame()
        self.hero_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #181c28, stop:1 #222840);
                border: 1px solid #2f3750;
                border-radius: 14px;
            }
        """)
        hero_layout = QHBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(20, 16, 20, 16)
        hero_layout.setSpacing(20)

        self.cover_label = CoverLabel()
        hero_layout.addWidget(self.cover_label, 0, Qt.AlignTop)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)

        badges_row = QHBoxLayout()
        self.format_badge = QLabel("RETRO")
        self.format_badge.setStyleSheet("""
            background-color: #5d48d9;
            color: #ffffff;
            font-size: 8pt;
            font-weight: bold;
            padding: 3px 10px;
            border-radius: 4px;
        """)
        badges_row.addWidget(self.format_badge)
        self.size_badge = QLabel("--")
        self.size_badge.setStyleSheet("color: #9ba8bd; font-size: 9pt; padding-left: 6px;")
        badges_row.addWidget(self.size_badge)
        badges_row.addStretch()
        info_layout.addLayout(badges_row)

        self.title_label = QLabel("Selecciona un juego")
        self.title_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.title_label.setStyleSheet("color: #f1f3f9;")
        self.title_label.setWordWrap(True)
        info_layout.addWidget(self.title_label)

        self.path_label = QLabel("--")
        self.path_label.setStyleSheet("color: #8c99ac; font-size: 9pt;")
        self.path_label.setWordWrap(True)
        info_layout.addWidget(self.path_label)

        self.emu_label = QLabel("Emulador: --")
        self.emu_label.setStyleSheet("color: #4ade80; font-weight: 600; font-size: 10pt;")
        info_layout.addWidget(self.emu_label)

        info_layout.addStretch()

        btn_row = QHBoxLayout()
        self.play_btn = QPushButton("Play JUGAR AHORA")
        self.play_btn.setFocusPolicy(Qt.NoFocus)
        self.play_btn.setMinimumHeight(44)
        self.play_btn.setFixedWidth(200)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #5d48d9;
                color: #ffffff;
                font-weight: bold;
                font-size: 11pt;
                border-radius: 8px;
                border: 1px solid #7563ed;
            }
            QPushButton:hover { background-color: #6e59ea; }
            QPushButton:disabled { background-color: #2a2d3e; color: #555870; border-color: #2a2d3e; }
        """)
        self.play_btn.clicked.connect(self._on_play_clicked)
        btn_row.addWidget(self.play_btn)
        btn_row.addStretch()
        info_layout.addLayout(btn_row)

        hero_layout.addLayout(info_layout, 1)
        main_layout.addWidget(self.hero_card, 2)

        strip_header = QLabel("COLECCION DE JUEGOS")
        strip_header.setStyleSheet("color: #8e9bb0; font-weight: bold; font-size: 9pt; letter-spacing: 1px;")
        main_layout.addWidget(strip_header)

        self.strip_widget = QListWidget()
        self.strip_widget.setViewMode(QListWidget.IconMode)
        self.strip_widget.setResizeMode(QListWidget.Adjust)
        self.strip_widget.setMovement(QListWidget.Static)
        self.strip_widget.setGridSize(QSize(160, 90))
        self.strip_widget.setSpacing(8)
        self.strip_widget.setFixedHeight(115)
        self.strip_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.strip_widget.setStyleSheet("""
            QListWidget { background-color: #12141a; border: 1px solid #232738; border-radius: 8px; }
            QListWidget::item { background-color: #1c202d; border: 1px solid #29304a; border-radius: 6px; color: #c5cce3; font-size: 8pt; }
            QListWidget::item:hover { background-color: #252b3d; border-color: #4a527a; }
            QListWidget::item:selected { background-color: #5d48d9; border-color: #7b6be8; color: #ffffff; }
        """)

        self.strip_widget.itemSelectionChanged.connect(self._on_item_selected)
        self.strip_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.strip_widget.customContextMenuRequested.connect(self._on_context_menu)
        main_layout.addWidget(self.strip_widget, 1)

    def render_games(self):
        self.strip_widget.blockSignals(True)
        self.strip_widget.clear()
        for g in self.games:
            p = Path(g["rom_path"])
            badge = p.suffix.upper()
            title = g["title"]
            short = title[:20] + ("..." if len(title) > 20 else "")
            item = QListWidgetItem(f"\n{short}\n[{badge}]")
            item.setData(Qt.UserRole, g["id"])
            item.setTextAlignment(Qt.AlignCenter)
            self.strip_widget.addItem(item)
        self.strip_widget.blockSignals(False)

        if self.current_game_id:
            self.select_game_by_id(self.current_game_id)
        elif self.strip_widget.count() > 0:
            self.strip_widget.setCurrentRow(0)
        else:
            self._update_hero(None)

    def select_game_by_id(self, game_id):
        self.current_game_id = game_id
        for i in range(self.strip_widget.count()):
            item = self.strip_widget.item(i)
            if item.data(Qt.UserRole) == game_id:
                self.strip_widget.blockSignals(True)
                self.strip_widget.setCurrentItem(item)
                self.strip_widget.blockSignals(False)
                break
        self._update_hero(game_id)

    def _update_hero(self, game_id):
        if not game_id or not self.games:
            self.title_label.setText("No hay juegos seleccionados")
            self.format_badge.setText("RETRO")
            self.size_badge.setText("--")
            self.path_label.setText("--")
            self.emu_label.setText("Emulador: --")
            self.play_btn.setEnabled(False)
            blank = load_cover(None, "PlayNexus", QSize(180, 160))
            self.cover_label.set_cover(blank)
            return

        game = next((g for g in self.games if g["id"] == game_id), None)
        if not game:
            return

        self.play_btn.setEnabled(True)
        self.title_label.setText(game["title"])
        p = Path(game["rom_path"])
        self.format_badge.setText(p.suffix.upper() or ".ROM")
        self.path_label.setText(str(p))

        if p.exists():
            mb = p.stat().st_size / (1024 * 1024)
            self.size_badge.setText(f"{mb:.2f} MB")
        else:
            self.size_badge.setText("Archivo no encontrado")

        emu = game.get("effective_name", "Sin emulador")
        source = game.get("source", "")
        source_str = f" ({source})" if source else ""
        xml_bits = []
        if game.get("year"):
            xml_bits.append(str(game["year"]))
        if game.get("manufacturer"):
            xml_bits.append(str(game["manufacturer"]))
        if game.get("genre"):
            xml_bits.append(str(game["genre"]))
        if game.get("players"):
            xml_bits.append(f"{game['players']} Jug.")
        extra_meta = f"   |   {' · '.join(xml_bits)}" if xml_bits else ""
        self.emu_label.setText(f"Emulador: {emu}{source_str}{extra_meta}")

        cover = load_cover(game.get("cover_path"), game["title"], QSize(180, 160))
        self.cover_label.set_cover(cover)

    def _on_item_selected(self):
        items = self.strip_widget.selectedItems()
        if items:
            game_id = items[0].data(Qt.UserRole)
            self.current_game_id = game_id
            self._update_hero(game_id)
            self.game_selected.emit(game_id)

    def _on_item_double_clicked(self, item):
        if item and self._can_activate_game():
            self.game_activated.emit(item.data(Qt.UserRole))

    def _on_play_clicked(self):
        if self.current_game_id and self._can_activate_game():
            self.game_activated.emit(self.current_game_id)

    def _on_context_menu(self, pos):
        item = self.strip_widget.itemAt(pos)
        if item:
            game_id = item.data(Qt.UserRole)
            global_pos = self.strip_widget.mapToGlobal(pos)
            self.context_menu_requested.emit(game_id, global_pos)
