# X2 — Plan de implementación: X2_fundamentals.py

Documento de diseño basado en experimentación real con las fuentes de datos (2026-06-12).  
Objetivo: producir un `score_fundamental` por activo en `[0, 1]` que X6 usará para ajustar parámetros de X0 y X1.

---

## 1. Fuentes de datos evaluadas

### 1.1 yfinance — acciones (TSLA, GOOGL, NVDA, AMZN)

**Veredicto: excelente. Cubre todo lo necesario sin API key.**

Campos confirmados disponibles (24–25 por activo):

| Grupo | Campos | Historia / periodicidad |
|---|---|---|
| Valorización | `trailingPE`, `forwardPE`, `priceToBook`, `enterpriseToEbitda` | Snapshot puntual, cache 24h. Refleja el último reporte disponible. |
| Rentabilidad | `returnOnEquity`, `returnOnAssets`, `grossMargins`, `operatingMargins`, `profitMargins` | Snapshot puntual, cache 24h. |
| Crecimiento | `revenueGrowth`, `earningsGrowth` | Snapshot puntual (YoY del último trimestre vs. año anterior). |
| Flujo de caja | `freeCashflow`, `operatingCashflow` | Snapshot puntual (TTM — últimos 12 meses acumulados). |
| Deuda / riesgo | `totalDebt`, `debtToEquity`, `currentRatio`, `quickRatio` | Snapshot puntual, del último balance disponible. |
| Mercado | `marketCap`, `enterpriseValue`, `beta`, `shortPercentOfFloat` | Snapshot puntual, intradiario para marketCap. |
| Earnings | `earnings_dates` (EPS estimate vs. actual, surprise%) | Trimestral. Historial ~3-4 años hacia atrás (NVDA: desde 2022-11). Incluye fechas futuras estimadas. |
| Analistas | `recommendations` (strongBuy/buy/hold/sell/strongSell) | Rolling: solo 4 meses (mes actual + 3 anteriores). Sin historial más largo. |
| Financieros históricos | `quarterly_financials`, `quarterly_cashflow`, `quarterly_balance_sheet` | Trimestral. Últimos **7 trimestres** (~21 meses). |
| Financieros históricos | `income_stmt`, `balance_sheet`, `cashflow` (anual) | Anual. Últimos **5 años**. |
| Precios históricos | `history(period='max')` | Diario/semanal/mensual. Desde **1999** para acciones US (NVDA: 27 años, 330 meses). |

Valores confirmados (2026-06-12):
- NVDA: forwardPE=16.1, ROE=114%, margen neto=63%, crecimiento ingresos=85%
- GOOGL: forwardPE=24.8, ROE=39%, margen neto=38%, crecimiento ingresos=22%
- AMZN: forwardPE=24.2, ROE=24%, margen neto=12%, D/E=53 (alto)
- TSLA: forwardPE=162, ROE=5%, margen neto=4%, crecimiento ingresos=16%

**Limitaciones confirmadas**: `priceToSalesTrailingTwelveMonths` viene nulo en todos (no crítico). `recommendations` tiene solo 4 meses de historia (no sirve para tendencia, solo para consenso actual).

---

### 1.2 yfinance — crypto (BTC-USD, ETH-USD)

**Veredicto: suficiente para métricas básicas. Sin P/E ni FCF (esperado).**

| Campos | Historia / periodicidad |
|---|---|
| `marketCap`, `volume24Hr`, `circulatingSupply`, `maxSupply`, `totalSupply` | Snapshot puntual, cache 24h. |
| `fullyDilutedValue`, `volume24HrMarketCapPercent` | Snapshot puntual. |
| `fiftyDayAverage`, `twoHundredDayAverage` | Calculados sobre precios diarios (50 y 200 días hacia atrás). |
| `allTimeHigh`, `allTimeLow` | Histórico total desde inicio del activo. |
| `blockReward`, `netHashesPerSecond` (solo BTC) | Snapshot puntual (dato en tiempo real de la red). |
| `blockNumber` | Snapshot puntual. |
| `history(period='max')` — precios | **BTC**: diario desde 2014-09-17 (~12 años, 4287 días). **ETH**: diario desde 2017-11-09 (~8.5 años, 3138 días). |

---

### 1.3 CoinGecko — free API (sin API key)

**Veredicto: complemento ideal para crypto. Gratis, sin registro, ~10-30 req/min.**

