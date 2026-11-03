import json
import os
import re
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent.parent

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
            b_found = find_media_file(bezel_folder, stem, IMAGE_EXTS)
            if not b_found:
                # Bezel de base (fallback) si no se encuentra el específico de la ROM
                for fb in ("default", "base", "generic", "bezel"):
                    b_found = find_media_file(bezel_folder, fb, IMAGE_EXTS)
                    if b_found:
                        break
            media["bezel"] = b_found

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


def is_game_vertical(game: dict | None) -> bool:
    """
    Determina si un juego tiene orientación de pantalla vertical:
    1. Campo directo o override manual: 'orientation', 'rotate', 'rotation', 'display_rotate'.
    2. Propiedades de XML / Metadatos (MAME, Arcade):
       - 'display_rotate' en ('90', '270')
       - 'rotate' / 'rotation' en ('90', '270')
       - 'orientation' / 'video_orientation' / 'display_orientation' con 'vertical'
       - 'display_height' > 'display_width' cuando no hay rotación explícita
    """
    if not game:
        return False

    meta_dict: dict = {}
    xml_props = game.get("xml_properties")
    if isinstance(xml_props, dict):
        meta_dict.update(xml_props)

    xml_raw = game.get("xml_metadata")
    if isinstance(xml_raw, dict):
        meta_dict.update(xml_raw)
    elif isinstance(xml_raw, str) and xml_raw.strip() and xml_raw != "{}":
        try:
            parsed = json.loads(xml_raw)
            if isinstance(parsed, dict):
                meta_dict.update(parsed)
        except Exception:
            pass

    # Combinar con los campos directos del diccionario del juego
    merged = {**meta_dict, **{k: v for k, v in game.items() if v is not None}}

    # 1. Comprobar orientación explícita o manual del usuario
    for k in ("orientation", "video_orientation", "display_orientation"):
        val = str(merged.get(k) or "").strip().lower()
        if "vertical" in val or val in ("v", "vert", "90", "270"):
            return True
        if "horizontal" in val or val in ("h", "horiz", "0", "180"):
            return False

    # 2. Comprobar rotación explícita (MAME XML: 90 y 270 grados indican monitor vertical)
    for k in ("display_rotate", "rotate", "rotation"):
        val = str(merged.get(k) or "").strip().lower()
        if val in ("90", "270", "90.0", "270.0"):
            return True

    # 3. Comprobar resolución si el alto nativo es mayor que el ancho
    w_str = str(merged.get("display_width") or "").strip()
    h_str = str(merged.get("display_height") or "").strip()
    if w_str.isdigit() and h_str.isdigit():
        w, h = int(w_str), int(h_str)
        if h > w and w > 0:
            return True

    return False


def resolve_game_bezel(db, game: dict | None, list_row: dict | None = None) -> str | None:
    """
    Resuelve el archivo para el Bezel HUD (superpuesto sobre el emulador):
    1. Si el juego tiene 'bezel_hud_mode' == 'disabled': retorna None.
    2. Si 'bezel_hud_mode' != 'enabled': comprueba 'bezel_hud_enabled' de la lista. Si es falso, retorna None.
    3. Obtiene la carpeta de Bezel HUD seleccionada en la lista ('bezel_hud_path').
       Si no está configurada o no existe, retorna None.
    4. Dentro de esa carpeta exclusivamente:
       a) Busca el bezel de la ROM: <stem>.png o <rom_name>.png.
       b) Si no lo encuentra:
          - Si el juego tiene pantalla vertical, busca 'default_v.png'.
          - Si no existe 'default_v.png' (o si es horizontal), busca estrictamente 'default.png'.
       c) Si ninguno existe, retorna None.
    """
    if not game:
        return None

    # 1. Comprobar override individual de la ROM
    game_mode = str(game.get("bezel_hud_mode") or "").strip().lower()
    if game_mode == "disabled":
        return None

    if list_row is None and db:
        lid = game.get("list_id")
        if lid:
            try:
                list_row = db.get_list(lid)
            except Exception:
                pass

    if not list_row:
        return None

    # 2. Comprobar si la lista tiene activo el Bezel HUD (a menos que la ROM fuerce 'enabled')
    if game_mode != "enabled":
        list_enabled = str(list_row.get("bezel_hud_enabled", "true")).strip().lower() in ("true", "1")
        if not list_enabled:
            return None

    # 3. Carpeta seleccionada para el Bezel HUD
    hud_folder = str(list_row.get("bezel_hud_path") or "").strip()
    if not hud_folder or not os.path.isdir(hud_folder):
        return None

    hud_path_obj = Path(hud_folder)

    # 4. Búsqueda del bezel específico de la ROM (<stem>.png o <rom_name>.png)
    rom_path = game.get("rom_path") or ""
    stem = Path(rom_path).stem if rom_path else ""
    rom_name = game.get("rom_name") or ""

    for name in (stem, rom_name):
        if name:
            cand = hud_path_obj / f"{name}.png"
            if cand.is_file():
                return str(cand).replace("\\", "/")

    # 5. Bezel por defecto:
    # Si el juego es de pantalla vertical, busca primero default_v.png
    if is_game_vertical(game):
        default_v = hud_path_obj / "default_v.png"
        if default_v.is_file():
            return str(default_v).replace("\\", "/")

    # Si no es vertical, o si default_v.png no está presente, busca default.png
    default_cand = hud_path_obj / "default.png"
    if default_cand.is_file():
        return str(default_cand).replace("\\", "/")

    return None


