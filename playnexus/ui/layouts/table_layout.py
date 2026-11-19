import os
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from playnexus.i18n import tr
from playnexus.ui.layouts.base import BaseLayout
from playnexus.services.controls import matches_action, ACTION_NAV_BACK
from playnexus.ui.table_utils import SortableTableWidgetItem, configure_details_table


class TableLayout(BaseLayout):
    """
    Layout personalizado: Tabla Detallada con datos técnicos ordenables.
    """
    LAYOUT_NAME = "Detalles"
    LAYOUT_DESCRIPTION = tr("layout.table_desc", "Complete technical table with resizable and sortable columns")

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._size_cache: dict[str, tuple[str, int]] = {}

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            tr("layout.col_title", "Title"),
            tr("layout.col_rom_file", "ROM / File"),
            tr("layout.col_sourcefile", "Sourcefile"),
            tr("layout.col_year", "Year"),
            tr("layout.col_manufacturer", "Manufacturer"),
            tr("layout.col_genre", "Genre"),
            tr("layout.col_format", "Format"),
            tr("layout.col_size", "Size"),
            tr("layout.col_effective_emulator", "Effective emulator"),
            tr("layout.col_ra_achievements", "RA Achievements"),
        ])
        configure_details_table(
            self.table,
            col_widths=(240, 140, 140, 65, 130, 110, 75, 95, 170),
        )
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)

        self.table.itemSelectionChanged.connect(self._on_item_selected)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.itemActivated.connect(self._on_item_activated)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.table)

    def clear(self):
        super().clear()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)

    def render_games(self):
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.games))

        for i, g in enumerate(self.games):
            rom_path = g.get("rom_path", "")
            filename = os.path.basename(rom_path)
            _, ext = os.path.splitext(rom_path)

            title_item = SortableTableWidgetItem(g.get("title", ""))
            title_item.setData(Qt.UserRole, g.get("id"))
            self.table.setItem(i, 0, title_item)

            file_item = SortableTableWidgetItem(filename)
            file_item.setToolTip(rom_path)
            self.table.setItem(i, 1, file_item)

            sourcefile = str(g.get("sourcefile") or "").strip()
            if not sourcefile:
                xml_meta = g.get("xml_properties") or {}
                if isinstance(xml_meta, dict):
                    sourcefile = str(xml_meta.get("sourcefile") or xml_meta.get("source_file") or "").strip()
            source_item = SortableTableWidgetItem(sourcefile or "—")
            if sourcefile:
                source_item.setToolTip(sourcefile)
            self.table.setItem(i, 2, source_item)

            year_raw = str(g.get("year") or "").strip()
            year_val = int(year_raw) if year_raw.isdigit() else -1
            self.table.setItem(i, 3, SortableTableWidgetItem(year_raw or "—", sort_key=year_val))

            self.table.setItem(i, 4, SortableTableWidgetItem(g.get("manufacturer") or "—"))
            self.table.setItem(i, 5, SortableTableWidgetItem(g.get("genre") or "—"))
            self.table.setItem(i, 6, SortableTableWidgetItem(ext.lower()))

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
            self.table.setItem(i, 7, SortableTableWidgetItem(size_str, sort_key=size_bytes))

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
            self.table.setItem(i, 8, SortableTableWidgetItem(f"{emu}{source_str}"))

            if g.get("is_menu_target"):
                ra_txt = "—"
                ra_sort = -1.0
            else:
                db_ref = getattr(self, "db", None)
                if db_ref is not None:
                    from playnexus.services.retroachievements import format_ra_badge_text, get_cached_ra_progress_summary
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
            self.table.setItem(i, 9, SortableTableWidgetItem(ra_txt, sort_key=ra_sort))

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
        # itemActivated y doubleClicked se disparan juntos en un doble clic: compartir el guard
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
