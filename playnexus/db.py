"""
Motor de almacenamiento 100% en Texto Plano (.txt) y memoria RAM para PlayNexus.
Guarda todo localmente dentro de la carpeta raíz de PlayNexus,
separado en tres carpetas con archivos .txt individuales:

Estructura en <Carpeta PlayNexus>/:
  - config/settings.txt             -> Configuración general del sistema (clave = valor)
  - emulators/<NombreEmulador>.txt  -> Un archivo .txt individual por cada emulador
  - lists/<NombreLista>.txt         -> Un archivo .txt individual por cada lista/menú y sus juegos
"""

from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
import sys
import json
from pathlib import Path
import re

# Carpeta raíz de PlayNexus (todo se guarda localmente dentro del proyecto, nada en AppData)
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

CONFIG_DIR = APP_DIR / "config"
EMULATORS_DIR = APP_DIR / "emulators"
LISTS_DIR = APP_DIR / "lists"

# Alias de compatibilidad
DATA_DIR = CONFIG_DIR
DB_PATH = APP_DIR


class RowDict(dict):
    """
    Diccionario de fila para elementos de texto plano
    (permite acceso por clave row['title'], row.get('title') y por índice row[0]).
    """
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _escape_field(val: object) -> str:
    """Escapa saltos de línea y punto y coma para líneas de texto plano en listas de juegos."""
    if val is None:
        return ""
    s = str(val)
    return (
        s.replace("\\", "\\\\")
        .replace(";", "\\s")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _unescape_field(val: str) -> str:
    """Revierte el escape de un campo leído desde un archivo .txt de forma optimizada."""
    if not val or "\\" not in val:
        return val or ""
    out: list[str] = []
    i = 0
    n = len(val)
    while i < n:
        ch = val[i]
        if ch == "\\" and i + 1 < n:
            nxt = val[i + 1]
            if nxt == "s":
                out.append(";")
                i += 2
                continue
            elif nxt == "n":
                out.append("\n")
                i += 2
                continue
            elif nxt == "\\":
                out.append("\\")
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _safe_filename(name: str, fallback: str = "item") -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", (name or fallback).strip())
    clean = clean[:80].strip(" .")
    return clean or fallback


LIST_DEFAULTS = {
    "name": "",
    "list_type": "games",
    "platform": "",
    "icon_path": "",
    "default_emulator_id": None,
    "layout": "Wheel",
    "allowed_extensions": "",
    "roms_path": "",
    "scan_subfolders": "true",
    "exclude_folder_if_zip": "false",
    "media_path": "",
    "boxart_path": "",
    "flyer_path": "",
    "wheel_path": "",
    "video_path": "",
    "cartart_path": "",
    "cabinet_path": "",
    "marquee_path": "",
    "bezel_path": "",
    "bezel_hud_enabled": "true",
    "bezel_hud_path": "",
    "loading_path": "",
    "loading_in_path": "",
    "loading_out_path": "",
    "xml_path": "",
    "created_at": "",
    "source_list_id": None,
    "filter_rules": "[]",
    "filter_match_mode": "all",
}

EMULATOR_DEFAULTS = {
    "name": "",
    "executable": "",
    "arguments": '"{rom}"',
    "platform": "",
    "bezel_delay": "0.0",
    "bezel_fade": "0.3",
    "loading_time": "1.5",
    "exit_loading_time": "1.0",
    "created_at": "",
}


class _PlainTextStore:
    """
    Almacén en memoria respaldado exclusivamente por carpetas locales de texto plano (.txt):
      - <root>/config/settings.txt
      - <root>/emulators/<NombreEmulador>.txt
      - <root>/lists/<NombreLista>.txt
    """

    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)
        self.config_dir = self.root_dir / "config"
        self.emulators_dir = self.root_dir / "emulators"
        self.lists_dir = self.root_dir / "lists"

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.emulators_dir.mkdir(parents=True, exist_ok=True)
        self.lists_dir.mkdir(parents=True, exist_ok=True)

        self.settings_file = self.config_dir / "settings.txt"

        self.settings: dict[str, str] = {}
        self.emulators: dict[int, dict] = {}
        self.game_lists: dict[int, dict] = {}
        self.menu_items: dict[int, list[int]] = {}
        self.games_by_id: dict[int, dict] = {}
        self.games_by_list: dict[int, list[dict]] = {}

        # Mapa de rutas actuales en disco para cada emulador y cada lista
        self._emu_files: dict[int, Path] = {}
        self._list_files: dict[int, Path] = {}

        self._next_emu_id = 1
        self._next_list_id = 1
        self._next_game_id = 1

        self._batch_depth = 0
        self._dirty_settings = False
        self._dirty_emulators: set[int] = set()
        self._dirty_lists: set[int] = set()

        self._initialize()

    def _has_existing_txt_data(self) -> bool:
        if self.settings_file.is_file():
            return True
        if any(self.emulators_dir.glob("*.txt")):
            return True
        if any(self.lists_dir.glob("*.txt")):
            return True
        return False

    def _initialize(self):
        if not self._has_existing_txt_data():
            self._write_settings()
        else:
            self.load_all()

    # ------------------------------------------------------------------
    # LECTURA DESDE CARPETAS config/, emulators/ y lists/
    # ------------------------------------------------------------------
    def load_all(self):
        self.settings.clear()
        self.emulators.clear()
        self.game_lists.clear()
        self.menu_items.clear()
        self.games_by_id.clear()
        self.games_by_list.clear()
        self._emu_files.clear()
        self._list_files.clear()
        self._next_emu_id = 1
        self._next_list_id = 1
        self._next_game_id = 1

        self._load_settings()
        self._load_emulators_folder()
        self._load_lists_folder()

    def _load_settings(self):
        if not self.settings_file.is_file():
            return
        try:
            text = self.settings_file.read_text(encoding="utf-8", errors="replace")
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                self.settings[k.strip()] = _unescape_field(v.strip())
        except Exception:
            pass

    def _load_emulators_folder(self):
        if not self.emulators_dir.is_dir():
            return
        files = sorted(self.emulators_dir.glob("*.txt"), key=lambda p: p.name.lower())
        for f_path in files:
            try:
                text = f_path.read_text(encoding="utf-8", errors="replace")
                data: dict[str, str] = {}
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or line.startswith("["):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        data[k.strip()] = _unescape_field(v.strip())

                raw_id = data.get("id", "").strip()
                eid = int(raw_id) if raw_id.isdigit() else self._next_emu_id
                if eid in self.emulators:
                    eid = max(self._next_emu_id, eid + 1)

                emu = {"id": eid}
                for k, def_v in EMULATOR_DEFAULTS.items():
                    emu[k] = data.get(k, def_v)
                if not emu["name"]:
                    emu["name"] = f_path.stem

                self.emulators[eid] = emu
                self._emu_files[eid] = f_path
                if eid >= self._next_emu_id:
                    self._next_emu_id = eid + 1
            except Exception:
                continue

    def _load_lists_folder(self):
        if not self.lists_dir.is_dir():
            return
        files = sorted(self.lists_dir.glob("*.txt"), key=lambda p: p.name.lower())
        for f_path in files:
            try:
                text = f_path.read_text(encoding="utf-8", errors="replace")
                section = "list"
                data: dict[str, str] = {}
                game_lines: list[str] = []

                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    low = line.lower()
                    if low == "[list]" or low.startswith("[list:"):
                        section = "list"
                        continue
                    elif low == "[games]":
                        section = "games"
                        continue

                    if section == "list":
                        if "=" in line:
                            k, v = line.split("=", 1)
                            data[k.strip()] = _unescape_field(v.strip())
                    else:
                        game_lines.append(line)

                raw_id = data.get("id", "").strip()
                lid = int(raw_id) if raw_id.isdigit() else self._next_list_id
                if lid in self.game_lists:
                    lid = max(self._next_list_id, lid + 1)

                lst = {"id": lid}
                for k, def_v in LIST_DEFAULTS.items():
                    lst[k] = data.get(k, def_v)
                for pk in ("media_path", "boxart_path", "flyer_path", "wheel_path", "video_path",
                           "cartart_path", "cabinet_path", "marquee_path", "bezel_path", "xml_path", "icon_path", "bezel_hud_path",
                           "loading_path", "loading_in_path", "loading_out_path"):
                    if lst.get(pk):
                        lst[pk] = str(lst[pk]).strip().replace("\\", "/")
                if not lst.get("loading_path") and lst.get("loading_in_path"):
                    lst["loading_path"] = lst["loading_in_path"]
                if lst.get("roms_path"):
                    lst["roms_path"] = ";".join(
                        p.strip().replace("\\", "/")
                        for p in str(lst["roms_path"]).split(";")
                        if p.strip()
                    )
                if not lst["name"]:
                    lst["name"] = f_path.stem

                raw_emu = lst.get("default_emulator_id")
                if raw_emu is not None and str(raw_emu).strip().isdigit():
                    lst["default_emulator_id"] = int(str(raw_emu).strip())
                else:
                    emu_name = data.get("default_emulator", "").strip()
                    matched_eid = None
                    if emu_name:
                        for eid, ed in self.emulators.items():
                            if ed["name"].lower() == emu_name.lower():
                                matched_eid = eid
                                break
                    lst["default_emulator_id"] = matched_eid

                raw_src = lst.get("source_list_id")
                if raw_src is not None and str(raw_src).strip().isdigit():
                    lst["source_list_id"] = int(str(raw_src).strip())
                else:
                    lst["source_list_id"] = None

                menu_str = data.get("menu_items", "")
                if menu_str:
                    m_ids = []
                    for tok in str(menu_str).split(";"):
                        tok = tok.strip()
                        if tok.isdigit():
                            m_ids.append(int(tok))
                    self.menu_items[lid] = m_ids

                self.game_lists[lid] = lst
                self._list_files[lid] = f_path
                self.games_by_list[lid] = []
                if lid >= self._next_list_id:
                    self._next_list_id = lid + 1

                # Cargar juegos de esta lista
                for g_line in game_lines:
                    parts = [_unescape_field(p) for p in g_line.split(";")]
                    if len(parts) < 4:
                        continue
                    try:
                        gid = int(parts[0]) if parts[0].strip() else self._next_game_id
                    except ValueError:
                        gid = self._next_game_id
                    if gid in self.games_by_id:
                        gid = max(self._next_game_id, gid + 1)

                    rom_name = parts[1] if len(parts) > 1 else ""
                    title = parts[2] if len(parts) > 2 else rom_name
                    rom_path = parts[3] if len(parts) > 3 else ""
                    year = parts[4] if len(parts) > 4 else ""
                    manufacturer = parts[5] if len(parts) > 5 else ""
                    genre = parts[6] if len(parts) > 6 else ""
                    players = parts[7] if len(parts) > 7 else ""
                    cloneof = parts[8] if len(parts) > 8 else ""
                    rating = parts[9] if len(parts) > 9 else ""
                    crc = parts[10] if len(parts) > 10 else ""
                    emu_ovr_str = parts[11].strip() if len(parts) > 11 else ""
                    emu_ovr = int(emu_ovr_str) if emu_ovr_str.isdigit() else None
                    launch_args = parts[12] if len(parts) > 12 else ""
                    cover_path = parts[13] if len(parts) > 13 else ""
                    notes = parts[14] if len(parts) > 14 else ""
                    xml_metadata = parts[15] if (len(parts) > 15 and parts[15]) else "{}"
                    created_at = parts[16] if len(parts) > 16 else ""
                    sourcefile = parts[17] if len(parts) > 17 else ""
                    bezel_hud_mode = parts[18].strip() if len(parts) > 18 else ""
                    if not sourcefile and xml_metadata and xml_metadata != "{}":
                        try:
                            _m = json.loads(xml_metadata)
                            if isinstance(_m, dict):
                                sourcefile = str(_m.get("sourcefile") or _m.get("source_file") or "").strip()
                        except Exception:
                            pass

                    g_dict = {
                        "id": gid,
                        "list_id": lid,
                        "rom_name": rom_name or (Path(rom_path).stem if rom_path else ""),
                        "title": title or rom_name or (Path(rom_path).stem if rom_path else ""),
                        "rom_path": rom_path,
                        "year": year,
                        "manufacturer": manufacturer,
                        "genre": genre,
                        "players": players,
                        "cloneof": cloneof,
                        "rating": rating,
                        "crc": crc,
                        "emulator_override_id": emu_ovr,
                        "launch_arguments": launch_args,
                        "cover_path": cover_path,
                        "notes": notes,
                        "sourcefile": sourcefile,
                        "bezel_hud_mode": bezel_hud_mode,
                        "xml_metadata": xml_metadata,
                        "created_at": created_at,
                    }
                    self.games_by_id[gid] = g_dict
                    self.games_by_list[lid].append(g_dict)
                    if gid >= self._next_game_id:
                        self._next_game_id = gid + 1
            except Exception:
                continue

    # ------------------------------------------------------------------
    # ESCRITURA EN ARCHIVOS INDIVIDUALES (.txt)
    # ------------------------------------------------------------------
    def begin_batch(self):
        self._batch_depth += 1

    def end_batch(self):
        if self._batch_depth > 0:
            self._batch_depth -= 1
        if self._batch_depth == 0:
            self.flush()

    def flush(self):
        if self._batch_depth > 0:
            return
        if self._dirty_settings:
            self._write_settings()
            self._dirty_settings = False
        if self._dirty_emulators:
            for eid in list(self._dirty_emulators):
                self._write_emulator_file(eid)
            self._dirty_emulators.clear()
        if self._dirty_lists:
            for lid in list(self._dirty_lists):
                self._write_list_file(lid)
            self._dirty_lists.clear()

    def _save_all(self):
        self._write_settings()
        for eid in list(self.emulators.keys()):
            self._write_emulator_file(eid)
        for lid in list(self.game_lists.keys()):
            self._write_list_file(lid)

    def _write_settings(self):
        lines = ["# Configuración del Sistema PlayNexus (Texto Plano)"]
        for k in sorted(self.settings.keys()):
            val = str(self.settings[k]).replace("\r", "").replace("\n", "\\n")
            lines.append(f"{k} = {val}")
        self.settings_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _target_emulator_file(self, eid: int, name: str) -> Path:
        safe = _safe_filename(name, fallback=f"emulator_{eid}")
        cand = self.emulators_dir / f"{safe}.txt"
        for other_id, other_path in self._emu_files.items():
            if other_id != eid and other_path == cand:
                cand = self.emulators_dir / f"{safe}_{eid}.txt"
                break
        return cand

    def _write_emulator_file(self, eid: int):
        old_file = self._emu_files.get(eid)
        if eid not in self.emulators:
            if old_file and old_file.is_file():
                try:
                    old_file.unlink()
                except Exception:
                    pass
            self._emu_files.pop(eid, None)
            return

        emu = self.emulators[eid]
        target_file = self._target_emulator_file(eid, emu.get("name", ""))
        if old_file and old_file != target_file and old_file.is_file():
            try:
                old_file.unlink()
            except Exception:
                pass

        lines = [
            f"# Configuración de Emulador: {emu.get('name', '')}",
            f"id = {eid}",
        ]
        for k in ("name", "executable", "arguments", "platform", "bezel_delay", "bezel_fade", "loading_time", "exit_loading_time", "created_at"):
            val = str(emu.get(k) or "").replace("\r", "").replace("\n", "\\n")
            lines.append(f"{k} = {val}")

        target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._emu_files[eid] = target_file

    def _target_list_file(self, lid: int, name: str) -> Path:
        safe = _safe_filename(name, fallback=f"list_{lid}")
        cand = self.lists_dir / f"{safe}.txt"
        for other_id, other_path in self._list_files.items():
            if other_id != lid and other_path == cand:
                cand = self.lists_dir / f"{safe}_{lid}.txt"
                break
        return cand

    def _write_list_file(self, lid: int):
        old_file = self._list_files.get(lid)
        if lid not in self.game_lists:
            if old_file and old_file.is_file():
                try:
                    old_file.unlink()
                except Exception:
                    pass
            self._list_files.pop(lid, None)
            return

        lst = self.game_lists[lid]
        target_file = self._target_list_file(lid, lst.get("name", ""))
        if old_file and old_file != target_file and old_file.is_file():
            try:
                old_file.unlink()
            except Exception:
                pass

        def_emu_id = lst.get("default_emulator_id")
        def_emu_name = ""
        if def_emu_id and def_emu_id in self.emulators:
            def_emu_name = self.emulators[def_emu_id].get("name", "")

        lines = [
            f"# Lista de PlayNexus: {lst.get('name', '')}",
            "[List]",
            f"id = {lid}",
        ]
        for k in LIST_DEFAULTS.keys():
            raw_v = lst.get(k)
            val = "" if raw_v is None else str(raw_v).replace("\r", "").replace("\n", "\\n")
            lines.append(f"{k} = {val}")
            if k == "default_emulator_id":
                lines.append(f"default_emulator = {def_emu_name}")

        m_items = self.menu_items.get(lid, [])
        m_str = ";".join(str(x) for x in m_items)
        lines.append(f"menu_items = {m_str}")

        lines.append("")
        lines.append("[Games]")
        lines.append(
            "# id;rom_name;title;rom_path;year;manufacturer;genre;players;cloneof;rating;crc;"
            "emulator_override_id;launch_arguments;cover_path;notes;xml_metadata;created_at;sourcefile;bezel_hud_mode"
        )
        for g in self.games_by_list.get(lid, []):
            row_fields = [
                _escape_field(g.get("id", "")),
                _escape_field(g.get("rom_name", "")),
                _escape_field(g.get("title", "")),
                _escape_field(g.get("rom_path", "")),
                _escape_field(g.get("year", "")),
                _escape_field(g.get("manufacturer", "")),
                _escape_field(g.get("genre", "")),
                _escape_field(g.get("players", "")),
                _escape_field(g.get("cloneof", "")),
                _escape_field(g.get("rating", "")),
                _escape_field(g.get("crc", "")),
                _escape_field("" if g.get("emulator_override_id") is None else g.get("emulator_override_id")),
                _escape_field(g.get("launch_arguments", "")),
                _escape_field(g.get("cover_path", "")),
                _escape_field(g.get("notes", "")),
                _escape_field(g.get("xml_metadata", "{}")),
                _escape_field(g.get("created_at", "")),
                _escape_field(g.get("sourcefile", "")),
                _escape_field(g.get("bezel_hud_mode", "")),
            ]
            lines.append(";".join(row_fields))

        target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._list_files[lid] = target_file


