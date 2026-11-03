# Guía de Creación de Layouts para PlayNexus

Este documento define el estándar oficial para crear un nuevo tema visual (`theme_layout.py`) en PlayNexus. Seguir esta guía garantiza compatibilidad con el sistema de descubrimiento automático, los controles, la gestión de medios y la navegación.

---

## Estructura de directorios

```
Layouts/
├── gtc-common/                  # Recursos compartidos entre todos los layouts
│   ├── art/                     # wheel_art.png, frame.png, wheel_vert.png ...
│   ├── fonts/                   # BebasNeue Bold.otf, ...
│   ├── sounds/                  # joystick.mp3, Mame_coin.mp3, hs_click.mp3 ...
│   ├── videos/                  # static.mp4, bkg_anim.mp4, ...
│   └── wheel/                   # wheel_shadow.png
│
└── Nombre Del Sistema/          # Carpeta del layout (nombre exacto del sistema)
    ├── theme_layout.py          # ← Archivo principal (OBLIGATORIO)
    ├── bkg.jpg                  # Imagen de fondo local
    ├── tv.png                   # Pantalla CRT
    ├── console.png              # Imagen de la consola
    ├── pointers/
    │   └── default.png          # Imagen del puntero
    └── ...                      # Demás assets propios del tema
```

---

## Estructura del archivo `theme_layout.py`

### 1. Encabezado e imports

```python
import playnexus
"""
=============================================================================
Layout Autónomo y Configuración: Nombre Del Sistema
=============================================================================
Descripción breve del layout.
"""
import os
import math
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QRect, QTimer
from PySide6.QtGui import QFont, QColor, QPainter, QPixmap, QFontDatabase
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QSoundEffect

from playnexus.ui.layouts.base import BaseLayout, WheelPreloadWorker
from playnexus.services.media import resolve_game_media
from playnexus.services.controls import (
    matches_action, ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_PAGE_UP,
    ACTION_PAGE_DOWN, ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD,
    ACTION_SELECT, ACTION_MUTE, ACTION_NAV_BACK
)

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"
```

> [!IMPORTANT]
> `LAYOUT_DIR` y `COMMON_DIR` deben definirse a nivel de módulo (fuera de la clase) para poder usarse en las constantes de clase.

---

### 2. Definición de la clase

La clase **debe** llamarse exactamente `ThemeLayout` y heredar de `BaseLayout`.

```python
class ThemeLayout(BaseLayout):
    LAYOUT_NAME        = "Nombre Del Sistema"
    LAYOUT_DESCRIPTION = "Descripción breve del layout"

    CANONICAL_W = 1920
    CANONICAL_H = 1080
```

---

### 3. Bloque `REQUERIMIENTOS DE MEDIOS`

Define qué carpetas de medios necesita el layout. El sistema las detecta automáticamente.

```python
    MEDIA_REQUIREMENTS = [
        {
            "key":        "video",
            "label":      "Video Snaps",
            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
            "required":   True,
        },
        {
            "key":        "wheel",
            "label":      "Logos Wheel",
            "extensions": [".png", ".webp"],
            "required":   True,
        },
        # Agregar según las necesidades del layout
    ]
```

**Claves válidas** para el campo `"key"` (usadas por `playnexus/services/media.py`):

| Clave      | Descripción                        |
|------------|------------------------------------|
| `video`    | Video snap / tema del juego        |
| `wheel`    | Logo de rueda (wheel art)          |
| `boxart`   | Carátula / Box art                 |
| `cartart`  | Arte de cartucho o disco           |
| `cabinet`  | Arte de mueble arcade              |
| `marquee`  | Marquesina del mueble              |
| `bezel`    | Marco / Bezel del monitor          |
| `flyer`    | Flyer / publicidad del juego       |

> [!CAUTION]
> **Nunca uses claves arbitrarias** como `"wheels"` o `"artwork"`. Solo se aceptan las claves de la tabla anterior.

---

### 4. Bloque `RECURSOS LOCALES PROPIOS DEL LAYOUT` ← **Premisa fundamental**

**Todas las rutas a recursos** — tanto los locales del layout como los provenientes de `gtc-common` — deben declararse como **constantes de clase** en este bloque. Esto permite cambiar cualquier recurso sin buscar dentro del código.

