# X5 — X5_macro_brain.py: Plan de implementación

> Fusiona los roles originales de X5 y X5 (ver `docs/context/decisiones.md` 2026-06-26).
> Estado: diseño en curso — pendiente de implementación.

---

## Qué hace X5

Ajusta dinámicamente los parámetros de config que usan X0 y X1, basándose en el contexto de mercado actual (X2 + X3). El objetivo es que el sistema se adapte a cambios de régimen de mercado (ej. caída fuerte de BTC → bajar N y lotaje) sin intervención manual.

**Enfoque: surrogate model + optimización en inferencia**

1. Se entrena un modelo que predice el retorno esperado de una operación dado:
   - El contexto de mercado al momento de abrir la operación (X2 + X3)
   - Los parámetros de config activos en ese momento
   - El estado del portafolio en ese activo (órdenes abiertas, exposición)

2. En inferencia: con el contexto de mercado actual fijo, se busca el set de config_params que maximiza el retorno predicho → ese set se escribe en `config/active_parameters.json`.

---

## Parámetros que X5 controla

| Parámetro | Tipo | Granularidad | Rango orientativo |
|---|---|---|---|
| `n_sizes_ejecucion[v]` | int | por activo | [50, 200] |
| `K` | float | global | [0.5, 2.0] |
| `N_EXP` | float | global | [0.5, 3.0] |
| `LAMBDA` | float | global | [1/1000, 1/50] |
| `A` | float | global | [2, 20] |
| `B` | float | global | [0.5, 5] |
| `LOTAJES_M[v]` | int ≥ 1 | por activo | [1, 5] |

`LOTAJES_M[v]` es el multiplicador sobre `MIN_LOTAJES[v]` (mínimo fijo del broker). El lote efectivo es `LOTAJES[v] = LOTAJES_M[v] * MIN_LOTAJES[v]`.

---

## Backtesting como generador de datos

### Ejecución independiente por activo

El backtesting corre por activo de forma completamente independiente. Cada activo tiene su propia instancia del proceso, con su propio set de parámetros. La cuenta de trading es compartida pero, para efectos del entrenamiento, se asume con capital suficiente para no imponer restricciones — los registros monetarios se capturan como **deltas** (variaciones de P&L), no como valores absolutos de cuenta.

Parámetros que pueden estimarse/entrenarse por separado para cada activo `v`:

```
n_sizes_ejecucion[v], K, N_EXP, LAMBDA, A, B, LOTAJES_M[v]
```

### Loop del backtesting

El proceso corre como un loop continuo sobre la historia disponible:

```
día 0 ──────────────────────────────────── día actual
  │                                              │
  └── ejecuta lógica X1 (simulada) por vela ────┘
        ↓ registra parámetros + deltas P&L
        ↓ actualiza parámetros según lo aprendido
        ↓ al llegar al final → vuelve a empezar
              (con los parámetros del final del ciclo anterior)
```

En cada vuelta el proceso:
1. Recorre las velas H1 desde `FECHA_INICIAL` hasta el día actual
2. Simula la lógica de X1 (colocación de buy limits, apertura/cierre de posiciones, trailing stop)
3. Registra en cada trade cerrado: el contexto de mercado (X2+X3), los parámetros activos, y los **deltas de P&L** (orden cerrada + posiciones aún abiertas)
4. Al terminar el recorrido, actualiza los parámetros y reinicia desde el día 0 con el set actualizado

**Acumulación de datos**: el store acumula todas las vueltas sin truncar. Los registros de ciclos con params peores son igualmente valiosos — más variedad de (contexto, params, resultado) = más relaciones causa-efecto que B puede aprender.

### Deltas registrados (en vez de P&L absoluto)

Para aislar la señal del ruido de capital:
- `delta_pnl_cerrado`: P&L de la orden que cierra en ese momento (USD)
- `delta_pnl_abierto_activo`: suma del P&L flotante de posiciones abiertas del activo al momento del cierre
- `retorno_pct`: `delta_pnl_cerrado / (precio_entrada * lote)` — normalizado al tamaño de la posición

Estos deltas son la variable objetivo que el modelo (X6) aprenderá a predecir como función del contexto y los parámetros.

---

## Store de trades — dataset de entrenamiento

### Qué es

Una fila por trade cerrado (OC). Captura el contexto en tres momentos del ciclo de vida de la orden:

```
OE (buy limit colocada) → OA (orden abierta) → OC (orden cerrada)
```

Solo cuando OC ocurre se registra la fila completa.

### Columnas (draft — sujeto a refinamiento)

**Identificadores**
- `activo`, `ticket`, `timestamp_oe`, `timestamp_oa`, `timestamp_oc`

