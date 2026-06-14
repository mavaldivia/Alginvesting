## Done

Ítems completados, organizados por sección.

### X2 — X2_fundamentals.py

- [x] **X2_fundamentals.py**: score fundamental por activo. Acciones: yfinance (ingresos, EPS, P/E, EV/EBITDA, ROE, ROA, FCF, deuda, market cap). Crypto: yfinance + fuentes on-chain (CoinGecko u otras). Output: score de confianza por activo en rango [0, 1]. (I:7 C:6 H:6 → 1.08)

### X0 — X0_data_supports.py

- [x] **X0: loop continuo (`--loop`) no funciona correctamente**: el ciclo `while True` no reinicia como se espera — verificar que tras converger todos los combos el loop vuelve a ejecutar descarga + soportes con los deltas actualizados, y que `_seleccionar_combos` refleja el estado real de cada `_delta.json` al inicio de cada vuelta. (I:9 C:2 H:9 → 4.50)
- [x] **Formato de outputs en paralelo**: al terminar cada par (valor, N) en modo paralelo, imprimir una línea con el tiempo que tardó en converger y si convergió o no. El resumen se imprime después de que el monitor para (sin interferir con el redibujado). `_procesar_valor_N` retorna `(duracion_s, convergio)`; el loop `as_completed` acumula en `resultados_tiempo` y se imprime tras `monitor.join()`.
- [x] **Separar `conjuntos_N/` en productivo vs backtesting**: reorganizar en `conjuntos_N/prod/{VALOR}_{N}.json`, `conjuntos_N/prod/{VALOR}_{N}_delta.json`, `conjuntos_N/bt/{VALOR}_{N}_bt.json`, `conjuntos_N/bt/{VALOR}_{N}_bt_delta.json`. Actualizar rutas en `config.py`, X0 y X1. Evita mezclar archivos de producción con cache de bt y facilita limpiar uno sin afectar el otro. (I:7 C:2 H:8 → 3.74)
- [x] **FO no decrece en el monitor de progreso**: el output en vivo muestra la FO de la iteración actual, que puede bajar. Debe mostrar solo la mejor FO encontrada hasta el momento (monotónicamente no decreciente). Requiere mantener `fo_mejor` por combo en el estado compartido del monitor y actualizar solo si `FO_actual > fo_mejor`. (I:5 C:1 H:7 → 5.92)
- [x] **FO inicial 0 al arrancar tupla (valor, N)**: tras calcular `FO_ref` en `_procesar_valor_N`, se actualiza `estado_compartido` con ese valor antes de lanzar el optimizador. El monitor ya no muestra FO=0 durante la fase de preparación. (I:4 C:2 H:3 → 1.73)
- [x] **Contador de cambios inflado en el output**: renombrada etiqueta `cambios` → `pasos` en el monitor en vivo (micro-pasos del optimizador). Al finalizar, se calcula `cambios_netos = len(conjunto_N_prev - conjunto_N)` (soportes cuya posición final difiere del warm start) y se usa en el estado final, print y log. (I:3 C:2 H:3 → 1.50)
- [x] **Cambios reportados en el output son demasiado altos**: el contador ya solo suma cambios aceptados (`mejora_rel > delta_inicial`); el número alto era consecuencia del cycling. Resuelto al corregir la detección de convergencia. (I:6 C:2 H:8 → 3.46)
- [x] **S5 — `prueba_cercanos=True` por defecto**: cambiar `prueba_cercanos: bool = False` a `True` en `nuevo_optimizador_2` — tras aceptar un cambio en soporte `i`, sus vecinos `i-1` e `i+1` pasan al frente de `casos_moviles` antes del shuffle. Lógicamente correcto porque sus cotas vecinas cambiaron. Ya implementado en el código, solo falta activar el default. Validar con logs de convergencia. (I:4 C:1 H:3 → 3.46)
- [x] **S3 — M adaptativo coarse-to-fine**: correr `nuevo_optimizador_2` en dos fases: **fase 1** con M=5 hasta convergencia (exploración barata), **fase 2** con M=30 tomando el resultado de fase 1 como warm start (refinamiento fino). Estimación: ~58% menos evaluaciones de FO vs. M=30 fijo. Implementar directamente en `X0_data_supports.py`. (I:7 C:2 H:6 → 3.24)
- [x] **Inconsistencia entre estado de convergencia reportado y `_delta.json`**: el optimizador cicla sin ganar terreno real porque el inner loop rompe al primer vecino mejorable y nunca completa el scan completo. Fix en `_procesar_valor_N`: tras ambas fases, si `|(FO_final - FO_ref) / FO_ref| < delta_actual` → forzar `convergio=True` → delta se reduce en la siguiente corrida, extinguiendo el ciclo progresivamente. (I:9 C:3 H:9 → 3.00)
- [x] **S4 — Priorización de soportes por historial de mejoras**: en `nuevo_optimizador_2`, mantener `mejora_acumulada[i]` (EMA de mejoras aceptadas por soporte) y al reconstruir `casos_moviles`, ordenar desc por este historial en lugar de shuffle aleatorio. Estimación: 15-25% menos llamadas a `calcular_FO` en iteraciones tardías cuando la mayoría de soportes ya convergió. (I:5 C:2 H:4 → 2.24)
- [x] **S2 — Inicialización inteligente del conjunto N**: en cold start (sin JSON previo), inicializar `conjunto_N` con los N precios de mayor score `y × w` de `df_extremos` (aislamiento × recencia), con diversidad espacial por quantiles del rango, en lugar de `np.random.uniform`. Estimación: 60-80% menos iteraciones en cold start. Crítico para X4 backtesting, que genera muchos cold starts. (I:6 C:3 H:7 → 2.16)
- [x] **Logs de convergencia**: al converger cada combo (valor, N) — o (valor, N, max_datetime) en modo bt — guardar JSON en `docs/X0/logs/` con: clave de la tupla, t_inicio, t_fin, duración, iteraciones, FO final, delta_final, convergio (I:5 C:4 H:6 → 1.37)
- [x] **N_MAX_MODELS + loop continuo**: parámetro `N_MAX_MODELS` en `config.py` — selecciona los N pares (valor, N) con mayor `delta_inicial` actual (tie-break aleatorio), los ejecuta en paralelo, y al terminar el último reinicia el ciclo completo (incluyendo descarga MT5 si opción 1 activa) en un `while True` (I:8 C:6 H:7 → 1.25)
- [x] **S6 — Vectorización del loop interno de candidatos M**: reemplazar el for-loop Python de M candidatos en `nuevo_optimizador_2` por evaluación matricial `(M, N)` con numpy — construir todos los M conjuntos de soportes como matriz y pasar a versión vectorizada de `asignar_soporte`. Complementario con S1. Estimación: 2-4x speedup en inner loop; más impactante si M sube con S3 fase fine. (I:6 C:5 H:6 → 1.20)
- [x] **S1 — Evaluación incremental de la FO**: refactorizar `calcular_FO` para que al mover soporte `i`, solo recompute las ~3n/N filas afectadas (asignadas a `i-1`, `i`, `i+1`) y los 2 gaps del `cv(H_n)` que cambian. Requiere precalcular `asignaciones[i]` al inicio de cada iteración y mantenerlo actualizado tras cada cambio. Estimación: 30-35x speedup en la evaluación de FO — convierte ~20 min a ~35-40 seg en BTCUSD N=100. Habilita X4 backtesting práctico. (I:9 C:8 H:9 → 1.13)
- [x] Velocidad lógica del optimizador: `DELTA_INICIAL` adaptativo — delta se reduce (`* FACTOR_DELTA = 0.7`) solo cuando el optimizador converge; si no converge, el delta se mantiene. Estado persistido en `{valor}_{N}_delta.json` con `{'delta_inicial', 'convergio'}`. Órdenes activas de MT5 (`positions_get`) se pasan como soportes fijos al optimizador vía `obtener_ordenes_activas_mt5` (falla gracefully si MT5 no disponible). (I:6 C:5 H:3 → 0.85)
- [x] **Sugerencias de convergencia**: 7 mejoras algorítmicas documentadas en `docs/documentacion_V0.md` — FO incremental, inicialización inteligente, M adaptativo, priorización por historial, prueba_cercanos, vectorización loop M, criterio parada por tasa. Ordenadas por impacto/complejidad.
- [x] **Monitor de progreso en vivo**: `buscar_soportes` usa `multiprocessing.Manager().dict()` compartido entre workers + hilo monitor que redibuja una tabla cada segundo. Muestra por cada (valor, N): cambios aceptados, `max_pasos` (máximo de posiciones recorridas en el inner loop antes de aceptar un cambio), y FO actual. Workers corren con `verbose=False` (sin prints ni tqdm).
- [x] **Fix bug crítico en el optimizador**: condición de mejora `(FO_iter - FO_base) / FO_base > delta` era siempre falsa porque la FO es negativa — denominador negativo invertía el signo. Corregido a `/ abs(FO_base)`. El optimizador nunca había aceptado ningún cambio desde que la FO pasó a ser negativa.
- [x] **Fix bug `idxmax` con índices duplicados**: `df_plot` se construía con `pd.concat` acumulando filas con índice 0; `df_plot.loc[idxmax(), 'caso']` devolvía una Serie en vez de un escalar. Corregido con `argmax()` + `iloc`.
- [x] **Títulos en gráficos**: todas las funciones de visualización reciben `valor` y `N` y muestran título `"Tipo — VALOR N=N"`.
- [x] **Guardar plots en disco**: `plt.show()` reemplazado por `plt.savefig()` en `plots/{Extremos,FO,Soportes,Zoom}/{valor}_{N}.png`. Carpetas se crean automáticamente; archivos se sobreescriben.
- [x] **Info previa secuencial**: antes de lanzar el executor, `buscar_soportes` imprime en orden (sin mezcla) el rango de fechas, último cierre, warm start y delta para cada (valor, N).
- [x] **Paralelización**: la búsqueda de soportes es independiente por cada par (valor, N) → paralelizar con `multiprocessing` o `concurrent.futures`. Ej: BTCUSD-130, ETHUSD-130, TSLA-120, etc. corriendo simultáneamente.
- [x] Velocidad: `calcular_distancias` vectorizada con numpy por bloques (evita matriz n×n completa) — ~19x más rápido (33.9s → 1.8s en BTCUSD, n=21213), resultados idénticos byte a byte
- [x] Velocidad: `asignar_soporte` vectorizada con `np.searchsorted` (búsqueda binaria del soporte más cercano, O(n log N) en vez de O(n×N) con `apply`) — ~45-178x más rápido (0.26s → 0.0014s en BTCUSD, N=130), resultados idénticos byte a byte
- [x] Parámetros: documentado el efecto de cada uno (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL) en la nueva sección "Parámetros del algoritmo — efecto de cada uno"
- [x] Storage: migrado `conjuntos_N/` de pickle a JSON (`json_act` en X0 y X1) — `conjunto_N` es solo un set de ~50-130 floats, parquet quedaba descartado por sobredimensionado; JSON permite inspeccionar los soportes a simple vista
- [x] Config: mover parámetros a un archivo de configuración separado (`config.py`)
- [x] Reorganizar `config.py` en grupos temáticos (rutas, activos, datos históricos, calidad del algoritmo, velocidad/cómputo, visualizaciones, trading) en vez del agrupamiento por script (X0/X1)
- [x] Migrar X0 (notebook) a `scripts/X0_data_supports.py`

