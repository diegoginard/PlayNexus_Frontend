"""
Modelos y configuración para el motor de scraping online de PlayNexus.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from typing import Any


def _encode_secret(raw: str) -> str:
    """Codifica credenciales en base64 URL-safe para persistencia limpia en settings.txt."""
    text = (raw or "").strip()
    if not text:
        return ""
    token = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
    return f"b64:{token}"


def _decode_secret(stored: str) -> str:
    """Decodifica credenciales guardadas en settings.txt (retrocompatible con texto plano)."""
    text = (stored or "").strip()
    if not text:
        return ""
    if text.startswith("b64:"):
        payload = text[4:]
        try:
            return base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        except Exception:
            return ""
    return text


DEFAULT_REGION_PRIORITY: tuple[str, ...] = ("us", "wor", "ss", "eu", "es", "jp")


@dataclass
class ScraperConfig:
    """Preferencias y credenciales del Scraper almacenadas en config/settings.txt."""

    preferred_provider: str = "auto"  # "auto" | "libretro" | "arcadedb" | "screenscraper"
    region_priority: tuple[str, ...] = DEFAULT_REGION_PRIORITY
    language: str = "es"
    ss_devid: str = ""
    ss_devpassword: str = ""
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
        return max(1, min(4, val))


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
        workers = max(1, min(4, int(_get("scraper_max_workers", "2") or "2")))
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

    raw_ssid = _decode_secret(_get("scraper_ss_ssid", ""))
    raw_sspass = _decode_secret(_get("scraper_ss_sspassword", ""))
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
        ss_devid=_decode_secret(_get("scraper_ss_devid", "")),
        ss_devpassword=_decode_secret(_get("scraper_ss_devpassword", "")),
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
    with db.batch():
        db.set_setting("scraper_provider", config.preferred_provider)
        db.set_setting("scraper_region_priority", ",".join(config.region_priority))
        db.set_setting("scraper_language", config.language)
        db.set_setting("scraper_ss_devid", _encode_secret(config.ss_devid))
        db.set_setting("scraper_ss_devpassword", _encode_secret(config.ss_devpassword))
        db.set_setting("scraper_ss_remember", "true" if config.ss_remember else "false")
        if config.ss_remember:
            db.set_setting("scraper_ss_ssid", _encode_secret(config.ss_ssid))
            db.set_setting("scraper_ss_sspassword", _encode_secret(config.ss_sspassword))
        else:
            db.set_setting("scraper_ss_ssid", "")
            db.set_setting("scraper_ss_sspassword", "")
        db.set_setting("scraper_max_workers", str(config.normalized_workers()))
        db.set_setting("scraper_update_empty_meta", "true" if config.update_empty_metadata else "false")
        db.set_setting("scraper_overwrite_meta", "true" if config.overwrite_metadata else "false")
        db.set_setting("scraper_cache_enabled", "true" if config.cache_enabled else "false")
        db.set_setting("scraper_timeout_sec", f"{float(config.timeout_sec):.1f}")
        db.set_setting("scraper_prefer_hd_video", "true" if config.prefer_hd_video else "false")


@dataclass
class ScraperMediaAsset:
    """Recurso multimedia descargable devuelto por un proveedor."""

    slot_key: str
    url: str
    ext_hint: str = ".png"
    region: str = "wor"
    media_kind: str = "image"  # "image" | "video"
    source_type: str = ""
    provider_id: str = ""


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
