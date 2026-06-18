# X4 Backtester — Plan de implementación

## 1. Objetivo

Simular la estrategia completa (X0 + lógica de X1) sobre datos históricos, desde una fecha configurable hasta el presente. La simulación avanza vela H1 a vela H1, recalcula soportes periódicamente, gestiona un libro de órdenes en memoria, y registra cada trade cerrado en un store JSON. Este store es la fuente de training data para X5 y X6.

X4 **no importa ni llama a X1**. Reimplementa su lógica de trading sin MT5.

---

## 2. Versión V1

| Parámetro              | Valor V1                       |
|------------------------|--------------------------------|
| `version`              | `'V1'`                         |
| `valores`              | `['BTCUSD', 'ETHUSD']`         |
| `n_sizes`              | `{'BTCUSD': 70, 'ETHUSD': 70}` |
| `fecha_inicio`         | `'2026-01-10'`                 |
| `fecha_fin`            | `'F'`  (hasta última vela disponible) |
| `capital_inicial`      | `3000.0` USD                   |
| `PERDIDA_MAX`          | `120.0` USD                    |
| `delta_recalculo_soportes` | `1` (días; ver sección 5)  |
| `hora_recalculo`       | `23`  (UTC)                    |
| `MARGEN_LIBRE_MIN_BT`  | `50.0` USD (buffer mínimo de margen libre para abrir/ejecutar OE) |
| `A`, `B`, `LOTAJES`, `UNITS`, `APALANCAMIENTO`, `K`, `N_EXP`, `LAMBDA`, `M`, … | Heredados de `config.py` |

Spread y slippage: ignorados en V1 (entrada exacta al precio del soporte).

---

## 3. Estructura de carpetas

```
x4_backtesting/
  config/
    config_V1.py          # parámetros de la versión V1
  output/
    V1/
      trades.json         # store acumulativo de trades cerrados
      events.json         # log de eventos de órdenes (ver sección 9)
      equity_global.csv   # capital total de la cuenta hora a hora (ver sección 9)
      equity_activos.csv  # GC / GA / GT por (activo, hora) (ver sección 9)
      checkpoint.json     # estado de la simulación (para reanudar)
  logs/
    V1/
      BTCUSD_70.json      # convergencia del optimizador por (activo, N)
      ETHUSD_70.json
X4_backtester.py          # script principal (en scripts/)
```

`conjuntos_N/bt/` ya existe y almacena los soportes calculados vela a vela, junto al delta adaptativo `{valor}_{N}_{version}_bt_delta.json`.

---

## 4. config_V1.py

```python
# x4_backtesting/config/config_V1.py

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from config import (
    K, N_EXP, parametros_soportes, LAMBDA, M, M_COARSE,
    DELTA_INICIAL, FACTOR_DELTA, BLOQUE_DISTANCIAS, MAX_ITERS,
    A, B, LOTAJES, UNITS, APALANCAMIENTO, CARPETA_DATA,
)
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent

version              = 'V1'
valores              = ['BTCUSD', 'ETHUSD']
n_sizes              = {'BTCUSD': 70, 'ETHUSD': 70}
fecha_inicio         = '2026-01-10'
fecha_fin            = 'F'   # 'F' = hasta la última vela disponible

capital_inicial      = 3000.0   # USD
PERDIDA_MAX_BT       = 120.0    # USD (sobreescribe el de config.py)
MARGEN_LIBRE_MIN_BT  = 50.0    # USD — margen libre mínimo para crear/ejecutar una OE

# Frecuencia de recálculo de soportes en backtesting.
# Unidad: días (puede ser < 1, ej. 0.5 = cada 12 horas).
# Cuando es entero, el recálculo ocurre a hora_recalculo UTC para evitar
# recalcular en medio de una sesión activa (para crypto: menor volatilidad a las 23h UTC).
delta_recalculo_soportes = 1    # días
hora_recalculo           = 23   # hora UTC (solo aplica cuando delta_recalculo_soportes es entero)

CARPETA_DATA_MINUTO  = BASE_DIR / 'Data_minuto'
CARPETA_OUTPUT       = BASE_DIR / 'x4_backtesting' / 'output' / version
CARPETA_LOGS_BT      = BASE_DIR / 'x4_backtesting' / 'logs' / version
CARPETA_N_BT         = BASE_DIR / 'conjuntos_N' / 'bt'
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

El parámetro `fecha_hora_max` de `_procesar_valor_N` es lo que activa el modo backtesting: filtra los datos hasta ese timestamp y usa/actualiza el cache en `conjuntos_N/bt/` en vez de `conjuntos_N/prod/`.

### Posiciones abiertas como soportes fijos (OA → `ordenes_abiertas_bt`)

Al recalcular soportes durante el backtest, X4 debe pasar las posiciones actualmente abiertas (OA) como soportes fijos al optimizador — igual que en producción se pasan las posiciones reales de MT5.

Una OA es una buy limit que ya fue tocada por el precio y está activa en la simulación (no es una OE pendiente). Su precio no debe moverse durante el recálculo porque ya hay capital comprometido ahí.

```python
# En _recalcular_soportes (X4), antes de llamar a _procesar_valor_N:
oa_bt = [precio_ap for precio_ap in estado['por_activo'][activo]['OA'].keys()]

