# X5 — X5_macro_brain.py: Plan de implementación

> Fusiona los roles originales de X5 y X6 (ver `docs/context/decisiones.md` 2026-06-26).
> Estado: **pipeline V1 implementado** (`scripts/X5_macro_brain.py` + captura en `X4_backtester.py --x5`).
> En fase de **recolección de datos** (store aún vacío → todos los activos en `untrained`).
> Última revisión: `docs/plans/x5_opus_review.md` (esta sesión). Para ejecutar, ver
> **"Paso a paso de ejecución"** al final de este documento.

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

## Fases de rollout

X5 se implementa en dos fases. **X1 sigue usando parámetros estáticos de `config.py` hasta que X5 esté entrenado y validado.**

El switch entre fases se controla con **`TIPO_EJECUCION`** en `config.py` (y en cada `config_V*.py` de backtesting):

```python
TIPO_EJECUCION = "est"   # "est" = estático (Fase 1) | "din" = dinámico (Fase 2)
```

### Fase 1 — Entrenamiento (estado actual, `TIPO_EJECUCION = "est"`)

| Quién | Qué hace |
|---|---|
| X1 | Corre con parámetros de `config.py` (ignora `active_parameters.json`). **No escribe al store de X5.** |
| X5 backtester (por activo) | Genera el store de trades simulando la lógica de X1 sobre el historial — loop explore/exploit, snapshots OE+OA+OC, output `resources/x5/{ACTIVO}_store.csv` |
| X5 | Se ejecuta manualmente (`--train`, `--infer`) para entrenar el modelo y producir `active_parameters.json` |
| X0/X1/X4 | **No leen** `active_parameters.json` todavía |

El objetivo de esta fase es acumular suficiente historial de trades con los parámetros base para que el modelo tenga con qué entrenarse.

### Fase 2 — Integración y retroalimentación (`TIPO_EJECUCION = "din"`)

Con `TIPO_EJECUCION = "din"`, X1 lee `active_parameters.json` y aplica los params por activo de forma independiente. La granularidad es por activo: cada uno tiene su propio `model_status` en el JSON.

Los valores posibles de `model_status` son:

| Valor | Significado |
|---|---|
| `"untrained"` | No hay suficientes datos aún (menos de `X5_MIN_TRADES_TRAIN` trades en el store). X1 cae back a `config.py`. |
| `"lgbm"` | **LightGBM** — modelo de Gradient Boosting (árboles de decisión encadenados). Es el modelo V1: robusto, rápido de entrenar, funciona bien con datasets pequeños (<5.000 trades). Ver `x5_plan_redes_neuronales.md` sección "V1: Gradient Boosting". |
| `"ftt"` | **FT-Transformer** (Feature Tokenizer + Transformer) — red neuronal que convierte cada feature en un vector y aplica mecanismos de atención entre ellas. Es el modelo V2: más potente para capturar interacciones complejas entre features, pero requiere más datos (>5.000 trades). Ver `x5_plan_redes_neuronales.md` sección "V2: FT-Transformer". |

La transición `"lgbm"` → `"ftt"` es automática al superar `X5_MIN_TRADES_FTT` trades en el store. Ambos modelos usan el mismo store y el mismo schema de inputs/outputs — solo cambia la arquitectura interna y la estrategia de inferencia.

```
BTCUSD: model_status = 'lgbm'      → X1 usa params de active_parameters.json  (modelo V1 activo)
TSLA:   model_status = 'untrained' → X1 cae back a config.py para TSLA         (sin datos suficientes)
NVDA:   model_status = 'ftt'       → X1 usa params de active_parameters.json  (modelo V2 activo)
```

X1 chequea `model_status[activo]` en cada vuelta del loop. El fallback a `config.py` es automático por activo — no requiere cambiar `TIPO_EJECUCION` de vuelta a `"est"`. Un activo puede estar en dinámico mientras otro sigue en estático, dentro de la misma corrida.

**Ciclo de retroalimentación (estado objetivo del sistema):**

En Fase 2 se cierra el loop completo. X1 con params dinámicos genera trades reales, que alimentan el store de X5, que reentrena el modelo, que mejora los params que usa X1:

```
        X0 (soportes óptimos, actualizado continuamente)
         │
         ▼
X2 ──► X1 live (TIPO_EJECUCION="din") ──► OC cerrada ──► resources/x5/{ACTIVO}_store.csv
X3 ──►  │                                                           │
         │ lee active_parameters.json                               ▼
         │         ▲                               X5 ──train──► modelo
         └─────────┘                               │
                   └──────── active_parameters.json ◄── inferencia con contexto X2+X3 actual
```

En este estado, los X5 backtesters dedicados dejan de ser la fuente principal de datos. X1 live los reemplaza progresivamente a medida que acumula trades reales con variedad de contextos de mercado.

**X0, X2 y X3 son siempre independientes de las fases** — siguen corriendo igual en Fase 1 y Fase 2:
- X0 sigue calculando soportes óptimos para distintos N
- X2 sigue generando scores fundamentales diarios
- X3 sigue generando features técnicas por vela

Cambiar `TIPO_EJECUCION` a `"din"` es la única acción manual para activar Fase 2. El momento de ese cambio es una decisión del operador, no automática.

---

## Parámetros que X5 controla

**Todos los parámetros son por activo `[v]`.** BTCUSD, TSLA y NVDA tienen dinámicas distintas (volatilidad, liquidez, correlaciones) y sus params óptimos difieren — un mismo `K` o `LAMBDA` no es necesariamente óptimo para todos. X5 entrena un modelo independiente por activo y optimiza cada set de params por separado.

| Parámetro | Tipo | Descripción | Valor por defecto (`config.py`) | Rango orientativo para X5 |
|---|---|---|---|---|
| `n_sizes_ejecucion[v]` | int | Cantidad de soportes activos en producción para el activo `v` | 80 (todos) | [50, 200] |
| `K[v]` | float | Peso del aislamiento futuro vs. pasado en el scoring de soportes (`y = dist_izq + K * dist_der`) | 1 | [0.5, 2.0] |
| `N_EXP[v]` | float | Exponente de recencia en el scoring (`w = t^N_EXP`); mayor valor = más peso a velas recientes | 1.3 | [0.5, 3.0] |
| `LAMBDA[v]` | float | Penalización por concentración de soportes en una zona del rango de precios | 1/5 = 0.2 | [1/1000, 1/3] |
| `A[v]` | float | Ganancia mínima en USD para activar el primer stop loss ganador (trailing stop) | 6 | [2, 20] |
| `B[v]` | float | Distancia en USD que mantiene el stop loss bajo el precio actual (holgura del trailing) | 2 | [0.5, 5] |
| `LOTAJES_M[v]` | int ≥ 1 | Multiplicador de lote: lote efectivo = `LOTAJES_M[v] × MIN_LOTAJES[v]` (mínimo fijo del broker) | 1 (todos) | [1, 5] |
| `PERDIDA_MAX[v]` | float | Pérdida máxima en USD por posición abierta antes de forzar cierre. Su nivel óptimo interactúa con LOTAJES_M y el régimen de mercado. | 120 USD (global) | [100, 300] |

