# X4 Backtester — Plan de implementación

> **Siglas de órdenes** (usadas en todo este documento):
> - **OE** — Orden en Espera: buy limit colocada en un nivel de soporte, esperando que el precio baje hasta ella.
> - **OA** — Orden Abierta: posición activa (la OE fue ejecutada, el precio tocó el soporte y entró la compra).
> - **OC** — Orden Cerrada: posición que ya cerró, ya sea por trailing stop, PERDIDA_MAX o stop loss.

## 1. Objetivo

Simular la estrategia completa (X0 + lógica de X1) sobre datos históricos, desde una fecha configurable hasta el presente. La simulación avanza vela H1 a vela H1, recalcula soportes periódicamente, gestiona un libro de órdenes en memoria, y registra cada trade cerrado en un store JSON. Este store es la fuente de training data para X5 y X6.

X4 **no importa ni llama a X1**. Reimplementa su lógica de trading sin MT5.

**Parámetros estáticos (V1)**: cada versión de backtesting tiene su propia `config_V[N].py` con todos los parámetros fijos al momento de crearla. Nada los mueve durante la ejecución. En el futuro, cuando X6 esté disponible, se añadirá backtesting dinámico (parámetros cambiando período a período según output de X6); el diseño actual debe ser escalable a ese caso.

---

## 2. Versión V1

| Parámetro              | Valor V1                       |
|------------------------|--------------------------------|
| `version`              | `'V1'`                         |
| `valores`              | `['BTCUSD', 'ETHUSD']`         |
| `n_sizes`              | `{'BTCUSD': 70, 'ETHUSD': 70}` |
| `fecha_inicio`         | `'2026-01-10'`                 |
| `fecha_fin`            | `'F'`  (hasta última vela disponible; no cierra posiciones al terminar) |
| `capital_inicial`      | `3000.0` USD                   |
| `PERDIDA_MAX_BT`       | `120.0` USD                    |
| `MARGEN_LIBRE_MIN_BT`  | `50.0` USD                     |
| `delta_recalculo_soportes` | `1` (días)                 |
| `hora_recalculo`       | `23` (UTC)                     |
| Algoritmo (K, N_EXP, LAMBDA, M, …) | Fijados explícitamente en `config_V1.py` (valores de producción al 2026-01-10) |

Spread y slippage: ignorados en V1 (entrada exacta al precio del soporte o al precio de gap).

### Registro en `config.py` (el principal, no `config_V1.py`)

Además de `config_V1.py`, el `config.py` del proyecto debe tener:

```python
# ─── X4 — Backtester ─────────────────────────────────────────────────────────
X4_VERSION_ACTIVA = 'V1'
X4_VERSIONES = {
    'V1': {'fecha_inicio': '2026-01-10', 'fecha_fin': 'F'},
}
```

- `X4_VERSION_ACTIVA`: versión que usa X4 si no se pasa `--version` en CLI.
- `X4_VERSIONES`: registro consultable de todas las versiones con sus rangos de fechas. Las fechas deben coincidir con `fecha_inicio`/`fecha_fin` en el `config_{V}.py` correspondiente — permiten consultar el rango sin importar el módulo de versión.
- `_cargar_config(version)` usa `importlib` para cargar `resources/x4/version{V}/config_{V}.py`. Si la versión ya tiene checkpoint guardado en `resources_V1/checkpoint.json`, la simulación retoma desde el último timestamp procesado (sin `--reset`).

---

## 3. Estructura de carpetas

```
resources/x4/
  versionV1/
    config_V1.py                   # parámetros fijados de la versión V1
    resources_V1/
      conjuntos_N/                 # soportes bt para esta versión
        BTCUSD_70.json
        BTCUSD_70_bt_delta.json
        ETHUSD_70.json
        ETHUSD_70_bt_delta.json
      logs/                        # convergencia del optimizador bt
        BTCUSD_70.json
        ETHUSD_70.json
      trades.json                  # store acumulativo de trades cerrados
      events.json                  # log de eventos de órdenes (ver sección 9)
      equity_global.csv            # capital total de la cuenta hora a hora (ver sección 9)
      equity_activos.csv           # GC / GA / GT por (activo, hora) (ver sección 9)
      checkpoint.json              # estado de la simulación (para reanudar)
scripts/X4_backtester.py          # script principal
```

