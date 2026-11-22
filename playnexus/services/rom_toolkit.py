"""
Pro Toolkit para Rom Manager de PlayNexus:
  1. Detección de capacidades opcionales (Pillow, ffmpeg/ffprobe, QtPdf).
  2. Auto-Trim de Wheels / Logos (recorte automático de bordes transparentes o negros con margen).
  3. Normalizador de Videos Preview a MP4 H.264/AAC ligero con ffmpeg (-movflags +faststart).
  4. Auditor 1G1R / Duplicados (agrupación por título canónico + disco + cloneof y prioridad regional).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import importlib
import json
import os
import re
import shutil
import subprocess
import time

from playnexus.db import APP_DIR
from playnexus.i18n import tr
from playnexus.services.library import sync_filtered_list_games
from playnexus.services.media import IMAGE_EXTS, VIDEO_EXTS, clear_media_cache
from playnexus.services.rom_manager import _unlink_with_retry
from playnexus.services.scraper.systems import clean_rom_search_title, normalize_match_key

FFMPEG_PATH_SETTING_KEY = "toolkit_ffmpeg_path"
DEFAULT_FFMPEG_REL_PATH = "tools/ffmpeg/ffmpeg.exe"

DEFAULT_1G1R_REGION_ORDER: tuple[str, ...] = (
    "USA",
    "World",
    "Europe",
    "Spain",
    "Japan",
    "Korea",
    "Asia",
    "Brazil",
    "France",
    "Germany",
    "Italy",
    "Unknown",
)

TRIM_SUPPORTED_EXTS: tuple[str, ...] = (".png", ".webp", ".bmp", ".tga", ".jpg", ".jpeg")
VIDEO_NORMALIZE_EXTS: tuple[str, ...] = tuple(
    dict.fromkeys(
        list(VIDEO_EXTS)
        + [".mov", ".wmv", ".flv", ".f4v", ".ts", ".vob", ".3gp", ".mpg", ".mpeg", ".m4v", ".ogv", ".ogm", ".divx", ".asf", ".rmvb"]
    )
)

_REGION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("USA", re.compile(r"\b(?:USA|US|U)\b", re.IGNORECASE)),
    ("World", re.compile(r"\b(?:World|W)\b", re.IGNORECASE)),
    ("Europe", re.compile(r"\b(?:Europe|EUR|EU|PAL|E)\b", re.IGNORECASE)),
    ("Spain", re.compile(r"\b(?:Spain|ESP|ES|S)\b", re.IGNORECASE)),
    ("Japan", re.compile(r"\b(?:Japan|JPN|JP|J)\b", re.IGNORECASE)),
    ("Korea", re.compile(r"\b(?:Korea|KOR|KR|K)\b", re.IGNORECASE)),
    ("Asia", re.compile(r"\b(?:Asia|AS)\b", re.IGNORECASE)),
    ("Brazil", re.compile(r"\b(?:Brazil|BRA|BR)\b", re.IGNORECASE)),
    ("France", re.compile(r"\b(?:France|FRA|FR|F)\b", re.IGNORECASE)),
    ("Germany", re.compile(r"\b(?:Germany|GER|DE|G)\b", re.IGNORECASE)),
    ("Italy", re.compile(r"\b(?:Italy|ITA|IT|I)\b", re.IGNORECASE)),
)

_PAREN_OR_BRACKET_RE = re.compile(r"\(([^)]+)\)|\[([^\]]+)\]")
_DISC_TAG_RE = re.compile(
    r"[\(\[]\s*(?:dis[ck]|cd|gd|dvd|tape|side|part)\s*[-_#]?\s*([a-z0-9]+)\s*[\)\]]"
    r"|\b(?:dis[ck]|cd|side)\s*[-_#]?\s*([a-z0-9]+)\b",
    re.IGNORECASE,
)
_REVISION_RE = re.compile(
    r"\(\s*(?:rev|revision)\s*([0-9]+(?:\.[0-9]+)*|[a-z])\s*\)"
    r"|\(\s*v([0-9]+(?:\.[0-9]+)*)\s*\)",
    re.IGNORECASE,
)
_PRE_RELEASE_RE = re.compile(
    r"\b(?:beta|proto|prototype|demo|sample|kiosk|preview|trial|unl|unlicensed|pirate|hack|aftermarket|homebrew|promo)\b",
    re.IGNORECASE,
)
_BAD_DUMP_RE = re.compile(r"\[(b\d*|h\d*|o\d*|f\d*|p\d*|t[+-][^\]]*)\]", re.IGNORECASE)
_LANG_TAG_RE = re.compile(r"\(([^)]+)\)", re.IGNORECASE)


# ------------------------------------------------------------------
# 1. DETECCIÓN DE CAPACIDADES Y HERRAMIENTAS EXTERNAS
# ------------------------------------------------------------------
def is_pillow_available() -> bool:
    try:
        importlib.import_module("PIL.Image")
        return True
    except ImportError:
        return False


def is_qtpdf_available() -> bool:
    try:
        from PySide6.QtPdf import QPdfDocument  # noqa: F401
        return True
    except ImportError:
        return False


def _probe_sibling_ffprobe(ffmpeg_exe: str) -> str:
    if not ffmpeg_exe:
        return ""
    try:
        p = Path(ffmpeg_exe)
        ext = p.suffix
        cand = p.with_name(f"ffprobe{ext}")
        if cand.is_file():
            return str(cand)
        cand2 = p.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if cand2.is_file():
            return str(cand2)
    except Exception:
        pass
    return shutil.which("ffprobe") or ""


def resolve_ffmpeg_paths(db=None) -> tuple[str, str]:
    """
    Resuelve las rutas de `ffmpeg` y `ffprobe` (setting manual -> carpetas portables -> PATH).
    Retorna `(ffmpeg_path, ffprobe_path)` o `("", "")`.
    """
    base = Path(APP_DIR)
    candidates: list[Path] = []
    if db is not None and hasattr(db, "get_setting"):
        saved = str(db.get_setting(FFMPEG_PATH_SETTING_KEY, DEFAULT_FFMPEG_REL_PATH) or "").strip()
        if saved:
            sp = Path(saved)
            sp_roots = [sp] if sp.is_absolute() else [base / sp, sp]
            for sp_cand in sp_roots:
                if sp_cand.is_dir():
                    candidates.extend([
                        sp_cand / "ffmpeg.exe",
                        sp_cand / "ffmpeg",
                        sp_cand / "bin" / "ffmpeg.exe",
                        sp_cand / "bin" / "ffmpeg",
                    ])
                else:
                    candidates.append(sp_cand)

    candidates.extend([
        base / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
        base / "tools" / "ffmpeg" / "ffmpeg.exe",
        base / "tools" / "ffmpeg.exe",
        base / "ffmpeg" / "bin" / "ffmpeg.exe",
        base / "ffmpeg" / "ffmpeg.exe",
        base / "ffmpeg.exe",
    ])

    ffmpeg_exe = ""
    for cand in candidates:
        try:
            if cand.is_file():
                ffmpeg_exe = str(cand.resolve())
                break
        except OSError:
            continue

    if not ffmpeg_exe:
        which_ff = shutil.which("ffmpeg")
        if which_ff:
            ffmpeg_exe = str(Path(which_ff).resolve()) if Path(which_ff).exists() else which_ff

    ffprobe_exe = _probe_sibling_ffprobe(ffmpeg_exe) if ffmpeg_exe else (shutil.which("ffprobe") or "")
    return ffmpeg_exe, ffprobe_exe


def save_ffmpeg_path(db, path: str | Path) -> str:
    """Guarda en configuración la ruta portable de ffmpeg (archivo o carpeta)."""
    clean = str(path or "").strip()
    if clean:
        p = Path(clean)
        if p.is_dir():
            for sub in (p / "ffmpeg.exe", p / "bin" / "ffmpeg.exe", p / "ffmpeg", p / "bin" / "ffmpeg"):
                if sub.is_file():
                    clean = str(sub.resolve())
                    break
        elif p.is_file():
            clean = str(p.resolve())
    if db is not None and hasattr(db, "set_setting"):
        db.set_setting(FFMPEG_PATH_SETTING_KEY, clean)
    return clean


def detect_toolkit_capabilities(db=None) -> dict[str, Any]:
    """Informa qué dependencias opcionales están listas y guía al usuario si falta alguna."""
    pil_ok = False
    pil_ver = ""
    try:
        pil_mod = importlib.import_module("PIL")
        importlib.import_module("PIL.Image")
        pil_ok = True
        pil_ver = str(getattr(pil_mod, "__version__", "") or "")
    except ImportError:
        pil_ok = False

    ffmpeg_path, ffprobe_path = resolve_ffmpeg_paths(db)
    qtpdf_ok = is_qtpdf_available()

    notices: list[str] = []
    if not pil_ok:
        notices.append(
            tr(
                "svc.toolkit.notice_no_pillow",
                "Pillow is not installed in this environment: Auto-Trim will run using the native Qt engine (RGBA8888), with no loss of compatibility.",
            )
        )
    if not ffmpeg_path:
        notices.append(
            tr(
                "svc.toolkit.notice_no_ffmpeg",
                "ffmpeg was not found on the system or in PlayNexus/tools/ffmpeg: the video normalization tab will remain informational until you locate ffmpeg.exe or add it to PATH.",
            )
        )
    if not qtpdf_ok:
        notices.append(
            tr(
                "svc.toolkit.notice_no_qtpdf",
                "PySide6.QtPdf is not available: the built-in viewer will fall back to opening files with the OS default PDF reader.",
            )
        )

    return {
        "pillow_available": pil_ok,
        "pillow_version": pil_ver,
        "ffmpeg_available": bool(ffmpeg_path),
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_available": bool(ffprobe_path),
        "ffprobe_path": ffprobe_path,
        "qtpdf_available": qtpdf_ok,
        "notices": notices,
    }


def _subprocess_creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


# ------------------------------------------------------------------
# 2. AUTO-TRIM DE WHEELS / LOGOS
# ------------------------------------------------------------------
@dataclass
class TrimFileResult:
    file_path: str
    status: str  # "trimmed", "skipped_no_margin", "skipped_empty", "skipped_format", "error"
    orig_size: tuple[int, int] = (0, 0)
    new_size: tuple[int, int] = (0, 0)
    bytes_before: int = 0
    bytes_after: int = 0
    backup_path: str = ""
    message: str = ""


def _qimage_load_rgba(path: Path):
    from PySide6.QtGui import QImage

    img = QImage(str(path))
    if img.isNull():
        return None, False
    had_alpha = bool(img.hasAlphaChannel())
    if img.format() != QImage.Format.Format_RGBA8888:
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    return img, had_alpha


def _rgba_row_has_visible_alpha(alpha_plane: bytes, alpha_threshold: int) -> bool:
    if not alpha_plane:
        return False
    if alpha_threshold <= 0:
        return any(alpha_plane)
    return max(alpha_plane) > alpha_threshold


def _rgba_row_has_nonblack_pixel(
    row_bytes: bytes,
    width: int,
    check_alpha: bool,
    alpha_threshold: int,
    black_threshold: int,
) -> bool:
    r_plane = row_bytes[0 : width * 4 : 4]
    g_plane = row_bytes[1 : width * 4 : 4]
    b_plane = row_bytes[2 : width * 4 : 4]
    if not check_alpha:
        return (
            (max(r_plane) > black_threshold)
            or (max(g_plane) > black_threshold)
            or (max(b_plane) > black_threshold)
        )
    a_plane = row_bytes[3 : width * 4 : 4]
    if max(a_plane) <= alpha_threshold:
        return False
    for x in range(width):
        if a_plane[x] > alpha_threshold and (
            r_plane[x] > black_threshold
            or g_plane[x] > black_threshold
            or b_plane[x] > black_threshold
        ):
            return True
    return False


def _detect_effective_trim_mode_qimage(
    rgba_bytes: bytes,
    w: int,
    h: int,
    bpl: int,
    had_alpha: bool,
    trim_mode: str,
    alpha_threshold: int,
) -> str:
    if trim_mode in ("alpha_only", "alpha_black", "black_only"):
        return trim_mode
    # Modo "auto": usar transparencia solo si realmente existe borde/píxel transparente
    if had_alpha and w > 0 and h > 0:
        top_a = rgba_bytes[3 : w * 4 : 4]
        bot_off = (h - 1) * bpl
        bot_a = rgba_bytes[bot_off + 3 : bot_off + w * 4 : 4]
        if min(top_a) <= alpha_threshold or min(bot_a) <= alpha_threshold:
            return "alpha_only"
        # Revisar bordes izquierdo y derecho
        for y in range(h):
            off = y * bpl
            if rgba_bytes[off + 3] <= alpha_threshold or rgba_bytes[off + (w - 1) * 4 + 3] <= alpha_threshold:
                return "alpha_only"
    return "black_only"


def _compute_bbox_from_qimage(
    img,
    had_alpha: bool,
    trim_mode: str = "auto",
    alpha_threshold: int = 4,
    black_threshold: int = 8,
) -> tuple[tuple[int, int, int, int] | None, str]:
    w = img.width()
    h = img.height()
    if w <= 0 or h <= 0:
        return None, "empty"

    bpl = img.bytesPerLine()
    raw = bytes(img.constBits())
    eff_mode = _detect_effective_trim_mode_qimage(raw, w, h, bpl, had_alpha, trim_mode, alpha_threshold)

    if eff_mode == "alpha_only" and not had_alpha:
        return (0, 0, w - 1, h - 1), eff_mode

    top = -1
    bottom = -1
    left = w
    right = -1
    row_span = w * 4

    if eff_mode == "alpha_only":
        for y in range(h):
            off = y * bpl
            a_plane = raw[off + 3 : off + row_span : 4]
            if not _rgba_row_has_visible_alpha(a_plane, alpha_threshold):
                continue
            if top < 0:
                top = y
            bottom = y
            if left > 0 and max(a_plane[:left]) > alpha_threshold:
                for x in range(left):
                    if a_plane[x] > alpha_threshold:
                        left = x
                        break
            if right < w - 1 and max(a_plane[right + 1 :]) > alpha_threshold:
                for x in range(w - 1, right, -1):
                    if a_plane[x] > alpha_threshold:
                        right = x
                        break
    else:
        check_alpha = (eff_mode == "alpha_black") and had_alpha
        for y in range(h):
            off = y * bpl
            row = raw[off : off + row_span]
            if not _rgba_row_has_nonblack_pixel(row, w, check_alpha, alpha_threshold, black_threshold):
                continue
            if top < 0:
                top = y
            bottom = y
            for x in range(left):
                px = x * 4
                a_ok = (not check_alpha) or (row[px + 3] > alpha_threshold)
                if a_ok and (row[px] > black_threshold or row[px + 1] > black_threshold or row[px + 2] > black_threshold):
                    left = x
                    break
            for x in range(w - 1, right, -1):
                px = x * 4
                a_ok = (not check_alpha) or (row[px + 3] > alpha_threshold)
                if a_ok and (row[px] > black_threshold or row[px + 1] > black_threshold or row[px + 2] > black_threshold):
                    right = x
                    break

    if top < 0 or bottom < top or right < left:
        return None, eff_mode
    return (left, top, right, bottom), eff_mode


def _compute_bbox_with_pillow(
    pil_img,
    trim_mode: str = "auto",
    alpha_threshold: int = 4,
    black_threshold: int = 8,
) -> tuple[tuple[int, int, int, int] | None, str]:
    rgba = pil_img.convert("RGBA")
    w, h = rgba.size
    had_alpha = "A" in pil_img.getbands()
    eff_mode = trim_mode

    if eff_mode == "auto":
        if had_alpha:
            a_band = rgba.getchannel("A")
            a_ext = a_band.getextrema()
            eff_mode = "alpha_only" if (a_ext and a_ext[0] <= alpha_threshold) else "black_only"
        else:
            eff_mode = "black_only"

    if eff_mode == "alpha_only":
        if not had_alpha:
            return (0, 0, w - 1, h - 1), eff_mode
        mask = rgba.getchannel("A").point(lambda a: 255 if a > alpha_threshold else 0)
        bbox = mask.getbbox()
        if not bbox:
            return None, eff_mode
        return (bbox[0], bbox[1], bbox[2] - 1, bbox[3] - 1), eff_mode

    # alpha_black o black_only
    r, g, b, a = rgba.split()
    if black_threshold > 0:
        r = r.point(lambda v: 255 if v > black_threshold else 0)
        g = g.point(lambda v: 255 if v > black_threshold else 0)
        b = b.point(lambda v: 255 if v > black_threshold else 0)
    ImageChops = importlib.import_module("PIL.ImageChops")

    rgb_mask = ImageChops.lighter(ImageChops.lighter(r, g), b)
    if eff_mode == "alpha_black" and had_alpha:
        a_mask = a.point(lambda v: 255 if v > alpha_threshold else 0)
        rgb_mask = ImageChops.darker(rgb_mask, a_mask)
    bbox = rgb_mask.getbbox()
    if not bbox:
        return None, eff_mode
    return (bbox[0], bbox[1], bbox[2] - 1, bbox[3] - 1), eff_mode


def compute_trim_bbox_for_image(
    image_path: str | Path,
    trim_mode: str = "auto",
    alpha_threshold: int = 4,
    black_threshold: int = 8,
    margin: int = 4,
) -> tuple[tuple[int, int, int, int] | None, tuple[int, int], str]:
    """
    Calcula la caja de recorte `(x0, y0, x1_exclusive, y1_exclusive)` más el margen indicado.
    Retorna `(crop_box_or_None, (width, height), effective_mode)`.
    """
    p = Path(image_path)
    if is_pillow_available():
        Image = importlib.import_module("PIL.Image")
        with Image.open(p) as im:
            im.load()
            w, h = im.size
            bbox, eff_mode = _compute_bbox_with_pillow(im, trim_mode, alpha_threshold, black_threshold)
    else:
        qimg, had_alpha = _qimage_load_rgba(p)
        if qimg is None:
            raise ValueError(tr("svc.toolkit.err_read_image", "Could not read image: {path}", path=p))
        w, h = qimg.width(), qimg.height()
        bbox, eff_mode = _compute_bbox_from_qimage(qimg, had_alpha, trim_mode, alpha_threshold, black_threshold)

    if bbox is None:
        return None, (w, h), eff_mode

    m = max(0, int(margin))
    x0 = max(0, bbox[0] - m)
    y0 = max(0, bbox[1] - m)
    x1 = min(w, bbox[2] + 1 + m)
    y1 = min(h, bbox[3] + 1 + m)
    return (x0, y0, x1, y1), (w, h), eff_mode


def _ensure_backup_file(src: Path) -> str:
    bak = Path(f"{src}.bak")
    if not bak.exists():
        shutil.copy2(src, bak)
    return str(bak)


def auto_trim_image_file(
    image_path: str | Path,
    margin: int = 4,
    trim_mode: str = "auto",
    alpha_threshold: int = 4,
    black_threshold: int = 8,
    min_shrink_px: int = 2,
    create_backup: bool = True,
    dry_run: bool = False,
) -> TrimFileResult:
    """
    Recorta bordes sobrantes de una imagen de Wheel/Logo conservando un margen uniforme.
    Usa Pillow si está instalado o cae de forma transparente en `PySide6.QtGui.QImage`.
    """
    p = Path(image_path)
    ext = p.suffix.lower()
    if ext not in TRIM_SUPPORTED_EXTS:
        return TrimFileResult(str(p), "skipped_format", message=tr("svc.toolkit.trim_unsupported_fmt", "Unsupported format ({ext})", ext=ext))
    if not p.is_file():
        return TrimFileResult(str(p), "error", message=tr("svc.toolkit.trim_missing_file", "File does not exist"))

    bytes_before = int(p.stat().st_size)
    try:
        crop_box, (w, h), eff_mode = compute_trim_bbox_for_image(
            p,
            trim_mode=trim_mode,
            alpha_threshold=alpha_threshold,
            black_threshold=black_threshold,
            margin=margin,
        )
    except Exception as exc:
        return TrimFileResult(str(p), "error", bytes_before=bytes_before, message=str(exc))

    if crop_box is None:
        return TrimFileResult(
            str(p),
            "skipped_empty",
            orig_size=(w, h),
            new_size=(w, h),
            bytes_before=bytes_before,
            bytes_after=bytes_before,
            message=tr("svc.toolkit.trim_empty_image", "Image is completely empty/transparent; skipped for safety"),
        )

    x0, y0, x1, y1 = crop_box
    new_w = max(1, x1 - x0)
    new_h = max(1, y1 - y0)
    shrink_total = (w - new_w) + (h - new_h)
    if shrink_total < max(1, int(min_shrink_px)):
        return TrimFileResult(
            str(p),
            "skipped_no_margin",
            orig_size=(w, h),
            new_size=(w, h),
            bytes_before=bytes_before,
            bytes_after=bytes_before,
            message=tr("svc.toolkit.trim_no_margin", "No significant trimmable margin ({mode})", mode=eff_mode),
        )

    if dry_run:
        return TrimFileResult(
            str(p),
            "trimmed",
            orig_size=(w, h),
            new_size=(new_w, new_h),
            bytes_before=bytes_before,
            bytes_after=bytes_before,
            message=tr(
                "svc.toolkit.trim_dry_run",
                "Dry run ({mode}): {w}x{h} -> {new_w}x{new_h}",
                mode=eff_mode,
                w=w,
                h=h,
                new_w=new_w,
                new_h=new_h,
            ),
        )

    bak_path = ""
    if create_backup:
        bak_path = _ensure_backup_file(p)

    tmp_path = p.with_name(f"{p.stem}.__trim_tmp__{p.suffix}")
    try:
        if is_pillow_available():
            Image = importlib.import_module("PIL.Image")
            with Image.open(p) as im:
                cropped = im.crop((x0, y0, x1, y1))
                save_kwargs: dict[str, Any] = {}
                if ext == ".webp":
                    save_kwargs = {"lossless": True, "quality": 95} if cropped.mode in ("RGBA", "LA", "P") else {"quality": 92}
                elif ext in (".jpg", ".jpeg"):
                    if cropped.mode != "RGB":
                        cropped = cropped.convert("RGB")
                    save_kwargs = {"quality": 92, "optimize": True}
                elif ext == ".png":
                    save_kwargs = {"optimize": True}
                cropped.save(tmp_path, **save_kwargs)
        else:
            from PySide6.QtGui import QImage
            qimg = QImage(str(p))
            if qimg.isNull():
                raise ValueError(tr("svc.toolkit.trim_qimage_reload_err", "QImage could not reload the file"))
            cropped_q = qimg.copy(x0, y0, new_w, new_h)
            fmt_map = {
                ".png": "PNG",
                ".webp": "WEBP",
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
                ".bmp": "BMP",
            }
            fmt = fmt_map.get(ext, "PNG")
            quality = 92 if ext in (".webp", ".jpg", ".jpeg") else -1
            if not cropped_q.save(str(tmp_path), fmt, quality):
                raise IOError(tr("svc.toolkit.trim_save_err", "Error saving cropped image ({fmt})", fmt=fmt))

        os.replace(tmp_path, p)
        bytes_after = int(p.stat().st_size)
        return TrimFileResult(
            str(p),
            "trimmed",
            orig_size=(w, h),
            new_size=(new_w, new_h),
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            backup_path=bak_path,
            message=tr(
                "svc.toolkit.trim_done",
                "Cropped ({mode}): {w}x{h} -> {new_w}x{new_h}",
                mode=eff_mode,
                w=w,
                h=h,
                new_w=new_w,
                new_h=new_h,
            ),
        )
    except Exception as exc:
        if tmp_path.exists():
            _unlink_with_retry(tmp_path)
        return TrimFileResult(
            str(p),
            "error",
            orig_size=(w, h),
            bytes_before=bytes_before,
            backup_path=bak_path,
            message=str(exc),
        )


def auto_trim_folder(
    folder: str | Path,
    margin: int = 4,
    trim_mode: str = "auto",
    alpha_threshold: int = 4,
    black_threshold: int = 8,
    min_shrink_px: int = 2,
    create_backup: bool = True,
    recursive: bool = False,
    dry_run: bool = False,
    progress_callback: Callable[[int, int, str, TrimFileResult], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Ejecuta Auto-Trim sobre todas las imágenes válidas dentro de una carpeta de Wheels/Logos."""
    root = Path(folder)
    if not root.is_dir():
        return {"total": 0, "trimmed": 0, "skipped": 0, "errors": 1, "saved_bytes": 0, "results": [], "cancelled": False}

    files: list[Path] = []
    if recursive:
        for dp, _, fns in os.walk(root):
            for fn in fns:
                p = Path(dp) / fn
                if p.suffix.lower() in TRIM_SUPPORTED_EXTS and not p.name.endswith(".bak") and ".__trim_tmp__" not in p.name:
                    files.append(p)
    else:
        for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
            if p.is_file() and p.suffix.lower() in TRIM_SUPPORTED_EXTS and ".__trim_tmp__" not in p.name:
                files.append(p)

    results: list[TrimFileResult] = []
    trimmed = 0
    skipped = 0
    errors = 0
    saved_bytes = 0
    cancelled = False
    total = len(files)

    for idx, fpath in enumerate(files, start=1):
        if cancel_check and cancel_check():
            cancelled = True
            break
        res = auto_trim_image_file(
            fpath,
            margin=margin,
            trim_mode=trim_mode,
            alpha_threshold=alpha_threshold,
            black_threshold=black_threshold,
            min_shrink_px=min_shrink_px,
            create_backup=create_backup,
            dry_run=dry_run,
        )
        results.append(res)
        if res.status == "trimmed":
            trimmed += 1
            if not dry_run:
                saved_bytes += max(0, res.bytes_before - res.bytes_after)
        elif res.status == "error":
            errors += 1
        else:
            skipped += 1
        if progress_callback:
            progress_callback(idx, total, fpath.name, res)

    if trimmed > 0 and not dry_run:
        clear_media_cache()

    return {
        "total": total,
        "processed": len(results),
        "trimmed": trimmed,
        "skipped": skipped,
        "errors": errors,
        "saved_bytes": saved_bytes,
        "results": results,
        "cancelled": cancelled,
    }


