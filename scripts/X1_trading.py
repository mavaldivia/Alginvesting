"""
X1_trading.py

Loop de trading semi-automático. Lee los N soportes generados por X0 y gestiona
órdenes en MetaTrader5 en tiempo real.

Por cada ciclo y activo:
  A) Elimina órdenes pendientes que ya no corresponden a soportes válidos
  B) Crea nuevas órdenes de compra pendientes (buy limit) en los soportes bajo el precio actual
  C) Gestiona el trailing stop en posiciones abiertas
  D) Cierra posiciones cuya pérdida supere perdida_max

Uso:
    python X1_trading.py
"""

import json
import os
import sys
import time
import warnings

import pandas as pd

import MetaTrader5 as mt5

warnings.filterwarnings('ignore')

from config import (
    CARPETA_N_PROD,
    VALORES, A, B, TS, PERDIDA_MAX, PRUEBA_TRAILING_STOP,
    LOTAJES, UNITS,
    n_sizes_ejecucion as n_sizes,
)


# ─── Utilidades ───────────────────────────────────────────────────────────────

def json_act(file_path: str, variable=None, mode: str = 'open'):
    """Guarda (mode='save') o carga (mode='open') una lista de soportes en disco como JSON."""
    path = f'{file_path}.json'
    try:
        with open(path, 'w' if mode == 'save' else 'r') as f:
            if mode == 'save':
                json.dump(sorted(variable), f)
                return None
            return json.load(f)
    except Exception as e:
        print(f'Error json_act ({mode}, {path}): {e}')
        raise


def leer_lista_N(valor: str, N: int) -> list:
    """
    Lee el conjunto de N soportes desde el JSON generado por X0.
    Reintenta hasta 10 veces con pausa de 2s, por si X0 está escribiendo simultáneamente.
    """
    json_path = CARPETA_N_PROD / f'{valor}_{N}.json'
    for _ in range(10):
        if json_path.exists():
            lista_N = json_act(str(CARPETA_N_PROD / f'{valor}_{N}'))
            return [round(n, 2) for n in lista_N]
        time.sleep(2)
    raise FileNotFoundError(f'No se encontró {json_path} después de 10 intentos')


# ─── Funciones MT5 ────────────────────────────────────────────────────────────

def obtener_precio_actual(valor: str, modo: str = 'B') -> float:
    """modo='B' → bid (precio de venta del mercado, precio de compra para nosotros)."""
    tick = mt5.symbol_info_tick(valor)
    if tick is None:
        raise RuntimeError(f'symbol_info_tick({valor}) retornó None: {mt5.last_error()}')
    return tick.bid if modo == 'B' else tick.ask


def obtener_conjuntos_actuales(valor: str, dic_seguimiento: dict) -> tuple:
    """
    Devuelve las posiciones abiertas (OA) y órdenes pendientes (OE) actuales en MT5.
    Limpia dic_seguimiento de posiciones que ya fueron cerradas externamente.
    """
    actual_OA = mt5.positions_get(symbol=valor) or []
    actual_OE = mt5.orders_get(symbol=valor) or []

    lista_OA = [p.price_open for p in actual_OA]
    lista_OE = [o.price_open for o in actual_OE]

    if valor in dic_seguimiento:
        for orden in list(dic_seguimiento[valor]):
            if orden not in actual_OA:
                print(f'Posición cerrada externamente, eliminando de seguimiento: {orden}')
                dic_seguimiento[valor].remove(orden)

    return lista_OA, lista_OE, actual_OA, actual_OE, dic_seguimiento


def limpiar_ordenes_pendientes_no_validas(valor: str, actual_OE: list, lista_N: list):
    """Cancela órdenes pendientes cuyo precio ya no está en la lista de soportes válidos."""
    for orden in actual_OE:
        precio_OE = round(orden.price_open, 2)
        if precio_OE not in lista_N:
            request = {
                'action': mt5.TRADE_ACTION_REMOVE,
                'order': orden.ticket,
                'symbol': valor,
                'type': orden.type,
                'position': orden.position_id,
                'comment': 'Eliminacion de orden',
            }
            result = mt5.order_send(request)
            if result is None:
                print(f'  order_send failed: {mt5.last_error()}')
            elif result.retcode != mt5.TRADE_RETCODE_DONE:
                if result.retcode not in [10018]:  # 10018: mercado cerrado
                    print(f'  Error al eliminar orden {orden.ticket}: retcode={result.retcode}')
            else:
                print(f'  Orden eliminada: {valor} @ {precio_OE}')


def generate_request_buy_limit(valor: str, order_type, volumen: float, precio: float, sl: float = 0) -> dict:
    request = {
        'action': mt5.TRADE_ACTION_PENDING,
        'symbol': valor,
        'volume': volumen,
        'type': order_type,
        'price': precio,
        'deviation': 10,
        'magic': 123456,
        'comment': 'Orden BUY desde Python',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK,
    }
    if sl != 0:
        request['sl'] = float(sl)
    return request


