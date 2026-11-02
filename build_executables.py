"""
Script automatizado para compilar los ejecutables de PlayNexus y
empaquetar la distribución limpia y completa en la carpeta bin/:
- bin/PlayNexus_Config.exe (Configurador)
- bin/PlayNexus_Launcher.exe (Frontend / Jugador)
- bin/PlayNexus_Logo.png
- bin/app_icon.ico
- bin/config/ (settings.txt limpio, emulator_templates.txt)
- bin/emulators/
- bin/lists/
- bin/icons/
- bin/Layouts/
"""
import sys
import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BIN_DIR = ROOT_DIR / "bin"

CLEAN_SETTINGS = """# Configuración del Sistema PlayNexus (Limpio)
video_mode = fullscreen
video_resolution = system
video_driver = d3d11
video_ui_scale = 100% (Normal)
video_show_fps = false
emulator_mute_video = true
emulator_global_exit = true
emulator_gamepad_exit = true
control_nav_up = Up
control_nav_down = Down
control_nav_letter = Left
control_nav_step5 = Right
control_select_game = Return
control_nav_back = Backspace
control_close_emulator = Escape
control_mute_video = M
control_close_frontend = F4
control_toggle_fps = F10
gamepad_nav_up = D-Pad Up
gamepad_nav_down = D-Pad Down
gamepad_nav_letter = D-Pad Left
gamepad_nav_step5 = D-Pad Right
gamepad_select_game = A
gamepad_nav_back = B
gamepad_close_emulator = Back+Start
gamepad_mute_video = Y
gamepad_page_up = LB
gamepad_page_down = RB
gamepad_toggle_fps = R-Thumb
"""

def setup_clean_environment(bin_dir: Path):
    """Crea la estructura limpia y copia todos los recursos necesarios dentro de bin/."""
    print("\n==================================================")
    print("3/3: Ensamblando entorno limpio en bin/...")
    print("==================================================")
    bin_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copiar logotipo e icono
    logo_file = ROOT_DIR / "PlayNexus_Logo.png"
    if logo_file.exists():
        shutil.copy2(logo_file, bin_dir / "PlayNexus_Logo.png")
        print(" [OK] Logotipo: PlayNexus_Logo.png copiado.")

    icon_file = ROOT_DIR / "app_icon.ico"
    if icon_file.exists():
        shutil.copy2(icon_file, bin_dir / "app_icon.ico")
        print(" [OK] Icono: app_icon.ico copiado.")

    # 2. Carpeta config/ con archivos limpios
    config_dir = bin_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    tmpl_src = ROOT_DIR / "config" / "emulator_templates.txt"
    if tmpl_src.exists():
        shutil.copy2(tmpl_src, config_dir / "emulator_templates.txt")
        print(" [OK] Plantillas: config/emulator_templates.txt copiado.")

    dest_settings = config_dir / "settings.txt"
    if not dest_settings.exists():
        dest_settings.write_text(CLEAN_SETTINGS, encoding="utf-8")
        print(" [OK] Configuración: config/settings.txt inicial creado.")

    # 3. Carpetas vacías emulators/ y lists/
    (bin_dir / "emulators").mkdir(parents=True, exist_ok=True)
    (bin_dir / "lists").mkdir(parents=True, exist_ok=True)
    print(" [OK] Directorios limpios: emulators/ y lists/ preparados.")

    # 4. Copiar icons/
    icons_src = ROOT_DIR / "icons"
    icons_dest = bin_dir / "icons"
    if icons_src.exists():
        if icons_dest.exists():
            shutil.rmtree(icons_dest)
        shutil.copytree(icons_src, icons_dest)
        print(" [OK] Iconos: carpeta icons/ copiada.")

    # 5. Copiar Layouts/ (excluyendo Media y cachés para mantener limpio y ligero)
    layouts_src = ROOT_DIR / "Layouts"
    layouts_dest = bin_dir / "Layouts"
    if layouts_src.exists():
        if layouts_dest.exists():
            shutil.rmtree(layouts_dest)
        shutil.copytree(
            layouts_src,
            layouts_dest,
            ignore=shutil.ignore_patterns("Media", ".cache", "__pycache__", "*.pyc")
        )
        print(" [OK] Temas y Diseños: carpeta Layouts/ copiada (limpia).")

    # 6. Copiar ejecutables desde dist/ hacia bin/
    dist_dir = ROOT_DIR / "dist"
    config_exe = dist_dir / "PlayNexus_Config.exe"
    launcher_exe = dist_dir / "PlayNexus_Launcher.exe"

    if config_exe.exists():
        dest_config = bin_dir / "PlayNexus_Config.exe"
        shutil.copy2(config_exe, dest_config)
        print(f" [OK] Ejecutable: {dest_config}")

    if launcher_exe.exists():
        dest_launcher = bin_dir / "PlayNexus_Launcher.exe"
        shutil.copy2(launcher_exe, dest_launcher)
        print(f" [OK] Ejecutable: {dest_launcher}")

    # Remover ejecutables obsoletos de la raíz si existen
    for old_name in ("PlayNexus_Config.exe", "PlayNexus_Launcher.exe"):
        old_exe = ROOT_DIR / old_name
        if old_exe.exists():
            try:
                old_exe.unlink()
                print(f" [OK] Removido binario redundante de la raíz: {old_name}")
            except Exception:
                pass


def build():
    pyinstaller_exe = ROOT_DIR / ".venv" / "Scripts" / "pyinstaller.exe"
    if not pyinstaller_exe.exists():
        pyinstaller_exe = Path(sys.executable).parent / "pyinstaller.exe"

    if not pyinstaller_exe.exists():
        print(f"Error: No se encontró pyinstaller en {pyinstaller_exe}")
        sys.exit(1)

    icon_arg = []
    icon_file = ROOT_DIR / "app_icon.ico"
    if icon_file.exists():
        icon_arg = ["--icon", str(icon_file)]

    common_args = [
        str(pyinstaller_exe),
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--collect-all", "playnexus",
        "--collect-submodules", "PySide6.QtMultimedia",
        "--collect-submodules", "PySide6.QtMultimediaWidgets",
        "--hidden-import", "PySide6.QtMultimedia",
        "--hidden-import", "PySide6.QtMultimediaWidgets",
        "--hidden-import", "shutil",
        "--hidden-import", "ctypes",
        "--hidden-import", "json",
        *icon_arg,
    ]

    print("==================================================")
    print("1/3: Compilando PlayNexus_Config.exe...")
    print("==================================================")
    cmd_config = [
        *common_args,
        "--name", "PlayNexus_Config",
        str(ROOT_DIR / "entry_config.py"),
    ]
    res_config = subprocess.run(cmd_config, cwd=str(ROOT_DIR))
    if res_config.returncode != 0:
        print("Error al compilar PlayNexus_Config.exe")
        sys.exit(res_config.returncode)

    print("\n==================================================")
    print("2/3: Compilando PlayNexus_Launcher.exe...")
    print("==================================================")
    cmd_launcher = [
        *common_args,
        "--name", "PlayNexus_Launcher",
        str(ROOT_DIR / "entry_launcher.py"),
    ]
    res_launcher = subprocess.run(cmd_launcher, cwd=str(ROOT_DIR))
    if res_launcher.returncode != 0:
        print("Error al compilar PlayNexus_Launcher.exe")
        sys.exit(res_launcher.returncode)

    # Configurar y poblar la carpeta bin/ limpia
    setup_clean_environment(BIN_DIR)

    print("\n¡Distribución limpia generada con éxito en la carpeta bin/!")


if __name__ == "__main__":
    build()
