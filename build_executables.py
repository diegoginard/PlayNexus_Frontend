"""
Script automatizado para compilar los ejecutables de PlayNexus:
- PlayNexus_Config.exe (Configurador)
- PlayNexus_Launcher.exe (Frontend / Jugador)
"""
import sys
import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

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
    print("1/2: Compilando PlayNexus_Config.exe...")
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
    print("2/2: Compilando PlayNexus_Launcher.exe...")
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

    # Copiar ejecutables a la raíz para acceso directo
    dist_dir = ROOT_DIR / "dist"
    config_exe = dist_dir / "PlayNexus_Config.exe"
    launcher_exe = dist_dir / "PlayNexus_Launcher.exe"

    if config_exe.exists():
        dest_config = ROOT_DIR / "PlayNexus_Config.exe"
        shutil.copy2(config_exe, dest_config)
        print(f"\n[OK] Generado: {dest_config}")

    if launcher_exe.exists():
        dest_launcher = ROOT_DIR / "PlayNexus_Launcher.exe"
        shutil.copy2(launcher_exe, dest_launcher)
        print(f"[OK] Generado: {dest_launcher}")

    print("\n¡Compilación completada con éxito!")

if __name__ == "__main__":
    build()