En `config.py` hoy `K`, `N_EXP`, `LAMBDA`, `A` y `B` son escalares globales. Al integrar X5 pasan a ser diccionarios indexados por activo, igual que `n_sizes_ejecucion` y `LOTAJES_M`.

---

## Backtesting como generador de datos

> El store de trades de X5 **no lo genera X1** (live trading). Lo generan **X5 backtesters dedicados** — uno por activo, completamente independientes entre sí. X1 con `TIPO_EJECUCION = "est"` no produce ningún output hacia X5.

### Ejecución independiente por activo

El X5 backtester corre por activo de forma completamente independiente. Cada activo tiene su propia instancia del proceso, con su propio set de parámetros. La cuenta de trading es compartida pero, para efectos del entrenamiento, se asume con capital suficiente para no imponer restricciones — los registros monetarios se capturan como **deltas** (variaciones de P&L), no como valores absolutos de cuenta.

Todos los parámetros se estiman por separado para cada activo `v`:

```
n_sizes_ejecucion[v], K[v], N_EXP[v], LAMBDA[v], A[v], B[v], LOTAJES_M[v], PERDIDA_MAX[v]
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
3. **En cada vela H1**: si es múltiplo de `X5_FREQ_REGISTRO_PERIODICO`, registra un snapshot periódico (`tipo_registro="periodico"`) con el estado actual del portfolio y el contexto X2+X3
4. **Al cerrar una orden**: registra un snapshot de OC (`tipo_registro="oc"`) con el resultado de la operación
5. Al terminar el recorrido, reinicia desde el día 0 (nuevo ciclo)

> **Actualización 2026-07-23 (implementado).** Los params ya **no** se eligen una vez por ciclo. Se **regeneran cada `delta_recalculo_soportes` días** (default 5, config_x5) DENTRO del recorrido, acoplados al recálculo cold-start de soportes hasta t. En cada punto, por activo: sin modelo → EXPLORE (aleatorio dentro de `X5_PARAM_RANGES`); con modelo → EXPLOIT con prob. `(1 - EXPLORATION_RATE)` mediante **inferencia as-of-t** (el modelo ve el contexto X2/X3/temporal/portfolio del día simulado), si no EXPLORE. Esto multiplica la variedad de tuplas (contexto, params, resultado) por pasada. Ver `docs/context/decisiones.md` 2026-07-23. El modelo se carga una vez por ciclo (`X5.cargar_modelo_para_activo`) y se infiere in-process (`X5.inferir_con_contexto`, sin airbag, rangos de config_x5).

**Acumulación de datos**: el store acumula todas las vueltas sin truncar. Los registros de ciclos con params peores son igualmente valiosos — más variedad de (contexto, params, resultado) = más relaciones causa-efecto que B puede aprender.

### Deltas registrados (en vez de P&L absoluto)

Para aislar la señal del ruido de capital:
- `delta_pnl_cerrado`: P&L de la orden que cierra en ese momento (USD)
- `delta_pnl_abierto_activo`: suma del P&L flotante de posiciones abiertas del activo al momento del cierre
- `retorno_pct`: `delta_pnl_cerrado / (precio_entrada * lote)` — normalizado al tamaño de la posición

Estos deltas son la variable objetivo que el modelo (X6) aprenderá a predecir como función del contexto y los parámetros.

---

## Store de trades — dataset de entrenamiento

> **Schema real implementado** (lo escribe `X4_backtester.py --x5`; puede diferir del diseño aspiracional de abajo). Columnas efectivas por fila:
>
> - **Identificadores**: `tipo_registro` (`oc`|`periodico`), `activo`, `timestamp_oe`, `timestamp_oa`, `timestamp_oc`.
> - **Config activa (OE)**: `n_ejecucion`, `K`, `N_EXP`, `LAMBDA`, `A`, `B`, `LOTAJES_M`, `PERDIDA_MAX`.
> - **Temporales (OE)** + **X2 (OE)** (`x2_*`) + **X3 (OE)** (`x3_*`).
> - **Portfolio (OE/momento)**: `n_ordenes_abiertas`, `n_ordenes_espera`, `exposicion_usd`, `mean_retorno_pct_abierto`, `std_retorno_pct_abierto`, `retorno_promedio_ultimas_5_oc`, `pnl_flotante_activo`.
> - **Temporales/X2/X3 (OA)**: sufijo `_oa` (vacías en filas `periodico`).
> - **Targets (Y)**: `pnl_cerrado_activo`, `retorno_pct`. En filas `periodico`, `retorno_pct` va vacío y el target es `pnl_flotante_activo`.
>
> **No implementado** (del diseño aspiracional): `ticket`, `precio_entrada`, `precio_salida`, `pnl_usd`, columnas `_oc` de X2/X3. Ver TO DOs si se decide agregarlos.
>
> **3 targets efectivos** que el modelo predice: `retorno_pct` (filas `oc`), `pnl_flotante_activo` (filas `oc` + `periodico`), `pnl_cerrado_activo` (filas `oc`).

### Dos tipos de registro

El store tiene **dos tipos de fila**, distinguidas por `tipo_registro`:

| tipo_registro | Cuándo se genera | Variable objetivo (Y) |
|---|---|---|
| `"oc"` | Al cerrar una orden (OC) | `retorno_pct` de esa operación |
| `"periodico"` | Cada `X5_FREQ_REGISTRO_PERIODICO` velas H1, haya o no OC | `pnl_flotante_activo` (P&L flotante de posiciones abiertas del activo en ese momento) |

**Por qué los dos tipos son necesarios:** si el store solo acumula registros en OC, durante una racha bajista sostenida (posiciones abiertas en pérdida, ninguna cerrando) el modelo no recibe señal de que algo está mal — precisamente cuando más necesita adaptar los params. Los registros periódicos cubren ese hueco: aunque no haya trades cerrados, capturan el deterioro del portfolio en tiempo real.

**Qué features entran al modelo y cuáles son solo para análisis:**

| Momento | Entra al modelo | Razón |
|---|---|---|
| OE | Sí | Es el contexto de decisión; equivale a "ahora" en inferencia |
| OA | Sí | El `retorno_pct` se mide desde el precio de OA; captura el estado real del mercado al entrar. Entre OE y OA puede pasar tiempo significativo (días). |
| OC | No (solo análisis) | No disponible en inferencia — es información del futuro. Capturado en el store para investigación. |

### Columnas — tipo `"oc"` (una fila por trade cerrado)

**Identificadores**
- `tipo_registro` = `"oc"`, `activo`, `ticket`, `timestamp_oe`, `timestamp_oa`, `timestamp_oc`

**Precio y resultado**
- `precio_entrada`, `precio_salida`, `pnl_usd`, `retorno_pct`
- `pnl_flotante_activo`: P&L flotante de posiciones aún abiertas del activo al cerrar esta orden
- `pnl_cerrado_activo_oc`: P&L acumulado de órdenes ya cerradas del activo en la sesión

**Config activa al momento de OE**
- `n_ejecucion`, `K`, `N_EXP`, `LAMBDA`, `A`, `B`, `LOTAJES_M`

**Features de X2 al momento de OE** *(entra al modelo)*
- `x2_score`, `x2_tendencia` + scores componentes según activo (stock vs crypto)

**Features de X2 al momento de OA** *(entra al modelo, sufijo `_oa`)*
- ídem, con sufijo `_oa`

**Features de X2 al momento de OC** *(solo análisis, sufijo `_oc`)*
- ídem, con sufijo `_oc`

**Features de X3 al momento de OE** *(entra al modelo)*
- `sma_20`, `sma_50`, `ema_12`, `ema_26`, `rsi_14`, `macd`, `macd_signal`
- `atr_14`, `atr_pct`, `bb_width`, `bb_pos`, `roc_3`, `roc_5`, `roc_10`, `roc_20`
- `vol_24h`, `vol_168h`, `vol_spike_ratio`, `drawdown_20`, `drawdown_50`
- `trend_slope_20`, `trend_slope_50`, `dist_nearest_support`, `dist_floor_support`, `density_2pct`

**Features de X3 al momento de OA** *(entra al modelo, sufijo `_oa`)*
- ídem, con sufijo `_oa`

**Features de X3 al momento de OC** *(solo análisis, sufijo `_oc`)*
- ídem, con sufijo `_oc`

**Contexto operativo al momento de OE**
- `n_ordenes_abiertas_activo`, `n_ordenes_espera_activo`, `exposicion_usd_activo`
- `mean_retorno_pct_abierto`, `std_retorno_pct_abierto`, `exposicion_pct_cuenta`
- `retorno_promedio_ultimas_5_oc`

**Features temporales al momento de OE** *(entra al modelo)*
- `hora` (0–23), `dia_semana` (0=Lunes, 6=Domingo), `dia_mes` (1–31), `mes` (1–12)
- Dummies día semana: `ds_lun`, `ds_mar`, `ds_mie`, `ds_jue`, `ds_vie`, `ds_sab`, `ds_dom`
- Dummies mes: `mes_1` … `mes_12`
- `dias_hasta_festivo`: días hasta el próximo festivo US (capped a 30)
- `dias_desde_festivo`: días desde el último festivo US (capped a 30)
- `es_vispera_festivo`: 1 si `dias_hasta_festivo <= 1`
- `es_post_festivo`: 1 si `dias_desde_festivo <= 1`

Los festivos considerados son los de mercado US (NYSE): Año Nuevo, MLK Day, Presidents Day, Viernes Santo, Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving, Christmas. Para crypto (BTCUSD, ETHUSD), el mercado es 24/7 pero los festivos US sí afectan volumen institucional, por eso se incluyen para todos los activos. Los dummies de día/mes capturan estacionalidad intrasemanal (lunes post-cierre semanal), fin de mes, etc.

### Columnas — tipo `"periodico"` (una fila cada T velas H1)

**Identificadores**
- `tipo_registro` = `"periodico"`, `activo`, `timestamp_registro`
- Campos de orden (`ticket`, `timestamp_oe`, `timestamp_oa`, `timestamp_oc`, `precio_entrada`, `precio_salida`, `pnl_usd`, `retorno_pct`): `null`

**Variable objetivo**
- `pnl_flotante_activo`: P&L flotante de todas las posiciones abiertas del activo en este momento. Es la señal de deterioro durante rachas adversas.

**Config activa en este momento**
- `n_ejecucion`, `K`, `N_EXP`, `LAMBDA`, `A`, `B`, `LOTAJES_M`

**Features de X2 y X3 en este momento** *(mismo schema que OE en registros "oc")*

**Features temporales en este momento** *(mismo schema que OE en registros "oc")*

**Contexto operativo en este momento**
- `n_ordenes_abiertas_activo`, `exposicion_usd_activo`, `exposicion_pct_cuenta`
- `mean_retorno_pct_abierto`, `std_retorno_pct_abierto`

### Output en disco

`resources/x5/{ACTIVO}_store.csv` — un CSV por activo, con append en cada OC y cada T velas H1.

---

## Ciclo A↔B — frecuencia de consulta y reentrenamiento

> **Fase 2.** Este ciclo no aplica mientras X1 corra con parámetros estáticos.

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

## Arquitectura del modelo

La arquitectura no es fija: escala automáticamente con el volumen de datos disponible. Cada activo vive en su propia fase de forma independiente.

```
< 500 OC → untrained  → devuelve config.py sin tocar (fallback seguro)
500–5.000 OC → lgbm  → 3 Gradient Boosting (LightGBM) independientes, uno por output
> 5.000 OC  →  ftt   → 1 FT-Transformer (Feature Tokenizer + Transformer) con 3 heads
```

Los umbrales se controlan con `X5_MIN_TRADES_TRAIN` y `X5_MIN_TRADES_FTT` en `config.py`. La transición es automática al detectar que el store del activo superó el umbral.

**Cuadro general — de inputs a outputs:**

```
┌──────────────────── INPUTS (~240 features, vector de tamaño fijo) ─────────────────┐
│  X2 en OE (~12)  · X3 en OE (~25)  · Temporal en OE (~28)                        │
│  X2 en OA (~12)  · X3 en OA (~25)  · Config params (7)  · Portfolio (~7)         │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        ↓
         ┌──────────────────────────────────────────────────────┐
         │  untrained → lgbm (V1) → ftt (V2)   (por activo)    │
         └──────────────────────────────────────────────────────┘
                                        ↓
          retorno_pct  ·  pnl_abierto_activo_oc  ·  pnl_cerrado_activo_oc