**Soportes de producción**: `resources/conjuntos_N/` pasa a ser plana (sin subdirectorios `prod/` ni `bt/`). Como consecuencia:
- `CARPETA_N_PROD` en `config.py` pasa de `.../conjuntos_N/prod` a `.../conjuntos_N`.
- `CARPETA_N_BT` se elimina de `config.py`; cada versión de X4 define la suya propia (ver sección 4).

Este cambio se ejecuta como primera tarea de la fase 1.

---

## 4. config_V1.py

```python
# resources/x4/versionV1/config_V1.py
# Parámetros fijados al crear V1. Sin imports de config.py — garantiza reproducibilidad
# aunque la configuración de producción cambie después.

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent  # raíz del proyecto

# ─── Versión y activos ───────────────────────────────────────────────────────
version  = 'V1'
valores  = ['BTCUSD', 'ETHUSD']
n_sizes  = {'BTCUSD': 70, 'ETHUSD': 70}

# ─── Fechas ──────────────────────────────────────────────────────────────────
fecha_inicio = '2026-01-10'
fecha_fin    = 'F'   # 'F' = hasta la última vela disponible; no cierra posiciones al terminar

# ─── Capital y riesgo ────────────────────────────────────────────────────────
capital_inicial      = 3000.0   # USD
PERDIDA_MAX_BT       = 120.0    # USD
MARGEN_LIBRE_MIN_BT  = 50.0     # USD — buffer mínimo de margen libre para abrir/ejecutar OE

# ─── Recálculo de soportes ───────────────────────────────────────────────────
delta_recalculo_soportes = 1    # días (puede ser fraccionario, ej. 0.5 = 12h)
hora_recalculo           = 23   # hora UTC (aplica solo cuando delta_recalculo_soportes es entero)

# ─── Algoritmo de soportes (parámetros de X0 fijados para esta versión) ─────
K    = 1
N_EXP = 1.3
parametros_soportes = {
    'y': True, 'w': True, 'h_dist': True, 'v': True, 'f': True,
}
LAMBDA            = 1 / 5
M                 = 30
M_COARSE          = 5
DELTA_INICIAL     = 1e-4
FACTOR_DELTA      = 0.7
BLOQUE_DISTANCIAS = 2000
MAX_ITERS         = 10000

# ─── Trading ─────────────────────────────────────────────────────────────────
A = 6     # ganancia mínima en USD para activar el primer SL ganador
B = 2     # distancia en USD (normalizada por L) que mantiene el SL bajo el precio actual
LOTAJES        = {'BTCUSD': 0.01, 'ETHUSD': 0.1}
UNITS          = {'BTCUSD': 1,    'ETHUSD': 1}
APALANCAMIENTO = {'BTCUSD': 400,  'ETHUSD': 400}

# ─── Rutas ───────────────────────────────────────────────────────────────────
_VERSION_DIR        = Path(__file__).parent
CARPETA_RESOURCES   = _VERSION_DIR / f'resources_{version}'
CARPETA_N_BT        = CARPETA_RESOURCES / 'conjuntos_N'
CARPETA_LOGS_BT     = CARPETA_RESOURCES / 'logs'
CARPETA_DATA        = BASE_DIR / 'Data'
CARPETA_DATA_MINUTO = BASE_DIR / 'Data_minuto'
```

---

## 5. Recálculo de soportes

### Dependencia directa de X0

X4 **importa** las funciones de búsqueda de soportes desde `X0_data_supports.py` — no las duplica. Así, cualquier cambio al algoritmo (scoring, optimizador, factores) se propaga automáticamente al backtester.

```python
# En X4_backtester.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from X0_data_supports import _procesar_valor_N, obtener_df_extremos, calcular_FO
```