### X1 — X1_trading.py

- [x] Migrar X1 (notebook) a `scripts/X1_trading.py`
  - Mismas reglas que X0: solo lo estrictamente necesario, misma lógica
  - Agregada lógica: si pérdida > `PERDIDA_MAX` → cerrar la operación (`controlar_perdida_max`)

### X2 — X2_fundamentals.py

- [x] **[x2_plan punto 4] Guardar historial del score X2**: al calcular el score por activo, hacer upsert en un archivo histórico (`fundamentals/x2_history.json` con entradas `{datetime, activo, score, components}`) para permitir análisis de evolución del sentimiento y uso como feature en X5/X6. Diseño detallado en sección 3.5 de `docs/x2_plan.md`. (I:6 C:2 H:7 → 2.92)
- [x] **Leer plan en `docs/x2_plan.md` y confirmar implementación**: revisar diseño de fuentes, score y arquitectura propuestos; aprobar o ajustar antes de codificar. (I:3 C:1 H:9 → 5.20)
- [x] Definir y evaluar fuentes de datos para X2: yfinance, MT5, investing.com, CoinGecko, Glassnode u otras. Qué cubre cada una, qué tan confiable y actualizable es. (I:5 C:2 H:8 → 3.16)
- [x] **[x2_plan cap.2] Los pesos iniciales del score son fijos por ahora, pero X6 DEBE incorporar lógica de aprendizaje sobre ellos**: los ponderadores del score compuesto (fundamentales + on-chain + sentimiento) deben ser parámetros entrenables que X6 ajuste según el historial de trades. Dejar los pesos actuales como inicialización, no como valores permanentes. (I:8 C:3 H:9 → 4.90)
- [x] **[x2_plan paso 3] Marcar día ya ejecutado**: al correr X2 al inicio de X0, guardar en disco la fecha de la última ejecución (`fundamentals/x2_last_run.json` con campo `fecha`). Si ya se ejecutó hoy, saltear. Evita re-ejecutar en cada ciclo del `while True` o cada corrida manual de X0. (I:4 C:1 H:9 → 6.00)
- [x] **[x2_plan paso 3] Ejecutar X2 al menos una vez al día en el loop de X0**: en el `while True` de X0, forzar ejecución de X2 a una hora determinada aunque ya se haya ejecutado al inicio del loop ese día — garantiza que el score se actualice diariamente en corridas de varios días seguidos. Hora configurable vía `X2_HORA_EJECUCION` en `config.py`. (I:5 C:2 H:8 → 3.16)