```python
    # -------------------------------------------------------------------------
    # RECURSOS LOCALES PROPIOS DEL LAYOUT
    # -------------------------------------------------------------------------
    BKG_IMAGE           = LAYOUT_DIR / "bkg.jpg"
    TV_IMAGE            = LAYOUT_DIR / "tv.png"
    CONSOLE_IMAGE       = LAYOUT_DIR / "console.png"
    CONSOLE_COVER_IMAGE = LAYOUT_DIR / "console_cover.png"  # o None si no existe
    JOYSTICK_IMAGE      = LAYOUT_DIR / "joystick.png"       # o None si no existe
    AVATAR_IMAGE        = LAYOUT_DIR / "avatar.png"
    LOGO_IMAGE          = LAYOUT_DIR / "logo.png"
    CARTART_IMAGE       = LAYOUT_DIR / "cartart.png"
    BOXART_IMAGE        = LAYOUT_DIR / "boxart.png"         # o None si no existe
    WHEEL_IMAGE         = LAYOUT_DIR / "wheel.png"
    POINTER_IMAGE       = LAYOUT_DIR / "pointers" / "default.png"
    FONT_FILES = [
        "Handel Gothic BT.ttf",   # relativo a LAYOUT_DIR
        "BebasNeue Bold.otf",
    ]

    # Recursos compartidos desde gtc-common
    WHEEL_SHADOW_IMAGE = COMMON_DIR / "wheel" / "wheel_shadow.png"
    COMMON_WHEEL_ART   = COMMON_DIR / "art" / "wheel_art.png"
    COMMON_FRAME       = COMMON_DIR / "art" / "frame.png"
    STATIC_VIDEO       = COMMON_DIR / "videos" / "static.mp4"
    SOUND_NAV          = COMMON_DIR / "sounds" / "joystick.mp3"
    SOUND_SELECT       = COMMON_DIR / "sounds" / "Mame_coin.mp3"
```

> [!TIP]
> Usa `None` como valor por defecto cuando un recurso local es opcional. En `__init__` comprueba con `if self.RESOURCE:` antes de cargar.

---

### 5. Carga de recursos en `__init__`

Dentro de `__init__`, carga los recursos usando **las constantes de clase** — nunca rutas hardcodeadas:

```python
    def __init__(self, theme_name: str = "Nombre Del Sistema", parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.layout_dir = LAYOUT_DIR

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        # --- Sonidos (desde constantes) ---
        self._sound_effect = QSoundEffect(self)
        self._sound_effect.setVolume(0.4)
        if self.SOUND_NAV.is_file():
            self._sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_NAV)))

        self._select_sound_effect = QSoundEffect(self)
        self._select_sound_effect.setVolume(0.5)
        if self.SOUND_SELECT.is_file():
            self._select_sound_effect.setSource(QUrl.fromLocalFile(str(self.SOUND_SELECT)))

        # --- Imágenes locales (desde constantes) ---
        self._pix_bkg     = self._load_pixmap(str(self.BKG_IMAGE))
        self._pix_tv      = self._load_pixmap(str(self.TV_IMAGE))
        self._pix_pointer = self._load_pixmap(str(self.POINTER_IMAGE))

        # --- Recursos compartidos desde gtc-common (desde constantes) ---
        self._pix_wheel_art    = self._load_pixmap(str(self.COMMON_WHEEL_ART))
        self._pix_frame        = self._load_pixmap(str(self.COMMON_FRAME))
        self._pix_wheel_shadow = self._load_pixmap(str(self.WHEEL_SHADOW_IMAGE)) \
                                  if self.WHEEL_SHADOW_IMAGE.is_file() else None
        self._static_video_path = str(self.STATIC_VIDEO) if self.STATIC_VIDEO.is_file() else None

        # --- Fuentes ---
        self._font_handel = "sans-serif"
        self._font_bebas  = "sans-serif"
        self._load_theme_fonts()
```

---

### 6. Señales que el layout debe emitir

Heredadas de `BaseLayout`. **No las redefinir**, solo emitirlas:

| Señal                 | Cuándo emitirla                                         |
|-----------------------|---------------------------------------------------------|
| `game_selected`       | Al cambiar el elemento resaltado en la ruleta           |
| `game_activated`      | Al confirmar/lanzar un elemento (Enter, doble clic)     |
| `nav_back_requested`  | Al presionar "atrás" / escape del menú                  |

```python
self.game_selected.emit(game_id)   # al navegar
self.game_activated.emit(game_id)  # al seleccionar
self.nav_back_requested.emit()     # al volver atrás
```

---

### 7. Métodos obligatorios

Todos los métodos siguientes deben implementarse:

| Método                            | Descripción                                                  |
|-----------------------------------|--------------------------------------------------------------|
| `set_games(games: list)`          | Recibe la lista de juegos/sistemas y reinicia el estado      |
| `select_game_by_id(game_id: int)` | Selecciona el elemento con el ID indicado                    |
| `get_selected_game_id() -> int`   | Retorna el ID del elemento actualmente seleccionado          |
| `_navigate_steps(delta: int)`     | Avanza/retrocede N pasos en la ruleta                        |
| `_update_current_selection()`     | Actualiza medios y emite `game_selected` para el ítem actual |
| `pause_media()`                   | Pausa video y audio (ej: al lanzar un emulador)              |
| `resume_media()`                  | Reanuda reproducción al volver al menú                       |
| `stop_media()`                    | Detiene completamente la reproducción multimedia             |
| `set_media_muted(muted: bool)`    | Activa/desactiva silencio global                             |

