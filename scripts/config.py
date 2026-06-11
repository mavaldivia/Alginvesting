"""
config.py

Parámetros centralizados del proyecto, agrupados por tema (rutas, activos,
datos históricos, calidad del algoritmo, velocidad, visualizaciones, trading)
en vez de por script (X0/X1) — varios temas son usados por ambos.
"""

from pathlib import Path

# ─── Rutas ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
CARPETA_DATA = BASE_DIR / 'Data'
CARPETA_N2 = BASE_DIR / 'conjuntos_N'
CARPETA_PLOTS = BASE_DIR / 'plots'
CARPETA_LOGS = BASE_DIR / 'docs' / 'X0' / 'logs'

# ─── Activos y universo de soportes ───────────────────────────────────────────

VALORES = ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']

# Cantidad de soportes evaluados por activo en el grid search de X0
"""
n_sizes = {
    'BTCUSD': [50, 60, 70, 80, 90, 100, 110, 120],
    'ETHUSD': [50, 60, 70, 80, 90, 100, 110, 120],
    'TSLA':   [50, 60, 70, 80, 90, 100, 110, 120],
    'GOOGL':  [50, 60, 70, 80, 90, 100, 110, 120],
    'NVDA':   [50, 60, 70, 80, 90, 100, 110, 120],
    'AMZN':   [50, 60, 70, 80, 90, 100, 110, 120],
}
"""

n_sizes = {
    'BTCUSD': [70, 100],
    'ETHUSD': [70, 100],
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

# ─── Datos históricos ─────────────────────────────────────────────────────────

FECHA_INICIAL = '2022-01-01'    # inicio del período considerado para calcular soportes

# ─── Calidad del algoritmo de búsqueda de soportes ────────────────────────────
# Ver CLAUDE.md "Parámetros del algoritmo — efecto de cada uno" para el detalle
# de cómo cada uno afecta el resultado de la optimización.

K = 1       # peso de las distancias futuras vs. pasadas: y = dist_izq + K * dist_der
N_EXP = 1.3 # exponente de ponderación temporal: w = t^N_EXP  (t=0 más antiguo, t=1 más reciente)

# Factores activos en el producto z = y * w * h_dist * v * f (calcular_FO).
# Permite activar/desactivar cada uno para experimentar con el scoring sin tocar el código.
parametros_soportes = {
    'y': True,       # aislamiento: y = Low_left + High_left + K * (Low_right + High_right)
    'w': True,       # recencia: w = t^N_EXP
    'h_dist': True,  # proximidad al soporte asignado: h_dist = 1 - dist²/dist_max
    'v': True,       # volumen normalizado: v = Tick_Volume / Tick_Volume.max()  (proxy de actividad en ese nivel)
    'f': True,       # fuerza del rechazo: f = 1 - |Close - Open| / (High - Low)  (proporción del rango que fue "mecha")
}

LAMBDA = 1 / 500    # penaliza dispersión desigual entre soportes: FO = mean(z) - LAMBDA * cv(H_n)
M = 30              # candidatos evaluados por soporte en cada paso (linspace entre vecinos)
DELTA_INICIAL = 1e-4  # mejora mínima relativa para aceptar un cambio (evita ruido); semilla para la primera corrida de cada (valor, N)
FACTOR_DELTA = 0.7    # factor de presión al converger: si el optimizador convergió, delta_next = FACTOR_DELTA * delta_actual

# ─── Velocidad / cómputo ──────────────────────────────────────────────────────

# calcular_distancias: tamaño de bloque para vectorizar sin construir la matriz (n x n) completa
BLOQUE_DISTANCIAS = 2000

MAX_ITERS = 10000  # tope de iteraciones del optimizador (cota del tiempo de ejecución)

# Combos a ejecutar por ciclo en modo --loop.
# None = todos los combos en cada ciclo (comportamiento original).
# Entero = selecciona los N pares (valor, N) con mayor delta_inicial actual (más prometedores).
N_MAX_MODELS = None

# ─── Visualizaciones ──────────────────────────────────────────────────────────
# Desactivadas por defecto para ejecución sin cabeza en Windows.

GRAFICAR_EXTREMOS = False
GRAFICAR_FO = True
GRAFICAR_SOPORTES = True
GRAFICAR_ZOOM = False

# ─── Trading: ejecución y gestión de riesgo (X1) ──────────────────────────────

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
