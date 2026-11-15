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

from playnexus.services.media import IMAGE_EXTS, VIDEO_EXTS, clear_media_cache


_VIDEO_KEYS = {"video", "snap"}
_VIDEO_EXT_SET = {e.lower() for e in VIDEO_EXTS}
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
    """Determina si un slot corresponde a imagen o video según clave y extensiones."""
    k = (key or "").strip().lower()
    if k in _VIDEO_KEYS:
        return "video"
    if extensions and all(ext.lower() in _VIDEO_EXT_SET for ext in extensions):
        return "video"
    return "image"


def normalize_extensions_tuple(raw_exts: list[str] | tuple[str, ...] | None, media_kind: str) -> tuple[str, ...]:
    """Normaliza las extensiones declaradas en MEDIA_REQUIREMENTS."""
    if not raw_exts:
        return VIDEO_EXTS if media_kind == "video" else IMAGE_EXTS
    out: list[str] = []
    for ext in raw_exts:
        s = str(ext).strip().lower()
        if not s:
            continue
        if not s.startswith("."):
            s = f".{s}"
        if s not in out:
            out.append(s)
    return tuple(out) if out else (VIDEO_EXTS if media_kind == "video" else IMAGE_EXTS)


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

    fallback_exts = VIDEO_EXTS if spec.media_kind == "video" else IMAGE_EXTS

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
