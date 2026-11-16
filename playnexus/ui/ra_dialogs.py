"""
Diálogos de integración con RetroAchievements:
  - RACredentialsDialog: configuración y prueba de Usuario + Web API Key.
  - RAGameDetailDialog: desglose de logros desbloqueados/pendientes y sincronización puntual.
  - RABatchSyncDialog: sincronización por lotes para toda una lista o juegos seleccionados.
"""
from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from playnexus.services.retroachievements import (
    RAConfig,
    RetroAchievementsClient,
    SYSTEM_KEY_TO_RA_CONSOLE_ID,
    format_ra_badge_text,
    get_cached_ra_detail,
    load_ra_config,
    resolve_ra_console_for_list,
    save_ra_config,
)
from playnexus.services.scraper.systems import SYSTEM_CATALOG

_RA_CONSOLE_CHOICES: list[tuple[int, str]] = sorted(
    {
        (cid, f"{s.display_name} (RA ID {cid})")
        for s in SYSTEM_CATALOG
        for cid in [SYSTEM_KEY_TO_RA_CONSOLE_ID.get(s.key, 0)]
        if cid > 0
    },
    key=lambda pair: pair[1].lower(),
)


class _RATestWorker(QThread):
    completed = Signal(bool, dict, str)

    def __init__(self, db, cfg: RAConfig, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = cfg

    def run(self):
        try:
            client = RetroAchievementsClient(self.db, config=self.cfg)
            info = client.test_credentials()
            self.completed.emit(True, info, "")
        except Exception as exc:
            self.completed.emit(False, {}, str(exc))


class _RASingleSyncWorker(QThread):
    completed = Signal(bool, dict, str)

    def __init__(self, db, game_row: dict, system_key: str, console_id: int, parent=None):
        super().__init__(parent)
        self.db = db
        self.game_row = dict(game_row)
        self.system_key = system_key
        self.console_id = console_id

    def run(self):
        try:
            client = RetroAchievementsClient(self.db)
            detail = client.sync_game_progress(
                self.game_row,
                system_key=self.system_key,
                console_id=self.console_id,
                force_refresh_catalog=False,
            )
            self.completed.emit(True, detail, "")
        except Exception as exc:
            self.completed.emit(False, {}, str(exc))


class _RABatchWorker(QThread):
    progress = Signal(int, int, str, dict)
    finished_all = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        db,
        games: list[dict],
        system_key: str,
        console_id: int,
        only_missing: bool,
        force_refresh: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self.games = list(games)
        self.system_key = system_key
        self.console_id = console_id
        self.only_missing = only_missing
        self.force_refresh = force_refresh
        self._cancel = threading.Event()

    def request_cancel(self):
        self._cancel.set()

    def run(self):
        try:
            client = RetroAchievementsClient(self.db)
            res = client.sync_list_progress(
                self.games,
                system_key=self.system_key,
                console_id=self.console_id,
                force_refresh_catalog=self.force_refresh,
                only_missing=self.only_missing,
                progress_callback=lambda d, t, title, item: self.progress.emit(d, t, title, item),
                cancel_check=self._cancel.is_set,
            )
            self.finished_all.emit(res)
        except Exception as exc:
            self.failed.emit(str(exc))


class RACredentialsDialog(QDialog):
    """Diálogo para configurar Usuario y Web API Key de RetroAchievements."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._test_worker: _RATestWorker | None = None
        self.setWindowTitle("Configurar RetroAchievements")
        self.setMinimumWidth(520)
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        hint = QLabel(
            "Ingresá tu usuario y <b>Web API Key</b> de RetroAchievements "
            "(disponible en retroachievements.org → Settings → Keys → Web API Key).\n"
            "La clave se almacena codificada localmente y solo realiza consultas de lectura."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        root.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Usuario exacto de RetroAchievements")
        form.addRow("Usuario RA:", self.user_edit)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Web API Key personal")
        self.btn_toggle_key = QPushButton("👁")
        self.btn_toggle_key.setCheckable(True)
        self.btn_toggle_key.setFixedWidth(36)
        self.btn_toggle_key.toggled.connect(
            lambda checked: self.key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(self.btn_toggle_key)
        form.addRow("Web API Key:", key_row)

        self.badge_cb = QCheckBox("Mostrar progreso/badges en Biblioteca, Tabla y Menú Rápido Arcade")
        form.addRow("", self.badge_cb)
        root.addLayout(form)

        test_row = QHBoxLayout()
        self.btn_test = QPushButton("🔌 Probar Conexión")
        self.btn_test.clicked.connect(self._test_connection)
        self.test_status_lbl = QLabel("")
        self.test_status_lbl.setWordWrap(True)
        test_row.addWidget(self.btn_test)
        test_row.addWidget(self.test_status_lbl, 1)
        root.addLayout(test_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load(self):
        cfg = load_ra_config(self.db)
        self.user_edit.setText(cfg.username)
        self.key_edit.setText(cfg.api_key)
        self.badge_cb.setChecked(cfg.show_badge)

    def _draft_config(self) -> RAConfig:
        return RAConfig(
            username=self.user_edit.text().strip(),
            api_key=self.key_edit.text().strip(),
            show_badge=self.badge_cb.isChecked(),
        )

    def _test_connection(self):
        cfg = self._draft_config()
        if not cfg.is_configured:
            QMessageBox.warning(self, "Datos incompletos", "Completá Usuario y Web API Key primero.")
            return
        self.btn_test.setEnabled(False)
        self.test_status_lbl.setText("Conectando con retroachievements.org…")
        self._test_worker = _RATestWorker(self.db, cfg, parent=self)
        self._test_worker.completed.connect(self._on_test_done)
        self._test_worker.start()

    def _on_test_done(self, ok: bool, info: dict, err: str):
        self.btn_test.setEnabled(True)
        if ok:
            self.test_status_lbl.setStyleSheet("color: #4ade80; font-weight: 600;")
            self.test_status_lbl.setText(
                f"✅ Conectado como {info.get('user')} · Puntos: {info.get('total_points', 0)} "
                f"(Softcore: {info.get('softcore_points', 0)})"
            )
        else:
            self.test_status_lbl.setStyleSheet("color: #f87171;")
            self.test_status_lbl.setText(f"❌ {err}")

    def _save_and_accept(self):
        save_ra_config(self.db, self._draft_config())
        self.accept()


class RAGameDetailDialog(QDialog):
    """Muestra los logros de RetroAchievements cacheados para un juego y permite resincronizarlo."""

    progress_updated = Signal(dict)

    def __init__(self, db, game_row: dict, list_row: dict | None = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.game_row = dict(game_row or {})
        self.list_row = dict(list_row or {}) if list_row else (db.get_list(self.game_row.get("list_id")) or {})
        self._worker: _RASingleSyncWorker | None = None
        self._detail: dict | None = None

        self.setWindowTitle(f"RetroAchievements — {self.game_row.get('title') or 'Juego'}")
        self.resize(860, 620)
        self._build_ui()
        self._load_cached()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        header = QFrame()
        header.setStyleSheet("QFrame { background-color: #161c2d; border: 1px solid #2e3852; border-radius: 8px; }")
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(12, 10, 12, 10)

        top_row = QHBoxLayout()
        self.header_title = QLabel(f"🏆 {self.game_row.get('title') or 'Juego'}")
        self.header_title.setStyleSheet("color: #f8fafc; font-size: 13pt; font-weight: 700; border: none;")
        top_row.addWidget(self.header_title, 1)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Todos los logros", "all")
        self.filter_combo.addItem("Desbloqueados ✅", "unlocked")
        self.filter_combo.addItem("Pendientes 🔒", "locked")
        self.filter_combo.currentIndexChanged.connect(self._refresh_table)
        top_row.addWidget(self.filter_combo)
        h_lay.addLayout(top_row)

        self.summary_lbl = QLabel("Sin datos en caché.")
        self.summary_lbl.setStyleSheet("color: #cbd5e1; border: none; font-size: 9.5pt;")
        h_lay.addWidget(self.summary_lbl)

        self.pct_bar = QProgressBar()
        self.pct_bar.setRange(0, 100)
        self.pct_bar.setValue(0)
        h_lay.addWidget(self.pct_bar)

        root.addWidget(header)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Estado", "Logro", "Descripción", "Puntos", "Desbloqueo"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.btn_cfg = QPushButton("⚙ Credenciales RA…")
        self.btn_cfg.clicked.connect(self._open_credentials)
        self.btn_sync = QPushButton("🔄 Actualizar Logros Ahora")
        self.btn_sync.setStyleSheet("font-weight: 700;")
        self.btn_sync.clicked.connect(self._sync_now)
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)

        actions.addWidget(self.btn_cfg)
        actions.addWidget(self.btn_sync)
        actions.addStretch()
        actions.addWidget(self.btn_close)
        root.addLayout(actions)

    def _load_cached(self):
        self._detail = get_cached_ra_detail(self.db, self.game_row)
        self._render_detail()

    def _render_detail(self):
        d = self._detail
        if not d:
            self.summary_lbl.setText(
                "No hay logros almacenados en caché para este juego. Pulsá 'Actualizar Logros Ahora'."
            )
            self.pct_bar.setValue(0)
            self.table.setRowCount(0)
            return

        if not d.get("matched", True):
            self.summary_lbl.setText(
                f"Juego no catalogado o hash no reconocido en RetroAchievements (método: {d.get('match_method', 'N/A')})."
            )
            self.pct_bar.setValue(0)
            self.table.setRowCount(0)
            return

        unlocked = int(d.get("unlocked") or 0)
        total = int(d.get("total") or 0)
        pct = float(d.get("pct") or 0.0)
        pts_e = int(d.get("points_earned") or 0)
        pts_t = int(d.get("points_total") or 0)
        method = str(d.get("match_method") or "")
        ra_id = d.get("ra_game_id") or 0
        self.summary_lbl.setText(
            f"RA ID: <b>{ra_id}</b> ({d.get('console_name') or 'Sistema'}) · "
            f"<b>{unlocked}/{total}</b> logros (<b>{pct:.1f}%</b>) · "
            f"Puntos: <b>{pts_e}/{pts_t}</b> · Emparejamiento: <code>{method}</code>"
        )
        self.pct_bar.setValue(int(round(pct)))
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        if not self._detail or not self._detail.get("achievements"):
            return
        mode = self.filter_combo.currentData()
        for ach in self._detail.get("achievements") or []:
            earned = bool(ach.get("earned"))
            if mode == "unlocked" and not earned:
                continue
            if mode == "locked" and earned:
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            st_txt = "🏆 HC" if ach.get("hardcore") else ("✅ Sí" if earned else "🔒")
            self.table.setItem(r, 0, QTableWidgetItem(st_txt))
            self.table.setItem(r, 1, QTableWidgetItem(str(ach.get("title") or "")))
            self.table.setItem(r, 2, QTableWidgetItem(str(ach.get("description") or "")))
            self.table.setItem(r, 3, QTableWidgetItem(str(ach.get("points") or 0)))
            self.table.setItem(r, 4, QTableWidgetItem(str(ach.get("date_earned") or "—")))

    def _open_credentials(self):
        dlg = RACredentialsDialog(self.db, self)
        dlg.exec()

    def _sync_now(self):
        cfg = load_ra_config(self.db)
        if not cfg.is_configured:
            dlg = RACredentialsDialog(self.db, self)
            if not dlg.exec():
                return
            cfg = load_ra_config(self.db)
            if not cfg.is_configured:
                return

        emu = self.db.get_default_emulator_for_list(self.list_row.get("id")) if self.list_row.get("id") else None
        sys_key, cid = resolve_ra_console_for_list(self.list_row, emulator_row=emu)
        if cid <= 0:
            QMessageBox.information(
                self,
                "Sistema no detectado",
                "No se pudo detectar automáticamente la consola RA de esta lista.\n"
                "Usá el sincronizador por lotes ('🏆 RetroAchievements…' en Rom Manager) para elegir la consola manualmente.",
            )
            return

        self.btn_sync.setEnabled(False)
        self.summary_lbl.setText("Consultando RetroAchievements…")
        self._worker = _RASingleSyncWorker(self.db, self.game_row, sys_key, cid, parent=self)
        self._worker.completed.connect(self._on_sync_done)
        self._worker.start()

    def _on_sync_done(self, ok: bool, detail: dict, err: str):
        self.btn_sync.setEnabled(True)
        if not ok:
            self.summary_lbl.setText(f"❌ {err}")
            QMessageBox.warning(self, "Error RetroAchievements", err)
            return
        self._detail = detail
        self._render_detail()
        self.progress_updated.emit(detail)


class RABatchSyncDialog(QDialog):
    """Sincronización por lotes de RetroAchievements para una lista en Rom Manager o Biblioteca."""

    sync_finished = Signal()

    def __init__(self, db, list_row: dict, games: list[dict], parent=None):
        super().__init__(parent)
        self.db = db
        self.list_row = dict(list_row or {})
        self.games = [dict(g) for g in (games or [])]
        self._worker: _RABatchWorker | None = None

        self.setWindowTitle(f"RetroAchievements — {self.list_row.get('name') or 'Lista'}")
        self.resize(900, 650)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        cfg_box = QGroupBox("Configuración de Sincronización")
        form = QFormLayout(cfg_box)

        emu = self.db.get_default_emulator_for_list(self.list_row.get("id")) if self.list_row.get("id") else None
        sys_key, detected_cid = resolve_ra_console_for_list(self.list_row, emulator_row=emu)
        self._detected_sys_key = sys_key

        self.console_combo = QComboBox()
        self.console_combo.addItem("Seleccionar consola RA…", 0)
        for cid, label in _RA_CONSOLE_CHOICES:
            self.console_combo.addItem(label, cid)
        if detected_cid > 0:
            idx = self.console_combo.findData(detected_cid)
            if idx >= 0:
                self.console_combo.setCurrentIndex(idx)
        form.addRow("Consola RetroAchievements:", self.console_combo)

        opts = QHBoxLayout()
        self.only_missing_cb = QCheckBox("Omitir juegos ya cacheados")
        self.only_missing_cb.setChecked(True)
        self.refresh_catalog_cb = QCheckBox("Forzar recarga de catálogo de hashes")
        opts.addWidget(self.only_missing_cb)
        opts.addWidget(self.refresh_catalog_cb)
        opts.addStretch()
        form.addRow("Opciones:", opts)
        root.addWidget(cfg_box)

        ctrl = QHBoxLayout()
        self.btn_creds = QPushButton("⚙ Credenciales RA…")
        self.btn_creds.clicked.connect(self._edit_creds)
        self.btn_start = QPushButton(f"🏆 Sincronizar {len(self.games)} juego(s)")
        self.btn_start.setStyleSheet("font-weight: 700;")
        self.btn_start.clicked.connect(self._start_sync)
        self.btn_cancel = QPushButton("⏹ Cancelar")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_sync)
        ctrl.addWidget(self.btn_creds)
        ctrl.addWidget(self.btn_start)
        ctrl.addWidget(self.btn_cancel)
        ctrl.addStretch()
        root.addLayout(ctrl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Configurá tu API Key (solo la primera vez) y presioná 'Sincronizar'.")
        self.status_lbl.setStyleSheet("color: #93c5fd; font-weight: 600;")
        root.addWidget(self.status_lbl)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Juego", "Estado", "Progreso RA", "Método / Hash"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    def _edit_creds(self):
        RACredentialsDialog(self.db, self).exec()

    def _start_sync(self):
        cfg = load_ra_config(self.db)
        if not cfg.is_configured:
            if not RACredentialsDialog(self.db, self).exec():
                return
            cfg = load_ra_config(self.db)
            if not cfg.is_configured:
                return

        cid = int(self.console_combo.currentData() or 0)
        if cid <= 0:
            QMessageBox.warning(self, "Consola requerida", "Seleccioná la consola de RetroAchievements.")
            return
        if not self.games or (self._worker and self._worker.isRunning()):
            return

        # Inferir system_key coherente si el usuario cambió manualmente el combo
        sys_key = self._detected_sys_key
        for k, val_cid in SYSTEM_KEY_TO_RA_CONSOLE_ID.items():
            if val_cid == cid and (not sys_key or SYSTEM_KEY_TO_RA_CONSOLE_ID.get(sys_key) != cid):
                sys_key = k
                break

        self.table.setRowCount(0)
        self.progress_bar.setMaximum(len(self.games))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.status_lbl.setText("Descargando/cargando catálogo de hashes de la consola…")

        self._worker = _RABatchWorker(
            self.db,
            games=self.games,
            system_key=sys_key,
            console_id=cid,
            only_missing=self.only_missing_cb.isChecked(),
            force_refresh=self.refresh_catalog_cb.isChecked(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _cancel_sync(self):
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()

    def _on_progress(self, done: int, total: int, title: str, item: dict):
        self.progress_bar.setValue(done)
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(title))
        if item.get("error"):
            self.table.setItem(r, 1, QTableWidgetItem("❌ Error"))
            self.table.setItem(r, 2, QTableWidgetItem(str(item.get("error"))))
            self.table.setItem(r, 3, QTableWidgetItem("—"))
        elif item.get("matched"):
            self.table.setItem(r, 1, QTableWidgetItem("✅ Emparejado"))
            self.table.setItem(r, 2, QTableWidgetItem(format_ra_badge_text(item)))
            self.table.setItem(r, 3, QTableWidgetItem(str(item.get("match_method") or "")))
        else:
            self.table.setItem(r, 1, QTableWidgetItem("— Sin match"))
            self.table.setItem(r, 2, QTableWidgetItem("No catalogado"))
            self.table.setItem(r, 3, QTableWidgetItem(str(item.get("hash_method") or "")))

    def _on_finished(self, summary: dict):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        extra = " (cancelado)" if summary.get("cancelled") else ""
        self.status_lbl.setText(
            f"Completado{extra}: {summary.get('matched', 0)} emparejados · "
            f"{summary.get('unmatched', 0)} sin coincidencia · "
            f"{summary.get('skipped_cached', 0)} desde caché · {summary.get('errors', 0)} errores."
        )
        self.sync_finished.emit()

    def _on_failed(self, err: str):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.status_lbl.setText(f"❌ Error: {err}")
        QMessageBox.warning(self, "Error RetroAchievements", err)
