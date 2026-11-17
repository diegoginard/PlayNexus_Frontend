"""
Diálogos de configuración, scraping en lote y búsqueda interactiva por ROM
para el Rom Manager de PlayNexus.
"""
from __future__ import annotations

import os
from dataclasses import replace
from typing import Any, Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from playnexus.db import Database
from playnexus.services.rom_manager import (
    AuditSummary,
    MediaRequirementSpec,
    RomAuditResult,
    ensure_media_folders_for_list,
    format_file_size,
    suggest_media_root_for_list,
)
from playnexus.services.scraper import (
    CompositeScraperEngine,
    DEFAULT_REGION_PRIORITY,
    SYSTEM_CATALOG,
    BatchScrapeSummary,
    RomScrapeOutcome,
    ScrapeJobOptions,
    ScraperCandidate,
    ScraperConfig,
    clean_rom_search_title,
    clear_scraper_cache,
    detect_system_for_list,
    get_scraper_cache_stats,
    load_scraper_config,
    save_scraper_config,
)
from playnexus.services.scraper.http_utils import http_get_bytes
from playnexus.ui.table_utils import (
    SortableTableWidgetItem,
    configure_details_table,
    paused_table_sorting,
)


# =====================================================================
# 0. DIÁLOGO RÁPIDO DE INICIO DE SESIÓN EN SCREENSCRAPER
# =====================================================================
class ScreenScraperLoginDialog(QDialog):
    """Solicita Usuario y Contraseña de ScreenScraper.fr con opción de recordar."""

    def __init__(self, db: Database, config: ScraperConfig | None = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.config = config or load_scraper_config(db)
        self.setWindowTitle("Iniciar sesión — ScreenScraper.fr")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        intro = QLabel(
            "Ingresá tu <b>usuario</b> y <b>contraseña</b> de "
            "<a href='https://www.screenscraper.fr'>screenscraper.fr</a> para continuar."
        )
        intro.setOpenExternalLinks(True)
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        root.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(8)
        self.ssid_edit = QLineEdit(self.config.ss_ssid)
        self.ssid_edit.setPlaceholderText("Usuario de ScreenScraper")
        self.sspass_edit = QLineEdit(self.config.ss_sspassword)
        self.sspass_edit.setEchoMode(QLineEdit.Password)
        self.sspass_edit.setPlaceholderText("Contraseña de ScreenScraper")

        form.addRow("Usuario:", self.ssid_edit)
        form.addRow("Contraseña:", self.sspass_edit)
        root.addLayout(form)

        opts = QHBoxLayout()
        self.chk_remember = QCheckBox("Recordar usuario y contraseña")
        self.chk_remember.setChecked(self.config.ss_remember)
        self.chk_show_pass = QCheckBox("Mostrar contraseña")
        self.chk_show_pass.toggled.connect(
            lambda show: self.sspass_edit.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)
        )
        opts.addWidget(self.chk_remember)
        opts.addStretch()
        opts.addWidget(self.chk_show_pass)
        root.addLayout(opts)

        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        self.btn_accept = QPushButton("Continuar")
        self.btn_accept.setObjectName("primary")
        self.btn_accept.clicked.connect(self._on_accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(self.btn_accept)
        root.addLayout(btns)

    def _on_accept(self):
        user = self.ssid_edit.text().strip()
        pwd = self.sspass_edit.text().strip()
        if not user or not pwd:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Ingresá tanto el usuario como la contraseña de ScreenScraper.",
            )
            return
        self.config = replace(
            self.config,
            ss_ssid=user,
            ss_sspassword=pwd,
            ss_remember=self.chk_remember.isChecked(),
        )
        save_scraper_config(self.db, self.config)
        self.accept()


