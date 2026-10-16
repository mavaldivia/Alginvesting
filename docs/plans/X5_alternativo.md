# X5_alt — Versión alternativa y simplificada de X5

## 1. Qué es esto y por qué existe

`X5_macro_brain.py` (el X5 actual) funciona, pero se percibe demasiado complejo para seguir iterando con confianza: LightGBM + FT-Transformer + Optuna + ascenso por gradiente + airbag + modo demo narrado, todo acoplado. **X5_alt** es una reconstrucción **paralela**, no un reemplazo: no toca `X5_macro_brain.py`, `X1_trading.py`, ni `config.py` (`TIPO_EJECUCION`). Corre al lado, sin interferir con producción, mientras se valida si el enfoque simplificado es mejor.

La idea es ir de menos a más: primero entender los datos con evidencia (correlaciones, gráficos), después decidir qué relaciones vale la pena modelar, y solo al final pensar en un script central (`X5_alternativo.py`) que tome decisiones. No se escribe ese script todavía.

Este documento usa como contexto (solo lectura, no modificar) [`docs/plans/X5_revision_exhaustiva_cerebro.md`](X5_revision_exhaustiva_cerebro.md).

`X5_alternativo.md`, en cambio, **no es de solo lectura**: es un documento vivo que se edita y actualiza a medida que avanza el trabajo (decisiones que se resuelven, alcance que se ajusta, nuevas fases).

## 2. Principios heredados de la revisión exhaustiva

Resumen de los principios de esa revisión que aplican directamente a X5_alt (ver dicho documento, sección 19, para el detalle completo):

- **Parsimonia**: pocas variables explicativas, elegidas por evidencia, no todas las disponibles.
- **Especialización por parámetro**: cada parámetro configurable (`N`, `A`, `B`, etc.) depende solo de las variables que tengan sentido para él — no un único estado global gigante.
- **Evidencia antes que arquitectura**: no saltar a modelos sofisticados (Markov, MDP, Aprendizaje por Refuerzo) sin haber demostrado antes, con datos, que la relación existe.
- **Confiabilidad antes que sofisticación**: entender bien qué información hay disponible y con qué calidad, antes de construir nada encima.
- **Baseline primero**: cualquier sofisticación debe superar algo simple y estático.

## 3. Alcance v0

- `X5_P1` y `X5_P2` reciben `{valor}` (el activo) como **input**, no hardcodeado — se ejecutan inicialmente con **BTCUSD**.
- Se parte de una **tabla continua en el tiempo** (una fila por vela H1), no de eventos aislados (OE/OA/OC) como hace el store de X5 actual (`resources/x5/BTCUSD_store.csv`). Esa granularidad de evento sirve para entrenar el modelo actual, pero no para responder "¿qué información hay disponible en cada momento y cómo se mueve junto al precio?", que es la pregunta de esta primera fase.
- No se expande a otros activos hasta validar el enfoque con BTCUSD.

## 4. Inventario de fuentes de datos disponibles hoy (BTCUSD)

| Fuente | Ruta | Frecuencia | Estado observado (2026-09-12) |
|---|---|---|---|
| Precio OHLCV (Open, High, Low, Close, Volumen) | `Data/BTCUSD.csv` | H1 | 40.283 filas, rango 2021-10-27 → 2026-06-02. **No viene ordenado por `DateTime`** — hay que hacer sort + dedup antes de usar. Además esta copia en Mac está desactualizada respecto a lo que hay en Windows (el máximo es junio 2026, hoy es septiembre 2026) — aceptable para un análisis exploratorio, pero a tener en cuenta. |
| Fundamentales (histórico) | `resources/x2/x2_history.json` | pensada diaria (guard de 1 corrida/día) | En la práctica **muy escasa**: solo 2 registros para BTCUSD (2026-06-12 y 2026-06-14). El score fundamental quedará casi constante (forward-fill) en la enorme mayoría del horizonte — limitación real, no un bug a corregir en esta fase. |
| Fundamentales (snapshot actual) | `resources/x2/scores.json` | último valor | Sin historia, no sirve para la tabla en el tiempo, solo como referencia del score vigente. |
| Técnicos | `scripts/X3_technical_features.py` (`_calcular_todos_indicadores(df, conjunto_N)`, `compute_snapshot`) | por vela | **No existe** `resources/x3/BTCUSD.csv` persistido (solo hay `ETHUSD.csv`) — X5_P1 debe llamar la función de X3 directamente sobre el histórico completo de precio, no depender de un archivo que no se ha generado para este activo. |
| Soportes / distancia a soporte | `resources/conjuntos_N/` | snapshot de producción | No hay JSON de producción para BTCUSD ahí. Existe cache de corridas previas de recolección en `resources/x5/bt_BTCUSD/conjuntos_N/`, pero reconstruir una serie histórica de soportes es trabajo no trivial. Se deja **fuera de v0** (ver decisión abierta abajo). |
| Trades / eventos ya capturados | `resources/x5/BTCUSD_store.csv` | por evento OE/OA/OC | Útil como referencia de nombres de columnas y como fuente secundaria de validación cruzada, pero no es la tabla continua que se busca construir acá. |

