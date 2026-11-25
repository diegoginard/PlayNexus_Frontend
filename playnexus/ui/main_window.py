import sys
import os
import subprocess
from pathlib import Path
import playnexus
from PySide6.QtCore import Qt, QSize, QPoint, QTimer, QUrl, QEvent
from PySide6.QtGui import QAction, QFont, QIcon, QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QComboBox, QLineEdit, QFileDialog, QMessageBox, QSplitter,
    QGroupBox, QFormLayout, QAbstractItemView, QMenu, QToolBar, QStackedWidget,
    QFrame, QTabWidget, QCheckBox, QScrollArea, QSizePolicy
)
from playnexus.db import Database, format_play_time
from playnexus.i18n import init_i18n, tr
from playnexus.services.library import (
    scan_rom_folder, import_scanned_games, add_game, parse_extensions_list,
    parse_rom_xml, enrich_game_dict,
    parse_rom_folders, format_rom_folders, sync_filtered_list_games,
    sync_filtered_lists_for_source,
)
from playnexus.services.media import clear_media_cache, is_game_vertical
from playnexus.services.launcher import launch_game, resolve_emulator
from playnexus.ui.dialogs import (
    EmulatorDialog, ListDialog, EmulatorManagerDialog, EmulatorManagerWidget,
    ScanSummaryDialog, GameEditDialog, ScanProgressDialog
)
from playnexus.ui.frontend_tab import FrontendSettingsWidget
from playnexus.ui.settings_tab import SystemSettingsWidget
from playnexus.ui.layout_studio import LayoutStudioWidget
from playnexus.ui.layouts import LAYOUT_REGISTRY, get_available_layouts, create_layout, resolve_theme_name
from playnexus import __version__, __version_full__

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #15171e;
    color: #e6e9f0;
}

QToolBar {
    background-color: #1b1e28;
    border-bottom: 1px solid #2b3040;
    padding: 6px 10px;
    spacing: 8px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}