| Endpoint | Datos | Historia / periodicidad |
|---|---|---|
| `/coins/markets` | Precio, market cap, volumen, ATH/ATL, cambios `1h`/`24h`/`7d`/`30d`, supply | Snapshot puntual. Actualizado cada pocos minutos. |
| `/global` | Dominancia BTC, market cap total crypto, cambio 24h global | Snapshot puntual. |
| `/coins/{id}` | `developer_data` (forks, stars, commits), cambios `14d`/`60d`/`200d`/`1y` | Snapshot puntual para datos de comunidad y developer. |
| `/coins/{id}/market_chart` | Serie histórica de precio, market cap y volumen | **Limitado a 365 días** en el free tier (confirmado: `days>365` retorna error 401). Para historial mayor se necesita plan pago. |

**Implicación para X2**: solo se usarán endpoints de snapshot (no histórico de CoinGecko). El historial de precios crypto se obtiene de yfinance cuando sea necesario.

---

### 1.4 alternative.me — Fear & Greed Index

**Veredicto: señal macro de sentimiento crypto, gratis, sin API key.**

- Score diario `[0, 100]`: 0–24 = Extreme Fear, 25–49 = Fear, 50–74 = Greed, 75–100 = Extreme Greed.
- **Historia**: diario desde **2018-01-31** (~8.5 años, 3050 puntos confirmados). Sin límite de consulta en el free tier.
- **Periodicidad**: un dato por día. Se actualiza una vez al día.
- URL: `https://api.alternative.me/fng/?limit=N` (`limit=0` devuelve todo el historial).
- Uso propuesto: valor del día actual normalizado a `[0, 1]` como componente del score crypto.

---

### 1.5 Fuentes descartadas o pospuestas

| Fuente | Razón |
|---|---|
| Glassnode | Pago. Métricas on-chain (MVRV, SOPR, NVT) son las mejores para crypto pero requieren suscripción. |
| CryptoQuant | Pago. Similar a Glassnode. |
| investing.com | Sin API oficial. Scraping frágil. |
| MT5 (fundamentales) | MT5 no expone datos fundamentales, solo precios. |
| FRED API | Interesante para macro (VIX, DXY, Fed Funds Rate). Gratis. Reservar para X3. |

**Nota**: VIX (`^VIX`) y DXY (`DX-Y.NYB`) están disponibles via yfinance y son útiles como contexto macro, pero encajan mejor en X3 (features técnicos de contexto) que en X2 (fundamentales por activo).

---

## 2. Diseño del score

### 2.1 Principios

- Un solo score por activo, en `[0, 1]`.
- Interpretación: `0` = condiciones fundamentales muy débiles (evitar/reducir exposición), `1` = condiciones muy fuertes (aumentar exposición).
- Normalización: cada componente se lleva a `[0, 1]` individualmente antes de combinar.
- No hay P/E ni FCF para crypto → métricas completamente distintas. Dos funciones separadas: `_score_stock` y `_score_crypto`.

### 2.2 Score para acciones (TSLA, GOOGL, NVDA, AMZN)

```
score_stock = promedio ponderado de:
  [calidad]
    c1 = norm(ROE)                      peso 0.20   # rentabilidad sobre capital
    c2 = norm(profitMargins)            peso 0.15   # margen neto
    c3 = norm(FCF_yield)                peso 0.10   # FCF / market cap
  [crecimiento]
    c4 = norm(revenueGrowth)            peso 0.15   # crecimiento ingresos YoY
    c5 = norm(earningsGrowth)           peso 0.10   # crecimiento earnings YoY
  [valorización]  (invertidas: menor ratio → mejor valorización)
    c6 = 1 - norm(forwardPE)            peso 0.10   # no se castiga crecer
    c7 = 1 - norm(enterpriseToEbitda)   peso 0.05
  [riesgo]
    c8 = 1 - norm(debtToEquity)         peso 0.05   # menor deuda → mejor
    c9 = 1 - norm(shortPercentOfFloat)  peso 0.05   # menos short sellers → mejor
  [sentimiento analistas]
    c10 = norm((strongBuy+buy)/total_recommendations)   peso 0.05
```

**FCF_yield** = `freeCashflow / marketCap`. Normalizado en la muestra de los 4 activos.

**Normalización**: min-max sobre los valores del universo actual (los 4 activos), recalculado cada vez que se obtienen los datos. Sin normalización histórica por ahora — suficiente para comparar entre activos.

**Pesos**: provisionales. Diseñados para favorecer calidad y crecimiento sobre valorización (consistente con el perfil de los activos — todos son tech de alta valorización). Ajustables en `config.py`.

---

### 2.3 Score para crypto (BTC, ETH)

