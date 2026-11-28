"""
Superposiciones Arcade In-Frontend para PlayerWindow (Fase 3):
  - Menú Rápido Arcade (navegable 100% con teclado o mando XInput/DirectInput)
  - Búsqueda Rápida con teclado virtual en pantalla y filtrado instantáneo
  - Helpers puros para filtrado/ordenamiento en caliente y acciones de energía
"""

from __future__ import annotations

import html
import re
import subprocess
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from playnexus.db import format_play_time
from playnexus.i18n import tr
from playnexus.services.library import (
    discover_dynamic_columns_from_games,
    extract_custom_game_properties,
    get_game_field_value,
    humanize_column_label,
)
from playnexus.services.controls import (
    ACTION_CLOSE_FRONTEND, ACTION_FRONTEND_MENU, ACTION_MUTE, ACTION_NAV_BACK,
    ACTION_NAV_DOWN, ACTION_NAV_LETTER_BACK, ACTION_NAV_LETTER_FWD,
    ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD, ACTION_NAV_UP, ACTION_PAGE_DOWN,
    ACTION_PAGE_UP, ACTION_SELECT, ACTION_TOGGLE_FAVORITE,
    get_all_bindings, matches_action,
)
from playnexus.ui.shaders import SHADER_PRESETS, get_shader_presets
from playnexus.ui.particles import PARTICLE_PRESETS, get_particle_presets


def _get_quick_shader_options() -> list[tuple[str, str]]:
    return [("layout", tr("qmenu.from_layout", "From Layout"))] + list(get_shader_presets())


def _get_quick_particle_options() -> list[tuple[str, str]]:
    return [("layout", tr("qmenu.from_layout", "From Layout"))] + list(get_particle_presets())


_STANDARD_FACET_SPECS: list[tuple[str, str, str, str]] = [
    ("genre", "🎭", "layout.col_genre", "Genre"),
    ("manufacturer", "🏢", "layout.col_manufacturer", "Manufacturer"),
    ("year", "📅", "layout.col_year", "Year"),
    ("players", "👥", "layout.col_players", "Players"),
    ("bios", "🧩", "layout.col_bios", "BIOS"),
    ("sourcefile", "⚙", "layout.col_sourcefile", "Sourcefile"),
]


def get_facet_field_label(field_key: str) -> str:
    fk = str(field_key or "").strip()
    for std_k, _ico, ikey, fb in _STANDARD_FACET_SPECS:
        if fk == std_k:
            return tr(ikey, fb)
    return f"✨ {humanize_column_label(fk)}"


def parse_field_filter_mode(filter_mode: str) -> tuple[str, str] | None:
    raw = str(filter_mode or "").strip()
    if not raw.lower().startswith("field:"):
        return None
    body = raw[6:]
    if "=" not in body:
        return None
    fk, fv = body.split("=", 1)
    fk = fk.strip()
    fv = fv.strip()
    if not fk or not fv:
        return None
    return fk, fv


def describe_runtime_filter(filter_mode: str) -> str:
    parsed = parse_field_filter_mode(filter_mode)
    if parsed:
        fk, fv = parsed
        return f"{get_facet_field_label(fk)}: {fv}"
    for k, lbl in _get_quick_filter_options():
        if k == filter_mode:
            return lbl
    return str(filter_mode or "")


def _get_quick_filter_options(extra_filter_mode: str = "") -> list[tuple[str, str]]:
    opts = [
        ("all", tr("qmenu.filter_all", "All games")),
        ("favorites", tr("qmenu.filter_favorites", "⭐ Favorites Only")),
        ("unplayed", tr("qmenu.filter_unplayed", "🧭 Unplayed (0 plays)")),
        ("played", tr("qmenu.filter_played", "🎮 Played")),
    ]
    if parse_field_filter_mode(extra_filter_mode):
        opts.append((extra_filter_mode, describe_runtime_filter(extra_filter_mode)))
    return opts


def _get_quick_sort_options(custom_cols: list[str] | None = None) -> list[tuple[str, str]]:
    opts = [
        ("title", tr("qmenu.sort_title", "Alphabetical (A-Z)")),
        ("title_desc", tr("qmenu.sort_title_desc", "Alphabetical (Z-A)")),
        ("favorites_first", tr("qmenu.sort_favorites_first", "Favorites first")),
        ("play_count_desc", tr("qmenu.sort_most_played", "Most played")),
        ("last_played_desc", tr("qmenu.sort_recently_played", "Recently played")),
        ("year_desc", tr("qmenu.sort_year_desc", "By Year (newest)")),
        ("year_asc", tr("qmenu.sort_year_asc", "By Year (oldest → newest)")),
        ("manufacturer", tr("qmenu.sort_manufacturer", "By Manufacturer")),
        ("genre", tr("qmenu.sort_genre", "By Genre")),
    ]
    seen = {k for k, _ in opts}
    for col in (custom_cols or []):
        ck = str(col or "").strip()
        if not ck:
            continue
        sk = f"custom:{ck}"
        if sk not in seen:
            seen.add(sk)
            opts.append((sk, tr("qmenu.sort_custom_fmt", "✨ By {col}", col=humanize_column_label(ck))))
    return opts


QUICK_SHADER_OPTIONS: list[tuple[str, str]] = [("layout", tr("qmenu.from_layout", "From Layout"))] + list(SHADER_PRESETS)
QUICK_PARTICLE_OPTIONS: list[tuple[str, str]] = [("layout", tr("qmenu.from_layout", "From Layout"))] + list(PARTICLE_PRESETS)


QUICK_FILTER_OPTIONS: list[tuple[str, str]] = _get_quick_filter_options()

QUICK_SORT_OPTIONS: list[tuple[str, str]] = _get_quick_sort_options()


def _parse_year_num(raw_year: object) -> int:
    m = re.search(r"\d{4}", str(raw_year or ""))
    return int(m.group(0)) if m else 0


def _natural_sort_tuple(raw_val: object) -> tuple:
    s = str(raw_val or "").strip()
    if not s:
        return (1, "")
    parts = re.split(r"(\d+)", s.lower())
    conv = [int(p) if p.isdigit() else p for p in parts]
    return (0, conv)


