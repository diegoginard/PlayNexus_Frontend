"""
Utilidades HTTP con stdlib (urllib), hashing incremental de ROMs y validación binaria de medios.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path
from typing import Any, Callable

from playnexus.__version__ import __version__
from playnexus.i18n import tr
from playnexus.services.media import IMAGE_EXTS, PDF_EXTS, VIDEO_EXTS, clear_media_cache
from playnexus.services.rom_manager import _unlink_with_retry


USER_AGENT = f"PlayNexus-Frontend/{__version__}"
_MAX_HASH_FILE_BYTES = 128 * 1024 * 1024  # Evitar leer ISOs/CHDs de varios GB por completo


class ProviderRateLimiter:
    """Limitador simple thread-safe de frecuencia entre solicitudes por proveedor."""

    def __init__(self, min_interval_sec: float = 0.25):
        self.min_interval = max(0.0, float(min_interval_sec))
        self._lock = threading.Lock()
        self._last_ts = 0.0

    def wait(self, cancel_check: Callable[[], bool] | None = None) -> bool:
        if self.min_interval <= 0:
            return not (cancel_check and cancel_check())
        with self._lock:
            now = time.monotonic()
            remaining = self.min_interval - (now - self._last_ts)
            if remaining > 0:
                deadline = now + remaining
                while time.monotonic() < deadline:
                    if cancel_check and cancel_check():
                        return False
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            self._last_ts = time.monotonic()
        return not (cancel_check and cancel_check())


def http_get_bytes(
    url: str,
    timeout: float = 18.0,
    retries: int = 2,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    """Realiza un GET HTTP/HTTPS con reintentos breves ante fallos transitorios (429/502/503/504)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(tr("svc.scraper.err_unsupported_scheme", "Unsupported URL scheme: {scheme}", scheme=parsed.scheme))

    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=req_headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return data, resp_headers
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 430, 431, 502, 503, 504) and attempt < retries:
                time.sleep(0.9 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err
    return b"", {}


def http_get_text(url: str, timeout: float = 18.0, retries: int = 2) -> str:
    data, _ = http_get_bytes(url, timeout=timeout, retries=retries)
    return data.decode("utf-8", errors="replace")


def http_get_json(url: str, timeout: float = 18.0, retries: int = 2) -> Any:
    raw = http_get_text(url, timeout=timeout, retries=retries)
    return json.loads(raw)


def detect_media_extension_from_bytes(
    header: bytes,
    content_type: str = "",
    fallback_ext: str = ".png",
) -> str | None:
    """
    Valida los magic bytes del archivo descargado y retorna su extensión real.
    Rechaza explícitamente páginas HTML o textos de error devueltos por CDNs/APIs.
    """
    if not header or len(header) < 12:
        return None

    ct = (content_type or "").lower()
    trimmed = header.lstrip()[:64].lower()
    if trimmed.startswith((b"<!doctype", b"<html", b"<head", b"<xml", b'{"error', b'{"header')):
        return None
    if "text/html" in ct or "application/json" in ct or "text/plain" in ct:
        return None

    # Imágenes
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return None  # Layouts usan PNG/JPG/WEBP estáticos

    # Videos
    if header[4:8] == b"ftyp":
        return ".mp4"
    if header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        return ".avi"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        # Matroska / WebM EBML
        if b"webm" in header[:128].lower() or (fallback_ext or "").lower() == ".webm" or "webm" in ct:
            return ".webm"
        return ".mkv"

    # Fallback únicamente si el Content-Type declara imagen/video explícito
    if "image/png" in ct:
        return ".png"
    if "image/jpeg" in ct or "image/jpg" in ct:
        return ".jpg"
    if "image/webp" in ct:
        return ".webp"
    if "video/mp4" in ct:
        return ".mp4"
    if "video/webm" in ct:
        return ".webm"
    if "video/x-msvideo" in ct:
        return ".avi"
    # Documentos PDF (Manuales)
    if header.lstrip().startswith(b"%PDF-") or "application/pdf" in ct:
        return ".pdf"
    return None


def _pick_compatible_ext(real_ext: str, allowed_exts: tuple[str, ...]) -> str | None:
    """
    Asegura compatibilidad entre la extensión real detectada y las admitidas por MEDIA_REQUIREMENTS.
    """
    norm_allowed = [e.lower() for e in (allowed_exts or ())]
    if not norm_allowed:
        return real_ext
    if real_ext in norm_allowed:
        return real_ext
    if real_ext == ".jpg" and ".jpeg" in norm_allowed:
        return ".jpeg"
    if real_ext == ".jpeg" and ".jpg" in norm_allowed:
        return ".jpg"
    if real_ext == ".mp4" and ".m4v" in norm_allowed:
        return ".m4v"
    return None


def download_media_to_slot(
    url: str,
    target_folder: str,
    target_stem: str,
    allowed_exts: tuple[str, ...],
    media_kind: str = "image",
    overwrite: bool = False,
    timeout: float = 25.0,
    fallback_ext: str = ".png",
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[str | None, str]:
    """
    Descarga un archivo multimedia por streaming, valida su firma binaria, verifica
    compatibilidad con allowed_exts de MEDIA_REQUIREMENTS y lo guarda atómicamente
    como `<target_stem><ext>` en `target_folder`.

    Retorna: (ruta_guardada_o_None, mensaje_estado)
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None, tr("svc.scraper.err_invalid_url", "Invalid URL")
    if not target_stem or not target_folder:
        return None, tr("svc.scraper.err_empty_target", "Empty target folder or stem")

    dest_dir = Path(target_folder)
    if not dest_dir.is_dir():
        return None, tr("svc.scraper.err_folder_missing", "Folder does not exist: {folder}", folder=target_folder)

    tmp_name = f".tmp_pn_{os.getpid()}_{threading.get_ident()}_{int(time.time() * 1000)}"
    tmp_path = dest_dir / tmp_name

    try:
        dl_retries = 2
        chosen_ext = ""
        for attempt in range(dl_retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    first_chunk = resp.read(64 * 1024)
                    if not first_chunk:
                        return None, tr("svc.scraper.err_empty_remote_file", "Empty remote file")

                    real_ext = detect_media_extension_from_bytes(
                        first_chunk[:256],
                        content_type=content_type,
                        fallback_ext=fallback_ext,
                    )
                    if not real_ext:
                        ct_disp = content_type or tr("svc.scraper.unknown_type", "unknown")
                        return None, tr("svc.scraper.err_invalid_remote_fmt", "Invalid remote file format ({content_type})", content_type=ct_disp)

                    kind_valid = (
                        set(VIDEO_EXTS) if media_kind == "video"
                        else (set(PDF_EXTS) if media_kind == "pdf" else set(IMAGE_EXTS))
                    )
                    if real_ext not in kind_valid:
                        return None, tr("svc.scraper.err_incompatible_type", "Incompatible type ({ext} for {kind} slot)", ext=real_ext, kind=media_kind)

                    chosen_ext = _pick_compatible_ext(real_ext, allowed_exts) or ""
                    if not chosen_ext:
                        exp = ", ".join(allowed_exts)
                        return None, tr("svc.scraper.err_ext_not_allowed", "Remote extension '{ext}' not accepted by layout ({allowed})", ext=real_ext, allowed=exp)

                    with open(tmp_path, "wb") as fh:
                        fh.write(first_chunk)
                        while True:
                            if cancel_check and cancel_check():
                                return None, tr("svc.scraper.err_download_cancelled", "Download cancelled")
                            chunk = resp.read(64 * 1024)
                            if not chunk:
                                break
                            fh.write(chunk)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 430, 431, 502, 503, 504) and attempt < dl_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < dl_retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise

        if not tmp_path.is_file() or tmp_path.stat().st_size < 64:
            return None, tr("svc.scraper.err_download_corrupt", "Downloaded file incomplete or corrupt")

        dest_path = dest_dir / f"{target_stem}{chosen_ext}"
        stem_low = target_stem.lower()
        if overwrite:
            for entry in os.scandir(dest_dir):
                if not entry.is_file() or entry.name.startswith(".tmp_pn_"):
                    continue
                e_stem, _ = os.path.splitext(entry.name)
                if e_stem.lower() == stem_low and Path(entry.path) != dest_path:
                    _unlink_with_retry(Path(entry.path))
        else:
            # No sobrescribir si ya apareció un archivo con el mismo stem
            for entry in os.scandir(dest_dir):
                if not entry.is_file() or entry.name.startswith(".tmp_pn_"):
                    continue
                e_stem, _ = os.path.splitext(entry.name)
                if e_stem.lower() == stem_low:
                    return str(entry.path).replace("\\", "/"), tr("svc.scraper.already_exists", "Already exists on disk")

        delays = (0.04, 0.08, 0.15)
        for idx in range(len(delays) + 1):
            try:
                os.replace(str(tmp_path), str(dest_path))
                break
            except PermissionError:
                if idx >= len(delays):
                    raise
                time.sleep(delays[idx])

        clear_media_cache()
        return str(dest_path).replace("\\", "/"), "OK"
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, str(exc)
    finally:
        try:
            if tmp_path.is_file():
                tmp_path.unlink()
        except Exception:
            pass


def compute_rom_hashes(rom_path: str | None, max_bytes: int = _MAX_HASH_FILE_BYTES) -> dict[str, str]:
    """
    Calcula tamaño, CRC32, MD5 y SHA1 por streaming para ROMs compactas (<= 128 MB).
    Omite el hashing en ISOs/CHDs grandes para mantener la velocidad del lote.
    """
    result = {"size": "", "crc": "", "md5": "", "sha1": ""}
    if not rom_path or not os.path.isfile(rom_path):
        return result
    try:
        size = os.path.getsize(rom_path)
    except OSError:
        return result

    result["size"] = str(size)
    if size <= 0 or size > max_bytes:
        return result

    crc_val = 0
    md5_h = hashlib.md5()
    sha1_h = hashlib.sha1()
    try:
        with open(rom_path, "rb") as fh:
            while True:
                buf = fh.read(1024 * 1024)
                if not buf:
                    break
                crc_val = zlib.crc32(buf, crc_val)
                md5_h.update(buf)
                sha1_h.update(buf)
    except OSError:
        return result

    result["crc"] = f"{crc_val & 0xFFFFFFFF:08X}"
    result["md5"] = md5_h.hexdigest().lower()
    result["sha1"] = sha1_h.hexdigest().lower()
    return result


_AUX_ZIP_EXTS = frozenset({".txt", ".nfo", ".diz", ".html", ".htm", ".url", ".ips", ".bps", ".ups", ".jpg", ".png"})


def compute_inner_zip_rom_info(rom_path: str | None) -> dict[str, str]:
    """
    Extrae instantáneamente desde la cabecera central de un archivo .zip de consola
    el CRC32 descomprimido, tamaño real y nombre interno de la ROM (sin descomprimir).
    Solo aplica cuando el .zip contiene una única ROM principal (no sets multi-chip MAME).
    """
    if not rom_path or not rom_path.lower().endswith(".zip") or not os.path.isfile(rom_path):
        return {}
    try:
        with zipfile.ZipFile(rom_path, "r") as zf:
            rom_entries = []
            for info in zf.infolist():
                if info.is_dir() or info.file_size <= 0:
                    continue
                base_name = os.path.basename(info.filename)
                if not base_name:
                    continue
                low_name = base_name.lower()
                _, ext = os.path.splitext(low_name)
                if ext in _AUX_ZIP_EXTS or low_name.startswith("readme"):
                    continue
                rom_entries.append(info)
            if len(rom_entries) != 1:
                return {}
            entry = rom_entries[0]
            return {
                "crc": f"{entry.CRC & 0xFFFFFFFF:08X}",
                "size": str(entry.file_size),
                "romnom": os.path.basename(entry.filename),
            }
    except Exception:
        return {}
