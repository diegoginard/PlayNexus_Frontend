"""
Paquete del Scraper Online integrado al Rom Manager de PlayNexus.
"""
from playnexus.services.scraper.cache import (
    ScraperCache,
    clear_scraper_cache,
    get_scraper_cache_stats,
)
from playnexus.services.scraper.engine import CompositeScraperEngine
from playnexus.services.scraper.models import (
    BatchScrapeSummary,
    DEFAULT_REGION_PRIORITY,
    RomScrapeOutcome,
    ScrapeJobOptions,
    ScraperCandidate,
    ScraperConfig,
    ScraperMediaAsset,
    load_scraper_config,
    save_scraper_config,
)
from playnexus.services.scraper.systems import (
    SYSTEM_CATALOG,
    ScraperSystem,
    clean_rom_search_title,
    detect_system_for_list,
    get_system_by_key,
    normalize_match_key,
)

__all__ = [
    "BatchScrapeSummary",
    "CompositeScraperEngine",
    "DEFAULT_REGION_PRIORITY",
    "RomScrapeOutcome",
    "SYSTEM_CATALOG",
    "ScrapeJobOptions",
    "ScraperCache",
    "ScraperCandidate",
    "ScraperConfig",
    "ScraperMediaAsset",
    "ScraperSystem",
    "clean_rom_search_title",
    "clear_scraper_cache",
    "detect_system_for_list",
    "get_scraper_cache_stats",
    "get_system_by_key",
    "load_scraper_config",
    "normalize_match_key",
    "save_scraper_config",
]
