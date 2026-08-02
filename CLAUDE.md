# Alginvesting — Contexto para Claude

## Qué es este proyecto

Sistema de trading algorítmico personal. Identifica soportes y resistencias óptimos en activos financieros (crypto + acciones US) y ejecuta órdenes de compra de forma semi-automática en MetaTrader5 (MT5).

**No es un SaaS ni un producto para terceros.** Es una herramienta personal de inversión.

---

## Flujo de trabajo Mac ↔ Windows

```
Mac (Claude Code)           GitHub              Windows (ejecución)
─────────────────     ───────────────     ──────────────────────────
Desarrollo + refactor  →  git push   →    git pull
CLAUDE.md, docs        ←─────────────     (no tiene Claude)
                                          Ejecutar X0 (datos + soportes)
                                          Ejecutar X1 (trading live)
```

- El código se desarrolla en Mac y se ejecuta en Windows donde está MT5.
- `Alginvesting_base/` es el repo clonado de la versión Windows (solo lectura, referencia histórica).
- `Data/`, `Data_minuto/` y `resources/` están fuera de git (`.gitignore`). Se generan y mantienen íntegramente desde Windows al ejecutar X0/X1. Nunca se commiten desde Mac.

---

## Arquitectura

### Scripts principales (en `scripts/`)

| Archivo | Propósito |
|---|---|
| `X0_data_supports.py` | **Etapa 1**: Descarga/actualiza CSVs de precios vía MT5 + llama X2 (score fundamental) y X3 (features técnicas). **Etapa 2**: Encuentra los N soportes/resistencias óptimos y los guarda en `resources/conjuntos_N/` como JSON. `--opcion 0/1/2` |
| `X1_trading.py` | Loop semi-automático (`while True`): lee soportes, gestiona buy limits en MT5, trailing stop, y cierra posiciones si pérdida > `PERDIDA_MAX`. Con `TIPO_EJECUCION="est"` usa params de `config.py`; con `"din"` lee `config/active_parameters.json` generado por X5 (por activo, con fallback automático si `model_status="untrained"`). En Fase 2, cada OC cerrada alimenta el store de X5. |
| `X2_fundamentals.py` | Score fundamental por activo `[0,1]` (yfinance + CoinGecko + Fear & Greed). Llamado desde X0 vía subprocess; guard de día para no ejecutar más de una vez. Alimenta X5. Output: `resources/x2/`. |
| `X3_technical_features.py` | Features técnicas incrementales por activo (SMA, EMA, RSI, MACD, ATR, Bollinger, momentum, volatilidad, drawdown, tendencia, distancia a soportes). Importado y llamado desde X0 tras cada descarga H1. Output: `resources/x3/{VALOR}.csv`. Alimenta X5. Features de contexto operativo (órdenes, PnL, exposición) son responsabilidad de X1/X4. Plan: `docs/plans/x3_plan.md`. |
| `X5_macro_brain.py` | Surrogate model que predice retorno esperado dado (X2+X3+config_params+portfolio) y optimiza config_params en inferencia. Output: `config/active_parameters.json`. **En Fase 1**: se entrena con datos de X5 backtesters dedicados (por activo). **En Fase 2**: X1 live con `TIPO_EJECUCION="din"` alimenta el store directamente → ciclo de retroalimentación cerrado. `--recolectar --demo` es un recorrido guiado interactivo de UN activo (lo pregunta al inicio): corre los ciclos secuencialmente sobre store/modelo/backtest demo aislados (`_demo`) y explica cada suceso nuevo (IDs D01–D10) pausando la primera vez, vía el módulo compartido `scripts/x5_demo.py`; reanudable por activo. Cada recálculo de soportes reporta `t` del backtest, el rango de precios usado (`t0 → tf`) y el warm start, y guarda/abre el gráfico de esa búsqueda en `resources/x5/demo_plots/`. Plan: `docs/plans/x5_plan.md`. |
| `config.py` | Parámetros centralizados: rutas, `VALORES`, `n_sizes`, `n_sizes_ejecucion`, configuración de X0 (algoritmo) y X1 (trading). `TIPO_EJECUCION = "est" \| "din"` controla si X1/X0/X4 usan params estáticos o los recomendados por X5. |

