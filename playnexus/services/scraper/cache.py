"""
Caché persistente local en JSON para respuestas del Scraper e índices de directorios Libretro.
Se almacena dentro de <PlayNexus>/config/scraper_cache/ manteniendo la portabilidad total.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from playnexus.db import APP_DIR


def get_scraper_cache_dir(root_dir: Path | None = None) -> Path:
    base = Path(root_dir) if root_dir else Path(APP_DIR)
    cache_dir = base / "config" / "scraper_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


class ScraperCache:
    """Almacén en memoria + disco JSON thread-safe con expiración (TTL)."""

    def __init__(self, root_dir: Path | None = None, enabled: bool = True):
        self.enabled = bool(enabled)
        self.cache_dir = get_scraper_cache_dir(root_dir) if self.enabled else None
        self._lock = threading.Lock()
        self._mem: dict[str, tuple[float, Any]] = {}

    @staticmethod
    def _hash_key(namespace: str, raw_key: str) -> str:
        digest = hashlib.sha1(f"{namespace}:{raw_key}".encode("utf-8")).hexdigest()
        return f"{namespace}_{digest}.json"

    def get(self, namespace: str, raw_key: str, max_age_sec: float = 86400.0 * 7) -> Any | None:
        if not self.enabled:
            return None
        mem_key = f"{namespace}:{raw_key}"
        now = time.time()

        with self._lock:
            hit = self._mem.get(mem_key)
            if hit is not None:
                ts, payload = hit
                if (now - ts) <= max_age_sec:
                    return payload
                self._mem.pop(mem_key, None)

        if self.cache_dir is None:
            return None
        path = self.cache_dir / self._hash_key(namespace, raw_key)
        if not path.is_file():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ts = float(data.get("ts") or 0.0)
            if (now - ts) > max_age_sec:
                return None
            payload = data.get("payload")
            with self._lock:
                self._mem[mem_key] = (ts, payload)
            return payload
        except Exception:
            return None

    def set(self, namespace: str, raw_key: str, payload: Any) -> None:
        if not self.enabled:
            return
        mem_key = f"{namespace}:{raw_key}"
        now = time.time()
        with self._lock:
            self._mem[mem_key] = (now, payload)

        if self.cache_dir is None:
            return
        path = self.cache_dir / self._hash_key(namespace, raw_key)
        tmp = self.cache_dir / f".tmp_{os.getpid()}_{threading.get_ident()}_{path.name}"
        try:
            tmp.write_text(
                json.dumps({"ts": now, "key": raw_key, "payload": payload}, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(str(tmp), str(path))
        except Exception:
            try:
                if tmp.is_file():
                    tmp.unlink()
            except Exception:
                pass


def clear_scraper_cache(root_dir: Path | None = None) -> tuple[int, int]:
    """Elimina todos los archivos de caché del scraper y retorna (archivos_eliminados, bytes_liberados)."""
    cache_dir = get_scraper_cache_dir(root_dir)
    count = 0
    total_bytes = 0
    if not cache_dir.is_dir():
        return 0, 0
    for entry in os.scandir(cache_dir):
        if entry.is_file():
            try:
                sz = entry.stat().st_size
                os.unlink(entry.path)
                count += 1
                total_bytes += sz
            except OSError:
                pass
    return count, total_bytes


def get_scraper_cache_stats(root_dir: Path | None = None) -> tuple[int, int]:
    """Retorna (cantidad_archivos, bytes_totales) actuales de la caché del scraper."""
    cache_dir = get_scraper_cache_dir(root_dir)
    count = 0
    total_bytes = 0
    if not cache_dir.is_dir():
        return 0, 0
    for entry in os.scandir(cache_dir):
        if entry.is_file():
            try:
                total_bytes += entry.stat().st_size
                count += 1
            except OSError:
                pass
    return count, total_bytes