# ------------------------------------------------------------------
# 3. NORMALIZADOR DE VIDEOS PREVIEW (ffmpeg)
# ------------------------------------------------------------------
@dataclass
class VideoCandidate:
    file_path: str
    filename: str
    ext: str
    size_bytes: int
    reasons: list[str] = field(default_factory=list)
    width: int = 0
    height: int = 0
    vcodec: str = ""
    pix_fmt: str = ""


def probe_video_info(video_path: str | Path, ffprobe_path: str = "") -> dict[str, Any]:
    """Obtiene resolución, códec y tamaño usando ffprobe (si está disponible)."""
    p = Path(video_path)
    info: dict[str, Any] = {
        "size_bytes": int(p.stat().st_size) if p.is_file() else 0,
        "ext": p.suffix.lower(),
        "width": 0,
        "height": 0,
        "vcodec": "",
        "acodec": "",
        "pix_fmt": "",
        "duration": 0.0,
    }
    if not ffprobe_path or not p.is_file():
        return info
    try:
        proc = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_subprocess_creation_flags(),
        )
        if proc.returncode != 0 or not proc.stdout:
            return info
        data = json.loads(proc.stdout)
        fmt = data.get("format") or {}
        try:
            info["duration"] = float(fmt.get("duration") or 0.0)
        except (TypeError, ValueError):
            pass
        for st in data.get("streams") or []:
            ctype = st.get("codec_type")
            if ctype == "video" and not info["vcodec"]:
                info["vcodec"] = str(st.get("codec_name") or "").lower()
                info["pix_fmt"] = str(st.get("pix_fmt") or "").lower()
                info["width"] = int(st.get("width") or 0)
                info["height"] = int(st.get("height") or 0)
            elif ctype == "audio" and not info["acodec"]:
                info["acodec"] = str(st.get("codec_name") or "").lower()
    except Exception:
        pass
    return info


