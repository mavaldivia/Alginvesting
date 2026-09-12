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
- **Fase 2 — `X5_P2.py`**: análisis ceteris paribus vs. precio sobre la tabla de `X5_P1`, mismo `{valor}`. Revisar primero `scripts/X5_analisis_exploratorio.ipynb` (ya hace un análisis similar, pero sobre el *store* de eventos de X5 actual, no sobre una tabla continua) antes de decidir si se reutiliza esa lógica.
- **Fase 3 — hacia `X5_alternativo.py`**: no empezar todavía. Se define recién después de ver los resultados concretos de `X5_P1` y `X5_P2` — no adelantar arquitectura sin evidencia.

## 7. Fuera de alcance por ahora

- No tocar `X5_macro_brain.py`, `X1_trading.py`, ni `config.py` (`TIPO_EJECUCION`).
- No expandir a otros activos (`ETHUSD`, `TSLA`, `GOOGL`, `NVDA`, `AMZN`) hasta validar el enfoque con BTCUSD.
- No definir la arquitectura de `X5_alternativo.py` (Fase 3) todavía.