### X4 — X4_backtester.py

- [x] **Fecha/hora máxima por tupla (valor, N) para backtesting**: `_procesar_valor_N` acepta `fecha_hora_max` opcional — filtra datos hasta ese datetime, usa warm start desde `{valor}_{N}_bt.json` (cache `{datetime: [soportes]}`), delta desde `{valor}_{N}_bt_delta.json`. Sin look-ahead: la clave guardada es `df['DateTime'].iloc[-1]` (último dato realmente usado). Lookup: `max(t1 <= t0)`. X4 llama esta función directamente con `fecha_hora_max=t`. X0 producción sin cambios. (I:10 C:5 H:8 → 1.26)
- [x] Evaluar incorporar X1.5_intravela al scope (renombrado de X2_Intravela; numeración 1.5 para no desplazar la visión) (I:6 C:7 H:5 → 0.78) — decisión: no es un script separado, la lógica va embebida en X4 como subrutina de simulación intra-vela. Ver `docs/decisiones.md` 2026-06-08.
- [x] Revisar los mensajes "SEGUIR EXPLICACION" en `prompts` (líneas 57 y 62) — quedaron explicaciones pendientes de continuar (lógica de `X2_Intravela` para el caso borde de abrir y cerrar una orden dentro de la misma vela horaria)

