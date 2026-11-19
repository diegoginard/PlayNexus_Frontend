"""
Diálogos del Pro Toolkit de Rom Manager:
  - Auto-Trim de Wheels / Logos (Pillow o motor nativo Qt)
  - Normalizador de Videos Preview (ffmpeg opcional + selector portable)
  - Auditor 1G1R / Duplicados no destructivo
"""
from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import QLocale, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from playnexus.i18n import tr
from playnexus.services.rom_toolkit import (
    DEFAULT_1G1R_REGION_ORDER,
    DuplicateGroup,
    analyze_1g1r_duplicates,
    auto_trim_folder,
    create_filtered_1g1r_list,
    detect_toolkit_capabilities,
    move_duplicate_roms_to_folder,
    normalize_video_file,
    remove_duplicates_from_list,
    save_ffmpeg_path,
    scan_video_candidates,
    tag_1g1r_duplicates,
)
from playnexus.ui.table_utils import (
    SortableTableWidgetItem,
    configure_details_table,
    find_table_row_by_user_data,
    paused_table_sorting,
)


class _FlexibleMBSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox que acepta tanto punto como coma decimal sin tratar '.' como separador de miles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c_loc = QLocale.c()
        c_loc.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
        self.setLocale(c_loc)

    def validate(self, text: str, pos: int):
        return super().validate(text.replace(",", "."), pos)

    def valueFromText(self, text: str) -> float:
        return super().valueFromText(text.replace(",", "."))


