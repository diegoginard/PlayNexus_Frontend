import os
import re
from pathlib import Path

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".webm", ".m4v")

# Caché en memoria de los contenidos de cada carpeta de medios:
# norm_folder_path -> (mtime, {nombre_archivo_minusculas: ruta_completa})
_MEDIA_DIR_CACHE: dict[str, tuple[float, dict[str, str]]] = {}


def clear_media_cache():
    """Limpia la caché de índices de archivos de directorios de medios en memoria."""
    _MEDIA_DIR_CACHE.clear()


def _get_folder_index(folder: str | Path | None) -> dict[str, str]:
    """
    Retorna un índice en memoria {nombre_archivo_minusculas: ruta_completa} para la carpeta dada.
    Solo escanea el directorio del disco una vez (y si su mtime cambia), haciendo que todas
    las búsquedas de imágenes y videos sean instantáneas en RAM (O(1)).
    """
    if not folder:
        return {}
    folder_str = str(folder).strip()
    if not folder_str:
        return {}

    norm_key = os.path.normcase(os.path.abspath(folder_str))
    try:
        mtime = os.path.getmtime(folder_str)
    except OSError:
        _MEDIA_DIR_CACHE.pop(norm_key, None)
        return {}

    cached = _MEDIA_DIR_CACHE.get(norm_key)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    file_map: dict[str, str] = {}
    try:
        for entry in os.scandir(folder_str):
            if entry.is_file():
                file_map[entry.name.lower()] = entry.path.replace("\\", "/")
    except OSError:
        pass

    _MEDIA_DIR_CACHE[norm_key] = (mtime, file_map)
    return file_map


def detect_media_folders(base_path: str | Path | None, media_root: str | Path | None = None, media_spec: list[dict] | None = None) -> dict[str, str]:
    """
    Escanea la carpeta de medios seleccionada buscando las subcarpetas requeridas
    estrictamente según la especificación del layout (media_spec).
    No asume alias ni carpetas fuera de la ruta indicada.
    """
    detected = {
        "media_path": "",
        "boxart_path": "",
        "wheel_path": "",
        "video_path": "",
        "cartart_path": "",
        "cabinet_path": "",
        "marquee_path": "",
        "bezel_path": "",
    }

    target_dir = None
    if media_root:
        mr_path = Path(media_root)
        if mr_path.is_dir():
            target_dir = mr_path
            detected["media_path"] = str(mr_path)
    elif base_path:
        bp = Path(base_path)
        if bp.is_dir():
            m_sub = bp / "media"
            if m_sub.is_dir():
                target_dir = m_sub
                detected["media_path"] = str(m_sub)
            else:
                target_dir = bp

    if not target_dir or not target_dir.is_dir() or not media_spec:
        return detected

    try:
        subdirs = {entry.name.lower(): entry.path for entry in os.scandir(target_dir) if entry.is_dir()}
    except Exception:
        return detected

    for item in media_spec:
        key = item.get("key", "")
        target_field = f"{key}_path"
        if detected.get(target_field):
            continue

        folder_name = (item.get("folder") or key).lower()
        cand_names = [folder_name]
        if folder_name.endswith("s"):
            cand_names.append(folder_name[:-1])
        else:
            cand_names.append(folder_name + "s")
        if key.lower() not in cand_names:
            cand_names.append(key.lower())

        for name in cand_names:
            if name in subdirs:
                sub_path = subdirs[name]
                exts = item.get("extensions")
                if exts:
                    has_files = False
                    try:
                        for file_entry in os.scandir(sub_path):
                            if file_entry.is_file() and any(file_entry.name.lower().endswith(e.lower()) for e in exts):
                                has_files = True
                                break
                    except Exception:
                        has_files = True
                    if has_files:
                        detected[target_field] = sub_path
                        break
                else:
                    detected[target_field] = sub_path
                    break

    return detected


def find_media_file(folder: str | Path | None, base_name: str, extensions: tuple[str, ...]) -> str | None:
    """Busca en memoria (O(1)) un archivo con base_name y alguna de las extensiones dentro de folder."""
    if not folder:
        return None
    if os.path.isfile(folder):
        return str(folder).replace("\\", "/")
    if not base_name:
        return None
    file_map = _get_folder_index(folder)
    if not file_map:
        return None

    base_lower = base_name.lower()
    for ext in extensions:
        cand = f"{base_lower}{ext.lower()}"
        if cand in file_map:
            return file_map[cand]
    return None


