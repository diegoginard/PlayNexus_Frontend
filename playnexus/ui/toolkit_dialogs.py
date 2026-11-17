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

        list_name = self.list_row.get("name") or "Lista"
        self.setWindowTitle(f"Rom Manager Pro Toolkit — {list_name}")
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

        self.btn_pick_ffmpeg = QPushButton("📁 Ubicar ffmpeg.exe…")
        self.btn_pick_ffmpeg.setToolTip("Seleccionar binario portable de ffmpeg (opcional)")
        self.btn_pick_ffmpeg.clicked.connect(self._pick_ffmpeg_executable)
        cap_lay.addWidget(self.btn_pick_ffmpeg)

        root.addWidget(self.cap_frame)

        # Pestañas
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_autotrim_tab(), "✂ Auto-Trim Wheels / Logos")
        self.tabs.addTab(self._build_video_tab(), "🎞 Normalizar Videos (ffmpeg)")
        self.tabs.addTab(self._build_1g1r_tab(), "🧬 Auditor 1G1R / Duplicados")
        root.addWidget(self.tabs, 1)

        # Pie
        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)
        root.addLayout(footer)

    def _refresh_capabilities_banner(self):
        caps = detect_toolkit_capabilities(self.db)
        self._caps = caps
        pil_badge = "Pillow: ✅ Activo" if caps["pillow_available"] else "Pillow: ⚡ Motor Qt Nativo (RGBA8888)"
        ff_badge = f"ffmpeg: ✅ Listo ({Path(caps['ffmpeg_path']).name})" if caps["ffmpeg_available"] else "ffmpeg: ⚠ No detectado"
        pdf_badge = "QtPdf: ✅ Activo" if caps["qtpdf_available"] else "QtPdf: ⚠ Fallback visor externo"

        lines = [f"<b>Capacidades del Toolkit:</b> &nbsp; {pil_badge} &nbsp;·&nbsp; {ff_badge} &nbsp;·&nbsp; {pdf_badge}"]
        if not caps["ffmpeg_available"]:
            lines.append(
                "<span style='color:#fbbf24;'>Para normalizar videos, colocá <code>ffmpeg.exe</code> en <code>tools/ffmpeg/</code> o seleccionalo con 'Ubicar ffmpeg.exe…'.</span>"
            )
        self.cap_lbl.setText("<br>".join(lines))

        if hasattr(self, "btn_video_normalize"):
            self.btn_video_normalize.setEnabled(bool(caps["ffmpeg_available"]) and self.video_table.rowCount() > 0)
        if hasattr(self, "video_ffmpeg_notice"):
            self.video_ffmpeg_notice.setVisible(not caps["ffmpeg_available"])

    def _pick_ffmpeg_executable(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar ejecutable ffmpeg",
            "",
            "Ejecutable ffmpeg (ffmpeg.exe ffmpeg);;Todos los archivos (*.*)",
        )
        if not path:
            return
        saved = save_ffmpeg_path(self.db, path)
        self._refresh_capabilities_banner()
        if detect_toolkit_capabilities(self.db)["ffmpeg_available"]:
            QMessageBox.information(self, "ffmpeg configurado", f"Se vinculó correctamente:\n{saved}")
        else:
            QMessageBox.warning(self, "Ruta no válida", f"No se encontró un ejecutable ffmpeg válido en:\n{saved}")

    # ------------------------------------------------------------------
    # TAB 1: AUTO-TRIM WHEELS / LOGOS
    # ------------------------------------------------------------------
    def _build_autotrim_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        cfg_group = QGroupBox("Carpeta y Parámetros de Recorte Automático")
        form = QFormLayout(cfg_group)
        form.setSpacing(8)

        folder_row = QHBoxLayout()
        self.trim_folder_combo = QComboBox()
        self.trim_folder_combo.setEditable(True)
        image_slots = [
            ("wheel_path", "Wheels / Logos"),
            ("boxart_path", "Boxart"),
            ("cartart_path", "Cartart / Disco"),
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
        btn_trim_browse = QPushButton("Examinar…")
        btn_trim_browse.clicked.connect(self._browse_trim_folder)
        folder_row.addWidget(self.trim_folder_combo, 1)
        folder_row.addWidget(btn_trim_browse)
        form.addRow("Carpeta de imágenes:", folder_row)

        opts_row = QHBoxLayout()
        self.trim_mode_combo = QComboBox()
        self.trim_mode_combo.addItem("Automático (Alfa si transparente, sino Negro)", "auto")
        self.trim_mode_combo.addItem("Solo borde transparente (Alfa)", "alpha_only")
        self.trim_mode_combo.addItem("Transparente + bordes negros", "alpha_black")
        self.trim_mode_combo.addItem("Solo bordes negros", "black_only")

        self.trim_margin_spin = QSpinBox()
        self.trim_margin_spin.setRange(0, 32)
        self.trim_margin_spin.setValue(4)
        self.trim_margin_spin.setSuffix(" px")

        self.trim_recursive_cb = QCheckBox("Incluir subcarpetas")
        self.trim_backup_cb = QCheckBox("Guardar respaldo (.bak)")
        self.trim_backup_cb.setChecked(True)

        opts_row.addWidget(QLabel("Modo:"))
        opts_row.addWidget(self.trim_mode_combo, 1)
        opts_row.addSpacing(10)
        opts_row.addWidget(QLabel("Margen:"))
        opts_row.addWidget(self.trim_margin_spin)
        opts_row.addSpacing(10)
        opts_row.addWidget(self.trim_recursive_cb)
        opts_row.addWidget(self.trim_backup_cb)
        form.addRow("Opciones:", opts_row)

        lay.addWidget(cfg_group)

        actions_row = QHBoxLayout()
        self.btn_trim_dry = QPushButton("🔍 Simular (Vista Previa)")
        self.btn_trim_dry.clicked.connect(lambda: self._start_autotrim(dry_run=True))
        self.btn_trim_run = QPushButton("✂ Ejecutar Auto-Trim Real")
        self.btn_trim_run.setStyleSheet("font-weight: 700;")
        self.btn_trim_run.clicked.connect(lambda: self._start_autotrim(dry_run=False))
        self.btn_trim_cancel = QPushButton("⏹ Cancelar")
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

        self.trim_summary_lbl = QLabel("Seleccioná una carpeta (ej: Wheels) y ejecutá una simulación o recorte real.")
        self.trim_summary_lbl.setStyleSheet("color: #93c5fd; font-weight: 600;")
        lay.addWidget(self.trim_summary_lbl)

        self.trim_table = QTableWidget(0, 4)
        self.trim_table.setHorizontalHeaderLabels(["Archivo", "Estado", "Resolución", "Detalle"])
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
        d = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de Wheels / Logos", self._current_trim_folder())
        if d:
            self.trim_folder_combo.setEditText(d)

    def _start_autotrim(self, dry_run: bool):
        folder = self._current_trim_folder()
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(self, "Carpeta inválida", "Seleccioná una carpeta de imágenes existente.")
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
                st_lbl = "Recortada" if res.status == "trimmed" else "Error"
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
        mode_lbl = "Simulación" if dry_run else "Auto-Trim completado"
        kb_saved = summary.get("saved_bytes", 0) / 1024.0
        extra = " (cancelado)" if summary.get("cancelled") else ""
        self.trim_summary_lbl.setText(
            f"{mode_lbl}{extra}: {summary.get('processed', 0)} revisadas · "
            f"{summary.get('trimmed', 0)} recortables/recortadas · "
            f"{summary.get('skipped', 0)} sin cambios · "
            f"{summary.get('errors', 0)} errores"
            + (f" · {kb_saved:.1f} KB ahorrados" if not dry_run else "")
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
            "⚠ <b>ffmpeg no detectado:</b> Podés escanear los videos de la carpeta igualmente, "
            "pero necesitás indicar <code>ffmpeg.exe</code> (botón superior 'Ubicar ffmpeg.exe…') para transcodificar a MP4 H.264/AAC."
        )
        self.video_ffmpeg_notice.setWordWrap(True)
        self.video_ffmpeg_notice.setStyleSheet(
            "background-color: #2c2112; color: #fde68a; border: 1px solid #b45309; border-radius: 6px; padding: 8px;"
        )
        lay.addWidget(self.video_ffmpeg_notice)

        cfg = QGroupBox("Carpeta y Perfil de Normalización MP4 (+faststart)")
        form = QFormLayout(cfg)

        list_name = str(self.list_row.get("name") or "Sin lista").strip()
        default_vdir = str(self.list_row.get("video_path") or "").strip()
        self.video_list_lbl = QLabel(f"<b>Lista activa:</b> {list_name}")
        self.video_list_lbl.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        form.addRow("Origen:", self.video_list_lbl)

        vfolder_row = QHBoxLayout()
        self.video_folder_edit = QLineEdit(default_vdir)
        self.video_folder_edit.setToolTip(default_vdir or "Ruta de la carpeta de videos a analizar")
        self.video_folder_edit.textChanged.connect(lambda t: self.video_folder_edit.setToolTip(t.strip()))
        btn_vbrowse = QPushButton("Examinar…")
        btn_vbrowse.clicked.connect(self._browse_video_folder)
        vfolder_row.addWidget(self.video_folder_edit, 1)
        vfolder_row.addWidget(btn_vbrowse)
        form.addRow("Carpeta de Videos:", vfolder_row)

        vopts_row = QHBoxLayout()
        self.video_res_combo = QComboBox()
        self.video_res_combo.addItem("480p (Liviano Arcade)", 480)
        self.video_res_combo.addItem("720p (Alta Calidad)", 720)

        self.video_max_mb_spin = _FlexibleMBSpinBox()
        self.video_max_mb_spin.setDecimals(1)
        self.video_max_mb_spin.setSingleStep(1.0)
        self.video_max_mb_spin.setRange(1.0, 500.0)
        self.video_max_mb_spin.setValue(15.0)
        self.video_max_mb_spin.setSuffix(" MB")

        self.video_crf_spin = QSpinBox()
        self.video_crf_spin.setRange(18, 30)
        self.video_crf_spin.setValue(24)

        self.video_strip_audio_cb = QCheckBox("Quitar audio (-an)")
        self.video_backup_cb = QCheckBox("Respaldar (.bak)")
        self.video_backup_cb.setChecked(True)

        vopts_row.addWidget(QLabel("Máx:"))
        vopts_row.addWidget(self.video_res_combo)
        vopts_row.addWidget(QLabel("Re-codificar si >"))
        vopts_row.addWidget(self.video_max_mb_spin)
        vopts_row.addWidget(QLabel("CRF:"))
        vopts_row.addWidget(self.video_crf_spin)
        vopts_row.addWidget(self.video_strip_audio_cb)
        vopts_row.addWidget(self.video_backup_cb)
        form.addRow("Perfil H.264:", vopts_row)

        vscan_opts_row = QHBoxLayout()
        self.video_recursive_cb = QCheckBox("Incluir subcarpetas")
        self.video_deep_probe_cb = QCheckBox("Analizar resolución/códec en todos los .mp4 (ffprobe)")
        self.video_deep_probe_cb.setToolTip(
            "Inspecciona con ffprobe incluso los .mp4 menores al límite de tamaño (útil para detectar 720p/1080p o códecs no-H.264)."
        )
        vscan_opts_row.addWidget(self.video_recursive_cb)
        vscan_opts_row.addSpacing(12)
        vscan_opts_row.addWidget(self.video_deep_probe_cb)
        vscan_opts_row.addStretch()
        form.addRow("Alcance escaneo:", vscan_opts_row)
        lay.addWidget(cfg)

        vact = QHBoxLayout()
        self.btn_video_scan = QPushButton("🔍 Escanear Videos")
        self.btn_video_scan.clicked.connect(self._scan_videos)
        self.btn_video_normalize = QPushButton("🎞 Normalizar Lista con ffmpeg")
        self.btn_video_normalize.setEnabled(False)
        self.btn_video_normalize.clicked.connect(self._start_video_normalize)
        self.btn_video_cancel = QPushButton("⏹ Cancelar")
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

        self.video_summary_lbl = QLabel("Escaneá la carpeta de videos para detectar formatos legados o archivos pesados.")
        self.video_summary_lbl.setStyleSheet("color: #93c5fd; font-weight: 600;")
        lay.addWidget(self.video_summary_lbl)

        self.video_table = QTableWidget(0, 4)
        self.video_table.setHorizontalHeaderLabels(["Archivo", "Tamaño", "Motivo", "Estado"])
        configure_details_table(
            self.video_table,
            col_widths=(290, 95, 320, 140),
        )
        lay.addWidget(self.video_table, 1)

        return w

    def _browse_video_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de videos", self.video_folder_edit.text().strip())
        if d:
            self.video_folder_edit.setText(d)

    def _scan_videos(self):
        folder = self.video_folder_edit.text().strip()
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(self, "Carpeta inválida", "Indicá una carpeta de videos válida.")
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
        self.video_summary_lbl.setText(f"Escaneando {folder} (>{max_mb:g} MB / máx. {max_h}p)…")

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
        self.video_summary_lbl.setText(f"Escaneando videos ({done}/{total}): {fname}")

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
                self.video_table.setItem(r, 3, SortableTableWidgetItem("Pendiente"))
                self._video_row_by_path[cand.file_path] = r

        caps = detect_toolkit_capabilities(self.db)
        scanned_n = int(stats.get("scanned_files", len(cands)))
        probed_n = int(stats.get("probed_files", 0))
        extra = " (cancelado)" if stats.get("cancelled") else ""
        probe_txt = f" · ffprobe: {probed_n}" if probed_n else ""
        self.video_summary_lbl.setText(
            f"Escaneo finalizado{extra}: {scanned_n} video(s) revisados{probe_txt} · "
            f"{len(cands)} candidato(s) (filtro: > {max_mb:g} MB o > {max_h}p / no-MP4)"
        )
        self.btn_video_normalize.setEnabled(bool(caps["ffmpeg_available"]) and len(cands) > 0)

    def _start_video_normalize(self):
        caps = detect_toolkit_capabilities(self.db)
        if not caps["ffmpeg_available"]:
            QMessageBox.warning(self, "ffmpeg faltante", "Configurá primero la ruta de ffmpeg.exe.")
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
                "Sin videos pendientes",
                "Todos los videos de la lista ya fueron normalizados. Volvé a escanear si querés revisar de nuevo.",
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
            lbl = "✅ Normalizado" if st == "normalized" else ("⏹ Cancelado" if st == "cancelled" else f"❌ {res.get('message', 'Error')}")
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
        extra = " (cancelado)" if summary.get("cancelled") else ""
        self.video_summary_lbl.setText(
            f"Normalización finalizada{extra}: {summary.get('normalized', 0)}/{summary.get('total', 0)} convertidos · "
            f"{summary.get('errors', 0)} errores · {saved_mb:.1f} MB ahorrados"
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

        cfg = QGroupBox("Reglas 1G1R (1 Game 1 ROM) — Prioridad Regional y Protección Multi-Disco")
        form = QFormLayout(cfg)

        reg_row = QHBoxLayout()
        self.region_order_edit = QLineEdit(", ".join(DEFAULT_1G1R_REGION_ORDER))
        self.region_order_edit.setToolTip("Orden de prioridad separado por comas (de mayor a menor preferencia)")
        btn_us = QPushButton("Preset USA")
        btn_us.clicked.connect(lambda: self.region_order_edit.setText(", ".join(DEFAULT_1G1R_REGION_ORDER)))
        btn_eu = QPushButton("Preset Europa/ESP")
        btn_eu.clicked.connect(
            lambda: self.region_order_edit.setText("Spain, Europe, World, USA, Japan, Korea, Asia, Brazil, France, Germany, Italy, Unknown")
        )
        btn_jp = QPushButton("Preset Japón")
        btn_jp.clicked.connect(
            lambda: self.region_order_edit.setText("Japan, World, USA, Europe, Spain, Korea, Asia, Brazil, France, Germany, Italy, Unknown")
        )
        reg_row.addWidget(self.region_order_edit, 1)
        reg_row.addWidget(btn_us)
        reg_row.addWidget(btn_eu)
        reg_row.addWidget(btn_jp)
        form.addRow("Prioridad regional:", reg_row)

        opts_1g1r = QHBoxLayout()
        self.dup_cloneof_cb = QCheckBox("Agrupar clones MAME / XML (campo cloneof)")
        self.dup_cloneof_cb.setChecked(True)
        self.btn_dup_analyze = QPushButton("🧬 Analizar Duplicados 1G1R")
        self.btn_dup_analyze.setStyleSheet("font-weight: 700;")
        self.btn_dup_analyze.clicked.connect(self._run_1g1r_analysis)
        opts_1g1r.addWidget(self.dup_cloneof_cb)
        opts_1g1r.addStretch()
        opts_1g1r.addWidget(self.btn_dup_analyze)
        form.addRow("", opts_1g1r)

        lay.addWidget(cfg)

        self.dup_summary_lbl = QLabel(
            f"Juegos cargados en lista: {len(self.games)}. Los juegos multi-disco (Disc 1 / Disc 2) nunca se mezclan."
        )
        self.dup_summary_lbl.setStyleSheet("color: #93c5fd; font-weight: 600;")
        lay.addWidget(self.dup_summary_lbl)

        self.dup_table = QTableWidget(0, 4)
        self.dup_table.setHorizontalHeaderLabels(["Grupo / Juego", "Ganador (1G1R)", "Duplicado a gestionar", "Acción / Motivo"])
        configure_details_table(
            self.dup_table,
            col_widths=(200, 260, 260, 200),
        )
        lay.addWidget(self.dup_table, 1)

        act_bar = QHBoxLayout()
        self.btn_dup_tag = QPushButton("🏷 Etiquetar como 'duplicate'")
        self.btn_dup_tag.setToolTip("Agrega la etiqueta 'duplicate' a los duplicados sin borrar ni mover ROMs")
        self.btn_dup_tag.clicked.connect(lambda: self._apply_dup_tag(create_filtered=False))

        self.btn_dup_filter_list = QPushButton("⚡ Etiquetar + Crear Lista 1G1R Filtrada")
        self.btn_dup_filter_list.setToolTip("Etiqueta duplicados y crea una lista filtrada ocultándolos")
        self.btn_dup_filter_list.clicked.connect(lambda: self._apply_dup_tag(create_filtered=True))

        self.btn_dup_remove = QPushButton("🧹 Quitar de esta Lista (no borra ROM)")
        self.btn_dup_remove.clicked.connect(self._remove_dups_from_list)

        self.btn_dup_move = QPushButton("📦 Mover ROMs a _duplicates/…")
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
                    why = f"Clon de {dup.get('cloneof')}" if dup.get("cloneof") else "Menor prioridad regional/revisión"
                    self.dup_table.setItem(r, 3, SortableTableWidgetItem(why))

        has_dups = bool(groups)
        for b in (self.btn_dup_tag, self.btn_dup_filter_list, self.btn_dup_remove, self.btn_dup_move):
            b.setEnabled(has_dups)

        self.dup_summary_lbl.setText(
            f"Total analizados: {self._dup_analysis.get('total_games', 0)} · "
            f"Grupos con duplicados: {self._dup_analysis.get('total_groups', 0)} · "
            f"Duplicados detectados: {self._dup_analysis.get('total_duplicates', 0)} · "
            f"Colección 1G1R limpia: {self._dup_analysis.get('unique_1g1r_count', 0)}"
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
        msg = f"Se etiquetaron {res['tagged']} juego(s) duplicado(s) con 'duplicate'."
        if create_filtered and self.list_row.get("id"):
            try:
                new_lid = create_filtered_1g1r_list(self.db, int(self.list_row["id"]), tag_name="duplicate")
                new_row = self.db.get_list(new_lid)
                msg += f"\nSe creó la lista filtrada 1G1R: '{new_row['name'] if new_row else new_lid}'."
            except Exception as exc:
                QMessageBox.warning(self, "Error creando lista 1G1R", str(exc))
        self.library_mutated.emit()
        QMessageBox.information(self, "Auditoría 1G1R", msg)

    def _remove_dups_from_list(self):
        dups = self._collect_duplicate_game_dicts()
        if not dups:
            return
        ans = QMessageBox.question(
            self,
            "Quitar duplicados de la lista",
            f"¿Quitar {len(dups)} juego(s) duplicado(s) de la lista '{self.list_row.get('name')}'?\n\n"
            "Los archivos ROM en el disco NO se moverán ni se eliminarán.",
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
        QMessageBox.information(self, "Duplicados quitados", f"Se quitaron {removed} entrada(s) de la lista.")

    def _move_dups_to_folder(self):
        dups = self._collect_duplicate_game_dicts()
        if not dups:
            return
        ans = QMessageBox.question(
            self,
            "Mover ROMs duplicadas a _duplicates/",
            f"¿Mover físicamente los {len(dups)} archivo(s) ROM duplicado(s) a la subcarpeta '_duplicates/'\n"
            "junto a su carpeta original y quitarlos de esta lista?\n\n"
            "Ningún archivo será borrado permanentemente.",
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
        err_note = f"\nErrores: {len(res['errors'])}" if res["errors"] else ""
        QMessageBox.information(
            self,
            "ROMs movidas a _duplicates/",
            f"Archivos movidos: {res['moved']}\nOmitidos: {res['skipped']}\nQuitados de la lista: {res['removed_from_list']}{err_note}",
        )
