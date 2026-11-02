from pathlib import Path
import json
import shutil
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QGuiApplication, QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QDialogButtonBox, QFileDialog, QMessageBox, QHBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QGroupBox,
    QTextEdit, QAbstractItemView, QCheckBox, QSpinBox, QFrame,
    QListWidget, QListWidgetItem, QScrollArea, QProgressBar, QPlainTextEdit
)
from playnexus.services.library import (
    normalize_extensions, parse_extensions_list,
    parse_rom_folders, format_rom_folders,
    FILTERABLE_FIELDS, FILTER_OPERATORS, game_matches_filter,
    scan_rom_folder, import_scanned_games
)
from playnexus.services.themes import get_layout_media_spec

PRESET_EXTENSIONS = {
    "Personalizado...": ("", ""),
    "Juegos de PC / Windows (.lnk, .bat)": ("PC Games", ".lnk;.bat;.cmd;.exe"),
    "Super Nintendo (SNES)": ("Super Nintendo", ".sfc;.smc;.zip"),
    "Game Boy Advance (GBA)": ("Game Boy Advance", ".gba;.zip;.7z"),
    "PlayStation (PS1)": ("PlayStation", ".cue;.bin;.iso;.chd;.pbp"),
    "PlayStation 2 (PS2)": ("PlayStation 2", ".iso;.chd;.cso;.bin"),
    "Sega Genesis / Mega Drive": ("Mega Drive", ".md;.gen;.smd;.bin"),
    "Nintendo 64 (N64)": ("Nintendo 64", ".z64;.n64;.v64;.zip"),
    "Nintendo DS (NDS)": ("Nintendo DS", ".nds;.zip;.7z"),
    "PSP": ("PlayStation Portable", ".iso;.cso;.pbp"),
    "Arcade (MAME / FBNeo)": ("Arcade", ".zip;.7z;<DIR>")
}