def collect_available_facets(games: list[dict], custom_cols: list[str] | None = None) -> list[tuple[str, str, int]]:
    """
    Descubre todas las facetas filtrables (estándar + personalizadas .pncat/.ini)
    que tengan al menos un valor no vacío en `games`.
    Retorna [(field_key, display_label, distinct_values_count)].
    """
    non_menu = [g for g in (games or []) if not g.get("is_menu_target")]
    if not non_menu:
        return []

    dyn_cols = list(custom_cols) if custom_cols is not None else discover_dynamic_columns_from_games(non_menu)
    candidates: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for std_k, ico, ikey, fb in _STANDARD_FACET_SPECS:
        candidates.append((std_k, f"{ico}  {tr(ikey, fb)}"))
        seen_keys.add(std_k)
    for ck in dyn_cols:
        if ck not in seen_keys:
            seen_keys.add(ck)
            candidates.append((ck, f"✨  {humanize_column_label(ck)}"))

    out: list[tuple[str, str, int]] = []
    for fk, flbl in candidates:
        distinct: set[str] = set()
        for g in non_menu:
            val = str(get_game_field_value(g, fk) or "").strip()
            if val:
                distinct.add(val.lower())
        if distinct:
            out.append((fk, flbl, len(distinct)))
    return out


def collect_facet_value_counts(
    games: list[dict], field_key: str, order_by_count: bool = False
) -> list[tuple[str, int]]:
    """
    Agrupa y cuenta juegos por cada valor no vacío de `field_key`.
    Retorna [(display_value, game_count)].
    """
    counts: dict[str, int] = {}
    canonical: dict[str, str] = {}
    for g in (games or []):
        if g.get("is_menu_target"):
            continue
        val = str(get_game_field_value(g, field_key) or "").strip()
        if not val:
            continue
        low = val.lower()
        if low not in canonical:
            canonical[low] = val
        counts[low] = counts.get(low, 0) + 1

    items = [(canonical[k], cnt) for k, cnt in counts.items()]
    if order_by_count:
        items.sort(key=lambda pair: (-pair[1], _natural_sort_tuple(pair[0])))
    else:
        items.sort(key=lambda pair: _natural_sort_tuple(pair[0]))
    return items


def filter_and_sort_runtime_games(
    games: list[dict], filter_mode: str = "all", sort_mode: str = "title"
) -> list[dict]:
    """Filtra y ordena una copia en memoria de la lista activa según el modo elegido."""
    raw_filter = str(filter_mode or "all").strip()
    fmode = raw_filter.lower()
    raw_sort = str(sort_mode or "title").strip()
    smode = raw_sort.lower()
    parsed_field = parse_field_filter_mode(raw_filter)

    filtered: list[dict] = []
    for g in games:
        if g.get("is_menu_target"):
            filtered.append(g)
            continue
        if parsed_field is not None:
            fk, target_val = parsed_field
            cur_val = str(get_game_field_value(g, fk) or "").strip()
            if cur_val.lower() != target_val.lower():
                continue
        elif fmode == "favorites" and int(g.get("is_favorite") or 0) != 1:
            continue
        elif fmode == "unplayed" and int(g.get("play_count") or 0) != 0:
            continue
        elif fmode == "played" and int(g.get("play_count") or 0) <= 0:
            continue
        filtered.append(g)

    result = list(filtered)
    result.sort(key=lambda item: (item.get("title") or "").lower())

    if smode == "title_desc":
        result.sort(key=lambda item: (item.get("title") or "").lower(), reverse=True)
    elif smode == "favorites_first":
        result.sort(key=lambda item: int(item.get("is_favorite") or 0), reverse=True)
    elif smode == "play_count_desc":
        result.sort(
            key=lambda item: (int(item.get("play_count") or 0), str(item.get("last_played") or "")),
            reverse=True,
        )
    elif smode == "last_played_desc":
        result.sort(key=lambda item: str(item.get("last_played") or ""), reverse=True)
    elif smode == "year_desc":
        result.sort(key=lambda item: _parse_year_num(item.get("year")), reverse=True)
    elif smode == "year_asc":
        result.sort(
            key=lambda item: (
                0 if _parse_year_num(item.get("year")) > 0 else 1,
                _parse_year_num(item.get("year")),
                (item.get("title") or "").lower(),
            )
        )
    elif smode in ("manufacturer", "genre"):
        result.sort(
            key=lambda item: (
                _natural_sort_tuple(get_game_field_value(item, smode)),
                (item.get("title") or "").lower(),
            )
        )
    elif raw_sort.lower().startswith("custom:"):
        ck = raw_sort.split(":", 1)[1].strip()
        if ck:
            result.sort(
                key=lambda item: (
                    _natural_sort_tuple(get_game_field_value(item, ck)),
                    (item.get("title") or "").lower(),
                )
            )
    return result


def build_power_command(action: str) -> list[str] | None:
    """Devuelve el comando de sistema operativo para reiniciar o apagar el equipo."""
    if sys.platform == "win32":
        if action == "restart_pc":
            return ["shutdown", "/r", "/t", "0"]
        if action == "shutdown_pc":
            return ["shutdown", "/s", "/t", "0"]
    else:
        if action == "restart_pc":
            return ["systemctl", "reboot"]
        if action == "shutdown_pc":
            return ["systemctl", "poweroff"]
    return None


def execute_system_power_action(action: str) -> bool:
    """Ejecuta de forma aislada la orden de energía del sistema tras confirmación explícita."""
    cmd = build_power_command(action)
    if not cmd:
        return False
    subprocess.Popen(cmd)
    return True


