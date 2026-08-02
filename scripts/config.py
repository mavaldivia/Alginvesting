"""
config.py

Parámetros centralizados del proyecto, agrupados por tema (rutas, activos,
datos históricos, calidad del algoritmo, velocidad, visualizaciones, trading)
en vez de por script (X0/X1) — varios temas son usados por ambos.
"""

import sys
from pathlib import Path

# ─── Consola UTF-8 (Windows) ──────────────────────────────────────────────────
# La consola/pipe de Windows usa cp1252 y no puede imprimir glifos como → ═ ✔
# presentes en los prints de X0–X5 (UnicodeEncodeError →). Todos los scripts
# importan config, así que forzar UTF-8 en stdout/stderr aquí lo cubre en un punto.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

# ─── Rutas ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
CARPETA_DATA = BASE_DIR / 'Data'
CARPETA_DATA_MINUTO = BASE_DIR / 'Data_minuto'
CARPETA_N_PROD = BASE_DIR / 'resources' / 'conjuntos_N'
CARPETA_PLOTS = BASE_DIR / 'resources' / 'x0' / 'plots'
CARPETA_LOGS = BASE_DIR / 'resources' / 'x0' / 'logs'
CARPETA_FUNDAMENTALS = BASE_DIR / 'resources' / 'x2'

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


