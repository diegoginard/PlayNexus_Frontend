import json
import os
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)

from playnexus.i18n import tr
from playnexus.services.controls import ACTION_NAV_BACK, matches_action
from playnexus.services.library import (
    discover_dynamic_columns_from_games,
    extract_game_xml_props,
    get_game_field_value,
    humanize_column_label,
)
from playnexus.ui.layouts.base import BaseLayout
from playnexus.ui.table_utils import SortableTableWidgetItem, configure_details_table

# Columnas base integradas: (col_id, i18n_key, fallback_en, default_width, default_visible)
_BASE_TABLE_COLUMNS: tuple[tuple[str, str, str, int, bool], ...] = (
    ("title", "layout.col_title", "Title", 240, True),
    ("rom_file", "layout.col_rom_file", "ROM / File", 135, True),
    ("sourcefile", "layout.col_sourcefile", "Sourcefile", 130, True),
    ("bios", "layout.col_bios", "BIOS", 85, True),
    ("year", "layout.col_year", "Year", 65, True),
    ("manufacturer", "layout.col_manufacturer", "Manufacturer", 130, True),
    ("genre", "layout.col_genre", "Genre", 115, True),
    ("players", "layout.col_players", "Players", 68, False),
    ("cloneof", "layout.col_cloneof", "Clone Of", 85, False),
    ("format", "layout.col_format", "Format", 72, True),
    ("size", "layout.col_size", "Size", 90, True),
    ("effective_emulator", "layout.col_effective_emulator", "Effective emulator", 165, True),
    ("ra_achievements", "layout.col_ra_achievements", "RA Achievements", 125, True),
)


