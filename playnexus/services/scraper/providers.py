"""
Proveedores online del Scraper de PlayNexus:
  1. ArcadeItaliaProvider  -> ADB (MAME / Arcade completo: video MP4, wheel, flyer, cabinet, marquee, bezel, metadata)
  2. LibretroThumbnailsProvider -> CDN Thumbnails (Gratis, sin API key: Boxart & Wheel/Logos para ~127 consolas)
  3. ScreenScraperProvider -> API v2 oficial (hashes CRC/MD5/SHA1 + búsqueda: toda la media + sinopsis/metadatos)
"""
from __future__ import annotations

import contextlib
import html as html_lib
import json
import os
import re
import threading
import urllib.error
import urllib.parse
from difflib import SequenceMatcher
from typing import Any, Callable

from playnexus.i18n import tr
from playnexus.services.scraper.cache import ScraperCache
from playnexus.services.scraper.http_utils import (
    ProviderRateLimiter,
    compute_inner_zip_rom_info,
    compute_rom_hashes,
    http_get_json,
    http_get_text,
)
from playnexus.services.scraper.models import (
    MAX_SCRAPER_WORKERS,
    ScraperCandidate,
    ScraperConfig,
    ScraperMediaAsset,
)
from playnexus.services.scraper.systems import (
    ScraperSystem,
    build_search_query_variants,
    clean_rom_search_title,
    normalize_match_key,
)


_LIBRETRO_BASE = "https://thumbnails.libretro.com"
_ADB_BASE = "https://adb.arcadeitalia.net/service_scraper.php"
_SS_BASE = "https://api.screenscraper.fr/api2"

_HREF_PNG_RE = re.compile(r'<a\s+href="([^"?]+\.png)"', re.IGNORECASE)
_REGION_TAG_RE = re.compile(r"\(([^)]+)\)")
_LIBRETRO_SAN_MAP = str.maketrans({c: "_" for c in '&*/:`<>?\\|"'})

_PRE_RELEASE_PENALTY_WORDS = ("beta", "proto", "sample", "demo", "kiosk", "promo", "pirate", "unl")
_SS_ISO_EXTS = frozenset({".iso", ".bin", ".cue", ".chd", ".cso", ".pbp", ".rvz", ".wbfs", ".nrg", ".cdi", ".gdi"})

# Regiones de No-Intro / Redump en nombres Libretro -> código normalizado ScreenScraper
_REGION_ALIAS_RANK = {
    "usa": "us",
    "u": "us",
    "world": "wor",
    "w": "wor",
    "europe": "eu",
    "e": "eu",
    "spain": "es",
    "s": "es",
    "en": "wor",
    "japan": "jp",
    "j": "jp",
    "france": "fr",
    "germany": "de",
    "italy": "it",
    "brazil": "br",
    "korea": "kr",
}

# Prioridad de tipos ScreenScraper por slot de MEDIA_REQUIREMENTS
_SS_SLOT_TYPE_PRIORITY: dict[str, tuple[str, ...]] = {
    "boxart": ("box-3D", "box-2D", "box-2D-front", "box-texture"),
    "wheel": ("wheel-hd", "wheel", "wheel-carbon", "wheel-steel"),
    "cartart": ("support-2D", "support-texture"),
    "discart": ("support-2D", "support-texture"),
    "video": ("video-normalized", "video"),
    "flyer": ("flyer",),
    "marquee": ("screenmarquee", "marquee"),
    "bezel": ("bezel-16-9", "overlay"),
    "cabinet": ("cab-2D", "cabinet"),
    "manual": ("manuel",),
}


def _infer_rom_regions(stem: str, rom_path: str = "") -> list[str]:
    """Infiere códigos de región prioritarios a partir de etiquetas como (J), (U), (E), (S) o [Tesp] en la ROM."""
    src = f"{stem or ''} {os.path.basename(rom_path) if rom_path else ''}"
    found: list[str] = []

    def _push(code: str) -> None:
        if code and code not in found:
            found.append(code)

    low_src = src.lower()
    if "[tesp" in low_src or "t-spa" in low_src or "spanish" in low_src:
        _push("sp")
        _push("es")
    for tag in _extract_region_tags(src):
        mapped = _REGION_ALIAS_RANK.get(tag, tag)
        if mapped == "es":
            _push("sp")
            _push("es")
        elif mapped in ("us", "eu", "jp", "sp", "wor", "fr", "de", "it", "br", "kr", "au"):
            _push(mapped)
    return found


def _extract_region_tags(filename_stem: str) -> list[str]:
    tags: list[str] = []
    for grp in _REGION_TAG_RE.findall(filename_stem or ""):
        for part in grp.split(","):
            tok = part.strip().lower()
            if tok:
                tags.append(tok)
    return tags


def _score_region_bonus(tags: list[str], region_priority: tuple[str, ...]) -> float:
    mapped: list[str] = []
    for t in tags:
        if t in _REGION_ALIAS_RANK:
            mapped.append(_REGION_ALIAS_RANK[t])
        else:
            mapped.append(t)

    best_bonus = 0.0
    for idx, reg in enumerate(region_priority):
        if reg in mapped:
            best_bonus = max(best_bonus, 0.05 * max(0, len(region_priority) - idx) / max(1, len(region_priority)))

    lowered = " ".join(tags)
    if any(w in lowered for w in _PRE_RELEASE_PENALTY_WORDS):
        best_bonus -= 0.06
    return best_bonus


def _libretro_sanitize(stem: str) -> str:
    return (stem or "").translate(_LIBRETRO_SAN_MAP)


