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

