# scripts/config_x5_default.py
# PLANTILLA por defecto de la config del pipeline de X5 (versionada en git).
# resources/x5/config_x5.py está en .gitignore, por lo que no llega al clonar en
# otra máquina. X5/X4 copian este archivo a resources/x5/config_x5.py en el primer
# arranque si no existe (las rutas basadas en __file__ se resuelven en el destino).
# No importa config.py — independiente de la config de producción.
# X4 en modo --x5 lee exclusivamente el archivo copiado en resources/x5/.

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent  # raíz del proyecto

# ─── Versión ─────────────────────────────────────────────────────────────────
# Identificador del pipeline (X4 --x5 lo usa en prints/checkpoints). No es una
# versión de X4: la recolección de X5 es independiente de las versiones V0/V1/...

version = 'x5'

# ─── Activos ─────────────────────────────────────────────────────────────────

valores = ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']

# N para el cache de soportes BT — debe cubrir el máximo de X5_PARAM_RANGES['n_sizes_ejecucion']
n_sizes = {
    'BTCUSD': 200,
    'ETHUSD': 200,
    'TSLA':   180,
    'GOOGL':  180,
    'NVDA':   180,
    'AMZN':   180,
}

# Baseline de soportes activos en ejecución (punto de partida para la exploración)
n_sizes_ejecucion = {
    'BTCUSD': 150,
    'ETHUSD': 150,
    'TSLA':   150,
    'GOOGL':  150,
    'NVDA':   150,
    'AMZN':   150,
}

# ─── Fechas ──────────────────────────────────────────────────────────────────

fecha_inicio = '2024-01-01'
fecha_fin    = 'F'   # 'F' = hasta la última vela disponible

# ─── Capital y riesgo ────────────────────────────────────────────────────────

capital_inicial     = 1_000_000.0   # USD virtual por activo (sin restricción real de margen)
MARGEN_LIBRE_MIN_BT = 50.0          # USD — buffer mínimo para abrir/ejecutar OE

PERDIDA_MAX_BT = {
    'BTCUSD': 120.0,
    'ETHUSD': 120.0,
    'TSLA':   120.0,
    'GOOGL':  120.0,
    'NVDA':   120.0,
    'AMZN':   120.0,
}

# ─── Recálculo de soportes ───────────────────────────────────────────────────
# En modo --x5 esta cadencia también gobierna la REGENERACIÓN de params: cada
# `delta_recalculo_soportes` días se eligen params nuevos (explore aleatorio o
# exploit as-of-t) y se recalculan los soportes cold-start hasta t con ellos.
# Dispara en la primera vela disponible tras cumplirse el umbral (no exige una
# hora exacta: acciones sin sesión 24h no siempre tienen vela en cualquier hora).

delta_recalculo_soportes = 5    # días

# Warm start: si ya existe una solución del combo (valor, N) en un t* <= t, se usa
# como solución inicial del optimizador aunque los params del tramo hayan cambiado
# (el delta adaptado NO se hereda: cada tramo parte del delta semilla).
# False → cada recálculo arranca desde puntos aleatorios (mucho más lento).
X5_WARM_START_SOPORTES = True

# ─── Algoritmo de soportes — baseline ────────────────────────────────────────
# K, N_EXP y LAMBDA son el punto de partida; X5 los varía dentro de X5_PARAM_RANGES.

K     = 1
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

# ─── Trading — parámetros por activo ─────────────────────────────────────────
# Todos como dict por activo. A y B son baseline; X5 los varía dentro de X5_PARAM_RANGES.

A = {
    'BTCUSD': 6.0,
    'ETHUSD': 6.0,
    'TSLA':   6.0,
    'GOOGL':  6.0,
    'NVDA':   6.0,
    'AMZN':   6.0,
}

B = {
    'BTCUSD': 2.0,
    'ETHUSD': 2.0,
    'TSLA':   2.0,
    'GOOGL':  2.0,
    'NVDA':   2.0,
    'AMZN':   2.0,
}

MIN_LOTAJES = {
    'BTCUSD': 0.01,
    'ETHUSD': 0.1,
    'TSLA':   0.01,
    'GOOGL':  0.01,
    'NVDA':   0.01,
    'AMZN':   0.01,
}

# Multiplicador baseline (X5 varía LOTAJES_M dentro de X5_PARAM_RANGES)
LOTAJES_M = {
    'BTCUSD': 1,
    'ETHUSD': 1,
    'TSLA':   1,
    'GOOGL':  1,
    'NVDA':   1,
    'AMZN':   1,
}

LOTAJES = {v: LOTAJES_M[v] * MIN_LOTAJES[v] for v in LOTAJES_M}

UNITS = {
    'BTCUSD': 1,
    'ETHUSD': 1,
    'TSLA':   100,
    'GOOGL':  100,
    'NVDA':   100,
    'AMZN':   100,
}

APALANCAMIENTO = {
    'BTCUSD': 400,
    'ETHUSD': 400,
    'TSLA':   5,
    'GOOGL':  5,
    'NVDA':   5,
    'AMZN':   5,
}

# ─── Recolección X5 ──────────────────────────────────────────────────────────

EXPLORATION_RATE = 0.30   # fracción de ciclos con params aleatorios
N_CICLOS_BT      = 10     # ciclos del loop explore/exploit por activo

# ─── Rangos de exploración por parámetro y activo ────────────────────────────

X5_PARAM_RANGES = {
    'K':     {v: (0.5, 2.0) for v in valores},
    'N_EXP': {v: (0.5, 3.0) for v in valores},
    'LAMBDA': {v: (1/1000, 1/50) for v in valores},
    'A':     {v: (2.0, 20.0) for v in valores},
    'B':     {v: (0.5, 5.0) for v in valores},
    'n_sizes_ejecucion': {
        'BTCUSD': (50, 200), 'ETHUSD': (50, 200),
        'TSLA':   (40, 180), 'GOOGL':  (40, 180),
        'NVDA':   (40, 180), 'AMZN':   (40, 180),
    },
    'LOTAJES_M':  {v: (1, 5) for v in valores},
    'PERDIDA_MAX': {v: (100, 300) for v in valores},
}

# ─── Rutas ───────────────────────────────────────────────────────────────────

_X5_DIR             = Path(__file__).parent
CARPETA_STORE       = _X5_DIR                    # {ACTIVO}_store.csv
CARPETA_MODELOS     = _X5_DIR / 'models'
CARPETA_N_BT        = _X5_DIR / 'conjuntos_N'   # cache de soportes BT para este pipeline
CARPETA_PERFORMANCE = _X5_DIR / 'Performance'
CARPETA_DATA        = BASE_DIR / 'Data'
CARPETA_DATA_MINUTO = BASE_DIR / 'Data_minuto'

# Aislamiento del backtest por activo: X4 --x5 --activo {A} usa `bt_{A}` para
# checkpoint/equity/logs, de modo que los workers paralelos no colisionen.
CARPETA_RESOURCES   = _X5_DIR / 'bt'
CARPETA_LOGS_BT     = CARPETA_RESOURCES / 'logs'
