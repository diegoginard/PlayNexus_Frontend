"""
Conversor en streaming de catálogos XML / DAT a formato ultrarrápido PlayNexus (.pncat)
y lector de alta velocidad en texto plano 100% portable.

Formato '.pncat' (PlayNexus Fast Catalog v1):
- Texto plano UTF-8 orientado a líneas (sin bases binarias SQLite).
- Cabecera identificadora: '# PlayNexus Fast Catalog v1'
- Columnas fijas separadas por tabulador (\t) para evitar parsear JSON en cada fila:
  0:keys | 1:rom_name | 2:title | 3:year | 4:manufacturer | 5:genre | 6:players |
  7:cloneof | 8:rating | 9:crc | 10:sourcefile | 11:notes | 12:bios | 13:romof |
  14:status | 15:isbios | 16:isdevice | 17:ismechanical | 18:runnable |
  19:display_type | 20:display_rotate | 21:display_width | 22:display_height |
  23:control_type | 24:control_buttons | 25:extra_json
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import time
from typing import Callable
import xml.etree.ElementTree as ET

PNCAT_EXT = ".pncat"
PNCAT_HEADER = "# PlayNexus Fast Catalog v1"

_BARE_AMP_RE = re.compile(r"&(?!amp;|lt;|gt;|apos;|quot;|#\d+;|#x[0-9a-fA-F]+;)")

# Nodos hijos relevantes al extraer en perfil optimizado (conserva biosset, display, input, driver, etc.)
_RELEVANT_CHILD_TAGS_OPTIMIZED = frozenset({
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

# Columnas ya representadas directamente en el TSV de 26 columnas
_DIRECT_PROP_KEYS = frozenset({
    "name",
    "rom_name",
    "title",
    "description",
    "year",
    "date",
    "releasedate",
    "manufacturer",
    "genre",
    "players",
    "input_players",
    "cloneof",
    "rating",
    "crc",
    "sourcefile",
    "source_file",
    "notes",
    "desc",
    "bios",
    "romof",
    "status",
    "driver_status",
    "isbios",
    "isdevice",
    "ismechanical",
    "runnable",
    "display_type",
    "display_rotate",
    "display_width",
    "display_height",
    "control_type",
    "control_buttons",
})

# Propiedades adicionales que vale la pena conservar en extra_json si existen en perfil optimizado
_EXTRA_OPTIMIZED_KEYS = frozenset({
    "biosset_name",
    "biosset_description",
    "orientation",
    "rotate",
    "rotation",
    "video_orientation",
    "display_orientation",
    "control_ways",
    "region",
    "language",
    "serial",
})


@dataclass
class ConvertOptions:
    profile: str = "optimized"  # "optimized" | "full"
    genre_ini_path: str = ""
    exclude_devices: bool = False
    exclude_mechanical: bool = False
    exclude_clones: bool = False
    exclude_non_runnable: bool = False


@dataclass
class ConvertSummary:
    source_path: str
    output_path: str
    profile: str
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


class _SanitizingXmlStream(io.RawIOBase):
    """
    Flujo de respaldo usado únicamente cuando un XML mal formado contiene '&' sin escapar
    o codificaciones antiguas (HyperSpin / listas caseras), manteniendo consumo mínimo de RAM.
    """

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
    """
    Extrae las claves normalizadas y el diccionario de metadatos desde un nodo XML (<machine>, <game>, <item>).
    Separa explícitamente `cloneof` real de `romof` / `bios` para que juegos principales con BIOS (ej. Neo Geo)
    no se marquen falsamente como clones y conserven siempre su referencia a la BIOS.
    """
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

        if optimized and tag_lower not in _RELEVANT_CHILD_TAGS_OPTIMIZED:
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
    # cloneof estricto (solo clones reales; romof se conserva por separado para BIOS)
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


def _format_pncat_line(keys: list[str], entry: dict, optimized: bool) -> str:
    props = entry["properties"]
    if optimized:
        extra = {
            k: v
            for k, v in props.items()
            if v and k in _EXTRA_OPTIMIZED_KEYS
        }
    else:
        extra = {
            k: v
            for k, v in props.items()
            if v and k not in _DIRECT_PROP_KEYS
        }
    extra_json = json.dumps(extra, ensure_ascii=False, separators=(",", ":")) if extra else ""
    keys_str = "|".join(_esc_field(k) for k in keys if k)

    return "\t".join((
        keys_str,
        _esc_field(entry["rom_name"]),
        _esc_field(entry["title"]),
        _esc_field(entry["year"]),
        _esc_field(entry["manufacturer"]),
        _esc_field(entry["genre"]),
        _esc_field(entry["players"]),
        _esc_field(entry["cloneof"]),
        _esc_field(entry["rating"]),
        _esc_field(entry["crc"]),
        _esc_field(entry["sourcefile"]),
        _esc_field(entry["notes"]),
        _esc_field(entry.get("bios") or props.get("bios", "")),
        _esc_field(props.get("romof", "")),
        _esc_field(props.get("status") or props.get("driver_status") or ""),
        _esc_field(props.get("isbios", "")),
        _esc_field(props.get("isdevice", "")),
        _esc_field(props.get("ismechanical", "")),
        _esc_field(props.get("runnable", "")),
        _esc_field(props.get("display_type", "")),
        _esc_field(props.get("display_rotate", "")),
        _esc_field(props.get("display_width", "")),
        _esc_field(props.get("display_height", "")),
        _esc_field(props.get("control_type", "")),
        _esc_field(props.get("control_buttons", "")),
        _esc_field(extra_json),
    ))


def parse_mame_genre_ini(ini_path: str | Path | None) -> dict[str, str]:
    """
    Lee un archivo INI externo de géneros/categorías de MAME y devuelve {rom_name_lower: genre}.
    Soporta ambos formatos estándar:
      1. Formato clásico 'catver.ini' (ProgettoSnaps): sección [Category] con líneas 'sf2=Fighter / Versus'.
      2. Formato carpetas MAMEUI / Arcade64 ('Category.ini', 'genre.ini'): secciones '[Fighter / Versus]'
         seguidas por nombres de ROM uno por línea.
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
    kv_category_sections = {"category", "categories", "genre", "genres"}
    trailing_num_re = re.compile(r"\s*/\s*\d+$")

    genre_map: dict[str, str] = {}
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
            if current_sec_lower in kv_category_sections:
                k, v = s.split("=", 1)
                rk = k.strip().lower()
                gv = v.strip()
                if rk and gv:
                    genre_map[rk] = gv
        else:
            # Formato MAMEUI Category.ini: una ROM por línea (sin espacios) bajo [Nombre Categoría]
            if " " not in s and "\t" not in s and current_section:
                rk = s.lower()
                genre_map.setdefault(rk, current_section)

    return genre_map