**Precio y resultado**
- `precio_entrada`, `precio_salida`, `pnl_usd`, `retorno_pct`
- `pnl_abierto_activo_oc`: P&L de posiciones aún abiertas del mismo activo al cerrar esta orden
- `pnl_cerrado_activo_oc`: P&L acumulado de órdenes ya cerradas del activo en la sesión

**Config activa al momento de OE**
- `n_ejecucion`, `K`, `N_EXP`, `LAMBDA`, `A`, `B`, `LOTAJES_M`

**Features de X2 al momento de OE** (snapshot del score fundamental)
- `x2_score`, `x2_tendencia` + scores componentes según activo (stock vs crypto)

**Features de X2 al momento de OC**
- ídem, con sufijo `_oc`

**Features de X3 al momento de OE** (snapshot técnicas)
- `sma_20`, `sma_50`, `ema_12`, `ema_26`, `rsi_14`, `macd`, `macd_signal`
- `atr_14`, `atr_pct`, `bb_width`, `bb_pos`, `roc_3`, `roc_5`, `roc_10`, `roc_20`
- `vol_24h`, `vol_168h`, `vol_spike_ratio`, `drawdown_20`, `drawdown_50`
- `trend_slope_20`, `trend_slope_50`, `dist_nearest_support`, `dist_floor_support`, `density_2pct`

**Features de X3 al momento de OC**
- ídem, con sufijo `_oc`

**Contexto operativo al momento de OE**
- `n_ordenes_abiertas_activo`: cuántas OA hay en ese activo al crear la OE
- `n_ordenes_espera_activo`: cuántas OE hay en ese activo
- `exposicion_usd_activo`: exposición total en USD de posiciones abiertas del activo

### Output en disco

`resources/x6/{ACTIVO}_store.csv` — un CSV por activo, con append al cerrar cada OC.

---

## Ciclo A↔B — frecuencia de consulta y reentrenamiento

```
cada vela H1 (A → B):
  contexto = X2_snapshot + X3_snapshot de la vela actual
  params_activos = B.inferir(contexto)        ← barato: MLP pequeño, ms
  A aplica esos params en la vela siguiente

cada N trades cerrados (A → B):
  B.reentrenar(store_acumulado_completo)      ← costoso: batch offline
  (N configurable; sugerencia inicial: 50–100 trades)
```

El re-entrenamiento de B y la inferencia son frecuencias independientes. A siempre usa la versión más reciente de B disponible. Si B no está entrenado aún (primeras vueltas), A usa los params iniciales de `config.py`.

### Airbag — capa de seguridad dura

Independiente de lo que B recomiende, si en las últimas 4 velas H1 el precio cayó más de un umbral configurable (sugerencia: 8% para crypto, 5% para acciones):

```python
if drawdown_4_velas < -AIRBAG_THRESHOLD[v]:
    params_activos['LOTAJES_M'] = 1           # mínimo lote
    params_activos['n_sizes_ejecucion'] = N_MINIMO[v]  # N mínimo
    # no abrir nuevas OE hasta que drawdown_4_velas > -AIRBAG_THRESHOLD[v] / 2
```

El airbag es una regla explícita, no aprendida. Es el último recurso si B no reaccionó a tiempo. La idea es que, con suficientes datos de crashes, B aprenda a recomendar params conservadores antes de que el airbag se active — el airbag existe pero no debería ser el mecanismo principal.

`AIRBAG_THRESHOLD` y `N_MINIMO` van en `config.py`, configurables por activo.

---

## Variables objetivo (Y)

El modelo predice las tres métricas; la función objetivo que se maximiza en inferencia es configurable. Propuesta inicial: `retorno_pct` de la operación individual (más limpio para que el modelo aprenda la señal de entrada).

| Variable | Descripción |
|---|---|
| `retorno_pct` | Retorno % de la operación cerrada |
| `pnl_abierto_activo_oc` | P&L de posiciones aún abiertas del activo al cerrar esta OC |
| `pnl_cerrado_activo_oc` | P&L acumulado cerrado del activo en la sesión |

---

## Arquitectura del modelo (opciones)

### Opción A — Gradient Boosting (XGBoost / LightGBM)
- Interpreta bien features tabulares heterogéneas (mix de scores, precios, conteos)
- No requiere normalización estricta
- Más fácil de depurar e interpretar
- Recomendado para la primera versión

### Opción B — Red neuronal (MLP o LSTM)
- Puede capturar interacciones no lineales más complejas
- Mejor candidato si se quiere pasar a RL más adelante
- Requiere más datos para generalizar

**Decisión pendiente**: evaluar con los primeros datos reales cuál generaliza mejor (cross-val temporal, no aleatoria).

---

## Inferencia — cómo X5 elige los params

Con el contexto de mercado actual fijo (X2+X3 de la última ejecución):

