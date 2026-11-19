# Reglas y Directivas de Trabajo para el Asistente

1. **PROHIBIDO MODIFICAR ARCHIVOS POR CUENTA PROPIA:**
   - No realizar cambios, creaciones ni ediciones en ningún archivo del proyecto a menos que el usuario lo solicite de manera explícita y directa.
   - Si se detecta un posible problema o mejora, consultar y pedir confirmación antes de tocar cualquier línea de código.

2. **ALCANCE ESTRICTO:**
   - Limitarse únicamente a lo solicitado en cada petición puntual.
   - No modificar archivos de otros sistemas o layouts si no fueron expresamente pedidos.

3. **CONFIRMACIÓN PREVIA:**
   - Explicar qué se planea modificar y esperar la aprobación del usuario antes de proceder con cualquier edición.

4. **REQUERIMIENTOS DE MEDIOS ESTRICTAMENTE EXPLÍCITOS:**
   - Los requerimientos de medios (`MEDIA_REQUIREMENTS`) provienen única y exclusivamente de cada `theme_layout.py`.
   - Si un medio no figura de forma explícita en los requerimientos del layout, no se muestra ni se solicita en el creador de listas.
   - Prohibido el uso de diccionarios paralelos o heurísticas de auto-detección/adivinación en el resto del código; todo debe manejarse de forma 100% explícita desde el layout.

5. **COMPROMISO DE MEDIOS AL SOLTAR EL BOTÓN (COMMIT ON RELEASE / DEBOUNCE):**
   - Durante la navegación continua (tecla mantenida, saltos rápidos o rueda de mouse), solo debe desplazarse la ruleta/lista y actualizarse el contador del pie.
   - **Ningún video debe pausarse durante la navegación:** El video del juego previo continúa reproduciéndose fluidamente sin pausas ni interrupciones mientras se mantengan pulsadas las teclas de navegación o se gire la ruleta. Asimismo, los videos de fondo (background video) deben reproducirse de forma continua y fluida en todo momento, sin pausarse ni saltear cuadros durante el giro.
   - Prohibido cargar artes pesadas (cabinets, carátulas, cartuchos/discos) o disparar la carga de videos de juegos intermedios o en el `keyPress` inicial antes de soltar la tecla.
   - La carga del nuevo juego (arte, animaciones de entrada, emisión de `game_selected` y reproducción de video) debe ejecutarse de forma sincronizada y unificada única y exclusivamente cuando el usuario suelta la tecla (`keyReleaseEvent`) o tras el vencimiento del temporizador de confirmación (`_commit_timer` a ~180 ms).
   - **Interacción con Mouse / Clics:** Al hacer clic con el mouse y no soltar el botón, queda estrictamente prohibido mover la ruleta de wheels, cambiar el arte o activar el juego. Nada debe variar hasta el evento de soltado (`mouseReleaseEvent`); la ruleta de wheels y los medios solo cambian o se activan al producirse el release.

6. **FIDELIDAD 100 % EN LAYOUT STUDIO Y SANDBOX (EJECUCIÓN DIRECTA DE `theme_layout.py`):**
   - Prohibido crear diccionarios paralelos, heurísticas o inventar geometrías en `playnexus/ui/layout_studio/`.
   - El Layout Studio debe leer, instanciar y replicar tal cual el código de `theme_layout.py` de cada layout (incluyendo todos los elementos locales y los tomados de `gtc-common`, puntero, sombra de ruleta, scanlines, flyer, cabinet, consola, cartucho/disco y barra inferior).
   - El Sandbox debe reflejar el 100 % del tamaño real de los elementos del layout (sin doble reescalado entre el espacio canónico `1920x1080` y la resolución de la ventana), ejecutarse con fluidez (>60 FPS mediante caché de texturas pre-escaladas) y permitir elegir modo (`Ventana`, `Pantalla Completa`, `Sin Bordes`) y resolución.

7. **VERSIONADO AUTOMÁTICO EN CORRECCIÓN DE BUGS (INCREMENTO DEL ÚLTIMO DÍGITO):**
   - Toda corrección de bugs debe sumar de `1` en `1` el último dígito del versionador central en `playnexus/__version__.py` (`__version__`, por ejemplo `1.1.0` -> `1.1.1` -> `1.1.2`).

