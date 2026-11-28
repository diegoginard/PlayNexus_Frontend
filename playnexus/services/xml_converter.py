"""
Conversor multi-fuente en streaming de catálogos XML / DAT / INI a formato ultrarrápido
PlayNexus (.pncat) con selección dinámica de columnas y lector de alta velocidad en texto plano.

Formato '.pncat' (PlayNexus Fast Catalog v1):
- Texto plano UTF-8 orientado a líneas (100% portable, sin bases binarias SQLite).
- Cabecera identificadora: '# PlayNexus Fast Catalog v1'
- Línea de esquema dinámico: '# columns: keys\trom_name\t<col_1>\t<col_2>...'
  conteniendo únicamente las columnas elegidas por el usuario.
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Sequence
import xml.etree.ElementTree as ET

PNCAT_EXT = ".pncat"
PNCAT_HEADER = "# PlayNexus Fast Catalog v1"

_BARE_AMP_RE = re.compile(r"&(?!amp;|lt;|gt;|apos;|quot;|#\d+;|#x[0-9a-fA-F]+;)")

# Definición canónica de grupos de columnas seleccionables por el usuario:
# (group_id, i18n_key, fallback_label_en, pncat_columns, default_checked)
COLUMN_GROUPS_SPEC: tuple[tuple[str, str, str, tuple[str, ...], bool], ...] = (
    ("title", "xmlconv.colgrp.title", "Full Title (title)", ("title",), True),
    ("year", "xmlconv.colgrp.year", "Year (year)", ("year",), True),
    ("manufacturer", "xmlconv.colgrp.manufacturer", "Manufacturer (manufacturer)", ("manufacturer",), True),
    ("genre", "xmlconv.colgrp.genre", "Genre (genre)", ("genre",), True),
    ("players", "xmlconv.colgrp.players", "Players (players)", ("players",), True),
    ("cloneof", "xmlconv.colgrp.cloneof", "Clone Of (cloneof)", ("cloneof",), True),
    ("bios", "xmlconv.colgrp.bios", "System BIOS (bios)", ("bios",), True),
    ("romof", "xmlconv.colgrp.romof", "Base ROM (romof)", ("romof",), True),
    ("sourcefile", "xmlconv.colgrp.sourcefile", "Board / Driver (sourcefile)", ("sourcefile",), True),
    ("orientation", "xmlconv.colgrp.orientation", "Screen Rotation (display_rotate)", ("display_rotate", "display_type"), True),
    ("resolution", "xmlconv.colgrp.resolution", "Resolution (width × height)", ("display_width", "display_height"), False),
    ("controls", "xmlconv.colgrp.controls", "Controls & Buttons", ("control_type", "control_buttons"), False),
    ("status", "xmlconv.colgrp.status", "Driver Status (status)", ("status",), True),
    ("mame_flags", "xmlconv.colgrp.mame_flags", "MAME Flags (bios/device/mech/run)", ("isbios", "isdevice", "ismechanical", "runnable"), True),
    ("crc", "xmlconv.colgrp.crc", "CRC32 (crc)", ("crc",), False),
    ("rating", "xmlconv.colgrp.rating", "Rating (rating)", ("rating",), False),
    ("notes", "xmlconv.colgrp.notes", "Notes / Synopsis (notes)", ("notes",), False),
)

MANDATORY_COLUMNS: tuple[str, ...] = ("keys", "rom_name")

ALL_KNOWN_COLUMNS: frozenset[str] = frozenset(
    MANDATORY_COLUMNS + tuple(col for _, _, _, cols, _ in COLUMN_GROUPS_SPEC for col in cols) + ("extra_json",)
)

# Columnas directas del diccionario principal de entrada vs propiedades técnicas
_ENTRY_TOP_LEVEL_COLS: frozenset[str] = frozenset({
    "rom_name",
    "title",
    "year",
    "manufacturer",
    "genre",
    "players",
    "cloneof",
    "bios",
    "rating",
    "crc",
    "sourcefile",
    "notes",
})

# Nodos hijos relevantes al extraer desde XML/DAT
_RELEVANT_CHILD_TAGS = frozenset({
    "description",
    "title",
    "fullname",
    "label",
    "name",
    "id",
    "path",
    "rom",
    "filename",
    "file",
    "romname",
    "year",
    "date",
    "releasedate",
    "manufacturer",
    "developer",
    "publisher",
    "company",
    "maker",
    "genre",
    "category",
    "type",
    "players",
    "nplayers",
    "cloneof",
    "romof",
    "bios",
    "biosset",
    "rating",
    "score",
    "crc",
    "sourcefile",
    "source_file",
    "desc",
    "plot",
    "synopsis",
    "story",
    "history",
    "notes",
    "input",
    "driver",
    "display",
    "video",
})


def sanitize_custom_column_name(raw_name: str | None) -> str:
    """
    Normaliza el nombre de una columna personalizada elegida por el usuario o derivada de un .ini
    (ej. '[GAMING HISTORY] Arcade By Decade' -> 'arcade_by_decade', 'Series' -> 'series').
    """
    s = str(raw_name or "").strip()
    if not s:
        return ""
    # Quitar etiquetas entre corchetes al inicio como '[GAMING HISTORY]'
    s = re.sub(r"^\s*\[[^\]]*\]\s*", "", s)
    s = s.lower()
    # Reemplazar caracteres acentuados comunes para claves limpias y portables
    for src_ch, dst_ch in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")):
        s = s.replace(src_ch, dst_ch)
    s = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    if s in ("keys", "rom_name", "extra_json"):
        s = f"custom_{s}"
    return s


def suggest_custom_column_from_ini(path: str | Path) -> str:
    """Sugiere un identificador limpio de columna a partir del nombre de un archivo .ini."""
    stem = Path(path).stem
    return sanitize_custom_column_name(stem) or "custom_ini"


def read_pncat_schema_columns(pncat_path: str | Path | None) -> list[str]:
    """
    Lee en <1 ms únicamente las líneas de cabecera '#' de un archivo '.pncat'
    y retorna la lista exacta de columnas definidas en '# columns: ...'.
    """
    if not pncat_path:
        return []
    p = Path(pncat_path)
    if not p.is_file() or not is_fast_catalog_file(p):
        return []
    try:
        with open(p, "r", encoding="utf-8-sig") as fh:
            for _ in range(25):
                line = fh.readline()
                if not line:
                    break
                if line.startswith("# columns:"):
                    cols = [c.strip() for c in line[10:].strip().split("\t") if c.strip()]
                    return cols
                if line and line[0] not in ("#", "\r", "\n"):
                    break
    except OSError:
        return []
    return []


def default_selected_columns() -> list[str]:
    """Devuelve la lista ordenada de columnas .pncat activas por defecto."""
    cols = list(MANDATORY_COLUMNS)
    for _gid, _ikey, _lbl, gcols, is_def in COLUMN_GROUPS_SPEC:
        if is_def:
            for c in gcols:
                if c not in cols:
                    cols.append(c)
    return cols


def normalize_selected_columns(columns: Sequence[str] | None) -> list[str]:
    """
    Normaliza una lista de grupos, columnas estándar o columnas personalizadas (.ini)
    asegurando que 'keys' y 'rom_name' vayan siempre en las posiciones 0 y 1.
    """
    if not columns:
        return default_selected_columns()

    group_map = {gid: gcols for gid, _, _, gcols, _ in COLUMN_GROUPS_SPEC}
    requested: list[str] = list(MANDATORY_COLUMNS)
    for item in columns:
        key = str(item or "").strip()
        if not key:
            continue
        if key in group_map:
            for c in group_map[key]:
                if c not in requested:
                    requested.append(c)
        elif key in ALL_KNOWN_COLUMNS:
            if key not in requested:
                requested.append(key)
        else:
            custom_c = sanitize_custom_column_name(key)
            if custom_c and custom_c not in requested:
                requested.append(custom_c)
    return requested


@dataclass
class SourceSpec:
    path: str
    role: str = "auto"  # "auto" | "catalog" | "genre" | "players" | "manufacturer" | "year" | "notes" | "custom"
    custom_column: str = ""


@dataclass
class ConvertOptions:
    selected_columns: list[str] | None = None
    profile: str = "optimized"
    genre_ini_path: str = ""
    exclude_devices: bool = False
    exclude_mechanical: bool = False
    exclude_clones: bool = False
    exclude_non_runnable: bool = False


@dataclass
class ConvertSummary:
    source_path: str
    output_path: str
    profile: str = "custom"
    sources_count: int = 1
    columns_written: list[str] = field(default_factory=list)
    total_seen: int = 0
    written_entries: int = 0
    genres_assigned: int = 0
    skipped_devices: int = 0
    skipped_mechanical: int = 0
    skipped_clones: int = 0
    skipped_non_runnable: int = 0
    source_size_bytes: int = 0
    output_size_bytes: int = 0
    elapsed_seconds: float = 0.0
    cancelled: bool = False

    @property
    def total_skipped(self) -> int:
        return (
            self.skipped_devices
            + self.skipped_mechanical
            + self.skipped_clones
            + self.skipped_non_runnable
        )

    @property
    def size_reduction_pct(self) -> float:
        if self.source_size_bytes <= 0 or self.output_size_bytes <= 0:
            return 0.0
        ratio = 1.0 - (self.output_size_bytes / float(self.source_size_bytes))
        return max(0.0, ratio * 100.0)


def _esc_field(val: str) -> str:
    if not val:
        return ""
    if "\\" not in val and "\t" not in val and "\n" not in val and "\r" not in val:
        return val
    return (
        val.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _unesc_field(val: str) -> str:
    if not val or "\\" not in val:
        return val
    out: list[str] = []
    i = 0
    n = len(val)
    while i < n:
        ch = val[i]
        if ch == "\\" and i + 1 < n:
            nxt = val[i + 1]
            if nxt == "t":
                out.append("\t")
                i += 2
                continue
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "r":
                out.append("\r")
                i += 2
                continue
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def is_fast_catalog_file(path: str | Path | None) -> bool:
    """Detecta rápidamente si un archivo es un catálogo rápido PlayNexus (.pncat)."""
    if not path:
        return False
    p = Path(path)
    if p.suffix.lower() == PNCAT_EXT:
        return True
    if not p.is_file():
        return False
    try:
        with open(p, "rb") as fh:
            head = fh.read(64)
        if head.startswith(b"\xef\xbb\xbf"):
            head = head[3:]
        return head.startswith(PNCAT_HEADER.encode("utf-8"))
    except OSError:
        return False


def infer_ini_role(path: str | Path) -> str:
    """
    Sugiere el campo de destino inicial cuando el usuario elige un archivo .ini.
    Si no corresponde a una de las columnas estándar (género, jugadores, fabricante, año),
    sugiere 'custom' para crear una columna propia con el nombre del .ini.
    """
    stem = re.sub(r"^\s*\[[^\]]*\]\s*", "", Path(path).stem).strip().lower()
    if stem in ("catver", "category", "categories", "genre", "genres") or "catver" in stem or stem.startswith("genre"):
        return "genre"
    if any(k in stem for k in ("nplayer", "player")):
        return "players"
    if any(k in stem for k in ("manuf", "maker", "developer", "publisher")):
        return "manufacturer"
    if stem in ("year", "years"):
        return "year"
    return "custom"


class _SanitizingXmlStream(io.RawIOBase):
    """Flujo de respaldo para XMLs con '&' sin escapar o codificaciones antiguas."""

    def __init__(self, file_path: Path, chunk_size: int = 524_288):
        super().__init__()
        self._fh = open(file_path, "rb")
        self._chunk_size = chunk_size
        self.bytes_read = 0
        self.total_bytes = max(1, os.path.getsize(file_path))
        self._out_buf = bytearray()
        self._carry_text = ""
        self._eof = False
        self._first_chunk = True
        self._decoder = None

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        try:
            self._fh.close()
        finally:
            super().close()

    def _init_decoder(self, raw: bytes) -> bytes:
        if raw.startswith(b"\xff\xfe"):
            self._decoder = codecs.getincrementaldecoder("utf-16-le")(errors="replace")
            return raw[2:]
        if raw.startswith(b"\xfe\xff"):
            self._decoder = codecs.getincrementaldecoder("utf-16-be")(errors="replace")
            return raw[2:]
        if raw.startswith(b"\xef\xbb\xbf"):
            self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            return raw[3:]
        head_ascii = raw[:256].decode("ascii", errors="ignore").lower()
        enc = "utf-8"
        if "iso-8859-1" in head_ascii or "latin-1" in head_ascii or "latin1" in head_ascii:
            enc = "latin-1"
        elif "windows-1252" in head_ascii or "cp1252" in head_ascii:
            enc = "cp1252"
        self._decoder = codecs.getincrementaldecoder(enc)(errors="replace")
        return raw

    def _fill_buffer(self) -> None:
        if self._eof:
            return
        raw = self._fh.read(self._chunk_size)
        if not raw:
            self._eof = True
            tail = self._carry_text
            if self._decoder is not None:
                tail += self._decoder.decode(b"", final=True)
            self._carry_text = ""
            if tail:
                if "&" in tail:
                    tail = _BARE_AMP_RE.sub("&amp;", tail)
                self._out_buf.extend(tail.encode("utf-8"))
            return

        self.bytes_read += len(raw)
        if self._first_chunk:
            raw = self._init_decoder(raw)
            text = self._carry_text + self._decoder.decode(raw, final=False)
            text = re.sub(
                r'(<\?xml[^>]*encoding\s*=\s*["\'])[^"\']+(["\'])',
                r"\1utf-8\2",
                text,
                count=1,
                flags=re.IGNORECASE,
            )
            self._first_chunk = False
        else:
            text = self._carry_text + self._decoder.decode(raw, final=False)

        self._carry_text = ""
        tail_window = text[-16:]
        amp_pos = tail_window.rfind("&")
        if amp_pos != -1 and ";" not in tail_window[amp_pos:]:
            cut = len(text) - len(tail_window) + amp_pos
            self._carry_text = text[cut:]
            text = text[:cut]

        if "&" in text:
            text = _BARE_AMP_RE.sub("&amp;", text)

        if text:
            self._out_buf.extend(text.encode("utf-8"))

    def readinto(self, b: bytearray | memoryview) -> int:
        target_len = len(b)
        while len(self._out_buf) < target_len and not self._eof:
            self._fill_buffer()
        if not self._out_buf:
            return 0
        n = min(target_len, len(self._out_buf))
        b[:n] = self._out_buf[:n]
        del self._out_buf[:n]
        return n


def extract_catalog_entry(elem: ET.Element, optimized: bool = True) -> tuple[list[str], dict] | None:
    """Extrae las claves normalizadas y metadatos desde un nodo XML (<machine>, <game>, <item>)."""
    props: dict[str, str] = {}
    raw_children: dict[str, str] = {}
    rom_child_names: list[str] = []
    has_crc = False

    attrib = elem.attrib
    for k, v in attrib.items():
        if v:
            val = v.strip()
            if val:
                props[k.strip().lower()] = val

    for ch in elem:
        raw_tag = ch.tag
        if not isinstance(raw_tag, str):
            continue
        tag_lower = raw_tag.rsplit("}", 1)[-1].lower() if "}" in raw_tag else raw_tag.lower()

        if optimized and tag_lower not in _RELEVANT_CHILD_TAGS:
            continue

        if tag_lower == "rom":
            if has_crc and len(rom_child_names) >= 2:
                continue
            ch_attr = ch.attrib
            r_name = (ch_attr.get("name") or "").strip()
            if r_name and len(rom_child_names) < 2:
                rom_child_names.append(r_name)
            if not has_crc:
                rv = (ch_attr.get("crc") or "").strip()
                if rv:
                    props["crc"] = rv
                    has_crc = True
            if not optimized:
                for rk in ("md5", "sha1", "size"):
                    if rk not in props:
                        rv2 = (ch_attr.get(rk) or "").strip()
                        if rv2:
                            props[rk] = rv2
            text = (ch.text or "").strip()
            if text and "rom" not in raw_children:
                raw_children["rom"] = text
                props["rom"] = text
        elif tag_lower == "biosset":
            ch_attr = ch.attrib
            bs_name = (ch_attr.get("name") or "").strip()
            bs_desc = (ch_attr.get("description") or "").strip()
            is_def = (ch_attr.get("default") or "").strip().lower() == "yes"
            if bs_name and (is_def or "biosset_name" not in props):
                props["biosset_name"] = bs_name
                if bs_desc:
                    props["biosset_description"] = bs_desc
        elif tag_lower == "input":
            for ik, iv in ch.attrib.items():
                if iv:
                    iv_s = iv.strip()
                    if iv_s:
                        ik_l = ik.lower()
                        if ik_l == "players" and "players" not in props:
                            props["players"] = iv_s
                        props[f"input_{ik_l}"] = iv_s
            for sub in ch:
                sub_tag = sub.tag
                if isinstance(sub_tag, str) and (sub_tag == "control" or sub_tag.endswith("}control")):
                    for ck, cv in sub.attrib.items():
                        if cv:
                            ck_key = f"control_{ck.lower()}"
                            if ck_key not in props:
                                props[ck_key] = cv.strip()
        elif tag_lower == "driver":
            for dk, dv in ch.attrib.items():
                if dv:
                    dk_l = dk.lower()
                    dv_s = dv.strip()
                    props[f"driver_{dk_l}"] = dv_s
                    if dk_l == "status" and "status" not in props:
                        props["status"] = dv_s
        else:
            text = (ch.text or "").strip()
            if text:
                raw_children[tag_lower] = text
                props[tag_lower] = text
            ch_attr = ch.attrib
            if ch_attr:
                for ak, av in ch_attr.items():
                    if av:
                        ak_key = f"{tag_lower}_{ak.lower()}"
                        if ak_key not in props:
                            props[ak_key] = av.strip()

    attr_rom = (
        attrib.get("name")
        or attrib.get("rom")
        or attrib.get("filename")
        or attrib.get("file")
        or ""
    ).strip()

    path_child = (
        raw_children.get("path")
        or raw_children.get("rom")
        or raw_children.get("filename")
        or raw_children.get("file")
        or raw_children.get("romname")
        or ""
    ).strip()

    keys: list[str] = []
    full_title = ""

    if attr_rom:
        keys.append(attr_rom)
        if path_child:
            keys.append(path_child)
        full_title = (
            raw_children.get("description")
            or raw_children.get("title")
            or raw_children.get("fullname")
            or raw_children.get("label")
            or raw_children.get("name")
            or attrib.get("description")
            or attrib.get("title")
            or attr_rom
        ).strip()
    elif path_child:
        keys.append(path_child)
        full_title = (
            raw_children.get("name")
            or raw_children.get("title")
            or raw_children.get("fullname")
            or raw_children.get("label")
            or raw_children.get("description")
            or Path(path_child.replace("\\", "/")).stem
        ).strip()
    else:
        fallback_key = (
            raw_children.get("name")
            or attrib.get("id")
            or raw_children.get("id")
            or ""
        ).strip()
        if not fallback_key and len(rom_child_names) == 1:
            fallback_key = rom_child_names[0]
        if fallback_key:
            keys.append(fallback_key)
        full_title = (
            raw_children.get("description")
            or raw_children.get("title")
            or raw_children.get("fullname")
            or raw_children.get("label")
            or raw_children.get("name")
            or fallback_key
        ).strip()

    if len(rom_child_names) == 1:
        keys.append(rom_child_names[0])

    if not keys:
        return None

    normalized_keys: list[str] = []
    primary_rom_name = ""
    for k in keys:
        clean_k = k.replace("\\", "/").strip()
        if not clean_k:
            continue
        slash_idx = clean_k.rfind("/")
        fname = clean_k[slash_idx + 1:] if slash_idx >= 0 else clean_k
        dot_idx = fname.rfind(".")
        stem = fname[:dot_idx] if dot_idx > 0 else fname
        if not primary_rom_name:
            primary_rom_name = stem or fname
        for candidate in (stem.lower(), fname.lower(), clean_k.lower()):
            if candidate and candidate not in normalized_keys:
                normalized_keys.append(candidate)

    if not normalized_keys:
        return None

    year = (props.get("year") or props.get("date") or "").strip()
    if not year and props.get("releasedate"):
        rd = props["releasedate"].strip()
        if len(rd) >= 4 and rd[:4].isdigit():
            year = rd[:4]

    manufacturer = (
        props.get("manufacturer")
        or props.get("developer")
        or props.get("publisher")
        or props.get("company")
        or props.get("maker")
        or ""
    ).strip()

    genre = (
        props.get("genre")
        or props.get("category")
        or props.get("type")
        or ""
    ).strip()

    players = (props.get("players") or props.get("nplayers") or "").strip()
    cloneof = (props.get("cloneof") or "").strip()
    romof = (props.get("romof") or "").strip()
    bios_explicit = (props.get("bios") or "").strip()
    if not bios_explicit and romof and romof.lower() != cloneof.lower():
        bios_explicit = romof

    rating = (props.get("rating") or props.get("score") or "").strip()
    crc = (props.get("crc") or "").strip()
    sourcefile = (
        props.get("sourcefile")
        or props.get("source_file")
        or attrib.get("sourcefile")
        or ""
    ).strip()

    notes = (
        raw_children.get("desc")
        or raw_children.get("plot")
        or raw_children.get("synopsis")
        or raw_children.get("story")
        or raw_children.get("history")
        or raw_children.get("notes")
        or ""
    ).strip()

    props["rom_name"] = primary_rom_name
    props["title"] = full_title or primary_rom_name
    if sourcefile:
        props["sourcefile"] = sourcefile
    if bios_explicit:
        props["bios"] = bios_explicit

    entry = {
        "title": full_title or primary_rom_name,
        "rom_name": primary_rom_name,
        "year": year,
        "manufacturer": manufacturer,
        "genre": genre,
        "players": players,
        "cloneof": cloneof,
        "bios": bios_explicit,
        "rating": rating,
        "crc": crc,
        "sourcefile": sourcefile,
        "notes": notes,
        "properties": props,
    }
    return normalized_keys, entry


def parse_mame_ini_mapping(ini_path: str | Path | None) -> dict[str, str]:
    """
    Lee cualquier archivo .ini de MAME y devuelve {rom_name_lower: valor}:
      1. Formato clave=valor ('catver.ini' [Category], 'nplayers.ini' [NPlayers], etc.),
         ignorando secciones de versión o ajustes ([VerAdded], [FOLDER_SETTINGS], [ROOT_FOLDER]).
      2. Formato carpetas MAMEUI / Arcade64 ('Category.ini', 'Manufacturer.ini', 'Year.ini', 'Series.ini'):
         secciones '[Valor]' seguidas de nombres de ROM uno por línea.
    """
    if not ini_path:
        return {}
    p = Path(ini_path)
    if not p.is_file():
        return {}

    raw = p.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")

    ignored_sections = {
        "",
        "folder_settings",
        "root_folder",
        "veradded",
        "version",
        "settings",
        "general",
    }
    trailing_num_re = re.compile(r"\s*/\s*\d+$")

    mapping: dict[str, str] = {}
    current_section = ""
    current_sec_lower = ""

    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s[0] in (";", "#") or s.startswith("//"):
            continue
        if s[0] == "[" and s[-1] == "]":
            sec = s[1:-1].strip()
            current_sec_lower = sec.lower()
            current_section = trailing_num_re.sub("", sec).strip()
            continue

        if current_sec_lower in ignored_sections:
            continue

        if "=" in s:
            k, v = s.split("=", 1)
            rk = k.strip().lower()
            val = v.strip()
            if rk and val:
                mapping.setdefault(rk, val)
        else:
            if " " not in s and "\t" not in s and current_section:
                rk = s.lower()
                mapping.setdefault(rk, current_section)

    return mapping


# Alias de compatibilidad
parse_mame_genre_ini = parse_mame_ini_mapping


def _merge_catalog_entry(
    existing_keys: list[str],
    existing_entry: dict,
    new_keys: list[str],
    new_entry: dict,
) -> None:
    """
    Fusiona los datos de una fuente secundaria sobre una entrada ya existente sin pisar
    valores no vacíos definidos por una fuente de mayor prioridad.
    """
    for k in new_keys:
        if k and k not in existing_keys:
            existing_keys.append(k)

    # Si la primera fuente solo tenía el nombre corto como título y la segunda tiene descripción real
    if (
        (not existing_entry["title"] or existing_entry["title"].lower() == existing_entry["rom_name"].lower())
        and new_entry["title"]
        and new_entry["title"].lower() != new_entry["rom_name"].lower()
    ):
        existing_entry["title"] = new_entry["title"]
        existing_entry["properties"]["title"] = new_entry["title"]

    for fld in ("year", "manufacturer", "genre", "players", "cloneof", "bios", "rating", "crc", "sourcefile", "notes"):
        if not existing_entry.get(fld) and new_entry.get(fld):
            existing_entry[fld] = new_entry[fld]
            if fld != "notes":
                existing_entry["properties"][fld] = new_entry[fld]

    ex_props = existing_entry["properties"]
    for pk, pv in new_entry["properties"].items():
        if pv and not ex_props.get(pk):
            ex_props[pk] = pv


def _format_dynamic_pncat_line(keys: list[str], entry: dict, columns: Sequence[str]) -> str:
    """Serializa una fila del archivo .pncat conteniendo exactamente las columnas seleccionadas."""
    props = entry["properties"]
    out_cells: list[str] = []

    for col in columns:
        if col == "keys":
            out_cells.append("|".join(_esc_field(k) for k in keys if k))
        elif col in _ENTRY_TOP_LEVEL_COLS:
            val = entry.get(col) or props.get(col, "")
            out_cells.append(_esc_field(str(val) if val else ""))
        elif col == "status":
            val = props.get("status") or props.get("driver_status") or ""
            out_cells.append(_esc_field(val))
        else:
            val = props.get(col, "")
            out_cells.append(_esc_field(str(val) if val else ""))

    return "\t".join(out_cells)


def build_pncat_from_sources(
    sources: Sequence[SourceSpec | str | Path],
    output_pncat_path: str | Path,
    options: ConvertOptions | None = None,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> ConvertSummary:
    """
    Construye un catálogo rápido '.pncat' combinando cualquier cantidad (1..N) de fuentes
    (.xml, .dat, .pncat e .ini) en el orden indicado y escribiendo únicamente las columnas elegidas.
    """
    opts = options or ConvertOptions()
    columns = normalize_selected_columns(opts.selected_columns)
    optimized = opts.profile != "full"

    norm_sources: list[SourceSpec] = []
    for item in sources:
        if isinstance(item, SourceSpec):
            p_str = item.path.strip()
            if p_str:
                norm_sources.append(
                    SourceSpec(
                        path=p_str,
                        role=item.role or "auto",
                        custom_column=item.custom_column or "",
                    )
                )
        else:
            p_str = str(item or "").strip()
            if p_str:
                norm_sources.append(SourceSpec(path=p_str, role="auto"))

    # Compatibilidad con llamadas que pasaban genre_ini_path en ConvertOptions
    if opts.genre_ini_path and opts.genre_ini_path.strip():
        g_path = opts.genre_ini_path.strip()
        if all(os.path.abspath(s.path).lower() != os.path.abspath(g_path).lower() for s in norm_sources):
            norm_sources.append(SourceSpec(path=g_path, role="genre"))

    if not norm_sources:
        raise ValueError("Debes agregar al menos un archivo de origen (.xml, .dat o .ini).")

    catalog_sources: list[Path] = []
    ini_sources: list[tuple[Path, str]] = []
    total_bytes = 0

    standard_ini_roles = {"genre", "players", "manufacturer", "year", "notes"}
    for spec in norm_sources:
        p = Path(spec.path)
        if not p.is_file():
            raise FileNotFoundError(f"No existe el archivo de origen: {p}")
        total_bytes += os.path.getsize(p)
        ext = p.suffix.lower()
        role = (spec.role or "auto").strip().lower()
        if ext == ".ini" or role != "catalog" and role != "auto":
            if role in ("auto", "catalog", ""):
                inferred = infer_ini_role(p)
                if inferred == "custom":
                    target_col = sanitize_custom_column_name(spec.custom_column) or suggest_custom_column_from_ini(p)
                else:
                    target_col = inferred
            elif role == "custom":
                target_col = sanitize_custom_column_name(spec.custom_column) or suggest_custom_column_from_ini(p)
            elif role in standard_ini_roles:
                target_col = role
            else:
                target_col = sanitize_custom_column_name(spec.custom_column or role) or suggest_custom_column_from_ini(p)
            ini_sources.append((p, target_col))
            # Si el usuario no pasó selected_columns explícito (uso por API), incluir las columnas personalizadas nuevas
            if opts.selected_columns is None and target_col not in columns:
                columns.append(target_col)
        else:
            catalog_sources.append(p)

    if not catalog_sources:
        raise ValueError("Debes incluir al menos una fuente de catálogo (.xml o .dat) con juegos.")

    total_bytes = max(1, total_bytes)
    dst = Path(output_pncat_path)
    if dst.suffix.lower() != PNCAT_EXT:
        dst = dst.with_suffix(PNCAT_EXT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_name(dst.name + ".tmp")

    t0 = time.perf_counter()
    summary = ConvertSummary(
        source_path="; ".join(str(s.path) for s in norm_sources),
        output_path=str(dst),
        profile=opts.profile,
        sources_count=len(norm_sources),
        columns_written=list(columns),
        source_size_bytes=total_bytes,
    )

    merged_by_rom: dict[str, tuple[list[str], dict]] = {}
    bios_names: dict[str, str] = {}
    parent_links: dict[str, str] = {}
    clone_links: dict[str, str] = {}
    cumulative_bytes_before = 0

    def _register_entry(keys: list[str], entry: dict) -> None:
        props = entry["properties"]
        r_low = entry["rom_name"].lower()
        romof_val = props.get("romof", "")
        clone_val = entry["cloneof"]
        is_bios_entry = props.get("isbios", "").lower() in ("yes", "true", "1")

        if is_bios_entry:
            bios_names[r_low] = entry["rom_name"]
        elif romof_val and romof_val.lower() != clone_val.lower():
            bios_names.setdefault(romof_val.lower(), romof_val)
        if romof_val or clone_val:
            parent_links.setdefault(r_low, (romof_val or clone_val).lower())
        if clone_val:
            clone_links.setdefault(r_low, clone_val.lower())

        if r_low in merged_by_rom:
            ex_keys, ex_entry = merged_by_rom[r_low]
            _merge_catalog_entry(ex_keys, ex_entry, keys, entry)
        else:
            merged_by_rom[r_low] = (keys, entry)

    def _stream_single_xml(src_file: Path, target_tags: frozenset[str], use_sanitizer: bool) -> int:
        found_in_pass = 0
        if use_sanitizer:
            reader = _SanitizingXmlStream(src_file)
            tell_fn = lambda: reader.bytes_read
        else:
            reader = open(src_file, "rb", buffering=1024 * 1024)
            tell_fn = reader.tell

        try:
            context = ET.iterparse(reader, events=("end",))
            last_report_t = 0.0

            for _event, elem in context:
                raw_tag = elem.tag
                if not isinstance(raw_tag, str):
                    continue
                tag = raw_tag.rsplit("}", 1)[-1].lower() if "}" in raw_tag else raw_tag.lower()
                if tag not in target_tags:
                    continue

                if cancel_check and (summary.total_seen & 0xFF) == 0 and cancel_check():
                    summary.cancelled = True
                    elem.clear()
                    return found_in_pass

                summary.total_seen += 1
                found_in_pass += 1
                extracted = extract_catalog_entry(elem, optimized=optimized)
                elem.clear()

                if extracted is not None:
                    keys, entry = extracted
                    _register_entry(keys, entry)

                if progress_callback and (summary.total_seen & 0x1FF) == 0:
                    now = time.perf_counter()
                    if now - last_report_t >= 0.08:
                        last_report_t = now
                        b_read = cumulative_bytes_before + tell_fn()
                        pct = min(94, int((b_read * 94) / total_bytes))
                        progress_callback(pct, summary.total_seen, len(merged_by_rom), b_read)
        finally:
            reader.close()

        return found_in_pass

    primary_tags = frozenset({"machine", "game", "item"})

    try:
        for cat_file in catalog_sources:
            if cancel_check and cancel_check():
                summary.cancelled = True
                break

            f_size = os.path.getsize(cat_file)
            if is_fast_catalog_file(cat_file):
                entries_list, _cols = read_fast_catalog_table(cat_file)
                for entry in entries_list:
                    summary.total_seen += 1
                    r_name = entry["rom_name"]
                    keys = entry.get("_keys") or [r_name.lower()]
                    _register_entry(list(keys), entry)
            else:
                # Respaldar estado por si un XML requiere reintento con sanitizador de '&'
                snap_merged = len(merged_by_rom)
                snap_seen = summary.total_seen
                used_sanitizer = False
                try:
                    cnt = _stream_single_xml(cat_file, primary_tags, use_sanitizer=False)
                except ET.ParseError:
                    used_sanitizer = True
                    if snap_merged == 0:
                        merged_by_rom.clear()
                        bios_names.clear()
                        parent_links.clear()
                        clone_links.clear()
                    summary.total_seen = snap_seen
                    cnt = _stream_single_xml(cat_file, primary_tags, use_sanitizer=True)

                if not summary.cancelled and cnt == 0:
                    _stream_single_xml(cat_file, frozenset({"rom"}), use_sanitizer=used_sanitizer)

            cumulative_bytes_before += f_size
            if summary.cancelled:
                break

        if summary.cancelled:
            tmp_dst.unlink(missing_ok=True)
            summary.elapsed_seconds = time.perf_counter() - t0
            return summary

        # Cargar fuentes .ini (géneros, jugadores, fabricante, año, notas) en orden de prioridad
        ini_layers: list[tuple[str, dict[str, str]]] = []
        for ini_path, role in ini_sources:
            if cancel_check and cancel_check():
                summary.cancelled = True
                break
            ini_map = parse_mame_ini_mapping(ini_path)
            if ini_map:
                ini_layers.append((role, ini_map))
            cumulative_bytes_before += os.path.getsize(ini_path)

        if summary.cancelled:
            tmp_dst.unlink(missing_ok=True)
            summary.elapsed_seconds = time.perf_counter() - t0
            return summary

        # Resolver herencia de BIOS y aplicar capas .ini (con herencia de padre a clon)
        for _r_low, (_keys, entry) in merged_by_rom.items():
            props = entry["properties"]
            if bios_names:
                if props.get("isbios", "").lower() in ("yes", "true", "1"):
                    entry["bios"] = entry["rom_name"]
                    props["bios"] = entry["rom_name"]
                else:
                    cur_bios = entry.get("bios", "")
                    if cur_bios and cur_bios.lower() in bios_names:
                        canon = bios_names[cur_bios.lower()]
                        entry["bios"] = canon
                        props["bios"] = canon
                    else:
                        visited: set[str] = set()
                        curr = (props.get("romof") or entry.get("cloneof") or "").strip().lower()
                        for _ in range(8):
                            if not curr or curr in visited:
                                break
                            if curr in bios_names:
                                canon = bios_names[curr]
                                entry["bios"] = canon
                                props["bios"] = canon
                                break
                            visited.add(curr)
                            curr = parent_links.get(curr, "")

            for role, ini_map in ini_layers:
                if entry.get(role):
                    continue
                rk = entry["rom_name"].lower()
                resolved_val = ini_map.get(rk, "")
                if not resolved_val:
                    visited_c: set[str] = set()
                    curr_c = entry["cloneof"].lower()
                    for _ in range(6):
                        if not curr_c or curr_c in visited_c:
                            break
                        if curr_c in ini_map:
                            resolved_val = ini_map[curr_c]
                            break
                        visited_c.add(curr_c)
                        curr_c = clone_links.get(curr_c, "")
                if resolved_val:
                    entry[role] = resolved_val
                    if role != "notes":
                        props[role] = resolved_val

            if entry.get("genre"):
                summary.genres_assigned += 1

        # Aplicar pre-filtros opcionales y escribir exactamente las columnas seleccionadas
        src_names_header = " + ".join(Path(s.path).name for s in norm_sources)
        cols_header = "\t".join(columns)

        with open(tmp_dst, "w", encoding="utf-8", buffering=1024 * 1024, newline="\n") as out_fh:
            out_fh.write(f"{PNCAT_HEADER}\n")
            out_fh.write(f"# sources: {src_names_header}\n")
            out_fh.write(f"# generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            out_fh.write(f"# columns: {cols_header}\n")

            for keys, entry in merged_by_rom.values():
                props = entry["properties"]
                is_bios_entry = props.get("isbios", "").lower() in ("yes", "true", "1")
                if not is_bios_entry:
                    if opts.exclude_devices and props.get("isdevice", "").lower() in ("yes", "true", "1"):
                        summary.skipped_devices += 1
                        continue
                    if opts.exclude_mechanical and props.get("ismechanical", "").lower() in ("yes", "true", "1"):
                        summary.skipped_mechanical += 1
                        continue
                    if opts.exclude_non_runnable and props.get("runnable", "").lower() in ("no", "false", "0"):
                        summary.skipped_non_runnable += 1
                        continue
                    if opts.exclude_clones and bool(entry["cloneof"]):
                        summary.skipped_clones += 1
                        continue

                out_fh.write(_format_dynamic_pncat_line(keys, entry, columns) + "\n")
                summary.written_entries += 1

        os.replace(tmp_dst, dst)
        summary.output_size_bytes = os.path.getsize(dst)
        summary.elapsed_seconds = time.perf_counter() - t0
        if progress_callback:
            progress_callback(100, summary.total_seen, summary.written_entries, total_bytes)
        return summary
    except Exception:
        tmp_dst.unlink(missing_ok=True)
        raise


def convert_xml_to_pncat(
    source_xml_path: str | Path,
    output_pncat_path: str | Path,
    options: ConvertOptions | None = None,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> ConvertSummary:
    """Envoltorio compatible para convertir un único XML/DAT (más .ini opcional en options)."""
    return build_pncat_from_sources(
        [SourceSpec(path=str(source_xml_path), role="catalog")],
        output_pncat_path=output_pncat_path,
        options=options,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


_LEGACY_26_COLS: tuple[str, ...] = (
    "keys", "rom_name", "title", "year", "manufacturer", "genre", "players",
    "cloneof", "rating", "crc", "sourcefile", "notes", "bios", "romof",
    "status", "isbios", "isdevice", "ismechanical", "runnable",
    "display_type", "display_rotate", "display_width", "display_height",
    "control_type", "control_buttons", "extra_json",
)

_LEGACY_25_COLS: tuple[str, ...] = (
    "keys", "rom_name", "title", "year", "manufacturer", "genre", "players",
    "cloneof", "rating", "crc", "sourcefile", "notes", "romof",
    "status", "isbios", "isdevice", "ismechanical", "runnable",
    "display_type", "display_rotate", "display_width", "display_height",
    "control_type", "control_buttons", "extra_json",
)


def _parse_fast_catalog_internal(
    pncat_path: str | Path,
    keep_keys_attr: bool = False,
) -> tuple[dict[str, dict], list[str]]:
    """
    Lector dinámico de alta velocidad para cualquier esquema '# columns: ...' de '.pncat'.
    Pre-calcula índices enteros desde la cabecera una sola vez antes del bucle.
    """
    p = Path(pncat_path)
    catalog_map: dict[str, dict] = {}
    unesc = _unesc_field

    header_cols: list[str] | None = None
    idx_map: dict[str, int] = {}
    prop_cols: list[tuple[str, int]] = []

    def _bind_schema(cols: Sequence[str]) -> None:
        nonlocal header_cols, idx_map, prop_cols
        header_cols = list(cols)
        idx_map = {c: i for i, c in enumerate(header_cols)}
        skip_for_props = {"keys", "rom_name", "title", "notes", "extra_json"}
        prop_cols = [(c, i) for i, c in enumerate(header_cols) if c not in skip_for_props]

    with open(p, "r", encoding="utf-8-sig", buffering=1024 * 1024) as fh:
        for raw_line in fh:
            if not raw_line or raw_line[0] in ("\r", "\n"):
                continue
            if raw_line[0] == "#":
                if raw_line.startswith("# columns:"):
                    raw_cols = raw_line[10:].strip().split("\t")
                    if len(raw_cols) >= 2:
                        _bind_schema(raw_cols)
                continue

            line = raw_line[:-1] if raw_line[-1] == "\n" else raw_line
            if line and line[-1] == "\r":
                line = line[:-1]
            if not line:
                continue

            parts = line.split("\t")
            n_parts = len(parts)
            if n_parts < 2:
                continue

            if header_cols is None:
                if n_parts >= 26:
                    _bind_schema(_LEGACY_26_COLS)
                elif n_parts == 25:
                    _bind_schema(_LEGACY_25_COLS)
                else:
                    _bind_schema(_LEGACY_26_COLS[:n_parts])

            has_backslash = "\\" in line

            def _cell(idx: int) -> str:
                if idx < 0 or idx >= n_parts:
                    return ""
                val = parts[idx]
                return unesc(val) if (has_backslash and val) else val

            keys_raw = parts[idx_map.get("keys", 0)] if idx_map.get("keys", 0) < n_parts else ""
            rom_name = _cell(idx_map.get("rom_name", 1))
            title = _cell(idx_map.get("title", -1)) or rom_name
            year = _cell(idx_map.get("year", -1))
            manufacturer = _cell(idx_map.get("manufacturer", -1))
            genre = _cell(idx_map.get("genre", -1))
            players = _cell(idx_map.get("players", -1))
            cloneof = _cell(idx_map.get("cloneof", -1))
            bios = _cell(idx_map.get("bios", -1))
            rating = _cell(idx_map.get("rating", -1))
            crc = _cell(idx_map.get("crc", -1))
            sourcefile = _cell(idx_map.get("sourcefile", -1))
            notes = _cell(idx_map.get("notes", -1))
            extra_raw = _cell(idx_map.get("extra_json", -1))

            props: dict[str, str] = {
                "rom_name": rom_name,
                "title": title,
            }
            if extra_raw:
                try:
                    loaded = json.loads(extra_raw)
                    if isinstance(loaded, dict):
                        for ek, ev in loaded.items():
                            if ev is not None and ev != "":
                                props[str(ek)] = str(ev)
                except Exception:
                    pass

            for c_name, c_idx in prop_cols:
                if c_idx < n_parts:
                    c_val = parts[c_idx]
                    if c_val:
                        val_clean = unesc(c_val) if has_backslash else c_val
                        props[c_name] = val_clean
                        if c_name == "status":
                            props["driver_status"] = val_clean

            if not bios and props.get("romof") and props["romof"].lower() != cloneof.lower():
                bios = props["romof"]
                props["bios"] = bios

            entry: dict = {
                "title": title,
                "rom_name": rom_name,
                "year": year,
                "manufacturer": manufacturer,
                "genre": genre,
                "players": players,
                "cloneof": cloneof,
                "bios": bios,
                "rating": rating,
                "crc": crc,
                "sourcefile": sourcefile,
                "notes": notes,
                "properties": props,
            }
            for c_name, _c_idx in prop_cols:
                if c_name not in entry and c_name in props:
                    entry[c_name] = props[c_name]

            parsed_keys: list[str] = []
            if "|" in keys_raw:
                for idx, k in enumerate(keys_raw.split("|")):
                    if not k:
                        continue
                    ck = unesc(k) if has_backslash else k
                    parsed_keys.append(ck)
                    if idx == 0 or ck not in catalog_map:
                        catalog_map[ck] = entry
            elif keys_raw:
                ck = unesc(keys_raw) if has_backslash else keys_raw
                parsed_keys.append(ck)
                catalog_map[ck] = entry
            elif rom_name:
                ck = rom_name.lower()
                parsed_keys.append(ck)
                catalog_map[ck] = entry

            if keep_keys_attr:
                entry["_keys"] = parsed_keys

    return catalog_map, (header_cols or list(default_selected_columns()))


def parse_fast_catalog(pncat_path: str | Path) -> dict[str, dict]:
    """Carga un catálogo '.pncat' y retorna el mapa {rom_key: entry} compatible con parse_rom_xml()."""
    catalog_map, _cols = _parse_fast_catalog_internal(pncat_path, keep_keys_attr=False)
    return catalog_map


def read_fast_catalog_table(pncat_path: str | Path, limit: int = 0) -> tuple[list[dict], list[str]]:
    """
    Devuelve (entradas_unicas, columnas_del_archivo) para poblar dinámicamente la tabla de vista previa.
    """
    catalog_map, cols = _parse_fast_catalog_internal(pncat_path, keep_keys_attr=True)
    seen_ids: set[int] = set()
    entries: list[dict] = []
    for entry in catalog_map.values():
        eid = id(entry)
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        entries.append(entry)
        if limit > 0 and len(entries) >= limit:
            break
    return entries, cols


def read_fast_catalog_entries(pncat_path: str | Path, limit: int = 0) -> list[dict]:
    """Devuelve la lista deduplicada de entradas únicas contenidas en un archivo '.pncat'."""
    entries, _cols = read_fast_catalog_table(pncat_path, limit=limit)
    return entries
