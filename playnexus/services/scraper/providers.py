"""
Proveedores online del Scraper de PlayNexus:
  1. ArcadeItaliaProvider  -> ADB (MAME / Arcade completo: video MP4, wheel, flyer, cabinet, marquee, bezel, metadata)
  2. LibretroThumbnailsProvider -> CDN Thumbnails (Gratis, sin API key: Boxart & Wheel/Logos para ~127 consolas)
  3. ScreenScraperProvider -> API v2 oficial (hashes CRC/MD5/SHA1 + búsqueda: toda la media + sinopsis/metadatos)
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import threading
import urllib.error
import urllib.parse
from difflib import SequenceMatcher
from typing import Any, Callable

from playnexus.services.scraper.cache import ScraperCache
from playnexus.services.scraper.http_utils import (
    ProviderRateLimiter,
    compute_rom_hashes,
    http_get_json,
    http_get_text,
)
from playnexus.services.scraper.models import (
    ScraperCandidate,
    ScraperConfig,
    ScraperMediaAsset,
)
from playnexus.services.scraper.systems import (
    ScraperSystem,
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
    "boxart": ("box-3D", "box-2D", "box-2D-front"),
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
                    assets[slot_k] = ScraperMediaAsset(
                        slot_key=slot_k,
                        url=u,
                        ext_hint=ext_h,
                        region="wor",
                        media_kind="image",
                        source_type=field_name,
                        provider_id=self.provider_id,
                    )

            vid_url = ""
            vid_type = ""
            if config.prefer_hd_video and merged.get("url_video_shortplay_hd"):
                vid_url = str(merged.get("url_video_shortplay_hd") or "").strip()
                vid_type = "url_video_shortplay_hd"
            elif merged.get("url_video_shortplay"):
                vid_url = str(merged.get("url_video_shortplay") or "").strip()
                vid_type = "url_video_shortplay"
            if vid_url:
                assets["video"] = ScraperMediaAsset(
                    slot_key="video",
                    url=vid_url,
                    ext_hint=".mp4",
                    region="wor",
                    media_kind="video",
                    source_type=vid_type,
                    provider_id=self.provider_id,
                )

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

        # Propagar logos coincidentes hacia boxarts con el mismo título normalizado (para candidatos completos)
        logo_by_norm: dict[str, ScraperMediaAsset] = {}
        for cand in by_clean_game.values():
            if "wheel" in cand.assets:
                nk = normalize_match_key(cand.matched_name)
                if nk and nk not in logo_by_norm:
                    logo_by_norm[nk] = cand.assets["wheel"]

        for cand in by_clean_game.values():
            if "wheel" not in cand.assets:
                nk = normalize_match_key(cand.matched_name)
                if nk in logo_by_norm:
                    cand.assets["wheel"] = logo_by_norm[nk]

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
        self._limiter = ProviderRateLimiter(0.95)

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
            return (
                "ScreenScraper rechazó la solicitud (HTTP 403) porque la API v2 exige una clave "
                "de aplicación (devid/devpassword) además del usuario y contraseña."
            )
        if exc.code in (401, 403):
            detail = f" ({body})" if body else ""
            return f"Credenciales de ScreenScraper rechazadas (HTTP {exc.code}){detail}"
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
                        raise ScreenScraperAuthError(f"ScreenScraper: {err_msg}")
                return data
            return None
        except json.JSONDecodeError as exc:
            low = text.lower()
            if any(tok in low for tok in ("erreur de login", "identifiant", "utilisateur", "développeur", "forbidden")):
                if not config.has_screenscraper_dev_credentials:
                    raise ScreenScraperAuthError(
                        f"ScreenScraper rechazó la solicitud ({text[:180]}) porque la API v2 exige "
                        "clave de desarrollador (devid/devpassword) además del usuario y contraseña."
                    ) from exc
                raise ScreenScraperAuthError(f"Error de autenticación en ScreenScraper: {text[:180]}") from exc
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
    ) -> ScraperCandidate:
        title = self._pick_localized_text(
            jeu.get("noms"),
            ("ss",) + tuple(config.region_priority) + ("wor", "us", "eu", "jp"),
            key_field="region",
        ) or str(jeu.get("id") or "Sin título")

        year_raw = self._pick_localized_text(
            jeu.get("dates"),
            tuple(config.region_priority) + ("wor", "us", "eu", "jp"),
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
        region_order = list(config.region_priority) + ["ss", "wor", "us", "eu", "es", "jp", ""]

        def _region_rank(reg: str) -> int:
            r = (reg or "").lower()
            if r in region_order:
                return region_order.index(r)
            return len(region_order)

        assets: dict[str, ScraperMediaAsset] = {}
        for slot_key, type_prio in _SS_SLOT_TYPE_PRIORITY.items():
            best_media: dict[str, Any] | None = None
            best_rank: tuple[int, int] | None = None
            for m in medias:
                if not isinstance(m, dict):
                    continue
                mtype = str(m.get("type") or "")
                url = str(m.get("url") or "").strip()
                if not url or mtype not in type_prio:
                    continue
                rank = (type_prio.index(mtype), _region_rank(str(m.get("region") or "")))
                if best_rank is None or rank < best_rank:
                    best_rank = rank
                    best_media = m

            if best_media:
                def_fmt = "mp4" if slot_key == "video" else ("pdf" if slot_key == "manual" else "png")
                fmt = str(best_media.get("format") or def_fmt).lower().lstrip(".")
                kind = "video" if slot_key == "video" else ("pdf" if slot_key == "manual" else "image")
                assets[slot_key] = ScraperMediaAsset(
                    slot_key=slot_key,
                    url=str(best_media["url"]).strip(),
                    ext_hint=f".{fmt}",
                    region=str(best_media.get("region") or "wor"),
                    media_kind=kind,
                    source_type=str(best_media.get("type") or ""),
                    provider_id=self.provider_id,
                )

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
        )

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
        clean_q = clean_rom_search_title(query or stem)

        # 1. Intentar lookup exacto por hash/nombre vía jeuInfos.php
        hashes = compute_rom_hashes(rom_path) if (rom_path and os.path.isfile(rom_path)) else {}
        cache_key_info = f"info:{system.screenscraper_id}:{stem}:{hashes.get('crc', '')}"
        cached_info = self.cache.get("screenscraper", cache_key_info, max_age_sec=86400.0 * 3)

        jeu_exact = None
        if isinstance(cached_info, dict) and "jeu" in cached_info:
            jeu_exact = cached_info.get("jeu")
        elif stem or hashes.get("crc"):
            if self._limiter.wait(cancel_check):
                params = self._base_params(config)
                if system.screenscraper_id:
                    params["systemeid"] = str(system.screenscraper_id)
                ext_low = os.path.splitext(rom_path or "")[1].lower()
                params["romtype"] = "iso" if ext_low in _SS_ISO_EXTS else "rom"
                if hashes.get("crc"):
                    params["crc"] = hashes["crc"]
                if hashes.get("md5"):
                    params["md5"] = hashes["md5"]
                if hashes.get("sha1"):
                    params["sha1"] = hashes["sha1"]
                if hashes.get("size"):
                    params["romtaille"] = hashes["size"]
                if rom_path:
                    params["romnom"] = os.path.basename(rom_path)
                elif stem:
                    params["romnom"] = f"{stem}.zip"
                data = self._fetch_api_json("jeuInfos.php", params, config)
                if isinstance(data, dict):
                    resp = data.get("response")
                    if isinstance(resp, dict) and isinstance(resp.get("jeu"), dict):
                        jeu_exact = resp["jeu"]
                    self.cache.set("screenscraper", cache_key_info, {"jeu": jeu_exact})

        if isinstance(jeu_exact, dict):
            results.append(self._parse_jeu_object(jeu_exact, system, config, match_score=1.0))

        # 2. Búsqueda textual (si faltan candidatos o si no hubo hash match)
        if clean_q and (len(results) == 0 or max_results > 1):
            cache_key_search = f"search:{system.screenscraper_id}:{clean_q.lower()}"
            cached_search = self.cache.get("screenscraper", cache_key_search, max_age_sec=86400.0 * 3)
            jeux_list = None
            if isinstance(cached_search, dict) and isinstance(cached_search.get("jeux"), list):
                jeux_list = cached_search["jeux"]
            elif self._limiter.wait(cancel_check):
                params = self._base_params(config)
                params["recherche"] = clean_q
                if system.screenscraper_id:
                    params["systemeid"] = str(system.screenscraper_id)
                data = self._fetch_api_json("jeuRecherche.php", params, config)
                if isinstance(data, dict):
                    resp = data.get("response")
                    if isinstance(resp, dict) and isinstance(resp.get("jeux"), list):
                        jeux_list = resp["jeux"]
                    else:
                        jeux_list = []
                    self.cache.set("screenscraper", cache_key_search, {"jeux": jeux_list})
                else:
                    jeux_list = []

            seen_ids = {c.game_id for c in results}
            norm_target = normalize_match_key(clean_q)
            for j in jeux_list or []:
                if not isinstance(j, dict):
                    continue
                gid = str(j.get("id") or "")
                if gid and gid in seen_ids:
                    continue
                cand = self._parse_jeu_object(j, system, config, match_score=0.75)
                nk = normalize_match_key(cand.title)
                if norm_target and nk:
                    cand.match_score = SequenceMatcher(None, norm_target, nk).ratio()
                results.append(cand)
                if gid:
                    seen_ids.add(gid)
                if len(results) >= max_results:
                    break

        results.sort(key=lambda c: (-round(c.match_score, 4), -len(c.assets), c.title.lower()))
        return results[:max_results]