1. Definir el espacio de búsqueda de cada param (rangos orientativos en la tabla de arriba)
2. Evaluar el retorno predicho para combinaciones del espacio (grid search o optimización)
3. Elegir el set de params con mayor retorno predicho
4. Validar constraints: `LOTAJES_M[v]` entero ≥ 1, `n_sizes_ejecucion[v]` dentro del rango del activo
5. Escribir en `config/active_parameters.json`

---

## Frecuencia de ejecución

Pendiente de decisión (ver TO DO). Opciones:
- **Diaria**: simple, batch. Desconectada del estado del portafolio en tiempo real.
- **Por evento**: al cerrar cada OC, re-evaluar si los params óptimos cambiaron. Más reactivo.
- **Antes de cada corrida de X0**: natural — X0 usa los params de config para calcular soportes.

---

## Dependencias

| Módulo | Rol |
|---|---|
| X1 | Genera el store de trades (captura OE+OA+OC y escribe en `resources/x6/`) |
| X2 | Provee features fundamentales (snapshot al momento de OE y OC) |
| X3 | Provee features técnicas (snapshot al momento de OE y OC) |
| config.py | Lee y escribe `active_parameters.json`; `MIN_LOTAJES` y `LOTAJES_M` definidos aquí |

---

## Decisiones pendientes

- [ ] Schema exacto de `config/active_parameters.json`
- [ ] Frecuencia de ejecución
- [ ] Variable objetivo principal para optimizar en inferencia (`retorno_pct` vs portfolio P&L)
- [ ] Arquitectura del modelo (Gradient Boosting vs NN) — decidir con datos reales
- [ ] Mínimo de filas en el store para que el modelo sea útil (estimación: ≥500 trades cerrados)
- [ ] Estrategia de actualización del modelo: ¿reentrenar completo periódicamente, o fine-tune incremental?

---

## Sugerencias y definiciones

### 1 — El problema contrafactual (sesgo de selección en el store)

El store acumula `(contexto, params, retorno)` observacional: los params nunca son aleatorios, siempre son los que el sistema considera "mejores" en esa vuelta del loop. El modelo aprenderá correlaciones espurias del tipo _"K=1 coincidió con mercado alcista → K=1 es bueno"_, sin saber si el resultado se debió al param o al contexto.

**Mitigación recomendada — exploración explícita en el loop de backtesting:**

En un porcentaje configurable de vueltas (sugerencia inicial: 20–30 %), samplear los params aleatoriamente dentro de sus rangos válidos en vez de usar el set "óptimo" conocido. Esto genera registros con variedad real de `(params, contexto, resultado)` que el modelo necesita para aprender relaciones causales.

```python
# en cada vuelta del loop de backtesting
if random.random() < EXPLORATION_RATE:
    params = samplear_params_aleatorios()   # uniform dentro de rangos
else:
    params = B.inferir(contexto_actual)     # explotación
```

`EXPLORATION_RATE` va en `config.py`. La exploración no es una pérdida — los registros con params subóptimos son igualmente valiosos para que el modelo aprenda qué _no_ funciona en cada régimen.

Técnica alternativa más avanzada si el dataset crece: **Inverse Propensity Weighting (IPW)** — ponderar cada fila del store por la inversa de la probabilidad de que esos params hayan sido seleccionados, para deshacer el sesgo de selección en el entrenamiento.

---

### 2 — Arquitecturas de modelo: comparativa para este problema

El problema es **regresión tabular heterogénea**: ~100 features de distintas escalas y tipos (scores normalizados, precios, conteos, parámetros de config), target continuo por fila/trade. No es secuencia pura — X3 ya captura el estado temporal.

| Arquitectura | Fit | Ventaja clave | Contra |
|---|---|---|---|
| **LightGBM** | Muy alto (<50k filas) | Robusto, interpretable, rápido de iterar | No diferenciable → inferencia por grid/Optuna |
| **FT-Transformer** (Feature Tokenizer + Transformer) | Alto (>5k filas) | Attention sobre features; captura interacciones `params × contexto` que MLP no ve | Requiere más datos para generalizar |
| **MLP estándar** | Medio | Simple, diferenciable | Interacciones implícitas; satura pronto |
| **TFT** (Temporal Fusion Transformer) | Bajo para este diseño | Potente para series multivariadas con horizonte múltiple | Diseñado para forecasting, no por-trade; overhead alto |
| **LSTM/GRU sobre X3** | Bajo | Capta trayectoria temporal de features técnicas | X3 ya codifica ese estado; duplica información |

**Secuencia recomendada:**
1. **V1**: LightGBM — el baseline más robusto para datasets pequeños (<50k filas).
2. **V2**: FT-Transformer — si el store supera ~5k trades y LightGBM plateó.

