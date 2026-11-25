"""
Diálogos de configuración, scraping en lote y búsqueda interactiva por ROM
para el Rom Manager de PlayNexus.
"""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
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
from playnexus.i18n import tr
from playnexus.services.media import IMAGE_EXTS, PDF_EXTS, VIDEO_EXTS, find_media_file
from playnexus.services.rom_manager import (
    AuditSummary,
    MediaRequirementSpec,
    RomAuditResult,
    ensure_media_folders_for_list,
    format_file_size,
    get_db_field_for_media_key,
    get_list_folder_for_media_key,
    get_media_slot_label,
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
        self.setWindowTitle(tr("scraper_dlg.ss_login_title", "Sign In — ScreenScraper.fr"))
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        intro = QLabel(
            tr(
                "scraper_dlg.ss_login_intro",
                "Enter your <a href='https://www.screenscraper.fr'>screenscraper.fr</a> "
                "<b>username</b> and <b>password</b> to continue.",
            )
        )
        intro.setOpenExternalLinks(True)
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        root.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(8)
        self.ssid_edit = QLineEdit(self.config.ss_ssid)
        self.ssid_edit.setPlaceholderText(tr("scraper_dlg.ss_user_placeholder", "ScreenScraper username"))
        self.sspass_edit = QLineEdit(self.config.ss_sspassword)
        self.sspass_edit.setEchoMode(QLineEdit.Password)
        self.sspass_edit.setPlaceholderText(tr("scraper_dlg.ss_pass_placeholder", "ScreenScraper password"))

        form.addRow(tr("scraper_dlg.ss_user_label", "Username:"), self.ssid_edit)
        form.addRow(tr("scraper_dlg.ss_pass_label", "Password:"), self.sspass_edit)
        root.addLayout(form)

        opts = QHBoxLayout()
        self.chk_remember = QCheckBox(tr("scraper_dlg.ss_remember_cb", "Remember username and password"))
        self.chk_remember.setChecked(self.config.ss_remember)
        self.chk_show_pass = QCheckBox(tr("scraper_dlg.ss_show_pass_cb", "Show password"))
        self.chk_show_pass.toggled.connect(
            lambda show: self.sspass_edit.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)
        )
        opts.addWidget(self.chk_remember)
        opts.addStretch()
        opts.addWidget(self.chk_show_pass)
        root.addLayout(opts)

        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton(tr("scraper_dlg.btn_cancel", "Cancel"))
        btn_cancel.clicked.connect(self.reject)
        self.btn_accept = QPushButton(tr("scraper_dlg.btn_continue", "Continue"))
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
                tr("scraper_dlg.incomplete_data_title", "Incomplete Data"),
                tr("scraper_dlg.ss_login_incomplete_msg", "Enter both the ScreenScraper username and password."),
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
        self.setWindowTitle(tr("scraper_dlg.settings_title", "Online Scraper Settings"))
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
            tr(
                "scraper_dlg.settings_intro",
                "Configure online providers to automatically download media declared "
                "in each layout's <code>MEDIA_REQUIREMENTS</code> and fill in game metadata.",
            )
        )
        intro.setWordWrap(True)
        intro.setMinimumWidth(0)
        intro.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        body.addWidget(intro)

        # Preferencias generales
        gen_grp = QGroupBox(tr("scraper_dlg.general_prefs_group", "General Preferences"))
        form = QFormLayout(gen_grp)
        form.setSpacing(7)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem(tr("scraper_dlg.prov_auto", "Automatic (ArcadeDB / ScreenScraper / Libretro)"), "auto")
        self.provider_combo.addItem(tr("scraper_dlg.prov_libretro", "Libretro Thumbnails (Free, no key — Boxart & Wheel)"), "libretro")
        self.provider_combo.addItem(tr("scraper_dlg.prov_arcadedb", "Arcade Database / ADB (Free — MAME / Arcade + Video)"), "arcadedb")
        self.provider_combo.addItem(tr("scraper_dlg.prov_screenscraper", "ScreenScraper API v2 (Full Media + Metadata)"), "screenscraper")
        form.addRow(tr("scraper_dlg.default_provider_label", "Default provider:"), self.provider_combo)

        self.regions_edit = QLineEdit()
        self.regions_edit.setPlaceholderText("us, wor, ss, eu, es, jp")
        self.regions_edit.setToolTip(
            tr("scraper_dlg.regions_tip", "Comma-separated region priority order (e.g., es, eu, us, wor, jp)")
        )
        form.addRow(tr("scraper_dlg.region_priority_label", "Region priority:"), self.regions_edit)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem(tr("scraper_dlg.lang_es", "Spanish (es)"), "es")
        self.lang_combo.addItem(tr("scraper_dlg.lang_en", "English (en)"), "en")
        self.lang_combo.addItem(tr("scraper_dlg.lang_fr", "French (fr)"), "fr")
        form.addRow(tr("scraper_dlg.meta_lang_label", "Synopsis/genre language:"), self.lang_combo)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 4)
        self.workers_spin.setToolTip(
            tr("scraper_dlg.workers_tip", "Number of simultaneous downloads in batch mode (1 to 4)")
        )
        form.addRow(tr("scraper_dlg.workers_label", "Parallel threads:"), self.workers_spin)

        self.chk_hd_video = QCheckBox(
            tr("scraper_dlg.chk_hd_video", "Prefer HD videos when available (ArcadeDB)")
        )
        self.chk_empty_meta = QCheckBox(
            tr("scraper_dlg.chk_empty_meta", "Fill empty database fields (year, genre, notes…)")
        )
        self.chk_overwrite_meta = QCheckBox(
            tr("scraper_dlg.chk_overwrite_meta", "Overwrite existing metadata when scraping")
        )
        self.chk_cache = QCheckBox(
            tr("scraper_dlg.chk_cache", "Use local cache in config/scraper_cache/ (speeds up rescans)")
        )

        form.addRow("", self.chk_hd_video)
        form.addRow("", self.chk_empty_meta)
        form.addRow("", self.chk_overwrite_meta)
        form.addRow("", self.chk_cache)
        body.addWidget(gen_grp)

        # Credenciales ScreenScraper (Miembro + API Dev + Debug, cifrado portátil en config/.key)
        ss_grp = QGroupBox(tr("scraper_dlg.ss_group_title", "ScreenScraper.fr Account and API"))
        ss_vbox = QVBoxLayout(ss_grp)
        ss_vbox.setSpacing(6)

        ss_note = QLabel(
            tr(
                "scraper_dlg.ss_note",
                "ScreenScraper offers 3D/2D box art, HD wheels, carts/discs, flyers, marquees, "
                "bezels, videos, and PDF manuals. All credentials are stored encrypted in "
                "<code>config/settings.txt</code> (portable key in <code>config/.key</code>). "
                "Without an account, <b>Libretro Thumbnails</b> and <b>ArcadeDB</b> still work for free.",
            )
        )
        ss_note.setWordWrap(True)
        ss_note.setMinimumWidth(0)
        ss_note.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        ss_vbox.addWidget(ss_note)

        ss_form = QFormLayout()
        ss_form.setSpacing(6)
        self.ss_ssid_edit = QLineEdit()
        self.ss_ssid_edit.setPlaceholderText(tr("scraper_dlg.ss_ssid_placeholder", "Member username (ssid)"))
        self.ss_sspass_edit = QLineEdit()
        self.ss_sspass_edit.setEchoMode(QLineEdit.Password)
        self.ss_sspass_edit.setPlaceholderText(tr("scraper_dlg.ss_sspass_placeholder", "Member password (sspassword)"))

        self.ss_devid_edit = QLineEdit()
        self.ss_devid_edit.setPlaceholderText(
            tr("scraper_dlg.ss_devid_placeholder", "Dev username (devid) — developer account")
        )
        self.ss_devpass_edit = QLineEdit()
        self.ss_devpass_edit.setEchoMode(QLineEdit.Password)
        self.ss_devpass_edit.setPlaceholderText(tr("scraper_dlg.ss_devpass_placeholder", "Dev password (devpassword)"))
        self.ss_devdebug_edit = QLineEdit()
        self.ss_devdebug_edit.setEchoMode(QLineEdit.Password)
        self.ss_devdebug_edit.setPlaceholderText(
            tr("scraper_dlg.ss_devdebug_placeholder", "Debug password (devdebugpassword) — optional")
        )

        ss_opts_grid = QGridLayout()
        ss_opts_grid.setContentsMargins(0, 2, 0, 0)
        ss_opts_grid.setHorizontalSpacing(14)
        ss_opts_grid.setVerticalSpacing(4)
        self.chk_remember_ss = QCheckBox(tr("scraper_dlg.ss_remember_cb", "Remember username and password"))
        self.chk_show_pass = QCheckBox(tr("scraper_dlg.ss_show_passwords_cb", "Show passwords"))
        self.chk_show_pass.toggled.connect(self._toggle_passwords)
        self.chk_debug_mode = QCheckBox(tr("scraper_dlg.ss_debug_mode_cb", "API Debug Mode (max 100/day)"))
        self.chk_debug_mode.setToolTip(
            tr(
                "scraper_dlg.ss_debug_mode_tip",
                "Sends devdebugpassword in test queries and bypasses ScreenScraper local cache.",
            )
        )
        ss_opts_grid.addWidget(self.chk_remember_ss, 0, 0)
        ss_opts_grid.addWidget(self.chk_show_pass, 0, 1)
        ss_opts_grid.addWidget(self.chk_debug_mode, 1, 0, 1, 2)

        ss_form.addRow(tr("scraper_dlg.ss_user_label", "Username:"), self.ss_ssid_edit)
        ss_form.addRow(tr("scraper_dlg.ss_pass_label", "Password:"), self.ss_sspass_edit)
        ss_form.addRow(tr("scraper_dlg.ss_devid_label", "Dev Username (devid):"), self.ss_devid_edit)
        ss_form.addRow(tr("scraper_dlg.ss_devpass_label", "Dev Password:"), self.ss_devpass_edit)
        ss_form.addRow(tr("scraper_dlg.ss_devdebug_label", "Debug Password:"), self.ss_devdebug_edit)
        ss_form.addRow("", ss_opts_grid)
        ss_vbox.addLayout(ss_form)
        body.addWidget(ss_grp)

        # Caché local
        bottom_row = QHBoxLayout()
        self.cache_lbl = QLabel()
        self.cache_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        self._refresh_cache_label()

        btn_clear_cache = QPushButton(tr("scraper_dlg.btn_clear_cache", "🧹 Clear Cache"))
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
        btn_cancel = QPushButton(tr("scraper_dlg.btn_cancel", "Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton(tr("scraper_dlg.btn_save_settings", "💾 Save Settings"))
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
        self.cache_lbl.setText(
            tr("scraper_dlg.cache_status", "Local cache: {count} file(s) ({size})", count=cnt, size=format_file_size(b))
        )

    def _on_clear_cache(self):
        cnt, b = clear_scraper_cache()
        self._refresh_cache_label()
        QMessageBox.information(
            self,
            tr("scraper_dlg.cache_cleared_title", "Cache Cleared"),
            tr("scraper_dlg.cache_cleared_msg", "Deleted {count} cache file(s) ({size}).", count=cnt, size=format_file_size(b)),
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

        self.setWindowTitle(tr("scraper_dlg.batch_title", "Scrape Online Media — {name}", name=summary.list_name))
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
            tr(
                "scraper_dlg.batch_header",
                "<b>List:</b> {list_name}  ·  <b>Layout:</b> {layout_name}  ·  <b>Total ROMs:</b> {total}",
                list_name=self.summary.list_name,
                layout_name=self.summary.layout_name,
                total=self.summary.total_roms,
            )
        )
        lbl_head.setStyleSheet("color: #e2e8f0; font-size: 9.5pt;")
        lbl_sub = QLabel(
            tr(
                "scraper_dlg.batch_sub",
                "<b>Only</b> media types declared in the selected layout's "
                "<code>MEDIA_REQUIREMENTS</code> will be searched and downloaded.",
            )
        )
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        lbl_sub.setWordWrap(True)
        b_lay.addWidget(lbl_head)
        b_lay.addWidget(lbl_sub)
        root.addWidget(banner)

        # Configuración del trabajo
        cfg_grp = QGroupBox(tr("scraper_dlg.batch_cfg_group", "Download Parameters"))
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
        cfg_form.addRow(tr("scraper_dlg.detected_system_label", "Detected system:"), self.system_combo)

        prov_row = QHBoxLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItem(
            tr("scraper_dlg.batch_prov_auto", "Automatic (ArcadeDB + ScreenScraper + Libretro)"), "auto"
        )
        self.provider_combo.addItem(
            tr("scraper_dlg.prov_libretro", "Libretro Thumbnails (Free, no key — Boxart & Wheel)"), "libretro"
        )
        self.provider_combo.addItem(
            tr("scraper_dlg.prov_arcadedb", "Arcade Database / ADB (Free — MAME / Arcade + Video)"), "arcadedb"
        )
        self.provider_combo.addItem(
            tr("scraper_dlg.batch_prov_ss", "ScreenScraper.fr (Username and Password)"), "screenscraper"
        )
        p_idx = self.provider_combo.findData(self.config.preferred_provider)
        if p_idx >= 0:
            self.provider_combo.setCurrentIndex(p_idx)
        self.provider_combo.currentIndexChanged.connect(self._update_provider_hint)

        self.btn_cfg = QPushButton(tr("scraper_dlg.btn_credentials", "⚙ Credentials…"))
        self.btn_cfg.clicked.connect(self._open_settings)
        prov_row.addWidget(self.provider_combo, 1)
        prov_row.addWidget(self.btn_cfg)
        cfg_form.addRow(tr("scraper_dlg.online_source_label", "Online source:"), prov_row)

        self.provider_hint_lbl = QLabel()
        self.provider_hint_lbl.setWordWrap(True)
        self.provider_hint_lbl.setStyleSheet("color: #93c5fd; font-size: 8.5pt;")
        cfg_form.addRow("", self.provider_hint_lbl)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem(
            tr("scraper_dlg.scope_missing", "Only ROMs missing media in selected slots"), "missing"
        )
        self.scope_combo.addItem(
            tr("scraper_dlg.scope_filtered", "Only ROMs visible under current filter ({count})", count=len(self.visible_roms)),
            "filtered",
        )
        self.scope_combo.addItem(
            tr("scraper_dlg.scope_all", "All ROMs in the list ({count})", count=len(self.summary.results)),
            "all",
        )
        cfg_form.addRow(tr("scraper_dlg.scope_label", "Scope:"), self.scope_combo)

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
            folder_warn = tr("scraper_dlg.slot_no_folder_tag", " [No folder]") if not spec.folder_exists else ""
            chk = QCheckBox(
                tr(
                    "scraper_dlg.batch_slot_check",
                    "{star}{label} (missing {miss}){folder_warn}",
                    star=star,
                    label=spec.label,
                    miss=miss,
                    folder_warn=folder_warn,
                )
            )
            chk.setChecked(miss > 0 or not spec.folder_exists)
            chk.toggled.connect(self._refresh_folder_warning)
            self._slot_checks[spec.key] = chk
            slots_grid.addWidget(chk, idx // 2, idx % 2)
        cfg_form.addRow(tr("scraper_dlg.layout_media_label", "Layout media:"), slots_widget)

        # Panel opcional de auto-creación de carpetas faltantes
        self.folder_box = QFrame()
        self.folder_box.setStyleSheet(
            "QFrame { background-color: #241f18; border: 1px solid #6b4f1d; border-radius: 6px; padding: 6px; }"
        )
        fb_lay = QVBoxLayout(self.folder_box)
        fb_lay.setContentsMargins(8, 6, 8, 6)
        fb_lay.setSpacing(6)
        fb_lbl = QLabel(
            tr(
                "scraper_dlg.folder_box_warning",
                "⚠ Some selected slots have no folder configured in the list. "
                "Specify the base folder to create subfolders automatically:",
            )
        )
        fb_lbl.setWordWrap(True)
        fb_lbl.setStyleSheet("color: #fcd34d; font-size: 8.5pt;")
        fb_lay.addWidget(fb_lbl)

        fb_row = QHBoxLayout()
        self.media_root_edit = QLineEdit(suggest_media_root_for_list(self.list_row))
        self.media_root_edit.setPlaceholderText(
            tr("scraper_dlg.media_root_placeholder", "E.g.: C:/Roms/SNES/media")
        )
        btn_pick_root = QPushButton(tr("scraper_dlg.btn_browse_folder", "📁 Browse…"))
        btn_pick_root.clicked.connect(self._pick_media_root)
        self.chk_auto_mkdir = QCheckBox(tr("scraper_dlg.chk_auto_mkdir", "Create subfolders on start"))
        self.chk_auto_mkdir.setChecked(True)
        fb_row.addWidget(self.media_root_edit, 1)
        fb_row.addWidget(btn_pick_root)
        fb_lay.addLayout(fb_row)
        fb_lay.addWidget(self.chk_auto_mkdir)
        cfg_form.addRow("", self.folder_box)

        # Opciones extra
        opts_row = QHBoxLayout()
        self.chk_overwrite = QCheckBox(tr("scraper_dlg.chk_overwrite", "Overwrite existing files"))
        self.chk_meta = QCheckBox(tr("scraper_dlg.chk_meta", "Fill empty metadata"))
        self.chk_meta.setChecked(self.config.update_empty_metadata)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 4)
        self.workers_spin.setValue(self.config.normalized_workers())
        self.workers_spin.setPrefix(tr("scraper_dlg.workers_prefix", "Threads: "))
        opts_row.addWidget(self.chk_overwrite)
        opts_row.addWidget(self.chk_meta)
        opts_row.addStretch()
        opts_row.addWidget(self.workers_spin)
        cfg_form.addRow(tr("scraper_dlg.options_label", "Options:"), opts_row)

        root.addWidget(cfg_grp)

        # Progreso + Log en vivo
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(tr("scraper_dlg.progress_ready", "Ready to start"))
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel(
            tr("scraper_dlg.batch_ready_hint", "Configure the options and press <b>Start Scraping</b>.")
        )
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
        self.btn_start = QPushButton(tr("scraper_dlg.btn_start_scrape", "🚀 Start Scraping"))
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(34)
        self.btn_start.clicked.connect(self._on_start_clicked)

        self.btn_cancel = QPushButton(tr("scraper_dlg.btn_close", "Close"))
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
                rem_txt = (
                    tr("scraper_dlg.ss_remembered", "remembered")
                    if self.config.ss_remember
                    else tr("scraper_dlg.ss_session_only", "this session only")
                )
                self.provider_hint_lbl.setText(
                    tr(
                        "scraper_dlg.hint_ss_user_ready",
                        "✓ ScreenScraper ready — User: <b>{user}</b> ({rem}).",
                        user=self.config.ss_ssid,
                        rem=rem_txt,
                    )
                )
                self.provider_hint_lbl.setStyleSheet("color: #86efac; font-size: 8.5pt;")
            elif self.config.has_screenscraper_dev_credentials:
                self.provider_hint_lbl.setText(
                    tr("scraper_dlg.hint_ss_dev_ready", "✓ ScreenScraper ready with configured API credentials.")
                )
                self.provider_hint_lbl.setStyleSheet("color: #86efac; font-size: 8.5pt;")
            else:
                self.provider_hint_lbl.setText(
                    tr(
                        "scraper_dlg.hint_ss_needs_login",
                        "ℹ ScreenScraper requires your username and password (it will prompt on start or via '⚙ Credentials…').",
                    )
                )
                self.provider_hint_lbl.setStyleSheet("color: #fcd34d; font-size: 8.5pt;")
        elif mode == "auto":
            ss_state = (
                tr("scraper_dlg.ss_state_active", "active")
                if self.config.has_screenscraper_credentials
                else tr("scraper_dlg.ss_state_inactive", "not signed in (will use ADB + Libretro)")
            )
            self.provider_hint_lbl.setText(
                tr("scraper_dlg.hint_auto_mode", "Automatic mode — ScreenScraper: {state}.", state=ss_state)
            )
            self.provider_hint_lbl.setStyleSheet("color: #93c5fd; font-size: 8.5pt;")
        elif mode == "libretro":
            self.provider_hint_lbl.setText(
                tr(
                    "scraper_dlg.hint_libretro",
                    "Libretro downloads free PNG box art (Boxart) and logos (Wheel) without keys.",
                )
            )
            self.provider_hint_lbl.setStyleSheet("color: #86efac; font-size: 8.5pt;")
        else:
            self.provider_hint_lbl.setText(
                tr(
                    "scraper_dlg.hint_arcadedb",
                    "ArcadeDB downloads MAME/Arcade media and MP4 videos without needing an account.",
                )
            )
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
        chosen = QFileDialog.getExistingDirectory(
            self,
            tr("scraper_dlg.pick_media_root_title", "Select root folder for media"),
            cur,
        )
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
            QMessageBox.information(
                self,
                tr("scraper_dlg.slots_required_title", "Slots Required"),
                tr("scraper_dlg.slots_required_msg", "Select at least one media type to scrape."),
            )
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
                        tr("scraper_dlg.root_required_title", "Root Folder Required"),
                        tr(
                            "scraper_dlg.root_required_msg",
                            "Specify a valid base folder to create the missing media subfolders.",
                        ),
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
                        self.log_edit.appendPlainText(
                            tr("scraper_dlg.log_folders_prepared", "📁 Folders prepared at: {path}", path=base_root)
                        )
                except Exception as exc:
                    QMessageBox.critical(
                        self, tr("scraper_dlg.mkdir_error_title", "Error Creating Folders"), str(exc)
                    )
                    return
            else:
                names = ", ".join(sp.label for sp in missing_folder_specs)
                QMessageBox.warning(
                    self,
                    tr("scraper_dlg.unconfigured_folders_title", "Unconfigured Folders"),
                    tr(
                        "scraper_dlg.unconfigured_folders_msg",
                        "The following slots have no folder configured and will not be downloaded:\n{names}",
                        names=names,
                    ),
                )

        targets = self._collect_target_roms(slot_keys)
        if not targets:
            QMessageBox.information(
                self,
                tr("scraper_dlg.nothing_pending_title", "Nothing Pending"),
                tr(
                    "scraper_dlg.nothing_pending_msg",
                    "All ROMs in the selected scope already have the chosen slots complete.",
                ),
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
        self.btn_cancel.setText(tr("scraper_dlg.btn_stop", "⏹ Stop"))
        self.progress_bar.setRange(0, len(targets))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0 / {len(targets)}")
        self.log_edit.clear()
        self.log_edit.appendPlainText(
            tr(
                "scraper_dlg.log_batch_start",
                "🚀 Starting scraping of {count} ROM(s) | System: {sys} | Provider: {prov}",
                count=len(targets),
                sys=opts.system_key,
                prov=provider_mode,
            )
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
        self.status_lbl.setText(
            tr(
                "scraper_dlg.batch_processing",
                "Processing {cur}/{total}: <b>{title}</b>",
                cur=cur,
                total=total,
                title=outcome.title,
            )
        )

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
        self.btn_cancel.setText(tr("scraper_dlg.btn_close", "Close"))
        state_lbl = (
            tr("scraper_dlg.batch_cancelled", "Scraping cancelled by user.")
            if batch_sum.cancelled
            else tr("scraper_dlg.batch_completed", "Scraping completed.")
        )
        self.status_lbl.setText(
            tr(
                "scraper_dlg.batch_summary_html",
                "<b>{state}</b> Downloaded OK: <b>{ok}</b> · Partial: <b>{partial}</b> · "
                "No match: <b>{not_found}</b> · Files saved: <b>{saved}</b>",
                state=state_lbl,
                ok=batch_sum.downloaded_roms,
                partial=batch_sum.partial_roms,
                not_found=batch_sum.not_found_roms,
                saved=batch_sum.files_saved,
            )
        )
        self.log_edit.appendPlainText(
            tr(
                "scraper_dlg.log_batch_end",
                "--- END: {saved} file(s) saved, {meta} game(s) with metadata ---",
                saved=batch_sum.files_saved,
                meta=batch_sum.metadata_enriched,
            )
        )

    def _on_batch_failed(self, err: str):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setText(tr("scraper_dlg.btn_close", "Close"))
        self.status_lbl.setText(tr("scraper_dlg.batch_error_html", "<span style='color:#f87171;'>Error: {err}</span>", err=err))
        self.log_edit.appendPlainText(tr("scraper_dlg.log_fatal_error", "❌ Fatal error: {err}", err=err))

    def _stop_worker_if_running(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2500)

    def _on_cancel_or_close(self):
        if self._worker and self._worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText(tr("scraper_dlg.btn_stopping", "Stopping…"))
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
        self._extra_rows: dict[str, dict[str, Any]] = {}
        self._custom_extra_inputs: dict[str, str] = {}
        self._media_root = suggest_media_root_for_list(self.list_row)
        self.downloaded_any = False
        self.metadata_updated = False
        self.has_folder_changes = False

        self.setWindowTitle(tr("scraper_dlg.single_title", "Search online media — {title}", title=rom.title))
        self.setMinimumSize(900, 620)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # Barra de búsqueda
        search_bar = QHBoxLayout()
        search_bar.setSpacing(8)
        self.query_edit = QLineEdit(clean_rom_search_title(self.rom.title or self.rom.stem))
        self.query_edit.setPlaceholderText(tr("scraper_dlg.single_query_placeholder", "Game title to search…"))
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
        self.provider_combo.addItem(tr("scraper_dlg.single_prov_all", "All (Auto)"), "auto")
        self.provider_combo.addItem("Libretro", "libretro")
        self.provider_combo.addItem("ArcadeDB", "arcadedb")
        self.provider_combo.addItem("ScreenScraper", "screenscraper")

        self.btn_cfg = QPushButton(tr("scraper_dlg.btn_account", "⚙ Account"))
        self.btn_cfg.setToolTip(tr("scraper_dlg.tip_account", "Configure ScreenScraper username, password, and options"))
        self.btn_cfg.clicked.connect(self._open_settings)

        self.btn_search = QPushButton(tr("scraper_dlg.btn_search", "🔎 Search"))
        self.btn_search.setObjectName("primary")
        self.btn_search.clicked.connect(self.start_search)

        search_bar.addWidget(QLabel(tr("scraper_dlg.search_label", "<b>Search:</b>")))
        search_bar.addWidget(self.query_edit, 2)
        search_bar.addWidget(self.system_combo, 1)
        search_bar.addWidget(self.provider_combo)
        search_bar.addWidget(self.btn_cfg)
        search_bar.addWidget(self.btn_search)
        root.addLayout(search_bar)

        self.status_lbl = QLabel(
            tr(
                "scraper_dlg.single_ready_status",
                "ROM: <code>{stem}</code> — Press <b>Search</b> to query online candidates.",
                stem=self.rom.stem,
            )
        )
        self.status_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        root.addWidget(self.status_lbl)

        # Splitter: candidatos a la izquierda, detalle + preview a la derecha
        splitter = QSplitter(Qt.Horizontal)

        self.cand_table = QTableWidget()
        self.cand_table.setColumnCount(5)
        self.cand_table.setHorizontalHeaderLabels(
            [
                tr("scraper_dlg.col_title", "Title"),
                tr("scraper_dlg.col_source", "Source"),
                tr("scraper_dlg.col_year", "Year"),
                tr("scraper_dlg.col_score", "Score"),
                tr("scraper_dlg.col_assets", "Assets"),
            ]
        )
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

        self.cand_title_lbl = QLabel(tr("scraper_dlg.no_candidate_selected", "No candidate selected"))
        self.cand_title_lbl.setFont(QFont("Segoe UI", 10.5, QFont.Bold))
        self.cand_title_lbl.setWordWrap(True)
        r_vbox.addWidget(self.cand_title_lbl)

        self.cand_meta_lbl = QLabel("—")
        self.cand_meta_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        self.cand_meta_lbl.setWordWrap(True)
        r_vbox.addWidget(self.cand_meta_lbl)

        # Selector rápido para previsualizar miniatura de imagen del candidato
        prev_ctrl = QHBoxLayout()
        prev_ctrl.addWidget(QLabel(tr("scraper_dlg.preview_label", "Preview:")))
        self.preview_slot_combo = QComboBox()
        self.preview_slot_combo.currentIndexChanged.connect(self._load_selected_asset_thumb)
        prev_ctrl.addWidget(self.preview_slot_combo, 1)
        r_vbox.addLayout(prev_ctrl)

        self.thumb_lbl = QLabel(tr("scraper_dlg.no_preview", "No preview"))
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setMinimumHeight(170)
        self.thumb_lbl.setStyleSheet(
            "QLabel { background-color: #10131b; border: 1px dashed #31394f; border-radius: 6px; color: #64748b; }"
        )
        r_vbox.addWidget(self.thumb_lbl, 1)

        # Checkboxes de slots del layout + medios adicionales del candidato
        slots_grp = QGroupBox(tr("scraper_dlg.slots_to_dl_group", "Slots to download into folders:"))
        sg_outer = QVBoxLayout(slots_grp)
        sg_outer.setContentsMargins(6, 6, 6, 6)
        sg_outer.setSpacing(4)

        slots_scroll = QScrollArea()
        slots_scroll.setWidgetResizable(True)
        slots_scroll.setFrameShape(QFrame.NoFrame)
        slots_scroll.setMinimumHeight(130)
        slots_scroll.setMaximumHeight(220)
        slots_inner = QWidget()
        sg_lay = QVBoxLayout(slots_inner)
        sg_lay.setContentsMargins(2, 2, 4, 2)
        sg_lay.setSpacing(4)

        for sp in self.specs:
            slot_obj = self.rom.slots.get(sp.key)
            has_ok = bool(slot_obj and slot_obj.status == "ok")
            state_tag = (
                tr("scraper_dlg.slot_tag_ok", "(Already OK)")
                if has_ok
                else (
                    tr("scraper_dlg.slot_tag_no_folder", "(No folder)")
                    if not sp.folder_exists
                    else tr("scraper_dlg.slot_tag_missing", "(Missing)")
                )
            )
            chk = QCheckBox(f"{sp.label} {state_tag}")
            chk.setEnabled(False)
            chk.toggled.connect(self._refresh_download_button)
            self._slot_checks[sp.key] = chk
            sg_lay.addWidget(chk)

        self._extra_slots_container = QWidget()
        self._extra_slots_layout = QVBoxLayout(self._extra_slots_container)
        self._extra_slots_layout.setContentsMargins(0, 6, 0, 0)
        self._extra_slots_layout.setSpacing(4)
        extra_hdr = QLabel(
            tr(
                "scraper_dlg.extra_media_header",
                "Other media found in candidate (folder inside Media):",
            )
        )
        extra_hdr.setStyleSheet("color: #93c5fd; font-size: 8pt; font-weight: 600;")
        extra_hdr.setWordWrap(True)
        self._extra_slots_layout.addWidget(extra_hdr)
        self._extra_slots_container.setVisible(False)
        sg_lay.addWidget(self._extra_slots_container)
        sg_lay.addStretch()

        slots_scroll.setWidget(slots_inner)
        sg_outer.addWidget(slots_scroll)
        r_vbox.addWidget(slots_grp)

        self.chk_apply_meta = QCheckBox(
            tr("scraper_dlg.chk_apply_meta", "Also save metadata (Year, Manufacturer, Genre, Synopsis)")
        )
        self.chk_apply_meta.setChecked(True)
        self.chk_apply_meta.toggled.connect(self._refresh_download_button)
        r_vbox.addWidget(self.chk_apply_meta)

        splitter.addWidget(right)
        splitter.setSizes([470, 360])
        root.addWidget(splitter, 1)

        # Botonera
        btns = QHBoxLayout()
        btns.addStretch()
        self.btn_download = QPushButton(tr("scraper_dlg.btn_download_selected", "⬇ Download Selected"))
        self.btn_download.setObjectName("primary")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._on_download_clicked)

        btn_close = QPushButton(tr("scraper_dlg.btn_close", "Close"))
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
        self.status_lbl.setText(
            tr("scraper_dlg.searching_status", "⏳ Searching for candidates in selected providers…")
        )
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
                it4 = SortableTableWidgetItem(", ".join(cand.assets.keys()) or tr("scraper_dlg.assets_meta_only", "Meta only"))
                self.cand_table.setItem(r_idx, 0, it0)
                self.cand_table.setItem(r_idx, 1, it1)
                self.cand_table.setItem(r_idx, 2, it2)
                self.cand_table.setItem(r_idx, 3, it3)
                self.cand_table.setItem(r_idx, 4, it4)

        if candidates:
            self.status_lbl.setText(
                tr("scraper_dlg.search_found", "Found <b>{count}</b> candidate(s).", count=len(candidates))
            )
            self.cand_table.selectRow(0)
        else:
            self.status_lbl.setText(
                tr("scraper_dlg.search_not_found", "No matches found. Try shortening the search term.")
            )

    def _on_search_failed(self, err: str):
        self.btn_search.setEnabled(True)
        self.status_lbl.setText(
            tr("scraper_dlg.search_error_html", "<span style='color:#f87171;'>Search error: {err}</span>", err=err)
        )

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

    @staticmethod
    def _extensions_for_media_kind(kind: str) -> tuple[str, ...]:
        if kind == "video":
            return VIDEO_EXTS
        if kind == "pdf":
            return PDF_EXTS
        return IMAGE_EXTS

    def _clear_extra_slots(self):
        self._extra_rows.clear()
        while self._extra_slots_layout.count() > 1:
            item = self._extra_slots_layout.takeAt(1)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._extra_slots_container.setVisible(False)

    def _resolve_extra_default_input(self, key: str) -> str:
        if key in self._custom_extra_inputs:
            return self._custom_extra_inputs[key]
        explicit = get_list_folder_for_media_key(self.list_row, key)
        if key == "bezel" and not explicit:
            explicit = str(self.list_row.get("bezel_hud_path") or "").strip().replace("\\", "/")
        if explicit:
            if self._media_root:
                try:
                    exp_parent = os.path.normcase(os.path.abspath(str(Path(explicit).parent)))
                    root_norm = os.path.normcase(os.path.abspath(self._media_root))
                    if exp_parent == root_norm:
                        return Path(explicit).name
                except OSError:
                    pass
            return explicit
        return key

    def _resolve_extra_target_dir(self, raw_text: str) -> str:
        raw = str(raw_text or "").strip().replace("\\", "/")
        if not raw:
            return ""
        p = Path(raw)
        if p.is_absolute():
            return str(p).replace("\\", "/")
        if self._media_root:
            return str(Path(self._media_root) / raw).replace("\\", "/")
        return ""

    def _sync_extra_row_state(self, key: str):
        info = self._extra_rows.get(key)
        if not info:
            return
        chk: QCheckBox = info["chk"]
        dir_edit: QLineEdit = info["dir_edit"]
        status_lbl: QLabel = info["status"]
        media_kind: str = info["media_kind"]

        raw = dir_edit.text()
        self._custom_extra_inputs[key] = raw
        target_dir = self._resolve_extra_target_dir(raw)
        exts = self._extensions_for_media_kind(media_kind)

        if target_dir and self.rom.stem:
            if os.path.isdir(target_dir):
                exists_file = find_media_file(target_dir, self.rom.stem, exts)
                tag = (
                    tr("scraper_dlg.slot_tag_ok", "(Already OK)")
                    if exists_file
                    else tr("scraper_dlg.slot_tag_missing", "(Missing)")
                )
            else:
                tag = tr("scraper_dlg.slot_tag_create", "(Create)")
            dir_edit.setToolTip(target_dir)
            chk.setEnabled(True)
        else:
            tag = tr("scraper_dlg.slot_tag_no_folder", "(No folder)")
            dir_edit.setToolTip(
                tr("scraper_dlg.extra_folder_tip", "Subfolder name inside Media, or browse for a full folder path")
            )
            chk.setChecked(False)
            chk.setEnabled(False)

        status_lbl.setText(tag)
        self._refresh_download_button()

    def _pick_extra_folder(self, key: str):
        info = self._extra_rows.get(key)
        if not info:
            return
        dir_edit: QLineEdit = info["dir_edit"]
        chk: QCheckBox = info["chk"]
        cur = self._resolve_extra_target_dir(dir_edit.text()) or self._media_root
        chosen = QFileDialog.getExistingDirectory(
            self,
            tr("scraper_dlg.pick_extra_folder_title", "Select folder for {label}", label=get_media_slot_label(key)),
            cur,
        )
        if not chosen:
            return
        norm = chosen.strip().replace("\\", "/")
        display_val = norm
        if self._media_root:
            try:
                p_norm = os.path.normcase(os.path.abspath(str(Path(norm).parent)))
                root_norm = os.path.normcase(os.path.abspath(self._media_root))
                if p_norm == root_norm:
                    display_val = Path(norm).name
            except OSError:
                pass
        dir_edit.setText(display_val)
        self._sync_extra_row_state(key)
        if chk.isEnabled():
            chk.setChecked(True)

    def _add_extra_slot_row(self, key: str, asset):
        row_w = QWidget()
        row_lay = QHBoxLayout(row_w)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(6)

        chk = QCheckBox(get_media_slot_label(key))
        chk.setChecked(False)
        dir_edit = QLineEdit(self._resolve_extra_default_input(key))
        dir_edit.setPlaceholderText(tr("scraper_dlg.extra_folder_placeholder", "Folder name…"))
        dir_edit.setMinimumWidth(90)
        dir_edit.setMaximumWidth(155)

        btn_pick = QPushButton("📁")
        btn_pick.setFixedWidth(28)
        btn_pick.setToolTip(tr("scraper_dlg.btn_browse_folder_short", "Browse destination folder…"))

        status_lbl = QLabel()
        status_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")

        row_lay.addWidget(chk)
        row_lay.addWidget(dir_edit)
        row_lay.addWidget(btn_pick)
        row_lay.addWidget(status_lbl, 1)

        self._extra_rows[key] = {
            "widget": row_w,
            "chk": chk,
            "dir_edit": dir_edit,
            "status": status_lbl,
            "media_kind": asset.media_kind,
        }
        self._extra_slots_layout.addWidget(row_w)

        chk.toggled.connect(self._refresh_download_button)
        dir_edit.textChanged.connect(lambda _txt, k=key: self._sync_extra_row_state(k))
        btn_pick.clicked.connect(lambda _checked=False, k=key: self._pick_extra_folder(k))
        self._sync_extra_row_state(key)

    def _refresh_download_button(self):
        any_enabled = any(c.isEnabled() for c in self._slot_checks.values()) or any(
            info["chk"].isEnabled() for info in self._extra_rows.values()
        )
        self.btn_download.setEnabled(any_enabled or bool(self.chk_apply_meta.isChecked()))

    def _on_candidate_selected(self, row: int, _col: int, _pr: int, _pc: int):
        cand = self._current_candidate()
        if not cand:
            self._clear_extra_slots()
            self.btn_download.setEnabled(False)
            return

        self.cand_title_lbl.setText(f"{cand.title}  [{cand.provider_label}]")
        meta_parts = [p for p in (cand.year, cand.manufacturer, cand.genre, cand.rating) if p]
        meta_head = " · ".join(meta_parts) if meta_parts else tr("scraper_dlg.no_extra_meta", "No additional metadata")
        notes_snip = f"\n{cand.notes[:220]}…" if cand.notes and len(cand.notes) > 220 else (f"\n{cand.notes}" if cand.notes else "")
        self.cand_meta_lbl.setText(meta_head + notes_snip)

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

        self._clear_extra_slots()
        for k, asset in cand.assets.items():
            if k not in self.specs_by_key:
                self._add_extra_slot_row(k, asset)
        self._extra_slots_container.setVisible(bool(self._extra_rows))
        self._refresh_download_button()

        self.preview_slot_combo.blockSignals(True)
        self.preview_slot_combo.clear()
        for k, asset in cand.assets.items():
            if asset.media_kind == "image":
                lbl = self.specs_by_key[k].label if k in self.specs_by_key else get_media_slot_label(k)
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
            self.thumb_lbl.setText(tr("scraper_dlg.no_image_preview", "No image preview"))
            return

        url = cand.assets[slot_k].url
        self.thumb_lbl.setPixmap(QPixmap())
        self.thumb_lbl.setText(tr("scraper_dlg.loading_thumb", "Loading thumbnail…"))
        self._thumb_worker = ThumbnailFetchWorker(url, timeout=10.0, parent=self)
        self._thumb_worker.image_ready.connect(self._on_thumb_ready)
        self._thumb_worker.start()

    def _on_thumb_ready(self, _url: str, data: bytes):
        if not data:
            self.thumb_lbl.setText(tr("scraper_dlg.preview_failed", "Could not preview this image"))
            return
        pix = QPixmap()
        if not pix.loadFromData(data):
            self.thumb_lbl.setText(tr("scraper_dlg.preview_invalid", "Invalid image format in preview"))
            return
        scaled = pix.scaled(self.thumb_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb_lbl.setText("")
        self.thumb_lbl.setPixmap(scaled)

    def _on_download_clicked(self):
        cand = self._current_candidate()
        if not cand:
            return
        chosen_layout = [k for k, c in self._slot_checks.items() if c.isEnabled() and c.isChecked()]
        chosen_extra = [k for k, info in self._extra_rows.items() if info["chk"].isEnabled() and info["chk"].isChecked()]
        chosen_slots = chosen_layout + chosen_extra
        if not chosen_slots and not self.chk_apply_meta.isChecked():
            QMessageBox.information(
                self,
                tr("scraper_dlg.nothing_selected_title", "Nothing Selected"),
                tr("scraper_dlg.nothing_selected_msg", "Check at least one media or metadata item to apply."),
            )
            return

        eff_specs_by_key = dict(self.specs_by_key)
        folder_db_updates: dict[str, str] = {}
        for k in chosen_extra:
            info = self._extra_rows[k]
            target_dir = self._resolve_extra_target_dir(info["dir_edit"].text())
            if not target_dir:
                QMessageBox.warning(
                    self,
                    tr("scraper_dlg.extra_folder_required_title", "Destination Folder Required"),
                    tr(
                        "scraper_dlg.extra_folder_required_msg",
                        "Specify or browse a destination folder for '{label}'.",
                        label=get_media_slot_label(k),
                    ),
                )
                return
            try:
                Path(target_dir).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.critical(self, tr("scraper_dlg.mkdir_error_title", "Error Creating Folders"), str(exc))
                return

            kind = str(info.get("media_kind") or "image")
            exts = self._extensions_for_media_kind(kind)
            db_field = (
                "bezel_hud_path"
                if (k == "bezel" and not str(self.list_row.get("bezel_path") or "").strip())
                else get_db_field_for_media_key(k)
            )
            eff_specs_by_key[k] = MediaRequirementSpec(
                key=k,
                label=get_media_slot_label(k),
                extensions=exts,
                required=False,
                media_kind=kind,
                folder_path=target_dir,
                folder_exists=True,
                db_field=db_field,
                default_folder_name=Path(target_dir).name,
            )
            if not str(self.list_row.get(db_field) or "").strip():
                folder_db_updates[db_field] = target_dir

        if folder_db_updates and self.db and self.list_row.get("id"):
            try:
                self.db.update_list(int(self.list_row["id"]), **folder_db_updates)
                self.list_row.update(folder_db_updates)
                self.has_folder_changes = True
            except Exception:
                pass

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
            QMessageBox.information(
                self,
                tr("scraper_dlg.meta_updated_title", "Metadata Updated"),
                tr("scraper_dlg.meta_updated_msg", "Available metadata has been updated in the database."),
            )
            self.accept()
            return

        self.btn_download.setEnabled(False)
        self.btn_search.setEnabled(False)
        self.status_lbl.setText(
            tr("scraper_dlg.downloading_status", "⬇ Downloading {count} file(s)…", count=len(chosen_slots))
        )

        self._dl_worker = SingleRomDownloadWorker(
            candidate=cand,
            stem=self.rom.stem,
            specs_by_key=eff_specs_by_key,
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
            msg_parts.append(
                tr(
                    "scraper_dlg.dl_ok_part",
                    "Successfully downloaded ({count}): {slots}",
                    count=len(downloaded),
                    slots=", ".join(downloaded.keys()),
                )
            )
        if failed:
            errs = "\n".join(f"• {k}: {v}" for k, v in failed.items())
            msg_parts.append(
                tr(
                    "scraper_dlg.dl_fail_part",
                    "Failed to download ({count}):\n{errs}",
                    count=len(failed),
                    errs=errs,
                )
            )
        QMessageBox.information(
            self,
            tr("scraper_dlg.dl_result_title", "Scraping Result"),
            "\n\n".join(msg_parts) or tr("scraper_dlg.dl_no_changes", "No changes."),
        )
        if downloaded:
            self.accept()

    def _on_download_failed(self, err: str):
        self.btn_download.setEnabled(True)
        self.btn_search.setEnabled(True)
        QMessageBox.critical(self, tr("scraper_dlg.dl_error_title", "Download Error"), err)

    def _stop_workers(self):
        for w in (self._search_worker, self._dl_worker, self._thumb_worker):
            if w and w.isRunning():
                w.cancel()
                w.wait(1500)

    def _on_close(self):
        self._stop_workers()
        self.accept() if (self.downloaded_any or self.metadata_updated or self.has_folder_changes) else self.reject()

    def closeEvent(self, event):
        self._stop_workers()
        super().closeEvent(event)
