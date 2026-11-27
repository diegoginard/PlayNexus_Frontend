from playnexus.db import APP_DIR
from playnexus.i18n import tr
from pathlib import Path
import json
import shutil
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QGuiApplication, QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QDialogButtonBox, QFileDialog, QMessageBox, QHBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QGroupBox,
    QTextEdit, QAbstractItemView, QCheckBox, QSpinBox, QDoubleSpinBox, QFrame,
    QListWidget, QListWidgetItem, QScrollArea, QProgressBar, QPlainTextEdit
)
from playnexus.services.library import (
    normalize_extensions, parse_extensions_list,
    parse_rom_folders, format_rom_folders,
    FILTERABLE_FIELDS, FILTER_OPERATORS, SORT_MODES, SMART_COLLECTION_PRESETS,
    game_matches_filter,
    scan_rom_folder, import_scanned_games
)
from playnexus.services.themes import get_layout_media_spec
from playnexus.ui.table_utils import (
    SortableTableWidgetItem,
    configure_details_table,
    paused_table_sorting,
)

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

_PRESET_EXTENSION_I18N: dict[str, tuple[str, str]] = {
    "Personalizado...": ("dlg.preset.custom", "Custom..."),
    "Juegos de PC / Windows (.lnk, .bat)": ("dlg.preset.pc_windows", "PC / Windows Games (.lnk, .bat)"),
    "Super Nintendo (SNES)": ("dlg.preset.snes", "Super Nintendo (SNES)"),
    "Game Boy Advance (GBA)": ("dlg.preset.gba", "Game Boy Advance (GBA)"),
    "PlayStation (PS1)": ("dlg.preset.ps1", "PlayStation (PS1)"),
    "PlayStation 2 (PS2)": ("dlg.preset.ps2", "PlayStation 2 (PS2)"),
    "Sega Genesis / Mega Drive": ("dlg.preset.genesis", "Sega Genesis / Mega Drive"),
    "Nintendo 64 (N64)": ("dlg.preset.n64", "Nintendo 64 (N64)"),
    "Nintendo DS (NDS)": ("dlg.preset.nds", "Nintendo DS (NDS)"),
    "PSP": ("dlg.preset.psp", "PSP"),
    "Arcade (MAME / FBNeo)": ("dlg.preset.arcade", "Arcade (MAME / FBNeo)"),
}

_FILTER_FIELD_I18N: dict[str, tuple[str, str]] = {
    "is_favorite": ("dlg.filter_field.is_favorite", "Favorite (1 = Yes / 0 = No)"),
    "play_count": ("dlg.filter_field.play_count", "Play count (play_count)"),
    "play_time_seconds": ("dlg.filter_field.play_time_seconds", "Time played in sec (play_time_seconds)"),
    "last_played": ("dlg.filter_field.last_played", "Last played (last_played)"),
    "tags": ("dlg.filter_field.tags", "Tags (tags)"),
    "sourcefile": ("dlg.filter_field.sourcefile", "Board / Driver (sourcefile — e.g. cps1, cps2, neogeo.cpp)"),
    "bios": ("dlg.filter_field.bios", "System BIOS (bios / romof — e.g. neogeo, pgm, naomi)"),
    "genre": ("dlg.filter_field.genre", "Genre (genre)"),
    "manufacturer": ("dlg.filter_field.manufacturer", "Manufacturer (manufacturer)"),
    "year": ("dlg.filter_field.year", "Year (year)"),
    "title": ("dlg.filter_field.title", "Title (title)"),
    "rom_name": ("dlg.filter_field.rom_name", "ROM name (rom_name)"),
    "players": ("dlg.filter_field.players", "Players (players)"),
    "cloneof": ("dlg.filter_field.cloneof", "Clone of (cloneof)"),
    "rating": ("dlg.filter_field.rating", "Rating (rating)"),
    "crc": ("dlg.filter_field.crc", "CRC"),
    "rom_path": ("dlg.filter_field.rom_path", "ROM path (rom_path)"),
    "notes": ("dlg.filter_field.notes", "Notes (notes)"),
    "emulator_override_id": ("dlg.filter_field.emulator_override_id", "Specific emulator (ID)"),
    "launch_arguments": ("dlg.filter_field.launch_arguments", "Launch arguments"),
    "manual_file_path": ("dlg.filter_field.manual_file_path", "Individual PDF manual"),
}

_FILTER_OP_I18N: dict[str, tuple[str, str]] = {
    "contains": ("dlg.filter_op.contains", "Contains"),
    "not_contains": ("dlg.filter_op.not_contains", "Does not contain"),
    "equals": ("dlg.filter_op.equals", "Equals"),
    "not_equals": ("dlg.filter_op.not_equals", "Does not equal"),
    "gt": ("dlg.filter_op.gt", "Greater than (>)"),
    "gte": ("dlg.filter_op.gte", "Greater or equal (>=)"),
    "lt": ("dlg.filter_op.lt", "Less than (<)"),
    "lte": ("dlg.filter_op.lte", "Less or equal (<=)"),
    "starts_with": ("dlg.filter_op.starts_with", "Starts with"),
    "ends_with": ("dlg.filter_op.ends_with", "Ends with"),
    "is_empty": ("dlg.filter_op.is_empty", "Is empty"),
    "is_not_empty": ("dlg.filter_op.is_not_empty", "Is not empty"),
}

_SORT_MODE_I18N: dict[str, tuple[str, str]] = {
    "title": ("dlg.sort.title", "Alphabetical by title (A-Z)"),
    "last_played_desc": ("dlg.sort.last_played_desc", "Recently played (latest session first)"),
    "play_count_desc": ("dlg.sort.play_count_desc", "Most played (highest play count)"),
    "play_time_desc": ("dlg.sort.play_time_desc", "Most accumulated playtime"),
    "favorites_first": ("dlg.sort.favorites_first", "Favorites first, then title A-Z"),
}

_SMART_PRESET_I18N: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "favorites": (
        ("dlg.smart.favorites.label", "⭐ Favorites (marked in library or frontend)"),
        ("dlg.smart.favorites.name", "Favorites"),
    ),
    "recent": (
        ("dlg.smart.recent.label", "🕒 Recently played (with recorded sessions)"),
        ("dlg.smart.recent.name", "Recently Played"),
    ),
    "most_played": (
        ("dlg.smart.most_played.label", "🏆 Most played (sorted by play count)"),
        ("dlg.smart.most_played.name", "Most Played"),
    ),
    "unplayed": (
        ("dlg.smart.unplayed.label", "🧭 Unplayed (0 plays)"),
        ("dlg.smart.unplayed.name", "Unplayed"),
    ),
}

_MEDIA_LABEL_I18N: dict[str, tuple[str, str]] = {
    "Box Art / Carátulas": ("dlg.media_lbl.boxart_covers", "Box Art / Covers"),
    "Box Art / Cajas": ("dlg.media_lbl.boxart_boxes", "Box Art / Boxes"),
    "Artwork / Imagen decorativa": ("dlg.media_lbl.artwork_deco", "Artwork / Decorative Image"),
    "Logos o Banners": ("dlg.media_lbl.logos_banners", "Logos or Banners"),
    "Logos Wheel": ("dlg.media_lbl.logos_wheel", "Wheel Logos"),
    "Wheel Logos": ("dlg.media_lbl.wheel_logos", "Wheel Logos"),
    "Wheel": ("dlg.media_lbl.wheel", "Wheel"),
    "Cartuchos": ("dlg.media_lbl.cartridges", "Cartridges"),
    "Discos": ("dlg.media_lbl.discs", "Discs"),
    "Discos / CDs": ("dlg.media_lbl.discs_cds", "Discs / CDs"),
    "Tarjetas HuCard": ("dlg.media_lbl.hucard", "HuCard Cards"),
    "Videos de Fondo / Temas": ("dlg.media_lbl.bg_videos", "Background / Theme Videos"),
    "Video Snaps": ("dlg.media_lbl.video_snaps", "Video Snaps"),
    "Videos": ("dlg.media_lbl.videos", "Videos"),
    "Cabinets": ("dlg.media_lbl.cabinets", "Cabinets"),
    "Flyers": ("dlg.media_lbl.flyers", "Flyers"),
    "Marquees": ("dlg.media_lbl.marquees", "Marquees"),
    "Bezels": ("dlg.media_lbl.bezels", "Bezels"),
}


def _tr_from_map(mapping: dict[str, tuple[str, str]], item_key: str, fallback: str) -> str:
    """Traduce un elemento registrado en un diccionario auxiliar manteniendo respaldo seguro."""
    pair = mapping.get(item_key)
    if pair:
        return tr(pair[0], pair[1])
    return fallback