_procesar_valor_N(
    activo, N, cfg.CARPETA_DATA, cfg.CARPETA_N_PROD, cfg.CARPETA_N_BT,
    fecha_hora_max=ts_actual,
    ordenes_abiertas_bt=oa_bt,   # precios de posiciones abiertas en la simulación
    ...
)
```

`_procesar_valor_N` ya acepta `ordenes_abiertas_bt: list = []` y lo pasa al optimizador cuando `es_bt=True` (en producción usa `ordenes_activas` de MT5 en su lugar).

El recálculo corre en paralelo por `(valor, N)` vía `ProcessPoolExecutor`, igual que en producción.

**Cold start**: si al iniciar el backtest no existen soportes en `conjuntos_N/bt/` para algún `(activo, N, version)`, se ejecuta un recálculo completo con `fecha_hora_max = fecha_inicio` **antes de entrar al loop principal**. Sin soportes, no hay órdenes posibles. Este paso puede ser lento (cold start del optimizador) — se loguea explícitamente.

**Cuándo recalcular durante el loop**:

```python
horas_desde_recalculo = (ts_actual - ts_ultimo_recalculo).total_seconds() / 3600
umbral_horas = delta_recalculo_soportes * 24

if delta_recalculo_soportes == int(delta_recalculo_soportes):
    # Solo a la hora exacta (ej. 23:00 UTC)
    disparar = horas_desde_recalculo >= umbral_horas and ts_actual.hour == hora_recalculo
else:
    disparar = horas_desde_recalculo >= umbral_horas
