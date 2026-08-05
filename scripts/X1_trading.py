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
    VALORES, A, B, TS, PERDIDA_MAX,
    LOTAJES, UNITS,
    n_sizes_ejecucion as n_sizes,
)


# ─── Utilidades ───────────────────────────────────────────────────────────────

def json_act(file_path: str, variable=None, mode: str = 'open'):
    """Guarda (mode='save') o carga (mode='open') una lista de soportes en disco como JSON.

    El guardado es atómico (escribe a un .tmp y hace os.replace) para que un lector
    concurrente nunca vea el archivo truncado a mitad de escritura.
    """
    path = f'{file_path}.json'
    try:
        if mode == 'save':
            tmp_path = f'{path}.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(sorted(variable), f)
            os.replace(tmp_path, path)
            return None
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f'Error json_act ({mode}, {path}): {e}')
        raise


def leer_lista_N(valor: str, N: int) -> list:
    """
    Lee el conjunto de N soportes desde el JSON generado por X0.
    Reintenta hasta 10 veces con pausa de 2s, por si X0 está escribiendo simultáneamente
    (archivo aún no existe, o existe pero X0 lo está reescribiendo — OneDrive puede
    extender la ventana de lock/sync más allá de la propia escritura del proceso).
    """
    json_path = CARPETA_N_PROD / f'{valor}_{N}.json'
    for _ in range(10):
        if json_path.exists():
            try:
                lista_N = json_act(str(CARPETA_N_PROD / f'{valor}_{N}'))
                return [round(n, 2) for n in lista_N]
            except (json.JSONDecodeError, PermissionError, OSError):
                pass
        time.sleep(2)
    raise FileNotFoundError(f'No se encontró (o no se pudo leer) {json_path} después de 10 intentos')


# ─── Funciones MT5 ────────────────────────────────────────────────────────────

def obtener_precio_actual(valor: str, modo: str = 'B') -> float:
    """modo='B' → bid (precio de venta del mercado, precio de compra para nosotros)."""
    tick = mt5.symbol_info_tick(valor)
    if tick is None:
        raise RuntimeError(f'symbol_info_tick({valor}) retornó None: {mt5.last_error()}')
    return tick.bid if modo == 'B' else tick.ask


def _servidor_ahora() -> int:
    """Aproxima la hora del servidor MT5 como el tick más reciente entre todos los
    símbolos. Los 24/7 (crypto) siempre están frescos, así que su timestamp sirve
    de reloj para medir cuán atrasado está el último tick de un símbolo cerrado."""
    ultimo = 0
    for v in VALORES:
        t = mt5.symbol_info_tick(v)
        if t is not None and t.time > ultimo:
            ultimo = t.time
    return ultimo


def mercado_abierto(valor: str, max_staleness_s: int = 300) -> bool:
    """True si el símbolo permite operar Y su sesión está abierta ahora.

    `trade_mode` es solo el permiso de trading del símbolo — los brokers lo dejan
    en FULL fuera del horario de la bolsa, así que no distingue sesión abierta de
    cerrada. Se compara además la frescura del último tick contra la hora del
    servidor (`_servidor_ahora`): si el último tick del símbolo está más de
    `max_staleness_s` atrasado, la sesión está cerrada aunque `trade_mode` sea FULL.
    Si todos los ticks estuvieran atrasados (broker caído), degrada a permitir."""
    info = mt5.symbol_info(valor)
    if info is None or info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
        return False
    tick = mt5.symbol_info_tick(valor)
    if tick is None or tick.time == 0:
        return False
    return (_servidor_ahora() - tick.time) <= max_staleness_s


def _precio_cierre_historico(ticket: int) -> float | None:
    """Precio de cierre real de una posición ya cerrada, vía el historial de
    deals de MT5 (el deal de salida, DEAL_ENTRY_OUT)."""
    deals = mt5.history_deals_get(position=ticket)
    if not deals:
        return None
    salidas = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    if not salidas:
        return None
    return salidas[-1].price


def _informar_cierre(valor: str, ticket: int, info: dict) -> None:
    """Imprime lotaje, precio de apertura y precio de cierre al detectar que una
    posición pasó de Activa (A) a Cerrada (C) — por perdida_max, trailing stop
    (SL ejecutado por el broker) o cierre externo. Única fuente para esta
    transición: cubre las tres causas sin duplicar el print entre ellas."""
    precio_cierre = _precio_cierre_historico(ticket)
    pc_str = f'{precio_cierre:.2f}' if precio_cierre is not None else 'desconocido'
    print(f'  [A→C] {valor}  ticket={ticket}  lotaje={info["lote"]}  '
          f'precio_apertura={info["precio_apertura"]:.2f}  precio_cierre={pc_str}')