def ejecutar_orden(request: dict, symbol: str, volumen: float, precio: float):
    if 'sl' in request:
        request['sl'] = float(round(request['sl'], 0))

    if volumen == 0:
        print('  Orden no ejecutada: volumen = 0')
        return

    result = mt5.order_send(request)
    try:
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            result_dict = result._asdict()
            if result_dict.get('comment') == 'Market closed':
                return
            if result.retcode in [10006, 10044, 10018, 10031]:
                return
            print(f'  Error al ejecutar orden: retcode={result.retcode}, comment={result_dict.get("comment")}')
        else:
            print(f'  Orden ejecutada: {symbol} {volumen} lotes @ {precio}')
    except Exception as e:
        print(f'  Excepción en ejecutar_orden: {e}')


def crear_ordenes_espera(lista_OA: list, lista_OE: list, lista_N: list,
                          valor: str, L: float, a: float, lotajes: dict):
    """
    Para cada soporte en lista_N que no tenga ya una orden activa o pendiente,
    crea una orden buy limit si el precio actual está al menos a distancia `a` USD por encima.
    """
    P0 = obtener_precio_actual(valor, modo='B')
    lista_OAE = lista_OA + lista_OE

    for Pi in lista_N:
        if Pi in lista_OAE:
            continue
        if (P0 - Pi) * L >= a:
            request = generate_request_buy_limit(
                valor,
                order_type=mt5.ORDER_TYPE_BUY_LIMIT,
                volumen=lotajes[valor],
                precio=Pi,
            )
            ejecutar_orden(request, symbol=valor, volumen=lotajes[valor], precio=Pi)


def cambiar_SL(orden, valor: str, sl: float):
    request = {
        'action': mt5.TRADE_ACTION_SLTP,
        'symbol': valor,
        'position': orden.ticket,
        'sl': float(round(sl, 2)),
        'deviation': 10,
        'comment': 'SL0',
    }
    result = mt5.order_send(request)
    if result is None:
        print(f'  cambiar_SL failed: {mt5.last_error()}')
    elif result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f'  Error modificando SL orden {orden.ticket}: retcode={result.retcode}')
    else:
        print(f'  SL actualizado: orden {orden.ticket} → {sl:.2f}')


def trailing_stop(actual_OA: list, valor: str, L: float, a: float, b: float,
                   lotajes: dict, dic_seguimiento: dict):
    """
    Para cada posición abierta:
    - Si no tiene SL y la ganancia >= a USD → pone el primer SL ganador y repone la orden
    - Si ya tiene SL y el nuevo SL calculado sube → mueve el SL al alza (trailing)

    b: distancia en USD que debe mantener el SL bajo el precio actual (normalizada por L).
    """
    if not actual_OA:
        return

    P0 = obtener_precio_actual(valor, modo='B')

    for orden in actual_OA:
        sl = orden.sl
        Pi = orden.price_open
        cambios = False

        if sl == 0:
            if (P0 - Pi) * L >= a:
                sl_nuevo = P0 - b / L
                cambiar_SL(orden, valor, sl_nuevo)
                # Repone la orden de compra en el mismo soporte para mantener el nivel activo
                request = generate_request_buy_limit(
                    valor,
                    order_type=mt5.ORDER_TYPE_BUY_LIMIT,
                    volumen=lotajes[valor],
                    precio=Pi,
                )
                ejecutar_orden(request, symbol=valor, volumen=lotajes[valor], precio=Pi)
                cambios = True
        else:
            sl_nuevo = P0 - b / L
            if sl_nuevo > sl:
                print(f'  Trailing stop: {valor} P0={P0:.2f} SL {sl:.2f} → {sl_nuevo:.2f}')
                cambiar_SL(orden, valor, sl_nuevo)
                cambios = True

        if cambios:
            if valor not in dic_seguimiento:
                dic_seguimiento[valor] = []
            if orden not in dic_seguimiento[valor]:
                dic_seguimiento[valor].append(orden)


def cerrar_posicion(orden, valor: str, lotajes: dict):
    """Cierra una posición abierta a precio de mercado (bid)."""
    precio = obtener_precio_actual(valor, modo='B')
    request = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': valor,
        'volume': lotajes[valor],
        'type': mt5.ORDER_TYPE_SELL,
        'position': orden.ticket,
        'price': precio,
        'deviation': 10,
        'magic': 123456,
        'comment': 'Cierre por perdida_max',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f'  Error al cerrar posición {orden.ticket}: {mt5.last_error()}')
    else:
        print(f'  Posición cerrada por perdida_max: {valor} ticket={orden.ticket} @ {precio:.2f}')