```

Cuando se recalcula: **la vela actual queda congelada** (no se procesa trading en ella). La simulación avanza a la siguiente vela con los nuevos soportes ya cargados. Las OE que quedaron en soportes eliminados se limpian en el paso A de esa siguiente vela (con evento `OE_eliminada` registrado).

**Delta adaptativo** (igual que producción):
- Archivo: `conjuntos_N/bt/{valor}_{N}_{version}_bt_delta.json`
- Si el optimizador convergió → `delta_next = FACTOR_DELTA * delta_actual`
- Si no convergió (salió por `max_iters`) → no se reduce

---

## 6. Lógica de trading (mirror de X1)

El estado de trading vive en memoria dentro del estado compartido de la simulación. No hay MT5.

### Estado en memoria

```python
estado = {
    'capital': 3000.0,             # balance corriente (se actualiza al cerrar cada trade)
    'GC_global': 0.0,              # suma de GC de todos los activos (evita recomputar en cada vela)
    'por_activo': {
        'BTCUSD': {
            'soportes': [],        # lista de floats (N soportes actuales)
            'OE': {},              # ordenes en espera: {precio: {lote, ts_creacion}}
            'OA': {},              # posiciones abiertas: {precio_apertura: {lote, sl, ts_apertura,
                                   #                       ganancia_max, drawdown_max, usa_intravela}}
            'GC': 0.0,             # ganancia/pérdida cerrada acumulada para este activo (USD)
        },
        ...
    },
    'ts_ultimo_recalculo': None,
    'ts_ultimo_checkpoint': None,
}
```

### Métricas de cuenta (hora a hora)

Se calculan al cierre de cada vela H1 sobre el estado en memoria. No se persisten en `estado` — se computan on-the-fly con `_calcular_estado_cuenta`.

```
balance       = estado['capital']
GA_global     = Σ (candle.Close − precio_ap) × lote × UNITS[activo]   para todo activo, toda OA
equity        = balance + GA_global
margen_usado  = Σ precio_ap × lote × UNITS[activo] / APALANCAMIENTO   para todo activo, toda OA
margen_libre  = equity − margen_usado
margin_level  = (equity / margen_usado × 100)  si margen_usado > 0, else None
```

`balance` es el capital "en papel" (ya realizó las pérdidas y ganancias cerradas). `equity` es el valor real de la cuenta incluyendo P&L flotante. `margin_level` < 100% significa que `equity < margen_usado` — situación de margin call; en V1 se loguea como warning pero no cierra posiciones automáticamente.

**Guard para abrir/ejecutar órdenes**: antes de ejecutar una OE (paso B) y antes de crear una nueva OE (paso F), se verifica:

```python
margen_nueva = precio_soporte * lote * UNITS[activo] / APALANCAMIENTO
puede_operar = margen_libre - margen_nueva >= MARGEN_LIBRE_MIN_BT
```

Si `puede_operar` es `False`:
- Paso B: la OE no se ejecuta ese ciclo y se cancela (`OE_eliminada`, motivo: `margen_insuficiente`).
- Paso F: la OE no se crea.

---

### Por cada vela H1 (para cada activo)

Orden de operaciones:

**A. Limpiar OE no válidas** — cancela órdenes espera cuyo precio ya no está en `soportes`.
→ Registra evento `OE_eliminada` por cada una.

**B. Verificar ejecuciones de OE** — una OE en precio `Pi` se ejecuta si `candle.Low <= Pi`:
- Verificar guard de margen: `margen_libre - margen_nueva >= MARGEN_LIBRE_MIN_BT`. Si falla → cancelar OE (`OE_eliminada`, motivo: `margen_insuficiente`) y continuar con la siguiente.
- La posición entra a `OA` con `sl=0`.
- La OE se elimina (no se repone; la reposición ocurre después del trailing stop si corresponde).
→ Registra evento `OE_ejecutada`.

**C. Trailing stop** — para cada posición en `OA`:
- `L = lote * UNITS[activo]`
- Usando `candle.High` como precio más alto alcanzado en la vela:
  - Si `sl == 0` y `(candle.High - Pi) * L >= A` → activa SL: `sl = candle.High - B/L`, repone OE en `Pi`.
  - Si `sl > 0` y `candle.High - B/L > sl` → mueve SL al alza.
→ Registra evento `SL_cambiado` cuando el SL se activa o sube.

**D. Controlar PERDIDA_MAX** — para cada posición en `OA`:
- `perdida = (Pi - candle.Low) * L`
- Si `perdida > PERDIDA_MAX_BT` → cerrar posición en `candle.Low`, registrar trade.
→ Registra evento `posicion_cerrada` (motivo: `perdida_max`).

**E. Cierre por SL tocado** — para cada posición con `sl > 0`:
- Si `candle.Low <= sl` → cerrar posición en `sl`, registrar trade (motivo: `trailing_stop`).
→ Registra evento `posicion_cerrada` (motivo: `trailing_stop`).

**F. Crear nuevas OE** — usando `candle.Close` como precio de referencia:
- Para cada soporte `Pi` en `soportes` no presente en OA ni OE:
  - Si `(candle.Close - Pi) * L >= A`:
    - Verificar guard de margen: `margen_libre - margen_nueva >= MARGEN_LIBRE_MIN_BT`. Si falla → no crear OE en ese soporte.
    - Si pasa → crear OE en `Pi`. El margen libre se reduce en `margen_nueva` para evaluar las OE siguientes del mismo ciclo (las OE creadas en esta vela son candidatas a ejecutarse en la próxima).
→ Registra evento `OE_creada` por cada una que pase el guard.

**G. Snapshot de equity** — al final de cada vela H1:
- Registra `ts` + `capital` en `equity_global.csv`.
- Para cada activo: calcula `GA = sum((candle.Close - pa) * lote * UNITS[activo] for pa in OA)`, lee `GC` del estado, registra `(ts, activo, GC, GA, GC+GA)` en `equity_activos.csv`.

> **Supuesto de orden dentro de la vela (sin intra-vela)**: el flujo C → E implica que el TS se actualiza con `High` *antes* de verificar si `Low` toca el SL. En "velas de conflicto" (Low tocaría el SL antiguo Y High subiría el TS) esto es levemente optimista: el sistema cierra al SL nuevo (más alto) en vez del antiguo. El sesgo es pequeño y la simulación intra-vela lo resuelve cuando el trigger se cumple.

---

## 7. Simulación intra-vela (M1)

Se activa cuando la resolución H1 no es suficiente para determinar qué ocurrió primero dentro de la vela. El caso más importante: una posición con trailing stop donde en la misma vela el precio pudo haber subido (moviendo el SL al alza) *antes* de bajar y tocar el SL — el precio exacto de cierre depende del orden real.

### Cuándo se usa

Siempre que haya al menos una posición abierta (OA) o una orden en espera (OE) que podría ejecutarse, y el rango de la vela sea suficiente para generar eventos conflictivos cuyo orden importe:

```python
def _necesita_intravela(activo_estado, candle, L, A, B, PERDIDA_MAX_BT):
    OA = activo_estado['OA']
    OE = activo_estado['OE']
    rango = candle['High'] - candle['Low']

    for precio_ap, pos in OA.items():
        sl = pos['sl']
        if sl == 0:
            # Sin SL: ¿puede activar TS Y caer a PERDIDA_MAX en la misma vela?
            if rango * L >= A and (precio_ap - candle['Low']) * L >= PERDIDA_MAX_BT:
                return True
        else:
            # Con SL: ¿puede mover el SL al alza Y al mismo tiempo Low tocar el SL?
            sl_nuevo = candle['High'] - B / L
            if sl_nuevo > sl and candle['Low'] <= sl_nuevo:
                return True

    for precio_oe in OE:
        # OE podría ejecutarse y la misma vela tiene rango para TS o PERDIDA_MAX
        if candle['Low'] <= precio_oe:
            if rango * L >= A or (precio_oe - candle['Low']) * L >= PERDIDA_MAX_BT:
                return True

    return False