def _resolve_bios_inheritance(
    collected: list[tuple[list[str], dict]],
    bios_names: dict[str, str],
    parent_links: dict[str, str],
    genre_map: dict[str, str] | None = None,
    clone_links: dict[str, str] | None = None,
) -> int:
    """
    Resuelve:
      1. La BIOS raíz incluso para clones (ej. kof98h -> kof98 -> neogeo).
      2. El género desde Category.ini / catver.ini (directo por ROM o heredado del padre cloneof).
    Retorna la cantidad de entradas con género asignado.
    """
    genres_count = 0
    g_map = genre_map or {}
    c_links = clone_links or {}

    for _keys, entry in collected:
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

        # Asignación / herencia de género si el XML no lo trajo
        if not entry["genre"] and g_map:
            r_low = entry["rom_name"].lower()
            resolved_g = g_map.get(r_low, "")
            if not resolved_g:
                visited_c: set[str] = set()
                curr_c = entry["cloneof"].lower()
                for _ in range(6):
                    if not curr_c or curr_c in visited_c:
                        break
                    if curr_c in g_map:
                        resolved_g = g_map[curr_c]
                        break
                    visited_c.add(curr_c)
                    curr_c = c_links.get(curr_c, "")
            if resolved_g:
                entry["genre"] = resolved_g
                props["genre"] = resolved_g

        if entry["genre"]:
            genres_count += 1

    return genres_count


