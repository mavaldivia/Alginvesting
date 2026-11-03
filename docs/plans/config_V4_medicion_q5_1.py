# resources/x4/versionV4/config_V4.py
# Medición de duración de una vuelta (X5_Q5-1): BTCUSD con los parámetros estáticos de producción
# (config.py), desde el 2022-03-01 hasta la última vela. Se copia sobre el config_V4.py que crea
# X4B_crear_version_backtesting.py. Sin imports de config.py — garantiza reproducibilidad.
#
# Diferencias con la plantilla de X4B:
#   - valores/n_sizes: solo BTCUSD, N = 180 (n_sizes_ejecucion de config.py)
#   - fecha_inicio: 2022-03-01 (60 días de calentamiento; los soportes usan datos desde FECHA_INICIAL)
#   - capital_inicial: 1_000_000 solo para medir; con 3000 USD el stop-out probablemente corta la corrida
#   - PERDIDA_MAX_BT, A, B, delta_recalculo_soportes: valores de producción (7 días = 168 velas)

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent.parent  # raíz del proyecto

# ─── Versión y activos ───────────────────────────────────────────────────────
version = 'V4'
valores = ['BTCUSD']
n_sizes = {'BTCUSD': 180}

# ─── Fechas ──────────────────────────────────────────────────────────────────
fecha_inicio = '2022-03-01'
fecha_fin    = 'F'   # 'F' = hasta la última vela disponible; no cierra posiciones al terminar

# ─── Capital y riesgo ────────────────────────────────────────────────────────
capital_inicial     = 1_000_000.0   # USD — solo para medir duración
PERDIDA_MAX_BT      = 200.0         # USD
MARGEN_LIBRE_MIN_BT = 50.0          # USD — buffer mínimo de margen libre para abrir/ejecutar OE
STOP_OUT_LEVEL      = 50            # % — margin level mínimo antes de declarar stop-out y detener la simulación

# ─── Recálculo de soportes ───────────────────────────────────────────────────
delta_recalculo_soportes = 7    # días (7 días = 168 velas H1 en crypto)

# ─── Algoritmo de soportes (parámetros de X0 fijados para esta versión) ─────
K     = 1
N_EXP = 1.3
parametros_soportes = {
    'y': True, 'w': True, 'h_dist': True, 'v': True, 'f': True,
}
LAMBDA            = 1 / 5
M                 = 30
M_COARSE          = 5
BLOQUE_DISTANCIAS = 2000
MAX_ITERS         = 10000

# ─── Trading ─────────────────────────────────────────────────────────────────
A = 3     # ganancia mínima en USD para activar el primer SL ganador
B = 1.5   # distancia en USD (normalizada por L) que mantiene el SL bajo el precio actual
LOTAJES        = {'BTCUSD': 0.01}
UNITS          = {'BTCUSD': 1}
APALANCAMIENTO = {'BTCUSD': 400}

# ─── Rutas ───────────────────────────────────────────────────────────────────
_VERSION_DIR        = Path(__file__).parent
CARPETA_RESOURCES   = _VERSION_DIR / f'resources_{version}'
CARPETA_N_BT        = CARPETA_RESOURCES / 'conjuntos_N'
CARPETA_LOGS_BT     = CARPETA_RESOURCES / 'logs'
CARPETA_DATA        = BASE_DIR / 'Data'
CARPETA_DATA_MINUTO = BASE_DIR / 'Data_minuto'
