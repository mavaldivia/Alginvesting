# Decisiones técnicas — Alginvesting

## 2026-06-03 — Migración de notebooks a .py

**Decisión:** migrar X0 y X1 de `.ipynb` a `.py`.
**Razón:** facilita control de versiones, ejecución en Windows sin Jupyter, y mantiene el código más limpio para refactors con Claude Code.
**Descartado:** mantener notebooks para todo — dificulta el diff en git y el flujo Mac→Windows.
**Excepción:** módulos nuevos con componente visual importante pueden iniciar como `.ipynb` durante exploración.

## 2026-06-03 — Alginvesting_base como solo lectura

**Decisión:** `Alginvesting_base/` se agrega al `.gitignore` del nuevo proyecto y se trata como referencia histórica inmutable.
**Razón:** es el repo clonado desde Windows (versión anterior). Mezclar código nuevo con ese directorio genera confusión.

## 2026-06-03 — Migración X0: eliminación de versiones obsoletas del optimizador

**Decisión:** en `X0_data_supports.py` se conservó solo `nuevo_optimizador_2`. Se eliminaron `buscar_soportes_optimos` v1–v5, `nuevo_optimizador_0/1`, `obtener_df_extremos` V1, y funciones de OC/SL (pertenecen a X1).
**Razón:** el notebook acumuló versiones históricas del algoritmo. Solo V2 del optimizador se llamaba en la ejecución real.
**Parámetro `prueba260417`:** era un flag siempre `True` → se eliminó y se dejó solo el branch activo (ajuste cuadrático + fallback idxmax).

## 2026-06-03 — Data/ y conjuntosN2/ fuera de git (revertida 2026-06-07, ver más abajo)

**Decisión:** los archivos generados (CSVs de precios y pickles de soportes) no se trackean en git.
**Razón:** son artefactos de ejecución, se regeneran corriendo X0 en Windows. Incluirlos en git es ruido y pesa.

## 2026-06-07 — Vectorización de `calcular_distancias` por bloques

**Decisión:** reemplazar el doble loop Python (`for i / for j` con `.loc` escalar) por `_vecino_mas_cercano`, que vectoriza con numpy procesando la serie en bloques de filas (`BLOQUE_DISTANCIAS = 2000`).
**Razón:** con `FECHA_INICIAL='2024-01-01'` las series superan 20k velas (BTCUSD ≈ 21k). El loop puro tardaba ~34s por (valor, N); vectorizado toma ~1.8s — mismos resultados byte a byte.
**Descartado:** construir la matriz booleana (n × n) completa de una sola vez — para n≈21k son ~450M elementos, demasiada memoria considerando que corre en paralelo (`ProcessPoolExecutor`) para ~48 pares (valor, N). El procesamiento por bloques acota la memoria a `block_size × n` por iteración.

## 2026-06-07 — Vectorización de `asignar_soporte` con búsqueda binaria

**Decisión:** reemplazar `df['Low'].apply(lambda x: min(soportes, key=...))` por `np.searchsorted` sobre el array ordenado de soportes, comparando solo contra el vecino izquierdo y derecho.
**Razón:** `calcular_FO` (que llama `asignar_soporte`) se invoca miles de veces por iteración del optimizador (hasta N×M ≈ 13.000 con N=130, M=100). El `apply` original es O(n×N) — con n≈40k velas y N=130 son ~5M comparaciones en Python puro por llamada. La búsqueda binaria baja esto a O(n log N), vectorizado en numpy: ~45-178x más rápido (0.26s → 0.0014s por llamada en BTCUSD), mismos resultados byte a byte verificados contra datos reales.
**Nota sobre empates:** en un empate exacto de distancias, el original depende del orden de iteración del `set` de Python (arbitrario, basado en hash) mientras la versión nueva elige el soporte menor. En la práctica esto no ocurre: `conjunto_N` se construye solo con floats continuos (`np.random.uniform`, `np.linspace`, `np.polyfit`) y `ordenes_activas=[]` en el único call site — la probabilidad de un empate exacto en float64 es ≈0.

## 2026-06-07 — Documentación del efecto de cada parámetro del algoritmo en CLAUDE.md

**Decisión:** agregar la sección "Parámetros del algoritmo — efecto de cada uno" (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL) directamente en `CLAUDE.md`, no en un doc aparte de `docs/`.
**Razón:** es contenido de referencia que se necesita consultar en cada sesión de trabajo sobre el algoritmo (tuning, debugging de resultados) — `CLAUDE.md` se carga siempre, un doc en `docs/` requeriría abrirlo a mano.
**Nota:** la descripción de cada parámetro es matemática/direccional (qué pasa al subir o bajar el valor); las decisiones de "cuál es el valor correcto" siguen siendo criterio del usuario, no se proponen valores nuevos.