## 5. Decisiones tomadas / abiertas para X5_P1

- **Frecuencia de la tabla maestra: H1** (la nativa del precio). Los fundamentales se pegan con forward-fill (último valor conocido hacia adelante), asumiendo la limitación de escasez ya señalada.
- **Distancia a soportes: fuera de v0.** Se difiere a una iteración posterior porque reconstruir soportes históricos completos es una tarea aparte; no bloquea el primer análisis de precio + técnicos + fundamentales.
- **Fuente de precio: `Data/BTCUSD.csv` tal cual está en Mac**, sin re-sincronizar desde Windows primero — el objetivo es analítico, no de producción; se puede repetir el ejercicio más adelante con datos más frescos si hace falta.
- **Parámetros de configuración (`K`, `N_EXP`, `LAMBDA`, `A`, `B`, `N`, `PERDIDA_MAX`): fuera de v0.** En `config.py` son constantes (no varían en el tiempo), así que no aportan nada a un análisis de correlación temporal salvo que se tomen desde `BTCUSD_store.csv` (donde sí varían por la exploración de X5 actual) — eso mezclaría la lógica de otro sistema y se deja para una fase posterior si se justifica.

## 6. Fases de trabajo y TODOs

El detalle de tareas pendientes vive en [`docs/tracking/todos.md`](../tracking/todos.md), sección **X5_alt** (única fuente de verdad del estado pendiente/hecho — no duplicar acá). El orden de implementación real es por fase, no por el score de prioridad de `todos.md`:

- **Fase 0 — Fundacional**: confirmar las decisiones abiertas de la sección 5 antes de escribir código.
- **Fase 1 — `X5_P1.ipynb`**: recolección y tabulación en el tiempo, parametrizado por `{valor}` (inicialmente `BTCUSD`). Debe completarse antes que la Fase 2.
- **Fase 2 — `X5_P2.ipynb`**: notebook exhaustivo de investigación y análisis exploratorio (no un script de carga simple) sobre la tabla maestra de `X5_P1`, mismo `{valor}`. Especificación completa en [`docs/plans/solicitud_claude_code_X5_P2_notebook_v2.md`](solicitud_claude_code_X5_P2_notebook_v2.md), resumida en la sección 9 de este documento. Revisar primero `scripts/X5_analisis_exploratorio.ipynb` (ya hace un análisis similar, pero sobre el *store* de eventos de X5 actual, no sobre una tabla continua) antes de decidir si se reutiliza esa lógica. Reemplazó en este rol a `X5_P2.py`, eliminado (ver sección 9.11).
- **Fase 3 — hacia `X5_alternativo.py`**: no empezar todavía. Se define recién después de ver los resultados concretos de `X5_P1` y `X5_P2` — no adelantar arquitectura sin evidencia.

## 7. Fuera de alcance por ahora

- No tocar `X5_macro_brain.py`, `X1_trading.py`, ni `config.py` (`TIPO_EJECUCION`).
- No expandir a otros activos (`ETHUSD`, `TSLA`, `GOOGL`, `NVDA`, `AMZN`) hasta validar el enfoque con BTCUSD.
- No definir la arquitectura de `X5_alternativo.py` (Fase 3) todavía.

## 8. Estado de avance

