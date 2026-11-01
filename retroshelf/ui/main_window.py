import sys
import os
import subprocess
from pathlib import Path
import retroshelf
from PySide6.QtCore import Qt, QSize, QPoint, QTimer, QUrl
from PySide6.QtGui import QAction, QFont, QIcon, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QComboBox, QLineEdit, QFileDialog, QMessageBox, QSplitter,
    QGroupBox, QFormLayout, QAbstractItemView, QMenu, QToolBar, QStackedWidget,
    QFrame, QTabWidget, QCheckBox
)
from retroshelf.db import Database
from retroshelf.services.library import (
    scan_rom_folder, import_scanned_games, add_game, parse_extensions_list,
    parse_rom_xml, apply_xml_to_list, enrich_game_dict,
    parse_rom_folders, format_rom_folders, sync_filtered_list_games
)
from retroshelf.services.media import clear_media_cache
from retroshelf.services.launcher import launch_game, resolve_emulator
from retroshelf.ui.dialogs import (
    EmulatorDialog, ListDialog, EmulatorManagerDialog, EmulatorManagerWidget,
    ScanSummaryDialog, GameEditDialog
)
from retroshelf.ui.frontend_tab import FrontendSettingsWidget
from retroshelf.ui.settings_tab import SystemSettingsWidget
from retroshelf.ui.layouts import LAYOUT_REGISTRY, get_available_layouts, create_layout, resolve_theme_name

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
"""

class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.db = db if db is not None else Database()
        self.current_list_id = None
        self.current_game_id = None
        self.games_cache = []

        self.setWindowTitle("RetroShelf — Configurador")
        self.resize(1300, 820)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(DARK_STYLESHEET)

        self._build_ui()
        self.refresh_lists()
        self.refresh_emulators()

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
        left_label = QLabel("LISTAS / PLATAFORMAS")
        left_label.setStyleSheet("font-weight: bold; color: #8e9bb0; letter-spacing: 1px;")
        left_layout.addWidget(left_label)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.on_list_changed)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_list_context_menu)
        left_layout.addWidget(self.list_widget, 1)

        left_btns = QHBoxLayout()
        btn_add_l = QPushButton("＋ Crear")
        btn_add_l.clicked.connect(self.create_list)
        btn_edit_l = QPushButton("✎ Editar")
        btn_edit_l.clicked.connect(self.edit_current_list)
        btn_del_l = QPushButton("🗑")
        btn_del_l.setToolTip("Eliminar lista")
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
        self.list_title = QLabel("Seleccioná una lista")
        self.list_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        h_top.addWidget(self.list_title, 1)

        self.layout_combo = QComboBox()
        self.layout_combo.addItems(get_available_layouts())
        self.layout_combo.currentTextChanged.connect(self.save_layout)
        h_top.addWidget(QLabel("Diseño visual:"))
        h_top.addWidget(self.layout_combo)

        # Control de sonido al probar layouts en configuración
        self.sound_checkbox = QCheckBox("🔊 Sonido")
        self.sound_checkbox.setToolTip("Activar o desactivar sonido y efectos al probar diseños visuales")
        self.sound_checkbox.setStyleSheet("margin-left: 10px; font-weight: 500;")
        sound_pref = self.db.get_setting("layout_preview_sound", "true").strip().lower() in ("true", "1")
        self.sound_checkbox.setChecked(sound_pref)
        self.sound_checkbox.setText("🔊 Sonido" if sound_pref else "🔇 Sonido")
        self.sound_checkbox.toggled.connect(self._on_layout_sound_toggled)
        h_top.addWidget(self.sound_checkbox)
        header_layout.addLayout(h_top)

        self.list_meta_label = QLabel("Extensiones admitidas: —")
        self.list_meta_label.setStyleSheet("color: #9ba7bc; font-size: 9pt;")
        header_layout.addWidget(self.list_meta_label)
        center_layout.addWidget(header_card)

        # Barra de búsqueda y conteo
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por título o archivo…")
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.filter_games)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        search_row.addWidget(self.search, 1)

        self.game_count_label = QLabel("0 juegos")
        self.game_count_label.setStyleSheet("color: #8e9bb0;")
        search_row.addWidget(self.game_count_label)
        center_layout.addLayout(search_row)

        # Contenedor de Layouts modulares personalizados (se instancian bajo demanda)
        self.layout_stack = QStackedWidget()
        self.active_layouts = {}
        center_layout.addWidget(self.layout_stack, 1)


        # Botones de acción inferior del centro
        center_btns = QHBoxLayout()
        btn_scan = QPushButton("▣ Escanear carpeta")
        btn_scan.clicked.connect(self.scan_folder)
        btn_add = QPushButton("＋ Agregar archivos")
        btn_add.clicked.connect(self.add_files)
        btn_edit_g = QPushButton("✎ Editar juego")
        btn_edit_g.clicked.connect(self.edit_selected_game)
        btn_del_g = QPushButton("Quitar de biblioteca")
        btn_del_g.setObjectName("danger")
        btn_del_g.clicked.connect(self.remove_game)

        center_btns.addWidget(btn_scan)
        center_btns.addWidget(btn_add)
        center_btns.addWidget(btn_edit_g)
        center_btns.addStretch()
        center_btns.addWidget(btn_del_g)
        center_layout.addLayout(center_btns)

        splitter.addWidget(center_widget)

        # Panel Derecho: Detalles del Juego y Lanzamiento
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        details_group = QGroupBox("Detalles y ejecución")
        form = QFormLayout(details_group)

        self.game_name = QLabel("—")
        self.game_name.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.game_name.setWordWrap(True)

        self.game_rom_code = QLabel("—")
        self.game_rom_code.setStyleSheet("color: #c4b5fd; font-weight: 600;")
        self.game_rom_code.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.game_meta_info = QLabel("—")
        self.game_meta_info.setWordWrap(True)
        self.game_meta_info.setStyleSheet("color: #9ba7bc; font-size: 9pt;")
        self.game_meta_info.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.game_path = QLabel("—")
        self.game_path.setWordWrap(True)
        self.game_path.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.game_size = QLabel("—")

        self.effective_emu = QLabel("—")
        self.effective_emu.setStyleSheet("font-weight: 600; color: #a5b4fc;")

        self.override_combo = QComboBox()
        self.override_combo.currentIndexChanged.connect(self.save_override)

        form.addRow("Título:", self.game_name)
        form.addRow("ROM / Código:", self.game_rom_code)
        form.addRow("Propiedades:", self.game_meta_info)
        form.addRow("Archivo:", self.game_path)
        form.addRow("Tamaño:", self.game_size)
        form.addRow("Emulador activo:", self.effective_emu)
        form.addRow("Emulador individual:", self.override_combo)

        right_layout.addWidget(details_group)

        self.launch_btn = QPushButton("▶  EJECUTAR JUEGO")
        self.launch_btn.setObjectName("primary")
        self.launch_btn.setMinimumHeight(48)
        self.launch_btn.clicked.connect(self.launch_selected)
        right_layout.addWidget(self.launch_btn)

        btn_open_folder = QPushButton("📂 Abrir en Explorador de Windows")
        btn_open_folder.clicked.connect(self.open_rom_location)
        right_layout.addWidget(btn_open_folder)

        tip_box = QFrame()
        tip_box.setStyleSheet("background-color: #1a1e28; border-radius: 6px; padding: 10px; margin-top: 10px;")
        tip_layout = QVBoxLayout(tip_box)
        tip_title = QLabel("<b>Prioridad de emulador</b>")
        tip_desc = QLabel(
            "1. Emulador individual del juego (si está asignado).<br>"
            "2. Emulador predeterminado de la lista.<br><br>"
            "<i>Doble clic en un juego para iniciar inmediatamente.</i>"
        )
        tip_desc.setStyleSheet("color: #9aa5b8; font-size: 9pt;")
        tip_layout.addWidget(tip_title)
        tip_layout.addWidget(tip_desc)
        right_layout.addWidget(tip_box)

        right_layout.addStretch()
        right_widget.setMinimumWidth(280)
        splitter.addWidget(right_widget)

        splitter.setSizes([230, 720, 310])
        outer.addWidget(splitter)

        # Contenedor con pestañas principales
        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)
        self.main_tabs.addTab(root, "🎮  Biblioteca de Juegos")

        self.emulator_tab = EmulatorManagerWidget(self.db, self)
        self.emulator_tab.emulators_changed.connect(self._on_emulators_changed)
        self.main_tabs.addTab(self.emulator_tab, "🕹  Administrar Emuladores")

        self.frontend_tab = FrontendSettingsWidget(self.db, self)
        self.frontend_tab.layout_changed.connect(self._on_frontend_layout_changed)
        self.frontend_tab.launch_requested.connect(self.launch_frontend_player)
        self.main_tabs.addTab(self.frontend_tab, "📺  Modo Frontend")

        self.settings_tab = SystemSettingsWidget(self.db, self)
        self.settings_tab.settings_saved.connect(self._on_settings_saved)
        self.main_tabs.addTab(self.settings_tab, "⚙  Configuración del Sistema")

        corner_btn = QPushButton("▶  Iniciar Frontend")
        corner_btn.setToolTip("Iniciar el Frontend a pantalla completa sin botones")
        corner_btn.setStyleSheet("""
            QPushButton {
                background-color: #5d48d9;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
                margin-right: 6px;
                font-size: 9.5pt;
            }
            QPushButton:hover {
                background-color: #6e59ea;
            }
        """)
        corner_btn.clicked.connect(self.launch_frontend_player)
        self.main_tabs.setCornerWidget(corner_btn, Qt.TopRightCorner)

        self.main_tabs.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(self.main_tabs)
        self.statusBar().showMessage("RetroShelf listo.")

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
                    f"🧭 Menú de Sistemas\n"
                    f"Sistemas incluidos: {len(menu_items)}\n"
                    f"Diseño: {row['layout']}"
                )
            elif is_filtered:
                src_id = row.get("source_list_id")
                src_name = "Desconocida"
                if src_id:
                    src_row = self.db.get_list(src_id)
                    if src_row:
                        src_name = src_row.get("name", "Desconocida")
                display_text = f"⚡ {row['name']} ({row['game_count']})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, row["id"])
                item.setToolTip(
                    f"⚡ Lista Filtrada\n"
                    f"Lista origen: {src_name}\n"
                    f"Juegos coincidentes: {row['game_count']}\n"
                    f"Plataforma: {row['platform'] or 'Sin definir'}\n"
                    f"Diseño: {row['layout']}"
                )
            else:
                display_text = f"{row['name']} ({row['game_count']})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, row["id"])
                folders_list = parse_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "")
                if len(folders_list) > 1:
                    folder_tip = "\nCarpetas:\n  • " + "\n  • ".join(folders_list)
                elif len(folders_list) == 1:
                    folder_tip = f"\nCarpeta: {folders_list[0]}"
                else:
                    folder_tip = ""
                xml_tip = f"\nXML: {Path(row['xml_path']).name}" if ("xml_path" in row.keys() and row["xml_path"]) else ""
                item.setToolTip(
                    f"Plataforma: {row['platform'] or 'Sin definir'}\n"
                    f"Extensiones: {row['allowed_extensions'] or 'Sin extensiones'}\n"
                    f"Diseño: {row['layout']}{folder_tip}{xml_tip}"
                )
            self.list_widget.addItem(item)
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
            self.list_title.setText("No hay listas creadas")
            self.list_meta_label.setText("Creá una lista para comenzar.")
            self.refresh_games()

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
                f"🧭 <b>Menú de Sistemas</b> · {len(menu_items)} sistema(s) vinculado(s) · Diseño: <b>{row['layout']}</b>"
            )
        elif is_filtered:
            src_id = row.get("source_list_id")
            src_name = "Desconocida"
            if src_id:
                src_row = self.db.get_list(src_id)
                if src_row:
                    src_name = src_row.get("name", "Desconocida")
            self.list_title.setText(f"⚡ {row['name']}")
            g_count = self.db.count_games(self.current_list_id)
            plat_text = f" · Plataforma: {row['platform']}" if row['platform'] else ""
            self.list_meta_label.setText(
                f"⚡ <b>Lista Filtrada</b> · Origen: <b>{src_name}</b> · {g_count} juego(s) coincidentes{plat_text} · Diseño: <b>{row['layout']}</b>"
            )
        else:
            self.list_title.setText(row["name"])
            exts_text = row["allowed_extensions"] or "Sin configurar"
            plat_text = f" · Plataforma: {row['platform']}" if row["platform"] else ""
            folders_list = parse_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "")
            if len(folders_list) > 1:
                folder_text = f" · Carpetas ({len(folders_list)}): {folders_list[0]} (+{len(folders_list) - 1} más)"
            elif len(folders_list) == 1:
                folder_text = f" · Carpeta: {folders_list[0]}"
            else:
                folder_text = ""
            xml_text = f" · XML: <b>{Path(row['xml_path']).name}</b>" if ("xml_path" in row.keys() and row["xml_path"]) else ""
            self.list_meta_label.setText(f"Extensiones admitidas: <b>{exts_text}</b>{plat_text}{folder_text}{xml_text}")

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
                    list_type=list_type,
                    xml_path=xml_path,
                    source_list_id=source_list_id,
                    filter_rules=filter_rules,
                    filter_match_mode=filter_match_mode,
                )
                clear_media_cache()
                if list_type == "menu":
                    self.db.set_menu_items(list_id, selected_list_ids)
                    self.refresh_lists(select_id=list_id)
                    self.statusBar().showMessage(f"Menú '{name}' creado con éxito con {len(selected_list_ids)} sistemas.", 4000)
                    return
                elif list_type == "filtered":
                    synced = sync_filtered_list_games(self.db, list_id)
                    self.refresh_lists(select_id=list_id)
                    self.statusBar().showMessage(f"Lista filtrada '{name}' creada con {synced} juego(s) coincidentes.", 5000)
                    return

                self.refresh_lists(select_id=list_id)

                rom_folders = [f for f in parse_rom_folders(folder) if Path(f).is_dir()]
                if list_type == "games" and rom_folders and auto_scan:
                    try:
                        self.statusBar().showMessage(f"Escaneando carpeta(s) de '{name}'…")
                        QApplication.setOverrideCursor(Qt.WaitCursor)
                        paths = scan_rom_folder(
                            rom_folders,
                            exts,
                            scan_subfolders=scan_subfolders,
                            exclude_folder_if_zip=exclude_folder_if_zip,
                        )
                        stats = import_scanned_games(self.db, list_id, paths, xml_path=xml_path)
                        QApplication.restoreOverrideCursor()
                        self.refresh_lists(select_id=list_id)
                        summary = ScanSummaryDialog(self, stats, format_rom_folders(rom_folders), name, exts)
                        summary.exec()
                        self.statusBar().showMessage(f"Lista '{name}' creada con {stats['added']} juego(s) importados.", 5000)
                    except Exception as err:
                        QApplication.restoreOverrideCursor()
                        QMessageBox.warning(self, "Aviso de escaneo", f"Se creó la lista pero ocurrió un error al escanear las carpetas:\n{err}")
                else:
                    msg = f"Lista '{name}' creada con éxito."
                    self.statusBar().showMessage(msg, 4000)
            except Exception as e:
                QMessageBox.critical(self, "No se pudo crear la lista", f"Error al guardar:\n{e}")

    def edit_current_list(self):
        if not self.current_list_id:
            QMessageBox.information(self, "Seleccionar", "Seleccioná una lista para editar.")
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        emulators = self.db.get_emulators()
        all_lists = self.db.get_lists(with_counts=False)
        initial_menu_items = self.db.get_menu_items(self.current_list_id)
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
            old_roms_path = format_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "")
            old_exts = (row["allowed_extensions"] if "allowed_extensions" in row.keys() else "") or ""
            old_scan_sub = str(row.get("scan_subfolders", "true")).strip().lower() in ("true", "1")
            old_excl_zip = str(row.get("exclude_folder_if_zip", "false")).strip().lower() in ("true", "1")
            folders_changed = (
                format_rom_folders(folder) != old_roms_path
                or exts != old_exts
                or scan_subfolders != old_scan_sub
                or exclude_folder_if_zip != old_excl_zip
            )
            try:
                self.db.update_list(
                    self.current_list_id,
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
                    list_type=list_type,
                    xml_path=xml_path,
                    source_list_id=source_list_id,
                    filter_rules=filter_rules,
                    filter_match_mode=filter_match_mode,
                )
                clear_media_cache()
                if list_type == "menu":
                    self.db.set_menu_items(self.current_list_id, selected_list_ids)
                    self.refresh_lists(select_id=self.current_list_id)
                    self.statusBar().showMessage(f"Menú '{name}' actualizado.", 4000)
                    return
                elif list_type == "filtered":
                    synced = sync_filtered_list_games(self.db, self.current_list_id)
                    self.refresh_lists(select_id=self.current_list_id)
                    self.statusBar().showMessage(f"Lista filtrada '{name}' sincronizada con {synced} juego(s) coincidentes.", 5000)
                    return

                rom_folders = [f for f in parse_rom_folders(folder) if Path(f).is_dir()]
                if list_type == "games" and rom_folders and (auto_scan or folders_changed):
                    try:
                        self.statusBar().showMessage(f"Escaneando carpeta(s) de '{name}'…")
                        QApplication.setOverrideCursor(Qt.WaitCursor)
                        paths = scan_rom_folder(
                            rom_folders,
                            exts,
                            scan_subfolders=scan_subfolders,
                            exclude_folder_if_zip=exclude_folder_if_zip,
                        )
                        stats = import_scanned_games(self.db, self.current_list_id, paths, xml_path=xml_path, replace=True)
                        QApplication.restoreOverrideCursor()
                        self.refresh_lists(select_id=self.current_list_id)
                        summary = ScanSummaryDialog(self, stats, format_rom_folders(rom_folders), name, exts)
                        summary.exec()
                        self.statusBar().showMessage(f"Lista '{name}' actualizada con {stats['added']} juego(s).", 5000)
                    except Exception as err:
                        QApplication.restoreOverrideCursor()
                        QMessageBox.warning(self, "Aviso de escaneo", f"Se actualizó la lista pero ocurrió un error al escanear las carpetas:\n{err}")
                elif list_type == "games" and not rom_folders and (auto_scan or folders_changed):
                    self.db.clear_list_games(self.current_list_id)
                    self.refresh_lists(select_id=self.current_list_id)
                    self.statusBar().showMessage(f"Lista '{name}' actualizada (sin carpetas de ROMs).", 4000)
                elif list_type == "games" and xml_path and Path(xml_path).is_file():
                    try:
                        QApplication.setOverrideCursor(Qt.WaitCursor)
                        xml_res = apply_xml_to_list(self.db, self.current_list_id, xml_path=xml_path)
                        QApplication.restoreOverrideCursor()
                        self.refresh_lists(select_id=self.current_list_id)
                        self.statusBar().showMessage(
                            f"Lista '{name}' actualizada. XML aplicado a {xml_res['matched']} juego(s).",
                            5000
                        )
                    except Exception as xml_err:
                        QApplication.restoreOverrideCursor()
                        self.refresh_lists(select_id=self.current_list_id)
                        QMessageBox.warning(self, "Aviso de XML", f"Se actualizó la lista pero ocurrió un error al aplicar el XML:\n{xml_err}")
                else:
                    self.refresh_lists(select_id=self.current_list_id)
                    self.statusBar().showMessage(f"Lista '{name}' actualizada.", 4000)
            except Exception as e:
                QMessageBox.critical(self, "No se pudo actualizar la lista", f"Error al actualizar:\n{e}")

    def sync_xml_for_current_list(self):
        """Permite seleccionar o re-aplicar un archivo XML a los juegos de la lista actual."""
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
            f"Seleccionar archivo XML para '{row['name']}'",
            initial_dir or "",
            "Archivos XML / DAT (*.xml *.dat);;Todos los archivos (*.*)"
        )
        if not path:
            return

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.db.update_list(self.current_list_id, xml_path=path)
            res = apply_xml_to_list(self.db, self.current_list_id, xml_path=path)
            QApplication.restoreOverrideCursor()
            self.refresh_lists(select_id=self.current_list_id)
            QMessageBox.information(
                self,
                "XML aplicado",
                f"Se vinculó el archivo XML a la lista '{row['name']}'.\n\n"
                f"Juegos en la lista: {res['total_games']}\n"
                f"ROMs asociadas con nombre completo y propiedades: {res['matched']}"
            )
            self.statusBar().showMessage(f"XML sincronizado: {res['matched']} juego(s) actualizados.", 4000)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error al procesar XML", f"No se pudo aplicar el archivo XML:\n{e}")


    def delete_current_list(self):
        if not self.current_list_id:
            QMessageBox.information(self, "Seleccionar", "Seleccioná una lista para eliminar.")
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        count = self.db.count_games(self.current_list_id)
        answer = QMessageBox.question(
            self,
            "Eliminar lista",
            f"¿Estás seguro de que deseas eliminar la lista '{row['name']}'?\n"
            f"Se desvincularán los {count} juegos registrados en esta lista (los archivos en el disco NO se eliminarán).",
            QMessageBox.Yes | QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            try:
                self.db.delete_list(self.current_list_id)
                self.refresh_lists()
                self.statusBar().showMessage("Lista eliminada.", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo eliminar la lista:\n{e}")

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
                f"Lista filtrada '{row['name']}' sincronizada: {count} juego(s) coincidentes.", 5000
            )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error de sincronización", f"No se pudo sincronizar la lista filtrada:\n{e}")

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
            sync_filt_act = menu.addAction("⚡ Sincronizar con lista origen…")
        elif not is_menu:
            scan_act = menu.addAction("▣ Escanear carpeta…")
            add_act = menu.addAction("＋ Agregar archivos…")
            xml_act = menu.addAction("📄 Asociar / Sincronizar XML…")

        menu.addSeparator()
        edit_act = menu.addAction("✎ Editar lista…")
        del_act = menu.addAction("🗑 Eliminar lista")

        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == sync_filt_act:
            self.sync_filtered_list()
        elif action == scan_act:
            self.scan_folder()
        elif action == add_act:
            self.add_files()
        elif action == xml_act:
            self.sync_xml_for_current_list()
        elif action == edit_act:
            self.edit_current_list()
        elif action == del_act:
            self.delete_current_list()

    # -------------------------------------------------------------
    # DISEÑOS VISUALES (LAYOUTS)
    # -------------------------------------------------------------
    def _on_layout_sound_toggled(self, checked: bool):
        self.sound_checkbox.setText("🔊 Sonido" if checked else "🔇 Sonido")
        self.db.set_setting("layout_preview_sound", "true" if checked else "false")
        muted = not checked
        for inst in list(getattr(self, "active_layouts", {}).values()):
            if hasattr(inst, "set_media_muted") and callable(inst.set_media_muted):
                try:
                    inst.set_media_muted(muted)
                except Exception:
                    pass
        cur = self.layout_stack.currentWidget()
        if cur and hasattr(cur, "set_media_muted") and callable(cur.set_media_muted):
            try:
                cur.set_media_muted(muted)
            except Exception:
                pass

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
            self.statusBar().showMessage(f"Diseño guardado: {layout}", 2500)

    def _get_or_create_layout(self, layout_name: str):
        """Obtiene una instancia del layout o la crea dinámicamente si es un tema de sistema."""
        if layout_name in self.active_layouts:
            return self.active_layouts[layout_name]

        inst = create_layout(layout_name)
        inst.db = self.db
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
                    "effective_name": f"{g_count} juegos",
                    "source": "menu",
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
            self.game_count_label.setText(f"{count} sistema{'s' if count != 1 else ''}")
        else:
            self.game_count_label.setText(f"{count} juego{'s' if count != 1 else ''}")

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
                current_layout.select_game_by_id(self.current_game_id)
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
        from retroshelf.services.emulator_manager import EMULATOR_MANAGER
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
            open_act = menu.addAction("📂 Abrir lista de este sistema")
            edit_act = menu.addAction("✎ Editar sistema…")
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

        menu = QMenu(self)
        play_act = menu.addAction("▶ Ejecutar juego")
        edit_act = menu.addAction("✎ Editar juego…")
        loc_act = menu.addAction("📂 Abrir ubicación del archivo")
        menu.addSeparator()
        del_act = menu.addAction("🗑 Quitar de la biblioteca")

        action = menu.exec(global_pos)
        if action == play_act:
            self.launch_selected()
        elif action == edit_act:
            self.edit_selected_game()
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
            self.game_path.setText(f"Plataforma: {selected_item['platform']}")
            self.game_size.setText(f"Sistema vinculado ({selected_item.get('effective_name', '')})")
            self.override_combo.blockSignals(True)
            self.override_combo.setCurrentIndex(0)
            self.override_combo.blockSignals(False)
            return

        game_row = self.db.get_game(game_id)
        if not game_row:
            self.on_game_unselected()
            return

        game = enrich_game_dict(game_row)
        self.game_name.setText(game["title"])
        self.game_path.setText(game["rom_path"])

        rom_p = Path(game["rom_path"])
        rom_code = game.get("rom_name") or rom_p.stem
        self.game_rom_code.setText(rom_code)

        # Mostrar propiedades del XML si están disponibles
        meta_parts = []
        if game.get("year"):
            meta_parts.append(f"<b>Año:</b> {game['year']}")
        if game.get("manufacturer"):
            meta_parts.append(f"<b>Fabricante:</b> {game['manufacturer']}")
        if game.get("genre"):
            meta_parts.append(f"<b>Género:</b> {game['genre']}")
        if game.get("players"):
            meta_parts.append(f"<b>Jugadores:</b> {game['players']}")
        if game.get("cloneof"):
            meta_parts.append(f"<b>Clon de:</b> {game['cloneof']}")
        if game.get("rating"):
            meta_parts.append(f"<b>Rating:</b> {game['rating']}")
        if game.get("crc"):
            meta_parts.append(f"<b>CRC:</b> {game['crc']}")
        if game.get("sourcefile"):
            meta_parts.append(f"<b>Driver:</b> {game['sourcefile']}")

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
                self.game_size.setText("Carpeta ROM (<DIR>)")
            else:
                size_mb = rom_p.stat().st_size / (1024 * 1024)
                self.game_size.setText(f"{size_mb:.2f} MB ({rom_p.suffix.lower()})")
        else:
            self.game_size.setText("<span style='color: #ef4444;'>Archivo o carpeta no encontrada en disco</span>")

        # Configurar combo de emulador individual
        self.override_combo.blockSignals(True)
        idx = self.override_combo.findData(game["emulator_override_id"])
        self.override_combo.setCurrentIndex(max(idx, 0))
        self.override_combo.blockSignals(False)

        emu, source = resolve_emulator(self.db, game_row)
        if emu:
            source_desc = "asignado a este juego" if source == "juego" else "predeterminado de la lista"
            self.effective_emu.setText(f"{emu['name']} ({source_desc})")
            self.effective_emu.setStyleSheet("font-weight: 600; color: #4ade80;")
        else:
            self.effective_emu.setText("Sin emulador asignado")
            self.effective_emu.setStyleSheet("font-weight: 600; color: #f87171;")

    def on_game_unselected(self):
        self.current_game_id = None
        self.game_name.setText("—")
        self.game_rom_code.setText("—")
        self.game_meta_info.setText("—")
        self.game_meta_info.setToolTip("")
        self.game_path.setText("—")
        self.game_size.setText("—")
        self.effective_emu.setText("—")
        self.override_combo.blockSignals(True)
        self.override_combo.setCurrentIndex(0)
        self.override_combo.blockSignals(False)

    def save_override(self, index):
        if not self.current_game_id:
            return
        emu_id = self.override_combo.currentData()
        self.db.update_game(self.current_game_id, emulator_override_id=emu_id)
        self.refresh_games()
        self.statusBar().showMessage("Emulador individual actualizado para este juego.", 3000)

    # -------------------------------------------------------------
    # ESCANEO Y ADICIÓN DE JUEGOS
    # -------------------------------------------------------------
    def scan_folder(self):
        if not self.current_list_id:
            QMessageBox.information(self, "Lista no seleccionada", "Seleccioná o creá una lista primero.")
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        if row.get("list_type") == "filtered":
            answer = QMessageBox.question(
                self,
                "Lista Filtrada",
                f"'{row['name']}' es una lista filtrada vinculada a una lista origen.\n"
                "Para actualizar sus juegos, debes sincronizarla con su origen.\n\n"
                "¿Deseas sincronizar los juegos ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if answer == QMessageBox.Yes:
                self.sync_filtered_list()
            return

        allowed_str = (row["allowed_extensions"] or "").strip()
        if not allowed_str:
            answer = QMessageBox.question(
                self,
                "Sin extensiones configuradas",
                f"La lista '{row['name']}' todavía no tiene extensiones de archivo configuradas.\n"
                "Para poder escanear, es obligatorio indicar qué extensiones buscar.\n\n"
                "¿Deseas editar la lista y configurar las extensiones ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if answer == QMessageBox.Yes:
                self.edit_current_list()
            return

        configured_folders = [f for f in parse_rom_folders(row["roms_path"] if "roms_path" in row.keys() else "") if Path(f).is_dir()]
        folders_to_scan = []

        if configured_folders:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(f"Escanear carpetas — {row['name']}")
            folders_bullet = "\n".join(f"• {f}" for f in configured_folders)
            msg_box.setText(
                f"La lista '{row['name']}' tiene {len(configured_folders)} carpeta(s) de ROMs configurada(s):\n\n"
                f"{folders_bullet}\n\n"
                "¿Deseas escanear todas las carpetas configuradas o agregar una nueva carpeta a la lista?"
            )
            btn_scan_existing = msg_box.addButton(f"Escanear configuradas ({len(configured_folders)})", QMessageBox.AcceptRole)
            btn_add_new = msg_box.addButton("＋ Agregar nueva carpeta…", QMessageBox.ActionRole)
            btn_cancel = msg_box.addButton("Cancelar", QMessageBox.RejectRole)
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
                    f"Agregar y escanear carpeta de juegos para '{row['name']}'",
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
                f"Seleccionar carpeta de juegos para '{row['name']}'",
                ""
            )
            if not folder:
                return
            self.db.update_list(self.current_list_id, roms_path=folder)
            folders_to_scan = [folder]

        scan_sub = str(row.get("scan_subfolders", "true")).strip().lower() in ("true", "1")
        excl_zip = str(row.get("exclude_folder_if_zip", "false")).strip().lower() in ("true", "1")

        try:
            self.statusBar().showMessage("Escaneando archivos…")
            QApplication.setOverrideCursor(Qt.WaitCursor)

            paths = scan_rom_folder(
                folders_to_scan,
                allowed_str,
                scan_subfolders=scan_sub,
                exclude_folder_if_zip=excl_zip,
            )
            stats = import_scanned_games(self.db, self.current_list_id, paths, replace=True)

            QApplication.restoreOverrideCursor()
            self.refresh_lists(select_id=self.current_list_id)

            # Mostrar resumen detallado del escaneo
            summary = ScanSummaryDialog(self, stats, format_rom_folders(folders_to_scan), row["name"], allowed_str)
            summary.exec()

            self.statusBar().showMessage(
                f"Escaneo finalizado: {stats['added']} juego(s) en la lista.",
                5000
            )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error durante el escaneo", str(e))

    def add_files(self):
        if not self.current_list_id:
            QMessageBox.information(self, "Lista no seleccionada", "Seleccioná o creá una lista primero.")
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        if row.get("list_type") == "filtered":
            QMessageBox.information(
                self,
                "Lista Filtrada",
                f"'{row['name']}' es una lista filtrada vinculada a una lista origen.\n"
                "Para incorporar juegos, agrégalos a la lista de origen y luego sincroniza esta lista."
            )
            return

        # Construir filtro de archivos sugerido según extensiones de la lista
        exts_list = parse_extensions_list(row["allowed_extensions"])
        if exts_list:
            filter_exts = " ".join(f"*{e}" for e in exts_list)
            filter_str = f"Extensiones de la lista ({filter_exts});;Todos los archivos (*.*)"
        else:
            filter_str = "Todos los archivos (*.*)"

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            f"Agregar juegos a '{row['name']}'",
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
        self.statusBar().showMessage(f"Se procesaron los archivos. Agregados a la biblioteca: {added}", 4000)

    def edit_selected_game(self):
        if not self.current_game_id:
            current_layout = self.layout_stack.currentWidget()
            if current_layout and hasattr(current_layout, "get_selected_game_id"):
                selected_id = current_layout.get_selected_game_id()
                if selected_id:
                    self._select_game_by_id(selected_id)
        if not self.current_game_id:
            QMessageBox.information(self, "Seleccionar juego", "Elegí un juego para editar sus datos.")
            return
        game = self.db.get_game(self.current_game_id)
        if not game:
            return
        dialog = GameEditDialog(self.db, game, self)
        if dialog.exec():
            self.refresh_games()
            self.statusBar().showMessage("Juego actualizado.", 3000)

    def remove_game(self):
        if not self.current_game_id:
            current_layout = self.layout_stack.currentWidget()
            if current_layout and hasattr(current_layout, "get_selected_game_id"):
                selected_id = current_layout.get_selected_game_id()
                if selected_id:
                    self._select_game_by_id(selected_id)
        if not self.current_game_id:
            QMessageBox.information(self, "Seleccionar juego", "Elegí un juego de la biblioteca.")
            return
        game = self.db.get_game(self.current_game_id)
        if not game:
            return
        answer = QMessageBox.question(
            self,
            "Quitar juego",
            f"¿Quitar '{game['title']}' de esta lista?\n"
            "El archivo ROM en el disco NO se eliminará.",
            QMessageBox.Yes | QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            self.db.delete_game(self.current_game_id)
            self.refresh_lists(select_id=self.current_list_id)
            self.statusBar().showMessage("Juego quitado de la biblioteca.", 3000)

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
            QMessageBox.warning(self, "No encontrado", f"El archivo no existe en el disco:\n{p}")

    def _show_game_context_menu(self, pos):
        if not self.current_game_id:
            return
        menu = QMenu(self)
        play_act = menu.addAction("▶ Ejecutar juego")
        edit_act = menu.addAction("✎ Editar juego…")
        loc_act = menu.addAction("📂 Abrir ubicación del archivo")
        menu.addSeparator()
        del_act = menu.addAction("🗑 Quitar de la biblioteca")

        sender = self.sender()
        action = menu.exec(sender.mapToGlobal(pos))
        if action == play_act:
            self.launch_selected()
        elif action == edit_act:
            self.edit_selected_game()
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
        self.override_combo.addItem("Heredar emulador de la lista (por defecto)", None)
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
            QMessageBox.information(self, "Seleccionar juego", "Elegí un juego de la biblioteca para ejecutar.")
            return

        from retroshelf.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            return

        game = self.db.get_game(self.current_game_id)
        if not game:
            return

        try:
            active_layout = self.layout_stack.currentWidget()
            result = launch_game(self.db, game, layout=active_layout, parent_window=self)
            if not result or result[0] is None:
                return
            name, source = result
            source_desc = "asignación individual del juego" if source == "juego" else "predeterminado de la lista"
            self.statusBar().showMessage(f"Iniciando con {name} ({source_desc})…", 6000)
        except Exception as e:
            QMessageBox.critical(self, "No se pudo iniciar el juego", str(e))

    def open_system_settings_tab(self):
        """Abre directamente la pestaña de Configuración del Sistema."""
        self.main_tabs.setCurrentWidget(self.settings_tab)

    def open_frontend_tab(self):
        """Abre directamente la pestaña de Modo Frontend."""
        self.main_tabs.setCurrentWidget(self.frontend_tab)

    def _on_tab_changed(self, index: int):
        """Mantiene sincronizados los datos al alternar entre pestañas."""
        current_widget = self.main_tabs.widget(index)
        if current_widget == self.main_tabs.widget(0):
            self.refresh_emulators()
            self.refresh_games()
            if self.current_game_id:
                self._select_game_by_id(self.current_game_id)
        elif current_widget == self.emulator_tab:
            self.emulator_tab.refresh()
        elif current_widget == self.frontend_tab:
            self.frontend_tab.refresh_data()

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
        from retroshelf.ui.player_window import PlayerWindow
        self.player_window = PlayerWindow(parent=None)
        self.player_window.apply_video_settings()

        def _on_player_closed():
            self.show()
            self.raise_()
            self.activateWindow()
            if hasattr(self, "gamepad") and self.gamepad:
                self.gamepad.set_enabled(True)

        self.player_window.destroyed.connect(_on_player_closed)
        QTimer.singleShot(0, self.player_window._apply_show)

    def stop_all_active_media(self):
        """Detiene cualquier reproducción activa en los layouts para evitar audio residual."""
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

    def _on_emulators_changed(self):
        """Callback cuando se modifica algún emulador en la pestaña de emuladores."""
        self.refresh_emulators()
        self.refresh_games()

    def _on_settings_saved(self):
        """Callback cuando se guardan los ajustes del sistema."""
        current_layout = self.layout_stack.currentWidget()
        if current_layout:
            current_layout.db = self.db
        self.statusBar().showMessage("Configuración del sistema actualizada correctamente.", 3500)

    def closeEvent(self, event):
        """Detiene cualquier reproducción activa antes de cerrar la ventana para evitar errores de Media Foundation."""
        self.stop_all_active_media()
        if hasattr(self, "player_window") and self.player_window:
            try:
                self.player_window.close()
            except Exception:
                pass
        super().closeEvent(event)


def run():
    try:
        db = Database()
        driver = db.get_setting("video_driver", "d3d11")
        if driver:
            os.environ["QSG_RHI_BACKEND"] = driver
            os.environ["QT_RHI_BACKEND"] = driver
    except Exception:
        pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("RetroShelf")
    app.setOrganizationName("RetroShelf")
    window = MainWindow()
    window.show()
    code = app.exec()
    del window
    sys.exit(code)


