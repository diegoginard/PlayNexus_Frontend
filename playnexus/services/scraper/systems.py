"""
Catálogo de sistemas, resolución automática por lista/layout y normalización de títulos de ROMs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_TAG_RE = re.compile(r"\s*[\(\[].*?[\)\]]")
_DISC_RE = re.compile(r"\b(?:disc|disk|cd)\s*\d+\b", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ScraperSystem:
    """Definición de plataforma para mapear PlayNexus -> Libretro / ScreenScraper / ArcadeDB."""

    key: str
    display_name: str
    screenscraper_id: int | None
    libretro_dir: str
    aliases: tuple[str, ...]
    is_arcade: bool = False


SYSTEM_CATALOG: tuple[ScraperSystem, ...] = (
    ScraperSystem(
        key="arcade",
        display_name="Arcade / MAME",
        screenscraper_id=75,
        libretro_dir="MAME",
        aliases=("at-the-arcade", "arcade", "mame", "cps1", "cps2", "cps3"),
        is_arcade=True,
    ),
    ScraperSystem(
        key="fbneo",
        display_name="FinalBurn Neo (Arcade)",
        screenscraper_id=75,
        libretro_dir="FBNeo - Arcade Games",
        aliases=("fbneo", "finalburn", "fba"),
        is_arcade=True,
    ),
    ScraperSystem(
        key="neogeo",
        display_name="SNK Neo Geo",
        screenscraper_id=142,
        libretro_dir="SNK - Neo Geo",
        aliases=("neo geo", "neogeo", "neo-geo"),
        is_arcade=True,
    ),
    ScraperSystem(
        key="jaguarcd",
        display_name="Atari Jaguar CD",
        screenscraper_id=171,
        libretro_dir="Atari - Jaguar",
        aliases=("atari jaguar cd", "jaguar cd", "jaguarcd"),
    ),
    ScraperSystem(
        key="jaguar",
        display_name="Atari Jaguar",
        screenscraper_id=27,
        libretro_dir="Atari - Jaguar",
        aliases=("atari jaguar", "jaguar"),
    ),
    ScraperSystem(
        key="pcfx",
        display_name="NEC PC-FX",
        screenscraper_id=72,
        libretro_dir="NEC - PC-FX",
        aliases=("nec pc-fx", "pc-fx", "pcfx"),
    ),
    ScraperSystem(
        key="tgcd",
        display_name="NEC TurboGrafx-CD / PC Engine CD",
        screenscraper_id=114,
        libretro_dir="NEC - PC Engine CD - TurboGrafx-CD",
        aliases=("turbografx-cd", "turbografx cd", "pc engine cd", "pcecd", "pce-cd"),
    ),
    ScraperSystem(
        key="tg16",
        display_name="NEC TurboGrafx-16 / PC Engine",
        screenscraper_id=31,
        libretro_dir="NEC - PC Engine - TurboGrafx 16",
        aliases=("turbografx-16", "turbografx 16", "turbografx", "tg16", "pc engine", "pce"),
    ),
    ScraperSystem(
        key="snes",
        display_name="Super Nintendo (SNES)",
        screenscraper_id=4,
        libretro_dir="Nintendo - Super Nintendo Entertainment System",
        aliases=("super nintendo", "snes", "super famicom", "sfc"),
    ),
    ScraperSystem(
        key="nes",
        display_name="Nintendo Entertainment System (NES)",
        screenscraper_id=3,
        libretro_dir="Nintendo - Nintendo Entertainment System",
        aliases=("nintendo entertainment system", "nes", "famicom"),
    ),
    ScraperSystem(
        key="n64",
        display_name="Nintendo 64 (N64)",
        screenscraper_id=14,
        libretro_dir="Nintendo - Nintendo 64",
        aliases=("nintendo 64", "n64"),
    ),
    ScraperSystem(
        key="gamecube",
        display_name="Nintendo GameCube",
        screenscraper_id=13,
        libretro_dir="Nintendo - GameCube",
        aliases=("gamecube", "game cube", "ngc", "gc"),
    ),
    ScraperSystem(
        key="wii",
        display_name="Nintendo Wii",
        screenscraper_id=16,
        libretro_dir="Nintendo - Wii",
        aliases=("nintendo wii", "wii"),
    ),
    ScraperSystem(
        key="gba",
        display_name="Nintendo Game Boy Advance",
        screenscraper_id=12,
        libretro_dir="Nintendo - Game Boy Advance",
        aliases=("game boy advance", "gameboy advance", "gba"),
    ),
    ScraperSystem(
        key="gbc",
        display_name="Nintendo Game Boy Color",
        screenscraper_id=10,
        libretro_dir="Nintendo - Game Boy Color",
        aliases=("game boy color", "gameboy color", "gbc"),
    ),
    ScraperSystem(
        key="gb",
        display_name="Nintendo Game Boy",
        screenscraper_id=9,
        libretro_dir="Nintendo - Game Boy",
        aliases=("game boy", "gameboy", "dmg"),
    ),
    ScraperSystem(
        key="nds",
        display_name="Nintendo DS",
        screenscraper_id=15,
        libretro_dir="Nintendo - Nintendo DS",
        aliases=("nintendo ds", "nds"),
    ),
    ScraperSystem(
        key="virtualboy",
        display_name="Nintendo Virtual Boy",
        screenscraper_id=11,
        libretro_dir="Nintendo - Virtual Boy",
        aliases=("virtual boy", "virtualboy", "vboy"),
    ),
    ScraperSystem(
        key="sega32x",
        display_name="Sega 32X",
        screenscraper_id=19,
        libretro_dir="Sega - 32X",
        aliases=("sega 32x", "32x", "megadrive 32x", "mega drive 32x"),
    ),
    ScraperSystem(
        key="segacd",
        display_name="Sega CD / Mega-CD",
        screenscraper_id=20,
        libretro_dir="Sega - Mega-CD - Sega CD",
        aliases=("sega cd", "segacd", "mega-cd", "mega cd", "megacd"),
    ),
    ScraperSystem(
        key="genesis",
        display_name="Sega Genesis / Mega Drive",
        screenscraper_id=1,
        libretro_dir="Sega - Mega Drive - Genesis",
        aliases=("sega genesis", "genesis", "mega drive", "megadrive"),
    ),
    ScraperSystem(
        key="mastersystem",
        display_name="Sega Master System",
        screenscraper_id=2,
        libretro_dir="Sega - Master System - Mark III",
        aliases=("master system", "mastersystem", "sms"),
    ),
    ScraperSystem(
        key="gamegear",
        display_name="Sega Game Gear",
        screenscraper_id=21,
        libretro_dir="Sega - Game Gear",
        aliases=("game gear", "gamegear"),
    ),
    ScraperSystem(
        key="saturn",
        display_name="Sega Saturn",
        screenscraper_id=22,
        libretro_dir="Sega - Saturn",
        aliases=("sega saturn", "saturn"),
    ),
    ScraperSystem(
        key="dreamcast",
        display_name="Sega Dreamcast",
        screenscraper_id=23,
        libretro_dir="Sega - Dreamcast",
        aliases=("dreamcast", "sega dreamcast"),
    ),
    ScraperSystem(
        key="psp",
        display_name="Sony PlayStation Portable (PSP)",
        screenscraper_id=61,
        libretro_dir="Sony - PlayStation Portable",
        aliases=("playstation portable", "sony psp", "psp"),
    ),
    ScraperSystem(
        key="ps2",
        display_name="Sony PlayStation 2",
        screenscraper_id=58,
        libretro_dir="Sony - PlayStation 2",
        aliases=("playstation 2", "sony ps2", "ps2", "psx2"),
    ),
    ScraperSystem(
        key="ps1",
        display_name="Sony PlayStation",
        screenscraper_id=57,
        libretro_dir="Sony - PlayStation",
        aliases=("sony playstation", "playstation", "ps1", "psx"),
    ),
    ScraperSystem(
        key="atari2600",
        display_name="Atari 2600",
        screenscraper_id=26,
        libretro_dir="Atari - 2600",
        aliases=("atari 2600", "2600", "vcs"),
    ),
)

_SYSTEMS_BY_KEY: dict[str, ScraperSystem] = {s.key: s for s in SYSTEM_CATALOG}


def get_system_by_key(key: str | None) -> ScraperSystem:
    """Obtiene una definición del catálogo por clave (o Arcade por defecto)."""
    k = (key or "").strip().lower()
    return _SYSTEMS_BY_KEY.get(k, _SYSTEMS_BY_KEY["snes"])


def detect_system_for_list(
    list_row: dict[str, Any] | None,
    layout_name: str = "",
    emulator_row: dict[str, Any] | None = None,
) -> ScraperSystem:
    """
    Detecta el sistema más probable combinando plataforma de la lista, nombre de lista,
    layout auditado y plataforma del emulador predeterminado.
    Evalúa alias más específicos primero para evitar colisiones (ej: Jaguar CD vs Jaguar,
    Game Boy Advance vs Game Boy, PlayStation Portable vs PlayStation).
    """
    candidates: list[str] = []
    if list_row:
        candidates.append(str(list_row.get("platform") or ""))
        candidates.append(str(list_row.get("name") or ""))
    if layout_name:
        candidates.append(layout_name)
    if emulator_row:
        candidates.append(str(emulator_row.get("platform") or ""))
        candidates.append(str(emulator_row.get("name") or ""))

    ordered_aliases: list[tuple[str, ScraperSystem]] = []
    for sys_obj in SYSTEM_CATALOG:
        for alias in sys_obj.aliases:
            ordered_aliases.append((alias.lower(), sys_obj))
    ordered_aliases.sort(key=lambda pair: -len(pair[0]))

    for source_text in candidates:
        low = source_text.strip().lower()
        if not low:
            continue
        for alias, sys_obj in ordered_aliases:
            if alias == low:
                return sys_obj
        for alias, sys_obj in ordered_aliases:
            if len(alias) >= 4 and alias in low:
                return sys_obj
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, low):
                return sys_obj

    return _SYSTEMS_BY_KEY["arcade"] if "arcade" in (layout_name or "").lower() else _SYSTEMS_BY_KEY["snes"]


def clean_rom_search_title(text: str) -> str:
    """Limpia etiquetas de región/revisión/disco de un nombre de ROM para búsquedas legibles."""
    if not text:
        return ""
    s = _TAG_RE.sub(" ", text)
    s = _DISC_RE.sub(" ", s)
    s = s.replace("_", " ").replace(".", " ")
    s = _SPACE_RE.sub(" ", s).strip(" -_")
    if s.lower().endswith(", the"):
        s = "The " + s[:-5].strip()
    elif s.lower().endswith(", a"):
        s = "A " + s[:-3].strip()
    return _SPACE_RE.sub(" ", s).strip()


def normalize_match_key(text: str) -> str:
    """Clave canónica alfanumérica sin artículos/regiones para emparejar nombres."""
    cleaned = clean_rom_search_title(text).lower()
    if cleaned.startswith("the "):
        cleaned = cleaned[4:]
    return _PUNCT_RE.sub(" ", cleaned).strip()
