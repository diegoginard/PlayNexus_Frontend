from pathlib import Path
import os
import shlex
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
    from retroshelf.services.emulator_manager import EMULATOR_MANAGER
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

    exe = Path(emulator["executable"])
    if not exe.exists():
        raise FileNotFoundError(f"No se encontró el ejecutable del emulador en la ruta configurada:\n{exe}")

    rom = Path(game["rom_path"])
    if not rom.exists():
        raise FileNotFoundError(f"No se encontró el archivo o carpeta del juego en el disco:\n{rom}")

    rom_str = str(rom)
    rom_dir_str = str(rom.parent)
    rom_name_str = rom.name if rom.is_dir() else rom.stem

    # Prioridad de argumentos: argumentos personalizados del juego > argumentos del emulador > '"{rom}"'
    custom_args = (game["launch_arguments"] or "").strip()
    emu_args = (emulator["arguments"] or "").strip()
    template = custom_args or emu_args or '"{rom}"'

    rendered = template

    # Reemplazo de comodines compatibles con Attract-Mode, LaunchBox y variables de entorno
    attract_wildcards = {
        "[romfilename]": rom_str,
        "[rom_filename]": rom_str,
        "[rompath]": rom_dir_str,
        "[rom_path]": rom_dir_str,
        "[romdir]": rom_dir_str,
        "[rom_dir]": rom_dir_str,
        "[romname]": rom_name_str,
        "[rom_name]": rom_name_str,
        "[name]": rom_name_str,
        "[rom]": rom_str,
        "%ROM%": rom_str,
        "%rom%": rom_str,
        "%1": rom_str,
    }
    for pattern, replacement in attract_wildcards.items():
        if pattern in rendered:
            rendered = rendered.replace(pattern, replacement)

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

    # Ejecutar emulador sin bloquear la aplicación
    proc = subprocess.Popen([str(exe), *args], cwd=str(exe.parent))

    # Iniciar monitoreo del proceso (silenciar videos de fondo y capturar tecla global de salida)
    try:
        from retroshelf.services.emulator_manager import EMULATOR_MANAGER
        game_title = game.get("title", emulator["name"]) if isinstance(game, dict) else emulator["name"]
        EMULATOR_MANAGER.start_monitoring(proc, game_title, layout, db, parent_window)
    except Exception:
        pass

    return emulator["name"], source
