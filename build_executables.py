"""
Script automatizado para compilar los ejecutables de PlayNexus y
empaquetar la distribución limpia y completa en la carpeta dist/:
- dist/PlayNexus_Config.exe (Configurador)
- dist/PlayNexus_Launcher.exe (Frontend / Jugador)
- dist/PlayNexus_Logo.png
- dist/app_icon.ico
- dist/config/ (settings.txt limpio, emulator_templates.txt)
- dist/emulators/
- dist/lists/
- dist/icons/
- dist/Layouts/
- dist/splash/
"""
import sys
import shutil
import struct
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"

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
control_toggle_bezel = F11
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
gamepad_toggle_bezel = L-Thumb
screensaver_enabled = true
screensaver_timeout = 3
screensaver_mode_basic_movie = true
screensaver_mode_movie_collage = true
screensaver_mode_image_collage = true
screensaver_mode_rgb_movie = true
screensaver_overlay_art = wheel
screensaver_sound = true
screensaver_preserve_ar = false
screensaver_blank_time = 60
"""

def setup_clean_environment(dist_dir: Path):
    """Crea la estructura limpia y copia todos los recursos necesarios dentro de dist/."""
    print("\n==================================================")
    print("3/3: Ensamblando entorno limpio en dist/...")
    print("==================================================")
    dist_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copiar logotipo e icono
    logo_file = ROOT_DIR / "PlayNexus_Logo.png"
    if logo_file.exists():
        shutil.copy2(logo_file, dist_dir / "PlayNexus_Logo.png")
        print(" [OK] Logotipo: PlayNexus_Logo.png copiado.")

    icon_file = ROOT_DIR / "app_icon.ico"
    if icon_file.exists():
        shutil.copy2(icon_file, dist_dir / "app_icon.ico")
        print(" [OK] Icono: app_icon.ico copiado.")

    icon_png = ROOT_DIR / "PlayNexus_icon.png"
    if icon_png.exists():
        shutil.copy2(icon_png, dist_dir / "PlayNexus_icon.png")
        print(" [OK] Icono PNG: PlayNexus_icon.png copiado.")

    # 2. Carpeta config/ con archivos limpios
    config_dir = dist_dir / "config"
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
    (dist_dir / "emulators").mkdir(parents=True, exist_ok=True)
    (dist_dir / "lists").mkdir(parents=True, exist_ok=True)
    print(" [OK] Directorios limpios: emulators/ y lists/ preparados.")

    # 4. Copiar icons/
    icons_src = ROOT_DIR / "icons"
    icons_dest = dist_dir / "icons"
    if icons_src.exists():
        if icons_dest.exists():
            shutil.rmtree(icons_dest)
        shutil.copytree(icons_src, icons_dest)
        print(" [OK] Iconos: carpeta icons/ copiada.")

    # 5. Copiar Layouts/ (excluyendo Media y cachés para mantener limpio y ligero)
    layouts_src = ROOT_DIR / "Layouts"
    layouts_dest = dist_dir / "Layouts"
    if layouts_src.exists():
        if layouts_dest.exists():
            shutil.rmtree(layouts_dest)
        shutil.copytree(
            layouts_src,
            layouts_dest,
            ignore=shutil.ignore_patterns("Media", ".cache", "__pycache__", "*.pyc")
        )
        print(" [OK] Temas y Diseños: carpeta Layouts/ copiada (limpia).")

    # 5b. Copiar splash/
    splash_src = ROOT_DIR / "splash"
    splash_dest = dist_dir / "splash"
    if splash_src.exists():
        if splash_dest.exists():
            shutil.rmtree(splash_dest)
        shutil.copytree(splash_src, splash_dest)
        print(" [OK] Splash Screen: carpeta splash/ copiada.")

    # 6. Verificar ejecutables en dist/
    config_exe = dist_dir / "PlayNexus_Config.exe"
    launcher_exe = dist_dir / "PlayNexus_Launcher.exe"

    if config_exe.exists():
        print(f" [OK] Ejecutable: {config_exe}")

    if launcher_exe.exists():
        print(f" [OK] Ejecutable: {launcher_exe}")

    # Remover carpeta bin/ obsoleta si existe
    old_bin = ROOT_DIR / "bin"
    if old_bin.exists():
        try:
            shutil.rmtree(old_bin)
            print(" [OK] Carpeta obsoleta bin/ eliminada.")
        except Exception:
            pass

    # Remover ejecutables obsoletos de la raíz si existen
    for old_name in ("PlayNexus_Config.exe", "PlayNexus_Launcher.exe"):
        old_exe = ROOT_DIR / old_name
        if old_exe.exists():
            try:
                old_exe.unlink()
                print(f" [OK] Removido binario redundante de la raíz: {old_name}")
            except Exception:
                pass


def ensure_icon():
    """Genera o actualiza app_icon.ico con todas las resoluciones estándar de Windows (256, 128, 64, 48, 32, 24, 16 px)."""
    src_png = ROOT_DIR / "PlayNexus_icon.png"
    ico_dest = ROOT_DIR / "app_icon.ico"
    if not src_png.exists():
        return
    try:
        from PySide6.QtCore import Qt, QBuffer, QIODevice
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        src = QImage(str(src_png))
        if src.isNull():
            return
        sizes = [256, 128, 64, 48, 32, 24, 16]
        png_buffers = []
        for s in sizes:
            scaled = src.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            scaled.save(buf, "PNG")
            png_buffers.append((s, bytes(buf.data())))

        header = struct.pack("<HHH", 0, 1, len(sizes))
        offset = 6 + (len(sizes) * 16)
        entries_bytes = bytearray()
        data_bytes = bytearray()
        for s, data in png_buffers:
            w = 0 if s == 256 else s
            h = 0 if s == 256 else s
            entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
            entries_bytes.extend(entry)
            data_bytes.extend(data)
            offset += len(data)

        with open(ico_dest, "wb") as f:
            f.write(header)
            f.write(entries_bytes)
            f.write(data_bytes)
        print(" [OK] Icono multi-resolución generado (256, 128, 64, 48, 32, 24, 16 px).")
    except Exception as e:
        print(f" [!] Advertencia al generar icono: {e}")


def build():
    ensure_icon()
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

    # Configurar y poblar la carpeta dist/ limpia
    setup_clean_environment(DIST_DIR)

    print("\n¡Distribución limpia generada con éxito en la carpeta dist/!")


if __name__ == "__main__":
    build()