```
score_crypto = promedio ponderado de:
  [salud de red]
    d1 = norm(netHashesPerSecond)        peso 0.20   # solo BTC; ETH usa proxy de blockReward
    d2 = norm(volume24Hr / marketCap)    peso 0.15   # liquidez relativa
  [posición de mercado]
    d3 = 1 - norm(circulating/max_supply) peso 0.10  # menor supply usado → más runway; None para ETH (inflationary → d3 = 0.5)
    d4 = norm(marketCap)                 peso 0.10   # tamaño / dominancia
  [momentum de precio]
    d5 = norm_sym(price_change_7d)       peso 0.15   # 7d > 0 → positivo
    d6 = norm_sym(price_change_30d)      peso 0.10   # 30d > 0 → tendencia más larga
  [sentimiento]
    d7 = fear_greed / 100               peso 0.20   # Fear & Greed normalizado a [0,1]
```

**norm_sym**: normalización de cambios porcentuales usando `tanh(x/50)` escalado a `[0,1]`, para no castigar desproporcionalmente caídas extremas.

**ETH supply**: ETH no tiene max_supply (es inflacionario post-merge con quema parcial de fees). Se asigna `d3 = 0.5` (neutral). A futuro se puede usar la tasa de quema neta.

---

## 3. Arquitectura del script

### 3.1 Output

Archivo `fundamentals/scores.json` (creado por X2, leído por X6):
```json
{
  "TSLA": {"score": 0.72, "components": {"roe": 0.81, "margins": 0.34, ...}, "ts": "2026-06-12T21:00:00"},
  "GOOGL": {"score": 0.83, "components": {...}, "ts": "..."},
  "NVDA": {"score": 0.91, "components": {...}, "ts": "..."},
  "AMZN": {"score": 0.68, "components": {...}, "ts": "..."},
  "BTCUSD": {"score": 0.41, "components": {...}, "ts": "..."},
  "ETHUSD": {"score": 0.38, "components": {...}, "ts": "..."}
}
```

**Mapeo de tickers**: `BTCUSD` → `BTC-USD` (yfinance) / `bitcoin` (CoinGecko); `ETHUSD` → `ETH-USD` / `ethereum`.

### 3.2 Frecuencia de actualización y control de ejecución

- Correr X2 **una vez al día** como mínimo — los fundamentales de acciones y Fear & Greed se actualizan diariamente; no tiene sentido correr por hora.

**Guard de día** (evitar re-ejecuciones innecesarias):
- Al terminar una corrida exitosa, guardar `fundamentals/x2_last_run.json` con el campo `fecha` (solo la fecha, sin hora).
- Al inicio de cada corrida, leer ese archivo. Si `fecha == hoy` → saltear y retornar el `scores.json` existente.
- Evita re-ejecutar en cada ciclo del `while True` de X0 o en corridas manuales repetidas el mismo día.

**Re-ejecución forzada diaria desde el loop de X0**:
- En el `while True` de X0, cuando la hora del sistema alcance `X2_HORA_EJECUCION` (configurable en `config.py`, ej. `"21:00"`), forzar una nueva corrida de X2 aunque el guard indique que ya corrió hoy — actualizando el timestamp en `x2_last_run.json`.
- Garantiza actualización diaria en sesiones de X0 que duren más de 24 horas seguidas.

### 3.3 Estructura del script

```python
# X2_fundamentals.py

def _ya_ejecutado_hoy() -> bool         # lee x2_last_run.json, compara con date.today()
def _marcar_ejecutado()                 # escribe x2_last_run.json con fecha de hoy
def _get_stock_data(ticker: str) -> dict       # yfinance raw
def _get_crypto_data(coin_id: str) -> dict     # yfinance + CoinGecko + F&G
def _score_stock(data: dict, universe: list) -> dict    # normaliza en universo
def _score_crypto(data: dict, universe: list) -> dict
def calcular_scores(valores: list) -> dict     # orquesta todo
def guardar_scores(scores: dict)               # → fundamentals/scores.json

if __name__ == '__main__':
    if _ya_ejecutado_hoy():
        # retorna scores.json existente sin re-ejecutar
    else:
        scores = calcular_scores(VALORES)
        guardar_scores(scores)
        _marcar_ejecutado()
        # imprimir tabla resumen
```

### 3.4 Integración con config.py

Agregar a `config.py`:
```python
CARPETA_FUNDAMENTALS = BASE_DIR / 'fundamentals'
X2_HORA_EJECUCION = '21:00'   # hora de re-ejecución forzada diaria desde el loop de X0

# Pesos del score fundamental (stocks) — inicialización; X6 puede sobreescribir vía active_parameters.json
PESOS_STOCK = {
    'roe': 0.20, 'margins': 0.15, 'fcf_yield': 0.10,
    'rev_growth': 0.15, 'earn_growth': 0.10,
    'forward_pe': 0.10, 'ev_ebitda': 0.05,
    'debt_eq': 0.05, 'short_pct': 0.05, 'analyst': 0.05,
}

# Pesos del score fundamental (crypto) — inicialización; X6 puede sobreescribir vía active_parameters.json
PESOS_CRYPTO = {
    'hash': 0.20, 'vol_mcap': 0.15, 'supply': 0.10,
    'mcap': 0.10, 'momentum_7d': 0.15, 'momentum_30d': 0.10,
    'fear_greed': 0.20,
}
```