# =====================================================================
# 1. DIÁLOGO DE CONFIGURACIÓN DEL SCRAPER
# =====================================================================
class ScraperSettingsDialog(QDialog):
    """Permite configurar fuentes, regiones, idioma, credenciales ScreenScraper y caché."""

    def __init__(self, db: Database, parent=None, current_config: ScraperConfig | None = None):
        super().__init__(parent)
        self.db = db
        self.config = current_config or load_scraper_config(db)
        self.setWindowTitle("Configuración del Scraper Online")
        self.setMinimumSize(500, 380)
        self._build_ui()
        self._load_values()
        screen = QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            self.resize(min(660, int(avail.width() * 0.90)), min(680, int(avail.height() * 0.85)))
        else:
            self.resize(620, 620)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        scroll_content = QWidget()
        body = QVBoxLayout(scroll_content)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(10)

        intro = QLabel(
            "Configurá los proveedores online para descargar automáticamente la media declarada "
            "en el <code>MEDIA_REQUIREMENTS</code> de cada layout y completar metadatos de juegos."
        )
        intro.setWordWrap(True)
        intro.setMinimumWidth(0)
        intro.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        body.addWidget(intro)

        # Preferencias generales
        gen_grp = QGroupBox("Preferencias generales")
        form = QFormLayout(gen_grp)
        form.setSpacing(7)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Automático (ArcadeDB / ScreenScraper / Libretro)", "auto")
        self.provider_combo.addItem("Libretro Thumbnails (Gratis, sin clave — Boxart y Wheel)", "libretro")
        self.provider_combo.addItem("Arcade Database / ADB (Gratis — MAME / Arcade + Video)", "arcadedb")
        self.provider_combo.addItem("ScreenScraper API v2 (Media completa + Metadatos)", "screenscraper")
        form.addRow("Proveedor predeterminado:", self.provider_combo)

        self.regions_edit = QLineEdit()
        self.regions_edit.setPlaceholderText("us, wor, ss, eu, es, jp")
        self.regions_edit.setToolTip("Orden de prioridad de regiones separado por comas (ej: es, eu, us, wor, jp)")
        form.addRow("Prioridad de regiones:", self.regions_edit)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Español (es)", "es")
        self.lang_combo.addItem("Inglés (en)", "en")
        self.lang_combo.addItem("Francés (fr)", "fr")
        form.addRow("Idioma de sinopsis/géneros:", self.lang_combo)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 4)
        self.workers_spin.setToolTip("Cantidad de descargas simultáneas en modo lote (1 a 4)")
        form.addRow("Hilos paralelos:", self.workers_spin)

        self.chk_hd_video = QCheckBox("Preferir videos HD cuando estén disponibles (ArcadeDB)")
        self.chk_empty_meta = QCheckBox("Completar campos vacíos en la base de datos (año, género, notas…)")
        self.chk_overwrite_meta = QCheckBox("Sobrescribir metadatos existentes al scrapear")
        self.chk_cache = QCheckBox("Usar caché local en config/scraper_cache/ (acelera re-escaneos)")

        form.addRow("", self.chk_hd_video)
        form.addRow("", self.chk_empty_meta)
        form.addRow("", self.chk_overwrite_meta)
        form.addRow("", self.chk_cache)
        body.addWidget(gen_grp)

        # Credenciales ScreenScraper (Miembro + API Dev + Debug, cifrado portátil en config/.key)
        ss_grp = QGroupBox("Cuenta y API de ScreenScraper.fr")
        ss_vbox = QVBoxLayout(ss_grp)
        ss_vbox.setSpacing(6)

        ss_note = QLabel(
            "ScreenScraper ofrece carátulas 3D/2D, wheels HD, cartuchos/discos, flyers, marquees, "
            "bezels, videos y manuales PDF. Todas las credenciales se guardan cifradas en "
            "<code>config/settings.txt</code> (clave portátil en <code>config/.key</code>). "
            "Sin cuenta, <b>Libretro Thumbnails</b> y <b>ArcadeDB</b> siguen funcionando gratis."
        )
        ss_note.setWordWrap(True)
        ss_note.setMinimumWidth(0)
        ss_note.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        ss_vbox.addWidget(ss_note)

        ss_form = QFormLayout()
        ss_form.setSpacing(6)
        self.ss_ssid_edit = QLineEdit()
        self.ss_ssid_edit.setPlaceholderText("Usuario de miembro (ssid)")
        self.ss_sspass_edit = QLineEdit()
        self.ss_sspass_edit.setEchoMode(QLineEdit.Password)
        self.ss_sspass_edit.setPlaceholderText("Contraseña de miembro (sspassword)")

        self.ss_devid_edit = QLineEdit()
        self.ss_devid_edit.setPlaceholderText("Usuario Dev (devid) — cuenta de desarrollador")
        self.ss_devpass_edit = QLineEdit()
        self.ss_devpass_edit.setEchoMode(QLineEdit.Password)
        self.ss_devpass_edit.setPlaceholderText("Contraseña Dev (devpassword)")
        self.ss_devdebug_edit = QLineEdit()
        self.ss_devdebug_edit.setEchoMode(QLineEdit.Password)
        self.ss_devdebug_edit.setPlaceholderText("Contraseña Debug (devdebugpassword) — opcional")

        ss_opts_grid = QGridLayout()
        ss_opts_grid.setContentsMargins(0, 2, 0, 0)
        ss_opts_grid.setHorizontalSpacing(14)
        ss_opts_grid.setVerticalSpacing(4)
        self.chk_remember_ss = QCheckBox("Recordar usuario y contraseña")
        self.chk_show_pass = QCheckBox("Mostrar contraseñas")
        self.chk_show_pass.toggled.connect(self._toggle_passwords)
        self.chk_debug_mode = QCheckBox("Modo Debug API (máx. 100/día)")
        self.chk_debug_mode.setToolTip(
            "Envía devdebugpassword en las consultas de prueba y evita la caché local de ScreenScraper."
        )
        ss_opts_grid.addWidget(self.chk_remember_ss, 0, 0)
        ss_opts_grid.addWidget(self.chk_show_pass, 0, 1)
        ss_opts_grid.addWidget(self.chk_debug_mode, 1, 0, 1, 2)

        ss_form.addRow("Usuario:", self.ss_ssid_edit)
        ss_form.addRow("Contraseña:", self.ss_sspass_edit)
        ss_form.addRow("Usuario Dev (devid):", self.ss_devid_edit)
        ss_form.addRow("Contraseña Dev:", self.ss_devpass_edit)
        ss_form.addRow("Contraseña Debug:", self.ss_devdebug_edit)
        ss_form.addRow("", ss_opts_grid)
        ss_vbox.addLayout(ss_form)
        body.addWidget(ss_grp)

        # Caché local
        bottom_row = QHBoxLayout()
        self.cache_lbl = QLabel()
        self.cache_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        self._refresh_cache_label()

        btn_clear_cache = QPushButton("🧹 Limpiar caché")
        btn_clear_cache.clicked.connect(self._on_clear_cache)

        bottom_row.addWidget(self.cache_lbl, 1)
        bottom_row.addWidget(btn_clear_cache)
        body.addLayout(bottom_row)
        body.addStretch()

        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        # Botones siempre visibles al pie
        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("💾 Guardar configuración")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self._on_save)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)
        root.addLayout(btns)

    def _toggle_passwords(self, show: bool):
        mode = QLineEdit.Normal if show else QLineEdit.Password
        self.ss_devpass_edit.setEchoMode(mode)
        self.ss_devdebug_edit.setEchoMode(mode)
        self.ss_sspass_edit.setEchoMode(mode)

    def _refresh_cache_label(self):
        cnt, b = get_scraper_cache_stats()
        self.cache_lbl.setText(f"Caché local: {cnt} archivo(s) ({format_file_size(b)})")

    def _on_clear_cache(self):
        cnt, b = clear_scraper_cache()
        self._refresh_cache_label()
        QMessageBox.information(
            self,
            "Caché limpiada",
            f"Se eliminaron {cnt} archivo(s) de caché ({format_file_size(b)}).",
        )

    def _load_values(self):
        c = self.config
        idx = self.provider_combo.findData(c.preferred_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.regions_edit.setText(", ".join(c.region_priority))
        l_idx = self.lang_combo.findData(c.language)
        if l_idx >= 0:
            self.lang_combo.setCurrentIndex(l_idx)
        self.workers_spin.setValue(c.normalized_workers())
        self.chk_hd_video.setChecked(c.prefer_hd_video)
        self.chk_empty_meta.setChecked(c.update_empty_metadata)
        self.chk_overwrite_meta.setChecked(c.overwrite_metadata)
        self.chk_cache.setChecked(c.cache_enabled)
        self.ss_devid_edit.setText(c.ss_devid)
        self.ss_devpass_edit.setText(c.ss_devpassword)
        self.ss_devdebug_edit.setText(c.ss_devdebugpassword)
        self.chk_debug_mode.setChecked(c.ss_debug_mode)
        self.ss_ssid_edit.setText(c.ss_ssid)
        self.ss_sspass_edit.setText(c.ss_sspassword)
        self.chk_remember_ss.setChecked(c.ss_remember)

    def _on_save(self):
        regs = tuple(r.strip().lower() for r in self.regions_edit.text().split(",") if r.strip())
        if not regs:
            regs = DEFAULT_REGION_PRIORITY
        new_cfg = ScraperConfig(
            preferred_provider=str(self.provider_combo.currentData() or "auto"),
            region_priority=regs,
            language=str(self.lang_combo.currentData() or "es"),
            ss_devid=self.ss_devid_edit.text().strip(),
            ss_devpassword=self.ss_devpass_edit.text().strip(),
            ss_devdebugpassword=self.ss_devdebug_edit.text().strip(),
            ss_debug_mode=self.chk_debug_mode.isChecked(),
            ss_ssid=self.ss_ssid_edit.text().strip(),
            ss_sspassword=self.ss_sspass_edit.text().strip(),
            ss_remember=self.chk_remember_ss.isChecked(),
            max_workers=self.workers_spin.value(),
            update_empty_metadata=self.chk_empty_meta.isChecked(),
            overwrite_metadata=self.chk_overwrite_meta.isChecked(),
            cache_enabled=self.chk_cache.isChecked(),
            timeout_sec=self.config.timeout_sec,
            prefer_hd_video=self.chk_hd_video.isChecked(),
        )
        save_scraper_config(self.db, new_cfg)
        self.config = new_cfg
        self.accept()


# =====================================================================
# 2. WORKERS ASÍNCRONOS (QThread — SIN TOCAR DB DESDE HILOS SECUNDARIOS)
# =====================================================================
class BatchScrapeWorker(QThread):
    rom_done = Signal(object, int, int)  # RomScrapeOutcome, processed, total
    finished_batch = Signal(object)      # BatchScrapeSummary
    failed = Signal(str)

    def __init__(
        self,
        roms: list[RomAuditResult],
        games_by_id: dict[int, dict[str, Any]],
        specs: list[MediaRequirementSpec],
        options: ScrapeJobOptions,
        config: ScraperConfig,
        parent=None,
    ):
        super().__init__(parent)
        self.roms = list(roms)
        self.games_by_id = {k: dict(v) for k, v in games_by_id.items()}
        self.specs = list(specs)
        self.options = options
        self.config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            engine = CompositeScraperEngine(self.config)
            summary = engine.run_batch(
                roms=self.roms,
                games_by_id=self.games_by_id,
                specs=self.specs,
                options=self.options,
                on_rom_done=lambda out, cur, tot: self.rom_done.emit(out, cur, tot),
                cancel_check=lambda: self._cancelled,
            )
            self.finished_batch.emit(summary)
        except Exception as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))