- **Fase 1 (`X5_P1.ipynb`) — pipeline base completo (2026-09-12)**: carga precio, calcula técnicos (X3) sin distancia a soportes, mergea fundamentales (X2) con `merge_asof` backward, ensambla la tabla (37 columnas, 40.283 filas para BTCUSD) y la guarda en `resources/x5_alt/BTCUSD_tabla_maestra.csv`. Ruta agregada a `config.py` como `CARPETA_X5_ALT`.
- **Hallazgo de datos**: con el `Data/BTCUSD.csv` actual en Mac (termina 2026-06-02) y los únicos 2 registros de X2 para BTCUSD (2026-06-12 y 2026-06-14, *posteriores* al fin del precio), `x2_score` queda `NaN` en el 100% de las filas de la tabla — el forward-fill no tiene nada hacia adelante que propagar. No es un bug: es la limitación de escasez de X2 ya señalada en la sección 4, agravada por el desfase de fechas entre ambas fuentes en esta copia de datos. Pendiente el ítem de backlog "reporte de calidad de datos" para cuantificar esto formalmente; se puede repetir el ejercicio con datos más frescos de Windows si hace falta ver `x2_score` variando.
- **Próximo paso**: Fase 2 (`X5_P2.ipynb`, notebook exhaustivo de investigación — ver sección 9) — pendiente en `docs/tracking/todos.md`.

## 9. Especificación de X5_P2 — notebook exhaustivo de investigación

Contexto completo: [`docs/plans/solicitud_claude_code_X5_P2_notebook_v2.md`](solicitud_claude_code_X5_P2_notebook_v2.md). Reemplazó el rol de `X5_P2.py` (solo cargaba la tabla maestra e imprimía dimensiones/rango) — P2 ya es `X5_P2.ipynb`, un notebook exhaustivo de investigación y análisis exploratorio, no un script de carga.

### 9.1. Filosofía y objetivo

- P1 construye la información, P2 la entiende, P3 (futuro) la usa para gobernar/optimizar los parámetros configurables de X5.
- Pregunta rectora: ¿qué información tenemos y cómo se han relacionado históricamente el precio, los técnicos y los fundamentales?
- P2 no optimiza ni decide valores de parámetros (`N`, `A`, `B`, etc.) — eso queda para P3.
- Input: la tabla maestra de X5_P1 (`resources/x5_alt/{valor}_tabla_maestra.csv`), sin recalcular nada que ya resuelva P1. Foco inicial: BTCUSD.

### 9.2. Tres capas explícitas (peso orientativo, no exacto en cantidad de celdas)

1. Descriptiva/histórica (~70-80%) — el core del notebook.
2. Prospectiva/potencial predictivo (~15-20%) — extensión secundaria, separada explícitamente.
3. Implicancias/hipótesis para X5 (~5-10%) — cierre, hipótesis a contrastar en P3, nunca reglas ya decididas.

### 9.3. Documentación obligatoria dentro del notebook

Cada sección/subsección relevante debe abrir con una celda Markdown que explique: qué se analiza, por qué, qué pregunta responde, qué métricas/gráficos usa, cómo interpretarlos, sus limitaciones, y si es descriptivo/prospectivo/hipotético. Agregar celda de interpretación/hallazgos después de análisis importantes. Debe leerse como un documento de investigación reproducible, no bloques de código sin narrativa.

### 9.4. Estructura — Parte I: Descriptivo/histórico (core)

Config y carga → auditoría e inventario de variables (familia Precio/Técnico/Fundamental, cobertura, nulos, frecuencia observada) → **frecuencia efectiva de actualización** (distinguir frecuencia de filas de frecuencia real de nueva información, crítico en fundamentales por forward-fill) → estadística descriptiva → evolución temporal → **relación contemporánea variable↔precio** (scatter, Pearson, Spearman, cuantiles) → variable vs. comportamiento histórico reciente del precio (retornos hacia atrás) → relaciones entre variables/redundancia → no linealidades y umbrales → ceteris paribus histórico (regresión multivariable, controla por otras variables, no implica causalidad) → regímenes (bull/bear/sideways, volatilidad, drawdown) → estabilidad histórica (por año, rolling) → síntesis técnicos / síntesis fundamentales → ranking descriptivo consolidado.

### 9.5. Estructura — Parte II: Prospectivo/potencial predictivo (secundaria, separada)