```

**V1 — LightGBM (Gradient Boosting)**: 3 modelos independientes, uno por output. Reentrena en batch cada `X5_RETRAIN_EVERY_N_VELAS` velas. Infiere con Optuna (Bayesian Optimization) para encontrar los config_params que maximizan `retorno_pct`.

**V2 — FT-Transformer (Feature Tokenizer + Transformer)**: cada feature se convierte en un vector de embedding → capa de atención entre features → trunk compartido → 3 heads. Aprende con un paso de gradiente por vela (online). Infiere con gradient ascent sobre los config_params.

El detalle completo de la arquitectura neuronal está en [`x5_plan_redes_neuronales.md`](x5_plan_redes_neuronales.md).

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

**Decisión: cada vela H1.** El ciclo completo de X5 (capturar datos → actualizar modelo → inferir params → ejecutar) corre una vez por vela horaria. El objetivo es que los parámetros de trading siempre reflejen el estado más reciente del mercado (X2 + X3) y la historia acumulada de operaciones.

**El ciclo por vela (4 pasos):**

```
── Cierre de vela t ──────────────────────────────────────────────────────────
Paso 1: Capturar — leer P&L flotante del activo + trades cerrados en esta vela
        → Generar nuevo(s) registro(s) en el store (tipo "oc" si hubo OC,
          tipo "periodico" siempre si hay posición abierta)
        → Alimentar el modelo con ese(s) nuevo(s) dato(s) (entrenamiento continuo)

── Apertura de vela t+1 ──────────────────────────────────────────────────────
Paso 2: Observar — leer contexto actual: X2 (fundamentales) + X3 (técnicas)
Paso 3: Seleccionar — dado ese contexto, ¿qué params maximizan retorno esperado?
        → El modelo responde con un set de params por activo
