from pathlib import Path
from contextlib import nullcontext
import json
import os
import re
import xml.etree.ElementTree as ET

GENERIC_EXTENSION_WARNINGS = {
    ".bin": "La extensión '.bin' es genérica y puede coincidir con archivos auxiliares o pistas secundarias de disco (por ejemplo en pistas CUE/BIN).",
    ".dat": "La extensión '.dat' suele utilizarse para archivos de datos auxiliares o metadatos, no necesariamente ejecutables.",
}

def normalize_extensions(raw_text: str) -> tuple[str, list[str]]:
    """
    Normaliza y valida una cadena de extensiones separadas exclusivamente por punto y coma (;).

    Retorna:
        tuple[str, list[str]]: (extensiones_normalizadas_separadas_por_punto_y_coma, advertencias)

    Lanza:
        ValueError: Si el campo está vacío, contiene comas, o alguna extensión tiene formato inválido.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("El campo de extensiones no puede estar vacío. Indicá al menos una extensión (ej: .sfc;.smc;.zip).")

    # Regla estricta: No permitir comas como separador
    if "," in raw_text:
        raise ValueError(
            "Las extensiones deben separarse exclusivamente mediante punto y coma (;).\n"
            "Se detectaron comas (,). Reemplazá las comas por punto y coma (ej: .cue;.bin;.iso)."
        )

    tokens = raw_text.split(";")
    normalized_list: list[str] = []
    seen = set()
    warnings: list[str] = []

    for raw_token in tokens:
        token = raw_token.strip()
        if not token:
            continue

        # Aceptar token especial <DIR> para carpetas de juegos (ej: MAME)
        if token.lower() in ("<dir>", "dir", "<directory>"):
            token_clean = "<DIR>"
            if token_clean not in seen:
                seen.add(token_clean)
                normalized_list.append(token_clean)
            continue

        # Aceptar con o sin punto inicial
        if not token.startswith("."):
            token = f".{token}"

        # Convertir a minúsculas
        token = token.lower()

        # Validar formato: debe comenzar con un punto seguido de caracteres alfanuméricos válidos
        if not re.match(r"^\.[a-z0-9_\-\.]{1,20}$", token) or token == ".":
            raise ValueError(
                f"La extensión '{raw_token.strip()}' tiene un formato inválido.\n"
                "Solo debe contener letras, números y el punto inicial (ej: .gba, .sfc, .zip o <DIR>)."
            )

        # Evitar duplicados manteniendo orden
        if token not in seen:
            seen.add(token)
            normalized_list.append(token)

            # Advertir sobre extensiones genéricas
            if token in GENERIC_EXTENSION_WARNINGS:
                warnings.append(GENERIC_EXTENSION_WARNINGS[token])

    if not normalized_list:
        raise ValueError("No se encontraron extensiones válidas en el texto ingresado.")

    return ";".join(normalized_list), warnings


def parse_extensions_list(extensions_str: str) -> list[str]:
    """
    Convierte la cadena almacenada en la base de datos (separada por ;) en una lista de extensiones en minúsculas.
    Preserva el token especial '<dir>'.
    """
    if not extensions_str:
        return []
    result = []
    for ext in extensions_str.split(";"):
        clean = ext.strip().lower()
        if not clean:
            continue
        if clean in ("<dir>", "dir", "<directory>"):
            token = "<dir>"
        else:
            token = clean if clean.startswith(".") else f".{clean}"
        if token not in result:
            result.append(token)
    return result


def parse_rom_folders(folders_raw: str | list[str | Path] | Path | None) -> list[str]:
    """
    Convierte una cadena de carpetas separadas por ';' (o salto de línea) o una lista de rutas
    en una lista limpia de rutas de carpetas sin duplicados.
    """
    if not folders_raw:
        return []
    if isinstance(folders_raw, Path):
        s = str(folders_raw).strip()
        return [s] if s else []
    if isinstance(folders_raw, str):
        tokens = re.split(r"[;\r\n]+", folders_raw)
    else:
        tokens = []
        for item in folders_raw:
            if item:
                tokens.extend(re.split(r"[;\r\n]+", str(item)))

    result: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        clean = tok.strip().strip('"').strip("'")
        if not clean:
            continue
        norm_key = clean.replace("/", "\\").rstrip("\\").lower()
        if norm_key not in seen:
            seen.add(norm_key)
            result.append(clean)
    return result


def format_rom_folders(folders: list[str | Path] | str | None) -> str:
    """
    Serializa una lista de carpetas de ROMs en una cadena separada por punto y coma (;).
    """
    return ";".join(parse_rom_folders(folders))


def scan_rom_folder(
    folder: str | Path | list[str | Path],
    allowed_extensions: list[str] | str,
    scan_subfolders: bool = True,
    exclude_folder_if_zip: bool = False,
    progress_callback: callable = None,
) -> list[Path]:
    """
    Escanea una o varias carpetas en busca de archivos cuyas extensiones
    coincidan con la lista permitida para la lista seleccionada.

    Parámetros:
      - scan_subfolders: Si es True, busca de forma recursiva en subcarpetas.
                         Si es False, busca exclusivamente en la raíz de cada carpeta configurada.
      - exclude_folder_if_zip: Si es True y una subcarpeta contiene archivo(s) .zip (o .7z),
                               lista únicamente el .zip y excluye el resto del contenido de la carpeta.
                               Asimismo, si en una carpeta existe 'juego.zip' y una subcarpeta 'juego',
                               se descarta la subcarpeta para evitar duplicar archivos auxiliares.
    """
    folder_list = parse_rom_folders(folder)
    valid_roots: list[Path] = []
    for f_str in folder_list:
        p = Path(f_str)
        if p.is_dir():
            valid_roots.append(p)

    if not valid_roots:
        raise ValueError("Ninguna de las rutas seleccionadas es una carpeta válida o accesible.")

    if isinstance(allowed_extensions, str):
        allowed_list = parse_extensions_list(allowed_extensions)
    else:
        allowed_list = []
        for e in allowed_extensions:
            clean = str(e).strip().lower()
            if not clean:
                continue
            if clean in ("<dir>", "dir", "<directory>"):
                allowed_list.append("<dir>")
            else:
                allowed_list.append(clean if clean.startswith(".") else f".{clean}")

    allowed_set = set(allowed_list)
    if not allowed_set:
        raise ValueError(
            "Esta lista no tiene extensiones configuradas.\n"
            "Editá la lista y configurá las extensiones permitidas separadas por ';' antes de escanear."
        )

    has_dir_token = "<dir>" in allowed_set
    file_ext_set = {e for e in allowed_set if e != "<dir>"}

    matched: list[Path] = []
    seen_resolved: set[str] = set()

    for root in valid_roots:
        abs_root = os.path.abspath(str(root)).lower()
        if progress_callback:
            progress_callback(f"[SCAN] Explorando carpeta raíz: {root}")
        for dirpath, dirnames, filenames in os.walk(str(root), topdown=True):
            abs_dir = os.path.abspath(dirpath).lower()
            is_root_dir = (abs_dir == abs_root)

            # Si no se permite escanear subcarpetas y ya estamos en un subdirectorio:
            if not scan_subfolders and not is_root_dir:
                dirnames.clear()
                continue

            if progress_callback and not is_root_dir:
                progress_callback(f"[SCAN] Escaneando subdirectorio: {dirpath}")

            # Identificar archivos .zip y .7z en este directorio
            zip_files = [f for f in filenames if os.path.splitext(f)[1].lower() in (".zip", ".7z")]
            has_zip_in_dir = len(zip_files) > 0
            zip_stems = {os.path.splitext(f)[0].lower() for f in zip_files}

            # 1. Filtrar los archivos a procesar según exclude_folder_if_zip
            if exclude_folder_if_zip:
                if not is_root_dir and has_zip_in_dir:
                    # En una subcarpeta que contiene .zip: listar ÚNICAMENTE los archivos .zip,
                    # descartar cualquier otro archivo y no recorrer subdirectorios hijos.
                    dirnames.clear()
                    target_filenames = zip_files
                else:
                    # Si es el directorio raíz (o una carpeta sin .zip):
                    # Podar de dirnames cualquier subcarpeta que comparta nombre base con un .zip
                    if has_zip_in_dir:
                        dirs_to_prune = [d for d in dirnames if d.lower() in zip_stems]
                        for d in dirs_to_prune:
                            dirnames.remove(d)

                        # Excluir archivos no-zip que compartan el mismo nombre base que un .zip en esta carpeta
                        target_filenames = []
                        for fname in filenames:
                            f_stem, ext = os.path.splitext(fname)
                            if ext.lower() not in (".zip", ".7z") and f_stem.lower() in zip_stems:
                                continue
                            target_filenames.append(fname)
                    else:
                        target_filenames = filenames
            else:
                target_filenames = filenames

            dir_zip_stems = set(zip_stems)
            for fname in target_filenames:
                f_stem, ext = os.path.splitext(fname)
                ext_lower = ext.lower()
                f_stem_lower = f_stem.lower()

                # Registrar los nombres base de zips/archivos en este directorio
                if ext_lower in (".zip", ".7z") or ext_lower in file_ext_set:
                    dir_zip_stems.add(f_stem_lower)

                if ext_lower in file_ext_set or (exclude_folder_if_zip and ext_lower in (".zip", ".7z")):
                    full_str = os.path.abspath(os.path.join(dirpath, fname))
                    res_key = full_str.lower()
                    if res_key not in seen_resolved:
                        seen_resolved.add(res_key)
                        matched.append(Path(full_str))
                        if progress_callback and (len(matched) <= 100 or len(matched) % 25 == 0):
                            progress_callback(f"[SCAN] Coincidencia #{len(matched)}: {fname}")

            # 2. Si <DIR> está habilitado, procesar subcarpetas
            if has_dir_token and (scan_subfolders or is_root_dir):
                dirs_to_prune = []
                for d in dirnames:
                    # Ignorar carpetas ocultas, del sistema o auxiliares comunes
                    if d.startswith(".") or d.startswith("$") or d.lower() in (
                        "__pycache__", "artwork", "samples", "ini", "cfg", "snap",
                        "titles", "flyers", "marquees", "cpanel", "history"
                    ):
                        dirs_to_prune.append(d)
                        continue

                    d_lower = d.lower()
                    if exclude_folder_if_zip:
                        sub_path = os.path.join(dirpath, d)
                        try:
                            if any(f.lower().endswith((".zip", ".7z")) for f in os.listdir(sub_path)):
                                continue
                        except OSError:
                            pass

                    # Si ya existe un .zip (o archivo coincidente) con el mismo nombre en la carpeta,
                    # la carpeta no es una ROM independiente (es la carpeta CHD/auxiliar del .zip).
                    if d_lower in dir_zip_stems:
                        dirs_to_prune.append(d)
                    else:
                        # No tiene .zip con su mismo nombre: la carpeta en sí se toma como ROM
                        full_dir_str = os.path.abspath(os.path.join(dirpath, d))
                        res_key = full_dir_str.lower()
                        if res_key not in seen_resolved:
                            seen_resolved.add(res_key)
                            matched.append(Path(full_dir_str))
                        # No recursar dentro de la carpeta que ya es una ROM
                        dirs_to_prune.append(d)

                for d in dirs_to_prune:
                    dirnames.remove(d)

            # Si no se debe escanear subcarpetas, vaciar dirnames para no descender en la siguiente iteración
            if not scan_subfolders:
                dirnames.clear()

    return sorted(matched, key=lambda p: str(p).lower())


scan_rom_folders = scan_rom_folder


def _parse_xml_root(xml_file: Path) -> ET.Element:
    """
    Lee y parsea un archivo XML de ROMs (HyperSpin, MAME, Logiqx DAT, EmulationStation gamelist.xml, etc.).
    Incluye recuperación automática ante caracteres '&' sin escapar o distintas codificaciones.
    """
    try:
        tree = ET.parse(str(xml_file))
        return tree.getroot()
    except Exception:
        raw_bytes = xml_file.read_bytes()
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw_bytes.decode("utf-8", errors="replace")

        # Sanitizar posibles '&' sueltos muy comunes en XMLs de HyperSpin / MAME (ej: "Track & Field")
        sanitized = re.sub(
            r"&(?!amp;|lt;|gt;|apos;|quot;|#\d+;|#x[0-9a-fA-F]+;)",
            "&amp;",
            text,
        )
        return ET.fromstring(sanitized)


def _extract_entry_from_element(elem: ET.Element) -> tuple[list[str], dict] | None:
    """
    Extrae las claves de asociación de la ROM (denominación / archivo) y el diccionario
    completo con el nombre completo y todas las propiedades definidas en el nodo XML.
    """
    props: dict[str, str] = {}
    raw_children: dict[str, str] = {}
    rom_child_names: list[str] = []

    # 1. Atributos directos del nodo (<game name="sf2" index="true" ...> o <machine name="sf2" cloneof="..." ...>)
    for k, v in elem.attrib.items():
        if v is None:
            continue
        val = str(v).strip()
        if val:
            k_clean = k.strip()
            props[k_clean] = val
            props[k_clean.lower()] = val

    # 2. Sub-elementos hijos (<description>, <year>, <manufacturer>, <genre>, <players>, <path>, <name>, etc.)
    for ch in elem:
        tag = ch.tag.split("}")[-1].strip() if isinstance(ch.tag, str) else ""
        if not tag:
            continue
        tag_lower = tag.lower()
        text = (ch.text or "").strip()

        if tag_lower == "rom":
            # En DATs / MAME puede haber <rom name="..." crc="..." md5="..." sha1="..." size="..."/>
            r_name = (ch.attrib.get("name") or "").strip()
            if r_name:
                rom_child_names.append(r_name)
            for rk in ("crc", "md5", "sha1", "size"):
                rv = (ch.attrib.get(rk) or "").strip()
                if rv and rk not in props:
                    props[rk] = rv
            if text and "rom" not in raw_children:
                raw_children["rom"] = text
                props["rom"] = text
        elif tag_lower == "input":
            # MAME <input players="2" coins="2"><control type="joy" buttons="6" ways="8"/></input>
            for ik, iv in ch.attrib.items():
                iv_s = str(iv).strip()
                if iv_s:
                    ik_l = ik.lower().strip()
                    if ik_l == "players" and not props.get("players"):
                        props["players"] = iv_s
                    props[f"input_{ik_l}"] = iv_s
            for sub in ch:
                sub_tag = sub.tag.split("}")[-1].lower() if isinstance(sub.tag, str) else ""
                if sub_tag == "control":
                    for ck, cv in sub.attrib.items():
                        cv_s = str(cv).strip()
                        if cv_s and f"control_{ck.lower()}" not in props:
                            props[f"control_{ck.lower()}"] = cv_s
        elif tag_lower == "driver":
            # MAME <driver status="good" emulation="good" savestate="supported"/>
            for dk, dv in ch.attrib.items():
                dv_s = str(dv).strip()
                if dv_s:
                    dk_l = dk.lower().strip()
                    props[f"driver_{dk_l}"] = dv_s
                    if dk_l == "status" and "status" not in props:
                        props["status"] = dv_s
        else:
            if text:
                raw_children[tag_lower] = text
                props[tag] = text
                props[tag_lower] = text
            for ak, av in ch.attrib.items():
                av_s = str(av).strip()
                if av_s:
                    props[f"{tag_lower}_{ak.lower().strip()}"] = av_s

    # 3. Determinar la denominación de la ROM (claves de búsqueda) y el Nombre Completo (title)
    attr_rom = (
        elem.attrib.get("name")
        or elem.attrib.get("rom")
        or elem.attrib.get("filename")
        or elem.attrib.get("file")
        or ""
    ).strip()

    path_child = (
        raw_children.get("path")
        or raw_children.get("rom")
        or raw_children.get("filename")
        or raw_children.get("file")
        or raw_children.get("romname")
        or ""
    ).strip()

    keys: list[str] = []
    full_title = ""

    if attr_rom:
        # Formato HyperSpin / MAME / Logiqx DAT (<game name="sf2"><description>Street Fighter II</description>...)
        keys.append(attr_rom)
        if path_child:
            keys.append(path_child)
        full_title = (
            raw_children.get("description")
            or raw_children.get("title")
            or raw_children.get("fullname")
            or raw_children.get("label")
            or raw_children.get("name")
            or elem.attrib.get("description")
            or elem.attrib.get("title")
            or attr_rom
        ).strip()
    elif path_child:
        # Formato EmulationStation gamelist.xml (<game><path>./sf2.zip</path><name>Street Fighter II</name>...)
        keys.append(path_child)
        full_title = (
            raw_children.get("name")
            or raw_children.get("title")
            or raw_children.get("fullname")
            or raw_children.get("label")
            or raw_children.get("description")
            or Path(path_child.replace("\\", "/")).stem
        ).strip()
    else:
        # Otros formatos (<game><name>sf2</name><description>Street Fighter II</description></game>)
        fallback_key = (
            raw_children.get("name")
            or elem.attrib.get("id")
            or raw_children.get("id")
            or ""
        ).strip()
        if not fallback_key and len(rom_child_names) == 1:
            fallback_key = rom_child_names[0]
        if fallback_key:
            keys.append(fallback_key)
        full_title = (
            raw_children.get("description")
            or raw_children.get("title")
            or raw_children.get("fullname")
            or raw_children.get("label")
            or raw_children.get("name")
            or fallback_key
        ).strip()

    # Si hay un único <rom name="..."/> hijo (ej. DATs No-Intro), agregarlo como clave secundaria
    if len(rom_child_names) == 1:
        keys.append(rom_child_names[0])

    if not keys:
        return None

    # Normalizar claves (tanto nombre de archivo como stem sin extensión, en minúsculas)
    normalized_keys: list[str] = []
    primary_rom_name = ""
    for k in keys:
        clean_k = k.replace("\\", "/").strip()
        if not clean_k:
            continue
        fname = Path(clean_k).name
        stem = Path(clean_k).stem
        if not primary_rom_name:
            primary_rom_name = stem or fname
        for candidate in (stem.lower(), fname.lower(), clean_k.lower()):
            if candidate and candidate not in normalized_keys:
                normalized_keys.append(candidate)

    if not normalized_keys:
        return None

    # 4. Extraer campos estructurados principales
    year = (props.get("year") or props.get("date") or "").strip()
    if not year and props.get("releasedate"):
        m = re.match(r"^(\d{4})", props["releasedate"].strip())
        if m:
            year = m.group(1)

    manufacturer = (
        props.get("manufacturer")
        or props.get("developer")
        or props.get("publisher")
        or props.get("company")
        or props.get("maker")
        or ""
    ).strip()

    genre = (
        props.get("genre")
        or props.get("category")
        or props.get("type")
        or ""
    ).strip()

    players = (
        props.get("players")
        or props.get("nplayers")
        or ""
    ).strip()

    cloneof = (
        props.get("cloneof")
        or props.get("romof")
        or ""
    ).strip()

    rating = (
        props.get("rating")
        or props.get("score")
        or ""
    ).strip()

    crc = (props.get("crc") or "").strip()

    sourcefile = (
        props.get("sourcefile")
        or props.get("source_file")
        or elem.attrib.get("sourcefile")
        or elem.attrib.get("source_file")
        or raw_children.get("sourcefile")
        or raw_children.get("source_file")
        or ""
    ).strip()

    # Sinopsis / Notas (evitando duplicar el título cuando <description> es el nombre del juego)
    notes = (
        raw_children.get("desc")
        or raw_children.get("plot")
        or raw_children.get("synopsis")
        or raw_children.get("story")
        or raw_children.get("history")
        or raw_children.get("notes")
        or ""
    ).strip()

    # Guardar todas las propiedades limpias para que estén disponibles si se requieren
    clean_props: dict[str, str] = {}
    for pk, pv in props.items():
        if pk == pk.lower() and pv:
            clean_props[pk] = pv
    clean_props["rom_name"] = primary_rom_name
    clean_props["title"] = full_title or primary_rom_name
    if sourcefile:
        clean_props["sourcefile"] = sourcefile

    entry = {
        "title": full_title or primary_rom_name,
        "rom_name": primary_rom_name,
        "year": year,
        "manufacturer": manufacturer,
        "genre": genre,
        "players": players,
        "cloneof": cloneof,
        "rating": rating,
        "crc": crc,
        "sourcefile": sourcefile,
        "notes": notes,
        "properties": clean_props,
    }
    return normalized_keys, entry


_XML_CACHE: dict[tuple[str, float], dict[str, dict]] = {}


def parse_rom_xml(xml_path: str | Path | None) -> dict[str, dict]:
    """
    Parsea un archivo XML de ROMs y retorna un diccionario indexado por la denominación
    de la ROM (stem y nombre de archivo en minúsculas) con su nombre completo ('title')
    y todas sus propiedades ('year', 'manufacturer', 'genre', 'players', 'cloneof',
    'rating', 'crc', 'notes', 'properties').
    Incluye caché en memoria por ruta y fecha de modificación para evitar re-parsear el mismo XML.
    """
    if not xml_path:
        return {}
    xml_file = Path(xml_path)
    if not xml_file.is_file():
        raise ValueError(f"El archivo XML especificado no existe:\n{xml_file}")

    abs_key = os.path.abspath(str(xml_file)).lower()
    try:
        mtime = os.path.getmtime(xml_file)
    except OSError:
        mtime = 0.0

    cache_key = (abs_key, mtime)
    if cache_key in _XML_CACHE:
        return _XML_CACHE[cache_key]

    root = _parse_xml_root(xml_file)
    xml_map: dict[str, dict] = {}

    # Buscar nodos <game>, <machine>, o <rom> de primer/segundo nivel
    candidate_nodes: list[ET.Element] = []
    for elem in root.iter():
        if elem is root:
            continue
        tag = elem.tag.split("}")[-1].lower() if isinstance(elem.tag, str) else ""
        if tag in ("game", "machine", "item"):
            candidate_nodes.append(elem)

    # Si el XML usa directamente etiquetas <rom> como entradas principales (sin <game>/<machine>)
    if not candidate_nodes:
        for elem in root.iter():
            if elem is root:
                continue
            tag = elem.tag.split("}")[-1].lower() if isinstance(elem.tag, str) else ""
            if tag == "rom":
                candidate_nodes.append(elem)

    for elem in candidate_nodes:
        extracted = _extract_entry_from_element(elem)
        if not extracted:
            continue
        keys, entry = extracted
        # La primera clave es la principal (ej. name="sf2"), las secundarias no pisan una principal existente
        for idx, k in enumerate(keys):
            if idx == 0 or k not in xml_map:
                xml_map[k] = entry

    _XML_CACHE[cache_key] = xml_map
    return xml_map


def lookup_xml_for_rom(xml_map: dict[str, dict] | None, rom_path: str | Path) -> dict | None:
    """
    Busca una ROM dentro del mapa XML por su denominación (nombre sin extensión o con extensión).
    """
    if not xml_map or not rom_path:
        return None
    p = Path(rom_path)
    stem_key = p.stem.lower().strip()
    if stem_key in xml_map:
        return xml_map[stem_key]
    name_key = p.name.lower().strip()
    if name_key in xml_map:
        return xml_map[name_key]
    return None


def enrich_game_dict(row) -> dict:
    """
    Convierte una fila de la tabla 'games' en un diccionario enriquecido con todas
    las propiedades del XML (tanto en 'xml_properties' como directamente en el diccionario).
    """
    d = dict(row) if not isinstance(row, dict) else dict(row)
    rom_path = d.get("rom_path") or ""
    if not d.get("rom_name") and rom_path:
        d["rom_name"] = Path(rom_path).stem

    raw_meta = d.get("xml_metadata")
    if raw_meta and isinstance(raw_meta, str):
        try:
            meta = json.loads(raw_meta)
            if isinstance(meta, dict):
                d["xml_properties"] = meta
                for k, v in meta.items():
                    if k not in d or d[k] in (None, ""):
                        d[k] = v
            else:
                d["xml_properties"] = {}
        except Exception:
            d["xml_properties"] = {}
    elif isinstance(d.get("xml_properties"), dict):
        pass
    else:
        d["xml_properties"] = {}

    if not d.get("sourcefile"):
        meta = d.get("xml_properties") or {}
        if isinstance(meta, dict) and (meta.get("sourcefile") or meta.get("source_file")):
            d["sourcefile"] = meta.get("sourcefile") or meta.get("source_file") or ""

    return d


def apply_xml_to_list(db, list_id: int, xml_path: str | Path | None = None, xml_map: dict[str, dict] | None = None) -> dict:
    """
    Asocia las ROMs ya registradas en una lista con el archivo XML indicado,
    asignándoles su nombre completo y todas sus propiedades.
    """
    if xml_map is None:
        if not xml_path:
            row_l = db.get_list(list_id)
            xml_path = row_l.get("xml_path", "") if row_l else ""
        if not xml_path or not Path(xml_path).is_file():
            return {"total_games": 0, "matched": 0}
        xml_map = parse_rom_xml(xml_path)

    games = db.get_games(list_id, enriched=False)
    matched = 0

    batch_ctx = db.batch() if hasattr(db, "batch") else nullcontext()
    with batch_ctx:
        for g in games:
            g_dict = dict(g)
            rom_path = g_dict.get("rom_path") or ""
            if not rom_path:
                continue
            info = lookup_xml_for_rom(xml_map, rom_path)
            if not info:
                continue

            new_title = info.get("title") or Path(rom_path).stem
            rom_name = info.get("rom_name") or Path(rom_path).stem
            year = info.get("year") or g_dict.get("year") or ""
            manufacturer = info.get("manufacturer") or g_dict.get("manufacturer") or ""
            genre = info.get("genre") or g_dict.get("genre") or ""
            players = info.get("players") or g_dict.get("players") or ""
            cloneof = info.get("cloneof") or g_dict.get("cloneof") or ""
            rating = info.get("rating") or g_dict.get("rating") or ""
            crc = info.get("crc") or g_dict.get("crc") or ""
            sourcefile = info.get("sourcefile") or g_dict.get("sourcefile") or ""
            notes = g_dict.get("notes") or info.get("notes") or ""
            xml_metadata = json.dumps(info.get("properties", {}), ensure_ascii=False)

            db.update_game(
                g_dict["id"],
                title=new_title,
                rom_name=rom_name,
                year=year,
                manufacturer=manufacturer,
                genre=genre,
                players=players,
                cloneof=cloneof,
                rating=rating,
                crc=crc,
                sourcefile=sourcefile,
                notes=notes,
                xml_metadata=xml_metadata,
            )
            matched += 1

    return {
        "total_games": len(games),
        "matched": matched,
    }


def import_scanned_games(
    db,
    list_id: int,
    paths: list[Path],
    xml_path: str | Path | None = None,
    replace: bool = True,
    progress_callback: callable = None,
    filter_rules: list[dict] | str | None = None,
    filter_match_mode: str | None = None,
) -> dict:
    """
    Importa una lista de rutas de juegos a una lista determinada en texto plano.
    Cuando replace=True (por defecto al escanear/reescanear), reemplaza la lista anterior
    por los juegos encontrados en el escaneo actual para que no queden juegos inexistentes.
    Si la lista tiene un archivo XML asociado (o se recibe xml_path), asigna el
    nombre completo y todas las propiedades del XML a cada ROM coincidente.
    Si la lista posee reglas de filtrado (o se reciben en filter_rules), únicamente
    se registran los juegos que cumplan con los criterios configurados.
    Retorna un diccionario con el resumen de la importación.
    """
    row_l = db.get_list(list_id) if hasattr(db, "get_list") else None
    if not xml_path and row_l and row_l.get("xml_path"):
        xml_path = row_l["xml_path"]

    if filter_rules is None and row_l and row_l.get("filter_rules"):
        filter_rules = row_l["filter_rules"]
        if filter_match_mode is None:
            filter_match_mode = row_l.get("filter_match_mode", "all")

    parsed_rules = []
    if filter_rules:
        if isinstance(filter_rules, str):
            try:
                parsed_rules = json.loads(filter_rules)
            except Exception:
                parsed_rules = []
        elif isinstance(filter_rules, list):
            parsed_rules = filter_rules
        parsed_rules = [
            r for r in parsed_rules
            if isinstance(r, dict) and (r.get("operator") in ("is_empty", "is_not_empty") or (r.get("value") and str(r.get("value")).strip()))
        ]

    effective_match_mode = (filter_match_mode or (row_l.get("filter_match_mode") if row_l else "all") or "all").lower()

    xml_map: dict[str, dict] = {}
    if xml_path and Path(xml_path).is_file():
        if progress_callback:
            progress_callback(0, len(paths), f"[XML] Cargando metadatos XML: {Path(xml_path).name}...")
        xml_map = parse_rom_xml(xml_path)
        if progress_callback:
            progress_callback(0, len(paths), f"[XML] {len(xml_map)} entradas indexadas desde el XML.")

    rows = db.get_games(list_id, enriched=False)
    previous_by_path = {os.path.abspath(str(r["rom_path"])).lower(): dict(r) for r in rows}

    added = 0
    skipped = 0
    removed = 0
    xml_matched = 0
    filtered_out = 0

    batch_ctx = db.batch() if hasattr(db, "batch") else nullcontext()
    with batch_ctx:
        if replace:
            scanned_keys = {os.path.abspath(str(p)).lower() for p in paths}
            removed = sum(1 for k in previous_by_path if k not in scanned_keys)
            if hasattr(db, "clear_list_games"):
                db.clear_list_games(list_id)
            else:
                for r in rows:
                    db.delete_game(r["id"])
            existing_by_path: dict[str, dict] = {}
        else:
            existing_by_path = dict(previous_by_path)

        total_paths = len(paths)
        for idx, path in enumerate(paths, 1):
            try:
                resolved = os.path.abspath(str(path))
                resolved_lower = resolved.lower()
                rom_stem = path.stem if isinstance(path, Path) else Path(path).stem
                info = lookup_xml_for_rom(xml_map, path) if xml_map else None

                prev_row = previous_by_path.get(resolved_lower, {})

                if info:
                    title = info.get("title") or rom_stem
                    rom_name = info.get("rom_name") or rom_stem
                    year = info.get("year", "")
                    manufacturer = info.get("manufacturer", "")
                    genre = info.get("genre", "")
                    players = info.get("players", "")
                    cloneof = info.get("cloneof", "")
                    rating = info.get("rating", "")
                    crc = info.get("crc", "")
                    sourcefile = info.get("sourcefile", "")
                    notes = prev_row.get("notes") or info.get("notes") or ""
                    xml_metadata = json.dumps(info.get("properties", {}), ensure_ascii=False)
                    has_xml = True
                else:
                    title = prev_row.get("title") or rom_stem
                    rom_name = prev_row.get("rom_name") or rom_stem
                    year = prev_row.get("year", "")
                    manufacturer = prev_row.get("manufacturer", "")
                    genre = prev_row.get("genre", "")
                    players = prev_row.get("players", "")
                    cloneof = prev_row.get("cloneof", "")
                    rating = prev_row.get("rating", "")
                    crc = prev_row.get("crc", "")
                    sourcefile = prev_row.get("sourcefile", "")
                    notes = prev_row.get("notes", "")
                    xml_metadata = prev_row.get("xml_metadata") or "{}"
                    has_xml = False

                # Evaluación de reglas de filtrado (si la lista tiene filtros configurados)
                if parsed_rules:
                    cand_game = {
                        "title": title,
                        "rom_name": rom_name,
                        "rom_path": resolved,
                        "year": year,
                        "manufacturer": manufacturer,
                        "genre": genre,
                        "players": players,
                        "cloneof": cloneof,
                        "rating": rating,
                        "crc": crc,
                        "sourcefile": sourcefile,
                        "notes": notes,
                        "xml_metadata": xml_metadata,
                    }
                    if not game_matches_filter(cand_game, parsed_rules, effective_match_mode):
                        filtered_out += 1
                        continue

                if has_xml:
                    xml_matched += 1

                if resolved_lower in existing_by_path:
                    skipped += 1
                    if info:
                        ex_row = existing_by_path[resolved_lower]
                        db.update_game(
                            ex_row["id"],
                            title=title,
                            rom_name=rom_name,
                            year=year,
                            manufacturer=manufacturer,
                            genre=genre,
                            players=players,
                            cloneof=cloneof,
                            rating=rating,
                            crc=crc,
                            sourcefile=sourcefile,
                            notes=notes,
                            xml_metadata=xml_metadata,
                        )
                    continue

                new_id = db.insert_game(
                    list_id,
                    title=title,
                    rom_path=resolved,
                    rom_name=rom_name,
                    year=year,
                    manufacturer=manufacturer,
                    genre=genre,
                    players=players,
                    cloneof=cloneof,
                    rating=rating,
                    crc=crc,
                    sourcefile=sourcefile,
                    emulator_override_id=prev_row.get("emulator_override_id"),
                    launch_arguments=prev_row.get("launch_arguments", ""),
                    cover_path=prev_row.get("cover_path", ""),
                    notes=notes,
                    xml_metadata=xml_metadata,
                )
                existing_by_path[resolved_lower] = {"id": new_id, "rom_path": resolved, "notes": notes}
                added += 1
            except Exception:
                skipped += 1

            if progress_callback:
                if total_paths <= 150 or idx % max(1, total_paths // 150) == 0 or idx == total_paths:
                    t_name = title if 'title' in locals() and title else rom_stem
                    progress_callback(idx, total_paths, f"{t_name}")

    return {
        "total_found": len(paths),
        "added": added,
        "skipped": skipped,
        "removed": removed,
        "xml_matched": xml_matched,
        "xml_total_entries": len(xml_map),
        "filtered_out": filtered_out,
    }


def add_game(
    db,
    list_id: int,
    path: str | Path,
    title: str | None = None,
    xml_map: dict[str, dict] | None = None,
) -> int | None:
    """
    Agrega un juego individual a una lista dada evitando duplicados.
    Si la lista posee un archivo XML configurado (o se pasa xml_map), asocia
    automáticamente la denominación de la ROM con su nombre completo y propiedades.
    """
    p = Path(path)
    resolved = os.path.abspath(str(p))

    if xml_map is None:
        row_l = db.get_list(list_id)
        if row_l and row_l.get("xml_path"):
            xml_p = Path(row_l["xml_path"])
            if xml_p.is_file():
                try:
                    xml_map = parse_rom_xml(xml_p)
                except Exception:
                    xml_map = None

    info = lookup_xml_for_rom(xml_map, p) if xml_map else None

    existing = db.get_game_by_path(list_id, resolved)
    if existing:
        if info:
            ex_dict = dict(existing)
            new_title = title or info.get("title") or p.stem
            rom_name = info.get("rom_name") or p.stem
            notes = ex_dict.get("notes") or info.get("notes") or ""
            xml_metadata = json.dumps(info.get("properties", {}), ensure_ascii=False)
            db.update_game(
                ex_dict["id"],
                title=new_title,
                rom_name=rom_name,
                year=info.get("year", ""),
                manufacturer=info.get("manufacturer", ""),
                genre=info.get("genre", ""),
                players=info.get("players", ""),
                cloneof=info.get("cloneof", ""),
                rating=info.get("rating", ""),
                crc=info.get("crc", ""),
                sourcefile=info.get("sourcefile", ""),
                notes=notes,
                xml_metadata=xml_metadata,
            )
        return existing["id"]

    if info:
        final_title = title or info.get("title") or p.stem
        rom_name = info.get("rom_name") or p.stem
        year = info.get("year", "")
        manufacturer = info.get("manufacturer", "")
        genre = info.get("genre", "")
        players = info.get("players", "")
        cloneof = info.get("cloneof", "")
        rating = info.get("rating", "")
        crc = info.get("crc", "")
        sourcefile = info.get("sourcefile", "")
        notes = info.get("notes", "")
        xml_metadata = json.dumps(info.get("properties", {}), ensure_ascii=False)
    else:
        final_title = title or p.stem
        rom_name = p.stem
        year = ""
        manufacturer = ""
        genre = ""
        players = ""
        cloneof = ""
        rating = ""
        crc = ""
        sourcefile = ""
        notes = ""
        xml_metadata = "{}"

    return db.insert_game(
        list_id,
        title=final_title,
        rom_path=resolved,
        rom_name=rom_name,
        year=year,
        manufacturer=manufacturer,
        genre=genre,
        players=players,
        cloneof=cloneof,
        rating=rating,
        crc=crc,
        sourcefile=sourcefile,
        notes=notes,
        xml_metadata=xml_metadata,
    )


# ----------------------------------------------------------------------
# CONSTANTES Y SERVICIOS PARA LISTAS FILTRADAS
# ----------------------------------------------------------------------

FILTERABLE_FIELDS = [
    ("sourcefile", "Archivo fuente / Driver (sourcefile)"),
    ("genre", "Género (genre)"),
    ("manufacturer", "Fabricante (manufacturer)"),
    ("year", "Año (year)"),
    ("title", "Título (title)"),
    ("rom_name", "Nombre de ROM (rom_name)"),
    ("players", "Jugadores (players)"),
    ("cloneof", "Clon de (cloneof)"),
    ("rating", "Clasificación (rating)"),
    ("crc", "CRC"),
    ("rom_path", "Ruta de ROM (rom_path)"),
    ("notes", "Notas (notes)"),
    ("emulator_override_id", "Emulador específico (ID)"),
    ("launch_arguments", "Argumentos de lanzamiento"),
]

FILTER_OPERATORS = [
    ("contains", "Contiene"),
    ("not_contains", "No contiene"),
    ("equals", "Es exactamente igual a"),
    ("not_equals", "Es distinto de"),
    ("starts_with", "Empieza con"),
    ("ends_with", "Termina con"),
    ("is_empty", "Está vacío"),
    ("is_not_empty", "No está vacío"),
]


def get_game_field_value(game: dict, field: str) -> str:
    """Extrae el valor en cadena de texto de un campo para un juego, con respaldo en xml_metadata."""
    raw_val = game.get(field)
    if raw_val is not None and str(raw_val).strip() != "":
        return str(raw_val).strip()

    # Si no se encuentra como campo directo, buscar en xml_metadata
    xml_meta = game.get("xml_metadata")
    if xml_meta and xml_meta != "{}":
        try:
            meta_dict = json.loads(xml_meta) if isinstance(xml_meta, str) else xml_meta
            if isinstance(meta_dict, dict):
                cand = meta_dict.get(field)
                if cand is None and "_" in field:
                    cand = meta_dict.get(field.replace("_", ""))
                if cand is None:
                    for k, v in meta_dict.items():
                        if k.lower() == field.lower():
                            cand = v
                            break
                if cand is not None:
                    return str(cand).strip()
        except Exception:
            pass
    return ""


def game_matches_rule(game: dict, field: str, operator: str, target_value: str = "") -> bool:
    """Evalúa si un juego cumple con una regla de filtrado individual."""
    val_str = get_game_field_value(game, field)
    op = (operator or "contains").lower()
    target = (target_value or "").strip().lower()
    val_lower = val_str.lower()

    if op == "contains":
        return target in val_lower if target else True
    elif op in ("not_contains", "does_not_contain", "not contains"):
        return target not in val_lower if target else True
    elif op in ("equals", "eq"):
        return val_lower == target
    elif op in ("not_equals", "neq", "not equals"):
        return val_lower != target
    elif op == "starts_with":
        return val_lower.startswith(target)
    elif op == "ends_with":
        return val_lower.endswith(target)
    elif op == "is_empty":
        return val_str == ""
    elif op == "is_not_empty":
        return val_str != ""
    return False


def game_matches_filter(game: dict, rules: list[dict], match_mode: str = "all") -> bool:
    """
    Evalúa si un juego cumple con un conjunto de reglas de filtrado.
    match_mode: 'all' (AND: cumple todas las reglas) o 'any' (OR: cumple al menos una).
    """
    if not rules:
        return False

    valid_rules = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        f = (r.get("field") or "").strip()
        op = (r.get("operator") or "contains").strip()
        v = (r.get("value") or "").strip()
        if not f:
            continue
        if op not in ("is_empty", "is_not_empty") and not v:
            continue
        valid_rules.append((f, op, v))

    if not valid_rules:
        return True

    mode = (match_mode or "all").lower()
    if mode == "any":
        return any(game_matches_rule(game, f, op, v) for f, op, v in valid_rules)
    else:
        return all(game_matches_rule(game, f, op, v) for f, op, v in valid_rules)


def sync_filtered_list_games(db, list_id: int) -> int:
    """
    Sincroniza los juegos de una lista filtrada a partir de su lista origen y sus reglas de filtrado.
    Limpia los juegos existentes de list_id e inserta los juegos de la lista origen que cumplan el filtro.
    Retorna la cantidad de juegos sincronizados.
    """
    list_info = db.get_list(list_id)
    if not list_info or list_info.get("list_type") != "filtered":
        return 0

    source_id = list_info.get("source_list_id")
    if not source_id:
        return 0

    raw_rules = list_info.get("filter_rules", "[]")
    if isinstance(raw_rules, str):
        try:
            rules = json.loads(raw_rules)
        except Exception:
            rules = []
    elif isinstance(raw_rules, list):
        rules = raw_rules
    else:
        rules = []

    match_mode = list_info.get("filter_match_mode", "all")
    source_games = db.get_games(source_id, enriched=False)
    matching_games = [g for g in source_games if game_matches_filter(g, rules, match_mode)]

    db.begin_batch()
    try:
        db.clear_list_games(list_id)
        for g in matching_games:
            db.insert_game(
                list_id,
                title=g.get("title", ""),
                rom_path=g.get("rom_path", ""),
                rom_name=g.get("rom_name", ""),
                emulator_override_id=g.get("emulator_override_id"),
                launch_arguments=g.get("launch_arguments", ""),
                cover_path=g.get("cover_path", ""),
                notes=g.get("notes", ""),
                year=g.get("year", ""),
                manufacturer=g.get("manufacturer", ""),
                genre=g.get("genre", ""),
                players=g.get("players", ""),
                cloneof=g.get("cloneof", ""),
                rating=g.get("rating", ""),
                crc=g.get("crc", ""),
                sourcefile=g.get("sourcefile", ""),
                xml_metadata=g.get("xml_metadata", "{}"),
                created_at=g.get("created_at", ""),
            )
    finally:
        db.end_batch()

    return len(matching_games)