def obtener_conjuntos_actuales(valor: str, dic_seguimiento: dict, pos_info: dict) -> tuple:
    """
    Devuelve las posiciones abiertas (OA) y órdenes pendientes (OE) actuales en MT5.
    Limpia dic_seguimiento de posiciones que ya fueron cerradas externamente.
    `pos_info` (ticket → lote/precio_apertura) se actualiza con las OA vivas y,
    al detectar que un ticket ya no está abierto, informa la transición A→C.
    """
    actual_OA = mt5.positions_get(symbol=valor) or []
    actual_OE = mt5.orders_get(symbol=valor) or []

    lista_OA = [p.price_open for p in actual_OA]
    lista_OE = [o.price_open for o in actual_OE]

    actual_tickets = {p.ticket for p in actual_OA}
    for p in actual_OA:
        pos_info.setdefault(p.ticket, {'valor': valor, 'lote': p.volume, 'precio_apertura': p.price_open})

    tickets_previos = [t for t, info in pos_info.items() if info['valor'] == valor]
    for ticket in tickets_previos:
        if ticket not in actual_tickets:
            _informar_cierre(valor, ticket, pos_info.pop(ticket))

    if valor in dic_seguimiento:
        for ticket in list(dic_seguimiento[valor]):
            if ticket not in actual_tickets:
                print(f'Posición cerrada externamente, eliminando de seguimiento: valor={valor}, ticket={ticket}')
                dic_seguimiento[valor].remove(ticket)

    return lista_OA, lista_OE, actual_OA, actual_OE, dic_seguimiento


def limpiar_ordenes_pendientes_no_validas(valor: str, actual_OE: list, lista_N: list):
    """Cancela órdenes pendientes cuyo precio ya no está en la lista de soportes válidos.

    Retorna el precio más alto entre las OE canceladas (la más cercana al precio
    actual), o None si no se canceló ninguna. Lo usa crear_ordenes_espera para
    recuperar la cobertura cercana al precio que deja el buy limit saliente.
    """
    eliminadas = []
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
                eliminadas.append(precio_OE)
    if eliminadas:
        print(f'  {valor}: {len(eliminadas)} órdenes eliminadas desde {min(eliminadas)} hasta {max(eliminadas)}')
        return max(eliminadas)
    return None


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


def ejecutar_orden(request: dict, symbol: str, volumen: float, precio: float) -> bool:
    if 'sl' in request:
        request['sl'] = float(round(request['sl'], 0))

    if volumen == 0:
        print('  Orden no ejecutada: volumen = 0')
        return False

    result = mt5.order_send(request)
    try:
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            result_dict = result._asdict()
            if result_dict.get('comment') == 'Market closed':
                return False
            if result.retcode in [10006, 10044, 10018, 10031]:
                return False
            print(f'  Error al ejecutar orden: retcode={result.retcode}, comment={result_dict.get("comment")}')
            return False
        else:
            return True
    except Exception as e:
        print(f'  Excepción en ejecutar_orden: {e}')
        return False


def crear_ordenes_espera(lista_OA: list, lista_OE: list, lista_N: list,
                          valor: str, L: float, a: float, lotajes: dict,
                          precio_max_saliente: float = None):
    """
    Para cada soporte en lista_N que no tenga ya una orden activa o pendiente,
    crea una orden buy limit si el precio actual está al menos a distancia `a` USD por encima.

    Regla de reemplazo: cuando este ciclo se canceló al menos un buy limit
    (precio_max_saliente = el más cercano al precio), un soporte también entra si
    queda por debajo del promedio entre el precio actual y ese buy limit saliente.
    Recupera la cobertura cercana al precio que si no se perdería, porque el filtro
    de distancia `a` deja el primer soporte de reemplazo al menos `a` bajo el precio.
    """
    P0 = obtener_precio_actual(valor, modo='B')
    lista_OAE = lista_OA + lista_OE
    umbral_reemplazo = None
    if precio_max_saliente is not None and precio_max_saliente < P0:
        umbral_reemplazo = (P0 + precio_max_saliente) / 2
    ejecutadas = []

    for Pi in sorted(lista_N, reverse=True):
        if Pi in lista_OAE:
            continue
        distancia_ok = (P0 - Pi) * L >= a
        reemplazo_ok = umbral_reemplazo is not None and Pi < umbral_reemplazo
        if distancia_ok or reemplazo_ok:
            request = generate_request_buy_limit(
                valor,
                order_type=mt5.ORDER_TYPE_BUY_LIMIT,
                volumen=lotajes[valor],
                precio=Pi,
            )
            if ejecutar_orden(request, symbol=valor, volumen=lotajes[valor], precio=Pi):
                ejecutadas.append(Pi)

    if ejecutadas:
        print(f'  {valor}: {len(ejecutadas)} órdenes ejecutadas desde {min(ejecutadas)} hasta {max(ejecutadas)}')