Paso 4: Ejecutar — X1 corre con esos params para la vela t+1
```

**Entrenamiento continuo vs. batch:**

- Con Red Neuronal (MLP o FT-Transformer): el modelo puede actualizar sus pesos con cada nuevo dato (aprendizaje online) — un paso de gradiente por registro nuevo. Esto implementa literalmente el "siempre entrenando en paralelo".
- Con Gradient Boosting (LightGBM): no hay aprendizaje online nativo; en cambio, se acumulan registros y se reentrena el modelo completo cada `X5_RETRAIN_EVERY_N_VELAS` velas. La inferencia sigue siendo por vela — solo el reentrenamiento es batch.

La variable `X5_RETRAIN_EVERY_N_VELAS` aplica solo al modo LightGBM. En modo Red Neuronal, el reentrenamiento ocurre en cada Paso 1.

---

## Dependencias

| Módulo | Rol |
|---|---|
| X5 backtester (por activo) | **Fase 1**: genera el store inicial — simula la lógica de X1 sobre el historial H1 con el loop explore/exploit, captura snapshots OE+OA+OC y escribe en `resources/x5/{ACTIVO}_store.csv`. |
| X1 (Fase 2) | **Fase 2**: llama `X5_macro_brain.py --vela` en cada cierre de vela H1. X5 captura el P&L real, actualiza el modelo y escribe los params recomendados. X1 los lee antes de la siguiente vela. |
| X2 | Provee features fundamentales (snapshot al momento de OE y OC, leído por el backtester y por X5 en inferencia) |
| X3 | Provee features técnicas (snapshot al momento de OE y OC, ídem) |
| config.py | `TIPO_EJECUCION` controla si X1/X0/X4 usan params estáticos o leen `active_parameters.json`; `MIN_LOTAJES` y `LOTAJES_M` definidos aquí |

---

## Diseño y estructura

### Carpetas y archivos

```
resources/x5/
├── {ACTIVO}_store.csv          # dataset de entrenamiento; append por cada OC
├── models/
│   ├── {ACTIVO}_lgbm.pkl       # modelo LightGBM (V1); se sobreescribe en cada reentrenamiento
│   └── {ACTIVO}_ftt.pt         # modelo FT-Transformer (V2); idem
└── Performance/
    └── {ACTIVO}_performance.json  # historial de métricas ML por entrenamiento (append)

config/
└── active_parameters.json      # output de X5; leído por X0 y X1
```

`model_status` va dentro de `active_parameters.json` (ver sección 5 de Sugerencias). No hay un archivo de estado separado.

### Métricas de performance del modelo

Cada vez que X5 reentrena (con `--train`), calcula y persiste métricas clásicas de Aprendizaje Automático (ML) para evaluar la calidad del modelo. El split es siempre 80 % train / 20 % test (cronológico — no aleatorio, para respetar el orden temporal de los trades).

**Métricas registradas**, para cada target (`retorno`, `flotante`, `cerrado`) y para cada set (train y test):

| Métrica | Fórmula | Descripción |
|---|---|---|
| **MAE** (Mean Absolute Error) | `mean(\|y - ŷ\|)` | Error absoluto promedio en las unidades del target. Más interpretable que MSE. |
| **MSE** (Mean Squared Error) | `mean((y - ŷ)²)` | Penaliza errores grandes cuadráticamente. Útil para detectar outliers de predicción. |
| **MAPE** (Mean Absolute Percentage Error) | `100 × mean(\|y - ŷ\| / \|y\|)` | Error porcentual relativo. Se omite (`None`) cuando `\|y\| ≈ 0` para evitar división por cero. |
| **R²** (coeficiente de determinación) | `1 - SS_res/SS_tot` · `SS_res = Σ(y-ŷ)²` · `SS_tot = Σ(y-ȳ)²` | Proporción de varianza explicada. 1.0 = perfecto; 0.0 = equivale a predecir la media; negativo = peor que la media. `None` si `SS_tot ≈ 0`. |

**Formato de `{ACTIVO}_performance.json`** — lista JSON con una entrada por entrenamiento (append histórico):

```json
[
  {
    "timestamp": "2026-07-16T00:05:00",
    "tipo_modelo": "lgbm",
    "n_train": 400,
    "n_test": 100,
    "targets": {
      "retorno": {
        "train": {"MAE": 0.012, "MSE": 0.0003, "MAPE": 5.2, "R2": 0.71},
        "test":  {"MAE": 0.018, "MSE": 0.0006, "MAPE": 8.1, "R2": 0.52}
      },
      "flotante": {
        "train": {"MAE": 0.9, "MSE": 1.4, "MAPE": null, "R2": 0.60},
        "test":  {"MAE": 1.2, "MSE": 2.1, "MAPE": null, "R2": 0.40}
      },
      "cerrado": {
        "train": {"MAE": 2.1, "MSE": 7.8, "MAPE": null, "R2": 0.45},
        "test":  {"MAE": 3.3, "MSE": 15.2, "MAPE": null, "R2": 0.21}
      }
    }
  }
]
```

**Señales de alerta a vigilar en las métricas:**

- `R² train >> R² test` → overfitting claro; considerar reducir `num_leaves` (LightGBM) o aumentar dropout (FTT).
- `R² test < 0` → el modelo es peor que predecir la media; el store probablemente tiene ruido excesivo o poca variedad de contextos.
- MAE test creciente entre entrenamientos consecutivos → degradación del modelo; coincide con el criterio de reentrenamiento forzado de la sección 4.
- MAPE `null` frecuente en `flotante` y `cerrado` → normal (targets cercanos a 0); usar MAE y R² para esos heads.

La evolución histórica de estas métricas es la fuente principal para decidir cuándo cambiar de arquitectura (V1 → V2) y para calibrar los umbrales del detector de degradación.

### Schema de `active_parameters.json`

Un objeto JSON con una clave por activo más un timestamp global:

```json
{
  "generated_at": "2026-01-07T09:00:00",
  "BTCUSD": {
    "model_status": "lgbm",
    "n_sizes_ejecucion": 95,
    "K": 1.1,
    "N_EXP": 1.4,
    "LAMBDA": 0.002,
    "A": 8.5,
    "B": 2.1,
    "LOTAJES_M": 2,
    "PERDIDA_MAX": 140.0
  },
  "ETHUSD": {
    "model_status": "untrained",
    "n_sizes_ejecucion": 80,
    "K": 1.0,
    "N_EXP": 1.3,
    "LAMBDA": 0.002,
    "A": 6.0,
    "B": 2.0,
    "LOTAJES_M": 1,
    "PERDIDA_MAX": 120.0
  }
}
```

**Decisiones fijadas:**

- `model_status` va anidado dentro de cada activo (no en una clave separada). X1 lee `json[activo]["model_status"]`.
- Activos con `model_status = "untrained"` incluyen igualmente todos los params — son los valores baseline de `config.py`. X1 los ignora y usa `config.py` directamente, pero el JSON siempre está completo.
- `generated_at` (ISO 8601) es metadata global para debugging y auditoría. No lo lee X1.
- Todos los params son por activo: `K`, `N_EXP`, `LAMBDA`, `A`, `B` (que hoy son escalares globales en `config.py`) pasan a ser por activo al integrar X5.
- `PERDIDA_MAX` se incluye por activo — su nivel óptimo interactúa con `LOTAJES_M` y el régimen del activo.

**Cómo lo lee X1:**

```python
import json
with open("config/active_parameters.json") as f:
    ap = json.load(f)