class ListDialog(QDialog):
    """
    Diálogo para crear o editar una lista de juegos o un Menú de Sistemas (lista de listas).
    """
    def __init__(self, emulators, parent=None, existing=None, all_lists=None, initial_menu_items=None, db=None):
        super().__init__(parent)
        self.existing = existing
        self.all_lists = all_lists or []
        self.initial_menu_items = initial_menu_items or []
        self.db = db or getattr(parent, "db", None)
        self.filter_rule_rows = []
        self.setWindowTitle("Editar lista / menú" if existing else "Crear nueva lista / menú")
        self.setMinimumWidth(640)
        self.normalized_exts = ""

        # Layout principal del diálogo
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # Contenedor desplazable con soporte de rueda de ratón
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(10)

        # 1. Cabecera básica: Nombre, Tipo de Lista, Plataforma
        basic_group = QGroupBox("Información Principal")
        form = QFormLayout(basic_group)
        form.setSpacing(8)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ej: Super Nintendo, Menú de Consolas...")
        form.addRow("Nombre *", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItem("🎮 Lista de juegos (ROMs y emulador)", "games")
        self.type_combo.addItem("🧭 Menú de sistemas (Lista de listas)", "menu")
        self.type_combo.addItem("⚡ Lista filtrada (a partir de otra lista)", "filtered")
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Tipo de lista", self.type_combo)

        self.platform_edit = QLineEdit()
        self.platform_edit.setPlaceholderText("Ej: Super Nintendo, GBA, Arcade...")
        form.addRow("Plataforma o etiqueta", self.platform_edit)

        # Icono de la lista
        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("Icono de la lista (PNG, JPG, WebP)…")
        self.icon_path_edit.setReadOnly(True)
        icon_browse_btn = QPushButton("Elegir icono…")
        icon_browse_btn.clicked.connect(self.pick_icon)
        icon_clear_btn = QPushButton("✕")
        icon_clear_btn.setFixedWidth(28)
        icon_clear_btn.setToolTip("Quitar icono")
        icon_clear_btn.clicked.connect(lambda: self.icon_path_edit.clear())
        icon_row = QHBoxLayout()
        icon_row.setContentsMargins(0, 0, 0, 0)
        icon_row.addWidget(self.icon_path_edit, 1)
        icon_row.addWidget(icon_browse_btn)
        icon_row.addWidget(icon_clear_btn)
        icon_holder = QWidget()
        icon_holder.setLayout(icon_row)
        form.addRow("Icono de la lista", icon_holder)

        from playnexus.ui.layouts import get_available_layouts
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(get_available_layouts())
        form.addRow("Diseño visual", self.layout_combo)

        scroll_layout.addWidget(basic_group)

        # 2. Grupo para Lista de Juegos (ROMs, Emulador, Extensiones)
        self.game_settings_group = QGroupBox("Configuración de Juegos y Emulador")
        game_form = QFormLayout(self.game_settings_group)
        game_form.setSpacing(8)

        self.preset_combo = QComboBox()
        for title in PRESET_EXTENSIONS.keys():
            self.preset_combo.addItem(title)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        game_form.addRow("Plantilla sugerida", self.preset_combo)

        self.extensions_edit = QLineEdit()
        self.extensions_edit.setPlaceholderText("Ej: .zip;.7z;<DIR> o .cue;.chd (separadas por ;)")
        game_form.addRow("Extensiones admitidas *", self.extensions_edit)

        ext_hint = QLabel(
            "<b>Obligatorio:</b> Escribí las extensiones permitidas separadas <b>exclusivamente por punto y coma (;)</b>.<br>"
            "<i>Ejemplo: .zip;.7z;<DIR> (en MAME <code>&lt;DIR&gt;</code> toma las subcarpetas como ROMs cuando no tienen un .zip con su mismo nombre).</i>"
        )
        ext_hint.setStyleSheet("color: #aab1c0; font-size: 9pt;")
        ext_hint.setWordWrap(True)
        game_form.addRow("", ext_hint)

        # Selector múltiple de carpetas de juegos (ROMs)
        folders_vbox = QVBoxLayout()
        folders_vbox.setContentsMargins(0, 0, 0, 0)
        folders_vbox.setSpacing(6)

        folders_top_row = QHBoxLayout()
        folders_top_row.setContentsMargins(0, 0, 0, 0)
        self.folders_list = QListWidget()
        self.folders_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.folders_list.setFixedHeight(84)
        self.folders_list.setStyleSheet(
            "QListWidget { background-color: #171a23; border: 1px solid #2a3143; border-radius: 6px; padding: 3px; }"
            "QListWidget::item { padding: 3px 6px; border-radius: 4px; }"
            "QListWidget::item:hover { background-color: #23293a; }"
            "QListWidget::item:selected { background-color: #5d48d9; color: white; }"
        )
        folders_top_row.addWidget(self.folders_list, 1)

        folders_btns_col = QVBoxLayout()
        folders_btns_col.setContentsMargins(0, 0, 0, 0)
        folders_btns_col.setSpacing(4)
        browse_folder_btn = QPushButton("＋ Agregar carpeta…")
        browse_folder_btn.setToolTip("Elegir y agregar una carpeta de ROMs a la lista")
        browse_folder_btn.clicked.connect(self.pick_folder)
        remove_folder_btn = QPushButton("✕ Quitar seleccionada")
        remove_folder_btn.setToolTip("Quitar la carpeta seleccionada de la lista")
        remove_folder_btn.clicked.connect(self.remove_selected_folder)
        clear_folders_btn = QPushButton("Limpiar todas")
        clear_folders_btn.setToolTip("Vaciar todas las carpetas de ROMs configuradas")
        clear_folders_btn.clicked.connect(self.clear_folders)
        folders_btns_col.addWidget(browse_folder_btn)
        folders_btns_col.addWidget(remove_folder_btn)
        folders_btns_col.addWidget(clear_folders_btn)
        folders_btns_col.addStretch()
        folders_top_row.addLayout(folders_btns_col)
        folders_vbox.addLayout(folders_top_row)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Rutas de carpetas separadas por ; (o usá '＋ Agregar carpeta…')")
        self.folder_edit.textEdited.connect(self._on_folder_edit_changed)
        folders_vbox.addWidget(self.folder_edit)

        folder_holder = QWidget()
        folder_holder.setLayout(folders_vbox)
        game_form.addRow("Carpetas de juegos", folder_holder)

        self.auto_scan_checkbox = QCheckBox("Escanear e importar juegos de esta(s) carpeta(s) automáticamente")
        self.auto_scan_checkbox.setChecked(True if not existing else False)
        game_form.addRow("", self.auto_scan_checkbox)

        self.scan_subfolders_checkbox = QCheckBox("Buscar juegos en subcarpetas de forma recursiva")
        self.scan_subfolders_checkbox.setChecked(True)
        self.scan_subfolders_checkbox.setToolTip("Si está desmarcado, solo se escaneará la raíz de cada carpeta configurada.")
        game_form.addRow("Opciones de escaneo", self.scan_subfolders_checkbox)

        self.exclude_folder_if_zip_checkbox = QCheckBox("Si contiene archivo .zip, listar solo el .zip (excluir resto de la carpeta)")
        self.exclude_folder_if_zip_checkbox.setChecked(False)
        self.exclude_folder_if_zip_checkbox.setToolTip(
            "Si una carpeta contiene archivo(s) .zip o .7z, se lista únicamente el .zip y se excluye\n"
            "el resto de los archivos (bin, cue, chd, etc.) y subcarpetas que contiene."
        )
        game_form.addRow("", self.exclude_folder_if_zip_checkbox)

        self.xml_edit = QLineEdit()
        self.xml_edit.setPlaceholderText("Opcional: archivo .xml/.dat con nombres completos y datos de las ROMs...")
        browse_xml_btn = QPushButton("Examinar…")
        browse_xml_btn.clicked.connect(self.pick_xml)
        clear_xml_btn = QPushButton("✕")
        clear_xml_btn.setToolTip("Quitar archivo XML asociado")
        clear_xml_btn.setFixedWidth(28)
        clear_xml_btn.clicked.connect(lambda: self.xml_edit.clear())
        xml_row = QHBoxLayout()
        xml_row.setContentsMargins(0, 0, 0, 0)
        xml_row.addWidget(self.xml_edit, 1)
        xml_row.addWidget(browse_xml_btn)
        xml_row.addWidget(clear_xml_btn)
        xml_holder = QWidget()
        xml_holder.setLayout(xml_row)
        game_form.addRow("Archivo XML (Opcional)", xml_holder)

        xml_hint = QLabel(
            "<i>Asociá un archivo XML (MAME, HyperSpin, Arcade, Gamelist o DAT) cuando las ROMs "
            "solo tengan una denominación corta (ej: sf2.zip). El XML le asignará el nombre completo "
            "y todas sus propiedades (año, fabricante, género, jugadores, etc.).</i>"
        )
        xml_hint.setStyleSheet("color: #aab1c0; font-size: 8.5pt;")
        xml_hint.setWordWrap(True)
        game_form.addRow("", xml_hint)

        self.emulator_combo = QComboBox()
        self.emulator_combo.addItem("Sin emulador predeterminado", None)
        for e in emulators:
            self.emulator_combo.addItem(e["name"], e["id"])
        game_form.addRow("Emulador predeterminado", self.emulator_combo)

        scroll_layout.addWidget(self.game_settings_group)

        # 3. Grupo para Menú de Sistemas (Selección y orden de listas vinculadas)
        self.menu_settings_group = QGroupBox("Sistemas a incluir en este Menú")
        menu_layout = QVBoxLayout(self.menu_settings_group)
        menu_layout.setSpacing(8)

        menu_hint = QLabel("Marcá las listas que formarán parte de este menú y utilizá las flechas para definir el orden:")
        menu_hint.setStyleSheet("color: #aab1c0; font-size: 9pt;")
        menu_hint.setWordWrap(True)
        menu_layout.addWidget(menu_hint)

        list_and_controls = QHBoxLayout()
        self.sublists_list = QListWidget()
        self.sublists_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.sublists_list.setStyleSheet(
            "QListWidget { background-color: #171a23; border: 1px solid #2a3143; border-radius: 6px; padding: 4px; }"
            "QListWidget::item { padding: 4px; border-radius: 4px; }"
            "QListWidget::item:hover { background-color: #23293a; }"
            "QListWidget::item:selected { background-color: #5d48d9; color: white; }"
        )
        list_and_controls.addWidget(self.sublists_list, 1)

        # Botones de orden y selección
        btn_vbox = QVBoxLayout()
        btn_vbox.setSpacing(6)

        up_btn = QPushButton("▲ Subir")
        up_btn.clicked.connect(self._move_item_up)
        btn_vbox.addWidget(up_btn)

        down_btn = QPushButton("▼ Bajar")
        down_btn.clicked.connect(self._move_item_down)
        btn_vbox.addWidget(down_btn)

        btn_vbox.addSpacing(10)

        check_all_btn = QPushButton("Marcar todas")
        check_all_btn.clicked.connect(lambda: self._check_all_lists(True))
        btn_vbox.addWidget(check_all_btn)

        uncheck_all_btn = QPushButton("Desmarcar")
        uncheck_all_btn.clicked.connect(lambda: self._check_all_lists(False))
        btn_vbox.addWidget(uncheck_all_btn)

        btn_vbox.addStretch()
        list_and_controls.addLayout(btn_vbox)
        menu_layout.addLayout(list_and_controls)

        scroll_layout.addWidget(self.menu_settings_group)

        # 3. Grupo de Filtros de Juegos (Reglas dinámicas, aplicable a lista común y lista filtrada)
        self.filtered_settings_group = QGroupBox("Filtros de Juegos (Opcional)")
        filt_vbox = QVBoxLayout(self.filtered_settings_group)
        filt_vbox.setSpacing(10)

        self.filt_hint = QLabel(
            "<b>Opcional:</b> Podés definir una o varias reglas de filtrado para que solo se importen los juegos "
            "que cumplan los criterios seleccionados (ej: fabricante contiene 'Capcom', género contiene 'Lucha', "
            "sourcefile contiene 'cps1', clon está vacío para solo juegos principales, etc.). Si no agregás filtros, se importan todos los juegos encontrados."
        )
        self.filt_hint.setStyleSheet("color: #aab1c0; font-size: 8.5pt;")
        self.filt_hint.setWordWrap(True)
        filt_vbox.addWidget(self.filt_hint)

        filt_form = QFormLayout()
        filt_form.setSpacing(8)

        self.filter_source_label = QLabel("Lista de origen *")
        self.filter_source_combo = QComboBox()
        excluded_id = self.existing.get("id") if self.existing else None
        for l_item in self.all_lists:
            if l_item["id"] == excluded_id:
                continue
            if l_item.get("list_type") == "menu":
                continue
            self.filter_source_combo.addItem(f"🎮 {l_item['name']}", l_item["id"])
        self.filter_source_combo.currentIndexChanged.connect(self._on_filter_source_changed)
        filt_form.addRow(self.filter_source_label, self.filter_source_combo)

        self.filter_emulator_label = QLabel("Emulador")
        self.filter_emulator_combo = QComboBox()
        self.filter_emulator_combo.addItem("⚡ Heredar emulador de la lista origen", "INHERIT")
        for e in emulators:
            self.filter_emulator_combo.addItem(e["name"], e["id"])
        filt_form.addRow(self.filter_emulator_label, self.filter_emulator_combo)

        self.filter_match_mode_combo = QComboBox()
        self.filter_match_mode_combo.addItem("Cumplir todos los filtros (AND)", "all")
        self.filter_match_mode_combo.addItem("Cumplir cualquiera de los filtros (OR)", "any")
        self.filter_match_mode_combo.currentIndexChanged.connect(self._update_filter_preview)
        filt_form.addRow("Criterio de evaluación", self.filter_match_mode_combo)

        filt_vbox.addLayout(filt_form)

        # Encabezado de reglas de filtrado
        rules_header_layout = QHBoxLayout()
        rules_header_label = QLabel("<b>Reglas de Filtrado:</b>")
        self.add_filter_btn = QPushButton("＋ Agregar filtro")
        self.add_filter_btn.clicked.connect(lambda: self._add_filter_rule_row())
        rules_header_layout.addWidget(rules_header_label)
        rules_header_layout.addStretch()
        rules_header_layout.addWidget(self.add_filter_btn)
        filt_vbox.addLayout(rules_header_layout)

        self.filter_rules_container = QWidget()
        self.filter_rules_layout = QVBoxLayout(self.filter_rules_container)
        self.filter_rules_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_rules_layout.setSpacing(6)
        filt_vbox.addWidget(self.filter_rules_container)

        # Barra de vista previa en vivo
        preview_box = QHBoxLayout()
        self.filter_preview_label = QLabel("📊 Vista previa: Calculando...")
        self.filter_preview_label.setStyleSheet("color: #7dd3fc; font-weight: 500; font-size: 8.5pt;")
        preview_btn = QPushButton("🔄 Actualizar vista previa")
        preview_btn.setToolTip("Re-calcular juegos coincidentes con los filtros actuales")
        preview_btn.clicked.connect(self._update_filter_preview)
        preview_box.addWidget(self.filter_preview_label, 1)
        preview_box.addWidget(preview_btn)
        self.filter_preview_widget = QWidget()
        self.filter_preview_widget.setLayout(preview_box)
        filt_vbox.addWidget(self.filter_preview_widget)

        scroll_layout.addWidget(self.filtered_settings_group)

        # 4. Sección de Medios y Arte (especificada dinámicamente según el diseño visual)
        media_group = QGroupBox("Carpetas de Medios y Arte (Opcional)")
        self.media_group = media_group
        media_layout = QFormLayout(media_group)
        media_layout.setSpacing(8)

        # Contenedor wrapper para alojar el formulario dinámico de medios
        self.dynamic_media_wrapper = QWidget()
        self.dynamic_media_wrapper_layout = QVBoxLayout(self.dynamic_media_wrapper)
        self.dynamic_media_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.dynamic_media_wrapper_layout.setSpacing(0)
        media_layout.addRow(self.dynamic_media_wrapper)

        self.dynamic_media_container = None
        self.media_edits = {}
        self._media_values = {}

        scroll_layout.addWidget(media_group)

        # 5. Sección de Bezel HUD (Marco superpuesto en el emulador)
        bezel_hud_group = QGroupBox("Marco Decorativo / Bezel HUD (Superpuesto al Emulador)")
        bezel_hud_layout = QFormLayout(bezel_hud_group)
        bezel_hud_layout.setSpacing(8)

        self.bezel_hud_enabled_cb = QCheckBox("Activar Bezel HUD para esta lista")
        self.bezel_hud_enabled_cb.setStyleSheet("font-weight: 600;")
        self.bezel_hud_enabled_cb.setChecked(True)
        bezel_hud_layout.addRow(self.bezel_hud_enabled_cb)

        self.bezel_hud_path_edit = QLineEdit()
        self.bezel_hud_path_edit.setPlaceholderText("Carpeta con marcos transparentes PNG para el HUD")
        browse_hud_btn = QPushButton("Examinar…")
        browse_hud_btn.clicked.connect(self.pick_bezel_hud)
        hud_box = QHBoxLayout()
        hud_box.addWidget(self.bezel_hud_path_edit, 1)
        hud_box.addWidget(browse_hud_btn)
        hud_holder = QWidget()
        hud_holder.setLayout(hud_box)
        bezel_hud_layout.addRow("Carpeta Bezel HUD:", hud_holder)

        lbl_hud_hint = QLabel(
            "<i>Esta carpeta es independiente de los bezels del diseño visual (layout). "
            "Contiene las imágenes PNG con centro transparente para proyectar sobre el emulador al jugar. "
            "Busca primero por nombre de la ROM (ej: pacman.png) y si no existe usa default.png (o default_v.png para juegos con pantalla vertical).</i>"
        )
        lbl_hud_hint.setStyleSheet("color: #8f9aa9; font-size: 8.5pt;")
        lbl_hud_hint.setWordWrap(True)
        bezel_hud_layout.addRow(lbl_hud_hint)

        scroll_layout.addWidget(bezel_hud_group)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # 5. Botones de acción siempre fijos y visibles en la parte inferior
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        # Adaptar dinámicamente el tamaño inicial a la pantalla disponible
        screen = QGuiApplication.primaryScreen()
        if screen:
            avail_geo = screen.availableGeometry()
            target_h = min(680, int(avail_geo.height() * 0.85))
            self.resize(620, target_h)
        else:
            self.resize(620, 650)

        # Poblar listas vinculadas
        self._populate_sublists()

        # Cargar valores si es edición
        if existing:
            self.name_edit.setText(existing.get("name") or "")
            self.platform_edit.setText(existing.get("platform") or "")
            self.extensions_edit.setText(existing.get("allowed_extensions") or "")
            self._set_rom_folders(existing.get("roms_path") or "")
            scan_sub = str(existing.get("scan_subfolders", "true")).strip().lower() in ("true", "1")
            self.scan_subfolders_checkbox.setChecked(scan_sub)
            excl_zip = str(existing.get("exclude_folder_if_zip", "false")).strip().lower() in ("true", "1")
            self.exclude_folder_if_zip_checkbox.setChecked(excl_zip)
            if "xml_path" in existing.keys() and existing["xml_path"]:
                self.xml_edit.setText(existing["xml_path"])
            idx = self.emulator_combo.findData(existing.get("default_emulator_id"))
            if idx >= 0:
                self.emulator_combo.setCurrentIndex(idx)
            self.layout_combo.setCurrentText(existing.get("layout") or "Wheel")

            list_type = existing["list_type"] if "list_type" in existing.keys() else "games"
            idx_t = self.type_combo.findData(list_type)
            if idx_t >= 0:
                self.type_combo.setCurrentIndex(idx_t)

            if existing.get("icon_path"):
                self.icon_path_edit.setText(self._normalize_path(existing["icon_path"]))
            hud_en = str(existing.get("bezel_hud_enabled", "true")).strip().lower() in ("true", "1")
            self.bezel_hud_enabled_cb.setChecked(hud_en)
            if existing.get("bezel_hud_path"):
                self.bezel_hud_path_edit.setText(self._normalize_path(existing["bezel_hud_path"]))
            for k in ("boxart", "flyer", "wheel", "video", "cartart", "cabinet", "marquee", "bezel"):
                field_name = f"{k}_path"
                if field_name in existing.keys() and existing[field_name]:
                    self._media_values[k] = self._normalize_path(existing[field_name])

            if list_type in ("filtered", "games"):
                mode = existing.get("filter_match_mode", "all")
                idx_m = self.filter_match_mode_combo.findData(mode)
                if idx_m >= 0:
                    self.filter_match_mode_combo.setCurrentIndex(idx_m)

                raw_rules = existing.get("filter_rules", "[]")
                try:
                    rules_list = json.loads(raw_rules) if isinstance(raw_rules, str) else raw_rules
                except Exception:
                    rules_list = []
                for r_data in list(self.filter_rule_rows):
                    self._remove_filter_rule_row(r_data)
                if isinstance(rules_list, list) and rules_list:
                    for r in rules_list:
                        if isinstance(r, dict):
                            self._add_filter_rule_row(
                                field=r.get("field", "sourcefile"),
                                op=r.get("operator", "contains"),
                                val=r.get("value", "")
                            )
                elif list_type == "filtered":
                    self._add_filter_rule_row()

            if list_type == "filtered":
                src_id = existing.get("source_list_id")
                idx_s = self.filter_source_combo.findData(src_id)
                if idx_s >= 0:
                    self.filter_source_combo.setCurrentIndex(idx_s)

                emu_id = existing.get("default_emulator_id")
                idx_e = self.filter_emulator_combo.findData(emu_id)
                if idx_e >= 0:
                    self.filter_emulator_combo.setCurrentIndex(idx_e)
                else:
                    self.filter_emulator_combo.setCurrentIndex(0)
        else:
            self.type_combo.setCurrentIndex(0)
            self._add_filter_rule_row()

        # Conectar cambio de layout para reconstruir dinámicamente las carpetas de medios esperadas
        self.layout_combo.currentTextChanged.connect(self._rebuild_dynamic_media_ui)
        self._rebuild_dynamic_media_ui()

        self._on_type_changed()

    def _populate_sublists(self):
        self.sublists_list.clear()
        excluded_id = self.existing.get("id") if self.existing else None

        initial_ids = [m["id"] for m in self.initial_menu_items]
        # Mapa de todas las listas disponibles
        lists_map = {l["id"]: dict(l) for l in self.all_lists if l["id"] != excluded_id}

        # 1. Agregar primero las ya vinculadas en su orden guardado
        for m_id in initial_ids:
            if m_id in lists_map:
                l_info = lists_map.pop(m_id)
                self._add_sublist_item(l_info, checked=True)

        # 2. Agregar las restantes
        for l_info in lists_map.values():
            checked = (self.existing is None)
            self._add_sublist_item(l_info, checked=checked)

    def _add_sublist_item(self, list_info: dict, checked: bool):
        plat = list_info.get("platform") or "Sin definir"
        is_menu = (list_info.get("list_type") == "menu")
        prefix = "🧭 " if is_menu else "🎮 "
        item = QListWidgetItem(f"{prefix}{list_info['name']}   [{plat}]")
        item.setData(Qt.UserRole, list_info["id"])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.sublists_list.addItem(item)

    def _move_item_up(self):
        row = self.sublists_list.currentRow()
        if row > 0:
            item = self.sublists_list.takeItem(row)
            self.sublists_list.insertItem(row - 1, item)
            self.sublists_list.setCurrentRow(row - 1)

    def _move_item_down(self):
        row = self.sublists_list.currentRow()
        if row >= 0 and row < self.sublists_list.count() - 1:
            item = self.sublists_list.takeItem(row)
            self.sublists_list.insertItem(row + 1, item)
            self.sublists_list.setCurrentRow(row + 1)

    def _check_all_lists(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.sublists_list.count()):
            self.sublists_list.item(i).setCheckState(state)

    def _on_type_changed(self):
        curr_type = self.type_combo.currentData()
        is_menu = (curr_type == "menu")
        is_filtered = (curr_type == "filtered")
        is_games = (curr_type == "games")

        self.game_settings_group.setVisible(is_games)
        self.menu_settings_group.setVisible(is_menu)
        self.filtered_settings_group.setVisible(is_filtered or is_games)

        if hasattr(self, "filter_source_label"):
            self.filter_source_label.setVisible(is_filtered)
            self.filter_source_combo.setVisible(is_filtered)
        if hasattr(self, "filter_emulator_label"):
            self.filter_emulator_label.setVisible(is_filtered)
            self.filter_emulator_combo.setVisible(is_filtered)
        if hasattr(self, "filter_preview_widget"):
            self.filter_preview_widget.setVisible(is_filtered)

        if is_menu:
            if not self.platform_edit.text().strip():
                self.platform_edit.setText("Menú Principal")
            if not self.name_edit.text().strip():
                self.name_edit.setText("Sistemas")
        elif is_games:
            self.filtered_settings_group.setTitle("Filtros de Juegos (Opcional)")
            if hasattr(self, "filt_hint"):
                self.filt_hint.setText(
                    "<b>Opcional:</b> Podés definir una o varias reglas de filtrado para que solo se importen los juegos "
                    "que cumplan los criterios seleccionados (ej: fabricante contiene 'Capcom', género contiene 'Lucha', "
                    "sourcefile contiene 'cps1', clon está vacío para solo juegos principales, etc.). Si no agregás filtros, se importan todos los juegos encontrados."
                )
        elif is_filtered:
            self.filtered_settings_group.setTitle("Configuración de Lista Filtrada")
            if hasattr(self, "filt_hint"):
                self.filt_hint.setText(
                    "Una <b>Lista Filtrada</b> crea una lista dinámica a partir de otra lista de juegos existente, "
                    "evaluando uno o varios filtros según sus campos (sourcefile, género, fabricante, año, título, etc.)."
                )
            if not self.filter_rule_rows:
                self._add_filter_rule_row()
            self._on_filter_source_changed()

    def _add_filter_rule_row(self, field="sourcefile", op="contains", val=""):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        field_combo = QComboBox()
        for f_key, f_label in FILTERABLE_FIELDS:
            field_combo.addItem(f_label, f_key)
        idx = field_combo.findData(field)
        if idx >= 0:
            field_combo.setCurrentIndex(idx)

        op_combo = QComboBox()
        for o_key, o_label in FILTER_OPERATORS:
            op_combo.addItem(o_label, o_key)
        idx_o = op_combo.findData(op)
        if idx_o >= 0:
            op_combo.setCurrentIndex(idx_o)

        val_edit = QLineEdit(str(val or ""))
        val_edit.setPlaceholderText("Valor a buscar...")

        def _on_op_changed():
            curr_op = op_combo.currentData()
            if curr_op in ("is_empty", "is_not_empty"):
                val_edit.setEnabled(False)
                val_edit.setPlaceholderText("(Sin valor requerido)")
            else:
                val_edit.setEnabled(True)
                val_edit.setPlaceholderText("Valor a buscar...")
            self._update_filter_preview()

        op_combo.currentIndexChanged.connect(_on_op_changed)
        field_combo.currentIndexChanged.connect(self._update_filter_preview)
        val_edit.textChanged.connect(self._update_filter_preview)
        _on_op_changed()

        del_btn = QPushButton("✕")
        del_btn.setToolTip("Quitar esta regla")
        del_btn.setFixedWidth(28)
        del_btn.setStyleSheet(
            "QPushButton { color: #f87171; font-weight: bold; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover { background-color: #ef4444; color: white; }"
        )

        row_data = {
            "widget": row_widget,
            "field_combo": field_combo,
            "op_combo": op_combo,
            "val_edit": val_edit,
        }
        del_btn.clicked.connect(lambda: self._remove_filter_rule_row(row_data))

        row_layout.addWidget(field_combo, 3)
        row_layout.addWidget(op_combo, 2)
        row_layout.addWidget(val_edit, 4)
        row_layout.addWidget(del_btn)

        self.filter_rule_rows.append(row_data)
        self.filter_rules_layout.addWidget(row_widget)
        self._update_filter_preview()

    def _remove_filter_rule_row(self, row_data):
        if row_data in self.filter_rule_rows:
            self.filter_rule_rows.remove(row_data)
            row_data["widget"].setParent(None)
            row_data["widget"].deleteLater()
            self._update_filter_preview()

    def _get_filter_rules_from_ui(self) -> list[dict]:
        rules = []
        for r in self.filter_rule_rows:
            rules.append({
                "field": r["field_combo"].currentData(),
                "operator": r["op_combo"].currentData(),
                "value": r["val_edit"].text().strip(),
            })
        return rules

    def _normalize_path(self, path_str: str | None) -> str:
        if not path_str:
            return ""
        return str(path_str).strip().replace("\\", "/")

    def _on_filter_source_changed(self):
        source_id = self.filter_source_combo.currentData()
        if source_id and self.db:
            src_list = self.db.get_list(source_id)
            if src_list:
                if not self.platform_edit.text().strip():
                    self.platform_edit.setText(src_list.get("platform", ""))
                pass  # media_path ya no se usa como campo global
                for k in ("boxart", "flyer", "wheel", "video", "cartart", "cabinet", "marquee", "bezel"):
                    src_k = f"{k}_path"
                    if src_k in src_list and src_list[src_k] and k not in self._media_values:
                        val = self._normalize_path(src_list[src_k])
                        self._media_values[k] = val
                        if k in self.media_edits:
                            self.media_edits[k].setText(val)
        self._update_filter_preview()

    def _update_filter_preview(self):
        if not hasattr(self, "filter_preview_label") or not hasattr(self, "filter_source_combo"):
            return
        source_id = self.filter_source_combo.currentData()
        if not source_id or not self.db:
            self.filter_preview_label.setText("📊 Vista previa: Seleccioná una lista origen.")
            return

        source_games = self.db.get_games(source_id, enriched=False)
        total = len(source_games)
        rules = self._get_filter_rules_from_ui()
        mode = self.filter_match_mode_combo.currentData() or "all"
        matching_count = sum(1 for g in source_games if game_matches_filter(g, rules, mode))
        self.filter_preview_label.setText(
            f"📊 Vista previa: <b>{matching_count}</b> de <b>{total}</b> juegos coinciden con los filtros actuales."
        )

    def _rebuild_dynamic_media_ui(self):
        """
        Reconstruye dinámicamente las filas de medios según lo especificado en el layout.json
        (o especificación estándar) del diseño visual seleccionado.
        Muestra únicamente los campos solicitados por dicho diseño junto con las extensiones esperadas.
        """
        # 1. Guardar cualquier cambio actual que haya introducido el usuario
        for key, edit in self.media_edits.items():
            self._media_values[key] = self._normalize_path(edit.text())

        # 2. Reemplazar contenedor dinámico limpiamente
        if hasattr(self, "dynamic_media_container") and self.dynamic_media_container is not None:
            self.dynamic_media_container.setParent(None)
            self.dynamic_media_container.deleteLater()

        self.dynamic_media_container = QWidget()
        dynamic_layout = QFormLayout(self.dynamic_media_container)
        dynamic_layout.setContentsMargins(0, 0, 0, 0)
        dynamic_layout.setSpacing(8)
        self.dynamic_media_wrapper_layout.addWidget(self.dynamic_media_container)

        self.media_edits.clear()

        # 3. Leer especificación del diseño visual actual
        layout_name = self.layout_combo.currentText()
        spec = get_layout_media_spec(layout_name)

        # 4. Crear solo las filas que el diseño requiere
        for item in spec:
            key = item.get("key", "")
            label = item.get("label", key.capitalize())
            folder_name = item.get("folder", key)
            exts = item.get("extensions", [])
            req = item.get("required", False)

            ext_str = ", ".join(exts) if exts else ""
            req_marker = " *" if req else ""
            if ext_str:
                label_text = f"{label} ({ext_str}){req_marker}:"
            else:
                label_text = f"{label}{req_marker}:"

            edit = QLineEdit()
            edit.setPlaceholderText(f"Carpeta de {label} (ej: media/{folder_name})...")
            
            init_val = self._media_values.get(key, "")
            if init_val:
                edit.setText(init_val)

            edit.textChanged.connect(lambda txt, k=key: self._media_values.__setitem__(k, self._normalize_path(txt)))
            edit.editingFinished.connect(lambda e=edit: e.setText(self._normalize_path(e.text())))

            browse_btn = QPushButton("Examinar…")
            browse_btn.clicked.connect(lambda checked=False, e=edit, l=label, k=key: self._pick_media_folder(e, f"Seleccionar carpeta de {l}", k))

            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(edit, 1)
            row_layout.addWidget(browse_btn)

            row_widget = QWidget()
            row_widget.setLayout(row_layout)

            dynamic_layout.addRow(label_text, row_widget)
            self.media_edits[key] = edit

    @property
    def boxart_edit(self):
        return self.media_edits.get("boxart")

    @property
    def flyer_edit(self):
        return self.media_edits.get("flyer")

    @property
    def wheel_edit(self):
        return self.media_edits.get("wheel")

    @property
    def video_edit(self):
        return self.media_edits.get("video")

    @property
    def cartart_edit(self):
        return self.media_edits.get("cartart")

    def _set_rom_folders(self, folders_raw):
        """Establece las carpetas de ROMs en el listado visual y en el campo de texto."""
        folders = parse_rom_folders(folders_raw)
        self._sync_folders_list_from_list(folders)
        self.folder_edit.blockSignals(True)
        self.folder_edit.setText(format_rom_folders(folders))
        self.folder_edit.blockSignals(False)

    def _sync_folders_list_from_list(self, folders: list[str]):
        """Actualiza el QListWidget con la lista de carpetas de ROMs."""
        self.folders_list.clear()
        for f in folders:
            item = QListWidgetItem(f"📁  {f}")
            item.setData(Qt.UserRole, f)
            self.folders_list.addItem(item)

    def _on_folder_edit_changed(self, text: str):
        """Sincroniza el QListWidget cuando el usuario edita manualmente las rutas separadas por ';'."""
        folders = parse_rom_folders(text)
        self._sync_folders_list_from_list(folders)

    def get_rom_folders(self) -> list[str]:
        """Retorna la lista de carpetas de ROMs configuradas."""
        if hasattr(self, "folders_list") and self.folders_list.count() > 0:
            res = []
            for i in range(self.folders_list.count()):
                f = self.folders_list.item(i).data(Qt.UserRole)
                if f and f not in res:
                    res.append(f)
            return res
        return parse_rom_folders(self.folder_edit.text().strip())

    def _get_primary_rom_folder(self) -> str:
        """Retorna la primera carpeta de ROMs configurada (para directorio inicial en diálogos)."""
        folders = self.get_rom_folders()
        return folders[0] if folders else ""

    def remove_selected_folder(self):
        """Quita la carpeta seleccionada de la lista."""
        row = self.folders_list.currentRow()
        if row < 0 and self.folders_list.count() > 0:
            row = self.folders_list.count() - 1
        if row >= 0:
            self.folders_list.takeItem(row)
            folders = [self.folders_list.item(i).data(Qt.UserRole) for i in range(self.folders_list.count())]
            self.folder_edit.blockSignals(True)
            self.folder_edit.setText(format_rom_folders(folders))
            self.folder_edit.blockSignals(False)

    def clear_folders(self):
        """Limpia todas las carpetas de ROMs configuradas."""
        self._set_rom_folders([])

    def _pick_media_folder(self, target_edit, dialog_title, key=None):
        current = target_edit.text().strip() or self._get_primary_rom_folder()
        folder = QFileDialog.getExistingDirectory(self, dialog_title, current or "")
        if folder:
            norm_folder = self._normalize_path(folder)
            target_edit.setText(norm_folder)
            if key:
                self._media_values[key] = norm_folder
            for k, ed in self.media_edits.items():
                if ed == target_edit:
                    self._media_values[k] = norm_folder

    def pick_icon(self):
        """Abre un selector de archivo para elegir el icono de la lista."""
        current = self.icon_path_edit.text().strip() if hasattr(self, "icon_path_edit") else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar icono de la lista",
            str(Path(current).parent) if current and Path(current).parent.is_dir() else "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp *.svg);;Todos (*.*)"
        )
        if path:
            self.icon_path_edit.setText(self._normalize_path(path))

    def pick_bezel_hud(self):
        """Abre un selector para elegir la carpeta del Bezel HUD."""
        current = self.bezel_hud_path_edit.text().strip() if hasattr(self, "bezel_hud_path_edit") else ""
        initial_dir = current if (current and Path(current).is_dir()) else self._get_primary_rom_folder()
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta para Bezel HUD", initial_dir or "")
        if path:
            self.bezel_hud_path_edit.setText(self._normalize_path(path))

    def pick_folder(self):
        current_folders = self.get_rom_folders()
        initial_dir = current_folders[-1] if current_folders else ""
        if initial_dir and Path(initial_dir).parent.is_dir():
            initial_dir = str(Path(initial_dir).parent)
        folder = QFileDialog.getExistingDirectory(
            self,
            "Agregar carpeta de juegos (ROMs)",
            initial_dir or ""
        )
        if folder:
            current_folders.append(self._normalize_path(folder))
            self._set_rom_folders(current_folders)
            self.auto_scan_checkbox.setChecked(True)

    def pick_xml(self):
        current_xml = self.xml_edit.text().strip()
        initial_dir = str(Path(current_xml).parent) if (current_xml and Path(current_xml).parent.is_dir()) else self._get_primary_rom_folder()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo XML de nombres y datos de ROMs",
            initial_dir or "",
            "Archivos XML / DAT (*.xml *.dat);;Todos los archivos (*.*)"
        )
        if path:
            self.xml_edit.setText(self._normalize_path(path))

    def _on_preset_selected(self, index):
        title = self.preset_combo.currentText()
        if title in PRESET_EXTENSIONS and title != "Personalizado...":
            plat, exts = PRESET_EXTENSIONS[title]
            if not self.platform_edit.text().strip():
                self.platform_edit.setText(plat)
            self.extensions_edit.setText(exts)

    def validate_and_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nombre requerido", "Por favor ingresá un nombre para la lista.")
            self.name_edit.setFocus()
            return

        is_menu = (self.type_combo.currentData() == "menu")
        is_filtered = (self.type_combo.currentData() == "filtered")
        if is_menu:
            checked_count = sum(1 for i in range(self.sublists_list.count()) if self.sublists_list.item(i).checkState() == Qt.Checked)
            if checked_count == 0:
                answer = QMessageBox.question(
                    self,
                    "Menú sin sistemas",
                    "No seleccionaste ninguna lista para incluir en este menú.\n¿Deseas crearlo de todas formas y vincular sistemas luego?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if answer != QMessageBox.Yes:
                    return
            self.accept()
            return

        if is_filtered:
            source_id = self.filter_source_combo.currentData()
            if not source_id:
                QMessageBox.warning(self, "Lista origen requerida", "Por favor seleccioná la lista de origen de la cual se filtrarán los juegos.")
                self.filter_source_combo.setFocus()
                return

            rules = self._get_filter_rules_from_ui()
            valid_rules = [
                r for r in rules
                if r["operator"] in ("is_empty", "is_not_empty") or r["value"].strip()
            ]
            if not valid_rules:
                QMessageBox.warning(
                    self,
                    "Filtro requerido",
                    "Por favor configurá al menos una regla de filtrado con un valor (ej: sourcefile contiene 'cps1')."
                )
                return
            self.accept()
            return

        raw_exts = self.extensions_edit.text().strip()
        try:
            normalized, warnings = normalize_extensions(raw_exts)
            self.normalized_exts = normalized
        except ValueError as err:
            QMessageBox.warning(
                self,
                "Error en las extensiones",
                f"Configuración de extensiones inválida:\n\n{err}"
            )
            self.extensions_edit.setFocus()
            return

        # Validar carpetas de juegos si fueron especificadas
        folders = self.get_rom_folders()
        for f in folders:
            if not Path(f).is_dir():
                QMessageBox.warning(
                    self,
                    "Carpeta no encontrada",
                    f"La carpeta especificada no existe o no es accesible:\n{f}\n\nPor favor seleccioná carpetas válidas."
                )
                self.folder_edit.setFocus()
                return

        # Validar archivo XML si fue especificado
        xml_path = self.xml_edit.text().strip() if hasattr(self, "xml_edit") else ""
        if xml_path:
            if not Path(xml_path).is_file():
                QMessageBox.warning(
                    self,
                    "Archivo XML no encontrado",
                    f"El archivo XML especificado no existe o no es accesible:\n{xml_path}\n\nPor favor seleccioná un archivo XML válido."
                )
                self.xml_edit.setFocus()
                return

        # Si hay advertencias (ejemplo: extensión genérica .bin)
        if warnings:
            warn_msg = "\n\n".join(warnings)
            answer = QMessageBox.question(
                self,
                "Aviso sobre extensiones configuradas",
                f"{warn_msg}\n\n¿Deseas continuar con esta configuración?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if answer != QMessageBox.Yes:
                return

        self.accept()

    def values(self):
        """Retorna tupla con todos los valores configurados de la lista o menú."""
        list_type = self.type_combo.currentData() if hasattr(self, "type_combo") else "games"
        selected_ids = []
        if list_type == "menu" and hasattr(self, "sublists_list"):
            for i in range(self.sublists_list.count()):
                item = self.sublists_list.item(i)
                if item.checkState() == Qt.Checked:
                    selected_ids.append(item.data(Qt.UserRole))

        # Sincronizar últimos valores de los edits
        for k, ed in self.media_edits.items():
            self._media_values[k] = self._normalize_path(ed.text())

        media_path = ""  # ya no se usa campo raíz global; cada carpeta se elige individualmente
        boxart_path = self._media_values.get("boxart", "")
        flyer_path = self._media_values.get("flyer", "")
        wheel_path = self._media_values.get("wheel", "")
        video_path = self._media_values.get("video", "")
        cartart_path = self._media_values.get("cartart", "")
        cabinet_path = self._media_values.get("cabinet", "")
        marquee_path = self._media_values.get("marquee", "")
        bezel_path = self._media_values.get("bezel", "")
        xml_path = self._normalize_path(self.xml_edit.text().strip()) if (list_type == "games" and hasattr(self, "xml_edit")) else ""
        roms_path_val = format_rom_folders(self.get_rom_folders()) if list_type == "games" else ""
        icon_path = self._normalize_path(self.icon_path_edit.text().strip()) if hasattr(self, "icon_path_edit") else ""

        # Determinar emulador efectivo
        if list_type == "games":
            emu_val = self.emulator_combo.currentData()
        elif list_type == "filtered":
            raw_f_emu = self.filter_emulator_combo.currentData()
            if raw_f_emu == "INHERIT":
                src_id = self.filter_source_combo.currentData()
                src_row = self.db.get_list(src_id) if (self.db and src_id) else None
                emu_val = src_row.get("default_emulator_id") if src_row else None
            else:
                emu_val = raw_f_emu
        else:
            emu_val = None

        if list_type in ("filtered", "games"):
            raw_rules = self._get_filter_rules_from_ui()
            filter_rules = [
                r for r in raw_rules
                if r.get("operator") in ("is_empty", "is_not_empty") or (r.get("value") and str(r.get("value")).strip())
            ]
            filter_match_mode = self.filter_match_mode_combo.currentData() if hasattr(self, "filter_match_mode_combo") else "all"
        else:
            filter_rules = []
            filter_match_mode = "all"
        filter_rules_json = json.dumps(filter_rules, ensure_ascii=False)
        source_list_id = self.filter_source_combo.currentData() if list_type == "filtered" else None

        return (
            self.name_edit.text().strip(),
            self.platform_edit.text().strip(),
            emu_val,
            self.layout_combo.currentText(),
            self.normalized_exts if list_type == "games" else "",
            roms_path_val,
            self.auto_scan_checkbox.isChecked() if list_type == "games" else False,
            media_path,
            boxart_path,
            wheel_path,
            video_path,
            cartart_path,
            list_type,
            selected_ids,
            cabinet_path,
            marquee_path,
            xml_path,
            bezel_path,
            self.scan_subfolders_checkbox.isChecked() if list_type == "games" else True,
            self.exclude_folder_if_zip_checkbox.isChecked() if list_type == "games" else False,
            source_list_id,
            filter_rules_json,
            filter_match_mode,
            flyer_path,
            icon_path,
            "true" if self.bezel_hud_enabled_cb.isChecked() else "false",
            self._normalize_path(self.bezel_hud_path_edit.text().strip()),
        )



class EmulatorDialog(QDialog):
    """Diálogo para registrar o editar un emulador."""
    def __init__(self, parent=None, existing=None):
        super().__init__(parent)
        self.setWindowTitle("Editar emulador" if existing else "Registrar emulador")
        self.setMinimumWidth(560)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Ej: RetroArch, Snes9x, PCSX2, DuckStation...")
        self.exe = QLineEdit()
        self.exe.setPlaceholderText("Ruta al archivo ejecutable (.exe)")
        self.args = QLineEdit('"{rom}"')
        self.platform = QLineEdit()
        self.platform.setPlaceholderText("Ej: Super Nintendo, Multi-sistema...")

        browse = QPushButton("Examinar…")
        browse.clicked.connect(self.pick_exe)

        exe_row = QHBoxLayout()
        exe_row.addWidget(self.exe, 1)
        exe_row.addWidget(browse)

        holder = QWidget()
        holder.setLayout(exe_row)

        form = QFormLayout()

        # Selector de plantilla rápida
        presets_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("— Seleccionar una plantilla rápida… —", None)
        self._load_presets()
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        presets_row.addWidget(self.preset_combo, 1)
        form.addRow("Plantilla rápida", presets_row)

        form.addRow("Nombre del emulador *", self.name)
        form.addRow("Ejecutable (.exe) *", holder)
        form.addRow("Argumentos de inicio", self.args)
        form.addRow("Plataforma (opcional)", self.platform)

        hint = QLabel(
            "<b>Plantillas de argumentos admitidas:</b><br>"
            "<code>{rom}</code> o <code>[romfilename]</code>: Ruta completa al archivo del juego.<br>"
            "<code>{rom_dir}</code> o <code>[rompath]</code>: Carpeta donde se ubica el juego.<br>"
            "<code>{rom_name}</code> o <code>[name]</code>: Nombre del archivo sin extensión.<br>"
            "<i>• Para Juegos de Windows (Attract-Mode / PC): Ejecutable <code>cmd</code> y argumentos <code>/c \"[romfilename]\"</code></i><br>"
            "<i>• Para RetroArch: <code>-f -L cores\\genesis_plus_gx_sot4w_libretro.dll \"{rom}\"</code></i>"
        )
        hint.setStyleSheet("color: #aab1c0; font-size: 9pt;")

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if existing:
            self.name.setText(existing["name"])
            self.exe.setText(existing["executable"])
            self.args.setText(existing["arguments"])
            self.platform.setText(existing["platform"] or "")

    def _load_presets(self):
        try:
            from playnexus.services.emulator_templates import load_emulator_templates
            templates = load_emulator_templates()
            for tmpl in templates:
                plat_str = f" [{tmpl['platform']}]" if tmpl.get("platform") else ""
                self.preset_combo.addItem(f"{tmpl['name']}{plat_str}", tmpl)
        except Exception as e:
            print(f"Error cargando plantillas de emuladores: {e}")

    def _on_preset_selected(self, index: int):
        tmpl = self.preset_combo.currentData()
        if not tmpl:
            return
        self.name.setText(tmpl.get("name", ""))
        self.exe.setText(tmpl.get("executable", ""))
        self.args.setText(tmpl.get("arguments", ""))
        if tmpl.get("platform"):
            self.platform.setText(tmpl.get("platform", ""))

    def _preset_windows_cmd(self):
        if not self.name.text().strip():
            self.name.setText("Juegos de Windows (cmd)")
        self.exe.setText("cmd")
        self.args.setText('/c "[romfilename]"')
        if not self.platform.text().strip():
            self.platform.setText("PC Games")

    def pick_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar ejecutable del emulador",
            "",
            "Archivos ejecutables (*.exe *.bat *.cmd);;Todos los archivos (*.*)"
        )
        if path:
            self.exe.setText(path)

    def validate_accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Dato requerido", "Por favor ingresá un nombre para el emulador.")
            self.name.setFocus()
            return
        raw_exe = self.exe.text().strip()
        if not raw_exe:
            QMessageBox.warning(self, "Dato requerido", "Por favor seleccioná la ruta al archivo ejecutable.")
            self.exe.setFocus()
            return

        exe_path = Path(raw_exe)
        if not exe_path.is_file() and not shutil.which(raw_exe):
            confirm = QMessageBox.question(
                self,
                "Ejecutable no encontrado",
                f"El archivo ejecutable no se encuentra actualmente en la ruta indicada ni en el PATH del sistema:\n{raw_exe}\n\n¿Deseas guardarlo de todos modos?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return

        self.accept()

    def values(self):
        return (
            self.name.text().strip(),
            self.exe.text().strip(),
            self.args.text().strip() or '"{rom}"',
            self.platform.text().strip()
        )


class TemplateEditDialog(QDialog):
    """Diálogo modal para crear o editar una plantilla rápida de emulador."""
    def __init__(self, parent=None, existing=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Plantilla de Emulador" if existing else "Nueva Plantilla de Emulador")
        self.setMinimumWidth(540)

        self.name_edit = QLineEdit(existing.get("name", "") if existing else "")
        self.name_edit.setPlaceholderText("Ej: RetroArch - Genesis Plus GX, DuckStation, PCSX2...")

        self.exe_edit = QLineEdit(existing.get("executable", "") if existing else "")
        self.exe_edit.setPlaceholderText("Ej: retroarch.exe, cmd, pcsx2-qtx64.exe...")
        browse_btn = QPushButton("Examinar…")
        browse_btn.clicked.connect(self._pick_exe)
        exe_row = QHBoxLayout()
        exe_row.addWidget(self.exe_edit, 1)
        exe_row.addWidget(browse_btn)
        exe_holder = QWidget()
        exe_holder.setLayout(exe_row)

        self.args_edit = QLineEdit(existing.get("arguments", "") if existing else '"{rom}"')
        self.args_edit.setPlaceholderText('Ej: -f -L cores\\core.dll "{rom}" o /c "[romfilename]"')

        self.plat_edit = QLineEdit(existing.get("platform", "") if existing else "")
        self.plat_edit.setPlaceholderText("Ej: Multi-sistema, PC Games, Arcade, Super Nintendo...")

        self.desc_edit = QLineEdit(existing.get("description", "") if existing else "")
        self.desc_edit.setPlaceholderText("Descripción breve o notas sobre la plantilla")

        form = QFormLayout()
        form.addRow("Nombre de la plantilla *", self.name_edit)
        form.addRow("Ejecutable (.exe / comando) *", exe_holder)
        form.addRow("Argumentos de inicio", self.args_edit)
        form.addRow("Plataforma", self.plat_edit)
        form.addRow("Descripción", self.desc_edit)

        hint = QLabel(
            "<b>Comodines de argumentos admitidos:</b><br>"
            "<code>{rom}</code> o <code>[romfilename]</code>: Ruta completa al archivo del juego.<br>"
            "<code>{rom_dir}</code> o <code>[rompath]</code>: Carpeta donde reside el juego.<br>"
            "<code>{rom_name}</code> o <code>[name]</code>: Nombre del juego sin extensión."
        )
        hint.setStyleSheet("color: #aab1c0; font-size: 8.5pt;")
        hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar ejecutable",
            "",
            "Archivos ejecutables (*.exe *.bat *.cmd);;Todos los archivos (*.*)"
        )
        if path:
            self.exe_edit.setText(path)

    def _validate(self):
        name = self.name_edit.text().strip()
        exe = self.exe_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Dato requerido", "Ingresá un nombre para la plantilla.")
            self.name_edit.setFocus()
            return
        if not exe:
            QMessageBox.warning(self, "Dato requerido", "Ingresá o seleccioná un ejecutable para la plantilla.")
            self.exe_edit.setFocus()
            return
        self.accept()

    def values(self) -> dict[str, str]:
        return {
            "name": self.name_edit.text().strip(),
            "executable": self.exe_edit.text().strip(),
            "arguments": self.args_edit.text().strip(),
            "platform": self.plat_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
        }


class EmulatorManagerWidget(QWidget):
    """Panel de administración completa de emuladores para pestaña o ventana."""
    emulators_changed = Signal()

    def __init__(self, db, parent=None, is_dialog=False):
        super().__init__(parent)
        self.db = db
        self.is_dialog = is_dialog
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Encabezado informativo (solo visible en modo pestaña integrada)
        if not self.is_dialog:
            header_card = QFrame()
            header_card.setStyleSheet("background-color: #1b1e2a; border-radius: 8px; padding: 12px;")
            h_layout = QVBoxLayout(header_card)
            title = QLabel("🕹 Administrador de Emuladores")
            title.setFont(QFont("Segoe UI", 16, QFont.Bold))
            title.setStyleSheet("color: #ffffff;")
            h_layout.addWidget(title)

            desc = QLabel(
                "Registrá y administrá los emuladores instalados en tu sistema. "
                "Podés vincular ejecutables, plataformas y parámetros de línea de comandos para cada emulador."
            )
            desc.setStyleSheet("color: #9aa5b8; font-size: 10pt;")
            desc.setWordWrap(True)
            h_layout.addWidget(desc)
            layout.addWidget(header_card)

        # Tabla de emuladores
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nombre", "Plataforma", "Ejecutable", "Argumentos"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_selected)
        layout.addWidget(self.table, 1)

        # Barra de botones
        btn_row = QHBoxLayout()
        add_btn = QPushButton("＋ Registrar nuevo emulador")
        add_btn.setStyleSheet("background-color: #5d48d9; color: #ffffff; font-weight: bold; padding: 8px 16px; border-radius: 6px;")
        add_btn.clicked.connect(self.add_emulator)

        edit_btn = QPushButton("✎ Editar seleccionado")
        edit_btn.clicked.connect(self.edit_selected)

        del_btn = QPushButton("🗑 Eliminar seleccionado")
        del_btn.clicked.connect(self.delete_selected)

        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()

        layout.addLayout(btn_row)

    def refresh(self):
        rows = self.db.get_emulators()
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            name_item = QTableWidgetItem(row["name"])
            name_item.setData(Qt.UserRole, row["id"])
            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, QTableWidgetItem(row["platform"] or "—"))
            self.table.setItem(i, 2, QTableWidgetItem(row["executable"]))
            self.table.setItem(i, 3, QTableWidgetItem(row["arguments"]))

    def _get_selected_id(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        return self.table.item(selected[0].row(), 0).data(Qt.UserRole)

    def add_emulator(self):
        dialog = EmulatorDialog(self)
        if dialog.exec():
            name, exe, args, plat = dialog.values()
            try:
                self.db.add_emulator(name=name, executable=exe, arguments=args, platform=plat)
                self.refresh()
                self.emulators_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error al registrar", f"No se pudo guardar el emulador:\n{e}")

    def edit_selected(self):
        emu_id = self._get_selected_id()
        if not emu_id:
            QMessageBox.information(self, "Seleccionar", "Seleccioná un emulador de la lista para editar.")
            return
        row = self.db.get_emulator(emu_id)
        if not row:
            return
        dialog = EmulatorDialog(self, existing=row)
        if dialog.exec():
            name, exe, args, plat = dialog.values()
            try:
                self.db.update_emulator(
                    emu_id,
                    name=name,
                    executable=exe,
                    arguments=args,
                    platform=plat,
                )
                self.refresh()
                self.emulators_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error al actualizar", f"No se pudo actualizar el emulador:\n{e}")

    def delete_selected(self):
        emu_id = self._get_selected_id()
        if not emu_id:
            QMessageBox.information(self, "Seleccionar", "Seleccioná un emulador de la lista para eliminar.")
            return
        row = self.db.get_emulator(emu_id)
        if not row:
            return

        # Consultar cuántas listas o juegos usan este emulador
        lists_count = self.db.count_lists_using_emulator(emu_id)
        games_count = self.db.count_games_using_emulator(emu_id)

        warning = f"¿Estás seguro de que deseas eliminar el emulador '{row['name']}'?"
        if lists_count > 0 or games_count > 0:
            warning += f"\n\nAtención: Está vinculado a {lists_count} lista(s) y {games_count} juego(s).\nSu asignación pasará a 'Sin emulador'."

        answer = QMessageBox.question(self, "Confirmar eliminación", warning, QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            try:
                self.db.delete_emulator(emu_id)
                self.refresh()
                self.emulators_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error al eliminar", f"No se pudo eliminar el emulador:\n{e}")


class EmulatorManagerDialog(QDialog):
    """Diálogo completo para administrar (ver, crear, editar, eliminar) emuladores."""
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Administrar emuladores")
        self.resize(780, 480)

        layout = QVBoxLayout(self)
        self.widget = EmulatorManagerWidget(db, self, is_dialog=True)
        layout.addWidget(self.widget)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def refresh(self):
        self.widget.refresh()


class ScanWorker(QThread):
    """Worker en hilo secundario para escanear carpetas e importar juegos sin congelar la UI."""
    progress_changed = Signal(int, str)  # porcentaje (0-100), estado
    log_received = Signal(str)           # mensaje para la consola de debug
    finished_scan = Signal(dict)         # diccionario de estadísticas
    error_occurred = Signal(str)         # mensaje de error

    def __init__(
        self,
        db,
        list_id: int,
        rom_folders: list[str | Path],
        exts: str,
        scan_subfolders: bool = True,
        exclude_folder_if_zip: bool = False,
        xml_path: str | Path | None = None,
        replace: bool = True,
        filter_rules: list[dict] | str | None = None,
        filter_match_mode: str = "all",
    ):
        super().__init__()
        self.db = db
        self.list_id = list_id
        self.rom_folders = rom_folders
        self.exts = exts
        self.scan_subfolders = scan_subfolders
        self.exclude_folder_if_zip = exclude_folder_if_zip
        self.xml_path = xml_path
        self.replace = replace
        self.filter_rules = filter_rules
        self.filter_match_mode = filter_match_mode
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.progress_changed.emit(5, "Iniciando escaneo de carpetas...")
            self.log_received.emit("[INICIO] Comenzando escaneo de carpetas de juegos.")
            for f in self.rom_folders:
                self.log_received.emit(f"[CONFIG] Carpeta objetivo: {f}")
            self.log_received.emit(f"[CONFIG] Extensiones: {self.exts or 'Todas'}")
            self.log_received.emit(f"[CONFIG] Subcarpetas recursivas: {'Sí' if self.scan_subfolders else 'No'}")
            self.log_received.emit(f"[CONFIG] Excluir si contiene .zip: {'Sí' if self.exclude_folder_if_zip else 'No'}")
            if self.xml_path:
                self.log_received.emit(f"[CONFIG] Archivo XML asociado: {self.xml_path}")
            if self.filter_rules and self.filter_rules != "[]":
                self.log_received.emit(f"[CONFIG] Reglas de filtrado activas ({self.filter_match_mode.upper()}): {self.filter_rules}")

            def scan_cb(msg):
                if self._cancelled:
                    raise InterruptedError("Operación cancelada por el usuario.")
                self.log_received.emit(msg)

            paths = scan_rom_folder(
                self.rom_folders,
                self.exts,
                scan_subfolders=self.scan_subfolders,
                exclude_folder_if_zip=self.exclude_folder_if_zip,
                progress_callback=scan_cb,
            )

            if self._cancelled:
                raise InterruptedError("Operación cancelada por el usuario.")

            total = len(paths)
            self.log_received.emit(f"[SCAN] Total de archivos coincidentes encontrados: {total}")
            self.progress_changed.emit(20, f"Procesando e importando {total} juego(s)...")

            if total == 0:
                self.progress_changed.emit(100, "Finalizado: no se encontraron archivos.")
                self.log_received.emit("[AVISO] No se encontraron archivos de juegos que coincidan con los criterios.")
                self.finished_scan.emit({
                    "total_found": 0,
                    "added": 0,
                    "skipped": 0,
                    "removed": 0,
                    "xml_matched": 0,
                    "xml_total_entries": 0,
                    "filtered_out": 0,
                })
                return

            def import_cb(curr, tot, title):
                if self._cancelled:
                    raise InterruptedError("Operación cancelada por el usuario.")
                pct = 20 + int((curr / max(tot, 1)) * 75)
                self.progress_changed.emit(pct, f"Importando [{curr}/{tot}]: {title}")
                self.log_received.emit(f"[IMPORT] [{curr}/{tot}] {title}")

            stats = import_scanned_games(
                self.db,
                self.list_id,
                paths,
                xml_path=self.xml_path,
                replace=self.replace,
                progress_callback=import_cb,
                filter_rules=self.filter_rules,
                filter_match_mode=self.filter_match_mode,
            )

            self.progress_changed.emit(100, "¡Importación completada con éxito!")
            self.log_received.emit("==================================================")
            self.log_received.emit("[RESUMEN FINAL]")
            self.log_received.emit(f"  • Total archivos encontrados: {stats['total_found']}")
            self.log_received.emit(f"  • Juegos registrados en biblioteca: {stats['added']}")
            if stats.get('removed', 0) > 0:
                self.log_received.emit(f"  • Juegos eliminados (ya no existentes): {stats['removed']}")
            if stats.get('skipped', 0) > 0:
                self.log_received.emit(f"  • Juegos omitidos (sin cambios): {stats['skipped']}")
            if stats.get('filtered_out', 0) > 0:
                self.log_received.emit(f"  • Descartados por filtros de la lista: {stats['filtered_out']}")
            if stats.get('xml_matched', 0) > 0:
                self.log_received.emit(f"  • Juegos vinculados con datos XML: {stats['xml_matched']}")
            self.log_received.emit("==================================================")
            self.finished_scan.emit(stats)

        except InterruptedError:
            self.log_received.emit("[CANCELADO] El proceso fue cancelado por el usuario.")
            self.error_occurred.emit("Operación cancelada por el usuario.")
        except Exception as e:
            self.log_received.emit(f"[ERROR CRÍTICO] {e}")
            self.error_occurred.emit(str(e))


class ScanProgressDialog(QDialog):
    """
    Pantalla informativa modal con barra de progreso en porcentaje
    y consola de depuración en vivo para el proceso de creación/escaneo.
    """
    def __init__(
        self,
        parent,
        db,
        list_id: int,
        list_name: str,
        rom_folders: list[str | Path],
        exts: str,
        scan_subfolders: bool = True,
        exclude_folder_if_zip: bool = False,
        xml_path: str | Path | None = None,
        replace: bool = True,
        filter_rules: list[dict] | str | None = None,
        filter_match_mode: str = "all",
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Procesando lista: {list_name}")
        self.resize(700, 520)
        self.setMinimumSize(560, 420)
        self.setModal(True)

        self.stats: dict | None = None
        self.error_msg: str | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Encabezado informativo
        header_title = QLabel(f"<b style='font-size: 15px; color: #f1f5f9;'>Procesando biblioteca: {list_name}</b>")
        self.status_lbl = QLabel("Iniciando escaneo e importación de juegos...")
        self.status_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(header_title)
        layout.addWidget(self.status_lbl)

        # Barra de progreso estilizada
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #334155;
                border-radius: 6px;
                text-align: center;
                background-color: #0f172a;
                color: #f8fafc;
                font-weight: bold;
                height: 24px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #38bdf8);
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Pantalla de debug en tiempo real
        debug_group = QGroupBox("Consola de depuración en vivo (Debug)")
        debug_group.setStyleSheet("QGroupBox { font-weight: bold; color: #cbd5e1; }")
        debug_vbox = QVBoxLayout(debug_group)
        debug_vbox.setContentsMargins(8, 8, 8, 8)

        self.debug_console = QPlainTextEdit()
        self.debug_console.setReadOnly(True)
        self.debug_console.setMaximumBlockCount(5000)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(9)
        self.debug_console.setFont(font)
        self.debug_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #090d16;
                color: #38bdf8;
                border: 1px solid #1e293b;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        debug_vbox.addWidget(self.debug_console)
        layout.addWidget(debug_group, 1)

        # Botones inferiores
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.accept_btn = QPushButton("Aceptar")
        self.accept_btn.setEnabled(False)
        self.accept_btn.setStyleSheet("""
            QPushButton:enabled {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
                padding: 6px 18px;
                border-radius: 4px;
            }
            QPushButton:enabled:hover {
                background-color: #1d4ed8;
            }
        """)
        self.accept_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.accept_btn)
        layout.addLayout(btn_layout)

        # Iniciar worker en hilo secundario
        self.worker = ScanWorker(
            db=db,
            list_id=list_id,
            rom_folders=rom_folders,
            exts=exts,
            scan_subfolders=scan_subfolders,
            exclude_folder_if_zip=exclude_folder_if_zip,
            xml_path=xml_path,
            replace=replace,
            filter_rules=filter_rules,
            filter_match_mode=filter_match_mode,
        )
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.log_received.connect(self._on_log)
        self.worker.finished_scan.connect(self._on_finished)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, percent: int, text: str):
        self.progress_bar.setValue(percent)
        self.status_lbl.setText(text)

    def _on_log(self, message: str):
        self.debug_console.appendPlainText(message)
        self.debug_console.moveCursor(QTextCursor.End)

    def _on_finished(self, stats: dict):
        self.stats = stats
        self.cancel_btn.setEnabled(False)
        self.accept_btn.setEnabled(True)
        self.status_lbl.setText("¡Proceso finalizado! Podés revisar el registro arriba y hacer clic en Aceptar.")
        self.status_lbl.setStyleSheet("color: #4ade80; font-weight: bold;")
        self.accept_btn.setFocus()

    def _on_error(self, err_msg: str):
        self.error_msg = err_msg
        self.cancel_btn.setEnabled(False)
        self.accept_btn.setEnabled(True)
        self.status_lbl.setText(f"Aviso / Error: {err_msg}")
        self.status_lbl.setStyleSheet("color: #f87171; font-weight: bold;")
        self.accept_btn.setFocus()

    def _on_cancel(self):
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText("Cancelando operación...")
        self.worker.cancel()

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1500)
        super().closeEvent(event)


class ScanSummaryDialog(QDialog):
    """Diálogo informativo con el resumen completo del escaneo de carpeta(s)."""
    def __init__(self, parent, stats: dict, folder: str, list_name: str, allowed_exts: str):
        super().__init__(parent)
        self.setWindowTitle("Resumen de escaneo de juegos")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        title = QLabel(f"<h2>Escaneo completado para: {list_name}</h2>")
        layout.addWidget(title)

        folders_parsed = parse_rom_folders(folder)
        folders_label_title = "Carpetas examinadas:" if len(folders_parsed) > 1 else "Carpeta examinada:"
        folders_display = "<br>".join(f"• {f}" for f in folders_parsed) if len(folders_parsed) > 1 else (folders_parsed[0] if folders_parsed else folder)

        box = QGroupBox("Detalles de la importación")
        form = QFormLayout(box)
        lbl_folders = QLabel(folders_display)
        lbl_folders.setWordWrap(True)
        form.addRow(folders_label_title, lbl_folders)
        form.addRow("Extensiones permitidas:", QLabel(allowed_exts))
        form.addRow("Archivos coincidentes encontrados:", QLabel(f"<b>{stats['total_found']}</b>"))
        form.addRow("Juegos registrados en la lista:", QLabel(f"<b style='color: #4cd964;'>{stats['added']}</b>"))
        if stats.get("removed", 0) > 0:
            form.addRow("Juegos anteriores eliminados:", QLabel(f"<b style='color: #f87171;'>{stats['removed']}</b>"))
        if stats.get("skipped", 0) > 0:
            form.addRow("Archivos omitidos:", QLabel(f"<b>{stats['skipped']}</b>"))
        if stats.get("filtered_out", 0) > 0:
            form.addRow("Descartados por filtros:", QLabel(f"<b style='color: #f59e0b;'>{stats['filtered_out']}</b>"))
        if stats.get("xml_total_entries", 0) > 0 or stats.get("xml_matched", 0) > 0:
            xml_matched = stats.get("xml_matched", 0)
            xml_total = stats.get("xml_total_entries", 0)
            form.addRow(
                "Asociados con XML (nombre y propiedades):",
                QLabel(f"<b style='color: #a5b4fc;'>{xml_matched}</b> <span style='color: #8a93a8;'>(de {xml_total} en XML)</span>")
            )
        layout.addWidget(box)

        btn = QPushButton("Aceptar")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignRight)


