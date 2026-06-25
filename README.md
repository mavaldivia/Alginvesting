# Alginvesting

Sistema de trading algorítmico personal. Identifica soportes y resistencias óptimos en activos financieros (crypto + acciones US) y ejecuta órdenes de compra de forma semi-automática vía MetaTrader5.

**No es un SaaS ni un producto para terceros.** Es una herramienta personal de inversión.

## Activos operados

`BTCUSD` · `ETHUSD` · `TSLA` · `GOOGL` · `NVDA` · `AMZN`

---

## Arquitectura

El sistema está organizado en 7 módulos (X0→X6):

| Módulo | Propósito | Estado |
|--------|-----------|--------|
| **X0** | Descarga precios vía MT5 + algoritmo de búsqueda de soportes/resistencias óptimos | Operativo |
| **X1** | Loop semi-automático de trading: buy limits, trailing stop, control de pérdida máxima | Operativo |
| **X2** | Score fundamental por activo (yfinance + CoinGecko + Fear & Greed) con historial diario | Operativo |
| **X3** | Features técnicas por precio/volumen (SMA, RSI, ATR, Bollinger, etc.) — alimenta X6 ([plan](docs/x3_plan.md)) | En diseño |
| **X4** | Backtester histórico sobre datos reales con parámetros dinámicos | En diseño ([plan](docs/x4_plan.md)) |
| **X5** | Modelos supervisados sobre store de trades (retorno esperado, probabilidad de pérdida) | Pendiente |
| **X6** | Cerebro macro: recomienda parámetros dinámicos a X0/X1 basándose en X2/X3/X5 | Pendiente |

---

## Flujo principal (X0 → X1)

```
X0 — Etapa 1: Descarga/actualiza CSVs OHLCV desde MT5
X0 — Etapa 2: Búsqueda de N soportes óptimos por activo → conjuntos_N/prod/{VALOR}_{N}.json
X1 — Loop: Lee soportes → Gestiona buy limits en MT5 → Trailing stop → Cierra si pérdida > PERDIDA_MAX
X2 — Diario: Score fundamental por activo → fundamentals/scores.json + x2_history.json
X3 — Incremental: Features técnicas por activo → features/{VALOR}.csv (actualizado en cada ciclo de X0, tras descarga H1)
```

---

## Algoritmo de soportes (X0)

El optimizador evalúa cada nivel de precio candidato con una función objetivo:

```
FO = mean(z) - LAMBDA * cv(H_n)
```

donde `z = y * w * h_dist * v * f` (factores activables individualmente en `config.py`):

- `y` — aislamiento temporal del nivel (distancia a velas vecinas que lo contengan)
- `w` — recencia (`t^N_EXP`, velas recientes pesan más)
- `h_dist` — proximidad normalizada al soporte asignado
- `v` — volumen normalizado (`Tick_Volume / max`)
- `f` — fuerza del rechazo (proporción de mecha vs. cuerpo de la vela)
- `cv(H_n)` — penalización por concentración de soportes en una zona del rango

### Optimizaciones implementadas

- **Evaluación incremental de FO** (`_fo_incremental_batch`): recalcula solo las ~3n/N filas afectadas por cada cambio de soporte — 33.5x más rápido que recalcular todo.
- **Vectorización del loop de candidatos** (`calcular_FO_batch`): M evaluaciones de FO → 1 pasada numpy con broadcasting (M, n).
- **Inicialización inteligente** (`_inicializar_conjunto_smart`): cold start por cuantiles de precio ordenados por `y×w`, en lugar de uniforme aleatorio.
- **Priorización por historial** (`mejora_acumulada`): EMA de mejoras aceptadas por soporte — los más activos se evalúan primero.
- **`DELTA_INICIAL` adaptativo**: se reduce (`* FACTOR_DELTA`) cada vez que converge, sin tocar el delta entre corridas cuando no converge.
- **Paralelización por (valor, N)**: `ProcessPoolExecutor` corre todos los pares en paralelo; monitor en vivo muestra progreso, FO y estado por combo.

El optimizador (`nuevo_optimizador_2`) usa búsqueda local iterativa con ajuste cuadrático y acepta solo mejoras relativas superiores a `DELTA_INICIAL`.

---

## Score fundamental (X2)

`X2_fundamentals.py` genera un score `[0,1]` por activo con dos componentes:

- **score_cross** (corte transversal): normaliza métricas dentro del universo de activos del día. Acciones vía yfinance (ROE, márgenes, FCF, crecimiento, P/E, deuda, analistas). Crypto vía yfinance + CoinGecko + Fear & Greed.
- **score_tendencia**: compara valores crudos de hoy vs. hace `DIAS_TENDENCIA=30` días desde `x2_history.json`. Delta por campo, normalizado y ponderado.

Score final = `(1 - W_TENDENCIA) × score_cross + W_TENDENCIA × score_tendencia` (0.5 neutral si < 7 días de historia).

Guarda historial en `fundamentals/x2_history.json` (upsert por fecha+activo), guard de día para no ejecutar dos veces, flag `--forzar`. Los pesos por activo son override-ables desde `config/active_parameters.json` (pensado para X6).

---

## Estructura del proyecto

```
scripts/
  X0_data_supports.py    # Descarga precios + algoritmo de soportes
  X1_trading.py          # Loop de trading semi-automático
  X2_fundamentals.py     # Score fundamental por activo
  config.py              # Parámetros centralizados (rutas, VALORES, n_sizes, algoritmo, trading)
Data/                    # CSVs OHLCV H1 por activo — trackeados en git (desde 2024-01-01)
Data_minuto/             # CSVs OHLCV M1 — para simulación intra-vela en X4, fuera de git
conjuntos_N/
  prod/                  # JSONs de soportes producción {VALOR}_{N}.json (X0 escribe, X1 lee)
  bt/                    # Cache de soportes para backtesting {VALOR}_{N}_bt.json
fundamentals/
  scores.json            # Score actual por activo
  x2_history.json        # Historial diario de scores y valores crudos
  x2_last_run.json       # Guard de ejecución diaria
plots/                   # Gráficos generados por X0 (Extremos, FO, Soportes, Zoom)
docs/
  X0/logs/              # Logs de convergencia por combo {valor}_{N}.json
  decisiones.md          # Decisiones técnicas del proyecto
  records.md             # Registro de sesiones de desarrollo
  vision.md              # Arquitectura completa X0→X6
  x2_plan.md             # Plan de implementación X2
  x4_plan.md             # Plan de implementación X4 (backtester)
  guia_git.md            # Flujo git Mac→Windows con Data/ trackeada
  documentacion_V0.md    # Análisis de convergencia del optimizador
Alginvesting_base/       # Versión anterior Windows/notebooks (solo lectura, referencia)
```

---

## Parámetros clave (`config.py`)

| Parámetro | Valor producción | Efecto |
|-----------|-----------------|--------|
| `N` (n_sizes) | 130 BTC/ETH, 120 resto | Cantidad de soportes activos por activo |
| `K` | 1 | Peso aislamiento futuro vs. pasado |
| `N_EXP` | 1.3 | Exponente de recencia |
| `M` | 30 | Candidatos evaluados por soporte en cada paso |
| `LAMBDA` | 1/500 | Penalización por dispersión desigual |
| `DELTA_INICIAL` | 1e-4 | Mejora relativa mínima para aceptar cambio |
| `FACTOR_DELTA` | 0.7 | Factor de reducción del delta al converger |
| `N_MAX_MODELS` | None | Top N combos a procesar (None = todos) |
| `W_TENDENCIA` | 0.20 | Peso del score_tendencia en X2 |
| `DIAS_TENDENCIA` | 30 | Ventana de comparación histórica en X2 |

---

## Flujo Mac ↔ Windows

```
Mac (Claude Code)           GitHub              Windows (ejecución)
─────────────────     ───────────────     ──────────────────────────
Desarrollo + refactor  →  git push   →    git pull
                                          python scripts/X0_data_supports.py
                                          python scripts/X1_trading.py
                                          python scripts/X2_fundamentals.py
```

MT5 solo disponible en Windows. El desarrollo ocurre en Mac. Ver [`docs/guia_git.md`](docs/guia_git.md) para manejo de `Data/` (trackeada en git).

---

## Setup

```bash
conda activate revenAI
```

Requiere MetaTrader5 instalado (solo Windows) con cuenta de broker configurada.

Librerías clave: `MetaTrader5`, `yfinance`, `pandas`, `numpy`, `matplotlib`, `mplfinance`

---

## Ejecución (Windows)