El parámetro `fecha_hora_max` de `_procesar_valor_N` es lo que activa el modo backtesting: filtra los datos hasta ese timestamp y usa/actualiza el cache en `cfg.CARPETA_N_BT` en vez de `resources/conjuntos_N/`.

### Posiciones abiertas como soportes fijos (OA → `ordenes_abiertas_bt`)

Al recalcular soportes durante el backtest, X4 debe pasar las posiciones actualmente abiertas (OA) como soportes fijos al optimizador — igual que en producción se pasan las posiciones reales de MT5.

```python
# En _recalcular_soportes (X4), antes de llamar a _procesar_valor_N:
oa_bt = [precio_ap for precio_ap in estado['por_activo'][activo]['OA'].keys()]

_procesar_valor_N(
    activo, N, cfg.CARPETA_DATA, CARPETA_N_PROD, cfg.CARPETA_N_BT,
    fecha_hora_max=ts_actual,
    ordenes_abiertas_bt=oa_bt,
    ...
)
```

`_procesar_valor_N` ya acepta `ordenes_abiertas_bt: list = []` y lo pasa al optimizador cuando `es_bt=True`.

El recálculo corre en paralelo por `(valor, N)` vía `ProcessPoolExecutor`, igual que en producción.

**Cold start**: si al iniciar el backtest no existen soportes en `cfg.CARPETA_N_BT` para algún `(activo, N)`, se ejecuta un recálculo completo con `fecha_hora_max = fecha_inicio` **antes de entrar al loop principal**. Sin soportes, no hay órdenes posibles. Este paso puede ser lento — se loguea explícitamente.

**Cuándo recalcular durante el loop**:

```python
horas_desde_recalculo = (ts_actual - ts_ultimo_recalculo).total_seconds() / 3600
umbral_horas = cfg.delta_recalculo_soportes * 24

if cfg.delta_recalculo_soportes == int(cfg.delta_recalculo_soportes):
    disparar = horas_desde_recalculo >= umbral_horas and ts_actual.hour == cfg.hora_recalculo
else:
    disparar = horas_desde_recalculo >= umbral_horas
```

Cuando se recalcula: **la vela actual queda congelada** (no se procesa trading en ella). La simulación avanza a la siguiente vela con los nuevos soportes ya cargados. Las OE que quedaron en soportes eliminados se limpian en el paso A de esa siguiente vela (con evento `OE_eliminada` registrado).

**Delta adaptativo**:
- Archivo: `cfg.CARPETA_N_BT / '{valor}_{N}_{version}_bt_delta.json'`
- Si el optimizador convergió → `delta_next = FACTOR_DELTA * delta_actual`
- Si no convergió (salió por `max_iters`) → no se reduce

---

## 6. Lógica de trading (mirror de X1)

El estado de trading vive en memoria dentro del estado compartido de la simulación. No hay MT5.

### Estado en memoria

```python
estado = {
    'capital': 3000.0,
    'GC_global': 0.0,
    'por_activo': {
        'BTCUSD': {
            'soportes': [],
            'OE': {},    # {precio: {lote, ts_creacion}}
            'OA': {},    # {precio_apertura: {lote, sl, ts_apertura, ganancia_max, drawdown_max, usa_intravela}}
            'GC': 0.0,
        },
        ...
    },
    'ts_ultimo_recalculo': None,
    'ts_ultimo_checkpoint': None,
}
```

### Métricas de cuenta (hora a hora)

Se calculan al cierre de cada vela H1 sobre el estado en memoria con `_calcular_estado_cuenta`.

```
balance       = estado['capital']
GA_global     = Σ (candle.Close − precio_ap) × lote × UNITS[activo]   para todo activo, toda OA
equity        = balance + GA_global
margen_usado  = Σ precio_ap × lote × UNITS[activo] / APALANCAMIENTO   para todo activo, toda OA
margen_libre  = equity − margen_usado
margin_level  = (equity / margen_usado × 100)  si margen_usado > 0, else None
```