## 2026-06-07 — Data/ vuelve a trackearse en git (revierte la decisión del 2026-06-03)

**Decisión:** sacar `Data/` del `.gitignore` y trackear los CSVs de precios en git.
**Razón:** `descargar_datos` solo trae las últimas 1000 velas H1 de MT5 (~41 días) y hace merge + `drop_duplicates` con el CSV existente. Si el CSV no existe (ej. checkout nuevo en Windows sin `Data/`), se pierde toda la historia previa a esa ventana — en este caso, ~2 años desde `FECHA_INICIAL=2024-01-01`. Versionar `Data/` en git asegura que esa historia viaje con el repo y no dependa de copiar carpetas a mano entre máquinas.
**Costo aceptado:** ~14MB iniciales (10 activos) que crecerán con cada actualización — el repo va a pesar más con el tiempo.

## 2026-06-07 — `conjuntosN2/` migra de pickle a JSON

**Decisión:** reemplazar `pickle_act` por `json_act` en `X0_data_supports.py` y `X1_trading.py`. Los archivos pasan de `{valor}_{N}_beta.pkl` / `{valor}_{N}.pkl` a `.json`.
**Razón:** `conjunto_N` es solo un `set` de ~50-130 floats (niveles de precio) — formato binario no aporta nada aquí. JSON permite abrir el archivo y revisar los soportes a simple vista, útil para validar resultados de X0 sin cargar Python. La conversión es trivial: `sorted(set)` al guardar, `set(list)` al cargar donde se necesita como set (X0); X1 ya consumía la lista directamente.
**Descartado:** Parquet — formato columnar pensado para datasets tabulares grandes, sobredimensionado para una lista de ~100 floats.
**Nota:** se quitó `*.pkl` de `.gitignore` (quedaba redundante; `conjuntosN2/` ya está ignorado como carpeta y pickle deja de usarse en el proyecto).

## 2026-06-07 — `transversal.py` se renombra a `config.py` y centraliza todos los parámetros

**Decisión:** renombrar `Transversal.py` → `config.py` y mover ahí los parámetros que estaban hardcodeados directamente en `X0_data_supports.py` (rutas, `VALORES`, `FECHA_INICIAL`, `K`, `N_EXP`, `BLOQUE_DISTANCIAS`, `M`, `LAMBDA`, `MAX_ITERS`, `DELTA_INICIAL`, flags `GRAFICAR_*`) y en `X1_trading.py` (rutas, `VALORES`, `A`, `B`, `TS`, `PERDIDA_MAX`, `PRUEBA_TRAILING_STOP`, `LOTAJES`, `UNITS`).
**Razón:** la sesión anterior (ver `docs/records.md`, SECCIÓN 3) había quedado en limitar `config.py` solo a parámetros de X0, pero al retomar el TO DO Mauricio prefirió consolidar todo en un único archivo — más simple y consistente con la convención ya declarada en `CLAUDE.md` ("parámetros clave centralizados").
**Cambios:** `BASE_DIR`/`CARPETA_DATA`/`CARPETA_N2` ahora se calculan solo en `config.py` (X0 y X1 los importan ya resueltos); se quitó el import `from pathlib import Path` de `X1_trading.py` por quedar sin uso. `VALORES` tenía orden distinto entre X0 (`..., TSLA, GOOGL, ...`) y X1 (`..., GOOGL, TSLA, ...`) — se unificó al orden de X0 (el orden no afecta el resultado, solo la secuencia de iteración).
**Nota:** `DELTA_INICIAL` se trasladó tal cual mantenía el código previo, pero sigue sin conectarse a `nuevo_optimizador_2` (la función usa su propio default `delta_inicial=1e-4`, que coincide en valor) — comportamiento preexistente, no se modificó como parte de este cambio.

## 2026-06-07 — Criterio para mergear `dev` → `master` (primera versión estable)

**Decisión:** el merge se hace recién después de validar `dev` corriendo en Windows (X0 + X1 contra MT5 real, sin errores, durante un período de prueba) — no por alcanzar un ítem puntual del TO DO ni por el estado actual del código. La estrategia será un merge commit normal (`git merge dev`), preservando el historial completo de los 8 commits de `dev`.
**Razón:** `dev` reemplazó casi toda la estructura de `master` (migración de notebooks a `.py`, paralelización, vectorización, JSON) — el código se desarrolla en Mac pero corre en Windows con MT5, que no está disponible en Mac. La validación funcional real solo puede hacerse ahí, así que es la condición de entrada más confiable para llamar a esta versión "estable".
**Descartado:** mergear ahora ("ya está lista") o condicionar el merge a resolver otro ítem del TO DO primero (ej. revisión de FO, backtesting) — ninguno de los dos prueba que el pipeline funciona end-to-end en el entorno real de ejecución. Tampoco hacer squash de los commits de `dev`: se prefiere conservar el historial detallado de la migración.

