"""
Cliente oficial de solo lectura para RetroAchievements Web API v1, cálculo de hashes
por sistema (MD5 según reglas rcheevos/RA) y caché local no bloqueante para la UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import hashlib
import json
import os
import re
import time
import urllib.parse
import zipfile

from playnexus.db import APP_DIR
from playnexus.services.scraper.http_utils import ProviderRateLimiter, http_get_json
from playnexus.services.scraper.models import _decode_secret, _encode_secret, _resolve_secret_key_dir
from playnexus.services.scraper.systems import clean_rom_search_title, detect_system_for_list, normalize_match_key

RA_API_BASE = "https://retroachievements.org/API"
RA_USER_AGENT = "PlayNexus-Frontend/1.2 (RetroAchievements Integration)"

RA_USERNAME_SETTING_KEY = "ra_username"
RA_API_KEY_SETTING_KEY = "ra_api_key_enc"
RA_SHOW_BADGE_SETTING_KEY = "ra_show_badge"

# Mapeo oficial de system_key de PlayNexus -> Console ID de RetroAchievements
SYSTEM_KEY_TO_RA_CONSOLE_ID: dict[str, int] = {
    "genesis": 1,
    "n64": 2,
    "snes": 3,
    "gb": 4,
    "gba": 5,
    "gbc": 6,
    "nes": 7,
    "tg16": 8,
    "segacd": 9,
    "sega32x": 10,
    "mastersystem": 11,
    "ps1": 12,
    "gamegear": 15,
    "gamecube": 16,
    "jaguar": 17,
    "nds": 18,
    "wii": 19,
    "ps2": 21,
    "atari2600": 25,
    "arcade": 27,
    "fbneo": 27,
    "neogeo": 27,
    "virtualboy": 28,
    "saturn": 39,
    "dreamcast": 40,
    "psp": 41,
    "pcfx": 49,
    "tgcd": 76,
    "jaguarcd": 77,
}

ARCADE_SYSTEM_KEYS = frozenset({"arcade", "fbneo", "neogeo"})
DISC_SYSTEM_KEYS = frozenset(
    {"ps1", "ps2", "psp", "dreamcast", "saturn", "segacd", "tgcd", "jaguarcd", "gamecube", "pcfx", "wii"}
)
DISC_IMAGE_EXTS = frozenset({".chd", ".iso", ".cue", ".bin", ".pbp", ".cso", ".rvz", ".gcz", ".gdi", ".cdi", ".img", ".mdf"})
SKIP_ZIP_MEMBER_EXTS = frozenset(
    {".txt", ".nfo", ".diz", ".md", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".sav", ".srm", ".ips", ".bps", ".ups", ".cue", ".xml", ".dat"}
)
PREFERRED_ROM_MEMBER_EXTS = frozenset(
    {
        ".nes", ".fds", ".unf", ".unif", ".sfc", ".smc", ".swc", ".fig",
        ".z64", ".n64", ".v64", ".gb", ".gbc", ".gba", ".nds", ".vb", ".vboy",
        ".md", ".gen", ".smd", ".32x", ".sms", ".gg", ".sg", ".pce",
        ".a26", ".a78", ".lnx", ".j64", ".jag", ".ngp", ".ngc", ".ws", ".wsc", ".bin", ".rom",
    }
)

_MAX_ZIP_HASH_MEMBER_BYTES = 128 * 1024 * 1024  # 128 MiB cap para ROMs comprimidas
_DEFAULT_CONSOLE_CATALOG_TTL_SEC = 7 * 24 * 3600

# Caché ligero en memoria para consultas O(1) en Biblioteca, TableLayout y Quick Menu
_MEM_ROM_INDEX_CACHE: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}


@dataclass
class RAConfig:
    username: str = ""
    api_key: str = ""
    show_badge: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.username.strip() and self.api_key.strip())


@dataclass
class RAHashResult:
    hashes: list[str] = field(default_factory=list)
    method: str = "raw_md5"
    inner_filename: str = ""
    requires_title_fallback: bool = False
    note: str = ""


def load_ra_config(db) -> RAConfig:
    if db is None:
        return RAConfig()
    key_dir = _resolve_secret_key_dir(db)
    username = str(db.get_setting(RA_USERNAME_SETTING_KEY, "") or "").strip()
    enc_key = str(db.get_setting(RA_API_KEY_SETTING_KEY, "") or "").strip()
    api_key = _decode_secret(enc_key, key_dir=key_dir) if enc_key else ""
    show_raw = str(db.get_setting(RA_SHOW_BADGE_SETTING_KEY, "true") or "true").strip().lower()
    return RAConfig(
        username=username,
        api_key=api_key,
        show_badge=(show_raw not in ("0", "false", "no")),
    )


def save_ra_config(db, cfg: RAConfig) -> None:
    if db is None:
        return
    key_dir = _resolve_secret_key_dir(db)
    with db.batch() if hasattr(db, "batch") else _NullCtx():
        db.set_setting(RA_USERNAME_SETTING_KEY, cfg.username.strip())
        enc = _encode_secret(cfg.api_key.strip(), key_dir=key_dir) if cfg.api_key.strip() else ""
        db.set_setting(RA_API_KEY_SETTING_KEY, enc)
        db.set_setting(RA_SHOW_BADGE_SETTING_KEY, "true" if cfg.show_badge else "false")


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def get_ra_cache_dir(db=None) -> Path:
    base = Path(getattr(db, "data_dir", None) or APP_DIR)
    cache_dir = base / "config" / "ra_cache"
    (cache_dir / "games").mkdir(parents=True, exist_ok=True)
    return cache_dir


def clear_ra_cache(db=None) -> None:
    cdir = get_ra_cache_dir(db)
    key = str(cdir).lower()
    _MEM_ROM_INDEX_CACHE.pop(key, None)


def _norm_rom_index_key(game_row: dict[str, Any] | Any) -> str:
    rom_path = ""
    if isinstance(game_row, dict):
        rom_path = str(game_row.get("rom_path") or "").strip()
    elif hasattr(game_row, "get"):
        rom_path = str(game_row.get("rom_path") or "").strip()
    if rom_path:
        return rom_path.replace("\\", "/").lower()
    if isinstance(game_row, dict) or hasattr(game_row, "get"):
        gid = game_row.get("id")
        if gid is not None:
            return f"id:{gid}"
    return ""


def _safe_user_slug(username: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(username or "").strip())
    return clean or "user"


def resolve_ra_console_for_list(list_row: dict[str, Any] | None, emulator_row: dict[str, Any] | None = None) -> tuple[str, int]:
    """Detecta `(system_key, ra_console_id)` para una lista usando `detect_system_for_list`."""
    if not list_row:
        return "", 0
    sys_obj = detect_system_for_list(list_row, emulator_row=emulator_row)
    if not sys_obj:
        return "", 0
    cid = SYSTEM_KEY_TO_RA_CONSOLE_ID.get(sys_obj.key, 0)
    return sys_obj.key, cid


# ------------------------------------------------------------------
# CÁLCULO DE HASHES MD5 POR SISTEMA (REGLAS RETROACHIEVEMENTS)
# ------------------------------------------------------------------
def _md5_file_stream(path: Path, skip_bytes: int = 0) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        if skip_bytes > 0:
            fh.seek(skip_bytes)
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def _normalize_n64_chunk(chunk: bytes, endian_mode: str) -> bytes:
    if endian_mode == "z64":
        return chunk
    n = len(chunk)
    if endian_mode == "v64":
        rem = n % 2
        usable = n - rem
        buf = bytearray(chunk)
        for i in range(0, usable, 2):
            buf[i], buf[i + 1] = buf[i + 1], buf[i]
        return bytes(buf)
    if endian_mode == "n64":
        rem = n % 4
        usable = n - rem
        buf = bytearray(chunk)
        for i in range(0, usable, 4):
            buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = buf[i + 3], buf[i + 2], buf[i + 1], buf[i]
        return bytes(buf)
    return chunk


def _detect_n64_endian_mode(head: bytes, name_hint: str = "") -> str:
    if len(head) >= 4:
        sig = head[:4]
        if sig == b"\x80\x37\x12\x40":
            return "z64"
        if sig == b"\x37\x80\x40\x12":
            return "v64"
        if sig == b"\x40\x12\x37\x80":
            return "n64"
    ext = Path(name_hint).suffix.lower()
    if ext == ".v64":
        return "v64"
    if ext == ".n64":
        return "n64"
    return "z64"


def _hash_rom_bytes_for_system(data: bytes, system_key: str, inner_name: str = "") -> RAHashResult:
    sys_k = (system_key or "").strip().lower()
    ext = Path(inner_name).suffix.lower()
    size = len(data)
    hashes: list[str] = []
    method = "raw_md5"

    if sys_k == "nes" or ext in (".nes", ".fds"):
        if size > 16 and data[:4] in (b"NES\x1a", b"FDS\x1a"):
            hashes.append(hashlib.md5(data[16:]).hexdigest().lower())
            method = "nes_stripped_16"
        raw_h = hashlib.md5(data).hexdigest().lower()
        if raw_h not in hashes:
            hashes.append(raw_h)
    elif sys_k in ("snes", "tg16") or ext in (".sfc", ".smc", ".swc", ".fig", ".pce"):
        if size > 512 and (size % 1024) == 512:
            hashes.append(hashlib.md5(data[512:]).hexdigest().lower())
            method = f"{sys_k or 'copier'}_stripped_512"
        raw_h = hashlib.md5(data).hexdigest().lower()
        if raw_h not in hashes:
            hashes.append(raw_h)
    elif sys_k == "n64" or ext in (".z64", ".v64", ".n64"):
        mode = _detect_n64_endian_mode(data[:4], inner_name)
        if mode != "z64":
            norm_data = _normalize_n64_chunk(data, mode)
            hashes.append(hashlib.md5(norm_data).hexdigest().lower())
            method = f"n64_{mode}_to_z64"
        raw_h = hashlib.md5(data).hexdigest().lower()
        if raw_h not in hashes:
            hashes.append(raw_h)
    elif ext == ".a78" and size > 128 and data[1:10] == b"ATARI7800":
        hashes.append(hashlib.md5(data[128:]).hexdigest().lower())
        hashes.append(hashlib.md5(data).hexdigest().lower())
        method = "a78_stripped_128"
    elif ext == ".lnx" and size > 64 and data[:4] == b"LYNX":
        hashes.append(hashlib.md5(data[64:]).hexdigest().lower())
        hashes.append(hashlib.md5(data).hexdigest().lower())
        method = "lnx_stripped_64"
    else:
        hashes.append(hashlib.md5(data).hexdigest().lower())
        method = "raw_md5"

    return RAHashResult(
        hashes=hashes,
        method=method,
        inner_filename=inner_name,
        requires_title_fallback=(sys_k == "nds" or ext == ".nds"),
    )


def _pick_zip_rom_member(zf: zipfile.ZipFile) -> zipfile.ZipInfo | None:
    files = [zi for zi in zf.infolist() if not zi.is_dir() and zi.file_size > 0]
    if not files:
        return None
    preferred = [
        zi for zi in files
        if Path(zi.filename).suffix.lower() in PREFERRED_ROM_MEMBER_EXTS
    ]
    pool = preferred or [
        zi for zi in files
        if Path(zi.filename).suffix.lower() not in SKIP_ZIP_MEMBER_EXTS
    ] or files
    return max(pool, key=lambda zi: zi.file_size)


def compute_ra_rom_hashes(rom_path: str | Path, system_key: str = "") -> RAHashResult:
    """
    Calcula los hashes MD5 esperados por RetroAchievements según el sistema y contenedor.
    Nunca lee discos completos de cientos de megabytes ni se bloquea en archivos CHD/ISO.
    """
    p = Path(rom_path)
    sys_k = (system_key or "").strip().lower()
    ext = p.suffix.lower()

    if not p.name:
        return RAHashResult(hashes=[], method="invalid_path", requires_title_fallback=True, note="Ruta de ROM vacía.")

    # 1. Arcade (MAME / FBNeo / Neo Geo): MD5 ASCII del nombre corto de ROM sin extensión
    if sys_k in ARCADE_SYSTEM_KEYS:
        stem_ascii = p.stem.lower().encode("ascii", errors="ignore")
        stem_hash = hashlib.md5(stem_ascii).hexdigest().lower()
        return RAHashResult(
            hashes=[stem_hash],
            method="arcade_zip_stem_md5",
            inner_filename=p.name,
            requires_title_fallback=True,
            note=f"MD5 del stem Arcade '{p.stem.lower()}'",
        )

    # 2. Sistemas de disco o imágenes ópticas grandes -> matching directo por catálogo de títulos
    if sys_k in DISC_SYSTEM_KEYS or (ext in DISC_IMAGE_EXTS and not (sys_k == "snes" or sys_k == "genesis" or sys_k == "tg16")):
        # Nota: .bin también se usa a veces en Genesis; si es sys_k en DISC_SYSTEM_KEYS o archivo grande (> 32 MB), saltar MD5
        if sys_k in DISC_SYSTEM_KEYS or ext != ".bin" or (p.is_file() and p.stat().st_size > 32 * 1024 * 1024):
            return RAHashResult(
                hashes=[],
                method="disc_title_match",
                inner_filename=p.name,
                requires_title_fallback=True,
                note="Sistema óptico / imagen de disco: emparejamiento por catálogo oficial de títulos RA.",
            )

    if p.is_dir() or not p.is_file():
        return RAHashResult(
            hashes=[],
            method="folder_or_missing_rom",
            requires_title_fallback=True,
            note="La ROM es una carpeta o no existe en disco; usando fallback por título.",
        )

    # 3. Contenedor ZIP: extraer miembro principal en memoria si <= 128 MiB
    if ext == ".zip":
        try:
            with zipfile.ZipFile(p, "r") as zf:
                member = _pick_zip_rom_member(zf)
                if member is None:
                    return RAHashResult(hashes=[], method="empty_zip", requires_title_fallback=True)
                if member.file_size > _MAX_ZIP_HASH_MEMBER_BYTES:
                    return RAHashResult(
                        hashes=[],
                        method="zip_too_large_title_match",
                        inner_filename=member.filename,
                        requires_title_fallback=True,
                        note="ROM dentro del ZIP excede 128 MiB; usando fallback por título.",
                    )
                with zf.open(member, "r") as mf:
                    rom_bytes = mf.read()
                res = _hash_rom_bytes_for_system(rom_bytes, sys_k, inner_name=member.filename)
                res.method = f"zip:{res.method}"
                return res
        except zipfile.BadZipFile:
            return RAHashResult(hashes=[], method="bad_zip", requires_title_fallback=True)

    # 4. Archivo comprimido no-ZIP (.7z / .rar): en esta etapa usa matching por título si no está descomprimido
    if ext in (".7z", ".rar"):
        return RAHashResult(
            hashes=[],
            method=f"archive_{ext.lstrip('.')}_title_match",
            inner_filename=p.name,
            requires_title_fallback=True,
            note=f"Archivo {ext}: usando emparejamiento por título (para hash exacto usa ROM suelta o .zip).",
        )

    file_size = int(p.stat().st_size)
    if file_size > 256 * 1024 * 1024:
        return RAHashResult(
            hashes=[],
            method="large_file_title_match",
            inner_filename=p.name,
            requires_title_fallback=True,
            note="Archivo mayor a 256 MiB; usando fallback por título.",
        )

    # 5. ROM suelta por streaming (eficiente en memoria)
    if sys_k == "n64" or ext in (".z64", ".v64", ".n64"):
        with p.open("rb") as fh:
            head = fh.read(4)
            fh.seek(0)
            mode = _detect_n64_endian_mode(head, p.name)
            h_norm = hashlib.md5()
            h_raw = hashlib.md5()
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                h_raw.update(chunk)
                h_norm.update(_normalize_n64_chunk(chunk, mode))
        hashes = [h_norm.hexdigest().lower()]
        raw_hex = h_raw.hexdigest().lower()
        if raw_hex not in hashes:
            hashes.append(raw_hex)
        return RAHashResult(
            hashes=hashes,
            method=f"n64_{mode}_to_z64" if mode != "z64" else "raw_md5",
            inner_filename=p.name,
        )

    skip = 0
    method = "raw_md5"
    with p.open("rb") as fh:
        head = fh.read(128)
    if (sys_k == "nes" or ext in (".nes", ".fds")) and file_size > 16 and head[:4] in (b"NES\x1a", b"FDS\x1a"):
        skip = 16
        method = "nes_stripped_16"
    elif (sys_k in ("snes", "tg16") or ext in (".sfc", ".smc", ".swc", ".fig", ".pce")) and file_size > 512 and (file_size % 1024) == 512:
        skip = 512
        method = f"{sys_k or 'copier'}_stripped_512"
    elif ext == ".a78" and file_size > 128 and head[1:10] == b"ATARI7800":
        skip = 128
        method = "a78_stripped_128"
    elif ext == ".lnx" and file_size > 64 and head[:4] == b"LYNX":
        skip = 64
        method = "lnx_stripped_64"

    hashes = [_md5_file_stream(p, skip_bytes=skip)]
    if skip > 0:
        raw_h = _md5_file_stream(p, skip_bytes=0)
        if raw_h not in hashes:
            hashes.append(raw_h)

    return RAHashResult(
        hashes=hashes,
        method=method,
        inner_filename=p.name,
        requires_title_fallback=(sys_k == "nds" or ext == ".nds"),
    )


# ------------------------------------------------------------------
# CLIENTE WEB API v1 + CACHÉ EN DISCO
# ------------------------------------------------------------------
def _build_ra_url(endpoint: str, params: dict[str, Any]) -> str:
    clean = {k: str(v) for k, v in params.items() if v is not None and str(v) != ""}
    return f"{RA_API_BASE}/{endpoint}?{urllib.parse.urlencode(clean)}"


def _translate_ra_http_error(exc: Exception) -> RuntimeError:
    msg = str(exc)
    if "401" in msg or "403" in msg or "Invalid API Key" in msg:
        return RuntimeError("Credenciales de RetroAchievements inválidas (revisá tu usuario y Web API Key).")
    if "422" in msg:
        return RuntimeError("Parámetros rechazados por RetroAchievements API (422).")
    if "429" in msg:
        return RuntimeError("RetroAchievements limitó temporalmente las consultas (HTTP 429). Reintentá en unos segundos.")
    return RuntimeError(f"Error consultando RetroAchievements: {msg}")


class RetroAchievementsClient:
    """Cliente oficial de solo lectura para RetroAchievements Web API v1 con caché en disco."""

    def __init__(self, db, config: RAConfig | None = None, http_get_json_fn=None):
        self.db = db
        self.config = config or load_ra_config(db)
        self.cache_dir = get_ra_cache_dir(db)
        self.limiter = ProviderRateLimiter(min_interval_sec=0.35)
        self._http_get_json = http_get_json_fn or http_get_json
        self._console_catalogs: dict[int, dict[str, Any]] = {}

    def _require_credentials(self) -> tuple[str, str]:
        user = self.config.username.strip()
        key = self.config.api_key.strip()
        if not user or not key:
            raise RuntimeError("Configurá tu Usuario y Web API Key de RetroAchievements antes de consultar.")
        return user, key

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> Any:
        url = _build_ra_url(endpoint, params)
        self.limiter.wait()
        try:
            return self._http_get_json(url, timeout=20.0)
        except Exception as exc:
            raise _translate_ra_http_error(exc) from exc

    def test_credentials(self) -> dict[str, Any]:
        """Valida Usuario y Web API Key contra `API_GetUserProfile.php`."""
        user, key = self._require_credentials()
        data = self._get_json("API_GetUserProfile.php", {"y": key, "u": user})
        if not isinstance(data, dict) or not data.get("User"):
            raise RuntimeError("No se encontró el perfil indicado en RetroAchievements.")
        return {
            "user": str(data.get("User") or user),
            "total_points": int(data.get("TotalPoints") or 0),
            "softcore_points": int(data.get("TotalSoftcorePoints") or 0),
            "rank": int(data.get("Rank") or 0),
            "total_ranked": int(data.get("TotalRanked") or 0),
            "motto": str(data.get("Motto") or ""),
            "user_pic": str(data.get("UserPic") or ""),
        }

    def get_console_catalog(
        self,
        console_id: int,
        force_refresh: bool = False,
        ttl_sec: int = _DEFAULT_CONSOLE_CATALOG_TTL_SEC,
    ) -> dict[str, Any]:
        """
        Descarga o lee desde caché (`console_<id>.json`) el catálogo con hashes MD5 de una consola.
        Indexa por hash exacto y por título normalizado.
        """
        cid = int(console_id)
        if cid <= 0:
            return {"console_id": 0, "hash_to_game": {}, "title_to_game": {}, "games_by_id": {}}

        if not force_refresh and cid in self._console_catalogs:
            return self._console_catalogs[cid]

        cache_file = self.cache_dir / f"console_{cid}.json"
        if not force_refresh and cache_file.is_file():
            try:
                raw_cached = json.loads(cache_file.read_text(encoding="utf-8"))
                fetched_at = float(raw_cached.get("fetched_at") or 0.0)
                if (time.time() - fetched_at) <= ttl_sec and isinstance(raw_cached.get("hash_to_game"), dict):
                    self._console_catalogs[cid] = raw_cached
                    return raw_cached
            except Exception:
                pass

        _, key = self._require_credentials()
        entries = self._get_json("API_GetGameList.php", {"y": key, "i": cid, "f": 1, "h": 1})
        if not isinstance(entries, list):
            entries = []

        hash_to_game: dict[str, int] = {}
        title_to_game: dict[str, int] = {}
        games_by_id: dict[str, dict[str, Any]] = {}

        for row in entries:
            if not isinstance(row, dict):
                continue
            gid = int(row.get("ID") or 0)
            if gid <= 0:
                continue
            title = str(row.get("Title") or "").strip()
            num_ach = int(row.get("NumAchievements") or 0)
            points = int(row.get("Points") or 0)
            icon = str(row.get("ImageIcon") or "")
            games_by_id[str(gid)] = {
                "id": gid,
                "title": title,
                "console_id": cid,
                "console_name": str(row.get("ConsoleName") or ""),
                "num_achievements": num_ach,
                "points": points,
                "image_icon": icon,
            }
            for h_item in row.get("Hashes") or []:
                h_clean = str(h_item or "").strip().lower()
                if h_clean:
                    hash_to_game.setdefault(h_clean, gid)

            for cand_title in (title, clean_rom_search_title(title)):
                nk = normalize_match_key(cand_title)
                if nk:
                    title_to_game.setdefault(nk, gid)

        catalog = {
            "console_id": cid,
            "fetched_at": time.time(),
            "total_games": len(games_by_id),
            "hash_to_game": hash_to_game,
            "title_to_game": title_to_game,
            "games_by_id": games_by_id,
        }
        try:
            cache_file.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self._console_catalogs[cid] = catalog
        return catalog

    def resolve_game_in_catalog(
        self,
        game_row: dict[str, Any],
        system_key: str,
        console_id: int,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Intenta identificar un juego por hash MD5 del sistema o fallback por título normalizado."""
        rom_path = str(game_row.get("rom_path") or "")
        hash_res = compute_ra_rom_hashes(rom_path, system_key=system_key)
        catalog = self.get_console_catalog(console_id, force_refresh=force_refresh)

        h2g = catalog.get("hash_to_game") or {}
        gmap = catalog.get("games_by_id") or {}

        for h_hex in hash_res.hashes:
            gid = h2g.get(h_hex)
            if gid:
                ginfo = gmap.get(str(gid), {})
                return {
                    "matched": True,
                    "ra_game_id": int(gid),
                    "ra_title": ginfo.get("title", ""),
                    "match_method": f"hash:{hash_res.method}",
                    "hash_used": h_hex,
                    "hash_result": hash_res,
                }

        # Fallback por título si corresponde o no encontró por hash (útil en CD/CHD/hacks/repack)
        t2g = catalog.get("title_to_game") or {}
        title_candidates: list[str] = []
        raw_title = str(game_row.get("title") or "").strip()
        rom_stem = Path(rom_path).stem if rom_path else str(game_row.get("rom_name") or "").strip()
        for raw in (raw_title, clean_rom_search_title(raw_title), rom_stem, clean_rom_search_title(rom_stem)):
            nk = normalize_match_key(raw)
            if nk and nk not in title_candidates:
                title_candidates.append(nk)

        for nk in title_candidates:
            gid = t2g.get(nk)
            if gid:
                ginfo = gmap.get(str(gid), {})
                return {
                    "matched": True,
                    "ra_game_id": int(gid),
                    "ra_title": ginfo.get("title", ""),
                    "match_method": "title_match",
                    "hash_used": hash_res.hashes[0] if hash_res.hashes else "",
                    "hash_result": hash_res,
                }

        return {
            "matched": False,
            "ra_game_id": 0,
            "ra_title": "",
            "match_method": "not_found",
            "hash_used": hash_res.hashes[0] if hash_res.hashes else "",
            "hash_result": hash_res,
        }

    def fetch_game_info_and_user_progress(self, ra_game_id: int) -> dict[str, Any]:
        """Consulta `API_GetGameInfoAndUserProgress.php` y normaliza el progreso del usuario."""
        user, key = self._require_credentials()
        data = self._get_json(
            "API_GetGameInfoAndUserProgress.php",
            {"y": key, "u": user, "g": int(ra_game_id), "a": 1},
        )
        if not isinstance(data, dict) or not data.get("ID"):
            raise RuntimeError(f"RetroAchievements no devolvió datos para el juego ID {ra_game_id}.")

        raw_ach = data.get("Achievements") or {}
        achievements: list[dict[str, Any]] = []
        points_earned = 0
        points_total = 0

        if isinstance(raw_ach, dict):
            ach_iter = raw_ach.values()
        elif isinstance(raw_ach, list):
            ach_iter = raw_ach
        else:
            ach_iter = []

        for item in ach_iter:
            if not isinstance(item, dict):
                continue
            pts = int(item.get("Points") or 0)
            date_soft = str(item.get("DateEarned") or "").strip()
            date_hard = str(item.get("DateEarnedHardcore") or "").strip()
            earned = bool(date_soft or date_hard)
            hardcore = bool(date_hard)
            points_total += pts
            if earned:
                points_earned += pts
            achievements.append(
                {
                    "id": int(item.get("ID") or 0),
                    "title": str(item.get("Title") or ""),
                    "description": str(item.get("Description") or ""),
                    "points": pts,
                    "true_ratio": int(item.get("TrueRatio") or 0),
                    "badge_name": str(item.get("BadgeName") or ""),
                    "display_order": int(item.get("DisplayOrder") or 0),
                    "type": str(item.get("type") or ""),
                    "earned": earned,
                    "hardcore": hardcore,
                    "date_earned": date_hard or date_soft,
                }
            )

        achievements.sort(key=lambda a: (0 if a["earned"] else 1, a["display_order"], a["id"]))
        total_ach = int(data.get("NumAchievements") or len(achievements))
        unlocked_soft = int(data.get("NumAwardedToUser") or sum(1 for a in achievements if a["earned"]))
        unlocked_hard = int(data.get("NumAwardedToUserHardcore") or sum(1 for a in achievements if a["hardcore"]))
        unlocked = max(unlocked_soft, unlocked_hard)
        pct = round((unlocked * 100.0) / total_ach, 1) if total_ach > 0 else 0.0

        return {
            "ra_game_id": int(data.get("ID") or ra_game_id),
            "title": str(data.get("Title") or ""),
            "console_id": int(data.get("ConsoleID") or 0),
            "console_name": str(data.get("ConsoleName") or ""),
            "image_icon": str(data.get("ImageIcon") or ""),
            "username": user,
            "total": total_ach,
            "unlocked": unlocked,
            "unlocked_hardcore": unlocked_hard,
            "pct": pct,
            "points_earned": points_earned,
            "points_total": points_total,
            "achievements": achievements,
            "synced_at": time.time(),
        }

    def sync_game_progress(
        self,
        game_row: dict[str, Any],
        system_key: str,
        console_id: int,
        force_refresh_catalog: bool = False,
    ) -> dict[str, Any]:
        """Identifica un juego, consulta sus logros y persiste detalle + índice en caché."""
        match = self.resolve_game_in_catalog(
            game_row,
            system_key=system_key,
            console_id=console_id,
            force_refresh=force_refresh_catalog,
        )
        rom_key = _norm_rom_index_key(game_row)

        if not match["matched"]:
            entry = {
                "matched": False,
                "ra_game_id": 0,
                "title": str(game_row.get("title") or ""),
                "console_id": console_id,
                "console_name": "",
                "unlocked": 0,
                "unlocked_hardcore": 0,
                "total": 0,
                "pct": 0.0,
                "points_earned": 0,
                "points_total": 0,
                "match_method": match["match_method"],
                "hash_used": match["hash_used"],
                "hash_method": match["hash_result"].method,
                "note": match["hash_result"].note,
                "synced_at": time.time(),
            }
            if rom_key:
                _update_rom_index_entries(self.cache_dir, {rom_key: entry})
            return entry

        ra_gid = int(match["ra_game_id"])
        detail = self.fetch_game_info_and_user_progress(ra_gid)
        detail["match_method"] = match["match_method"]
        detail["hash_used"] = match["hash_used"]
        detail["hash_method"] = match["hash_result"].method

        detail_file = self.cache_dir / "games" / f"{ra_gid}_{_safe_user_slug(self.config.username)}.json"
        try:
            detail_file.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        summary = {
            "matched": True,
            "ra_game_id": ra_gid,
            "title": detail["title"],
            "console_id": detail["console_id"] or console_id,
            "console_name": detail["console_name"],
            "username": detail["username"],
            "unlocked": detail["unlocked"],
            "unlocked_hardcore": detail["unlocked_hardcore"],
            "total": detail["total"],
            "pct": detail["pct"],
            "points_earned": detail["points_earned"],
            "points_total": detail["points_total"],
            "match_method": match["match_method"],
            "hash_used": match["hash_used"],
            "hash_method": detail["hash_method"],
            "detail_file": detail_file.name,
            "synced_at": detail["synced_at"],
        }
        if rom_key:
            _update_rom_index_entries(self.cache_dir, {rom_key: summary})
        return {**summary, "achievements": detail["achievements"]}

    def sync_list_progress(
        self,
        games: list[dict[str, Any]],
        system_key: str,
        console_id: int,
        force_refresh_catalog: bool = False,
        only_missing: bool = False,
        progress_callback: Callable[[int, int, str, dict[str, Any]], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Sincroniza todos los juegos de una lista con barra de progreso y soporte de cancelación."""
        self.get_console_catalog(console_id, force_refresh=force_refresh_catalog)
        total = len(games)
        matched_count = 0
        unmatched_count = 0
        error_count = 0
        skipped_cached = 0
        cancelled = False

        for idx, g in enumerate(games, start=1):
            if cancel_check and cancel_check():
                cancelled = True
                break

            title = str(g.get("title") or Path(str(g.get("rom_path") or "")).stem)
            if only_missing:
                existing = get_cached_ra_progress_summary(self.db, g)
                if existing and existing.get("synced_at"):
                    skipped_cached += 1
                    if existing.get("matched"):
                        matched_count += 1
                    if progress_callback:
                        progress_callback(idx, total, title, existing)
                    continue

            try:
                res = self.sync_game_progress(g, system_key=system_key, console_id=console_id, force_refresh_catalog=False)
                if res.get("matched"):
                    matched_count += 1
                else:
                    unmatched_count += 1
                if progress_callback:
                    progress_callback(idx, total, title, res)
            except Exception as exc:
                error_count += 1
                if progress_callback:
                    progress_callback(idx, total, title, {"matched": False, "error": str(exc)})

        return {
            "total": total,
            "matched": matched_count,
            "unmatched": unmatched_count,
            "skipped_cached": skipped_cached,
            "errors": error_count,
            "cancelled": cancelled,
        }


# ------------------------------------------------------------------
# LECTURA O(1) DE CACHÉ LOCAL (SIN RED PARA LA UI Y FRONTEND)
# ------------------------------------------------------------------
def _load_rom_index(cache_dir: Path) -> dict[str, dict[str, Any]]:
    idx_file = cache_dir / "rom_index.json"
    if not idx_file.is_file():
        return {}
    cache_key = str(cache_dir).lower()
    try:
        mtime = idx_file.stat().st_mtime
    except OSError:
        mtime = 0.0

    cached = _MEM_ROM_INDEX_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        data = json.loads(idx_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    _MEM_ROM_INDEX_CACHE[cache_key] = (mtime, data)
    return data


def _update_rom_index_entries(cache_dir: Path, updates: dict[str, dict[str, Any]]) -> None:
    if not updates:
        return
    idx_file = cache_dir / "rom_index.json"
    current = dict(_load_rom_index(cache_dir))
    current.update(updates)
    tmp = idx_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, idx_file)
    try:
        mtime = idx_file.stat().st_mtime
    except OSError:
        mtime = time.time()
    _MEM_ROM_INDEX_CACHE[str(cache_dir).lower()] = (mtime, current)


def get_cached_ra_progress_summary(db, game_row: dict[str, Any] | Any) -> dict[str, Any] | None:
    """
    Lee en O(1) el resumen en caché de RetroAchievements para un juego (cero peticiones de red).
    """
    if db is None or game_row is None:
        return None
    rom_key = _norm_rom_index_key(game_row)
    if not rom_key:
        return None
    cdir = get_ra_cache_dir(db)
    idx = _load_rom_index(cdir)
    entry = idx.get(rom_key)
    return dict(entry) if isinstance(entry, dict) else None


def get_cached_ra_detail(db, game_row: dict[str, Any] | Any) -> dict[str, Any] | None:
    """Lee desde caché el detalle completo de logros desbloqueados/bloqueados de un juego."""
    summary = get_cached_ra_progress_summary(db, game_row)
    if not summary or not summary.get("matched"):
        return None
    cdir = get_ra_cache_dir(db)
    detail_name = str(summary.get("detail_file") or "").strip()
    if detail_name:
        fpath = cdir / "games" / detail_name
        if fpath.is_file():
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    ra_gid = int(summary.get("ra_game_id") or 0)
    if ra_gid > 0:
        for cand in sorted((cdir / "games").glob(f"{ra_gid}_*.json")):
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    return summary


def format_ra_badge_text(summary: dict[str, Any] | None) -> str:
    """Formatea un texto corto para tablas/fichas/menús ('🏆 12/24 (50%)')."""
    if not summary:
        return "Sin sincronizar"
    if not summary.get("matched"):
        return "No catalogado en RA"
    total = int(summary.get("total") or 0)
    unlocked = int(summary.get("unlocked") or 0)
    pct = float(summary.get("pct") or 0.0)
    if total <= 0:
        return "🏆 0 logros"
    return f"🏆 {unlocked}/{total} ({pct:.0f}%)"
