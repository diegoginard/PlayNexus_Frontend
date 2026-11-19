from pathlib import Path
from PySide6.QtCore import Qt, QSize, QPoint, QRect
from PySide6.QtGui import QFont, QColor, QLinearGradient, QBrush, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QFrame
)
from playnexus.i18n import tr
from playnexus.ui.layouts.base import (
    BaseLayout,
    CoverPreloadWorker,
    CoverCacheLRU,
    make_rounded_cover_pixmap,
)
from playnexus.ui.cover_utils import generate_placeholder_cover


class CoverLabel(QLabel):
    """Label que renderiza la portada pre-escalada y redondeada sin reescalar en `paintEvent`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._rendered_pixmap = None
        self.setFixedSize(180, 160)

    def _rebuild_rendered(self):
        if self._pixmap is None or self._pixmap.isNull():
            self._rendered_pixmap = None
            return
        self._rendered_pixmap = make_rounded_cover_pixmap(
            self._pixmap,
            max(1, self.width()),
            max(1, self.height()),
            radius=10,
        )

    def set_cover(self, pix):
        self._pixmap = pix
        self._rebuild_rendered()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_rendered()

    def paintEvent(self, event):
        if self._rendered_pixmap is None or self._rendered_pixmap.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._rendered_pixmap)
        painter.end()


class ShowcaseLayout(BaseLayout):
    """
    Layout personalizado: Modo Cinematico / Showcase.
    Muestra el juego seleccionado en un banner heroe con portada a la izquierda
    e informacion detallada a la derecha. Carrusel de seleccion inferior.
    """
    LAYOUT_NAME = "Showcase"
    LAYOUT_DESCRIPTION = tr("layout.showcase_desc", "Cinematic mode with main hero banner and bottom carousel")

    def __init__(self, parent=None):
        super().__init__(parent)

        self._cover_worker = CoverPreloadWorker(
            self,
            aspect_mode=Qt.KeepAspectRatioByExpanding,
            collect_rom_size=True,
        )
        self._cover_worker.cover_loaded.connect(self._on_hero_cover_loaded)
        self._cover_worker.rom_size_loaded.connect(self._on_hero_rom_size_loaded)
        self._hero_cover_cache = CoverCacheLRU(max_items=64)
        self._rom_size_cache: dict[int, str] = {}

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
        self.format_badge = QLabel(tr("layout.retro_badge", "RETRO"))
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

        self.title_label = QLabel(tr("layout.select_game", "Select a game"))
        self.title_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.title_label.setStyleSheet("color: #f1f3f9;")
        self.title_label.setWordWrap(True)
        info_layout.addWidget(self.title_label)

        self.path_label = QLabel("--")
        self.path_label.setStyleSheet("color: #8c99ac; font-size: 9pt;")
        self.path_label.setWordWrap(True)
        info_layout.addWidget(self.path_label)

        self.emu_label = QLabel(tr("layout.emulator_empty", "Emulator: --"))
        self.emu_label.setStyleSheet("color: #4ade80; font-weight: 600; font-size: 10pt;")
        info_layout.addWidget(self.emu_label)

        info_layout.addStretch()

        btn_row = QHBoxLayout()
        self.play_btn = QPushButton(tr("layout.play_now_btn", "▶ PLAY NOW"))
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

        strip_header = QLabel(tr("layout.game_collection_header", "GAME COLLECTION"))
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

    def _on_hero_cover_loaded(self, gid: int, tw: int, th: int, img):
        if img is not None and not img.isNull():
            rounded = make_rounded_cover_pixmap(img, tw, th, radius=10)
            self._hero_cover_cache.put((gid, tw, th), rounded)
            if gid == self.current_game_id:
                self.cover_label.set_cover(rounded)
        else:
            self._hero_cover_cache.put((gid, tw, th), False)

    def _on_hero_rom_size_loaded(self, gid: int, size_str: str):
        label_txt = tr("layout.file_not_found", "File not found") if size_str == "?" else size_str
        self._rom_size_cache[gid] = label_txt
        if gid == self.current_game_id:
            self.size_badge.setText(label_txt)

    def render_games(self):
        self.strip_widget.blockSignals(True)
        self.strip_widget.clear()
        self._hero_cover_cache.clear()
        self._rom_size_cache.clear()
        if hasattr(self, "_cover_worker") and self._cover_worker:
            self._cover_worker.clear()
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
            self.title_label.setText(tr("layout.no_games_selected", "No games selected"))
            self.format_badge.setText(tr("layout.retro_badge", "RETRO"))
            self.size_badge.setText("--")
            self.path_label.setText("--")
            self.emu_label.setText(tr("layout.emulator_empty", "Emulator: --"))
            self.play_btn.setEnabled(False)
            blank = generate_placeholder_cover("PlayNexus", QSize(180, 160))
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

        cached_sz = self._rom_size_cache.get(game_id)
        self.size_badge.setText(cached_sz if cached_sz is not None else "--")

        raw_emu = game.get("effective_name")
        emu = tr("layout.no_emulator", "No emulator") if not raw_emu or raw_emu == "Sin emulador" else raw_emu
        source = game.get("source", "")
        source_lbl = {
            "juego": tr("layout.source_game", "game"),
            "lista": tr("layout.source_list", "list"),
            "ninguno": tr("layout.source_none", "none"),
            "menu": tr("layout.source_menu", "menu"),
        }.get(source, source)
        source_str = f" ({source_lbl})" if source_lbl else ""
        xml_bits = []
        if game.get("year"):
            xml_bits.append(str(game["year"]))
        if game.get("manufacturer"):
            xml_bits.append(str(game["manufacturer"]))
        if game.get("genre"):
            xml_bits.append(str(game["genre"]))
        if game.get("players"):
            xml_bits.append(tr("layout.players_short", "{players} Pl.", players=game["players"]))
        extra_meta = f"   |   {' · '.join(xml_bits)}" if xml_bits else ""
        self.emu_label.setText(
            tr(
                "layout.showcase_emu_line",
                "Emulator: {emulator}{source}{extra}",
                emulator=emu,
                source=source_str,
                extra=extra_meta,
            )
        )

        tw = max(1, self.cover_label.width())
        th = max(1, self.cover_label.height())
        cached_cov = self._hero_cover_cache.get((game_id, tw, th))
        if isinstance(cached_cov, QPixmap) and not cached_cov.isNull():
            self.cover_label.set_cover(cached_cov)
        else:
            ph = generate_placeholder_cover(game["title"], QSize(tw, th))
            self.cover_label.set_cover(ph)
            if cached_cov is None and hasattr(self, "_cover_worker") and self._cover_worker:
                if not self._cover_worker.isRunning():
                    self._cover_worker.start()
                self._cover_worker.queue_game(game, tw, th, priority=True)

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

    def closeEvent(self, event):
        if hasattr(self, "_cover_worker") and self._cover_worker:
            self._cover_worker.stop()
        if event is not None:
            super().closeEvent(event)