## 2026-06-08 — Simulación intra-vela para X4: diseño y descarte de X1.5 como módulo separado

**Decisión:** la lógica de simulación intra-vela (antes llamada X2_Intravela / X1.5_intravela) no se implementa como script independiente, sino como subrutina embebida en X4_backtester.py.
**Razón:** el único caso de uso es el backtesting — no tiene sentido separarlo. El archivo X2_Intravela original no se reutiliza; solo se rescata la idea de datos por minuto.

**Nuevo directorio:** `Data_minuto/` — CSVs OHLCV M1 por activo, descargados desde MT5 e incrementados igual que `Data/`. Fuera de git (regenerables desde MT5).

**Trigger — cuándo simular intra-vela (en orden de evaluación):**
1. `hay_soporte_en_rango = Low <= max(soportes_activos)` — si el precio no bajó hasta ningún soporte, no abre ninguna orden → sin edge case.
2. `puede_activar_ts = (High - Low) > A / (LOTAJES[valor] * UNITS[valor])` — rango mínimo para que el trailing stop se active dentro de la vela.
3. `puede_activar_perdida_max = (High - Low) > PERDIDA_MAX / (LOTAJES[valor] * UNITS[valor])` — rango mínimo para que la pérdida máxima se active dentro de la vela.
→ Se simula intra-vela si `hay_soporte_en_rango and (puede_activar_ts or puede_activar_perdida_max)`.

**Método de escalado:** tomar 60 registros M1 consecutivos aleatorios de `Data_minuto/` (aunque existan datos reales para esa hora, siempre se toman aleatorios) y aplicar escalado lineal para que el OHLC resultante calce con el de la vela horaria.
**Descartado:** usar los datos M1 reales de esa hora específica — implica alinear timestamps M1 con H1, mayor complejidad, y no aporta validez estadística sobre una muestra aleatoria dado el propósito (simular la forma del movimiento, no reproducirlo exactamente).

## 2026-06-26 — X5 y X6 fusionados en X5_macro_brain.py

**Decisión:** eliminar `X5_model_training.py` y `X6_macro_brain.py` como módulos separados. El módulo unificado se llama `X5_macro_brain.py`.
**Razón:** X5 predecía resultados de trades; X6 usaría esas predicciones para ajustar params de config. Colapsar ambos evita una capa intermedia sin beneficio claro: el modelo puede aprender directamente (X2, X3, config_params, contexto) → retorno esperado, y luego optimizar sobre config_params en inferencia.

**Diseño de X5 — surrogate + optimización:**
- El modelo aprende a predecir retorno dado `(X2, X3, config_params, órdenes abiertas del activo)`.
- En inferencia: se fija el contexto actual (X2+X3) y se buscan los `config_params` que maximizan el retorno predicho (gradient descent o búsqueda discreta).
- **Datos de entrenamiento**: una fila por trade cerrado (OC). Snapshot de features capturado en tres momentos: OE (buy limit colocada), OA (orden abierta/activada), OC (orden cerrada). Y = rentabilidad de la operación + P&L abierto del activo + P&L cerrado del activo en el momento OC.
- **Parámetros que X5 controla**: `n_sizes_ejecucion[v]`, `K`, `N_EXP`, `LAMBDA`, `A`, `B`, `LOTAJES_M[v]` (entero ≥ 1).

**Cambio de config asociado:** `LOTAJES` pasa a ser derivado: `LOTAJES[v] = LOTAJES_M[v] * MIN_LOTAJES[v]`. `MIN_LOTAJES` = mínimos fijos del broker. `LOTAJES_M` = multiplicador por activo que X5 ajusta.

**Descartado:** mantener dos módulos separados (predictor + ajustador) — capa extra sin beneficio si el modelo aprende directamente la relación. También descartado por ahora: RL con X4 como simulador — más potente pero requiere X4 maduro y un simulador fiel; queda como evolución natural si el surrogate no generaliza bien.

## 2026-06-30 — El store de X5 lo generan backtesters dedicados, no X1 live