def resolve_loading_image(db, game: dict | None, is_exit: bool = False, list_row: dict | None = None) -> str | None:
    """
    Resuelve la imagen para la pantalla de carga (apertura o cierre):
    1. Si la lista tiene 'loading_path' configurado (o retrocompatible 'loading_in_path'):
       - Prioridad 1 (Por ROM / juego):
         Busca dentro de una subcarpeta nombrada como la ROM (<rom_name> o <stem>):
           - Apertura (is_exit=False): <nombrerom>_i.<ext>, <stem>_i.<ext>, default_i.<ext>, loading_i.<ext>, etc.
           - Cierre (is_exit=True): <nombrerom>_o.<ext>, <stem>_o.<ext>, default_o.<ext>, loading_o.<ext>, exit.<ext>, etc.
         También busca directamente en la raíz de loading_path con sufijo _i / _o:
           - Apertura: <nombrerom>_i.<ext>
           - Cierre: <nombrerom>_o.<ext>
       - Prioridad 2 (Por defecto del sistema / lista):
         Busca dentro de la subcarpeta 'default' (o 'Default'):
           - Apertura: default_i.<ext>, loading_i.<ext>, default_in.<ext>, default.<ext>
           - Cierre: default_o.<ext>, loading_o.<ext>, default_out.<ext>, exit.<ext>
         También busca directamente en la raíz de loading_path:
           - Apertura: default_i.<ext>
           - Cierre: default_o.<ext>
    2. Prioridad 3 (Genérico global en splash/):
       - Si es de cierre: busca splash/exit.<ext>, splash/loading_out.<ext>, splash/loading_o.<ext>, splash/outro.<ext>.
       - Si no se encuentra cierre específico o es de apertura:
         busca splash/loading.<ext>, splash/loading_in.<ext>, splash/loading_i.<ext>, splash/splash.<ext>.
    """
    if list_row is None and db and game:
        lid = game.get("list_id")
        if lid:
            try:
                list_row = db.get_list(lid)
            except Exception:
                pass

    rom_path = (game.get("rom_path") or "") if game else ""
    stem = Path(rom_path).stem if rom_path else ""
    rom_name = (game.get("rom_name") or "") if game else ""

    loading_folder = ""
    if list_row:
        loading_folder = str(list_row.get("loading_path") or list_row.get("loading_in_path") or "").strip()

    if loading_folder:
        p_root = Path(loading_folder)
        if p_root.is_file():
            return str(p_root.resolve()).replace("\\", "/")
        if p_root.is_dir():
            # 1. Prioridad 1: Subcarpeta con el nombre de la ROM conteniendo nombrerom_i / nombrerom_o
            cand_rom_names = []
            for n in (rom_name, stem):
                if n and n not in cand_rom_names:
                    cand_rom_names.append(n)

            for r_name in cand_rom_names:
                sub_dir = p_root / r_name
                if sub_dir.is_dir():
                    if not is_exit:
                        cand_files = [f"{r_name}_i", f"{stem}_i", f"{r_name}_in", "default_i", "loading_i", "loading", r_name]
                    else:
                        cand_files = [f"{r_name}_o", f"{stem}_o", f"{r_name}_out", "default_o", "loading_o", "exit", r_name]

                    for fname in cand_files:
                        found = find_media_file(sub_dir, fname, IMAGE_EXTS)
                        if found:
                            return found.replace("\\", "/")

                # Búsqueda suelta directamente en la raíz de loading_folder
                direct_candidates = [f"{r_name}_o", f"{stem}_o"] if is_exit else [f"{r_name}_i", f"{stem}_i"]
                for fname in direct_candidates:
                    found = find_media_file(p_root, fname, IMAGE_EXTS)
                    if found:
                        return found.replace("\\", "/")

            # 2. Prioridad 2: Subcarpeta 'default' con default_i / default_o
            def_sub_dir = p_root / "default"
            if not def_sub_dir.is_dir():
                def_sub_dir = p_root / "Default"

            if def_sub_dir.is_dir():
                if not is_exit:
                    cand_def = ["default_i", "default_in", "loading_i", "loading", "default"]
                else:
                    cand_def = ["default_o", "default_out", "loading_o", "exit", "default"]

                for fname in cand_def:
                    found = find_media_file(def_sub_dir, fname, IMAGE_EXTS)
                    if found:
                        return found.replace("\\", "/")

                # Si es de cierre y no hay default_o, fallback a default_i en la carpeta default
                if is_exit:
                    found = find_media_file(def_sub_dir, "default_i", IMAGE_EXTS)
                    if found:
                        return found.replace("\\", "/")

            # Si no hay subcarpeta default, probar default_i / default_o sueltas en loading_folder
            direct_def = ["default_o", "exit", "loading_out", "default_i"] if is_exit else ["default_i", "loading", "default_in", "default"]
            for fname in direct_def:
                found = find_media_file(p_root, fname, IMAGE_EXTS)
                if found:
                    return found.replace("\\", "/")

    # 3. Prioridad 3: Fallback global genérico en splash/
    splash_dir = APP_DIR / "splash"
    if splash_dir.is_dir():
        if is_exit:
            for cand_exit in ("exit", "loading_out", "loading_o", "outro"):
                found = find_media_file(splash_dir, cand_exit, IMAGE_EXTS)
                if found:
                    return found.replace("\\", "/")

        for cand_load in ("loading", "loading_in", "loading_i", "splash"):
            found = find_media_file(splash_dir, cand_load, IMAGE_EXTS)
            if found:
                return found.replace("\\", "/")

    return None