QToolButton:hover {
    background: #262b3a;
    border: 1px solid #3a4258;
}
QListWidget, QTableWidget, QLineEdit, QComboBox, QTextEdit {
    background-color: #1e222f;
    border: 1px solid #2e3549;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #5d48d9;
    selection-color: #ffffff;
}
QListWidget::item {
    padding: 8px;
    border-radius: 4px;
    margin-bottom: 2px;
}
QListWidget::item:selected {
    background-color: #5d48d9;
}
QListWidget::item:hover:!selected {
    background-color: #262b3c;
}
QHeaderView::section {
    background-color: #242938;
    padding: 8px;
    border: none;
    border-right: 1px solid #1e222f;
    border-bottom: 1px solid #2e3549;
    font-weight: 600;
}
QPushButton {
    background-color: #2b3144;
    border: 1px solid #3b445e;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #38415a;
    border-color: #4b5777;
}
QPushButton#primary {
    background-color: #5d48d9;
    border: 1px solid #715ee3;
    font-weight: bold;
    font-size: 11pt;
    color: #ffffff;
}
QPushButton#primary:hover {
    background-color: #6e5ae6;
}
QPushButton#danger {
    background-color: #462529;
    border: 1px solid #6b353c;
    color: #fca5a5;
}
QPushButton#danger:hover {
    background-color: #5c2f35;
}
QGroupBox {
    border: 1px solid #2d3448;
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #9aa5b9;
}
QSplitter::handle {
    background-color: #202432;
}
QStatusBar {
    background-color: #12141a;
    border-top: 1px solid #252a38;
    color: #8f9aa9;
}
QTabWidget::pane {
    border: 1px solid #232838;
    background-color: #15171e;
    border-radius: 8px;
    margin-top: -1px;
}
QTabBar::tab {
    background-color: #1a1e2a;
    border: 1px solid #282f42;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 10px 22px;
    font-size: 10pt;
    font-weight: 600;
    color: #8f9db5;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background-color: #242a3c;
    border-color: #5d48d9;
    color: #ffffff;
    border-bottom: 3px solid #5d48d9;
}
QTabBar::tab:hover:!selected {
    background-color: #202536;
    color: #e2e8f0;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: #141722;
    width: 8px;
    margin: 2px 0 2px 0;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #353d54;
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #4e597a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
"""

class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.db = db if db is not None else Database()
        self.current_list_id = None
        self.current_game_id = None
        self.games_cache = []
        self._pending_rom_manager_refresh = False
        self._pending_rom_manager_list_id = None

        self.setWindowTitle(
            tr("mw.window_title", "PlayNexus — Configurator {version}", version=__version_full__)
        )
        self.resize(1300, 820)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(DARK_STYLESHEET)

        root_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
        icon_path = root_dir / "app_icon.ico"
        if not icon_path.exists():
            icon_path = root_dir / "PlayNexus_icon.png"
        if not icon_path.exists():
            icon_path = root_dir / "PlayNexus_Logo.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self.refresh_lists()
        self.refresh_emulators()

        try:
            from playnexus.services.emulator_manager import EMULATOR_MANAGER
            EMULATOR_MANAGER.telemetry_updated.connect(self._on_telemetry_updated)
        except Exception:
            pass
        try:
            from playnexus.services.audio_guard import ensure_audio_guard_installed
            ensure_audio_guard_installed(self)
        except Exception:
            pass

    def _build_ui(self):
        # Estructura principal de la biblioteca
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        splitter = QSplitter(Qt.Horizontal)

        # Panel Izquierdo: Listas
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Logo de la aplicación
        root_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
        logo_path = root_dir / "PlayNexus_Logo.png"
        if logo_path.exists():
            logo_label = QLabel()
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                scaled_pix = pix.scaledToWidth(210, Qt.SmoothTransformation)
                logo_label.setPixmap(scaled_pix)
                logo_label.setAlignment(Qt.AlignCenter)
                logo_label.setStyleSheet("padding: 2px 0 6px 0;")
                left_layout.addWidget(logo_label)

        left_label = QLabel(tr("mw.left.header", "LISTS / PLATFORMS"))
        left_label.setStyleSheet("font-weight: bold; color: #8e9bb0; letter-spacing: 1px;")
        left_layout.addWidget(left_label)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.on_list_changed)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_list_context_menu)
        self.list_widget.setIconSize(QSize(24, 24))
        left_layout.addWidget(self.list_widget, 1)

        left_btns = QHBoxLayout()
        btn_add_l = QPushButton(tr("mw.left.create_btn", "＋ Create"))
        btn_add_l.clicked.connect(self.create_list)
        btn_edit_l = QPushButton(tr("mw.left.edit_btn", "✎ Edit"))
        btn_edit_l.clicked.connect(self.edit_current_list)
        btn_del_l = QPushButton("🗑")
        btn_del_l.setToolTip(tr("mw.left.delete_tip", "Delete list"))
        btn_del_l.setObjectName("danger")
        btn_del_l.clicked.connect(self.delete_current_list)
        left_btns.addWidget(btn_add_l)
        left_btns.addWidget(btn_edit_l)
        left_btns.addWidget(btn_del_l)
        left_layout.addLayout(left_btns)

        left_widget.setMinimumWidth(220)
        splitter.addWidget(left_widget)

        # Panel Central: Juegos y Vistas
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(6, 0, 6, 0)

        # Encabezado de la lista actual
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #1b1e2a; border-radius: 8px; padding: 10px;")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(8, 8, 8, 8)

        h_top = QHBoxLayout()
        self.list_title = QLabel(tr("mw.center.select_list", "Select a list"))
        self.list_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        h_top.addWidget(self.list_title, 1)

        self.layout_combo = QComboBox()
        self.layout_combo.addItems(get_available_layouts())
        self.layout_combo.currentTextChanged.connect(self.save_layout)
        h_top.addWidget(QLabel(tr("mw.center.visual_layout", "Visual layout:")))
        h_top.addWidget(self.layout_combo)

        # Control de sonido al probar layouts en configuración
        self.sound_checkbox = QCheckBox(tr("mw.center.sound_on", "🔊 Sound"))
        self.sound_checkbox.setFocusPolicy(Qt.NoFocus)
        self.sound_checkbox.setToolTip(tr("mw.center.sound_tip", "Enable or disable sound and effects when previewing visual layouts"))
        self.sound_checkbox.setStyleSheet("margin-left: 10px; font-weight: 500;")
        sound_pref = self.db.get_setting("layout_preview_sound", "true").strip().lower() in ("true", "1")
        self.sound_checkbox.setChecked(sound_pref)
        self.sound_checkbox.setText(tr("mw.center.sound_on", "🔊 Sound") if sound_pref else tr("mw.center.sound_off", "🔇 Sound"))
        self.sound_checkbox.toggled.connect(self._on_layout_sound_toggled)
        h_top.addWidget(self.sound_checkbox)
        header_layout.addLayout(h_top)

        self.list_meta_label = QLabel(tr("mw.center.exts_none", "Supported extensions: —"))
        self.list_meta_label.setStyleSheet("color: #9ba7bc; font-size: 9pt;")
        header_layout.addWidget(self.list_meta_label)
        center_layout.addWidget(header_card)

        # Barra de búsqueda y conteo
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("mw.center.search_placeholder", "Search by title or filename…"))
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.filter_games)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        search_row.addWidget(self.search, 1)

        self.game_count_label = QLabel(tr("mw.center.count_zero", "0 games"))
        self.game_count_label.setStyleSheet("color: #8e9bb0;")
        search_row.addWidget(self.game_count_label)
        center_layout.addLayout(search_row)

        # Contenedor de Layouts modulares personalizados (se instancian bajo demanda)
        self.layout_stack = QStackedWidget()
        self.active_layouts = {}
        center_layout.addWidget(self.layout_stack, 1)


        # Botones de acción inferior del centro
        center_btns = QHBoxLayout()
        btn_scan = QPushButton(tr("mw.center.scan_btn", "▣ Scan folder"))
        btn_scan.clicked.connect(self.scan_folder)
        btn_add = QPushButton(tr("mw.center.add_files_btn", "＋ Add files"))
        btn_add.clicked.connect(self.add_files)
        btn_edit_g = QPushButton(tr("mw.center.edit_game_btn", "✎ Edit game"))
        btn_edit_g.clicked.connect(self.edit_selected_game)
        btn_del_g = QPushButton(tr("mw.center.remove_game_btn", "Remove from library"))
        btn_del_g.setObjectName("danger")
        btn_del_g.clicked.connect(self.remove_game)

        center_btns.addWidget(btn_scan)
        center_btns.addWidget(btn_add)
        center_btns.addWidget(btn_edit_g)
        center_btns.addStretch()
        center_btns.addWidget(btn_del_g)
        center_layout.addLayout(center_btns)

        splitter.addWidget(center_widget)

        # Panel Derecho: Detalles del Juego (con scroll) y Lanzamiento fijo abajo
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(QFrame.NoFrame)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        details_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 6, 4)
        scroll_layout.setSpacing(10)

        details_group = QGroupBox(tr("mw.details.group", "Details"))
        details_lay = QVBoxLayout(details_group)
        details_lay.setContentsMargins(12, 16, 12, 12)
        details_lay.setSpacing(9)

        def _add_detail_field(caption: str, field_widget: QWidget):
            block = QVBoxLayout()
            block.setContentsMargins(0, 0, 0, 0)
            block.setSpacing(2)
            lbl = QLabel(caption)
            lbl.setStyleSheet("color: #8e9bb0; font-size: 8.5pt; font-weight: 600;")
            block.addWidget(lbl)
            block.addWidget(field_widget)
            details_lay.addLayout(block)

        def _prep_detail_label(lbl: QLabel):
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            return lbl

        self.game_name = _prep_detail_label(QLabel("—"))
        self.game_name.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.game_name.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.game_rom_code = _prep_detail_label(QLabel("—"))
        self.game_rom_code.setStyleSheet("color: #c4b5fd; font-weight: 600;")
        self.game_rom_code.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.game_meta_info = _prep_detail_label(QLabel("—"))
        self.game_meta_info.setStyleSheet("color: #9ba7bc; font-size: 9pt;")
        self.game_meta_info.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.game_path = _prep_detail_label(QLabel("—"))
        self.game_path.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        self.game_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.game_size = _prep_detail_label(QLabel("—"))

        self.effective_emu = _prep_detail_label(QLabel("—"))
        self.effective_emu.setStyleSheet("font-weight: 600; color: #a5b4fc;")

        self.override_combo = QComboBox()
        self.override_combo.setMinimumHeight(32)
        self.override_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.override_combo.setMinimumContentsLength(14)
        self.override_combo.currentIndexChanged.connect(self.save_override)

        self.game_bezel_combo = QComboBox()
        self.game_bezel_combo.setMinimumHeight(32)
        self.game_bezel_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.game_bezel_combo.setMinimumContentsLength(14)
        self.game_bezel_combo.addItem(tr("mw.details.bezel_inherit", "Inherit from list (default)"), "")
        self.game_bezel_combo.addItem(tr("mw.details.bezel_enable", "Enable Bezel HUD (Force)"), "enabled")
        self.game_bezel_combo.addItem(tr("mw.details.bezel_disable", "Disable Bezel HUD"), "disabled")
        self.game_bezel_combo.currentIndexChanged.connect(self.save_game_bezel_hud)

        self.game_tags_label = _prep_detail_label(QLabel("—"))
        self.game_tags_label.setStyleSheet("color: #93c5fd; font-size: 9pt;")

        self.game_stats_label = _prep_detail_label(QLabel("—"))
        self.game_stats_label.setStyleSheet("color: #cbd5e1; font-size: 9pt;")

        _add_detail_field(tr("mw.details.title", "Title"), self.game_name)
        _add_detail_field(tr("mw.details.rom_code", "ROM / Code"), self.game_rom_code)
        _add_detail_field(tr("mw.details.props", "Properties"), self.game_meta_info)
        _add_detail_field(tr("mw.details.tags", "Tags"), self.game_tags_label)
        _add_detail_field(tr("mw.details.activity", "Activity"), self.game_stats_label)
        _add_detail_field(tr("mw.details.file", "File"), self.game_path)
        _add_detail_field(tr("mw.details.size", "Size"), self.game_size)
        _add_detail_field(tr("mw.details.effective_emu", "Active emulator"), self.effective_emu)
        _add_detail_field(tr("mw.details.override_emu", "Custom emulator"), self.override_combo)
        _add_detail_field(tr("mw.details.bezel_hud", "Bezel HUD"), self.game_bezel_combo)

        ra_row_w = QWidget()
        ra_row_lay = QHBoxLayout(ra_row_w)
        ra_row_lay.setContentsMargins(0, 0, 0, 0)
        ra_row_lay.setSpacing(6)
        self.game_ra_label = _prep_detail_label(QLabel("—"))
        self.game_ra_label.setStyleSheet("color: #fde047; font-weight: 600;")
        self.ra_detail_btn = QPushButton(tr("mw.details.ra_btn", "🏆 Achievements"))
        self.ra_detail_btn.setMinimumHeight(30)
        self.ra_detail_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.ra_detail_btn.setEnabled(False)
        self.ra_detail_btn.setToolTip(tr("mw.details.ra_tip", "View or refresh RetroAchievements"))
        self.ra_detail_btn.clicked.connect(self._open_selected_game_ra)
        ra_row_lay.addWidget(self.game_ra_label, 1)
        ra_row_lay.addWidget(self.ra_detail_btn)
        _add_detail_field(tr("mw.details.ra_field", "RetroAchievements"), ra_row_w)

        manual_row_w = QWidget()
        manual_row_lay = QHBoxLayout(manual_row_w)
        manual_row_lay.setContentsMargins(0, 0, 0, 0)
        manual_row_lay.setSpacing(6)
        self.game_manual_label = _prep_detail_label(QLabel("—"))
        self.manual_view_btn = QPushButton(tr("mw.details.manual_btn", "📖 View Manual"))
        self.manual_view_btn.setMinimumHeight(30)
        self.manual_view_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.manual_view_btn.setEnabled(False)
        self.manual_view_btn.setToolTip(tr("mw.details.manual_tip", "Open game PDF manual"))
        self.manual_view_btn.clicked.connect(self._open_selected_game_manual)
        manual_row_lay.addWidget(self.game_manual_label, 1)
        manual_row_lay.addWidget(self.manual_view_btn)
        _add_detail_field(tr("mw.details.manual_field", "PDF Manual"), manual_row_w)

        scroll_layout.addWidget(details_group)
        scroll_layout.addStretch()

        details_scroll.setWidget(scroll_content)
        right_layout.addWidget(details_scroll, 1)

        self.fav_toggle_btn = QPushButton(tr("mw.details.fav_add", "☆  Add to Favorites"))
        self.fav_toggle_btn.setMinimumHeight(34)
        self.fav_toggle_btn.setEnabled(False)
        self.fav_toggle_btn.clicked.connect(self.toggle_selected_favorite)
        right_layout.addWidget(self.fav_toggle_btn)

        self.launch_btn = QPushButton(tr("mw.details.launch_btn", "▶  LAUNCH GAME"))
        self.launch_btn.setObjectName("primary")
        self.launch_btn.setMinimumHeight(46)
        self.launch_btn.clicked.connect(self.launch_selected)
        right_layout.addWidget(self.launch_btn)

        right_widget.setMinimumWidth(300)
        splitter.addWidget(right_widget)

        splitter.setSizes([230, 690, 340])
        outer.addWidget(splitter)

        # Contenedor con pestañas principales
        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)
        self.main_tabs.addTab(root, tr("mw.tabs.library", "🎮  Game Library"))

        # Carga perezosa de Rom Manager: no instanciar reproductor hasta abrir la pestaña
        self.rom_manager_tab = None
        self._rom_manager_container = QWidget()
        rm_container_layout = QVBoxLayout(self._rom_manager_container)
        rm_container_layout.setContentsMargins(0, 0, 0, 0)
        rm_container_layout.setSpacing(0)
        self._rom_manager_tab_index = self.main_tabs.addTab(self._rom_manager_container, tr("mw.tabs.rom_manager", "🧰  Rom Manager"))

        self.emulator_tab = EmulatorManagerWidget(self.db, self)
        self.emulator_tab.emulators_changed.connect(self._on_emulators_changed)
        self.main_tabs.addTab(self.emulator_tab, tr("mw.tabs.emulators", "🕹  Manage Emulators"))

        self.frontend_tab = FrontendSettingsWidget(self.db, self)
        self.frontend_tab.layout_changed.connect(self._on_frontend_layout_changed)
        self.frontend_tab.launch_requested.connect(self.launch_frontend_player)
        self.main_tabs.addTab(self.frontend_tab, tr("mw.tabs.frontend", "📺  Frontend Mode"))

        # Carga perezosa de Layout Studio: no instanciar motores pesados hasta abrir la pestaña
        self.layout_studio_tab = None
        self._layout_studio_container = QWidget()
        studio_container_layout = QVBoxLayout(self._layout_studio_container)
        studio_container_layout.setContentsMargins(0, 0, 0, 0)
        studio_container_layout.setSpacing(0)
        self._layout_studio_tab_index = self.main_tabs.addTab(self._layout_studio_container, tr("mw.tabs.layout_studio", "🎨  Layout Studio"))

        self.settings_tab = SystemSettingsWidget(self.db, self)
        self.settings_tab.settings_saved.connect(self._on_settings_saved)
        self.main_tabs.addTab(self.settings_tab, tr("mw.tabs.settings", "⚙  System Settings"))

        version_label = QLabel(f"{__version_full__}  ")
        version_label.setStyleSheet("color: #a78bfa; font-weight: bold; font-size: 9.5pt; padding-right: 12px;")
        self.main_tabs.setCornerWidget(version_label, Qt.TopRightCorner)

        self.main_tabs.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(self.main_tabs)
        self.statusBar().showMessage(tr("mw.status.ready", "PlayNexus ready."))

    # -------------------------------------------------------------
    # GESTIÓN DE LISTAS
    # -------------------------------------------------------------
    def refresh_lists(self, select_id=None):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        rows = self.db.get_lists(with_counts=True)

        for row in rows:
            is_menu = (row["list_type"] == "menu") if "list_type" in row.keys() else False
            is_filtered = (row["list_type"] == "filtered") if "list_type" in row.keys() else False
            if is_menu:
                menu_items = self.db.get_menu_items(row["id"])
                display_text = f"🧭 {row['name']} ({len(menu_items)})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, row["id"])
                item.setToolTip(
                    tr(
                        "mw.list.menu_tip",
                        "🧭 System Menu\nIncluded systems: {count}\nLayout: {layout}",
                        count=len(menu_items), layout=row["layout"],
                    )
                )
            elif is_filtered:
                src_id = row.get("source_list_id")
                unknown_txt = tr("common.unknown", "Unknown")
                src_name = unknown_txt
                if src_id:
                    src_row = self.db.get_list(src_id)
                    if src_row:
                        src_name = src_row.get("name", unknown_txt)
                display_text = f"⚡ {row['name']} ({row['game_count']})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, row["id"])
                item.setToolTip(
                    tr(
                        "mw.list.filtered_tip",
                        "⚡ Filtered List\nSource list: {src}\nMatching games: {count}\nPlatform: {platform}\nLayout: {layout}",
                        src=src_name,
                        count=row["game_count"],
                        platform=row["platform"] or tr("common.undefined", "Undefined"),
                        layout=row["layout"],
                    )
                )
            else:
                display_text = f"{row['name']} ({row['game_count']})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, row["id"])
                folders_list = parse_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "")
                if len(folders_list) > 1:
                    folder_tip = "\n" + tr("mw.list.folders_prefix", "Folders:") + "\n  • " + "\n  • ".join(folders_list)
                elif len(folders_list) == 1:
                    folder_tip = "\n" + tr("mw.list.folder_single", "Folder: {path}", path=folders_list[0])
                else:
                    folder_tip = ""
                xml_tip = f"\nXML: {Path(row['xml_path']).name}" if ("xml_path" in row.keys() and row["xml_path"]) else ""
                item.setToolTip(
                    tr(
                        "mw.list.games_tip",
                        "Platform: {platform}\nExtensions: {exts}\nLayout: {layout}{folder_tip}{xml_tip}",
                        platform=row["platform"] or tr("common.undefined", "Undefined"),
                        exts=row["allowed_extensions"] or tr("mw.list.no_extensions", "No extensions"),
                        layout=row["layout"],
                        folder_tip=folder_tip,
                        xml_tip=xml_tip,
                    )
                )
            self.list_widget.addItem(item)
            # Icono personalizado de la lista (si tiene uno configurado)
            icon_path = row.get("icon_path", "")
            if icon_path and Path(icon_path).is_file():
                item.setIcon(QIcon(icon_path))
            if select_id and row["id"] == select_id:
                self.list_widget.setCurrentItem(item)

        self.list_widget.blockSignals(False)

        if hasattr(self, "frontend_tab"):
            self.frontend_tab.refresh_data()

        if self.list_widget.count() > 0 and self.list_widget.currentRow() < 0:
            self.list_widget.setCurrentRow(0)

        current = self.list_widget.currentItem()
        if current:
            self.on_list_changed(current)
        else:
            self.current_list_id = None
            self.list_title.setText(tr("mw.list.empty_title", "No lists created"))
            self.list_meta_label.setText(tr("mw.list.empty_meta", "Create a list to get started."))
            self.refresh_games()

        if getattr(self, "rom_manager_tab", None) is not None and self.main_tabs.currentIndex() == 0:
            self._pending_rom_manager_refresh = True
            self._pending_rom_manager_list_id = self.current_list_id

    def on_list_changed(self, current, previous=None):
        if not current:
            return
        self.current_list_id = current.data(Qt.UserRole)
        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        is_menu = (row["list_type"] == "menu") if "list_type" in row.keys() else False
        is_filtered = (row["list_type"] == "filtered") if "list_type" in row.keys() else False
        if is_menu:
            menu_items = self.db.get_menu_items(self.current_list_id)
            self.list_title.setText(f"🧭 {row['name']}")
            self.list_meta_label.setText(
                tr(
                    "mw.list.menu_meta",
                    "🧭 <b>System Menu</b> · {count} linked system(s) · Layout: <b>{layout}</b>",
                    count=len(menu_items), layout=row["layout"],
                )
            )
        elif is_filtered:
            try:
                sync_filtered_list_games(self.db, self.current_list_id)
            except Exception:
                pass
            src_id = row.get("source_list_id")
            unknown_txt = tr("common.unknown", "Unknown")
            src_name = unknown_txt
            if src_id:
                src_row = self.db.get_list(src_id)
                if src_row:
                    src_name = src_row.get("name", unknown_txt)
            self.list_title.setText(f"⚡ {row['name']}")
            g_count = self.db.count_games(self.current_list_id)
            current.setText(f"⚡ {row['name']} ({g_count})")
            plat_text = tr("mw.list.meta_platform", " · Platform: {platform}", platform=row["platform"]) if row["platform"] else ""
            self.list_meta_label.setText(
                tr(
                    "mw.list.filtered_meta",
                    "⚡ <b>Filtered List</b> · Source: <b>{src}</b> · {count} matching game(s){plat} · Layout: <b>{layout}</b>",
                    src=src_name, count=g_count, plat=plat_text, layout=row["layout"],
                )
            )
        else:
            self.list_title.setText(row["name"])
            exts_text = row["allowed_extensions"] or tr("common.not_configured", "Not configured")
            plat_text = tr("mw.list.meta_platform", " · Platform: {platform}", platform=row["platform"]) if row["platform"] else ""
            folders_list = parse_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "")
            if len(folders_list) > 1:
                folder_text = tr(
                    "mw.list.meta_folders_multi",
                    " · Folders ({count}): {first} (+{more} more)",
                    count=len(folders_list), first=folders_list[0], more=len(folders_list) - 1,
                )
            elif len(folders_list) == 1:
                folder_text = tr("mw.list.meta_folder_single", " · Folder: {path}", path=folders_list[0])
            else:
                folder_text = ""
            xml_text = f" · XML: <b>{Path(row['xml_path']).name}</b>" if ("xml_path" in row.keys() and row["xml_path"]) else ""
            self.list_meta_label.setText(
                tr(
                    "mw.list.games_meta",
                    "Supported extensions: <b>{exts}</b>{plat}{folders}{xml}",
                    exts=exts_text, plat=plat_text, folders=folder_text, xml=xml_text,
                )
            )

        # Sincronizar combo de layout y resetear selección previa
        layout_name = row["layout"] or "Grid"
        self.layout_combo.blockSignals(True)
        self.layout_combo.setCurrentText(layout_name)
        self.layout_combo.blockSignals(False)

        # 1. Resetear selección y cache de la lista anterior
        self.current_game_id = None
        self.games_cache = []

        # 2. Aplicar vista del layout (sin renderizar dos veces)
        self._apply_layout_view(layout_name, render=False)

        # 3. Refrescar juegos y sincronizar la selección con el primer elemento
        self.refresh_games()

    def create_list(self):
        emulators = self.db.get_emulators()
        all_lists = self.db.get_lists(with_counts=False)
        dialog = ListDialog(emulators, self, all_lists=all_lists, db=self.db)
        if dialog.exec():
            vals = dialog.values()
            name, platform, emu_id, layout, exts, folder, auto_scan, media_path, boxart_path, wheel_path, video_path, cartart_path, list_type, selected_list_ids = vals[:14]
            cabinet_path = vals[14] if len(vals) > 14 else ""
            marquee_path = vals[15] if len(vals) > 15 else ""
            xml_path = vals[16] if len(vals) > 16 else ""
            bezel_path = vals[17] if len(vals) > 17 else ""
            scan_subfolders = vals[18] if len(vals) > 18 else True
            exclude_folder_if_zip = vals[19] if len(vals) > 19 else False
            source_list_id = vals[20] if len(vals) > 20 else None
            filter_rules = vals[21] if len(vals) > 21 else "[]"
            filter_match_mode = vals[22] if len(vals) > 22 else "all"
            flyer_path = vals[23] if len(vals) > 23 else ""
            icon_path = vals[24] if len(vals) > 24 else ""
            bezel_hud_enabled = vals[25] if len(vals) > 25 else "true"
            bezel_hud_path = vals[26] if len(vals) > 26 else ""
            loading_path = vals[27] if len(vals) > 27 else ""
            manual_path = vals[29] if len(vals) > 29 else ""
            try:
                list_id = self.db.add_list(
                    name=name,
                    platform=platform,
                    default_emulator_id=emu_id,
                    layout=layout,
                    allowed_extensions=exts,
                    roms_path=folder,
                    scan_subfolders=str(scan_subfolders).lower(),
                    exclude_folder_if_zip=str(exclude_folder_if_zip).lower(),
                    media_path=media_path,
                    boxart_path=boxart_path,
                    flyer_path=flyer_path,
                    wheel_path=wheel_path,
                    video_path=video_path,
                    cartart_path=cartart_path,
                    cabinet_path=cabinet_path,
                    marquee_path=marquee_path,
                    bezel_path=bezel_path,
                    manual_path=manual_path,
                    list_type=list_type,
                    xml_path=xml_path,
                    source_list_id=source_list_id,
                    filter_rules=filter_rules,
                    filter_match_mode=filter_match_mode,
                    sort_mode=dialog.selected_sort_mode(),
                    icon_path=icon_path,
                    bezel_hud_enabled=str(bezel_hud_enabled).lower(),
                    bezel_hud_path=bezel_hud_path,
                    loading_path=loading_path,
                )
                clear_media_cache()
                if list_type == "menu":
                    self.db.set_menu_items(list_id, selected_list_ids)
                    self.refresh_lists(select_id=list_id)
                    self.statusBar().showMessage(
                        tr("mw.list.menu_created", "Menu '{name}' created successfully with {count} systems.", name=name, count=len(selected_list_ids)),
                        4000,
                    )
                    return
                elif list_type == "filtered":
                    synced = sync_filtered_list_games(self.db, list_id)
                    self.refresh_lists(select_id=list_id)
                    self.statusBar().showMessage(
                        tr("mw.list.filtered_created", "Filtered list '{name}' created with {count} matching game(s).", name=name, count=synced),
                        5000,
                    )
                    return

                self.refresh_lists(select_id=list_id)

                rom_folders = [f for f in parse_rom_folders(folder) if Path(f).is_dir()]
                if list_type == "games" and rom_folders and auto_scan:
                    progress_dlg = ScanProgressDialog(
                        parent=self,
                        db=self.db,
                        list_id=list_id,
                        list_name=name,
                        rom_folders=rom_folders,
                        exts=exts,
                        scan_subfolders=scan_subfolders,
                        exclude_folder_if_zip=exclude_folder_if_zip,
                        xml_path=xml_path,
                        replace=True,
                        filter_rules=filter_rules,
                        filter_match_mode=filter_match_mode,
                    )
                    progress_dlg.exec()
                    self.refresh_lists(select_id=list_id)
                    if progress_dlg.stats:
                        self.statusBar().showMessage(
                            tr("mw.list.created_scanned", "List '{name}' created with {count} imported game(s).", name=name, count=progress_dlg.stats["added"]),
                            5000,
                        )
                    elif progress_dlg.error_msg:
                        QMessageBox.warning(
                            self,
                            tr("mw.scan.warning_title", "Scan Warning"),
                            tr("mw.list.create_scan_err", "The list was created, but an error occurred while scanning folders:\n{err}", err=progress_dlg.error_msg),
                        )
                else:
                    msg = tr("mw.list.created", "List '{name}' created successfully.", name=name)
                    self.statusBar().showMessage(msg, 4000)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("mw.list.create_err_title", "Could Not Create List"),
                    tr("mw.list.save_err_msg", "Error while saving:\n{err}", err=e),
                )

    def edit_current_list(self):
        if not self.current_list_id:
            QMessageBox.information(
                self,
                tr("common.select", "Select"),
                tr("mw.list.select_to_edit", "Select a list to edit."),
            )
            return
        self._edit_list_by_id(self.current_list_id, from_rom_manager=False)

    def _finish_edit_list_refresh(self, edited_list_id: int, from_rom_manager: bool):
        self.refresh_lists(select_id=self.current_list_id)
        if from_rom_manager and self.main_tabs.currentIndex() != 0:
            self._stop_library_layouts_media()
            if getattr(self, "rom_manager_tab", None):
                self.rom_manager_tab.refresh_sources(select_list_id=edited_list_id, auto_scan=True)

    def _edit_list_by_id(self, list_id: int, from_rom_manager: bool = False):
        row = self.db.get_list(list_id)
        if not row:
            return

        emulators = self.db.get_emulators()
        all_lists = self.db.get_lists(with_counts=False)
        initial_menu_items = self.db.get_menu_items(list_id)
        dialog = ListDialog(emulators, self, existing=row, all_lists=all_lists, initial_menu_items=initial_menu_items, db=self.db)
        if dialog.exec():
            vals = dialog.values()
            name, platform, emu_id, layout, exts, folder, auto_scan, media_path, boxart_path, wheel_path, video_path, cartart_path, list_type, selected_list_ids = vals[:14]
            cabinet_path = vals[14] if len(vals) > 14 else ""
            marquee_path = vals[15] if len(vals) > 15 else ""
            xml_path = vals[16] if len(vals) > 16 else ""
            bezel_path = vals[17] if len(vals) > 17 else ""
            scan_subfolders = vals[18] if len(vals) > 18 else True
            exclude_folder_if_zip = vals[19] if len(vals) > 19 else False
            source_list_id = vals[20] if len(vals) > 20 else None
            filter_rules = vals[21] if len(vals) > 21 else "[]"
            filter_match_mode = vals[22] if len(vals) > 22 else "all"
            flyer_path = vals[23] if len(vals) > 23 else ""
            icon_path = vals[24] if len(vals) > 24 else ""
            bezel_hud_enabled = vals[25] if len(vals) > 25 else "true"
            bezel_hud_path = vals[26] if len(vals) > 26 else ""
            loading_path = vals[27] if len(vals) > 27 else ""
            manual_path = vals[29] if len(vals) > 29 else ""
            old_roms_path = format_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "")
            old_exts = (row["allowed_extensions"] if "allowed_extensions" in row.keys() else "") or ""
            old_scan_sub = str(row.get("scan_subfolders", "true")).strip().lower() in ("true", "1")
            old_excl_zip = str(row.get("exclude_folder_if_zip", "false")).strip().lower() in ("true", "1")
            old_filter_rules = str(row.get("filter_rules", "[]"))
            old_match_mode = str(row.get("filter_match_mode", "all"))
            folders_changed = (
                format_rom_folders(folder) != old_roms_path
                or exts != old_exts
                or scan_subfolders != old_scan_sub
                or exclude_folder_if_zip != old_excl_zip
            )
            filters_changed = (
                filter_rules != old_filter_rules
                or filter_match_mode != old_match_mode
            )
            try:
                self.db.update_list(
                    list_id,
                    name=name,
                    platform=platform,
                    default_emulator_id=emu_id,
                    layout=layout,
                    allowed_extensions=exts,
                    roms_path=folder,
                    scan_subfolders=str(scan_subfolders).lower(),
                    exclude_folder_if_zip=str(exclude_folder_if_zip).lower(),
                    media_path=media_path,
                    boxart_path=boxart_path,
                    flyer_path=flyer_path,
                    wheel_path=wheel_path,
                    video_path=video_path,
                    cartart_path=cartart_path,
                    cabinet_path=cabinet_path,
                    marquee_path=marquee_path,
                    bezel_path=bezel_path,
                    manual_path=manual_path,
                    list_type=list_type,
                    xml_path=xml_path,
                    source_list_id=source_list_id,
                    filter_rules=filter_rules,
                    filter_match_mode=filter_match_mode,
                    sort_mode=dialog.selected_sort_mode(),
                    icon_path=icon_path,
                    bezel_hud_enabled=str(bezel_hud_enabled).lower(),
                    bezel_hud_path=bezel_hud_path,
                    loading_path=loading_path,
                )
                clear_media_cache()
                if list_type == "menu":
                    self.db.set_menu_items(list_id, selected_list_ids)
                    self._finish_edit_list_refresh(list_id, from_rom_manager)
                    self.statusBar().showMessage(tr("mw.list.menu_updated", "Menu '{name}' updated.", name=name), 4000)
                    return
                elif list_type == "filtered":
                    synced = sync_filtered_list_games(self.db, list_id)
                    self._finish_edit_list_refresh(list_id, from_rom_manager)
                    self.statusBar().showMessage(
                        tr("mw.list.filtered_synced", "Filtered list '{name}' synced with {count} matching game(s).", name=name, count=synced),
                        5000,
                    )
                    return

                rom_folders = [f for f in parse_rom_folders(folder) if Path(f).is_dir()]
                if list_type == "games" and rom_folders and (auto_scan or folders_changed or filters_changed):
                    progress_dlg = ScanProgressDialog(
                        parent=self,
                        db=self.db,
                        list_id=list_id,
                        list_name=name,
                        rom_folders=rom_folders,
                        exts=exts,
                        scan_subfolders=scan_subfolders,
                        exclude_folder_if_zip=exclude_folder_if_zip,
                        xml_path=xml_path,
                        replace=True,
                        filter_rules=filter_rules,
                        filter_match_mode=filter_match_mode,
                    )
                    progress_dlg.exec()
                    self._finish_edit_list_refresh(list_id, from_rom_manager)
                    if progress_dlg.stats:
                        self.statusBar().showMessage(
                            tr("mw.list.updated_count", "List '{name}' updated with {count} game(s).", name=name, count=progress_dlg.stats["added"]),
                            5000,
                        )
                    elif progress_dlg.error_msg:
                        QMessageBox.warning(
                            self,
                            tr("mw.scan.warning_title", "Scan Warning"),
                            tr("mw.list.update_scan_err", "The list was updated, but an error occurred while scanning folders:\n{err}", err=progress_dlg.error_msg),
                        )
                elif list_type == "games" and not rom_folders and (auto_scan or folders_changed):
                    self.db.clear_list_games(list_id)
                    self._finish_edit_list_refresh(list_id, from_rom_manager)
                    self.statusBar().showMessage(
                        tr("mw.list.updated_no_folders", "List '{name}' updated (no ROM folders).", name=name),
                        4000,
                    )
                else:
                    self._finish_edit_list_refresh(list_id, from_rom_manager)
                    self.statusBar().showMessage(tr("mw.list.updated", "List '{name}' updated.", name=name), 4000)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("mw.list.update_err_title", "Could Not Update List"),
                    tr("mw.list.update_err_msg", "Error while updating:\n{err}", err=e),
                )

    def sync_xml_for_current_list(self):
        """Permite seleccionar y vincular un archivo XML a la lista actual (se usará al escanear ROMs)."""
        if not self.current_list_id:
            return
        row = self.db.get_list(self.current_list_id)
        if not row or ("list_type" in row.keys() and row["list_type"] == "menu"):
            return

        current_xml = row["xml_path"] if ("xml_path" in row.keys() and row["xml_path"]) else ""
        folders_list = parse_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "")
        first_folder = folders_list[0] if folders_list else ""
        initial_dir = str(Path(current_xml).parent) if (current_xml and Path(current_xml).parent.is_dir()) else first_folder
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("mw.xml.pick_title", "Select XML file for '{name}'", name=row["name"]),
            initial_dir or "",
            tr("mw.xml.file_filter", "XML / DAT Files (*.xml *.dat);;All Files (*.*)"),
        )
        if not path:
            return

        try:
            self.db.update_list(self.current_list_id, xml_path=path)
            self.refresh_lists(select_id=self.current_list_id)
            xml_name = Path(path).name
            QMessageBox.information(
                self,
                tr("mw.xml.applied_title", "XML Linked"),
                tr(
                    "mw.xml.applied_msg",
                    "The XML file was linked to list '{name}'.\n\nFile: {xml_name}\n\nIt will be read and applied automatically when scanning ROMs.",
                    name=row["name"], xml_name=xml_name,
                ),
            )
            self.statusBar().showMessage(
                tr("mw.xml.synced_status", "XML linked: {xml_name} (will apply on ROM scan).", xml_name=xml_name),
                4000,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("mw.xml.err_title", "XML Error"),
                tr("mw.xml.err_msg", "Could not link the XML file:\n{err}", err=e),
            )

    def delete_current_list(self):
        if not self.current_list_id:
            QMessageBox.information(
                self,
                tr("common.select", "Select"),
                tr("mw.list.select_to_delete", "Select a list to delete."),
            )
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        count = self.db.count_games(self.current_list_id)
        answer = QMessageBox.question(
            self,
            tr("mw.list.delete_title", "Delete List"),
            tr(
                "mw.list.delete_confirm",
                "Are you sure you want to delete the list '{name}'?\n"
                "The {count} games registered in this list will be unlinked (files on disk will NOT be deleted).",
                name=row["name"], count=count,
            ),
            QMessageBox.Yes | QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            try:
                self.db.delete_list(self.current_list_id)
                self.refresh_lists()
                self.statusBar().showMessage(tr("mw.list.deleted", "List deleted."), 3000)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("common.error", "Error"),
                    tr("mw.list.delete_err_msg", "Could not delete the list:\n{err}", err=e),
                )

    def sync_filtered_list(self):
        """Re-ejecuta los filtros de la lista filtrada actual contra su lista origen."""
        if not self.current_list_id:
            return
        row = self.db.get_list(self.current_list_id)
        if not row or row.get("list_type") != "filtered":
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            count = sync_filtered_list_games(self.db, self.current_list_id)
            QApplication.restoreOverrideCursor()
            self.refresh_lists(select_id=self.current_list_id)
            self.statusBar().showMessage(
                tr("mw.list.filtered_synced_status", "Filtered list '{name}' synced: {count} matching game(s).", name=row["name"], count=count),
                5000,
            )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self,
                tr("mw.list.sync_err_title", "Sync Error"),
                tr("mw.list.sync_err_msg", "Could not sync filtered list:\n{err}", err=e),
            )

    def _show_list_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        lid = item.data(Qt.UserRole)
        row = self.db.get_list(lid)
        if not row:
            return

        is_menu = (row.get("list_type") == "menu")
        is_filtered = (row.get("list_type") == "filtered")

        menu = QMenu(self)
        sync_filt_act = None
        scan_act = None
        add_act = None
        xml_act = None

        if is_filtered:
            sync_filt_act = menu.addAction(tr("mw.list_ctx.sync_filtered", "⚡ Sync with source list…"))
        elif not is_menu:
            scan_act = menu.addAction(tr("mw.list_ctx.scan", "▣ Scan folder…"))
            add_act = menu.addAction(tr("mw.list_ctx.add_files", "＋ Add files…"))
            xml_act = menu.addAction(tr("mw.list_ctx.sync_xml", "📄 Link XML…"))

        menu.addSeparator()
        rom_mgr_act = menu.addAction(tr("mw.list_ctx.audit_rom_mgr", "🧰 Audit media in Rom Manager…"))
        edit_act = menu.addAction(tr("mw.list_ctx.edit", "✎ Edit list…"))
        del_act = menu.addAction(tr("mw.list_ctx.delete", "🗑 Delete list"))

        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == sync_filt_act:
            self.sync_filtered_list()
        elif action == scan_act:
            self.scan_folder()
        elif action == add_act:
            self.add_files()
        elif action == xml_act:
            self.sync_xml_for_current_list()
        elif action == rom_mgr_act:
            self.open_rom_manager_for_list(lid)
        elif action == edit_act:
            self.edit_current_list()
        elif action == del_act:
            self.delete_current_list()

    # -------------------------------------------------------------
    # DISEÑOS VISUALES (LAYOUTS)
    # -------------------------------------------------------------
    def _on_layout_sound_toggled(self, checked: bool):
        self.sound_checkbox.setText(tr("mw.center.sound_on", "🔊 Sound") if checked else tr("mw.center.sound_off", "🔇 Sound"))
        self.db.set_setting("layout_preview_sound", "true" if checked else "false")
        muted = not checked
        for inst in list(getattr(self, "active_layouts", {}).values()):
            if hasattr(inst, "set_media_muted") and callable(inst.set_media_muted):
                try:
                    inst.set_media_muted(muted)
                except Exception:
                    pass
        cur = self.layout_stack.currentWidget()
        if cur:
            if hasattr(cur, "set_media_muted") and callable(cur.set_media_muted):
                try:
                    cur.set_media_muted(muted)
                except Exception:
                    pass
            # Restaurar el foco inmediatamente para que la rueda de juegos y el layout sigan respondiendo al teclado
            if hasattr(cur, "wheel_list") and cur.wheel_list:
                cur.wheel_list.setFocus()
            else:
                cur.setFocus()

    def _sync_layout_sound(self, inst):
        """Aplica el estado actual de silencio/sonido a la instancia del layout."""
        if hasattr(self, "sound_checkbox"):
            muted = not self.sound_checkbox.isChecked()
            if hasattr(inst, "set_media_muted") and callable(inst.set_media_muted):
                try:
                    inst.set_media_muted(muted)
                except Exception:
                    pass

    def save_layout(self, layout):
        self._apply_layout_view(layout)
        if self.current_list_id:
            self.db.update_list(self.current_list_id, layout=layout)
            if hasattr(self, "frontend_tab"):
                self.frontend_tab.refresh_data()
            self.statusBar().showMessage(tr("mw.layout.saved", "Layout saved: {layout}", layout=layout), 2500)

    def _get_or_create_layout(self, layout_name: str):
        """Obtiene una instancia del layout o la crea dinámicamente si es un tema de sistema."""
        if layout_name in self.active_layouts:
            return self.active_layouts[layout_name]

        inst = create_layout(layout_name)
        inst.db = self.db
        from playnexus.services.themes import get_theme_info
        info = get_theme_info(layout_name)
        if info and info.get("folder"):
            py_file = Path(info["folder"]) / "theme_layout.py"
            if py_file.is_file():
                try:
                    inst._loaded_mtime = py_file.stat().st_mtime
                except Exception:
                    pass
        inst.game_selected.connect(self._select_game_by_id)
        inst.game_activated.connect(self._on_game_activated)
        inst.context_menu_requested.connect(self._on_game_context_menu)
        self._sync_layout_sound(inst)
        self.active_layouts[layout_name] = inst
        self.layout_stack.addWidget(inst)
        return inst

    def _apply_layout_view(self, layout, render: bool = True):
        available = get_available_layouts()
        if layout in available:
            target = layout
        else:
            resolved = resolve_theme_name(layout)
            target = resolved if (resolved and resolved in available) else "Grid"
        # Detener multimedia de todos los layouts activos para evitar audio residual
        self.stop_all_active_media()
        inst = self._get_or_create_layout(target)
        inst.db = self.db
        self._sync_layout_sound(inst)
        self.layout_stack.setCurrentWidget(inst)
        if not render:
            inst.setFocus()
            return
        inst.set_games(self.games_cache)
        matching_ids = {g["id"] for g in self.games_cache} if self.games_cache else set()
        if self.current_game_id and self.current_game_id in matching_ids:
            inst.select_game_by_id(self.current_game_id)
            self._select_game_by_id(self.current_game_id)
        elif hasattr(inst, "get_selected_game_id") and inst.get_selected_game_id():
            cand_id = inst.get_selected_game_id()
            if cand_id in matching_ids:
                self._select_game_by_id(cand_id)
            else:
                self.on_game_unselected()
        else:
            self.on_game_unselected()
        inst.setFocus()

    # -------------------------------------------------------------
    # GESTIÓN Y CARGA DE JUEGOS
    # -------------------------------------------------------------
    def refresh_games(self):
        if not self.current_list_id:
            self.games_cache = []
            self._render_games()
            self.on_game_unselected()
            return

        row_list = self.db.get_list(self.current_list_id)
        term = self.search.text().strip().lower()

        if row_list and ("list_type" in row_list.keys() and row_list["list_type"] == "menu"):
            menu_media_path = row_list["media_path"] if "media_path" in row_list.keys() else ""
            menu_boxart_path = row_list["boxart_path"] if "boxart_path" in row_list.keys() else ""
            menu_flyer_path = row_list.get("flyer_path", "")
            menu_wheel_path = row_list["wheel_path"] if "wheel_path" in row_list.keys() else ""
            menu_video_path = row_list["video_path"] if "video_path" in row_list.keys() else ""
            menu_cartart_path = row_list["cartart_path"] if "cartart_path" in row_list.keys() else ""
            menu_cabinet_path = row_list.get("cabinet_path", "")
            menu_marquee_path = row_list.get("marquee_path", "")
            menu_bezel_path = row_list.get("bezel_path", "")

            targets = self.db.get_menu_items(self.current_list_id)
            items = []
            for t in targets:
                t_dict = dict(t)
                title = t_dict["name"]
                platform = t_dict["platform"] or title
                if term and (term not in title.lower() and term not in platform.lower()):
                    continue
                g_count = self.db.count_games(t_dict["id"])
                items.append({
                    "id": t_dict["id"],
                    "target_list_id": t_dict["id"],
                    "is_menu_target": True,
                    "title": title,
                    "rom_path": "",
                    "list_id": self.current_list_id,
                    "platform": platform,
                    "media_path": menu_media_path,
                    "boxart_path": menu_boxart_path,
                    "flyer_path": menu_flyer_path,
                    "wheel_path": menu_wheel_path,
                    "video_path": menu_video_path,
                    "cartart_path": menu_cartart_path,
                    "cabinet_path": menu_cabinet_path,
                    "marquee_path": menu_marquee_path,
                    "bezel_path": menu_bezel_path,
                    "menu_media_path": menu_media_path,
                    "menu_wheel_path": menu_wheel_path,
                    "menu_video_path": menu_video_path,
                    "menu_boxart_path": menu_boxart_path,
                    "menu_cartart_path": menu_cartart_path,
                    "effective_name": tr("mw.count.games_simple", "{count} games", count=g_count),
                    "source": "menu",
                    "icon_path": t_dict.get("icon_path", ""),
                })
            self.games_cache = items
            self._render_games()
            return

        rows = self.db.get_games(self.current_list_id, search_term=term, enriched=True)
        self.games_cache = [enrich_game_dict(r) for r in rows]
        self._render_games()

    def filter_games(self):
        self.refresh_games()

    def _render_games(self):
        count = len(self.games_cache)
        current_list = self.db.get_list(self.current_list_id) if self.current_list_id else None
        if current_list and ("list_type" in current_list.keys() and current_list["list_type"] == "menu"):
            key = "mw.count.system_singular" if count == 1 else "mw.count.system_plural"
            fallback = "{count} system" if count == 1 else "{count} systems"
            self.game_count_label.setText(tr(key, fallback, count=count))
        else:
            key = "mw.count.game_singular" if count == 1 else "mw.count.game_plural"
            fallback = "{count} game" if count == 1 else "{count} games"
            self.game_count_label.setText(tr(key, fallback, count=count))

        matching_ids = {g["id"] for g in self.games_cache} if self.games_cache else set()
        if not self.current_game_id or self.current_game_id not in matching_ids:
            if self.games_cache:
                self.current_game_id = self.games_cache[0]["id"]
            else:
                self.current_game_id = None

        current_layout = self.layout_stack.currentWidget()
        if current_layout:
            current_layout.set_games(self.games_cache)
            if self.current_game_id:
                if current_layout.get_selected_game_id() != self.current_game_id:
                    current_layout.select_game_by_id(self.current_game_id)
                else:
                    self._select_game_by_id(self.current_game_id)
            elif hasattr(current_layout, "get_selected_game_id") and current_layout.get_selected_game_id():
                cand_id = current_layout.get_selected_game_id()
                if cand_id in matching_ids:
                    self._select_game_by_id(cand_id)
                else:
                    self.on_game_unselected()
            else:
                self.on_game_unselected()

    def _on_game_activated(self, game_id: int):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            return

        # Anti doble activación: aplica también a menús para que un doble clic sobre un
        # sistema no abra la lista y luego ejecute el juego seleccionado en ella.
        import time
        now = time.perf_counter()
        last = getattr(self, "_last_activation_time", 0.0)
        window = max(0.6, QApplication.doubleClickInterval() / 1000.0 + 0.2)
        if last and (now - last < window):
            return
        self._last_activation_time = now

        self._select_game_by_id(game_id)
        selected_item = next((g for g in self.games_cache if g["id"] == game_id), None)
        if selected_item and selected_item.get("is_menu_target"):
            target_id = selected_item["target_list_id"]
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(Qt.UserRole) == target_id:
                    self.list_widget.setCurrentItem(item)
                    break
            return
        self.launch_selected()

    def _on_game_context_menu(self, game_id: int, global_pos: QPoint):
        self._select_game_by_id(game_id)
        selected_item = next((g for g in self.games_cache if g["id"] == game_id), None)
        if selected_item and selected_item.get("is_menu_target"):
            menu = QMenu(self)
            open_act = menu.addAction(tr("mw.game_ctx.open_system", "📂 Open system list"))
            edit_act = menu.addAction(tr("mw.game_ctx.edit_system", "✎ Edit system…"))
            action = menu.exec(global_pos)
            if action == open_act:
                self._on_game_activated(game_id)
            elif action == edit_act:
                target_id = selected_item["target_list_id"]
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    if item.data(Qt.UserRole) == target_id:
                        self.list_widget.setCurrentItem(item)
                        self.edit_current_list()
                        break
            return

        game_row_ctx = self.db.get_game(game_id) or selected_item
        is_fav = bool(int((game_row_ctx or {}).get("is_favorite") or 0))
        list_row_ctx = self.db.get_list(self.current_list_id) if self.current_list_id else None
        from playnexus.services.media import resolve_game_manual_pdf
        manual_ctx = resolve_game_manual_pdf(game_row_ctx, list_row=list_row_ctx) if game_row_ctx else ""

        menu = QMenu(self)
        play_act = menu.addAction(tr("mw.game_ctx.launch", "▶ Launch game"))
        fav_act = menu.addAction(
            tr("mw.game_ctx.fav_remove", "☆ Remove from Favorites")
            if is_fav
            else tr("mw.game_ctx.fav_add", "⭐ Add to Favorites")
        )
        edit_act = menu.addAction(tr("mw.game_ctx.edit_game", "✎ Edit game…"))
        ra_act = menu.addAction(tr("mw.game_ctx.ra", "🏆 RetroAchievements…"))
        manual_act = menu.addAction(tr("mw.game_ctx.manual", "📖 View PDF Manual…")) if manual_ctx else None
        loc_act = menu.addAction(tr("mw.game_ctx.open_loc", "📂 Open file location"))
        menu.addSeparator()
        del_act = menu.addAction(tr("mw.game_ctx.remove", "🗑 Remove from library"))

        action = menu.exec(global_pos)
        if action == play_act:
            self.launch_selected()
        elif action == fav_act:
            self.toggle_selected_favorite()
        elif action == edit_act:
            self.edit_selected_game()
        elif action == ra_act:
            self._open_selected_game_ra()
        elif manual_act and action == manual_act:
            self._open_selected_game_manual()
        elif action == loc_act:
            self.open_rom_location()
        elif action == del_act:
            self.remove_game()

    def _select_game_by_id(self, game_id: int):
        self.current_game_id = game_id
        current_layout = self.layout_stack.currentWidget()
        if current_layout and current_layout.get_selected_game_id() != game_id:
            current_layout.select_game_by_id(game_id)

        selected_item = next((g for g in self.games_cache if g["id"] == game_id), None)
        if not selected_item:
            self.on_game_unselected()
            return

        if selected_item.get("is_menu_target"):
            self.game_name.setText(f"🧭 {selected_item['title']}")
            self.game_rom_code.setText("—")
            self.game_meta_info.setText("—")
            self.game_meta_info.setToolTip("")
            self.game_tags_label.setText("—")
            self.game_stats_label.setText("—")
            self.fav_toggle_btn.setEnabled(False)
            self.fav_toggle_btn.setText(tr("mw.details.fav_menu_na", "☆  Favorite (not applicable to menu)"))
            self.fav_toggle_btn.setStyleSheet("")
            self.game_path.setText(tr("mw.details.platform_val", "Platform: {platform}", platform=selected_item["platform"]))
            self.game_size.setText(tr("mw.details.linked_system", "Linked system ({info})", info=selected_item.get("effective_name", "")))
            self.override_combo.blockSignals(True)
            self.override_combo.setCurrentIndex(0)
            self.override_combo.blockSignals(False)
            self._refresh_selected_game_extras(None)
            return

        game_row = self.db.get_game(game_id)
        if not game_row:
            self.on_game_unselected()
            return

        game = enrich_game_dict(game_row)
        is_fav = bool(int(game.get("is_favorite") or 0))
        self.game_name.setText(f"⭐ {game['title']}" if is_fav else game["title"])
        self.game_path.setText(game["rom_path"])
        tags_txt = str(game.get("tags") or "").strip()
        self.game_tags_label.setText(tags_txt or "—")
        plays_n = int(game.get("play_count") or 0)
        time_txt = format_play_time(game.get("play_time_seconds") or 0)
        last_txt = str(game.get("last_played") or "").strip() or tr("common.never", "Never")
        self.game_stats_label.setText(
            tr("mw.details.stats_fmt", "{plays} plays · {time} · Last: {last}", plays=plays_n, time=time_txt, last=last_txt)
        )
        self._apply_fav_button_style(is_fav)

        rom_p = Path(game["rom_path"])
        rom_code = game.get("rom_name") or rom_p.stem
        self.game_rom_code.setText(rom_code)

        # Mostrar propiedades del XML si están disponibles
        meta_parts = []
        if game.get("year"):
            meta_parts.append(tr("mw.details.meta_year", "<b>Year:</b> {val}", val=game["year"]))
        if game.get("manufacturer"):
            meta_parts.append(tr("mw.details.meta_manufacturer", "<b>Manufacturer:</b> {val}", val=game["manufacturer"]))
        if game.get("genre"):
            meta_parts.append(tr("mw.details.meta_genre", "<b>Genre:</b> {val}", val=game["genre"]))
        if game.get("players"):
            meta_parts.append(tr("mw.details.meta_players", "<b>Players:</b> {val}", val=game["players"]))
        if game.get("cloneof"):
            meta_parts.append(tr("mw.details.meta_cloneof", "<b>Clone of:</b> {val}", val=game["cloneof"]))
        if game.get("rating"):
            meta_parts.append(tr("mw.details.meta_rating", "<b>Rating:</b> {val}", val=game["rating"]))
        if game.get("crc"):
            meta_parts.append(tr("mw.details.meta_crc", "<b>CRC:</b> {val}", val=game["crc"]))
        if game.get("sourcefile"):
            meta_parts.append(tr("mw.details.meta_driver", "<b>Driver:</b> {val}", val=game["sourcefile"]))
        if is_game_vertical(game):
            meta_parts.append(tr("mw.details.meta_vertical", "<span style='color: #38bdf8;'><b>Display:</b> Vertical ↕</span>"))

        if meta_parts:
            self.game_meta_info.setText(" · ".join(meta_parts))
            # Construir tooltip con todas las propiedades del XML
            xml_props = game.get("xml_properties") or {}
            if xml_props:
                tip_lines = [f"{k}: {v}" for k, v in sorted(xml_props.items()) if v]
                self.game_meta_info.setToolTip("\n".join(tip_lines))
            else:
                self.game_meta_info.setToolTip("")
        else:
            self.game_meta_info.setText("—")
            self.game_meta_info.setToolTip("")

        if rom_p.exists():
            if rom_p.is_dir():
                self.game_size.setText(tr("mw.details.rom_dir", "ROM Folder (<DIR>)"))
            else:
                size_mb = rom_p.stat().st_size / (1024 * 1024)
                self.game_size.setText(f"{size_mb:.2f} MB ({rom_p.suffix.lower()})")
        else:
            self.game_size.setText(tr("mw.details.not_found_disk", "<span style='color: #ef4444;'>File or folder not found on disk</span>"))

        # Configurar combo de emulador individual
        self.override_combo.blockSignals(True)
        idx = self.override_combo.findData(game["emulator_override_id"])
        self.override_combo.setCurrentIndex(max(idx, 0))
        self.override_combo.blockSignals(False)

        # Configurar combo de Bezel HUD individual
        self.game_bezel_combo.blockSignals(True)
        bezel_mode = game.get("bezel_hud_mode") or ""
        idx_b = self.game_bezel_combo.findData(bezel_mode)
        self.game_bezel_combo.setCurrentIndex(max(idx_b, 0))
        self.game_bezel_combo.blockSignals(False)

        emu, source = resolve_emulator(self.db, game_row)
        if emu:
            source_desc = (
                tr("mw.details.emu_src_game", "assigned to this game")
                if source == "juego"
                else tr("mw.details.emu_src_list", "list default")
            )
            self.effective_emu.setText(f"{emu['name']} ({source_desc})")
            self.effective_emu.setStyleSheet("font-weight: 600; color: #4ade80;")
        else:
            self.effective_emu.setText(tr("mw.details.no_emu", "No emulator assigned"))
            self.effective_emu.setStyleSheet("font-weight: 600; color: #f87171;")
        self._refresh_selected_game_extras(game_id)

    def _apply_fav_button_style(self, is_fav: bool):
        self.fav_toggle_btn.setEnabled(True)
        if is_fav:
            self.fav_toggle_btn.setText(tr("mw.details.fav_active", "⭐  In Favorites (click to remove)"))
            self.fav_toggle_btn.setStyleSheet(
                "QPushButton { background-color: #3f2f12; color: #fbbf24; border: 1px solid #d97706; font-weight: 600; }"
                "QPushButton:hover { background-color: #523d17; }"
            )
        else:
            self.fav_toggle_btn.setText(tr("mw.details.fav_add", "☆  Add to Favorites"))
            self.fav_toggle_btn.setStyleSheet("")

    def _refresh_selected_game_extras(self, game_id: int | None):
        selected_item = next((g for g in self.games_cache if g.get("id") == game_id), None) if game_id else None
        if not game_id or (selected_item and selected_item.get("is_menu_target")):
            self.game_ra_label.setText("—")
            self.ra_detail_btn.setEnabled(False)
            self.game_manual_label.setText("—")
            self.manual_view_btn.setEnabled(False)
            return

        game = self.db.get_game(game_id) or selected_item
        list_row = self.db.get_list(self.current_list_id) if self.current_list_id else None

        from playnexus.services.media import resolve_game_manual_pdf
        from playnexus.services.retroachievements import format_ra_badge_text, get_cached_ra_progress_summary

        ra_sum = get_cached_ra_progress_summary(self.db, game) if game else None
        self.game_ra_label.setText(format_ra_badge_text(ra_sum) if ra_sum else tr("mw.details.ra_unsynced", "Not synced"))
        self.ra_detail_btn.setEnabled(bool(game))

        manual_pdf = resolve_game_manual_pdf(game, list_row=list_row) if game else ""
        if manual_pdf:
            self.game_manual_label.setText(Path(manual_pdf).name)
            self.game_manual_label.setToolTip(manual_pdf)
            self.manual_view_btn.setEnabled(True)
        else:
            self.game_manual_label.setText(tr("mw.details.no_manual", "No PDF manual"))
            self.game_manual_label.setToolTip("")
            self.manual_view_btn.setEnabled(False)

    def _open_selected_game_ra(self):
        if not self.current_game_id:
            return
        selected_item = next((g for g in self.games_cache if g.get("id") == self.current_game_id), None)
        if selected_item and selected_item.get("is_menu_target"):
            return
        game = self.db.get_game(self.current_game_id) or selected_item
        if not game:
            return
        from playnexus.ui.ra_dialogs import RAGameDetailDialog

        list_row = self.db.get_list(self.current_list_id) if self.current_list_id else None
        dlg = RAGameDetailDialog(self.db, game, list_row=list_row, parent=self)
        dlg.progress_updated.connect(lambda _d: self._refresh_selected_game_extras(self.current_game_id))
        dlg.progress_updated.connect(lambda _d: self.refresh_games())
        dlg.exec()

    def _open_selected_game_manual(self):
        if not self.current_game_id:
            return
        selected_item = next((g for g in self.games_cache if g.get("id") == self.current_game_id), None)
        if selected_item and selected_item.get("is_menu_target"):
            return
        game = self.db.get_game(self.current_game_id) or selected_item
        if not game:
            return
        from playnexus.services.media import resolve_game_manual_pdf
        from playnexus.ui.manual_viewer import ManualViewerDialog

        list_row = self.db.get_list(self.current_list_id) if self.current_list_id else None
        pdf = resolve_game_manual_pdf(game, list_row=list_row)
        if not pdf:
            QMessageBox.information(
                self,
                tr("mw.manual.none_title", "No Manual"),
                tr("mw.manual.none_msg", "This game does not have an assigned PDF manual."),
            )
            return
        ManualViewerDialog(pdf, game_title=game.get("title", ""), db=self.db, parent=self).exec()

    def toggle_selected_favorite(self):
        if not self.current_game_id:
            return
        selected_item = next((g for g in self.games_cache if g.get("id") == self.current_game_id), None)
        if selected_item and selected_item.get("is_menu_target"):
            return
        new_state = self.db.toggle_game_favorite(self.current_game_id)
        if new_state is None:
            return
        try:
            sync_filtered_lists_for_source(self.db)
        except Exception:
            pass
        cur_list = self.db.get_list(self.current_list_id) if self.current_list_id else None
        if cur_list and cur_list.get("list_type") == "filtered":
            self.refresh_lists(select_id=self.current_list_id)
        else:
            self._select_game_by_id(self.current_game_id)
        msg = tr("mw.fav.added_status", "⭐ Game added to Favorites.") if new_state else tr("mw.fav.removed_status", "☆ Game removed from Favorites.")
        self.statusBar().showMessage(msg, 3000)

    def _on_telemetry_updated(self, game_id: int):
        """Actualiza detalles visibles tras registrar lanzamiento o cierre de sesión."""
        if not self.db:
            return
        if self.current_game_id == game_id:
            self._select_game_by_id(game_id)

    def on_game_unselected(self):
        self.current_game_id = None
        self.game_name.setText("—")
        self.game_rom_code.setText("—")
        self.game_meta_info.setText("—")
        self.game_meta_info.setToolTip("")
        self.game_tags_label.setText("—")
        self.game_stats_label.setText("—")
        self.fav_toggle_btn.setEnabled(False)
        self.fav_toggle_btn.setText(tr("mw.details.fav_add", "☆  Add to Favorites"))
        self.fav_toggle_btn.setStyleSheet("")
        self.game_path.setText("—")
        self.game_size.setText("—")
        self.effective_emu.setText("—")
        self.override_combo.blockSignals(True)
        self.override_combo.setCurrentIndex(0)
        self.override_combo.blockSignals(False)
        self.game_bezel_combo.blockSignals(True)
        self.game_bezel_combo.setCurrentIndex(0)
        self.game_bezel_combo.blockSignals(False)
        self.game_ra_label.setText("—")
        self.ra_detail_btn.setEnabled(False)
        self.game_manual_label.setText("—")
        self.game_manual_label.setToolTip("")
        self.manual_view_btn.setEnabled(False)

    def save_override(self, index):
        if not self.current_game_id:
            return
        emu_id = self.override_combo.currentData()
        self.db.update_game(self.current_game_id, emulator_override_id=emu_id)
        self.refresh_games()
        self.statusBar().showMessage(tr("mw.details.override_updated", "Custom emulator updated for this game."), 3000)

    def save_game_bezel_hud(self, index):
        if not self.current_game_id:
            return
        mode = self.game_bezel_combo.currentData() or ""
        self.db.update_game(self.current_game_id, bezel_hud_mode=mode)
        self.statusBar().showMessage(tr("mw.details.bezel_updated", "Bezel HUD setting updated for this game."), 3000)

    # -------------------------------------------------------------
    # ESCANEO Y ADICIÓN DE JUEGOS
    # -------------------------------------------------------------
    def scan_folder(self):
        if not self.current_list_id:
            QMessageBox.information(
                self,
                tr("mw.scan.no_list_title", "No List Selected"),
                tr("mw.scan.no_list_msg", "Select or create a list first."),
            )
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        if row.get("list_type") == "filtered":
            answer = QMessageBox.question(
                self,
                tr("mw.scan.filtered_title", "Filtered List"),
                tr(
                    "mw.scan.filtered_msg",
                    "'{name}' is a filtered list linked to a source list.\n"
                    "To update its games, you must sync it with its source.\n\n"
                    "Do you want to sync the games now?",
                    name=row["name"],
                ),
                QMessageBox.Yes | QMessageBox.No
            )
            if answer == QMessageBox.Yes:
                self.sync_filtered_list()
            return

        allowed_str = (row["allowed_extensions"] or "").strip()
        if not allowed_str:
            answer = QMessageBox.question(
                self,
                tr("mw.scan.no_exts_title", "No Extensions Configured"),
                tr(
                    "mw.scan.no_exts_msg",
                    "The list '{name}' does not have file extensions configured yet.\n"
                    "Before scanning, you must specify which extensions to look for.\n\n"
                    "Do you want to edit the list and configure extensions now?",
                    name=row["name"],
                ),
                QMessageBox.Yes | QMessageBox.No
            )
            if answer == QMessageBox.Yes:
                self.edit_current_list()
            return

        configured_folders = [f for f in parse_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "") if Path(f).is_dir()]
        folders_to_scan = []

        if configured_folders:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(tr("mw.scan.folders_title", "Scan Folders — {name}", name=row["name"]))
            folders_bullet = "\n".join(f"• {f}" for f in configured_folders)
            msg_box.setText(
                tr(
                    "mw.scan.folders_prompt",
                    "The list '{name}' has {count} configured ROM folder(s):\n\n{folders}\n\n"
                    "Do you want to scan all configured folders or add a new folder to the list?",
                    name=row["name"], count=len(configured_folders), folders=folders_bullet,
                )
            )
            btn_scan_existing = msg_box.addButton(
                tr("mw.scan.btn_scan_existing", "Scan configured ({count})", count=len(configured_folders)),
                QMessageBox.AcceptRole,
            )
            btn_add_new = msg_box.addButton(tr("mw.scan.btn_add_folder", "＋ Add new folder…"), QMessageBox.ActionRole)
            btn_cancel = msg_box.addButton(tr("common.cancel", "Cancel"), QMessageBox.RejectRole)
            msg_box.setDefaultButton(btn_scan_existing)
            msg_box.exec()

            clicked = msg_box.clickedButton()
            if clicked == btn_cancel:
                return
            elif clicked == btn_scan_existing:
                folders_to_scan = configured_folders
            elif clicked == btn_add_new:
                initial_dir = str(Path(configured_folders[-1]).parent) if Path(configured_folders[-1]).parent.is_dir() else configured_folders[-1]
                new_folder = QFileDialog.getExistingDirectory(
                    self,
                    tr("mw.scan.add_folder_dlg", "Add and scan games folder for '{name}'", name=row["name"]),
                    initial_dir
                )
                if not new_folder:
                    return
                updated_folders = parse_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "")
                if new_folder not in updated_folders:
                    updated_folders.append(new_folder)
                self.db.update_list(
                    self.current_list_id,
                    roms_path=format_rom_folders(updated_folders),
                )
                folders_to_scan = updated_folders
        else:
            folder = QFileDialog.getExistingDirectory(
                self,
                tr("mw.scan.pick_folder_dlg", "Select games folder for '{name}'", name=row["name"]),
                ""
            )
            if not folder:
                return
            self.db.update_list(self.current_list_id, roms_path=folder)
            folders_to_scan = [folder]

        scan_sub = str(row.get("scan_subfolders", "true")).strip().lower() in ("true", "1")
        excl_zip = str(row.get("exclude_folder_if_zip", "false")).strip().lower() in ("true", "1")

        try:
            progress_dlg = ScanProgressDialog(
                parent=self,
                db=self.db,
                list_id=self.current_list_id,
                list_name=row["name"],
                rom_folders=folders_to_scan,
                exts=allowed_str,
                scan_subfolders=scan_sub,
                exclude_folder_if_zip=excl_zip,
                xml_path=row.get("xml_path"),
                replace=True,
                filter_rules=row.get("filter_rules"),
                filter_match_mode=row.get("filter_match_mode", "all"),
            )
            progress_dlg.exec()
            self.refresh_lists(select_id=self.current_list_id)
            if progress_dlg.stats:
                self.statusBar().showMessage(
                    tr("mw.scan.done_status", "Scan finished: {count} game(s) in the list.", count=progress_dlg.stats["added"]),
                    5000
                )
            elif progress_dlg.error_msg:
                QMessageBox.warning(self, tr("mw.scan.error_title", "Scan Error"), progress_dlg.error_msg)
        except Exception as e:
            QMessageBox.critical(self, tr("mw.scan.error_title", "Scan Error"), str(e))

    def add_files(self):
        if not self.current_list_id:
            QMessageBox.information(
                self,
                tr("mw.scan.no_list_title", "No List Selected"),
                tr("mw.scan.no_list_msg", "Select or create a list first."),
            )
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        if row.get("list_type") == "filtered":
            QMessageBox.information(
                self,
                tr("mw.scan.filtered_title", "Filtered List"),
                tr(
                    "mw.add_files.filtered_msg",
                    "'{name}' is a filtered list linked to a source list.\n"
                    "To add games, add them to the source list and then sync this list.",
                    name=row["name"],
                ),
            )
            return

        # Construir filtro de archivos sugerido según extensiones de la lista
        exts_list = parse_extensions_list(row["allowed_extensions"])
        if exts_list:
            filter_exts = " ".join(f"*{e}" for e in exts_list)
            filter_str = tr(
                "mw.add_files.filter_exts",
                "List extensions ({exts});;All files (*.*)",
                exts=filter_exts,
            )
        else:
            filter_str = tr("common.filter_all_files", "All files (*.*)")

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr("mw.add_files.dlg_title", "Add games to '{name}'", name=row["name"]),
            "",
            filter_str
        )
        if not paths:
            return

        xml_map = {}
        if "xml_path" in row.keys() and row["xml_path"] and Path(row["xml_path"]).is_file():
            try:
                xml_map = parse_rom_xml(row["xml_path"])
            except Exception:
                xml_map = {}

        added = 0
        for p in paths:
            res = add_game(self.db, self.current_list_id, p, xml_map=xml_map)
            if res:
                added += 1

        self.refresh_lists(select_id=self.current_list_id)
        self.statusBar().showMessage(
            tr("mw.add_files.done_status", "Files processed. Added to library: {count}", count=added),
            4000,
        )

    def edit_selected_game(self):
        if not self.current_game_id:
            current_layout = self.layout_stack.currentWidget()
            if current_layout and hasattr(current_layout, "get_selected_game_id"):
                selected_id = current_layout.get_selected_game_id()
                if selected_id:
                    self._select_game_by_id(selected_id)
        if not self.current_game_id:
            QMessageBox.information(
                self,
                tr("mw.game.select_title", "Select Game"),
                tr("mw.game.select_edit_msg", "Choose a game to edit its details."),
            )
            return
        game = self.db.get_game(self.current_game_id)
        if not game:
            return
        dialog = GameEditDialog(self.db, game, self)
        if dialog.exec():
            try:
                sync_filtered_lists_for_source(self.db)
            except Exception:
                pass
            self.refresh_lists(select_id=self.current_list_id)
            self._select_game_by_id(game["id"])
            self.statusBar().showMessage(tr("mw.game.updated_status", "Game updated."), 3000)

    def remove_game(self):
        if not self.current_game_id:
            current_layout = self.layout_stack.currentWidget()
            if current_layout and hasattr(current_layout, "get_selected_game_id"):
                selected_id = current_layout.get_selected_game_id()
                if selected_id:
                    self._select_game_by_id(selected_id)
        if not self.current_game_id:
            QMessageBox.information(
                self,
                tr("mw.game.select_title", "Select Game"),
                tr("mw.game.select_from_lib", "Choose a game from the library."),
            )
            return
        game = self.db.get_game(self.current_game_id)
        if not game:
            return
        answer = QMessageBox.question(
            self,
            tr("mw.game.remove_title", "Remove Game"),
            tr(
                "mw.game.remove_confirm",
                "Remove '{title}' from this list?\nThe ROM file on disk will NOT be deleted.",
                title=game["title"],
            ),
            QMessageBox.Yes | QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            self.db.delete_game(self.current_game_id)
            self.refresh_lists(select_id=self.current_list_id)
            self.statusBar().showMessage(tr("mw.game.removed_status", "Game removed from library."), 3000)

    def open_rom_location(self):
        if not self.current_game_id:
            current_layout = self.layout_stack.currentWidget()
            if current_layout and hasattr(current_layout, "get_selected_game_id"):
                selected_id = current_layout.get_selected_game_id()
                if selected_id:
                    self._select_game_by_id(selected_id)
        if not self.current_game_id:
            return
        game = self.db.get_game(self.current_game_id)
        if not game:
            return
        p = Path(game["rom_path"])
        if p.exists():
            subprocess.run(["explorer", f"/select,{str(p.resolve())}"])
        else:
            QMessageBox.warning(
                self,
                tr("common.not_found_title", "Not Found"),
                tr("mw.game.file_missing_msg", "The file does not exist on disk:\n{path}", path=p),
            )

    def _show_game_context_menu(self, pos):
        if not self.current_game_id:
            return
        game_row_ctx = self.db.get_game(self.current_game_id)
        list_row_ctx = self.db.get_list(self.current_list_id) if self.current_list_id else None
        from playnexus.services.media import resolve_game_manual_pdf
        manual_ctx = resolve_game_manual_pdf(game_row_ctx, list_row=list_row_ctx) if game_row_ctx else ""

        menu = QMenu(self)
        play_act = menu.addAction(tr("mw.game_ctx.launch", "▶ Launch game"))
        edit_act = menu.addAction(tr("mw.game_ctx.edit_game", "✎ Edit game…"))
        ra_act = menu.addAction(tr("mw.game_ctx.ra", "🏆 RetroAchievements…"))
        manual_act = menu.addAction(tr("mw.game_ctx.manual", "📖 View PDF Manual…")) if manual_ctx else None
        loc_act = menu.addAction(tr("mw.game_ctx.open_loc", "📂 Open file location"))
        menu.addSeparator()
        del_act = menu.addAction(tr("mw.game_ctx.remove", "🗑 Remove from library"))

        sender = self.sender()
        action = menu.exec(sender.mapToGlobal(pos))
        if action == play_act:
            self.launch_selected()
        elif action == edit_act:
            self.edit_selected_game()
        elif action == ra_act:
            self._open_selected_game_ra()
        elif manual_act and action == manual_act:
            self._open_selected_game_manual()
        elif action == loc_act:
            self.open_rom_location()
        elif action == del_act:
            self.remove_game()

    # -------------------------------------------------------------
    # GESTIÓN DE EMULADORES Y LANZAMIENTO
    # -------------------------------------------------------------
    def refresh_emulators(self):
        emulators = self.db.get_emulators()
        self.override_combo.blockSignals(True)
        self.override_combo.clear()
        self.override_combo.addItem(tr("mw.details.emu_inherit", "Inherit list emulator (default)"), None)
        for emu in emulators:
            self.override_combo.addItem(emu["name"], emu["id"])
        self.override_combo.blockSignals(False)

        if self.current_game_id:
            game = self.db.get_game(self.current_game_id)
            if game:
                idx = self.override_combo.findData(game["emulator_override_id"])
                self.override_combo.blockSignals(True)
                self.override_combo.setCurrentIndex(max(idx, 0))
                self.override_combo.blockSignals(False)

    def manage_emulators(self):
        """Abre directamente la pestaña de Administrar Emuladores."""
        self.main_tabs.setCurrentIndex(1)

    def launch_selected(self, *args):
        if not self.current_game_id:
            QMessageBox.information(
                self,
                tr("mw.game.select_title", "Select Game"),
                tr("mw.game.select_launch_msg", "Choose a game from the library to launch."),
            )
            return

        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            return

        game = self.db.get_game(self.current_game_id)
        if not game:
            return

        active_layout = self.layout_stack.currentWidget()
        try:
            self._was_maximized_before_emu = self.isMaximized()
            self._restore_after_emulator = True
            if active_layout and hasattr(active_layout, "pause_media") and callable(active_layout.pause_media):
                try:
                    active_layout.pause_media()
                except Exception:
                    pass
            result = launch_game(self.db, game, layout=active_layout, parent_window=self)
            if not result or result[0] is None:
                self._restore_after_emulator = False
                if active_layout and hasattr(active_layout, "resume_media") and callable(active_layout.resume_media):
                    try:
                        active_layout.resume_media()
                    except Exception:
                        pass
                return
            name, source = result
            source_desc = (
                tr("mw.launch.src_game", "game custom assignment")
                if source == "juego"
                else tr("mw.launch.src_list", "list default")
            )
            self.statusBar().showMessage(
                tr("mw.launch.starting_status", "Starting with {name} ({source})…", name=name, source=source_desc),
                6000,
            )
            # Ceder pantalla completa/escritorio al emulador minimizando el Configurador
            # para evitar que tape al juego lanzado desde la Biblioteca.
            self.showMinimized()
            EMULATOR_MANAGER.refocus_emulator()
        except Exception as e:
            self._restore_after_emulator = False
            if active_layout and hasattr(active_layout, "resume_media") and callable(active_layout.resume_media):
                try:
                    active_layout.resume_media()
                except Exception:
                    pass
            QMessageBox.critical(self, tr("mw.launch.error_title", "Could Not Launch Game"), str(e))

    def open_system_settings_tab(self):
        """Abre directamente la pestaña de Configuración del Sistema."""
        self.main_tabs.setCurrentWidget(self.settings_tab)

    def open_frontend_tab(self):
        """Abre directamente la pestaña de Modo Frontend."""
        self.main_tabs.setCurrentWidget(self.frontend_tab)

    def _ensure_rom_manager_tab(self):
        if self.rom_manager_tab is None:
            from playnexus.ui.rom_manager_tab import RomManagerWidget
            self.rom_manager_tab = RomManagerWidget(self.db, self._rom_manager_container)
            self.rom_manager_tab.list_updated.connect(self._on_rom_manager_list_updated)
            self.rom_manager_tab.edit_list_requested.connect(self._on_rom_manager_edit_list)
            self.rom_manager_tab.games_metadata_updated.connect(self._on_rom_manager_games_updated)
            self._rom_manager_container.layout().addWidget(self.rom_manager_tab)
        return self.rom_manager_tab

    def open_rom_manager_for_list(self, list_id: int | None = None):
        """Abre la pestaña Rom Manager enfocando una lista específica y lanzando su auditoría."""
        self.main_tabs.setCurrentWidget(self._rom_manager_container)
        rm = self._ensure_rom_manager_tab()
        if list_id is not None:
            rm.focus_list(int(list_id), auto_scan=True)

    def _on_rom_manager_list_updated(self, list_id: int):
        """Sincroniza Biblioteca y Modo Frontend cuando se modifican carpetas/layouts desde Rom Manager."""
        if hasattr(self, "frontend_tab"):
            self.frontend_tab.refresh_data()
        if self.current_list_id == list_id:
            row = self.db.get_list(list_id)
            if row and row.get("layout"):
                target_lay = row["layout"]
                if self.layout_combo.currentText() != target_lay:
                    self.layout_combo.blockSignals(True)
                    self.layout_combo.setCurrentText(target_lay)
                    self.layout_combo.blockSignals(False)
                    self._pending_layout_reload = True

    def _on_rom_manager_edit_list(self, list_id: int):
        self._edit_list_by_id(list_id, from_rom_manager=True)

    def _on_rom_manager_games_updated(self, list_id: int):
        """Refresca datos de biblioteca cuando el scraper o eliminador del Rom Manager modifica juegos de la lista."""
        if hasattr(self, "frontend_tab"):
            self.frontend_tab.refresh_data()
        if self.main_tabs.currentIndex() == 0:
            self.refresh_lists(select_id=self.current_list_id)
        else:
            self._pending_library_lists_refresh = True

    def _on_tab_changed(self, index: int):
        """Mantiene sincronizados los datos al alternar entre pestañas y suspende la multimedia inactiva."""
        current_widget = self.main_tabs.widget(index)
        if current_widget != getattr(self, "_rom_manager_container", None):
            if getattr(self, "rom_manager_tab", None):
                self.rom_manager_tab.stop_media()

        if current_widget == self.main_tabs.widget(0):
            # Asegurar sincronización del layout de la lista actual por si se cambió desde Rom Manager
            if self.current_list_id:
                row = self.db.get_list(self.current_list_id)
                if row and row.get("layout") and self.layout_combo.currentText() != row["layout"]:
                    self.layout_combo.blockSignals(True)
                    self.layout_combo.setCurrentText(row["layout"])
                    self.layout_combo.blockSignals(False)
                    self._apply_layout_view(row["layout"], render=False)

            # Recargar layout si su archivo theme_layout.py fue modificado o guardado mientras estábamos en otra pestaña
            cur_layout_name = self.layout_combo.currentText().strip()
            needs_reload = getattr(self, "_pending_layout_reload", False)
            if cur_layout_name in self.active_layouts:
                from playnexus.services.themes import get_theme_info
                info = get_theme_info(cur_layout_name)
                if info and info.get("folder"):
                    py_file = Path(info["folder"]) / "theme_layout.py"
                    if py_file.is_file():
                        try:
                            file_mtime = py_file.stat().st_mtime
                            inst = self.active_layouts[cur_layout_name]
                            if getattr(inst, "_loaded_mtime", 0.0) != file_mtime:
                                needs_reload = True
                        except Exception:
                            pass
            elif cur_layout_name:
                needs_reload = True

            if needs_reload and cur_layout_name:
                self._pending_layout_reload = False
                self._on_layout_studio_saved(cur_layout_name)

            self.refresh_emulators()
            if getattr(self, "_pending_library_lists_refresh", False):
                self._pending_library_lists_refresh = False
                self.refresh_lists(select_id=self.current_list_id)
            else:
                self.refresh_games()
            cur = self.layout_stack.currentWidget() if hasattr(self, "layout_stack") else None
            if cur and hasattr(cur, "resume_media") and callable(cur.resume_media):
                cur.resume_media()
            elif cur and hasattr(cur, "_update_current_selection") and callable(cur._update_current_selection):
                cur._update_current_selection()
            if self.current_game_id:
                self._select_game_by_id(self.current_game_id)
        else:
            self._stop_library_layouts_media()
            if current_widget == getattr(self, "_rom_manager_container", None):
                first_init = (self.rom_manager_tab is None)
                rm = self._ensure_rom_manager_tab()
                pending_rm = getattr(self, "_pending_rom_manager_refresh", False)
                pending_lid = getattr(self, "_pending_rom_manager_list_id", None)
                self._pending_rom_manager_refresh = False
                self._pending_rom_manager_list_id = None
                if first_init:
                    if self.current_list_id:
                        rm.focus_list(self.current_list_id, auto_scan=True)
                    elif rm.list_combo.currentData():
                        rm.start_scan()
                elif pending_rm:
                    target_lid = (
                        self.current_list_id
                        if (self.current_list_id and self.db.get_list(self.current_list_id))
                        else pending_lid
                    )
                    rm.refresh_sources(select_list_id=target_lid, auto_scan=True)
                else:
                    rm.refresh_sources(auto_scan=False)
            elif current_widget == self.emulator_tab:
                self.emulator_tab.refresh()
            elif current_widget == self.frontend_tab:
                self.frontend_tab.refresh_data()
            elif current_widget == getattr(self, "_layout_studio_container", None):
                if self.layout_studio_tab is None:
                    from playnexus.ui.layout_studio import LayoutStudioWidget
                    self.layout_studio_tab = LayoutStudioWidget(self.db, self._layout_studio_container)
                    self.layout_studio_tab.layout_saved.connect(self._on_layout_studio_saved)
                    self._layout_studio_container.layout().addWidget(self.layout_studio_tab)
                elif not getattr(self.layout_studio_tab, "current_project", None):
                    self.layout_studio_tab.refresh_layouts_list()

    def _on_layout_studio_saved(self, layout_name: str):
        """Invalida la caché del layout y lo recarga de forma segura y sin bloquear la interfaz."""
        try:
            from playnexus.ui.layouts.theme_layout import _THEME_CLASS_CACHE
            _THEME_CLASS_CACHE.clear()

            # Si el usuario NO está en la pestaña 0 (Listas de Juegos), no tocar widgets ni hilos en segundo plano;
            # simplemente marcar como pendiente para que se recargue limpiamente cuando regrese a dicha pestaña.
            if self.main_tabs.currentIndex() != 0:
                self._pending_layout_reload = True
                return

            # Comprobar si la instancia activa ya está actualizada con el mtime del archivo
            matching_keys = [k for k in list(self.active_layouts.keys()) if k.strip().lower() == layout_name.strip().lower()]
            from playnexus.services.themes import get_theme_info
            info = get_theme_info(layout_name)
            target_mtime = None
            if info and info.get("folder"):
                py_file = Path(info["folder"]) / "theme_layout.py"
                if py_file.is_file():
                    try:
                        target_mtime = py_file.stat().st_mtime
                    except Exception:
                        pass

            for k in matching_keys:
                inst = self.active_layouts.get(k)
                if inst and target_mtime is not None and getattr(inst, "_loaded_mtime", 0.0) == target_mtime:
                    # Ya está actualizada con la versión guardada en disco
                    continue

                old_inst = self.active_layouts.pop(k, None)
                if old_inst:
                    try:
                        self.layout_stack.removeWidget(old_inst)
                    except Exception:
                        pass
                    try:
                        if hasattr(old_inst, "cleanup") and callable(old_inst.cleanup):
                            old_inst.cleanup()
                        elif hasattr(old_inst, "close") and callable(old_inst.close):
                            old_inst.close()
                        elif hasattr(old_inst, "stop_media") and callable(old_inst.stop_media):
                            old_inst.stop_media()
                    except Exception:
                        pass
                    # Salvaguarda crítica: asegurar parada garantizada de worker antes de deleteLater
                    if hasattr(old_inst, "_wheel_worker") and old_inst._wheel_worker:
                        try:
                            old_inst._wheel_worker.stop()
                            old_inst._wheel_worker.wait(500)
                        except Exception:
                            pass
                    old_inst.deleteLater()

            # Recrear y enfocar la vista en Listas de Juegos (tab 0)
            cur_layout = self.layout_combo.currentText().strip()
            cur_list_data = self.db.get_list(self.current_list_id) if (self.db and self.current_list_id) else None
            list_layout = (cur_list_data.get("layout", "") if cur_list_data else "").strip().lower()
            if cur_layout.lower() == layout_name.lower() or list_layout == layout_name.lower():
                if layout_name not in self.active_layouts:
                    self._apply_layout_view(layout_name, render=True)
        except Exception as e:
            print(f"[MainWindow] Error en recarga segura de layout '{layout_name}': {e}")

    def _on_frontend_layout_changed(self, list_id: int, layout_name: str):
        """Sincroniza el diseño visual cuando se edita desde la pestaña de Modo Frontend."""
        if self.current_list_id == list_id:
            self.layout_combo.blockSignals(True)
            self.layout_combo.setCurrentText(layout_name)
            self.layout_combo.blockSignals(False)
            self._apply_layout_view(layout_name, render=True)
        self.refresh_lists(select_id=self.current_list_id)

    def launch_frontend_player(self):
        """Lanza el reproductor Frontend a pantalla completa directamente desde el configurador."""
        self.stop_all_active_media()
        if hasattr(self, "gamepad") and self.gamepad:
            self.gamepad.set_enabled(False)
        self.hide()
        from playnexus.ui.player_window import PlayerWindow
        self.player_window = PlayerWindow(parent=None)
        self.player_window.apply_video_settings()

        def _on_player_closed():
            self.show()
            self.raise_()
            self.activateWindow()
            if hasattr(self, "gamepad") and self.gamepad:
                self.gamepad.set_enabled(True)
            try:
                self.refresh_lists(select_id=self.current_list_id)
            except Exception:
                pass

        self.player_window.destroyed.connect(_on_player_closed)
        QTimer.singleShot(0, self.player_window._apply_show)

    def _stop_library_layouts_media(self):
        """Detiene la reproducción activa únicamente de los layouts de la pestaña Biblioteca."""
        for inst in list(getattr(self, "active_layouts", {}).values()):
            if hasattr(inst, "stop_media") and callable(inst.stop_media):
                try:
                    inst.stop_media()
                except Exception:
                    pass
            for audio_attr in ("audio_output", "game_audio"):
                if hasattr(inst, audio_attr):
                    ao = getattr(inst, audio_attr)
                    if ao:
                        try:
                            ao.setMuted(True)
                            ao.setVolume(0.0)
                        except Exception:
                            pass
            for player_attr in ("player", "game_player"):
                if hasattr(inst, player_attr):
                    p = getattr(inst, player_attr)
                    if p:
                        try:
                            p.stop()
                            p.setSource(QUrl())
                        except Exception:
                            pass

    def stop_all_active_media(self):
        """Detiene cualquier reproducción activa en los layouts y Rom Manager para evitar audio residual."""
        self._stop_library_layouts_media()
        if getattr(self, "rom_manager_tab", None):
            try:
                self.rom_manager_tab.stop_media()
            except Exception:
                pass

    def _on_emulators_changed(self):
        """Callback cuando se modifica algún emulador en la pestaña de emuladores."""
        self.refresh_emulators()
        self.refresh_games()

    def _on_settings_saved(self):
        """Callback cuando se guardan los ajustes del sistema."""
        current_layout = self.layout_stack.currentWidget()
        if current_layout:
            current_layout.db = self.db
        self.statusBar().showMessage(tr("mw.settings.saved_status", "System settings updated successfully."), 3500)

    def keyPressEvent(self, event):
        """Reenvía la navegación por teclado al layout visual activo en la Biblioteca de Juegos."""
        if hasattr(self, "main_tabs") and self.main_tabs.currentIndex() == 0:
            fw = self.focusWidget()
            from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
            # Si no se está escribiendo texto en un campo de búsqueda o edición ni navegando la lista de listas
            if fw != getattr(self, "list_widget", None) and not isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
                cur = self.layout_stack.currentWidget() if hasattr(self, "layout_stack") else None
                if cur:
                    if hasattr(cur, "keyPressEvent"):
                        cur.keyPressEvent(event)
                        if event.isAccepted():
                            return
                    elif hasattr(cur, "wheel_list") and cur.wheel_list:
                        cur.wheel_list.keyPressEvent(event)
                        if event.isAccepted():
                            return
        super().keyPressEvent(event)

    def changeEvent(self, event):
        """Gestiona el ciclo de vida de la multimedia al minimizar o restaurar la ventana."""
        if event.type() == QEvent.Type.WindowStateChange:
            old_state = event.oldState()
            if self.isMinimized():
                self.stop_all_active_media()
            elif (old_state & Qt.WindowMinimized) and not self.isMinimized():
                if hasattr(self, "main_tabs") and self.main_tabs.currentIndex() == 0:
                    cur = self.layout_stack.currentWidget() if hasattr(self, "layout_stack") else None
                    if cur:
                        if hasattr(cur, "resume_media") and callable(cur.resume_media):
                            cur.resume_media()
                        elif hasattr(cur, "_update_current_selection") and callable(cur._update_current_selection):
                            cur._update_current_selection()
        super().changeEvent(event)

    def closeEvent(self, event):
        """Detiene cualquier reproducción activa antes de cerrar la ventana para evitar errores de Media Foundation."""
        self.stop_all_active_media()
        # Cerrar y liberar hilos de layouts cargados en layout_stack y active_layouts
        if hasattr(self, "layout_stack"):
            for i in range(self.layout_stack.count()):
                inst = self.layout_stack.widget(i)
                try:
                    if hasattr(inst, "cleanup"):
                        inst.cleanup()
                    elif hasattr(inst, "close"):
                        inst.close()
                except Exception:
                    pass
        for inst in list(getattr(self, "active_layouts", {}).values()):
            try:
                if hasattr(inst, "cleanup"):
                    inst.cleanup()
                elif hasattr(inst, "close"):
                    inst.close()
            except Exception:
                pass
        if hasattr(self, "rom_manager_tab") and self.rom_manager_tab:
            try:
                self.rom_manager_tab.cleanup()
            except Exception:
                pass
        if hasattr(self, "layout_studio_tab") and self.layout_studio_tab:
            try:
                if hasattr(self.layout_studio_tab, "canvas") and hasattr(self.layout_studio_tab.canvas, "cleanup"):
                    self.layout_studio_tab.canvas.cleanup()
                if hasattr(self.layout_studio_tab, "close"):
                    self.layout_studio_tab.close()
            except Exception:
                pass
        # Detener gestor global de mandos si existiera
        try:
            from playnexus.services.gamepad import _GLOBAL_GAMEPAD_MANAGER
            if _GLOBAL_GAMEPAD_MANAGER:
                _GLOBAL_GAMEPAD_MANAGER.stop()
        except Exception:
            pass
        if hasattr(self, "player_window") and self.player_window:
            try:
                self.player_window.close()
            except Exception:
                pass
        super().closeEvent(event)


def run():
    try:
        db = Database()
        init_i18n(db)
        driver = db.get_setting("video_driver", "d3d11")
        if driver:
            os.environ["QSG_RHI_BACKEND"] = driver
            os.environ["QT_RHI_BACKEND"] = driver
    except Exception:
        pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("PlayNexus")
    app.setOrganizationName("PlayNexus")
    window = MainWindow()
    window.show()
    code = app.exec()
    del window
    sys.exit(code)