**Decisión:** X1 con `TIPO_EJECUCION = "est"` no produce ningún output hacia X5. Los datos de entrenamiento de X5 los generan **X5 backtesters dedicados** — uno por activo, independientes entre sí — que simulan la lógica de X1 sobre el historial H1 con el loop explore/exploit y capturan los snapshots OE+OA+OC en `resources/x5/{ACTIVO}_store.csv`.
**Razón:** separar el live trading del proceso de generación de datos permite controlar la exploración (params aleatorios vs. óptimos) sin afectar la operativa real. X1 live con params estáticos genera datos sesgados hacia una sola combinación de parámetros — inútil para entrenar un surrogate model que necesita variedad de `(contexto, params, resultado)`.
**Descartado:** capturar trades en X1 live y usarlos como training data — introduce sesgo de selección severo (todos los trades con los mismos params estáticos) y acopla el ciclo de vida del modelo al de la operativa real.

## 2026-06-30 — `TIPO_EJECUCION` como switch entre parámetros estáticos y dinámicos (X5)

**Decisión:** agregar `TIPO_EJECUCION = "est"` a `config.py` y a cada `config_V*.py` de backtesting. Valor `"est"` = X1/X0/X4 usan parámetros de `config.py`; valor `"din"` = leen `config/active_parameters.json` generado por X5. Con `"din"`, si `model_status[activo] == "untrained"` para un activo concreto, ese activo cae back a `config.py` automáticamente — la transición es independiente por activo dentro de una misma corrida.
**Razón:** X5 se construye en dos fases. Fase 1: X1 sigue con parámetros estáticos mientras X5 acumula datos y se entrena. Fase 2: se activa `"din"` manualmente cuando X5 esté entrenado y validado. El parámetro hace ese switch explícito y reversible sin tocar código.
**Descartado:** activar dinámico por activo de forma automática al cruzar el umbral de trades — opaco y difícil de auditar. El cambio manual de `"est"` → `"din"` deja trazabilidad clara de cuándo se activó el modo dinámico.

## 2026-06-07 — `DELTA_INICIAL` adaptativo entre corridas, presionado vía `LAMBDA_DELTA`

**Decisión:** conectar `DELTA_INICIAL` (hasta ahora sin uso real — ver nota en la decisión "renombra a config.py") a `nuevo_optimizador_2`, y hacerlo adaptativo *entre* corridas sucesivas de cada combo (valor, N): si existe un estado previo en `{valor}_{N}_delta.json`, se usa `delta_actual = LAMBDA_DELTA * delta_previo` (con `LAMBDA_DELTA = 0.9`); si no existe (primera corrida, cold start), se usa `DELTA_INICIAL` de `config.py` como semilla sin presionar. El valor usado en cada corrida se persiste al converger en un archivo de estado separado por combo (`{valor}_{N}_delta.json`, formato `{"delta_inicial": valor}` vía `json.dump`/`json.load` directo — no `json_act`, que asume listas/sets de soportes y aplica `sorted()`).
**Razón:** cuando un combo (valor, N) ya tiene un warm start cargado desde `{valor}_{N}_beta.json` (conjunto de soportes cercano al óptimo), el optimizador parte con menos margen de mejora por recorrer, así que exigir una mejora relativa cada vez más chica (`delta` decreciente) no dispara un costo proporcional en iteraciones — se puede "presionar" la precisión sin pagar el precio que pagaría un cold start. Multiplicar siempre por `LAMBDA_DELTA ∈ (0,1)` garantiza `delta >= 0` por construcción (decae asintóticamente a 0, nunca lo cruza).
**Descartado:** guardar `delta_inicial` junto a `conjunto_N` en el mismo JSON (cambiaba su estructura de lista a dict, obligando a tocar `json_act`, `promover_a_productivo`, `leer_lista_N` y la lectura en X1 — mayor radio de impacto sobre el flujo productivo de trading). También un único archivo de estado consolidado para todos los combos: con `ProcessPoolExecutor` corriendo en paralelo, escrituras concurrentes sobre un solo archivo introducen riesgo de carrera; un archivo por combo lo evita naturalmente, igual que ya hace `{valor}_{N}_beta.json`.
**Nota:** esto deja pendiente el ítem original del TO DO (schedule decreciente *dentro* de una misma corrida, partiendo alto y bajando si nada supera el umbral) — lo implementado es un mecanismo distinto y complementario, a nivel de corridas sucesivas, no de iteraciones dentro de una corrida.

## 2026-07-18 — X5: pipeline de targets, recolección paralela y CLI simplificada

Revisión completa de `X5_macro_brain.py` (ver `docs/plans/x5_opus_review.md`). Cuatro decisiones:

**1. Pipeline de targets completo.**
**Decisión:** X4 (`_construir_fila_oc`/`_construir_fila_periodica`) ahora escribe los 3 targets: `retorno_pct`, `pnl_flotante_activo` (P&L flotante de las OA, calculado en `_contexto_portfolio_x5`) y `pnl_cerrado_activo` (= `est_a['GC']`). X5 alinea `TARGET_CERRADO='pnl_cerrado_activo'`.
**Razón:** antes X4 solo escribía `retorno_pct`; los targets `pnl_flotante`/`pnl_cerrado` no existían en el store → en LightGBM se omitían (0 filas) y en FTT se entrenaban contra `np.zeros` (ruido). Los registros periódicos quedaban inertes (sin su Y `pnl_flotante_activo`).
**Alcance:** el head `flotante` de LightGBM entrena con `('oc','periodico')`; en FTT los 3 heads comparten el tensor de filas `oc` (periódicas para flotante en FTT quedan como TO DO — los heads no pueden usar subconjuntos de filas distintos con un X compartido).

**2. Recolección paralela por activo.**
**Decisión:** `X5 --recolectar` lanza un worker por activo (`ThreadPoolExecutor`), cada uno corre ciclos de `X4 --x5 --activo {activo}` y auto-entrena al cruzar `X5_MIN_TRADES_TRAIN`. X4 aísla los recursos por activo en `resources_{version}_{activo}` (checkpoint/equity), evitando colisión entre procesos.
**Razón:** el diseño anterior corría los activos secuencialmente dentro de un proceso. El usuario quería backtesting paralelo con corrección de params por activo. El store (`{ACTIVO}_store.csv`) ya es por activo; solo faltaba aislar checkpoint/equity de X4.
**Descartado:** paralelizar con `multiprocessing` los entrenamientos — el grueso del trabajo (backtest) ya está en subprocess de X4, así que threads bastan (GIL liberado en subprocess y en rutinas nativas de LGBM/torch).

**3. CLI simplificada (3 modos + casilla).**
**Decisión:** de 5 flags a 3 modos mutuamente excluyentes (`--recolectar`, `--infer`, `--status`) + casilla `--train` (solo con `--infer`). Se eliminó `--vela`.
**Razón:** `--vela` era un alias exacto de `--infer` (su lógica de captura/online nunca se implementó). `--train` era "entrena+infiere" → se vuelve modificador de `--infer`.

**4. Merge en `active_parameters.json`.**
**Decisión:** `_escribir_active_parameters` hace read-modify-write (merge por activo) con escritura atómica (tmp + replace), en vez de overwrite total.
**Razón:** en EXPLOIT paralelo varios procesos llaman `--infer --activo X`; el overwrite borraría los demás activos. Merge + escritura atómica lo evita (carrera residual benigna: peor caso, un ciclo usa baseline).

**Otros:** `config/active_parameters.json` agregado a `.gitignore` (output generado, como `resources/`). Documento LaTeX `docs/plans/x5_documento.tex` (+PDF) que fusiona ambos planes con diagramas TikZ, compilable con tectonic.

## 2026-07-20 — X1/X4: regla de reemplazo de buy limits (lógica replicada, no compartida)

Al reemplazar soportes, la OE más cercana al precio (aún no ejecutada) se cancelaba pero el primer soporte de reemplazo entraba al menos `a` bajo el precio (filtro de distancia), dejando un hueco de cobertura cerca del precio.

**Decisión:** regla aditiva de reemplazo. `limpiar_ordenes_pendientes_no_validas` (X1) / `_paso_A` (X4) retornan el precio más alto entre las OE canceladas; el paso de creación (`crear_ordenes_espera` / `_paso_F`) coloca todo soporte bajo `umbral = (precio + max_saliente)/2`, además del filtro `a`. Tope en el punto medio para no colocar buy limits pegados al precio.

**Decisión (deuda técnica):** la lógica quedó **replicada** en X1 y X4, no extraída a un módulo compartido. El usuario asumía que X4 se colgaba de funciones importadas de X1; no es así — X4 reimplementa `_paso_A`/`_paso_F` y no puede importar X1 porque X1 hace `import MetaTrader5` a nivel de módulo (no disponible en el entorno de backtest).

**Descartado (por ahora):** extraer la lógica pura de buy limits a un módulo común que X1 y X4 importen, desacoplando el `import MetaTrader5` (lazy o inyectado). Es lo correcto a futuro pero toca arquitectura y agrega superficie de riesgo en código live. Costo de la deuda: cualquier cambio a la regla de buy limits debe editarse en dos lugares (X1 y X4) manteniéndolos en paridad, o X5 (vía X4) diverge de la ejecución real.

## 2026-07-23 — X5 --recolectar: soportes se recalculan con los params del ciclo, sin cache

Al revisar por qué `--recolectar` avanzaba tan rápido se detectaron dos desconexiones: (1) `_procesar_valor_N` (X0) calculaba soportes con las globales `K/N_EXP/LAMBDA` importadas de `config.py` producción, de modo que los params que X5 explora por ciclo nunca afectaban el cálculo de soportes; (2) el cache bt (`_bt_warm_start`) se heredaba entre ciclos, arrancando el optimizador ya convergido con soportes de params distintos.