def _localize_dialog_buttons(buttons: QDialogButtonBox) -> None:
    """Aplica traducción explícita a los botones estándar Guardar y Cancelar."""
    save_btn = buttons.button(QDialogButtonBox.Save)
    if save_btn is not None:
        save_btn.setText(tr("dlg.btn.save", "Save"))
    cancel_btn = buttons.button(QDialogButtonBox.Cancel)
    if cancel_btn is not None:
        cancel_btn.setText(tr("dlg.btn.cancel", "Cancel"))

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
        self.setWindowTitle(tr("dlg.list.title_edit", "Edit list / menu") if existing else tr("dlg.list.title_new", "Create new list / menu"))
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
        basic_group = QGroupBox(tr("dlg.list.basic_group", "Main Information"))
        form = QFormLayout(basic_group)
        form.setSpacing(8)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("dlg.list.name_placeholder", "e.g., Super Nintendo, Consoles Menu..."))
        form.addRow(tr("dlg.list.name_label", "Name *"), self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItem(tr("dlg.list.type_games", "🎮 Game list (ROMs & emulator)"), "games")
        self.type_combo.addItem(tr("dlg.list.type_menu", "🧭 Systems menu (List of lists)"), "menu")
        self.type_combo.addItem(tr("dlg.list.type_filtered", "⚡ Filtered list (from another list)"), "filtered")
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow(tr("dlg.list.type_label", "List type"), self.type_combo)

        self.platform_edit = QLineEdit()
        self.platform_edit.setPlaceholderText(tr("dlg.list.platform_placeholder", "e.g., Super Nintendo, GBA, Arcade..."))
        form.addRow(tr("dlg.list.platform_label", "Platform or tag"), self.platform_edit)

        # Icono de la lista
        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText(tr("dlg.list.icon_placeholder", "List icon (PNG, JPG, WebP)…"))
        self.icon_path_edit.setReadOnly(True)
        icon_browse_btn = QPushButton(tr("dlg.list.choose_icon", "Choose icon…"))
        icon_browse_btn.clicked.connect(self.pick_icon)
        icon_clear_btn = QPushButton("✕")
        icon_clear_btn.setFixedWidth(28)
        icon_clear_btn.setToolTip(tr("dlg.list.clear_icon_tooltip", "Remove icon"))
        icon_clear_btn.clicked.connect(lambda: self.icon_path_edit.clear())
        icon_row = QHBoxLayout()
        icon_row.setContentsMargins(0, 0, 0, 0)
        icon_row.addWidget(self.icon_path_edit, 1)
        icon_row.addWidget(icon_browse_btn)
        icon_row.addWidget(icon_clear_btn)
        icon_holder = QWidget()
        icon_holder.setLayout(icon_row)
        form.addRow(tr("dlg.list.icon_label", "List icon"), icon_holder)

        from playnexus.ui.layouts import get_available_layouts
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(get_available_layouts())
        form.addRow(tr("dlg.list.layout_label", "Visual layout"), self.layout_combo)

        scroll_layout.addWidget(basic_group)

        # 2. Grupo para Lista de Juegos (ROMs, Emulador, Extensiones)
        self.game_settings_group = QGroupBox(tr("dlg.list.game_settings_group", "Games & Emulator Settings"))
        game_form = QFormLayout(self.game_settings_group)
        game_form.setSpacing(8)

        self.preset_combo = QComboBox()
        for title in PRESET_EXTENSIONS.keys():
            self.preset_combo.addItem(_tr_from_map(_PRESET_EXTENSION_I18N, title, title), title)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        game_form.addRow(tr("dlg.list.preset_label", "Suggested template"), self.preset_combo)

        self.extensions_edit = QLineEdit()
        self.extensions_edit.setPlaceholderText(tr("dlg.list.ext_placeholder", "e.g., .zip;.7z;<DIR> or .cue;.chd (separated by ;)"))
        game_form.addRow(tr("dlg.list.ext_label", "Allowed extensions *"), self.extensions_edit)

        ext_hint = QLabel(
            tr(
                "dlg.list.ext_hint",
                "<b>Required:</b> Enter the allowed extensions separated <b>exclusively by semicolons (;)</b>.<br>"
                "<i>Example: .zip;.7z;<DIR> (in MAME <code>&lt;DIR&gt;</code> treats subfolders as ROMs when they do not have a .zip with the same name).</i>",
            )
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
        browse_folder_btn = QPushButton(tr("dlg.list.add_folder_btn", "＋ Add folder…"))
        browse_folder_btn.setToolTip(tr("dlg.list.add_folder_tooltip", "Choose and add a ROM folder to the list"))
        browse_folder_btn.clicked.connect(self.pick_folder)
        remove_folder_btn = QPushButton(tr("dlg.list.remove_folder_btn", "✕ Remove selected"))
        remove_folder_btn.setToolTip(tr("dlg.list.remove_folder_tooltip", "Remove the selected folder from the list"))
        remove_folder_btn.clicked.connect(self.remove_selected_folder)
        clear_folders_btn = QPushButton(tr("dlg.list.clear_folders_btn", "Clear all"))
        clear_folders_btn.setToolTip(tr("dlg.list.clear_folders_tooltip", "Clear all configured ROM folders"))
        clear_folders_btn.clicked.connect(self.clear_folders)
        folders_btns_col.addWidget(browse_folder_btn)
        folders_btns_col.addWidget(remove_folder_btn)
        folders_btns_col.addWidget(clear_folders_btn)
        folders_btns_col.addStretch()
        folders_top_row.addLayout(folders_btns_col)
        folders_vbox.addLayout(folders_top_row)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(tr("dlg.list.folders_placeholder", "Folder paths separated by ; (or use '＋ Add folder…')"))
        self.folder_edit.textEdited.connect(self._on_folder_edit_changed)
        folders_vbox.addWidget(self.folder_edit)

        folder_holder = QWidget()
        folder_holder.setLayout(folders_vbox)
        game_form.addRow(tr("dlg.list.folders_label", "Game folders"), folder_holder)

        self.auto_scan_checkbox = QCheckBox(tr("dlg.list.auto_scan_cb", "Automatically scan and import games from these folder(s)"))
        self.auto_scan_checkbox.setChecked(True if not existing else False)
        game_form.addRow("", self.auto_scan_checkbox)

        self.scan_subfolders_checkbox = QCheckBox(tr("dlg.list.scan_subfolders_cb", "Search for games in subfolders recursively"))
        self.scan_subfolders_checkbox.setChecked(True)
        self.scan_subfolders_checkbox.setToolTip(tr("dlg.list.scan_subfolders_tooltip", "If unchecked, only the root of each configured folder will be scanned."))
        game_form.addRow(tr("dlg.list.scan_options_label", "Scan options"), self.scan_subfolders_checkbox)

        self.exclude_folder_if_zip_checkbox = QCheckBox(tr("dlg.list.exclude_zip_cb", "If a folder contains a .zip file, list only the .zip (exclude the rest of the folder)"))
        self.exclude_folder_if_zip_checkbox.setChecked(False)
        self.exclude_folder_if_zip_checkbox.setToolTip(
            tr(
                "dlg.list.exclude_zip_tooltip",
                "If a folder contains .zip or .7z file(s), only the .zip is listed and the rest\n"
                "of the files (bin, cue, chd, etc.) and subfolders inside are excluded.",
            )
        )
        game_form.addRow("", self.exclude_folder_if_zip_checkbox)

        self.xml_edit = QLineEdit()
        self.xml_edit.setPlaceholderText(tr("dlg.list.xml_placeholder", "Optional: .pncat / .xml / .dat file with full names and ROM metadata..."))
        browse_xml_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
        browse_xml_btn.clicked.connect(self.pick_xml)
        clear_xml_btn = QPushButton("✕")
        clear_xml_btn.setToolTip(tr("dlg.list.clear_xml_tooltip", "Remove associated XML file"))
        clear_xml_btn.setFixedWidth(28)
        clear_xml_btn.clicked.connect(lambda: self.xml_edit.clear())
        xml_row = QHBoxLayout()
        xml_row.setContentsMargins(0, 0, 0, 0)
        xml_row.addWidget(self.xml_edit, 1)
        xml_row.addWidget(browse_xml_btn)
        xml_row.addWidget(clear_xml_btn)
        xml_holder = QWidget()
        xml_holder.setLayout(xml_row)
        game_form.addRow(tr("dlg.list.xml_label", "Catalog .pncat / XML (Optional)"), xml_holder)

        xml_hint = QLabel(
            tr(
                "dlg.list.xml_hint",
                "<i>Associate a fast catalog (<b>.pncat</b>) or XML/DAT file (MAME, HyperSpin, Gamelist) when ROMs "
                "only have short filenames (e.g., sf2.zip). Tip: use the <b>⚡ XML Converter</b> tab for instant loading on large sets.</i>",
            )
        )
        xml_hint.setStyleSheet("color: #aab1c0; font-size: 8.5pt;")
        xml_hint.setWordWrap(True)
        game_form.addRow("", xml_hint)

        self.emulator_combo = QComboBox()
        self.emulator_combo.addItem(tr("dlg.list.no_default_emu", "No default emulator"), None)
        for e in emulators:
            self.emulator_combo.addItem(e["name"], e["id"])
        game_form.addRow(tr("dlg.list.default_emu_label", "Default emulator"), self.emulator_combo)

        scroll_layout.addWidget(self.game_settings_group)

        # 3. Grupo para Menú de Sistemas (Selección y orden de listas vinculadas)
        self.menu_settings_group = QGroupBox(tr("dlg.list.menu_group", "Systems to include in this Menu"))
        menu_layout = QVBoxLayout(self.menu_settings_group)
        menu_layout.setSpacing(8)

        menu_hint = QLabel(tr("dlg.list.menu_hint", "Check the lists that will be part of this menu and use the arrows to set the order:"))
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

        up_btn = QPushButton(tr("dlg.list.move_up", "▲ Move Up"))
        up_btn.clicked.connect(self._move_item_up)
        btn_vbox.addWidget(up_btn)

        down_btn = QPushButton(tr("dlg.list.move_down", "▼ Move Down"))
        down_btn.clicked.connect(self._move_item_down)
        btn_vbox.addWidget(down_btn)

        btn_vbox.addSpacing(10)

        check_all_btn = QPushButton(tr("dlg.list.check_all", "Check All"))
        check_all_btn.clicked.connect(lambda: self._check_all_lists(True))
        btn_vbox.addWidget(check_all_btn)

        uncheck_all_btn = QPushButton(tr("dlg.list.uncheck_all", "Uncheck All"))
        uncheck_all_btn.clicked.connect(lambda: self._check_all_lists(False))
        btn_vbox.addWidget(uncheck_all_btn)

        btn_vbox.addStretch()
        list_and_controls.addLayout(btn_vbox)
        menu_layout.addLayout(list_and_controls)

        scroll_layout.addWidget(self.menu_settings_group)

        # 3. Grupo de Filtros de Juegos (Reglas dinámicas, aplicable a lista común y lista filtrada)
        self.filtered_settings_group = QGroupBox(tr("dlg.list.filters_group_optional", "Game Filters (Optional)"))
        filt_vbox = QVBoxLayout(self.filtered_settings_group)
        filt_vbox.setSpacing(10)

        self.filt_hint = QLabel(
            tr(
                "dlg.list.filt_hint_games",
                "<b>Optional:</b> You can define one or more filter rules so only games "
                "matching the selected criteria are imported (e.g., manufacturer contains 'Capcom', genre contains 'Fighting', "
                "sourcefile contains 'cps1', clone is empty for main games only, etc.). If you don't add filters, all found games are imported.",
            )
        )
        self.filt_hint.setStyleSheet("color: #aab1c0; font-size: 8.5pt;")
        self.filt_hint.setWordWrap(True)
        filt_vbox.addWidget(self.filt_hint)

        filt_form = QFormLayout()
        filt_form.setSpacing(8)

        self.filter_source_label = QLabel(tr("dlg.list.filter_source_label", "Source list *"))
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

        self.filter_emulator_label = QLabel(tr("dlg.list.filter_emu_label", "Emulator"))
        self.filter_emulator_combo = QComboBox()
        self.filter_emulator_combo.addItem(tr("dlg.list.inherit_emu", "⚡ Inherit emulator from source list"), "INHERIT")
        for e in emulators:
            self.filter_emulator_combo.addItem(e["name"], e["id"])
        filt_form.addRow(self.filter_emulator_label, self.filter_emulator_combo)

        self.filter_match_mode_combo = QComboBox()
        self.filter_match_mode_combo.addItem(tr("dlg.list.match_all", "Match all filters (AND)"), "all")
        self.filter_match_mode_combo.addItem(tr("dlg.list.match_any", "Match any filter (OR)"), "any")
        self.filter_match_mode_combo.currentIndexChanged.connect(self._update_filter_preview)
        filt_form.addRow(tr("dlg.list.match_mode_label", "Evaluation mode"), self.filter_match_mode_combo)

        self.smart_preset_label = QLabel(tr("dlg.list.smart_preset_label", "Smart collection"))
        self.smart_preset_combo = QComboBox()
        self.smart_preset_combo.addItem(tr("dlg.list.custom_rules", "— Custom rules —"), "")
        for p in SMART_COLLECTION_PRESETS:
            sp_entry = _SMART_PRESET_I18N.get(p["id"])
            sp_label = tr(*sp_entry[0]) if sp_entry else p["label"]
            self.smart_preset_combo.addItem(sp_label, p["id"])
        self.smart_preset_combo.activated.connect(self._on_smart_preset_activated)
        filt_form.addRow(self.smart_preset_label, self.smart_preset_combo)

        self.sort_mode_label = QLabel(tr("dlg.list.sort_mode_label", "Game order"))
        self.sort_mode_combo = QComboBox()
        for s_key, s_label in SORT_MODES:
            self.sort_mode_combo.addItem(_tr_from_map(_SORT_MODE_I18N, s_key, s_label), s_key)
        filt_form.addRow(self.sort_mode_label, self.sort_mode_combo)

        filt_vbox.addLayout(filt_form)

        # Encabezado de reglas de filtrado
        rules_header_layout = QHBoxLayout()
        rules_header_label = QLabel(tr("dlg.list.rules_header", "<b>Filter Rules:</b>"))
        self.add_filter_btn = QPushButton(tr("dlg.list.add_filter_btn", "＋ Add filter"))
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
        self.filter_preview_label = QLabel(tr("dlg.list.preview_calculating", "📊 Preview: Calculating..."))
        self.filter_preview_label.setStyleSheet("color: #7dd3fc; font-weight: 500; font-size: 8.5pt;")
        preview_btn = QPushButton(tr("dlg.list.refresh_preview_btn", "🔄 Refresh preview"))
        preview_btn.setToolTip(tr("dlg.list.refresh_preview_tooltip", "Recalculate matching games with current filters"))
        preview_btn.clicked.connect(self._update_filter_preview)
        preview_box.addWidget(self.filter_preview_label, 1)
        preview_box.addWidget(preview_btn)
        self.filter_preview_widget = QWidget()
        self.filter_preview_widget.setLayout(preview_box)
        filt_vbox.addWidget(self.filter_preview_widget)

        scroll_layout.addWidget(self.filtered_settings_group)

        # 4. Sección de Medios y Arte (especificada dinámicamente según el diseño visual)
        media_group = QGroupBox(tr("dlg.list.media_group", "Media & Artwork Folders (Optional)"))
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
        bezel_hud_group = QGroupBox(tr("dlg.list.bezel_hud_group", "Decorative Frame / Bezel HUD (Emulator Overlay)"))
        bezel_hud_layout = QFormLayout(bezel_hud_group)
        bezel_hud_layout.setSpacing(8)

        self.bezel_hud_enabled_cb = QCheckBox(tr("dlg.list.bezel_hud_enabled", "Enable Bezel HUD for this list"))
        self.bezel_hud_enabled_cb.setStyleSheet("font-weight: 600;")
        self.bezel_hud_enabled_cb.setChecked(True)
        bezel_hud_layout.addRow(self.bezel_hud_enabled_cb)

        self.bezel_hud_path_edit = QLineEdit()
        self.bezel_hud_path_edit.setPlaceholderText(tr("dlg.list.bezel_hud_placeholder", "Folder with transparent PNG frames for the HUD"))
        browse_hud_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
        browse_hud_btn.clicked.connect(self.pick_bezel_hud)
        hud_box = QHBoxLayout()
        hud_box.addWidget(self.bezel_hud_path_edit, 1)
        hud_box.addWidget(browse_hud_btn)
        hud_holder = QWidget()
        hud_holder.setLayout(hud_box)
        bezel_hud_layout.addRow(tr("dlg.list.bezel_hud_folder", "Bezel HUD Folder:"), hud_holder)

        lbl_hud_hint = QLabel(
            tr(
                "dlg.list.bezel_hud_hint",
                "<i>This folder is independent from the visual layout bezels. "
                "It contains PNG images with a transparent center to overlay on top of the emulator while playing. "
                "It looks first by ROM name (e.g., pacman.png) and falls back to default.png (or default_v.png for vertical-screen games).</i>",
            )
        )
        lbl_hud_hint.setStyleSheet("color: #8f9aa9; font-size: 8.5pt;")
        lbl_hud_hint.setWordWrap(True)
        bezel_hud_layout.addRow(lbl_hud_hint)

        scroll_layout.addWidget(bezel_hud_group)

        # 6. Pantalla de Carga / Loading HUD
        loading_group = QGroupBox(tr("dlg.list.loading_group", "Loading Screen / Loading HUD"))
        loading_layout = QFormLayout(loading_group)
        loading_layout.setSpacing(8)

        self.loading_path_edit = QLineEdit()
        self.loading_path_edit.setPlaceholderText(tr("dlg.list.loading_placeholder", "Loading Screens folder (e.g., D:/Media/Loading)"))
        browse_load_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
        browse_load_btn.clicked.connect(self.pick_loading_path)
        load_box = QHBoxLayout()
        load_box.addWidget(self.loading_path_edit, 1)
        load_box.addWidget(browse_load_btn)
        load_holder = QWidget()
        load_holder.setLayout(load_box)
        loading_layout.addRow(tr("dlg.list.loading_folder", "Loading Screens Folder:"), load_holder)

        lbl_load_hint = QLabel(
            tr(
                "dlg.list.loading_hint",
                "<i>Folder structure:</i><br>"
                "• <b>Priority 1 (Per game):</b> Subfolder named after the ROM containing <code>&lt;rom&gt;_i.ext</code> (intro) and <code>&lt;rom&gt;_o.ext</code> (outro).<br>"
                "• <b>Priority 2 (System default):</b> <code>default</code> subfolder containing <code>default_i.ext</code> and <code>default_o.ext</code>.<br>"
                "• <b>Priority 3 (Global generic):</b> If not found, <code>splash/loading.jpg</code> is used automatically.<br>"
                "<i>(Intro and outro durations are calibrated individually per emulator).</i>",
            )
        )
        lbl_load_hint.setStyleSheet("color: #8f9aa9; font-size: 8.5pt;")
        lbl_load_hint.setWordWrap(True)
        loading_layout.addRow(lbl_load_hint)

        scroll_layout.addWidget(loading_group)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # 5. Botones de acción siempre fijos y visibles en la parte inferior
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        _localize_dialog_buttons(buttons)
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
            if existing.get("loading_path"):
                self.loading_path_edit.setText(self._normalize_path(existing["loading_path"]))
            elif existing.get("loading_in_path"):
                self.loading_path_edit.setText(self._normalize_path(existing["loading_in_path"]))
            for k in ("boxart", "flyer", "wheel", "video", "cartart", "cabinet", "marquee", "bezel", "manual"):
                field_name = f"{k}_path"
                if field_name in existing.keys() and existing[field_name]:
                    self._media_values[k] = self._normalize_path(existing[field_name])
            if "cartart" in self._media_values and "discart" not in self._media_values:
                self._media_values["discart"] = self._media_values["cartart"]

            if list_type in ("filtered", "games"):
                mode = existing.get("filter_match_mode", "all")
                idx_m = self.filter_match_mode_combo.findData(mode)
                if idx_m >= 0:
                    self.filter_match_mode_combo.setCurrentIndex(idx_m)

                sort_val = existing.get("sort_mode") or "title"
                idx_sm = self.sort_mode_combo.findData(sort_val)
                if idx_sm >= 0:
                    self.sort_mode_combo.setCurrentIndex(idx_sm)

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
        plat = list_info.get("platform") or tr("dlg.list.undefined_platform", "Undefined")
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
        if hasattr(self, "smart_preset_label"):
            self.smart_preset_label.setVisible(is_filtered)
            self.smart_preset_combo.setVisible(is_filtered)
        if hasattr(self, "sort_mode_label"):
            self.sort_mode_label.setVisible(is_filtered or is_games)
            self.sort_mode_combo.setVisible(is_filtered or is_games)

        if is_menu:
            if not self.platform_edit.text().strip():
                self.platform_edit.setText(tr("dlg.list.default_menu_platform", "Main Menu"))
            if not self.name_edit.text().strip():
                self.name_edit.setText(tr("dlg.list.default_menu_name", "Systems"))
        elif is_games:
            self.filtered_settings_group.setTitle(tr("dlg.list.filters_group_optional", "Game Filters (Optional)"))
            if hasattr(self, "filt_hint"):
                self.filt_hint.setText(
                    tr(
                        "dlg.list.filt_hint_games",
                        "<b>Optional:</b> You can define one or more filter rules so only games "
                        "matching the selected criteria are imported (e.g., manufacturer contains 'Capcom', genre contains 'Fighting', "
                        "sourcefile contains 'cps1', clone is empty for main games only, etc.). If you don't add filters, all found games are imported.",
                    )
                )
        elif is_filtered:
            self.filtered_settings_group.setTitle(tr("dlg.list.filtered_group_title", "Filtered List Configuration"))
            if hasattr(self, "filt_hint"):
                self.filt_hint.setText(
                    tr(
                        "dlg.list.filt_hint_filtered",
                        "A <b>Filtered List</b> creates a dynamic list from another existing game list, "
                        "evaluating one or more filters based on its fields (sourcefile, genre, manufacturer, year, title, etc.).",
                    )
                )
            if not self.filter_rule_rows:
                self._add_filter_rule_row()
            self._on_filter_source_changed()

    def _on_smart_preset_activated(self):
        """Aplica reglas, criterio y orden de una colección inteligente predefinida."""
        preset_id = self.smart_preset_combo.currentData()
        if not preset_id:
            return
        preset = next((p for p in SMART_COLLECTION_PRESETS if p["id"] == preset_id), None)
        if not preset:
            return

        for r_data in list(self.filter_rule_rows):
            self._remove_filter_rule_row(r_data)

        for r in preset.get("rules", []):
            self._add_filter_rule_row(
                field=r.get("field", "is_favorite"),
                op=r.get("operator", "equals"),
                val=r.get("value", "1"),
            )

        idx_m = self.filter_match_mode_combo.findData(preset.get("match_mode", "all"))
        if idx_m >= 0:
            self.filter_match_mode_combo.setCurrentIndex(idx_m)

        idx_s = self.sort_mode_combo.findData(preset.get("sort_mode", "title"))
        if idx_s >= 0:
            self.sort_mode_combo.setCurrentIndex(idx_s)

        curr_name = self.name_edit.text().strip()
        preset_names = {p["default_name"] for p in SMART_COLLECTION_PRESETS}
        for _lbl_pair, (n_key, n_en) in _SMART_PRESET_I18N.values():
            preset_names.add(tr(n_key, n_en))
        sp_entry = _SMART_PRESET_I18N.get(preset_id)
        target_default_name = tr(*sp_entry[1]) if sp_entry else preset["default_name"]
        if not curr_name or curr_name in preset_names:
            self.name_edit.setText(target_default_name)

        self._update_filter_preview()

    def selected_sort_mode(self) -> str:
        """Retorna el modo de ordenación elegido para la lista."""
        if hasattr(self, "sort_mode_combo"):
            return str(self.sort_mode_combo.currentData() or "title")
        return "title"

    def _add_filter_rule_row(self, field="sourcefile", op="contains", val=""):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        field_combo = QComboBox()
        for f_key, f_label in FILTERABLE_FIELDS:
            field_combo.addItem(_tr_from_map(_FILTER_FIELD_I18N, f_key, f_label), f_key)
        idx = field_combo.findData(field)
        if idx >= 0:
            field_combo.setCurrentIndex(idx)

        op_combo = QComboBox()
        for o_key, o_label in FILTER_OPERATORS:
            op_combo.addItem(_tr_from_map(_FILTER_OP_I18N, o_key, o_label), o_key)
        idx_o = op_combo.findData(op)
        if idx_o >= 0:
            op_combo.setCurrentIndex(idx_o)

        val_edit = QLineEdit(str(val or ""))
        val_edit.setPlaceholderText(tr("dlg.list.filter_val_placeholder", "Value to search..."))

        def _on_op_changed():
            curr_op = op_combo.currentData()
            if curr_op in ("is_empty", "is_not_empty"):
                val_edit.setEnabled(False)
                val_edit.setPlaceholderText(tr("dlg.list.filter_val_none", "(No value required)"))
            else:
                val_edit.setEnabled(True)
                val_edit.setPlaceholderText(tr("dlg.list.filter_val_placeholder", "Value to search..."))
            self._update_filter_preview()

        op_combo.currentIndexChanged.connect(_on_op_changed)
        field_combo.currentIndexChanged.connect(self._update_filter_preview)
        val_edit.textChanged.connect(self._update_filter_preview)
        _on_op_changed()

        del_btn = QPushButton("✕")
        del_btn.setToolTip(tr("dlg.list.remove_rule_tooltip", "Remove this rule"))
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
                for k in ("boxart", "flyer", "wheel", "video", "cartart", "cabinet", "marquee", "bezel", "manual"):
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
            self.filter_preview_label.setText(tr("dlg.list.preview_select_source", "📊 Preview: Select a source list."))
            return

        source_games = self.db.get_games(source_id, enriched=False)
        total = len(source_games)
        rules = self._get_filter_rules_from_ui()
        mode = self.filter_match_mode_combo.currentData() or "all"
        matching_count = sum(1 for g in source_games if game_matches_filter(g, rules, mode))
        self.filter_preview_label.setText(
            tr(
                "dlg.list.preview_count",
                "📊 Preview: <b>{matching}</b> of <b>{total}</b> games match current filters.",
                matching=matching_count,
                total=total,
            )
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
            raw_label = item.get("label", key.capitalize())
            label = _tr_from_map(_MEDIA_LABEL_I18N, raw_label, raw_label)
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
            edit.setPlaceholderText(
                tr("dlg.list.media_folder_placeholder", "{label} folder (e.g., media/{folder})...", label=label, folder=folder_name)
            )
            
            init_val = self._media_values.get(key, "")
            if init_val:
                edit.setText(init_val)

            edit.textChanged.connect(lambda txt, k=key: self._media_values.__setitem__(k, self._normalize_path(txt)))
            edit.editingFinished.connect(lambda e=edit: e.setText(self._normalize_path(e.text())))

            browse_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
            browse_btn.clicked.connect(
                lambda checked=False, e=edit, l=label, k=key: self._pick_media_folder(
                    e, tr("dlg.list.pick_media_folder_title", "Select {label} folder", label=l), k
                )
            )

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
            self, tr("dlg.list.pick_icon_title", "Select list icon"),
            str(Path(current).parent) if current and Path(current).parent.is_dir() else "",
            tr("dlg.list.pick_icon_filter", "Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg);;All files (*.*)")
        )
        if path:
            self.icon_path_edit.setText(self._normalize_path(path))

    def pick_bezel_hud(self):
        """Abre un selector para elegir la carpeta del Bezel HUD."""
        current = self.bezel_hud_path_edit.text().strip() if hasattr(self, "bezel_hud_path_edit") else ""
        initial_dir = current if (current and Path(current).is_dir()) else self._get_primary_rom_folder()
        path = QFileDialog.getExistingDirectory(self, tr("dlg.list.pick_bezel_hud_title", "Select Bezel HUD folder"), initial_dir or "")
        if path:
            self.bezel_hud_path_edit.setText(self._normalize_path(path))

    def pick_loading_path(self):
        """Abre un selector para elegir la carpeta de pantallas de carga (Loading HUD)."""
        current = self.loading_path_edit.text().strip() if hasattr(self, "loading_path_edit") else ""
        initial_dir = current if (current and Path(current).is_dir()) else str(APP_DIR)
        path = QFileDialog.getExistingDirectory(  
            self, tr("dlg.list.pick_loading_title", "Select Loading Screens folder"),
            initial_dir
        )
        if path:
            self.loading_path_edit.setText(self._normalize_path(path))

    def pick_folder(self):
        current_folders = self.get_rom_folders()
        initial_dir = current_folders[-1] if current_folders else ""
        if initial_dir and Path(initial_dir).parent.is_dir():
            initial_dir = str(Path(initial_dir).parent)
        folder = QFileDialog.getExistingDirectory(
            self,
            tr("dlg.list.pick_rom_folder_title", "Add game folder (ROMs)"),
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
            tr("dlg.list.pick_xml_title", "Select .pncat or XML file with ROM names and metadata"),
            initial_dir or "",
            tr(
                "dlg.list.pick_xml_filter",
                "Catalogs & XML (*.pncat *.xml *.dat);;PlayNexus Fast Catalog (*.pncat);;XML / DAT Files (*.xml *.dat);;All files (*.*)",
            )
        )
        if path:
            self.xml_edit.setText(self._normalize_path(path))

    def _on_preset_selected(self, index):
        title = self.preset_combo.currentData() or self.preset_combo.currentText()
        if title in PRESET_EXTENSIONS and title != "Personalizado...":
            plat, exts = PRESET_EXTENSIONS[title]
            if not self.platform_edit.text().strip():
                self.platform_edit.setText(plat)
            self.extensions_edit.setText(exts)

    def validate_and_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("dlg.list.err_name_title", "Name required"), tr("dlg.list.err_name_msg", "Please enter a name for the list."))
            self.name_edit.setFocus()
            return

        is_menu = (self.type_combo.currentData() == "menu")
        is_filtered = (self.type_combo.currentData() == "filtered")
        if is_menu:
            checked_count = sum(1 for i in range(self.sublists_list.count()) if self.sublists_list.item(i).checkState() == Qt.Checked)
            if checked_count == 0:
                answer = QMessageBox.question(
                    self,
                    tr("dlg.list.warn_empty_menu_title", "Menu without systems"),
                    tr("dlg.list.warn_empty_menu_msg", "You didn't select any list to include in this menu.\nDo you want to create it anyway and link systems later?"),
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
                QMessageBox.warning(self, tr("dlg.list.err_source_title", "Source list required"), tr("dlg.list.err_source_msg", "Please select the source list from which games will be filtered."))
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
                    tr("dlg.list.err_filter_title", "Filter required"),
                    tr("dlg.list.err_filter_msg", "Please configure at least one filter rule with a value (e.g., sourcefile contains 'cps1').")
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
                tr("dlg.list.err_ext_title", "Extension error"),
                tr("dlg.list.err_ext_msg", "Invalid extension configuration:\n\n{error}", error=err)
            )
            self.extensions_edit.setFocus()
            return

        # Validar carpetas de juegos si fueron especificadas
        folders = self.get_rom_folders()
        for f in folders:
            if not Path(f).is_dir():
                QMessageBox.warning(
                    self,
                    tr("dlg.list.err_folder_title", "Folder not found"),
                    tr("dlg.list.err_folder_msg", "The specified folder does not exist or is not accessible:\n{folder}\n\nPlease select valid folders.", folder=f)
                )
                self.folder_edit.setFocus()
                return

        # Validar archivo XML si fue especificado
        xml_path = self.xml_edit.text().strip() if hasattr(self, "xml_edit") else ""
        if xml_path:
            if not Path(xml_path).is_file():
                QMessageBox.warning(
                    self,
                    tr("dlg.list.err_xml_title", "XML file not found"),
                    tr("dlg.list.err_xml_msg", "The specified XML file does not exist or is not accessible:\n{path}\n\nPlease select a valid XML file.", path=xml_path)
                )
                self.xml_edit.setFocus()
                return

        # Si hay advertencias (ejemplo: extensión genérica .bin)
        if warnings:
            warn_msg = "\n\n".join(warnings)
            answer = QMessageBox.question(
                self,
                tr("dlg.list.warn_ext_title", "Notice about configured extensions"),
                tr("dlg.list.warn_ext_msg", "{warnings}\n\nDo you want to continue with this configuration?", warnings=warn_msg),
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

        # Restringir estrictamente a los requerimientos explícitos del layout seleccionado
        layout_name = self.layout_combo.currentText()
        spec = get_layout_media_spec(layout_name)
        active_keys = {item.get("key") for item in spec} if spec else set()

        media_path = ""  # ya no se usa campo raíz global; cada carpeta se elige individualmente
        boxart_path = self._media_values.get("boxart", "") if "boxart" in active_keys else ""
        flyer_path = self._media_values.get("flyer", "") if "flyer" in active_keys else ""
        wheel_path = self._media_values.get("wheel", "") if "wheel" in active_keys else ""
        video_path = self._media_values.get("video", "") if "video" in active_keys else ""
        if "discart" in active_keys:
            cartart_path = self._media_values.get("discart", "") or self._media_values.get("cartart", "")
        elif "cartart" in active_keys:
            cartart_path = self._media_values.get("cartart", "") or self._media_values.get("discart", "")
        else:
            cartart_path = ""
        cabinet_path = self._media_values.get("cabinet", "") if "cabinet" in active_keys else ""
        marquee_path = self._media_values.get("marquee", "") if "marquee" in active_keys else ""
        bezel_path = self._media_values.get("bezel", "") if "bezel" in active_keys else ""
        manual_path = self._media_values.get("manual", "") if "manual" in active_keys else ""
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
            self._normalize_path(self.loading_path_edit.text().strip()),
            self._normalize_path(self.loading_path_edit.text().strip()),
            manual_path,
        )



class EmulatorDialog(QDialog):
    """Diálogo para registrar o editar un emulador."""
    def __init__(self, parent=None, existing=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.emu.title_edit", "Edit emulator") if existing else tr("dlg.emu.title_new", "Register emulator"))
        self.setMinimumWidth(560)
        self._last_test_rom_dir = ""

        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("dlg.emu.name_placeholder", "e.g., RetroArch, Snes9x, PCSX2, DuckStation..."))
        self.exe = QLineEdit()
        self.exe.setPlaceholderText(tr("dlg.emu.exe_placeholder", "Path to executable file (.exe)"))
        self.args = QLineEdit('"{rom}"')
        self.platform = QLineEdit()
        self.platform.setPlaceholderText(tr("dlg.emu.platform_placeholder", "e.g., Super Nintendo, Multi-system..."))

        browse = QPushButton(tr("dlg.btn.browse", "Browse…"))
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
        self.preset_combo.addItem(tr("dlg.emu.select_quick_preset", "— Select a quick template… —"), None)
        self._load_presets()
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        presets_row.addWidget(self.preset_combo, 1)
        form.addRow(tr("dlg.emu.quick_preset_label", "Quick template"), presets_row)

        form.addRow(tr("dlg.emu.name_label", "Emulator name *"), self.name)
        form.addRow(tr("dlg.emu.exe_label", "Executable (.exe) *"), holder)
        form.addRow(tr("dlg.emu.args_label", "Launch arguments"), self.args)
        form.addRow(tr("dlg.emu.platform_label", "Platform (optional)"), self.platform)

        # Configuración de retardo y fade para el Bezel HUD
        self.bezel_delay_spin = QDoubleSpinBox()
        self.bezel_delay_spin.setRange(0.0, 30.0)
        self.bezel_delay_spin.setSingleStep(0.5)
        self.bezel_delay_spin.setDecimals(1)
        self.bezel_delay_spin.setSuffix(tr("dlg.common.sec_suffix", " sec"))
        self.bezel_delay_spin.setValue(0.0)
        self.bezel_delay_spin.setToolTip(tr("dlg.emu.bezel_delay_tooltip", "Wait time after launch before showing the Bezel HUD and allowing exit."))

        self.bezel_fade_spin = QDoubleSpinBox()
        self.bezel_fade_spin.setRange(0.0, 10.0)
        self.bezel_fade_spin.setSingleStep(0.1)
        self.bezel_fade_spin.setDecimals(1)
        self.bezel_fade_spin.setSuffix(tr("dlg.common.sec_suffix", " sec"))
        self.bezel_fade_spin.setValue(0.3)
        self.bezel_fade_spin.setToolTip(tr("dlg.emu.bezel_fade_tooltip", "Duration of the Bezel HUD fade-in animation in seconds."))

        bezel_anim_row = QHBoxLayout()
        bezel_anim_row.addWidget(QLabel(tr("dlg.emu.delay_label", "Delay:")))
        bezel_anim_row.addWidget(self.bezel_delay_spin, 1)
        bezel_anim_row.addSpacing(16)
        bezel_anim_row.addWidget(QLabel(tr("dlg.emu.fade_in_label", "Fade-in:")))
        bezel_anim_row.addWidget(self.bezel_fade_spin, 1)

        bezel_holder = QWidget()
        bezel_holder.setLayout(bezel_anim_row)
        form.addRow(tr("dlg.emu.bezel_hud_row", "Bezel HUD (Appearance)"), bezel_holder)

        # Configuración de tiempos de Loading Screen (Apertura y Cierre)
        self.loading_time_spin = QDoubleSpinBox()
        self.loading_time_spin.setRange(0.0, 30.0)
        self.loading_time_spin.setSingleStep(0.5)
        self.loading_time_spin.setDecimals(1)
        self.loading_time_spin.setSuffix(tr("dlg.common.sec_suffix", " sec"))
        self.loading_time_spin.setValue(1.5)
        self.loading_time_spin.setToolTip(tr("dlg.emu.loading_in_tooltip", "Time the loading screen is displayed when launching the emulator (0 to disable)."))

        self.exit_loading_time_spin = QDoubleSpinBox()
        self.exit_loading_time_spin.setRange(0.0, 30.0)
        self.exit_loading_time_spin.setSingleStep(0.5)
        self.exit_loading_time_spin.setDecimals(1)
        self.exit_loading_time_spin.setSuffix(tr("dlg.common.sec_suffix", " sec"))
        self.exit_loading_time_spin.setValue(1.0)
        self.exit_loading_time_spin.setToolTip(tr("dlg.emu.loading_out_tooltip", "Time the loading screen is displayed when closing the emulator while the layout returns."))

        loading_row = QHBoxLayout()
        loading_row.addWidget(QLabel(tr("dlg.emu.loading_in_label", "Intro (In):")))
        loading_row.addWidget(self.loading_time_spin, 1)
        loading_row.addSpacing(16)
        loading_row.addWidget(QLabel(tr("dlg.emu.loading_out_label", "Outro (Out):")))
        loading_row.addWidget(self.exit_loading_time_spin, 1)

        loading_holder = QWidget()
        loading_holder.setLayout(loading_row)
        form.addRow(tr("dlg.emu.loading_row", "Loading Screen (HUD)"), loading_holder)

        lockout_hint = QLabel(
            tr(
                "dlg.emu.lockout_hint",
                "🔒 <i>Freeze protection: The exit button or command (Escape / Back+Start) remains locked "
                "during initialization until the Bezel finishes appearing.</i>",
            )
        )
        lockout_hint.setStyleSheet("color: #7289da; font-size: 8.5pt;")
        lockout_hint.setWordWrap(True)
        form.addRow("", lockout_hint)

        hint = QLabel(
            tr(
                "dlg.emu.args_hint",
                "<b>Supported argument placeholders:</b><br>"
                "<code>{rom}</code> or <code>[romfilename]</code>: Full path to the game file.<br>"
                "<code>{rom_dir}</code> or <code>[rompath]</code>: Folder where the game is located.<br>"
                "<code>{rom_name}</code> or <code>[name]</code>: Filename without extension.<br>"
                "<i>• For Windows Games (Attract-Mode / PC): Executable <code>cmd</code> and arguments <code>/c \"[romfilename]\"</code></i><br>"
                "<i>• For RetroArch: <code>-f -L cores\\genesis_plus_gx_sot4w_libretro.dll \"{rom}\"</code></i>",
            )
        )
        hint.setStyleSheet("color: #aab1c0; font-size: 9pt;")

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)

        actions_bar = QHBoxLayout()
        self.run_emu_btn = QPushButton(tr("dlg.emu.run_btn", "▶ Launch emulator"))
        self.run_emu_btn.setAutoDefault(False)
        self.run_emu_btn.setToolTip(
            tr("dlg.emu.run_tooltip", "Open the emulator without ROM arguments to adjust settings")
        )
        self.run_emu_btn.clicked.connect(self._run_emulator_standalone)

        self.test_args_btn = QPushButton(tr("dlg.emu.test_args_btn", "🧪 Test arguments"))
        self.test_args_btn.setAutoDefault(False)
        self.test_args_btn.setToolTip(
            tr(
                "dlg.emu.test_args_tooltip",
                "Launch the emulator with the configured arguments (prompts for a test ROM if ROM placeholders are used)",
            )
        )
        self.test_args_btn.clicked.connect(self._test_emulator_args)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        _localize_dialog_buttons(buttons)
        buttons.accepted.connect(self.validate_accept)
        buttons.rejected.connect(self.reject)

        actions_bar.addWidget(self.run_emu_btn)
        actions_bar.addWidget(self.test_args_btn)
        actions_bar.addStretch()
        actions_bar.addWidget(buttons)
        layout.addLayout(actions_bar)

        if existing:
            self.name.setText(existing["name"])
            self.exe.setText(existing["executable"])
            self.args.setText(existing["arguments"])
            self.platform.setText(existing["platform"] or "")
            try:
                self.bezel_delay_spin.setValue(float(existing.get("bezel_delay", 0.0) or 0.0))
            except Exception:
                self.bezel_delay_spin.setValue(0.0)
            try:
                self.bezel_fade_spin.setValue(float(existing.get("bezel_fade", 0.3) if existing.get("bezel_fade") is not None else 0.3))
            except Exception:
                self.bezel_fade_spin.setValue(0.3)
            try:
                self.loading_time_spin.setValue(float(existing.get("loading_time", 1.5) if existing.get("loading_time") is not None else 1.5))
            except Exception:
                self.loading_time_spin.setValue(1.5)
            try:
                self.exit_loading_time_spin.setValue(float(existing.get("exit_loading_time", 1.0) if existing.get("exit_loading_time") is not None else 1.0))
            except Exception:
                self.exit_loading_time_spin.setValue(1.0)

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
        if "bezel_delay" in tmpl:
            try:
                self.bezel_delay_spin.setValue(float(tmpl["bezel_delay"]))
            except Exception:
                pass
        if "bezel_fade" in tmpl:
            try:
                self.bezel_fade_spin.setValue(float(tmpl["bezel_fade"]))
            except Exception:
                pass
        if "loading_time" in tmpl:
            try:
                self.loading_time_spin.setValue(float(tmpl["loading_time"]))
            except Exception:
                pass
        if "exit_loading_time" in tmpl:
            try:
                self.exit_loading_time_spin.setValue(float(tmpl["exit_loading_time"]))
            except Exception:
                pass

    def _preset_windows_cmd(self):
        if not self.name.text().strip():
            self.name.setText(tr("dlg.emu.windows_games_cmd", "Windows Games (cmd)"))
        self.exe.setText("cmd")
        self.args.setText('/c "[romfilename]"')
        if not self.platform.text().strip():
            self.platform.setText("PC Games")

    def pick_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dlg.emu.pick_exe_title", "Select emulator executable"),
            "",
            tr("dlg.common.exe_filter", "Executable files (*.exe *.bat *.cmd);;All files (*.*)")
        )
        if path:
            self.exe.setText(path)

    def _run_emulator_standalone(self):
        """Abre el ejecutable del emulador limpio para configurar controles/opciones."""
        self._launch_preview(with_args=False)

    def _test_emulator_args(self):
        """Prueba el emulador con los argumentos actuales (pidiendo ROM si hay marcadores)."""
        self._launch_preview(with_args=True)

    def _launch_preview(self, with_args: bool):
        from playnexus.services.launcher import (
            has_rom_placeholder,
            launch_emulator_process,
            resolve_executable_path,
        )

        raw_exe = self.exe.text().strip()
        if not raw_exe:
            QMessageBox.warning(
                self,
                tr("dlg.common.required_title", "Required field"),
                tr("dlg.emu.err_exe_msg", "Please select the path to the executable file."),
            )
            self.exe.setFocus()
            return

        try:
            resolve_executable_path(raw_exe)
        except Exception as e:
            QMessageBox.warning(
                self,
                tr("dlg.emu.exe_missing_title", "Executable not found"),
                str(e),
            )
            self.exe.setFocus()
            return

        template = ""
        rom_path = None
        if with_args:
            template = self.args.text().strip()
            if has_rom_placeholder(template):
                chosen_rom, _ = QFileDialog.getOpenFileName(
                    self,
                    tr("dlg.emu.pick_test_rom_title", "Select a ROM file to test arguments"),
                    self._last_test_rom_dir or "",
                    tr("dlg.common.all_files_filter", "All files (*.*)"),
                )
                if not chosen_rom:
                    return
                rom_path = chosen_rom
                self._last_test_rom_dir = str(Path(chosen_rom).parent)

        try:
            launch_emulator_process(raw_exe, template=template, rom_path=rom_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("dlg.emu.launch_err_title", "Could Not Launch Emulator"),
                tr("dlg.emu.launch_err_msg", "An error occurred while launching the emulator:\n{error}", error=e),
            )

    def validate_accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, tr("dlg.common.required_title", "Required field"), tr("dlg.emu.err_name_msg", "Please enter a name for the emulator."))
            self.name.setFocus()
            return
        raw_exe = self.exe.text().strip()
        if not raw_exe:
            QMessageBox.warning(self, tr("dlg.common.required_title", "Required field"), tr("dlg.emu.err_exe_msg", "Please select the path to the executable file."))
            self.exe.setFocus()
            return

        exe_path = Path(raw_exe)
        if not exe_path.is_file() and not shutil.which(raw_exe):
            confirm = QMessageBox.question(
                self,
                tr("dlg.emu.exe_missing_title", "Executable not found"),
                tr(
                    "dlg.emu.exe_missing_msg",
                    "The executable file was not currently found at the specified path or in the system PATH:\n{path}\n\nDo you want to save it anyway?",
                    path=raw_exe,
                ),
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
            self.platform.text().strip(),
            float(self.bezel_delay_spin.value()),
            float(self.bezel_fade_spin.value()),
            float(self.loading_time_spin.value()),
            float(self.exit_loading_time_spin.value()),
        )