class TableLayout(BaseLayout):
    """
    Layout personalizado: Tabla Detallada con columnas estándar y columnas dinámicas
    ilimitadas (.pncat / INI), selector de visibilidad de columnas y ordenación inteligente.
    """

    LAYOUT_NAME = "Detalles"
    LAYOUT_DESCRIPTION = tr("layout.table_desc", "Complete technical table with resizable and sortable columns")

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._size_cache: dict[str, tuple[str, int]] = {}
        self._discovered_custom_cols: list[str] = []
        self._active_col_specs: list[tuple[str, str, int]] = []  # (col_id, header_text, width)
        self._hidden_cols: set[str] | None = None
        self._hidden_cols_from_db: bool = False

        # Barra compacta superior derecha para elegir columnas visibles
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addStretch(1)
        self.cols_btn = QPushButton(tr("layout.cols_btn", "⚙  Columns"))
        self.cols_btn.setToolTip(
            tr("layout.cols_btn_tip", "Show or hide standard and custom (.pncat / INI) columns")
        )
        self.cols_btn.setStyleSheet(
            "QPushButton { padding: 3px 10px; font-size: 8.5pt; border-radius: 5px; }"
        )
        self.cols_btn.clicked.connect(self._show_columns_button_menu)
        top_bar.addWidget(self.cols_btn)
        layout.addLayout(top_bar)

        self.table = QTableWidget(0, 0)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)

        hdr = self.table.horizontalHeader()
        hdr.setContextMenuPolicy(Qt.CustomContextMenu)
        hdr.customContextMenuRequested.connect(
            lambda pos: self._open_columns_menu(hdr.mapToGlobal(pos))
        )

        self.table.itemSelectionChanged.connect(self._on_item_selected)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.itemActivated.connect(self._on_item_activated)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.table, 1)
        self._rebuild_columns_schema()

    def _load_hidden_cols(self) -> set[str]:
        db_ref = getattr(self, "db", None)
        if self._hidden_cols is not None and (self._hidden_cols_from_db or db_ref is None):
            return self._hidden_cols
        default_hidden = {cid for cid, _ik, _fb, _w, def_vis in _BASE_TABLE_COLUMNS if not def_vis}
        if db_ref is not None:
            self._hidden_cols_from_db = True
            raw = db_ref.get_setting("table_hidden_columns", "")
            if raw:
                try:
                    loaded = json.loads(raw)
                    if isinstance(loaded, list):
                        self._hidden_cols = {str(x) for x in loaded if str(x) != "title"}
                        return self._hidden_cols
                except Exception:
                    pass
        self._hidden_cols = set(default_hidden)
        return self._hidden_cols

    def _save_hidden_cols(self) -> None:
        if self._hidden_cols is None:
            return
        db_ref = getattr(self, "db", None)
        if db_ref is not None:
            try:
                db_ref.set_setting(
                    "table_hidden_columns",
                    json.dumps(sorted(self._hidden_cols), ensure_ascii=False),
                )
            except Exception:
                pass

    def _all_available_columns(self) -> list[tuple[str, str, int, bool]]:
        """Retorna [(col_id, label, width, is_custom)] combinando columnas estándar y dinámicas."""
        cols: list[tuple[str, str, int, bool]] = []
        base_ids: set[str] = set()
        for cid, ikey, fb, width, _def_vis in _BASE_TABLE_COLUMNS:
            cols.append((cid, tr(ikey, fb), width, False))
            base_ids.add(cid)

        for cust_key in self._discovered_custom_cols:
            if cust_key not in base_ids:
                cols.append((f"custom:{cust_key}", f"✨ {humanize_column_label(cust_key)}", 125, True))
        return cols

    def _rebuild_columns_schema(self) -> None:
        hidden = self._load_hidden_cols()
        all_cols = self._all_available_columns()
        active = [(cid, lbl, w) for cid, lbl, w, _is_c in all_cols if cid == "title" or cid not in hidden]
        if not active:
            active = [("title", tr("layout.col_title", "Title"), 240)]

        prev_ids = [c[0] for c in self._active_col_specs]
        new_ids = [c[0] for c in active]
        if prev_ids == new_ids and self.table.columnCount() == len(active):
            return

        self._active_col_specs = active
        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(active))
        self.table.setHorizontalHeaderLabels([c[1] for c in active])
        configure_details_table(
            self.table,
            col_widths=[c[2] for c in active],
            stretch_last=True,
            sorting=True,
        )

    def _show_columns_button_menu(self) -> None:
        pos = self.cols_btn.mapToGlobal(QPoint(0, self.cols_btn.height()))
        self._open_columns_menu(pos)

    def _open_columns_menu(self, global_pos: QPoint) -> None:
        hidden = self._load_hidden_cols()
        menu = QMenu(self)
        actions_map = {}

        for cid, lbl, _w, _is_custom in self._all_available_columns():
            act = menu.addAction(lbl)
            act.setCheckable(True)
            act.setChecked(cid not in hidden)
            if cid == "title":
                act.setEnabled(False)
            actions_map[act] = cid

        menu.addSeparator()
        reset_act = menu.addAction(tr("layout.cols_reset", "↺ Reset default columns"))

        chosen = menu.exec(global_pos)
        if not chosen:
            return
        if chosen == reset_act:
            self._hidden_cols = {cid for cid, _ik, _fb, _w, def_vis in _BASE_TABLE_COLUMNS if not def_vis}
        elif chosen in actions_map:
            target_cid = actions_map[chosen]
            if target_cid in hidden:
                hidden.discard(target_cid)
            else:
                hidden.add(target_cid)

        self._save_hidden_cols()
        self._rebuild_columns_schema()
        self.render_games()

    def clear(self):
        super().clear()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)

    def render_games(self):
        # Descubrir columnas dinámicas presentes en esta lista / juegos
        list_row = None
        db_ref = getattr(self, "db", None)
        if db_ref is not None and self.games:
            first_lid = self.games[0].get("list_id")
            if first_lid:
                try:
                    list_row = db_ref.get_list(first_lid)
                except Exception:
                    list_row = None
        self._discovered_custom_cols = discover_dynamic_columns_from_games(self.games, list_row=list_row)
        self._rebuild_columns_schema()

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.games))

        active_ids = [c[0] for c in self._active_col_specs]

        for i, g in enumerate(self.games):
            rom_path = g.get("rom_path", "")
            filename = os.path.basename(rom_path)
            _, ext = os.path.splitext(rom_path)
            props = extract_game_xml_props(g)

            for col_idx, cid in enumerate(active_ids):
                if cid == "title":
                    item = SortableTableWidgetItem(g.get("title", ""))
                    item.setData(Qt.UserRole, g.get("id"))
                elif cid == "rom_file":
                    item = SortableTableWidgetItem(filename)
                    item.setToolTip(rom_path)
                elif cid == "sourcefile":
                    sf = str(g.get("sourcefile") or props.get("sourcefile") or props.get("source_file") or "").strip()
                    item = SortableTableWidgetItem(sf or "—")
                    if sf:
                        item.setToolTip(sf)
                elif cid == "bios":
                    bv = get_game_field_value(g, "bios") if not g.get("is_menu_target") else ""
                    item = SortableTableWidgetItem(bv or "—")
                elif cid == "year":
                    year_raw = str(g.get("year") or "").strip()
                    year_val = int(year_raw) if year_raw.isdigit() else -1
                    item = SortableTableWidgetItem(year_raw or "—", sort_key=year_val)
                elif cid == "manufacturer":
                    item = SortableTableWidgetItem(g.get("manufacturer") or "—")
                elif cid == "genre":
                    item = SortableTableWidgetItem(g.get("genre") or "—")
                elif cid == "players":
                    item = SortableTableWidgetItem(str(g.get("players") or props.get("players") or "—"))
                elif cid == "cloneof":
                    item = SortableTableWidgetItem(str(g.get("cloneof") or props.get("cloneof") or "—"))
                elif cid == "format":
                    item = SortableTableWidgetItem(ext.lower())
                elif cid == "size":
                    cached = self._size_cache.get(rom_path)
                    if cached is None:
                        try:
                            st = os.stat(rom_path)
                            mb = st.st_size / (1024 * 1024)
                            size_str = f"{mb:.2f} MB"
                            size_bytes = st.st_size
                        except OSError:
                            size_str = "—"
                            size_bytes = -1
                        self._size_cache[rom_path] = (size_str, size_bytes)
                    else:
                        size_str, size_bytes = cached
                    item = SortableTableWidgetItem(size_str, sort_key=size_bytes)
                elif cid == "effective_emulator":
                    raw_emu = g.get("effective_name")
                    emu = tr("layout.no_emulator", "No emulator") if not raw_emu or raw_emu == "Sin emulador" else raw_emu
                    source = g.get("source", "")
                    source_lbl = {
                        "juego": tr("layout.source_game", "game"),
                        "lista": tr("layout.source_list", "list"),
                        "ninguno": tr("layout.source_none", "none"),
                        "menu": tr("layout.source_menu", "menu"),
                    }.get(source, source)
                    source_str = f" ({source_lbl})" if source_lbl else ""
                    item = SortableTableWidgetItem(f"{emu}{source_str}")
                elif cid == "ra_achievements":
                    if g.get("is_menu_target"):
                        ra_txt = "—"
                        ra_sort = -1.0
                    elif db_ref is not None:
                        from playnexus.services.retroachievements import (
                            format_ra_badge_text,
                            get_cached_ra_progress_summary,
                        )
                        ra_sum = get_cached_ra_progress_summary(db_ref, g)
                        if ra_sum and ra_sum.get("matched"):
                            ra_txt = format_ra_badge_text(ra_sum)
                            ra_sort = float(ra_sum.get("pct") or 0.0)
                        elif ra_sum:
                            ra_txt = tr("layout.ra_na", "N/A")
                            ra_sort = -0.5
                        else:
                            ra_txt = "—"
                            ra_sort = -1.0
                    else:
                        ra_txt = "—"
                        ra_sort = -1.0
                    item = SortableTableWidgetItem(ra_txt, sort_key=ra_sort)
                elif cid.startswith("custom:"):
                    raw_k = cid[7:]
                    val_s = get_game_field_value(g, raw_k)
                    s_key = None
                    if val_s:
                        try:
                            s_key = float(val_s)
                        except ValueError:
                            s_key = None
                    item = SortableTableWidgetItem(val_s or "—", sort_key=s_key)
                else:
                    item = SortableTableWidgetItem("—")

                self.table.setItem(i, col_idx, item)

        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)
        self.table.blockSignals(False)

        found = False
        if self.current_game_id:
            found = self.select_game_by_id(self.current_game_id)
        if not found:
            if self.table.rowCount() > 0:
                self.table.blockSignals(True)
                self.table.selectRow(0)
                self.table.blockSignals(False)
                item = self.table.item(0, 0)
                if item:
                    self.current_game_id = item.data(Qt.UserRole)
                    self.game_selected.emit(self.current_game_id)
            else:
                self.current_game_id = None

    def select_game_by_id(self, game_id: int) -> bool:
        self.current_game_id = game_id
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item and item.data(Qt.UserRole) == game_id:
                self.table.blockSignals(True)
                self.table.selectRow(i)
                self.table.blockSignals(False)
                return True
        return False

    def _on_item_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 0)
            if item:
                game_id = item.data(Qt.UserRole)
                if game_id:
                    self.current_game_id = game_id
                    self.game_selected.emit(game_id)
                    return
        rows = self.table.selectionModel().selectedRows()
        if rows:
            item = self.table.item(rows[0].row(), 0)
            if item:
                game_id = item.data(Qt.UserRole)
                if game_id:
                    self.current_game_id = game_id
                    self.game_selected.emit(game_id)

    def _on_item_activated(self, item):
        if item and self._can_activate_game():
            row = item.row()
            id_item = self.table.item(row, 0)
            if id_item:
                game_id = id_item.data(Qt.UserRole)
                if game_id:
                    self.current_game_id = game_id
                    self.game_activated.emit(game_id)

    def _on_double_clicked(self, index=None):
        if not self._can_activate_game():
            return
        if self.current_game_id:
            self.game_activated.emit(self.current_game_id)
        elif index and hasattr(index, "isValid") and index.isValid():
            id_item = self.table.item(index.row(), 0)
            if id_item:
                game_id = id_item.data(Qt.UserRole)
                if game_id:
                    self.current_game_id = game_id
                    self.game_activated.emit(game_id)

    def keyPressEvent(self, event):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if matches_action(event, ACTION_NAV_BACK):
            self.nav_back_requested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.isAutoRepeat():
                event.accept()
                return
            if self.current_game_id and self._can_activate_game():
                self.game_activated.emit(self.current_game_id)
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_context_menu(self, pos: QPoint):
        item = self.table.itemAt(pos)
        if item:
            row = item.row()
            self.table.selectRow(row)
            id_item = self.table.item(row, 0)
            if id_item:
                game_id = id_item.data(Qt.UserRole)
                if game_id:
                    self.current_game_id = game_id
                    self.game_selected.emit(game_id)
                    global_pos = self.table.viewport().mapToGlobal(pos)
                    self.context_menu_requested.emit(game_id, global_pos)