n_sizes = {
    'BTCUSD': [70, 100],
    'ETHUSD': [70, 100],
}
"""

n_sizes = {
    'BTCUSD': [250],
    'ETHUSD': [250],
    'TSLA':   [250],
    'GOOGL':  [250],
    'NVDA':   [250],
    'AMZN':   [250],
}

# Cantidad de soportes activos en producción, usada por X1
n_sizes_ejecucion = {
    'BTCUSD': 250,
    'ETHUSD': 250,
    'TSLA': 250,
    'GOOGL': 250,
    'NVDA': 250,
    'AMZN': 250,
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

LAMBDA = 1 / 5    # penaliza dispersión desigual entre soportes: FO = mean(z) - LAMBDA * cv(H_n)
M = 30              # candidatos evaluados por soporte en fase fine (linspace entre vecinos)
M_COARSE = 5        # candidatos en fase coarse (exploración barata antes del refinamiento fino)
DELTA_INICIAL = 1e-4  # mejora mínima relativa para aceptar un cambio (evita ruido); semilla para la primera corrida de cada (valor, N)
FACTOR_DELTA = 0.7    # factor de presión al converger: si el optimizador convergió, delta_next = FACTOR_DELTA * delta_actual

# ─── Velocidad / cómputo ──────────────────────────────────────────────────────

# calcular_distancias: tamaño de bloque para vectorizar sin construir la matriz (n x n) completa
BLOQUE_DISTANCIAS = 2000

MAX_ITERS = 10000  # tope de iteraciones del optimizador (cota del tiempo de ejecución)

# Combos a ejecutar por ciclo en modo --loop.
# None = todos los combos en cada ciclo (comportamiento original).
# Entero = selecciona los N pares (valor, N) con mayor delta_inicial actual (más prometedores).
N_MAX_MODELS = 6

# ─── Visualizaciones ──────────────────────────────────────────────────────────
# Desactivadas por defecto para ejecución sin cabeza en Windows.

GRAFICAR_EXTREMOS = False
GRAFICAR_FO = True
GRAFICAR_SOPORTES = True
GRAFICAR_ZOOM = False

# ─── Control de estado X0 ─────────────────────────────────────────────────────
# Si True, al inicio de la Etapa 2 elimina logs, soportes y plots generados por X0,
# y luego se resetea a False automáticamente en este archivo.

reiniciar_x0 = False

# ─── X2: score fundamental ────────────────────────────────────────────────────

X2_HORA_EJECUCION = '21:00'   # re-ejecución forzada diaria desde el loop de X0
W_TENDENCIA   = 0.20  # peso del score_tendencia en el score final (0 = solo cross-sectional)
DIAS_TENDENCIA = 30   # ventana de días hacia atrás para comparar el activo consigo mismo

# Pesos iniciales del score fundamental — X6 puede sobreescribir vía config/active_parameters.json
PESOS_STOCK = {
    'roe': 0.20, 'margins': 0.15, 'fcf_yield': 0.10,
    'rev_growth': 0.15, 'earn_growth': 0.10,
    'forward_pe': 0.10, 'ev_ebitda': 0.05,
    'debt_eq': 0.05, 'short_pct': 0.05, 'analyst': 0.05,
}

PESOS_CRYPTO = {
    'hash': 0.20, 'vol_mcap': 0.15, 'supply': 0.10,
    'mcap': 0.10, 'momentum_7d': 0.15, 'momentum_30d': 0.10,
    'fear_greed': 0.20,
}

# ─── X3: features técnicas ────────────────────────────────────────────────────

CARPETA_FEATURES = BASE_DIR / 'resources' / 'x3'

X3_VENTANAS = {
    'sma': [20, 50, 200],
    'ema': [12, 26],
    'rsi': 14,
    'macd': (12, 26, 9),        # fast, slow, signal
    'atr': 14,
    'bb': (20, 2),               # window, k
    'roc': [10, 20],
    'vol': [24, 168],            # horas: 1d, 7d
    'drawdown': [20, 50],
    'trend_slope': [20, 50],
    'density_delta': 0.02,       # banda ±2% para densidad de soportes
}

# ─── Trading: ejecución y gestión de riesgo (X1) ──────────────────────────────

# Parámetros por activo (formato alineado con config_x5). X1 los indexa por activo.
# A: ganancia mínima en USD para activar el primer SL ganador
# B: distancia en USD (normalizada por L) que mantiene el SL bajo el precio actual
A = {
    'BTCUSD': 4,
    'ETHUSD': 4,
    'TSLA':   4,
    'GOOGL':  4,
    'NVDA':   4,
    'AMZN':   4,
}

B = {
    'BTCUSD': 1.5,
    'ETHUSD': 1.5,
    'TSLA':   1.5,
    'GOOGL':  1.5,
    'NVDA':   1.5,
    'AMZN':   1.5,
}

TS = 0.01  # segundos de espera entre ciclos cuando no hay posiciones activas en seguimiento

# USD — si la pérdida de una posición abierta supera este valor, se cierra
PERDIDA_MAX = {
    'BTCUSD': 120,
    'ETHUSD': 120,
    'TSLA':   120,
    'GOOGL':  120,
    'NVDA':   120,
    'AMZN':   120,
}

# Tamaño mínimo de lote por activo (granularidad del broker)
MIN_LOTAJES = {
    'BTCUSD': 0.01,
    'ETHUSD': 0.1,
    'TSLA':   0.01,
    'GOOGL':  0.01,
    'NVDA':   0.01,
    'AMZN':   0.01,
}

# Multiplicador de lote por activo — X6 ajusta este valor; siempre entero >= 1
LOTAJES_M = {
    'BTCUSD': 1,
    'ETHUSD': 1,
    'TSLA':   1,
    'GOOGL':  1,
    'NVDA':   1,
    'AMZN':   1,
}

# Lote efectivo: LOTAJES[v] = LOTAJES_M[v] * MIN_LOTAJES[v]
LOTAJES = {v: LOTAJES_M[v] * MIN_LOTAJES[v] for v in LOTAJES_M}

# Unidades del activo por lote (multiplica la exposición en USD)
UNITS = {
    'BTCUSD': 1,
    'ETHUSD': 1,
    'TSLA':   100,
    'GOOGL':  100,
    'NVDA':   100,
    'AMZN':   100,
}

# Apalancamiento por activo según configuración del broker
APALANCAMIENTO = {
    'BTCUSD': 400,
    'ETHUSD': 400,
    'TSLA':   5,
    'GOOGL':  5,
    'NVDA':   5,
    'AMZN':   5,
}

# ─── Modo de ejecución ────────────────────────────────────────────────────────
# "est" → X1/X0/X4 usan los parámetros definidos en este archivo (estático).
# "din" → X1/X0/X4 leen config/active_parameters.json generado por X5.
#          Si model_status[activo] == "untrained" para un activo concreto,
#          ese activo cae back a los valores de este archivo.
#          La transición es por activo: BTCUSD puede estar en "din" mientras TSLA sigue en "est".

TIPO_EJECUCION = "est"

# ─── X5 — Backtester y surrogate model ───────────────────────────────────────

CARPETA_X5 = BASE_DIR / 'resources' / 'x5'

# Loop explore/exploit
X5_EXPLORATION_RATE      = 0.30   # fracción de ciclos con params aleatorios
X5_CAPITAL_BT            = 1_000_000  # capital virtual por activo (sin restricción de margen)
X5_FREQ_REGISTRO_PERIODICO = 4    # snapshot periódico cada N velas H1 (si hay OA)
X5_CKPT_INTERVAL         = 100    # guardar checkpoint cada N velas del ciclo actual
X5_RECALC_SOPORTES_CADA  = 168    # actualizar soportes del bt cache cada N velas H1 (≈1 semana)
X5_N_CICLOS_BT           = 20     # máx de ciclos de backtesting en --recolectar

# Modo demo (--recolectar --demo)
X5_DEMO_PLOTS       = True   # guardar PNG de precios + soportes en cada recálculo
X5_DEMO_ABRIR_PLOTS = True   # además abrirlo en el visor del sistema al generarlo

# Umbrales de modelo
X5_MIN_TRADES_TRAIN      = 500    # mínimo de OC para entrenar (menor → untrained)
X5_MIN_TRADES_FTT        = 5000   # a partir de aquí usa FT-Transformer en vez de LightGBM

# Reentrenamiento (modo LightGBM)
X5_RETRAIN_EVERY_N_VELAS = 48     # reentrenamiento completo cada N velas H1 (≈2 días)

# Dataset y ponderación temporal
X5_WINDOW_TRAIN          = None   # None = todo el store; int = últimas N filas
X5_LAMBDA_DECAY          = 0.001  # decay exponencial: peso = e^(-λ × días_antigüedad)
                                   # 0.001 ≈ peso 0.5 para trades de ~700 días atrás

# Optuna (modo LightGBM): optimizador bayesiano de hiperparámetros — concentra
# intentos en zonas prometedoras del espacio de parámetros.
X5_N_OPTUNA_TRIALS       = 200    # intentos por inferencia (~10-30 seg con 200)

# Gradient ascent (modo FTT): ajusta los parámetros de entrada para maximizar
# el retorno predicho, propagando el gradiente hacia la entrada (no los pesos).
X5_ASCENT_RESTARTS       = 10     # puntos de inicio aleatorios (para evitar óptimos locales)
X5_ASCENT_STEPS          = 300    # pasos por punto de inicio
X5_ASCENT_LR             = 0.01   # magnitud del paso

# Airbag: anula la recomendación del modelo si el precio cayó demasiado en las últimas 4 velas
X5_AIRBAG_THRESHOLD = {
    'BTCUSD': 0.08, 'ETHUSD': 0.08,
    'TSLA':   0.05, 'GOOGL':  0.05, 'NVDA': 0.05, 'AMZN': 0.05,
}
X5_N_MINIMO = {
    'BTCUSD': 30, 'ETHUSD': 30,
    'TSLA':   20, 'GOOGL':  20, 'NVDA': 20, 'AMZN': 20,
}

# Rangos de búsqueda — todos por activo
# K, N_EXP, LAMBDA, A, B comparten el mismo rango entre activos (ajustable)
X5_PARAM_RANGES = {
    'K': {v: (0.5, 2.0) for v in ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']},
    'N_EXP': {v: (0.5, 3.0) for v in ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']},
    'LAMBDA': {v: (1/1000, 1/50) for v in ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']},
    'A': {v: (2.0, 20.0) for v in ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']},
    'B': {v: (0.5, 5.0) for v in ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']},
    'n_sizes_ejecucion': {
        'BTCUSD': (50, 200), 'ETHUSD': (50, 200),
        'TSLA': (40, 180), 'GOOGL': (40, 180), 'NVDA': (40, 180), 'AMZN': (40, 180),
    },
    'LOTAJES_M': {v: (1, 5) for v in ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']},
    'PERDIDA_MAX': {v: (100, 300) for v in ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']},
}

# Festivos US (NYSE) — afectan patrones de volumen incluso en crypto
X5_US_HOLIDAYS = [
    '2022-01-17', '2022-02-21', '2022-04-15', '2022-05-30', '2022-06-20',
    '2022-07-04', '2022-09-05', '2022-11-24', '2022-12-26',
    '2023-01-02', '2023-01-16', '2023-02-20', '2023-04-07', '2023-05-29',
    '2023-06-19', '2023-07-04', '2023-09-04', '2023-11-23', '2023-12-25',
    '2024-01-01', '2024-01-15', '2024-02-19', '2024-03-29', '2024-05-27',
    '2024-06-19', '2024-07-04', '2024-09-02', '2024-11-28', '2024-12-25',
    '2025-01-01', '2025-01-20', '2025-02-17', '2025-04-18', '2025-05-26',
    '2025-06-19', '2025-07-04', '2025-09-01', '2025-11-27', '2025-12-25',
    '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25',
    '2026-06-19', '2026-07-03', '2026-09-07', '2026-11-26', '2026-12-25',
]

# ─── X4 — Backtester ─────────────────────────────────────────────────────────
X4_VERSION_ACTIVA = 'V1'
X4_VERSIONES = {
    'V1': {'fecha_inicio': '2026-01-10', 'fecha_fin': 'F'},
    'V0': {'fecha_inicio': '2026-01-10', 'fecha_fin': 'F'},
    'V2': {'fecha_inicio': '2026-01-10', 'fecha_fin': 'F'},
    'V3': {'fecha_inicio': '2026-01-10', 'fecha_fin': 'F'},
}
