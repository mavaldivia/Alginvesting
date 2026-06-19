# X3 Technical Features — Plan de implementación

## 1. Objetivo

`X3_technical_features.py` genera un snapshot de indicadores técnicos para cada activo en un instante de tiempo dado. Su output alimenta a X6 (cerebro macro).

Las **features de contexto operativo** (órdenes abiertas, PnL flotante, exposición, capital libre, etc.) dependen del estado de cuenta en cada corrida y son responsabilidad de X1 (producción) y X4 (backtesting), que los tienen disponibles directamente.

X3 **no toma decisiones de trading**. Solo calcula y serializa indicadores técnicos derivados de precios/volumen.

---

## 2. Posición en la arquitectura

```
X0 ciclo:
  descargar_datos (H1)  ──→  calcular_features_x3()  ──→  features/{valor}.csv  ──→  X6
  descargar_datos_minuto (M1)
  buscar_soportes (X0 core)
```

X3 **no es un script standalone**. Es un módulo importado y llamado desde X0 al final de la Etapa 1 (descarga de datos), antes de arrancar la búsqueda de soportes. Su única salida es `features/{valor}.csv`; X6 lee el snapshot más reciente de ese archivo.

X4 **no llama a X3**. Consume `features/{valor}.csv` que ya fue escrito por X0 en su momento — las features están pre-computadas sin look-ahead.

---

## 3. Inputs

| Input | Descripción |
|---|---|
| `df_ohlcv` | DataFrame OHLCV H1 completo del activo (ya descargado en Etapa 1 de X0) |
| `conjunto_N` | Set de N soportes activos del activo (leídos desde `conjuntos_N/prod/`) — para features de distancia a soportes (sección 4.11) |
| `valor` | Ticker del activo (ej. `'BTCUSD'`) |
| `ultimo_t_calculado` | Datetime de la última fila ya computada en `features/{valor}.csv` (para cálculo incremental) |

---

## 4. Indicadores técnicos

Notación: $C_t$ = Close, $H_t$ = High, $L_t$ = Low, $V_t$ = Tick Volume, $w$ = ventana de velas.

Ventanas por defecto en paréntesis — todas configurables en `config.py`.

---

### 4.1 SMA — Simple Moving Average

$$\text{SMA}_t(w) = \frac{1}{w} \sum_{i=0}^{w-1} C_{t-i}$$

**Features generadas**: `sma_20`, `sma_50`, `sma_200`

**Derivada útil** — distancia relativa al precio:

$$\text{sma\_dist}_{w} = \frac{C_t - \text{SMA}_t(w)}{C_t}$$

---

### 4.2 EMA — Exponential Moving Average

Inicialización: $\text{EMA}_0 = C_0$. Actualización recursiva:

$$\text{EMA}_t = \alpha \cdot C_t + (1-\alpha) \cdot \text{EMA}_{t-1}, \qquad \alpha = \frac{2}{w+1}$$

**Features generadas**: `ema_12`, `ema_26`

**Derivada útil**:

$$\text{ema\_dist}_{w} = \frac{C_t - \text{EMA}_t(w)}{C_t}$$

---

### 4.3 RSI — Relative Strength Index (Wilder, 1978)

Sea $\Delta_t = C_t - C_{t-1}$. Definir:

$$G_t = \max(\Delta_t, 0), \qquad L_t = \max(-\Delta_t, 0)$$

Promedio suavizado con EMA de Wilder ($\alpha = 1/w$):

$$\overline{G}_t = \alpha \cdot G_t + (1-\alpha) \cdot \overline{G}_{t-1}$$
$$\overline{L}_t = \alpha \cdot L_t + (1-\alpha) \cdot \overline{L}_{t-1}$$

$$\text{RSI}_t(w) = 100 - \frac{100}{1 + \dfrac{\overline{G}_t}{\overline{L}_t}}$$

**Features generadas**: `rsi_14`

Zonas de referencia: sobrecompra $> 70$, sobreventa $< 30$.

---

### 4.4 MACD — Moving Average Convergence Divergence

$$\text{MACD}_t = \text{EMA}_{12}(C) - \text{EMA}_{26}(C)$$

$$\text{Signal}_t = \text{EMA}_9(\text{MACD})$$

$$\text{Histogram}_t = \text{MACD}_t - \text{Signal}_t$$

**Features generadas**: `macd`, `macd_signal`, `macd_hist`

El histograma es el indicador más directo del momentum: positivo y creciente → tendencia alcista acelerando; cruce de cero → cambio de régimen.

---

### 4.5 ATR — Average True Range (Wilder, 1978)

True Range de la vela $t$:

$$\text{TR}_t = \max\!\bigl(H_t - L_t,\ |H_t - C_{t-1}|,\ |L_t - C_{t-1}|\bigr)$$