class BaseScraperProvider:
    """Interfaz común para proveedores online de metadata y artwork."""

    provider_id: str = ""
    provider_label: str = ""

    def is_available(self, system: ScraperSystem, config: ScraperConfig) -> bool:
        return True

    def find_candidates(
        self,
        query: str,
        stem: str,
        rom_path: str,
        system: ScraperSystem,
        config: ScraperConfig,
        target_slots: tuple[str, ...] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        max_results: int = 8,
    ) -> list[ScraperCandidate]:
        raise NotImplementedError


# =====================================================================
# 1. ARCADE DATABASE (adb.arcadeitalia.net) — CERO API KEY PARA MAME
# =====================================================================
class ArcadeItaliaProvider(BaseScraperProvider):
    """Proveedor gratuito para MAME / FBNeo / Arcade usando service_scraper.php."""

    provider_id = "arcadedb"
    provider_label = "Arcade Database (ADB)"

    def __init__(self, cache: ScraperCache):
        self.cache = cache
        self._limiter = ProviderRateLimiter(0.35)

    def is_available(self, system: ScraperSystem, config: ScraperConfig) -> bool:
        return bool(system.is_arcade)

    def _query_raw(
        self,
        ajax_mode: str,
        game_name: str,
        config: ScraperConfig,
        cancel_check: Callable[[], bool] | None,
    ) -> dict[str, Any] | None:
        key = f"{ajax_mode}:{game_name.lower()}"
        cached = self.cache.get("adb", key, max_age_sec=86400.0 * 7)
        if isinstance(cached, dict):
            return cached.get("item")

        if not self._limiter.wait(cancel_check):
            return None

        params = {
            "ajax": ajax_mode,
            "lang": "en",
            "game_name": game_name,
        }
        if ajax_mode == "query_mame_media":
            params["use_parent"] = "1"
        url = f"{_ADB_BASE}?{urllib.parse.urlencode(params)}"
        try:
            payload = http_get_json(url, timeout=config.timeout_sec, retries=1)
        except Exception:
            return None

        results = payload.get("result") if isinstance(payload, dict) else None
        item = results[0] if isinstance(results, list) and results else None
        self.cache.set("adb", key, {"item": item})
        return item if isinstance(item, dict) else None

    def find_candidates(
        self,
        query: str,
        stem: str,
        rom_path: str,
        system: ScraperSystem,
        config: ScraperConfig,
        target_slots: tuple[str, ...] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        max_results: int = 5,
    ) -> list[ScraperCandidate]:
        if not stem and not query:
            return []

        probe_names: list[str] = []
        if stem:
            clean_stem = stem.strip().lower()
            if clean_stem and " " not in clean_stem:
                probe_names.append(clean_stem)
        if query:
            q_slug = query.strip().lower()
            if q_slug and " " not in q_slug and q_slug not in probe_names:
                probe_names.append(q_slug)

        for name_token in probe_names:
            if cancel_check and cancel_check():
                return []
            media_row = self._query_raw("query_mame_media", name_token, config, cancel_check)
            info_row = self._query_raw("query_mame", name_token, config, cancel_check)
            merged = dict(info_row or {})
            if media_row:
                merged.update({k: v for k, v in media_row.items() if v})
            if not merged or not merged.get("title"):
                continue

            assets: dict[str, ScraperMediaAsset] = {}
            asset_variants: dict[str, list[ScraperMediaAsset]] = {}
            img_map = (
                ("boxart", "url_image_box", ".png"),
                ("wheel", "url_image_logo", ".png"),
                ("cabinet", "url_image_cabinet", ".png"),
                ("flyer", "url_image_flyer", ".jpg"),
                ("marquee", "url_image_marquee", ".png"),
                ("bezel", "url_image_bezel", ".png"),
            )
            for slot_k, field_name, ext_h in img_map:
                u = str(merged.get(field_name) or "").strip()
                if u:
                    a_obj = ScraperMediaAsset(
                        slot_key=slot_k,
                        url=u,
                        ext_hint=ext_h,
                        region="wor",
                        media_kind="image",
                        source_type=field_name,
                        provider_id=self.provider_id,
                    )
                    assets[slot_k] = a_obj
                    asset_variants[slot_k] = [a_obj]

            vid_fields = (
                (("url_video_shortplay_hd", "url_video_shortplay") if config.prefer_hd_video else ("url_video_shortplay", "url_video_shortplay_hd"))
            )
            vid_variants: list[ScraperMediaAsset] = []
            seen_vurls: set[str] = set()
            for vf in vid_fields:
                vu = str(merged.get(vf) or "").strip()
                if vu and vu not in seen_vurls:
                    seen_vurls.add(vu)
                    vid_variants.append(
                        ScraperMediaAsset(
                            slot_key="video",
                            url=vu,
                            ext_hint=".mp4",
                            region="wor",
                            media_kind="video",
                            source_type=vf,
                            provider_id=self.provider_id,
                        )
                    )
            if vid_variants:
                assets["video"] = vid_variants[0]
                asset_variants["video"] = vid_variants

            year_raw = re.sub(r"[^0-9]", "", str(merged.get("year") or ""))[:4]
            rate_raw = merged.get("rate")
            rating_str = ""
            if rate_raw not in (None, "", 0, "0"):
                try:
                    rating_str = f"{float(rate_raw):.0f}/100"
                except (TypeError, ValueError):
                    rating_str = str(rate_raw)

            players_val = str(merged.get("players") or merged.get("nplayers") or "").strip()
            if players_val == "0":
                players_val = ""

            history = str(merged.get("history") or "").strip()
            if len(history) > 1200:
                history = history[:1197].rstrip() + "..."

            cand = ScraperCandidate(
                provider_id=self.provider_id,
                provider_label=self.provider_label,
                game_id=str(merged.get("game_name") or name_token),
                title=str(merged.get("title") or name_token),
                system_id=system.key,
                year=year_raw,
                manufacturer=str(merged.get("manufacturer") or ""),
                genre=str(merged.get("genre") or ""),
                players=players_val,
                rating=rating_str,
                notes=history,
                cloneof=str(merged.get("cloneof") or ""),
                match_score=1.0,
                matched_name=str(merged.get("game_name") or name_token),
                assets=assets,
                asset_variants=asset_variants,
            )
            return [cand]

        return []