8. **ORDEN Y DECLARACIÓN EXPLÍCITA DE REQUERIMIENTOS, FUENTES Y MEDIOS AL INICIO DE TODO `theme_layout.py`:**
   - Todo layout debe respetar estrictamente el siguiente orden en la cabecera de la clase `ThemeLayout`:
     1. **Requerimientos de Medios (`MEDIA_REQUIREMENTS`):** Debe ubicarse en primer lugar inmediatamente al inicio de la clase (leídos directamente por el creador de listas y el sistema de escaneo).
     2. **Fuentes Tipográficas (Fonts):** Inmediatamente después de los requerimientos de medios. Declarar obligatoriamente: `FONT_TITLE_FILE` (para títulos destacados), `FONT_MAIN_FILE` o `FONT_COUNTER_FILE` (para contadores, información técnica y texto general) y la lista agrupada `FONT_FILES = [FONT_TITLE_FILE, ...]`. Si un layout no utiliza fuentes externas personalizadas, debe declararse explícitamente como `None`.
     3. **Recursos de Medios Compartidos y Locales:**
        - Compartidos desde `gtc-common`: `SCANLINES_IMAGE`, `SCRATCHES_IMAGE`, `WHEEL_SHADOW_IMAGE`, `COMMON_WHEEL_ART`, `COMMON_FRAME`, `STATIC_VIDEO`, `SOUND_NAV`, `SOUND_SELECT`.
        - Locales del layout: `BKG_IMAGE`, `TV_IMAGE`, `CONSOLE_IMAGE`, `CONSOLE_COVER_IMAGE`, `JOYSTICK_IMAGE`, `AVATAR_IMAGE`, `LOGO_IMAGE`, `CARTART_IMAGE` (o `DISCART_IMAGE`), `BOXART_IMAGE`, `WHEEL_IMAGE`, `POINTER_IMAGE`, etc. Si un recurso no se utiliza o es opcional en dicho layout, debe declararse explícitamente como `None`.
     4. **Configuración Geométrica y Métricas:** (`TV_RECT`, `CART_RECT`, `CONVEYOR_*`, etc.).
   - Prohibido dejar rutas "mágicas" o resoluciones en tiempo de ejecución hardcodeadas dentro de los métodos; el Layout Studio debe poder inspeccionar y leer directamente estas constantes de clase desde `ThemeLayout`.

9. **ESTÁNDAR DE RENDERIZADO 100 % GPU (OpenGL) EN FUTUROS LAYOUTS Y PREVISUALIZADORES:**
   - **Integración obligatoria con el motor GPU (`playnexus/ui/gpu_renderer.py` y `runtime_hook.py`):**
     - Todo nuevo `theme_layout.py` en `Layouts/<Sistema>/` debe incluir al final el bloque `# --- PLAYNEXUS STUDIO OVERRIDES START --- ... # --- PLAYNEXUS STUDIO OVERRIDES END ---` llamando a `install_studio_overrides(self, STUDIO_ELEMENTS, **STUDIO_EFFECTS)` y respetar `SHADER_PRESET`, `SHADER_TARGET` y `PARTICLE_PRESET` en su configuración (con respaldo automático a `QPainter` bajo `frontend_render_backend = software`).
     - Para habilitar GPU en layouts existentes sin editar archivos individuales bajo `Layouts/`, el cargador central (`playnexus/ui/layouts/theme_layout.py`) puede extraer `STUDIO_ELEMENTS` e instalar `install_studio_overrides` automáticamente en tiempo de instanciación.
   - **Ruleta de Wheels fluida a >60 FPS (`_WheelGpuCollector` / `_emit_wheel_gpu_commands`):**
     - `_draw_wheel_conveyor` y `_draw_wheel` deben usar exclusivamente las primitivas soportadas por el recolector GPU (`save`, `restore`, `translate`, `rotate`, `setTransform`, `setOpacity`, `drawPixmap`, y para tarjetas sin PNG `fillPath`, `drawPath`, `fillRect`, `drawRect`, `drawRoundedRect`, `drawText` agrupadas dentro de `save()`/`restore()`).
     - **Prohibido** reescalar `QPixmap` o generar capas completas en CPU dentro de cada tick de giro (`_wheel_spin_offset` / `_wheel_offset`); los logos PNG se emiten directamente por quad manteniendo la textura residente en VRAM por `cacheKey()`.
   - **Texturas PNG nítidas y sin halos (`GpuTextureCache`):**
     - Prohibido subir `QImage` premultiplicadas vía `QOpenGLTexture(img)` (Qt des-premultiplica RGB causando halos en bordes y sombras transparentes); toda textura nueva o dinámica debe usar subida premultiplicada directa (`Target2D` + `RGBA8_UNorm` + `setData(0, RGBA, UInt8, ...)`), con mipmaps trilineales (`LinearMipMapLinear` + `LOD bias -0.75`) para artes/wheels/portadas/overlays y actualización *in-place* (`dynamic_rev`) sin reallocs VRAM para capas de texto dinámico.
   - **Videos y animaciones sin cortes ni reinicios dobles:**
     - Los reproductores de video (`ThemeLayout`, futuros layouts genéricos como `WheelLayout`, y previsualizadores como `MediaPreviewWidget`) deben consumir `QVideoFrame` directo vía `GpuVideoSurface` (NV12/YUV420P/RGBA/BGRA en shader GPU sin `frame.toImage()` ni `fbo.toImage()`), cayendo a `QVideoWidget`/`QPainter` solo en modo `software`.
     - Las animaciones de entrada por juego (`cart_drop`, `disc_rise`, `boxart_slide_fade`, `flyer_slide_right`) deben dispararse **una sola vez por cambio efectivo de juego** (prohibido enlazar `_load_pending_art` u otros helpers llamados por `_play_debounced_video` o commits diferidos incompletos); las animaciones continuas (`avatar_float`, `pointer_pulse`, `disc_spin`, shaders y partículas) deben correr sobre reloj continuo independiente y `logo_bounce` solo al cargar la lista (`set_games`), evitando duplicar offsets nativos cuando Studio ya anima el elemento.
   - **Layouts genéricos y delegados (`Grid`, `Showcase`, `Banners`, `Wheel`):**
     - **Prohibido** llamar `QPixmap.scaled(..., Qt.SmoothTransformation)` o leer portadas desde disco (`load_cover`) dentro de `paint()` / `paintEvent()`; cualquier nuevo layout o vista genérica debe precargar en hilo secundario, cachear escalados por `(game_id, ancho, alto)` o renderizar sus tarjetas/carrusel/efectos directamente sobre `GpuSceneViewport` con loteo OpenGL (`GpuQuadPipeline`) evitando `bind`/`release` repetitivos por cada quad.

