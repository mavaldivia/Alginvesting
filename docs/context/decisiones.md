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
