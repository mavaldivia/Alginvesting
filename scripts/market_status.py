"""
market_status.py

Estado de mercado de cada activo en config.VALORES, leído desde MT5 (no por horario fijo):
  abierto -> el símbolo permite operar y su último tick es reciente
  cerrado -> trade_mode deshabilitado, o último tick atrasado respecto de la hora del servidor

Reutiliza mercado_abierto de X1 (misma lógica que decide si X1 repone/reemplaza órdenes).
La API Python de MT5 no expone las sesiones de trading/cotización (symbol_info_session_*
es solo MQL5), por eso no distingue premarket/postmarket. Requiere Windows con MT5 abierto.
"""

from datetime import datetime

import MetaTrader5 as mt5

from config import VALORES
from X1_trading import _servidor_ahora, mercado_abierto


def estado_mercado(valor):
    if mt5.symbol_info(valor) is None:
        return 'sin símbolo'
    return 'abierto' if mercado_abierto(valor) else 'cerrado'


if __name__ == '__main__':
    if not mt5.initialize():
        raise SystemExit(f"No se pudo inicializar MT5: {mt5.last_error()}")
    try:
        for v in VALORES:
            mt5.symbol_select(v, True)
        ahora_srv = datetime.utcfromtimestamp(_servidor_ahora())
        print(f"Hora servidor MT5: {ahora_srv:%Y-%m-%d %H:%M %a}")
        for v in VALORES:
            print(f"{v:<8} {estado_mercado(v)}")
    finally:
        mt5.shutdown()