class TemplateEditDialog(QDialog):
    """Diálogo modal para crear o editar una plantilla rápida de emulador."""
    def __init__(self, parent=None, existing=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.tmpl.title_edit", "Edit Emulator Template") if existing else tr("dlg.tmpl.title_new", "New Emulator Template"))
        self.setMinimumWidth(540)

        self.name_edit = QLineEdit(existing.get("name", "") if existing else "")
        self.name_edit.setPlaceholderText(tr("dlg.tmpl.name_placeholder", "e.g., RetroArch - Genesis Plus GX, DuckStation, PCSX2..."))

        self.exe_edit = QLineEdit(existing.get("executable", "") if existing else "")
        self.exe_edit.setPlaceholderText(tr("dlg.tmpl.exe_placeholder", "e.g., retroarch.exe, cmd, pcsx2-qtx64.exe..."))
        browse_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
        browse_btn.clicked.connect(self._pick_exe)
        exe_row = QHBoxLayout()
        exe_row.addWidget(self.exe_edit, 1)
        exe_row.addWidget(browse_btn)
        exe_holder = QWidget()
        exe_holder.setLayout(exe_row)

        self.args_edit = QLineEdit(existing.get("arguments", "") if existing else '"{rom}"')
        self.args_edit.setPlaceholderText(tr("dlg.tmpl.args_placeholder", 'e.g., -f -L cores\\core.dll "{rom}" or /c "[romfilename]"'))

        self.plat_edit = QLineEdit(existing.get("platform", "") if existing else "")
        self.plat_edit.setPlaceholderText(tr("dlg.tmpl.platform_placeholder", "e.g., Multi-system, PC Games, Arcade, Super Nintendo..."))

        self.desc_edit = QLineEdit(existing.get("description", "") if existing else "")
        self.desc_edit.setPlaceholderText(tr("dlg.tmpl.desc_placeholder", "Brief description or notes about the template"))

        self.bezel_delay_spin = QDoubleSpinBox()
        self.bezel_delay_spin.setRange(0.0, 30.0)
        self.bezel_delay_spin.setSingleStep(0.5)
        self.bezel_delay_spin.setDecimals(1)
        self.bezel_delay_spin.setSuffix(tr("dlg.common.sec_suffix", " sec"))
        try:
            self.bezel_delay_spin.setValue(float(existing.get("bezel_delay", 0.0) or 0.0) if existing else 0.0)
        except Exception:
            self.bezel_delay_spin.setValue(0.0)

        self.bezel_fade_spin = QDoubleSpinBox()
        self.bezel_fade_spin.setRange(0.0, 10.0)
        self.bezel_fade_spin.setSingleStep(0.1)
        self.bezel_fade_spin.setDecimals(1)
        self.bezel_fade_spin.setSuffix(tr("dlg.common.sec_suffix", " sec"))
        try:
            self.bezel_fade_spin.setValue(float(existing.get("bezel_fade", 0.3) if existing and existing.get("bezel_fade") is not None else 0.3))
        except Exception:
            self.bezel_fade_spin.setValue(0.3)

        anim_row = QHBoxLayout()
        anim_row.addWidget(QLabel(tr("dlg.emu.delay_label", "Delay:")))
        anim_row.addWidget(self.bezel_delay_spin, 1)
        anim_row.addSpacing(16)
        anim_row.addWidget(QLabel(tr("dlg.tmpl.fade_label", "Fade:")))
        anim_row.addWidget(self.bezel_fade_spin, 1)
        anim_holder = QWidget()
        anim_holder.setLayout(anim_row)

        self.loading_time_spin = QDoubleSpinBox()
        self.loading_time_spin.setRange(0.0, 30.0)
        self.loading_time_spin.setSingleStep(0.5)
        self.loading_time_spin.setDecimals(1)
        self.loading_time_spin.setSuffix(tr("dlg.common.sec_suffix", " sec"))
        try:
            self.loading_time_spin.setValue(float(existing.get("loading_time", 1.5) if existing and existing.get("loading_time") is not None else 1.5))
        except Exception:
            self.loading_time_spin.setValue(1.5)

        self.exit_loading_time_spin = QDoubleSpinBox()
        self.exit_loading_time_spin.setRange(0.0, 30.0)
        self.exit_loading_time_spin.setSingleStep(0.5)
        self.exit_loading_time_spin.setDecimals(1)
        self.exit_loading_time_spin.setSuffix(tr("dlg.common.sec_suffix", " sec"))
        try:
            self.exit_loading_time_spin.setValue(float(existing.get("exit_loading_time", 1.0) if existing and existing.get("exit_loading_time") is not None else 1.0))
        except Exception:
            self.exit_loading_time_spin.setValue(1.0)

        load_anim_row = QHBoxLayout()
        load_anim_row.addWidget(QLabel(tr("dlg.emu.loading_in_label", "Intro (In):")))
        load_anim_row.addWidget(self.loading_time_spin, 1)
        load_anim_row.addSpacing(16)
        load_anim_row.addWidget(QLabel(tr("dlg.emu.loading_out_label", "Outro (Out):")))
        load_anim_row.addWidget(self.exit_loading_time_spin, 1)
        load_anim_holder = QWidget()
        load_anim_holder.setLayout(load_anim_row)

        form = QFormLayout()
        form.addRow(tr("dlg.tmpl.name_label", "Template name *"), self.name_edit)
        form.addRow(tr("dlg.tmpl.exe_label", "Executable (.exe / command) *"), exe_holder)
        form.addRow(tr("dlg.emu.args_label", "Launch arguments"), self.args_edit)
        form.addRow(tr("dlg.tmpl.platform_label", "Platform"), self.plat_edit)
        form.addRow(tr("dlg.tmpl.desc_label", "Description"), self.desc_edit)
        form.addRow(tr("dlg.emu.bezel_hud_row", "Bezel HUD (Appearance)"), anim_holder)
        form.addRow(tr("dlg.emu.loading_row", "Loading Screen (HUD)"), load_anim_holder)

        hint = QLabel(
            tr(
                "dlg.tmpl.args_hint",
                "<b>Supported argument placeholders:</b><br>"
                "<code>{rom}</code> or <code>[romfilename]</code>: Full path to the game file.<br>"
                "<code>{rom_dir}</code> or <code>[rompath]</code>: Folder where the game resides.<br>"
                "<code>{rom_name}</code> or <code>[name]</code>: Game name without extension.",
            )
        )
        hint.setStyleSheet("color: #aab1c0; font-size: 8.5pt;")
        hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        _localize_dialog_buttons(buttons)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dlg.tmpl.pick_exe_title", "Select executable"),
            "",
            tr("dlg.common.exe_filter", "Executable files (*.exe *.bat *.cmd);;All files (*.*)")
        )
        if path:
            self.exe_edit.setText(path)

    def _validate(self):
        name = self.name_edit.text().strip()
        exe = self.exe_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("dlg.common.required_title", "Required field"), tr("dlg.tmpl.err_name_msg", "Enter a name for the template."))
            self.name_edit.setFocus()
            return
        if not exe:
            QMessageBox.warning(self, tr("dlg.common.required_title", "Required field"), tr("dlg.tmpl.err_exe_msg", "Enter or select an executable for the template."))
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
            "bezel_delay": f"{self.bezel_delay_spin.value():.1f}",
            "bezel_fade": f"{self.bezel_fade_spin.value():.1f}",
            "loading_time": f"{self.loading_time_spin.value():.1f}",
            "exit_loading_time": f"{self.exit_loading_time_spin.value():.1f}",
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
            title = QLabel(tr("dlg.emumgr.title", "🕹 Emulator Manager"))
            title.setFont(QFont("Segoe UI", 16, QFont.Bold))
            title.setStyleSheet("color: #ffffff;")
            h_layout.addWidget(title)

            desc = QLabel(
                tr(
                    "dlg.emumgr.desc",
                    "Register and manage the emulators installed on your system. "
                    "You can link executables, platforms, and command-line parameters for each emulator.",
                )
            )
            desc.setStyleSheet("color: #9aa5b8; font-size: 10pt;")
            desc.setWordWrap(True)
            h_layout.addWidget(desc)
            layout.addWidget(header_card)

        # Tabla de emuladores con anchos iniciales optimizados para respuesta instantánea
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            tr("dlg.emumgr.col_name", "Name"),
            tr("dlg.emumgr.col_platform", "Platform"),
            tr("dlg.emumgr.col_exe", "Executable"),
            tr("dlg.emumgr.col_args", "Arguments"),
            tr("dlg.emumgr.col_bezel_delay", "Bezel Delay"),
            tr("dlg.emumgr.col_bezel_fade", "Bezel Fade"),
            tr("dlg.emumgr.col_load_in", "Load (In)"),
            tr("dlg.emumgr.col_load_out", "Exit (Out)"),
        ])
        configure_details_table(
            self.table,
            col_widths=(180, 130, 260, 160, 100, 95, 95, 95),
        )
        self.table.doubleClicked.connect(self.edit_selected)
        layout.addWidget(self.table, 1)

        # Barra de botones
        btn_row = QHBoxLayout()
        add_btn = QPushButton(tr("dlg.emumgr.add_btn", "＋ Register new emulator"))
        add_btn.setStyleSheet("background-color: #5d48d9; color: #ffffff; font-weight: bold; padding: 8px 16px; border-radius: 6px;")
        add_btn.clicked.connect(self.add_emulator)

        edit_btn = QPushButton(tr("dlg.emumgr.edit_btn", "✎ Edit selected"))
        edit_btn.clicked.connect(self.edit_selected)

        del_btn = QPushButton(tr("dlg.emumgr.del_btn", "🗑 Delete selected"))
        del_btn.clicked.connect(self.delete_selected)

        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()

        layout.addLayout(btn_row)

    def refresh(self):
        rows = self.db.get_emulators()
        with paused_table_sorting(self.table, reenable=True):
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                name_item = SortableTableWidgetItem(row["name"])
                name_item.setData(Qt.UserRole, row["id"])
                self.table.setItem(i, 0, name_item)
                self.table.setItem(i, 1, SortableTableWidgetItem(row["platform"] or "—"))
                self.table.setItem(i, 2, SortableTableWidgetItem(row["executable"]))
                self.table.setItem(i, 3, SortableTableWidgetItem(row["arguments"]))

                d_raw = row.get("bezel_delay", "0.0")
                f_raw = row.get("bezel_fade", "0.3")
                load_raw = row.get("loading_time", "1.5")
                exit_load_raw = row.get("exit_loading_time", "1.0")
                try:
                    d_val = float(d_raw)
                except Exception:
                    d_val = 0.0
                d_str = tr("dlg.common.sec_short", "{val} s", val=f"{d_val:.1f}")
                try:
                    f_val = float(f_raw)
                except Exception:
                    f_val = 0.3
                f_str = tr("dlg.common.sec_short", "{val} s", val=f"{f_val:.1f}")
                try:
                    load_val = float(load_raw)
                except Exception:
                    load_val = 1.5
                load_str = tr("dlg.common.sec_short", "{val} s", val=f"{load_val:.1f}")
                try:
                    exit_load_val = float(exit_load_raw)
                except Exception:
                    exit_load_val = 1.0
                exit_load_str = tr("dlg.common.sec_short", "{val} s", val=f"{exit_load_val:.1f}")

                item_d = SortableTableWidgetItem(d_str, sort_key=d_val)
                item_d.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 4, item_d)

                item_f = SortableTableWidgetItem(f_str, sort_key=f_val)
                item_f.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 5, item_f)

                item_load = SortableTableWidgetItem(load_str, sort_key=load_val)
                item_load.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 6, item_load)

                item_exit_load = SortableTableWidgetItem(exit_load_str, sort_key=exit_load_val)
                item_exit_load.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, 7, item_exit_load)

    def _get_selected_id(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        return self.table.item(selected[0].row(), 0).data(Qt.UserRole)

    def add_emulator(self):
        dialog = EmulatorDialog(self)
        if dialog.exec():
            vals = dialog.values()
            name, exe, args, plat = vals[:4]
            delay = vals[4] if len(vals) > 4 else 0.0
            fade = vals[5] if len(vals) > 5 else 0.3
            load_t = vals[6] if len(vals) > 6 else 1.5
            exit_load_t = vals[7] if len(vals) > 7 else 1.0
            try:
                self.db.add_emulator(
                    name=name,
                    executable=exe,
                    arguments=args,
                    platform=plat,
                    bezel_delay=delay,
                    bezel_fade=fade,
                    loading_time=load_t,
                    exit_loading_time=exit_load_t,
                )
                self.refresh()
                self.emulators_changed.emit()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("dlg.emumgr.err_add_title", "Registration error"),
                    tr("dlg.emumgr.err_add_msg", "Could not save the emulator:\n{error}", error=e),
                )

    def edit_selected(self):
        emu_id = self._get_selected_id()
        if not emu_id:
            QMessageBox.information(
                self,
                tr("dlg.common.select_title", "Select"),
                tr("dlg.emumgr.select_edit_msg", "Select an emulator from the list to edit."),
            )
            return
        row = self.db.get_emulator(emu_id)
        if not row:
            return
        dialog = EmulatorDialog(self, existing=row)
        if dialog.exec():
            vals = dialog.values()
            name, exe, args, plat = vals[:4]
            delay = vals[4] if len(vals) > 4 else 0.0
            fade = vals[5] if len(vals) > 5 else 0.3
            load_t = vals[6] if len(vals) > 6 else 1.5
            exit_load_t = vals[7] if len(vals) > 7 else 1.0
            try:
                self.db.update_emulator(
                    emu_id,
                    name=name,
                    executable=exe,
                    arguments=args,
                    platform=plat,
                    bezel_delay=delay,
                    bezel_fade=fade,
                    loading_time=load_t,
                    exit_loading_time=exit_load_t,
                )
                self.refresh()
                self.emulators_changed.emit()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("dlg.emumgr.err_update_title", "Update error"),
                    tr("dlg.emumgr.err_update_msg", "Could not update the emulator:\n{error}", error=e),
                )

    def delete_selected(self):
        emu_id = self._get_selected_id()
        if not emu_id:
            QMessageBox.information(
                self,
                tr("dlg.common.select_title", "Select"),
                tr("dlg.emumgr.select_del_msg", "Select an emulator from the list to delete."),
            )
            return
        row = self.db.get_emulator(emu_id)
        if not row:
            return

        # Consultar cuántas listas o juegos usan este emulador
        lists_count = self.db.count_lists_using_emulator(emu_id)
        games_count = self.db.count_games_using_emulator(emu_id)

        warning = tr("dlg.emumgr.confirm_del_msg", "Are you sure you want to delete the emulator '{name}'?", name=row["name"])
        if lists_count > 0 or games_count > 0:
            warning += "\n\n" + tr(
                "dlg.emumgr.confirm_del_used",
                "Warning: It is linked to {lists} list(s) and {games} game(s).\nIts assignment will change to 'No emulator'.",
                lists=lists_count,
                games=games_count,
            )

        answer = QMessageBox.question(self, tr("dlg.common.confirm_del_title", "Confirm deletion"), warning, QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            try:
                self.db.delete_emulator(emu_id)
                self.refresh()
                self.emulators_changed.emit()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("dlg.emumgr.err_del_title", "Deletion error"),
                    tr("dlg.emumgr.err_del_msg", "Could not delete the emulator:\n{error}", error=e),
                )


