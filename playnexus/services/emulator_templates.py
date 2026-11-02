"""
Servicio de gestión de Plantillas Rápidas de Emuladores para PlayNexus.
Permite cargar, guardar, editar y restaurar plantillas de emuladores
almacenadas en Texto Plano (config/emulator_templates.txt).
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Directorio raíz del aplicativo
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent.parent

CONFIG_DIR = APP_DIR / "config"
TEMPLATES_FILE = CONFIG_DIR / "emulator_templates.txt"

# Plantillas oficiales predeterminadas
DEFAULT_EMULATOR_TEMPLATES: list[dict[str, str]] = [
    {
        "name": "Juegos de Windows / PC (cmd.exe)",
        "executable": "cmd",
        "arguments": '/c "[romfilename]"',
        "platform": "PC Games",
        "description": "Lanza ejecutables (.exe), accesos directos (.lnk) y scripts (.bat) con cwd en la carpeta del juego.",
    },
    {
        "name": "RetroArch (General)",
        "executable": "retroarch.exe",
        "arguments": '-f -L cores\\nombre_core_libretro.dll "{rom}"',
        "platform": "Multi-sistema",
        "description": "Inicia RetroArch en pantalla completa cargando el núcleo especificado.",
    },
    {
        "name": "RetroArch - Genesis Plus GX (Mega Drive)",
        "executable": "retroarch.exe",
        "arguments": '-f -L cores\\genesis_plus_gx_libretro.dll "{rom}"',
        "platform": "Sega Genesis",
        "description": "Núcleo de alta compatibilidad para Sega Genesis / Mega Drive y Master System.",
    },
    {
        "name": "RetroArch - Snes9x (Super Nintendo)",
        "executable": "retroarch.exe",
        "arguments": '-f -L cores\\snes9x_libretro.dll "{rom}"',
        "platform": "Super Nintendo",
        "description": "Núcleo Snes9x para Super Nintendo / Super Famicom.",
    },
    {
        "name": "RetroArch - Beetle PSX (PlayStation 1)",
        "executable": "retroarch.exe",
        "arguments": '-f -L cores\\mednafen_psx_hw_libretro.dll "{rom}"',
        "platform": "Sony PlayStation",
        "description": "Núcleo Beetle PSX HW con renderizado por hardware.",
    },
    {
        "name": "RetroArch - Mupen64Plus (Nintendo 64)",
        "executable": "retroarch.exe",
        "arguments": '-f -L cores\\mupen64plus_next_libretro.dll "{rom}"',
        "platform": "Nintendo 64",
        "description": "Núcleo Mupen64Plus-Next de alto rendimiento para N64.",
    },
    {
        "name": "MAME (Arcade Oficial)",
        "executable": "mame.exe",
        "arguments": "[name] -skip_gameinfo",
        "platform": "Arcade",
        "description": "Lanza la ROM de arcade en MAME omitiendo pantallas de diagnóstico inicial.",
    },
    {
        "name": "DuckStation (PlayStation 1)",
        "executable": "duckstation-qt-x64-ReleaseLTCG.exe",
        "arguments": '-batch -fullscreen "[romfilename]"',
        "platform": "Sony PlayStation",
        "description": "Emulador DuckStation moderno en modo batch a pantalla completa.",
    },
    {
        "name": "PCSX2 (PlayStation 2)",
        "executable": "pcsx2-qtx64.exe",
        "arguments": '-nogui -fullscreen -- "[romfilename]"',
        "platform": "Sony PlayStation 2",
        "description": "PCSX2 Qt en modo pantalla completa sin GUI.",
    },
    {
        "name": "Dolphin (GameCube / Wii)",
        "executable": "Dolphin.exe",
        "arguments": '-b -e "[romfilename]"',
        "platform": "Nintendo GameCube",
        "description": "Dolphin en modo batch / arranque directo del juego.",
    },
    {
        "name": "PPSSPP (Sony PSP)",
        "executable": "PPSSPPWindows64.exe",
        "arguments": '"[romfilename]"',
        "platform": "Sony PSP",
        "description": "Emulador PPSSPP para PlayStation Portable en pantalla completa.",
    },
    {
        "name": "Flycast (Dreamcast / Naomi)",
        "executable": "flycast.exe",
        "arguments": '"[romfilename]"',
        "platform": "Sega Dreamcast",
        "description": "Emulador Flycast para Sega Dreamcast, Naomi y Naomi 2.",
    },
    {
        "name": "RPCS3 (PlayStation 3)",
        "executable": "rpcs3.exe",
        "arguments": '--no-gui "[romfilename]"',
        "platform": "Sony PlayStation 3",
        "description": "RPCS3 para PS3 en modo directo sin interfaz.",
    },
]


def _escape(val: str) -> str:
    """Escapa separadores de punto y coma y saltos de línea."""
    return str(val or "").replace("\\", "\\\\").replace(";", "\\;").replace("\n", "\\n").replace("\r", "")


def _unescape(val: str) -> str:
    """Restaura caracteres escapados."""
    res = []
    i = 0
    s = str(val or "")
    n = len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == ";":
                res.append(";")
                i += 2
                continue
            elif nxt == "n":
                res.append("\n")
                i += 2
                continue
            elif nxt == "\\":
                res.append("\\")
                i += 2
                continue
        res.append(s[i])
        i += 1
    return "".join(res)


def _split_row(line: str) -> list[str]:
    """Divide una línea por ';' respetando el escape '\\;'."""
    parts = []
    curr = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "\\" and i + 1 < n:
            curr.append(line[i : i + 2])
            i += 2
            continue
        elif line[i] == ";":
            parts.append(_unescape("".join(curr)))
            curr = []
            i += 1
            continue
        curr.append(line[i])
        i += 1
    parts.append(_unescape("".join(curr)))
    return parts


def get_templates_file_path(custom_dir: Path | str | None = None) -> Path:
    """Retorna la ruta al archivo de texto plano de plantillas de emuladores."""
    if custom_dir:
        return Path(custom_dir) / "emulator_templates.txt"
    return TEMPLATES_FILE


def load_emulator_templates(custom_dir: Path | str | None = None) -> list[dict[str, str]]:
    """
    Carga la lista de plantillas de emulador desde config/emulator_templates.txt.
    Si el archivo no existe, lo crea automáticamente con las plantillas predeterminadas.
    """
    path = get_templates_file_path(custom_dir)
    if not path.exists():
        save_emulator_templates(DEFAULT_EMULATOR_TEMPLATES, custom_dir=custom_dir)
        return [dict(t) for t in DEFAULT_EMULATOR_TEMPLATES]

    templates: list[dict[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = _split_row(line)
            if len(parts) >= 3:
                name = parts[0].strip()
                exe = parts[1].strip()
                args = parts[2].strip()
                plat = parts[3].strip() if len(parts) > 3 else ""
                desc = parts[4].strip() if len(parts) > 4 else ""
                templates.append({
                    "name": name,
                    "executable": exe,
                    "arguments": args,
                    "platform": plat,
                    "description": desc,
                })
    except Exception as e:
        print(f"Error al cargar {path}: {e}")
        return [dict(t) for t in DEFAULT_EMULATOR_TEMPLATES]

    return templates if templates else [dict(t) for t in DEFAULT_EMULATOR_TEMPLATES]


def save_emulator_templates(templates: list[dict[str, str]], custom_dir: Path | str | None = None) -> None:
    """
    Guarda la lista completa de plantillas en config/emulator_templates.txt.
    """
    path = get_templates_file_path(custom_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    header = [
        "# Plantillas Rápidas de Emuladores para PlayNexus (Texto Plano)",
        "# Formato: nombre;ejecutable;argumentos;plataforma;descripcion",
        "# Este archivo puede ser editado directamente o desde Configuración del Sistema en la aplicación.",
        "",
    ]
    rows = []
    for t in templates:
        name = _escape(t.get("name", ""))
        exe = _escape(t.get("executable", ""))
        args = _escape(t.get("arguments", ""))
        plat = _escape(t.get("platform", ""))
        desc = _escape(t.get("description", ""))
        rows.append(f"{name};{exe};{args};{plat};{desc}")

    content = "\n".join(header + rows) + "\n"
    path.write_text(content, encoding="utf-8")


def reset_default_templates(custom_dir: Path | str | None = None) -> list[dict[str, str]]:
    """
    Restaura el archivo a las plantillas oficiales predeterminadas.
    """
    save_emulator_templates(DEFAULT_EMULATOR_TEMPLATES, custom_dir=custom_dir)
    return [dict(t) for t in DEFAULT_EMULATOR_TEMPLATES]