def cambiar_SL(orden, valor: str, sl: float) -> bool:
    """Modifica el SL. Retorna True solo si MT5 confirma el cambio Y la posición sigue abierta."""
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
        return False
    elif result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f'  Error modificando SL orden {orden.ticket}: retcode={result.retcode}')
        return False
    posiciones = mt5.positions_get(ticket=orden.ticket)
    if not posiciones:
        print(f'  SL enviado pero posición {orden.ticket} ya fue cerrada durante la modificación')
        return False
    print(f'  {valor}: SL actualizado: orden {orden.ticket} → {posiciones[0].sl:.2f}')
    return True


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
    sl_nuevo = P0 - b / L

    for orden in actual_OA:
        sl = orden.sl
        Pi = orden.price_open
        cambios = False
        ganancia = (P0 - Pi) * L

        if sl == 0:
            if ganancia >= a:
                sl_ok = cambiar_SL(orden, valor, sl_nuevo)
                # Repone la orden de compra en el mismo soporte para mantener el nivel activo
                request = generate_request_buy_limit(
                    valor,
                    order_type=mt5.ORDER_TYPE_BUY_LIMIT,
                    volumen=lotajes[valor],
                    precio=Pi,
                )
                ejecutar_orden(request, symbol=valor, volumen=lotajes[valor], precio=Pi)
                cambios = sl_ok
        else:
            if sl_nuevo > sl:
                print(f'  Trailing stop: {valor} P0={P0:.2f} SL {sl:.2f} → {sl_nuevo:.2f}')
                if cambiar_SL(orden, valor, sl_nuevo):
                    cambios = True
                elif valor in dic_seguimiento and orden.ticket in dic_seguimiento[valor]:
                    dic_seguimiento[valor].remove(orden.ticket)

        if cambios:
            if valor not in dic_seguimiento:
                dic_seguimiento[valor] = []
            if orden.ticket not in dic_seguimiento[valor]:
                dic_seguimiento[valor].append(orden.ticket)


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


def informacion(valores: list, lotajes: dict, units: dict, n_sizes: dict, a: dict):
    """Muestra el estado actual de soportes y distancias para todos los activos."""
    print('\n─── Información ───────────────────────────────────────────')
    for valor in valores:
        P0 = obtener_precio_actual(valor, modo='B')
        N = n_sizes[valor]
        lista_N = leer_lista_N(valor, N)
        L = lotajes[valor] * units[valor]
        a_valor = a[valor]

        df = pd.DataFrame(lista_N, columns=['Precio'])
        df['Distancia_USD'] = (P0 - df['Precio']) * L
        df = df[df['Distancia_USD'] >= 0].sort_values('Distancia_USD').reset_index(drop=True)

        por_declarar = df[df['Distancia_USD'] < a_valor].copy()
        declarados = df[df['Distancia_USD'] >= a_valor].copy()

        print(f'\n{valor} | P0={P0:.2f} | N={N}')
        if len(por_declarar):
            por_declarar['Falta_USD'] = (a_valor - por_declarar['Distancia_USD']).round(2)
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
    pos_info = {}
    sl_activo_global_prev = None
    i = 0

    try:
        while True:
            time_sleep = True

            # Si hay alguna posición con SL activo (sl≠0) en un activo con mercado
            # abierto, este ciclo se saltan A) limpiar OE y B) crear buy limits en
            # TODOS los activos para acelerar la revisión del trailing stop, hasta
            # que esa posición cierre.
            posiciones_todas = mt5.positions_get() or []
            sl_activo_global = any(p.sl != 0 and mercado_abierto(p.symbol) for p in posiciones_todas)
            if sl_activo_global != sl_activo_global_prev:
                if sl_activo_global:
                    print('  SL activo con mercado abierto → pausando gestión de buy limits (foco en trailing stop)')
                else:
                    print('  Sin SL activo → reanudando gestión de buy limits')
                sl_activo_global_prev = sl_activo_global

            for valor in VALORES:
                try:
                    L = LOTAJES[valor] * UNITS[valor]

                    N = n_sizes[valor]
                    lista_N = leer_lista_N(valor, N)

                    lista_OA, lista_OE, actual_OA, actual_OE, dic_seguimiento = obtener_conjuntos_actuales(valor, dic_seguimiento, pos_info)

                    # A y B: solo si el mercado permite nuevas órdenes; si está cerrado,
                    # no eliminar las OE existentes porque no se pueden reponer.
                    # Si hay un SL activo en el sistema (sl_activo_global), se saltan
                    # A/B para priorizar la revisión del trailing stop.
                    if mercado_abierto(valor) and not sl_activo_global:
                        precio_max_saliente = limpiar_ordenes_pendientes_no_validas(valor, actual_OE, lista_N)
                        crear_ordenes_espera(lista_OA, lista_OE, lista_N, valor, L, A[valor], LOTAJES, precio_max_saliente)

                    # C: Trailing stop en posiciones abiertas
                    trailing_stop(actual_OA, valor, L, A[valor], B[valor], LOTAJES, dic_seguimiento)

                    # D: Cierre por pérdida máxima
                    controlar_perdida_max(actual_OA, valor, L, LOTAJES, PERDIDA_MAX[valor])

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