```

### Método

1. Seleccionar un índice `t` aleatorio en `Data_minuto/{activo}.csv` y tomar las 60 velas consecutivas `[t : t+60]`. La consecutividad preserva la estructura real de precios minuto a minuto.
2. Escalar linealmente ese bloque para que encaje dentro del marco OHLC de la vela H1:
   - `Open_m1[0]` → `candle.Open`
   - `Close_m1[-1]` → `candle.Close`
   - `max(High_m1)` → `candle.High`
   - `min(Low_m1)` → `candle.Low`
   - Cada precio intermedio se escala proporcionalmente dentro de ese rango.
3. Reproducir las operaciones A→F sobre cada vela M1 en secuencia (mismo código, `precio_ref = vela_m1.Close`). Los eventos generados dentro de intra-vela se marcan con `"usa_intravela": true`.

Si `Data_minuto/` no tiene datos del activo, se degrada a lógica H1 pura (log de advertencia).

---

## 8. Store de trades (`trades.json`)

Lista de objetos JSON, uno por cada trade cerrado. Se hace append al archivo existente (no se sobreescribe).

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
    "N": 70, "K": 1.0, "LAMBDA": 0.002, "N_EXP": 1.3,
    "LOTAJE": 0.01, "UNITS": 1
  },
  "features_x2": null,
  "features_x3": null
}
```

`motivo_cierre` ∈ `{"trailing_stop", "perdida_max", "fin_backtest"}`.  
`features_x2` y `features_x3` quedan `null` en V1; X5/X6 los rellenarán.

---

## 9. Log de eventos (`events.json`) y curvas de equity

### events.json

Lista cronológica de todos los eventos de órdenes durante la simulación. Propósito: auditoría completa del libro de órdenes, debugging, y contexto para X5 (ej. cuántas OE había activas cuando se abrió un trade).

Cada evento tiene campos comunes + campos específicos por tipo:

**Campos comunes a todos los eventos:**
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

`OE_creada` — se declara una nueva orden de compra en un soporte:
```json
{ "tipo": "OE_creada", "precio": 94500.0, "lote": 0.01 }
```