def resolve_game_media(*args, **kwargs) -> dict[str, str | None]:
    """
    Resuelve las rutas completas a los archivos multimedia (boxart, wheel, video/snap, cartart)
    para un juego según el archivo de ROM y la configuración de su lista o datos del juego.
    Soporta múltiples formas de llamada:
      - resolve_game_media(rom_path, list_row)
      - resolve_game_media(db, gid, game)
      - resolve_game_media(game)
    """
    media = {
        "boxart": None,
        "flyer": None,
        "wheel": None,
        "video": None,
        "snap": None,
        "cartart": None,
        "discart": None,
        "cabinet": None,
        "marquee": None,
        "bezel": None,
    }

    rom_path = ""
    list_row = None

    if len(args) == 3:
        _db, _gid, list_row = args
    elif len(args) == 2:
        a0, a1 = args
        if isinstance(a0, str):
            rom_path = a0
            list_row = a1
        else:
            list_row = a1
    elif len(args) == 1:
        a0 = args[0]
        if isinstance(a0, str):
            rom_path = a0
        else:
            list_row = a0
    else:
        rom_path = kwargs.get("rom_path", "")
        list_row = kwargs.get("list_row", kwargs.get("game"))

    row_dict = {}
    if list_row is not None:
        if isinstance(list_row, dict):
            row_dict = list_row
        elif hasattr(list_row, "keys"):
            row_dict = dict(list_row)

    if not rom_path and row_dict:
        rom_path = row_dict.get("rom_path") or ""

    stem = Path(rom_path).stem if rom_path else ""

    if stem and row_dict:
        # 1. Box Art y Flyer
        box_folder = row_dict.get("boxart_path")
        if box_folder:
            media["boxart"] = find_media_file(box_folder, stem, IMAGE_EXTS)

        flyer_folder = row_dict.get("flyer_path")
        if flyer_folder:
            media["flyer"] = find_media_file(flyer_folder, stem, IMAGE_EXTS)

        # 2. Wheel Logos
        wheel_folder = row_dict.get("wheel_path")
        if wheel_folder:
            media["wheel"] = find_media_file(wheel_folder, stem, IMAGE_EXTS)

        # 3. Video Snaps
        video_folder = row_dict.get("video_path")
        if video_folder:
            v_found = find_media_file(video_folder, stem, VIDEO_EXTS)
            media["video"] = v_found
            media["snap"] = v_found

        # 4. Cart Art / Disc Art
        cart_folder = row_dict.get("cartart_path") or row_dict.get("discart_path")
        if cart_folder:
            c_found = find_media_file(cart_folder, stem, IMAGE_EXTS)
            media["cartart"] = c_found
            media["discart"] = c_found

        # 5. Cabinet, Marquee y Bezel
        cab_folder = row_dict.get("cabinet_path")
        if cab_folder:
            media["cabinet"] = find_media_file(cab_folder, stem, IMAGE_EXTS)

        marq_folder = row_dict.get("marquee_path")
        if marq_folder:
            media["marquee"] = find_media_file(marq_folder, stem, IMAGE_EXTS)

        bezel_folder = row_dict.get("bezel_path")
        if bezel_folder:
            media["bezel"] = find_media_file(bezel_folder, stem, IMAGE_EXTS)

    # Resolución de medios para Menú de Sistemas (cuando el item representa una lista/consola)
    if (not stem or row_dict.get("is_menu_target")) and row_dict:
        sys_name = (row_dict.get("title") or "").strip()
        plat_name = (row_dict.get("platform") or "").strip()

        candidates = []
        for n in (sys_name, plat_name):
            if not n:
                continue
            if n not in candidates:
                candidates.append(n)
            clean_paren = re.sub(r"\s*\(.*?\)", "", n).strip()
            if clean_paren and clean_paren not in candidates:
                candidates.append(clean_paren)
            clean_slash = n.replace("/", " - ").replace("\\", " - ").strip()
            if clean_slash and clean_slash not in candidates:
                candidates.append(clean_slash)

        # 1. Wheel Logos
        wheel_folder = row_dict.get("menu_wheel_path") or row_dict.get("wheel_path")
        if wheel_folder:
            for cand in candidates:
                found = find_media_file(wheel_folder, cand, IMAGE_EXTS)
                if found:
                    media["wheel"] = found
                    break

        # 2. Video Snaps
        video_folder = row_dict.get("menu_video_path") or row_dict.get("video_path")
        if video_folder:
            for cand in candidates:
                found = find_media_file(video_folder, cand, VIDEO_EXTS)
                if found:
                    media["video"] = found
                    media["snap"] = found
                    break

        # 3. Box Art
        box_folder = row_dict.get("menu_boxart_path") or row_dict.get("boxart_path")
        if box_folder:
            for cand in candidates:
                found = find_media_file(box_folder, cand, IMAGE_EXTS)
                if found:
                    media["boxart"] = found
                    break

        # 4. Cart Art / Disc Art
        cart_folder = row_dict.get("menu_cartart_path") or row_dict.get("cartart_path") or row_dict.get("discart_path")
        if cart_folder:
            for cand in candidates:
                found = find_media_file(cart_folder, cand, IMAGE_EXTS)
                if found:
                    media["cartart"] = found
                    media["discart"] = found
                    break

    # Carátula personalizada asignada manualmente a un juego individual (games.cover_path)
    if row_dict and not media["boxart"] and not row_dict.get("is_menu_target"):
        c_path = row_dict.get("cover_path")
        if c_path and os.path.isfile(c_path):
            media["boxart"] = c_path

    if not media["discart"] and media["cartart"]:
        media["discart"] = media["cartart"]
    elif not media["cartart"] and media["discart"]:
        media["cartart"] = media["discart"]

    media["snap"] = media["video"]
    return media
