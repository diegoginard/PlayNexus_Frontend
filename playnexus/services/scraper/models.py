"""
Modelos y configuración para el motor de scraping online de PlayNexus.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playnexus.db import APP_DIR
from playnexus.i18n import tr

_KEY_FILENAME = ".key"
_SECRET_PREFIX = "enc1:"
_KEY_BYTES = 32
_NONCE_BYTES = 16
_TAG_BYTES = 32


def _resolve_secret_key_dir(db: Any | None = None, key_dir: Path | str | None = None) -> Path:
    """Resuelve la carpeta `config/` donde vive `.key` (soporta instancias aisladas de Database)."""
    if key_dir is not None:
        return Path(key_dir)
    if db is not None:
        base = getattr(db, "path", None) or getattr(db, "data_dir", None)
        if base:
            return Path(base) / "config"
    return Path(APP_DIR) / "config"


def _load_or_create_secret_key(key_dir: Path, create: bool) -> bytes | None:
    """Carga la llave aleatoria de 256 bits desde `config/.key` (o la crea de forma atómica)."""
    key_path = Path(key_dir) / _KEY_FILENAME
    try:
        if key_path.is_file():
            raw_txt = key_path.read_text(encoding="ascii").strip()
            raw_key = base64.urlsafe_b64decode(raw_txt.encode("ascii"))
            if len(raw_key) == _KEY_BYTES:
                return raw_key
    except Exception:
        pass

    if not create:
        return None

    Path(key_dir).mkdir(parents=True, exist_ok=True)
    new_key = secrets.token_bytes(_KEY_BYTES)
    encoded_key = base64.urlsafe_b64encode(new_key).decode("ascii")
    tmp_path = Path(key_dir) / f".key.tmp.{os.getpid()}"
    try:
        tmp_path.write_text(encoded_key, encoding="ascii")
        os.replace(str(tmp_path), str(key_path))
    finally:
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except Exception:
                pass
    return new_key


def _xor_keystream(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    """Genera flujo de cifrado CTR mediante SHA-256 sobre clave derivada y nonce aleatorio."""
    out = bytearray(len(data))
    offset = 0
    counter = 0
    total = len(data)
    while offset < total:
        block = hashlib.sha256(enc_key + nonce + counter.to_bytes(4, "big")).digest()
        chunk_len = min(len(block), total - offset)
        for i in range(chunk_len):
            out[offset + i] = data[offset + i] ^ block[i]
        offset += chunk_len
        counter += 1
    return bytes(out)


def _derive_subkeys(master_key: bytes) -> tuple[bytes, bytes]:
    enc_key = hmac.new(master_key, b"playnexus-enc-v1", hashlib.sha256).digest()
    mac_key = hmac.new(master_key, b"playnexus-mac-v1", hashlib.sha256).digest()
    return enc_key, mac_key


def _encode_secret(raw: str, key_dir: Path | str | None = None) -> str:
    """Cifra credenciales usando clave aleatoria portátil en config/.key (SHA256-CTR + HMAC-SHA256)."""
    text = (raw or "").strip()
    if not text:
        return ""
    resolved_dir = _resolve_secret_key_dir(key_dir=key_dir)
    master_key = _load_or_create_secret_key(resolved_dir, create=True)
    if not master_key:
        raise RuntimeError(tr("svc.scraper.err_init_key", "Could not initialize local encryption key."))
    enc_key, mac_key = _derive_subkeys(master_key)
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ciphertext = _xor_keystream(enc_key, nonce, text.encode("utf-8"))
    tag = hmac.new(mac_key, b"enc1" + nonce + ciphertext, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii")
    return f"{_SECRET_PREFIX}{token}"


def _decode_secret(stored: str, key_dir: Path | str | None = None) -> str:
    """Descifra secretos `enc1:` (con retrocompatibilidad para valores `b64:` y texto plano)."""
    text = (stored or "").strip()
    if not text:
        return ""
    if text.startswith(_SECRET_PREFIX):
        payload_b64 = text[len(_SECRET_PREFIX):]
        try:
            blob = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
            if len(blob) < _NONCE_BYTES + _TAG_BYTES:
                return ""
            resolved_dir = _resolve_secret_key_dir(key_dir=key_dir)
            master_key = _load_or_create_secret_key(resolved_dir, create=False)
            if not master_key:
                return ""
            nonce = blob[:_NONCE_BYTES]
            tag = blob[-_TAG_BYTES:]
            ciphertext = blob[_NONCE_BYTES:-_TAG_BYTES]
            enc_key, mac_key = _derive_subkeys(master_key)
            expected_tag = hmac.new(mac_key, b"enc1" + nonce + ciphertext, hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected_tag):
                return ""
            plain = _xor_keystream(enc_key, nonce, ciphertext)
            return plain.decode("utf-8")
        except Exception:
            return ""
    if text.startswith("b64:"):
        payload = text[4:]
        try:
            return base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        except Exception:
            return ""
    return text


DEFAULT_REGION_PRIORITY: tuple[str, ...] = ("us", "wor", "ss", "eu", "es", "jp")
MAX_SCRAPER_WORKERS: int = 20


@dataclass
class ScraperConfig:
    """Preferencias y credenciales del Scraper almacenadas en config/settings.txt."""

    preferred_provider: str = "auto"  # "auto" | "libretro" | "arcadedb" | "screenscraper"
    region_priority: tuple[str, ...] = DEFAULT_REGION_PRIORITY
    language: str = "es"
    ss_devid: str = ""
    ss_devpassword: str = ""
    ss_devdebugpassword: str = ""
    ss_debug_mode: bool = False
    ss_ssid: str = ""
    ss_sspassword: str = ""
    ss_remember: bool = False
    max_workers: int = 2
    update_empty_metadata: bool = True
    overwrite_metadata: bool = False
    cache_enabled: bool = True
    timeout_sec: float = 18.0
    prefer_hd_video: bool = True

    def resolved_ss_devid(self) -> str:
        """Retorna el Dev ID propio o inyectado por entorno para la API v2."""
        return self.ss_devid.strip() or os.environ.get("PLAYNEXUS_SS_DEVID", "").strip()

    def resolved_ss_devpassword(self) -> str:
        """Retorna el Dev Password propio o inyectado por entorno para la API v2."""
        return (
            self.ss_devpassword.strip()
            or os.environ.get("PLAYNEXUS_SS_DEVPASSWORD", "").strip()
            or os.environ.get("PLAYNEXUS_SS_DEVPASS", "").strip()
        )

    def resolved_ss_devdebugpassword(self) -> str:
        """Retorna la Contraseña Debug de desarrollador propia o por entorno."""
        return (
            self.ss_devdebugpassword.strip()
            or os.environ.get("PLAYNEXUS_SS_DEVDEBUGPASSWORD", "").strip()
        )

    @property
    def has_screenscraper_dev_credentials(self) -> bool:
        return bool(self.resolved_ss_devid() and self.resolved_ss_devpassword())

    @property
    def has_screenscraper_user_credentials(self) -> bool:
        return bool(self.ss_ssid.strip() and self.ss_sspassword.strip())

    @property
    def has_screenscraper_credentials(self) -> bool:
        return self.has_screenscraper_user_credentials or self.has_screenscraper_dev_credentials

    def normalized_workers(self) -> int:
        try:
            val = int(self.max_workers)
        except (TypeError, ValueError):
            val = 2
        return max(1, min(MAX_SCRAPER_WORKERS, val))


def load_scraper_config(db: Any | None) -> ScraperConfig:
    """Carga ScraperConfig desde Database.get_setting sin fallar si db es None."""
    if not db:
        return ScraperConfig()

    def _get(key: str, default: str = "") -> str:
        val = db.get_setting(key, default)
        return default if val is None else str(val)

    raw_regions = _get("scraper_region_priority", ",".join(DEFAULT_REGION_PRIORITY))
    regions = tuple(
        r.strip().lower()
        for r in raw_regions.split(",")
        if r.strip()
    ) or DEFAULT_REGION_PRIORITY

    try:
        workers = max(1, min(MAX_SCRAPER_WORKERS, int(_get("scraper_max_workers", "2") or "2")))
    except ValueError:
        workers = 2

    try:
        timeout = max(5.0, min(60.0, float(_get("scraper_timeout_sec", "18.0") or "18.0")))
    except ValueError:
        timeout = 18.0

    provider = _get("scraper_provider", "auto").strip().lower()
    if provider not in ("auto", "libretro", "arcadedb", "screenscraper"):
        provider = "auto"

    lang = _get("scraper_language", "es").strip().lower()
    if lang not in ("es", "en", "fr"):
        lang = "es"

    key_dir = _resolve_secret_key_dir(db)
    raw_ssid = _decode_secret(_get("scraper_ss_ssid", ""), key_dir=key_dir)
    raw_sspass = _decode_secret(_get("scraper_ss_sspassword", ""), key_dir=key_dir)
    raw_remember = _get("scraper_ss_remember", "").strip().lower()
    if raw_remember in ("true", "false"):
        ss_remember = (raw_remember == "true")
    else:
        ss_remember = bool(raw_ssid or raw_sspass)
    if not ss_remember:
        raw_ssid = ""
        raw_sspass = ""

    return ScraperConfig(
        preferred_provider=provider,
        region_priority=regions,
        language=lang,
        ss_devid=_decode_secret(_get("scraper_ss_devid", ""), key_dir=key_dir),
        ss_devpassword=_decode_secret(_get("scraper_ss_devpassword", ""), key_dir=key_dir),
        ss_devdebugpassword=_decode_secret(_get("scraper_ss_devdebugpassword", ""), key_dir=key_dir),
        ss_debug_mode=_get("scraper_ss_debug_mode", "false").strip().lower() == "true",
        ss_ssid=raw_ssid,
        ss_sspassword=raw_sspass,
        ss_remember=ss_remember,
        max_workers=workers,
        update_empty_metadata=_get("scraper_update_empty_meta", "true").lower() == "true",
        overwrite_metadata=_get("scraper_overwrite_meta", "false").lower() == "true",
        cache_enabled=_get("scraper_cache_enabled", "true").lower() == "true",
        timeout_sec=timeout,
        prefer_hd_video=_get("scraper_prefer_hd_video", "true").lower() == "true",
    )


def save_scraper_config(db: Any, config: ScraperConfig) -> None:
    """Guarda ScraperConfig en config/settings.txt mediante db.batch()."""
    if not db:
        return
    key_dir = _resolve_secret_key_dir(db)
    with db.batch():
        db.set_setting("scraper_provider", config.preferred_provider)
        db.set_setting("scraper_region_priority", ",".join(config.region_priority))
        db.set_setting("scraper_language", config.language)
        db.set_setting("scraper_ss_devid", _encode_secret(config.ss_devid, key_dir=key_dir))
        db.set_setting("scraper_ss_devpassword", _encode_secret(config.ss_devpassword, key_dir=key_dir))
        db.set_setting("scraper_ss_devdebugpassword", _encode_secret(config.ss_devdebugpassword, key_dir=key_dir))
        db.set_setting("scraper_ss_debug_mode", "true" if config.ss_debug_mode else "false")
        db.set_setting("scraper_ss_remember", "true" if config.ss_remember else "false")
        if config.ss_remember:
            db.set_setting("scraper_ss_ssid", _encode_secret(config.ss_ssid, key_dir=key_dir))
            db.set_setting("scraper_ss_sspassword", _encode_secret(config.ss_sspassword, key_dir=key_dir))
        else:
            db.set_setting("scraper_ss_ssid", "")
            db.set_setting("scraper_ss_sspassword", "")
        db.set_setting("scraper_max_workers", str(config.normalized_workers()))
        db.set_setting("scraper_update_empty_meta", "true" if config.update_empty_metadata else "false")
        db.set_setting("scraper_overwrite_meta", "true" if config.overwrite_metadata else "false")
        db.set_setting("scraper_cache_enabled", "true" if config.cache_enabled else "false")
        db.set_setting("scraper_timeout_sec", f"{float(config.timeout_sec):.1f}")
        db.set_setting("scraper_prefer_hd_video", "true" if config.prefer_hd_video else "false")


_SUBTYPE_SHORT_LABELS: dict[str, str] = {
    "box-3d": "3D",
    "box-2d": "2D",
    "box-2d-front": "2D Front",
    "box-texture": "Full Cover",
    "wheel-hd": "HD",
    "wheel": "Std",
    "wheel-carbon": "Carbon",
    "wheel-steel": "Steel",
    "support-2d": "2D",
    "support-texture": "Label",
    "video": "HD/Orig",
    "video-normalized": "Norm",
    "url_video_shortplay_hd": "HD",
    "url_video_shortplay": "SD",
    "bezel-16-9": "16:9",
    "overlay": "Overlay",
    "screenmarquee": "Screen",
    "marquee": "Cabinet",
    "cab-2d": "2D",
}


@dataclass
class ScraperMediaAsset:
    """Recurso multimedia descargable devuelto por un proveedor."""

    slot_key: str
    url: str
    ext_hint: str = ".png"
    region: str = "wor"
    media_kind: str = "image"  # "image" | "video" | "pdf"
    source_type: str = ""
    provider_id: str = ""

    def variant_label(self) -> str:
        """Etiqueta legible de región y subtipo para selectores exclusivos por slot (ej. 'US · 3D', 'JP · 2D')."""
        reg = (self.region or "wor").strip().upper()
        st_raw = (self.source_type or "").strip()
        st_short = _SUBTYPE_SHORT_LABELS.get(st_raw.lower(), "")
        if st_short:
            return f"{reg} · {st_short}"
        if st_raw and st_raw.lower() not in (self.slot_key.lower(), "named_boxarts", "named_logos"):
            return f"{reg} · {st_raw}"
        return reg


@dataclass
class ScraperCandidate:
    """Juego candidato encontrado en un proveedor online."""

    provider_id: str
    provider_label: str
    game_id: str
    title: str
    system_id: str = ""
    year: str = ""
    manufacturer: str = ""
    genre: str = ""
    players: str = ""
    rating: str = ""
    notes: str = ""
    cloneof: str = ""
    crc: str = ""
    match_score: float = 1.0
    matched_name: str = ""
    assets: dict[str, ScraperMediaAsset] = field(default_factory=dict)
    asset_variants: dict[str, list[ScraperMediaAsset]] = field(default_factory=dict)

    def variants_for_slot(self, slot_key: str) -> list[ScraperMediaAsset]:
        """Retorna todas las variantes regionales/tipo disponibles para un slot (sin duplicar URLs)."""
        vars_list = self.asset_variants.get(slot_key)
        if vars_list:
            return list(vars_list)
        single = self.assets.get(slot_key)
        return [single] if single else []


@dataclass
class ScrapeJobOptions:
    """Opciones elegidas por el usuario para un lote de scraping en Rom Manager."""

    system_key: str
    provider_mode: str  # "auto" | "libretro" | "arcadedb" | "screenscraper"
    target_slots: tuple[str, ...]
    overwrite_existing: bool = False
    update_empty_metadata: bool = True
    overwrite_metadata: bool = False
    only_filtered: bool = False
    max_workers: int = 2


@dataclass
class RomScrapeOutcome:
    """Resultado completo del scraping online de una ROM individual."""

    game_id: int
    title: str
    stem: str
    status: str  # "downloaded" | "partial" | "skipped" | "not_found" | "error" | "cancelled"
    downloaded_slots: dict[str, str] = field(default_factory=dict)  # slot_key -> saved_path
    failed_slots: dict[str, str] = field(default_factory=dict)      # slot_key -> error/reason
    metadata_updates: dict[str, str] = field(default_factory=dict)
    provider_used: str = ""
    matched_title: str = ""
    message: str = ""


@dataclass
class BatchScrapeSummary:
    """Resumen agregado de una ejecución de scraping en lote."""

    total_targets: int = 0
    processed: int = 0
    downloaded_roms: int = 0
    partial_roms: int = 0
    not_found_roms: int = 0
    skipped_roms: int = 0
    error_roms: int = 0
    files_saved: int = 0
    metadata_enriched: int = 0
    cancelled: bool = False
    outcomes: list[RomScrapeOutcome] = field(default_factory=list)