**Decisión:** cada ciclo de X5 re-optimiza los soportes desde cero con sus propios params. `_procesar_valor_N` acepta `params_soporte={K,N_EXP,LAMBDA}` (override de las globales) y `cold_start` (ignora warm start del cache/JSON y el delta adaptado, parte de inicialización inteligente con delta semilla). `_recalcular_soportes`/`_worker_recalcular` (X4) los pasan en modo x5; `ejecutar_backtest` borra el cache bt (`*_bt.json`, `*_bt_delta.json`) al inicio de cada ciclo con reset. El cache bt sigue existiendo solo como canal worker→proceso principal dentro del recálculo del día actual. X0 producción no pasa los args nuevos → comportamiento idéntico.

**Trade-off aceptado:** la recolección es mucho más lenta (cada recálculo diario vuelve a converger desde cold start, ×días ×ciclos), pero los datos del store quedan consistentes: los soportes de cada fila reflejan los params K/N_EXP/LAMBDA que se registran junto a ella.

**Elegido sobre warm start intra-ciclo:** se descartó reusar el soporte del día anterior dentro del mismo ciclo (params constantes, sería correcto y más rápido) porque el usuario pidió explícitamente que todo se recalcule fresco con los params del momento.

**Implicación operativa:** el store `{ACTIVO}_store.csv` generado antes de este fix está contaminado (params de soporte registrados no corresponden a los soportes usados). Recomendado regenerar desde cero antes de entrenar.

## 2026-07-23 — X5 --recolectar: regeneración de params cada N días dentro del backtest (explore/exploit as-of-t)

Antes los params de un ciclo se elegían **una sola vez** (`ejecutar_x5_ciclo`) y todo el run desde `fecha_inicio` a hoy usaba ese set. Eso da poca variedad de tuplas (contexto, params, resultado) por pasada. Se movió la selección de params al **interior del backtest**, acoplada a la cadencia de recálculo de soportes.

**Decisión:** cada `delta_recalculo_soportes` días (default subido de 1 → 5 en config_x5) se regeneran los params y se recalculan los soportes cold-start hasta t con ellos. Por activo, en cada punto:
- **Sin modelo entrenado** → EXPLORE: params aleatorios uniformes dentro de `X5_PARAM_RANGES` (config_x5).
- **Con modelo** → EXPLOIT con prob. `(1 - EXPLORATION_RATE)`: inferencia **as-of-t** (el modelo ve el contexto X2/X3/temporal/portfolio del día simulado, que X4 ya computa por vela), si no EXPLORE. Se mantiene `EXPLORATION_RATE` (30%) aun con modelo para no colapsar el store sobre la propia política del modelo (sesgo de selección; Sugerencia 1 de `x5_plan.md`).

**Elegido sobre alternativas:**
- *Cadencias separadas (recálculo diario, params cada 5 días)* → descartado: los soportes de una fila quedarían calculados con params distintos a los que el store le atribuye (inconsistencia de datos).
- *Recomendación única por ciclo con `X5 --infer`* → descartado: `--infer` usa contexto "now", semánticamente inválido para un tramo simulado en el pasado.

**Implementación:** X5 expone `cargar_modelo_para_activo` (carga el modelo 1 vez por ciclo, fijo durante el ciclo) e `inferir_con_contexto(activo, tipo, bundle, contexto, param_ranges)` (rangos inyectables de config_x5 vía `_RANGES_OVERRIDE`; **sin airbag** en recolección, para que el store capture también las consecuencias de regímenes de caída). `_inferir_params` acepta ahora `contexto` opcional (el path live no cambia: contexto "now" + airbag). X4 arma el contexto con `_contexto_inferencia_x5` y decide en `_seleccionar_params_x5`/`_aplicar_seleccion_x5`, llamado en el cold start y en cada trigger de recálculo. Eliminados `_generar_params_exploit` (shell-out a `--infer`) y `_imprimir_ciclo_x5`.

**Trade-off aceptado:** el EXPLOIT in-loop infiere en cada punto de 5 días (Optuna/gradient ascent × ~150 puntos por pasada). Aceptable porque los ciclos tempranos son 100% EXPLORE (barato) y el EXPLOIT solo entra una vez entrenado. Si escala mal, bajar `X5_N_OPTUNA_TRIALS` para la inferencia in-loop.

## 2026-08-01 — Warm start por combo (valor, N, t*) en X0 y X5 + visibilidad de la búsqueda de soportes