# Caché de almacenes en memoria por directorio raíz
_STORES_CACHE: dict[str, _PlainTextStore] = {}


def _get_store_for_path(path: Path) -> _PlainTextStore:
    p = Path(path).resolve()
    if p == APP_DIR.resolve():
        root_dir = APP_DIR
    elif p.suffix:
        root_dir = p.parent / f"{p.stem}_store"
    else:
        root_dir = p

    key = str(root_dir).lower()
    if key not in _STORES_CACHE:
        _STORES_CACHE[key] = _PlainTextStore(root_dir)
    return _STORES_CACHE[key]


class Database:
    """
    Interfaz de almacenamiento 100% en Texto Plano para PlayNexus.
    Opera en memoria RAM y persiste únicamente en archivos .txt dentro de PlayNexus:
      - config/settings.txt
      - emulators/<NombreEmulador>.txt
      - lists/<NombreLista>.txt
    """

    def __init__(self, path=APP_DIR):
        self.path = Path(path)
        self._store = _get_store_for_path(self.path)

    @property
    def data_dir(self) -> Path:
        return self._store.root_dir

    @contextmanager
    def batch(self):
        """Agrupa múltiples escrituras en memoria y guarda los archivos .txt una sola vez al finalizar."""
        self._store.begin_batch()
        try:
            yield
        finally:
            self._store.end_batch()

    def begin_batch(self):
        self._store.begin_batch()

    def end_batch(self):
        self._store.end_batch()

    # ------------------------------------------------------------------
    # 1. CONFIGURACIÓN (config/settings.txt)
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str = None) -> str | None:
        return self._store.settings.get(key, default)

    def set_setting(self, key: str, value: str):
        val_str = str(value)
        if self._store.settings.get(key) != val_str:
            self._store.settings[key] = val_str
            self._store._dirty_settings = True
            self._store.flush()

    # ------------------------------------------------------------------
    # 2. EMULADORES (emulators/<NombreEmulador>.txt)
    # ------------------------------------------------------------------
    def get_emulators(self) -> list[RowDict]:
        """Devuelve todos los emuladores ordenados alfabéticamente por nombre."""
        return [
            RowDict(emu)
            for _, emu in sorted(self._store.emulators.items(), key=lambda kv: (kv[1].get("name") or "").lower())
        ]

    def get_emulator(self, emu_id: int | None) -> RowDict | None:
        """Devuelve un emulador por su ID."""
        if emu_id is None:
            return None
        emu = self._store.emulators.get(int(emu_id))
        return RowDict(emu) if emu else None

    def get_default_emulator_for_list(self, list_id: int) -> RowDict | None:
        """Devuelve el emulador predeterminado asignado a una lista."""
        lst = self._store.game_lists.get(int(list_id))
        if not lst:
            return None
        eid = lst.get("default_emulator_id")
        if eid and eid in self._store.emulators:
            return RowDict(self._store.emulators[eid])
        return None

    def add_emulator(
        self,
        name: str,
        executable: str,
        arguments: str = '"{rom}"',
        platform: str = "",
        bezel_delay: float | str = 0.0,
        bezel_fade: float | str = 0.3,
        loading_time: float | str = 1.5,
        exit_loading_time: float | str = 1.0,
    ) -> int:
        """Registra un nuevo emulador y crea su archivo .txt en emulators/."""
        clean_name = str(name or "").strip()
        for ex in self._store.emulators.values():
            if ex["name"].lower() == clean_name.lower():
                raise ValueError(f"Ya existe un emulador con el nombre '{clean_name}'.")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        eid = self._store._next_emu_id
        self._store._next_emu_id += 1
        self._store.emulators[eid] = {
            "id": eid,
            "name": clean_name,
            "executable": str(executable or ""),
            "arguments": str(arguments or '"{rom}"'),
            "platform": str(platform or ""),
            "bezel_delay": str(bezel_delay if bezel_delay is not None else "0.0"),
            "bezel_fade": str(bezel_fade if bezel_fade is not None else "0.3"),
            "loading_time": str(loading_time if loading_time is not None else "1.5"),
            "exit_loading_time": str(exit_loading_time if exit_loading_time is not None else "1.0"),
            "created_at": now_str,
        }
        self._store._dirty_emulators.add(eid)
        self._store.flush()
        return eid

    def update_emulator(self, emu_id: int, **updates) -> int | None:
        """Actualiza un emulador existente y su archivo .txt en emulators/."""
        eid = int(emu_id)
        if eid not in self._store.emulators:
            return None
        if "name" in updates and updates["name"] is not None:
            new_name = str(updates["name"]).strip()
            for other_id, ex in self._store.emulators.items():
                if other_id != eid and ex["name"].lower() == new_name.lower():
                    raise ValueError(f"Ya existe un emulador con el nombre '{new_name}'.")
            updates["name"] = new_name
        if "bezel_delay" in updates and updates["bezel_delay"] is not None:
            updates["bezel_delay"] = str(updates["bezel_delay"])
        if "bezel_fade" in updates and updates["bezel_fade"] is not None:
            updates["bezel_fade"] = str(updates["bezel_fade"])
        if "loading_time" in updates and updates["loading_time"] is not None:
            updates["loading_time"] = str(updates["loading_time"])
        if "exit_loading_time" in updates and updates["exit_loading_time"] is not None:
            updates["exit_loading_time"] = str(updates["exit_loading_time"])
        self._store.emulators[eid].update(updates)
        self._store._dirty_emulators.add(eid)
        self._store.flush()
        return eid

    def delete_emulator(self, emu_id: int) -> int:
        """Elimina un emulador y borra su archivo .txt de emulators/."""
        eid = int(emu_id)
        if eid in self._store.emulators:
            del self._store.emulators[eid]
            self._store._dirty_emulators.add(eid)
            for lid, lst in self._store.game_lists.items():
                if lst.get("default_emulator_id") == eid:
                    lst["default_emulator_id"] = None
                    self._store._dirty_lists.add(lid)
            for g in self._store.games_by_id.values():
                if g.get("emulator_override_id") == eid:
                    g["emulator_override_id"] = None
                    self._store._dirty_lists.add(int(g["list_id"]))
            self._store.flush()
        return eid

    def count_lists_using_emulator(self, emu_id: int) -> int:
        eid = int(emu_id)
        return sum(1 for l in self._store.game_lists.values() if l.get("default_emulator_id") == eid)

    def count_games_using_emulator(self, emu_id: int) -> int:
        eid = int(emu_id)
        return sum(1 for g in self._store.games_by_id.values() if g.get("emulator_override_id") == eid)

    # ------------------------------------------------------------------
    # 3. LISTAS Y MENÚS (lists/<NombreLista>.txt)
    # ------------------------------------------------------------------
    def get_lists(self, with_counts: bool = True) -> list[RowDict]:
        """Devuelve todas las listas/menús ordenados alfabéticamente por nombre."""
        res: list[RowDict] = []
        for lid, lst in sorted(self._store.game_lists.items(), key=lambda kv: (kv[1].get("name") or "").lower()):
            d = RowDict(lst)
            if with_counts:
                d["game_count"] = len(self._store.games_by_list.get(lid, []))
            res.append(d)
        return res

    def get_list(self, list_id: int | None) -> RowDict | None:
        """Devuelve los datos de una lista o menú por su ID."""
        if list_id is None:
            return None
        lst = self._store.game_lists.get(int(list_id))
        return RowDict(lst) if lst else None

    def add_list(self, **fields) -> int:
        """Crea una nueva lista o menú y genera su archivo .txt en lists/."""
        clean_name = str(fields.get("name") or "").strip()
        for ex in self._store.game_lists.values():
            if ex["name"].lower() == clean_name.lower():
                raise ValueError(f"Ya existe una lista con el nombre '{clean_name}'.")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lid = self._store._next_list_id
        self._store._next_list_id += 1
        lst = {"id": lid}
        for k, def_v in LIST_DEFAULTS.items():
            if k in fields and fields[k] is not None:
                lst[k] = fields[k]
            else:
                lst[k] = def_v
        for pk in ("media_path", "boxart_path", "flyer_path", "wheel_path", "video_path",
                   "cartart_path", "cabinet_path", "marquee_path", "bezel_path", "xml_path", "icon_path", "bezel_hud_path",
                   "loading_path", "loading_in_path", "loading_out_path"):
            if lst.get(pk):
                lst[pk] = str(lst[pk]).strip().replace("\\", "/")
        if not lst.get("loading_path") and lst.get("loading_in_path"):
            lst["loading_path"] = lst["loading_in_path"]
        if lst.get("roms_path"):
            lst["roms_path"] = ";".join(
                p.strip().replace("\\", "/")
                for p in str(lst["roms_path"]).split(";")
                if p.strip()
            )
        lst["name"] = clean_name
        if not lst["created_at"]:
            lst["created_at"] = now_str
        if lst["default_emulator_id"] is not None and str(lst["default_emulator_id"]).strip() != "":
            lst["default_emulator_id"] = int(lst["default_emulator_id"])
        else:
            lst["default_emulator_id"] = None

        if lst.get("source_list_id") is not None and str(lst["source_list_id"]).strip() != "":
            lst["source_list_id"] = int(lst["source_list_id"])
        else:
            lst["source_list_id"] = None

        self._store.game_lists[lid] = lst
        self._store.games_by_list[lid] = []
        self._store._dirty_lists.add(lid)
        self._store.flush()
        return lid

    def update_list(self, list_id: int, **updates) -> int | None:
        """Actualiza los campos de una lista y su archivo .txt en lists/."""
        lid = int(list_id)
        if lid not in self._store.game_lists:
            return None
        if "name" in updates and updates["name"] is not None:
            new_name = str(updates["name"]).strip()
            for other_id, ex in self._store.game_lists.items():
                if other_id != lid and ex["name"].lower() == new_name.lower():
                    raise ValueError(f"Ya existe una lista con el nombre '{new_name}'.")
            updates["name"] = new_name
        for pk in ("media_path", "boxart_path", "flyer_path", "wheel_path", "video_path",
                   "cartart_path", "cabinet_path", "marquee_path", "bezel_path", "xml_path", "icon_path", "bezel_hud_path",
                   "loading_path", "loading_in_path", "loading_out_path"):
            if pk in updates and updates[pk] is not None:
                updates[pk] = str(updates[pk]).strip().replace("\\", "/")
        if "roms_path" in updates and updates["roms_path"] is not None:
            updates["roms_path"] = ";".join(
                p.strip().replace("\\", "/")
                for p in str(updates["roms_path"]).split(";")
                if p.strip()
            )
        lst = self._store.game_lists[lid]
        lst.update(updates)
        if "default_emulator_id" in updates:
            raw_e = lst.get("default_emulator_id")
            lst["default_emulator_id"] = int(raw_e) if (raw_e is not None and str(raw_e).strip() != "") else None
        if "source_list_id" in updates:
            raw_s = lst.get("source_list_id")
            lst["source_list_id"] = int(raw_s) if (raw_s is not None and str(raw_s).strip() != "") else None
        self._store._dirty_lists.add(lid)
        self._store.flush()
        return lid

    def delete_list(self, list_id: int) -> int:
        """Elimina una lista y su archivo .txt en lists/."""
        lid = int(list_id)
        if lid in self._store.game_lists:
            for g in self._store.games_by_list.pop(lid, []):
                self._store.games_by_id.pop(g["id"], None)
            del self._store.game_lists[lid]
            self._store.menu_items.pop(lid, None)
            for mid, items in self._store.menu_items.items():
                if lid in items:
                    items.remove(lid)
                    self._store._dirty_lists.add(mid)
            for other_id, other_lst in self._store.game_lists.items():
                if other_lst.get("source_list_id") == lid:
                    other_lst["source_list_id"] = None
                    self._store._dirty_lists.add(other_id)
            self._store._dirty_lists.add(lid)
            self._store.flush()
        return lid

    def get_menu_items(self, menu_id: int) -> list[RowDict]:
        target_ids = self._store.menu_items.get(int(menu_id), [])
        result: list[RowDict] = []
        for idx, tid in enumerate(target_ids):
            gl = self._store.game_lists.get(tid)
            if gl:
                d = RowDict(gl)
                d["sort_order"] = idx
                result.append(d)
        return result

    def set_menu_items(self, menu_id: int, target_list_ids: list[int]):
        mid = int(menu_id)
        dedup: list[int] = []
        for tid in target_list_ids:
            t_int = int(tid)
            if t_int not in dedup:
                dedup.append(t_int)
        self._store.menu_items[mid] = dedup
        self._store._dirty_lists.add(mid)
        self._store.flush()

    # ------------------------------------------------------------------
    # 4. JUEGOS (sección [Games] en lists/<NombreLista>.txt)
    # ------------------------------------------------------------------
    def count_games(self, list_id: int) -> int:
        return len(self._store.games_by_list.get(int(list_id), []))

    def get_game(self, game_id: int | None) -> RowDict | None:
        if game_id is None:
            return None
        g = self._store.games_by_id.get(int(game_id))
        return RowDict(g) if g else None

    def get_game_by_path(self, list_id: int, rom_path: str) -> RowDict | None:
        lid = int(list_id)
        target_path = str(rom_path or "").lower()
        for g in self._store.games_by_list.get(lid, []):
            if (g.get("rom_path") or "").lower() == target_path:
                return RowDict(g)
        return None

    def get_games(self, list_id: int, search_term: str = "", enriched: bool = True) -> list[RowDict]:
        """
        Devuelve los juegos de una lista filtrados por término de búsqueda y ordenados por título.
        Si enriched=True, adjunta las rutas multimedia de la lista y el emulador efectivo.
        """
        lid = int(list_id)
        games = self._store.games_by_list.get(lid, [])
        if not enriched:
            out_raw = [RowDict(g) for g in games]
            out_raw.sort(key=lambda item: (item.get("title") or "").lower())
            return out_raw

        term = (search_term or "").strip().strip("%").lower()
        lst = self._store.game_lists.get(lid, {})
        def_emu_id = lst.get("default_emulator_id")
        base_emu = self._store.emulators.get(def_emu_id) if def_emu_id else None
        base_emu_name = base_emu["name"] if base_emu else None

        out: list[RowDict] = []
        for g in games:
            if term:
                haystack = (
                    f"{g.get('title', '')} {g.get('rom_path', '')} {g.get('rom_name', '')} "
                    f"{g.get('manufacturer', '')} {g.get('year', '')} {g.get('genre', '')} "
                    f"{g.get('sourcefile', '')}"
                ).lower()
                if term not in haystack:
                    continue

            d = RowDict(g)
            d["default_emulator_id"] = def_emu_id
            d["platform"] = lst.get("platform", "")
            d["boxart_path"] = lst.get("boxart_path", "")
            d["flyer_path"] = lst.get("flyer_path", "")
            d["wheel_path"] = lst.get("wheel_path", "")
            d["video_path"] = lst.get("video_path", "")
            d["cartart_path"] = lst.get("cartart_path", "")
            d["cabinet_path"] = lst.get("cabinet_path", "")
            d["marquee_path"] = lst.get("marquee_path", "")
            d["bezel_path"] = lst.get("bezel_path", "")
            d["media_path"] = lst.get("media_path", "")

            ovr_id = g.get("emulator_override_id")
            ovr_emu = self._store.emulators.get(ovr_id) if ovr_id else None
            if ovr_emu:
                d["effective_name"] = ovr_emu["name"]
                d["source"] = "juego"
            elif base_emu_name:
                d["effective_name"] = base_emu_name
                d["source"] = "lista"
            else:
                d["effective_name"] = "Sin emulador"
                d["source"] = "ninguno"

            out.append(d)

        out.sort(key=lambda item: (item.get("title") or "").lower())
        return out

    def insert_game(self, list_id: int, **fields) -> int:
        """Agrega un juego a la lista indicada y actualiza su archivo .txt en lists/."""
        lid = int(list_id)
        rom_path = str(fields.get("rom_path") or "")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        gid = self._store._next_game_id
        self._store._next_game_id += 1

        emu_ovr = fields.get("emulator_override_id")
        if emu_ovr is not None and str(emu_ovr).strip() != "":
            emu_ovr = int(emu_ovr)
        else:
            emu_ovr = None

        g_dict = {
            "id": gid,
            "list_id": lid,
            "title": str(fields.get("title") or Path(rom_path).stem),
            "rom_path": rom_path,
            "rom_name": str(fields.get("rom_name") or Path(rom_path).stem),
            "emulator_override_id": emu_ovr,
            "launch_arguments": str(fields.get("launch_arguments") or ""),
            "cover_path": str(fields.get("cover_path") or ""),
            "notes": str(fields.get("notes") or ""),
            "year": str(fields.get("year") or ""),
            "manufacturer": str(fields.get("manufacturer") or ""),
            "genre": str(fields.get("genre") or ""),
            "players": str(fields.get("players") or ""),
            "cloneof": str(fields.get("cloneof") or ""),
            "rating": str(fields.get("rating") or ""),
            "crc": str(fields.get("crc") or ""),
            "sourcefile": str(fields.get("sourcefile") or ""),
            "bezel_hud_mode": str(fields.get("bezel_hud_mode") or ""),
            "xml_metadata": str(fields.get("xml_metadata") or "{}"),
            "created_at": str(fields.get("created_at") or now_str),
        }
        self._store.games_by_id[gid] = g_dict
        self._store.games_by_list.setdefault(lid, []).append(g_dict)
        self._store._dirty_lists.add(lid)
        self._store.flush()
        return gid

    def update_game(self, game_id: int, **updates) -> int | None:
        """Actualiza los campos de un juego y su archivo .txt en lists/."""
        gid = int(game_id)
        if gid not in self._store.games_by_id:
            return None
        g = self._store.games_by_id[gid]
        g.update(updates)
        if "emulator_override_id" in updates:
            raw_e = g.get("emulator_override_id")
            g["emulator_override_id"] = int(raw_e) if (raw_e is not None and str(raw_e).strip() != "") else None
        self._store._dirty_lists.add(int(g["list_id"]))
        self._store.flush()
        return gid

    def delete_game(self, game_id: int) -> int:
        """Quita un juego de su lista y actualiza su archivo .txt en lists/."""
        gid = int(game_id)
        g = self._store.games_by_id.pop(gid, None)
        if g:
            lid = int(g["list_id"])
            if lid in self._store.games_by_list:
                self._store.games_by_list[lid] = [
                    item for item in self._store.games_by_list[lid] if item["id"] != gid
                ]
            self._store._dirty_lists.add(lid)
            self._store.flush()
        return gid

    def clear_list_games(self, list_id: int) -> int:
        """Elimina todos los juegos registrados en la lista indicada y actualiza su archivo .txt."""
        lid = int(list_id)
        old_games = self._store.games_by_list.get(lid, [])
        removed = len(old_games)
        for g in old_games:
            self._store.games_by_id.pop(g["id"], None)
        self._store.games_by_list[lid] = []
        self._store._dirty_lists.add(lid)
        self._store.flush()
        return removed