class SingleRomSearchWorker(QThread):
    finished_search = Signal(list)  # list[ScraperCandidate]
    failed = Signal(str)

    def __init__(
        self,
        query: str,
        stem: str,
        rom_path: str,
        system_key: str,
        provider_mode: str,
        target_slots: tuple[str, ...],
        config: ScraperConfig,
        parent=None,
    ):
        super().__init__(parent)
        self.query = query
        self.stem = stem
        self.rom_path = rom_path
        self.system_key = system_key
        self.provider_mode = provider_mode
        self.target_slots = target_slots
        self.config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            engine = CompositeScraperEngine(self.config)
            candidates = engine.search_candidates(
                query=self.query,
                stem=self.stem,
                rom_path=self.rom_path,
                system_key=self.system_key,
                provider_mode=self.provider_mode,
                target_slots=self.target_slots,
                cancel_check=lambda: self._cancelled,
                max_per_provider=8,
            )
            if not self._cancelled:
                self.finished_search.emit(candidates)
        except Exception as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))


class SingleRomDownloadWorker(QThread):
    finished_download = Signal(dict, dict)  # downloaded, failed
    failed = Signal(str)

    def __init__(
        self,
        candidate: ScraperCandidate,
        stem: str,
        specs_by_key: dict[str, MediaRequirementSpec],
        slot_keys: list[str],
        overwrite: bool,
        config: ScraperConfig,
        parent=None,
    ):
        super().__init__(parent)
        self.candidate = candidate
        self.stem = stem
        self.specs_by_key = dict(specs_by_key)
        self.slot_keys = list(slot_keys)
        self.overwrite = overwrite
        self.config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            engine = CompositeScraperEngine(self.config)
            downloaded, failed = engine.download_candidate_slots(
                candidate=self.candidate,
                stem=self.stem,
                specs_by_key=self.specs_by_key,
                slot_keys=self.slot_keys,
                overwrite=self.overwrite,
                cancel_check=lambda: self._cancelled,
            )
            if not self._cancelled:
                self.finished_download.emit(downloaded, failed)
        except Exception as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))


class ThumbnailFetchWorker(QThread):
    image_ready = Signal(str, bytes)

    def __init__(self, url: str, timeout: float = 12.0, parent=None):
        super().__init__(parent)
        self.url = url
        self.timeout = timeout
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self._cancelled or not self.url:
            return
        try:
            data, _ = http_get_bytes(self.url, timeout=self.timeout, retries=0)
            if not self._cancelled:
                self.image_ready.emit(self.url, data)
        except Exception:
            if not self._cancelled:
                self.image_ready.emit(self.url, b"")