Retornos futuros por horizonte → radiografía temporal pasado/contemporáneo/futuro (distinguir `X_t↔retorno pasado` de `X_t↔retorno futuro`, detecta variables rezagadas/contemporáneas/adelantadas) → potencial predictivo preliminar → validación temporal preliminar sin leakage (train/test temporal, walk-forward simple). No es un proyecto de forecasting.

### 9.6. Estructura — Parte III: Implicancias/hipótesis para X5 (corta)

Traducir hallazgos robustos en hipótesis explícitas del tipo `parámetro = f(pocas variables)` (ej. `N = f(drawdown)`, `A = f(volatilidad)`) — sin implementarlas como reglas. Cierra con tabla variable explicativa → evidencia → estabilidad → régimen → potencial prospectivo → parámetro X5 candidato → relación hipotética → prioridad de prueba en P3.

### 9.7. Orden obligatorio de relevancia dentro del notebook

Dentro de cada parte, ir de lo más relevante/general a lo más específico/complementario — el orden refleja importancia analítica para X5, no el orden tradicional de un análisis estadístico. La auditoría inicial debe ser breve: el notebook debe llegar rápido al bloque **variable vs. precio** (Nivel 2: gráficos, scatter, Pearson, Spearman, cuantiles, ranking inicial), antes de profundizar en no linealidades/relaciones entre variables/ceteris paribus (Nivel 3), regímenes/estabilidad (Nivel 4) y síntesis (Nivel 5). Solo después de cerrar la Parte I descriptiva comienza la Parte II prospectiva.

### 9.8. Filosofía estadística (aplica a todo el notebook)

No confundir correlación con causalidad; no confundir relación contemporánea con predicción (`Corr(X_t,P_t)` no implica anticipar `P_{t+h}`); no confundir repetición de datos con información nueva (fundamentales con forward-fill); no asumir linealidad ni estabilidad; no sobrecomplicar — favorecer interpretabilidad sobre maximizar una métrica de ML.

### 9.9. Requisitos técnicos

Ejecutar de arriba hacia abajo sin estado oculto; reutilizar `config.py` y rutas existentes; no duplicar lógica de P1; funcionar inicialmente para BTCUSD pero razonablemente preparado para otro `valor`; minimizar dependencias nuevas. Antes de dar por terminado: ejecutar el notebook completo desde cero y confirmar que todas las celdas corren en orden y generan tablas/gráficos correctamente.

### 9.10. Primer To Do obligatorio (arranque) — hecho (2026-09-13)

El primer ítem de implementación era crear `X5_P2.ipynb` y su celda de arranque: declarar `valor` (inicialmente `'BTCUSD'`), construir la ruta del CSV, leer `{valor}_tabla_maestra.csv`, dejarlo cargado como DataFrame — todo el análisis posterior parte de ahí. Completado: `scripts/X5_P2.ipynb` carga `resources/x5_alt/{valor}_tabla_maestra.csv` (40.283 filas x 37 columnas para BTCUSD) y queda como base para las secciones de análisis siguientes.

### 9.11. Qué hacer con `X5_P2.py` — decidido (2026-09-13)

Se eliminó `X5_P2.py`. Su lógica de carga (ruta vía `config.CARPETA_X5_ALT`, `pd.read_csv` con `parse_dates=['DateTime']`, validación de existencia con mensaje claro) se reutilizó tal cual en la primera sección de `X5_P2.ipynb`.

## 10. X5_alt_v2 — evolución paralela de X5_alt (2026-10-10)

### 10.1. Qué es y por qué existe

`X5_P1.ipynb`/`X5_P2.ipynb` (v1, ahora congelados en `scripts/otros_strings/`) construyeron una tabla maestra y dejaron casi todo el análisis descriptivo de P2 pendiente. En paralelo, varias sesiones de conversación redefinieron conceptualmente el enfoque — documentadas íntegramente en [`docs/plans/x5_contexto_conversacion.md`](x5_contexto_conversacion.md), que **es el documento rector**: prevalece sobre cualquier definición de este archivo o de la sección 9 en caso de contradicción.

**X5_alt_v2 es una evolución paralela de X5_alt, no un reemplazo** — mismo criterio de "corre al lado, sin interferir" que X5_alt tiene frente a `X5_macro_brain.py`. v1 (`X5_P1.ipynb`/`X5_P2.ipynb`) queda congelada en `scripts/otros_strings/` como referencia histórica; no se vuelve a tocar.