ATR como EMA de Wilder ($\alpha = 1/w$):

$$\text{ATR}_t(w) = \alpha \cdot \text{TR}_t + (1-\alpha) \cdot \text{ATR}_{t-1}$$

**Features generadas**: `atr_14`

**Derivada útil** — ATR normalizado al precio (volatilidad relativa):

$$\text{atr\_pct} = \frac{\text{ATR}_t}{C_t}$$

ATR es base de los parámetros `A` (ganancia mínima TS) y `B` (distancia TS) — una versión adaptativa de esos parámetros podría expresarlos en unidades de ATR.

---

### 4.6 Bandas de Bollinger

$$\mu_t(w) = \text{SMA}_t(w), \qquad \sigma_t(w) = \sqrt{\frac{1}{w}\sum_{i=0}^{w-1}(C_{t-i} - \mu_t)^2}$$

$$\text{BB\_upper}_t = \mu_t + k\,\sigma_t, \qquad \text{BB\_lower}_t = \mu_t - k\,\sigma_t$$

con $k = 2$ por defecto (cubre ~95 % de los valores bajo normalidad).

**Features generadas**:

| Feature | Fórmula |
|---|---|
| `bb_width` | $(\text{BB\_upper} - \text{BB\_lower}) / \mu_t$ — ancho relativo (proxy de volatilidad) |
| `bb_pos` | $(C_t - \text{BB\_lower}) / (\text{BB\_upper} - \text{BB\_lower}) \in [0, 1]$ — posición dentro de la banda |

`bb_pos > 1` o `< 0` indica que el precio está fuera de las bandas.

---

### 4.7 Momentum / Rate of Change

Momentum absoluto:

$$\text{MOM}_t(w) = C_t - C_{t-w}$$

Rate of Change (normalizado):

$$\text{ROC}_t(w) = \frac{C_t - C_{t-w}}{C_{t-w}}$$

**Features generadas**: `roc_10`, `roc_20`

---

### 4.8 Volatilidad histórica (log-returns)

$$r_t = \ln\!\left(\frac{C_t}{C_{t-1}}\right)$$

$$\sigma_t^{\text{hist}}(w) = \sqrt{\frac{1}{w-1}\sum_{i=0}^{w-1}(r_{t-i} - \bar{r})^2}$$

Anualizada (H1, asumiendo 8760 velas/año):

$$\sigma^{\text{anual}} = \sigma^{\text{hist}} \cdot \sqrt{8760}$$

**Features generadas**: `vol_24h` ($w=24$), `vol_7d` ($w=168$)

---

### 4.9 Drawdown desde máximo reciente

$$\text{DD}_t(w) = \frac{C_t - \max_{i \in [t-w,\,t]} C_i}{\max_{i \in [t-w,\,t]} C_i} \leq 0$$

**Features generadas**: `drawdown_20`, `drawdown_50`

Un drawdown cercano a cero indica que el precio está cerca del máximo de la ventana (potencial resistencia); muy negativo indica caída sostenida.

---

### 4.10 Tendencia — pendiente de regresión lineal

Regresión OLS sobre los cierres de la ventana $[t-w+1, t]$, con índice temporal $i \in \{1, \dots, w\}$:

$$\hat{m}_t(w) = \frac{\displaystyle\sum_{i=1}^{w}\!\left(i - \bar{i}\right)\!\left(C_{t-w+i} - \bar{C}\right)}{\displaystyle\sum_{i=1}^{w}\!\left(i - \bar{i}\right)^2}$$

Pendiente normalizada al precio actual:

$$\text{trend\_slope}_t(w) = \frac{\hat{m}_t(w) \cdot w}{C_t}$$

**Features generadas**: `trend_slope_20`, `trend_slope_50`

Valores positivos indican tendencia alcista en la ventana; el denominador $C_t$ hace la pendiente comparable entre activos de distinta escala.

---

### 4.11 Distancia a soportes y resistencias

Sea $\mathcal{S} = \{s_1 < s_2 < \cdots < s_N\}$ el conjunto de N soportes activos.

**Soporte más cercano**:

$$s^* = \arg\min_{s \in \mathcal{S}} |C_t - s|$$

$$\text{dist\_nearest} = \frac{C_t - s^*}{C_t} \qquad \text{(negativo si el precio está bajo el soporte)}$$

**Soporte inmediatamente inferior** (el nivel que actuaría como "piso" activo):

$$s^{\downarrow} = \max\{s \in \mathcal{S} : s \leq C_t\}$$

$$\text{dist\_floor} = \frac{C_t - s^{\downarrow}}{C_t}$$

**Densidad de soportes en banda** $[\,C_t(1-\delta),\; C_t(1+\delta)\,]$ con $\delta = 0.02$:

$$\text{density\_2pct} = \frac{|\{s \in \mathcal{S} : |s - C_t|/C_t \leq \delta\}|}{N}$$

**Features generadas**: `dist_nearest_support`, `dist_floor_support`, `density_2pct`

---

## 5. Features de contexto operativo (fuera de X3)

Las features que dependen del estado de cuenta en cada corrida son calculadas directamente por X1 y X4:

| Feature | Quién la calcula |
|---|---|
| `n_oa`, `n_oe` | X1 (MT5 live) · X4 (libro simulado) |
| `exposicion`, `capital_libre` | X1 (MT5 live) · X4 (libro simulado) |
| `pnl_flotante`, `pnl_pct` | X1 (MT5 live) · X4 (libro simulado) |
| `densidad_oa`, `dist_oa_nearest` | X1 (MT5 live) · X4 (libro simulado) |

Estas features pueden unirse a `features/{valor}.csv` por `datetime` en X5 si se incluyen en el store de trades de X4.

---

## 6. Output schema

X3 devuelve un `dict` plano (compatible con pandas row) con las features de la sección 4 (indicadores técnicos). Se acumula en `features/{valor}.csv`:

```
features/
  BTCUSD.csv    # columna datetime + todas las features
  ETHUSD.csv
  ...
```

Formato CSV: `datetime` como índice (H1, UTC), una columna por feature. Toda feature es `float64`; `NaN` los primeros `max(ventana)` registros donde no hay suficiente historia.

---

## 7. Parámetros configurables (`config.py`)

```python
# Ventanas de indicadores técnicos
X3_VENTANAS = {
    'sma': [20, 50, 200],
    'ema': [12, 26],
    'rsi': 14,
    'macd': (12, 26, 9),          # fast, slow, signal
    'atr': 14,
    'bb': (20, 2),                # window, k
    'roc': [10, 20],
    'vol': [24, 168],             # horas: 1d, 7d
    'drawdown': [20, 50],
    'trend_slope': [20, 50],
    'density_delta': 0.02,        # banda ±2% para densidad de soportes
}
CARPETA_FEATURES = BASE_DIR / 'features'
```

---

## 8. Uso previsto

X3 alimenta **solo a X6**. X2 y X3 son las dos fuentes de contexto del cerebro macro.

| Script | Cómo consume X3 |
|---|---|
| **X6** | Lee el snapshot más reciente de `features/{valor}.csv` para recomendar parámetros a X0/X1 |

X4 y X5 **no llaman a X3**. X4 puede leer `features/{valor}.csv` (ya escrito por X0) si necesita features técnicas históricas como input adicional al store de trades, pero no depende de X3 en tiempo de ejecución.

---

## 9. Notas de implementación

- **Cálculo incremental**: `actualizar_features(valor)` lee `features/{valor}.csv`, extrae el último datetime computado, filtra `df_ohlcv` para quedarse solo con las filas nuevas (`df[df['DateTime'] > ultimo_t]`), y hace append al CSV. Si el archivo no existe, computa desde el principio. En un ciclo típico de X0 con 1-3 velas nuevas, el costo es despreciable.
- **Sin look-ahead por diseño**: cada fila de `features/{valor}.csv` se calcula usando solo `df[:t]` (filas hasta `t` inclusive). Como X0 llama a X3 inmediatamente después de descargar los datos (no antes), la causalidad está garantizada sin lógica adicional de filtrado dentro de X3.
- **Compatibilidad Mac/Windows**: X3 no depende de MT5. Funciona igual en Mac y Windows.
- **`conjunto_N` puede ser vacío**: si no existe `conjuntos_N/prod/{valor}_{N}.json`, las features de distancia a soportes retornan `NaN`.
- **Orden de features en el CSV**: determinístico (orden de definición en `_calcular_features`), para reproducibilidad.

---

## 10. Secuencia de implementación

1. `_calcular_indicadores_tecnicos(df_hasta_t, conjunto_N, ventanas)` → dict con todas las features técnicas de las secciones 4.1–4.11; `df_hasta_t` es el slice hasta la fila `t` inclusive
2. `calcular_features_fila(df_hasta_t, conjunto_N)` → llama al paso 1 y agrega campo `datetime`
3. `actualizar_features(valor, df_ohlcv, conjunto_N)` → función principal: lee `features/{valor}.csv`, detecta último `t` calculado, itera sobre filas nuevas llamando a `calcular_features_fila`, hace append al CSV
4. Integración en **X0**: en `__main__`, tras `descargar_datos` y `descargar_datos_minuto`, llamar `actualizar_features(valor, df, conjunto_N)` por cada activo en `VALORES`

No se requiere CLI standalone. La función se expone como `from X3_technical_features import actualizar_features`.

---

*Última actualización: 2026-06-18*