class _AutoTrimWorker(QThread):
    progress = Signal(int, int, str, object)
    finished_summary = Signal(dict)

    def __init__(
        self,
        folder: str,
        margin: int,
        trim_mode: str,
        create_backup: bool,
        recursive: bool,
        dry_run: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.folder = folder
        self.margin = margin
        self.trim_mode = trim_mode
        self.create_backup = create_backup
        self.recursive = recursive
        self.dry_run = dry_run
        self._cancel = threading.Event()

    def request_cancel(self):
        self._cancel.set()

    def run(self):
        summary = auto_trim_folder(
            self.folder,
            margin=self.margin,
            trim_mode=self.trim_mode,
            create_backup=self.create_backup,
            recursive=self.recursive,
            dry_run=self.dry_run,
            progress_callback=lambda d, t, name, res: self.progress.emit(d, t, name, res),
            cancel_check=self._cancel.is_set,
        )
        self.finished_summary.emit(summary)


class _VideoScanWorker(QThread):
    progress = Signal(int, int, str)
    finished_scan = Signal(list, dict, float, int)

    def __init__(
        self,
        folder: str,
        max_size_mb: float,
        max_height: int,
        ffprobe_path: str,
        deep_probe_mp4: bool,
        recursive: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.folder = folder
        self.max_size_mb = max_size_mb
        self.max_height = max_height
        self.ffprobe_path = ffprobe_path
        self.deep_probe_mp4 = deep_probe_mp4
        self.recursive = recursive
        self._cancel = threading.Event()

    def request_cancel(self):
        self._cancel.set()

    def run(self):
        stats: dict = {}
        cands = scan_video_candidates(
            self.folder,
            max_size_mb=self.max_size_mb,
            max_height=self.max_height,
            ffprobe_path=self.ffprobe_path,
            deep_probe_mp4=self.deep_probe_mp4,
            recursive=self.recursive,
            progress_callback=lambda d, t, name: self.progress.emit(d, t, name),
            cancel_check=self._cancel.is_set,
            stats_out=stats,
        )
        self.finished_scan.emit(cands, stats, self.max_size_mb, self.max_height)


class _VideoNormalizeWorker(QThread):
    item_done = Signal(int, int, dict)
    finished_all = Signal(dict)

    def __init__(
        self,
        files: list[str],
        ffmpeg_path: str,
        target_height: int,
        crf: int,
        preset: str,
        strip_audio: bool,
        create_backup: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.files = list(files)
        self.ffmpeg_path = ffmpeg_path
        self.target_height = target_height
        self.crf = crf
        self.preset = preset
        self.strip_audio = strip_audio
        self.create_backup = create_backup
        self._cancel = threading.Event()

    def request_cancel(self):
        self._cancel.set()

    def run(self):
        total = len(self.files)
        normalized = 0
        errors = 0
        cancelled = False
        bytes_saved = 0

        for idx, fpath in enumerate(self.files, start=1):
            if self._cancel.is_set():
                cancelled = True
                break
            res = normalize_video_file(
                fpath,
                ffmpeg_path=self.ffmpeg_path,
                target_height=self.target_height,
                crf=self.crf,
                preset=self.preset,
                strip_audio=self.strip_audio,
                create_backup=self.create_backup,
                cancel_check=self._cancel.is_set,
            )
            st = res.get("status")
            if st == "normalized":
                normalized += 1
                bytes_saved += max(0, int(res.get("bytes_before", 0)) - int(res.get("bytes_after", 0)))
            elif st == "cancelled":
                cancelled = True
                self.item_done.emit(idx, total, res)
                break
            else:
                errors += 1
            self.item_done.emit(idx, total, res)

        self.finished_all.emit(
            {
                "total": total,
                "normalized": normalized,
                "errors": errors,
                "cancelled": cancelled,
                "bytes_saved": bytes_saved,
            }
        )


class RomToolkitDialog(QDialog):
    """Ventana modal unificada de Pro Toolkit para optimización de media y auditoría 1G1R."""

    media_mutated = Signal()
    library_mutated = Signal()

    def __init__(self, db, list_row: dict, games: list[dict], parent=None):
        super().__init__(parent)
        self.db = db
        self.list_row = dict(list_row or {})
        self.games = [dict(g) for g in (games or [])]
        self._trim_worker: _AutoTrimWorker | None = None
        self._video_scan_worker: _VideoScanWorker | None = None
        self._video_worker: _VideoNormalizeWorker | None = None
        self._video_row_by_path: dict[str, int] = {}
        self._dup_analysis: dict = {}

        list_name = self.list_row.get("name") or tr("toolkit_dlg.default_list_name", "List")
        self.setWindowTitle(tr("toolkit_dlg.window_title", "Rom Manager Pro Toolkit — {name}", name=list_name))
        self.resize(1020, 740)
        self.setMinimumSize(860, 620)

        self._build_ui()
        self._refresh_capabilities_banner()

    def _stop_all_workers(self):
        for w in (self._trim_worker, self._video_scan_worker, self._video_worker):
            if w and w.isRunning():
                w.request_cancel()
                w.wait(2000)

    def done(self, result: int):
        self._stop_all_workers()
        super().done(result)

    def closeEvent(self, event):
        self._stop_all_workers()
        super().closeEvent(event)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Banner de estado de capacidades opcionales
        self.cap_frame = QFrame()
        self.cap_frame.setStyleSheet(
            "QFrame { background-color: #161b29; border: 1px solid #2e3852; border-radius: 8px; }"
        )
        cap_lay = QHBoxLayout(self.cap_frame)
        cap_lay.setContentsMargins(12, 8, 12, 8)
        cap_lay.setSpacing(10)

        self.cap_lbl = QLabel()
        self.cap_lbl.setWordWrap(True)
        self.cap_lbl.setStyleSheet("color: #e2e8f0; border: none; font-size: 9pt;")
        cap_lay.addWidget(self.cap_lbl, 1)

        self.btn_pick_ffmpeg = QPushButton(tr("toolkit_dlg.btn_pick_ffmpeg", "📁 Locate ffmpeg.exe…"))
        self.btn_pick_ffmpeg.setToolTip(tr("toolkit_dlg.tip_pick_ffmpeg", "Select portable ffmpeg binary (optional)"))
        self.btn_pick_ffmpeg.clicked.connect(self._pick_ffmpeg_executable)
        cap_lay.addWidget(self.btn_pick_ffmpeg)

        root.addWidget(self.cap_frame)

        # Pestañas
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_autotrim_tab(), tr("toolkit_dlg.tab_autotrim", "✂ Auto-Trim Wheels / Logos"))
        self.tabs.addTab(self._build_video_tab(), tr("toolkit_dlg.tab_video", "🎞 Normalize Videos (ffmpeg)"))
        self.tabs.addTab(self._build_1g1r_tab(), tr("toolkit_dlg.tab_1g1r", "🧬 1G1R / Duplicates Auditor"))
        root.addWidget(self.tabs, 1)

        # Pie
        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_close = QPushButton(tr("toolkit_dlg.btn_close", "Close"))
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)
        root.addLayout(footer)

    def _refresh_capabilities_banner(self):
        caps = detect_toolkit_capabilities(self.db)
        self._caps = caps
        pil_badge = (
            tr("toolkit_dlg.cap_pillow_active", "Pillow: ✅ Active")
            if caps["pillow_available"]
            else tr("toolkit_dlg.cap_pillow_qt", "Pillow: ⚡ Native Qt Engine (RGBA8888)")
        )
        ff_badge = (
            tr("toolkit_dlg.cap_ffmpeg_ready", "ffmpeg: ✅ Ready ({name})", name=Path(caps["ffmpeg_path"]).name)
            if caps["ffmpeg_available"]
            else tr("toolkit_dlg.cap_ffmpeg_missing", "ffmpeg: ⚠ Not detected")
        )
        pdf_badge = (
            tr("toolkit_dlg.cap_qtpdf_active", "QtPdf: ✅ Active")
            if caps["qtpdf_available"]
            else tr("toolkit_dlg.cap_qtpdf_fallback", "QtPdf: ⚠ External viewer fallback")
        )

        lines = [
            tr(
                "toolkit_dlg.cap_header",
                "<b>Toolkit Capabilities:</b> &nbsp; {pil} &nbsp;·&nbsp; {ff} &nbsp;·&nbsp; {pdf}",
                pil=pil_badge,
                ff=ff_badge,
                pdf=pdf_badge,
            )
        ]
        if not caps["ffmpeg_available"]:
            lines.append(
                tr(
                    "toolkit_dlg.cap_ffmpeg_hint",
                    "<span style='color:#fbbf24;'>To normalize videos, place <code>ffmpeg.exe</code> in "
                    "<code>tools/ffmpeg/</code> or select it using 'Locate ffmpeg.exe…'.</span>",
                )
            )
        self.cap_lbl.setText("<br>".join(lines))

        if hasattr(self, "btn_video_normalize"):
            self.btn_video_normalize.setEnabled(bool(caps["ffmpeg_available"]) and self.video_table.rowCount() > 0)
        if hasattr(self, "video_ffmpeg_notice"):
            self.video_ffmpeg_notice.setVisible(not caps["ffmpeg_available"])

    def _pick_ffmpeg_executable(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("toolkit_dlg.pick_ffmpeg_title", "Select ffmpeg executable"),
            "",
            tr("toolkit_dlg.pick_ffmpeg_filter", "ffmpeg executable (ffmpeg.exe ffmpeg);;All files (*.*)"),
        )
        if not path:
            return
        saved = save_ffmpeg_path(self.db, path)
        self._refresh_capabilities_banner()
        if detect_toolkit_capabilities(self.db)["ffmpeg_available"]:
            QMessageBox.information(
                self,
                tr("toolkit_dlg.ffmpeg_ok_title", "ffmpeg Configured"),
                tr("toolkit_dlg.ffmpeg_ok_msg", "Successfully linked:\n{path}", path=saved),
            )
        else:
            QMessageBox.warning(
                self,
                tr("toolkit_dlg.ffmpeg_bad_title", "Invalid Path"),
                tr("toolkit_dlg.ffmpeg_bad_msg", "No valid ffmpeg executable found at:\n{path}", path=saved),
            )

    # ------------------------------------------------------------------
    # TAB 1: AUTO-TRIM WHEELS / LOGOS
    # ------------------------------------------------------------------
    def _build_autotrim_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        cfg_group = QGroupBox(tr("toolkit_dlg.trim_cfg_group", "Folder and Auto-Trim Parameters"))
        form = QFormLayout(cfg_group)
        form.setSpacing(8)

        folder_row = QHBoxLayout()
        self.trim_folder_combo = QComboBox()
        self.trim_folder_combo.setEditable(True)
        image_slots = [
            ("wheel_path", tr("toolkit_dlg.slot_wheels", "Wheels / Logos")),
            ("boxart_path", "Boxart"),
            ("cartart_path", tr("toolkit_dlg.slot_cartart", "Cartart / Disc")),
            ("marquee_path", "Marquee"),
            ("flyer_path", "Flyer"),
            ("cabinet_path", "Cabinet"),
            ("snap_path", "Snap"),
            ("title_path", "Title"),
            ("fanart_path", "Fanart"),
        ]
        for key, label in image_slots:
            val = str(self.list_row.get(key) or "").strip()
            if val and Path(val).is_dir():
                self.trim_folder_combo.addItem(f"{label}: {val}", val)
        if self.trim_folder_combo.count() == 0:
            self.trim_folder_combo.setEditText("")
        btn_trim_browse = QPushButton(tr("toolkit_dlg.btn_browse", "Browse…"))
        btn_trim_browse.clicked.connect(self._browse_trim_folder)
        folder_row.addWidget(self.trim_folder_combo, 1)
        folder_row.addWidget(btn_trim_browse)
        form.addRow(tr("toolkit_dlg.trim_folder_label", "Image Folder:"), folder_row)

        opts_row = QHBoxLayout()
        self.trim_mode_combo = QComboBox()
        self.trim_mode_combo.addItem(
            tr("toolkit_dlg.trim_mode_auto", "Automatic (Alpha if transparent, else Black)"), "auto"
        )
        self.trim_mode_combo.addItem(
            tr("toolkit_dlg.trim_mode_alpha_only", "Transparent border only (Alpha)"), "alpha_only"
        )
        self.trim_mode_combo.addItem(
            tr("toolkit_dlg.trim_mode_alpha_black", "Transparent + black borders"), "alpha_black"
        )
        self.trim_mode_combo.addItem(
            tr("toolkit_dlg.trim_mode_black_only", "Black borders only"), "black_only"
        )

        self.trim_margin_spin = QSpinBox()
        self.trim_margin_spin.setRange(0, 32)
        self.trim_margin_spin.setValue(4)
        self.trim_margin_spin.setSuffix(" px")

        self.trim_recursive_cb = QCheckBox(tr("toolkit_dlg.include_subfolders", "Include subfolders"))
        self.trim_backup_cb = QCheckBox(tr("toolkit_dlg.trim_backup_cb", "Keep backup (.bak)"))
        self.trim_backup_cb.setChecked(True)

        opts_row.addWidget(QLabel(tr("toolkit_dlg.trim_mode_label", "Mode:")))
        opts_row.addWidget(self.trim_mode_combo, 1)
        opts_row.addSpacing(10)
        opts_row.addWidget(QLabel(tr("toolkit_dlg.trim_margin_label", "Margin:")))
        opts_row.addWidget(self.trim_margin_spin)
        opts_row.addSpacing(10)
        opts_row.addWidget(self.trim_recursive_cb)
        opts_row.addWidget(self.trim_backup_cb)
        form.addRow(tr("toolkit_dlg.options_label", "Options:"), opts_row)

        lay.addWidget(cfg_group)

        actions_row = QHBoxLayout()
        self.btn_trim_dry = QPushButton(tr("toolkit_dlg.btn_trim_dry", "🔍 Dry Run (Preview)"))
        self.btn_trim_dry.clicked.connect(lambda: self._start_autotrim(dry_run=True))
        self.btn_trim_run = QPushButton(tr("toolkit_dlg.btn_trim_run", "✂ Run Actual Auto-Trim"))
        self.btn_trim_run.setStyleSheet("font-weight: 700;")
        self.btn_trim_run.clicked.connect(lambda: self._start_autotrim(dry_run=False))
        self.btn_trim_cancel = QPushButton(tr("toolkit_dlg.btn_cancel", "⏹ Cancel"))
        self.btn_trim_cancel.setEnabled(False)
        self.btn_trim_cancel.clicked.connect(self._cancel_autotrim)

        actions_row.addWidget(self.btn_trim_dry)
        actions_row.addWidget(self.btn_trim_run)
        actions_row.addWidget(self.btn_trim_cancel)
        actions_row.addStretch()
        lay.addLayout(actions_row)

        self.trim_progress = QProgressBar()
        self.trim_progress.setVisible(False)
        lay.addWidget(self.trim_progress)

        self.trim_summary_lbl = QLabel(
            tr("toolkit_dlg.trim_ready_summary", "Select a folder (e.g., Wheels) and run a dry run or actual trim.")
        )
        self.trim_summary_lbl.setStyleSheet("color: #93c5fd; font-weight: 600;")
        lay.addWidget(self.trim_summary_lbl)

        self.trim_table = QTableWidget(0, 4)
        self.trim_table.setHorizontalHeaderLabels(
            [
                tr("toolkit_dlg.col_file", "File"),
                tr("toolkit_dlg.col_status", "Status"),
                tr("toolkit_dlg.col_resolution", "Resolution"),
                tr("toolkit_dlg.col_detail", "Detail"),
            ]
        )
        configure_details_table(
            self.trim_table,
            col_widths=(260, 110, 160, 260),
        )
        lay.addWidget(self.trim_table, 1)

        return w

    def _current_trim_folder(self) -> str:
        idx = self.trim_folder_combo.currentIndex()
        data = self.trim_folder_combo.itemData(idx)
        txt = self.trim_folder_combo.currentText().strip()
        if data and txt == self.trim_folder_combo.itemText(idx):
            return str(data)
        return txt

    def _browse_trim_folder(self):
        d = QFileDialog.getExistingDirectory(
            self,
            tr("toolkit_dlg.browse_trim_title", "Select Wheels / Logos Folder"),
            self._current_trim_folder(),
        )
        if d:
            self.trim_folder_combo.setEditText(d)

    def _start_autotrim(self, dry_run: bool):
        folder = self._current_trim_folder()
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(
                self,
                tr("toolkit_dlg.invalid_folder_title", "Invalid Folder"),
                tr("toolkit_dlg.trim_invalid_folder_msg", "Select an existing image folder."),
            )
            return
        if self._trim_worker and self._trim_worker.isRunning():
            return

        self.trim_table.setSortingEnabled(False)
        self.trim_table.setRowCount(0)
        self.trim_progress.setValue(0)
        self.trim_progress.setVisible(True)
        self.btn_trim_dry.setEnabled(False)
        self.btn_trim_run.setEnabled(False)
        self.btn_trim_cancel.setEnabled(True)

        self._trim_worker = _AutoTrimWorker(
            folder=folder,
            margin=self.trim_margin_spin.value(),
            trim_mode=self.trim_mode_combo.currentData(),
            create_backup=self.trim_backup_cb.isChecked(),
            recursive=self.trim_recursive_cb.isChecked(),
            dry_run=dry_run,
            parent=self,
        )
        self._trim_worker.progress.connect(self._on_trim_progress)
        self._trim_worker.finished_summary.connect(lambda s: self._on_trim_finished(s, dry_run))
        self._trim_worker.start()

    def _cancel_autotrim(self):
        if self._trim_worker and self._trim_worker.isRunning():
            self._trim_worker.request_cancel()

    def _on_trim_progress(self, done: int, total: int, fname: str, res):
        self.trim_progress.setMaximum(max(1, total))
        self.trim_progress.setValue(done)
        if res.status in ("trimmed", "error"):
            with paused_table_sorting(self.trim_table, disable_updates=False):
                r = self.trim_table.rowCount()
                self.trim_table.insertRow(r)
                self.trim_table.setItem(r, 0, SortableTableWidgetItem(fname))
                st_lbl = (
                    tr("toolkit_dlg.trim_status_trimmed", "Trimmed")
                    if res.status == "trimmed"
                    else tr("toolkit_dlg.status_error", "Error")
                )
                self.trim_table.setItem(r, 1, SortableTableWidgetItem(st_lbl))
                res_txt = f"{res.orig_size[0]}x{res.orig_size[1]} → {res.new_size[0]}x{res.new_size[1]}"
                area_key = int(res.orig_size[0]) * int(res.orig_size[1])
                self.trim_table.setItem(r, 2, SortableTableWidgetItem(res_txt, sort_key=area_key))
                self.trim_table.setItem(r, 3, SortableTableWidgetItem(res.message))

    def _on_trim_finished(self, summary: dict, dry_run: bool):
        self.trim_table.setSortingEnabled(True)
        self.btn_trim_dry.setEnabled(True)
        self.btn_trim_run.setEnabled(True)
        self.btn_trim_cancel.setEnabled(False)
        mode_lbl = (
            tr("toolkit_dlg.trim_mode_dry_done", "Dry Run")
            if dry_run
            else tr("toolkit_dlg.trim_mode_real_done", "Auto-Trim completed")
        )
        kb_saved = summary.get("saved_bytes", 0) / 1024.0
        extra = tr("toolkit_dlg.cancelled_suffix", " (cancelled)") if summary.get("cancelled") else ""
        saved_txt = "" if dry_run else tr("toolkit_dlg.trim_saved_kb", " · {kb:.1f} KB saved", kb=kb_saved)
        self.trim_summary_lbl.setText(
            tr(
                "toolkit_dlg.trim_finished_summary",
                "{mode}{extra}: {processed} checked · {trimmed} trimmable/trimmed · "
                "{skipped} unchanged · {errors} errors{saved}",
                mode=mode_lbl,
                extra=extra,
                processed=summary.get("processed", 0),
                trimmed=summary.get("trimmed", 0),
                skipped=summary.get("skipped", 0),
                errors=summary.get("errors", 0),
                saved=saved_txt,
            )
        )
        if not dry_run and summary.get("trimmed", 0) > 0:
            self.media_mutated.emit()

    # ------------------------------------------------------------------
    # TAB 2: NORMALIZADOR DE VIDEOS PREVIEW (ffmpeg)
    # ------------------------------------------------------------------
    def _build_video_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        self.video_ffmpeg_notice = QLabel(
            tr(
                "toolkit_dlg.video_ffmpeg_notice",
                "⚠ <b>ffmpeg not detected:</b> You can still scan the folder's videos, "
                "but you need to specify <code>ffmpeg.exe</code> (top button 'Locate ffmpeg.exe…') "
                "to transcode to H.264/AAC MP4.",
            )
        )
        self.video_ffmpeg_notice.setWordWrap(True)
        self.video_ffmpeg_notice.setStyleSheet(
            "background-color: #2c2112; color: #fde68a; border: 1px solid #b45309; border-radius: 6px; padding: 8px;"
        )
        lay.addWidget(self.video_ffmpeg_notice)

        cfg = QGroupBox(tr("toolkit_dlg.video_cfg_group", "Folder and MP4 Normalization Profile (+faststart)"))
        form = QFormLayout(cfg)

        list_name = str(self.list_row.get("name") or tr("toolkit_dlg.no_list", "No list")).strip()
        default_vdir = str(self.list_row.get("video_path") or "").strip()
        self.video_list_lbl = QLabel(tr("toolkit_dlg.video_active_list", "<b>Active list:</b> {name}", name=list_name))
        self.video_list_lbl.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        form.addRow(tr("toolkit_dlg.video_source_label", "Source:"), self.video_list_lbl)

        vfolder_row = QHBoxLayout()
        self.video_folder_edit = QLineEdit(default_vdir)
        self.video_folder_edit.setToolTip(
            default_vdir or tr("toolkit_dlg.video_folder_tip", "Path of the videos folder to analyze")
        )
        self.video_folder_edit.textChanged.connect(lambda t: self.video_folder_edit.setToolTip(t.strip()))
        btn_vbrowse = QPushButton(tr("toolkit_dlg.btn_browse", "Browse…"))
        btn_vbrowse.clicked.connect(self._browse_video_folder)
        vfolder_row.addWidget(self.video_folder_edit, 1)
        vfolder_row.addWidget(btn_vbrowse)
        form.addRow(tr("toolkit_dlg.video_folder_label", "Videos Folder:"), vfolder_row)

        vopts_row = QHBoxLayout()
        self.video_res_combo = QComboBox()
        self.video_res_combo.addItem(tr("toolkit_dlg.video_res_480", "480p (Lightweight Arcade)"), 480)
        self.video_res_combo.addItem(tr("toolkit_dlg.video_res_720", "720p (High Quality)"), 720)

        self.video_max_mb_spin = _FlexibleMBSpinBox()
        self.video_max_mb_spin.setDecimals(1)
        self.video_max_mb_spin.setSingleStep(1.0)
        self.video_max_mb_spin.setRange(1.0, 500.0)
        self.video_max_mb_spin.setValue(15.0)
        self.video_max_mb_spin.setSuffix(" MB")

        self.video_crf_spin = QSpinBox()
        self.video_crf_spin.setRange(18, 30)
        self.video_crf_spin.setValue(24)

        self.video_strip_audio_cb = QCheckBox(tr("toolkit_dlg.video_strip_audio_cb", "Strip audio (-an)"))
        self.video_backup_cb = QCheckBox(tr("toolkit_dlg.video_backup_cb", "Backup (.bak)"))
        self.video_backup_cb.setChecked(True)

        vopts_row.addWidget(QLabel(tr("toolkit_dlg.video_max_label", "Max:")))
        vopts_row.addWidget(self.video_res_combo)
        vopts_row.addWidget(QLabel(tr("toolkit_dlg.video_reencode_label", "Re-encode if >")))
        vopts_row.addWidget(self.video_max_mb_spin)
        vopts_row.addWidget(QLabel("CRF:"))
        vopts_row.addWidget(self.video_crf_spin)
        vopts_row.addWidget(self.video_strip_audio_cb)
        vopts_row.addWidget(self.video_backup_cb)
        form.addRow(tr("toolkit_dlg.video_profile_label", "H.264 Profile:"), vopts_row)

        vscan_opts_row = QHBoxLayout()
        self.video_recursive_cb = QCheckBox(tr("toolkit_dlg.include_subfolders", "Include subfolders"))
        self.video_deep_probe_cb = QCheckBox(
            tr("toolkit_dlg.video_deep_probe_cb", "Analyze resolution/codec on all .mp4 files (ffprobe)")
        )
        self.video_deep_probe_cb.setToolTip(
            tr(
                "toolkit_dlg.video_deep_probe_tip",
                "Inspects with ffprobe even .mp4 files under the size limit (useful to detect 720p/1080p or non-H.264 codecs).",
            )
        )
        vscan_opts_row.addWidget(self.video_recursive_cb)
        vscan_opts_row.addSpacing(12)
        vscan_opts_row.addWidget(self.video_deep_probe_cb)
        vscan_opts_row.addStretch()
        form.addRow(tr("toolkit_dlg.video_scan_scope_label", "Scan scope:"), vscan_opts_row)
        lay.addWidget(cfg)

        vact = QHBoxLayout()
        self.btn_video_scan = QPushButton(tr("toolkit_dlg.btn_video_scan", "🔍 Scan Videos"))
        self.btn_video_scan.clicked.connect(self._scan_videos)
        self.btn_video_normalize = QPushButton(tr("toolkit_dlg.btn_video_normalize", "🎞 Normalize List with ffmpeg"))
        self.btn_video_normalize.setEnabled(False)
        self.btn_video_normalize.clicked.connect(self._start_video_normalize)
        self.btn_video_cancel = QPushButton(tr("toolkit_dlg.btn_cancel", "⏹ Cancel"))
        self.btn_video_cancel.setEnabled(False)
        self.btn_video_cancel.clicked.connect(self._cancel_video_action)

        vact.addWidget(self.btn_video_scan)
        vact.addWidget(self.btn_video_normalize)
        vact.addWidget(self.btn_video_cancel)
        vact.addStretch()
        lay.addLayout(vact)

        self.video_progress = QProgressBar()
        self.video_progress.setVisible(False)
        lay.addWidget(self.video_progress)

        self.video_summary_lbl = QLabel(
            tr(
                "toolkit_dlg.video_ready_summary",
                "Scan the videos folder to detect legacy formats or oversized files.",
            )
        )
        self.video_summary_lbl.setStyleSheet("color: #93c5fd; font-weight: 600;")
        lay.addWidget(self.video_summary_lbl)

        self.video_table = QTableWidget(0, 4)
        self.video_table.setHorizontalHeaderLabels(
            [
                tr("toolkit_dlg.col_file", "File"),
                tr("toolkit_dlg.col_size", "Size"),
                tr("toolkit_dlg.col_reason", "Reason"),
                tr("toolkit_dlg.col_status", "Status"),
            ]
        )
        configure_details_table(
            self.video_table,
            col_widths=(290, 95, 320, 140),
        )
        lay.addWidget(self.video_table, 1)

        return w

    def _browse_video_folder(self):
        d = QFileDialog.getExistingDirectory(
            self,
            tr("toolkit_dlg.browse_video_title", "Select Videos Folder"),
            self.video_folder_edit.text().strip(),
        )
        if d:
            self.video_folder_edit.setText(d)

    def _scan_videos(self):
        folder = self.video_folder_edit.text().strip()
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(
                self,
                tr("toolkit_dlg.invalid_folder_title", "Invalid Folder"),
                tr("toolkit_dlg.video_invalid_folder_msg", "Specify a valid videos folder."),
            )
            return
        if (self._video_scan_worker and self._video_scan_worker.isRunning()) or (
            self._video_worker and self._video_worker.isRunning()
        ):
            return

        self.video_max_mb_spin.interpretText()
        self.video_crf_spin.interpretText()
        max_mb = float(self.video_max_mb_spin.value())
        max_h = int(self.video_res_combo.currentData() or 480)
        caps = detect_toolkit_capabilities(self.db)

        self.video_table.setRowCount(0)
        self._video_row_by_path.clear()
        self.video_progress.setMaximum(0)
        self.video_progress.setValue(0)
        self.video_progress.setVisible(True)
        self.btn_video_scan.setEnabled(False)
        self.btn_video_normalize.setEnabled(False)
        self.btn_video_cancel.setEnabled(True)
        self.video_summary_lbl.setText(
            tr(
                "toolkit_dlg.video_scanning_start",
                "Scanning {folder} (>{max_mb:g} MB / max {max_h}p)…",
                folder=folder,
                max_mb=max_mb,
                max_h=max_h,
            )
        )

        self._video_scan_worker = _VideoScanWorker(
            folder=folder,
            max_size_mb=max_mb,
            max_height=max_h,
            ffprobe_path=caps.get("ffprobe_path", ""),
            deep_probe_mp4=self.video_deep_probe_cb.isChecked(),
            recursive=self.video_recursive_cb.isChecked(),
            parent=self,
        )
        self._video_scan_worker.progress.connect(self._on_video_scan_progress)
        self._video_scan_worker.finished_scan.connect(self._on_video_scan_finished)
        self._video_scan_worker.start()

    def _on_video_scan_progress(self, done: int, total: int, fname: str):
        self.video_progress.setMaximum(max(1, total))
        self.video_progress.setValue(done)
        self.video_summary_lbl.setText(
            tr("toolkit_dlg.video_scanning_progress", "Scanning videos ({done}/{total}): {fname}", done=done, total=total, fname=fname)
        )

    def _on_video_scan_finished(self, cands: list, stats: dict, max_mb: float, max_h: int):
        self.btn_video_scan.setEnabled(True)
        self.btn_video_cancel.setEnabled(False)
        self.video_progress.setVisible(False)

        with paused_table_sorting(self.video_table, reenable=True):
            self.video_table.setRowCount(len(cands))
            self._video_row_by_path.clear()
            for r, cand in enumerate(cands):
                item_name = SortableTableWidgetItem(cand.filename)
                item_name.setData(Qt.UserRole, cand.file_path)
                self.video_table.setItem(r, 0, item_name)
                mb = cand.size_bytes / (1024.0 * 1024.0)
                self.video_table.setItem(r, 1, SortableTableWidgetItem(f"{mb:.2f} MB", sort_key=int(cand.size_bytes)))
                self.video_table.setItem(r, 2, SortableTableWidgetItem(" · ".join(cand.reasons)))
                self.video_table.setItem(r, 3, SortableTableWidgetItem(tr("toolkit_dlg.video_status_pending", "Pending")))
                self._video_row_by_path[cand.file_path] = r

        caps = detect_toolkit_capabilities(self.db)
        scanned_n = int(stats.get("scanned_files", len(cands)))
        probed_n = int(stats.get("probed_files", 0))
        extra = tr("toolkit_dlg.cancelled_suffix", " (cancelled)") if stats.get("cancelled") else ""
        probe_txt = f" · ffprobe: {probed_n}" if probed_n else ""
        self.video_summary_lbl.setText(
            tr(
                "toolkit_dlg.video_scan_done",
                "Scan finished{extra}: {scanned} video(s) checked{probe} · "
                "{cands} candidate(s) (filter: > {max_mb:g} MB or > {max_h}p / non-MP4)",
                extra=extra,
                scanned=scanned_n,
                probe=probe_txt,
                cands=len(cands),
                max_mb=max_mb,
                max_h=max_h,
            )
        )
        self.btn_video_normalize.setEnabled(bool(caps["ffmpeg_available"]) and len(cands) > 0)

    def _start_video_normalize(self):
        caps = detect_toolkit_capabilities(self.db)
        if not caps["ffmpeg_available"]:
            QMessageBox.warning(
                self,
                tr("toolkit_dlg.ffmpeg_missing_title", "Missing ffmpeg"),
                tr("toolkit_dlg.ffmpeg_missing_msg", "Configure the ffmpeg.exe path first."),
            )
            return
        if (self._video_worker and self._video_worker.isRunning()) or (
            self._video_scan_worker and self._video_scan_worker.isRunning()
        ):
            return

        files: list[str] = []
        for r in range(self.video_table.rowCount()):
            st_item = self.video_table.item(r, 3)
            if st_item and st_item.text().startswith("✅"):
                continue
            p = self.video_table.item(r, 0).data(Qt.UserRole)
            if p:
                files.append(str(p))
        if not files:
            QMessageBox.information(
                self,
                tr("toolkit_dlg.no_pending_videos_title", "No Pending Videos"),
                tr(
                    "toolkit_dlg.no_pending_videos_msg",
                    "All videos in the list have already been normalized. Scan again if you want to recheck.",
                ),
            )
            return

        self.video_crf_spin.interpretText()
        self.video_table.setSortingEnabled(False)
        self.video_progress.setMaximum(len(files))
        self.video_progress.setValue(0)
        self.video_progress.setVisible(True)
        self.btn_video_scan.setEnabled(False)
        self.btn_video_normalize.setEnabled(False)
        self.btn_video_cancel.setEnabled(True)

        self._video_worker = _VideoNormalizeWorker(
            files=files,
            ffmpeg_path=caps["ffmpeg_path"],
            target_height=int(self.video_res_combo.currentData() or 480),
            crf=self.video_crf_spin.value(),
            preset="veryfast",
            strip_audio=self.video_strip_audio_cb.isChecked(),
            create_backup=self.video_backup_cb.isChecked(),
            parent=self,
        )
        self._video_worker.item_done.connect(self._on_video_item_done)
        self._video_worker.finished_all.connect(self._on_video_finished)
        self._video_worker.start()

    def _cancel_video_action(self):
        if self._video_scan_worker and self._video_scan_worker.isRunning():
            self._video_scan_worker.request_cancel()
        if self._video_worker and self._video_worker.isRunning():
            self._video_worker.request_cancel()

    def _on_video_item_done(self, idx: int, total: int, res: dict):
        self.video_progress.setValue(idx)
        src = str(res.get("src") or "")
        row = find_table_row_by_user_data(self.video_table, src, col=0)
        if row < 0:
            row = self._video_row_by_path.get(src, idx - 1)
        if 0 <= row < self.video_table.rowCount():
            st = res.get("status", "error")
            lbl = (
                tr("toolkit_dlg.video_status_normalized", "✅ Normalized")
                if st == "normalized"
                else (
                    tr("toolkit_dlg.video_status_cancelled", "⏹ Cancelled")
                    if st == "cancelled"
                    else f"❌ {res.get('message', tr('toolkit_dlg.status_error', 'Error'))}"
                )
            )
            self.video_table.setItem(row, 3, SortableTableWidgetItem(lbl))

    def _on_video_finished(self, summary: dict):
        self.video_table.setSortingEnabled(True)
        self.btn_video_scan.setEnabled(True)
        caps = detect_toolkit_capabilities(self.db)
        has_pending = any(
            not (self.video_table.item(r, 3) and self.video_table.item(r, 3).text().startswith("✅"))
            for r in range(self.video_table.rowCount())
        )
        self.btn_video_normalize.setEnabled(bool(caps["ffmpeg_available"]) and has_pending)
        self.btn_video_cancel.setEnabled(False)
        saved_mb = summary.get("bytes_saved", 0) / (1024.0 * 1024.0)
        extra = tr("toolkit_dlg.cancelled_suffix", " (cancelled)") if summary.get("cancelled") else ""
        self.video_summary_lbl.setText(
            tr(
                "toolkit_dlg.video_norm_done",
                "Normalization finished{extra}: {normalized}/{total} converted · "
                "{errors} errors · {saved_mb:.1f} MB saved",
                extra=extra,
                normalized=summary.get("normalized", 0),
                total=summary.get("total", 0),
                errors=summary.get("errors", 0),
                saved_mb=saved_mb,
            )
        )
        if summary.get("normalized", 0) > 0:
            self.media_mutated.emit()

    # ------------------------------------------------------------------
    # TAB 3: AUDITOR 1G1R / DUPLICADOS
    # ------------------------------------------------------------------
    def _build_1g1r_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        cfg = QGroupBox(
            tr(
                "toolkit_dlg.g1r_cfg_group",
                "1G1R Rules (1 Game 1 ROM) — Region Priority and Multi-Disc Protection",
            )
        )
        form = QFormLayout(cfg)

        reg_row = QHBoxLayout()
        self.region_order_edit = QLineEdit(", ".join(DEFAULT_1G1R_REGION_ORDER))
        self.region_order_edit.setToolTip(
            tr("toolkit_dlg.region_order_tip", "Comma-separated priority order (highest to lowest preference)")
        )
        btn_us = QPushButton(tr("toolkit_dlg.preset_usa", "USA Preset"))
        btn_us.clicked.connect(lambda: self.region_order_edit.setText(", ".join(DEFAULT_1G1R_REGION_ORDER)))
        btn_eu = QPushButton(tr("toolkit_dlg.preset_eu", "Europe/ESP Preset"))
        btn_eu.clicked.connect(
            lambda: self.region_order_edit.setText("Spain, Europe, World, USA, Japan, Korea, Asia, Brazil, France, Germany, Italy, Unknown")
        )
        btn_jp = QPushButton(tr("toolkit_dlg.preset_jp", "Japan Preset"))
        btn_jp.clicked.connect(
            lambda: self.region_order_edit.setText("Japan, World, USA, Europe, Spain, Korea, Asia, Brazil, France, Germany, Italy, Unknown")
        )
        reg_row.addWidget(self.region_order_edit, 1)
        reg_row.addWidget(btn_us)
        reg_row.addWidget(btn_eu)
        reg_row.addWidget(btn_jp)
        form.addRow(tr("toolkit_dlg.region_priority_label", "Region priority:"), reg_row)

        opts_1g1r = QHBoxLayout()
        self.dup_cloneof_cb = QCheckBox(
            tr("toolkit_dlg.dup_cloneof_cb", "Group MAME / XML clones (cloneof field)")
        )
        self.dup_cloneof_cb.setChecked(True)
        self.btn_dup_analyze = QPushButton(tr("toolkit_dlg.btn_dup_analyze", "🧬 Analyze 1G1R Duplicates"))
        self.btn_dup_analyze.setStyleSheet("font-weight: 700;")
        self.btn_dup_analyze.clicked.connect(self._run_1g1r_analysis)
        opts_1g1r.addWidget(self.dup_cloneof_cb)
        opts_1g1r.addStretch()
        opts_1g1r.addWidget(self.btn_dup_analyze)
        form.addRow("", opts_1g1r)

        lay.addWidget(cfg)

        self.dup_summary_lbl = QLabel(
            tr(
                "toolkit_dlg.dup_ready_summary",
                "Games loaded in list: {count}. Multi-disc games (Disc 1 / Disc 2) are never merged.",
                count=len(self.games),
            )
        )
        self.dup_summary_lbl.setStyleSheet("color: #93c5fd; font-weight: 600;")
        lay.addWidget(self.dup_summary_lbl)

        self.dup_table = QTableWidget(0, 4)
        self.dup_table.setHorizontalHeaderLabels(
            [
                tr("toolkit_dlg.col_dup_group", "Group / Game"),
                tr("toolkit_dlg.col_dup_winner", "Winner (1G1R)"),
                tr("toolkit_dlg.col_dup_item", "Duplicate to manage"),
                tr("toolkit_dlg.col_dup_reason", "Action / Reason"),
            ]
        )
        configure_details_table(
            self.dup_table,
            col_widths=(200, 260, 260, 200),
        )
        lay.addWidget(self.dup_table, 1)

        act_bar = QHBoxLayout()
        self.btn_dup_tag = QPushButton(tr("toolkit_dlg.btn_dup_tag", "🏷 Tag as 'duplicate'"))
        self.btn_dup_tag.setToolTip(
            tr("toolkit_dlg.tip_dup_tag", "Adds the 'duplicate' tag to duplicates without deleting or moving ROMs")
        )
        self.btn_dup_tag.clicked.connect(lambda: self._apply_dup_tag(create_filtered=False))

        self.btn_dup_filter_list = QPushButton(
            tr("toolkit_dlg.btn_dup_filter_list", "⚡ Tag + Create Filtered 1G1R List")
        )
        self.btn_dup_filter_list.setToolTip(
            tr("toolkit_dlg.tip_dup_filter_list", "Tags duplicates and creates a filtered list hiding them")
        )
        self.btn_dup_filter_list.clicked.connect(lambda: self._apply_dup_tag(create_filtered=True))

        self.btn_dup_remove = QPushButton(
            tr("toolkit_dlg.btn_dup_remove", "🧹 Remove from this List (keeps ROM)")
        )
        self.btn_dup_remove.clicked.connect(self._remove_dups_from_list)

        self.btn_dup_move = QPushButton(tr("toolkit_dlg.btn_dup_move", "📦 Move ROMs to _duplicates/…"))
        self.btn_dup_move.clicked.connect(self._move_dups_to_folder)

        for b in (self.btn_dup_tag, self.btn_dup_filter_list, self.btn_dup_remove, self.btn_dup_move):
            b.setEnabled(False)
            act_bar.addWidget(b)
        lay.addLayout(act_bar)

        return w

    def _parse_region_order(self) -> list[str]:
        parts = [p.strip() for p in self.region_order_edit.text().split(",") if p.strip()]
        return parts or list(DEFAULT_1G1R_REGION_ORDER)

    def _run_1g1r_analysis(self):
        self._dup_analysis = analyze_1g1r_duplicates(
            self.games,
            region_order=self._parse_region_order(),
            group_by_cloneof=self.dup_cloneof_cb.isChecked(),
        )
        groups: list[DuplicateGroup] = self._dup_analysis.get("duplicate_groups") or []
        with paused_table_sorting(self.dup_table, reenable=True):
            self.dup_table.setRowCount(0)

            for gr in groups:
                winner_name = f"🏆 {gr.winner.get('title') or Path(str(gr.winner.get('rom_path') or '')).name} [{gr.winner_region}]"
                for dup in gr.duplicates:
                    r = self.dup_table.rowCount()
                    self.dup_table.insertRow(r)
                    self.dup_table.setItem(r, 0, SortableTableWidgetItem(gr.group_label))
                    self.dup_table.setItem(r, 1, SortableTableWidgetItem(winner_name))
                    dup_file = Path(str(dup.get("rom_path") or "")).name or str(dup.get("title") or "")
                    item_dup = SortableTableWidgetItem(f"{dup.get('title') or dup_file} ({dup_file})")
                    item_dup.setData(Qt.UserRole, dup)
                    self.dup_table.setItem(r, 2, item_dup)
                    why = (
                        tr("toolkit_dlg.dup_why_clone", "Clone of {parent}", parent=dup.get("cloneof"))
                        if dup.get("cloneof")
                        else tr("toolkit_dlg.dup_why_region", "Lower region/revision priority")
                    )
                    self.dup_table.setItem(r, 3, SortableTableWidgetItem(why))

        has_dups = bool(groups)
        for b in (self.btn_dup_tag, self.btn_dup_filter_list, self.btn_dup_remove, self.btn_dup_move):
            b.setEnabled(has_dups)

        self.dup_summary_lbl.setText(
            tr(
                "toolkit_dlg.dup_analysis_summary",
                "Total analyzed: {total} · Groups with duplicates: {groups} · "
                "Duplicates detected: {dups} · Clean 1G1R collection: {unique}",
                total=self._dup_analysis.get("total_games", 0),
                groups=self._dup_analysis.get("total_groups", 0),
                dups=self._dup_analysis.get("total_duplicates", 0),
                unique=self._dup_analysis.get("unique_1g1r_count", 0),
            )
        )

    def _collect_duplicate_game_dicts(self) -> list[dict]:
        dups: list[dict] = []
        for gr in self._dup_analysis.get("duplicate_groups") or []:
            dups.extend(gr.duplicates)
        return dups

    def _apply_dup_tag(self, create_filtered: bool):
        groups = self._dup_analysis.get("duplicate_groups") or []
        if not groups:
            return
        res = tag_1g1r_duplicates(self.db, groups, tag_name="duplicate")
        msg = tr("toolkit_dlg.dup_tagged_msg", "Tagged {count} duplicate game(s) with 'duplicate'.", count=res["tagged"])
        if create_filtered and self.list_row.get("id"):
            try:
                new_lid = create_filtered_1g1r_list(self.db, int(self.list_row["id"]), tag_name="duplicate")
                new_row = self.db.get_list(new_lid)
                msg += "\n" + tr(
                    "toolkit_dlg.dup_filtered_created",
                    "Created filtered 1G1R list: '{name}'.",
                    name=(new_row["name"] if new_row else new_lid),
                )
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    tr("toolkit_dlg.dup_create_list_err_title", "Error Creating 1G1R List"),
                    str(exc),
                )
        self.library_mutated.emit()
        QMessageBox.information(self, tr("toolkit_dlg.dup_audit_title", "1G1R Audit"), msg)

    def _remove_dups_from_list(self):
        dups = self._collect_duplicate_game_dicts()
        if not dups:
            return
        ans = QMessageBox.question(
            self,
            tr("toolkit_dlg.dup_remove_confirm_title", "Remove duplicates from list"),
            tr(
                "toolkit_dlg.dup_remove_confirm_msg",
                "Remove {count} duplicate game(s) from list '{name}'?\n\n"
                "ROM files on disk will NOT be moved or deleted.",
                count=len(dups),
                name=self.list_row.get("name"),
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        removed = remove_duplicates_from_list(self.db, dups)
        dup_ids = {int(d["id"]) for d in dups}
        self.games = [g for g in self.games if int(g["id"]) not in dup_ids]
        self._run_1g1r_analysis()
        self.library_mutated.emit()
        QMessageBox.information(
            self,
            tr("toolkit_dlg.dup_removed_title", "Duplicates Removed"),
            tr("toolkit_dlg.dup_removed_msg", "Removed {count} entry/entries from the list.", count=removed),
        )

    def _move_dups_to_folder(self):
        dups = self._collect_duplicate_game_dicts()
        if not dups:
            return
        ans = QMessageBox.question(
            self,
            tr("toolkit_dlg.dup_move_confirm_title", "Move duplicate ROMs to _duplicates/"),
            tr(
                "toolkit_dlg.dup_move_confirm_msg",
                "Physically move the {count} duplicate ROM file(s) to the '_duplicates/' subfolder\n"
                "next to their original folder and remove them from this list?\n\n"
                "No files will be permanently deleted.",
                count=len(dups),
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        res = move_duplicate_roms_to_folder(self.db, dups, dest_folder=None, remove_from_list=True)
        dup_ids = {int(d["id"]) for d in dups}
        self.games = [g for g in self.games if int(g["id"]) not in dup_ids]
        self._run_1g1r_analysis()
        self.library_mutated.emit()
        err_note = (
            tr("toolkit_dlg.dup_move_errors_note", "\nErrors: {count}", count=len(res["errors"]))
            if res["errors"]
            else ""
        )
        QMessageBox.information(
            self,
            tr("toolkit_dlg.dup_moved_title", "ROMs Moved to _duplicates/"),
            tr(
                "toolkit_dlg.dup_moved_msg",
                "Files moved: {moved}\nSkipped: {skipped}\nRemoved from list: {removed}{err_note}",
                moved=res["moved"],
                skipped=res["skipped"],
                removed=res["removed_from_list"],
                err_note=err_note,
            ),
        )