### 10.2. Qué cambia respecto a v1

- **Análisis siempre por activo**, nunca con drawdown/equity/exposición de cuenta agregada (`x5_contexto_conversacion.md` sección 1).
- **Lista de parámetros Y a explicar** redefinida y documentada con precisión en [`docs/context/pars_configurables.md`](../context/pars_configurables.md): `N`, `A`, `factor_B` (con `B = factor_B * A`, ya no independiente), `K`, `N_EXP`, `LAMBDA`, `LOTAJES_M` (fijo, no prioritario). `PERDIDA_MAX` pausada.
- **Variables de estado del activo** (drawdown propio, volatilidad, ruido, tendencia/régimen, liquidez, fundamentales) como vector `X` candidato, no solo indicadores técnicos crudos — y transformaciones (distancia a SMA en unidades de ATR, etc.) en vez de niveles crudos de medias móviles.
- **Métrica nueva**: coseno entre el vector de precios `Pv` y el vector de una variable `Xv` en el tiempo, `cos(Pv, Xv)`, como medida de alineación direccional complementaria a Pearson/Spearman — más gráficos de series temporales a doble eje (precio a la izquierda, variable a la derecha, centrados).
- **Export estructurado de métricas/KPIs** por variable (pensado para alimentarlo después a una IA y obtener conclusiones del tipo "el drawdown se relaciona con N").
- **Generación de hipótesis parámetro↔variable** como uno de los primeros objetivos de la sección (no solo un puente al cierre, como en v1) — con pre-registro directo desde `x5_contexto_conversacion.md` antes de correr ningún notebook.
- **Convención de nombres**: `X5_Q1`, `X5_Q2`, `X5_Q3` (no `P1`/`P2`), para no confundirlos con v1.
- **Parametrización por `valores` (lista)**: cada notebook `X5_Q*` declara `valores = ['BTCUSD']` al comienzo (default, solo BTC por ahora) en vez del `valor` (string único) de v1 — preparado para operar sobre varios activos a la vez sin reescribir la celda de arranque.
- **Exportar outputs a zip (Windows → Mac)**: los tres notebooks corren en Windows con `Data/`/`resources/x2/`/`resources/x3/` actualizados, no disponibles así en Mac. Cada `X5_Q*.ipynb` cierra con una celda que llama a `exportar_zip(nombre_notebook, archivos)` (`scripts/x5_alt_export.py`, módulo compartido) sobre los archivos que ese notebook generó en `resources/x5_alt/`, para bajar el zip resultante desde Windows y pasárselo a Claude. Implementado en `X5_Q1.ipynb` (Sección 11) — al construir `X5_Q2.ipynb`/`X5_Q3.ipynb` agregar la misma celda final con la lista de archivos propia de cada uno.
- **Gráficos vs. datos — qué entra al zip**: ningún notebook `X5_Q*` commitea gráficos embebidos en el `.ipynb` (quedan fuera del notebook commiteado, solo el código y los `print` de resumen — criterio ya aplicado en `[Q2-2]`/`[Q2-3]`). Si en algún punto hace falta persistir el render de un gráfico, se guarda como archivo `.png` en disco (`plt.savefig`, nunca embebido) para que entre al zip igual que cualquier otro archivo. Lo que **siempre** se persiste, en cambio, son los datos detrás de cada gráfico (métricas, series por decil, etc.) — en un CSV propio dentro de `resources/x5_alt/` (ej. `{valor}_q2_3_metricas.csv`, `{valor}_q2_3_deciles.csv`), para poder re-analizarlos sin re-ejecutar el notebook completo. Cada ítem de Q2/Q3 que calcule métricas debe guardar su propio CSV al cerrar su sección — no dejarlo solo en memoria — para que la celda final de export a zip los recoja.

### 10.3. Los tres notebooks

