# PlayNexus v1.1.14 — Frontend de Emulación para Windows

![PlayNexus Logo](PlayNexus_Logo.png)

**PlayNexus** es un frontend modular, rápido y elegante para organizar, visualizar y ejecutar videojuegos retro y modernos mediante emuladores y lanzadores en Windows 10 y Windows 11. Desarrollado con **Python 3.11+**, **PySide6** (Qt) y almacenamiento 100% portable en **texto plano (`.txt`)**.

Su desarrollo toma como referencia funcionalidades y conceptos de **Attract-Mode** y **RocketLauncher**, especialmente en la organización de bibliotecas de videojuegos, gestión de emuladores, configuración de sistemas y automatización del lanzamiento de juegos, incorporando una arquitectura propia, modular y orientada a la portabilidad.

---

## 🚀 Guía de inicio rápido

PlayNexus puede ejecutarse directamente mediante sus **ejecutables independientes** (sin necesidad de tener Python instalado), mediante scripts `.bat` automatizados o desde la consola de comandos.

### 1. Ejecutables independientes en carpeta `dist/` (Distribución 100% limpia y portable)
Al ejecutar `python build_executables.py`, se compilan y ensamblan todos los archivos necesarios dentro de la carpeta **`dist/`**, lista para usarse de forma autónoma en limpio (o comprimirse en `.zip` para llevar a cualquier equipo):
- **`dist/PlayNexus_Config.exe`**: Abre directamente el **Configurador de Biblioteca** sin requerir Python ni dependencias externas.
- **`dist/PlayNexus_Launcher.exe`**: Inicia directamente el **Modo Frontend / Reproductor** en pantalla completa.
- **Estructura autónoma incluida en `dist/`**:
  - `dist/config/`: `settings.txt` con ajustes limpios de fábrica y `emulator_templates.txt` con el catálogo de plantillas rápidas.
  - `dist/emulators/`: Carpeta limpia preparada para dar de alta emuladores.
  - `dist/lists/`: Carpeta limpia preparada para tus listas de juegos.
  - `dist/icons/`: Logotipos e iconos de consolas y arcades.
  - `dist/Layouts/`: Temas y diseños visuales listos para usar (CRT tv, consolas, wheel, showcase, etc.).
  - `dist/splash/`: Carpeta preparada para el video de presentación (Splash Screen).
  - `dist/PlayNexus_Logo.png` y `dist/app_icon.ico`: Logotipo e icono de la aplicación.
  *(Nota: La carpeta `dist/` se encuentra excluida del repositorio Git mediante `.gitignore` para mantener limpio el control de versiones).*

### 2. Lanzadores y utilidades por scripts (.bat)
- **`PlayNexus.bat`**: Menú selector interactivo que te permite elegir entre iniciar el Frontend, el Configurador o compilar los ejecutables.
- **`PlayNexus_Launcher.bat`**: Inicia el Modo Frontend en pantalla completa creando o utilizando el entorno virtual `.venv`.
- **`PlayNexus_Config.bat`**: Inicia el Modo Configurador con detección automática de Python y dependencias.
- **`build_executables.bat` / `Compilar_EXE.bat`**: Automatiza la compilación con PyInstaller y genera la distribución limpia y portable en la carpeta `dist/`.

---

### 3. Instalación manual para desarrollo (PowerShell o CMD)
Si preferís ejecutar desde el entorno de desarrollo:
1. **Crear y activar el entorno virtual:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Ejecutar el Configurador:**
   ```bash
   python -m playnexus
   ```
3. **Ejecutar el Modo Frontend / Jugador:**
   ```bash
   python -m playnexus --player
   ```

---

## 📋 Características principales

