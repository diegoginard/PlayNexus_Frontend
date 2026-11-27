<a id="english"></a>

# PlayNexus v1.5.5 — Emulation Frontend for Windows

> **Language:** **English** | [Español](#spanish)

![PlayNexus Logo](PlayNexus_Logo.png)

**PlayNexus** is a fast, modular, and customizable emulation frontend for organizing, browsing, and launching retro and modern video games on Windows 10 and Windows 11. Built with **Python 3.11+**, **PySide6 (Qt)**, an **OpenGL hardware-accelerated GPU rendering pipeline**, and 100% portable **plain-text (`.txt`)** storage.

Its design takes inspiration from classic concepts in **Attract-Mode** and **RocketLauncher**—especially library organization, emulator management, per-system layouts, bezels, and launch automation—implemented through a clean, portable, native Python/Qt architecture.

---

## 🚀 Quick Start Guide

PlayNexus can run directly via its **standalone executables** (no Python installation required), via helper `.bat` scripts, or from source in a Python virtual environment.

### 1. Standalone Executables in `dist/` (100% Clean & Portable Distribution)
Running `python build_executables.py` compiles a fast shared `--onedir` build (embedding the active Git commit hash into `_build_commit.txt` and isolating child emulator environments from PyInstaller DLL paths) inside **`dist/`**:
- **`dist/PlayNexus_Config.exe`**: Launches the **Library Configurator & Management UI** without requiring Python or external dependencies.
- **`dist/PlayNexus_Launcher.exe`**: Launches the fullscreen **Frontend / Arcade Player Mode** directly.
- **Portable directory structure assembled inside `dist/`**:
  - `dist/_internal/`: Shared Python, PySide6, OpenGL, and QtMultimedia runtime used by both executables.
  - `dist/config/`: Includes `emulator_templates.txt` **without overwriting `settings.txt`**, preserving user settings across updates (on a fresh install, `settings.txt` is automatically generated on first launch defaulting to `app_language = en`).
  - `dist/lang/`: Plain-text UI language packs (`en.txt`, `es.txt`, plus any custom `<code>.txt` translations you add).
  - `dist/tools/`: Bundled `ffmpeg/` (`ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`) ready out of the box for the Pro Toolkit video normalizer.
  - `dist/emulators/`: Clean folder ready for user-configured emulator profiles.
  - `dist/lists/`: Clean folder ready for your game lists and menus.
  - `dist/icons/`: System and arcade icons.
  - `dist/Layouts/`: Ready-to-use system themes and visual layouts (CRT TVs, consoles, wheels, showcase, and shared `gtc-common` assets/fonts).
  - `dist/splash/`: Folder for the intro splash video and fallback loading screen.
  - `dist/PlayNexus_Logo.png`, `dist/PlayNexus_icon.png`, and `dist/app_icon.ico`: Application branding and multi-resolution icon.
  *(Note: `dist/`, `emulators/`, `lists/`, `backups/`, and `config/.key` are excluded from Git via `.gitignore` to keep the repository clean).*

### 2. Batch Launchers & Utilities (`.bat`)
- **`PlayNexus.bat`**: Interactive selector menu to launch Frontend Mode, Configurator Mode, or build executables.
- **`PlayNexus_Launcher.bat`**: Starts fullscreen Frontend Mode using `.venv`.
- **`PlayNexus_Config.bat`**: Starts Configurator Mode with automatic Python/dependency setup.
- **`build_executables.bat` / `Compilar_EXE.bat`**: Automates PyInstaller builds into `dist/`.

### 3. Manual Developer Setup (PowerShell or CMD)
1. **Create and activate the virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Launch the Configurator:**
   ```powershell
   python -m playnexus
   ```
3. **Launch Frontend / Player Mode:**
   ```powershell
   python -m playnexus --player
   ```

---

## 📋 Key Features

### 1. Multi-Language Interface via `lang/*.txt` (`i18n.py`)
- **English by default (`en`)** on first launch, with complete **English (`lang/en.txt`)** and **Spanish (`lang/es.txt`)** packs included.
- **Open & extensible plain-text format:** Add any language simply by copying `lang/en.txt` to `lang/<code>.txt` (UTF-8), editing `_lang_code`, `_lang_name`, and the translated values (`key = text`).
- **Dynamic language selector:** Switch languages under *⚙ System Settings → 🌐 Language / Idioma* with a **Reload languages** button and an optional one-click restart to apply the language across every window, dialog, overlay, and service.
- **Resilient fallback chain:** Missing keys or broken placeholders in community packs automatically fall back to `lang/en.txt` and built-in defaults without crashing the UI.

### 2. Hardware-Accelerated OpenGL Rendering (`gpu_renderer.py`)
- **60+ FPS GPU scene compositor (`GpuSceneViewport` / `GpuQuadPipeline`):** Batches quads, homographies (`corner_pins`), premultiplied textures (`Target2D` + trilinear mipmaps without alpha halos), and retro shader FBO passes on the GPU, with automatic `QPainter` software fallback (`frontend_render_backend`).
- **Zero-copy GPU video playback (`GpuVideoSurface` / `GpuVideoPlayerWidget`):** Uploads `NV12`, `YUV420P`, and `RGBA/BGRA` `QVideoFrame` planes directly to OpenGL shaders without CPU `frame.toImage()` or `fbo.toImage()` readbacks.
- **Safe context & VRAM lifecycle:** Synchronized cleanup across widget hides, tab switches, Layout Studio Sandbox mode changes (`Windowed` / `Borderless` / `Fullscreen`), and parent teardowns.

### 3. PC & Windows Games Support (Attract-Mode Style)
- Integrates native Windows games, shortcuts (`.lnk`), batch scripts (`.bat`, `.cmd`), and executables (`.exe`).
- **System command launcher & one-click template:** Register `cmd` / `cmd.exe` cleanly via `PATH` or load **«Load Windows Games template (cmd.exe)»** (`/c "[romfilename]"`).
- **Smart working directory (`cwd`):** Automatically sets the working directory to the game's folder when launching `.bat`, `.cmd`, or `.lnk` targets.
- **Attract-Mode & LaunchBox compatible argument tokens:**
  - `[romfilename]`, `[rom_filename]`, `[rom]`, `%rom%`, `%1`: Normalized full path (`C:\...`).
  - `[rompath]`, `[rom_path]`, `[romdir]`: Game directory.
  - `[romname]`, `[rom_name]`, `[name]`, `[cleanromname]`: Filename without extension.
  - Python-style placeholders: `{rom}`, `{rom_dir}`, `{rom_name}`.

### 4. Asynchronous Scanning with Live Progress & Debug Console
- Dedicated background `QThread` scanner keeps Windows responsive on massive catalogs (e.g., full MAME/Arcade sets).
- Live progress bar, imported/skipped counters, and real-time processing log.

### 5. Lists, Smart Filtered Lists & System Menus
- **Games Lists (`games`):** Tied to one or more ROM folders with automatic scanning and extension normalization.
- **Filtered Lists (`filtered`):** Dynamic rule-based subsets linked to a source list (genres, years, manufacturers, non-clones, favorites, etc.).
- **System Menus (`menu`):** Hierarchical navigation menus grouping multiple system lists, with custom icons (`icons/` included) and dedicated artwork paths (`boxart`, `wheel`, `video`, `flyer`, `cartart`, `cabinet`, `marquee`, `bezel`, `manual`).

### 6. Advanced Rule Filtering Engine
- Available for both Filtered Lists and standard Games Lists (`sourcefile`, `cloneof`, `romof`, `year`, `manufacturer`, `status`, `title`, `name`, etc.) with `contains`, `equals`, `starts with`, `ends with`, `empty` operators, `AND`/`OR` matching, and live match-count preview.

### 7. Flexible Extensions & Multi-Folder ROM Configuration
- Built-in extension presets for PC Games, SNES, GBA, PS1, PS2, Mega Drive, N64, NDS, PSP, Arcade (`.zip;.7z;<DIR>`), or custom extensions.
- Semicolon-separated (`;`) multi-folder ROM paths, `scan_subfolders`, and `exclude_folder_if_zip` options.

### 8. Emulator Management, Templates & Launch Priority
- Centralized emulator profiles stored individually in `emulators/*.txt`, plus quick templates (`config/emulator_templates.txt`) editable in *System Settings*.
- **Direct test & launch controls:** Test or run an emulator executable directly from the Emulator configuration dialog, link external MAME/Arcade XML databases instantly without UI stalls, and launch child processes with clean environment variables in standalone builds.
- **Mandatory launch priority:**
  1. Per-game emulator override.
  2. List default emulator.
  3. Guided prompt if unconfigured.
- Smart RetroArch core detection and duplicate-instance launch guard.

### 9. Unified Layout Engine (`theme_base.py`), Tables & 19 System Themes
- **Declarative base architecture (`CommonThemeLayout` / `ConsoleThemeLayout`):** Centralizes shared `gtc-common` fonts (`Layouts/gtc-common/fonts/`) and wheel fallback art, 14-node GPU-compatible curved conveyor wheels, configurable `LAYER_ORDER` (CRT TV, console/cover/joystick, floating avatar, bouncing logo, cartridge drop or spinning disc, boxart), pointer animations, and a unified bottom metadata bar (including **Main Menu**).
- **19 autonomous console & arcade themes (`Layouts/<System>/theme_layout.py`):** **Main Menu**, **At-The-Arcade Flex**, **Atari Jaguar**, **Atari Jaguar CD**, **NEC PC-FX**, **NEC TurboGrafx-16**, **NEC TurboGrafx-CD**, **Nintendo 64**, **Nintendo Gameboy Advance**, **Nintendo Gamecube**, **Nintendo Virtual Boy**, **Sega 32X**, **Sega CD**, **Sega Dreamcast**, **Sega Genesis**, **Sega Saturn**, **Sony Playstation**, **Sony PlayStation Portable**, and **Super Nintendo Entertainment System**.
- **Generic views:** **Wheel**, **Grid** (zoomable), **Showcase**, **Banners**, and **Details** (`table_utils.py` sortable technical view), plus automatic minimization/restoration around emulator launches.
- **Standardized vertical wheel navigation & commit-on-release:** Smooth 60 FPS wheel scrolling with next items ordered above center and previous items below center, continuous video playback during scrolling, and debounced/on-release artwork commits (~180 ms).

### 10. Display, Resolutions & Multi-Monitor Settings
- **Window modes:** Exclusive Fullscreen, Borderless Window, Standard Windowed.
- **Resolutions:** Native monitor resolution, presets (4K, 2K, 1080p, 720p, 16:10, 4:3), or exact pixel dimensions, plus target monitor selection and HiDPI UI scaling (`100%`–`200%`).

### 11. Gamepad / Joystick Controls & Global Exit Separation
- Windows XInput / DirectInput gamepad support (D-Pad, analog sticks, buttons) working seamlessly alongside keyboard bindings.
- **Cleanly separated navigation & exit bindings:** Exit running emulators with `F4` (or configured Close Emulator key / `Back+Start` gamepad combo) and navigate back through menus with `Backspace` (`nav_back`) without accidentally triggering the frontend exit prompt, which responds directly to `Escape` / gamepad confirmation.

### 12. Foreground Bezel Overlays (Transparent Win32 Bezel HUD)
- Per-list `bezel_hud_path` with strict resolution (`<rom_name>.png` → `default_v.png` for vertical / `default.png` for horizontal), configurable `bezel_delay` and `bezel_fade`, per-game override (`Inherit` / `Force Enable` / `Disable`), click-through overlay (`WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE`), and real-time toggle hotkey (`F11` / `L-Thumb`).

### 13. Intro Splash Video, Loading/Exit Screens & Exit Confirmation
- Optional fullscreen intro splash video (`PlayNexus_Launcher.exe`) with instant skip via keyboard/gamepad/mouse.
- Per-emulator timed fullscreen `TOPMOST` Loading/Exit HUD (`nombrerom_i/o.<ext>` → `default/default_i/o.<ext>` → `splash/loading.jpg`).
- Arcade modal exit confirmation dialog navigable and confirmable directly via keyboard (`Escape` / `Enter`) and gamepad.

### 14. Arcade Screensaver (`screensaver.py`)
- Smart inactivity timer with 4 weighted random modes (**Basic Movie**, **2×2 Movie Collage**, **4×4 Image Collage**, **RGB Movie**), deep OLED/CRT blank screen timer, and instant **Select** jump straight to the showcased game.

### 15. Layout Studio 2.0 (Real-Time WYSIWYG Editor & Sandbox)
- Executes and edits real `ThemeLayout` classes directly (`1920x1080` canonical canvas), with 4-point perspective pinning (`corner_pins`), Z-order/opacity/lock controls, 60 FPS animation timeline (`0.00s`–`5.00s`), auto-backups (`Layouts/<Theme>/backups/`), and live multi-resolution **Sandbox** preview (`Windowed`, `Borderless`, `Fullscreen`).

### 16. Rom Manager, Strict `MEDIA_REQUIREMENTS` Audit & Online Scraper
- **Strict declarative media audit:** Audits only the exact media slots declared by each layout's `MEDIA_REQUIREMENTS` (zero predictive folder guessing), automatically resyncing lists and game counts immediately after scanning or editing in the Library tab.
- **Per-ROM management:** Quick row actions (open folder, replace ROM, safe literal delete of ROM + exclusive media), dual image/PDF/seekable video preview, drag-and-drop media slotting, and CSV export.
- **Multi-source batch & single-ROM scraper (`1`–`20` parallel threads):** Supports **ArcadeItalia ADB**, **Libretro Thumbnails**, and **ScreenScraper API v2** (with `enc1:` encrypted local credentials, `1`–`20` parallel worker threads, one-click `maxthreads` account detection via `ssuserInfos.php`, and dynamic concurrent semaphore throttling). Matches inner uncompressed ROM CRC32/size inside console `.zip` archives, falls back to clean `romnom`, scores against all localized regional titles (`noms`) and split fan-translated subtitles (`[Ting]`/`[Tesp]`), honors `prefer_hd_video`, and auto-prioritizes the ROM's own region tag (`(J)`, `(U)`, `(E)`, `(S)`).
- **Exclusive multi-region & extra-slot selector:** In **Single-ROM Online Search**, preserves every regional and style variant returned by the provider (`US · 3D`, `EU · 3D`, `JP · 2D`, `SP · 3D`, `Wheel HD / Carbon / Steel`, etc.) with an exclusive **1-region-per-media-type** dropdown synced two-way with the live preview, plus dynamic optional extra media (`bezel`, `marquee`, `flyer`, `cabinet`, `manual`) with editable destination subfolder names and auto-mkdir.

### 17. Pro Toolkit, RetroAchievements, In-App PDF Manual Viewer & Quick Menu
- **Pro Toolkit:** Batch Auto-Trim for transparent/black borders, cancelable `ffmpeg` MP4 normalizer (`-movflags +faststart`, powered out of the box by bundled `tools/ffmpeg/`), and non-destructive 1G1R duplicate auditor.
- **RetroAchievements Web API v1:** `rcheevos`-compatible MD5 hashing, local cache, achievements viewer, plus automatic play-count / play-time / last-played telemetry.
- **In-App PDF Viewer:** Memory-buffered `QPdfDocument` reader navigable with keyboard/gamepad.
- **Player Quick Menu & On-Screen Search:** Live filtering, sorting, shader/particle switching, and virtual keyboard inside `PlayerWindow`.
- **Retro GPU Shaders, Ambient Particles & Audio Guardian:** `CRT Aperture`, `CRT Bloom`, `LCD Handheld`, `VHS`, 4 particle presets, and automatic WASAPI audio-device switch recovery (`AudioDeviceGuardian`).

---

## 🗂 Project Structure

```text
PlayNexus_Frontend/
├── README.md                 # Bilingual documentation (English + Español)
├── requirements.txt          # Python dependencies (PySide6, etc.)
├── PlayNexus.bat             # Interactive selector menu (.bat)
├── PlayNexus_Config.bat      # Direct Configurator launcher (.bat)
├── PlayNexus_Launcher.bat    # Direct Frontend / Player launcher (.bat)
├── build_executables.bat     # PyInstaller build script (.bat)
├── Compilar_EXE.bat          # Quick compile shortcut (.bat)
├── build_executables.py      # Builds shared --onedir .exe bundle into dist/
├── entry_config.py           # Entry point for PlayNexus_Config.exe
├── entry_launcher.py         # Entry point for PlayNexus_Launcher.exe
├── PlayNexus_Logo.png        # Project logo
├── PlayNexus_icon.png        # Master high-resolution icon
├── app_icon.ico              # Multi-resolution Windows icon
├── lang/                     # Plain-text UI language files (extensible by users)
│   ├── en.txt                # English language pack (default)
│   └── es.txt                # Spanish language pack
├── tools/                    # Bundled external utilities (ffmpeg, ffprobe, ffplay)
├── splash/                   # Splash screen video & fallback loading image
├── dist/                     # Clean standalone portable build (gitignored)
│   ├── PlayNexus_Config.exe
│   ├── PlayNexus_Launcher.exe
│   ├── _internal/            # Shared PyInstaller runtime
│   ├── PlayNexus_Logo.png
│   ├── PlayNexus_icon.png
│   ├── app_icon.ico
│   ├── config/               # emulator_templates.txt (preserves user settings.txt)
│   ├── lang/                 # Bundled lang/*.txt files (users can add more here)
│   ├── tools/                # Bundled ffmpeg tools
│   ├── emulators/
│   ├── lists/
│   ├── icons/
│   ├── Layouts/
│   └── splash/
├── config/                   # Local configuration (settings.txt, emulator_templates.txt)
├── emulators/                # User-created emulator .txt files (gitignored)
├── lists/                    # User game lists & menus .txt files (gitignored)
├── icons/                    # System & arcade icons (.png)
├── Layouts/                  # 19 dedicated console & arcade themes + gtc-common
└── playnexus/
    ├── __init__.py           # QtMultimedia FFmpeg setup & early i18n initialization
    ├── __version__.py        # Centralized app version (v1.5.5) & embedded build commit
    ├── __main__.py           # CLI router (--player or Configurator)
    ├── db.py                 # Portable .txt storage engine & game telemetry
    ├── i18n.py               # Plain-text lang/*.txt loader, fallback & restart helper
    ├── services/
    │   ├── audio_guard.py    # WASAPI / QtMultimedia audio device hot-swap recovery
    │   ├── controls.py       # Keyboard & gamepad action bindings
    │   ├── emulator_manager.py # Process watcher, bezel delay/fade, global kill switch
    │   ├── emulator_templates.py # Quick emulator templates loader/editor
    │   ├── gamepad.py        # Controller polling & event manager
    │   ├── launcher.py       # Emulator resolution, token expansion & launch logic
    │   ├── library.py        # Extension normalization, MAME XML, rules & scanning
    │   ├── media.py          # Media & manual PDF resolver
    │   ├── retroachievements.py # RetroAchievements API v1 client & MD5 hasher
    │   ├── rom_manager.py    # MEDIA_REQUIREMENTS audit, ROM replace & safe delete
    │   ├── rom_toolkit.py    # Auto-Trim, Video Normalizer (ffmpeg) & 1G1R auditor
    │   ├── themes.py         # Theme discovery & generic media specs
    │   └── scraper/          # Multi-source online scraper package (ADB, Libretro, SS v2)
    └── ui/
        ├── bezel_overlay.py  # Transparent click-through Bezel HUD window
        ├── cover_utils.py    # Dynamic cover generator & async art loader
        ├── dialogs.py        # Lists, Emulators, Templates, Scan, Filters & Video dialogs
        ├── exit_confirm_dialog.py # Arcade exit confirmation modal
        ├── frontend_quick_menu.py # In-player Quick Menu & virtual keyboard
        ├── frontend_tab.py   # Frontend video, shader, Screensaver & Splash settings
        ├── gpu_renderer.py   # OpenGL quad/homography pipeline, VRAM cache & video surface
        ├── loading_overlay.py# Topmost Loading/Exit HUD overlay
        ├── main_window.py    # Main Configurator window & library management
        ├── manual_viewer.py  # In-app QPdfDocument PDF manual reader
        ├── particles.py      # Ambient particle presets & overlay renderer
        ├── player_window.py  # Fullscreen Arcade Player / Frontend window
        ├── ra_dialogs.py     # RetroAchievements UI & batch sync dialogs
        ├── rom_manager_tab.py# Rom Manager tab (audit, previewer, actions & drag-drop)
        ├── scraper_dialogs.py# Online Scraper configuration, batch & single-ROM dialogs
        ├── screensaver.py    # 4-mode dynamic Arcade Screensaver
        ├── settings_tab.py   # Controls, Emulator Behavior, Video, Templates & Language UI
        ├── shaders.py        # Retro GLSL FBO shaders with CPU QPainter fallback
        ├── splash_screen.py  # Fullscreen splash intro player
        ├── table_utils.py    # Shared table sorting & resizing helpers
        ├── toolkit_dialogs.py# Pro Toolkit dialogs (Auto-Trim, Normalizer, 1G1R)
        ├── layout_studio/    # Layout Studio 2.0 WYSIWYG editor, timeline & Sandbox
        └── layouts/          # CommonThemeLayout/ConsoleThemeLayout & generic views
```

---

## 💾 Plain-Text Data Persistence (100% Portable)

PlayNexus stores all configuration, translations, and library data in human-readable plain-text files inside the application folder—never touching the Windows Registry or `AppData`:

- **`lang/<code>.txt`**: Plain-text localization files (`_lang_code`, `_lang_name`, `key = value`) automatically discovered at startup and from Settings.
- **`config/settings.txt`**: General settings (`app_language`, controls, video, shaders/particles, encrypted `enc1:` scraper/RA credentials). Never overwritten during `dist/` updates.
- **`config/.key`**: Local symmetric key used to decrypt `enc1:` credentials (excluded from Git).
- **`config/emulator_templates.txt`**: Quick emulator templates catalog.
- **`emulators/<EmulatorName>.txt`**: Individual emulator parameters (local user files, ignored in Git).
- **`lists/<ListName>.txt`**: Per-list settings (`[List]`) and game catalog (`[Games]`) with telemetry and overrides (local user files, ignored in Git).

---
---

<a id="spanish"></a>

# 🌐 Versión en Español

> **Idioma:** [English](#english) | **Español**

# PlayNexus v1.5.5 — Frontend de Emulación para Windows

![PlayNexus Logo](PlayNexus_Logo.png)

**PlayNexus** es un frontend modular, rápido y elegante para organizar, visualizar y ejecutar videojuegos retro y modernos mediante emuladores y lanzadores en Windows 10 y Windows 11. Desarrollado con **Python 3.11+**, **PySide6 (Qt)**, motor de **renderizado acelerado por GPU (OpenGL)**, sistema **multi-idioma basado en archivos `.txt` (`lang/`)** y almacenamiento 100 % portable en **texto plano (`.txt`)**.

Su desarrollo toma como referencia funcionalidades y conceptos de **Attract-Mode** y **RocketLauncher**, especialmente en la organización de bibliotecas de videojuegos, gestión de emuladores, configuración de sistemas y automatización del lanzamiento de juegos, incorporando una arquitectura propia, modular y orientada a la portabilidad.

---

## 🚀 Guía de inicio rápido

PlayNexus puede ejecutarse directamente mediante sus **ejecutables independientes** (sin necesidad de tener Python instalado), mediante scripts `.bat` automatizados o desde la consola de comandos.

### 1. Ejecutables independientes en carpeta `dist/` (Distribución 100 % limpia y portable)
Al ejecutar `python build_executables.py`, se compila una distribución rápida en modo `--onedir` compartido (incrustando el commit actual de Git en `_build_commit.txt` y aislando las variables de entorno al lanzar emuladores externos) dentro de **`dist/`**, lista para usarse de forma autónoma o actualizar una instalación previa:
- **`dist/PlayNexus_Config.exe`**: Abre directamente el **Configurador de Biblioteca** sin requerir Python ni dependencias externas.
- **`dist/PlayNexus_Launcher.exe`**: Inicia directamente el **Modo Frontend / Reproductor** en pantalla completa.
- **Estructura autónoma incluida en `dist/`**:
  - `dist/_internal/`: Runtime compartido de Python, PySide6, OpenGL y QtMultimedia utilizado por ambos ejecutables.
  - `dist/config/`: Incluye `emulator_templates.txt` **sin sobrescribir `settings.txt`**, protegiendo la configuración del usuario al actualizar (en una instalación nueva, `settings.txt` se genera automáticamente al primer inicio con `app_language = en`).
  - `dist/lang/`: Archivos de idioma en texto plano (`en.txt`, `es.txt` y cualquier `<codigo>.txt` adicional que agregue el usuario).
  - `dist/tools/`: Incluye `ffmpeg/` (`ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`) listo de fábrica para el normalizador de video del Pro Toolkit.
  - `dist/emulators/`: Carpeta limpia preparada para dar de alta emuladores.
  - `dist/lists/`: Carpeta limpia preparada para tus listas de juegos.
  - `dist/icons/`: Logotipos e iconos de consolas y arcades.
  - `dist/Layouts/`: Temas y diseños visuales listos para usar (CRT TV, consolas, wheel, showcase y recursos/fuentes compartidas en `gtc-common`).
  - `dist/splash/`: Carpeta preparada para el video de presentación (Splash Screen) e imagen de carga.
  - `dist/PlayNexus_Logo.png`, `dist/PlayNexus_icon.png` y `dist/app_icon.ico`: Logotipo e iconos de la aplicación.
  *(Nota: las carpetas `dist/`, `emulators/`, `lists/`, `backups/` y `config/.key` están excluidas de Git mediante `.gitignore`).*

### 2. Lanzadores y utilidades por scripts (`.bat`)
- **`PlayNexus.bat`**: Menú selector interactivo que permite elegir entre iniciar el Frontend, el Configurador o compilar los ejecutables.
- **`PlayNexus_Launcher.bat`**: Inicia el Modo Frontend en pantalla completa utilizando el entorno virtual `.venv`.
- **`PlayNexus_Config.bat`**: Inicia el Modo Configurador con detección automática de Python y dependencias.
- **`build_executables.bat` / `Compilar_EXE.bat`**: Automatiza la compilación con PyInstaller y genera la distribución limpia y portable en `dist/`.

### 3. Instalación manual para desarrollo (PowerShell o CMD)
1. **Crear y activar el entorno virtual:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Ejecutar el Configurador:**
   ```powershell
   python -m playnexus
   ```
3. **Ejecutar el Modo Frontend / Jugador:**
   ```powershell
   python -m playnexus --player
   ```

---

## 📋 Características principales

### 1. Soporte Multi-Idioma mediante `lang/*.txt` (`i18n.py`)
- **Inglés (`en`) predeterminado al iniciar por primera vez**, incluyendo traducciones completas en **[lang/en.txt](lang/en.txt)** y **[lang/es.txt](lang/es.txt)**.
- **Extensible por texto plano:** Podés agregar cualquier idioma copiando `lang/en.txt` como `lang/<codigo>.txt` (UTF-8), ajustando `_lang_code`, `_lang_name` y traduciendo las líneas `clave = texto`.
- **Selector dinámico en Configuración:** Desde *⚙ Configuración del Sistema → 🌐 Idioma / Language*, PlayNexus detecta todos los `.txt` de `lang/`, permite recargar la lista al instante y ofrece reiniciar la ventana automáticamente al guardar para aplicar el nuevo idioma en toda la aplicación.
- **Cadena de respaldo segura:** Si a un archivo comunitario le faltan claves o tiene placeholders inválidos, respalda automáticamente en `lang/en.txt` y textos por defecto sin errores.

### 2. Motor de Renderizado GPU OpenGL (`gpu_renderer.py`)
- **Pipeline por lotes OpenGL (`GpuSceneViewport` / `GpuQuadPipeline`):** Composición GPU a >60 FPS, homografías proyectivas (`corner_pins`), texturas premultiplicadas sin halos con mipmaps trilineales, shaders en FBO y respaldo automático a `QPainter` (`frontend_render_backend`).
- **Video directo en GPU (`GpuVideoSurface` / `GpuVideoPlayerWidget`):** Subida directa de planos `NV12`, `YUV420P` y `RGBA/BGRA` desde `QVideoFrame` sin conversiones en CPU ni readbacks de FBO.
- **Ciclo de vida OpenGL limpio:** Liberación segura de texturas, FBOs, shaders y superficies de video al ocultar pestañas, cambiar de modo en el Sandbox o cerrar ventanas.

### 3. Soporte para Juegos de PC y Windows (Estilo Attract-Mode)
- Integración nativa de ejecutables (`.exe`), accesos directos (`.lnk`) y scripts (`.bat`, `.cmd`) con `cmd` / `cmd.exe`, plantilla rápida **«Cargar plantilla para Juegos de Windows (cmd.exe)»**, ajuste automático de `cwd` y comodines compatibles con Attract-Mode y LaunchBox (`[romfilename]`, `[rompath]`, `[romname]`, `{rom}`, `{rom_dir}`, `{rom_name}`).

### 4. Escaneo Asíncrono con Progreso en Vivo y Consola de Depuración
- Búsqueda e importación en hilo dedicado (`QThread`) sin bloquear la interfaz ante catálogos masivos MAME/Arcade, con contadores en vivo y registro detallado.

### 5. Listas, Sublistas Filtradas, Menús Jerárquicos y Filtros por Reglas
- Listas de juegos (`games`), listas filtradas dinámicas (`filtered`) y menús jerárquicos de sistemas (`menu`) con iconos (`icons/`) y carpetas independientes de medios (`boxart`, `wheel`, `video`, `flyer`, `cartart`, `cabinet`, `marquee`, `bezel`, `manual`).
- Motor de reglas por campos (`sourcefile`, `cloneof`, `year`, `manufacturer`, `title`, etc.) con operadores flexibles, combinación `AND`/`OR` y vista previa en vivo de coincidencias.

### 6. Extensiones Flexibles, Gestión de Emuladores y Prioridad de Lanzamiento
- Presets rápidos de extensiones, soporte multi-carpeta separado por `;`, detección de subcarpetas y exclusión de carpetas con `.zip` duplicado.
- Perfiles individuales en `emulators/*.txt`, catálogo editable de plantillas rápidas (`config/emulator_templates.txt`), botones directos para **ejecutar / probar el emulador** desde su diálogo de configuración, vinculación instantánea de archivos XML sin bloquear la interfaz, detección de núcleos RetroArch, guardia anti-doble instancia y prioridad obligatoria:
  1. Emulador asignado individualmente al juego.
  2. Emulador predeterminado de la lista.
  3. Guía asistida si no hay emulador configurado.

### 7. Motor Unificado de Layouts (`theme_base.py`), Tablas y 19 Temas por Sistema
- **Arquitectura declarativa compartida (`CommonThemeLayout` / `ConsoleThemeLayout`):** Centraliza fuentes (`Layouts/gtc-common/fonts/`) y `wheel.png` común en `gtc-common`, ruleta curva unificada de 14 nodos acelerada por GPU, orden de capas declarativo (`LAYER_ORDER`), animaciones sincronizadas y barra inferior unificada de metadatos (incluido **Main Menu**).
- **19 layouts temáticos autónomos (`Layouts/<Sistema>/theme_layout.py`):** **Main Menu**, **At-The-Arcade Flex**, **Atari Jaguar**, **Atari Jaguar CD**, **NEC PC-FX**, **NEC TurboGrafx-16**, **NEC TurboGrafx-CD**, **Nintendo 64**, **Nintendo Gameboy Advance**, **Nintendo Gamecube**, **Nintendo Virtual Boy**, **Sega 32X**, **Sega CD**, **Sega Dreamcast**, **Sega Genesis**, **Sega Saturn**, **Sony Playstation**, **Sony PlayStation Portable** y **Super Nintendo Entertainment System**.
- **Vistas genéricas:** **Wheel**, **Grid**, **Showcase**, **Banners** y **Detalles** (`table_utils.py`).
- **Navegación vertical estándar y *Commit on Release*:** Desplazamiento fluido de ruleta a 60 FPS sin pausar el video previo ni el de fondo durante el giro, con carga sincronizada al soltar la tecla o al vencer el debounce (~180 ms).

### 8. Video, Controles Separados, Bezels HUD, Splash, Loading Screen y Salvapantallas
- Modos Fullscreen, Borderless y Ventana, múltiples monitores, escala HiDPI (`100%`–`200%`) y control simultáneo por teclado y gamepad (XInput/DirectInput).
- **Separación limpia de atajos de cierre y navegación:** Cerrar emulador (`F4` o `Back+Start` en mando) y retroceder entre menús (`Backspace` / `nav_back`) operan de forma independiente sin disparar por error el diálogo de salida del frontend, el cual responde directamente a `Escape` / confirmación con mando.
- **Bezel HUD transparente Click-Through** (`WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE`) con resolución por ROM/orientación (`default_v.png`/`default.png`), retardo/fade configurable y atajo en vivo (`F11` / `L-Thumb`).
- **Splash Screen** con salto instantáneo, **Loading/Exit Screen** (`nombrerom_i/o` → `default_i/o` → `splash/loading.jpg`), confirmación modal arcade al salir y **Salvapantallas Arcade** con 4 modos (*Basic Movie*, *Movie Collage 2×2*, *Image Collage 4×4*, *RGB Movie*), apagado de pantalla y salto directo al juego mostrado al presionar Select.

### 9. Layout Studio 2.0, Rom Manager, Scraper, Pro Toolkit, RetroAchievements y Extras
- **Layout Studio 2.0:** Edición directa sobre `ThemeLayout` real en lienzo `1920x1080`, deformación proyectiva 4 puntos (`corner_pins`), línea de tiempo de animaciones a 60 FPS, copias de seguridad locales en `Layouts/<Tema>/backups/` y **Sandbox en vivo** multi-resolución.
- **Rom Manager y Scraper Multi-Fuente (`1`–`20` hilos y Multi-Región):** Auditoría estricta guiada exclusivamente por `MEDIA_REQUIREMENTS` (sin diccionarios predictivos), sincronización inmediata de listas al volver desde la pestaña Biblioteca, reemplazo y borrado literal seguro de ROM+artes exclusivas, previsualizador dual imagen/PDF/video con timeline, exportación CSV y scraping integrado con **ArcadeItalia (ADB)**, **Libretro Thumbnails** y **ScreenScraper API v2** (cifrado local `enc1:`, de **`1` a `20` hilos paralelos**, botón de autodetección de `maxthreads` reales de tu cuenta vía `ssuserInfos.php` y semáforo concurrente dinámico). Incluye lectura de CRC32/tamaño interno en `.zip` de consola, respaldo limpio por `romnom`, comparación contra todos los nombres regionales (`noms`) y subtítulos traducidos (`[Ting]`/`[Tesp]`), soporte de `prefer_hd_video` y priorización automática según la región de la ROM (`(J)`, `(U)`, `(E)`, `(S)`). En **Buscar online… (individual)** conserva todas las regiones y variantes (`US · 3D`, `EU · 3D`, `JP · 2D`, `SP · 3D`, `Wheel HD`, etc.) con selector exclusivo de **1 sola región por tipo de medio** sincronizado en vivo con la vista previa, más descarga opcional de medios adicionales (`bezel`, `marquee`, `flyer`, `cabinet`, `manual`) con subcarpeta editable y creación automática.
- **Pro Toolkit:** Auto-Trim de wheels/logos, normalizador MP4 vía `ffmpeg` (con `tools/ffmpeg/` incluido por defecto) y auditor no destructivo 1G1R/duplicados.
- **RetroAchievements API v1, Visor PDF in-app, Menú Rápido Arcade, Shaders/Partículas y Guardián WASAPI (`audio_guard.py`).**

---

## 🗂 Estructura del proyecto

```text
PlayNexus_Frontend/
├── README.md                 # Documentación bilingüe (English + Español)
├── requirements.txt          # Dependencias del proyecto (PySide6, etc.)
├── PlayNexus.bat             # Menú interactivo (.bat)
├── PlayNexus_Config.bat      # Lanzador del Configurador (.bat)
├── PlayNexus_Launcher.bat    # Lanzador del Frontend / Jugador (.bat)
├── build_executables.bat     # Script de compilación (.bat)
├── Compilar_EXE.bat          # Acceso rápido de compilación (.bat)
├── build_executables.py      # Genera ejecutables --onedir y entorno limpio en dist/
├── entry_config.py           # Punto de entrada para PlayNexus_Config.exe
├── entry_launcher.py         # Punto de entrada para PlayNexus_Launcher.exe
├── PlayNexus_Logo.png        # Logotipo del proyecto
├── PlayNexus_icon.png        # Icono maestro de alta resolución
├── app_icon.ico              # Icono multi-resolución de Windows
├── lang/                     # Archivos de idioma en texto plano (.txt)
│   ├── en.txt                # Paquete en inglés (predeterminado)
│   └── es.txt                # Paquete en español
├── tools/                    # Herramientas externas incluidas (ffmpeg, ffprobe, ffplay)
├── splash/                   # Video de bienvenida e imagen loading por defecto
├── dist/                     # Distribución portable compilada (.exe + _internal + tools + lang)
├── config/                   # Configuración local (settings.txt, emulator_templates.txt)
├── emulators/                # Perfiles locales de emuladores (.txt, ignorados en Git)
├── lists/                    # Listas locales de juegos y menús (.txt, ignorados en Git)
├── icons/                    # Iconos de sistemas y arcades (.png)
├── Layouts/                  # 19 temas dedicados por consola/arcade + gtc-common
└── playnexus/
    ├── __init__.py           # Inicialización de QtMultimedia FFmpeg e i18n temprano
    ├── __version__.py        # Versión centralizada (v1.5.5) y commit incrustado
    ├── __main__.py           # Enrutador CLI (--player o Configurador)
    ├── db.py                 # Motor de almacenamiento en texto plano y telemetría
    ├── i18n.py               # Motor de carga multi-idioma desde lang/*.txt y reinicio
    ├── services/             # Controles, emuladores, gamepad, biblioteca, medios, RA, toolkit, scraper
    └── ui/                   # Configurador, Player, diálogos, shaders, GPU, Layout Studio y layouts
```

---

## 💾 Persistencia de datos en Texto Plano (100 % Portable)

PlayNexus almacena toda su configuración, idiomas y biblioteca en archivos de texto plano legibles dentro de la carpeta del programa, sin usar el Registro de Windows ni `AppData`:

- **`lang/<codigo>.txt`**: Archivos de traducción en texto plano (`_lang_code`, `_lang_name`, `clave = valor`) detectados automáticamente al iniciar y desde Configuración.
- **`config/settings.txt`**: Ajustes generales (`app_language`, controles, pantalla/video, shaders/partículas y credenciales cifradas `enc1:`). No se sobrescribe al actualizar `dist/`.
- **`config/.key`**: Llave simétrica local para descifrar credenciales `enc1:` (excluida de Git).
- **`config/emulator_templates.txt`**: Catálogo editable de plantillas rápidas de emuladores.
- **`emulators/<NombreEmulador>.txt`**: Parámetros locales de cada emulador (ignorados en Git).
- **`lists/<NombreLista>.txt`**: Configuración (`[List]`) y juegos (`[Games]`) de cada lista/menú con telemetría y overrides (ignorados en Git).
