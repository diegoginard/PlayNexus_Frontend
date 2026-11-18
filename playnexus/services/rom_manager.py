"""
Servicio de auditoría y gestión de media por ROM (Rom Manager) para PlayNexus.

Valida las ROMs de una lista contra los requerimientos explícitos (MEDIA_REQUIREMENTS)
declarados en el theme_layout.py (o especificación genérica) del diseño visual elegido.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from playnexus.services.media import IMAGE_EXTS, PDF_EXTS, VIDEO_EXTS, clear_media_cache


_VIDEO_KEYS = {"video", "snap"}
_VIDEO_EXT_SET = {e.lower() for e in VIDEO_EXTS}
_PDF_KEYS = {"manual"}
_PDF_EXT_SET = {e.lower() for e in PDF_EXTS}
_PAREN_TAG_RE = re.compile(r"\s*[\(\[].*?[\)\]]")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class MediaRequirementSpec:
    """Especificación normalizada de un slot de media requerido por un layout."""

    key: str
    label: str
    extensions: tuple[str, ...]
    required: bool
    media_kind: str  # "image" | "video"
    folder_path: str
    folder_exists: bool
    db_field: str
    default_folder_name: str = ""


@dataclass
class SlotAuditResult:
    """Resultado de auditoría para un slot de media específico de una ROM."""

    key: str
    label: str
    status: str  # "ok" | "wrong_ext" | "missing_required" | "missing_optional" | "no_folder"
    file_path: str | None = None
    extension: str = ""
    size_bytes: int = 0
    expected_stem: str = ""
    expected_folder: str = ""
    is_required: bool = False
    media_kind: str = "image"
    note: str = ""


@dataclass
class RomAuditResult:
    """Resultado completo de auditoría de media para una ROM o ítem de menú."""

    game_id: int
    title: str
    rom_path: str
    rom_name: str
    stem: str
    rom_exists: bool
    is_menu_target: bool = False
    platform: str = ""
    slots: dict[str, SlotAuditResult] = field(default_factory=dict)
    missing_required_count: int = 0
    missing_optional_count: int = 0
    wrong_ext_count: int = 0
    present_count: int = 0
    total_slots: int = 0
    overall_status: str = "complete"  # "complete" | "missing_optional" | "missing_required"


@dataclass
class OrphanMediaFile:
    """Archivo presente en una carpeta de media que no coincide con ninguna ROM de la lista."""

    key: str
    filename: str
    stem: str
    extension: str
    file_path: str
    size_bytes: int
    clean_stem: str = ""


@dataclass
class AuditSummary:
    """Resumen completo de auditoría de una lista frente a un layout."""

    list_id: int
    list_name: str
    list_type: str
    layout_name: str
    total_roms: int = 0
    roms_missing_on_disk: int = 0
    complete_roms: int = 0
    ready_roms: int = 0  # Sin faltantes obligatorios (pueden faltar opcionales)
    incomplete_required_roms: int = 0
    specs: list[MediaRequirementSpec] = field(default_factory=list)
    slot_totals: dict[str, dict[str, int]] = field(default_factory=dict)
    orphan_files_by_key: dict[str, list[OrphanMediaFile]] = field(default_factory=dict)
    results: list[RomAuditResult] = field(default_factory=list)


def get_db_field_for_media_key(key: str) -> str:
    """Mapea la clave declarada en MEDIA_REQUIREMENTS a su columna de carpeta en la DB."""
    k = (key or "").strip().lower()
    if k in ("discart", "cartart"):
        return "cartart_path"
    if k in ("video", "snap"):
        return "video_path"
    return f"{k}_path"


def get_list_folder_for_media_key(list_row: dict[str, Any] | None, key: str) -> str:
    """Obtiene la carpeta configurada en la lista para una clave de media."""
    if not list_row:
        return ""
    k = (key or "").strip().lower()
    if k == "discart":
        raw = list_row.get("discart_path") or list_row.get("cartart_path") or ""
    elif k == "cartart":
        raw = list_row.get("cartart_path") or list_row.get("discart_path") or ""
    elif k in ("video", "snap"):
        raw = list_row.get("video_path") or ""
    else:
        raw = list_row.get(f"{k}_path") or ""
    return str(raw).strip().replace("\\", "/")


def infer_media_kind(key: str, extensions: tuple[str, ...]) -> str:
    """Determina si un slot corresponde a imagen, video o manual PDF según clave y extensiones."""
    k = (key or "").strip().lower()
    if k in _VIDEO_KEYS:
        return "video"
    if k in _PDF_KEYS:
        return "pdf"
    if extensions and all(ext.lower() in _VIDEO_EXT_SET for ext in extensions):
        return "video"
    if extensions and all(ext.lower() in _PDF_EXT_SET for ext in extensions):
        return "pdf"
    return "image"


def normalize_extensions_tuple(raw_exts: list[str] | tuple[str, ...] | None, media_kind: str) -> tuple[str, ...]:
    """Normaliza las extensiones declaradas en MEDIA_REQUIREMENTS."""
    default_exts = (
        VIDEO_EXTS if media_kind == "video"
        else (PDF_EXTS if media_kind == "pdf" else IMAGE_EXTS)
    )
    if not raw_exts:
        return default_exts
    out: list[str] = []
    for ext in raw_exts:
        s = str(ext).strip().lower()
        if not s:
            continue
        if not s.startswith("."):
            s = f".{s}"
        if s not in out:
            out.append(s)
    return tuple(out) if out else default_exts


def build_requirement_specs(
    raw_spec: list[dict[str, Any]],
    list_row: dict[str, Any] | None,
) -> list[MediaRequirementSpec]:
    """Convierte el MEDIA_REQUIREMENTS del layout en objetos enriquecidos con carpetas de la lista."""
    specs: list[MediaRequirementSpec] = []
    seen_keys: set[str] = set()
    for item in raw_spec or []:
        key = str(item.get("key") or "").strip().lower()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        raw_exts = item.get("extensions") or []
        tentative_exts = tuple(
            str(e).strip().lower() if str(e).strip().startswith(".") else f".{str(e).strip().lower()}"
            for e in raw_exts if str(e).strip()
        )
        media_kind = infer_media_kind(key, tentative_exts)
        extensions = normalize_extensions_tuple(raw_exts, media_kind)

        folder_path = get_list_folder_for_media_key(list_row, key)
        folder_exists = bool(folder_path and os.path.isdir(folder_path))
        specs.append(
            MediaRequirementSpec(
                key=key,
                label=str(item.get("label") or key.capitalize()),
                extensions=extensions,
                required=bool(item.get("required", False)),
                media_kind=media_kind,
                folder_path=folder_path,
                folder_exists=folder_exists,
                db_field=get_db_field_for_media_key(key),
                default_folder_name=str(item.get("folder") or key).strip(),
            )
        )
    return specs


def _scan_folder_index(folder_path: str) -> dict[str, list[tuple[str, str, int, str]]]:
    """
    Escanea una carpeta una sola vez y retorna:
      {stem_lower: [(ext_lower, normalized_full_path, size_bytes, actual_filename), ...]}
    """
    by_stem: dict[str, list[tuple[str, str, int, str]]] = {}
    if not folder_path or not os.path.isdir(folder_path):
        return by_stem

    try:
        for entry in os.scandir(folder_path):
            if not entry.is_file():
                continue
            name = entry.name
            stem, ext = os.path.splitext(name)
            if not stem:
                continue
            ext_low = ext.lower()
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            full_path = entry.path.replace("\\", "/")
            by_stem.setdefault(stem.lower(), []).append((ext_low, full_path, size, name))
    except OSError:
        pass
    return by_stem


def _menu_candidate_stems(game: dict[str, Any]) -> list[str]:
    """Genera nombres candidatos para ítems de Menú de Sistemas (mismo criterio que resolve_game_media)."""
    sys_name = str(game.get("title") or "").strip()
    plat_name = str(game.get("platform") or "").strip()
    candidates: list[str] = []
    for n in (sys_name, plat_name):
        if not n:
            continue
        for variant in (
            n,
            re.sub(r"\s*\(.*?\)", "", n).strip(),
            n.replace("/", " - ").replace("\\", " - ").strip(),
        ):
            if variant and variant not in candidates:
                candidates.append(variant)
    return candidates


def _clean_match_text(text: str) -> str:
    """Normaliza títulos y nombres de ROM para comparación difusa rápida."""
    if not text:
        return ""
    s = _PAREN_TAG_RE.sub(" ", text.lower())
    s = s.replace(", the", " ").strip()
    if s.startswith("the "):
        s = s[4:]
    s = _NON_ALNUM_RE.sub(" ", s).strip()
    return s


def _match_slot_from_index(
    spec: MediaRequirementSpec,
    by_stem: dict[str, list[tuple[str, str, int, str]]],
    candidate_stems: list[str],
    primary_stem: str,
    game: dict[str, Any],
) -> tuple[SlotAuditResult, set[str]]:
    """Evalúa un slot puntual contra el índice en memoria de su carpeta."""
    matched_stem_keys: set[str] = set()

    if not spec.folder_exists:
        note = (
            f"La carpeta configurada no existe en disco: {spec.folder_path}"
            if spec.folder_path
            else "Carpeta no configurada en la lista"
        )
        return (
            SlotAuditResult(
                key=spec.key,
                label=spec.label,
                status="no_folder",
                expected_stem=primary_stem,
                expected_folder=spec.folder_path,
                is_required=spec.required,
                media_kind=spec.media_kind,
                note=note,
            ),
            matched_stem_keys,
        )

    fallback_exts = (
        VIDEO_EXTS if spec.media_kind == "video"
        else (PDF_EXTS if spec.media_kind == "pdf" else IMAGE_EXTS)
    )

    # 1. Búsqueda estricta por orden de extensiones definidas en MEDIA_REQUIREMENTS
    for cand in candidate_stems:
        entries = by_stem.get(cand.lower())
        if not entries:
            continue
        ext_map = {ext: (path, size) for ext, path, size, _ in entries}
        for ext in spec.extensions:
            if ext in ext_map:
                path, size = ext_map[ext]
                matched_stem_keys.add(cand.lower())
                return (
                    SlotAuditResult(
                        key=spec.key,
                        label=spec.label,
                        status="ok",
                        file_path=path,
                        extension=ext,
                        size_bytes=size,
                        expected_stem=primary_stem,
                        expected_folder=spec.folder_path,
                        is_required=spec.required,
                        media_kind=spec.media_kind,
                    ),
                    matched_stem_keys,
                )

    # 2. Búsqueda secundaria: existe el archivo con otra extensión compatible (ej. .jpg donde pide .png)
    for cand in candidate_stems:
        entries = by_stem.get(cand.lower())
        if not entries:
            continue
        ext_map = {ext: (path, size) for ext, path, size, _ in entries}
        for ext in fallback_exts:
            if ext in ext_map:
                path, size = ext_map[ext]
                matched_stem_keys.add(cand.lower())
                expected_str = ", ".join(spec.extensions)
                return (
                    SlotAuditResult(
                        key=spec.key,
                        label=spec.label,
                        status="wrong_ext",
                        file_path=path,
                        extension=ext,
                        size_bytes=size,
                        expected_stem=primary_stem,
                        expected_folder=spec.folder_path,
                        is_required=spec.required,
                        media_kind=spec.media_kind,
                        note=f"Encontrado como '{ext}', el layout declara: {expected_str}",
                    ),
                    matched_stem_keys,
                )

    # 3. Faltante
    missing_status = "missing_required" if spec.required else "missing_optional"
    note = ""
    if spec.key == "boxart" and game.get("cover_path") and os.path.isfile(str(game["cover_path"])):
        note = "Sin archivo en carpeta boxart (usa carátula manual cover_path)"

    return (
        SlotAuditResult(
            key=spec.key,
            label=spec.label,
            status=missing_status,
            expected_stem=primary_stem,
            expected_folder=spec.folder_path,
            is_required=spec.required,
            media_kind=spec.media_kind,
            note=note,
        ),
        matched_stem_keys,
    )


def audit_list_media(
    list_row: dict[str, Any],
    games: list[dict[str, Any]],
    raw_spec: list[dict[str, Any]],
    layout_name: str,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> AuditSummary:
    """
    Audita todas las ROMs/ítems de una lista contra los requerimientos explícitos
    del layout indicado. Diseñada para ejecutarse tanto sincrónicamente como en QThread.
    """
    list_id = int(list_row.get("id") or 0)
    list_name = str(list_row.get("name") or "")
    list_type = str(list_row.get("list_type") or "games")

    specs = build_requirement_specs(raw_spec, list_row)
    summary = AuditSummary(
        list_id=list_id,
        list_name=list_name,
        list_type=list_type,
        layout_name=layout_name,
        total_roms=len(games),
        specs=specs,
    )

    # Inicializar contadores por columna
    for s in specs:
        summary.slot_totals[s.key] = {
            "present": 0,
            "wrong_ext": 0,
            "missing": 0,
            "no_folder": 0,
            "total": len(games),
        }

    # Indexar en memoria cada carpeta una sola vez
    folder_indices: dict[str, dict[str, list[tuple[str, str, int, str]]]] = {}
    matched_stems: dict[str, set[str]] = {s.key: set() for s in specs}

    for idx_s, s in enumerate(specs):
        if cancel_check and cancel_check():
            return summary
        if s.folder_exists:
            norm_dir = os.path.normcase(os.path.abspath(s.folder_path))
            if norm_dir not in folder_indices:
                if progress_cb:
                    progress_cb(idx_s, max(1, len(specs)), f"Indexando carpeta de {s.label}…")
                folder_indices[norm_dir] = _scan_folder_index(s.folder_path)

    total = len(games)
    is_menu = (list_type == "menu")

    for i, game in enumerate(games):
        if cancel_check and cancel_check():
            break

        if progress_cb and (i == 0 or (i + 1) % 50 == 0 or i + 1 == total):
            progress_cb(i + 1, max(1, total), f"Auditando {i + 1}/{total}: {game.get('title', '')}")

        rom_path = str(game.get("rom_path") or "").strip()
        rom_name = str(game.get("rom_name") or "").strip()
        title = str(game.get("title") or "").strip()
        is_target_menu = bool(game.get("is_menu_target") or is_menu)

        if is_target_menu or not rom_path:
            cand_stems = _menu_candidate_stems(game)
            primary_stem = cand_stems[0] if cand_stems else (rom_name or title)
            rom_exists = True if is_target_menu else False
        else:
            primary_stem = Path(rom_path).stem
            cand_stems = [primary_stem] if primary_stem else []
            rom_exists = os.path.exists(rom_path)

        if not rom_exists and not is_target_menu:
            summary.roms_missing_on_disk += 1

        slots_res: dict[str, SlotAuditResult] = {}
        missing_req = 0
        missing_opt = 0
        wrong_ext = 0
        present = 0

        for spec in specs:
            if spec.folder_exists:
                norm_dir = os.path.normcase(os.path.abspath(spec.folder_path))
                by_stem = folder_indices.get(norm_dir, {})
            else:
                by_stem = {}

            slot_res, m_stems = _match_slot_from_index(spec, by_stem, cand_stems, primary_stem, game)
            matched_stems[spec.key].update(m_stems)
            slots_res[spec.key] = slot_res

            totals = summary.slot_totals[spec.key]
            if slot_res.status == "ok":
                present += 1
                totals["present"] += 1
            elif slot_res.status == "wrong_ext":
                present += 1
                wrong_ext += 1
                totals["present"] += 1
                totals["wrong_ext"] += 1
            elif slot_res.status == "no_folder":
                totals["no_folder"] += 1
                totals["missing"] += 1
                if spec.required:
                    missing_req += 1
                else:
                    missing_opt += 1
            elif slot_res.status == "missing_required":
                totals["missing"] += 1
                missing_req += 1
            else:
                totals["missing"] += 1
                missing_opt += 1

        if missing_req > 0:
            overall = "missing_required"
            summary.incomplete_required_roms += 1
        elif missing_opt > 0:
            overall = "missing_optional"
            summary.ready_roms += 1
        else:
            overall = "complete"
            summary.ready_roms += 1
            summary.complete_roms += 1

        summary.results.append(
            RomAuditResult(
                game_id=int(game.get("id") or 0),
                title=title or primary_stem,
                rom_path=rom_path,
                rom_name=rom_name,
                stem=primary_stem,
                rom_exists=rom_exists,
                is_menu_target=is_target_menu,
                platform=str(game.get("platform") or ""),
                slots=slots_res,
                missing_required_count=missing_req,
                missing_optional_count=missing_opt,
                wrong_ext_count=wrong_ext,
                present_count=present,
                total_slots=len(specs),
                overall_status=overall,
            )
        )

    # Identificar archivos huérfanos en las carpetas para sugerencias de renombrado
    valid_exts_by_kind = {
        "video": set(VIDEO_EXTS),
        "pdf": set(PDF_EXTS),
        "image": set(IMAGE_EXTS),
    }
    for spec in specs:
        if not spec.folder_exists:
            summary.orphan_files_by_key[spec.key] = []
            continue
        norm_dir = os.path.normcase(os.path.abspath(spec.folder_path))
        by_stem = folder_indices.get(norm_dir, {})
        used_stems = matched_stems.get(spec.key, set())
        allowed_kind_exts = valid_exts_by_kind[spec.media_kind] | set(spec.extensions)

        orphans: list[OrphanMediaFile] = []
        for stem_low, entries in by_stem.items():
            if stem_low in used_stems:
                continue
            for ext_low, full_path, size, fname in entries:
                if ext_low not in allowed_kind_exts:
                    continue
                stem_real = os.path.splitext(fname)[0]
                orphans.append(
                    OrphanMediaFile(
                        key=spec.key,
                        filename=fname,
                        stem=stem_real,
                        extension=ext_low,
                        file_path=full_path,
                        size_bytes=size,
                        clean_stem=_clean_match_text(stem_real),
                    )
                )
        orphans.sort(key=lambda o: o.filename.lower())
        summary.orphan_files_by_key[spec.key] = orphans

    return summary


def find_fuzzy_media_candidates(
    target_stem: str,
    target_title: str,
    orphans: list[OrphanMediaFile],
    min_score: float = 0.58,
    limit: int = 5,
) -> list[tuple[OrphanMediaFile, float]]:
    """Busca archivos huérfanos con nombre parecido al de la ROM/título."""
    if not orphans:
        return []

    clean_stem = _clean_match_text(target_stem)
    clean_title = _clean_match_text(target_title)
    if not clean_stem and not clean_title:
        return []

    scored: list[tuple[OrphanMediaFile, float]] = []
    for orp in orphans:
        cand = orp.clean_stem or _clean_match_text(orp.stem)
        if not cand:
            continue

        if cand == clean_stem or (clean_title and cand == clean_title):
            score = 0.99
        else:
            best = 0.0
            for q in (clean_stem, clean_title):
                if not q:
                    continue
                sm = SequenceMatcher(None, q, cand)
                if sm.quick_ratio() < min_score:
                    continue
                r = sm.ratio()
                if r > best:
                    best = r
            score = best

        if score >= min_score:
            scored.append((orp, score))

    scored.sort(key=lambda pair: (-pair[1], pair[0].filename.lower()))
    return scored[:limit]


def _unlink_with_retry(target: Path) -> None:
    """Elimina un archivo con reintentos breves por si Windows Media Foundation aún libera el handle."""
    delays = (0.04, 0.08, 0.15)
    for idx in range(len(delays) + 1):
        try:
            if target.is_file():
                target.unlink()
            return
        except PermissionError:
            if idx >= len(delays):
                raise
            time.sleep(delays[idx])


def assign_media_file(
    source_path: str,
    target_folder: str,
    target_stem: str,
    remove_existing_for_stem: bool = True,
    allowed_exts: tuple[str, ...] | None = None,
    move: bool = False,
) -> str:
    """
    Copia (o mueve) un archivo multimedia hacia la carpeta de media destino,
    renombrándolo exactamente a `<target_stem><ext>` para que el layout lo reconozca.
    """
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(f"No se encontró el archivo origen:\n{source_path}")
    if not target_stem:
        raise ValueError("No se pudo determinar el nombre base (stem) destino para la ROM.")

    dest_dir = Path(target_folder)
    if not dest_dir.is_dir():
        raise FileNotFoundError(f"La carpeta destino no existe:\n{target_folder}")

    ext = src.suffix.lower()
    if allowed_exts and ext not in {e.lower() for e in allowed_exts}:
        raise ValueError(
            f"La extensión '{ext}' no es compatible con este tipo de medio.\n"
            f"Extensiones aceptadas: {', '.join(allowed_exts)}"
        )

    dest = dest_dir / f"{target_stem}{ext}"

    if remove_existing_for_stem:
        stem_low = target_stem.lower()
        try:
            for entry in os.scandir(dest_dir):
                if not entry.is_file():
                    continue
                e_stem, _ = os.path.splitext(entry.name)
                if e_stem.lower() == stem_low:
                    existing_p = Path(entry.path)
                    if existing_p.resolve() != src.resolve():
                        _unlink_with_retry(existing_p)
        except OSError as exc:
            if isinstance(exc, PermissionError):
                raise

    if src.resolve() != dest.resolve():
        delays = (0.04, 0.08, 0.15)
        for idx in range(len(delays) + 1):
            try:
                if move:
                    shutil.move(str(src), str(dest))
                else:
                    shutil.copy2(str(src), str(dest))
                break
            except PermissionError:
                if idx >= len(delays):
                    raise
                time.sleep(delays[idx])

    clear_media_cache()
    return str(dest).replace("\\", "/")


def rename_orphan_media_file(source_path: str, target_stem: str) -> str:
    """Renombra un archivo multimedia existente dentro de su misma carpeta a `<target_stem><ext>`."""
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(f"El archivo ya no existe:\n{source_path}")
    if not target_stem:
        raise ValueError("El nombre destino está vacío.")
    dest = src.parent / f"{target_stem}{src.suffix.lower()}"
    if src.resolve() != dest.resolve():
        os.replace(str(src), str(dest))
    clear_media_cache()
    return str(dest).replace("\\", "/")


def delete_media_file(file_path: str) -> None:
    """Elimina de disco un archivo de media puntual y limpia la caché."""
    _unlink_with_retry(Path(file_path))
    clear_media_cache()


_PROTECTED_SHARED_STEMS: frozenset[str] = frozenset({
    "default",
    "default_v",
    "default_i",
    "default_in",
    "default_o",
    "default_out",
    "base",
    "generic",
    "bezel",
    "loading",
    "loading_i",
    "loading_in",
    "loading_o",
    "loading_out",
    "exit",
    "splash",
    "outro",
})

_ALL_LIST_MEDIA_FOLDERS: tuple[tuple[str, str, bool], ...] = (
    ("boxart_path", "Box Art", False),
    ("flyer_path", "Flyer", False),
    ("wheel_path", "Wheel / Logo", False),
    ("video_path", "Video / Snap", False),
    ("cartart_path", "Cart Art / Disc Art", False),
    ("discart_path", "Disc Art", False),
    ("cabinet_path", "Cabinet", False),
    ("marquee_path", "Marquee", False),
    ("bezel_path", "Bezel", False),
    ("manual_path", "Manual PDF", False),
    ("bezel_hud_path", "Bezel HUD", False),
    ("loading_path", "Pantalla de carga", True),
    ("loading_in_path", "Carga (entrada)", True),
    ("loading_out_path", "Carga (salida)", True),
)

_KNOWN_MEDIA_SUBFOLDERS: tuple[tuple[str, str], ...] = (
    ("boxart", "Box Art"),
    ("boxarts", "Box Art"),
    ("flyer", "Flyer"),
    ("flyers", "Flyer"),
    ("wheel", "Wheel / Logo"),
    ("wheels", "Wheel / Logo"),
    ("video", "Video / Snap"),
    ("videos", "Video / Snap"),
    ("snap", "Video / Snap"),
    ("snaps", "Video / Snap"),
    ("cartart", "Cart Art / Disc Art"),
    ("cartarts", "Cart Art / Disc Art"),
    ("discart", "Disc Art"),
    ("discarts", "Disc Art"),
    ("cabinet", "Cabinet"),
    ("cabinets", "Cabinet"),
    ("marquee", "Marquee"),
    ("marquees", "Marquee"),
    ("bezel", "Bezel"),
    ("bezels", "Bezel"),
    ("manual", "Manual PDF"),
    ("manuals", "Manual PDF"),
    ("fanart", "Fanart"),
    ("fanarts", "Fanart"),
)


@dataclass
class DeletionFileTarget:
    """Archivo en disco candidato a eliminarse junto con un juego."""

    category: str  # "rom" | "media"
    label: str
    file_path: str
    size_bytes: int
    slot_key: str = ""
    is_rom: bool = False


@dataclass
class GameDeletionPlan:
    """Plan completo de archivos físicos y referencias en listas asociados a un juego."""

    game_id: int
    list_id: int
    title: str
    stem: str
    rom_path: str
    rom_target: DeletionFileTarget | None = None
    media_targets: list[DeletionFileTarget] = field(default_factory=list)
    empty_dirs_to_cleanup: list[str] = field(default_factory=list)
    other_list_refs: list[tuple[int, int, str, str]] = field(default_factory=list)

    @property
    def all_targets(self) -> list[DeletionFileTarget]:
        out: list[DeletionFileTarget] = []
        if self.rom_target is not None:
            out.append(self.rom_target)
        out.extend(self.media_targets)
        return out

    @property
    def total_bytes(self) -> int:
        return sum(max(0, int(t.size_bytes or 0)) for t in self.all_targets)


def _norm_fs_key(path: str | Path) -> str:
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except OSError:
        return os.path.normcase(os.path.abspath(str(path)))


def _matches_game_stem(filename: str, candidate_stems: set[str], allow_loading_suffix: bool = False) -> bool:
    name_low = filename.lower()
    if name_low.endswith(".bak"):
        name_low = name_low[:-4]
    f_stem = os.path.splitext(name_low)[0]
    if f_stem in _PROTECTED_SHARED_STEMS:
        return False
    if f_stem in candidate_stems:
        return True
    if allow_loading_suffix:
        for st in candidate_stems:
            if f_stem in (f"{st}_i", f"{st}_o", f"{st}_in", f"{st}_out"):
                return True
    return False


def collect_game_deletion_targets(
    db: Any,
    list_row: dict[str, Any] | None,
    rom: RomAuditResult,
    game_row: dict[str, Any] | None = None,
    specs: list[MediaRequirementSpec] | None = None,
) -> GameDeletionPlan:
    """
    Reúne el archivo ROM en disco, todas las artes/manuales/videos del juego en las carpetas
    configuradas (sin tocar archivos genéricos compartidos) y referencias en otras listas.
    """
    if rom.is_menu_target:
        raise ValueError("Los ítems de menú de sistemas no se pueden eliminar desde disco.")

    if game_row is None and db is not None and hasattr(db, "get_game"):
        try:
            g_db = db.get_game(int(rom.game_id))
            if g_db:
                game_row = dict(g_db)
        except Exception:
            game_row = None

    list_id = int((list_row or {}).get("id") or (game_row or {}).get("list_id") or 0)
    rom_path = str((game_row or {}).get("rom_path") or rom.rom_path or "").strip()
    primary_stem = (rom.stem or (Path(rom_path).stem if rom_path else "") or str((game_row or {}).get("rom_name") or "")).strip()

    candidate_stems: set[str] = set()
    for raw_st in (rom.stem, Path(rom_path).stem if rom_path else "", str((game_row or {}).get("rom_name") or "").strip()):
        s = str(raw_st or "").strip().lower()
        if s:
            candidate_stems.add(s)

    plan = GameDeletionPlan(
        game_id=int(rom.game_id),
        list_id=list_id,
        title=rom.title or primary_stem or "Juego",
        stem=primary_stem,
        rom_path=rom_path,
    )

    seen_files: set[str] = set()

    if rom_path and os.path.isfile(rom_path):
        try:
            r_size = int(os.path.getsize(rom_path))
        except OSError:
            r_size = 0
        seen_files.add(_norm_fs_key(rom_path))
        plan.rom_target = DeletionFileTarget(
            category="rom",
            label="Archivo ROM",
            file_path=rom_path.replace("\\", "/"),
            size_bytes=r_size,
            is_rom=True,
        )

    def _add_media_file(path_str: str, label: str, slot_key: str = "") -> None:
        if not path_str or not os.path.isfile(path_str):
            return
        fk = _norm_fs_key(path_str)
        if fk in seen_files:
            return
        seen_files.add(fk)
        try:
            sz = int(os.path.getsize(path_str))
        except OSError:
            sz = 0
        final_label = f"{label} (respaldo .bak)" if path_str.lower().endswith(".bak") else label
        plan.media_targets.append(
            DeletionFileTarget(
                category="media",
                label=final_label,
                file_path=str(path_str).replace("\\", "/"),
                size_bytes=sz,
                slot_key=slot_key,
                is_rom=False,
            )
        )

    # 1. Archivos ya detectados en los slots del layout actual (solo si pertenecen al stem del juego)
    for sp_key, slot in (rom.slots or {}).items():
        fp = str(slot.file_path or "").strip()
        if not fp or not os.path.isfile(fp):
            continue
        fname = os.path.basename(fp)
        f_stem = os.path.splitext(fname.lower())[0]
        if f_stem in _PROTECTED_SHARED_STEMS:
            continue
        if candidate_stems and not _matches_game_stem(fname, candidate_stems, allow_loading_suffix=True):
            continue
        _add_media_file(fp, slot.label or sp_key, slot_key=sp_key)

    # 2. Barrido de todas las carpetas de medios configuradas en la lista + media_path + specs
    scanned_dirs: set[str] = set()

    def _scan_dir_for_stem(folder_str: str, label: str, slot_key: str = "", is_loading: bool = False) -> None:
        if not folder_str or not candidate_stems or not os.path.isdir(folder_str):
            return
        dk = _norm_fs_key(folder_str)
        if dk in scanned_dirs:
            return
        scanned_dirs.add(dk)
        try:
            for entry in os.scandir(folder_str):
                if entry.is_file():
                    if _matches_game_stem(entry.name, candidate_stems, allow_loading_suffix=is_loading):
                        _add_media_file(entry.path, label, slot_key=slot_key)
                elif is_loading and entry.is_dir():
                    if entry.name.lower() in candidate_stems and entry.name.lower() not in _PROTECTED_SHARED_STEMS:
                        plan.empty_dirs_to_cleanup.append(str(entry.path).replace("\\", "/"))
                        try:
                            for sub_entry in os.scandir(entry.path):
                                if sub_entry.is_file():
                                    _add_media_file(sub_entry.path, label, slot_key=slot_key)
                        except OSError:
                            pass
        except OSError:
            pass

    if specs:
        for sp in specs:
            if sp.folder_path:
                _scan_dir_for_stem(sp.folder_path, sp.label, slot_key=sp.key, is_loading=(sp.key == "loading"))

    if list_row:
        for field_key, lbl, is_load in _ALL_LIST_MEDIA_FOLDERS:
            folder_val = str(list_row.get(field_key) or "").strip()
            if folder_val:
                _scan_dir_for_stem(folder_val, lbl, slot_key=field_key.removesuffix("_path"), is_loading=is_load)

        media_root = str(list_row.get("media_path") or "").strip()
        if media_root and os.path.isdir(media_root):
            mr_path = Path(media_root)
            for sub_name, lbl in _KNOWN_MEDIA_SUBFOLDERS:
                cand_sub = mr_path / sub_name
                if cand_sub.is_dir():
                    _scan_dir_for_stem(str(cand_sub), lbl, slot_key=sub_name.rstrip("s"))

    # 3. Rutas individuales del juego (cover_path / manual_file_path)
    if game_row:
        for g_field, lbl, s_key in (("cover_path", "Carátula asignada", "boxart"), ("manual_file_path", "Manual PDF asignado", "manual")):
            fp = str(game_row.get(g_field) or "").strip()
            if not fp or not os.path.isfile(fp):
                continue
            f_stem = os.path.splitext(os.path.basename(fp).lower())[0]
            if f_stem in _PROTECTED_SHARED_STEMS:
                continue
            _add_media_file(fp, lbl, slot_key=s_key)

    # 4. Detectar referencias de la misma ROM en otras listas (incluyendo listas filtradas o hermanas)
    if db is not None and rom_path and hasattr(db, "get_lists") and hasattr(db, "get_games"):
        target_rom_key = _norm_fs_key(rom_path)
        try:
            for lst in db.get_lists(with_counts=False):
                if lst.get("list_type") == "menu":
                    continue
                other_lid = int(lst["id"])
                for og in db.get_games(other_lid, enriched=False):
                    og_id = int(og["id"])
                    if og_id == plan.game_id:
                        continue
                    og_rom = str(og.get("rom_path") or "").strip()
                    if og_rom and _norm_fs_key(og_rom) == target_rom_key:
                        plan.other_list_refs.append((
                            og_id,
                            other_lid,
                            str(lst.get("name") or f"Lista {other_lid}"),
                            str(lst.get("list_type") or "games"),
                        ))
        except Exception:
            pass

    return plan


def delete_game_and_assets(
    db: Any,
    plan: GameDeletionPlan,
    selected_paths: list[str] | set[str] | None = None,
    *,
    delete_rom: bool = True,
    delete_media: bool = True,
    remove_other_list_refs: bool = True,
) -> dict[str, Any]:
    """
    Elimina físicamente del disco los archivos confirmados (ROM + artes) y borra el registro de la lista.
    Si el archivo ROM fue eliminado o ya no existe, opcionalmente limpia entradas huérfanas en otras listas.
    """
    allowed_keys: set[str] | None = None
    if selected_paths is not None:
        allowed_keys = {_norm_fs_key(p) for p in selected_paths if str(p).strip()}

    targets_to_delete: list[DeletionFileTarget] = []
    if allowed_keys is not None:
        for t in plan.all_targets:
            if _norm_fs_key(t.file_path) in allowed_keys:
                targets_to_delete.append(t)
    else:
        if delete_rom and plan.rom_target is not None:
            targets_to_delete.append(plan.rom_target)
        if delete_media:
            targets_to_delete.extend(plan.media_targets)

    deleted_files: list[str] = []
    deleted_rom = False
    deleted_media_count = 0
    errors: list[str] = []

    for tgt in targets_to_delete:
        p = Path(tgt.file_path)
        if not p.is_file():
            continue
        try:
            _unlink_with_retry(p)
            deleted_files.append(tgt.file_path)
            if tgt.is_rom:
                deleted_rom = True
            else:
                deleted_media_count += 1
        except Exception as exc:
            errors.append(f"{tgt.label} ({p.name}): {exc}")

    # Limpiar subcarpetas exclusivas del juego (ej. loading_path/<stem>) si quedaron vacías
    for dir_str in plan.empty_dirs_to_cleanup:
        d = Path(dir_str)
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    rom_gone = deleted_rom or (not plan.rom_path) or (not os.path.isfile(plan.rom_path))
    removed_game_ids: list[int] = []
    affected_list_ids: set[int] = {plan.list_id}

    if db is not None and hasattr(db, "delete_game"):
        gids_to_remove = [plan.game_id]
        if remove_other_list_refs and rom_gone and plan.other_list_refs:
            for og_id, ol_id, _ol_name, _ol_type in plan.other_list_refs:
                if og_id not in gids_to_remove:
                    gids_to_remove.append(og_id)
                affected_list_ids.add(ol_id)

        batch_ctx = db.batch() if hasattr(db, "batch") else None
        if batch_ctx is not None:
            with batch_ctx:
                for gid in gids_to_remove:
                    db.delete_game(gid)
                    removed_game_ids.append(gid)
        else:
            for gid in gids_to_remove:
                db.delete_game(gid)
                removed_game_ids.append(gid)

        if rom_gone:
            try:
                from playnexus.services.library import sync_filtered_lists_for_source
                sync_filtered_lists_for_source(db, None)
            except Exception:
                pass

    clear_media_cache()
    return {
        "deleted_rom": deleted_rom,
        "deleted_media_count": deleted_media_count,
        "deleted_files": deleted_files,
        "removed_game_ids": removed_game_ids,
        "affected_list_ids": sorted(affected_list_ids),
        "errors": errors,
    }


def _resolve_target_rom_directory(list_row: dict[str, Any] | None, old_rom_path: str) -> Path | None:
    if old_rom_path:
        old_parent = Path(old_rom_path).parent
        if old_parent.is_dir():
            return old_parent
    roms_raw = str((list_row or {}).get("roms_path") or "").strip()
    if roms_raw:
        for chunk in roms_raw.split(";"):
            c_str = chunk.strip()
            if c_str and Path(c_str).is_dir():
                return Path(c_str)
    if old_rom_path:
        return Path(old_rom_path).parent
    return None


def replace_game_rom_file(
    db: Any,
    list_row: dict[str, Any] | None,
    rom: RomAuditResult,
    new_rom_source_path: str,
    *,
    keep_existing_stem: bool = True,
    copy_to_list_folder: bool = True,
    remove_old_rom: bool = True,
    rename_media_on_new_stem: bool = False,
) -> dict[str, Any]:
    """
    Reemplaza el archivo ROM de un juego manteniendo opcionalmente el stem existente (para conservar
    todas sus artes sin perder coincidencias) o actualizando la ruta/stem y renombrando sus medios.
    """
    if rom.is_menu_target:
        raise ValueError("No se puede reemplazar la ROM de un ítem de menú.")

    src = Path(new_rom_source_path)
    if not src.is_file():
        raise FileNotFoundError(f"No se encontró el archivo ROM seleccionado:\n{new_rom_source_path}")

    old_rom_path = str(rom.rom_path or "").strip()
    old_stem = (rom.stem or (Path(old_rom_path).stem if old_rom_path else "")).strip()
    target_dir = _resolve_target_rom_directory(list_row, old_rom_path)

    if keep_existing_stem and old_stem:
        dest_dir = target_dir or src.parent
        dest_path = dest_dir / f"{old_stem}{src.suffix}"
    elif copy_to_list_folder and target_dir is not None:
        dest_path = target_dir / src.name
    else:
        dest_path = src

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Capturar referencias y artes del stem previo antes de modificar DB o archivos
    pre_plan = collect_game_deletion_targets(db, list_row, rom)
    old_game_row = dict(db.get_game(int(rom.game_id)) or {}) if (db is not None and hasattr(db, "get_game")) else {}

    # Copia atómica segura mediante archivo temporal si el origen difiere del destino
    if _norm_fs_key(src) != _norm_fs_key(dest_path):
        tmp_dest = dest_path.parent / f"{dest_path.name}.__rom_tmp__.{os.getpid()}"
        try:
            shutil.copy2(str(src), str(tmp_dest))
            os.replace(str(tmp_dest), str(dest_path))
        finally:
            if tmp_dest.is_file():
                try:
                    tmp_dest.unlink()
                except OSError:
                    pass

    if not dest_path.is_file():
        raise IOError(f"No se pudo escribir el archivo ROM destino:\n{dest_path}")

    old_removed = False
    warnings: list[str] = []
    if (
        remove_old_rom
        and old_rom_path
        and os.path.isfile(old_rom_path)
        and _norm_fs_key(old_rom_path) != _norm_fs_key(dest_path)
    ):
        try:
            _unlink_with_retry(Path(old_rom_path))
            old_removed = True
        except Exception as exc:
            warnings.append(f"No se pudo eliminar la ROM anterior ({Path(old_rom_path).name}): {exc}")

    new_rom_str = str(dest_path).replace("\\", "/")
    new_stem = dest_path.stem
    stem_changed = bool(old_stem) and (new_stem.lower() != old_stem.lower())

    renamed_media = 0
    extra_db_updates: dict[str, Any] = {}
    old_cov_key = _norm_fs_key(old_game_row.get("cover_path", "")) if old_game_row.get("cover_path") else ""
    old_man_key = _norm_fs_key(old_game_row.get("manual_file_path", "")) if old_game_row.get("manual_file_path") else ""

    if (not keep_existing_stem) and rename_media_on_new_stem and stem_changed:
        for tgt in pre_plan.media_targets:
            mp = Path(tgt.file_path)
            if not mp.is_file():
                continue
            low_name = mp.name.lower()
            if low_name.endswith(".bak"):
                inner = mp.name[:-4]
                _, ext = os.path.splitext(inner)
                dst_media = mp.parent / f"{new_stem}{ext}.bak"
            else:
                dst_media = mp.parent / f"{new_stem}{mp.suffix}"
            if _norm_fs_key(mp) == _norm_fs_key(dst_media):
                continue
            if dst_media.exists():
                warnings.append(f"Ya existe {dst_media.name}; se conservó {mp.name}.")
                continue
            try:
                os.replace(str(mp), str(dst_media))
                renamed_media += 1
                new_m_str = str(dst_media).replace("\\", "/")
                if old_cov_key and _norm_fs_key(tgt.file_path) == old_cov_key:
                    extra_db_updates["cover_path"] = new_m_str
                if old_man_key and _norm_fs_key(tgt.file_path) == old_man_key:
                    extra_db_updates["manual_file_path"] = new_m_str
            except Exception as exc:
                warnings.append(f"No se pudo renombrar {mp.name}: {exc}")

    if db is not None and hasattr(db, "update_game"):
        updates = {"rom_path": new_rom_str, "rom_name": new_stem, **extra_db_updates}
        batch_ctx = db.batch() if hasattr(db, "batch") else None
        if batch_ctx is not None:
            with batch_ctx:
                db.update_game(rom.game_id, **updates)
                for og_id, _ol_id, _ol_name, _ol_type in pre_plan.other_list_refs:
                    db.update_game(og_id, **updates)
        else:
            db.update_game(rom.game_id, **updates)
            for og_id, _ol_id, _ol_name, _ol_type in pre_plan.other_list_refs:
                db.update_game(og_id, **updates)

        try:
            from playnexus.services.library import sync_filtered_lists_for_source
            sync_filtered_lists_for_source(db, None)
        except Exception:
            pass

    clear_media_cache()
    return {
        "new_rom_path": new_rom_str,
        "new_stem": new_stem,
        "old_removed": old_removed,
        "renamed_media": renamed_media,
        "warnings": warnings,
    }


def export_audit_csv(summary: AuditSummary, output_path: str, only_incomplete: bool = False) -> int:
    """Exporta la tabla de auditoría de media a CSV compatible con Excel (UTF-8 BOM)."""
    rows_to_export = (
        [r for r in summary.results if r.overall_status != "complete"]
        if only_incomplete
        else summary.results
    )

    headers = ["Estado", "Titulo", "ROM (stem)", "ROM en disco", "Ruta ROM"]
    for spec in summary.specs:
        req_tag = " (Obligatorio)" if spec.required else " (Opcional)"
        headers.append(f"{spec.label}{req_tag}")

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(headers)
        for item in rows_to_export:
            status_map = {
                "complete": "Completo",
                "missing_optional": "Falta opcional",
                "missing_required": "Falta obligatorio",
            }
            line = [
                status_map.get(item.overall_status, item.overall_status),
                item.title,
                item.stem,
                "Si" if item.rom_exists else "No encontrada",
                item.rom_path,
            ]
            for spec in summary.specs:
                slot = item.slots.get(spec.key)
                if not slot:
                    line.append("-")
                elif slot.status == "ok":
                    line.append(f"OK ({slot.extension})")
                elif slot.status == "wrong_ext":
                    line.append(f"Ext no sugerida ({slot.extension})")
                elif slot.status == "no_folder":
                    line.append("Sin carpeta")
                else:
                    line.append("Falta")
            writer.writerow(line)

    return len(rows_to_export)


def format_file_size(size_bytes: int) -> str:
    """Formatea un tamaño en bytes a KB / MB legible."""
    if size_bytes <= 0:
        return "0 B"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def suggest_media_root_for_list(list_row: dict[str, Any] | None) -> str:
    """Sugiere una carpeta raíz razonable para crear subcarpetas de media faltantes."""
    if not list_row:
        return ""
    media_root = str(list_row.get("media_path") or "").strip()
    if media_root:
        return media_root.replace("\\", "/")
    for key in ("boxart_path", "wheel_path", "video_path", "cartart_path", "flyer_path", "marquee_path", "bezel_path", "manual_path"):
        existing = str(list_row.get(key) or "").strip()
        if existing:
            parent = str(Path(existing).parent)
            if parent and parent != existing:
                return parent.replace("\\", "/")
    roms_raw = str(list_row.get("roms_path") or "").strip()
    if roms_raw:
        first_rom_dir = roms_raw.split(";")[0].strip()
        if first_rom_dir:
            p = Path(first_rom_dir)
            base_parent = p.parent if p.parent != p else p
            return str(base_parent / "media").replace("\\", "/")
    return ""


def ensure_media_folders_for_list(
    db: Any,
    list_row: dict[str, Any],
    specs: list[MediaRequirementSpec],
    target_keys: list[str] | tuple[str, ...],
    base_media_root: str,
) -> list[str]:
    """
    Crea en disco las carpetas faltantes para `target_keys` bajo `base_media_root/<default_folder_name>`
    y guarda las rutas en `db.update_list(...)`. Retorna los nombres de campos actualizados.
    """
    if not list_row or not base_media_root:
        return []
    root = Path(base_media_root)
    root.mkdir(parents=True, exist_ok=True)
    updates: dict[str, str] = {}
    norm_root = str(root).replace("\\", "/")
    if not str(list_row.get("media_path") or "").strip():
        updates["media_path"] = norm_root

    target_set = set(target_keys)
    for spec in specs:
        if spec.key not in target_set:
            continue
        if spec.folder_path and os.path.isdir(spec.folder_path):
            continue
        dest = Path(spec.folder_path) if spec.folder_path else (root / (spec.default_folder_name or spec.key))
        dest.mkdir(parents=True, exist_ok=True)
        norm_dest = str(dest).replace("\\", "/")
        spec.folder_path = norm_dest
        spec.folder_exists = True
        updates[spec.db_field] = norm_dest
        if spec.key == "discart":
            updates.setdefault("cartart_path", norm_dest)

    if updates and db is not None:
        db.update_list(int(list_row["id"]), **updates)
        clear_media_cache()
    return sorted(updates.keys())
