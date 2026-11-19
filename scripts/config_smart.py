"""
config_smart.py

Pisos, techos y pasos de los parámetros dinámicos (X5_Q4 y backtesting inteligente), separados en
cryptos y acciones, más `N_VELAS` (cadencia de recálculo de soportes) y `GRADO` (etapa de aprendizaje).
Es el único lugar donde se mueven: ni X5_Q4.ipynb ni el backtesting inteligente los repiten.

Para cambiarlos en caliente basta editar este archivo y guardar; el consumidor los relee con
`importlib.reload(config_smart)` al inicio de cada corrida (X5_Q4) o de cada vuelta (backtesting).
Los valores productivos de config.py (cfg.A, cfg.K, ...) no se tocan.
"""

CRYPTOS = ['BTCUSD', 'ETHUSD']

RANGOS_CRYPTO = {
    'N': (50, 200),
    'A': (2.0, 20.0),
    'factor_B': (0.2, 0.7),
    'K': (0.5, 2.0),
    'N_EXP': (0.5, 3.0),
    'LAMBDA': (0.05, 0.5),
    'PERDIDA_MAX': (100, 300),
    'PERDIDA_MAX_PCT': (0.03, 0.06),
}

RANGOS_ACCION = {
    'N': (40, 180),
    'A': (2.0, 20.0),
    'factor_B': (0.2, 0.7),
    'K': (0.5, 2.0),
    'N_EXP': (0.5, 3.0),
    'LAMBDA': (0.05, 0.5),
    'PERDIDA_MAX': (100, 300),
    'PERDIDA_MAX_PCT': (0.03, 0.06),
}

# `PERDIDA_MAX` (USD) es el de X5_Q4, que queda reproducible. `PERDIDA_MAX_PCT` es el del backtesting
# inteligente: fracción de la cuenta inicial por tramo de lotajes_m: p * 3000 * m (0.04 con m=1 -> 120 USD por orden).

# Paso permitido de cada parámetro C1: el valor calculado se lleva al más cercano de la grilla
# piso + k * paso. Ej. N crypto (50, 200, paso 10): 52.33 -> 50.
PASOS_CRYPTO = {
    'N': 10,
    'A': 0.5,
    'factor_B': 0.05,
    'K': 0.1,
    'N_EXP': 0.1,
    'LAMBDA': 0.05,
    'PERDIDA_MAX_PCT': 0.005,
}

PASOS_ACCION = {
    'N': 10,
    'A': 0.5,
    'factor_B': 0.05,
    'K': 0.1,
    'N_EXP': 0.1,
    'LAMBDA': 0.05,
    'PERDIDA_MAX_PCT': 0.005,
}

# Cada cuántas velas H1 se actualizan N, K, N_EXP y LAMBDA y se busca un conjunto nuevo de soportes.
# crypto = X5_RECALC_SOPORTES_CADA (config.py); accion asume ~7 velas H1 por día * 5 días ~ 1 semana (sin verificar).
N_VELAS = {'crypto': 168, 'accion': 35}

# Grado del modelo de la etapa de aprendizaje (Z_tongo = f(C2)): 1 lineal, 2 suma productos cruzados.
GRADO = 1

# ─── Backtesting inteligente (Q5-3, plan_x5_alt_v2.md 9.3 y 9.6) ──────────────────────────────────────────
# Toda vuelta parte siempre en esta fecha (60 días de calentamiento); los soportes usan datos desde FECHA_INICIAL.
FECHA_INICIO_BT = '2022-03-01'

# Cuenta por valor: lotajes_m = max(1, (Z - z_base_lote) // paso_lote + 2) con Z = cerrado + P&L abierto.
CUENTA = {'capital_inicial': 3000.0, 'z_base_lote': 6000.0, 'paso_lote': 3000.0,
          'margen_libre_min': 50.0, 'stop_out_level': 50}  # las dos últimas: mismos valores que la plantilla de X4B

# Tope de Órdenes Abiertas (OA): cupo = floor(R_TOPE_OA * Z / umbral), con umbral = p * capital_inicial * lotajes_m(Z).
# R_TOPE_OA es el peor caso: si todas las OA permitidas llegaran a su umbral a la vez, la pérdida sería a lo más
# R_TOPE_OA * Z. Con el umbral fijo de 132 USD (p = 0.044, m = 1) y 0.5, bajo Z = 264 el cupo es 0 y no se opera.
R_TOPE_OA = 0.5

# Fracción final de las velas que no entra al aprendizaje (tramo reservado); el corte es por número de velas.
FRACCION_RESERVADA = 0.20

# Curvas de equity que se conservan completas por valor: las de la vuelta estática y las de las vueltas con mejor
# premio de aprendizaje (nunca el reservado, que no decide nada); del resto se borran los CSV de equity, no los trades.
CURVAS_MEJORES = 3

# Fracción p de la vuelta estática de control: el PERDIDA_MAX estático de 200 USD sobre los 3000 USD iniciales
# (200 / 3000 = 0.0667), fuera del rango dinámico (0.03, 0.06). Misma semántica p * 3000 * m que la vuelta dinámica.
P_ESTATICO = 0.067


# Rango del sorteo Sobol de los C2 de cada C1, relativo a la calibración de Q4 (decidido 2026-11-10: cerca de Q4).
# punto_medio: Q4 ± punto_medio_delta (unidades del índice, que es un z-score); pendiente: de Q4/pendiente_factor
# a Q4*pendiente_factor; span: rango absoluto en velas H1 (entero); peso w_i (sin normalizar): Q4 ± peso_delta,
# con piso peso_min.
SORTEO_C2 = {
    'punto_medio_delta': 0.5,
    'pendiente_factor': 2.0,
    'span': (6, 24),
    'peso_delta': 0.2,
    'peso_min': 0.05,
}


def tipo_valor(valor: str) -> str:
    return 'crypto' if valor in CRYPTOS else 'accion'


def rango(parametro: str, valor: str) -> tuple:
    """(piso, techo) del parámetro dinámico para ese activo, según su tipo (crypto o acción)."""
    rangos = RANGOS_CRYPTO if valor in CRYPTOS else RANGOS_ACCION
    return rangos[parametro]


def paso(parametro: str, valor: str) -> float:
    """Paso de la grilla del parámetro dinámico para ese activo, según su tipo (crypto o acción)."""
    pasos = PASOS_CRYPTO if valor in CRYPTOS else PASOS_ACCION
    return pasos[parametro]