class GameEditDialog(QDialog):
    """Diálogo para editar metadatos y configuración individual de un juego."""
    def __init__(self, db, game, parent=None):
        super().__init__(parent)
        self.db = db
        self.game = dict(game) if hasattr(game, "keys") else game
        game = self.game
        self.setWindowTitle(f"Editar juego: {game['title']}")
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_edit = QLineEdit(game["title"])
        form.addRow("Título completo *", self.title_edit)

        rom_code = game.get("rom_name") or (Path(game["rom_path"]).stem if game.get("rom_path") else "")
        self.rom_name_edit = QLineEdit(rom_code)
        self.rom_name_edit.setPlaceholderText("Denominación corta de la ROM (ej: sf2)")
        form.addRow("Denominación ROM", self.rom_name_edit)

        self.path_edit = QLineEdit(game["rom_path"])
        browse_btn = QPushButton("Examinar…")
        browse_btn.clicked.connect(self.pick_file)
        path_box = QHBoxLayout()
        path_box.addWidget(self.path_edit, 1)
        path_box.addWidget(browse_btn)
        path_holder = QWidget()
        path_holder.setLayout(path_box)
        form.addRow("Ruta del archivo", path_holder)

        # Propiedades del juego (provenientes del XML o editables manualmente)
        meta_group = QGroupBox("Propiedades del Juego (XML / Metadatos)")
        meta_form = QFormLayout(meta_group)

        row_ym = QHBoxLayout()
        self.year_edit = QLineEdit(game.get("year") or "")
        self.year_edit.setPlaceholderText("Ej: 1991")
        self.year_edit.setFixedWidth(100)
        self.manufacturer_edit = QLineEdit(game.get("manufacturer") or "")
        self.manufacturer_edit.setPlaceholderText("Ej: Capcom, Konami, Sega...")
        row_ym.addWidget(self.year_edit)
        row_ym.addWidget(QLabel("Fabricante:"))
        row_ym.addWidget(self.manufacturer_edit, 1)
        ym_widget = QWidget()
        ym_widget.setLayout(row_ym)
        meta_form.addRow("Año:", ym_widget)

        row_gp = QHBoxLayout()
        self.genre_edit = QLineEdit(game.get("genre") or "")
        self.genre_edit.setPlaceholderText("Ej: Fighter, Shooter, Platform...")
        self.players_edit = QLineEdit(game.get("players") or "")
        self.players_edit.setPlaceholderText("Ej: 1-2")
        self.players_edit.setFixedWidth(90)
        row_gp.addWidget(self.genre_edit, 1)
        row_gp.addWidget(QLabel("Jugadores:"))
        row_gp.addWidget(self.players_edit)
        gp_widget = QWidget()
        gp_widget.setLayout(row_gp)
        meta_form.addRow("Género:", gp_widget)

        row_cr = QHBoxLayout()
        self.cloneof_edit = QLineEdit(game.get("cloneof") or "")
        self.cloneof_edit.setPlaceholderText("ROM padre (si es clon)")
        self.rating_edit = QLineEdit(game.get("rating") or "")
        self.rating_edit.setPlaceholderText("Clasificación / Rating")
        self.crc_edit = QLineEdit(game.get("crc") or "")
        self.crc_edit.setPlaceholderText("CRC")
        self.crc_edit.setFixedWidth(95)
        row_cr.addWidget(self.cloneof_edit, 1)
        row_cr.addWidget(QLabel("Rating:"))
        row_cr.addWidget(self.rating_edit, 1)
        row_cr.addWidget(QLabel("CRC:"))
        row_cr.addWidget(self.crc_edit)
        cr_widget = QWidget()
        cr_widget.setLayout(row_cr)
        meta_form.addRow("Clon de:", cr_widget)

        sourcefile_val = game.get("sourcefile") or ""
        if not sourcefile_val:
            meta_json = game.get("xml_metadata") or "{}"
            try:
                m_dict = json.loads(meta_json) if isinstance(meta_json, str) else meta_json
                if isinstance(m_dict, dict):
                    sourcefile_val = m_dict.get("sourcefile") or m_dict.get("source_file") or ""
            except Exception:
                pass
        self.sourcefile_edit = QLineEdit(sourcefile_val)
        self.sourcefile_edit.setPlaceholderText("Archivo fuente driver MAME (ej: capcom/cps1.cpp, neogeo.cpp)")
        meta_form.addRow("Sourcefile:", self.sourcefile_edit)

        # Orientación de pantalla (útil para Bezel HUD vertical/horizontal)
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem("Automático (según XML / Metadatos)", "")
        self.orientation_combo.addItem("Horizontal (Estándar)", "horizontal")
        self.orientation_combo.addItem("Vertical (TATE)", "vertical")
        cur_orient = ""
        meta_json_raw = game.get("xml_metadata") or "{}"
        try:
            m_dict_or = json.loads(meta_json_raw) if isinstance(meta_json_raw, str) else meta_json_raw
            if isinstance(m_dict_or, dict):
                cur_orient = m_dict_or.get("orientation") or ""
        except Exception:
            pass
        idx_or = self.orientation_combo.findData(cur_orient.lower())
        if idx_or >= 0:
            self.orientation_combo.setCurrentIndex(idx_or)
        meta_form.addRow("Orientación:", self.orientation_combo)

        self.override_combo = QComboBox()
        self.override_combo.addItem("Heredar emulador de la lista (por defecto)", None)
        emulators = self.db.get_emulators()
        for emu in emulators:
            self.override_combo.addItem(f"{emu['name']} ({emu['executable']})", emu["id"])
        idx = self.override_combo.findData(game["emulator_override_id"])
        if idx >= 0:
            self.override_combo.setCurrentIndex(idx)
        form.addRow("Emulador individual", self.override_combo)

        self.bezel_hud_combo = QComboBox()
        self.bezel_hud_combo.addItem("Heredar de la lista (por defecto)", "")
        self.bezel_hud_combo.addItem("Activar Bezel HUD (Forzar para este juego)", "enabled")
        self.bezel_hud_combo.addItem("Desactivar Bezel HUD (No mostrar)", "disabled")
        idx_bh = self.bezel_hud_combo.findData(game.get("bezel_hud_mode") or "")
        if idx_bh >= 0:
            self.bezel_hud_combo.setCurrentIndex(idx_bh)
        form.addRow("Bezel HUD (Marco)", self.bezel_hud_combo)

        self.args_edit = QLineEdit(game["launch_arguments"] or "")
        self.args_edit.setPlaceholderText("Dejar vacío para usar los argumentos del emulador")
        form.addRow("Argumentos propios", self.args_edit)

        self.notes_edit = QTextEdit(game["notes"] or "")
        self.notes_edit.setMaximumHeight(70)
        form.addRow("Notas / Sinopsis", self.notes_edit)

        layout.addLayout(form)
        layout.addWidget(meta_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo de juego", "", "Todos los archivos (*.*)")
        if path:
            self.path_edit.setText(path)

    def save(self):
        import json
        title = self.title_edit.text().strip()
        path = self.path_edit.text().strip()
        if not title or not path:
            QMessageBox.warning(self, "Campos requeridos", "El título y la ruta del archivo son obligatorios.")
            return

        rom_name = self.rom_name_edit.text().strip() or Path(path).stem
        year = self.year_edit.text().strip()
        manufacturer = self.manufacturer_edit.text().strip()
        genre = self.genre_edit.text().strip()
        players = self.players_edit.text().strip()
        cloneof = self.cloneof_edit.text().strip()
        rating = self.rating_edit.text().strip()
        crc = self.crc_edit.text().strip()
        sourcefile = self.sourcefile_edit.text().strip() if hasattr(self, "sourcefile_edit") else ""

        emu_override = self.override_combo.currentData()
        bezel_hud_mode = self.bezel_hud_combo.currentData() or ""
        args = self.args_edit.text().strip()
        notes = self.notes_edit.toPlainText().strip()

        # Actualizar xml_metadata preservando propiedades adicionales existentes
        raw_meta = self.game.get("xml_metadata") or "{}"
        try:
            meta_dict = json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta)
            if not isinstance(meta_dict, dict):
                meta_dict = {}
        except Exception:
            meta_dict = {}

        meta_dict["title"] = title
        meta_dict["rom_name"] = rom_name
        if sourcefile:
            meta_dict["sourcefile"] = sourcefile
        orient_val = self.orientation_combo.currentData() or ""
        if orient_val:
            meta_dict["orientation"] = orient_val
        elif "orientation" in meta_dict:
            meta_dict.pop("orientation", None)
        for k, v in (
            ("year", year),
            ("manufacturer", manufacturer),
            ("genre", genre),
            ("players", players),
            ("cloneof", cloneof),
            ("rating", rating),
            ("crc", crc),
            ("sourcefile", sourcefile),
        ):
            if v:
                meta_dict[k] = v
        xml_metadata = json.dumps(meta_dict, ensure_ascii=False)

        try:
            self.db.update_game(
                self.game["id"],
                title=title,
                rom_path=path,
                rom_name=rom_name,
                year=year,
                manufacturer=manufacturer,
                genre=genre,
                players=players,
                cloneof=cloneof,
                rating=rating,
                crc=crc,
                sourcefile=sourcefile,
                xml_metadata=xml_metadata,
                emulator_override_id=emu_override,
                bezel_hud_mode=bezel_hud_mode,
                launch_arguments=args,
                notes=notes,
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la información del juego:\n{e}")


RESOLUTIONS_LIST = [
    ("Nativa / Automática (Recomendado)", "native"),
    ("3840 x 2160 (4K Ultra HD - 16:9)", "3840x2160"),
    ("2560 x 1440 (2K QHD - 16:9)", "2560x1440"),
    ("1920 x 1080 (Full HD 1080p - 16:9)", "1920x1080"),
    ("1600 x 900 (HD+ - 16:9)", "1600x900"),
    ("1366 x 768 (Laptop HD - 16:9)", "1366x768"),
    ("1280 x 720 (HD 720p - 16:9)", "1280x720"),
    ("1920 x 1200 (WUXGA - 16:10)", "1920x1200"),
    ("1680 x 1050 (16:10)", "1680x1050"),
    ("1280 x 800 (16:10)", "1280x800"),
    ("1280 x 1024 (SXGA - 5:4)", "1280x1024"),
    ("1024 x 768 (XGA - 4:3)", "1024x768"),
    ("800 x 600 (SVGA - 4:3)", "800x600"),
    ("640 x 480 (VGA - 4:3)", "640x480"),
    ("Personalizada...", "custom"),
]

SCREEN_MODES = [
    ("Pantalla completa (Fullscreen)", "fullscreen"),
    ("Ventana sin bordes (Borderless)", "borderless"),
    ("Modo Ventana (Windowed)", "windowed"),
]


class VideoSettingsDialog(QDialog):
    """
    Diálogo para configurar la resolución, modo de pantalla completa y monitor
    del Frontend / Reproductor de PlayNexus.
    """
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Configuración de Video y Pantalla")
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        header = QLabel("<b>Configuración de Video del Frontend</b>")
        header.setStyleSheet("font-size: 11pt; color: #f1f3f9;")
        layout.addWidget(header)

        desc = QLabel(
            "Configurá la resolución, modo de pantalla completa y monitor "
            "con el que se ejecutará el Frontend de juegos (PlayNexus_Launcher.bat)."
        )
        desc.setStyleSheet("color: #9aa5b8; font-size: 9pt;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(12)

        # 1. Modo de Pantalla
        self.mode_combo = QComboBox()
        for label, val in SCREEN_MODES:
            self.mode_combo.addItem(label, val)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Modo de pantalla:", self.mode_combo)

        # 2. Resolución
        self.res_combo = QComboBox()
        for label, val in RESOLUTIONS_LIST:
            self.res_combo.addItem(label, val)
        self.res_combo.currentIndexChanged.connect(self._on_res_changed)
        form.addRow("Resolución:", self.res_combo)

        # 3. Resolución personalizada (ancho x alto)
        self.custom_row = QWidget()
        custom_layout = QHBoxLayout(self.custom_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 7680)
        self.width_spin.setValue(1920)
        self.width_spin.setSuffix(" px")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 4320)
        self.height_spin.setValue(1080)
        self.height_spin.setSuffix(" px")
        custom_layout.addWidget(QLabel("Ancho:"))
        custom_layout.addWidget(self.width_spin)
        custom_layout.addWidget(QLabel("Alto:"))
        custom_layout.addWidget(self.height_spin)
        form.addRow("Tamaño personalizado:", self.custom_row)
        self.custom_row.setVisible(False)

        # 4. Monitor / Pantalla de destino
        self.screen_combo = QComboBox()
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        for idx, scr in enumerate(screens):
            geo = scr.geometry()
            tag = " [Principal]" if scr == primary else ""
            self.screen_combo.addItem(f"Monitor {idx + 1}: {geo.width()}x{geo.height()} ({scr.name()}){tag}", idx)
        self.screen_combo.currentIndexChanged.connect(self._update_info)
        form.addRow("Monitor de destino:", self.screen_combo)

        # 5. Escala de interfaz (UI Scale)
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["100% (Normal)", "125%", "150%", "175%", "200% (4K)"])
        form.addRow("Escala de la interfaz:", self.scale_combo)

        layout.addLayout(form)

        # Nota informativa
        note_box = QGroupBox("Resumen de visualización")
        note_layout = QVBoxLayout(note_box)
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #a0aec0; font-size: 9pt;")
        self.info_label.setWordWrap(True)
        note_layout.addWidget(self.info_label)
        layout.addWidget(note_box)

        # Botones
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_current_settings()
        self._update_info()

    def _on_mode_changed(self):
        mode = self.mode_combo.currentData()
        # En modo ventana o sin bordes se puede elegir resolución
        self.res_combo.setEnabled(mode != "fullscreen")
        self._update_info()

    def _on_res_changed(self):
        val = self.res_combo.currentData()
        self.custom_row.setVisible(val == "custom")
        self._update_info()

    def _update_info(self):
        mode = self.mode_combo.currentData()
        res = self.res_combo.currentData()
        screens = QGuiApplication.screens()
        s_idx = self.screen_combo.currentIndex()
        cur_screen = screens[s_idx] if 0 <= s_idx < len(screens) else QGuiApplication.primaryScreen()
        geo = cur_screen.geometry() if cur_screen else None
        geo_str = f"{geo.width()}x{geo.height()}" if geo else "pantalla"

        if mode == "fullscreen":
            msg = f"El Frontend iniciará a <b>Pantalla completa</b> ocupando todo el monitor ({geo_str}). Ideal para gabinetes arcade y televisores."
        elif mode == "borderless":
            msg = f"El Frontend iniciará en <b>Ventana sin bordes</b> adaptada a la resolución del monitor ({geo_str})."
        else:
            if res == "native":
                msg = f"Modo <b>Ventana</b> ajustado automáticamente a las dimensiones de la pantalla ({geo_str})."
            elif res == "custom":
                msg = f"Modo <b>Ventana</b> con resolución personalizada de <b>{self.width_spin.value()} x {self.height_spin.value()}</b> píxeles."
            else:
                msg = f"Modo <b>Ventana</b> con resolución fija de <b>{res}</b> píxeles."
        self.info_label.setText(msg)

    def _load_current_settings(self):
        mode = self.db.get_setting("video_mode", "fullscreen")
        idx = self.mode_combo.findData(mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        res = self.db.get_setting("video_resolution", "native")
        idx_r = self.res_combo.findData(res)
        if idx_r >= 0:
            self.res_combo.setCurrentIndex(idx_r)
        else:
            idx_cust = self.res_combo.findData("custom")
            if idx_cust >= 0:
                self.res_combo.setCurrentIndex(idx_cust)

        self.width_spin.setValue(int(self.db.get_setting("video_custom_width", "1920")))
        self.height_spin.setValue(int(self.db.get_setting("video_custom_height", "1080")))

        mon_idx = int(self.db.get_setting("video_monitor", "0"))
        if 0 <= mon_idx < self.screen_combo.count():
            self.screen_combo.setCurrentIndex(mon_idx)

        scale = self.db.get_setting("video_ui_scale", "100% (Normal)")
        idx_s = self.scale_combo.findText(scale)
        if idx_s >= 0:
            self.scale_combo.setCurrentIndex(idx_s)

        self._on_mode_changed()
        self._on_res_changed()

    def save(self):
        mode = self.mode_combo.currentData()
        res = self.res_combo.currentData()
        self.db.set_setting("video_mode", mode)
        self.db.set_setting("video_resolution", res)
        self.db.set_setting("video_custom_width", str(self.width_spin.value()))
        self.db.set_setting("video_custom_height", str(self.height_spin.value()))
        self.db.set_setting("video_monitor", str(self.screen_combo.currentData()))
        self.db.set_setting("video_ui_scale", self.scale_combo.currentText())
        self.accept()