- **`X5_Q1.ipynb`** — tabla maestra + variables de estado del activo (drawdown, volatilidad, ruido, tendencia/régimen, liquidez, fundamentales), con catálogo de documentación por variable (fuente, significado, unidad, fórmula, granularidad, cobertura, limitaciones).
- **`X5_Q2.ipynb`** — core descriptivo: todo lo ya especificado para P2 en la sección 9 (Pearson, Spearman, cuantiles, no linealidades, regímenes, estabilidad, ceteris paribus, redundancia) **más** coseno `cos(Pv,Xv)`, gráficos a doble eje, y export estructurado de métricas por variable.
- **`X5_Q3.ipynb`** — hipótesis explícitas parámetro↔variable (`N=f(drawdown_activo)`, `A=f(volatilidad)`, `factor_B=f(volatilidad,tendencia)`, y candidatas para `K`/`N_EXP`/`LAMBDA`), tabla final de tuplas (parámetro, variable explicativa) y vista unificada de variables explicativas + precio en el tiempo. No implementa reglas de trading — eso es responsabilidad de una etapa posterior (puente a backtesting/X4).

### 10.4. Estado de avance

- **2026-10-10**: `X5_P1.ipynb`/`X5_P2.ipynb` movidos a `scripts/otros_strings/` (congelados). TODOs de `X5_Q1`/`X5_Q2`/`X5_Q3` registrados en [`docs/tracking/todos.md`](../tracking/todos.md), sección **X5_alt_v2**. `X5_Q1.ipynb` completo (tabla maestra + catálogo + export a zip). `X5_Q2.ipynb` en curso: Q2-1 a Q2-4, Q2-6 a Q2-14 implementados y ejecutados de punta a punta sobre datos reales de BTCUSD (incluye `Q2-13` régimen, `Q2-11` síntesis/ranking consolidado y `Q2-5` export estructurado + zip) — solo queda `Q2-EXEC` (gate de cierre) antes de empezar `X5_Q3.ipynb`.
- **2026-10-12**: `Q2-EXEC` validado con corrida multi-activo (6 activos) — habilita `X5_Q3.ipynb`. `X5_Q3.ipynb` completo: `Q3-1` a `Q3-8` implementados y ejecutados sin errores sobre BTCUSD, cerrando con la tabla final de tuplas (parámetro, variable candidata, evidencia Q2, prioridad de prueba) en `Q3-4` y el gate `Q3-EXEC`. De paso se agregó a `X5_Q3.ipynb` la celda de `exportar_zip` (Sección 9) que le faltaba respecto a la convención de §10.2. `TRANS-1` cerrado (gap de documentación corregido en la Sección 0 de `X5_Q2.ipynb`/`X5_Q3.ipynb`). **Con esto, el TODO de `X5_alt_v2` en `docs/tracking/todos.md` queda sin pendientes** — implementación de los 3 notebooks cerrada; lo que sigue es el puente hacia backtesting (`X4_backtester.py`), fuera del alcance de este notebook (ver `Q3-3`).

El detalle de tareas pendientes vive en `docs/tracking/todos.md`, sección X5_alt_v2 (única fuente de verdad del pendiente — no duplicar acá).

### 10.5. Pre-registro de hipótesis parámetro↔variable (`[PRE-1]`, 2026-10-10)

Síntesis de las hipótesis ya documentadas en [`x5_contexto_conversacion.md`](x5_contexto_conversacion.md) para cada parámetro de [`pars_configurables.md`](../context/pars_configurables.md), previa a correr cualquier notebook `X5_Q*`. Sirve de hipótesis a confirmar/refinar con la evidencia que produzca `X5_Q2.ipynb`; `X5_Q3.ipynb` la retoma en `[Q3-6]`/`[Q3-7]`.

