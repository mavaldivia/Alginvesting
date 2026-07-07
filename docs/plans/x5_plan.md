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
5. Al terminar el recorrido, actualiza los parámetros y reinicia desde el día 0 con el set actualizado

**Acumulación de datos**: el store acumula todas las vueltas sin truncar. Los registros de ciclos con params peores son igualmente valiosos — más variedad de (contexto, params, resultado) = más relaciones causa-efecto que B puede aprender.

### Deltas registrados (en vez de P&L absoluto)

Para aislar la señal del ruido de capital:
- `delta_pnl_cerrado`: P&L de la orden que cierra en ese momento (USD)
- `delta_pnl_abierto_activo`: suma del P&L flotante de posiciones abiertas del activo al momento del cierre
- `retorno_pct`: `delta_pnl_cerrado / (precio_entrada * lote)` — normalizado al tamaño de la posición

Estos deltas son la variable objetivo que el modelo (X6) aprenderá a predecir como función del contexto y los parámetros.

---

## Store de trades — dataset de entrenamiento

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
└── models/
    ├── {ACTIVO}_lgbm.pkl       # modelo LightGBM (V1); se sobreescribe en cada reentrenamiento
    └── {ACTIVO}_ftt.pt         # modelo FT-Transformer (V2); idem

config/
└── active_parameters.json      # output de X5; leído por X0 y X1
```

`model_status` va dentro de `active_parameters.json` (ver sección 5 de Sugerencias). No hay un archivo de estado separado.

### Estructura del código (`X5_macro_brain.py`)

El script tiene cuatro modos de uso:

```
python X5_macro_brain.py --vela      # ciclo completo por vela: capturar + actualizar modelo + inferir params
python X5_macro_brain.py --train     # reentrenamiento profundo (solo LightGBM o cuando se quiere forzar)
python X5_macro_brain.py --infer     # solo inferir params (sin capturar ni entrenar)
python X5_macro_brain.py --status    # mostrar n_trades por activo y modelo activo
```

**¿Qué hace cada modo?**

- **`--vela`** — Es el modo normal de producción. Corre al cierre de cada vela H1 y realiza los 4 pasos del ciclo:
  1. Captura P&L flotante + trades cerrados → escribe nuevos registros en el store
  2. Lee contexto actual (X2 + X3)
  3. Actualiza el modelo con los nuevos datos (online si Red Neuronal, batch ligero si LightGBM)
  4. Infiere los mejores params para el activo y escribe `config/active_parameters.json`

  En Fase 2, X1 llama a `--vela` automáticamente en cada cierre de vela. En Fase 1, se llama manualmente (o via cron).

- **`--train`** — Reentrenamiento profundo (completo, desde cero con todos los datos del store). Útil cuando se quiere mejorar el modelo con una corrida más costosa y exhaustiva. Solo necesario en LightGBM cuando el dataset ha crecido mucho; con Red Neuronal el aprendizaje online del `--vela` ya lo hace continuamente.

- **`--infer`** — Solo inferir params con el modelo ya cargado, sin capturar datos ni actualizar el modelo. Útil para recalcular params sin esperar al cierre de vela (p.ej. al arrancar el sistema en medio de la sesión).

- **`--status`** — Dashboard de diagnóstico. Muestra en pantalla cuántos registros tiene el store por activo y qué modelo está activo para cada uno. No escribe nada.

**Ejemplo concreto de uso típico (Fase 1 — manual):**

```
Lunes 09:00  → python X5_macro_brain.py --vela    # vela de las 08:00 cerró → captura + infiere
Lunes 10:00  → python X5_macro_brain.py --vela    # siguiente vela
Lunes 11:00  → python X5_macro_brain.py --vela    # siguiente vela
...
Cuando el store creció mucho:
               python X5_macro_brain.py --train   # reentrenamiento profundo ocasional
```

**Ejemplo en Fase 2 (automático desde X1):**

```
X1 detecta cierre de vela H1
  → llama X5_macro_brain.py --vela en subprocess
  → X5 actualiza store + modelo + params
  → X1 lee config/active_parameters.json para la siguiente vela