`OE_eliminada` — una OE existente se cancela porque su soporte fue eliminado en el recálculo de X0. La orden nunca llegó a ejecutarse:
```json
{ "tipo": "OE_eliminada", "precio": 93200.0, "motivo": "soporte_desactivado" }
```

`OE_ejecutada` — una OE que estaba esperando se activa (el precio la toca). Pasa a ser posición abierta:
```json
{ "tipo": "OE_ejecutada", "precio": 94500.0, "lote": 0.01, "ts_oe_creacion": "2026-01-14T08:00:00" }
```

`SL_cambiado` — el stop loss de una posición abierta se activa o sube:
```json
{ "tipo": "SL_cambiado", "precio_apertura": 94500.0, "sl_anterior": 0, "sl_nuevo": 94350.0, "precio_max_vela": 94600.0 }
```
(`sl_anterior = 0` indica que el SL se activa por primera vez al alcanzar el umbral `A`.)

`posicion_cerrada` — una posición se cierra por SL tocado o pérdida máxima:
```json
{ "tipo": "posicion_cerrada", "precio_apertura": 94500.0, "precio_cierre": 94350.0,
  "motivo": "trailing_stop", "retorno_usd": -15.0, "lote": 0.01 }
```
(`motivo` ∈ `{"trailing_stop", "perdida_max"}`. Los cierres por `fin_backtest` solo van en `trades.json`, no aquí.)

Append-only, igual que `trades.json`.

### equity_global.csv

Snapshot de todas las métricas de cuenta al cierre de cada vela H1.

Columnas: `ts`, `balance`, `equity`, `margen_usado`, `margen_libre`, `margin_level`, `n_OA`, `n_OE`.

- `balance`: `estado['capital']` — capital ya realizando P&L cerrado.
- `equity`: balance + GA_global flotante.
- `margen_usado` / `margen_libre` / `margin_level`: ver fórmulas en "Métricas de cuenta".
- `n_OA`: total de posiciones abiertas en todos los activos.
- `n_OE`: total de órdenes en espera en todos los activos.

```csv
ts,balance,equity,margen_usado,margen_libre,margin_level,n_OA,n_OE
2026-01-10T00:00:00,3000.0,3000.0,0.0,3000.0,,0,0
2026-01-10T01:00:00,3000.0,2987.5,945.0,2042.5,315.9,1,3
...
```

(`margin_level` vacío cuando `margen_usado = 0`.)

### equity_activos.csv

Snapshot por `(activo, ts)` al cierre de cada vela H1. Separa ganancia cerrada acumulada y ganancia abierta en ese momento:

- **GC** (Ganancia Cerrada acumulada): suma de `retorno_usd` de todos los trades cerrados de este activo hasta este instante. Se acumula en `estado['por_activo'][activo]['GC']` cada vez que cierra una posición.
- **GA** (Ganancia Abierta): suma de `(candle.Close - precio_apertura) * lote * UNITS[activo]` para cada posición en `OA` al cerrar la vela. Calculada al vuelo — no se persiste en estado.
- **GT = GC + GA**

```csv
ts,activo,GC,GA,GT
2026-01-10T00:00:00,BTCUSD,0.0,0.0,0.0
2026-01-10T00:00:00,ETHUSD,0.0,0.0,0.0
2026-01-10T01:00:00,BTCUSD,0.0,-12.5,-12.5
2026-01-10T01:00:00,ETHUSD,0.0,4.2,4.2
...
```

GA y GC pueden ser negativas. El valor de cuenta por activo no es `capital / n_activos` — es el P&L neto de ese activo independientemente del capital base.