def controlar_perdida_max(actual_OA: list, valor: str, L: float,
                           lotajes: dict, perdida_max: float):
    """Cierra cualquier posición abierta cuya pérdida actual supere perdida_max USD."""
    P0 = obtener_precio_actual(valor, modo='B')
    for orden in actual_OA:
        Pi = orden.price_open
        perdida = (Pi - P0) * L
        if perdida > perdida_max:
            print(f'  PERDIDA_MAX alcanzada: {valor} Pi={Pi:.2f} P0={P0:.2f} pérdida={perdida:.2f} USD')
            cerrar_posicion(orden, valor, lotajes)


def informacion(valores: list, lotajes: dict, units: dict, n_sizes: dict, a: float):
    """Muestra el estado actual de soportes y distancias para todos los activos."""
    print('\n─── Información ───────────────────────────────────────────')
    for valor in valores:
        P0 = obtener_precio_actual(valor, modo='B')
        N = n_sizes[valor]
        lista_N = leer_lista_N(valor, N)
        L = lotajes[valor] * units[valor]

        df = pd.DataFrame(lista_N, columns=['Precio'])
        df['Distancia_USD'] = (P0 - df['Precio']) * L
        df = df[df['Distancia_USD'] >= 0].sort_values('Distancia_USD').reset_index(drop=True)

        por_declarar = df[df['Distancia_USD'] < a].copy()
        declarados = df[df['Distancia_USD'] >= a].copy()

        print(f'\n{valor} | P0={P0:.2f} | N={N}')
        if len(por_declarar):
            print('  Por declarar (muy cerca):')
            print(por_declarar.head(5).to_string(index=False))
        if len(declarados):
            print('  Declarados (activos):')
            print(declarados.head(5).to_string(index=False))


# ─── Loop principal ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not mt5.initialize():
        sys.exit(f'MT5 initialize() falló: {mt5.last_error()}')

    # Validar que todos los activos existen en el broker
    for valor in VALORES:
        info = mt5.symbol_info(valor)
        if info is None:
            print(f'Símbolo no encontrado en broker: {valor}')
        else:
            if not info.visible:
                mt5.symbol_select(valor, True)
            print(f'OK: {info.name} (visible={info.visible})')

    def _fmt_duracion(s):
        s = int(s)
        if s < 60:
            return f'{s}s'
        h, rem = divmod(s, 3600)
        m, seg = divmod(rem, 60)
        return f'{h:02d}:{m:02d}:{seg:02d}'

    print('\nInicio del loop de trading')
    t0 = time.time()
    dic_seguimiento = {}
    i = 0

    try:
        while True:
            time_sleep = True

            for valor in VALORES:
                try:
                    L = LOTAJES[valor] * UNITS[valor]

                    if not PRUEBA_TRAILING_STOP:
                        N = n_sizes[valor]
                        lista_N = leer_lista_N(valor, N)

                    lista_OA, lista_OE, actual_OA, actual_OE, dic_seguimiento = obtener_conjuntos_actuales(valor, dic_seguimiento)

                    # A: Limpiar órdenes pendientes que ya no corresponden a soportes vigentes
                    if not PRUEBA_TRAILING_STOP and (i % int(5 / TS) == 0):
                        limpiar_ordenes_pendientes_no_validas(valor, actual_OE, lista_N)

                    # B: Crear órdenes de compra pendientes en soportes válidos
                    if not PRUEBA_TRAILING_STOP:
                        crear_ordenes_espera(lista_OA, lista_OE, lista_N, valor, L, A, LOTAJES)

                    # C: Trailing stop en posiciones abiertas
                    trailing_stop(actual_OA, valor, L, A, B, LOTAJES, dic_seguimiento)

                    # D: Cierre por pérdida máxima
                    controlar_perdida_max(actual_OA, valor, L, LOTAJES, PERDIDA_MAX)

                except Exception as e:
                    print(f'  [X1] Error en {valor}: {e} — saltando activo este ciclo')

            # Si alguna posición tiene trailing stop activo → no dormir (reaccionar rápido)
            for c in dic_seguimiento:
                if dic_seguimiento[c]:
                    time_sleep = False

            if i % int(5000 / TS) == 0:
                print(f'\nIteración {i} | Tiempo: {round((time.time() - t0) / 60, 1)} min')
                try:
                    informacion(VALORES, LOTAJES, UNITS, n_sizes, A)
                except Exception as e:
                    print(f'  [X1] Error en informacion: {e}')

            i += 1
            if time_sleep:
                time.sleep(TS)
    except KeyboardInterrupt:
        pass
    finally:
        print(f'\nTiempo total: {_fmt_duracion(time.time() - t0)}')