### 2.4 Pesos como inicialización, no como valores permanentes

Los pesos definidos en 2.2 y 2.3 (y en `PESOS_STOCK` / `PESOS_CRYPTO` de `config.py`) son **valores iniciales** — una hipótesis de partida razonable dado el dominio, no la configuración definitiva.

**X6 debe ajustar estos pesos** en función del historial de trades (X4 → X5 → X6): qué componentes del score han correlacionado con retornos positivos, cuáles resultan ruido para este universo de activos. Los pesos actuales son la semilla del entrenamiento, no su resultado.

Implicación de implementación: `PESOS_STOCK` y `PESOS_CRYPTO` deben ser sobreescribibles por X6 vía `config/active_parameters.json` (o equivalente), sin modificar `config.py` directamente. Al cargar los pesos, X2 comprueba primero si existen overrides en ese archivo; si no, usa los defaults de `config.py`.

---

## 4. Decisiones de diseño clave

### ¿Por qué normalizar en el universo actual y no en histórico?

El score sirve para **comparar activos entre sí** (cuál está en mejores condiciones fundamentales hoy), no para determinar si un activo está "caro o barato" en términos históricos. Min-max sobre los 6 activos es suficiente para ese propósito. Si en el futuro se quiere comparación histórica, se puede guardar un percentil histórico por separado.

### ¿Por qué no usar `priceToSalesTrailingTwelveMonths`?

Viene nulo para los 4 activos en yfinance 0.2.65. Omitido.

### ¿Por qué Fear & Greed tiene peso 0.20 en crypto?

Crypto es mucho más sensible al sentimiento que las acciones. Un índice en "Extreme Fear" (confirmado: 8–12 al momento de escribir este documento) es señal real de reversión o riesgo, no solo ruido. En acciones el equivalente sería el VIX, pero ese va mejor en X3.

### ¿Por qué pesos iguales para ROE y Fear & Greed son diferentes?

Ambos son 0.20, pero en categorías distintas (calidad vs. sentimiento), y la categoría "sentimiento" tiene un solo componente en crypto vs. tres en stocks. Neto: el sentimiento pesa más en crypto que en acciones, lo cual es intencional.

---

## 5. Pasos de implementación (en orden)

1. **Ítem 1 del TO DO** (ya cubierto por este documento): Definir y evaluar fuentes de datos. → **LISTO** (este doc).
2. Agregar `CARPETA_FUNDAMENTALS`, `PESOS_STOCK`, `PESOS_CRYPTO` a `config.py`.
3. Implementar `_get_stock_data` y `_get_crypto_data` (llamadas a API, manejo de nulos).
4. Implementar `_score_stock` y `_score_crypto` con la normalización descrita.
5. Implementar `calcular_scores` y `guardar_scores`.
6. Testear con los 6 activos y verificar que los scores tienen sentido (NVDA debería estar alto hoy dado ROE=114%).
7. Integrar llamada a X2 en el `if __name__ == '__main__'` de X0 (antes de buscar soportes), o como script independiente.

---

## 6. Riesgos y limitaciones

| Riesgo | Mitigación |
|---|---|
| yfinance puede fallar / cambiar su API | Envolver en `try/except`, guardar último score válido con timestamp |
| CoinGecko rate limit (free tier: ~10-30 req/min) | Solo 2 coins. Sin problema con rate limit. |
| Datos de earnings desactualizados entre trimestres | Usar `forwardPE` en vez de `trailingPE` para valorización. El trailing puede estar distorsionado por trimestres con perdidas o atípicos. |
| ETH sin max_supply | `d3 = 0.5` (neutral). Suficiente por ahora. |
| Fear & Greed no diferencia BTC de ETH | Ambos usan el mismo índice. Aceptable — el mercado crypto se mueve en conjunto. |

---

## 7. Lo que NO entra en X2

- Indicadores técnicos (SMA, RSI, ATR) → X3
- Variables de contexto operativo (órdenes abiertas, capital disponible) → X3
- Macro global (VIX, DXY, Fed rate) → X3
- Recomendación dinámica de parámetros → X6

---

_Generado con experimentación real 2026-06-12. Actualizar si cambian las APIs o el universo de activos._