### Directorios de datos

| Carpeta | Contenido |
|---|---|
| `Data/` | CSVs OHLCV H1 por activo (BTCUSD, ETHUSD, TSLA, GOOGL, NVDA, AMZN) — actualizados por X0, fuera de git |
| `Data_minuto/` | CSVs OHLCV M1 por activo — usados por X4 para simulación intra-vela; se alimentan incrementalmente igual que `Data/`. Fuera de git (regenerables). |
| `resources/conjuntos_N/` | JSONs por activo — `{VALOR}_{N}.json` (soportes producción, leído por X1), `{VALOR}_{N}_delta.json` (delta adaptativo producción), `{VALOR}_{N}_bt.json` (cache bt: `{datetime: [soportes], ...}`), `{VALOR}_{N}_bt_delta.json` (delta adaptativo bt) — generados, fuera de git |
| `resources/x0/` | `logs/` (JSONs de convergencia por combo) y `plots/` (FO, Soportes) — generados en Windows, fuera de git |
| `resources/x2/` | Scores fundamentales (`scores.json`), historial (`x2_history.json`), guard de día (`x2_last_run.json`) — generados en Windows, fuera de git |
| `resources/x3/` | Features técnicas por activo (`{VALOR}.csv`) — generados, fuera de git |
| `resources/x5/` | Store de trades por activo (`{ACTIVO}_store.csv`) + modelos entrenados (`models/{ACTIVO}_lgbm.pkl`, `models/{ACTIVO}_ftt.pt`) + `demo_plots/{ACTIVO}/` (gráficos de cada búsqueda de soportes del modo demo) — generados, fuera de git |
| `config/` | `active_parameters.json` — escrito por X5, leído por X1/X0 cuando `TIPO_EJECUCION="din"` |

---

## Conceptos clave del dominio

- **N (n_sizes)**: Cantidad de soportes a mantener activos por activo. Actualmente 250 para todos los activos.
- **M**: Número de precios candidatos evaluados por soporte en cada paso del optimizador (linspace equidistante entre soportes vecinos). Controla la granularidad de la búsqueda local — mayor M, barrido más fino pero más evaluaciones de FO por iteración.
- **Conjunto N**: Los N soportes óptimos elegidos por el algoritmo de optimización.
- **OE / OA / OC**: OE = Orden en Espera (buy limit colocada en un soporte, esperando que el precio baje hasta ella) / OA = Orden Abierta (posición activa; la OE fue ejecutada) / OC = Orden Cerrada (posición que ya cerró por trailing stop, PERDIDA_MAX o stop loss).
- **Trailing Stop**: SL que sigue el precio hacia arriba para proteger ganancias.
- **Beta**: Riesgo por operación como % de cuenta.
- **T**: Ventana de días históricos usada para calcular soportes (default: 60).
- **lambda_ponderador**: Ponderador en la función objetivo que balancea calidad de soportes vs. dispersión entre ellos.

---

## Algoritmo de búsqueda de soportes (X0)

### Paso 1 — `calcular_distancias`
Para cada vela `i`, busca la vela más cercana a la izquierda y derecha cuyo rango `[Low, High]` *contenga* el `Low` (o `High`) de la vela `i`. La distancia temporal entre ambas velas queda en `Low_left / Low_right / High_left / High_right`. Velas con distancias grandes en ambas direcciones son extremos aislados, candidatos naturales a soporte/resistencia.

### Paso 2 — Scoring por vela (`obtener_df_extremos`)
- `y` (aislamiento): `Low_left + High_left + K * (Low_right + High_right)`
- `w` (recencia): `t^N_EXP`, donde `t ∈ [0,1]` normalizado; velas recientes pesan más.
- `v` (volumen): `Tick_Volume / Tick_Volume.max()`, normalizado a `[0,1]`; proxy de actividad/participación en ese nivel de precio (`Real_Volume` viene vacío en los CSV de MT5, así que se usa `Tick_Volume`).
- `f` (fuerza del rechazo): `1 - |Close - Open| / (High - Low)`, en `[0,1]`; proporción del rango de la vela que fue "mecha" en vez de cuerpo — una vela con cuerpo chico y rango grande indica que el precio visitó el extremo y fue rechazado con fuerza, señal de un nivel más respetado. Direccional-agnóstico (no distingue rechazo al alza/baja), consistente con cómo `y` ya combina aislamiento de `Low` y `High` en una sola señal.