# =====================================================================
# 3. DIÁLOGO DE SCRAPING EN LOTE (POR LISTA Y MEDIA_REQUIREMENTS)
# =====================================================================
class BatchScrapeDialog(QDialog):
    """Configura y ejecuta la descarga masiva de media faltante según el layout auditado."""

    def __init__(
        self,
        db: Database,
        list_row: dict[str, Any],
        summary: AuditSummary,
        visible_roms: list[RomAuditResult],
        games_by_id: dict[int, dict[str, Any]],
        release_media_cb: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self.list_row = dict(list_row)
        self.summary = summary
        self.visible_roms = list(visible_roms)
        self.games_by_id = games_by_id
        self.release_media_cb = release_media_cb
        self.config = load_scraper_config(db)

        self._worker: BatchScrapeWorker | None = None
        self._slot_checks: dict[str, QCheckBox] = {}
        self.has_media_changes = False
        self.has_metadata_changes = False
        self.has_folder_changes = False

        self.setWindowTitle(f"Scrapear Media Online — {summary.list_name}")
        self.setMinimumSize(720, 620)
        self._build_ui()
        self._refresh_folder_warning()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        banner = QFrame()
        banner.setStyleSheet(
            "QFrame { background-color: #1b1e2a; border: 1px solid #2b3144; border-radius: 8px; padding: 8px; }"
        )
        b_lay = QVBoxLayout(banner)
        b_lay.setContentsMargins(8, 6, 8, 6)
        b_lay.setSpacing(4)
        lbl_head = QLabel(
            f"<b>Lista:</b> {self.summary.list_name}  ·  <b>Layout:</b> {self.summary.layout_name}  ·  "
            f"<b>ROMs totales:</b> {self.summary.total_roms}"
        )
        lbl_head.setStyleSheet("color: #e2e8f0; font-size: 9.5pt;")
        lbl_sub = QLabel(
            "Se buscarán y descargarán <b>únicamente</b> los tipos de media declarados en "
            "<code>MEDIA_REQUIREMENTS</code> del layout elegido."
        )
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        lbl_sub.setWordWrap(True)
        b_lay.addWidget(lbl_head)
        b_lay.addWidget(lbl_sub)
        root.addWidget(banner)

        # Configuración del trabajo
        cfg_grp = QGroupBox("Parámetros de descarga")
        cfg_form = QFormLayout(cfg_grp)
        cfg_form.setSpacing(8)

        # Detección de plataforma
        emu_row = self.db.get_default_emulator_for_list(int(self.list_row["id"])) if self.db else None
        detected_sys = detect_system_for_list(
            self.list_row,
            self.summary.layout_name,
            dict(emu_row) if emu_row else None,
        )
        self.system_combo = QComboBox()
        for sys_obj in SYSTEM_CATALOG:
            self.system_combo.addItem(sys_obj.display_name, sys_obj.key)
        s_idx = self.system_combo.findData(detected_sys.key)
        if s_idx >= 0:
            self.system_combo.setCurrentIndex(s_idx)
        cfg_form.addRow("Sistema detectado:", self.system_combo)

        prov_row = QHBoxLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Automático (ArcadeDB + ScreenScraper + Libretro)", "auto")
        self.provider_combo.addItem("Libretro Thumbnails (Gratis, sin clave — Boxart y Wheel)", "libretro")
        self.provider_combo.addItem("Arcade Database / ADB (Gratis — MAME / Arcade + Video)", "arcadedb")
        self.provider_combo.addItem("ScreenScraper.fr (Usuario y Contraseña)", "screenscraper")
        p_idx = self.provider_combo.findData(self.config.preferred_provider)
        if p_idx >= 0:
            self.provider_combo.setCurrentIndex(p_idx)
        self.provider_combo.currentIndexChanged.connect(self._update_provider_hint)

        self.btn_cfg = QPushButton("⚙ Credenciales…")
        self.btn_cfg.clicked.connect(self._open_settings)
        prov_row.addWidget(self.provider_combo, 1)
        prov_row.addWidget(self.btn_cfg)
        cfg_form.addRow("Fuente online:", prov_row)

        self.provider_hint_lbl = QLabel()
        self.provider_hint_lbl.setWordWrap(True)
        self.provider_hint_lbl.setStyleSheet("color: #93c5fd; font-size: 8.5pt;")
        cfg_form.addRow("", self.provider_hint_lbl)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Solo ROMs con media faltante en los slots elegidos", "missing")
        self.scope_combo.addItem(
            f"Solo ROMs visibles con el filtro actual ({len(self.visible_roms)})",
            "filtered",
        )
        self.scope_combo.addItem(
            f"Todas las ROMs de la lista ({len(self.summary.results)})",
            "all",
        )
        cfg_form.addRow("Alcance:", self.scope_combo)

        # Slots según MEDIA_REQUIREMENTS
        slots_widget = QWidget()
        slots_grid = QGridLayout(slots_widget)
        slots_grid.setContentsMargins(0, 0, 0, 0)
        slots_grid.setHorizontalSpacing(14)
        slots_grid.setVerticalSpacing(6)
        for idx, spec in enumerate(self.summary.specs):
            tot = self.summary.slot_totals.get(spec.key, {})
            miss = int(tot.get("missing", 0))
            star = "★ " if spec.required else ""
            folder_warn = " [Sin carpeta]" if not spec.folder_exists else ""
            chk = QCheckBox(f"{star}{spec.label} (faltan {miss}){folder_warn}")
            chk.setChecked(miss > 0 or not spec.folder_exists)
            chk.toggled.connect(self._refresh_folder_warning)
            self._slot_checks[spec.key] = chk
            slots_grid.addWidget(chk, idx // 2, idx % 2)
        cfg_form.addRow("Medios del layout:", slots_widget)

        # Panel opcional de auto-creación de carpetas faltantes
        self.folder_box = QFrame()
        self.folder_box.setStyleSheet(
            "QFrame { background-color: #241f18; border: 1px solid #6b4f1d; border-radius: 6px; padding: 6px; }"
        )
        fb_lay = QVBoxLayout(self.folder_box)
        fb_lay.setContentsMargins(8, 6, 8, 6)
        fb_lay.setSpacing(6)
        fb_lbl = QLabel(
            "⚠ Hay slots seleccionados sin carpeta configurada en la lista. "
            "Indicá la carpeta base para crear automáticamente las subcarpetas:"
        )
        fb_lbl.setWordWrap(True)
        fb_lbl.setStyleSheet("color: #fcd34d; font-size: 8.5pt;")
        fb_lay.addWidget(fb_lbl)

        fb_row = QHBoxLayout()
        self.media_root_edit = QLineEdit(suggest_media_root_for_list(self.list_row))
        self.media_root_edit.setPlaceholderText("Ej: C:/Roms/SNES/media")
        btn_pick_root = QPushButton("📁 Examinar…")
        btn_pick_root.clicked.connect(self._pick_media_root)
        self.chk_auto_mkdir = QCheckBox("Crear subcarpetas al iniciar")
        self.chk_auto_mkdir.setChecked(True)
        fb_row.addWidget(self.media_root_edit, 1)
        fb_row.addWidget(btn_pick_root)
        fb_lay.addLayout(fb_row)
        fb_lay.addWidget(self.chk_auto_mkdir)
        cfg_form.addRow("", self.folder_box)

        # Opciones extra
        opts_row = QHBoxLayout()
        self.chk_overwrite = QCheckBox("Sobrescribir archivos existentes")
        self.chk_meta = QCheckBox("Completar metadatos vacíos")
        self.chk_meta.setChecked(self.config.update_empty_metadata)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 4)
        self.workers_spin.setValue(self.config.normalized_workers())
        self.workers_spin.setPrefix("Hilos: ")
        opts_row.addWidget(self.chk_overwrite)
        opts_row.addWidget(self.chk_meta)
        opts_row.addStretch()
        opts_row.addWidget(self.workers_spin)
        cfg_form.addRow("Opciones:", opts_row)

        root.addWidget(cfg_grp)

        # Progreso + Log en vivo
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Listo para iniciar")
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Configurá las opciones y presioná <b>Iniciar Scraping</b>.")
        self.status_lbl.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        root.addWidget(self.status_lbl)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(140)
        self.log_edit.setStyleSheet(
            "QPlainTextEdit { background-color: #10131b; border: 1px solid #282f42; "
            "border-radius: 6px; font-family: Consolas, monospace; font-size: 8.5pt; color: #cbd5e1; }"
        )
        root.addWidget(self.log_edit, 1)

        # Botonera inferior
        btns = QHBoxLayout()
        self.btn_start = QPushButton("🚀 Iniciar Scraping")
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(34)
        self.btn_start.clicked.connect(self._on_start_clicked)

        self.btn_cancel = QPushButton("Cerrar")
        self.btn_cancel.clicked.connect(self._on_cancel_or_close)

        btns.addStretch()
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_cancel)
        root.addLayout(btns)

        self._update_provider_hint()

    def _update_provider_hint(self):
        mode = str(self.provider_combo.currentData() or "auto")
        if mode == "screenscraper":
            if self.config.has_screenscraper_user_credentials:
                rem_txt = "recordado" if self.config.ss_remember else "solo esta sesión"
                self.provider_hint_lbl.setText(
                    f"✓ ScreenScraper listo — Usuario: <b>{self.config.ss_ssid}</b> ({rem_txt})."
                )
                self.provider_hint_lbl.setStyleSheet("color: #86efac; font-size: 8.5pt;")
            elif self.config.has_screenscraper_dev_credentials:
                self.provider_hint_lbl.setText("✓ ScreenScraper listo con credenciales de API configuradas.")
                self.provider_hint_lbl.setStyleSheet("color: #86efac; font-size: 8.5pt;")
            else:
                self.provider_hint_lbl.setText(
                    "ℹ ScreenScraper solicita tu usuario y contraseña (te los pedirá al iniciar o desde '⚙ Credenciales…')."
                )
                self.provider_hint_lbl.setStyleSheet("color: #fcd34d; font-size: 8.5pt;")
        elif mode == "auto":
            ss_state = "activo" if self.config.has_screenscraper_credentials else "sin sesión (usará ADB + Libretro)"
            self.provider_hint_lbl.setText(f"Modo automático — ScreenScraper: {ss_state}.")
            self.provider_hint_lbl.setStyleSheet("color: #93c5fd; font-size: 8.5pt;")
        elif mode == "libretro":
            self.provider_hint_lbl.setText("Libretro descarga PNG gratuitos de carátulas (Boxart) y logos (Wheel) sin claves.")
            self.provider_hint_lbl.setStyleSheet("color: #86efac; font-size: 8.5pt;")
        else:
            self.provider_hint_lbl.setText("ArcadeDB descarga media y videos MP4 de MAME/Arcade sin necesidad de cuenta.")
            self.provider_hint_lbl.setStyleSheet("color: #86efac; font-size: 8.5pt;")

    def _open_settings(self):
        dlg = ScraperSettingsDialog(self.db, self, current_config=self.config)
        if dlg.exec():
            self.config = dlg.config
            self.workers_spin.setValue(self.config.normalized_workers())
            self.chk_meta.setChecked(self.config.update_empty_metadata)
            self._update_provider_hint()

    def _pick_media_root(self):
        cur = self.media_root_edit.text().strip()
        chosen = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta raíz para media", cur)
        if chosen:
            self.media_root_edit.setText(chosen.replace("\\", "/"))

    def _refresh_folder_warning(self):
        needs_folder = any(
            chk.isChecked() and not sp.folder_exists
            for sp in self.summary.specs
            if (chk := self._slot_checks.get(sp.key)) is not None
        )
        self.folder_box.setVisible(needs_folder)

    def _selected_slot_keys(self) -> list[str]:
        return [sp.key for sp in self.summary.specs if (c := self._slot_checks.get(sp.key)) and c.isChecked()]

    def _collect_target_roms(self, slot_keys: list[str]) -> list[RomAuditResult]:
        scope = str(self.scope_combo.currentData() or "missing")
        if scope == "filtered":
            pool = self.visible_roms
        else:
            pool = self.summary.results

        target_list: list[RomAuditResult] = []
        overwrite = self.chk_overwrite.isChecked()
        for rom in pool:
            if rom.is_menu_target or not rom.stem:
                continue
            if scope == "missing" and not overwrite:
                has_missing = any(
                    rom.slots.get(k) and rom.slots[k].status != "ok"
                    for k in slot_keys
                )
                if not has_missing:
                    continue
            target_list.append(rom)
        return target_list

    def _on_start_clicked(self):
        slot_keys = self._selected_slot_keys()
        if not slot_keys:
            QMessageBox.information(self, "Slots requeridos", "Seleccioná al menos un tipo de medio para scrapear.")
            return

        # Crear carpetas faltantes si el usuario lo solicitó
        missing_folder_specs = [
            sp for sp in self.summary.specs if sp.key in slot_keys and not sp.folder_exists
        ]
        if missing_folder_specs:
            if self.chk_auto_mkdir.isChecked():
                base_root = self.media_root_edit.text().strip()
                if not base_root:
                    QMessageBox.warning(
                        self,
                        "Carpeta raíz requerida",
                        "Indicá una carpeta base válida para crear las subcarpetas de media faltantes.",
                    )
                    return
                try:
                    updated_fields = ensure_media_folders_for_list(
                        self.db,
                        self.list_row,
                        self.summary.specs,
                        slot_keys,
                        base_root,
                    )
                    if updated_fields:
                        self.has_folder_changes = True
                        self.log_edit.appendPlainText(f"📁 Carpetas preparadas en: {base_root}")
                except Exception as exc:
                    QMessageBox.critical(self, "Error creando carpetas", str(exc))
                    return
            else:
                names = ", ".join(sp.label for sp in missing_folder_specs)
                QMessageBox.warning(
                    self,
                    "Carpetas sin configurar",
                    f"Los siguientes slots no tienen carpeta configurada y no serán descargados:\n{names}",
                )

        targets = self._collect_target_roms(slot_keys)
        if not targets:
            QMessageBox.information(
                self,
                "Nada pendiente",
                "Todas las ROMs del alcance seleccionado ya tienen completos los slots elegidos.",
            )
            return

        provider_mode = str(self.provider_combo.currentData() or "auto")
        if provider_mode == "screenscraper" and not self.config.has_screenscraper_credentials:
            login_dlg = ScreenScraperLoginDialog(self.db, self.config, self)
            if not login_dlg.exec():
                return
            self.config = login_dlg.config
            self._update_provider_hint()

        if self.release_media_cb:
            self.release_media_cb()

        opts = ScrapeJobOptions(
            system_key=str(self.system_combo.currentData() or "snes"),
            provider_mode=provider_mode,
            target_slots=tuple(slot_keys),
            overwrite_existing=self.chk_overwrite.isChecked(),
            update_empty_metadata=self.chk_meta.isChecked(),
            overwrite_metadata=self.config.overwrite_metadata,
            only_filtered=(self.scope_combo.currentData() == "filtered"),
            max_workers=self.workers_spin.value(),
        )

        self.btn_start.setEnabled(False)
        self.btn_cancel.setText("⏹ Detener")
        self.progress_bar.setRange(0, len(targets))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0 / {len(targets)}")
        self.log_edit.clear()
        self.log_edit.appendPlainText(
            f"🚀 Iniciando scraping de {len(targets)} ROM(s) | Sistema: {opts.system_key} | Proveedor: {provider_mode}"
        )

        self._worker = BatchScrapeWorker(
            roms=targets,
            games_by_id=self.games_by_id,
            specs=self.summary.specs,
            options=opts,
            config=self.config,
            parent=self,
        )
        self._worker.rom_done.connect(self._on_rom_done)
        self._worker.finished_batch.connect(self._on_batch_finished)
        self._worker.failed.connect(self._on_batch_failed)
        self._worker.start()

    def _on_rom_done(self, outcome: RomScrapeOutcome, cur: int, total: int):
        if outcome.downloaded_slots:
            self.has_media_changes = True
        if outcome.metadata_updates and outcome.game_id:
            try:
                self.db.update_game(outcome.game_id, **outcome.metadata_updates)
                self.has_metadata_changes = True
            except Exception:
                pass

        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(min(cur, total))
        self.progress_bar.setFormat(f"{cur} / {total} ({int(round((cur / max(1, total)) * 100))}%)")
        self.status_lbl.setText(f"Procesando {cur}/{total}: <b>{outcome.title}</b>")

        if outcome.status == "downloaded":
            icon = "✅"
        elif outcome.status == "partial":
            icon = "🟨"
        elif outcome.status == "skipped":
            icon = "⏭"
        elif outcome.status == "cancelled":
            icon = "⏹"
        else:
            icon = "❌"
        prov_txt = f" [{outcome.provider_used}]" if outcome.provider_used else ""
        meta_txt = " +meta" if outcome.metadata_updates else ""
        self.log_edit.appendPlainText(f"{icon} {outcome.title}{prov_txt}{meta_txt} — {outcome.message}")

    def _on_batch_finished(self, batch_sum: BatchScrapeSummary):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setText("Cerrar")
        state_lbl = "Scraping cancelado por el usuario." if batch_sum.cancelled else "Scraping completado."
        self.status_lbl.setText(
            f"<b>{state_lbl}</b> Descargadas OK: <b>{batch_sum.downloaded_roms}</b> · "
            f"Parciales: <b>{batch_sum.partial_roms}</b> · Sin coincidencia: <b>{batch_sum.not_found_roms}</b> · "
            f"Archivos guardados: <b>{batch_sum.files_saved}</b>"
        )
        self.log_edit.appendPlainText(
            f"--- FIN: {batch_sum.files_saved} archivo(s) guardados, {batch_sum.metadata_enriched} juego(s) con metadatos ---"
        )

    def _on_batch_failed(self, err: str):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setText("Cerrar")
        self.status_lbl.setText(f"<span style='color:#f87171;'>Error: {err}</span>")
        self.log_edit.appendPlainText(f"❌ Error fatal: {err}")

    def _stop_worker_if_running(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2500)

    def _on_cancel_or_close(self):
        if self._worker and self._worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("Deteniendo…")
            self._worker.cancel()
            return
        self.accept() if (self.has_media_changes or self.has_metadata_changes or self.has_folder_changes) else self.reject()

    def closeEvent(self, event):
        self._stop_worker_if_running()
        super().closeEvent(event)