class EmulatorManagerDialog(QDialog):
    """Diálogo completo para administrar (ver, crear, editar, eliminar) emuladores."""
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.emumgr.dlg_title", "Manage emulators"))
        self.resize(780, 480)

        layout = QVBoxLayout(self)
        self.widget = EmulatorManagerWidget(db, self, is_dialog=True)
        layout.addWidget(self.widget)

        close_btn = QPushButton(tr("dlg.btn.close", "Close"))
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
            self.progress_changed.emit(5, tr("dlg.scan.status_starting", "Starting folder scan..."))
            self.log_received.emit(tr("dlg.scan.log_start", "[START] Starting game folder scan."))
            for f in self.rom_folders:
                self.log_received.emit(tr("dlg.scan.log_folder", "[CONFIG] Target folder: {folder}", folder=f))
            exts_disp = self.exts or tr("dlg.scan.exts_all", "All")
            self.log_received.emit(tr("dlg.scan.log_exts", "[CONFIG] Extensions: {exts}", exts=exts_disp))
            yes_txt = tr("dlg.common.yes", "Yes")
            no_txt = tr("dlg.common.no", "No")
            self.log_received.emit(
                tr("dlg.scan.log_subfolders", "[CONFIG] Recursive subfolders: {val}", val=yes_txt if self.scan_subfolders else no_txt)
            )
            self.log_received.emit(
                tr("dlg.scan.log_exclude_zip", "[CONFIG] Exclude if contains .zip: {val}", val=yes_txt if self.exclude_folder_if_zip else no_txt)
            )
            if self.xml_path:
                self.log_received.emit(tr("dlg.scan.log_xml", "[CONFIG] Associated XML file: {path}", path=self.xml_path))
            if self.filter_rules and self.filter_rules != "[]":
                self.log_received.emit(
                    tr(
                        "dlg.scan.log_filters",
                        "[CONFIG] Active filter rules ({mode}): {rules}",
                        mode=self.filter_match_mode.upper(),
                        rules=self.filter_rules,
                    )
                )

            def scan_cb(msg):
                if self._cancelled:
                    raise InterruptedError(tr("dlg.scan.cancelled_err", "Operation cancelled by user."))
                self.log_received.emit(msg)

            paths = scan_rom_folder(
                self.rom_folders,
                self.exts,
                scan_subfolders=self.scan_subfolders,
                exclude_folder_if_zip=self.exclude_folder_if_zip,
                progress_callback=scan_cb,
            )

            if self._cancelled:
                raise InterruptedError(tr("dlg.scan.cancelled_err", "Operation cancelled by user."))

            total = len(paths)
            self.log_received.emit(tr("dlg.scan.log_found", "[SCAN] Total matching files found: {total}", total=total))
            self.progress_changed.emit(20, tr("dlg.scan.status_importing_total", "Processing and importing {total} game(s)...", total=total))

            if total == 0:
                self.progress_changed.emit(100, tr("dlg.scan.status_empty", "Finished: no files found."))
                self.log_received.emit(tr("dlg.scan.log_empty", "[NOTICE] No game files matching the criteria were found."))
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
                    raise InterruptedError(tr("dlg.scan.cancelled_err", "Operation cancelled by user."))
                pct = 20 + int((curr / max(tot, 1)) * 75)
                self.progress_changed.emit(pct, tr("dlg.scan.status_importing_item", "Importing [{curr}/{total}]: {title}", curr=curr, total=tot, title=title))
                self.log_received.emit(tr("dlg.scan.log_importing_item", "[IMPORT] [{curr}/{total}] {title}", curr=curr, total=tot, title=title))

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

            self.progress_changed.emit(100, tr("dlg.scan.status_done", "Import completed successfully!"))
            self.log_received.emit("==================================================")
            self.log_received.emit(tr("dlg.scan.log_summary_header", "[FINAL SUMMARY]"))
            self.log_received.emit(tr("dlg.scan.log_summary_found", "  • Total files found: {count}", count=stats['total_found']))
            self.log_received.emit(tr("dlg.scan.log_summary_added", "  • Games registered in library: {count}", count=stats['added']))
            if stats.get('removed', 0) > 0:
                self.log_received.emit(tr("dlg.scan.log_summary_removed", "  • Games removed (no longer existing): {count}", count=stats['removed']))
            if stats.get('skipped', 0) > 0:
                self.log_received.emit(tr("dlg.scan.log_summary_skipped", "  • Games skipped (unchanged): {count}", count=stats['skipped']))
            if stats.get('filtered_out', 0) > 0:
                self.log_received.emit(tr("dlg.scan.log_summary_filtered", "  • Filtered out by list rules: {count}", count=stats['filtered_out']))
            if stats.get('xml_matched', 0) > 0:
                self.log_received.emit(tr("dlg.scan.log_summary_xml", "  • Games linked with XML data: {count}", count=stats['xml_matched']))
            self.log_received.emit("==================================================")
            self.finished_scan.emit(stats)

        except InterruptedError:
            self.log_received.emit(tr("dlg.scan.log_cancelled", "[CANCELLED] The process was cancelled by the user."))
            self.error_occurred.emit(tr("dlg.scan.cancelled_err", "Operation cancelled by user."))
        except Exception as e:
            self.log_received.emit(tr("dlg.scan.log_error", "[CRITICAL ERROR] {error}", error=e))
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
        self.setWindowTitle(tr("dlg.scan_prog.title", "Processing list: {name}", name=list_name))
        self.resize(700, 520)
        self.setMinimumSize(560, 420)
        self.setModal(True)

        self.stats: dict | None = None
        self.error_msg: str | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Encabezado informativo
        header_title = QLabel(
            tr("dlg.scan_prog.header", "<b style='font-size: 15px; color: #f1f5f9;'>Processing library: {name}</b>", name=list_name)
        )
        self.status_lbl = QLabel(tr("dlg.scan_prog.init_status", "Starting game scan and import..."))
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
        debug_group = QGroupBox(tr("dlg.scan_prog.debug_group", "Live Debug Console"))
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
        self.cancel_btn = QPushButton(tr("dlg.btn.cancel", "Cancel"))
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.accept_btn = QPushButton(tr("dlg.btn.ok", "OK"))
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
        self.status_lbl.setText(tr("dlg.scan_prog.done_status", "Process finished! You can review the log above and click OK."))
        self.status_lbl.setStyleSheet("color: #4ade80; font-weight: bold;")
        self.accept_btn.setFocus()

    def _on_error(self, err_msg: str):
        self.error_msg = err_msg
        self.cancel_btn.setEnabled(False)
        self.accept_btn.setEnabled(True)
        self.status_lbl.setText(tr("dlg.scan_prog.err_status", "Notice / Error: {error}", error=err_msg))
        self.status_lbl.setStyleSheet("color: #f87171; font-weight: bold;")
        self.accept_btn.setFocus()

    def _on_cancel(self):
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText(tr("dlg.scan_prog.cancelling", "Cancelling operation..."))
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
        self.setWindowTitle(tr("dlg.scan_sum.title", "Game scan summary"))
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        title = QLabel(tr("dlg.scan_sum.header", "<h2>Scan completed for: {name}</h2>", name=list_name))
        layout.addWidget(title)

        folders_parsed = parse_rom_folders(folder)
        folders_label_title = (
            tr("dlg.scan_sum.folders_label", "Folders scanned:")
            if len(folders_parsed) > 1
            else tr("dlg.scan_sum.folder_label", "Folder scanned:")
        )
        folders_display = "<br>".join(f"• {f}" for f in folders_parsed) if len(folders_parsed) > 1 else (folders_parsed[0] if folders_parsed else folder)

        box = QGroupBox(tr("dlg.scan_sum.details_group", "Import details"))
        form = QFormLayout(box)
        lbl_folders = QLabel(folders_display)
        lbl_folders.setWordWrap(True)
        form.addRow(folders_label_title, lbl_folders)
        form.addRow(tr("dlg.scan_sum.allowed_exts", "Allowed extensions:"), QLabel(allowed_exts))
        form.addRow(tr("dlg.scan_sum.found_files", "Matching files found:"), QLabel(f"<b>{stats['total_found']}</b>"))
        form.addRow(tr("dlg.scan_sum.registered_games", "Games registered in list:"), QLabel(f"<b style='color: #4cd964;'>{stats['added']}</b>"))
        if stats.get("removed", 0) > 0:
            form.addRow(tr("dlg.scan_sum.removed_games", "Previous games removed:"), QLabel(f"<b style='color: #f87171;'>{stats['removed']}</b>"))
        if stats.get("skipped", 0) > 0:
            form.addRow(tr("dlg.scan_sum.skipped_files", "Files skipped:"), QLabel(f"<b>{stats['skipped']}</b>"))
        if stats.get("filtered_out", 0) > 0:
            form.addRow(tr("dlg.scan_sum.filtered_out", "Filtered out:"), QLabel(f"<b style='color: #f59e0b;'>{stats['filtered_out']}</b>"))
        if stats.get("xml_total_entries", 0) > 0 or stats.get("xml_matched", 0) > 0:
            xml_matched = stats.get("xml_matched", 0)
            xml_total = stats.get("xml_total_entries", 0)
            form.addRow(
                tr("dlg.scan_sum.xml_matched", "Matched with XML (name and metadata):"),
                QLabel(
                    tr(
                        "dlg.scan_sum.xml_matched_val",
                        "<b style='color: #a5b4fc;'>{matched}</b> <span style='color: #8a93a8;'>(of {total} in XML)</span>",
                        matched=xml_matched,
                        total=xml_total,
                    )
                )
            )
        layout.addWidget(box)

        btn = QPushButton(tr("dlg.btn.ok", "OK"))
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignRight)