for activo in VALORES:
    if ap[activo]["model_status"] == "untrained":
        # usa config.py directamente para este activo
        continue
    n_sizes_ejecucion = ap[activo]["n_sizes_ejecucion"]
    K = ap[activo]["K"]
    # ... etc.
```

### Estructura del código (`X5_macro_brain.py`) — implementación real

El script tiene **3 modos + 1 casilla** (simplificado en `x5_opus_review.md`; antes eran 5).
`--vela` fue **eliminado** (era un alias exacto de `--infer`).

```
python X5_macro_brain.py --recolectar       # genera datos: backtesting paralelo por activo + auto-entrena
python X5_macro_brain.py --infer            # recomienda params con el modelo actual → active_parameters.json
python X5_macro_brain.py --infer --train    # reentrena desde el store y luego recomienda
python X5_macro_brain.py --status           # diagnóstico: n_trades y modelo activo por activo
python X5_macro_brain.py --infer --activo BTCUSD   # solo un activo (merge en active_parameters.json)
```

**¿Qué hace cada modo?** (analogía del chef en `x5_plan_redes_neuronales.md`)

- **`--recolectar`** — *"practica cocinando para llenar el cuaderno"*. Es el modo de **Fase 1** cuando el store está vacío. Lanza un **worker por activo en paralelo** (`ThreadPoolExecutor`), y cada worker corre ciclos de `X4_backtester.py --x5 --activo {activo}` — un backtest completo desde `fecha_inicio` que simula la lógica de X1 vela a vela y captura snapshots (OE/OA/OC + periódicos) al store. Al cerrar cada ciclo, si el activo superó `X5_MIN_TRADES_TRAIN` OC, **auto-entrena** su modelo. Los activos avanzan a distinto ritmo, en paralelo.

- **`--infer`** — *"con lo que ya estudiaste, dame la mejor receta para hoy"*. Carga el modelo guardado de cada activo, infiere los params que maximizan `retorno_pct` para el contexto actual (X2+X3) y escribe `config/active_parameters.json`. No entrena ni captura datos. Es rápido.
  - `--infer --train`: reentrena desde el store antes de recomendar (la casilla `--train`).
  - `--infer --activo X`: infiere solo ese activo y hace **merge** en el JSON (preserva los demás). Usado por X4 en modo EXPLOIT.

- **`--status`** — *"muéstrame cómo va el chef"*. Imprime, por activo: nº de OC en el store, nº total de filas, tipo de modelo activo (`untrained`/`lgbm`/`ftt`) y qué recomendó la última vez. Solo lectura.

**Casilla `--train`**: no es un modo. Solo tiene efecto junto a `--infer`. `--recolectar` ya entrena por su cuenta.

**Funciones principales (nombres reales del código):**

```python
_cargar_store(activo) -> pd.DataFrame       # lee resources/x5/{ACTIVO}_store.csv
_n_oc(store) -> int                         # cuenta filas con tipo_registro == 'oc'
_seleccionar_tipo(n_oc) -> str              # 'untrained' | 'lgbm' | 'ftt' según umbrales

_feature_cols_de_store(store) -> list       # orden reproducible del vector de features
                                            # (excluye columnas _oc: info del futuro)
_preparar_features(store, feature_cols, target, tipos_registro=('oc',)) -> (X, y, w)
    # Filtra por tipos_registro; aplica ventana X5_WINDOW_TRAIN y decay temporal
    # exponencial (X5_LAMBDA_DECAY) como sample_weight.

# Entrenamiento (elige LGBM o FTT según _seleccionar_tipo)
_entrenar(activo) -> str                    # entrena el modelo apropiado; retorna el tipo
_entrenar_lgbm(activo, store) -> bool       # 3 LightGBMRegressor: retorno/flotante/cerrado
_entrenar_ftt(activo, store) -> bool        # 1 FT-Transformer con 3 heads

# Inferencia
_inferir_params(activo) -> (params, status) # carga modelo y optimiza params
_inferir_lgbm(...)                          # Optuna (X5_N_OPTUNA_TRIALS trials)
_inferir_ftt(...)                           # gradient ascent (X5_ASCENT_* configs)
_aplicar_airbag(activo, params) -> dict     # regla dura: fuerza N y lote mínimos si caída > umbral
_leer_contexto_actual(activo) -> dict       # X2 (x2_history.json) + X3 (última fila) + temporal

# Salida y orquestación
_escribir_active_parameters(resultados)     # merge + escritura atómica del JSON
_recolectar(version)                        # Fase 1: paralelo por activo (ver arriba)
_worker_recolectar_activo(activo, version, x4_path)   # bucle de ciclos de 1 activo
_mostrar_status()                           # dashboard --status
```

**Métricas de ML calculadas** — `_calcular_metricas(y_true, y_pred)` devuelve `MAE`, `MSE`,
`MAPE` (None si `|y|≈0`) y `R²` (None si `SS_tot≈0`). Se guardan por entrenamiento en
`resources/x5/Performance/{ACTIVO}_performance.json` (historial, split 80/20 cronológico),
para cada target (`retorno`/`flotante`/`cerrado`) y cada set (train/test).

**Independencia por activo:** cada activo tiene su propio store, su propio modelo
(`resources/x5/models/{ACTIVO}/`) y su propia fase. BTCUSD puede estar en `ftt` mientras
TSLA sigue en `untrained`, dentro de la misma corrida.

---

## Configuraciones de usuario

Todo va en `config.py` (y en cada `config_V*.py` de backtesting), bajo el bloque `# ─── Modo de ejecución ───`.

### Modo de ejecución

```python
TIPO_EJECUCION = "est"   # "est" | "din"
```

Controla si X1, X0 y X4 usan parámetros estáticos de `config.py` o dinámicos de `active_parameters.json`. Con `"din"`, el fallback por activo a `config.py` es automático si `model_status[activo] == "untrained"`. Ver sección "Fases de rollout" para el comportamiento completo.

### Umbrales del modelo

```python
X5_MIN_TRADES_TRAIN = 500     # mínimo de OC en el store para entrenar cualquier modelo
X5_MIN_TRADES_FTT   = 5000    # a partir de este n, X5 usa FT-Transformer en vez de LightGBM
```

Si el store de un activo tiene menos de `X5_MIN_TRADES_TRAIN` trades, X5 devuelve los parámetros de `config.py` sin tocarlos. La transición LGBM → FTT es automática al cruzar `X5_MIN_TRADES_FTT`.

### Frecuencia de reentrenamiento profundo (solo LightGBM)

```python
X5_RETRAIN_EVERY_N_VELAS = 48   # cada cuántas velas H1 forzar un reentrenamiento completo (LightGBM)
                                 # = aprox. cada 2 días; irrelevante en modo Red Neuronal (online)
```