class _BaseBackdropOverlay(QWidget):
    """Lienzo semitransparente oscuro superpuesto al layout activo sin pausar video."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)

    def focusNextPrevChild(self, next: bool) -> bool:
        """Evita que Tab salga del overlay hacia widgets padre."""
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(6, 8, 16, 178))
        painter.end()


_CARD_STYLESHEET = """
QFrame#ArcadeGlassCard {
    background-color: rgba(16, 20, 32, 242);
    border: 2px solid #5d48d9;
    border-radius: 16px;
}
QListWidget#ArcadeMenuList {
    background-color: transparent;
    border: none;
    outline: none;
    color: #e2e8f0;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13pt;
    font-weight: 600;
}
QListWidget#ArcadeMenuList::item {
    padding: 11px 16px;
    margin: 3px 0px;
    border-radius: 9px;
    background-color: rgba(255, 255, 255, 0.04);
}
QListWidget#ArcadeMenuList::item:selected {
    background-color: #5d48d9;
    color: #ffffff;
    border: 1px solid #a78bfa;
}
QListWidget#ArcadeMenuList::item:hover:!selected {
    background-color: rgba(93, 72, 217, 0.28);
}
"""


class FrontendQuickMenuOverlay(_BaseBackdropOverlay):
    """
    Menú Rápido Arcade superpuesto a PlayerWindow.
    Permite operar favoritos, ruleta aleatoria, búsqueda rápida, filtros/orden,
    cambio de layout en caliente, ficha/controles y opciones del sistema con 100% mando o teclado.
    """

    close_requested = Signal()
    toggle_favorite_requested = Signal()
    random_game_requested = Signal()
    search_requested = Signal()
    open_manual_requested = Signal()
    filter_sort_changed = Signal(str, str)
    layout_selected = Signal(str)
    shader_preset_changed = Signal(str)
    particle_preset_changed = Signal(str)
    system_action_requested = Signal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._is_menu_list = False
        self._current_game: dict | None = None
        self._all_games: list[dict] = []
        self._custom_cols: list[str] = []
        self._active_facet_key: str = ""
        self._facet_order_by_count: bool = False
        self._filter_mode = "all"
        self._sort_mode = "title"
        self._active_layout_name = "Wheel"
        self._available_layouts: list[str] = ["Wheel"]
        self._shader_preset = "layout"
        self._particle_preset = "layout"
        self._pending_power_action: str | None = None
        self._page = "main"

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)
        root.setContentsMargins(36, 28, 36, 28)

        self.card = QFrame()
        self.card.setObjectName("ArcadeGlassCard")
        self.card.setMinimumWidth(680)
        self.card.setMaximumWidth(860)
        self.card.setStyleSheet(_CARD_STYLESHEET)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 20, 24, 18)
        card_layout.setSpacing(12)

        # Cabecera del menú rápido
        header_row = QHBoxLayout()
        self.title_lbl = QLabel(tr("qmenu.title", "🕹  ARCADE QUICK MENU"))
        self.title_lbl.setStyleSheet("color: #f8fafc; font-size: 16pt; font-weight: 800; letter-spacing: 0.5px;")
        self.subtitle_lbl = QLabel("")
        self.subtitle_lbl.setStyleSheet("color: #a5b4fc; font-size: 10pt; font-weight: 600;")
        header_row.addWidget(self.title_lbl)
        header_row.addStretch()
        header_row.addWidget(self.subtitle_lbl)
        card_layout.addLayout(header_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: rgba(148, 163, 184, 0.25); max-height: 1px;")
        card_layout.addWidget(sep)

        self.stack = QStackedWidget()
        card_layout.addWidget(self.stack, 1)

        # Página 0: Lista reutilizable para menú principal, layouts, sistema y confirmación
        self.menu_list = QListWidget()
        self.menu_list.setObjectName("ArcadeMenuList")
        self.menu_list.setFocusPolicy(Qt.NoFocus)
        self.menu_list.setMinimumHeight(340)
        self.menu_list.itemActivated.connect(self._on_list_item_activated)
        self.menu_list.itemClicked.connect(self._on_list_item_activated)
        self.stack.addWidget(self.menu_list)

        # Página 1: Ficha del Juego y Guía de Controles del Sistema
        info_page = QWidget()
        info_layout = QVBoxLayout(info_page)
        info_layout.setContentsMargins(6, 4, 6, 4)
        info_layout.setSpacing(10)

        self.info_game_lbl = QLabel("")
        self.info_game_lbl.setWordWrap(True)
        self.info_game_lbl.setStyleSheet(
            "background-color: rgba(255,255,255,0.04); border: 1px solid rgba(165,180,252,0.22); "
            "border-radius: 10px; padding: 12px; color: #e2e8f0; font-size: 10.5pt;"
        )
        info_layout.addWidget(self.info_game_lbl)

        self.info_controls_lbl = QLabel("")
        self.info_controls_lbl.setWordWrap(True)
        self.info_controls_lbl.setStyleSheet(
            "background-color: rgba(255,255,255,0.03); border: 1px solid rgba(148,163,184,0.2); "
            "border-radius: 10px; padding: 12px; color: #cbd5e1; font-size: 9.8pt;"
        )
        info_layout.addWidget(self.info_controls_lbl, 1)
        self.stack.addWidget(info_page)

        self.hint_lbl = QLabel(
            tr(
                "qmenu.hint",
                "▲▼ Navigate   ·   ◀▶ Change Filter / Sort / Layout   ·   Enter / A Confirm   ·   Back / B / Tab Return",
            )
        )
        self.hint_lbl.setAlignment(Qt.AlignCenter)
        self.hint_lbl.setStyleSheet("color: #94a3b8; font-size: 9pt; padding-top: 4px;")
        card_layout.addWidget(self.hint_lbl)

        root.addWidget(self.card)

    def open_with_context(
        self,
        *,
        list_name: str,
        is_menu_list: bool,
        current_game: dict | None,
        filter_mode: str,
        sort_mode: str,
        active_layout_name: str,
        available_layouts: list[str],
        shader_preset: str = "layout",
        particle_preset: str = "layout",
        manual_path: str = "",
        all_games: list[dict] | None = None,
    ):
        """Prepara el menú rápido con el estado vivo actual antes de mostrarse."""
        self._is_menu_list = is_menu_list
        self._current_game = dict(current_game) if current_game else None
        self._all_games = [g for g in (all_games or []) if not g.get("is_menu_target")]
        if not self._all_games and self._current_game and not self._current_game.get("is_menu_target"):
            self._all_games = [self._current_game]
        self._custom_cols = discover_dynamic_columns_from_games(self._all_games) if not is_menu_list else []
        self._active_facet_key = ""
        self._manual_path = str(manual_path or "").strip()
        self._has_manual = bool(self._manual_path)
        self._filter_mode = filter_mode or "all"
        self._sort_mode = sort_mode or "title"
        self._active_layout_name = active_layout_name or "Wheel"
        self._available_layouts = list(available_layouts or ["Wheel"])
        self._shader_preset = shader_preset or "layout"
        self._particle_preset = particle_preset or "layout"
        self._pending_power_action = None
        self.subtitle_lbl.setText(tr("qmenu.list_subtitle", "List: {name}", name=list_name or "Frontend"))
        self._show_page("main")

    def _label_for(self, options: list[tuple[str, str]], key: str) -> str:
        return next((lbl for k, lbl in options if k == key), key)

    def _show_page(self, page: str, keep_row: int = 0):
        self._page = page
        if page == "info":
            self.title_lbl.setText(tr("qmenu.info_title", "📖  GAME DETAILS & CONTROLS"))
            self._populate_info_page()
            self.stack.setCurrentIndex(1)
            return

        self.stack.setCurrentIndex(0)
        self.menu_list.clear()

        if page == "main":
            self.title_lbl.setText(tr("qmenu.title", "🕹  ARCADE QUICK MENU"))
            if not self._is_menu_list and self._current_game:
                is_fav = int(self._current_game.get("is_favorite") or 0) == 1
                fav_txt = (
                    tr("qmenu.remove_favorite", "⭐  Remove from Favorites")
                    if is_fav
                    else tr("qmenu.add_favorite", "☆  Add to Favorites")
                )
                self._add_action_item("toggle_fav", fav_txt)
            self._add_action_item("random_game", tr("qmenu.random_game", "🎲  Random Game (Lucky Wheel)"))
            self._add_action_item("quick_search", tr("qmenu.quick_search", "🔍  Quick Search in List"))

            f_opts = _get_quick_filter_options(self._filter_mode)
            s_opts = _get_quick_sort_options(self._custom_cols)
            f_lbl = self._label_for(f_opts, self._filter_mode)
            s_lbl = self._label_for(s_opts, self._sort_mode)
            if not self._is_menu_list:
                self._add_action_item("open_facets", tr("qmenu.open_facets", "🧭  Explore by Category / INI…"))
                self._add_action_item("cycle_filter", tr("qmenu.cycle_filter", "⚡  Quick Filter:   ◀  {label}  ▶", label=f_lbl))
                self._add_action_item("cycle_sort", tr("qmenu.cycle_sort", "⇅   List Order:  ◀  {label}  ▶", label=s_lbl))

            self._add_action_item("pick_layout", tr("qmenu.pick_layout", "🎨  Change Layout:   ◀  {layout}  ▶", layout=self._active_layout_name))
            sh_lbl = self._label_for(_get_quick_shader_options(), self._shader_preset)
            pt_lbl = self._label_for(_get_quick_particle_options(), self._particle_preset)
            self._add_action_item("cycle_shader", tr("qmenu.cycle_shader", "📺  GPU Shader:       ◀  {label}  ▶", label=sh_lbl))
            self._add_action_item("cycle_particle", tr("qmenu.cycle_particle", "✨  Particles:       ◀  {label}  ▶", label=pt_lbl))
            if not self._is_menu_list and self._current_game:
                manual_txt = (
                    tr("qmenu.manual_available", "📘  Game PDF Manual")
                    if getattr(self, "_has_manual", False)
                    else tr("qmenu.manual_unassigned", "📘  PDF Manual (Unassigned)")
                )
                self._add_action_item("view_manual", manual_txt)
            self._add_action_item("info_controls", tr("qmenu.info_controls", "📖  Game Info & System Controls"))
            self._add_action_item("system_menu", tr("qmenu.system_menu", "⚙   System / Power Options"))
            self._add_action_item("close_menu", tr("qmenu.close_menu", "✕   Resume Frontend"))

        elif page == "facets":
            self.title_lbl.setText(tr("qmenu.facets_title", "🧭  EXPLORE BY CATEGORY / INI"))
            total_n = len(self._all_games)
            mark_all = "✓  " if self._filter_mode == "all" else "    "
            self._add_action_item(
                "set_filter:all",
                tr("qmenu.facet_show_all", "{mark}All games ({count})", mark=mark_all, count=total_n),
            )
            facets = collect_available_facets(self._all_games, self._custom_cols)
            parsed_cur = parse_field_filter_mode(self._filter_mode)
            sel_idx = 0
            for idx, (fk, flbl, dcount) in enumerate(facets, start=1):
                active_mark = "●  " if (parsed_cur and parsed_cur[0] == fk) else "    "
                self._add_action_item(
                    f"open_facet:{fk}",
                    tr(
                        "qmenu.facet_row_fmt",
                        "{mark}{label}   ({count} categories)",
                        mark=active_mark,
                        label=flbl,
                        count=dcount,
                    ),
                )
                if parsed_cur and parsed_cur[0] == fk:
                    sel_idx = idx
            self._add_action_item("back_main", tr("qmenu.back_main", "←  Back to Quick Menu"))
            keep_row = keep_row if keep_row > 0 else sel_idx

        elif page == "facet_values":
            fk = self._active_facet_key
            flbl = get_facet_field_label(fk)
            order_lbl = (
                tr("qmenu.facet_order_count", "Most games")
                if self._facet_order_by_count
                else tr("qmenu.facet_order_az", "A-Z")
            )
            self.title_lbl.setText(
                tr("qmenu.facet_values_title", "🧭  {label}   [◀ {order} ▶]", label=flbl, order=order_lbl)
            )
            val_counts = collect_facet_value_counts(
                self._all_games, fk, order_by_count=self._facet_order_by_count
            )
            parsed_cur = parse_field_filter_mode(self._filter_mode)
            sel_idx = 0
            for idx, (val_str, cnt) in enumerate(val_counts):
                is_cur = bool(parsed_cur and parsed_cur[0] == fk and parsed_cur[1].lower() == val_str.lower())
                mark = "✓  " if is_cur else "    "
                self._add_action_item(
                    f"set_filter:field:{fk}={val_str}",
                    f"{mark}{val_str}   ({cnt})",
                )
                if is_cur:
                    sel_idx = idx
            self._add_action_item("back_facets", tr("qmenu.back_facets", "←  Back to Categories"))
            keep_row = keep_row if keep_row > 0 else sel_idx

        elif page == "sort":
            self.title_lbl.setText(tr("qmenu.select_sort_title", "⇅  SELECT LIST ORDER"))
            s_opts = _get_quick_sort_options(self._custom_cols)
            sel_idx = 0
            for idx, (skey, slbl) in enumerate(s_opts):
                mark = "✓  " if skey == self._sort_mode else "    "
                self._add_action_item(f"set_sort:{skey}", f"{mark}{slbl}")
                if skey == self._sort_mode:
                    sel_idx = idx
            self._add_action_item("back_main", tr("qmenu.back_main", "←  Back to Quick Menu"))
            keep_row = sel_idx

        elif page == "layout":
            self.title_lbl.setText(tr("qmenu.select_layout_title", "🎨  SELECT VISUAL LAYOUT"))
            sel_idx = 0
            for idx, lname in enumerate(self._available_layouts):
                mark = "✓  " if lname == self._active_layout_name else "    "
                self._add_action_item(f"set_layout:{lname}", f"{mark}{lname}")
                if lname == self._active_layout_name:
                    sel_idx = idx
            self._add_action_item("back_main", tr("qmenu.back_main", "←  Back to Quick Menu"))
            keep_row = sel_idx

        elif page == "system":
            self.title_lbl.setText(tr("qmenu.system_title", "⚙  SYSTEM & POWER"))
            self._add_action_item("sys:return_configurator", tr("qmenu.sys_return_configurator", "🛠  Return to Configurator"))
            self._add_action_item("sys:exit_frontend", tr("qmenu.sys_exit_frontend", "🚪  Exit PlayNexus (Desktop)"))
            self._add_action_item("sys:ask_restart_pc", tr("qmenu.sys_restart_pc", "🔄  Restart PC…"))
            self._add_action_item("sys:ask_shutdown_pc", tr("qmenu.sys_shutdown_pc", "⏻   Shut Down PC…"))
            self._add_action_item("back_main", tr("qmenu.back_main", "←  Back to Quick Menu"))

        elif page == "confirm_power":
            is_shut = self._pending_power_action == "shutdown_pc"
            self.title_lbl.setText(
                tr("qmenu.confirm_shutdown_title", "⏻  CONFIRM SHUTDOWN")
                if is_shut
                else tr("qmenu.confirm_restart_title", "🔄  CONFIRM RESTART")
            )
            self._add_action_item("back_system", tr("qmenu.confirm_cancel", "✕  No, cancel and go back"))
            confirm_lbl = (
                tr("qmenu.confirm_shutdown_exec", "⏻  Yes, shut down PC now")
                if is_shut
                else tr("qmenu.confirm_restart_exec", "🔄  Yes, restart PC now")
            )
            self._add_action_item("confirm_power_exec", confirm_lbl)
            keep_row = 0

        if self.menu_list.count() > 0:
            self.menu_list.setCurrentRow(max(0, min(self.menu_list.count() - 1, keep_row)))

    def _add_action_item(self, action_key: str, text: str):
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, action_key)
        self.menu_list.addItem(item)

    def _populate_info_page(self):
        g = self._current_game
        if g and not g.get("is_menu_target"):
            title = html.escape(str(g.get("title") or tr("qmenu.untitled", "Untitled")))
            year = html.escape(str(g.get("year") or "—"))
            maker = html.escape(str(g.get("manufacturer") or "—"))
            genre = html.escape(str(g.get("genre") or "—"))
            players = html.escape(str(g.get("players") or "—"))
            bios_val = str(get_game_field_value(g, "bios") or "").strip()
            plays = int(g.get("play_count") or 0)
            ptime = format_play_time(g.get("play_time_seconds") or 0)
            last = html.escape(str(g.get("last_played") or "").strip() or tr("qmenu.never", "Never"))
            tags = html.escape(str(g.get("tags") or "").strip() or "—")
            fav_badge = (
                tr("qmenu.badge_favorite", "⭐ Favorite")
                if int(g.get("is_favorite") or 0) == 1
                else tr("qmenu.badge_standard", "Standard")
            )
            from playnexus.services.retroachievements import format_ra_badge_text, get_cached_ra_progress_summary
            ra_sum = get_cached_ra_progress_summary(self.db, g)
            ra_txt = html.escape(format_ra_badge_text(ra_sum) if ra_sum else tr("qmenu.ra_unsynced", "Not synced"))
            manual_badge = (
                tr("qmenu.manual_badge_available", "Available (PDF)")
                if getattr(self, "_has_manual", False)
                else tr("qmenu.manual_badge_none", "Not assigned")
            )
            base_html = tr(
                "qmenu.info_game_html",
                "<b style='font-size:12pt; color:#f8fafc;'>{title}</b>   "
                "<span style='color:#fbbf24;'>[{fav_badge}]</span><br>"
                "<b>Year:</b> {year}  ·  <b>Manufacturer:</b> {maker}  ·  <b>Genre:</b> {genre}  ·  <b>Players:</b> {players}<br>"
                "<b>Activity:</b> {plays} plays  ·  {ptime} total  ·  <b>Last played:</b> {last}<br>"
                "<b>RetroAchievements:</b> <span style='color:#fde047;'>{ra_txt}</span>  ·  <b>Manual:</b> {manual_badge}<br>"
                "<b>Tags:</b> {tags}",
                title=title,
                fav_badge=fav_badge,
                year=year,
                maker=maker,
                genre=genre,
                players=players,
                plays=plays,
                ptime=ptime,
                last=last,
                ra_txt=ra_txt,
                manual_badge=manual_badge,
                tags=tags,
            )
            extra_parts: list[str] = []
            if bios_val:
                extra_parts.append(f"<b>BIOS:</b> {html.escape(bios_val)}")
            for _ck, clbl, cval in extract_custom_game_properties(g):
                extra_parts.append(
                    f"<span style='color:#c4b5fd;'><b>✨ {html.escape(clbl)}:</b></span> {html.escape(cval)}"
                )
            if extra_parts:
                base_html += "<br>" + "  ·  ".join(extra_parts)
            self.info_game_lbl.setText(base_html)
        else:
            self.info_game_lbl.setText(
                tr("qmenu.info_menu_view", "<b>Menu / List View</b> — Select a game to view its stats.")
            )

        bindings = get_all_bindings(self.db)
        rows_html = []
        for b in bindings:
            key_s = b.get("key") or "—"
            pad_s = b.get("pad") or "—"
            rows_html.append(
                tr(
                    "qmenu.control_binding_row",
                    "• <b>{name}:</b> Keyboard <code>{key}</code> | Gamepad <code>{pad}</code>",
                ).format(
                    name=html.escape(str(b["name"])),
                    key=html.escape(str(key_s)),
                    pad=html.escape(str(pad_s)),
                )
            )
        self.info_controls_lbl.setText("<br>".join(rows_html))

    def _cycle_option(self, options: list[tuple[str, str]], current: str, delta: int) -> str:
        keys = [k for k, _ in options]
        if current not in keys:
            return keys[0]
        idx = (keys.index(current) + delta) % len(keys)
        return keys[idx]

    def _cycle_current_row_inline(self, delta: int) -> bool:
        if self._page == "facet_values":
            self._facet_order_by_count = not self._facet_order_by_count
            self._show_page("facet_values", keep_row=0)
            return True
        if self._page != "main":
            return False
        item = self.menu_list.currentItem()
        if not item:
            return False
        act = item.data(Qt.UserRole)
        row = self.menu_list.currentRow()
        if act == "cycle_filter":
            f_opts = _get_quick_filter_options(self._filter_mode)
            self._filter_mode = self._cycle_option(f_opts, self._filter_mode, delta)
            self.filter_sort_changed.emit(self._filter_mode, self._sort_mode)
            self._show_page("main", keep_row=row)
            return True
        if act == "cycle_sort":
            s_opts = _get_quick_sort_options(self._custom_cols)
            self._sort_mode = self._cycle_option(s_opts, self._sort_mode, delta)
            self.filter_sort_changed.emit(self._filter_mode, self._sort_mode)
            self._show_page("main", keep_row=row)
            return True
        if act == "pick_layout" and self._available_layouts:
            if self._active_layout_name in self._available_layouts:
                idx = self._available_layouts.index(self._active_layout_name)
                new_idx = (idx + delta) % len(self._available_layouts)
            else:
                new_idx = 0
            self._active_layout_name = self._available_layouts[new_idx]
            self.layout_selected.emit(self._active_layout_name)
            self._show_page("main", keep_row=row)
            return True
        if act == "cycle_shader":
            self._shader_preset = self._cycle_option(_get_quick_shader_options(), self._shader_preset, delta)
            self.shader_preset_changed.emit(self._shader_preset)
            self._show_page("main", keep_row=row)
            return True
        if act == "cycle_particle":
            self._particle_preset = self._cycle_option(_get_quick_particle_options(), self._particle_preset, delta)
            self.particle_preset_changed.emit(self._particle_preset)
            self._show_page("main", keep_row=row)
            return True
        return False

    def _on_list_item_activated(self, item: QListWidgetItem):
        if not item:
            return
        act = str(item.data(Qt.UserRole) or "")
        if act == "toggle_fav":
            self.toggle_favorite_requested.emit()
            if self._current_game is not None:
                cur = int(self._current_game.get("is_favorite") or 0)
                self._current_game["is_favorite"] = 0 if cur else 1
                self._show_page("main", keep_row=self.menu_list.currentRow())
        elif act == "random_game":
            self.close_requested.emit()
            self.random_game_requested.emit()
        elif act == "quick_search":
            self.close_requested.emit()
            self.search_requested.emit()
        elif act == "open_facets":
            self._show_page("facets")
        elif act.startswith("open_facet:"):
            self._active_facet_key = act.split(":", 1)[1]
            self._show_page("facet_values")
        elif act.startswith("set_filter:"):
            chosen_f = act.split(":", 1)[1]
            self._filter_mode = chosen_f
            self.filter_sort_changed.emit(self._filter_mode, self._sort_mode)
            self.close_requested.emit()
        elif act == "cycle_filter":
            self._cycle_current_row_inline(1)
        elif act == "cycle_sort":
            self._show_page("sort")
        elif act.startswith("set_sort:"):
            chosen_s = act.split(":", 1)[1]
            self._sort_mode = chosen_s
            self.filter_sort_changed.emit(self._filter_mode, self._sort_mode)
            self.close_requested.emit()
        elif act in ("cycle_shader", "cycle_particle"):
            self._cycle_current_row_inline(1)
        elif act == "pick_layout":
            self._show_page("layout")
        elif act.startswith("set_layout:"):
            chosen = act.split(":", 1)[1]
            self._active_layout_name = chosen
            self.layout_selected.emit(chosen)
            self.close_requested.emit()
        elif act == "info_controls":
            self._show_page("info")
        elif act == "view_manual":
            self.close_requested.emit()
            self.open_manual_requested.emit()
        elif act == "system_menu":
            self._show_page("system")
        elif act == "back_facets":
            self._show_page("facets")
        elif act == "back_main":
            self._show_page("main")
        elif act == "back_system":
            self._show_page("system")
        elif act == "close_menu":
            self.close_requested.emit()
        elif act == "sys:return_configurator":
            self.close_requested.emit()
            self.system_action_requested.emit("return_configurator")
        elif act == "sys:exit_frontend":
            self.close_requested.emit()
            self.system_action_requested.emit("exit_frontend")
        elif act == "sys:ask_restart_pc":
            self._pending_power_action = "restart_pc"
            self._show_page("confirm_power")
        elif act == "sys:ask_shutdown_pc":
            self._pending_power_action = "shutdown_pc"
            self._show_page("confirm_power")
        elif act == "confirm_power_exec" and self._pending_power_action:
            pending = self._pending_power_action
            self._pending_power_action = None
            self.close_requested.emit()
            self.system_action_requested.emit(pending)

    def _move_row(self, delta: int):
        total = self.menu_list.count()
        if total <= 0:
            return
        cur = self.menu_list.currentRow()
        self.menu_list.setCurrentRow((cur + delta) % total)

    def handle_action(self, action_id: str) -> bool:
        """Despacha acciones de mando/teclado dentro del Menú Rápido."""
        if action_id in (ACTION_FRONTEND_MENU, ACTION_CLOSE_FRONTEND):
            self.close_requested.emit()
            return True

        if action_id == ACTION_NAV_BACK:
            if self._page == "main":
                self.close_requested.emit()
            elif self._page == "confirm_power":
                self._show_page("system")
            elif self._page == "facet_values":
                self._show_page("facets")
            else:
                self._show_page("main")
            return True

        if self._page == "info":
            if action_id == ACTION_SELECT:
                self._show_page("main")
            return True

        if action_id == ACTION_NAV_UP:
            self._move_row(-1)
            return True
        if action_id == ACTION_NAV_DOWN:
            self._move_row(1)
            return True
        if action_id in (ACTION_NAV_STEP5_BACK, ACTION_PAGE_UP):
            self._move_row(-5)
            return True
        if action_id in (ACTION_NAV_STEP5_FWD, ACTION_PAGE_DOWN):
            self._move_row(5)
            return True
        if action_id == ACTION_NAV_LETTER_BACK:
            self._cycle_current_row_inline(-1)
            return True
        if action_id == ACTION_NAV_LETTER_FWD:
            self._cycle_current_row_inline(1)
            return True
        if action_id == ACTION_SELECT:
            self._on_list_item_activated(self.menu_list.currentItem())
            return True
        return False

    def keyPressEvent(self, event):
        if matches_action(event, ACTION_FRONTEND_MENU, self.db) or matches_action(event, ACTION_CLOSE_FRONTEND, self.db):
            self.handle_action(ACTION_FRONTEND_MENU)
            event.accept()
            return
        if matches_action(event, ACTION_NAV_BACK, self.db):
            self.handle_action(ACTION_NAV_BACK)
            event.accept()
            return
        for act in (
            ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_NAV_LETTER_BACK,
            ACTION_NAV_LETTER_FWD, ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD,
            ACTION_SELECT,
        ):
            if matches_action(event, act, self.db):
                self.handle_action(act)
                event.accept()
                return
        event.accept()


class QuickSearchOverlay(_BaseBackdropOverlay):
    """
    Barra y teclado virtual en pantalla para búsqueda rápida in-Frontend
    operable con mando (D-Pad/L-Stick + A/B) o teclado físico.
    """

    close_requested = Signal()
    game_selected_requested = Signal(int)

    _OSK_ROWS: list[list[tuple[str, str]]] = [
        [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8"), ("9", "9"), ("0", "0")],
        [("Q", "Q"), ("W", "W"), ("E", "E"), ("R", "R"), ("T", "T"), ("Y", "Y"), ("U", "U"), ("I", "I"), ("O", "O"), ("P", "P")],
        [("A", "A"), ("S", "S"), ("D", "D"), ("F", "F"), ("G", "G"), ("H", "H"), ("J", "J"), ("K", "K"), ("L", "L"), ("⌫", "BKSP")],
        [("Z", "Z"), ("X", "X"), ("C", "C"), ("V", "V"), ("B", "B"), ("N", "N"), ("M", "M"), (tr("qmenu.osk_space", "SPACE"), "SPACE"), (tr("qmenu.osk_clear", "CLEAR"), "CLEAR"), (tr("qmenu.osk_go", "GO ✓"), "GO")],
    ]

    @staticmethod
    def _osk_label_for(token: str, default_lbl: str) -> str:
        if token == "SPACE":
            return tr("qmenu.osk_space", "SPACE")
        if token == "CLEAR":
            return tr("qmenu.osk_clear", "CLEAR")
        if token == "GO":
            return tr("qmenu.osk_go", "GO ✓")
        return default_lbl

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._games: list[dict] = []
        self._query = ""
        self._focus_zone = "kbd"  # "kbd" | "results"
        self._osk_row = 1
        self._osk_col = 0
        self._osk_buttons: list[list[QPushButton]] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)
        root.setContentsMargins(36, 24, 36, 24)

        card = QFrame()
        card.setObjectName("ArcadeGlassCard")
        card.setMinimumWidth(740)
        card.setMaximumWidth(920)
        card.setStyleSheet(_CARD_STYLESHEET)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(12)

        top = QHBoxLayout()
        title_lbl = QLabel(tr("qmenu.search_title", "🔍  QUICK SEARCH IN LIST"))
        title_lbl.setStyleSheet("color: #f8fafc; font-size: 15pt; font-weight: 800;")
        self.count_lbl = QLabel(tr("qmenu.search_count_zero", "0 games"))
        self.count_lbl.setStyleSheet("color: #a5b4fc; font-size: 10.5pt; font-weight: 600;")
        top.addWidget(title_lbl)
        top.addStretch()
        top.addWidget(self.count_lbl)
        lay.addLayout(top)

        self.query_display = QLabel(tr("qmenu.search_placeholder", "Type or use the arcade keyboard…"))
        self.query_display.setStyleSheet(
            "background-color: rgba(8, 10, 18, 0.9); color: #f8fafc; "
            "border: 2px solid #7c3aed; border-radius: 10px; padding: 10px 14px; "
            "font-size: 15pt; font-weight: 700;"
        )
        lay.addWidget(self.query_display)

        self.results_list = QListWidget()
        self.results_list.setObjectName("ArcadeMenuList")
        self.results_list.setFocusPolicy(Qt.NoFocus)
        self.results_list.setMinimumHeight(180)
        self.results_list.setMaximumHeight(240)
        self.results_list.itemActivated.connect(self._on_result_activated)
        self.results_list.itemClicked.connect(self._on_result_activated)
        lay.addWidget(self.results_list)

        # Teclado virtual en pantalla
        osk_box = QFrame()
        osk_box.setStyleSheet("background-color: rgba(255,255,255,0.03); border-radius: 12px; padding: 8px;")
        grid = QGridLayout(osk_box)
        grid.setSpacing(6)

        for r_idx, row_spec in enumerate(self._OSK_ROWS):
            btn_row: list[QPushButton] = []
            for c_idx, (lbl, token) in enumerate(row_spec):
                btn = QPushButton(self._osk_label_for(token, lbl))
                btn.setFocusPolicy(Qt.NoFocus)
                btn.setMinimumHeight(40)
                btn.clicked.connect(lambda _=False, t=token: self._apply_osk_token(t))
                grid.addWidget(btn, r_idx, c_idx)
                btn_row.append(btn)
            self._osk_buttons.append(btn_row)
        lay.addWidget(osk_box)

        hint = QLabel(
            tr(
                "qmenu.search_hint",
                "D-Pad / Arrows: Move cursor · A: Press key · RB/LB: Switch between Keyboard and Results · "
                "X: Backspace · Y: Clear · Enter: Go to selected · Esc/B: Close",
            )
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #94a3b8; font-size: 8.8pt;")
        lay.addWidget(hint)

        root.addWidget(card)
        self._refresh_osk_highlight()

    def open_with_games(self, games: list[dict]):
        self._games = list(games or [])
        self._query = ""
        self._focus_zone = "kbd"
        self._osk_row = 1
        self._osk_col = 0
        self._refresh_query_ui()
        self._refresh_results()
        self._refresh_osk_highlight()

    def _refresh_query_ui(self):
        if self._query:
            self.query_display.setText(f"🔍  {self._query}|")
            self.query_display.setStyleSheet(
                "background-color: rgba(8, 10, 18, 0.95); color: #fbbf24; "
                "border: 2px solid #7c3aed; border-radius: 10px; padding: 10px 14px; "
                "font-size: 15pt; font-weight: 700;"
            )
        else:
            self.query_display.setText(f"🔍  {tr('qmenu.search_placeholder', 'Type or use the arcade keyboard…')}")
            self.query_display.setStyleSheet(
                "background-color: rgba(8, 10, 18, 0.9); color: #94a3b8; "
                "border: 2px solid #5d48d9; border-radius: 10px; padding: 10px 14px; "
                "font-size: 15pt; font-weight: 600;"
            )

    def _refresh_results(self):
        q = self._query.strip().lower()
        self.results_list.clear()
        matches: list[dict] = []
        for g in self._games:
            if not q:
                matches.append(g)
                continue
            parts = [
                str(g.get(k) or "")
                for k in ("title", "rom_name", "genre", "manufacturer", "year", "sourcefile", "tags")
            ]
            parts.append(str(get_game_field_value(g, "bios") or ""))
            for _ck, _clbl, cval in extract_custom_game_properties(g):
                parts.append(cval)
            if any(q in p.lower() for p in parts if p):
                matches.append(g)

        game_fallback = tr("qmenu.game_fallback", "Game")
        for g in matches[:50]:
            star = "⭐ " if int(g.get("is_favorite") or 0) == 1 else ""
            yr = f" ({g['year']})" if g.get("year") else ""
            maker = f"  ·  {g['manufacturer']}" if g.get("manufacturer") else ""
            item = QListWidgetItem(f"{star}{g.get('title') or game_fallback}{yr}{maker}")
            item.setData(Qt.UserRole, g.get("id"))
            self.results_list.addItem(item)

        cnt = len(matches)
        if cnt == 1:
            self.count_lbl.setText(tr("qmenu.search_match_one", "{count} match", count=cnt))
        else:
            self.count_lbl.setText(tr("qmenu.search_match_many", "{count} matches", count=cnt))
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)

    def _refresh_osk_highlight(self):
        for r_idx, row in enumerate(self._osk_buttons):
            for c_idx, btn in enumerate(row):
                selected = (self._focus_zone == "kbd" and r_idx == self._osk_row and c_idx == self._osk_col)
                if selected:
                    btn.setStyleSheet(
                        "QPushButton { background-color: #6d28d9; color: #ffffff; "
                        "border: 2px solid #fbbf24; border-radius: 7px; font-weight: 800; font-size: 11pt; }"
                    )
                else:
                    btn.setStyleSheet(
                        "QPushButton { background-color: #1e2436; color: #e2e8f0; "
                        "border: 1px solid #334155; border-radius: 7px; font-weight: 600; font-size: 10.5pt; }"
                        "QPushButton:hover { background-color: #313b57; }"
                    )

    def _apply_osk_token(self, token: str):
        if token == "BKSP":
            self._query = self._query[:-1]
        elif token == "SPACE":
            if self._query and not self._query.endswith(" "):
                self._query += " "
        elif token == "CLEAR":
            self._query = ""
        elif token == "GO":
            self._confirm_selected_result()
            return
        else:
            self._query += token.lower()
        self._refresh_query_ui()
        self._refresh_results()

    def _on_result_activated(self, item: QListWidgetItem):
        if not item:
            return
        gid = item.data(Qt.UserRole)
        if gid is not None:
            self.close_requested.emit()
            self.game_selected_requested.emit(int(gid))

    def _confirm_selected_result(self):
        item = self.results_list.currentItem()
        if not item and self.results_list.count() > 0:
            item = self.results_list.item(0)
        if item:
            self._on_result_activated(item)

    def handle_action(self, action_id: str) -> bool:
        """Navega teclado virtual y resultados con teclado o gamepad."""
        if action_id in (ACTION_NAV_BACK, ACTION_CLOSE_FRONTEND, ACTION_FRONTEND_MENU):
            self.close_requested.emit()
            return True

        if action_id == ACTION_TOGGLE_FAVORITE:
            self._apply_osk_token("BKSP")
            return True

        if action_id == ACTION_MUTE:
            self._apply_osk_token("CLEAR")
            return True

        if action_id in (ACTION_NAV_STEP5_FWD, ACTION_PAGE_DOWN):
            if self.results_list.count() > 0:
                self._focus_zone = "results" if self._focus_zone == "kbd" else "kbd"
                self._refresh_osk_highlight()
            return True

        if action_id in (ACTION_NAV_STEP5_BACK, ACTION_PAGE_UP):
            self._focus_zone = "kbd" if self._focus_zone == "results" else "results"
            if self._focus_zone == "results" and self.results_list.count() == 0:
                self._focus_zone = "kbd"
            self._refresh_osk_highlight()
            return True

        if self._focus_zone == "results":
            total = self.results_list.count()
            if action_id == ACTION_NAV_UP and total > 0:
                cur = self.results_list.currentRow()
                if cur == 0:
                    self._focus_zone = "kbd"
                    self._refresh_osk_highlight()
                else:
                    self.results_list.setCurrentRow(cur - 1)
                return True
            if action_id == ACTION_NAV_DOWN and total > 0:
                cur = self.results_list.currentRow()
                self.results_list.setCurrentRow(min(total - 1, cur + 1))
                return True
            if action_id == ACTION_SELECT:
                self._confirm_selected_result()
                return True
            return True

        # Zona teclado virtual ("kbd")
        cols = len(self._OSK_ROWS[self._osk_row])
        rows = len(self._OSK_ROWS)
        if action_id == ACTION_NAV_UP:
            self._osk_row = (self._osk_row - 1) % rows
        elif action_id == ACTION_NAV_DOWN:
            self._osk_row = (self._osk_row + 1) % rows
        elif action_id == ACTION_NAV_LETTER_BACK:
            self._osk_col = (self._osk_col - 1) % cols
        elif action_id == ACTION_NAV_LETTER_FWD:
            self._osk_col = (self._osk_col + 1) % cols
        elif action_id == ACTION_SELECT:
            _lbl, token = self._OSK_ROWS[self._osk_row][self._osk_col]
            self._apply_osk_token(token)
            return True
        self._refresh_osk_highlight()
        return True

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Escape,):
            self.close_requested.emit()
            event.accept()
            return
        if key == Qt.Key_Backspace:
            self._apply_osk_token("BKSP")
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm_selected_result()
            event.accept()
            return
        if key == Qt.Key_Tab:
            self.handle_action(ACTION_NAV_STEP5_FWD)
            event.accept()
            return

        txt = event.text()
        if txt and txt.isprintable() and not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            self._query += txt.lower()
            self._refresh_query_ui()
            self._refresh_results()
            event.accept()
            return

        for act in (
            ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_NAV_LETTER_BACK,
            ACTION_NAV_LETTER_FWD, ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD,
        ):
            if matches_action(event, act, self.db):
                self.handle_action(act)
                event.accept()
                return
        event.accept()