class GameEditDialog(QDialog):
    """Diálogo para editar metadatos y configuración individual de un juego."""
    def __init__(self, db, game, parent=None):
        super().__init__(parent)
        self.db = db
        self.game = dict(game) if hasattr(game, "keys") else game
        game = self.game
        self.setWindowTitle(tr("dlg.game.title", "Edit game: {title}", title=game['title']))
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_edit = QLineEdit(game["title"])
        form.addRow(tr("dlg.game.full_title_label", "Full title *"), self.title_edit)

        rom_code = game.get("rom_name") or (Path(game["rom_path"]).stem if game.get("rom_path") else "")
        self.rom_name_edit = QLineEdit(rom_code)
        self.rom_name_edit.setPlaceholderText(tr("dlg.game.rom_name_placeholder", "Short ROM identifier (e.g., sf2)"))
        form.addRow(tr("dlg.game.rom_name_label", "ROM name"), self.rom_name_edit)

        self.path_edit = QLineEdit(game["rom_path"])
        browse_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
        browse_btn.clicked.connect(self.pick_file)
        path_box = QHBoxLayout()
        path_box.addWidget(self.path_edit, 1)
        path_box.addWidget(browse_btn)
        path_holder = QWidget()
        path_holder.setLayout(path_box)
        form.addRow(tr("dlg.game.file_path_label", "File path"), path_holder)

        # Propiedades del juego (provenientes del XML o editables manualmente)
        meta_group = QGroupBox(tr("dlg.game.meta_group", "Game Properties (XML / Metadata)"))
        meta_form = QFormLayout(meta_group)

        row_ym = QHBoxLayout()
        self.year_edit = QLineEdit(game.get("year") or "")
        self.year_edit.setPlaceholderText(tr("dlg.game.year_placeholder", "e.g., 1991"))
        self.year_edit.setFixedWidth(100)
        self.manufacturer_edit = QLineEdit(game.get("manufacturer") or "")
        self.manufacturer_edit.setPlaceholderText(tr("dlg.game.manufacturer_placeholder", "e.g., Capcom, Konami, Sega..."))
        row_ym.addWidget(self.year_edit)
        row_ym.addWidget(QLabel(tr("dlg.game.manufacturer_label", "Manufacturer:")))
        row_ym.addWidget(self.manufacturer_edit, 1)
        ym_widget = QWidget()
        ym_widget.setLayout(row_ym)
        meta_form.addRow(tr("dlg.game.year_label", "Year:"), ym_widget)

        row_gp = QHBoxLayout()
        self.genre_edit = QLineEdit(game.get("genre") or "")
        self.genre_edit.setPlaceholderText(tr("dlg.game.genre_placeholder", "e.g., Fighter, Shooter, Platform..."))
        self.players_edit = QLineEdit(game.get("players") or "")
        self.players_edit.setPlaceholderText(tr("dlg.game.players_placeholder", "e.g., 1-2"))
        self.players_edit.setFixedWidth(90)
        row_gp.addWidget(self.genre_edit, 1)
        row_gp.addWidget(QLabel(tr("dlg.game.players_label", "Players:")))
        row_gp.addWidget(self.players_edit)
        gp_widget = QWidget()
        gp_widget.setLayout(row_gp)
        meta_form.addRow(tr("dlg.game.genre_label", "Genre:"), gp_widget)

        row_cr = QHBoxLayout()
        self.cloneof_edit = QLineEdit(game.get("cloneof") or "")
        self.cloneof_edit.setPlaceholderText(tr("dlg.game.cloneof_placeholder", "Parent ROM (if clone)"))
        self.rating_edit = QLineEdit(game.get("rating") or "")
        self.rating_edit.setPlaceholderText(tr("dlg.game.rating_placeholder", "Classification / Rating"))
        self.crc_edit = QLineEdit(game.get("crc") or "")
        self.crc_edit.setPlaceholderText(tr("dlg.game.crc_placeholder", "CRC"))
        self.crc_edit.setFixedWidth(95)
        row_cr.addWidget(self.cloneof_edit, 1)
        row_cr.addWidget(QLabel(tr("dlg.game.rating_label", "Rating:")))
        row_cr.addWidget(self.rating_edit, 1)
        row_cr.addWidget(QLabel(tr("dlg.game.crc_label", "CRC:")))
        row_cr.addWidget(self.crc_edit)
        cr_widget = QWidget()
        cr_widget.setLayout(row_cr)
        meta_form.addRow(tr("dlg.game.cloneof_label", "Clone of:"), cr_widget)

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
        self.sourcefile_edit.setPlaceholderText(tr("dlg.game.sourcefile_placeholder", "MAME driver source file (e.g., capcom/cps1.cpp, neogeo.cpp)"))
        meta_form.addRow(tr("dlg.game.sourcefile_label", "Sourcefile:"), self.sourcefile_edit)

        # Orientación de pantalla (útil para Bezel HUD vertical/horizontal)
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem(tr("dlg.game.orient_auto", "Automatic (from XML / Metadata)"), "")
        self.orientation_combo.addItem(tr("dlg.game.orient_h", "Horizontal (Standard)"), "horizontal")
        self.orientation_combo.addItem(tr("dlg.game.orient_v", "Vertical (TATE)"), "vertical")
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
        meta_form.addRow(tr("dlg.game.orient_label", "Orientation:"), self.orientation_combo)

        self.override_combo = QComboBox()
        self.override_combo.addItem(tr("dlg.game.inherit_emu", "Inherit list emulator (default)"), None)
        emulators = self.db.get_emulators()
        for emu in emulators:
            self.override_combo.addItem(f"{emu['name']} ({emu['executable']})", emu["id"])
        idx = self.override_combo.findData(game["emulator_override_id"])
        if idx >= 0:
            self.override_combo.setCurrentIndex(idx)
        form.addRow(tr("dlg.game.override_emu_label", "Individual emulator"), self.override_combo)

        self.bezel_hud_combo = QComboBox()
        self.bezel_hud_combo.addItem(tr("dlg.game.bezel_inherit", "Inherit from list (default)"), "")
        self.bezel_hud_combo.addItem(tr("dlg.game.bezel_enable", "Enable Bezel HUD (Force for this game)"), "enabled")
        self.bezel_hud_combo.addItem(tr("dlg.game.bezel_disable", "Disable Bezel HUD (Do not show)"), "disabled")
        idx_bh = self.bezel_hud_combo.findData(game.get("bezel_hud_mode") or "")
        if idx_bh >= 0:
            self.bezel_hud_combo.setCurrentIndex(idx_bh)
        form.addRow(tr("dlg.game.bezel_hud_label", "Bezel HUD (Frame)"), self.bezel_hud_combo)

        self.args_edit = QLineEdit(game["launch_arguments"] or "")
        self.args_edit.setPlaceholderText(tr("dlg.game.args_placeholder", "Leave empty to use the emulator's arguments"))
        form.addRow(tr("dlg.game.args_label", "Custom arguments"), self.args_edit)

        self.notes_edit = QTextEdit(game["notes"] or "")
        self.notes_edit.setMaximumHeight(70)
        form.addRow(tr("dlg.game.notes_label", "Notes / Synopsis"), self.notes_edit)

        self.favorite_cb = QCheckBox(tr("dlg.game.favorite_cb", "⭐ Mark as favorite game"))
        self.favorite_cb.setChecked(bool(int(game.get("is_favorite") or 0)))
        form.addRow(tr("dlg.game.favorite_label", "Favorite"), self.favorite_cb)

        self.tags_edit = QLineEdit(game.get("tags") or "")
        self.tags_edit.setPlaceholderText(tr("dlg.game.tags_placeholder", "Comma-separated tags (e.g., arcade, coop, local)"))
        form.addRow(tr("dlg.game.tags_label", "Tags"), self.tags_edit)

        manual_row = QHBoxLayout()
        self.manual_file_edit = QLineEdit(game.get("manual_file_path") or "")
        self.manual_file_edit.setPlaceholderText(tr("dlg.game.manual_placeholder", "Explicit path to individual PDF manual (optional)"))
        btn_pick_manual = QPushButton(tr("dlg.game.manual_pick_btn", "📄 PDF…"))
        btn_pick_manual.clicked.connect(self._pick_manual_pdf)
        btn_view_manual = QPushButton(tr("dlg.game.manual_view_btn", "📖 View"))
        btn_view_manual.setToolTip(tr("dlg.game.manual_view_tooltip", "Open the PDF manual in the built-in viewer"))
        btn_view_manual.clicked.connect(self._open_manual_preview)
        manual_row.addWidget(self.manual_file_edit, 1)
        manual_row.addWidget(btn_pick_manual)
        manual_row.addWidget(btn_view_manual)
        form.addRow(tr("dlg.game.manual_label", "PDF Manual (individual)"), manual_row)

        layout.addLayout(form)
        layout.addWidget(meta_group)

        from playnexus.db import format_play_time
        stats_group = QGroupBox(tr("dlg.game.stats_group", "Activity & Telemetry"))
        stats_layout = QHBoxLayout(stats_group)
        play_count = int(game.get("play_count") or 0)
        play_time_txt = format_play_time(game.get("play_time_seconds") or 0)
        last_played_txt = str(game.get("last_played") or "").strip() or tr("dlg.game.never_played", "Never")
        self.stats_summary_label = QLabel(
            tr(
                "dlg.game.stats_summary",
                "<b>Plays:</b> {plays}   ·   <b>Time:</b> {time}   ·   <b>Last session:</b> {last}",
                plays=play_count,
                time=play_time_txt,
                last=last_played_txt,
            )
        )
        self.stats_summary_label.setStyleSheet("color: #cbd5e1;")
        stats_layout.addWidget(self.stats_summary_label, 1)
        reset_stats_btn = QPushButton(tr("dlg.game.reset_stats_btn", "↺ Reset stats"))
        reset_stats_btn.setToolTip(tr("dlg.game.reset_stats_tooltip", "Reset play count and playtime for this game to zero"))
        reset_stats_btn.clicked.connect(self._reset_telemetry)
        stats_layout.addWidget(reset_stats_btn)
        layout.addWidget(stats_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        _localize_dialog_buttons(buttons)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reset_telemetry(self):
        from playnexus.db import format_play_time
        answer = QMessageBox.question(
            self,
            tr("dlg.game.reset_stats_title", "Reset statistics"),
            tr("dlg.game.reset_stats_msg", "Do you want to reset plays and playtime to 0 for '{title}'?", title=self.game['title']),
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer == QMessageBox.Yes and self.db and self.game.get("id"):
            if self.db.reset_game_telemetry(self.game["id"]):
                self.game["play_count"] = 0
                self.game["play_time_seconds"] = 0
                self.game["last_played"] = ""
                self.stats_summary_label.setText(
                    tr(
                        "dlg.game.stats_summary",
                        "<b>Plays:</b> {plays}   ·   <b>Time:</b> {time}   ·   <b>Last session:</b> {last}",
                        plays=0,
                        time=format_play_time(0),
                        last=tr("dlg.game.never_played", "Never"),
                    )
                )

    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dlg.game.pick_file_title", "Select game file"),
            "",
            tr("dlg.common.all_files_filter", "All files (*.*)"),
        )
        if path:
            self.path_edit.setText(path)

    def save(self):
        import json
        title = self.title_edit.text().strip()
        path = self.path_edit.text().strip()
        if not title or not path:
            QMessageBox.warning(
                self,
                tr("dlg.game.err_required_title", "Required fields"),
                tr("dlg.game.err_required_msg", "Title and file path are required."),
            )
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
                is_favorite=1 if self.favorite_cb.isChecked() else 0,
                tags=self.tags_edit.text().strip(),
                manual_file_path=self.manual_file_edit.text().strip(),
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("dlg.game.err_save_title", "Save error"),
                tr("dlg.game.err_save_msg", "Could not save game information:\n{error}", error=e),
            )

    def _pick_manual_pdf(self):
        cur = self.manual_file_edit.text().strip()
        start_dir = str(Path(cur).parent) if cur and Path(cur).parent.is_dir() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dlg.game.pick_manual_title", "Select individual PDF Manual"),
            start_dir,
            tr("dlg.game.pick_manual_filter", "PDF Manuals (*.pdf);;All files (*.*)"),
        )
        if path:
            self.manual_file_edit.setText(path)

    def _open_manual_preview(self):
        from playnexus.services.media import resolve_game_manual_pdf
        from playnexus.ui.manual_viewer import ManualViewerDialog

        explicit = self.manual_file_edit.text().strip()
        cand_row = dict(self.game)
        cand_row["manual_file_path"] = explicit
        list_row = self.db.get_list(cand_row.get("list_id")) if cand_row.get("list_id") else None
        pdf = resolve_game_manual_pdf(cand_row, list_row=list_row)
        if not pdf:
            QMessageBox.information(
                self,
                tr("dlg.game.no_manual_title", "No PDF manual"),
                tr("dlg.game.no_manual_msg", "No .pdf file has been assigned to this game yet."),
            )
            return
        dlg = ManualViewerDialog(
            pdf,
            game_title=self.title_edit.text().strip() or cand_row.get("title", ""),
            db=self.db,
            parent=self,
        )
        dlg.exec()