### 1. Soporte para Juegos de PC y Windows (Estilo Attract-Mode)
PlayNexus permite integrar juegos nativos de Windows, accesos directos (`.lnk`), scripts por lotes (`.bat`, `.cmd`) y ejecutables (`.exe`):
- **Lanzador mediante comandos de sistema:** Podés registrar emuladores utilizando `cmd` o `cmd.exe` sin necesidad de escribir la ruta absoluta (se resuelve automáticamente a través del `PATH` del sistema).
- **Plantilla rápida en un clic:** En el diálogo de emuladores contás con el botón **«⚙ Cargar plantilla para Juegos de Windows (cmd.exe)»** que configura automáticamente el ejecutable `cmd` con los argumentos `/c "[romfilename]"` y plataforma `PC Games`.
- **Directorio de trabajo (`cwd`) inteligente:** Al ejecutar scripts `.bat`, `.cmd` o accesos directos `.lnk`, PlayNexus sitúa automáticamente el directorio de trabajo en la carpeta donde reside el juego, asegurando que cargue sus archivos locales, configuraciones y librerías sin errores de ruta.
- **Comodines de argumentos compatibles con Attract-Mode y LaunchBox:**
  - `[romfilename]`, `[rom_filename]`, `[rom]`, `%rom%`, `%1`: Ruta completa al archivo del juego con barras invertidas normalizadas de Windows (`C:\...`).
  - `[rompath]`, `[rom_path]`, `[romdir]`: Directorio donde se aloja el juego.
  - `[romname]`, `[rom_name]`, `[name]`, `[cleanromname]`: Nombre del archivo sin extensión.
  - Comodines estilo Python estándar: `{rom}`, `{rom_dir}`, `{rom_name}`.
  - Soporte inteligente de rutas con espacios, evitando la fragmentación de argumentos tanto si se colocan entre comillas como si no.

### 2. Escaneo Asíncrono con Progreso en Vivo y Consola de Depuración
- **Escaneo e importación en segundo plano:** El proceso de búsqueda e importación de juegos se ejecuta en un hilo de trabajo dedicado (`QThread`), garantizando que la interfaz permanezca totalmente fluida y sin bloqueos de Windows (*"no responde"*).
- **Ventana de progreso en vivo:** Muestra una barra de porcentaje, contadores de archivos encontrados, juegos importados y juegos omitidos.
- **Consola de depuración en tiempo real:** Permite observar detalladamente qué archivo se está procesando, qué juego coincidió con las reglas y qué ROMs fueron filtradas.
- **Optimización para XML pesados de MAME/Arcade:** El guardado y validación de listas no bloquea la interfaz al trabajar con catálogos masivos de decenas de miles de juegos (ej. Taito G-Net o conjuntos completos de MAME).

### 3. Listas y Menús Jerárquicos
- **Tipos de listas configurables:**
  - **Juegos (`games`):** Lista estándar asociada a una o más carpetas de ROMs con escaneo automático.
  - **Sublista filtrada (`filtered`):** Lista dinámica generada a partir de otra lista según criterios específicos (ej. juegos de carreras, clones excluidos, fabricantes).
  - **Menú de Sistemas (`menu`):** Menú jerárquico de navegación que agrupa otras listas (ideal para crear menús principales estilo "Arcades", "Consolas" o "Computadoras").
- **Iconos por sistema:** Soporte para asignar iconos individuales (`icon_path`) a cada lista para mostrarlos en selectores y ruedas de navegación. Incluye una carpeta `icons/` con logotipos listos para usar (Arcade, SNES, Genesis, Saturn, PS1, Atomiswave, Naomi, N64, Jaguar, etc.).
- **Carpetas de medios y arte dedicadas:** Configuración por lista para rutas independientes de `boxart`, `wheel` (logos transparentes), `video` (snaps), `flyer`, `cartart`, `cabinet`, `marquee` y `bezel` (artwork de layout).

### 4. Sistema Avanzado de Filtros por Reglas
Disponible tanto para **Listas Filtradas** como para **Listas Comunes**:
- Permite filtrar ROMs durante el escaneo para que sólo se importen los títulos que cumplan condiciones concretas.
- **Campos evaluables:** `sourcefile` (archivo de driver/fuente en XMLs de arcade), `cloneof`, `romof`, `year`, `manufacturer`, `status`, `title`, `name`, entre otros.
- **Operadores flexibles:** `contiene`, `no contiene`, `es igual a`, `comienza con`, `termina con`, `está vacío`, `no está vacío`.
- **Modos de combinación:** Coincidir con todas las reglas (`AND`) o con al menos una (`OR`).
- **Vista previa interactiva:** Botón de previsualización que calcula y muestra en vivo cuántos juegos coincidirán antes de guardar.

