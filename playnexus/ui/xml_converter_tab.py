"""
Pestaña 'Conversor XML' para el Configurador de PlayNexus.

Convierte catálogos XML / DAT pesados (MAME 300+ MB, HyperSpin, Logiqx DAT, EmulationStation gamelist.xml)
al formato de texto plano ultrarrápido y 100% portable '.pncat' (PlayNexus Fast Catalog v1),
con lectura por streaming en hilo secundario, pre-filtros opcionales, buscador de prueba instantáneo
y vinculación en 1 clic a cualquier lista existente.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
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

from playnexus.db import CONFIG_DIR, Database
from playnexus.i18n import tr
from playnexus.services.library import apply_xml_to_list, sync_filtered_lists_for_source
from playnexus.services.media import is_game_vertical
from playnexus.services.xml_converter import (
    PNCAT_EXT,
    ConvertOptions,
    ConvertSummary,
    convert_xml_to_pncat,
    is_fast_catalog_file,
    parse_mame_genre_ini,
    read_fast_catalog_entries,
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


class XmlConvertWorker(QThread):
    """Hilo de conversión XML/DAT -> .pncat en streaming sin bloquear la interfaz."""

    progress = Signal(int, int, int, int, float)  # pct, seen, written, bytes_read, elapsed
    finished_ok = Signal(object)  # ConvertSummary
    failed = Signal(str)

    def __init__(
        self,
        source_path: str,
        output_path: str,
        options: ConvertOptions,
        parent=None,
    ):
        super().__init__(parent)
        self.source_path = source_path
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

            summary = convert_xml_to_pncat(
                self.source_path,
                self.output_path,
                options=self.options,
                progress_callback=_on_prog,
                cancel_check=lambda: self._cancelled,
            )
            self.finished_ok.emit(summary)
        except Exception as exc:
            self.failed.emit(str(exc))


class XmlConverterWidget(QWidget):
    """Pestaña principal del Conversor de Catálogos XML / DAT a formato rápido .pncat."""

    catalog_linked = Signal(int)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._worker: XmlConvertWorker | None = None
        self._loaded_catalog_path: str = ""
        self._catalog_entries: list[dict] = []
        self._load_ms: float = 0.0
        self._output_manually_edited: bool = False

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._populate_preview_table)

        self._build_ui()
        self.refresh_lists()

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
                "⚡  XML / DAT Fast Catalog Converter (.pncat)",
            )
        )
        title_lbl.setStyleSheet("font-size: 13pt; font-weight: 700; color: #e6e9f0; border: none;")
        sub_lbl = QLabel(
            tr(
                "xmlconv.header.subtitle",
                "Convert heavy XML or DAT files (such as MAME 300+ MB, HyperSpin, Logiqx DAT, or gamelist.xml) "
                "into PlayNexus's ultra-fast 100% portable plain-text format (.pncat): ~98% smaller and over 100x faster.",
            )
        )
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet("color: #9aa3b8; font-size: 9pt; border: none;")
        header_text_col.addWidget(title_lbl)
        header_text_col.addWidget(sub_lbl)
        header_layout.addLayout(header_text_col, 1)

        open_existing_btn = QPushButton(tr("xmlconv.btn.open_pncat", "📂  Open existing .pncat…"))
        open_existing_btn.setToolTip(
            tr("xmlconv.btn.open_pncat_tip", "Load an already-converted .pncat file to inspect or link it to a list")
        )
        open_existing_btn.clicked.connect(self._pick_existing_pncat)
        header_layout.addWidget(open_existing_btn)

        outer.addWidget(header_frame)

        # Splitter principal: Izquierda (Configuración / Conversión / Vinculación) | Derecha (Vista previa)
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

        # 1. Origen y Destino
        io_group = QGroupBox(tr("xmlconv.io.group", "1. Source XML / DAT & Output File"))
        io_form = QFormLayout(io_group)
        io_form.setSpacing(8)

        self.src_list_combo = QComboBox()
        self.src_list_combo.activated.connect(self._on_prefill_from_list)
        io_form.addRow(tr("xmlconv.io.from_list", "Take XML from list:"), self.src_list_combo)

        src_row = QHBoxLayout()
        src_row.setSpacing(6)
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText(
            tr("xmlconv.io.src_placeholder", "Select a .xml or .dat file (e.g. Mame_289.xml)...")
        )
        self.src_edit.textChanged.connect(self._on_source_changed)
        src_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
        src_btn.clicked.connect(self._pick_source_xml)
        src_row.addWidget(self.src_edit, 1)
        src_row.addWidget(src_btn)
        src_holder = QWidget()
        src_holder.setLayout(src_row)
        io_form.addRow(tr("xmlconv.io.src_label", "Source XML / DAT:"), src_holder)

        self.src_info_lbl = QLabel(tr("xmlconv.io.no_src", "No source file selected."))
        self.src_info_lbl.setStyleSheet("color: #8b95ab; font-size: 8.5pt;")
        io_form.addRow("", self.src_info_lbl)

        genre_row = QHBoxLayout()
        genre_row.setSpacing(6)
        self.genre_ini_edit = QLineEdit()
        self.genre_ini_edit.setPlaceholderText(
            tr("xmlconv.io.genre_ini_placeholder", "Optional for MAME: Category.ini, catver.ini or genre.ini...")
        )
        self.genre_ini_edit.textChanged.connect(self._on_genre_ini_changed)
        genre_browse_btn = QPushButton(tr("dlg.btn.browse", "Browse…"))
        genre_browse_btn.clicked.connect(self._pick_genre_ini)
        genre_auto_btn = QPushButton(tr("xmlconv.io.genre_auto_btn", "🔎 MAME"))
        genre_auto_btn.setToolTip(
            tr(
                "xmlconv.io.genre_auto_tip",
                "Search Category.ini / catver.ini / genre.ini inside your configured MAME emulators' folders",
            )
        )
        genre_auto_btn.clicked.connect(self._auto_find_mame_genre_ini)
        genre_clear_btn = QPushButton("✕")
        genre_clear_btn.setFixedWidth(28)
        genre_clear_btn.clicked.connect(lambda: self.genre_ini_edit.clear())
        genre_row.addWidget(self.genre_ini_edit, 1)
        genre_row.addWidget(genre_browse_btn)
        genre_row.addWidget(genre_auto_btn)
        genre_row.addWidget(genre_clear_btn)
        genre_holder = QWidget()
        genre_holder.setLayout(genre_row)
        io_form.addRow(tr("xmlconv.io.genre_ini_label", "MAME Genres (.ini):"), genre_holder)

        self.genre_info_lbl = QLabel("")
        self.genre_info_lbl.setStyleSheet("color: #7dd3fc; font-size: 8.5pt;")
        self.genre_info_lbl.setVisible(False)
        io_form.addRow("", self.genre_info_lbl)

        dst_row = QHBoxLayout()
        dst_row.setSpacing(6)
        self.dst_edit = QLineEdit()
        self.dst_edit.setPlaceholderText(
            tr("xmlconv.io.dst_placeholder", "Destination path (.pncat)...")
        )
        self.dst_edit.textEdited.connect(self._on_dst_edited_manually)
        dst_btn = QPushButton(tr("xmlconv.io.save_as", "Save as…"))
        dst_btn.clicked.connect(self._pick_output_pncat)
        portable_dir_btn = QPushButton(tr("xmlconv.io.use_portable_dir", "📁 config/catalogs"))
        portable_dir_btn.setToolTip(
            tr(
                "xmlconv.io.use_portable_dir_tip",
                "Place the output .pncat inside PlayNexus's portable 'config/catalogs' folder",
            )
        )
        portable_dir_btn.clicked.connect(self._set_output_in_portable_catalogs)
        dst_row.addWidget(self.dst_edit, 1)
        dst_row.addWidget(dst_btn)
        dst_row.addWidget(portable_dir_btn)
        dst_holder = QWidget()
        dst_holder.setLayout(dst_row)
        io_form.addRow(tr("xmlconv.io.dst_label", "Output (.pncat):"), dst_holder)

        left_vbox.addWidget(io_group)

        # 2. Perfil y Pre-filtros
        opts_group = QGroupBox(tr("xmlconv.opts.group", "2. Optimization Profile & Pre-Filters"))
        opts_vbox = QVBoxLayout(opts_group)
        opts_vbox.setSpacing(7)

        prof_form = QFormLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.addItem(
            tr(
                "xmlconv.opts.profile_optimized",
                "⚡ Optimized (Recommended — keeps titles, filters & screen rotation)",
            ),
            "optimized",
        )
        self.profile_combo.addItem(
            tr(
                "xmlconv.opts.profile_full",
                "📦 Full (Keeps all extra XML child attributes)",
            ),
            "full",
        )
        prof_form.addRow(tr("xmlconv.opts.profile_label", "Profile:"), self.profile_combo)
        opts_vbox.addLayout(prof_form)

        filt_caption = QLabel(
            tr(
                "xmlconv.opts.prefilter_hint",
                "Optional pre-filters during conversion (BIOS sets & references are always preserved for list filtering):",
            )
        )
        filt_caption.setWordWrap(True)
        filt_caption.setStyleSheet("color: #9aa3b8; font-size: 8.5pt; margin-top: 2px;")
        opts_vbox.addWidget(filt_caption)

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
        for cb in (
            self.cb_excl_devices,
            self.cb_excl_mech,
            self.cb_excl_nonrun,
            self.cb_excl_clones,
        ):
            opts_vbox.addWidget(cb)

        left_vbox.addWidget(opts_group)

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

        # 4. Vincular en 1 clic a una lista
        link_group = QGroupBox(tr("xmlconv.link.group", "4. Link Fast Catalog to a Game List"))
        link_vbox = QVBoxLayout(link_group)
        link_vbox.setSpacing(8)

        link_form = QFormLayout()
        self.target_list_combo = QComboBox()
        link_form.addRow(tr("xmlconv.link.target_list", "Target list:"), self.target_list_combo)
        link_vbox.addLayout(link_form)

        self.apply_now_cb = QCheckBox(
            tr(
                "xmlconv.link.apply_now_cb",
                "Immediately update titles & metadata of games already in this list",
            )
        )
        self.apply_now_cb.setChecked(True)
        link_vbox.addWidget(self.apply_now_cb)

        self.link_btn = QPushButton(tr("xmlconv.link.btn", "🔗  Link .pncat to Selected List"))
        self.link_btn.setMinimumHeight(36)
        self.link_btn.setEnabled(False)
        self.link_btn.clicked.connect(self._link_catalog_to_selected_list)
        link_vbox.addWidget(self.link_btn)

        left_vbox.addWidget(link_group)
        left_vbox.addStretch(1)

        left_scroll.setWidget(left_container)
        left_scroll.setMinimumWidth(420)
        splitter.addWidget(left_scroll)

        # ---------------- PANEL DERECHO (EXPLORADOR DE VISTA PREVIA) ----------------
        right_panel = QGroupBox(tr("xmlconv.preview.group", "Fast Catalog Inspector & Instant Search"))
        right_vbox = QVBoxLayout(right_panel)
        right_vbox.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            tr(
                "xmlconv.preview.search_placeholder",
                "🔍 Search by ROM, title, manufacturer, year, genre, driver, or cloneof...",
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
            tr("xmlconv.preview.empty", "Convert an XML/DAT or open an existing .pncat file to preview its entries.")
        )
        self.preview_summary_lbl.setStyleSheet("color: #7dd3fc; font-size: 8.8pt; font-weight: 500;")
        right_vbox.addWidget(self.preview_summary_lbl)

        self.preview_table = QTableWidget(0, 10)
        self.preview_table.setHorizontalHeaderLabels([
            tr("xmlconv.col.rom", "ROM"),
            tr("xmlconv.col.title", "Full Title"),
            tr("xmlconv.col.year", "Year"),
            tr("xmlconv.col.manufacturer", "Manufacturer"),
            tr("xmlconv.col.genre", "Genre"),
            tr("xmlconv.col.players", "Players"),
            tr("xmlconv.col.cloneof", "Clone Of"),
            tr("xmlconv.col.bios", "BIOS"),
            tr("xmlconv.col.sourcefile", "Driver / Source"),
            tr("xmlconv.col.orientation", "Screen"),
        ])
        configure_details_table(
            self.preview_table,
            col_widths=[100, 245, 58, 135, 105, 60, 82, 82, 115, 90],
            stretch_last=True,
            sorting=True,
            hide_vertical_header=True,
            alternating_rows=True,
        )
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
        splitter.setSizes([460, 760])
        outer.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # LISTAS Y RUTAS
    # ------------------------------------------------------------------
    def refresh_lists(self, preferred_list_id: int | None = None) -> None:
        rows = self.db.get_lists(with_counts=False)
        game_lists = [
            r for r in rows
            if r.get("list_type") not in ("menu", "filtered")
        ]

        prev_target_id = preferred_list_id or self.target_list_combo.currentData()

        self.src_list_combo.blockSignals(True)
        self.src_list_combo.clear()
        self.src_list_combo.addItem(
            tr("xmlconv.io.select_list_placeholder", "— Select a list with XML/DAT configured —"),
            None,
        )
        for r in game_lists:
            xp = (r.get("xml_path") or "").strip()
            if xp:
                badge = Path(xp).name
                self.src_list_combo.addItem(f"🎮 {r['name']}  ({badge})", r["id"])
        self.src_list_combo.blockSignals(False)

        self.target_list_combo.blockSignals(True)
        self.target_list_combo.clear()
        selected_idx = 0
        for idx, r in enumerate(game_lists):
            xp = (r.get("xml_path") or "").strip()
            suffix = f"  [{Path(xp).name}]" if xp else ""
            self.target_list_combo.addItem(f"🎮 {r['name']}{suffix}", r["id"])
            if prev_target_id and r["id"] == prev_target_id:
                selected_idx = idx
        if self.target_list_combo.count() > 0:
            self.target_list_combo.setCurrentIndex(selected_idx)
        self.target_list_combo.blockSignals(False)
        self._update_link_button_state()

    def _on_prefill_from_list(self, index: int) -> None:
        list_id = self.src_list_combo.itemData(index)
        if not list_id:
            return
        row = self.db.get_list(list_id)
        if not row:
            return
        xp = (row.get("xml_path") or "").strip()
        if xp:
            self._output_manually_edited = False
            self.src_edit.setText(xp.replace("\\", "/"))
            if is_fast_catalog_file(xp) and Path(xp).is_file():
                self.load_preview_catalog(xp)
        # Sincronizar también el combo de destino con esa misma lista
        for i in range(self.target_list_combo.count()):
            if self.target_list_combo.itemData(i) == list_id:
                self.target_list_combo.setCurrentIndex(i)
                break

    def _on_source_changed(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            self.src_info_lbl.setText(tr("xmlconv.io.no_src", "No source file selected."))
            return
        p = Path(clean)
        if p.is_file():
            sz = os.path.getsize(p)
            self.src_info_lbl.setText(
                tr("xmlconv.io.src_size_info", "Source size: {size}  ·  {name}", size=_format_bytes(sz), name=p.name)
            )
            if not self._output_manually_edited or not self.dst_edit.text().strip():
                if p.suffix.lower() == PNCAT_EXT:
                    out_p = p.with_name(p.stem + "_opt" + PNCAT_EXT)
                else:
                    out_p = p.with_suffix(PNCAT_EXT)
                self.dst_edit.setText(str(out_p).replace("\\", "/"))
        else:
            self.src_info_lbl.setText(tr("xmlconv.io.src_missing", "⚠ File does not exist on disk."))

    def _on_dst_edited_manually(self, _text: str) -> None:
        self._output_manually_edited = True
        self._update_link_button_state()

    def _pick_source_xml(self) -> None:
        cur = self.src_edit.text().strip()
        init_dir = str(Path(cur).parent) if (cur and Path(cur).parent.is_dir()) else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("xmlconv.io.pick_src_title", "Select XML or DAT Catalog"),
            init_dir,
            tr("xmlconv.io.pick_src_filter", "XML / DAT Files (*.xml *.dat);;All Files (*.*)"),
        )
        if path:
            self._output_manually_edited = False
            self.src_edit.setText(path.replace("\\", "/"))

    def _on_genre_ini_changed(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            self.genre_info_lbl.setVisible(False)
            return
        p = Path(clean)
        if p.is_file():
            try:
                g_map = parse_mame_genre_ini(p)
                self.genre_info_lbl.setText(
                    tr(
                        "xmlconv.io.genre_ini_loaded",
                        "✓ {name}  ·  {count:,} ROM genres ready (clones inherit automatically)",
                        name=p.name,
                        count=len(g_map),
                    )
                )
            except Exception:
                self.genre_info_lbl.setText(f"✓ {p.name}")
            self.genre_info_lbl.setVisible(True)
        else:
            self.genre_info_lbl.setText(tr("xmlconv.io.src_missing", "⚠ File does not exist on disk."))
            self.genre_info_lbl.setVisible(True)

    def _pick_genre_ini(self) -> None:
        cur = self.genre_ini_edit.text().strip() or self.src_edit.text().strip()
        init_dir = str(Path(cur).parent) if (cur and Path(cur).parent.is_dir()) else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("xmlconv.io.pick_genre_title", "Select MAME Genre INI (Category.ini / catver.ini)"),
            init_dir,
            tr("xmlconv.io.pick_genre_filter", "MAME Category / Genre INI (*.ini);;All Files (*.*)"),
        )
        if path:
            self.genre_ini_edit.setText(path.replace("\\", "/"))

    def _auto_find_mame_genre_ini(self) -> None:
        preferred_names = ("catver.ini", "category.ini", "genre.ini")
        search_dirs: list[Path] = []
        src_txt = self.src_edit.text().strip()
        if src_txt and Path(src_txt).parent.is_dir():
            sp = Path(src_txt).parent
            search_dirs.extend([sp, sp / "folders", sp / "ini"])

        for emu in self.db.get_emulators():
            exe = (emu.get("executable") or "").strip()
            if exe and Path(exe).parent.is_dir():
                ep = Path(exe).parent
                search_dirs.extend([ep / "folders", ep, ep / "ini"])

        found_path: Path | None = None
        for d in search_dirs:
            if not d.is_dir():
                continue
            by_low = {f.name.lower(): f for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".ini"}
            for pref in preferred_names:
                if pref in by_low:
                    found_path = by_low[pref]
                    break
            if found_path:
                break

        if found_path:
            self.genre_ini_edit.setText(str(found_path).replace("\\", "/"))
        else:
            QMessageBox.information(
                self,
                tr("xmlconv.io.genre_not_found_title", "INI Not Found Automatically"),
                tr(
                    "xmlconv.io.genre_not_found_msg",
                    "No Category.ini, catver.ini, or genre.ini was found in your configured MAME folders.\n"
                    "Use 'Browse…' to select it manually if you have one.",
                ),
            )

    def _pick_output_pncat(self) -> None:
        cur = self.dst_edit.text().strip() or self.src_edit.text().strip()
        init_path = str(Path(cur).with_suffix(PNCAT_EXT)) if cur else f"catalog{PNCAT_EXT}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("xmlconv.io.pick_dst_title", "Save PlayNexus Fast Catalog (.pncat)"),
            init_path,
            tr("xmlconv.io.pick_dst_filter", "PlayNexus Fast Catalog (*.pncat)"),
        )
        if path:
            if not path.lower().endswith(PNCAT_EXT):
                path += PNCAT_EXT
            self._output_manually_edited = True
            self.dst_edit.setText(path.replace("\\", "/"))
            self._update_link_button_state()

    def _set_output_in_portable_catalogs(self) -> None:
        cat_dir = CONFIG_DIR / "catalogs"
        cat_dir.mkdir(parents=True, exist_ok=True)
        src_txt = self.src_edit.text().strip()
        stem = Path(src_txt).stem if src_txt else "catalog"
        out_path = cat_dir / f"{stem}{PNCAT_EXT}"
        self._output_manually_edited = True
        self.dst_edit.setText(str(out_path).replace("\\", "/"))
        self._update_link_button_state()

    def _pick_existing_pncat(self) -> None:
        cat_dir = CONFIG_DIR / "catalogs"
        init_dir = str(cat_dir) if cat_dir.is_dir() else ""
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

        src_path = self.src_edit.text().strip()
        dst_path = self.dst_edit.text().strip()
        if not src_path or not Path(src_path).is_file():
            QMessageBox.warning(
                self,
                tr("xmlconv.err.no_src_title", "Source File Required"),
                tr("xmlconv.err.no_src_msg", "Please select a valid .xml or .dat file to convert."),
            )
            return

        if not dst_path:
            dst_path = str(Path(src_path).with_suffix(PNCAT_EXT)).replace("\\", "/")
            self.dst_edit.setText(dst_path)
        elif not dst_path.lower().endswith(PNCAT_EXT):
            dst_path += PNCAT_EXT
            self.dst_edit.setText(dst_path)

        if os.path.abspath(src_path).lower() == os.path.abspath(dst_path).lower():
            QMessageBox.warning(
                self,
                tr("xmlconv.err.same_path_title", "Invalid Output Path"),
                tr("xmlconv.err.same_path_msg", "The output .pncat file must be different from the source file."),
            )
            return

        genre_ini = self.genre_ini_edit.text().strip()
        if genre_ini and not Path(genre_ini).is_file():
            QMessageBox.warning(
                self,
                tr("xmlconv.err.bad_genre_title", "Genre INI Not Found"),
                tr("xmlconv.err.bad_genre_msg", "The specified MAME genre .ini file does not exist:\n{path}", path=genre_ini),
            )
            return

        opts = ConvertOptions(
            profile=str(self.profile_combo.currentData() or "optimized"),
            genre_ini_path=genre_ini,
            exclude_devices=self.cb_excl_devices.isChecked(),
            exclude_mechanical=self.cb_excl_mech.isChecked(),
            exclude_non_runnable=self.cb_excl_nonrun.isChecked(),
            exclude_clones=self.cb_excl_clones.isChecked(),
        )

        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.reveal_btn.setEnabled(False)
        self.link_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_lbl.setText(tr("xmlconv.run.starting", "Streaming XML and building fast catalog..."))

        self._worker = XmlConvertWorker(src_path, dst_path, opts, self)
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
                "⏳ {pct}%  ·  {seen:,} read  ·  {written:,} saved  ·  {speed:,} entries/s  ({read_mb})",
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
            self._update_link_button_state()
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
        self._update_link_button_state()

    def _on_worker_failed(self, err: str) -> None:
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText(tr("xmlconv.run.error_status", "❌ Error during conversion."))
        self._update_link_button_state()
        QMessageBox.critical(
            self,
            tr("xmlconv.err.failed_title", "Conversion Error"),
            tr("xmlconv.err.failed_msg", "Could not convert the XML/DAT file:\n\n{err}", err=err),
        )

    # ------------------------------------------------------------------
    # VISTA PREVIA Y BÚSQUEDA INSTANTÁNEA
    # ------------------------------------------------------------------
    def load_preview_catalog(self, pncat_path: str) -> None:
        p = Path(pncat_path)
        if not p.is_file():
            return
        try:
            t0 = time.perf_counter()
            entries = read_fast_catalog_entries(p)
            self._load_ms = (time.perf_counter() - t0) * 1000.0
            self._loaded_catalog_path = str(p).replace("\\", "/")
            self._catalog_entries = entries
            self.reveal_btn.setEnabled(True)
            self._update_link_button_state()
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
            ]
        else:
            matched = entries

        max_rows = int(self.limit_combo.currentData() or 0)
        shown = matched[:max_rows] if max_rows > 0 else matched

        vert_label = tr("xmlconv.screen.vertical", "Vertical")
        horiz_label = tr("xmlconv.screen.horizontal", "Horizontal")

        with paused_table_sorting(self.preview_table):
            self.preview_table.setRowCount(len(shown))
            for row_idx, entry in enumerate(shown):
                props = entry.get("properties") or {}
                is_vert = is_game_vertical({"xml_properties": props})
                rot = props.get("display_rotate") or props.get("rotate") or ""
                if is_vert:
                    scr_txt = f"{vert_label} ({rot}°)" if rot else vert_label
                else:
                    scr_txt = horiz_label if props.get("display_type") or rot else "—"

                rom_item = SortableTableWidgetItem(entry["rom_name"])
                rom_item.setData(Qt.UserRole, entry)
                year_str = entry["year"]
                year_key = int(year_str) if year_str.isdigit() else 999999
                bios_str = entry.get("bios") or props.get("bios", "")

                self.preview_table.setItem(row_idx, 0, rom_item)
                self.preview_table.setItem(row_idx, 1, SortableTableWidgetItem(entry["title"]))
                self.preview_table.setItem(row_idx, 2, SortableTableWidgetItem(year_str, sort_key=year_key))
                self.preview_table.setItem(row_idx, 3, SortableTableWidgetItem(entry["manufacturer"]))
                self.preview_table.setItem(row_idx, 4, SortableTableWidgetItem(entry["genre"]))
                self.preview_table.setItem(row_idx, 5, SortableTableWidgetItem(entry["players"]))
                self.preview_table.setItem(row_idx, 6, SortableTableWidgetItem(entry["cloneof"]))
                self.preview_table.setItem(row_idx, 7, SortableTableWidgetItem(bios_str))
                self.preview_table.setItem(row_idx, 8, SortableTableWidgetItem(entry["sourcefile"]))
                self.preview_table.setItem(row_idx, 9, SortableTableWidgetItem(scr_txt))

        cat_name = Path(self._loaded_catalog_path).name if self._loaded_catalog_path else ""
        self.preview_summary_lbl.setText(
            tr(
                "xmlconv.preview.summary",
                "📄 {name}  ·  Showing {shown:,} of {matched:,} matching ({total:,} total)  ·  ⚡ Loaded in {ms:.0f} ms",
                name=cat_name,
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

    # ------------------------------------------------------------------
    # VINCULACIÓN A LISTA
    # ------------------------------------------------------------------
    def _current_candidate_pncat(self) -> str:
        dst = self.dst_edit.text().strip()
        if dst and Path(dst).is_file() and is_fast_catalog_file(dst):
            return dst.replace("\\", "/")
        if self._loaded_catalog_path and Path(self._loaded_catalog_path).is_file():
            return self._loaded_catalog_path
        return ""

    def _update_link_button_state(self) -> None:
        has_cat = bool(self._current_candidate_pncat())
        has_list = self.target_list_combo.count() > 0 and self.target_list_combo.currentData() is not None
        running = self._worker is not None and self._worker.isRunning()
        self.link_btn.setEnabled(has_cat and has_list and not running)

    def _reveal_current_output(self) -> None:
        cand = self._current_candidate_pncat() or self.dst_edit.text().strip()
        if cand:
            _reveal_file_in_explorer(cand)

    def _link_catalog_to_selected_list(self) -> None:
        pncat_path = self._current_candidate_pncat()
        list_id = self.target_list_combo.currentData()
        if not pncat_path or not list_id:
            return

        row = self.db.get_list(list_id)
        if not row:
            return

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.db.update_list(list_id, xml_path=pncat_path)
            matched_txt = ""
            if self.apply_now_cb.isChecked():
                res = apply_xml_to_list(self.db, list_id, xml_path=pncat_path)
                sync_filtered_lists_for_source(self.db, list_id)
                matched_txt = tr(
                    "xmlconv.link.applied_counts",
                    "\n\nUpdated games in list: {matched:,} of {total:,}.",
                    matched=res.get("matched", 0),
                    total=res.get("total_games", 0),
                )
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self,
                tr("mw.xml.err_title", "XML Error"),
                tr("mw.xml.err_msg", "Could not link the XML file:\n{err}", err=exc),
            )
            return
        finally:
            while QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        self.refresh_lists(preferred_list_id=list_id)
        self.catalog_linked.emit(list_id)
        QMessageBox.information(
            self,
            tr("xmlconv.link.success_title", "Fast Catalog Linked"),
            tr(
                "xmlconv.link.success_msg",
                "Fast catalog '{cat}' is now linked to list '{name}'.{extra}",
                cat=Path(pncat_path).name,
                name=row["name"],
                extra=matched_txt,
            ),
        )

    def cleanup(self) -> None:
        self._search_timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1500)