```

**Funciones principales:**

```python
_cargar_store(activo: str) -> pd.DataFrame
    # Lee resources/x5/{ACTIVO}_store.csv. Retorna DataFrame vacío si no existe.

_seleccionar_tipo_modelo(n_trades: int) -> str
    # 'untrained' si n_trades < X5_MIN_TRADES_TRAIN
    # 'lgbm'      si X5_MIN_TRADES_TRAIN <= n_trades < X5_MIN_TRADES_FTT
    # 'ftt'       si n_trades >= X5_MIN_TRADES_FTT

_preparar_features(store: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]
    # Separa X (features) e Y (retorno_pct) del store.
    # Aplica ponderación temporal exponencial (sample_weight).
    # Mismo preproceso para lgbm y ftt — misma tabla, mismo contrato.

_entrenar(activo: str, store: pd.DataFrame, tipo: str) -> modelo
    # Entrena lgbm o ftt según tipo. Guarda en resources/x5/models/.
    # Si tipo == 'lgbm': LightGBMRegressor; si 'ftt': FTTransformer.

_inferir_params(activo: str, modelo, contexto_x2_x3: dict) -> dict
    # Fija el vector de contexto y busca los config_params que maximizan retorno_pct.
    # lgbm: búsqueda con Optuna (N_OPTUNA_TRIALS evaluaciones). Optuna es un optimizador
    #        bayesiano: aprende qué zonas del espacio de params son prometedoras y concentra
    #        los intentos ahí, en vez de probar todas las combinaciones posibles.
    # ftt:  gradient ascent sobre los inputs de params: el gradiente se propaga desde la
    #        salida del modelo hacia los valores de params de entrada (no hacia los pesos).
    # Aplica airbag si drawdown_4_velas < -AIRBAG_THRESHOLD[activo].
    # Retorna dict con los params optimizados para ese activo.

_leer_contexto_actual(activo: str) -> dict
    # Lee el snapshot más reciente de X2 (resources/x2/scores.json)
    # y X3 (resources/x3/{ACTIVO}.csv, última fila).

_escribir_active_parameters(params_por_activo: dict, model_status: dict)
    # Escribe config/active_parameters.json con los params por activo
    # y el campo model_status por activo ('untrained'|'lgbm'|'ftt').
```

**Flujo principal (`--train` + `--infer`) — Fase 1:**

En Fase 1 X5 se ejecuta manualmente. X1 no lo llama ni lee su output.

```python
params_por_activo = {}
model_status = {}

for activo in VALORES:
    store = _cargar_store(activo)
    n = len(store)
    tipo = _seleccionar_tipo_modelo(n)   # 'untrained' | 'lgbm' | 'ftt'

    if tipo == 'untrained':
        params_por_activo[activo] = _params_baseline(activo)   # desde config.py
        model_status[activo] = 'untrained'
        continue

    modelo = _entrenar(activo, store, tipo)                    # solo en --train
    contexto = _leer_contexto_actual(activo)
    params = _inferir_params(activo, modelo, contexto)         # solo en --infer
    params_por_activo[activo] = params
    model_status[activo] = tipo

_escribir_active_parameters(params_por_activo, model_status)
# En Fase 1, este JSON se escribe pero X1/X0 no lo leen todavía.
# La activación por activo (Fase 2) es una decisión manual.
```

Cada activo es completamente independiente. Si BTCUSD ya tiene 6000 trades y usa FTT, y TSLA tiene 400 y está UNTRAINED, cada uno sigue su propio camino. En Fase 2, X1 chequeará `model_status[activo]` para decidir si usa `config.py` o el JSON — activo por activo, sin afectar a los demás.

**Frecuencia de reentrenamiento en Fase 1:** manual o por cron externo. En Fase 2, el ciclo `--vela` actualiza el modelo en cada vela (online para NN, batch ligero para LightGBM). El `--train` profundo es opcional y se corre manualmente cuando el dataset creció significativamente.

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