### Transversal

- [x] **Tiempo de ejecución al final de cada script**: al terminar `X0_data_supports.py`, `X1_trading.py` y cualquier script Python del proyecto, imprimir el tiempo total transcurrido (formato `HH:MM:SS` o segundos si < 60 s). Implementar con `time.time()` en el `if __name__ == '__main__'` de cada script. (I:3 C:1 H:2 → 2.45)
- [x] **Modificar skill `/todos`**: al preguntar qué sección elegir, mostrar nombre del grupo + cantidad de ítems pendientes + score del ítem más prioritario del grupo. Omitir grupos sin pendientes.
- [x] **TO DOs en archivo separado + actualizar skill `update-push`**: mover los ítems TO DO de `CLAUDE.md` a `docs/todos.md` para reducir el contexto que Claude carga en cada sesión. Adaptar la skill `update-push` para que incluya `docs/todos.md` en el staging y mantenga `CLAUDE.md` sin la sección TO DO (o con solo un puntero a `docs/todos.md`). (I:8 C:2 H:8 → 4.00)
- [x] Definir cuándo y cómo mergear `dev` → `master` (primera versión estable) — ver `docs/decisiones.md` 2026-06-07: merge solo tras validar X0+X1 en Windows con MT5 real, vía merge commit normal (sin squash)
- [x] Crear skill/comando `/push` para git push a rama desde Claude Code (I:3 C:2 H:4 → 1.73) — cubierto por la skill global `/update-push` (commit + push a la rama actual, con actualización de CLAUDE.md/README.md)
- [x] **BIG PICTURE**: Mauricio explicó la visión completa — ver `docs/vision.md`. Arquitectura X0→X6 definida, orden de construcción declarado, decisiones de diseño registradas. (I:9 C:8 H:9 → 1.13)
- [x] Rama `base_v0` → estado original (notebooks, estructura Windows)
- [x] Rama `dev` → trabajo activo. Push inicial: migración X0 + X1 a .py
- [x] Próximo push a `dev`: después de mejoras X0 (paralelización, velocidad) — ya estaba en `origin/dev` (commits hasta `c92a8f0`)

---
