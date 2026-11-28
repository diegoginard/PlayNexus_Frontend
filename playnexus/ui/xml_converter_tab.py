"""
Pestaña 'Conversor XML' para el Configurador de PlayNexus.

Constructor multi-fuente a medida de catálogos rápidos '.pncat' (PlayNexus Fast Catalog v1):
- Permite sumar cualquier cantidad de fuentes con el botón '＋' (.xml, .dat, .ini) y ordenar su prioridad.
- Permite elegir explícitamente qué columnas se guardarán en el archivo '.pncat' (y se mostrarán en la vista previa).
- Sin botones ni rutas predefinidas por defecto: todas las ubicaciones las elige el usuario.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from playnexus.db import Database
from playnexus.i18n import tr
from playnexus.services.media import is_game_vertical
from playnexus.services.xml_converter import (
    ALL_KNOWN_COLUMNS,
    COLUMN_GROUPS_SPEC,
    MANDATORY_COLUMNS,
    PNCAT_EXT,
    ConvertOptions,
    ConvertSummary,
    SourceSpec,
    build_pncat_from_sources,
    infer_ini_role,
    is_fast_catalog_file,
    read_fast_catalog_table,
    sanitize_custom_column_name,
    suggest_custom_column_from_ini,
)
from playnexus.ui.table_utils import (
    SortableTableWidgetItem,
    configure_details_table,
    paused_table_sorting,
)


def _format_bytes(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB")
    val = float(num_bytes)
    for unit in units:
        if val < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(val)} B"
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} GB"


def _reveal_file_in_explorer(path: str) -> None:
    if not path:
        return
    norm = os.path.normpath(path)
    try:
        if sys.platform.startswith("win"):
            if os.path.isfile(norm):
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


# Definición de columnas mostrables dinámicamente en la tabla de vista previa según el esquema del .pncat
_PREVIEW_COLUMN_DEFS: tuple[tuple[str, str, str, int], ...] = (
    ("rom_name", "xmlconv.col.rom", "ROM", 100),
    ("title", "xmlconv.col.title", "Full Title", 240),
    ("year", "xmlconv.col.year", "Year", 58),
    ("manufacturer", "xmlconv.col.manufacturer", "Manufacturer", 135),
    ("genre", "xmlconv.col.genre", "Genre", 120),
    ("players", "xmlconv.col.players", "Players", 62),
    ("cloneof", "xmlconv.col.cloneof", "Clone Of", 82),
    ("bios", "xmlconv.col.bios", "BIOS", 82),
    ("romof", "xmlconv.col.romof", "ROM Of", 82),
    ("sourcefile", "xmlconv.col.sourcefile", "Driver / Source", 115),
    ("display_rotate", "xmlconv.col.orientation", "Screen", 90),
    ("resolution_ui", "xmlconv.col.resolution", "Resolution", 90),
    ("controls_ui", "xmlconv.col.controls", "Controls", 95),
    ("status", "xmlconv.col.status", "Status", 78),
    ("crc", "xmlconv.col.crc", "CRC32", 85),
    ("rating", "xmlconv.col.rating", "Rating", 70),
    ("notes", "xmlconv.col.notes", "Notes", 160),
)


class XmlConvertWorker(QThread):
    """Hilo de conversión multi-fuente (.xml / .dat / .ini) -> .pncat sin bloquear la interfaz."""

    progress = Signal(int, int, int, int, float)  # pct, seen, written, bytes_read, elapsed
    finished_ok = Signal(object)  # ConvertSummary
    failed = Signal(str)

    def __init__(
        self,
        sources: list[SourceSpec],
        output_path: str,
        options: ConvertOptions,
        parent=None,
    ):
        super().__init__(parent)
        self.sources = list(sources)
        self.output_path = output_path
        self.options = options
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        t0 = time.perf_counter()
        try:
            def _on_prog(pct: int, seen: int, written: int, bytes_read: int) -> None:
                self.progress.emit(pct, seen, written, bytes_read, time.perf_counter() - t0)

            summary = build_pncat_from_sources(
                self.sources,
                self.output_path,
                options=self.options,
                progress_callback=_on_prog,
                cancel_check=lambda: self._cancelled,
            )
            self.finished_ok.emit(summary)
        except Exception as exc:
            self.failed.emit(str(exc))


class XmlConverterWidget(QWidget):
    """Pestaña principal del Conversor Multi-Fuente de Catálogos a formato rápido .pncat."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._worker: XmlConvertWorker | None = None
        self._loaded_catalog_path: str = ""
        self._catalog_entries: list[dict] = []
        self._catalog_columns: list[str] = []
        self._active_preview_cols: list[str] = ["rom_name", "title", "year", "manufacturer", "genre", "bios", "sourcefile"]
        self._load_ms: float = 0.0
        self.source_rows: list[dict] = []
        self.column_checkboxes: dict[str, QCheckBox] = {}
        self.custom_column_checkboxes: dict[str, QCheckBox] = {}

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._populate_preview_table)

        self._build_ui()
        self._add_source_row()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        # Cabecera informativa
        header_frame = QFrame()
        header_frame.setStyleSheet(
            "QFrame { background-color: #1b1f2d; border: 1px solid #2d354b; border-radius: 8px; }"
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(12)

        header_text_col = QVBoxLayout()
        header_text_col.setSpacing(3)
        title_lbl = QLabel(
            tr(
                "xmlconv.header.title",
                "⚡  XML / DAT / INI Fast Catalog Builder (.pncat)",
            )
        )
        title_lbl.setStyleSheet("font-size: 13pt; font-weight: 700; color: #e6e9f0; border: none;")
        sub_lbl = QLabel(
            tr(
                "xmlconv.header.subtitle",
                "Combine one or multiple XML, DAT, and INI sources (such as MAME XML + Category.ini + nplayers.ini) "
                "and choose the exact columns to generate an ultra-fast 100% portable plain-text catalog (.pncat).",
            )
        )
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet("color: #9aa3b8; font-size: 9pt; border: none;")
        header_text_col.addWidget(title_lbl)
        header_text_col.addWidget(sub_lbl)
        header_layout.addLayout(header_text_col, 1)

        open_existing_btn = QPushButton(tr("xmlconv.btn.open_pncat", "📂  Open existing .pncat…"))
        open_existing_btn.setToolTip(
            tr("xmlconv.btn.open_pncat_tip", "Load an already-converted .pncat file to inspect its entries")
        )
        open_existing_btn.clicked.connect(self._pick_existing_pncat)
        header_layout.addWidget(open_existing_btn)

        outer.addWidget(header_frame)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ---------------- PANEL IZQUIERDO ----------------
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_container = QWidget()
        left_vbox = QVBoxLayout(left_container)
        left_vbox.setContentsMargins(0, 0, 6, 0)
        left_vbox.setSpacing(10)

        # 1. Fuentes dinámicas (+) y Destino (.pncat)
        io_group = QGroupBox(tr("xmlconv.io.group", "1. Input Sources & Output File"))
        io_vbox = QVBoxLayout(io_group)
        io_vbox.setSpacing(8)

        src_hdr = QHBoxLayout()
        src_hdr_lbl = QLabel(
            tr(
                "xmlconv.io.sources_header",
                "<b>Data Sources (.xml / .dat / .ini):</b>  <span style='color:#8b95ab; font-size:8.5pt;'>(top = highest priority)</span>",
            )
        )
        add_src_btn = QPushButton(tr("xmlconv.io.add_source_btn", "＋  Add source"))
        add_src_btn.setToolTip(
            tr("xmlconv.io.add_source_tip", "Add another .xml, .dat, or .ini file to combine into the catalog")
        )
        add_src_btn.clicked.connect(lambda: self._add_source_row())
        src_hdr.addWidget(src_hdr_lbl, 1)
        src_hdr.addWidget(add_src_btn)
        io_vbox.addLayout(src_hdr)

        self.sources_container = QWidget()
        self.sources_vbox = QVBoxLayout(self.sources_container)
        self.sources_vbox.setContentsMargins(0, 0, 0, 0)
        self.sources_vbox.setSpacing(6)
        io_vbox.addWidget(self.sources_container)

        self.src_info_lbl = QLabel(tr("xmlconv.io.no_src", "No source files selected."))
        self.src_info_lbl.setStyleSheet("color: #8b95ab; font-size: 8.5pt;")
        io_vbox.addWidget(self.src_info_lbl)

        dst_form = QFormLayout()
        dst_form.setContentsMargins(0, 4, 0, 0)
        dst_row = QHBoxLayout()
        dst_row.setSpacing(6)
        self.dst_edit = QLineEdit()
        self.dst_edit.setPlaceholderText(
            tr("xmlconv.io.dst_placeholder", "Choose where to save the output .pncat file...")
        )
        dst_btn = QPushButton(tr("xmlconv.io.save_as", "Save as…"))
        dst_btn.clicked.connect(self._pick_output_pncat)
        dst_row.addWidget(self.dst_edit, 1)
        dst_row.addWidget(dst_btn)
        dst_holder = QWidget()
        dst_holder.setLayout(dst_row)
        dst_form.addRow(tr("xmlconv.io.dst_label", "Output (.pncat):"), dst_holder)
        io_vbox.addLayout(dst_form)

        left_vbox.addWidget(io_group)

        # 2. Selección explícita de Columnas y Pre-filtros
        cols_group = QGroupBox(tr("xmlconv.cols.group", "2. Columns to Include & Pre-Filters"))
        cols_vbox = QVBoxLayout(cols_group)
        cols_vbox.setSpacing(8)

        cols_hdr = QHBoxLayout()
        cols_hdr.setSpacing(6)
        cols_caption = QLabel(tr("xmlconv.cols.caption", "<b>Columns in .pncat:</b>"))
        btn_all_cols = QPushButton(tr("xmlconv.cols.btn_all", "Check all"))
        btn_all_cols.clicked.connect(lambda: self._set_column_selection("all"))
        btn_ess_cols = QPushButton(tr("xmlconv.cols.btn_recommended", "Recommended"))
        btn_ess_cols.clicked.connect(lambda: self._set_column_selection("recommended"))
        btn_min_cols = QPushButton(tr("xmlconv.cols.btn_minimal", "Minimal"))
        btn_min_cols.clicked.connect(lambda: self._set_column_selection("minimal"))
        cols_hdr.addWidget(cols_caption, 1)
        cols_hdr.addWidget(btn_all_cols)
        cols_hdr.addWidget(btn_ess_cols)
        cols_hdr.addWidget(btn_min_cols)
        cols_vbox.addLayout(cols_hdr)

        cols_grid = QGridLayout()
        cols_grid.setHorizontalSpacing(12)
        cols_grid.setVerticalSpacing(5)

        fixed_rom_cb = QCheckBox(tr("xmlconv.colgrp.rom_fixed", "ROM & Keys (required)"))
        fixed_rom_cb.setChecked(True)
        fixed_rom_cb.setEnabled(False)
        cols_grid.addWidget(fixed_rom_cb, 0, 0)

        for idx, (gid, i18n_key, fallback_en, _pcols, def_checked) in enumerate(COLUMN_GROUPS_SPEC, start=1):
            cb = QCheckBox(tr(i18n_key, fallback_en))
            cb.setChecked(def_checked)
            self.column_checkboxes[gid] = cb
            r, c = divmod(idx, 2)
            cols_grid.addWidget(cb, r, c)

        cols_vbox.addLayout(cols_grid)

        self.custom_cols_container = QWidget()
        self.custom_cols_grid = QGridLayout(self.custom_cols_container)
        self.custom_cols_grid.setContentsMargins(0, 2, 0, 0)
        self.custom_cols_grid.setHorizontalSpacing(12)
        self.custom_cols_grid.setVerticalSpacing(5)
        self.custom_cols_container.setVisible(False)
        cols_vbox.addWidget(self.custom_cols_container)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2b3246;")
        cols_vbox.addWidget(sep)

        filt_caption = QLabel(
            tr(
                "xmlconv.opts.prefilter_hint",
                "Optional pre-filters during conversion (BIOS sets & references are always preserved):",
            )
        )
        filt_caption.setWordWrap(True)
        filt_caption.setStyleSheet("color: #9aa3b8; font-size: 8.5pt;")
        cols_vbox.addWidget(filt_caption)

        self.cb_excl_devices = QCheckBox(tr("xmlconv.opts.excl_devices", "Exclude internal devices (isdevice=\"yes\")"))
        self.cb_excl_mech = QCheckBox(
            tr("xmlconv.opts.excl_mech", "Exclude mechanical / pinball / slot machines (ismechanical=\"yes\")")
        )
        self.cb_excl_nonrun = QCheckBox(
            tr("xmlconv.opts.excl_nonrun", "Exclude non-runnable entries (runnable=\"no\")")
        )
        self.cb_excl_clones = QCheckBox(
            tr("xmlconv.opts.excl_clones", "Exclude clones (keep parent / main sets only)")
        )
        for cb in (self.cb_excl_devices, self.cb_excl_mech, self.cb_excl_nonrun, self.cb_excl_clones):
            cols_vbox.addWidget(cb)

        left_vbox.addWidget(cols_group)

        # 3. Ejecución y Progreso
        run_group = QGroupBox(tr("xmlconv.run.group", "3. Convert Catalog"))
        run_vbox = QVBoxLayout(run_group)
        run_vbox.setSpacing(8)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.convert_btn = QPushButton(tr("xmlconv.run.start_btn", "⚡  Convert to .pncat"))
        self.convert_btn.setObjectName("primary")
        self.convert_btn.setMinimumHeight(38)
        self.convert_btn.clicked.connect(self.start_conversion)

        self.cancel_btn = QPushButton(tr("common.cancel", "Cancel"))
        self.cancel_btn.setMinimumHeight(38)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_conversion)

        self.reveal_btn = QPushButton(tr("xmlconv.run.reveal_btn", "📂  Show File"))
        self.reveal_btn.setMinimumHeight(38)
        self.reveal_btn.setEnabled(False)
        self.reveal_btn.clicked.connect(self._reveal_current_output)

        btn_row.addWidget(self.convert_btn, 1)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.reveal_btn)
        run_vbox.addLayout(btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        run_vbox.addWidget(self.progress_bar)

        self.status_lbl = QLabel(tr("xmlconv.run.ready", "Ready to convert."))
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("color: #a78bfa; font-weight: 600; font-size: 9pt;")
        run_vbox.addWidget(self.status_lbl)

        left_vbox.addWidget(run_group)
        left_vbox.addStretch(1)

        left_scroll.setWidget(left_container)
        left_scroll.setMinimumWidth(460)
        splitter.addWidget(left_scroll)

        # ---------------- PANEL DERECHO (EXPLORADOR DINÁMICO DE VISTA PREVIA) ----------------
        right_panel = QGroupBox(tr("xmlconv.preview.group", "Fast Catalog Inspector & Instant Search"))
        right_vbox = QVBoxLayout(right_panel)
        right_vbox.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            tr(
                "xmlconv.preview.search_placeholder",
                "🔍 Search across any column in the loaded .pncat...",
            )
        )
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(lambda _: self._search_timer.start())
        search_row.addWidget(self.search_edit, 1)

        search_row.addWidget(QLabel(tr("xmlconv.preview.limit_label", "Max rows:")))
        self.limit_combo = QComboBox()
        self.limit_combo.addItem("500", 500)
        self.limit_combo.addItem("2 000", 2000)
        self.limit_combo.addItem("5 000", 5000)
        self.limit_combo.addItem(tr("xmlconv.preview.limit_all", "All"), 0)
        self.limit_combo.currentIndexChanged.connect(lambda _: self._populate_preview_table())
        search_row.addWidget(self.limit_combo)

        right_vbox.addLayout(search_row)

        self.preview_summary_lbl = QLabel(
            tr("xmlconv.preview.empty", "Convert your sources or open an existing .pncat file to preview its entries.")
        )
        self.preview_summary_lbl.setStyleSheet("color: #7dd3fc; font-size: 8.8pt; font-weight: 500;")
        right_vbox.addWidget(self.preview_summary_lbl)

        self.preview_table = QTableWidget(0, 0)
        self._rebuild_preview_columns(self._active_preview_cols)
        self.preview_table.itemSelectionChanged.connect(self._on_preview_selection_changed)
        right_vbox.addWidget(self.preview_table, 1)

        self.entry_detail_lbl = QLabel("")
        self.entry_detail_lbl.setWordWrap(True)
        self.entry_detail_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.entry_detail_lbl.setStyleSheet(
            "background-color: #181c27; border: 1px solid #2a3145; border-radius: 6px; "
            "padding: 7px 10px; color: #c7d0e4; font-size: 8.5pt;"
        )
        self.entry_detail_lbl.setVisible(False)
        right_vbox.addWidget(self.entry_detail_lbl)

        splitter.addWidget(right_panel)
        splitter.setSizes([490, 740])
        outer.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # FILAS DINÁMICAS DE FUENTES (+)
    # ------------------------------------------------------------------
    def _add_source_row(self, path: str = "", role: str = "", custom_col: str = "") -> dict:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)

        path_edit = QLineEdit(path)
        path_edit.setPlaceholderText(
            tr("xmlconv.io.row_placeholder", "Select .xml, .dat or .ini source file...")
        )

        role_combo = QComboBox()
        role_combo.setMinimumWidth(148)
        role_combo.addItem(tr("xmlconv.role.catalog", "📄 XML / DAT Catalog"), "catalog")
        role_combo.addItem(tr("xmlconv.role.genre", "🏷 INI ➔ Genre"), "genre")
        role_combo.addItem(tr("xmlconv.role.players", "👥 INI ➔ Players"), "players")
        role_combo.addItem(tr("xmlconv.role.manufacturer", "🏢 INI ➔ Manufacturer"), "manufacturer")
        role_combo.addItem(tr("xmlconv.role.year", "📅 INI ➔ Year"), "year")
        role_combo.addItem(tr("xmlconv.role.notes", "📝 INI ➔ Notes"), "notes")
        role_combo.addItem(tr("xmlconv.role.custom", "✨ INI ➔ New Column…"), "custom")

        custom_col_edit = QLineEdit(custom_col)
        custom_col_edit.setFixedWidth(122)
        custom_col_edit.setPlaceholderText(tr("xmlconv.io.custom_col_placeholder", "col_name (e.g. series)"))
        custom_col_edit.setVisible(False)

        browse_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
        up_btn = QPushButton("▲")
        up_btn.setFixedWidth(26)
        up_btn.setToolTip(tr("dlg.list.move_up", "▲ Move Up"))
        down_btn = QPushButton("▼")
        down_btn.setFixedWidth(26)
        down_btn.setToolTip(tr("dlg.list.move_down", "▼ Move Down"))
        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(26)
        del_btn.setToolTip(tr("xmlconv.io.remove_source_tip", "Remove this source"))
        del_btn.setStyleSheet(
            "QPushButton { color: #f87171; font-weight: bold; padding: 2px; }"
            "QPushButton:hover { background-color: #ef4444; color: white; }"
        )

        row_data = {
            "widget": row_widget,
            "path_edit": path_edit,
            "role_combo": role_combo,
            "custom_col_edit": custom_col_edit,
        }

        def _on_role_changed() -> None:
            is_cust = role_combo.isEnabled() and role_combo.currentData() == "custom"
            custom_col_edit.setVisible(is_cust)
            if is_cust and not custom_col_edit.text().strip():
                p_clean = path_edit.text().strip()
                if p_clean:
                    custom_col_edit.setText(suggest_custom_column_from_ini(p_clean))
            self._sync_custom_column_checkboxes()
            self._update_sources_summary()

        def _sync_role_from_path(txt: str) -> None:
            clean = txt.strip()
            ext = Path(clean).suffix.lower() if clean else ""
            role_combo.blockSignals(True)
            if ext == ".ini":
                role_combo.setEnabled(True)
                if role_combo.currentData() == "catalog":
                    suggested = infer_ini_role(clean)
                    idx_s = role_combo.findData(suggested)
                    role_combo.setCurrentIndex(idx_s if idx_s >= 0 else 1)
                if role_combo.currentData() == "custom" and clean:
                    custom_col_edit.setText(suggest_custom_column_from_ini(clean))
            else:
                idx_c = role_combo.findData("catalog")
                if idx_c >= 0:
                    role_combo.setCurrentIndex(idx_c)
                role_combo.setEnabled(False)
            role_combo.blockSignals(False)
            _on_role_changed()

        path_edit.textChanged.connect(_sync_role_from_path)
        role_combo.currentIndexChanged.connect(lambda _: _on_role_changed())
        custom_col_edit.textChanged.connect(lambda _: self._sync_custom_column_checkboxes())
        browse_btn.clicked.connect(lambda: self._browse_for_source_row(row_data))
        up_btn.clicked.connect(lambda: self._move_source_row(row_data, -1))
        down_btn.clicked.connect(lambda: self._move_source_row(row_data, +1))
        del_btn.clicked.connect(lambda: self._remove_source_row(row_data))

        row_layout.addWidget(path_edit, 1)
        row_layout.addWidget(role_combo)
        row_layout.addWidget(custom_col_edit)
        row_layout.addWidget(browse_btn)
        row_layout.addWidget(up_btn)
        row_layout.addWidget(down_btn)
        row_layout.addWidget(del_btn)

        self.source_rows.append(row_data)
        self.sources_vbox.addWidget(row_widget)

        _sync_role_from_path(path)
        if role:
            idx_r = role_combo.findData(role)
            if idx_r >= 0:
                role_combo.setCurrentIndex(idx_r)
        if custom_col:
            custom_col_edit.setText(custom_col)
        _on_role_changed()

        return row_data

    def _browse_for_source_row(self, row_data: dict) -> None:
        cur = row_data["path_edit"].text().strip()
        init_dir = str(Path(cur).parent) if (cur and Path(cur).parent.is_dir()) else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("xmlconv.io.pick_any_src_title", "Select Data Source (.xml, .dat, .ini)"),
            init_dir,
            tr(
                "xmlconv.io.pick_any_src_filter",
                "Catalog & INI Sources (*.xml *.dat *.ini *.pncat);;XML / DAT Files (*.xml *.dat);;MAME INI Files (*.ini);;All Files (*.*)",
            ),
        )
        if path:
            row_data["path_edit"].setText(path.replace("\\", "/"))

    def _move_source_row(self, row_data: dict, delta: int) -> None:
        if row_data not in self.source_rows:
            return
        idx = self.source_rows.index(row_data)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self.source_rows):
            return
        self.source_rows.pop(idx)
        self.source_rows.insert(new_idx, row_data)
        self.sources_vbox.removeWidget(row_data["widget"])
        self.sources_vbox.insertWidget(new_idx, row_data["widget"])
        self._update_sources_summary()

    def _remove_source_row(self, row_data: dict) -> None:
        if row_data not in self.source_rows:
            return
        if len(self.source_rows) <= 1:
            row_data["path_edit"].clear()
            row_data["custom_col_edit"].clear()
            self._sync_custom_column_checkboxes()
            return
        self.source_rows.remove(row_data)
        w = row_data["widget"]
        w.setParent(None)
        w.deleteLater()
        self._sync_custom_column_checkboxes()
        self._update_sources_summary()

    def _sync_custom_column_checkboxes(self) -> None:
        """Sincroniza en vivo las casillas de columnas nuevas declaradas por filas .ini personalizadas."""
        active_custom_cols: list[str] = []
        for r in self.source_rows:
            if not r["role_combo"].isEnabled() or r["role_combo"].currentData() != "custom":
                continue
            raw_c = r["custom_col_edit"].text().strip()
            p_txt = r["path_edit"].text().strip()
            clean_c = sanitize_custom_column_name(raw_c) or (suggest_custom_column_from_ini(p_txt) if p_txt else "")
            if clean_c and clean_c not in ALL_KNOWN_COLUMNS and clean_c not in active_custom_cols:
                active_custom_cols.append(clean_c)

        prev_states = {k: cb.isChecked() for k, cb in self.custom_column_checkboxes.items()}
        while self.custom_cols_grid.count():
            item = self.custom_cols_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.custom_column_checkboxes.clear()

        if not active_custom_cols:
            self.custom_cols_container.setVisible(False)
            return

        for idx, col_name in enumerate(active_custom_cols):
            cb = QCheckBox(f"✨ {col_name} (.ini)")
            cb.setStyleSheet("color: #7dd3fc; font-weight: 600;")
            cb.setChecked(prev_states.get(col_name, True))
            self.custom_column_checkboxes[col_name] = cb
            r_idx, c_idx = divmod(idx, 2)
            self.custom_cols_grid.addWidget(cb, r_idx, c_idx)

        self.custom_cols_container.setVisible(True)

    def _collect_source_specs(self) -> list[SourceSpec]:
        specs: list[SourceSpec] = []
        for r in self.source_rows:
            p = r["path_edit"].text().strip()
            if not p:
                continue
            role = str(r["role_combo"].currentData() or "auto")
            cust_col = r["custom_col_edit"].text().strip() if role == "custom" else ""
            specs.append(SourceSpec(path=p, role=role, custom_column=cust_col))
        return specs

    def _update_sources_summary(self) -> None:
        specs = self._collect_source_specs()
        if not specs:
            self.src_info_lbl.setText(tr("xmlconv.io.no_src", "No source files selected."))
            return

        valid_bytes = 0
        missing = 0
        cat_count = 0
        ini_count = 0
        for s in specs:
            p = Path(s.path)
            if p.is_file():
                valid_bytes += os.path.getsize(p)
                if p.suffix.lower() == ".ini" or s.role != "catalog":
                    ini_count += 1
                else:
                    cat_count += 1
            else:
                missing += 1

        if missing > 0:
            self.src_info_lbl.setText(
                tr("xmlconv.io.sources_missing_warn", "⚠ {count} selected source file(s) do not exist on disk.", count=missing)
            )
        else:
            self.src_info_lbl.setText(
                tr(
                    "xmlconv.io.sources_summary",
                    "{total} source(s) ready ({cats} XML/DAT · {inis} INI)  ·  Total input: {size}",
                    total=len(specs),
                    cats=cat_count,
                    inis=ini_count,
                    size=_format_bytes(valid_bytes),
                )
            )

    # ------------------------------------------------------------------
    # SELECCIÓN DE COLUMNAS Y ARCHIVOS
    # ------------------------------------------------------------------
    def _set_column_selection(self, mode: str) -> None:
        minimal_ids = {"title", "year", "manufacturer", "genre", "bios", "sourcefile", "orientation"}
        for gid, _ikey, _lbl, _pcols, def_checked in COLUMN_GROUPS_SPEC:
            cb = self.column_checkboxes.get(gid)
            if not cb:
                continue
            if mode == "all":
                cb.setChecked(True)
            elif mode == "minimal":
                cb.setChecked(gid in minimal_ids)
            else:
                cb.setChecked(def_checked)
        for cb in self.custom_column_checkboxes.values():
            cb.setChecked(True)

    def _get_selected_column_groups(self) -> list[str]:
        selected = [gid for gid, cb in self.column_checkboxes.items() if cb.isChecked()]
        for custom_col, cb in self.custom_column_checkboxes.items():
            if cb.isChecked() and custom_col not in selected:
                selected.append(custom_col)
        return selected

    def _pick_output_pncat(self) -> bool:
        cur = self.dst_edit.text().strip()
        init_path = str(Path(cur).with_suffix(PNCAT_EXT)) if cur else ""
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("xmlconv.io.pick_dst_title", "Save PlayNexus Fast Catalog (.pncat)"),
            init_path,
            tr("xmlconv.io.pick_dst_filter", "PlayNexus Fast Catalog (*.pncat)"),
        )
        if path:
            if not path.lower().endswith(PNCAT_EXT):
                path += PNCAT_EXT
            self.dst_edit.setText(path.replace("\\", "/"))
            return True
        return False

    def _pick_existing_pncat(self) -> None:
        cur = self._loaded_catalog_path or self.dst_edit.text().strip()
        init_dir = str(Path(cur).parent) if (cur and Path(cur).parent.is_dir()) else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("xmlconv.io.open_existing_title", "Open PlayNexus Fast Catalog (.pncat)"),
            init_dir,
            tr("xmlconv.io.pick_dst_filter", "PlayNexus Fast Catalog (*.pncat)"),
        )
        if path:
            norm = path.replace("\\", "/")
            self.dst_edit.setText(norm)
            self.load_preview_catalog(norm)

    # ------------------------------------------------------------------
    # CONVERSIÓN EN SEGUNDO PLANO
    # ------------------------------------------------------------------
    def start_conversion(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        specs = self._collect_source_specs()
        if not specs:
            QMessageBox.warning(
                self,
                tr("xmlconv.err.no_src_title", "Source File Required"),
                tr("xmlconv.err.no_src_msg", "Please add at least one valid .xml or .dat source file to convert."),
            )
            return

        for s in specs:
            if not Path(s.path).is_file():
                QMessageBox.warning(
                    self,
                    tr("xmlconv.err.no_src_title", "Source File Required"),
                    tr("xmlconv.err.missing_src_item", "The specified source file does not exist:\n{path}", path=s.path),
                )
                return

        has_catalog = any(
            Path(s.path).suffix.lower() != ".ini" and s.role == "catalog"
            for s in specs
        )
        if not has_catalog:
            QMessageBox.warning(
                self,
                tr("xmlconv.err.no_cat_title", "Catalog Source Required"),
                tr(
                    "xmlconv.err.no_cat_msg",
                    "Include at least one .xml or .dat catalog source so PlayNexus has a game list to enrich.",
                ),
            )
            return

        dst_path = self.dst_edit.text().strip()
        if not dst_path:
            if not self._pick_output_pncat():
                return
            dst_path = self.dst_edit.text().strip()
        elif not dst_path.lower().endswith(PNCAT_EXT):
            dst_path += PNCAT_EXT
            self.dst_edit.setText(dst_path)

        dst_abs = os.path.abspath(dst_path).lower()
        for s in specs:
            if os.path.abspath(s.path).lower() == dst_abs:
                QMessageBox.warning(
                    self,
                    tr("xmlconv.err.same_path_title", "Invalid Output Path"),
                    tr("xmlconv.err.same_path_msg", "The output .pncat file must be different from all source files."),
                )
                return

        selected_groups = self._get_selected_column_groups()
        opts = ConvertOptions(
            selected_columns=selected_groups,
            exclude_devices=self.cb_excl_devices.isChecked(),
            exclude_mechanical=self.cb_excl_mech.isChecked(),
            exclude_non_runnable=self.cb_excl_nonrun.isChecked(),
            exclude_clones=self.cb_excl_clones.isChecked(),
        )

        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.reveal_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_lbl.setText(tr("xmlconv.run.starting", "Reading sources and building custom .pncat catalog..."))

        self._worker = XmlConvertWorker(specs, dst_path, opts, self)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished_ok.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

    def cancel_conversion(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status_lbl.setText(tr("xmlconv.run.cancelling", "Cancelling conversion..."))

    def _on_worker_progress(self, pct: int, seen: int, written: int, bytes_read: int, elapsed: float) -> None:
        self.progress_bar.setValue(pct)
        rate = int(seen / elapsed) if elapsed > 0.05 else 0
        self.status_lbl.setText(
            tr(
                "xmlconv.run.progress_msg",
                "⏳ {pct}%  ·  {seen:,} read  ·  {written:,} merged  ·  {speed:,} entries/s  ({read_mb})",
                pct=pct,
                seen=seen,
                written=written,
                speed=rate,
                read_mb=_format_bytes(bytes_read),
            )
        )

    def _on_worker_finished(self, summary: ConvertSummary) -> None:
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if summary.cancelled:
            self.progress_bar.setValue(0)
            self.status_lbl.setText(tr("xmlconv.run.cancelled_done", "⏹ Conversion cancelled by user."))
            return

        self.progress_bar.setValue(100)
        skipped_txt = ""
        if summary.total_skipped > 0:
            skipped_txt = tr("xmlconv.run.skipped_suffix", "  ·  {count:,} filtered out", count=summary.total_skipped)

        self.status_lbl.setText(
            tr(
                "xmlconv.run.done_msg",
                "✅ Done in {sec:.2f} s  ·  {written:,} games  ·  {src_sz} ➔ {dst_sz} (-{pct:.1f}%){skipped}",
                sec=summary.elapsed_seconds,
                written=summary.written_entries,
                src_sz=_format_bytes(summary.source_size_bytes),
                dst_sz=_format_bytes(summary.output_size_bytes),
                pct=summary.size_reduction_pct,
                skipped=skipped_txt,
            )
        )
        out_norm = summary.output_path.replace("\\", "/")
        self.dst_edit.setText(out_norm)
        self.reveal_btn.setEnabled(True)
        self.load_preview_catalog(out_norm)

    def _on_worker_failed(self, err: str) -> None:
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText(tr("xmlconv.run.error_status", "❌ Error during conversion."))
        QMessageBox.critical(
            self,
            tr("xmlconv.err.failed_title", "Conversion Error"),
            tr("xmlconv.err.failed_msg", "Could not convert the selected sources:\n\n{err}", err=err),
        )

    # ------------------------------------------------------------------
    # VISTA PREVIA DINÁMICA SEGÚN LAS COLUMNAS DEL .PNCAT
    # ------------------------------------------------------------------
    def _derive_preview_cols(self, file_cols: list[str]) -> list[str]:
        fset = set(file_cols)
        ui_cols = ["rom_name"]
        for key, _ik, _fb, _w in _PREVIEW_COLUMN_DEFS:
            if key == "rom_name":
                continue
            if key == "resolution_ui":
                if "display_width" in fset or "display_height" in fset:
                    ui_cols.append(key)
            elif key == "controls_ui":
                if "control_type" in fset or "control_buttons" in fset:
                    ui_cols.append(key)
            elif key == "display_rotate":
                if "display_rotate" in fset or "display_type" in fset:
                    ui_cols.append(key)
            elif key in fset:
                ui_cols.append(key)
        # Agregar también cualquier columna personalizada definida desde .ini
        for fc in file_cols:
            if fc not in MANDATORY_COLUMNS and fc not in ALL_KNOWN_COLUMNS and fc not in ui_cols:
                ui_cols.append(fc)
        return ui_cols

    def _rebuild_preview_columns(self, ui_cols: list[str]) -> None:
        self._active_preview_cols = list(ui_cols)
        def_map = {k: (ik, fb, w) for k, ik, fb, w in _PREVIEW_COLUMN_DEFS}
        headers: list[str] = []
        widths: list[int] = []
        for k in self._active_preview_cols:
            if k in def_map:
                ik, fb, w = def_map[k]
                headers.append(tr(ik, fb))
                widths.append(w)
            else:
                headers.append(f"✨ {k}")
                widths.append(120)

        self.preview_table.setSortingEnabled(False)
        self.preview_table.clear()
        self.preview_table.setColumnCount(len(headers))
        self.preview_table.setHorizontalHeaderLabels(headers)
        configure_details_table(
            self.preview_table,
            col_widths=widths,
            stretch_last=True,
            sorting=True,
            hide_vertical_header=True,
            alternating_rows=True,
        )

    def load_preview_catalog(self, pncat_path: str) -> None:
        p = Path(pncat_path)
        if not p.is_file():
            return
        try:
            t0 = time.perf_counter()
            entries, file_cols = read_fast_catalog_table(p)
            self._load_ms = (time.perf_counter() - t0) * 1000.0
            self._loaded_catalog_path = str(p).replace("\\", "/")
            self._catalog_entries = entries
            self._catalog_columns = file_cols
            self._rebuild_preview_columns(self._derive_preview_cols(file_cols))
            self.reveal_btn.setEnabled(True)
            self._populate_preview_table()
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("xmlconv.err.load_title", "Could Not Read .pncat"),
                tr("xmlconv.err.load_msg", "Error loading fast catalog:\n{err}", err=exc),
            )

    def _populate_preview_table(self) -> None:
        entries = self._catalog_entries
        if not entries:
            self.preview_table.setRowCount(0)
            self.entry_detail_lbl.setVisible(False)
            return

        q = self.search_edit.text().strip().lower()
        if q:
            matched = [
                e for e in entries
                if q in e["rom_name"].lower()
                or q in e["title"].lower()
                or q in e["manufacturer"].lower()
                or q in e["year"].lower()
                or q in e["genre"].lower()
                or q in e["sourcefile"].lower()
                or q in e["cloneof"].lower()
                or q in (e.get("bios") or "").lower()
                or q in (e.get("notes") or "").lower()
                or any(q in str(v).lower() for v in (e.get("properties") or {}).values())
            ]
        else:
            matched = entries

        max_rows = int(self.limit_combo.currentData() or 0)
        shown = matched[:max_rows] if max_rows > 0 else matched

        vert_label = tr("xmlconv.screen.vertical", "Vertical")
        horiz_label = tr("xmlconv.screen.horizontal", "Horizontal")
        active_cols = self._active_preview_cols

        with paused_table_sorting(self.preview_table):
            self.preview_table.setRowCount(len(shown))
            for row_idx, entry in enumerate(shown):
                props = entry.get("properties") or {}
                for col_idx, col_key in enumerate(active_cols):
                    if col_key == "rom_name":
                        item = SortableTableWidgetItem(entry["rom_name"])
                        item.setData(Qt.UserRole, entry)
                    elif col_key == "year":
                        ys = entry["year"]
                        item = SortableTableWidgetItem(ys, sort_key=(int(ys) if ys.isdigit() else 999999))
                    elif col_key == "display_rotate":
                        is_vert = is_game_vertical({"xml_properties": props})
                        rot = props.get("display_rotate") or props.get("rotate") or ""
                        if is_vert:
                            scr_txt = f"{vert_label} ({rot}°)" if rot else vert_label
                        else:
                            scr_txt = horiz_label if props.get("display_type") or rot else "—"
                        item = SortableTableWidgetItem(scr_txt)
                    elif col_key == "resolution_ui":
                        w = props.get("display_width", "")
                        h = props.get("display_height", "")
                        item = SortableTableWidgetItem(f"{w}×{h}" if (w and h) else "")
                    elif col_key == "controls_ui":
                        ct = props.get("control_type", "")
                        cb = props.get("control_buttons", "")
                        txt = f"{ct} ({cb}b)" if (ct and cb) else (ct or cb)
                        item = SortableTableWidgetItem(txt)
                    elif col_key == "status":
                        item = SortableTableWidgetItem(props.get("status") or props.get("driver_status") or "")
                    elif col_key == "romof":
                        item = SortableTableWidgetItem(props.get("romof", ""))
                    elif col_key == "bios":
                        item = SortableTableWidgetItem(entry.get("bios") or props.get("bios", ""))
                    else:
                        item = SortableTableWidgetItem(str(entry.get(col_key) or props.get(col_key, "")))
                    self.preview_table.setItem(row_idx, col_idx, item)

        cat_name = Path(self._loaded_catalog_path).name if self._loaded_catalog_path else ""
        self.preview_summary_lbl.setText(
            tr(
                "xmlconv.preview.summary_cols",
                "📄 {name}  ·  {cols} columns  ·  Showing {shown:,} of {matched:,} ({total:,} total)  ·  ⚡ {ms:.0f} ms",
                name=cat_name,
                cols=len(self._catalog_columns),
                shown=len(shown),
                matched=len(matched),
                total=len(entries),
                ms=self._load_ms,
            )
        )
        if len(shown) > 0:
            self.preview_table.selectRow(0)
        else:
            self.entry_detail_lbl.setVisible(False)

    def _on_preview_selection_changed(self) -> None:
        sel = self.preview_table.selectedItems()
        if not sel:
            self.entry_detail_lbl.setVisible(False)
            return
        row = sel[0].row()
        first_item = self.preview_table.item(row, 0)
        entry = first_item.data(Qt.UserRole) if first_item else None
        if not isinstance(entry, dict):
            self.entry_detail_lbl.setVisible(False)
            return

        props = entry.get("properties") or {}
        bits = [f"<b>{entry['title']}</b> (<code>{entry['rom_name']}</code>)"]
        bios_val = entry.get("bios") or props.get("bios", "")
        if bios_val:
            bits.append(f"BIOS: <b>{bios_val}</b>")
        if props.get("status") or props.get("driver_status"):
            bits.append(f"Driver: <b>{props.get('status') or props.get('driver_status')}</b>")
        if props.get("display_width") and props.get("display_height"):
            rot = f" @ {props['display_rotate']}°" if props.get("display_rotate") else ""
            bits.append(f"Res: <b>{props['display_width']}×{props['display_height']}{rot}</b>")
        if props.get("control_type") or props.get("control_buttons"):
            ctrl = props.get("control_type", "")
            btns = f" ({props['control_buttons']} btn)" if props.get("control_buttons") else ""
            bits.append(f"Control: <b>{ctrl}{btns}</b>")
        if entry.get("crc"):
            bits.append(f"CRC: <code>{entry['crc']}</code>")
        if props.get("romof"):
            bits.append(f"ROM Of: <code>{props['romof']}</code>")
        self.entry_detail_lbl.setText("   ·   ".join(bits))
        self.entry_detail_lbl.setVisible(True)

    def _current_candidate_pncat(self) -> str:
        dst = self.dst_edit.text().strip()
        if dst and Path(dst).is_file() and is_fast_catalog_file(dst):
            return dst.replace("\\", "/")
        if self._loaded_catalog_path and Path(self._loaded_catalog_path).is_file():
            return self._loaded_catalog_path
        return ""

    def _reveal_current_output(self) -> None:
        cand = self._current_candidate_pncat() or self.dst_edit.text().strip()
        if cand:
            _reveal_file_in_explorer(cand)

    def cleanup(self) -> None:
        self._search_timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1500)