Solo aplica en modo LightGBM. En el ciclo `--vela` normal, LightGBM acumula registros y reentrena rápido (incremental); cada `X5_RETRAIN_EVERY_N_VELAS` velas se hace un reentrenamiento completo desde cero para evitar deriva acumulada. Con Red Neuronal, el modelo se actualiza en cada `--vela` — este parámetro se ignora.

### Dataset y ponderación temporal

```python
X5_WINDOW_TRAIN  = None    # None = usar todo el store; int = últimas N filas (ventana deslizante)
X5_LAMBDA_DECAY  = 0.001   # decay exponencial: peso = e^(-lambda * dias_antiguedad)
                            # 0.001 ≈ peso 0.5 para operaciones de ~700 días atrás
```

Estos dos parámetros son excluyentes en la práctica: si `X5_WINDOW_TRAIN` es `None` se usa `X5_LAMBDA_DECAY`; si se define una ventana, la ponderación temporal es opcional dentro de esa ventana.

### Airbag (protección de mercado)

```python
X5_AIRBAG_THRESHOLD = {    # caída máxima permitida en las últimas 4 velas H1
    'BTCUSD': 0.08,        # 8% para crypto
    'ETHUSD': 0.08,
    'TSLA':   0.05,        # 5% para acciones
    'GOOGL':  0.05,
    'NVDA':   0.05,
    'AMZN':   0.05,
}

X5_N_MINIMO = {            # N mínimo de soportes a usar cuando se activa el airbag
    'BTCUSD': 30,
    'ETHUSD': 30,
    'TSLA':   20,
    'GOOGL':  20,
    'NVDA':   20,
    'AMZN':   20,
}
```

### Frecuencia de registros periódicos

```python
X5_FREQ_REGISTRO_PERIODICO = 4   # registrar snapshot periódico cada N velas H1 (4 = cada 4 horas)
                                  # si no hay posiciones abiertas en el activo, el registro se omite
```

### Exploración en backtesting

```python
X5_EXPLORATION_RATE = 0.30   # % de ciclos de backtesting con params aleatorios (exploración vs. explotación)
```

### Inferencia

```python
# Optuna (modo LGBM): optimizador bayesiano que aprende qué zonas del espacio de params son
# prometedoras y concentra los intentos ahí — más eficiente que probar todas las combinaciones.
X5_N_OPTUNA_TRIALS  = 200    # intentos por inferencia (~10-30 seg con 200)
# Gradient ascent (modo FTT): ajusta iterativamente los valores de params de entrada para
# maximizar el retorno predicho, propagando el gradiente hacia la entrada (no hacia los pesos).
X5_ASCENT_RESTARTS  = 10     # puntos de inicio aleatorios (para no quedar en óptimo local)
X5_ASCENT_STEPS     = 300    # pasos de ascent por punto de inicio
X5_ASCENT_LR        = 0.01   # magnitud del paso por iteración
```

### Rangos de búsqueda de parámetros

Todos los parámetros son por activo — X5 optimiza un set independiente para cada uno.

```python
# Todos los rangos son por activo. Los params K, N_EXP, LAMBDA, A, B comparten el mismo
# rango orientativo entre activos; n_sizes_ejecucion y LOTAJES_M difieren por activo.
X5_PARAM_RANGES = {
    'K':               {'BTCUSD': (0.5, 2.0), 'ETHUSD': (0.5, 2.0),
                        'TSLA': (0.5, 2.0), 'GOOGL': (0.5, 2.0),
                        'NVDA': (0.5, 2.0), 'AMZN': (0.5, 2.0)},
    'N_EXP':           {'BTCUSD': (0.5, 3.0), 'ETHUSD': (0.5, 3.0),
                        'TSLA': (0.5, 3.0), 'GOOGL': (0.5, 3.0),
                        'NVDA': (0.5, 3.0), 'AMZN': (0.5, 3.0)},
    'LAMBDA':          {'BTCUSD': (1/1000, 1/50), 'ETHUSD': (1/1000, 1/50),
                        'TSLA': (1/1000, 1/50), 'GOOGL': (1/1000, 1/50),
                        'NVDA': (1/1000, 1/50), 'AMZN': (1/1000, 1/50)},
    'A':               {'BTCUSD': (2.0, 20.0), 'ETHUSD': (2.0, 20.0),
                        'TSLA': (2.0, 20.0), 'GOOGL': (2.0, 20.0),
                        'NVDA': (2.0, 20.0), 'AMZN': (2.0, 20.0)},
    'B':               {'BTCUSD': (0.5, 5.0), 'ETHUSD': (0.5, 5.0),
                        'TSLA': (0.5, 5.0), 'GOOGL': (0.5, 5.0),
                        'NVDA': (0.5, 5.0), 'AMZN': (0.5, 5.0)},
    'n_sizes_ejecucion': {'BTCUSD': (50, 200), 'ETHUSD': (50, 200),
                          'TSLA': (40, 180), 'GOOGL': (40, 180),
                          'NVDA': (40, 180), 'AMZN': (40, 180)},
    'LOTAJES_M':         {'BTCUSD': (1, 5), 'ETHUSD': (1, 5),
                          'TSLA': (1, 5), 'GOOGL': (1, 5),
                          'NVDA': (1, 5), 'AMZN': (1, 5)},
}
```

---

## TO DO (derivados de la revisión `x5_opus_review.md`)

**Pendientes técnicos concretos:**

- [ ] **Head `flotante` con filas periódicas en FTT**: hoy en LightGBM el target `pnl_flotante_activo` entrena con `('oc','periodico')`, pero en FT-Transformer los 3 heads comparten el mismo tensor `X` (solo filas `oc`), así que las filas periódicas no llegan al head flotante. Incorporarlas vía un pase separado o Deep Sets en V2.
- [ ] **`_features_temporales_ahora()` usa `pd.Timestamp.now()`**: correcto para inferencia en vivo (Fase 2), pero no reconstruye el timestamp histórico del contexto. Si se quiere inferencia offline reproducible, parametrizar el timestamp.
- [ ] **Coherencia `n_ejecucion` vs `n_sizes_ejecucion`**: X4 registra en el store `n_ejecucion = cfg.n_sizes[activo]` (el N aplicado en el backtest), mientras el baseline/rango de X5 usan `n_sizes_ejecucion`. Verificar que el parámetro registrado sea el mismo que se optimiza.
- [ ] **Eficiencia de `_recolectar`**: cada worker recarga el CSV completo del store por ciclo. Aceptable a esta escala; si el store crece a decenas de miles de filas, contar OC incrementalmente.
- [ ] **(Opcional) Columnas de análisis del store**: decidir si vale agregar `ticket`, `precio_entrada/salida`, `pnl_usd` y features `_oc` (X2/X3 al cierre) — solo para análisis, no entran al modelo.
- [ ] **Contención de `active_parameters.json` en EXPLOIT paralelo**: mitigada con merge + escritura atómica (read-modify-write). Si se observa pérdida de actualizaciones bajo alta concurrencia, agregar file lock.

**Decisiones de modelado (se cierran con datos reales, no antes):**

