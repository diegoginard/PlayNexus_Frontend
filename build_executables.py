"""
Script automatizado para compilar los ejecutables de PlayNexus y
empaquetar la distribución limpia y completa en la carpeta dist/:
- dist/PlayNexus_Config.exe (Configurador)
- dist/PlayNexus_Launcher.exe (Frontend / Jugador)
- dist/_internal/ (runtime compartido de Python/PySide6/OpenGL/FFmpeg en modo --onedir)
- dist/PlayNexus_Logo.png
- dist/app_icon.ico
- dist/config/ (emulator_templates.txt; sin settings.txt para preservar configuración de usuario)
- dist/emulators/
- dist/lists/
- dist/icons/
- dist/Layouts/
- dist/splash/
- dist/lang/
- dist/tools/ (ffmpeg, ffprobe, herramientas auxiliares)
"""
import os
import sys
import shutil
import struct
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"


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

    # 2. Carpeta config/ sin settings.txt (para no sobrescribir configuración al actualizar)
    config_dir = dist_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    tmpl_src = ROOT_DIR / "config" / "emulator_templates.txt"
    if tmpl_src.exists():
        shutil.copy2(tmpl_src, config_dir / "emulator_templates.txt")
        print(" [OK] Plantillas: config/emulator_templates.txt copiado.")

    dest_settings = config_dir / "settings.txt"
    if dest_settings.exists():
        try:
            dest_settings.unlink()
            print(" [OK] Removido config/settings.txt de dist/ para proteger configuraciones existentes.")
        except OSError:
            pass

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

    # 5c. Copiar lang/
    lang_src = ROOT_DIR / "lang"
    lang_dest = dist_dir / "lang"
    if lang_src.exists():
        if lang_dest.exists():
            shutil.rmtree(lang_dest)
        shutil.copytree(lang_src, lang_dest)
        print(" [OK] Idiomas: carpeta lang/ copiada.")

    # 5d. Copiar tools/ (ffmpeg, ffprobe, etc.)
    tools_src = ROOT_DIR / "tools"
    tools_dest = dist_dir / "tools"
    if tools_src.exists():
        if tools_dest.exists():
            shutil.rmtree(tools_dest)
        shutil.copytree(
            tools_src,
            tools_dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        print(" [OK] Herramientas: carpeta tools/ copiada (incluyendo ffmpeg).")

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


def _resolve_current_git_commit() -> str:
    """Obtiene el hash corto del commit actual para incrustarlo en los ejecutables."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def _write_build_commit_file() -> Path | None:
    """Crea temporalmente playnexus/_build_commit.txt para empaquetarlo en el .exe."""
    commit_hash = _resolve_current_git_commit()
    if not commit_hash:
        return None
    commit_file = ROOT_DIR / "playnexus" / "_build_commit.txt"
    commit_file.write_text(commit_hash + "\n", encoding="utf-8")
    print(f" [OK] Commit de compilación incrustado: {commit_hash}")
    return commit_file


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

    commit_file = _write_build_commit_file()
    commit_data_arg = ["--add-data", f"{commit_file}{os.pathsep}playnexus"] if commit_file else []

    stage_dist_dir = ROOT_DIR / "build" / "_pyi_dist"
    if stage_dist_dir.exists():
        shutil.rmtree(stage_dist_dir, ignore_errors=True)
    stage_dist_dir.mkdir(parents=True, exist_ok=True)

    common_args = [
        str(pyinstaller_exe),
        "--noconfirm",
        "--clean",
        "--onedir",
        "--contents-directory", "_internal",
        "--distpath", str(stage_dist_dir),
        "--noupx",
        "--windowed",
        "--collect-all", "playnexus",
        "--collect-submodules", "PySide6.QtMultimedia",
        "--collect-submodules", "PySide6.QtMultimediaWidgets",
        "--hidden-import", "PySide6.QtMultimedia",
        "--hidden-import", "PySide6.QtMultimediaWidgets",
        "--hidden-import", "shutil",
        "--hidden-import", "ctypes",
        "--hidden-import", "json",
        *commit_data_arg,
        *icon_arg,
    ]

    try:
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

        print("\n==================================================")
        print("2.5/3: Ensamblando ejecutables con runtime compartido en dist/_internal/...")
        print("==================================================")
        DIST_DIR.mkdir(parents=True, exist_ok=True)
        shared_internal = DIST_DIR / "_internal"
        if shared_internal.exists():
            shutil.rmtree(shared_internal)

        for app_name in ("PlayNexus_Config", "PlayNexus_Launcher"):
            app_stage = stage_dist_dir / app_name
            exe_src = app_stage / f"{app_name}.exe"
            internal_src = app_stage / "_internal"
            if exe_src.exists():
                shutil.copy2(exe_src, DIST_DIR / f"{app_name}.exe")
            if internal_src.exists():
                shutil.copytree(internal_src, shared_internal, dirs_exist_ok=True)
    finally:
        if commit_file and commit_file.exists():
            try:
                commit_file.unlink()
            except OSError:
                pass
        if stage_dist_dir.exists():
            shutil.rmtree(stage_dist_dir, ignore_errors=True)

    # Configurar y poblar la carpeta dist/ limpia
    setup_clean_environment(DIST_DIR)

    print("\n¡Distribución limpia generada con éxito en la carpeta dist/!")


if __name__ == "__main__":
    build()