### 5. Configuración Flexible de Extensiones y Carpetas de ROMs
- **Selector de presets:** Opciones rápidas para PC Games (`.lnk;.bat;.cmd;.exe`), SNES, GBA, PS1, PS2, Mega Drive, N64, NDS, PSP, Arcade (`.zip;.7z;<DIR>`) o personalización manual.
- **Múltiples carpetas de ROMs:** Soporte para asociar múltiples directorios separados por punto y coma (`;`).
- **Opciones de escaneo:**
  - Activar o desactivar exploración de subcarpetas (`scan_subfolders`).
  - Opción de excluir carpetas descomprimidas si existe un archivo `.zip` con el mismo nombre (`exclude_folder_if_zip`).
  - Normalización automática de extensiones (limpieza de espacios, eliminación de duplicados, minúsculas automáticas y prevención de errores).

### 6. Gestión de Emuladores y Prioridad de Lanzamiento
- Administrador centralizado de emuladores con soporte para cualquier ejecutable o comando del sistema.
- **Plantillas rápidas configurables:** Al dar de alta o editar un emulador, el selector desplegable **«Plantilla rápida»** permite autocompletar nombre, ejecutable, argumentos y plataforma con un solo clic (Juegos de Windows, RetroArch y núcleos habituales, MAME, DuckStation, PCSX2, Dolphin, PPSSPP, Flycast, RPCS3, etc.).
- **Gestor de plantillas en Configuración del Sistema:** En la pestaña *⚙ Configuración del Sistema* podés agregar tus propias plantillas personalizadas con sus ejecutables y argumentos preferidos, editarlas, eliminarlas o restablecer las predeterminadas, quedando inmediatamente disponibles en el selector rápido.
- **Prioridad obligatoria al lanzar un juego:**
  1. *Prioridad 1:* Emulador asignado individualmente al juego (sobrescritura por título).
  2. *Prioridad 2:* Emulador predeterminado configurado en la lista activa.
  3. *Prioridad 3:* Guía asistida si no se ha configurado ninguno.
- **Detección inteligente de núcleos RetroArch:** Corrección automática de rutas si el usuario especificó un `.dll` en una subcarpeta o ruta diferente.
- **Prevención de múltiples instancias:** Evita abrir copias duplicadas del mismo juego ante dobles clics rápidos o pulsaciones repetidas de joystick.

### 7. Motor de Layouts y Temas por Sistema
PlayNexus ofrece un sistema modular y nativo de presentación visual en PySide6 (`playnexus/ui/layouts/`) con múltiples estilos:
- **Temas por Consola (`Layouts/<Sistema>/`):** Diseños gráficos dedicados con renderizado de televisores CRT (`tv.png`), consola física (`console.png`), cartuchos/discos, mandos, video snaps y fondos temáticos (`bkg.jpg` / `bg.jpg`). Incluye soporte autónomo completo para **NEC TurboGrafx-16** (inserción de HuCard en consola), **NEC TurboGrafx-CD** (disco CD-ROM giratorio a 60 FPS), **NEC PC-FX** (disco CD giratorio y avatar animado), **Atari Jaguar**, **Atari Jaguar CD**, **Sega Genesis**, **Sega CD**, **Sega 32X**, **Sega Saturn**, **Sony Playstation**, **Nintendo 64**, **Super Nintendo** y **Nintendo Gameboy Advance** (pantalla LCD integrada en consola portátil).
- **Wheel (Rueda Arcade Clásica):** Rueda curva de logos transparentes con previsualización de video en vivo y carga asíncrona de arte (`wheel_worker.py`).
- **Grid (Estantería / Cuadrícula):** Cuadrícula de carátulas dinámicas o personalizadas con control deslizante de zoom en vivo.
- **Showcase (Modo Cinemático / Big Screen):** Vista cinematográfica con banner superior, tipografía destacada y carrusel inferior de selección rápida.
- **Banners (Tarjetas Horizontales):** Filas amplias con resumen visual y detalles técnicos estilo Steam / LaunchBox.
- **Detalles (Tabla Técnica):** Vista completa y ordenable por columnas (Título, Archivo, Formato, Tamaño, Emulador).

