"""
config_smart.py

Pisos y techos de los parámetros dinámicos (X5_Q4 y backtesting inteligente), separados en
cryptos y acciones. Es el único lugar donde se mueven: ni X5_Q4.ipynb ni el backtesting
inteligente los repiten.

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
}

RANGOS_ACCION = {
    'N': (40, 180),
    'A': (2.0, 20.0),
    'factor_B': (0.2, 0.7),
    'K': (0.5, 2.0),
    'N_EXP': (0.5, 3.0),
    'LAMBDA': (0.05, 0.5),
    'PERDIDA_MAX': (100, 300),
}


def tipo_valor(valor: str) -> str:
    return 'crypto' if valor in CRYPTOS else 'accion'


def rango(parametro: str, valor: str) -> tuple:
    """(piso, techo) del parámetro dinámico para ese activo, según su tipo (crypto o acción)."""
    rangos = RANGOS_CRYPTO if valor in CRYPTOS else RANGOS_ACCION
    return rangos[parametro]
