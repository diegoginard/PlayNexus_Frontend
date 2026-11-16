"""
Motor orquestador del Scraper Online (lote e interactivo) para Rom Manager.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable

from playnexus.db import APP_DIR
from playnexus.services.rom_manager import MediaRequirementSpec, RomAuditResult
from playnexus.services.scraper.cache import ScraperCache
from playnexus.services.scraper.http_utils import download_media_to_slot
from playnexus.services.scraper.models import (
    BatchScrapeSummary,
    RomScrapeOutcome,
    ScraperCandidate,
    ScraperConfig,
    ScrapeJobOptions,
)
from playnexus.services.scraper.providers import (
    ArcadeItaliaProvider,
    BaseScraperProvider,
    LibretroThumbnailsProvider,
    ScreenScraperAuthError,
    ScreenScraperProvider,
)
from playnexus.services.scraper.systems import (
    ScraperSystem,
    clean_rom_search_title,
    get_system_by_key,
)


_AUTO_BATCH_MIN_SCORE = 0.72


class CompositeScraperEngine:
    """Coordina proveedores múltiples compartiendo índices cacheados y limitadores de tasa."""

    def __init__(self, config: ScraperConfig, root_dir: Path | None = None):
        self.config = config
        self.cache = ScraperCache(root_dir=root_dir or APP_DIR, enabled=config.cache_enabled)
        self.providers: dict[str, BaseScraperProvider] = {
            "arcadedb": ArcadeItaliaProvider(self.cache),
            "libretro": LibretroThumbnailsProvider(self.cache),
            "screenscraper": ScreenScraperProvider(self.cache),
        }

    def provider_order(self, system: ScraperSystem, mode: str | None = None) -> list[BaseScraperProvider]:
        chosen = (mode or self.config.preferred_provider or "auto").strip().lower()
        if chosen in self.providers:
            p = self.providers[chosen]
            return [p] if (chosen == "libretro" or p.is_available(system, self.config)) else [p]

        order: list[str] = []
        if system.is_arcade:
            order.append("arcadedb")
        if self.config.has_screenscraper_credentials:
            order.append("screenscraper")
        order.append("libretro")
        return [self.providers[pid] for pid in order if self.providers[pid].is_available(system, self.config)]

    def search_candidates(
        self,
        query: str,
        stem: str,
        rom_path: str,
        system_key: str,
        provider_mode: str = "auto",
        target_slots: tuple[str, ...] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        max_per_provider: int = 8,
    ) -> list[ScraperCandidate]:
        """Busca candidatos en uno o varios proveedores para selección interactiva del usuario."""
        system = get_system_by_key(system_key)
        all_candidates: list[ScraperCandidate] = []
        for provider in self.provider_order(system, provider_mode):
            if cancel_check and cancel_check():
                break
            try:
                found = provider.find_candidates(
                    query=query,
                    stem=stem,
                    rom_path=rom_path,
                    system=system,
                    config=self.config,
                    target_slots=target_slots,
                    cancel_check=cancel_check,
                    max_results=max_per_provider,
                )
                all_candidates.extend(found)
            except ScreenScraperAuthError:
                if (provider_mode or self.config.preferred_provider or "").strip().lower() == "screenscraper":
                    raise
                continue
            except Exception:
                continue
        return all_candidates

    @staticmethod
    def build_metadata_updates(
        game_row: dict[str, Any] | None,
        candidate: ScraperCandidate,
        update_empty: bool,
        overwrite: bool,
    ) -> dict[str, str]:
        """Calcula qué campos de metadata en db.update_game deben completarse."""
        if not update_empty and not overwrite:
            return {}
        existing = game_row or {}
        incoming = {
            "year": candidate.year,
            "manufacturer": candidate.manufacturer,
            "genre": candidate.genre,
            "players": candidate.players,
            "rating": candidate.rating,
            "notes": candidate.notes,
            "cloneof": candidate.cloneof,
        }
        updates: dict[str, str] = {}
        for field_name, val in incoming.items():
            clean_val = str(val or "").strip()
            if not clean_val:
                continue
            cur_val = str(existing.get(field_name) or "").strip()
            if overwrite or not cur_val:
                updates[field_name] = clean_val
        return updates

    def download_candidate_slots(
        self,
        candidate: ScraperCandidate,
        stem: str,
        specs_by_key: dict[str, MediaRequirementSpec],
        slot_keys: list[str] | tuple[str, ...],
        overwrite: bool = True,
        cancel_check: Callable[[], bool] | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Descarga los slots elegidos de un candidato puntual a sus carpetas de layout."""
        downloaded: dict[str, str] = {}
        failed: dict[str, str] = {}
        for key in slot_keys:
            if cancel_check and cancel_check():
                failed[key] = "Cancelado"
                continue
            spec = specs_by_key.get(key)
            asset = candidate.assets.get(key)
            if not spec:
                failed[key] = "Slot no declarado en el layout"
                continue
            if not spec.folder_exists:
                failed[key] = "Carpeta no configurada o inexistente"
                continue
            if not asset or not asset.url:
                failed[key] = "No disponible en este candidato"
                continue

            saved_path, msg = download_media_to_slot(
                url=asset.url,
                target_folder=spec.folder_path,
                target_stem=stem,
                allowed_exts=spec.extensions,
                media_kind=spec.media_kind,
                overwrite=overwrite,
                timeout=max(self.config.timeout_sec, 30.0 if spec.media_kind == "video" else self.config.timeout_sec),
                fallback_ext=asset.ext_hint,
                cancel_check=cancel_check,
            )
            if saved_path:
                downloaded[key] = saved_path
            else:
                failed[key] = msg or "Error de descarga"
        return downloaded, failed

    def scrape_rom(
        self,
        rom: RomAuditResult,
        game_row: dict[str, Any] | None,
        specs_by_key: dict[str, MediaRequirementSpec],
        options: ScrapeJobOptions,
        cancel_check: Callable[[], bool] | None = None,
    ) -> RomScrapeOutcome:
        """Busca y descarga los slots faltantes para una ROM siguiendo prioridades de proveedores."""
        if cancel_check and cancel_check():
            return RomScrapeOutcome(game_id=rom.game_id, title=rom.title, stem=rom.stem, status="cancelled")

        if rom.is_menu_target or not rom.stem:
            return RomScrapeOutcome(
                game_id=rom.game_id,
                title=rom.title,
                stem=rom.stem,
                status="skipped",
                message="Ítem sin nombre base de ROM",
            )

        needed_slots: list[str] = []
        skipped_reasons: dict[str, str] = {}
        for key in options.target_slots:
            spec = specs_by_key.get(key)
            if not spec or not spec.folder_exists:
                if spec and not spec.folder_exists:
                    skipped_reasons[key] = "Carpeta sin configurar"
                continue
            cur_slot = rom.slots.get(key)
            has_valid = bool(cur_slot and cur_slot.status == "ok")
            if has_valid and not options.overwrite_existing:
                continue
            needed_slots.append(key)

        if not needed_slots:
            return RomScrapeOutcome(
                game_id=rom.game_id,
                title=rom.title,
                stem=rom.stem,
                status="skipped",
                failed_slots=skipped_reasons,
                message="Sin slots pendientes para descargar",
            )

        system = get_system_by_key(options.system_key)
        query = clean_rom_search_title(rom.title or rom.stem)
        providers = self.provider_order(system, options.provider_mode)

        best_candidate: ScraperCandidate | None = None
        merged_assets: dict[str, Any] = {}
        matched_providers: list[str] = []

        for prov in providers:
            if cancel_check and cancel_check():
                return RomScrapeOutcome(game_id=rom.game_id, title=rom.title, stem=rom.stem, status="cancelled")

            remaining = [k for k in needed_slots if k not in merged_assets]
            if not remaining and best_candidate is not None:
                break

            effective_query = query
            if best_candidate and best_candidate.title:
                cand_q = clean_rom_search_title(best_candidate.title)
                if cand_q:
                    effective_query = cand_q

            try:
                cands = prov.find_candidates(
                    query=effective_query,
                    stem=rom.stem,
                    rom_path=rom.rom_path,
                    system=system,
                    config=self.config,
                    target_slots=tuple(remaining or needed_slots),
                    cancel_check=cancel_check,
                    max_results=3,
                )
            except ScreenScraperAuthError as auth_exc:
                if options.provider_mode == "screenscraper":
                    return RomScrapeOutcome(
                        game_id=rom.game_id,
                        title=rom.title,
                        stem=rom.stem,
                        status="error",
                        message=str(auth_exc),
                    )
                cands = []
            except Exception:
                cands = []

            if not cands:
                continue

            top = cands[0]
            if top.match_score < _AUTO_BATCH_MIN_SCORE:
                continue

            if best_candidate is None:
                best_candidate = top
            else:
                # Enriquecer metadata del primer candidato si algún campo faltaba
                for fld in ("year", "manufacturer", "genre", "players", "rating", "notes", "cloneof"):
                    if not getattr(best_candidate, fld) and getattr(top, fld):
                        setattr(best_candidate, fld, getattr(top, fld))

            if prov.provider_label not in matched_providers:
                matched_providers.append(prov.provider_label)

            for k in remaining:
                if k in top.assets and k not in merged_assets:
                    merged_assets[k] = top.assets[k]

        if best_candidate is None and not merged_assets:
            return RomScrapeOutcome(
                game_id=rom.game_id,
                title=rom.title,
                stem=rom.stem,
                status="not_found",
                message="Sin coincidencias confiables online",
            )

        best_candidate.assets.update(merged_assets)
        downloaded, failed = self.download_candidate_slots(
            candidate=best_candidate,
            stem=rom.stem,
            specs_by_key=specs_by_key,
            slot_keys=needed_slots,
            overwrite=options.overwrite_existing,
            cancel_check=cancel_check,
        )
        failed.update(skipped_reasons)

        meta_updates = self.build_metadata_updates(
            game_row=game_row,
            candidate=best_candidate,
            update_empty=options.update_empty_metadata,
            overwrite=options.overwrite_metadata,
        )

        if downloaded:
            status = "downloaded" if len(downloaded) == len(needed_slots) else "partial"
            msg = f"Descargados: {', '.join(downloaded.keys())}"
        elif failed:
            status = "not_found" if all("No disponible" in v for v in failed.values()) else "partial"
            msg = "; ".join(f"{k}: {v}" for k, v in list(failed.items())[:2])
        else:
            status = "not_found"
            msg = "Sin archivos compatibles para los slots elegidos"

        return RomScrapeOutcome(
            game_id=rom.game_id,
            title=rom.title,
            stem=rom.stem,
            status=status,
            downloaded_slots=downloaded,
            failed_slots=failed,
            metadata_updates=meta_updates,
            provider_used=" + ".join(matched_providers),
            matched_title=best_candidate.title if best_candidate else "",
            message=msg,
        )

    def run_batch(
        self,
        roms: list[RomAuditResult],
        games_by_id: dict[int, dict[str, Any]],
        specs: list[MediaRequirementSpec],
        options: ScrapeJobOptions,
        on_rom_done: Callable[[RomScrapeOutcome, int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> BatchScrapeSummary:
        """Ejecuta el scraping en lote respetando cancelaciones y concurrencia segura."""
        specs_by_key = {s.key: s for s in specs}
        summary = BatchScrapeSummary(total_targets=len(roms))
        if not roms:
            return summary

        workers = max(1, min(4, int(options.max_workers or self.config.normalized_workers())))
        # Respetar límites de API si ScreenScraper es la fuente principal
        if options.provider_mode == "screenscraper":
            workers = 1

        total = len(roms)
        if workers == 1:
            for item in roms:
                if cancel_check and cancel_check():
                    summary.cancelled = True
                    break
                outcome = self.scrape_rom(
                    rom=item,
                    game_row=games_by_id.get(item.game_id),
                    specs_by_key=specs_by_key,
                    options=options,
                    cancel_check=cancel_check,
                )
                self._accumulate_outcome(summary, outcome)
                if on_rom_done:
                    on_rom_done(outcome, summary.processed, total)
            return summary

        # Precalentar índices compartidos en caché si Libretro participa en modo paralelo
        system = get_system_by_key(options.system_key)
        libretro = self.providers.get("libretro")
        if isinstance(libretro, LibretroThumbnailsProvider) and system.libretro_dir and options.provider_mode in ("auto", "libretro"):
            for slot_k in ("boxart", "wheel"):
                if cancel_check and cancel_check():
                    summary.cancelled = True
                    return summary
                if slot_k in options.target_slots:
                    cat = libretro._CATEGORY_BY_SLOT[slot_k]
                    libretro._get_directory_index(system.libretro_dir, cat, self.config, cancel_check)

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="PlayNexusScraper") as pool:
            pending: set[Future[RomScrapeOutcome]] = set()
            rom_iter = iter(roms)

            # Encolar inicialmente solo un lote controlado para poder cancelar sin esperar toda la cola
            for _ in range(min(total, workers * 2)):
                try:
                    item = next(rom_iter)
                except StopIteration:
                    break
                pending.add(
                    pool.submit(
                        self.scrape_rom,
                        item,
                        games_by_id.get(item.game_id),
                        specs_by_key,
                        options,
                        cancel_check,
                    )
                )

            while pending:
                if cancel_check and cancel_check():
                    summary.cancelled = True
                    for fut in pending:
                        fut.cancel()
                    break

                done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                for fut in done:
                    try:
                        outcome = fut.result()
                    except Exception as exc:
                        outcome = RomScrapeOutcome(
                            game_id=0,
                            title="",
                            stem="",
                            status="error",
                            message=str(exc),
                        )
                    self._accumulate_outcome(summary, outcome)
                    if on_rom_done:
                        on_rom_done(outcome, summary.processed, total)

                    if not (cancel_check and cancel_check()):
                        try:
                            nxt = next(rom_iter)
                            pending.add(
                                pool.submit(
                                    self.scrape_rom,
                                    nxt,
                                    games_by_id.get(nxt.game_id),
                                    specs_by_key,
                                    options,
                                    cancel_check,
                                )
                            )
                        except StopIteration:
                            pass

        return summary

    @staticmethod
    def _accumulate_outcome(summary: BatchScrapeSummary, outcome: RomScrapeOutcome) -> None:
        summary.outcomes.append(outcome)
        summary.processed += 1
        summary.files_saved += len(outcome.downloaded_slots)
        if outcome.metadata_updates:
            summary.metadata_enriched += 1
        if outcome.status == "downloaded":
            summary.downloaded_roms += 1
        elif outcome.status == "partial":
            summary.partial_roms += 1
        elif outcome.status == "not_found":
            summary.not_found_roms += 1
        elif outcome.status == "skipped":
            summary.skipped_roms += 1
        elif outcome.status == "cancelled":
            summary.cancelled = True
        else:
            summary.error_roms += 1