### 8. Configuración de Video, Resoluciones y Pantalla
- **Modos de visualización:**
  - *Pantalla completa (Fullscreen):* Ideal para gabinetes arcade y televisores.
  - *Ventana sin bordes (Borderless):* Expansión a pantalla completa sin bordes de ventana.
  - *Modo Ventana (Windowed):* Ventana redimensionable y centrada.
- **Resoluciones:** 4K UHD, 2K QHD, Full HD (1080p), 720p, relaciones 16:10, 4:3 arcade clásico, resolución nativa automática o personalización exacta en píxeles.
- **Soporte multi-monitor:** Selección del monitor específico donde se abrirá el Frontend.
- **Escala de interfaz (UI Scale):** Ajustes de escala (100%, 125%, 150%, 175%, 200%) para pantallas de alta densidad (HiDPI).

### 9. Control por Gamepad / Joystick y Salida Global
- Soporte para gamepads mediante API de Windows (XInput / DirectInput): navegación por D-Pad, sticks analógicos y botones de acción.
- **Salida rápida de emuladores (`Kill Switch`):** Permite cerrar cualquier emulador en ejecución al presionar `Escape` o el combo de joystick `Back+Start`.
- **Silenciador automático de video:** Pausa y silencia los videos y sonidos de fondo del Frontend mientras el emulador está en ejecución, reanudándolos al salir.

### 10. Bezels Superpuestos en Primer Plano (Bezel HUD / Overlay Transparente)
PlayNexus puede proyectar marcos decorativos (bezels) flotantes directamente por encima de la ventana del emulador en tiempo de ejecución:
- **Carpeta independiente de Bezel HUD:** La carpeta de Bezel HUD (`bezel_hud_path`) se configura por lista y es totalmente independiente de los bezels de artwork del frontend (`bezel_path`).
- **Resolución estricta por ROM y orientación de pantalla:** Al iniciar el juego, PlayNexus busca únicamente dentro de la carpeta HUD seleccionada:
  1. `<nombre_rom>.png` (o el nombre base de la ROM).
  2. Si no se encuentra:
     - Para juegos con pantalla vertical (detectados automáticamente por rotación MAME 90°/270°, resolución o configuración manual): busca primero **`default_v.png`**. Si no existe en la carpeta, recurre a **`default.png`**.
     - Para juegos con pantalla horizontal estándar: busca estrictamente **`default.png`**.
  3. Si ninguno de los archivos existe, no se proyecta ningún bezel.
  *(No busca en ninguna otra carpeta ni utiliza heurísticas de nombres alternativos).*
- **Retardo (`bezel_delay`) y fundido (`bezel_fade`) configurable por emulador:**
  - En la edición de cada emulador se puede calibrar el tiempo de espera en segundos (`Retardo de inicio del Bezel HUD`) para que emuladores que demoran en arrancar o cambiar de modo de video abran limpiamente antes de proyectar el marco.
  - Duración de animación de fundido suave configurable (`Duración del Fade-in`).
  - **Protección anti-crasheos:** Los comandos de cierre de salida forzada quedan bloqueados durante la inicialización del bezel para evitar cierres prematuros de emuladores durante transiciones gráficas delicadas.
- **Control por lista y anulación (override) por ROM:**
  - Se puede activar o desactivar el HUD para toda la lista de juegos.
  - Cada juego cuenta con una opción individual en el panel de detalles y edición para:
    - *Heredar de la lista (por defecto)*.
    - *Activar Bezel HUD (Forzar)*: muestra el bezel aunque la lista lo tenga desactivado.
    - *Desactivar Bezel HUD*: oculta el bezel para esta ROM aunque la lista lo tenga activado.
