from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess

from playnexus.i18n import tr

_SHELL_EXECUTABLES = ("cmd", "powershell", "pwsh", "explorer", "start")
_SCRIPT_EXTENSIONS = (".bat", ".cmd", ".lnk", ".url", ".ps1")
_ROM_PLACEHOLDER_RE = re.compile(
    r"(\[(?:romfilename|rom_filename|rompath|rom_path|romdir|rom_dir|"
    r"romname|rom_name|name|cleanromname|clean_rom_name|rom)\]"
    r"|%rom%|%1"
    r"|\{(?:rom|rom_dir|rom_name|romfilename|rompath|romname|name)\})",
    re.IGNORECASE,
)


def has_rom_placeholder(template: str) -> bool:
    """Indica si una plantilla de argumentos referencia algún marcador de ROM."""
    return bool(_ROM_PLACEHOLDER_RE.search(template or ""))


def resolve_executable_path(exe_raw: str) -> Path:
    """Resuelve la ruta real del ejecutable del emulador o comando en PATH."""
    clean = (exe_raw or "").strip()
    if not clean:
        raise FileNotFoundError(
            tr(
                "svc.launch.err_emu_not_found",
                "Emulator executable not found at the configured path:\n{path}",
                path=clean,
            )
        )
    exe = Path(clean)
    if exe.is_file():
        return exe
    resolved_which = shutil.which(clean)
    if resolved_which:
        return Path(resolved_which)
    raise FileNotFoundError(
        tr(
            "svc.launch.err_emu_not_found",
            "Emulator executable not found at the configured path:\n{path}",
            path=clean,
        )
    )


def _autocorrect_core_paths(args: list[str], exe: Path) -> list[str]:
    """Corrige rutas inexistentes a librerías/cores buscando junto al ejecutable."""
    fixed = list(args)
    for i, arg in enumerate(fixed):
        if arg.lower().endswith(".dll") or (i > 0 and fixed[i - 1].lower() in ("-l", "/l")):
            p_arg = Path(arg)
            if not p_arg.exists():
                candidate_cores = exe.parent / "cores" / p_arg.name
                if candidate_cores.exists():
                    fixed[i] = str(candidate_cores)
                else:
                    candidate_root = exe.parent / p_arg.name
                    if candidate_root.exists():
                        fixed[i] = str(candidate_root)
    return fixed


def build_emulator_command(
    exe_raw: str,
    template: str = "",
    rom_path: str | Path | None = None,
) -> tuple[list[str], str]:
    """
    Construye `(comando, working_dir)` para ejecutar un emulador con o sin ROM.
    Si `rom_path` se provee, reemplaza los comodines y añade la ROM si no aparece.
    """
    exe = resolve_executable_path(exe_raw)
    tpl = (template or "").strip()

    if rom_path is not None:
        rom = Path(rom_path)
        if not rom.exists():
            raise FileNotFoundError(
                tr(
                    "svc.launch.err_rom_not_found",
                    "Game file or folder not found on disk:\n{path}",
                    path=rom,
                )
            )

        rom_str = os.path.normpath(str(rom.resolve()))
        rom_dir_str = os.path.normpath(str(rom.resolve().parent))
        rom_name_str = rom.name if rom.is_dir() else rom.stem
        rendered = tpl or '"{rom}"'

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
                    s = match.string
                    prefix = s[max(0, match.start() - 1):match.start()]
                    suffix = s[match.end():min(len(s), match.end() + 1)]
                    if prefix == '"' and suffix == '"':
                        return r
                    if " " in r and suffix not in ("\\", "/", '"') and prefix not in ("\\", "/", '"'):
                        return f'"{r}"'
                    return r
                return _repl
            rendered = re.sub(pat, _make_replacer(rep), rendered, flags=re.IGNORECASE)

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

        if rom_str not in rendered and rom_name_str not in rendered:
            rendered = f'{rendered} "{rom_name_str if rom.is_dir() else rom_str}"'.strip()

        raw_args = shlex.split(rendered, posix=False)
        args = _autocorrect_core_paths([a.strip('"') for a in raw_args], exe)

        is_shell_exec = exe.stem.lower() in _SHELL_EXECUTABLES
        is_script_rom = rom.suffix.lower() in _SCRIPT_EXTENSIONS
        working_dir = rom_dir_str if (is_shell_exec or is_script_rom) else str(exe.parent)
        return [str(exe), *args], working_dir

    args: list[str] = []
    if tpl:
        raw_args = shlex.split(tpl, posix=False)
        args = _autocorrect_core_paths([a.strip('"') for a in raw_args], exe)
    return [str(exe), *args], str(exe.parent)


def launch_emulator_process(
    exe_raw: str,
    template: str = "",
    rom_path: str | Path | None = None,
) -> tuple[subprocess.Popen, list[str], str]:
    """Lanza un proceso de emulador aislado (útil para configuración o prueba de argumentos)."""
    cmd, working_dir = build_emulator_command(exe_raw, template=template, rom_path=rom_path)
    env = os.environ.copy()
    env["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
    proc = subprocess.Popen(cmd, cwd=working_dir, env=env)
    return proc, cmd, working_dir

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
            tr(
                "svc.launch.err_no_emulator",
                "This game has no assigned emulator.\n"
                "You can assign a default emulator to the list or assign a specific one to this game.",
            )
        )

    custom_args = (game["launch_arguments"] or "").strip()
    emu_args = (emulator["arguments"] or "").strip()
    template = custom_args or emu_args or '"{rom}"'

    proc, _cmd, _wd = launch_emulator_process(
        emulator["executable"] or "",
        template=template,
        rom_path=game["rom_path"],
    )

    # Iniciar monitoreo del proceso (silenciar videos de fondo, bezel overlay y capturar tecla global de salida)
    try:
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        game_title = game.get("title", emulator["name"]) if isinstance(game, dict) else emulator["name"]
        EMULATOR_MANAGER.start_monitoring(proc, game_title, layout, db, parent_window, game=game, emulator=emulator)
    except Exception:
        pass

    return emulator["name"], source