Tres necesidades del modo demo de X5 y del algoritmo de soportes: (1) ver el gráfico de cada búsqueda, (2) saber con qué ventana de precios se buscó, (3) reusar soluciones previas como punto de partida.

**Decisión 1 — warm start por (valor, N, t\*):** si existe una solución del combo `(valor, N)` calculada en un `t* <= t`, se usa como solución inicial del optimizador para resolver `t`. Aplica a X0 (producción: JSON `{VALOR}_{N}.json`, `t*` = mtime; backtesting: cache `{VALOR}_{N}_bt.json`, `t*` = clave más reciente ≤ t) y a X5, donde estaba desactivado.

Esto **revierte parcialmente** la decisión del 2026-07-23 ("soportes se recalculan con los params del ciclo, sin cache"). Para no perder lo que esa decisión protegía, se separaron los dos efectos que estaban fusionados en el flag `cold_start`:
- `warm_start` (nuevo, default `True`) → de dónde sale la **solución inicial**.
- `cold_start` (ahora solo eso) → si se hereda el **delta adaptado** del combo. X5 lo mantiene en `True`: con params nuevos, heredar la presión acumulada dejaría al optimizador satisfecho de entrada y no re-optimizaría.

Así el conjunto N sigue re-convergiendo con los params del tramo (la consistencia store↔soportes se mantiene), pero partiendo de un punto cercano en vez de aleatorio. Medido sobre BTCUSD N=8, 38.730 velas: 15,3s → 6,5s (mismo FO). `ejecutar_backtest` ya no borra `*_bt.json` entre ciclos (sí `*_bt_delta.json`). Reversible con `X5_WARM_START_SOPORTES = False` en `config_x5`.

**Riesgo asumido:** la solución previa se calculó con otros `K/N_EXP/LAMBDA`, así que el punto de partida sesga hacia esa cuenca del óptimo. Se aceptó a cambio del costo: sin warm start, cada tramo (×días ×ciclos ×activos) vuelve a converger desde cero.

**Decisión 2 — gráfico por búsqueda (solo demo):** `graficar_soportes_demo` en X0 guarda un PNG con los precios de `t0 → tf` y los N niveles, separados visualmente por dónde quedó el precio en `tf` (verde = soportes bajo el precio, rojo = resistencias sobre él). `_procesar_valor_N` acepta `ruta_plot` y grafica también en modo bt (antes solo producción). Se gatilla únicamente con el demo activo (`X5_DEMO_PLOTS`) para no pagar matplotlib por recálculo × activo × día en la recolección paralela. Archivos en `resources/x5/demo_plots/{ACTIVO}/{ACTIVO}_c{ciclo}_N{N}_{t}.png`; `x5_demo.abrir_archivo` los abre en el visor del sistema (`X5_DEMO_ABRIR_PLOTS`). Backend matplotlib fijado a `Agg` porque `_procesar_valor_N` corre en workers spawn.

**Decisión 3 — metadata de la búsqueda:** `_procesar_valor_N` pasa de retornar `(duracion, convergio)` a un dict con `t0/tf/n_velas/warm_start_n/warm_start_t/FO/duracion/plot`. X4 lo reporta en cada recálculo (bloque detallado en demo, una línea si no) y X0 lo usa en su resumen final. Motivo: el `t` del backtest no dice con qué ventana de precios se buscó — `t0` viene de `FECHA_INICIAL` (config producción), no de `fecha_inicio` de X4.

## 2026-08-04 — Fix: X5 --recolectar (sin reiniciar) volvía a `fecha_inicio` aunque el activo ya tuviera avance

**Síntoma reportado:** al elegir "no reiniciar" (acumular) en `X5 --recolectar` para un solo activo, cada ciclo igual arrancaba el backtest desde `fecha_inicio` (2024-01-01), como si nunca se hubiera procesado nada.

**Causa:** `ejecutar_x5_ciclo` (`X4_backtester.py`) llamaba `ejecutar_backtest(cfg, reset=True, x5_mode=True, ...)` con `reset` **hardcodeado a `True`**. La pregunta de reinicio de `X5_macro_brain.py` (0/1) solo controlaba si se borraba el store/modelo acumulado antes del loop de ciclos (`_borrar_checkpoints_activo`); nunca llegaba a `ejecutar_backtest`. Por diseño (`docs/plans/x5_plan.md`), cada ciclo debía partir de cero para generar pasadas independientes con params distintos (diversidad de exploración) — pero eso también borraba el progreso de una pasada que se cortó a mitad de camino (proceso interrumpido, Ctrl+C, crash), aunque el usuario quisiera conservarlo.