Útil para: curva de equity por activo, atribución de resultados entre BTCUSD y ETHUSD, drawdown por activo, y como feature para X5 (P&L flotante y acumulado al momento de abrir cada trade).

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
X4_backtester.py
├── _cargar_config(version)              → importa config_V[version].py
├── _descargar_actualizar_datos(cfg)     → H1 + M1, solo Windows/MT5
├── _cargar_datos_h1(cfg)                → dict {activo: DataFrame OHLCV}
├── _cargar_datos_m1(cfg)                → dict {activo: DataFrame M1} (None si no existe)
├── _cargar_checkpoint(cfg)              → dict estado | None
├── _guardar_checkpoint(estado, cfg)
│
├── _recalcular_soportes(estado, datos_h1, ts_actual, cfg)
│     └── ProcessPoolExecutor → _procesar_valor_N() de X0 (importado)
│
├── _limpiar_OE(activo_estado, soportes)          → lista de precios eliminados
├── _verificar_ejecuciones_OE(activo_estado, candle, L)
├── _trailing_stop_sim(activo_estado, precio_max, L, A, B)
├── _controlar_perdida_max(activo_estado, precio_min, L, PERDIDA_MAX)
├── _cerrar_sl_tocados(activo_estado, precio_min)
├── _crear_OE(activo_estado, precio_ref, soportes, L, A, lote)
│
├── _calcular_estado_cuenta(estado, precios_cierre, cfg)
│     → {balance, equity, margen_usado, margen_libre, margin_level, n_OA, n_OE}
│     precios_cierre: dict {activo: candle.Close} para calcular GA flotante
│
├── _trigger_intravela(activo_estado, candle, L, A, PERDIDA_MAX)
├── _escalar_bloque_m1(bloque_m1, candle_h1)
├── _simular_intravela(activo_estado, candle_h1, datos_m1, params)
│
├── _procesar_candle(candle, activo, estado, datos_m1, trades_log, events_log, cfg)
│     └── decide: intra-vela o H1 puro → ejecuta A→G → append a trades_log y events_log
│
├── _registrar_trade(posicion, precio_cierre, motivo, ts, capital, cfg)  → dict
├── _registrar_evento(tipo, activo, ts, cfg, **kwargs)                   → dict
├── _append_eventos(events_log, cfg)     → append a events.json
├── _calcular_GA(activo_estado, precio_actual, units)                     → float
├── _append_equity(ts, capital, estado, datos_candle, cfg)
│     → append fila a equity_global.csv
│     → append filas (GC, GA, GT) por activo a equity_activos.csv
│
└── ejecutar_backtest(cfg)               → loop principal
      1. descargar/actualizar datos
      2. cargar checkpoint o inicializar estado
      3. cold start: si no hay soportes en conjuntos_N/bt/ para algún (activo, N, version)
            → recalcular con fecha_hora_max = fecha_inicio antes de entrar al loop
      4. for ts, candle in datos_h1.iterrows() desde ts_ultimo_procesado:
           a. check recálculo → si sí: recalcular, congelar, continuar
           b. for activo in valores: _procesar_candle(...)
           c. cada 24 velas: _guardar_checkpoint(...)
      5. guardar checkpoint final + mensaje de tiempo total
```

---

## 12. CLI

```bash
python scripts/X4_backtester.py --version V1
python scripts/X4_backtester.py --version V1 --reset   # ignora checkpoint, parte de cero
```

---

## 13. Secuencia de implementación

| Fase | Qué |
|------|-----|
| 1 | Crear estructura de carpetas + `config_V1.py` |
| 2 | `_cargar_datos_h1` + `_cargar_datos_m1` + actualización con MT5 (Windows only) |
| 3 | `_recalcular_soportes` — importar y envolver funciones de X0; cold start al inicio |
| 4 | `_limpiar_OE`, `_verificar_ejecuciones_OE`, `_trailing_stop_sim`, `_controlar_perdida_max`, `_cerrar_sl_tocados`, `_crear_OE` |
| 5 | `_procesar_candle` H1 puro + `_registrar_trade` + `trades.json` |
| 6 | `_registrar_evento` + `events.json` + `_calcular_GA` + `_append_equity` + `equity_global.csv` + `equity_activos.csv` |
| 7 | Checkpoint save/load + argparse + loop principal `ejecutar_backtest` |
| 8 | `_trigger_intravela` + `_escalar_bloque_m1` + `_simular_intravela` |
| 9 | Prueba end-to-end V1 en Mac (sin MT5: datos ya en `Data/` y `Data_minuto/`) |

---

## 14. Qué queda fuera de V1 (para V2+)

- Parámetros dinámicos por período (X6)
- Features X2/X3 en el trade store (X5)
- Múltiples N simultáneos por activo en producción
- Modelado de spread/slippage
- Soporte para acciones US (solo cambia `valores` y `n_sizes` en config; el resto funciona igual — `Data/` ya tiene solo velas de días hábiles en horario de mercado y el recálculo a las 23 UTC cae post-cierre)

---

_Última actualización: 2026-06-18_