```bash
# Solo actualizar precios (sin recalcular soportes)
python scripts/X0_data_supports.py --opcion 0

# Actualizar precios + recalcular soportes
python scripts/X0_data_supports.py --opcion 1

# Recalcular soportes sin actualizar precios
python scripts/X0_data_supports.py --opcion 2

# Loop continuo (reinicia el ciclo completo al terminar)
python scripts/X0_data_supports.py --opcion 1 --loop

# Ejecutar loop de trading
python scripts/X1_trading.py

# Score fundamental (guard de día, no re-ejecuta si ya corrió hoy)
python scripts/X2_fundamentals.py

# Score fundamental forzado (ignora guard de día)
python scripts/X2_fundamentals.py --forzar
```

---

## Changelog

- **2026-06-25** — fix: corregir regex en X4B_crear_version_backtesting
- **2026-06-24** — docs: simplificar guia_git_v2 con git add -A
- **2026-06-24** — docs: guia_git_v2 + fix tracking resources + update CLAUDE.md
- **2026-06-24** — fix: suprimir stdout en workers para proteger monitor ANSI
- **2026-06-22** — X4: implementar X4_backtester.py + migrar paths prod
- **2026-06-20** — docs: agregar ítems X4B y X4.py al TO DO
- **2026-06-20** — docs: actualizar plan X4 con comentarios de sesión
- **2026-06-19** — docs: paso_a_paso_git + guia_git simplificada para Windows
- **2026-06-19** — refactor: reestructurar directorios del proyecto
- **2026-06-18** — X3: implementar X3_technical_features.py
- **2026-06-18** — X1: robustez — try/except por activo + fixes sys.exit
- **2026-06-18** — config: APALANCAMIENTO por activo + métricas de cuenta en x4_plan
- **2026-06-15** — X0: fijar OA en bt + guard en optimizador
- **2026-06-14** — X0: descargar Data_minuto/ con velas M1 en Etapa 1
- **2026-06-14** — X0: pintar OA en negro en plot Soportes + leyenda
- **2026-06-14** — X0: fix dist_max batch + sort/dedup CSVs
- **2026-06-14** — X0+X2: llamar X2 en cada ciclo + historial por periodos
- **2026-06-14** — X0: mostrar LAMBDA y FO warm start antes del optimizador
- **2026-06-14** — gitignore: actualizar rutas (Data/, Data_minuto/, limpiar conjuntosN old)
- **2026-06-14** — X0: revert optimizador a base + S6 + reiniciar_x0 + plots en docs/X0
- **2026-06-14** — X4: plan de implementación en docs/x4_plan.md
- **2026-06-14** — X0: FO inicial en monitor + cambios_netos vs warm start
- **2026-06-13** — Prioridad_0: tiempo ejecución scripts + `[listo Xs]` en monitor
- **2026-06-12** — X2: score_tendencia + historial con campo `raw` + validadores
- **2026-06-12** — X2: implementar X2_fundamentals.py (yfinance + CoinGecko + Fear & Greed)
- **2026-06-12** — docs: guía git Mac→Windows (`docs/guia_git.md`)
- **2026-06-12** — X0: separar rutas prod vs bt (`conjuntos_N/prod/` y `conjuntos_N/bt/`)
- **2026-06-11** — S1: evaluación incremental de la FO (33.5x speedup en hot path)
- **2026-06-11** — S6: vectorización del loop de candidatos M con numpy broadcasting
- **2026-06-11** — S2: inicialización inteligente del conjunto N por cuantiles de precio
- **2026-06-11** — S4: priorización de soportes por historial de mejoras (EMA)
- **2026-06-11** — N_MAX_MODELS + flag `--loop` en X0 + logs de convergencia por combo
- **2026-06-10** — Fix crítico en condición de mejora + monitor de progreso en vivo
- **2026-06-09** — Cache de backtesting (`_bt_warm_start` / `_bt_guardar`) + sin sufijo `_beta`
- **2026-06-08** — Diseño simulación intra-vela para X4 + visión X0→X6 en docs/vision.md
- **2026-06-08** — DELTA_INICIAL adaptativo entre corridas + órdenes activas fijas en optimizador
- **2026-06-07** — Factores `v` (volumen) y `f` (fuerza del rechazo) en scoring de soportes
- **2026-06-07** — Renombrar Transversal.py → config.py + centralizar todos los parámetros
- **2026-06-07** — Migrar conjuntosN2 de pickle a JSON
- **2026-06-07** — Vectorizar calcular_distancias (~19x) + asignar_soporte (~45-178x)
- **2026-06-06** — Paralelizar búsqueda de soportes por (valor, N) con ProcessPoolExecutor
