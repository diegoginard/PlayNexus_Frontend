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

