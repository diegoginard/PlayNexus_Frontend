"""
Utilidades compartidas de configuración y ordenación para todas las tablas (`QTableWidget`)
de PlayNexus, unificando el comportamiento de `TableLayout` ("Detalles"):
  - Columnas redimensionables manualmente (`QHeaderView.Interactive`) con `stretchLastSection(True)`.
  - Encabezados ordenables (`setSortingEnabled(True)`, indicador de ordenación visible).
  - Ordenación numérica inteligente (`sort_key`) o alfanumérica case-insensitive (`SortableTableWidgetItem`).
  - Pausado seguro de ordenación al poblar filas o recibir progreso de hilos en segundo plano.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)


class SortableTableWidgetItem(QTableWidgetItem):
    """Elemento de tabla con ordenación numérica por `sort_key` o texto case-insensitive."""

    def __init__(self, text: str = "", sort_key: Any = None):
        super().__init__(str(text) if text is not None else "")
        self._sort_key = sort_key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortableTableWidgetItem):
            k1 = self._sort_key
            k2 = other._sort_key
            if k1 is not None and k2 is not None:
                try:
                    return bool(k1 < k2)
                except TypeError:
                    pass
        t1 = (self.text() or "").strip().lower()
        t2 = (other.text() or "").strip().lower() if other else ""
        return t1 < t2


def configure_details_table(
    table: QTableWidget,
    *,
    col_widths: Sequence[int] | None = None,
    stretch_last: bool = True,
    sorting: bool = True,
    selection_behavior: QAbstractItemView.SelectionBehavior = QAbstractItemView.SelectionBehavior.SelectRows,
    selection_mode: QAbstractItemView.SelectionMode = QAbstractItemView.SelectionMode.SingleSelection,
    edit_triggers: QAbstractItemView.EditTrigger = QAbstractItemView.EditTrigger.NoEditTriggers,
    hide_vertical_header: bool | None = None,
    alternating_rows: bool | None = None,
    apply_columns: bool = True,
) -> None:
    """Aplica la configuración estándar de `TableLayout` (columnas arrastrables y ordenables)."""
    if apply_columns:
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(bool(stretch_last))
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(bool(sorting))
        if col_widths:
            col_count = table.columnCount()
            for col, width in enumerate(col_widths):
                if col >= col_count:
                    break
                if width and int(width) > 0:
                    table.setColumnWidth(col, int(width))

    table.setSelectionBehavior(selection_behavior)
    table.setSelectionMode(selection_mode)
    table.setEditTriggers(edit_triggers)
    if hide_vertical_header is not None:
        table.verticalHeader().setVisible(not hide_vertical_header)
    if alternating_rows is not None:
        table.setAlternatingRowColors(bool(alternating_rows))
    table.setSortingEnabled(bool(sorting))


@contextmanager
def paused_table_sorting(
    table: QTableWidget,
    *,
    reenable: bool | None = None,
    disable_updates: bool = True,
) -> Iterator[None]:
    """Desactiva temporalmente la ordenación (y opcionalmente el repintado) al llenar la tabla."""
    was_sorting = table.isSortingEnabled()
    table.setSortingEnabled(False)
    if disable_updates:
        table.setUpdatesEnabled(False)
    try:
        yield
    finally:
        if disable_updates:
            table.setUpdatesEnabled(True)
        target = was_sorting if reenable is None else bool(reenable)
        table.setSortingEnabled(target)


def find_table_row_by_user_data(table: QTableWidget, value: Any, col: int = 0) -> int:
    """Busca el índice actual de una fila comparando `Qt.UserRole` (seguro tras reordenar)."""
    for r in range(table.rowCount()):
        item = table.item(r, col)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == value:
            return r
    return -1