def scan_video_candidates(
    folder: str | Path,
    max_size_mb: float = 15.0,
    max_height: int = 720,
    ffprobe_path: str = "",
    deep_probe_mp4: bool = False,
    recursive: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    stats_out: dict[str, Any] | None = None,
) -> list[VideoCandidate]:
    """Detecta videos fuera de estándar (no .mp4, > max_size_mb, o códec/resolución excesiva)."""
    root = Path(folder)
    if not root.is_dir():
        if stats_out is not None:
            stats_out.update({"scanned_files": 0, "probed_files": 0, "skipped_non_video": 0, "cancelled": False})
        return []

    threshold_mb = max(0.5, float(max_size_mb))
    threshold_bytes = int(threshold_mb * 1024 * 1024)
    limit_lbl = f"{threshold_mb:g}"

    video_files: list[Path] = []
    skipped_non_video = 0
    if recursive:
        for dp, _dirnames, fns in os.walk(root):
            for fn in fns:
                p = Path(dp) / fn
                name_l = p.name.lower()
                if name_l.endswith(".bak") or ".__ff_tmp__" in name_l:
                    continue
                if p.suffix.lower() in VIDEO_NORMALIZE_EXTS:
                    video_files.append(p)
                else:
                    skipped_non_video += 1
        video_files.sort(key=lambda x: str(x.relative_to(root)).lower())
    else:
        for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_file():
                continue
            name_l = p.name.lower()
            if name_l.endswith(".bak") or ".__ff_tmp__" in name_l:
                continue
            if p.suffix.lower() in VIDEO_NORMALIZE_EXTS:
                video_files.append(p)
            else:
                skipped_non_video += 1

    candidates: list[VideoCandidate] = []
    total = len(video_files)
    probed_files = 0
    cancelled = False

    for idx, p in enumerate(video_files, start=1):
        if cancel_check and cancel_check():
            cancelled = True
            break

        try:
            rel_name = str(p.relative_to(root)).replace("\\", "/") if recursive else p.name
        except ValueError:
            rel_name = p.name

        if progress_callback:
            progress_callback(idx, total, rel_name)

        ext = p.suffix.lower()
        size_b = int(p.stat().st_size)
        reasons: list[str] = []
        if ext != ".mp4":
            reasons.append(tr("svc.toolkit.vid_reason_format", "Format {ext} (target .mp4)", ext=ext))
        if size_b > threshold_bytes:
            mb = size_b / (1024.0 * 1024.0)
            reasons.append(tr("svc.toolkit.vid_reason_size", "Size {mb} MB > {limit} MB", mb=f"{mb:.1f}", limit=limit_lbl))

        w = h = 0
        vcodec = pix_fmt = ""
        if ffprobe_path and (reasons or deep_probe_mp4):
            probed_files += 1
            vinfo = probe_video_info(p, ffprobe_path=ffprobe_path)
            w = vinfo["width"]
            h = vinfo["height"]
            vcodec = vinfo["vcodec"]
            pix_fmt = vinfo["pix_fmt"]
            if h > max_height:
                reasons.append(tr("svc.toolkit.vid_reason_height", "Height {h}p > {max_h}p", h=h, max_h=max_height))
            if vcodec and vcodec != "h264":
                reasons.append(tr("svc.toolkit.vid_reason_codec", "Codec {codec} != h264", codec=vcodec))
            if pix_fmt and pix_fmt not in ("yuv420p", "yuvj420p"):
                reasons.append(tr("svc.toolkit.vid_reason_pixfmt", "Pixel format {pix_fmt} != yuv420p", pix_fmt=pix_fmt))

        if reasons:
            candidates.append(
                VideoCandidate(
                    file_path=str(p),
                    filename=rel_name,
                    ext=ext,
                    size_bytes=size_b,
                    reasons=reasons,
                    width=w,
                    height=h,
                    vcodec=vcodec,
                    pix_fmt=pix_fmt,
                )
            )

    if stats_out is not None:
        stats_out.update(
            {
                "scanned_files": total if not cancelled else idx - 1,
                "total_candidates": len(candidates),
                "probed_files": probed_files,
                "skipped_non_video": skipped_non_video,
                "cancelled": cancelled,
            }
        )
    return candidates