**Guard para abrir/ejecutar órdenes**: antes de ejecutar una OE (paso B) y antes de crear una nueva OE (paso F):

```python
margen_nueva = precio_soporte * lote * UNITS[activo] / APALANCAMIENTO
puede_operar = margen_libre - margen_nueva >= MARGEN_LIBRE_MIN_BT
```

Si `puede_operar` es `False`:
- Paso B: la OE se cancela (`OE_eliminada`, motivo: `margen_insuficiente`).
- Paso F: la OE no se crea.

---

### Por cada vela H1 (para cada activo)

**A. Limpiar OE no válidas** — cancela órdenes cuyo precio ya no está en `soportes`.
→ Registra evento `OE_eliminada` por cada una.

**B. Verificar ejecuciones de OE** — con manejo de gap de mercado:

*Gap de mercado*: si `candle.Open <= precio_OE` para alguna OE activa, el precio de apertura ya está por debajo de ese soporte — el precio nunca bajó gradualmente hasta él. Todas las OE con `precio_OE >= candle.Open` se ejecutan simultáneamente al precio de la menor de ellas (`precio_gap = min(oes_gap)`).

```
Ejemplo: OEs en [130, 120, 110, 100], cierre previo = 140, candle.Open = 105.
  oes_gap = [130, 120, 110]  (precio_OE >= 105)
  precio_gap = 110
  Las tres se ejecutan a 110 (no a sus precios individuales).
  La OE en 100 se evalúa normalmente con candle.Low (no está en el gap).
```

El guard de margen se aplica a cada OE del gap individualmente en orden ascendente de precio. Si una no pasa, se cancela (`OE_eliminada`, motivo: `margen_insuficiente`); las demás del gap siguen ejecutándose a `precio_gap`.

*Caso normal* (sin gap): una OE en precio `Pi` se ejecuta si `candle.Low <= Pi`. Verificar guard de margen; si falla → cancelar OE. Si pasa → la posición entra a `OA` con `sl=0` a precio `Pi`.
→ Registra evento `OE_ejecutada`.

**C. Trailing stop** — para cada posición en `OA`:
- `L = lote * UNITS[activo]`
- Si `sl == 0` y `(candle.High - Pi) * L >= A` → activa SL: `sl = candle.High - B/L`, repone OE en `Pi`.
- Si `sl > 0` y `candle.High - B/L > sl` → mueve SL al alza.
→ Registra evento `SL_cambiado` cuando el SL se activa o sube.

**D. Controlar PERDIDA_MAX** — para cada posición en `OA`:
- `perdida = (Pi - candle.Low) * L`
- Si `perdida > PERDIDA_MAX_BT` → cerrar posición en `candle.Low`, registrar trade.
→ Registra evento `posicion_cerrada` (motivo: `perdida_max`).

**E. Cierre por SL tocado** — para cada posición con `sl > 0`:
- Si `candle.Low <= sl` → cerrar posición en `sl`, registrar trade.
→ Registra evento `posicion_cerrada` (motivo: `trailing_stop`).

**F. Crear nuevas OE** — usando `candle.Close` como precio de referencia:
- Para cada soporte `Pi` en `soportes` no presente en OA ni OE:
  - Si `(candle.Close - Pi) * L >= A`:
    - Verificar guard de margen. Si falla → no crear OE en ese soporte.
    - Si pasa → crear OE en `Pi`. El margen libre se reduce en `margen_nueva` para evaluar las OE siguientes del mismo ciclo.
→ Registra evento `OE_creada` por cada una que pase el guard.

**G. Snapshot de equity** — al final de cada vela H1:
- Registra fila en `equity_global.csv`.
- Para cada activo: registra `(ts, activo, GC, GA, GC+GA)` en `equity_activos.csv`.

**Fin de datos (`fecha_fin = 'F'`)**: cuando se agotan las velas de `datos_h1`, el loop termina. Las posiciones abiertas en ese momento **no se cierran** y **no se registra ningún trade con motivo `fin_backtest`**. Se guarda el checkpoint final con el estado completo.

