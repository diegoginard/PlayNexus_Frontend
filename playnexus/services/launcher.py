from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess

def resolve_emulator(db, game):
    """
    Determina qué emulador utilizar según la prioridad obligatoria:
    1. Emulador asignado individualmente al juego, si existe.
    2. Emulador predeterminado de la lista.
    3. Si ninguno existe, retorna (None, "ninguno").
    """
    if game.get("emulator_override_id"):
        row = db.get_emulator(game["emulator_override_id"])
        if row and row.get("id") is not None:
            return row, "juego"

    row = db.get_default_emulator_for_list(game["list_id"])
    if row and row.get("id") is not None:
        return row, "lista"

    return None, "ninguno"

def launch_game(db, game, layout=None, parent_window=None):
    """
    Lanza el emulador correspondiente con los argumentos configurados y la ROM.
    Inicia la supervisión automática para silenciar videos y permitir cerrar el emulador con la tecla configurada.
    """
    from playnexus.services.emulator_manager import EMULATOR_MANAGER
    if EMULATOR_MANAGER.is_launching_or_running():
        # Evitar abrir múltiples instancias del juego por doble clic, joystick o teclado
        return None, "en_ejecucion"

    EMULATOR_MANAGER.mark_launching()
    try:
        return _launch_game_impl(db, game, layout, parent_window)
    except Exception:
        # Si el inicio falló antes de crear el proceso, no bloquear el siguiente intento
        if not EMULATOR_MANAGER.is_running():
            EMULATOR_MANAGER.clear_launching()
        raise


def _launch_game_impl(db, game, layout=None, parent_window=None):
    """Resuelve el emulador, arma los argumentos y crea el proceso del emulador."""
    emulator, source = resolve_emulator(db, game)
    if not emulator:
        raise RuntimeError(
            "Este juego no tiene ningún emulador asignado.\n"
            "Podés asignar un emulador predeterminado a la lista o asignarle uno específico a este juego."
        )

    exe_raw = (emulator["executable"] or "").strip()
    exe = Path(exe_raw)
    if not exe.is_file():
        # Resolver si es un comando o binario en PATH (ej: 'cmd', 'cmd.exe', 'powershell', etc.)
        resolved_which = shutil.which(exe_raw)
        if resolved_which:
            exe = Path(resolved_which)
        else:
            raise FileNotFoundError(f"No se encontró el ejecutable del emulador en la ruta configurada:\n{exe_raw}")

    rom = Path(game["rom_path"])
    if not rom.exists():
        raise FileNotFoundError(f"No se encontró el archivo o carpeta del juego en el disco:\n{rom}")

    # Rutas nativas normalizadas con barras invertidas para compatibilidad total en Windows
    rom_str = os.path.normpath(str(rom.resolve()))
    rom_dir_str = os.path.normpath(str(rom.resolve().parent))
    rom_name_str = rom.name if rom.is_dir() else rom.stem

    # Prioridad de argumentos: argumentos personalizados del juego > argumentos del emulador > '"{rom}"'
    custom_args = (game["launch_arguments"] or "").strip()
    emu_args = (emulator["arguments"] or "").strip()
    template = custom_args or emu_args or '"{rom}"'

    rendered = template

    # Reemplazo de comodines compatibles con Attract-Mode, LaunchBox y variables de entorno
    # Soporta cualquier combinación de mayúsculas/minúsculas ([romfilename], [ROMFILENAME], [name], etc.)
    attract_wildcard_patterns = [
        (r"\[romfilename\]", rom_str),
        (r"\[rom_filename\]", rom_str),
        (r"\[rompath\]", rom_dir_str),
        (r"\[rom_path\]", rom_dir_str),
        (r"\[romdir\]", rom_dir_str),
        (r"\[rom_dir\]", rom_dir_str),
        (r"\[romname\]", rom_name_str),
        (r"\[rom_name\]", rom_name_str),
        (r"\[name\]", rom_name_str),
        (r"\[cleanromname\]", rom_name_str),
        (r"\[clean_rom_name\]", rom_name_str),
        (r"\[rom\]", rom_str),
        (r"%rom%", rom_str),
        (r"%1", rom_str),
    ]
    for pat, rep in attract_wildcard_patterns:
        def _make_replacer(r):
            def _repl(match):
                # Si el patrón no está entre comillas dobles y el valor contiene espacios,
                # protegerlo con comillas para evitar fragmentación en shlex
                s = match.string
                prefix = s[max(0, match.start()-1):match.start()]
                suffix = s[match.end():min(len(s), match.end()+1)]
                if prefix == '"' and suffix == '"':
                    return r
                if " " in r and suffix not in ("\\", "/", '"') and prefix not in ("\\", "/", '"'):
                    return f'"{r}"'
                return r
            return _repl
        rendered = re.sub(pat, _make_replacer(rep), rendered, flags=re.IGNORECASE)

    # Reemplazo de comodines estilo Python ({rom}, {rom_dir}, {rom_name}, etc.)
    try:
        rendered = rendered.format(
            rom=rom_str,
            rom_dir=rom_dir_str,
            rom_name=rom_name_str,
            romfilename=rom_str,
            rompath=rom_dir_str,
            romname=rom_name_str,
            name=rom_name_str,
        )
    except (KeyError, ValueError, IndexError):
        pass

    # Si la plantilla no contenía ningún marcador de la ROM, añadirla automáticamente al final
    if rom_str not in rendered and rom_name_str not in rendered:
        rendered = f'{rendered} "{rom_name_str if rom.is_dir() else rom_str}"'.strip()

    # Separar argumentos en Windows sin invocar cmd/shell
    args = shlex.split(rendered, posix=False)
    args = [a.strip('"') for a in args]

    # Auto-corrección inteligente de rutas a cores si el usuario configuró una ruta inexistente (ej: C:\retroarch\cores\...)
    for i in range(len(args)):
        arg = args[i]
        if arg.lower().endswith(".dll") or (i > 0 and args[i-1].lower() in ("-l", "/l")):
            p_arg = Path(arg)
            if not p_arg.exists():
                candidate_cores = exe.parent / "cores" / p_arg.name
                if candidate_cores.exists():
                    args[i] = str(candidate_cores)
                else:
                    candidate_root = exe.parent / p_arg.name
                    if candidate_root.exists():
                        args[i] = str(candidate_root)

    # Determinar el directorio de trabajo (cwd):
    # Si el ejecutable es cmd/shell o el juego es un script/enlace (.bat, .cmd, .lnk),
    # el working directory debe ser la carpeta donde reside la ROM/script para que encuentre sus archivos locales
    is_shell_exec = exe.stem.lower() in ("cmd", "powershell", "pwsh", "explorer", "start")
    is_script_rom = rom.suffix.lower() in (".bat", ".cmd", ".lnk", ".url", ".ps1")
    if is_shell_exec or is_script_rom:
        working_dir = rom_dir_str
    else:
        working_dir = str(exe.parent)

    # Ejecutar emulador sin bloquear la aplicación
    proc = subprocess.Popen([str(exe), *args], cwd=working_dir)

    # Iniciar monitoreo del proceso (silenciar videos de fondo, bezel overlay y capturar tecla global de salida)
    try:
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        game_title = game.get("title", emulator["name"]) if isinstance(game, dict) else emulator["name"]
        EMULATOR_MANAGER.start_monitoring(proc, game_title, layout, db, parent_window, game=game)
    except Exception:
        pass

    return emulator["name"], source
