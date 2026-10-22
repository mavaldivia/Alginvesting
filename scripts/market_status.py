"""
market_status.py

Estado de mercado de cada activo en config.VALORES, leído desde MT5 (no por horario fijo):
  abierto    -> la hora del servidor cae dentro de una sesión de trading del símbolo
  premarket  -> hay cotización pero aún no abre la primera sesión de trading del día
  postmarket -> hay cotización pero ya cerró la última sesión de trading del día
  cerrado    -> fuera de toda sesión, o símbolo deshabilitado (trade_mode)

La hora del servidor se toma del último tick de un activo crypto (opera 24/7); las
sesiones salen de symbol_info_session_trade / symbol_info_session_quote. Requiere
Windows con MT5 abierto.
"""

from datetime import datetime

import MetaTrader5 as mt5

from config import VALORES

CRYPTO = ('BTCUSD', 'ETHUSD')
MAX_SESIONES = 10


def _segundos_dia(dt):
    # 24:00 llega como 1970-01-02 00:00 -> 86400 s
    return int((dt - datetime(1970, 1, 1)).total_seconds())


def _hora_servidor():
    for v in CRYPTO:
        tick = mt5.symbol_info_tick(v)
        if tick is not None:
            return datetime.utcfromtimestamp(tick.time)
    raise RuntimeError("Sin tick de crypto para inferir la hora del servidor")


def _sesiones(fn, valor, dia_mt5):
    sesiones = []
    for i in range(MAX_SESIONES):
        s = fn(valor, dia_mt5, i)
        if not s:
            break
        sesiones.append((_segundos_dia(s[0]), _segundos_dia(s[1])))
    return sesiones


def estado_mercado(valor, ahora_srv):
    info = mt5.symbol_info(valor)
    if info is None:
        return 'sin símbolo'
    if info.trade_mode in (mt5.SYMBOL_TRADE_MODE_DISABLED, mt5.SYMBOL_TRADE_MODE_CLOSEONLY):
        return 'cerrado'

    dia = (ahora_srv.weekday() + 1) % 7  # MT5: 0 = domingo
    t = ahora_srv.hour * 3600 + ahora_srv.minute * 60 + ahora_srv.second
    trade = _sesiones(mt5.symbol_info_session_trade, valor, dia)
    quote = _sesiones(mt5.symbol_info_session_quote, valor, dia)

    if any(a <= t < b for a, b in trade):
        return 'abierto'
    if trade and any(a <= t < b for a, b in quote):
        return 'premarket' if t < trade[0][0] else 'postmarket'
    return 'cerrado'


if __name__ == '__main__':
    if not mt5.initialize():
        raise SystemExit(f"No se pudo inicializar MT5: {mt5.last_error()}")
    try:
        for v in VALORES:
            mt5.symbol_select(v, True)
        ahora_srv = _hora_servidor()
        print(f"Hora servidor MT5: {ahora_srv:%Y-%m-%d %H:%M %a}")
        for v in VALORES:
            print(f"{v:<8} {estado_mercado(v, ahora_srv)}")
    finally:
        mt5.shutdown()