> **Supuesto de orden dentro de la vela (sin intra-vela)**: el flujo C → E implica que el TS se actualiza con `High` antes de verificar si `Low` toca el SL. En "velas de conflicto" esto es levemente optimista. La simulación intra-vela lo resuelve cuando el trigger se cumple.

---

## 7. Simulación intra-vela (M1)

Se activa cuando la resolución H1 no es suficiente para determinar qué ocurrió primero dentro de la vela.

### Cuándo se usa

```python
def _necesita_intravela(activo_estado, candle, L, A, B, PERDIDA_MAX_BT):
    OA = activo_estado['OA']
    OE = activo_estado['OE']
    rango = candle['High'] - candle['Low']

    for precio_ap, pos in OA.items():
        sl = pos['sl']
        if sl == 0:
            if rango * L >= A and (precio_ap - candle['Low']) * L >= PERDIDA_MAX_BT:
                return True
        else:
            sl_nuevo = candle['High'] - B / L
            if sl_nuevo > sl and candle['Low'] <= sl_nuevo:
                return True

    for precio_oe in OE:
        if candle['Low'] <= precio_oe:
            if rango * L >= A or (precio_oe - candle['Low']) * L >= PERDIDA_MAX_BT:
                return True

    return False
```

### Método

1. Seleccionar un índice `t` aleatorio en `Data_minuto/{activo}.csv` y tomar las 60 velas consecutivas `[t : t+60]`.
2. Escalar linealmente ese bloque para que encaje dentro del marco OHLC de la vela H1.
3. Reproducir las operaciones A→F sobre cada vela M1 en secuencia. Los eventos generados dentro de intra-vela se marcan con `"usa_intravela": true`.

Si `Data_minuto/` no tiene datos del activo, se degrada a lógica H1 pura (log de advertencia).

---

## 8. Store de trades (`trades.json`)

Lista de objetos JSON, uno por cada trade cerrado. Append-only.

```json
{
  "id": "BTCUSD_20260115T1000_94500.0",
  "version": "V1",
  "activo": "BTCUSD",
  "N": 70,
  "soporte_nivel": 94500.0,
  "timestamp_apertura": "2026-01-15T10:00:00",
  "precio_apertura": 94500.0,
  "lote": 0.01,
  "L": 0.01,
  "timestamp_cierre": "2026-01-16T08:00:00",
  "precio_cierre": 95200.0,
  "motivo_cierre": "trailing_stop",
  "retorno_usd": 70.0,
  "retorno_pct": 0.023,
  "duracion_velas_h1": 22,
  "drawdown_max_usd": -30.0,
  "ganancia_flotante_max_usd": 85.0,
  "capital_cuenta_apertura": 3150.0,
  "usa_intravela": false,
  "parametros": {
    "A": 6, "B": 2, "PERDIDA_MAX": 120.0,
    "N": 70, "K": 1.0, "LAMBDA": 0.2, "N_EXP": 1.3,
    "LOTAJE": 0.01, "UNITS": 1
  },
  "features_x2": null,
  "features_x3": null
}
```

`motivo_cierre` ∈ `{"trailing_stop", "perdida_max"}`.
Cuando `fecha_fin != 'F'` y el backtest llega a la fecha de corte, las posiciones abiertas se cierran con `motivo_cierre = "fin_backtest"` al `candle.Close` de la última vela. En V1 esto no aplica (`fecha_fin = 'F'`).

`features_x2` y `features_x3` quedan `null` en V1; X5/X6 los rellenarán.

---

## 9. Log de eventos (`events.json`) y curvas de equity

### events.json

Lista cronológica de todos los eventos de órdenes durante la simulación. Append-only.

**Campos comunes:**
```json
{
  "ts": "2026-01-15T10:00:00",
  "version": "V1",
  "activo": "BTCUSD",
  "tipo": "...",
  "usa_intravela": false
}
```

**Tipos de evento:**

`OE_creada`:
```json
{ "tipo": "OE_creada", "precio": 94500.0, "lote": 0.01 }
```