# =====================================================================
# 4. DIÁLOGO INTERACTIVO DE BÚSQUEDA Y DESCARGA PARA UNA ROM PUNTUAL
# =====================================================================
class SingleRomScrapeDialog(QDialog):
    """Permite buscar candidatos online, previsualizar imágenes y elegir qué slots descargar."""

    def __init__(
        self,
        db: Database,
        list_row: dict[str, Any],
        rom: RomAuditResult,
        game_row: dict[str, Any] | None,
        specs: list[MediaRequirementSpec],
        layout_name: str,
        release_media_cb: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self.list_row = dict(list_row)
        self.rom = rom
        self.game_row = dict(game_row) if game_row else {}
        self.specs = list(specs)
        self.specs_by_key = {s.key: s for s in specs}
        self.layout_name = layout_name
        self.release_media_cb = release_media_cb
        self.config = load_scraper_config(db)

        self._candidates: list[ScraperCandidate] = []
        self._search_worker: SingleRomSearchWorker | None = None
        self._dl_worker: SingleRomDownloadWorker | None = None
        self._thumb_worker: ThumbnailFetchWorker | None = None
        self._slot_checks: dict[str, QCheckBox] = {}
        self.downloaded_any = False
        self.metadata_updated = False

        self.setWindowTitle(f"Buscar media online — {rom.title}")
        self.setMinimumSize(860, 580)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # Barra de búsqueda
        search_bar = QHBoxLayout()
        search_bar.setSpacing(8)
        self.query_edit = QLineEdit(clean_rom_search_title(self.rom.title or self.rom.stem))
        self.query_edit.setPlaceholderText("Nombre del juego a buscar…")
        self.query_edit.returnPressed.connect(self.start_search)

        emu_row = self.db.get_default_emulator_for_list(int(self.list_row["id"])) if self.db else None
        detected = detect_system_for_list(self.list_row, self.layout_name, dict(emu_row) if emu_row else None)
        self.system_combo = QComboBox()
        for sys_obj in SYSTEM_CATALOG:
            self.system_combo.addItem(sys_obj.display_name, sys_obj.key)
        idx = self.system_combo.findData(detected.key)
        if idx >= 0:
            self.system_combo.setCurrentIndex(idx)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Todos (Auto)", "auto")
        self.provider_combo.addItem("Libretro", "libretro")
        self.provider_combo.addItem("ArcadeDB", "arcadedb")
        self.provider_combo.addItem("ScreenScraper", "screenscraper")

        self.btn_cfg = QPushButton("⚙ Cuenta")
        self.btn_cfg.setToolTip("Configurar usuario, contraseña y opciones de ScreenScraper")
        self.btn_cfg.clicked.connect(self._open_settings)

        self.btn_search = QPushButton("🔎 Buscar")
        self.btn_search.setObjectName("primary")
        self.btn_search.clicked.connect(self.start_search)

        search_bar.addWidget(QLabel("<b>Buscar:</b>"))
        search_bar.addWidget(self.query_edit, 2)
        search_bar.addWidget(self.system_combo, 1)
        search_bar.addWidget(self.provider_combo)
        search_bar.addWidget(self.btn_cfg)
        search_bar.addWidget(self.btn_search)
        root.addLayout(search_bar)

        self.status_lbl = QLabel(
            f"ROM: <code>{self.rom.stem}</code> — Presioná <b>Buscar</b> para consultar candidatos online."
        )
        self.status_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        root.addWidget(self.status_lbl)

        # Splitter: candidatos a la izquierda, detalle + preview a la derecha
        splitter = QSplitter(Qt.Horizontal)

        self.cand_table = QTableWidget()
        self.cand_table.setColumnCount(5)
        self.cand_table.setHorizontalHeaderLabels(["Título", "Fuente", "Año", "Score", "Assets"])
        configure_details_table(
            self.cand_table,
            col_widths=(240, 130, 65, 70, 140),
            hide_vertical_header=True,
        )
        self.cand_table.currentCellChanged.connect(self._on_candidate_selected)
        splitter.addWidget(self.cand_table)

        # Panel derecho
        right = QFrame()
        right.setStyleSheet("QFrame { background-color: #171a24; border: 1px solid #282f42; border-radius: 8px; }")
        r_vbox = QVBoxLayout(right)
        r_vbox.setContentsMargins(10, 10, 10, 10)
        r_vbox.setSpacing(8)

        self.cand_title_lbl = QLabel("Sin candidato seleccionado")
        self.cand_title_lbl.setFont(QFont("Segoe UI", 10.5, QFont.Bold))
        self.cand_title_lbl.setWordWrap(True)
        r_vbox.addWidget(self.cand_title_lbl)

        self.cand_meta_lbl = QLabel("—")
        self.cand_meta_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        self.cand_meta_lbl.setWordWrap(True)
        r_vbox.addWidget(self.cand_meta_lbl)

        # Selector rápido para previsualizar miniatura de imagen del candidato
        prev_ctrl = QHBoxLayout()
        prev_ctrl.addWidget(QLabel("Vista previa:"))
        self.preview_slot_combo = QComboBox()
        self.preview_slot_combo.currentIndexChanged.connect(self._load_selected_asset_thumb)
        prev_ctrl.addWidget(self.preview_slot_combo, 1)
        r_vbox.addLayout(prev_ctrl)

        self.thumb_lbl = QLabel("Sin vista previa")
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setMinimumHeight(170)
        self.thumb_lbl.setStyleSheet(
            "QLabel { background-color: #10131b; border: 1px dashed #31394f; border-radius: 6px; color: #64748b; }"
        )
        r_vbox.addWidget(self.thumb_lbl, 1)

        # Checkboxes de slots disponibles en el layout
        slots_grp = QGroupBox("Slots a descargar en sus carpetas:")
        sg_lay = QVBoxLayout(slots_grp)
        sg_lay.setSpacing(4)
        for sp in self.specs:
            slot_obj = self.rom.slots.get(sp.key)
            has_ok = bool(slot_obj and slot_obj.status == "ok")
            state_tag = "(Ya OK)" if has_ok else ("(Sin carpeta)" if not sp.folder_exists else "(Falta)")
            chk = QCheckBox(f"{sp.label} {state_tag}")
            chk.setEnabled(False)
            self._slot_checks[sp.key] = chk
            sg_lay.addWidget(chk)
        r_vbox.addWidget(slots_grp)

        self.chk_apply_meta = QCheckBox("Guardar también metadatos (Año, Fabricante, Género, Sinopsis)")
        self.chk_apply_meta.setChecked(True)
        r_vbox.addWidget(self.chk_apply_meta)

        splitter.addWidget(right)
        splitter.setSizes([470, 360])
        root.addWidget(splitter, 1)

        # Botonera
        btns = QHBoxLayout()
        btns.addStretch()
        self.btn_download = QPushButton("⬇ Descargar seleccionados")
        self.btn_download.setObjectName("primary")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._on_download_clicked)

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self._on_close)
        btns.addWidget(self.btn_download)
        btns.addWidget(btn_close)
        root.addLayout(btns)

    def _open_settings(self):
        dlg = ScraperSettingsDialog(self.db, self, current_config=self.config)
        if dlg.exec():
            self.config = dlg.config

    def start_search(self):
        provider_mode = str(self.provider_combo.currentData() or "auto")
        if provider_mode == "screenscraper" and not self.config.has_screenscraper_credentials:
            login_dlg = ScreenScraperLoginDialog(self.db, self.config, self)
            if not login_dlg.exec():
                return
            self.config = login_dlg.config

        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self._search_worker.wait(800)

        self.btn_search.setEnabled(False)
        self.btn_download.setEnabled(False)
        self.status_lbl.setText("⏳ Buscando candidatos en los proveedores seleccionados…")
        self.cand_table.setRowCount(0)
        self._candidates.clear()

        self._search_worker = SingleRomSearchWorker(
            query=self.query_edit.text().strip(),
            stem=self.rom.stem,
            rom_path=self.rom.rom_path,
            system_key=str(self.system_combo.currentData() or "snes"),
            provider_mode=str(self.provider_combo.currentData() or "auto"),
            target_slots=tuple(sp.key for sp in self.specs),
            config=self.config,
            parent=self,
        )
        self._search_worker.finished_search.connect(self._on_search_done)
        self._search_worker.failed.connect(self._on_search_failed)
        self._search_worker.start()

    def _on_search_done(self, candidates: list[ScraperCandidate]):
        self.btn_search.setEnabled(True)
        self._candidates = candidates
        with paused_table_sorting(self.cand_table, reenable=True):
            self.cand_table.setRowCount(len(candidates))
            for r_idx, cand in enumerate(candidates):
                it0 = SortableTableWidgetItem(cand.title)
                it0.setData(Qt.UserRole, r_idx)
                it1 = SortableTableWidgetItem(cand.provider_label)
                yr_raw = str(cand.year or "").strip()
                yr_key = int(yr_raw) if yr_raw.isdigit() else -1
                it2 = SortableTableWidgetItem(yr_raw or "—", sort_key=yr_key)
                score_pct = int(round(cand.match_score * 100))
                it3 = SortableTableWidgetItem(f"{score_pct}%", sort_key=float(cand.match_score))
                it4 = SortableTableWidgetItem(", ".join(cand.assets.keys()) or "Solo meta")
                self.cand_table.setItem(r_idx, 0, it0)
                self.cand_table.setItem(r_idx, 1, it1)
                self.cand_table.setItem(r_idx, 2, it2)
                self.cand_table.setItem(r_idx, 3, it3)
                self.cand_table.setItem(r_idx, 4, it4)

        if candidates:
            self.status_lbl.setText(f"Se encontraron <b>{len(candidates)}</b> candidato(s).")
            self.cand_table.selectRow(0)
        else:
            self.status_lbl.setText("No se encontraron coincidencias. Probá acortando el término de búsqueda.")

    def _on_search_failed(self, err: str):
        self.btn_search.setEnabled(True)
        self.status_lbl.setText(f"<span style='color:#f87171;'>Error al buscar: {err}</span>")

    def _current_candidate(self) -> ScraperCandidate | None:
        row = self.cand_table.currentRow()
        if row < 0:
            return None
        it0 = self.cand_table.item(row, 0)
        orig_idx = it0.data(Qt.UserRole) if it0 is not None else None
        idx = int(orig_idx) if orig_idx is not None else row
        if 0 <= idx < len(self._candidates):
            return self._candidates[idx]
        return None

    def _on_candidate_selected(self, row: int, _col: int, _pr: int, _pc: int):
        cand = self._current_candidate()
        if not cand:
            self.btn_download.setEnabled(False)
            return

        self.cand_title_lbl.setText(f"{cand.title}  [{cand.provider_label}]")
        meta_parts = [p for p in (cand.year, cand.manufacturer, cand.genre, cand.rating) if p]
        meta_head = " · ".join(meta_parts) if meta_parts else "Sin metadatos adicionales"
        notes_snip = f"\n{cand.notes[:220]}…" if cand.notes and len(cand.notes) > 220 else (f"\n{cand.notes}" if cand.notes else "")
        self.cand_meta_lbl.setText(meta_head + notes_snip)

        any_downloadable = False
        for sp in self.specs:
            chk = self._slot_checks.get(sp.key)
            if not chk:
                continue
            has_asset = sp.key in cand.assets
            can_dl = has_asset and sp.folder_exists and bool(self.rom.stem)
            chk.setEnabled(can_dl)
            slot_obj = self.rom.slots.get(sp.key)
            needs_it = not (slot_obj and slot_obj.status == "ok")
            chk.setChecked(can_dl and needs_it)
            if can_dl:
                any_downloadable = True

        self.btn_download.setEnabled(any_downloadable or bool(self.chk_apply_meta.isChecked()))

        self.preview_slot_combo.blockSignals(True)
        self.preview_slot_combo.clear()
        for k, asset in cand.assets.items():
            if asset.media_kind == "image":
                lbl = self.specs_by_key[k].label if k in self.specs_by_key else k.capitalize()
                self.preview_slot_combo.addItem(f"{lbl} ({asset.region.upper()})", k)
        self.preview_slot_combo.blockSignals(False)
        self._load_selected_asset_thumb()

    def _load_selected_asset_thumb(self):
        if self._thumb_worker and self._thumb_worker.isRunning():
            self._thumb_worker.cancel()
            self._thumb_worker.wait(500)

        cand = self._current_candidate()
        slot_k = self.preview_slot_combo.currentData()
        if not cand or not slot_k or slot_k not in cand.assets:
            self.thumb_lbl.setPixmap(QPixmap())
            self.thumb_lbl.setText("Sin vista previa de imagen")
            return

        url = cand.assets[slot_k].url
        self.thumb_lbl.setPixmap(QPixmap())
        self.thumb_lbl.setText("Cargando miniatura…")
        self._thumb_worker = ThumbnailFetchWorker(url, timeout=10.0, parent=self)
        self._thumb_worker.image_ready.connect(self._on_thumb_ready)
        self._thumb_worker.start()

    def _on_thumb_ready(self, _url: str, data: bytes):
        if not data:
            self.thumb_lbl.setText("No se pudo previsualizar esta imagen")
            return
        pix = QPixmap()
        if not pix.loadFromData(data):
            self.thumb_lbl.setText("Formato no válido en vista previa")
            return
        scaled = pix.scaled(self.thumb_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb_lbl.setText("")
        self.thumb_lbl.setPixmap(scaled)

    def _on_download_clicked(self):
        cand = self._current_candidate()
        if not cand:
            return
        chosen_slots = [k for k, c in self._slot_checks.items() if c.isEnabled() and c.isChecked()]
        if not chosen_slots and not self.chk_apply_meta.isChecked():
            QMessageBox.information(self, "Nada seleccionado", "Marcá al menos un medio o metadato para aplicar.")
            return

        if self.release_media_cb:
            self.release_media_cb()

        if self.chk_apply_meta.isChecked() and self.rom.game_id:
            meta_updates = CompositeScraperEngine.build_metadata_updates(
                self.game_row,
                cand,
                update_empty=True,
                overwrite=False,
            )
            if meta_updates:
                self.db.update_game(self.rom.game_id, **meta_updates)
                self.metadata_updated = True

        if not chosen_slots:
            QMessageBox.information(self, "Metadatos actualizados", "Se completaron los metadatos disponibles en la base.")
            self.accept()
            return

        self.btn_download.setEnabled(False)
        self.btn_search.setEnabled(False)
        self.status_lbl.setText(f"⬇ Descargando {len(chosen_slots)} archivo(s)…")

        self._dl_worker = SingleRomDownloadWorker(
            candidate=cand,
            stem=self.rom.stem,
            specs_by_key=self.specs_by_key,
            slot_keys=chosen_slots,
            overwrite=True,
            config=self.config,
            parent=self,
        )
        self._dl_worker.finished_download.connect(self._on_download_done)
        self._dl_worker.failed.connect(self._on_download_failed)
        self._dl_worker.start()

    def _on_download_done(self, downloaded: dict[str, str], failed: dict[str, str]):
        self.btn_download.setEnabled(True)
        self.btn_search.setEnabled(True)
        if downloaded:
            self.downloaded_any = True
        msg_parts = []
        if downloaded:
            msg_parts.append(f"Descargados correctamente ({len(downloaded)}): {', '.join(downloaded.keys())}")
        if failed:
            errs = "\n".join(f"• {k}: {v}" for k, v in failed.items())
            msg_parts.append(f"No descargados ({len(failed)}):\n{errs}")
        QMessageBox.information(self, "Resultado del Scraping", "\n\n".join(msg_parts) or "Sin cambios.")
        if downloaded:
            self.accept()

    def _on_download_failed(self, err: str):
        self.btn_download.setEnabled(True)
        self.btn_search.setEnabled(True)
        QMessageBox.critical(self, "Error descargando", err)

    def _stop_workers(self):
        for w in (self._search_worker, self._dl_worker, self._thumb_worker):
            if w and w.isRunning():
                w.cancel()
                w.wait(1500)

    def _on_close(self):
        self._stop_workers()
        self.accept() if (self.downloaded_any or self.metadata_updated) else self.reject()

    def closeEvent(self, event):
        self._stop_workers()
        super().closeEvent(event)