def _get_resolutions_list() -> list[tuple[str, str]]:
    return [
        (tr("dlg.video.res_native", "Native / Automatic (Recommended)"), "native"),
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
        (tr("dlg.video.res_custom", "Custom..."), "custom"),
    ]


def _get_screen_modes() -> list[tuple[str, str]]:
    return [
        (tr("dlg.video.mode_fullscreen", "Fullscreen"), "fullscreen"),
        (tr("dlg.video.mode_borderless", "Borderless Window"), "borderless"),
        (tr("dlg.video.mode_windowed", "Windowed Mode"), "windowed"),
    ]


RESOLUTIONS_LIST = _get_resolutions_list()
SCREEN_MODES = _get_screen_modes()


class VideoSettingsDialog(QDialog):
    """
    Diálogo para configurar la resolución, modo de pantalla completa y monitor
    del Frontend / Reproductor de PlayNexus.
    """
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(tr("dlg.video.title", "Video & Display Settings"))
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        header = QLabel(tr("dlg.video.header", "<b>Frontend Video Settings</b>"))
        header.setStyleSheet("font-size: 11pt; color: #f1f3f9;")
        layout.addWidget(header)

        desc = QLabel(
            tr(
                "dlg.video.desc",
                "Configure the resolution, fullscreen mode, and display "
                "used when launching the game Frontend (PlayNexus_Launcher.bat).",
            )
        )
        desc.setStyleSheet("color: #9aa5b8; font-size: 9pt;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(12)

        # 1. Modo de Pantalla
        self.mode_combo = QComboBox()
        for label, val in _get_screen_modes():
            self.mode_combo.addItem(label, val)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow(tr("dlg.video.mode_label", "Display mode:"), self.mode_combo)

        # 2. Resolución
        self.res_combo = QComboBox()
        for label, val in _get_resolutions_list():
            self.res_combo.addItem(label, val)
        self.res_combo.currentIndexChanged.connect(self._on_res_changed)
        form.addRow(tr("dlg.video.res_label", "Resolution:"), self.res_combo)

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
        custom_layout.addWidget(QLabel(tr("dlg.video.width_label", "Width:")))
        custom_layout.addWidget(self.width_spin)
        custom_layout.addWidget(QLabel(tr("dlg.video.height_label", "Height:")))
        custom_layout.addWidget(self.height_spin)
        form.addRow(tr("dlg.video.custom_size_label", "Custom size:"), self.custom_row)
        self.custom_row.setVisible(False)

        # 4. Monitor / Pantalla de destino
        self.screen_combo = QComboBox()
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        for idx, scr in enumerate(screens):
            geo = scr.geometry()
            tag = tr("dlg.video.monitor_primary", " [Primary]") if scr == primary else ""
            self.screen_combo.addItem(
                tr(
                    "dlg.video.monitor_item",
                    "Monitor {num}: {w}x{h} ({name}){tag}",
                    num=idx + 1,
                    w=geo.width(),
                    h=geo.height(),
                    name=scr.name(),
                    tag=tag,
                ),
                idx,
            )
        self.screen_combo.currentIndexChanged.connect(self._update_info)
        form.addRow(tr("dlg.video.monitor_label", "Target display:"), self.screen_combo)

        # 5. Escala de interfaz (UI Scale)
        self.scale_combo = QComboBox()
        self.scale_combo.addItem(tr("dlg.video.scale_100", "100% (Normal)"), "100% (Normal)")
        self.scale_combo.addItem("125%", "125%")
        self.scale_combo.addItem("150%", "150%")
        self.scale_combo.addItem("175%", "175%")
        self.scale_combo.addItem(tr("dlg.video.scale_200", "200% (4K)"), "200% (4K)")
        form.addRow(tr("dlg.video.scale_label", "Interface scale:"), self.scale_combo)

        layout.addLayout(form)

        # Nota informativa
        note_box = QGroupBox(tr("dlg.video.summary_group", "Display summary"))
        note_layout = QVBoxLayout(note_box)
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #a0aec0; font-size: 9pt;")
        self.info_label.setWordWrap(True)
        note_layout.addWidget(self.info_label)
        layout.addWidget(note_box)

        # Botones
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        _localize_dialog_buttons(buttons)
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
        geo_str = f"{geo.width()}x{geo.height()}" if geo else tr("dlg.video.screen_fallback", "display")

        if mode == "fullscreen":
            msg = tr(
                "dlg.video.info_fullscreen",
                "The Frontend will start in <b>Fullscreen</b> filling the entire display ({geo}). Ideal for arcade cabinets and TVs.",
                geo=geo_str,
            )
        elif mode == "borderless":
            msg = tr(
                "dlg.video.info_borderless",
                "The Frontend will start in a <b>Borderless Window</b> fitted to the display resolution ({geo}).",
                geo=geo_str,
            )
        else:
            if res == "native":
                msg = tr(
                    "dlg.video.info_windowed_native",
                    "<b>Windowed</b> mode automatically fitted to the display dimensions ({geo}).",
                    geo=geo_str,
                )
            elif res == "custom":
                msg = tr(
                    "dlg.video.info_windowed_custom",
                    "<b>Windowed</b> mode with custom resolution of <b>{w} x {h}</b> pixels.",
                    w=self.width_spin.value(),
                    h=self.height_spin.value(),
                )
            else:
                msg = tr(
                    "dlg.video.info_windowed_fixed",
                    "<b>Windowed</b> mode with fixed resolution of <b>{res}</b> pixels.",
                    res=res,
                )
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
        idx_s = self.scale_combo.findData(scale)
        if idx_s < 0:
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
        self.db.set_setting("video_ui_scale", self.scale_combo.currentData() or self.scale_combo.currentText())
        self.accept()