`OE_eliminada`:
```json
{ "tipo": "OE_eliminada", "precio": 93200.0, "motivo": "soporte_desactivado" }
```
(`motivo` ∈ `{"soporte_desactivado", "margen_insuficiente"}`)

`OE_ejecutada`:
```json
{ "tipo": "OE_ejecutada", "precio": 94500.0, "precio_ejecucion": 94500.0, "lote": 0.01,
  "ts_oe_creacion": "2026-01-14T08:00:00", "es_gap": false }
```
(`precio_ejecucion` difiere de `precio` cuando la orden se ejecuta por gap de mercado.)

`SL_cambiado`:
```json
{ "tipo": "SL_cambiado", "precio_apertura": 94500.0, "sl_anterior": 0, "sl_nuevo": 94350.0,
  "precio_max_vela": 94600.0 }
```

`posicion_cerrada`:
```json
{ "tipo": "posicion_cerrada", "precio_apertura": 94500.0, "precio_cierre": 94350.0,
  "motivo": "trailing_stop", "retorno_usd": -15.0, "lote": 0.01 }
```
(`motivo` ∈ `{"trailing_stop", "perdida_max"}`)

### equity_global.csv

Columnas: `ts`, `balance`, `equity`, `margen_usado`, `margen_libre`, `margin_level`, `n_OA`, `n_OE`.

```csv
ts,balance,equity,margen_usado,margen_libre,margin_level,n_OA,n_OE
2026-01-10T00:00:00,3000.0,3000.0,0.0,3000.0,,0,0
2026-01-10T01:00:00,3000.0,2987.5,945.0,2042.5,315.9,1,3
```

### equity_activos.csv

Columnas: `ts`, `activo`, `GC`, `GA`, `GT`.

```csv
ts,activo,GC,GA,GT
2026-01-10T00:00:00,BTCUSD,0.0,0.0,0.0
2026-01-10T00:00:00,ETHUSD,0.0,0.0,0.0
```

---

## 10. Checkpoint (`checkpoint.json`)

Se guarda cada 24 velas (configurable). Permite reanudar sin perder progreso.

```json
{
  "version": "V1",
  "ts_ultimo_procesado": "2026-03-15T10:00:00",
  "ts_ultimo_recalculo": "2026-03-14T23:00:00",
  "capital": 3210.0,
  "por_activo": {
    "BTCUSD": {
      "soportes": [94500.0, 93200.0],
      "OE": {"93200.0": {"lote": 0.01, "ts_creacion": "2026-03-14T12:00:00"}},
      "OA": {"94500.0": {"lote": 0.01, "sl": 94350.0, "ts_apertura": "2026-03-10T15:00:00",
                          "ganancia_max": 85.0, "drawdown_max": -12.0, "usa_intravela": false}}
    },
    "ETHUSD": { "soportes": [], "OE": {}, "OA": {} }
  }
}
```

---

## 11. Funciones principales