**Argumento para priorizar NN en inferencia**: con un modelo diferenciable (MLP / FT-Transformer), la búsqueda de params óptimos puede hacerse por **gradient ascent** sobre los inputs de params con el contexto fijo. Esto es mucho más barato que grid search u Optuna, especialmente si la inferencia corre cada vela H1. Si se elige LightGBM, la estrategia de inferencia debe ser explícitamente Optuna con el espacio acotado.

---

### 3 — Estrategia de inferencia según tipo de modelo

Debe documentarse explícitamente antes de implementar, porque condiciona la elección de arquitectura.

**Si modelo = GBDT (LightGBM / XGBoost):**
- Grid search discreto sobre params enteros (`n_sizes_ejecucion`, `LOTAJES_M`) + Optuna para params continuos (`K`, `N_EXP`, `LAMBDA`, `A`, `B`)
- El contexto se fija como constante; Optuna optimiza los params como variables de decisión

**Si modelo = NN diferenciable (MLP / FT-Transformer):**
- Fijar el vector de contexto (X2+X3 de la última vela)
- Inicializar params aleatoriamente dentro de sus rangos
- Gradient ascent sobre los inputs de params (backprop a través del modelo, no actualizar pesos)
- Repetir desde varios puntos de inicio para evitar mínimos locales
- Aplicar constraints post-hoc: redondear enteros, clampear a rangos válidos

La opción NN es más elegante y escala mejor, pero requiere que el modelo esté bien calibrado — si subestima la incertidumbre, el ascent convergerá a params extremos. Agregar regularización L2 sobre los params durante el ascent mitiga esto.

---

### 4 — No-estacionariedad y degradación del modelo

Los mercados cambian de régimen (bull/bear, alta/baja volatilidad). Un modelo entrenado en 2024 puede ser malo en 2026. El plan actual no tiene mecanismo para detectar esto.

**Opciones (en orden de complejidad):**

a. **Ventana deslizante de entrenamiento**: en vez de acumular todo el store, entrenar solo con los últimos `W` trades (ej. W=2000). Pierde historia pero se adapta a regímenes recientes. Parámetro `WINDOW_TRAIN` en `config.py`.

b. **Ponderación temporal en entrenamiento**: usar todos los datos pero con pesos que decaen exponencialmente hacia el pasado. Combina memoria histórica con sensibilidad al régimen actual.

c. **Detección de degradación**: monitorear el error de predicción del modelo sobre los últimos N trades. Si supera un umbral → reentrenamiento forzado + alerta. Métrica sugerida: MAE rolling sobre `retorno_pct` real vs. predicho.

**Recomendación**: empezar con (b) — es una línea en el `sample_weight` del entrenamiento y no descarta datos valiosos de mercados pasados.

---

### 5 — Estado UNTRAINED: bootstrap y fallback

Antes de alcanzar el mínimo de trades para entrenar el modelo (~500), X5 no tiene qué inferir. El plan menciona esto como decisión pendiente pero debe quedar documentado como estado explícito del sistema.

**Propuesta:**

```
Estado UNTRAINED → X5 devuelve params de config.py (baseline manual)
Estado TRAINED   → X5 infiere params óptimos desde el modelo
```

El estado se persiste en `config/active_parameters.json` con un campo `model_status: "untrained" | "trained"`. X1 y X0 leen ese campo; si es `"untrained"`, ignoran el JSON y usan `config.py` directamente. Esto evita que un modelo vacío/malo sobreescriba parámetros funcionales.

El airbag del plan cubre el riesgo de mercado durante el bootstrap. Este mecanismo cubre el riesgo de decisión del modelo.

---

### 6 — Multi-tarea: predicción conjunta de las 3 variables objetivo

El plan lista 3 variables objetivo (`retorno_pct`, `pnl_abierto_activo_oc`, `pnl_cerrado_activo_oc`) pero no define si son 3 modelos separados o uno solo.

**Recomendación: arquitectura multi-head sobre trunk compartido.**

```
features (X2+X3+params)
        ↓
    Trunk (capas compartidas)
    ↙        ↓        ↘
Head_1    Head_2    Head_3
retorno   pnl_ab    pnl_cerr
  pct      _oc       _oc
```

Ventajas: comparte representación de features (más eficiente), el trunk aprende a separar señal de ruido en las features compartidas, y el gradiente de los 3 heads estabiliza el entrenamiento.

La función objetivo de inferencia (qué maximizar con los params) sigue siendo configurable — puede ser `Head_1` solo, o una combinación ponderada. Pero el modelo se entrena con las 3 señales simultáneamente.

Para LightGBM (V1): entrenar 3 modelos separados. La arquitectura multi-head aplica a partir de V2 con NN.