10. **ORDEN VERTICAL E INTERACCIÓN ESTÁNDAR DE LA RULETA DE WHEELS EN FUTUROS LAYOUTS:**
    - **Distribución vertical en ruletas curvas (`_draw_wheel_conveyor` / `_draw_wheel`):**
      - El elemento **siguiente** de la lista (`(selected_index + 1) % n`, `+2`, `+3`...) debe dibujarse **arriba** del centro (`slot < center_node`), y el elemento **anterior** (`(selected_index - 1) % n`, `-2`, `-3`...) **abajo** del centro (`slot > center_node`):
        - En conveyors interpolados de 14 nodos (`_wheel_spin_offset`): usar `game_idx = (self.selected_index + offset) % n_games` con `pos = (7.0 - offset) - self._wheel_spin_offset` (de modo que al avanzar `+1`, el ítem superior en `pos = 6.0` descienda suavemente hacia `7.0`).
        - En conveyors discretos (`for i in range(len(self.CONVEYOR_X))`): usar `slot_idx = center_node - i` y `game_idx = (self.selected_index + slot_idx) % n`.
        - En ruletas elípticas (`_draw_wheel`): usar `game_idx = (self.selected_index - offset) % n` manteniendo `dist = float(offset) - self._wheel_spin_offset`.
    - **Navegación con teclado, rueda del ratón y clic/arrastre:**
      - Teclado y rueda del ratón conservan el sentido de avance estándar: **Abajo / rueda hacia abajo (`delta < 0`)** avanza al siguiente (`_navigate_steps(+1)`), y **Arriba / rueda hacia arriba (`delta > 0`)** retrocede al anterior (`_navigate_steps(-1)`).
      - En `mouseReleaseEvent`: los clics por slot deben usar el mismo índice (`pos_idx = (7.0 - offset) - self._wheel_spin_offset`); los clics en la zona superior o arrastres hacia abajo navegan al siguiente (`+1`, ubicado arriba) y los clics en la zona inferior o arrastres hacia arriba al anterior (`-1`, ubicado abajo).
      - El layout genérico de lista vertical plana (`WheelLayout`, basado en `QListWidget`) conserva su orden normal `A -> Z` de arriba hacia abajo.