```
scripts/X4_backtester.py
├── _cargar_config(version)              → importa resources/x4/version{V}/config_{V}.py con importlib
├── _descargar_actualizar_datos(cfg)     → H1 + M1, solo Windows/MT5
├── _cargar_datos_h1(cfg)                → dict {activo: DataFrame OHLCV}
├── _cargar_datos_m1(cfg)                → dict {activo: DataFrame M1} (None si no existe)
├── _cargar_checkpoint(cfg)              → dict estado | None
├── _guardar_checkpoint(estado, cfg)
│
├── _recalcular_soportes(estado, datos_h1, ts_actual, cfg)
│     └── ProcessPoolExecutor → _procesar_valor_N() de X0 (importado)
│
├── _limpiar_OE(activo_estado, soportes)
├── _verificar_ejecuciones_OE(activo_estado, candle, cierre_previo, L, cfg)
│     └── detecta gap (candle.Open vs precio_OE), aplica precio_gap
├── _trailing_stop_sim(activo_estado, precio_max, L, A, B)
├── _controlar_perdida_max(activo_estado, precio_min, L, PERDIDA_MAX)
├── _cerrar_sl_tocados(activo_estado, precio_min)
├── _crear_OE(activo_estado, precio_ref, soportes, L, A, lote, cfg)
│
├── _calcular_estado_cuenta(estado, precios_cierre, cfg)
│     → {balance, equity, margen_usado, margen_libre, margin_level, n_OA, n_OE}
│
├── _trigger_intravela(activo_estado, candle, L, A, PERDIDA_MAX)
├── _escalar_bloque_m1(bloque_m1, candle_h1)
├── _simular_intravela(activo_estado, candle_h1, datos_m1, params)
│
├── _procesar_candle(candle, cierre_previo, activo, estado, datos_m1, trades_log, events_log, cfg)
│     └── decide: intra-vela o H1 puro → ejecuta A→G → append a trades_log y events_log
│
├── _registrar_trade(posicion, precio_cierre, motivo, ts, capital, cfg)  → dict
├── _registrar_evento(tipo, activo, ts, cfg, **kwargs)                   → dict
├── _append_eventos(events_log, cfg)
├── _calcular_GA(activo_estado, precio_actual, units)                     → float
├── _append_equity(ts, capital, estado, datos_candle, cfg)
│
└── ejecutar_backtest(cfg)               → loop principal
      1. descargar/actualizar datos (Windows/MT5 only; en Mac usar Data/ existente)
      2. cargar checkpoint o inicializar estado
      3. cold start: si no hay soportes en cfg.CARPETA_N_BT → recalcular con fecha_hora_max = fecha_inicio
      4. for ts, candle in datos_h1.iterrows() desde ts_ultimo_procesado:
           a. check recálculo → si sí: recalcular, congelar vela, continuar
           b. for activo in valores: _procesar_candle(candle, cierre_previo[activo], ...)
           c. cada 24 velas: _guardar_checkpoint(...)
      5. guardar checkpoint final + mensaje de tiempo total
         (si fecha_fin = 'F': posiciones abiertas quedan sin cerrar, sin fin_backtest)
```

---

## 12. CLI

```bash
python scripts/X4_backtester.py                        # usa X4_VERSION_ACTIVA de config.py
python scripts/X4_backtester.py --version V1
python scripts/X4_backtester.py --version V1 --reset   # ignora checkpoint, parte de cero
```

---

## 13. Secuencia de implementación

| Fase | Qué |
|------|-----|
| 1 | Crear estructura `resources/x4/versionV1/` + `config_V1.py`. Actualizar `config.py`: `CARPETA_N_PROD` sin `prod/`, eliminar `CARPETA_N_BT`. |
| 2 | `_cargar_datos_h1` + `_cargar_datos_m1` + `_cargar_config` con importlib |
| 3 | `_recalcular_soportes` — importar y envolver funciones de X0; cold start al inicio |
| 4 | `_limpiar_OE`, `_verificar_ejecuciones_OE` (con gap), `_trailing_stop_sim`, `_controlar_perdida_max`, `_cerrar_sl_tocados`, `_crear_OE` |
| 5 | `_procesar_candle` H1 puro + `_registrar_trade` + `trades.json` |
| 6 | `_registrar_evento` + `events.json` + `_calcular_GA` + `_append_equity` + CSVs de equity |
| 7 | Checkpoint save/load + argparse + loop principal `ejecutar_backtest` |
| 8 | `_trigger_intravela` + `_escalar_bloque_m1` + `_simular_intravela` |
| 9 | Prueba end-to-end V1 en Mac (sin MT5: datos ya en `Data/` y `Data_minuto/`) |

---

## 14. Qué queda fuera de V1 (para V2+)

- Parámetros dinámicos por período (X6 — backtesting dinámico)
- Features X2/X3 en el trade store (X5)
- Múltiples N simultáneos por activo en producción
- Modelado de spread/slippage
- Soporte para acciones US (solo cambia `valores` y `n_sizes` en config)

---

_Última actualización: 2026-06-20_