### Paso 3 — Función objetivo (`calcular_FO`)
Se asigna cada vela al soporte más cercano del conjunto N. Luego:
- `h_dist = 1 - dist²/dist_max` (proximidad normalizada al soporte asignado)
- `z = producto de los factores activos en `parametros_soportes` (config.py)`: por defecto `y * w * h_dist * v * f`. El diccionario permite activar/desactivar cada uno para experimentar con el scoring sin tocar el código.
- `FO = mean(z) - LAMBDA * cv(H_n)`
  - `mean(z)`: calidad promedio de asignación (combinación de los factores activos: aislamiento, recencia, proximidad, volumen, fuerza del rechazo)
  - `cv(H_n)`: coeficiente de variación de las distancias entre soportes consecutivos — penaliza que los N soportes se concentren en una zona del rango

### Paso 4 — Optimizador de búsqueda local (`nuevo_optimizador_2`)
En cada iteración, para cada soporte `i` del conjunto N:
1. Genera M precios candidatos equidistantes (linspace) entre los soportes vecinos `i-1` e `i+1`.
2. Evalúa la FO para cada candidato.
3. Si la curva FO(candidato) tiene forma de U invertida → ajuste cuadrático para hallar el máximo analítico exacto.
4. Si no → toma el candidato con mayor FO.
5. Acepta el cambio solo si la mejora relativa supera `DELTA_INICIAL`.

Si ningún soporte mejora en la vuelta actual → expande a todos los soportes y reintenta. Si aún no hay mejora → convergencia.

Versión activa: `nuevo_optimizador_2`.

### Warm start — solución inicial por combo (valor, N, t*)

Buscar los N soportes en `t` nunca parte de cero si el combo `(valor, N)` ya se resolvió en un `t* <= t`: esa solución es el punto de partida del optimizador. Aplica a X0 y X5:

| Modo | Fuente de la solución previa | `t*` |
|---|---|---|
| X0 producción | `resources/conjuntos_N/{VALOR}_{N}.json` | mtime del JSON |
| X0/X4 backtesting | `{VALOR}_{N}_bt.json` (cache indexado por datetime) | clave más reciente ≤ `t` |
| X5 (`X4 --x5`) | mismo cache bt, aislado por activo en `resources/x5/bt_{ACTIVO}/` | ídem |

`_procesar_valor_N` separa dos cosas que suenan parecidas:
- **`warm_start`** (default `True`): de dónde sale la solución inicial. `False` → puntos aleatorios.
- **`cold_start`**: si se hereda el `delta_inicial` adaptado del combo o se parte del semilla. X5 lo activa porque cada tramo cambia `K/N_EXP/LAMBDA`: heredar la presión acumulada dejaría al optimizador convergido de entrada sobre una FO que ya no es la misma.

En X5 se desactiva con `X5_WARM_START_SOPORTES = False` (`config_x5`), a costa de re-converger desde cero en cada tramo.

---

## Parámetros del algoritmo — efecto de cada uno

Definidos en `scripts/config.py:42-55`. Valores listados = los usados en producción (no los defaults de las funciones, que pueden diferir).

### N — cantidad de soportes (`config.py`: 250 para todos los activos)
- **↑ N**: más cobertura del rango de precios y entradas más finas, pero capital más fragmentado por posición y mayor costo computacional (`calcular_FO` se llama del orden de N×M veces por iteración del optimizador).
- **↓ N**: posiciones más concentradas (mayor peso por entrada), optimización más rápida, cobertura más gruesa del rango.

### K = 1 — peso del aislamiento futuro vs. pasado en `y = Low_left + High_left + K*(Low_right + High_right)`
- **K = 1** (actual): el aislamiento hacia atrás (pasado) y hacia adelante (futuro respecto a la vela, no al presente) pesan igual.
- **↑ K**: prioriza velas cuyo nivel permaneció "intacto" mucho tiempo después de formarse — favorece niveles ya validados por el tiempo transcurrido.
- **↓ K**: prioriza el aislamiento previo a la formación de la vela — favorece el contexto que la originó por sobre su validación posterior.

