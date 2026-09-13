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