# =====================================================================
# 2. LIBRETRO THUMBNAILS (thumbnails.libretro.com) — CERO API KEY
# =====================================================================
class LibretroThumbnailsProvider(BaseScraperProvider):
    """
    Descarga e indexa listados HTML de thumbnails.libretro.com una sola vez por sistema/categoría
    y empareja por coincidencia exacta o similitud limpia de título.
    """

    provider_id = "libretro"
    provider_label = "Libretro Thumbnails"

    _CATEGORY_BY_SLOT = {
        "boxart": "Named_Boxarts",
        "wheel": "Named_Logos",
    }

    def __init__(self, cache: ScraperCache):
        self.cache = cache
        self._limiter = ProviderRateLimiter(0.10)
        self._index_lock = threading.Lock()
        self._dir_indices: dict[tuple[str, str], dict[str, Any]] = {}

    def is_available(self, system: ScraperSystem, config: ScraperConfig) -> bool:
        return bool(system.libretro_dir)

    def _get_directory_index(
        self,
        libretro_dir: str,
        category: str,
        config: ScraperConfig,
        cancel_check: Callable[[], bool] | None,
    ) -> dict[str, Any]:
        cache_key = f"{libretro_dir}/{category}"
        with self._index_lock:
            existing = self._dir_indices.get((libretro_dir, category))
            if existing is not None:
                return existing

        files_list = self.cache.get("libretro_dir", cache_key, max_age_sec=86400.0 * 7)
        if not isinstance(files_list, list):
            if cancel_check and cancel_check():
                return {"files": [], "exact": {}, "buckets": {}}
            self._limiter.wait(cancel_check)
            url = f"{_LIBRETRO_BASE}/{urllib.parse.quote(libretro_dir)}/{category}/"
            try:
                html_text = http_get_text(url, timeout=max(20.0, config.timeout_sec), retries=1)
                parsed: list[str] = []
                for raw_href in _HREF_PNG_RE.findall(html_text):
                    decoded = html_lib.unescape(urllib.parse.unquote(raw_href))
                    fname = decoded.split("/")[-1].strip()
                    if fname and fname.lower().endswith(".png"):
                        parsed.append(fname)
                files_list = parsed
                self.cache.set("libretro_dir", cache_key, files_list)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    files_list = []
                    self.cache.set("libretro_dir", cache_key, files_list)
                else:
                    return {"files": [], "exact": {}, "buckets": {}}
            except Exception:
                return {"files": [], "exact": {}, "buckets": {}}

        exact_map: dict[str, str] = {}
        buckets: dict[str, list[str]] = {}
        for fname in files_list:
            stem_only = fname[:-4] if fname.lower().endswith(".png") else fname
            exact_map[stem_only.lower()] = fname
            norm = normalize_match_key(stem_only)
            if norm:
                buckets.setdefault(norm, []).append(fname)

        index_obj = {"files": files_list, "exact": exact_map, "buckets": buckets}
        with self._index_lock:
            self._dir_indices[(libretro_dir, category)] = index_obj
        return index_obj

    def _match_filenames(
        self,
        index_obj: dict[str, Any],
        stem: str,
        query: str,
        region_priority: tuple[str, ...],
        limit: int = 8,
    ) -> list[tuple[str, float]]:
        exact_map: dict[str, str] = index_obj.get("exact") or {}
        buckets: dict[str, list[str]] = index_obj.get("buckets") or {}
        if not exact_map:
            return []

        seen_files: dict[str, float] = {}

        # 1. Coincidencia exacta por stem (incluyendo región del nombre de archivo)
        for probe in (stem, _libretro_sanitize(stem), query):
            p = (probe or "").strip().lower()
            if p and p in exact_map:
                fn = exact_map[p]
                seen_files[fn] = max(seen_files.get(fn, 0.0), 1.0)

        # 2. Coincidencia exacta tras normalizar artículo + etiquetas
        norm_queries = []
        for raw_q in (query, stem):
            nq = normalize_match_key(raw_q)
            if nq and nq not in norm_queries:
                norm_queries.append(nq)

        for nq in norm_queries:
            if nq in buckets:
                for fn in buckets[nq]:
                    bonus = _score_region_bonus(_extract_region_tags(fn), region_priority)
                    seen_files[fn] = max(seen_files.get(fn, 0.0), min(0.99, 0.94 + bonus))

        # 3. Coincidencia difusa controlada si todavía faltan candidatos fuertes
        if not any(sc >= 0.90 for sc in seen_files.values()) and norm_queries:
            primary_q = norm_queries[0]
            q_len = len(primary_q)
            for norm_key, fnames in buckets.items():
                if not norm_key or abs(len(norm_key) - q_len) > max(12, q_len // 2):
                    continue
                if primary_q[0] != norm_key[0] and primary_q not in norm_key and norm_key not in primary_q:
                    continue
                sm = SequenceMatcher(None, primary_q, norm_key)
                if sm.quick_ratio() < 0.56:
                    continue
                base_ratio = sm.ratio()
                if primary_q in norm_key or norm_key in primary_q:
                    base_ratio = max(base_ratio, 0.78 if min(len(primary_q), len(norm_key)) >= 4 else base_ratio)
                if base_ratio < 0.56:
                    continue
                for fn in fnames:
                    bonus = _score_region_bonus(_extract_region_tags(fn), region_priority)
                    total = max(0.0, min(0.92, base_ratio + bonus))
                    seen_files[fn] = max(seen_files.get(fn, 0.0), total)

        ranked = sorted(seen_files.items(), key=lambda pair: (-pair[1], pair[0].lower()))
        return ranked[:limit]

    def find_candidates(
        self,
        query: str,
        stem: str,
        rom_path: str,
        system: ScraperSystem,
        config: ScraperConfig,
        target_slots: tuple[str, ...] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        max_results: int = 8,
    ) -> list[ScraperCandidate]:
        if not system.libretro_dir:
            return []

        wanted = set(target_slots or ("boxart", "wheel")) & set(self._CATEGORY_BY_SLOT.keys())
        if not wanted:
            wanted = {"boxart", "wheel"}

        by_clean_game: dict[str, ScraperCandidate] = {}

        for slot_key in ("boxart", "wheel"):
            if slot_key not in wanted:
                continue
            if cancel_check and cancel_check():
                break
            category = self._CATEGORY_BY_SLOT[slot_key]
            idx_obj = self._get_directory_index(system.libretro_dir, category, config, cancel_check)
            matches = self._match_filenames(
                idx_obj,
                stem=stem,
                query=query,
                region_priority=config.region_priority,
                limit=max_results,
            )
            for fname, score in matches:
                base_stem = fname[:-4] if fname.lower().endswith(".png") else fname
                group_key = base_stem.lower()
                url = (
                    f"{_LIBRETRO_BASE}/{urllib.parse.quote(system.libretro_dir)}/"
                    f"{category}/{urllib.parse.quote(fname)}"
                )
                asset = ScraperMediaAsset(
                    slot_key=slot_key,
                    url=url,
                    ext_hint=".png",
                    region=_extract_primary_region(base_stem),
                    media_kind="image",
                    source_type=category,
                    provider_id=self.provider_id,
                )
                if group_key not in by_clean_game:
                    by_clean_game[group_key] = ScraperCandidate(
                        provider_id=self.provider_id,
                        provider_label=self.provider_label,
                        game_id=f"{system.libretro_dir}:{base_stem}",
                        title=clean_rom_search_title(base_stem) or base_stem,
                        system_id=system.key,
                        match_score=score,
                        matched_name=base_stem,
                        assets={slot_key: asset},
                    )
                else:
                    cand = by_clean_game[group_key]
                    cand.match_score = max(cand.match_score, score)
                    cand.assets.setdefault(slot_key, asset)

        # Propagar logos y agrupar variantes regionales por título normalizado en Libretro
        variants_by_norm: dict[tuple[str, str], list[ScraperMediaAsset]] = {}
        for cand in by_clean_game.values():
            nk = normalize_match_key(cand.matched_name)
            if not nk:
                continue
            for sk, a_obj in cand.assets.items():
                lst = variants_by_norm.setdefault((nk, sk), [])
                if all(x.url != a_obj.url for x in lst):
                    lst.append(a_obj)

        for cand in by_clean_game.values():
            nk = normalize_match_key(cand.matched_name)
            for sk in ("boxart", "wheel"):
                sibs = list(variants_by_norm.get((nk, sk)) or [])
                own = cand.assets.get(sk)
                if own:
                    sibs = [own] + [x for x in sibs if x.url != own.url]
                elif sibs:
                    cand.assets[sk] = sibs[0]
                if sibs:
                    cand.asset_variants[sk] = sibs

        ranked = sorted(
            by_clean_game.values(),
            key=lambda c: (-round(c.match_score, 4), -len(c.assets), c.matched_name.lower()),
        )
        return ranked[:max_results]


def _extract_primary_region(name: str) -> str:
    tags = _extract_region_tags(name)
    for t in tags:
        if t in _REGION_ALIAS_RANK:
            return _REGION_ALIAS_RANK[t]
    return "wor"


# =====================================================================
# 3. SCREENSCRAPER API v2 (Opcional con credenciales)
# =====================================================================
class ScreenScraperAuthError(RuntimeError):
    """Error de autenticación o autorización reportado por ScreenScraper API v2."""


class ScreenScraperProvider(BaseScraperProvider):
    """Cliente oficial de API v2 (jeuInfos.php + jeuRecherche.php) para media y metadatos."""

    provider_id = "screenscraper"
    provider_label = "ScreenScraper v2"

    def __init__(self, cache: ScraperCache):
        self.cache = cache
        self._quota_lock = threading.Lock()
        self._detected_max_threads: int | None = None
        self._account_checked: bool = False
        self._sem_size: int = 4
        self._sem = threading.BoundedSemaphore(self._sem_size)

    @property
    def detected_max_threads(self) -> int | None:
        with self._quota_lock:
            return self._detected_max_threads

    def _set_max_threads(self, count: int) -> None:
        clamped = max(1, min(MAX_SCRAPER_WORKERS, int(count)))
        with self._quota_lock:
            self._detected_max_threads = clamped
            self._account_checked = True
            if clamped != self._sem_size:
                self._sem_size = clamped
                self._sem = threading.BoundedSemaphore(clamped)

    @contextlib.contextmanager
    def _acquire_slot(self, config: ScraperConfig, cancel_check: Callable[[], bool] | None = None):
        with self._quota_lock:
            if self._detected_max_threads is None:
                want = config.normalized_workers()
                if want != self._sem_size:
                    self._sem_size = want
                    self._sem = threading.BoundedSemaphore(want)
            sem = self._sem

        acquired = False
        while not acquired:
            if cancel_check and cancel_check():
                yield False
                return
            acquired = sem.acquire(timeout=0.1)
        try:
            yield not (cancel_check and cancel_check())
        finally:
            try:
                sem.release()
            except ValueError:
                pass

    def _update_quota_from_response(self, data: dict[str, Any] | None) -> None:
        if not isinstance(data, dict):
            return
        resp = data.get("response")
        if not isinstance(resp, dict):
            return
        ssuser = resp.get("ssuser")
        if not isinstance(ssuser, dict):
            return
        raw_mt = str(ssuser.get("maxthreads") or "").strip()
        if raw_mt.isdigit() and int(raw_mt) >= 1:
            self._set_max_threads(int(raw_mt))

    def fetch_user_quota(self, config: ScraperConfig) -> dict[str, Any]:
        """Consulta ssuserInfos.php y retorna los límites reales de la cuenta (maxthreads, nivel, cuota diaria)."""
        if not config.has_screenscraper_credentials:
            raise ScreenScraperAuthError(
                tr("svc.scraper.ss_err_no_creds", "Enter your ScreenScraper credentials first.")
            )
        params = self._base_params(config)
        data = self._fetch_api_json("ssuserInfos.php", params, config)
        resp = (data or {}).get("response") if isinstance(data, dict) else None
        ssuser = resp.get("ssuser") if isinstance(resp, dict) else None
        if not isinstance(ssuser, dict):
            raise RuntimeError(
                tr("svc.scraper.ss_err_quota_unavailable", "Could not retrieve account information from ScreenScraper.")
            )
        raw_mt = str(ssuser.get("maxthreads") or "1").strip()
        mt = max(1, min(MAX_SCRAPER_WORKERS, int(raw_mt) if raw_mt.isdigit() else 1))
        self._set_max_threads(mt)
        return {
            "user": str(ssuser.get("id") or config.ss_ssid or ""),
            "level": str(ssuser.get("niveau") or ""),
            "maxthreads": mt,
            "requests_today": str(ssuser.get("requeststoday") or "0"),
            "max_requests_per_day": str(ssuser.get("maxrequestsperday") or ""),
        }

    def ensure_account_limits(self, config: ScraperConfig) -> int | None:
        """Detecta una sola vez por instancia el maxthreads real de la cuenta antes de un lote."""
        with self._quota_lock:
            if self._account_checked:
                return self._detected_max_threads
        try:
            info = self.fetch_user_quota(config)
            return int(info["maxthreads"])
        except Exception:
            with self._quota_lock:
                self._account_checked = True
            return None

    def is_available(self, system: ScraperSystem, config: ScraperConfig) -> bool:
        return config.has_screenscraper_credentials

    def _base_params(self, config: ScraperConfig) -> dict[str, str]:
        params = {
            "softname": "PlayNexusFrontend",
            "output": "json",
        }
        devid = config.resolved_ss_devid()
        devpass = config.resolved_ss_devpassword()
        if devid:
            params["devid"] = devid
        if devpass:
            params["devpassword"] = devpass
        debug_pw = config.resolved_ss_devdebugpassword()
        if config.ss_debug_mode and debug_pw:
            params["devdebugpassword"] = debug_pw
        if config.ss_ssid.strip():
            params["ssid"] = config.ss_ssid.strip()
        if config.ss_sspassword.strip():
            params["sspassword"] = config.ss_sspassword.strip()
        return params

    @staticmethod
    def _explain_http_error(exc: urllib.error.HTTPError, config: ScraperConfig) -> str:
        body = ""
        try:
            raw = exc.read()
            if raw:
                body = raw.decode("utf-8", errors="ignore").strip()[:220]
        except Exception:
            body = ""
        if exc.code == 403 and not config.has_screenscraper_dev_credentials:
            return tr(
                "svc.scraper.ss_err_403_no_dev",
                "ScreenScraper rejected the request (HTTP 403) because API v2 requires an application key "
                "(devid/devpassword) in addition to username and password.",
            )
        if exc.code in (401, 403):
            detail = f" ({body})" if body else ""
            return tr(
                "svc.scraper.ss_err_creds_rejected",
                "ScreenScraper credentials rejected (HTTP {code}){detail}",
                code=exc.code,
                detail=detail,
            )
        return f"HTTP {exc.code}"

    def _fetch_api_json(
        self,
        endpoint: str,
        params: dict[str, str],
        config: ScraperConfig,
    ) -> dict[str, Any] | None:
        """Ejecuta una consulta GET contra API v2 distinguiendo errores de login en texto plano o HTTP 401/403."""
        url = f"{_SS_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
        try:
            raw_text = http_get_text(url, timeout=config.timeout_sec, retries=1)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ScreenScraperAuthError(self._explain_http_error(exc, config)) from exc
            return None
        except Exception:
            return None

        text = (raw_text or "").strip()
        if not text:
            return None

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                hdr = data.get("header")
                if isinstance(hdr, dict) and str(hdr.get("success") or "").lower() == "false":
                    err_msg = str(hdr.get("error") or "").strip()
                    low_err = err_msg.lower()
                    if any(tok in low_err for tok in ("login", "identifiant", "utilisateur", "password", "devid")):
                        raise ScreenScraperAuthError(tr("svc.scraper.ss_err_prefix", "ScreenScraper: {msg}", msg=err_msg))
                self._update_quota_from_response(data)
                return data
            return None
        except json.JSONDecodeError as exc:
            low = text.lower()
            if any(tok in low for tok in ("erreur de login", "identifiant", "utilisateur", "développeur", "forbidden")):
                if not config.has_screenscraper_dev_credentials:
                    raise ScreenScraperAuthError(
                        tr(
                            "svc.scraper.ss_err_text_no_dev",
                            "ScreenScraper rejected the request ({detail}) because API v2 requires a developer key "
                            "(devid/devpassword) in addition to username and password.",
                            detail=text[:180],
                        )
                    ) from exc
                raise ScreenScraperAuthError(
                    tr(
                        "svc.scraper.ss_err_auth",
                        "ScreenScraper authentication error: {detail}",
                        detail=text[:180],
                    )
                ) from exc
            return None

    @staticmethod
    def _pick_localized_text(items: Any, preferred_keys: tuple[str, ...], key_field: str = "region") -> str:
        if isinstance(items, dict):
            return str(items.get("text") or "").strip()
        if not isinstance(items, list):
            return ""
        for pref in preferred_keys:
            for item in items:
                if isinstance(item, dict) and str(item.get(key_field) or "").lower() == pref:
                    txt = str(item.get("text") or "").strip()
                    if txt:
                        return txt
        for item in items:
            if isinstance(item, dict):
                txt = str(item.get("text") or "").strip()
                if txt:
                    return txt
        return ""

    @staticmethod
    def _extract_genres(raw_genres: Any, lang: str) -> str:
        if not isinstance(raw_genres, list):
            return ""
        names: list[str] = []
        for g in raw_genres:
            if not isinstance(g, dict):
                continue
            val = ""
            noms = g.get("noms")
            if isinstance(noms, list):
                val = ScreenScraperProvider._pick_localized_text(noms, (lang, "en", "es"), key_field="langue")
            elif isinstance(g.get("nom"), dict):
                nom_d = g["nom"]
                val = str(nom_d.get(lang) or nom_d.get("en") or next(iter(nom_d.values()), "") or "").strip()
            if val and val not in names:
                names.append(val)
        return ", ".join(names[:3])

    def _parse_jeu_object(
        self,
        jeu: dict[str, Any],
        system: ScraperSystem,
        config: ScraperConfig,
        match_score: float,
        rom_regions: list[str] | tuple[str, ...] = (),
    ) -> ScraperCandidate:
        eff_regions = tuple(dict.fromkeys([*rom_regions, *config.region_priority]))
        title = self._pick_localized_text(
            jeu.get("noms"),
            ("ss",) + eff_regions + ("wor", "us", "eu", "jp"),
            key_field="region",
        ) or str(jeu.get("id") or tr("svc.scraper.untitled", "Untitled"))

        year_raw = self._pick_localized_text(
            jeu.get("dates"),
            eff_regions + ("wor", "us", "eu", "jp"),
            key_field="region",
        )
        year_m = re.search(r"\b(19\d{2}|20\d{2})\b", year_raw)
        year = year_m.group(1) if year_m else ""

        dev = self._pick_localized_text(jeu.get("developpeur"), ())
        pub = self._pick_localized_text(jeu.get("editeur"), ())
        manufacturer = dev or pub
        genre = self._extract_genres(jeu.get("genres"), config.language)
        players = self._pick_localized_text(jeu.get("joueurs"), ())
        notes = self._pick_localized_text(
            jeu.get("synopsis"),
            (config.language, "en", "fr"),
            key_field="langue",
        )
        raw_note = self._pick_localized_text(jeu.get("note"), ())
        rating = f"{raw_note}/20" if raw_note else ""

        medias = jeu.get("medias") if isinstance(jeu.get("medias"), list) else []
        exp_regions: list[str] = []
        for rc in eff_regions:
            if rc not in exp_regions:
                exp_regions.append(rc)
            if rc == "es" and "sp" not in exp_regions:
                exp_regions.append("sp")
            elif rc == "sp" and "es" not in exp_regions:
                exp_regions.append("es")
        region_order = exp_regions + ["ss", "wor", "us", "eu", "sp", "es", "jp", "fr", "de", "it", "br", "kr", "au", ""]

        def _region_rank(reg: str) -> int:
            r = (reg or "").lower()
            if r in region_order:
                return region_order.index(r)
            return len(region_order)

        assets: dict[str, ScraperMediaAsset] = {}
        asset_variants: dict[str, list[ScraperMediaAsset]] = {}
        for slot_key, type_prio in _SS_SLOT_TYPE_PRIORITY.items():
            if slot_key == "video":
                eff_prio: tuple[str, ...] = ("video", "video-normalized") if config.prefer_hd_video else ("video-normalized", "video")
            else:
                eff_prio = type_prio

            ranked_entries: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
            for idx_m, m in enumerate(medias):
                if not isinstance(m, dict):
                    continue
                mtype = str(m.get("type") or "")
                url = str(m.get("url") or "").strip()
                if not url or mtype not in eff_prio:
                    continue
                # En ScreenScraper el orden primario es región preferida y luego subtipo (ej. JP 2D antes que US 3D si la ROM es JP; o en el selector aparecen todas)
                reg_str = str(m.get("region") or "")
                if rom_regions and reg_str.lower() in rom_regions:
                    rank = (0, rom_regions.index(reg_str.lower()), eff_prio.index(mtype))
                else:
                    rank = (1, eff_prio.index(mtype), _region_rank(reg_str) * 100 + idx_m)
                ranked_entries.append((rank, m))

            if ranked_entries:
                ranked_entries.sort(key=lambda pair: pair[0])
                def_fmt = "mp4" if slot_key == "video" else ("pdf" if slot_key == "manual" else "png")
                kind = "video" if slot_key == "video" else ("pdf" if slot_key == "manual" else "image")
                variants_list: list[ScraperMediaAsset] = []
                seen_urls: set[str] = set()
                for _rk, m_item in ranked_entries:
                    u_clean = str(m_item["url"]).strip()
                    if u_clean in seen_urls:
                        continue
                    seen_urls.add(u_clean)
                    fmt = str(m_item.get("format") or def_fmt).lower().lstrip(".")
                    variants_list.append(
                        ScraperMediaAsset(
                            slot_key=slot_key,
                            url=u_clean,
                            ext_hint=f".{fmt}",
                            region=str(m_item.get("region") or "wor"),
                            media_kind=kind,
                            source_type=str(m_item.get("type") or ""),
                            provider_id=self.provider_id,
                        )
                    )
                if variants_list:
                    assets[slot_key] = variants_list[0]
                    asset_variants[slot_key] = variants_list

        return ScraperCandidate(
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            game_id=str(jeu.get("id") or title),
            title=title,
            system_id=system.key,
            year=year,
            manufacturer=manufacturer,
            genre=genre,
            players=players,
            rating=rating,
            notes=notes,
            match_score=match_score,
            matched_name=title,
            assets=assets,
            asset_variants=asset_variants,
        )

    @staticmethod
    def _score_jeu_names(jeu: dict[str, Any], fallback_title: str, norm_variants: list[str]) -> float:
        """Compara todas las variantes de búsqueda contra TODOS los nombres regionales ('noms') del juego."""
        if not norm_variants:
            return 0.75
        cand_names: list[str] = []
        raw_noms = jeu.get("noms")
        if isinstance(raw_noms, list):
            for item in raw_noms:
                if isinstance(item, dict):
                    txt = str(item.get("text") or "").strip()
                    if txt:
                        cand_names.append(txt)
        if fallback_title:
            cand_names.append(fallback_title)

        norm_cands: list[str] = []
        for cn in cand_names:
            for piece in [cn, *[p.strip() for sep in (" - ", " : ", ": ") if sep in cn for p in cn.split(sep) if len(p.strip()) >= 4]]:
                nk = normalize_match_key(piece)
                if nk and nk not in norm_cands:
                    norm_cands.append(nk)
        if not norm_cands:
            return 0.0

        best = 0.0
        for v_idx, nv in enumerate(norm_variants):
            penalty = 0.0 if v_idx == 0 else 0.03
            for nk in norm_cands:
                if nv == nk:
                    best = max(best, 1.0 if v_idx == 0 else 0.96)
                else:
                    ratio = SequenceMatcher(None, nv, nk).ratio()
                    if len(nv) >= 6 and (nk.startswith(nv + " ") or nk.endswith(" " + nv)):
                        ratio = max(ratio, 0.86)
                    elif len(nk) >= 6 and (nv.startswith(nk + " ") or nv.endswith(" " + nk)):
                        ratio = max(ratio, 0.86)
                    ratio -= penalty
                    if ratio > best:
                        best = ratio
        return max(0.0, min(1.0, best))

    def _query_jeu_infos_attempts(
        self,
        stem: str,
        rom_path: str,
        system: ScraperSystem,
        config: ScraperConfig,
        cancel_check: Callable[[], bool] | None,
    ) -> dict[str, Any] | None:
        ext_low = os.path.splitext(rom_path or "")[1].lower()
        romtype = "iso" if ext_low in _SS_ISO_EXTS else "rom"
        base_romnom = os.path.basename(rom_path) if rom_path else (f"{stem}.zip" if stem else "")
        hashes = compute_rom_hashes(rom_path) if (rom_path and os.path.isfile(rom_path)) else {}
        inner_zip = compute_inner_zip_rom_info(rom_path) if (not system.is_arcade and ext_low == ".zip") else {}

        cache_sig = inner_zip.get("crc") or hashes.get("crc", "")
        cache_key_info = f"info:{system.screenscraper_id}:{stem}:{cache_sig}"
        if not config.ss_debug_mode:
            cached_info = self.cache.get("screenscraper", cache_key_info, max_age_sec=86400.0 * 3)
            if isinstance(cached_info, dict) and isinstance(cached_info.get("jeu"), dict):
                return cached_info["jeu"]

        attempts: list[dict[str, str]] = []
        sys_id_str = str(system.screenscraper_id) if system.screenscraper_id else ""

        # a) En .zip de consola: probar primero CRC32 + tamaño descomprimido de la ROM interna
        if inner_zip.get("crc"):
            p_inner: dict[str, str] = {"romtype": "rom", "crc": inner_zip["crc"]}
            if sys_id_str:
                p_inner["systemeid"] = sys_id_str
            if inner_zip.get("size"):
                p_inner["romtaille"] = inner_zip["size"]
            if inner_zip.get("romnom"):
                p_inner["romnom"] = inner_zip["romnom"]
            attempts.append(p_inner)

        # b) Hashes del archivo directo en disco + romnom
        if hashes.get("crc") or base_romnom:
            p_hash: dict[str, str] = {"romtype": romtype}
            if sys_id_str:
                p_hash["systemeid"] = sys_id_str
            if hashes.get("crc"):
                p_hash["crc"] = hashes["crc"]
            if hashes.get("md5"):
                p_hash["md5"] = hashes["md5"]
            if hashes.get("sha1"):
                p_hash["sha1"] = hashes["sha1"]
            if hashes.get("size"):
                p_hash["romtaille"] = hashes["size"]
            if base_romnom:
                p_hash["romnom"] = base_romnom
            attempts.append(p_hash)

        # c) Si llevaba hashes y falló (ROM parcheada [Ting]/[Tesp] o archivo reempaquetado), reintentar limpio por romnom
        if base_romnom and (hashes.get("crc") or inner_zip.get("crc")):
            p_name: dict[str, str] = {"romtype": romtype, "romnom": base_romnom}
            if sys_id_str:
                p_name["systemeid"] = sys_id_str
            attempts.append(p_name)

        # d) Sub-sistemas Arcade (ej. Neo Geo 142) también indexados bajo Arcade/MAME (75) en ScreenScraper
        if system.is_arcade and sys_id_str and sys_id_str != "75" and base_romnom:
            attempts.append({"systemeid": "75", "romtype": romtype, "romnom": base_romnom})

        for extra_params in attempts:
            with self._acquire_slot(config, cancel_check) as ok:
                if not ok:
                    return None
                params = self._base_params(config)
                params.update(extra_params)
                data = self._fetch_api_json("jeuInfos.php", params, config)
            if isinstance(data, dict):
                resp = data.get("response")
                if isinstance(resp, dict) and isinstance(resp.get("jeu"), dict) and resp["jeu"].get("id"):
                    jeu_exact = resp["jeu"]
                    self.cache.set("screenscraper", cache_key_info, {"jeu": jeu_exact})
                    return jeu_exact
        return None

    def find_candidates(
        self,
        query: str,
        stem: str,
        rom_path: str,
        system: ScraperSystem,
        config: ScraperConfig,
        target_slots: tuple[str, ...] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        max_results: int = 8,
    ) -> list[ScraperCandidate]:
        if not self.is_available(system, config):
            return []

        results: list[ScraperCandidate] = []
        rom_regions = _infer_rom_regions(stem, rom_path)
        query_variants = build_search_query_variants(query or stem, stem)
        norm_variants = []
        for qv in query_variants:
            nk = normalize_match_key(qv)
            if nk and nk not in norm_variants:
                norm_variants.append(nk)

        # 1. Intentar lookup exacto por hash interno/externo o romnom vía jeuInfos.php
        if stem or rom_path:
            jeu_exact = self._query_jeu_infos_attempts(stem, rom_path, system, config, cancel_check)
            if isinstance(jeu_exact, dict):
                results.append(
                    self._parse_jeu_object(jeu_exact, system, config, match_score=1.0, rom_regions=rom_regions)
                )

        # 2. Búsqueda textual con soporte de subtítulos traducidos y nombres multi-región
        if query_variants and (len(results) == 0 or max_results > 3):
            seen_ids = {c.game_id for c in results}
            sys_ids_to_try = [str(system.screenscraper_id)] if system.screenscraper_id else [""]
            if system.is_arcade and system.screenscraper_id and int(system.screenscraper_id) != 75:
                sys_ids_to_try.append("75")

            for sys_id_str in sys_ids_to_try:
                for q_var in query_variants:
                    if cancel_check and cancel_check():
                        break
                    cache_key_search = f"search:{sys_id_str}:{q_var.lower()}"
                    cached_search = (
                        None
                        if config.ss_debug_mode
                        else self.cache.get("screenscraper", cache_key_search, max_age_sec=86400.0 * 3)
                    )
                    jeux_list: list[dict[str, Any]] | None = None
                    if isinstance(cached_search, dict) and isinstance(cached_search.get("jeux"), list):
                        cached_valid = [j for j in cached_search["jeux"] if isinstance(j, dict) and j.get("id")]
                        if cached_valid or len(cached_search["jeux"]) == 0:
                            jeux_list = cached_valid

                    if jeux_list is None:
                        with self._acquire_slot(config, cancel_check) as ok:
                            if not ok:
                                break
                            params = self._base_params(config)
                            params["recherche"] = q_var
                            if sys_id_str:
                                params["systemeid"] = sys_id_str
                            data = self._fetch_api_json("jeuRecherche.php", params, config)
                        if isinstance(data, dict):
                            resp = data.get("response")
                            raw_jeux = resp.get("jeux") if isinstance(resp, dict) and isinstance(resp.get("jeux"), list) else []
                            jeux_list = [j for j in raw_jeux if isinstance(j, dict) and j.get("id")]
                            self.cache.set("screenscraper", cache_key_search, {"jeux": jeux_list})
                        else:
                            jeux_list = []

                    for j in jeux_list:
                        gid = str(j.get("id") or "")
                        if gid and gid in seen_ids:
                            continue
                        cand = self._parse_jeu_object(j, system, config, match_score=0.75, rom_regions=rom_regions)
                        cand.match_score = self._score_jeu_names(j, cand.title, norm_variants)
                        results.append(cand)
                        if gid:
                            seen_ids.add(gid)
                        if len(results) >= max_results * 2:
                            break

                    if any(c.match_score >= 0.85 for c in results):
                        break
                if any(c.match_score >= 0.85 for c in results):
                    break

        results.sort(key=lambda c: (-round(c.match_score, 4), -len(c.assets), c.title.lower()))
        return results[:max_results]