| Parámetro | Hipótesis funcional | Dirección esperada | Variables candidatas principales | Fuente / estado |
|---|---|---|---|---|
| `N` | `N = f(drawdown_activo, volatilidad)` | Drawdown sano + volatilidad baja/normal → `N` alto. Drawdown profundo + volatilidad alta → `N` bajo. | Profundidad/duración del drawdown, tiempo desde máximo, velocidad de caída/recuperación, volatilidad corta/larga, ATR relativo, ruido, tendencia, liquidez, estado fundamental. | Sección 6. Hipótesis más madura — ya es `[PRE-1]`/`[Q3-7]` prioritaria. |
| `A` | `A = f(volatilidad)` | Volatilidad alta → `A` más alto (OE más espaciadas, trailing se activa más tarde). Volatilidad baja → `A` más bajo. | ATR absoluto/relativo, volatilidad realizada, ratio volatilidad corta/larga, ruido, spread, liquidez, fuerza de tendencia, drawdown del activo, velocidad de cambio de volatilidad, incertidumbre fundamental. | Sección 7. Doble rol (filtro de OE vs. activación del trailing) — el efecto neto del drawdown sobre `A` no tiene dirección única; podría requerir separar `A_OE`/`A_TRAILING` (decisión pendiente, sección 21). |
| `factor_B` (con `B = factor_B * A`) | `factor_B = f(volatilidad, tendencia)` | Volatilidad alta → `factor_B` más alto (evita cierre por ruido). Volatilidad baja → `factor_B` más bajo (asegura ganancia más rápido). Tendencia fuerte y persistente → `factor_B` más alto. Mercado lateral/ruidoso → `factor_B` bajo/intermedio (por validar). | Volatilidad (ATR, desviación de retornos), fuerza de tendencia/régimen, ruido. | Sección 8. La relación con mercado lateral queda explícitamente "por comprobar con backtesting", no confirmada. |
| `K` | Candidata, no una función explícita todavía | Mercado estable y niveles persistentes → `K` más alto. Muchos cambios de régimen/rupturas → `K` más bajo. | Persistencia histórica de niveles, frecuencia de retesteo, tasa de rechazo posterior, estabilidad del régimen, cambios de tendencia, simetría de aislamiento previo/posterior. | Sección 12. Conviene estudiarlo como relativamente estable por activo, no necesariamente dinámico vela a vela. |
| `N_EXP` | Candidata, no una función explícita todavía | Mercado estable y repetitivo → `N_EXP` más bajo. Cambio de régimen o volatilidad creciente → `N_EXP` más alto. | Cambio de régimen, ratio volatilidad corta/larga, aceleración de tendencia, variación reciente de máximos/mínimos, pérdida de efectividad de soportes antiguos, estabilidad de relaciones históricas. | Sección 13. Señalado como "buen candidato a depender dinámicamente del estado del activo". |
| `LAMBDA` | Candidata, no una función explícita todavía | Mercado lateral/rango amplio con soportes concentrados → `LAMBDA` más alto. Tendencia fuerte con evidencia naturalmente concentrada → `LAMBDA` más bajo. | Amplitud del rango reciente, densidad de soportes candidatos, concentración alrededor del precio actual, huecos en la cobertura, lateral vs. tendencial, volatilidad relativa, capacidad de reacción histórica por zona. | Sección 14. Debe analizarse junto con `N` (la penalización por dispersión cambia según la cantidad de soportes). Rango de exploración X5 (`0.001`–`0.02`) no cubre el valor productivo (`0.2`) — pendiente de resolver antes de optimizar, fuera de alcance de `[PRE-1]`. |
| `LOTAJES_M` | Sin hipótesis dinámica | — | — | No prioritario: fijo mientras X5 opere siempre a lotaje mínimo (rango degenerado `(1,1)`). |
| `PERDIDA_MAX` | Sin hipótesis dinámica por ahora | — | — | Pausado — en evaluación para moverse a una capa externa de gestión de riesgo (`RIESGO_MAX_PCT * CAPITAL_BASE_ACTIVO`), no como función del estado del activo. |

### 10.6. Fase 2 — funciones dinámicas (2026-10-15)

Con `Q1`/`Q2`/`Q3` cerrados, el siguiente paso (convertir cada hipótesis de la tabla de §10.5 en una función `P_t = f(x_t)` calibrada, no solo una dirección esperada) tiene su propio plan completo: [`docs/plans/plan_x5_alt_v2.md`](plan_x5_alt_v2.md). Resumen: sigmoide acotada por parámetro, calibrada contra un target sintético de diseño (percentil causal, sin backtesting todavía) — la validación económica real queda para `X5_Q5.ipynb`. TODOs en `docs/tracking/todos.md`, secciones `Q4`/`Q5` dentro de `X5_alt_v2`.

Ninguna de estas hipótesis se implementa como regla todavía — quedan a la espera de la evidencia descriptiva de `X5_Q2.ipynb` (principio 9, sección 20: "P2 debe producir evidencia e hipótesis, no reglas prescriptivas definitivas").
