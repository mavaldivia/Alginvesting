"""
config.py

Parámetros centralizados del proyecto: rutas, activos y configuración de
los algoritmos de X0 (búsqueda de soportes) y X1 (trading).
"""

from pathlib import Path

# ─── Rutas ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
CARPETA_DATA = BASE_DIR / 'Data'
CARPETA_N2 = BASE_DIR / 'conjuntosN2'

# ─── Activos ──────────────────────────────────────────────────────────────────

VALORES = ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']

# Cantidad de soportes evaluados por activo en el grid search de X0
n_sizes = {
    'BTCUSD': [50, 60, 70, 80, 90, 100, 110, 120],
    'ETHUSD': [50, 60, 70, 80, 90, 100, 110, 120],
    'TSLA':   [50, 60, 70, 80, 90, 100, 110, 120],
    'GOOGL':  [50, 60, 70, 80, 90, 100, 110, 120],
    'NVDA':   [50, 60, 70, 80, 90, 100, 110, 120],
    'AMZN':   [50, 60, 70, 80, 90, 100, 110, 120],
}

# Cantidad de soportes activos en producción, usada por X1
n_sizes_ejecucion = {
    'BTCUSD': 130,
    'ETHUSD': 130,
    'TSLA': 120,
    'GOOGL': 120,
    'NVDA': 120,
    'AMZN': 120,
}

# ─── X0: búsqueda de soportes ─────────────────────────────────────────────────

FECHA_INICIAL = '2024-01-01'    # inicio del período considerado para calcular soportes

# Puntaje y (aislamiento de cada vela)
K = 1       # peso de las distancias futuras vs. pasadas: y = dist_izq + K * dist_der
N_EXP = 1.3 # exponente de ponderación temporal: w = t^N_EXP  (t=0 más antiguo, t=1 más reciente)

# calcular_distancias: tamaño de bloque para vectorizar sin construir la matriz (n x n) completa
BLOQUE_DISTANCIAS = 2000

# Optimizador
M = 30              # candidatos evaluados por soporte en cada paso (linspace entre vecinos)
LAMBDA = 1 / 500    # penaliza dispersión desigual entre soportes: FO = mean(z) - LAMBDA * cv(H_n)
MAX_ITERS = 10000
DELTA_INICIAL = 1e-4  # mejora mínima relativa para aceptar un cambio (evita ruido)

# Visualizaciones (desactivadas por defecto para ejecución sin cabeza en Windows)
GRAFICAR_EXTREMOS = False
GRAFICAR_FO = False
GRAFICAR_SOPORTES = False
GRAFICAR_ZOOM = False

# ─── X1: trading ──────────────────────────────────────────────────────────────

# a: ganancia mínima en USD para activar el primer SL ganador
# b: distancia en USD (normalizada por L) que mantiene el SL bajo el precio actual
A = 6
B = 2

TS = 0.5  # segundos de espera entre ciclos cuando no hay posiciones activas en seguimiento

PERDIDA_MAX = 50  # USD — si la pérdida de una posición abierta supera este valor, se cierra

PRUEBA_TRAILING_STOP = False  # True: solo prueba el trailing stop, no crea nuevas órdenes

# Tamaño mínimo de lote por activo (granularidad del broker)
LOTAJES = {
    'BTCUSD': 0.01,
    'ETHUSD': 0.1,
    'TSLA':   0.01,
    'GOOGL':  0.01,
    'NVDA':   0.01,
    'AMZN':   0.01,
}

# Unidades del activo por lote (multiplica la exposición en USD)
UNITS = {
    'BTCUSD': 1,
    'ETHUSD': 1,
    'TSLA':   100,
    'GOOGL':  100,
    'NVDA':   100,
    'AMZN':   100,
}