- **Tecnología Click-Through (Win32 Overlay):** El marco se dibuja en una ventana sin bordes en primer plano con atributos `WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE`. El mouse, teclado y joystick traspasan la ventana hacia el emulador sin perder el foco ni sufrir pérdida de rendimiento.
- **Alternar/Ocultar Bezel en tiempo real durante la emulación:** Se puede presionar en cualquier momento la tecla o botón de mando asignado en la pestaña de Controles de la Configuración del Sistema (por defecto `F11` en teclado o `L-Thumb`/`L3` en gamepad) para ocultar o restaurar el marco decorativo al instante. Esto permite visualizar y operar con comodidad los menús de pausa, configuraciones y barras de herramientas internas del emulador (ej: al pulsar Escape en DuckStation o menús en MAME/RetroArch) sin que el bezel tape ninguna opción.
- **Ciclo de vida y recuperación de primer plano limpio:** Se proyecta automáticamente y se destruye de inmediato al terminar el juego, devolviendo el foco a PlayNexus mediante `AttachThreadInput` sin alterar modificadores del teclado ni activar menús del sistema.

### 11. Pantalla de Bienvenida con Video (Splash Screen de Intro)
- **Video cinematográfico al iniciar:** Permite reproducir un video de introducción a pantalla completa al arrancar el Frontend (`PlayNexus_Launcher.exe`) antes de cargar la biblioteca.
- **Configuración en la pestaña Modo Frontend:**
  - Casilla para activar o desactivar la pantalla de bienvenida.
  - Campo de ruta para el video (soporta `.mp4`, `.mkv`, `.avi`, `.webm`, `.mov`, etc.).
  - Botón **«Examinar…»** y botón de prueba en vivo **«▶ Probar video»** en el monitor de destino.
- **Salto instantáneo (Skip):** Cualquier pulsación de tecla, botón del gamepad o clic de ratón saltea el video al instante para entrar directamente a la biblioteca.
- **Sincronización fluida:** Al terminar o saltar la intro, el layout activo comienza de inmediato la reproducción de su video de fondo o snaps temáticos sin requerir mover la ruleta.

### 12. Pantallas de Carga y Cierre (Loading Screen HUD)
- **Ocultamiento de transiciones de Windows:** Al iniciar un juego o cerrarlo, se despliega una pantalla de carga a pantalla completa (`TOPMOST`) que enmascara los parpadeos del escritorio, cambios de resolución y demoras del emulador.
- **Tiempos configurables por Emulador:**
  - **Apertura (In):** Segundos que se mantiene la pantalla al arrancar el emulador antes de desvanecerse suavemente.
  - **Cierre (Out):** Segundos que se mantiene la pantalla al pulsar la tecla o combo de cierre mientras el emulador finaliza y el layout de PlayNexus recupera el foco.
- **Carpeta única por Lista de Juegos (`loading_path`) con jerarquía de prioridad:**
  - Cada lista permite configurar una única carpeta de Loading Screens, la cual se organiza de forma modular:
    1. **Prioridad 1 (Por juego / ROM):** Subcarpeta con el nombre de la ROM conteniendo `nombrerom_i.<ext>` (apertura) y `nombrerom_o.<ext>` (cierre).
    2. **Prioridad 2 (Por defecto del sistema / lista):** Subcarpeta `default/` conteniendo `default_i.<ext>` y `default_o.<ext>`.
    3. **Prioridad 3 (Genérico global):** Si no existe arte asignado en la lista, recurre automáticamente a la imagen predeterminada en `splash/loading.jpg` (o PNG/WebP).

### 13. Confirmación Segura de Salida del Sistema
- **Diálogo modal arcade con confirmación:** Al pulsar la tecla configurada para cerrar el frontend (por defecto `Escape`) o combo de mando (`Back+Start`), se despliega una ventana interactiva de confirmación que evita salidas involuntarias.
- **Navegación completa por Joystick y Teclado:** Se puede alternar entre «Cancelar» y «Salir del Frontend» mediante las flechas o D-Pad, confirmar con Enter/Botón A o cancelar directamente con Escape/Botón B.