def convert_xml_to_pncat(
    source_xml_path: str | Path,
    output_pncat_path: str | Path,
    options: ConvertOptions | None = None,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> ConvertSummary:
    """
    Convierte un archivo XML / DAT de cualquier tamaño (ej. MAME 300+ MB) a '.pncat'
    conservando siempre todas las BIOS y resolviendo la herencia de BIOS en padres y clones.
    """
    opts = options or ConvertOptions()
    optimized = opts.profile != "full"

    src = Path(source_xml_path)
    if not src.is_file():
        raise FileNotFoundError(f"No existe el archivo XML/DAT de origen: {src}")

    dst = Path(output_pncat_path)
    if dst.suffix.lower() != PNCAT_EXT:
        dst = dst.with_suffix(PNCAT_EXT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_name(dst.name + ".tmp")

    t0 = time.perf_counter()
    total_bytes = max(1, os.path.getsize(src))
    summary = ConvertSummary(
        source_path=str(src),
        output_path=str(dst),
        profile=opts.profile,
        source_size_bytes=total_bytes,
    )

    def _reset_counts() -> None:
        summary.total_seen = 0
        summary.written_entries = 0
        summary.skipped_devices = 0
        summary.skipped_mechanical = 0
        summary.skipped_clones = 0
        summary.skipped_non_runnable = 0

    def _stream_collect(
        target_tags: frozenset[str],
        use_sanitizer: bool,
    ) -> tuple[list[tuple[list[str], dict]], dict[str, str], dict[str, str], dict[str, str]]:
        collected: list[tuple[list[str], dict]] = []
        bios_names: dict[str, str] = {}
        parent_links: dict[str, str] = {}
        clone_links: dict[str, str] = {}

        if use_sanitizer:
            reader = _SanitizingXmlStream(src)
            tell_fn = lambda: reader.bytes_read
        else:
            reader = open(src, "rb", buffering=1024 * 1024)
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
                    return collected, bios_names, parent_links, clone_links

                summary.total_seen += 1
                extracted = extract_catalog_entry(elem, optimized=optimized)
                elem.clear()

                if extracted is not None:
                    keys, entry = extracted
                    props = entry["properties"]
                    r_low = entry["rom_name"].lower()
                    romof_val = props.get("romof", "")
                    clone_val = entry["cloneof"]
                    is_bios_entry = props.get("isbios", "").lower() in ("yes", "true", "1")

                    # Registrar grafo ligero para resolver BIOS y género de clones aunque el padre fuese filtrado
                    if is_bios_entry:
                        bios_names[r_low] = entry["rom_name"]
                    elif romof_val and romof_val.lower() != clone_val.lower():
                        bios_names.setdefault(romof_val.lower(), romof_val)
                    if romof_val or clone_val:
                        parent_links[r_low] = (romof_val or clone_val).lower()
                    if clone_val:
                        clone_links[r_low] = clone_val.lower()

                    # Las entradas isbios="yes" NUNCA se descartan por pre-filtros
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
                        if opts.exclude_clones and bool(clone_val):
                            summary.skipped_clones += 1
                            continue

                    collected.append((keys, entry))
                    summary.written_entries += 1

                if progress_callback and (summary.total_seen & 0x1FF) == 0:
                    now = time.perf_counter()
                    if now - last_report_t >= 0.08:
                        last_report_t = now
                        b_read = tell_fn()
                        pct = min(96, int((b_read * 96) / total_bytes))
                        progress_callback(pct, summary.total_seen, summary.written_entries, b_read)
        finally:
            reader.close()

        return collected, bios_names, parent_links, clone_links

    primary_tags = frozenset({"machine", "game", "item"})
    genre_map = parse_mame_genre_ini(opts.genre_ini_path) if opts.genre_ini_path else {}

    try:
        used_sanitizer = False
        try:
            collected, bios_names, parent_links, clone_links = _stream_collect(primary_tags, use_sanitizer=False)
        except ET.ParseError:
            used_sanitizer = True
            _reset_counts()
            collected, bios_names, parent_links, clone_links = _stream_collect(primary_tags, use_sanitizer=True)

        if not summary.cancelled and summary.total_seen == 0:
            _reset_counts()
            collected, bios_names, parent_links, clone_links = _stream_collect(
                frozenset({"rom"}), use_sanitizer=used_sanitizer
            )

        if summary.cancelled:
            tmp_dst.unlink(missing_ok=True)
            summary.elapsed_seconds = time.perf_counter() - t0
            return summary

        summary.genres_assigned = _resolve_bios_inheritance(
            collected, bios_names, parent_links, genre_map=genre_map, clone_links=clone_links
        )

        with open(tmp_dst, "w", encoding="utf-8", buffering=1024 * 1024, newline="\n") as out_fh:
            out_fh.write(f"{PNCAT_HEADER}\n")
            out_fh.write(f"# source: {src.name}\n")
            out_fh.write(f"# profile: {opts.profile}\n")
            out_fh.write(f"# generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            out_fh.write(
                "# columns: keys\trom_name\ttitle\tyear\tmanufacturer\tgenre\tplayers\t"
                "cloneof\trating\tcrc\tsourcefile\tnotes\tbios\tromof\tstatus\tisbios\tisdevice\t"
                "ismechanical\trunnable\tdisplay_type\tdisplay_rotate\tdisplay_width\t"
                "display_height\tcontrol_type\tcontrol_buttons\textra_json\n"
            )
            for keys, entry in collected:
                out_fh.write(_format_pncat_line(keys, entry, optimized=optimized) + "\n")

        os.replace(tmp_dst, dst)
        summary.output_size_bytes = os.path.getsize(dst)
        summary.elapsed_seconds = time.perf_counter() - t0
        if progress_callback:
            progress_callback(100, summary.total_seen, summary.written_entries, total_bytes)
        return summary
    except Exception:
        tmp_dst.unlink(missing_ok=True)
        raise


def parse_fast_catalog(pncat_path: str | Path) -> dict[str, dict]:
    """
    Carga un catálogo '.pncat' a velocidad ultrarrápida retornando la misma estructura
    que parse_rom_xml(), incluyendo 'bios' y 'romof' para reglas de filtrado.
    """
    p = Path(pncat_path)
    catalog_map: dict[str, dict] = {}
    unesc = _unesc_field

    with open(p, "r", encoding="utf-8-sig", buffering=1024 * 1024) as fh:
        for raw_line in fh:
            if not raw_line or raw_line[0] == "#" or raw_line[0] in ("\r", "\n"):
                continue
            line = raw_line[:-1] if raw_line[-1] == "\n" else raw_line
            if line and line[-1] == "\r":
                line = line[:-1]
            if not line:
                continue

            parts = line.split("\t")
            n_parts = len(parts)
            if n_parts < 12:
                continue

            has_backslash = "\\" in line
            if has_backslash:
                keys_raw = parts[0]
                rom_name = unesc(parts[1])
                title = unesc(parts[2]) or rom_name
                year = unesc(parts[3])
                manufacturer = unesc(parts[4])
                genre = unesc(parts[5])
                players = unesc(parts[6])
                cloneof = unesc(parts[7])
                rating = unesc(parts[8])
                crc = unesc(parts[9])
                sourcefile = unesc(parts[10])
                notes = unesc(parts[11])
            else:
                keys_raw = parts[0]
                rom_name = parts[1]
                title = parts[2] or rom_name
                year = parts[3]
                manufacturer = parts[4]
                genre = parts[5]
                players = parts[6]
                cloneof = parts[7]
                rating = parts[8]
                crc = parts[9]
                sourcefile = parts[10]
                notes = parts[11]

            props: dict[str, str] = {
                "rom_name": rom_name,
                "title": title,
            }
            bios = ""

            if n_parts >= 26:
                if has_backslash:
                    bios = unesc(parts[12])
                    romof = unesc(parts[13])
                    status = unesc(parts[14])
                    isbios = unesc(parts[15])
                    isdevice = unesc(parts[16])
                    ismechanical = unesc(parts[17])
                    runnable = unesc(parts[18])
                    display_type = unesc(parts[19])
                    display_rotate = unesc(parts[20])
                    display_width = unesc(parts[21])
                    display_height = unesc(parts[22])
                    control_type = unesc(parts[23])
                    control_buttons = unesc(parts[24])
                    extra_raw = unesc(parts[25])
                else:
                    bios = parts[12]
                    romof = parts[13]
                    status = parts[14]
                    isbios = parts[15]
                    isdevice = parts[16]
                    ismechanical = parts[17]
                    runnable = parts[18]
                    display_type = parts[19]
                    display_rotate = parts[20]
                    display_width = parts[21]
                    display_height = parts[22]
                    control_type = parts[23]
                    control_buttons = parts[24]
                    extra_raw = parts[25]

                if extra_raw:
                    try:
                        loaded = json.loads(extra_raw)
                        if isinstance(loaded, dict):
                            for ek, ev in loaded.items():
                                if ev is not None and ev != "":
                                    props[str(ek)] = str(ev)
                    except Exception:
                        pass

                if bios:
                    props["bios"] = bios
                if romof:
                    props["romof"] = romof
                if status:
                    props["status"] = status
                    props["driver_status"] = status
                if isbios:
                    props["isbios"] = isbios
                if isdevice:
                    props["isdevice"] = isdevice
                if ismechanical:
                    props["ismechanical"] = ismechanical
                if runnable:
                    props["runnable"] = runnable
                if display_type:
                    props["display_type"] = display_type
                if display_rotate:
                    props["display_rotate"] = display_rotate
                if display_width:
                    props["display_width"] = display_width
                if display_height:
                    props["display_height"] = display_height
                if control_type:
                    props["control_type"] = control_type
                if control_buttons:
                    props["control_buttons"] = control_buttons
            elif n_parts == 25:
                # Retrocompatibilidad con layout previo de 25 columnas
                romof = unesc(parts[12]) if has_backslash else parts[12]
                status = unesc(parts[13]) if has_backslash else parts[13]
                isbios = unesc(parts[14]) if has_backslash else parts[14]
                isdevice = unesc(parts[15]) if has_backslash else parts[15]
                ismechanical = unesc(parts[16]) if has_backslash else parts[16]
                runnable = unesc(parts[17]) if has_backslash else parts[17]
                display_type = unesc(parts[18]) if has_backslash else parts[18]
                display_rotate = unesc(parts[19]) if has_backslash else parts[19]
                display_width = unesc(parts[20]) if has_backslash else parts[20]
                display_height = unesc(parts[21]) if has_backslash else parts[21]
                control_type = unesc(parts[22]) if has_backslash else parts[22]
                control_buttons = unesc(parts[23]) if has_backslash else parts[23]
                if romof:
                    props["romof"] = romof
                    if romof.lower() != cloneof.lower():
                        bios = romof
                        props["bios"] = bios
                if status:
                    props["status"] = status
                    props["driver_status"] = status
                if isbios:
                    props["isbios"] = isbios
                if isdevice:
                    props["isdevice"] = isdevice
                if ismechanical:
                    props["ismechanical"] = ismechanical
                if runnable:
                    props["runnable"] = runnable
                if display_type:
                    props["display_type"] = display_type
                if display_rotate:
                    props["display_rotate"] = display_rotate
                if display_width:
                    props["display_width"] = display_width
                if display_height:
                    props["display_height"] = display_height
                if control_type:
                    props["control_type"] = control_type
                if control_buttons:
                    props["control_buttons"] = control_buttons

            if year:
                props["year"] = year
            if manufacturer:
                props["manufacturer"] = manufacturer
            if genre:
                props["genre"] = genre
            if players:
                props["players"] = players
            if cloneof:
                props["cloneof"] = cloneof
            if rating:
                props["rating"] = rating
            if crc:
                props["crc"] = crc
            if sourcefile:
                props["sourcefile"] = sourcefile

            entry = {
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

            if "|" in keys_raw:
                for idx, k in enumerate(keys_raw.split("|")):
                    if not k:
                        continue
                    ck = unesc(k) if has_backslash else k
                    if idx == 0 or ck not in catalog_map:
                        catalog_map[ck] = entry
            elif keys_raw:
                ck = unesc(keys_raw) if has_backslash else keys_raw
                catalog_map[ck] = entry
            elif rom_name:
                catalog_map[rom_name.lower()] = entry

    return catalog_map


def read_fast_catalog_entries(pncat_path: str | Path, limit: int = 0) -> list[dict]:
    """Devuelve una lista deduplicada de entradas únicas contenidas en un archivo '.pncat'."""
    catalog_map = parse_fast_catalog(pncat_path)
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
    return entries