**Fix:** `ejecutar_backtest` ahora decide el `reset` internamente en `x5_mode`, comparando el checkpoint existente contra el último timestamp disponible en los datos H1:
- Sin checkpoint, o checkpoint ya en `stop_out`, o `ts_ultimo_procesado >= ts_max` (la pasada anterior llegó al final) → pasada nueva desde `fecha_inicio` (mismo comportamiento de siempre, preserva la diversidad entre pasadas completas).
- Checkpoint con `ts_ultimo_procesado < ts_max` (pasada interrumpida a mitad de camino) → retoma desde ahí: mismo capital, soportes, OE/OA y `ts_ultimo_recalculo`.

Efecto lateral aceptado (positivo): si llegan velas H1 nuevas después de que una pasada ya había "terminado" (ts_max creció), la siguiente invocación la retoma y simula las velas nuevas en vez de recalcular todo desde cero.

**Fix relacionado:** `_guardar_checkpoint` no persistía el flag `stop_out` (se seteaba en memoria pero nunca se escribía a disco) — sin esto, una cuenta quemada se habría "retomado" como si tuviera capital sano. Ahora se persiste.

**Alcance:** el cambio vive en `ejecutar_backtest`/`ejecutar_x5_ciclo` (X4_backtester.py), así que aplica por igual a `--recolectar` en paralelo (`_recolectar`) y al recorrido guiado de un activo (`_recolectar_guiado`, oficial o `--demo`) — ambos llaman el mismo subprocess `X4_backtester.py --x5 --activo {activo}`. Modo producción de X4 (`--version` sin `--x5`) no se toca: su `reset` sigue viniendo solo de `--reset`.

## 2026-08-26 — cv(H_n) incluye P_min/P_max del período como anclas de borde

**Síntoma reportado:** si el precio rompe el rango donde vienen operando los soportes (ej. BTC subiendo de una meseta de meses a un nuevo máximo en un día), todos los soportes quedan muy por debajo del precio nuevo. `cv(H_n)` no lo detectaba porque solo mide dispersión entre soportes consecutivos — es ciego a qué tan lejos queda el soporte extremo del precio máximo/mínimo real.

**Decisión:** en `calcular_FO` y `calcular_FO_batch` (`X0_data_supports.py`), `H_n` se calcula ahora sobre `[P_min] + soportes_ordenados + [P_max]` en vez de solo los soportes — agrega 2 gaps de borde (soporte extremo ↔ precio extremo del período). P_min/P_max se derivan de `df_extremos['Low']` (mismo dato que ya recibe cada función), sin agregar parámetros nuevos a las firmas ni tocar los otros call sites de `calcular_FO`.

**Ventana usada — acumulado desde `FECHA_INICIAL`, no rolling:** se evaluó una ventana rodante (ej. últimos 90 días) pero se descartó por dos razones:
1. **Efecto borde:** un p_max rodante puede caer, de un día para otro, solo porque el día que contenía el máximo salió de la ventana — sin que el precio se haya movido. Eso metería ruido en la FO no relacionado a la señal real.
2. **Puede quedar por debajo de un soporte real:** los soportes se generan acotados por el rango histórico completo (`nuevo_optimizador_2`, vía `p_min`/`p_max` ya calculados ahí desde `df_extremos['Low']`). Un p_max rodante más chico que el soporte más alto rompe el supuesto de que las anclas están en el borde — o hay que forzar `max(p_max_ventana, max(soportes))`, que en ese caso anula el gap justo cuando se quiere que reaccione.

Con el acumulado, p_min/p_max son monótonos y por construcción siempre están en el borde (los soportes nunca los superan), así que el problema de arriba no existe. Costo aceptado: un extremo histórico muy viejo (ej. un ATH de hace años) queda anclado en la FO aunque ya no sea relevante al régimen actual — no se resolvió, se prioriza correctitud sobre reactividad.

**Descartado:** término aparte que penalice solo rupturas reales (en vez de extender `cv(H_n)`) — más quirúrgico pero requiere re-tunear `LAMBDA` de cualquier forma y agrega un tercer término a calibrar; se prefirió la extensión mínima de la fórmula existente.

**Validado:** con datos sintéticos, `cv(H_n)` de `calcular_FO` coincide byte a byte con el cálculo manual de las anclas, y `calcular_FO_batch` da la misma FO que `calcular_FO` para el mismo soporte movido (consistencia FO_base ↔ batch, mismo criterio que ya aplicaba `dist_max_global`).

**Aislamiento del demo:** con el cache bt persistiendo entre ciclos, el demo habría sembrado el cache de la recolección real (ambos usaban `bt_{activo}`). `ejecutar_x5_ciclo` ahora sufija los recursos de X4 con `X5_DEMO_SUFFIX` → `bt_{activo}_demo`, en línea con el store y el modelo demo.