### 14. Sistema de Salvapantallas (Screensaver Arcade)
Inspirado y perfeccionado a partir del script oficial de Attract-Mode (`screensaver.nut`), PlayNexus incluye un motor nativo y dinámico de salvapantallas en PySide6:
- **Detección inteligente de inactividad:** Se activa automáticamente al transcurrir el tiempo configurado sin interacción (por defecto 3 minutos) y se pausa de forma transparente mientras haya un emulador en juego.
- **Cuatro modos visuales con rotación ponderada aleatoria:**
  1. **Video a pantalla completa (`Basic Movie`):** Reproduce video snaps de juegos aleatorios con el logotipo del juego (`wheel` o `boxart`) flotante con sombra suave y transiciones de fade-in y fade-out.
  2. **Collage de videos 2x2 (`Movie Collage`):** Cuadrícula de 4 videos simultáneos. Uno de los cuadrantes reproduce audio temático mientras los otros 3 permanecen en silencio para evitar saturación de sonido. Al finalizar un video se reemplaza por otro o rota el modo.
  3. **Collage de imágenes 4x4 (`Image Collage`):** Mosaico dinámico de 16 capturas o carátulas donde cada 100 ms se reemplaza una celda al azar. Duración de 12 segundos antes de dar paso al siguiente modo.
  4. **Efecto RGB animado (`RGB Movie`):** Video dividido en 3 columnas; la franja central modula dinámicamente colores RGB mientras las columnas laterales realizan un scroll vertical continuo en loop.
- **Apagado profundo de pantalla (Blank Screen):** Pasa a negro absoluto (`#000000`) tras N minutos (por defecto 60 min) para proteger paneles OLED/CRT y ahorrar energía.
- **Interactividad y salto directo al juego (On Select):**
  - Mover el mouse, tocar cualquier tecla ordinaria o presionar botones del mando despierta el Frontend al instante reanudando el layout activo.
  - Al presionar la acción **SELECT** (tecla `Enter` o botón `A` del mando), el salvapantallas se cierra y salta directamente al juego exhibido en ese preciso momento, seleccionándolo en la rueda o lista.
- **Configuración completa en la pestaña *Modo Frontend*:** Tiempo de espera (1 a 120 min), selección de modos habilitados, selector de arte superpuesto (*Wheel*, *Flyer*, *Marquee* o *Ninguno*), activación de sonido, relación de aspecto y botón **«▶ Probar salvapantallas»**.

### 15. Layout Studio (Editor Visual WYSIWYG e Interactivo en Tiempo Real — v1.1.0)
La pestaña **🎨 Layout Studio** ofrece un entorno de edición visual y de código en tiempo real para todos los temas de `Layouts/`:
- **Ejecución directa del código real (`theme_layout.py`):** Lee, instancia y ejecuta directamente el `ThemeLayout` de cada layout sin diccionarios paralelos ni heurísticas, respetando el 100 % de sus elementos locales y compartidos (`gtc-common`, puntero, sombra de ruleta, scanlines, consola, cartucho/disco, flyer, cabinet, marquee, barra inferior).
- **Edición en tiempo real en el lienzo 16:9 (`1920x1080`):**
  - Arrastrar y redimensionar cualquier elemento con gizmos interactivos.
  - **Deformación 4 Puntos (`🔮 Deformación 4 Puntos`):** Transformación proyectiva de perspectiva (`QTransform.quadToQuad` / `corner_pins`) arrastrando individualmente cada esquina de cualquier capa.
  - Gestión de orden de capas (Z-Order), visibilidad individual, opacidad y bloqueo.
  - **Línea de tiempo de animaciones:** Controles de reproducción a 60 FPS (`▶ Play`, `⏸ Pausa`, `⏮ 0.0s`, `±0.1s` y barra deslizante de `0.00s` a `5.00s`) para previsualizar las trayectorias reales de entrada y flotación de cada elemento.