- [ ] Variable objetivo principal para optimizar en inferencia (`retorno_pct` es la actual).
- [ ] Confirmar umbrales `X5_MIN_TRADES_TRAIN=500` / `X5_MIN_TRADES_FTT=5000` con las métricas de `Performance/`.
- [ ] Estrategia de reentrenamiento en Fase 2 (completo vs incremental).

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
| **Perceptrón Multicapa (MLP) estándar** | Medio | Simple, diferenciable | Interacciones implícitas; satura pronto |
| **TFT** (Temporal Fusion Transformer) | Bajo para este diseño | Potente para series multivariadas con horizonte múltiple | Diseñado para forecasting, no por-trade; overhead alto |
| **LSTM/GRU sobre X3** | Bajo | Capta trayectoria temporal de features técnicas | X3 ya codifica ese estado; duplica información |

**Secuencia recomendada:**
1. **V1**: LightGBM — el baseline más robusto para datasets pequeños (<50k filas).
2. **V2**: FT-Transformer — si el store supera ~5k trades y LightGBM plateó.

**Argumento para priorizar Red Neuronal (NN) en inferencia**: con un modelo diferenciable (MLP o FT-Transformer), la búsqueda de params óptimos puede hacerse por **gradient ascent** (igual que el entrenamiento, pero maximizando en vez de minimizar, y ajustando los valores de params de entrada en vez de los pesos del modelo) con el contexto fijo. Esto es mucho más barato que grid search u Optuna, especialmente si la inferencia corre cada vela H1. Si se elige LightGBM, la estrategia de inferencia debe ser explícitamente Optuna (optimizador bayesiano de hiperparámetros: concentra intentos en zonas prometedoras del espacio de params) con el espacio acotado.

---

### 3 — Estrategia de inferencia según tipo de modelo

Debe documentarse explícitamente antes de implementar, porque condiciona la elección de arquitectura.

**Si modelo = Gradient Boosting sobre Árboles de Decisión (GBDT — LightGBM / XGBoost son dos implementaciones del mismo algoritmo):**
- Grid search discreto sobre params enteros (`n_sizes_ejecucion`, `LOTAJES_M`) + Optuna para params continuos (`K`, `N_EXP`, `LAMBDA`, `A`, `B`)
- El contexto se fija como constante; Optuna optimiza los params como variables de decisión

**Si modelo = Red Neuronal (NN) diferenciable (MLP o FT-Transformer):**
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

c. **Detección de degradación**: monitorear el error de predicción del modelo sobre los últimos N trades. Si supera un umbral → reentrenamiento forzado + alerta. Métrica sugerida: MAE rolling sobre `retorno_pct` real vs. predicho. Las métricas históricas guardadas en `resources/x5/Performance/` son la fuente de referencia para calibrar ese umbral (ver sección "Métricas de performance del modelo").

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

---

### 7 — Representación del estado del portfolio en los inputs

El store tiene **una fila por OC**. Los features de portfolio son snapshots en el momento de OE (cuando se coloca el buy limit). El diseño debe evitar que el modelo aprenda de ruido de posiciones individuales en lugar de la señal real del mercado.

#### Órdenes abiertas (OA) al momento de OE

**No usar inputs individuales por orden.** Si se alimentan las OAs como filas separadas, el modelo puede aprender identidades espurias ("la orden con entrada en $45k y P&L flotante +2% implica usar params agresivos") en vez del patrón general. El número de OAs también varía, lo que crea inputs de longitud variable.

**Opción A (recomendada para V1) — agregación estadística:**

```
n_ordenes_abiertas_activo       (ya en el schema)
exposicion_usd_activo           (ya en el schema)
mean_retorno_pct_abierto        → promedio de retorno flotante % entre las OAs del activo
std_retorno_pct_abierto         → dispersión del retorno flotante (¿portfolio "partido" o uniforme?)
```

Usar `retorno_pct` (no P&L absoluto) y `exposicion_pct_cuenta` (no USD) para eliminar el efecto del capital y hacer los features transferibles entre sesiones.

**Opción B (V2 con NN) — Deep Sets / mean pooling permutation-invariant:**

Si se quiere representación individual sin introducir orden artificial, cada OA se codifica como un vector pequeño:

```
[retorno_pct_flotante, horas_abierta, dist_precio_entrada_pct, lotaje_relativo]
```

Un módulo de **mean pooling** sobre todos esos vectores produce un embedding de tamaño fijo independiente del número de OAs. Esto es equivalente a una capa de atención simplificada (Deep Sets) y es permutation-invariant: el resultado no depende de en qué orden se listen las OAs. Se concatena al vector principal de features antes del trunk.

La opción A es suficiente para V1 y evita complejidad arquitectural innecesaria.

#### Órdenes cerradas (OC) hasta t

El store ya tiene `pnl_cerrado_activo_oc` (P&L acumulado cerrado del activo en la sesión). Eso cubre la señal de "cómo le fue al activo en la sesión hasta ahora".

**No agregar una secuencia de OCs individuales pasadas**: introduce correlación redundante con X3 (que ya refleja el historial de precios) y riesgo de overfitting a rachas de suerte.

**Si se quiere capturar momentum de sesión** (racha ganadora/perdedora), agregar una sola feature rolling:

```
retorno_promedio_ultimas_N_oc   (N = 3 o 5, configurable)
```

Esta feature resume si las últimas N operaciones cerradas del activo fueron ganadoras o perdedoras en promedio — sin exponer el modelo a identidades individuales de trades.

#### Resumen de features de portfolio a agregar al schema

Las siguientes columnas se agregan al snapshot **al momento de OE** (sección "Contexto operativo al momento de OE" del store):

| Feature | Descripción |
|---|---|
| `mean_retorno_pct_abierto` | Promedio de retorno flotante % de las OA del activo al colocar la OE |
| `std_retorno_pct_abierto` | Desviación estándar del retorno flotante de las OA del activo |
| `exposicion_pct_cuenta` | `exposicion_usd_activo / capital_cuenta` — normalizado por capital |
| `retorno_promedio_ultimas_5_oc` | Promedio de `retorno_pct` de las últimas 5 OC cerradas del activo en la sesión |

---

# Paso a paso de ejecución (desde cero, con peras y manzanas)

> Esta sección responde: **"tengo cero datos de entrenamiento, ¿cómo pongo a funcionar el cerebro (X5)?"**.
> Se ejecuta en **Windows** (donde están los datos y MT5). En Mac solo se desarrolla.

## El mapa mental en una frase

X5 es un chef que aún **no sabe cocinar** (no hay datos). Para que aprenda hay que **hacerlo cocinar miles de platos simulados** sobre la historia de precios (backtesting), anotar cada resultado en su cuaderno (el *store*), y recién ahí **estudiar** ese cuaderno (entrenar el modelo). Después le podemos preguntar **"¿qué receta uso hoy?"** (inferir params). Todo esto ocurre **en paralelo para los 6 activos**, cada uno con su propio cuaderno y su propio chef.

```
   SIN DATOS                CON DATOS                 MODELO LISTO
  ┌─────────┐   recolectar  ┌─────────┐   (auto)    ┌──────────┐   infer   ┌──────────────────────┐
  │ store   │ ────────────► │ store   │ ──train───► │ modelo   │ ────────► │ active_parameters.json│
  │ vacío   │  BT paralelo  │ 500+ OC │             │ lgbm/ftt │           │ (params por activo)   │
  └─────────┘               └─────────┘             └──────────┘           └──────────────────────┘
```

