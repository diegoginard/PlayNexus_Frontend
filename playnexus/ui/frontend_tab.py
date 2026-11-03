"""
Pestaña de Configuración del Modo Frontend (Pantalla Completa) para PlayNexus.
Permite configurar:
1. Qué lista o menú de sistemas se mostrará al iniciar el frontend en pantalla completa.
2. El diseño visual del elemento de inicio.
3. Para menús de sistemas (listas de listas), la visualización y asignación del diseño visual
   propio de cada una de sus sub-listas (para que al navegar a ellas se muestre su diseño asignado).
4. Opciones de visualización de pantalla (pantalla completa, resolución, monitor).
5. Lanzamiento directo del Frontend en pantalla completa.
"""

import sys
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QGroupBox, QFrame, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QCheckBox, QLineEdit, QFileDialog
)
from playnexus.db import Database, APP_DIR
from playnexus.ui.layouts import get_available_layouts
from playnexus.ui.settings_tab import SCREEN_MODES, RESOLUTIONS_LIST


class FrontendSettingsWidget(QWidget):
    """
    Panel de configuración del Frontend para pantalla completa.
    """
    layout_changed = Signal(int, str)  # (list_id, layout_name)
    launch_requested = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._updating = False

        self._build_ui()
        self.refresh_data()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # -------------------------------------------------------------
        # 1. ENCABEZADO
        # -------------------------------------------------------------
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #1b1e2a; border-radius: 8px; padding: 12px;")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(8, 8, 8, 8)
        h_layout.setSpacing(6)

        title = QLabel("📺  Configuración del Modo Frontend (Pantalla Completa)")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        h_layout.addWidget(title)

        desc = QLabel(
            "En esta sección podés determinar qué lista o menú de sistemas se mostrará al iniciar el frontend "
            "en pantalla completa sin botones. Si seleccionás un Menú de Sistemas (lista de listas), podrás definir "
            "el diseño visual individual que tendrá cada sistema vinculado cuando el usuario ingrese a él."
        )
        desc.setStyleSheet("color: #9aa5b8; font-size: 9.5pt;")
        desc.setWordWrap(True)
        h_layout.addWidget(desc)
        layout.addWidget(header_card)

        # -------------------------------------------------------------
        # 2. INICIO PRINCIPAL DEL FRONTEND
        # -------------------------------------------------------------
        grp_startup = QGroupBox("🚀 Elemento de Inicio del Frontend")
        v_startup = QVBoxLayout(grp_startup)
        v_startup.setSpacing(12)

        row_start = QHBoxLayout()
        row_start.setSpacing(14)

        col_list = QVBoxLayout()
        col_list.addWidget(QLabel("<b>Lista o Menú principal que se mostrará al iniciar:</b>"))
        self.startup_combo = QComboBox()
        self.startup_combo.setMinimumHeight(34)
        self.startup_combo.currentIndexChanged.connect(self._on_startup_list_changed)
        col_list.addWidget(self.startup_combo)
        row_start.addLayout(col_list, 2)

        col_layout = QVBoxLayout()
        col_layout.addWidget(QLabel("<b>Diseño visual de inicio:</b>"))
        self.startup_layout_combo = QComboBox()
        self.startup_layout_combo.setMinimumHeight(34)
        self.startup_layout_combo.addItems(get_available_layouts(for_frontend=True))
        self.startup_layout_combo.currentTextChanged.connect(self._on_startup_layout_changed)
        col_layout.addWidget(self.startup_layout_combo)
        row_start.addLayout(col_layout, 1)

        v_startup.addLayout(row_start)

        self.startup_info_label = QLabel("")
        self.startup_info_label.setStyleSheet("color: #7b88a3; font-size: 9pt;")
        self.startup_info_label.setWordWrap(True)
        v_startup.addWidget(self.startup_info_label)

        layout.addWidget(grp_startup)

        # -------------------------------------------------------------
        # 3. MENÚS DE SISTEMAS Y DISEÑOS DE SUB-LISTAS
        # -------------------------------------------------------------
        self.grp_menu_systems = QGroupBox("🧭 Diseños Visuales para Menús de Sistemas (Listas de listas)")
        v_menu = QVBoxLayout(self.grp_menu_systems)
        v_menu.setSpacing(12)

        # Explicación del funcionamiento
        notice_box = QFrame()
        notice_box.setStyleSheet("background-color: #171b26; border-left: 4px solid #5d48d9; border-radius: 6px; padding: 10px;")
        n_layout = QVBoxLayout(notice_box)
        n_layout.setContentsMargins(6, 6, 6, 6)
        notice_text = QLabel(
            "<b>💡 Comportamiento de navegación en Menús:</b><br>"
            "Al iniciar el frontend con un Menú de Sistemas, se mostrará primero el diseño del menú (ej: ruleta de consolas). "
            "Al presionar Enter / Seleccionar sobre cualquier sistema, el Frontend cargará automáticamente "
            "<b>el diseño visual asignado a esa lista específica</b> (aunque no haya sido seleccionada como la lista de inicio principal). "
            "Al presionar Volver (Escape / Retroceso / Botón B del mando), regresará instantáneamente al menú de sistemas."
        )
        notice_text.setStyleSheet("color: #c4cde0; font-size: 9pt;")
        notice_text.setWordWrap(True)
        n_layout.addWidget(notice_text)
        v_menu.addWidget(notice_box)

        # Selector del menú a inspeccionar/configurar
        row_menu_sel = QHBoxLayout()
        row_menu_sel.addWidget(QLabel("<b>Menú de Sistemas a configurar:</b>"))
        self.menu_selector_combo = QComboBox()
        self.menu_selector_combo.setMinimumHeight(32)
        self.menu_selector_combo.currentIndexChanged.connect(self._on_menu_selector_changed)
        row_menu_sel.addWidget(self.menu_selector_combo, 1)
        row_menu_sel.addStretch(1)
        v_menu.addLayout(row_menu_sel)

        # Tabla de sistemas vinculados al menú
        self.sublists_table = QTableWidget()
        self.sublists_table.setColumnCount(5)
        self.sublists_table.setHorizontalHeaderLabels([
            "Sistema / Lista", "Plataforma", "Juegos", "Diseño Visual para este Sistema", "Emulador"
        ])
        self.sublists_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.sublists_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.sublists_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.sublists_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.sublists_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.sublists_table.setAlternatingRowColors(True)
        self.sublists_table.setSelectionMode(QTableWidget.NoSelection)
        self.sublists_table.setMinimumHeight(220)
        v_menu.addWidget(self.sublists_table)

        self.empty_menu_label = QLabel("Este menú no tiene sistemas vinculados actualmente.")
        self.empty_menu_label.setAlignment(Qt.AlignCenter)
        self.empty_menu_label.setStyleSheet("color: #8b97ac; font-style: italic; padding: 20px;")
        self.empty_menu_label.setVisible(False)
        v_menu.addWidget(self.empty_menu_label)

        layout.addWidget(self.grp_menu_systems)

        # -------------------------------------------------------------
        # 4. OPCIONES DE PANTALLA Y VIDEO
        # -------------------------------------------------------------
        grp_video = QGroupBox("🖥 Pantalla y Monitor del Frontend")
        v_video = QVBoxLayout(grp_video)
        v_video.setSpacing(12)

        row_v = QHBoxLayout()
        row_v.setSpacing(16)

        col_m = QVBoxLayout()
        col_m.addWidget(QLabel("Modo de pantalla:"))
        self.mode_combo = QComboBox()
        for label, val in SCREEN_MODES:
            self.mode_combo.addItem(label, val)
        self.mode_combo.currentIndexChanged.connect(self._save_video_settings)
        col_m.addWidget(self.mode_combo)
        row_v.addLayout(col_m, 1)

        col_scr = QVBoxLayout()
        col_scr.addWidget(QLabel("Monitor de destino:"))
        self.screen_combo = QComboBox()
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        for idx, scr in enumerate(screens):
            geo = scr.geometry()
            tag = " [Principal]" if scr == primary else ""
            self.screen_combo.addItem(f"Monitor {idx + 1}: {geo.width()}x{geo.height()}{tag}", idx)
        self.screen_combo.currentIndexChanged.connect(self._on_screen_changed)
        col_scr.addWidget(self.screen_combo)
        row_v.addLayout(col_scr, 1)

        col_res = QVBoxLayout()
        col_res.addWidget(QLabel("Resolución:"))
        self.res_combo = QComboBox()
        for label, val in RESOLUTIONS_LIST:
            self.res_combo.addItem(label, val)
        self.res_combo.currentIndexChanged.connect(self._on_res_changed)
        col_res.addWidget(self.res_combo)
        row_v.addLayout(col_res, 1)

        v_video.addLayout(row_v)

        # Fila de resolución personalizada (se muestra únicamente al seleccionar 'Personalizada...')
        self.custom_res_container = QWidget()
        row_custom = QHBoxLayout(self.custom_res_container)
        row_custom.setContentsMargins(0, 0, 0, 0)
        row_custom.setSpacing(16)

        col_cw = QVBoxLayout()
        col_cw.addWidget(QLabel("📐 Ancho personalizado (px):"))
        self.spin_custom_w = QSpinBox()
        self.spin_custom_w.setRange(320, 7680)
        self.spin_custom_w.setSingleStep(10)
        self.spin_custom_w.setSuffix(" px")
        self.spin_custom_w.setValue(1920)
        self.spin_custom_w.valueChanged.connect(self._save_video_settings)
        col_cw.addWidget(self.spin_custom_w)
        row_custom.addLayout(col_cw, 1)

        col_ch = QVBoxLayout()
        col_ch.addWidget(QLabel("Alto personalizado (px):"))
        self.spin_custom_h = QSpinBox()
        self.spin_custom_h.setRange(240, 4320)
        self.spin_custom_h.setSingleStep(10)
        self.spin_custom_h.setSuffix(" px")
        self.spin_custom_h.setValue(1080)
        self.spin_custom_h.valueChanged.connect(self._save_video_settings)
        col_ch.addWidget(self.spin_custom_h)
        row_custom.addLayout(col_ch, 1)

        v_video.addWidget(self.custom_res_container)
        self.custom_res_container.setVisible(False)
        layout.addWidget(grp_video)

        # -------------------------------------------------------------
        # 5. PANTALLA DE BIENVENIDA (SPLASH SCREEN DE VIDEO)
        # -------------------------------------------------------------
        grp_splash = QGroupBox("🎬 Pantalla de Bienvenida (Splash Screen de Video)")
        v_splash = QVBoxLayout(grp_splash)
        v_splash.setSpacing(10)

        self.chk_splash = QCheckBox("Reproducir video de presentación al iniciar el Frontend")
        self.chk_splash.setStyleSheet("font-weight: 500; font-size: 10pt;")
        self.chk_splash.toggled.connect(self._on_splash_toggled)
        v_splash.addWidget(self.chk_splash)

        self.splash_container = QWidget()
        v_splash_box = QVBoxLayout(self.splash_container)
        v_splash_box.setContentsMargins(0, 0, 0, 0)
        v_splash_box.setSpacing(8)

        v_splash_box.addWidget(QLabel("<b>Ruta del archivo de video (.mp4, .mkv, .webm, etc.):</b>"))

        row_splash_path = QHBoxLayout()
        self.splash_path_edit = QLineEdit()
        self.splash_path_edit.setPlaceholderText("Ej: splash/splash-1920x1080.mp4")
        self.splash_path_edit.textChanged.connect(self._save_splash_settings)
        row_splash_path.addWidget(self.splash_path_edit, 1)

        btn_browse_splash = QPushButton("Examinar…")
        btn_browse_splash.clicked.connect(self._browse_splash_video)
        row_splash_path.addWidget(btn_browse_splash)

        btn_test_splash = QPushButton("▶ Probar video")
        btn_test_splash.clicked.connect(self._test_splash_video)
        row_splash_path.addWidget(btn_test_splash)

        v_splash_box.addLayout(row_splash_path)

        lbl_splash_hint = QLabel(
            "💡 <i>El video se reproducirá a pantalla completa al arrancar el Frontend antes de entrar a la biblioteca. "
            "Cualquier tecla, botón del gamepad o clic de ratón lo salteará al instante para ingresar directamente.</i>"
        )
        lbl_splash_hint.setStyleSheet("color: #718096; font-size: 8.5pt;")
        lbl_splash_hint.setWordWrap(True)
        v_splash_box.addWidget(lbl_splash_hint)

        v_splash.addWidget(self.splash_container)
        self.splash_container.setVisible(False)
        layout.addWidget(grp_splash)

        # -------------------------------------------------------------
        # 6. BOTÓN DE INICIO DEL FRONTEND
        # -------------------------------------------------------------
        btn_bar = QHBoxLayout()
        btn_bar.addStretch(1)

        self.btn_launch = QPushButton("▶  INICIAR FRONTEND EN PANTALLA COMPLETA")
        self.btn_launch.setObjectName("primary")
        self.btn_launch.setMinimumHeight(48)
        self.btn_launch.setMinimumWidth(360)
        self.btn_launch.setStyleSheet("""
            QPushButton#primary {
                background-color: #5d48d9;
                color: #ffffff;
                font-weight: bold;
                font-size: 11pt;
                border-radius: 8px;
                padding: 10px 24px;
            }
            QPushButton#primary:hover {
                background-color: #6d58ea;
            }
        """)
        self.btn_launch.clicked.connect(self._on_launch_clicked)
        btn_bar.addWidget(self.btn_launch)
        btn_bar.addStretch(1)

        layout.addLayout(btn_bar)
        layout.addStretch(1)

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    # -----------------------------------------------------------------
    # CARGA Y ACTUALIZACIÓN DE DATOS
    # -----------------------------------------------------------------
    def refresh_data(self):
        """Actualiza todas las listas, menús y configuraciones desde la base de datos."""
        self._updating = True
        try:
            lists = self.db.get_lists(with_counts=True)

            # 1. Selector de inicio
            self.startup_combo.clear()
            saved_startup = self.db.get_setting("frontend_startup_list", "")
            target_idx = 0

            for idx, r in enumerate(lists):
                lid = r["id"]
                name = r["name"]
                is_menu = (r["list_type"] == "menu") if "list_type" in r.keys() else False
                is_filtered = (r["list_type"] == "filtered") if "list_type" in r.keys() else False

                if is_menu:
                    sub_count = len(self.db.get_menu_items(lid))
                    text = f"🧭 [Menú de Sistemas]  {name}  ({sub_count} sistemas vinculados)"
                elif is_filtered:
                    g_count = r.get("game_count", 0)
                    plat = r.get("platform") or "Sin plataforma"
                    text = f"⚡ [Lista Filtrada]  {name}  ({g_count} juegos) — {plat}"
                else:
                    g_count = r.get("game_count", 0)
                    plat = r.get("platform") or "Sin plataforma"
                    text = f"🎮 [Lista de Juegos]  {name}  ({g_count} juegos) — {plat}"

                self.startup_combo.addItem(text, lid)
                if str(lid) == str(saved_startup):
                    target_idx = idx

            if self.startup_combo.count() > 0:
                self.startup_combo.setCurrentIndex(target_idx)

            # 2. Selector de menús
            self.menu_selector_combo.clear()
            menu_lists = [r for r in lists if ("list_type" in r.keys() and r["list_type"] == "menu")]

            for m in menu_lists:
                sub_count = len(self.db.get_menu_items(m["id"]))
                self.menu_selector_combo.addItem(f"🧭 {m['name']} ({sub_count} sistemas)", m["id"])

            if not menu_lists:
                self.menu_selector_combo.addItem("No hay menús de sistemas creados", None)
                self.menu_selector_combo.setEnabled(False)
            else:
                self.menu_selector_combo.setEnabled(True)

            # 3. Cargar video settings
            curr_mode = self.db.get_setting("video_mode", "fullscreen")
            idx_mode = self.mode_combo.findData(curr_mode)
            if idx_mode >= 0:
                self.mode_combo.setCurrentIndex(idx_mode)

            try:
                mon_idx = int(self.db.get_setting("video_monitor", "0"))
            except (ValueError, TypeError):
                mon_idx = 0
            if 0 <= mon_idx < self.screen_combo.count():
                self.screen_combo.setCurrentIndex(mon_idx)

            curr_res = self.db.get_setting("video_resolution", "system")
            if curr_res == "native":
                curr_res = "system"
            idx_res = self.res_combo.findData(curr_res)
            if idx_res >= 0:
                self.res_combo.setCurrentIndex(idx_res)
            else:
                idx_cust = self.res_combo.findData("custom")
                if idx_cust >= 0:
                    self.res_combo.setCurrentIndex(idx_cust)

            try:
                custom_w = int(self.db.get_setting("video_custom_width", "1920") or "1920")
                custom_h = int(self.db.get_setting("video_custom_height", "1080") or "1080")
            except (ValueError, TypeError):
                custom_w, custom_h = 1920, 1080
            self.spin_custom_w.setValue(custom_w)
            self.spin_custom_h.setValue(custom_h)
            self.custom_res_container.setVisible(self.res_combo.currentData() == "custom")
            self._update_system_res_label()

            # 4. Cargar configuración de Splash Screen
            splash_en = self.db.get_setting("frontend_splash_enabled", "false").strip().lower() in ("true", "1", "yes")
            self.chk_splash.setChecked(splash_en)
            self.splash_container.setVisible(splash_en)

            saved_splash = self.db.get_setting("frontend_splash_video", "").strip()
            if not saved_splash:
                from playnexus.ui.splash_screen import resolve_splash_video
                auto_vid = resolve_splash_video(self.db)
                if auto_vid:
                    try:
                        saved_splash = str(auto_vid.relative_to(APP_DIR)).replace("\\", "/")
                    except ValueError:
                        saved_splash = str(auto_vid).replace("\\", "/")
            self.splash_path_edit.setText(saved_splash)

        finally:
            self._updating = False

        self._sync_startup_item_details()
        self._refresh_sublists_table()

    def _on_startup_list_changed(self, index: int):
        if self._updating:
            return
        lid = self.startup_combo.currentData()
        if lid is not None:
            self.db.set_setting("frontend_startup_list", str(lid))

        self._sync_startup_item_details()

        # Si el inicio seleccionado es un menú, sincronizar el selector de menú
        row = self.db.get_list(lid)
        if row and ("list_type" in row.keys() and row["list_type"] == "menu"):
            idx = self.menu_selector_combo.findData(lid)
            if idx >= 0 and self.menu_selector_combo.currentIndex() != idx:
                self._updating = True
                self.menu_selector_combo.setCurrentIndex(idx)
                self._updating = False
                self._refresh_sublists_table()

    def _sync_startup_item_details(self):
        lid = self.startup_combo.currentData()
        if lid is None:
            self.startup_info_label.setText("No hay ninguna lista seleccionada.")
            return

        row = self.db.get_list(lid)
        if not row:
            return

        # Sincronizar combo de layout del inicio (Detalles no se permite en frontend)
        curr_layout = row["layout"] or "Wheel"
        if curr_layout == "Detalles":
            curr_layout = "Wheel"
        self.startup_layout_combo.blockSignals(True)
        idx = self.startup_layout_combo.findText(curr_layout)
        if idx >= 0:
            self.startup_layout_combo.setCurrentIndex(idx)
        else:
            self.startup_layout_combo.setCurrentText(curr_layout)
        self.startup_layout_combo.blockSignals(False)

        is_menu = (row["list_type"] == "menu") if "list_type" in row.keys() else False
        if is_menu:
            sub_items = self.db.get_menu_items(lid)
            self.startup_info_label.setText(
                f"🧭 <b>Menú de Sistemas:</b> Este elemento contiene <b>{len(sub_items)}</b> sistemas vinculados. "
                f"Al iniciar el frontend mostrará el diseño <i>{curr_layout}</i>, y al entrar a cualquiera de sus sistemas "
                f"mostrará el diseño configurado abajo en la tabla de sistemas."
            )
        else:
            g_count = self.db.count_games(lid)
            self.startup_info_label.setText(
                f"🎮 <b>Lista de Juegos:</b> Contiene <b>{g_count}</b> juegos. "
                f"Al iniciar el frontend mostrará directamente esta lista con el diseño <i>{curr_layout}</i>."
            )

    def _on_startup_layout_changed(self, new_layout: str):
        if self._updating:
            return
        lid = self.startup_combo.currentData()
        if lid is not None and new_layout:
            self.db.update_list(lid, layout=new_layout)
            self.layout_changed.emit(lid, new_layout)
            self._sync_startup_item_details()

    def _on_menu_selector_changed(self, index: int):
        if self._updating:
            return
        self._refresh_sublists_table()

    def _refresh_sublists_table(self):
        """Llena la tabla de sub-listas para el menú actualmente seleccionado."""
        menu_id = self.menu_selector_combo.currentData()
        if menu_id is None:
            self.sublists_table.setRowCount(0)
            self.sublists_table.setVisible(False)
            self.empty_menu_label.setText("No hay ningún Menú de Sistemas seleccionado.")
            self.empty_menu_label.setVisible(True)
            return

        sub_items = self.db.get_menu_items(menu_id)
        if not sub_items:
            self.sublists_table.setRowCount(0)
            self.sublists_table.setVisible(False)
            self.empty_menu_label.setText("Este menú no tiene sistemas vinculados actualmente. Podés agregarlos editando el menú en la Biblioteca.")
            self.empty_menu_label.setVisible(True)
            return

        self.empty_menu_label.setVisible(False)
        self.sublists_table.setVisible(True)
        self.sublists_table.setRowCount(len(sub_items))

        available_layouts = get_available_layouts(for_frontend=True)

        for row_idx, item in enumerate(sub_items):
            item_id = item["id"]
            name = item["name"]
            platform = item.get("platform") or "—"
            game_count = self.db.count_games(item_id)
            current_layout = item.get("layout") or "Wheel"
            if current_layout == "Detalles":
                current_layout = "Wheel"

            # 0. Nombre
            name_item = QTableWidgetItem(f"🎮  {name}")
            name_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.sublists_table.setItem(row_idx, 0, name_item)

            # 1. Plataforma
            plat_item = QTableWidgetItem(platform)
            plat_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.sublists_table.setItem(row_idx, 1, plat_item)

            # 2. Juegos
            count_item = QTableWidgetItem(f"{game_count} juegos")
            count_item.setTextAlignment(Qt.AlignCenter)
            count_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.sublists_table.setItem(row_idx, 2, count_item)

            # 3. Combo de diseño visual para este sistema
            layout_combo = QComboBox()
            layout_combo.addItems(available_layouts)
            idx_lay = layout_combo.findText(current_layout)
            if idx_lay >= 0:
                layout_combo.setCurrentIndex(idx_lay)
            else:
                layout_combo.setCurrentText(current_layout)

            # Conectar guardado inmediato al cambiar
            layout_combo.currentTextChanged.connect(
                lambda new_l, sid=item_id: self._on_sublist_layout_changed(sid, new_l)
            )
            self.sublists_table.setCellWidget(row_idx, 3, layout_combo)

            # 4. Emulador
            emu_id = item.get("default_emulator_id")
            emu_name = "Sin emulador"
            if emu_id:
                emu_data = self.db.get_emulator(emu_id)
                if emu_data:
                    emu_name = emu_data.get("name", "Asignado")
            emu_item = QTableWidgetItem(emu_name)
            emu_item.setForeground(Qt.gray)
            emu_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.sublists_table.setItem(row_idx, 4, emu_item)

    def _on_sublist_layout_changed(self, sub_list_id: int, new_layout: str):
        if self._updating or not new_layout:
            return
        self.db.update_list(sub_list_id, layout=new_layout)
        self.layout_changed.emit(sub_list_id, new_layout)

    def _on_res_changed(self):
        is_custom = (self.res_combo.currentData() == "custom")
        self.custom_res_container.setVisible(is_custom)
        self._save_video_settings()

    def _on_screen_changed(self):
        self._update_system_res_label()
        self._save_video_settings()

    def _update_system_res_label(self):
        screens = QGuiApplication.screens()
        mon_idx = self.screen_combo.currentData()
        if screens and isinstance(mon_idx, int) and 0 <= mon_idx < len(screens):
            scr = screens[mon_idx]
        else:
            scr = QGuiApplication.primaryScreen()

        if scr:
            geo = scr.geometry()
            rate = int(round(scr.refreshRate())) if scr.refreshRate() > 0 else 60
            text = f"Resolución del sistema ({geo.width()} x {geo.height()} @ {rate}Hz — {scr.name()})"
        else:
            text = "Resolución del sistema (Nativa del monitor)"

        if self.res_combo.count() > 0 and self.res_combo.itemData(0) == "system":
            self.res_combo.setItemText(0, text)

    def _save_video_settings(self):
        if self._updating:
            return
        mode = self.mode_combo.currentData()
        mon = self.screen_combo.currentData()
        res = self.res_combo.currentData()

        if mode is not None:
            self.db.set_setting("video_mode", str(mode))
        if mon is not None:
            self.db.set_setting("video_monitor", str(mon))
            self.db.set_setting("target_screen", str(mon))
        if res is not None:
            self.db.set_setting("video_resolution", str(res))
        if hasattr(self, "spin_custom_w") and hasattr(self, "spin_custom_h"):
            self.db.set_setting("video_custom_width", str(self.spin_custom_w.value()))
            self.db.set_setting("video_custom_height", str(self.spin_custom_h.value()))

    def _on_splash_toggled(self, checked: bool):
        self.splash_container.setVisible(checked)
        if checked and not self.splash_path_edit.text().strip():
            from playnexus.ui.splash_screen import resolve_splash_video
            auto_vid = resolve_splash_video(self.db)
            if auto_vid:
                try:
                    rel = str(auto_vid.relative_to(APP_DIR)).replace("\\", "/")
                except ValueError:
                    rel = str(auto_vid).replace("\\", "/")
                self.splash_path_edit.setText(rel)
        self._save_splash_settings()

    def _save_splash_settings(self):
        if self._updating:
            return
        enabled = self.chk_splash.isChecked()
        video_path = self.splash_path_edit.text().strip()
        self.db.set_setting("frontend_splash_enabled", "true" if enabled else "false")
        self.db.set_setting("frontend_splash_video", video_path)

    def _browse_splash_video(self):
        splash_dir = APP_DIR / "splash"
        start_dir = str(splash_dir if splash_dir.is_dir() else APP_DIR)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar video de presentación",
            start_dir,
            "Archivos de video (*.mp4 *.mkv *.avi *.webm *.mov *.wmv);;Todos los archivos (*.*)"
        )
        if path:
            p = Path(path)
            try:
                rel = p.relative_to(APP_DIR)
                self.splash_path_edit.setText(str(rel).replace("\\", "/"))
            except ValueError:
                self.splash_path_edit.setText(str(p).replace("\\", "/"))

    def _test_splash_video(self):
        path = self.splash_path_edit.text().strip()
        from playnexus.ui.splash_screen import resolve_splash_video, VideoSplashScreen
        video_file = resolve_splash_video(self.db, path)
        if not video_file or not video_file.is_file():
            QMessageBox.warning(self, "Video no encontrado", "No se encontró ningún archivo de video en la ruta especificada.")
            return
        geo = None
        mon_idx = self.screen_combo.currentData()
        screens = QGuiApplication.screens()
        if screens and isinstance(mon_idx, int) and 0 <= mon_idx < len(screens):
            geo = screens[mon_idx].geometry()
        elif screens:
            geo = screens[0].geometry()

        self._test_splash = VideoSplashScreen(video_file, target_geo=geo, db=self.db)
        self._test_splash.showFullScreen()
        self._test_splash.raise_()
        self._test_splash.activateWindow()
        self._test_splash.start_playback()

    def _on_launch_clicked(self):
        self._save_video_settings()
        self._save_splash_settings()
        self.launch_requested.emit()