- **Restablecimiento y copias de seguridad automáticas:**
  - Botón **`🔄 Restablecer Cambios`** para devolver todos los elementos a su posición, tamaño, forma y visibilidad originales de fábrica.
  - Al guardar (`💾 Guardar Cambios`), genera automáticamente un respaldo fechado en `Layouts/<Tema>/backups/` antes de escribir en `theme_layout.py`.
- **Sandbox Interactivo en Vivo (`▶ Probar en Sandbox`):**
  - Selector de modo de visualización (`🪟 Modo Ventana`, `🖥 Pantalla Completa`, `🔲 Ventana sin Bordes`) y selector de resolución (`1280x720`, `1920x1080`, `1600x900`, `1366x768`, `2560x1440`, `3840x2160`, `16:10`, `5:4`, `4:3` y `Nativa del Monitor`).
  - Sincronización en tiempo real: cualquier cambio de posición, tamaño, deformación o resolución en el Studio se refleja al instante en la ventana del Sandbox a >170–285 FPS gracias al cacheo de texturas pre-escaladas en espacio de pantalla (`_studio_pix_cache`).

---

## 🗂 Estructura del proyecto

```text
PlayNexus_Frontend/
├── README.md                 # Documentación técnica y guía de uso
├── gemini.md                 # Reglas y directivas de arquitectura del proyecto
├── requirements.txt          # Dependencias del proyecto (PySide6)
├── PlayNexus.bat             # Menú interactivo de selección (.bat)
├── PlayNexus_Config.bat      # Lanzador directo del Modo Configurador (.bat)
├── PlayNexus_Launcher.bat    # Lanzador directo del Modo Frontend / Jugador (.bat)
├── build_executables.py      # Script de compilación y ensamblado de la carpeta dist/ limpia
├── entry_config.py           # Punto de entrada para PlayNexus_Config.exe
├── entry_launcher.py         # Punto de entrada para PlayNexus_Launcher.exe
├── PlayNexus_Logo.png        # Logotipo del proyecto
├── PlayNexus_icon.png        # Icono maestro de alta resolución (1254x1254)
├── app_icon.ico              # Icono multi-resolución de Windows (256, 128, 64, 48, 32, 24, 16 px)
├── splash/                   # Carpeta de videos de presentación (Splash Screen)
├── dist/                     # Distribución independiente 100% limpia y portable (.exe y recursos)
│   ├── PlayNexus_Config.exe  # Ejecutable del Configurador
│   ├── PlayNexus_Launcher.exe# Ejecutable del Frontend / Jugador
│   ├── PlayNexus_Logo.png    # Logotipo del aplicativo
│   ├── app_icon.ico          # Icono del aplicativo
│   ├── config/               # Configuración limpia (settings.txt, emulator_templates.txt)
│   ├── emulators/            # Directorio limpio para registrar emuladores
│   ├── lists/                # Directorio limpio para listas de juegos
│   ├── icons/                # Iconos de consolas y arcades
│   ├── Layouts/              # Diseños y temas visuales nativos
│   └── splash/               # Video de presentación (Splash Screen)
├── config/                   # Configuración del entorno de desarrollo
├── emulators/                # Archivos .txt de emuladores del entorno local
├── lists/                    # Archivos .txt de listas del entorno local
├── icons/                    # Logotipos e iconos de consolas y arcades (.png)
├── Layouts/                  # Carpetas de temas y layouts dedicados por consola y arcade
└── playnexus/
    ├── __init__.py
    ├── __version__.py        # Versión centralizada del sistema (v1.1.13)
    ├── __main__.py           # Enrutador principal (--player o configurador)
    ├── db.py                 # Motor de almacenamiento en memoria y archivos de texto plano (.txt)
    ├── services/
    │   ├── __init__.py
    │   ├── controls.py       # Mapeo y gestión de controles de teclado
    │   ├── emulator_manager.py # Monitoreo de procesos, retardos, fade, HUD y salida global
    │   ├── emulator_templates.py # Carga, edición y persistencia de plantillas rápidas
    │   ├── gamepad.py        # Lectura y eventos de joystick / gamepad
    │   ├── launcher.py       # Resolución de emuladores, comodines Attract-Mode y ejecución
    │   ├── library.py        # Normalización de extensiones, XML de MAME, filtros y escaneo
    │   ├── media.py          # Resolución y búsqueda de medios (video, wheel, carátulas, bezels)
    │   └── themes.py         # Carga y detección de temas personalizados por consola
    └── ui/
        ├── __init__.py
        ├── bezel_overlay.py  # Ventana de overlay transparente para Bezel HUD con fade
        ├── cover_utils.py    # Generador procedural de carátulas dinámicas y carga de arte
        ├── dialogs.py        # Diálogos: Listas, Emuladores (retardo/fade/loading), Escaneo, Filtros
        ├── exit_confirm_dialog.py # Diálogo modal de confirmación de salida del Frontend
        ├── frontend_tab.py   # Configuración de video, pantalla, Salvapantallas y Splash Screen
        ├── loading_overlay.py# Ventana a pantalla completa para Loading HUD (apertura/cierre)
        ├── main_window.py    # Ventana principal del Configurador
        ├── player_window.py  # Ventana del Modo Frontend / Jugador (pantalla completa)
        ├── screensaver.py    # Motor de salvapantallas arcade (4 modos visuales)
        ├── settings_tab.py   # Pestaña de configuración general y controles
        ├── splash_screen.py  # Reproductor a pantalla completa del video de bienvenida
        ├── layout_studio/    # Entorno visual de diseño de layouts en tiempo real (v1.1.0)
        │   ├── __init__.py
        │   ├── canvas.py         # Lienzo WYSIWYG interactivo 16:9, gizmos y deformación 4 puntos
        │   ├── code_editor.py    # Editor de código Python con resaltado y Hot Reload
        │   ├── inspector.py      # Inspector de capas (Z-Order), geometría y propiedades
        │   ├── models.py         # Modelos de datos (LayoutProject, LayoutElement)
        │   ├── runtime_hook.py   # Introspección AST/píxel y renderizado en vivo de ThemeLayout
        │   ├── studio_tab.py     # Pestaña principal, línea de tiempo y Sandbox multi-resolución
        │   └── templates.py      # Generador de plantillas base para nuevos layouts
        └── layouts/          # Fábrica y modos de layouts
            ├── __init__.py
            ├── base.py       # Clase base abstracta BaseLayout
            ├── banner_layout.py    # Modo Banners horizontales
            ├── grid_layout.py      # Modo Cuadrícula con zoom regulable
            ├── showcase_layout.py  # Modo Cinemático / Showcase
            ├── table_layout.py     # Modo Tabla técnica de detalles
            ├── theme_layout.py     # Layout temático por sistema (TV CRT, consola, video)
            ├── wheel_layout.py     # Rueda arcade interactiva
            └── wheel_worker.py     # Hilo trabajador para renderizado suave de la rueda
```

---

## 💾 Persistencia de datos en Texto Plano (100% Portable)

PlayNexus almacena toda la información de manera legible y portable en archivos de texto plano directamente dentro de la carpeta del proyecto, sin crear entradas en el registro ni carpetas ocultas en `AppData`:

- **`config/settings.txt`**: Ajustes generales, controles asignados, modos de video y preferencias.
- **`config/emulator_templates.txt`**: Catálogo de plantillas rápidas de emuladores (nombre, ejecutable, argumentos, plataforma, descripción, retardo/fade de Bezel y tiempos de Loading Screen).
- **`emulators/<NombreEmulador>.txt`**: Parámetros de cada emulador (`executable`, `arguments`, `platform`, `bezel_delay`, `bezel_fade`, `loading_time`, `exit_loading_time`).
- **`lists/<NombreLista>.txt`**: Configuración de cada lista (`[List]`: rutas de ROMs, layout, icono, filtros, medios, Bezel HUD, carpeta única de carga `loading_path`) y catálogo completo de juegos (`[Games]`: título, archivo, emulador individual, modo de Bezel HUD, metadatos).