def build_ffmpeg_normalize_command(
    ffmpeg_path: str,
    src_path: str | Path,
    dst_path: str | Path,
    target_height: int = 480,
    crf: int = 24,
    preset: str = "veryfast",
    audio_bitrate: str = "96k",
    strip_audio: bool = False,
) -> list[str]:
    """Construye argumentos seguros para normalizar a MP4 H.264/yuv420p + AAC + faststart."""
    th = max(240, min(1080, int(target_height)))
    # Mantiene aspecto y dimensiones pares sin reescalar hacia arriba videos más chicos
    vf = f"scale=-2:'min({th},trunc(ih/2)*2)':flags=lanczos"
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        str(preset or "veryfast"),
        "-crf",
        str(max(16, min(32, int(crf)))),
        "-movflags",
        "+faststart",
    ]
    if strip_audio:
        cmd.append("-an")
    else:
        cmd.extend(["-c:a", "aac", "-b:a", str(audio_bitrate or "96k"), "-ac", "2"])
    cmd.extend(["-f", "mp4", str(dst_path)])
    return cmd


def normalize_video_file(
    src_path: str | Path,
    ffmpeg_path: str,
    target_height: int = 480,
    crf: int = 24,
    preset: str = "veryfast",
    audio_bitrate: str = "96k",
    strip_audio: bool = False,
    create_backup: bool = True,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Transcodifica un video de forma cancelable y reemplaza atómicamente con respaldo `.bak` opcional."""
    src = Path(src_path)
    if not ffmpeg_path or not Path(ffmpeg_path).is_file():
        return {"status": "error", "src": str(src), "message": tr("svc.toolkit.vid_no_ffmpeg", "ffmpeg is not available.")}
    if not src.is_file():
        return {"status": "error", "src": str(src), "message": tr("svc.toolkit.vid_missing_file", "Video file does not exist.")}

    bytes_before = int(src.stat().st_size)
    final_mp4 = src.with_suffix(".mp4")
    tmp_mp4 = final_mp4.with_name(f"{final_mp4.stem}.__ff_tmp__.mp4")
    if tmp_mp4.exists():
        _unlink_with_retry(tmp_mp4)

    cmd = build_ffmpeg_normalize_command(
        ffmpeg_path=ffmpeg_path,
        src_path=src,
        dst_path=tmp_mp4,
        target_height=target_height,
        crf=crf,
        preset=preset,
        audio_bitrate=audio_bitrate,
        strip_audio=strip_audio,
    )

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_subprocess_creation_flags(),
        )
        while proc.poll() is None:
            if cancel_check and cancel_check():
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
                if tmp_mp4.exists():
                    _unlink_with_retry(tmp_mp4)
                return {"status": "cancelled", "src": str(src), "message": tr("svc.toolkit.vid_cancelled", "Cancelled by user.")}
            time.sleep(0.15)

        stderr_bytes = proc.stderr.read() if proc.stderr else b""
        if proc.returncode != 0 or not tmp_mp4.is_file() or tmp_mp4.stat().st_size == 0:
            err_msg = stderr_bytes.decode("utf-8", errors="replace").strip() or tr(
                "svc.toolkit.vid_ffmpeg_exit_code",
                "ffmpeg exited with code {code}",
                code=proc.returncode,
            )
            if tmp_mp4.exists():
                _unlink_with_retry(tmp_mp4)
            return {"status": "error", "src": str(src), "message": err_msg}

        backup_path = ""
        if create_backup:
            backup_path = _ensure_backup_file(src)
            if final_mp4 != src and final_mp4.exists():
                _ensure_backup_file(final_mp4)

        os.replace(tmp_mp4, final_mp4)
        # Si la extensión cambió (.avi -> .mp4), quitar el original solo tras haber garantizado el .bak si se pidió
        if final_mp4 != src and src.exists():
            _unlink_with_retry(src)

        clear_media_cache()
        bytes_after = int(final_mp4.stat().st_size)
        return {
            "status": "normalized",
            "src": str(src),
            "dst": str(final_mp4),
            "backup_path": backup_path,
            "bytes_before": bytes_before,
            "bytes_after": bytes_after,
            "message": tr(
                "svc.toolkit.vid_converted",
                "Converted to {name} ({mb} MB)",
                name=final_mp4.name,
                mb=f"{bytes_after / (1024 * 1024):.1f}",
            ),
        }
    except Exception as exc:
        if tmp_mp4.exists():
            _unlink_with_retry(tmp_mp4)
        return {"status": "error", "src": str(src), "message": str(exc)}


# ------------------------------------------------------------------
# 4. AUDITOR 1G1R / DUPLICADOS
# ------------------------------------------------------------------
def extract_disc_tag(text: str) -> str:
    """Extrae identificador normalizado de disco/cara para no mezclar Disc 1 y Disc 2 en 1G1R."""
    m = _DISC_TAG_RE.search(text or "")
    if not m:
        return ""
    token = (m.group(1) or m.group(2) or "").strip().lower()
    return f"disc:{token}" if token else ""


def extract_game_region(game: dict[str, Any]) -> str:
    """Detecta la región principal desde el nombre de archivo o título del juego."""
    rom_name = Path(str(game.get("rom_path") or "")).stem or str(game.get("rom_name") or "")
    title = str(game.get("title") or "")
    for source in (rom_name, title):
        if not source:
            continue
        tags = [g1 or g2 for g1, g2 in _PAREN_OR_BRACKET_RE.findall(source)]
        combined = " ".join(tags) if tags else source
        for reg_name, pat in _REGION_PATTERNS:
            if pat.search(combined):
                return reg_name
    return "Unknown"


def _extract_revision_score(text: str) -> tuple[int, int, int]:
    """Devuelve tupla comparable para elegir la revisión más reciente (Rev B > Rev A > base)."""
    best = (0, 0, 0)
    for m in _REVISION_RE.finditer(text or ""):
        rev_raw = m.group(1) or ""
        ver_raw = m.group(2) or ""
        if rev_raw:
            if rev_raw.isalpha():
                cand = (1, ord(rev_raw.upper()) - ord("A") + 1, 0)
            else:
                parts = [int(x) for x in rev_raw.split(".") if x.isdigit()]
                cand = (parts[0] if parts else 0, parts[1] if len(parts) > 1 else 0, parts[2] if len(parts) > 2 else 0)
            if cand > best:
                best = cand
        elif ver_raw:
            parts = [int(x) for x in ver_raw.split(".") if x.isdigit()]
            cand = (parts[0] if parts else 0, parts[1] if len(parts) > 1 else 0, parts[2] if len(parts) > 2 else 0)
            if cand > best:
                best = cand
    return best


def build_1g1r_canonical_key(game: dict[str, Any], group_by_cloneof: bool = True) -> str:
    """
    Construye una clave canónica para agrupar duplicados regionales/clones sin mezclar multidisco.
    """
    raw_stem = Path(str(game.get("rom_path") or "")).stem or str(game.get("rom_name") or "")
    raw_title = str(game.get("title") or "")
    disc_tag = extract_disc_tag(raw_stem) or extract_disc_tag(raw_title)

    cloneof = str(game.get("cloneof") or "").strip().lower()
    if group_by_cloneof and cloneof:
        return f"mame_family:{cloneof}|{disc_tag}"

    base_text = clean_rom_search_title(raw_title or raw_stem)
    norm_title = normalize_match_key(base_text)
    if not norm_title and raw_stem:
        norm_title = normalize_match_key(clean_rom_search_title(raw_stem))
    return f"title:{norm_title or raw_stem.lower()}|{disc_tag}"


def score_game_for_1g1r(
    game: dict[str, Any],
    region_order: list[str] | tuple[str, ...] = DEFAULT_1G1R_REGION_ORDER,
) -> tuple:
    """Calcula puntuación determinista para elegir el mejor ganador de cada grupo 1G1R."""
    raw_stem = Path(str(game.get("rom_path") or "")).stem or str(game.get("rom_name") or "")
    raw_title = str(game.get("title") or "")
    combined = f"{raw_stem} {raw_title}"

    is_parent = 0 if str(game.get("cloneof") or "").strip() else 1
    is_final_release = 0 if _PRE_RELEASE_RE.search(combined) else 1
    is_verified_good = 1 if "[!]" in combined else 0
    is_clean_dump = 0 if _BAD_DUMP_RE.search(combined) else 1

    region = extract_game_region(game)
    order_norm = [r.lower() for r in region_order]
    try:
        reg_idx = order_norm.index(region.lower())
        region_score = len(order_norm) - reg_idx
    except ValueError:
        region_score = 0

    lang_bonus = 0
    for lm in _LANG_TAG_RE.findall(combined):
        toks = {t.strip().lower() for t in lm.split(",")}
        if "es" in toks or "spa" in toks:
            lang_bonus = max(lang_bonus, 2)
        elif "en" in toks or "eng" in toks:
            lang_bonus = max(lang_bonus, 1)

    rev_score = _extract_revision_score(combined)
    fav = 1 if int(game.get("is_favorite") or 0) else 0
    plays = int(game.get("play_count") or 0)
    rom_path = str(game.get("rom_path") or "")
    exists_on_disk = 1 if (rom_path and Path(rom_path).exists()) else 0
    shorter_name = -len(raw_stem)
    neg_id = -int(game.get("id") or 0)

    return (
        is_parent,
        is_final_release,
        is_verified_good,
        is_clean_dump,
        region_score,
        lang_bonus,
        rev_score,
        fav,
        plays,
        exists_on_disk,
        shorter_name,
        neg_id,
    )


@dataclass
class DuplicateGroup:
    canonical_key: str
    group_label: str
    winner: dict[str, Any]
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    winner_region: str = "Unknown"


def analyze_1g1r_duplicates(
    games: list[dict[str, Any]],
    region_order: list[str] | tuple[str, ...] = DEFAULT_1G1R_REGION_ORDER,
    group_by_cloneof: bool = True,
) -> dict[str, Any]:
    """
    Analiza los juegos de una lista y agrupa clones/duplicados multi-región manteniendo
    intactos los discos separados (`Disc 1`, `Disc 2`) y eligiendo el ganador óptimo.
    """
    clean_games = [dict(g) for g in games]

    # Si group_by_cloneof=True, mapear también las entradas padre cuya rom_name/stem coincide con cloneof
    parent_keys: set[str] = set()
    if group_by_cloneof:
        for g in clean_games:
            cf = str(g.get("cloneof") or "").strip().lower()
            if cf:
                parent_keys.add(cf)

    buckets: dict[str, list[dict[str, Any]]] = {}
    for g in clean_games:
        stem = (Path(str(g.get("rom_path") or "")).stem or str(g.get("rom_name") or "")).strip().lower()
        rom_name = str(g.get("rom_name") or "").strip().lower()
        disc_tag = extract_disc_tag(stem) or extract_disc_tag(str(g.get("title") or ""))

        if group_by_cloneof and not g.get("cloneof") and (stem in parent_keys or rom_name in parent_keys):
            fam = stem if stem in parent_keys else rom_name
            key = f"mame_family:{fam}|{disc_tag}"
        else:
            key = build_1g1r_canonical_key(g, group_by_cloneof=group_by_cloneof)

        buckets.setdefault(key, []).append(g)

    groups: list[DuplicateGroup] = []
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        ranked = sorted(members, key=lambda item: score_game_for_1g1r(item, region_order=region_order), reverse=True)
        winner = ranked[0]
        dups = ranked[1:]
        label = clean_rom_search_title(str(winner.get("title") or Path(str(winner.get("rom_path") or "")).stem)) or key
        groups.append(
            DuplicateGroup(
                canonical_key=key,
                group_label=label,
                winner=winner,
                duplicates=dups,
                winner_region=extract_game_region(winner),
            )
        )

    groups.sort(key=lambda gr: gr.group_label.lower())
    total_duplicates = sum(len(gr.duplicates) for gr in groups)
    return {
        "total_games": len(clean_games),
        "duplicate_groups": groups,
        "total_groups": len(groups),
        "total_duplicates": total_duplicates,
        "unique_1g1r_count": len(clean_games) - total_duplicates,
    }


def _merge_csv_tag(raw_tags: str, tag_name: str, add: bool) -> str:
    tokens = [t.strip() for t in str(raw_tags or "").split(",") if t.strip()]
    lower_target = tag_name.strip().lower()
    filtered = [t for t in tokens if t.lower() != lower_target]
    if add:
        filtered.append(tag_name.strip())
    return ", ".join(filtered)


def tag_1g1r_duplicates(
    db,
    groups: list[DuplicateGroup],
    tag_name: str = "duplicate",
) -> dict[str, int]:
    """
    Etiqueta de forma no destructiva los juegos duplicados con `tag_name` (`duplicate`) y limpia
    dicha etiqueta de los ganadores de cada grupo.
    """
    tagged = 0
    untagged_winners = 0
    batch_ctx = db.batch() if hasattr(db, "batch") else None

    def _apply():
        nonlocal tagged, untagged_winners
        for gr in groups:
            w = gr.winner
            w_old = str(w.get("tags") or "")
            w_new = _merge_csv_tag(w_old, tag_name, add=False)
            if w_new != w_old:
                db.update_game(w["id"], tags=w_new)
                w["tags"] = w_new
                untagged_winners += 1
            for dup in gr.duplicates:
                d_old = str(dup.get("tags") or "")
                d_new = _merge_csv_tag(d_old, tag_name, add=True)
                if d_new != d_old:
                    db.update_game(dup["id"], tags=d_new)
                    dup["tags"] = d_new
                    tagged += 1

    if batch_ctx is not None:
        with batch_ctx:
            _apply()
    else:
        _apply()

    return {"tagged": tagged, "untagged_winners": untagged_winners}


def create_filtered_1g1r_list(
    db,
    source_list_id: int,
    new_list_name: str = "",
    tag_name: str = "duplicate",
) -> int:
    """
    Crea una lista filtrada 1G1R vinculada a `source_list_id` excluyendo juegos con etiqueta `duplicate`.
    """
    src = db.get_list(int(source_list_id))
    if not src:
        raise ValueError(tr("svc.toolkit.err_source_list_not_found", "Source list not found."))

    base_name = (new_list_name or f"{src['name']} (1G1R)").strip()
    existing_names = {str(l.get("name") or "").strip().lower() for l in db.get_lists(with_counts=False)}
    candidate_name = base_name
    counter = 2
    while candidate_name.lower() in existing_names:
        candidate_name = f"{base_name} #{counter}"
        counter += 1

    rules = [{"field": "tags", "operator": "not_contains", "value": tag_name}]
    new_lid = db.add_list(
        name=candidate_name,
        platform=src.get("platform", ""),
        allowed_extensions=src.get("allowed_extensions", ""),
        default_emulator_id=src.get("default_emulator_id"),
        layout=src.get("layout", "Arcade"),
        list_type="filtered",
        roms_path="",
        xml_path="",
        boxart_path=src.get("boxart_path", ""),
        wheel_path=src.get("wheel_path", ""),
        video_path=src.get("video_path", ""),
        cartart_path=src.get("cartart_path", ""),
        flyer_path=src.get("flyer_path", ""),
        cabinet_path=src.get("cabinet_path", ""),
        snap_path=src.get("snap_path", ""),
        title_path=src.get("title_path", ""),
        marquee_path=src.get("marquee_path", ""),
        cpanel_path=src.get("cpanel_path", ""),
        fanart_path=src.get("fanart_path", ""),
        bezel_hud_path=src.get("bezel_hud_path", ""),
        bezel_hud_enabled=src.get("bezel_hud_enabled", 1),
        loading_path=src.get("loading_path", ""),
        manual_path=src.get("manual_path", ""),
        source_list_id=int(source_list_id),
        filter_rules=json.dumps(rules, ensure_ascii=False),
        filter_match_mode="all",
        sort_mode=src.get("sort_mode", "title") or "title",
    )
    sync_filtered_list_games(db, new_lid)
    return new_lid


def remove_duplicates_from_list(db, duplicate_games: list[dict[str, Any]]) -> int:
    """Quita los juegos seleccionados de la lista en PlayNexus SIN borrar ningún archivo del disco."""
    removed = 0
    batch_ctx = db.batch() if hasattr(db, "batch") else None

    def _run():
        nonlocal removed
        for g in duplicate_games:
            gid = int(g["id"])
            db.delete_game(gid)
            removed += 1

    if batch_ctx is not None:
        with batch_ctx:
            _run()
    else:
        _run()
    return removed


def move_duplicate_roms_to_folder(
    db,
    duplicate_games: list[dict[str, Any]],
    dest_folder: str | Path | None = None,
    remove_from_list: bool = True,
) -> dict[str, Any]:
    """
    Mueve físicamente los archivos ROM duplicados a `_duplicates/` (o a `dest_folder`)
    sin borrar archivos permanentemente, y opcionalmente los quita de la lista.
    """
    moved = 0
    skipped = 0
    errors: list[str] = []
    removed_ids: list[int] = []

    custom_dest = Path(dest_folder) if dest_folder else None
    if custom_dest:
        custom_dest.mkdir(parents=True, exist_ok=True)

    for g in duplicate_games:
        rom_str = str(g.get("rom_path") or "").strip()
        if not rom_str:
            skipped += 1
            continue
        src = Path(rom_str)
        if not src.exists():
            skipped += 1
            if remove_from_list and g.get("id") is not None:
                removed_ids.append(int(g["id"]))
            continue

        target_dir = custom_dest if custom_dest else (src.parent / "_duplicates")
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            dst = target_dir / src.name
            if dst.exists() and dst.resolve() != src.resolve():
                idx = 1
                while True:
                    cand = target_dir / f"{src.stem}__dup{idx}{src.suffix}"
                    if not cand.exists():
                        dst = cand
                        break
                    idx += 1
            if src.resolve() == dst.resolve():
                skipped += 1
                continue
            shutil.move(str(src), str(dst))
            moved += 1
            if remove_from_list and g.get("id") is not None:
                removed_ids.append(int(g["id"]))
        except Exception as exc:
            errors.append(f"{src.name}: {exc}")

    if removed_ids and hasattr(db, "delete_game"):
        batch_ctx = db.batch() if hasattr(db, "batch") else None
        if batch_ctx is not None:
            with batch_ctx:
                for gid in removed_ids:
                    db.delete_game(gid)
        else:
            for gid in removed_ids:
                db.delete_game(gid)

    return {
        "moved": moved,
        "skipped": skipped,
        "removed_from_list": len(removed_ids),
        "errors": errors,
    }