---

### 8. Manejadores de eventos obligatorios

```python
    def keyPressEvent(self, event):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        # ... lógica de navegación con matches_action(event, ACTION_*)

    def wheelEvent(self, event):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._navigate_steps(-1)
        elif delta < 0:
            self._navigate_steps(1)
        event.accept()

    def mousePressEvent(self, event):
        ...
        self.setFocus()
        ...

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        event.accept()
```

> [!WARNING]
> **Siempre** chequear `EMULATOR_MANAGER.is_launching_or_running()` al inicio de `keyPressEvent` y `wheelEvent`. Omitirlo causa que la ruleta no responda correctamente después de cerrar un emulador.

---

### 9. Descubrimiento automático

El sistema descubre los layouts automáticamente buscando:
```
Layouts/<NombreTema>/theme_layout.py  →  clase ThemeLayout
```

No se necesita registro manual. El nombre de la carpeta es el identificador del tema en la base de datos.

---

### 10. Checklist rápido para un nuevo layout

- [ ] Carpeta en `Layouts/<NombreTema>/`
- [ ] Archivo `theme_layout.py` con clase `ThemeLayout(BaseLayout)`
- [ ] `LAYOUT_NAME`, `LAYOUT_DESCRIPTION`, `CANONICAL_W`, `CANONICAL_H`
- [ ] `MEDIA_REQUIREMENTS` con claves válidas (`video`, `wheel`, `boxart`, etc.)
- [ ] Bloque **RECURSOS LOCALES**: todos los assets locales como constantes de clase
- [ ] Bloque **Recursos desde gtc-common**: `WHEEL_SHADOW_IMAGE`, `SOUND_NAV`, `SOUND_SELECT`, etc. como constantes de clase
- [ ] `__init__` usa `self.CONSTANT_NAME` — nunca rutas hardcodeadas
- [ ] Métodos obligatorios implementados (`set_games`, `select_game_by_id`, `get_selected_game_id`, `pause_media`, `resume_media`, `stop_media`, `set_media_muted`)
- [ ] Eventos `keyPressEvent`, `wheelEvent`, `mousePressEvent`, `mouseReleaseEvent` con check de `EMULATOR_MANAGER`
- [ ] Señales `game_selected`, `game_activated`, `nav_back_requested` emitidas correctamente
- [ ] `py_compile` sin errores: `.\.venv\Scripts\python.exe -m py_compile Layouts/<NombreTema>/theme_layout.py`

---

## 11. Catálogo de Layouts Oficiales Activos

| Layout | Tipo de Soporte | Medios Requeridos | Elementos Destacados |
|--------|-----------------|-------------------|----------------------|
| **NEC TurboGrafx-16** | Cartucho (HuCard) | `video`, `wheel`, `cartart` | TV CRT, animación de inserción vertical en consola, tapa de ranura, nave espacial animada |
| **NEC TurboGrafx-CD** | Disco CD-ROM | `video`, `wheel`, `cartart` | TV CRT, giro continuo de disco CD a 60 FPS, carátula dinámica, nave espacial animada |
| **NEC PC-FX** | Disco CD-ROM | `video`, `wheel`, `cartart` | TV CRT, giro continuo de disco CD a 60 FPS, carátula dinámica, avatar temático animado |
| **Atari Jaguar** | Cartucho | `video`, `wheel`, `cartart` | TV CRT, inserción tridimensional en ranura de consola, mecha robot animado |
| **Atari Jaguar CD** | Disco CD-ROM | `video`, `wheel`, `cartart` | TV CRT, rotación de CD de 60 FPS, avatar robot animado |
| **Sega Genesis** | Cartucho | `video`, `wheel`, `cartart` | TV CRT, inserción en ranura, avatar Sonic animado |
| **Sega CD** | Disco CD-ROM | `video`, `wheel`, `cartart` | TV CRT, rotación de CD a 60 FPS, avatar Sonic animado |
| **Sega 32X** | Cartucho | `video`, `wheel`, `cartart` | TV CRT, inserción en add-on 32X, avatar Knuckles animado |
| **Sega Saturn** | Disco CD-ROM | `video`, `wheel`, `cartart` | TV CRT, rotación continua de CD, avatar animado |
| **Sony Playstation** | Disco CD-ROM | `video`, `wheel`, `cartart` | TV CRT, rotación de disco negro PlayStation, avatar Crash Bandicoot |
| **Nintendo 64** | Cartucho | `video`, `wheel`, `cartart` | TV CRT, inserción frontal, avatar Mario 64 |
| **Super Nintendo** | Cartucho | `video`, `wheel`, `cartart` | TV CRT, inserción vertical en SNES, avatar Mario animado |

