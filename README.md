# Alginvesting

Sistema de trading algorítmico personal. Identifica soportes y resistencias óptimos en activos financieros (crypto + acciones US) y ejecuta órdenes de compra de forma semi-automática vía MetaTrader5.

**No es un SaaS ni un producto para terceros.** Es una herramienta personal de inversión.

## Activos operados

`BTCUSD` · `ETHUSD` · `TSLA` · `GOOGL` · `NVDA` · `AMZN`

---

## Arquitectura

El sistema está organizado en 7 módulos (X0→X6), de los cuales X0 y X1 están operativos:

| Módulo | Propósito | Estado |
|--------|-----------|--------|
| **X0** | Descarga precios vía MT5 + algoritmo de búsqueda de soportes/resistencias óptimos | Operativo |
| **X1** | Loop semi-automático de trading: buy limits, trailing stop, control de pérdida máxima | Operativo |
| **X2** | Score fundamental por activo (ingresos, P/E, ROE, on-chain para crypto) | Pendiente |
| **X3** | Features técnicos (SMA, RSI, ATR, Bollinger, contexto operativo) | Pendiente |
| **X4** | Backtester histórico sobre datos reales con parámetros dinámicos | En diseño |
| **X5** | Modelos supervisados sobre store de trades (retorno esperado, probabilidad de pérdida) | Pendiente |
| **X6** | Cerebro macro: recomienda parámetros dinámicos a X0/X1 basándose en X2/X3/X5 | Pendiente |

---

## Flujo principal (X0 → X1)

```
X0 — Etapa 1: Descarga/actualiza CSVs OHLCV desde MT5
X0 — Etapa 2: Búsqueda de N soportes óptimos por activo → conjuntos_N/{VALOR}_{N}.json
X1 — Loop: Lee soportes → Gestiona buy limits en MT5 → Trailing stop → Cierra si pérdida > PERDIDA_MAX
```

---

## Algoritmo de soportes (X0)

El optimizador evalúa cada nivel de precio candidato con una función objetivo:

```
FO = mean(z) - LAMBDA * cv(H_n)
```

donde `z = y * w * h_dist * v * f` (factores configurables en `config.py`):

- `y` — aislamiento temporal del nivel (distancia a velas vecinas que lo contengan)
- `w` — recencia (`t^N_EXP`, velas recientes pesan más)
- `h_dist` — proximidad normalizada al soporte asignado
- `v` — volumen normalizado (`Tick_Volume / max`)
- `f` — fuerza del rechazo (proporción de mecha vs. cuerpo de la vela)
- `cv(H_n)` — penalización por concentración de soportes en una zona del rango

El optimizador (`nuevo_optimizador_2`) usa búsqueda local iterativa con ajuste cuadrático y `DELTA_INICIAL` adaptativo que se reduce (`* FACTOR_DELTA`) cada vez que converge.

---

## Estructura del proyecto

```
scripts/
  X0_data_supports.py    # Descarga precios + algoritmo de soportes
  X1_trading.py          # Loop de trading semi-automático
  config.py              # Parámetros centralizados (rutas, VALORES, n_sizes, algoritmo, trading)
Data/                    # CSVs OHLCV H1 por activo — trackeados en git (historia desde 2024-01-01)
Data_minuto/             # CSVs OHLCV M1 — para simulación intra-vela en X4, fuera de git
conjuntos_N/             # JSONs de soportes {VALOR}_{N}.json — generados por X0, fuera de git
plots/                   # Gráficos generados por X0 (Extremos, FO, Soportes, Zoom)
docs/
  decisiones.md          # Decisiones técnicas del proyecto
  records.md             # Registro de sesiones de desarrollo
  vision.md              # Arquitectura completa X0→X6
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

---

## Flujo Mac ↔ Windows

```
Mac (Claude Code)           GitHub              Windows (ejecución)
─────────────────     ───────────────     ──────────────────────────
Desarrollo + refactor  →  git push   →    git pull
                                          python scripts/X0_data_supports.py
                                          python scripts/X1_trading.py
```

MT5 solo disponible en Windows. El desarrollo ocurre en Mac y se ejecuta en Windows.

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

# Ejecutar loop de trading
python scripts/X1_trading.py
```

---

## Changelog

- **2026-06-14** — X4: plan de implementación en docs/x4_plan.md
- **2026-06-14** — X0: FO inicial en monitor + cambios_netos vs warm start
- **2026-06-13** — Prioridad_0: tiempo ejecución scripts + listo Xs en monitor
- **2026-06-12** — X2: score_tendencia + date en historial + validadores
- **2026-06-12** — X2: implementar X2_fundamentals.py + validadores
- **2026-06-12** — docs: guía git Mac→Windows
- **2026-06-12** — X2: historial del score — sección 3.5 en x2_plan.md + TO DO actualizados
- **2026-06-12** — X2: investigación fuentes + plan docs/x2_plan.md + ítem TO DO
- **2026-06-12** — Correcciones X0 260612 + sep rutas prod vs backtesting
- **2026-06-11** — S1: evaluación incremental de la FO (33.5x speedup)
- **2026-06-11** — N_MAX_MODELS + loop continuo: `_seleccionar_combos` + `--loop` flag en X0
- **2026-06-11** — Logs de convergencia por combo: `_guardar_log_convergencia` + `CARPETA_LOGS` en config
- **2026-06-11** — Análisis de convergencia de `nuevo_optimizador_2` + docs/documentacion_V0.md + X0_aux al TO DO
- **2026-06-10** — TO DO: nuevos ítems X0/X4 + skill /todos completada
- **2026-06-10** — Fixes al optimizador + monitor de progreso en vivo + mejoras de visualización
- **2026-06-09** — conjuntos_N + sin _beta + bt cache para backtesting
- **2026-06-09** — TO DO: fecha máxima por tupla valor-N en X4
- **2026-06-08** — Diseño simulación intra-vela para X4_backtester
- **2026-06-08** — Visión: arquitectura X0→X6 + TO DO en CLAUDE.md
- **2026-06-08** — DELTA_INICIAL adaptativo + órdenes activas fijas en optimizador
- **2026-06-07** — DELTA_INICIAL adaptativo entre corridas
- **2026-06-07** — Agregar volumen (v) y fuerza del rechazo (f) al scoring de soportes
- **2026-06-07** — Renombrar transversal.py a config.py y centralizar parámetros
- **2026-06-07** — Migrar conjuntosN2 de pickle a JSON
- **2026-06-07** — Vectorizar calcular_distancias + asignar_soporte
- **2026-06-06** — Paralelizar búsqueda de soportes por (valor, N)
