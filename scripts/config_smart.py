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
# inteligente: fracción de Z = cerrado + P&L abierto del valor (0.04 con Z=5000 -> 200 USD por orden).

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


def tipo_valor(valor: str) -> str:
    return 'crypto' if valor in CRYPTOS else 'accion'


def rango(parametro: str, valor: str) -> tuple:
    """(piso, techo) del parámetro dinámico para ese activo, según su tipo (crypto o acción)."""
    rangos = RANGOS_CRYPTO if valor in CRYPTOS else RANGOS_ACCION
    return rangos[parametro]