### N_EXP = 1.3 — exponente de recencia en `w = t^N_EXP`, con `t ∈ [0,1]`
- **N_EXP = 1.3** (actual, convexo): los pesos crecen más que proporcionalmente con `t` — las velas recientes dominan la FO, las antiguas casi no influyen.
- **↑ N_EXP**: acentúa esa concentración en lo reciente — más reactivo a cambios de régimen, menos memoria del historial.
- **↓ N_EXP** (hacia 1, o cóncavo si <1): reparte el peso de forma más pareja entre todo el historial — más estable, menos sensible a movimientos recientes.

### M = 30 — candidatos evaluados por soporte en cada paso del optimizador
Genera M precios equidistantes (`linspace`) entre los soportes vecinos y evalúa la FO en cada uno.
- **↑ M**: barrido más fino entre soportes vecinos → más probabilidad de hallar el óptimo local exacto (o una buena base para el ajuste cuadrático), pero cada paso cuesta M evaluaciones de `calcular_FO` adicionales.
- **↓ M**: pasos más rápidos, pero candidatos más espaciados → más riesgo de saltarse el máximo real entre dos soportes vecinos.

### LAMBDA = 1/500 — penalización por dispersión desigual: `FO = mean(z) - LAMBDA * cv(H_n)`
- **↑ LAMBDA**: castiga con más fuerza que los soportes se amontonen en una zona del rango — empuja el conjunto N hacia una distribución más pareja en precio, aunque sacrifique algo de `mean(z)` (calidad de asignación).
- **↓ LAMBDA**: la FO se guía casi solo por `mean(z)` — permite que los soportes se concentren donde hay más "evidencia" (velas aisladas y recientes), aunque dejen huecos grandes en otras zonas del rango.

### DELTA_INICIAL = 1e-4 — mejora relativa mínima para aceptar un cambio: `(FO_iter - FO_base)/FO_base > DELTA_INICIAL`
- **↑ DELTA_INICIAL**: exige mejoras más significativas para mover un soporte → converge más rápido (menos iteraciones), pero puede detenerse en un óptimo más alejado del ideal.
- **↓ DELTA_INICIAL**: acepta mejoras más marginales → resultado más fino, pero más iteraciones y más riesgo de aceptar cambios por ruido numérico.

---

## Activos operados

```python
valores = ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']
```

---

## Entorno

- Conda: `revenAI` (Python 3.11)
- Librerías clave: `MetaTrader5`, `yfinance`, `pandas`, `numpy`, `matplotlib`, `mplfinance`
- En Windows: requiere MT5 instalado y cuenta de broker configurada
- En Mac: desarrollo solo (MT5 no disponible en macOS)

---

## Convenciones de este proyecto

- `snake_case` para variables y funciones. `PascalCase` para clases.
- Archivos `.py` en producción. `.ipynb` solo para exploración visual de nuevos módulos.
- Parámetros clave centralizados en `config.py`.
- Archivos en `resources/conjuntos_N/`: `{VALOR}_{N}.json` es el único archivo de soportes (X0 escribe, X1 lee).
- Sin hardcodear rutas fuera de `config.py`.
- `docs/context/decisiones.md` registra decisiones técnicas relevantes.
- **Siglas técnicas**: siempre escribir el concepto completo primero y la sigla entre paréntesis después. Ej: Aprendizaje por Refuerzo (RL), Gradient Boosting (GB), Red Neuronal (NN). Nunca usar solo la sigla sin haberla definido antes en el mismo documento.

---

## TO DO

Ver [`docs/tracking/todos.md`](docs/tracking/todos.md).

## Referencia base

`Alginvesting_base/` contiene la versión anterior (Windows, notebooks). Solo lectura. No modificar.

---

## Cambios recientes

Ver [`docs/tracking/records.md`](docs/tracking/records.md). Si solo se necesita contexto de los últimos cambios, leer las 3 últimas secciones (están al final del archivo, usa `Read` con `offset` cercano al total de líneas).