## Requisitos previos (una sola vez)

1. **Datos de precios** en `Data/{ACTIVO}.csv` (H1) y `Data_minuto/{ACTIVO}.csv` (M1). Los genera X0 al ejecutarse en Windows. Sin ellos el backtesting no tiene sobre qué correr.
2. **Scores fundamentales** en `resources/x2/x2_history.json` (los genera X2). Si faltan, X5 usa el contexto X2 vacío (no rompe, pero el modelo aprende con menos señal).
3. **Config de la versión de backtesting** en `resources/x4/version{V}/config_{V}.py` (define `valores`, `fecha_inicio`, capital, etc.).
4. **Dependencias Python**: `lightgbm`, `torch`, `optuna` (además de numpy/pandas). Si falta alguna, X5 lo avisa y ese pedazo se omite (no crashea).

## Paso 1 — Ver el estado inicial (opcional, para orientarse)

```bash
python scripts/X5_macro_brain.py --status
```

Muestra, por activo, cuántas OC hay en el store y qué modelo está activo. Al principio verás **0 OC** y **`untrained`** en los 6 — es lo esperado: el chef todavía no cocinó nada.

## Paso 2 — Recolectar datos (backtesting paralelo) + auto-entrenar

**Este es el paso principal de la Fase 1.** Un solo comando:

```bash
python scripts/X5_macro_brain.py --recolectar --version V1
```

**Qué pasa por dentro (peras y manzanas):**

- X5 lanza **6 workers en paralelo**, uno por activo. Cada worker es como un chef independiente cocinando en su propia cocina.
- Cada worker corre un **ciclo** = un backtest completo desde `fecha_inicio` hasta el final de los datos, simulando la lógica de X1 vela a vela (coloca buy limits, abre/cierra posiciones, trailing stop). Cada vez que una orden cierra (OC) o cada 4 velas con posiciones abiertas (registro periódico), **anota una fila en el cuaderno** (`resources/x5/{ACTIVO}_store.csv`).
- **Cuando un worker termina su ciclo, vuelve a empezar desde `fecha_inicio`** (reset), pero con parámetros distintos (ver "explore/exploit" abajo). Así acumula variedad de experiencias.
- Cada worker corre hasta `X5_N_CICLOS_BT` ciclos (config) o hasta juntar `X5_MIN_TRADES_FTT` OC.
- **Apenas un activo cruza `X5_MIN_TRADES_TRAIN` (500) OC, ese worker entrena su modelo** (`_entrenar`) sin esperar a los demás. Desde ese momento, sus ciclos "EXPLOIT" ya usan el modelo recién entrenado → **los params se van corrigiendo por activo**, que es exactamente lo que buscamos.

**Aislamiento (por qué no chocan los 6 en paralelo):** cada worker usa su propia carpeta de trabajo de X4 (`resources/x4/version{V}/resources_{V}_{ACTIVO}/`) para el checkpoint y el equity. El cuaderno (`{ACTIVO}_store.csv`) ya es por activo. Así 6 procesos escriben sin pisarse.

**Explore vs Exploit (por qué los params varían entre ciclos):**

```
Ciclo EXPLORE  (prob. X5_EXPLORATION_RATE = 30%): params ALEATORIOS dentro de los rangos.
Ciclo EXPLOIT  (70%): params = lo que recomienda el modelo (o baseline si aún no hay modelo).
```

Los ciclos EXPLORE generan peor P&L a propósito — su valor es **enseñarle al modelo qué NO funciona** en cada tipo de mercado. Sin exploración, el chef solo probaría sus recetas favoritas y nunca sabría si hay mejores (el "sesgo de selección", ver `x5_plan_redes_neuronales.md`).

**Qué verás en pantalla:** líneas prefijadas por activo, ej.:

```
  [BTCUSD] ciclo 1/20: 320 OC (Δ+320 desde el inicio)
  [ETHUSD] ciclo 1/20: 410 OC (Δ+410 desde el inicio)
  [BTCUSD] ciclo 2/20: 660 OC (Δ+660 desde el inicio)   ← cruzó 500 → entrena solo
  ...
  ✔ [BTCUSD] terminó: 0 → 5200 OC
```

> **Nota de tiempo**: el **primer ciclo de cada activo es lento** porque hace *cold start* (recalcula soportes desde cero). Los siguientes reutilizan la cache de soportes del activo.

## Paso 3 — Confirmar que hay modelos entrenados

```bash
python scripts/X5_macro_brain.py --status
```

Ahora deberías ver activos en `lgbm` (500–5000 OC) o `ftt` (>5000 OC), con "modelo ok". Las métricas de cada entrenamiento quedan en `resources/x5/Performance/{ACTIVO}_performance.json` (MAE, MSE, MAPE, R² para train y test).

## Paso 4 — Pedir la recomendación de params (inferir)

```bash
python scripts/X5_macro_brain.py --infer
```

Lee el contexto actual (X2+X3), busca los params que maximizan `retorno_pct` predicho y los escribe en `config/active_parameters.json`. Un activo que siga en `untrained` sale con sus valores de `config.py` (baseline) — X1 los ignorará y usará `config.py` para ese activo.

- Reentrenar antes de inferir: `python scripts/X5_macro_brain.py --infer --train`
- Un solo activo: `python scripts/X5_macro_brain.py --infer --activo BTCUSD`

## Paso 5 — Activar Fase 2 (cuando confíes en el modelo)

Recién cuando las métricas de `Performance/` sean razonables (R² test positivo, MAE estable), cambiar en `config.py`:

```python
TIPO_EJECUCION = "din"   # antes "est"
```

Con esto, X1 lee `active_parameters.json` y aplica los params por activo. Los activos en `untrained` caen back a `config.py` automáticamente — la transición es por activo, no todo-o-nada.

## Resumen ultra-corto

```bash
# 1. ¿cómo estoy?
python scripts/X5_macro_brain.py --status
# 2. generar datos + entrenar (el paso largo; corre en paralelo los 6 activos)
python scripts/X5_macro_brain.py --recolectar --version V1
# 3. recomendar params
python scripts/X5_macro_brain.py --infer
# 4. (cuando confíes) activar Fase 2 en config.py: TIPO_EJECUCION = "din"
```

## Preguntas frecuentes

- **¿Tengo que llamar `--train` aparte?** No. `--recolectar` ya entrena solo cuando cada activo cruza el umbral. `--train` es solo la casilla de `--infer` para forzar un reentreno puntual.
- **¿`--recolectar` borra lo anterior?** No borra el store (acumula). Cada ciclo de backtest sí parte de cero en la simulación (reset del checkpoint de X4), pero las filas del cuaderno se **agregan**, no se reemplazan.
- **¿Puedo cortar y retomar?** Sí. El store persiste en disco. Al relanzar `--recolectar`, cada worker sigue sumando OC sobre lo que ya había.
- **¿Por qué en paralelo y no uno por uno?** Para que los 6 activos avancen a la vez y cada uno corrija sus params apenas tenga datos, en vez de esperar a que termine BTCUSD para empezar ETHUSD.
