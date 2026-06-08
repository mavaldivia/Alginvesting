# Alginvesting

Sistema de trading algorítmico personal. Detecta soportes y resistencias óptimas en activos financieros y ejecuta órdenes de compra semi-automáticamente vía MetaTrader5.

## Activos

`BTCUSD` · `ETHUSD` · `TSLA` · `GOOGL` · `NVDA` · `AMZN`

## Flujo principal

```
X0: Actualizar precios → Buscar soportes óptimos → Guardar en conjuntosN2/
X1: Leer soportes → Conectar MT5 → Gestionar órdenes (buy limit + trailing stop)
```

## Setup

```bash
conda activate revenAI
```

Requiere MetaTrader5 instalado (solo Windows) con cuenta de broker configurada.

## Estructura

```
scripts/
  X0_data_supports.py    # Descarga precios + algoritmo de soportes
  X1_trading.py          # Loop de trading semi-automático
  config.py              # Parámetros centralizados (rutas, VALORES, n_sizes, X0/X1)
Data/                    # CSVs OHLCV — generados por X0, no en git
conjuntosN2/             # Pickles de soportes — generados por X0, no en git
docs/
  decisiones.md          # Decisiones técnicas del proyecto
Alginvesting_base/       # Versión anterior (referencia, solo lectura)
```

## Ejecución (Windows)

```bash
# 1. Actualizar datos y recalcular soportes
python scripts/X0_data_supports.py

# 2. Ejecutar algoritmo de trading
python scripts/X1_trading.py
```
