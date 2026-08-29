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
    X1_RETRY_BLOQUEADOS_S,
)


class LimiteOrdenesError(Exception):
    """MT5 rechazó la orden por límite de posiciones/órdenes pendientes en la cuenta
    (retcode 10040) — hay demasiadas OA+OE abiertas simultáneamente."""


_ultimo_print_error = {}  # {(symbol, clave): timestamp} — throttle de prints de error MT5


def _print_throttled(symbol: str, clave, mensaje: str, intervalo: float = X1_RETRY_BLOQUEADOS_S):
    """Imprime mensaje solo si no se avisó el mismo (symbol, clave) hace menos de intervalo
    segundos. Evita spam cuando un retcode de MT5 (ej. servidor con autotrading deshabilitado)
    se repite en cada ciclo mientras persiste — sin ocultar que sigue ocurriendo."""
    ahora = time.time()
    if ahora - _ultimo_print_error.get((symbol, clave), 0) >= intervalo:
        print(mensaje)
        _ultimo_print_error[(symbol, clave)] = ahora


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
    Reintenta hasta 12 veces con pausa de 5s, por si X0 está escribiendo simultáneamente
    (archivo aún no existe, o existe pero X0 lo está reescribiendo — OneDrive puede
    extender la ventana de lock/sync más allá de la propia escritura del proceso).
    """
    json_path = CARPETA_N_PROD / f'{valor}_{N}.json'
    for _ in range(12):
        if json_path.exists():
            try:
                lista_N = json_act(str(CARPETA_N_PROD / f'{valor}_{N}'))
                return [round(n, 2) for n in lista_N]
            except (json.JSONDecodeError, PermissionError, OSError):
                pass
        time.sleep(5)
    raise FileNotFoundError(f'No se encontró (o no se pudo leer) {json_path} después de 12 intentos')


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


def _cierre_historico(ticket: int) -> tuple:
    """Precio y ganancia reales de una posición ya cerrada, vía el historial de
    deals de MT5 (el deal de salida, DEAL_ENTRY_OUT). Retorna (None, None) si
    el historial todavía no tiene el deal de salida."""
    deals = mt5.history_deals_get(position=ticket)
    if not deals:
        return None, None
    salidas = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    if not salidas:
        return None, None
    return salidas[-1].price, salidas[-1].profit


def _informar_cierre(valor: str, ticket: int, info: dict) -> None:
    """Imprime lotaje, precio de apertura, precio de cierre y ganancia al detectar
    que una OA pasó a OC — por perdida_max, trailing stop (SL ejecutado por el
    broker) o cierre externo. Única fuente para esta transición: cubre las tres
    causas sin duplicar el print entre ellas."""
    precio_cierre, ganancia = _cierre_historico(ticket)
    pc_str = f'{precio_cierre:.2f}' if precio_cierre is not None else 'desconocido'
    g_str = f'${ganancia:.2f}' if ganancia is not None else 'desconocida'
    print(f'  [OA > OC] {valor}  ticket={ticket}  lotaje={info["lote"]}  '
          f'precio_apertura={info["precio_apertura"]:.2f}  precio_cierre={pc_str}  ganancia={g_str}')


def obtener_conjuntos_actuales(valor: str, dic_seguimiento: dict, pos_info: dict,
                                valores_inicializados: set) -> tuple:
    """
    Devuelve las posiciones abiertas (OA) y órdenes pendientes (OE) actuales en MT5.
    Limpia dic_seguimiento de posiciones que ya fueron cerradas externamente.
    `pos_info` (ticket → lote/precio_apertura) se actualiza con las OA vivas: al
    ver un ticket nuevo informa la transición OE > OA (la única forma de abrir
    una posición en X1 es que una buy limit se ejecute), y al detectar que un
    ticket ya no está abierto, informa la transición OA > OC. `valores_inicializados`
    evita el falso positivo de reportar OE > OA para posiciones que ya estaban
    abiertas antes de arrancar X1 (primer ciclo de cada activo no notifica).
    """
    actual_OA = mt5.positions_get(symbol=valor)
    if actual_OA is None:
        raise RuntimeError(f'positions_get({valor}) retornó None: {mt5.last_error()}')
    actual_OE = mt5.orders_get(symbol=valor)
    if actual_OE is None:
        raise RuntimeError(f'orders_get({valor}) retornó None: {mt5.last_error()}')

    lista_OA = [p.price_open for p in actual_OA]
    lista_OE = [o.price_open for o in actual_OE]

    ya_inicializado = valor in valores_inicializados
    valores_inicializados.add(valor)

    actual_tickets = {p.ticket for p in actual_OA}
    for p in actual_OA:
        if p.ticket not in pos_info:
            if ya_inicializado:
                print(f'  [OE > OA] {valor}  ticket={p.ticket}  ejecutada @ {p.price_open:.2f}')
            pos_info[p.ticket] = {'valor': valor, 'lote': p.volume, 'precio_apertura': p.price_open}

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
                _print_throttled(valor, 'order_send_none',
                                  f'  {valor}: order_send failed: {mt5.last_error()}')
            elif result.retcode != mt5.TRADE_RETCODE_DONE:
                if result.retcode not in [10018]:  # 10018: mercado cerrado
                    _print_throttled(valor, result.retcode,
                                      f'  {valor}: Error al eliminar orden {orden.ticket}: retcode={result.retcode}')
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
            if result.retcode == 10040:  # límite de posiciones/órdenes pendientes de la cuenta
                raise LimiteOrdenesError(f'{symbol}: límite de órdenes en la cuenta (retcode 10040)')
            if result.retcode in [10006, 10044, 10018, 10031]:
                return False
            _print_throttled(symbol, result.retcode,
                              f'  {symbol}: Error al ejecutar orden: retcode={result.retcode}, comment={result_dict.get("comment")}')
            return False
        else:
            return True
    except LimiteOrdenesError:
        raise
    except Exception as e:
        _print_throttled(symbol, 'excepcion', f'  {symbol}: Excepción en ejecutar_orden: {e}')
        return False


def liberar_orden_lejana(dic_bloqueados: dict):
    """Ante el límite de posiciones/órdenes pendientes de la cuenta (retcode 10040),
    cancela el buy limit más lejano del precio actual entre TODOS los activos —
    libera espacio para priorizar los soportes más cercanos, sin importar qué activo
    sea dueño de la orden lejana. Marca el precio cancelado como temporalmente bloqueado.

    Retorna (symbol, precio) de la orden liberada, o None si no había nada que liberar.
    """
    todas_OE = mt5.orders_get() or []
    candidatas = [o for o in todas_OE if o.type == mt5.ORDER_TYPE_BUY_LIMIT]

    mas_lejana = None
    mayor_distancia = -float('inf')
    for orden in candidatas:
        if orden.symbol not in LOTAJES:
            continue
        try:
            P0 = obtener_precio_actual(orden.symbol, modo='B')
        except RuntimeError:
            continue
        L = LOTAJES[orden.symbol] * UNITS[orden.symbol]
        distancia = (P0 - orden.price_open) * L
        if distancia > mayor_distancia:
            mayor_distancia = distancia
            mas_lejana = orden

    if mas_lejana is None:
        return None

    request = {
        'action': mt5.TRADE_ACTION_REMOVE,
        'order': mas_lejana.ticket,
        'symbol': mas_lejana.symbol,
        'type': mas_lejana.type,
        'position': mas_lejana.position_id,
        'comment': 'Liberacion por limite de ordenes',
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        return None

    symbol = mas_lejana.symbol
    precio = round(mas_lejana.price_open, 2)
    dic_bloqueados.setdefault(symbol, {})[precio] = time.time()
    print(f'  Límite de órdenes alcanzado: liberando {symbol} @ {precio:.2f} '
          f'(distancia {mayor_distancia:.2f} USD) para priorizar soportes cercanos')
    return symbol, precio


def _ejecutar_con_liberacion(request: dict, symbol: str, volumen: float, precio: float,
                              dic_bloqueados: dict, silent: bool = False) -> bool:
    """Envuelve ejecutar_orden: si MT5 rechaza por límite de posiciones/órdenes de la
    cuenta (retcode 10040), libera la orden más lejana del precio (de cualquier activo,
    vía liberar_orden_lejana) y reintenta una vez. Si no hay nada que liberar o el
    reintento vuelve a chocar con el límite, bloquea `precio` temporalmente — se
    reintenta recién pasado X1_RETRY_BLOQUEADOS_S.

    silent=True omite el print individual del bloqueo (usado por crear_ordenes_espera,
    que ya imprime un resumen agregado por activo al final del ciclo)."""
    try:
        return ejecutar_orden(request, symbol, volumen, precio)
    except LimiteOrdenesError:
        pass

    if liberar_orden_lejana(dic_bloqueados) is not None:
        try:
            if ejecutar_orden(request, symbol, volumen, precio):
                return True
        except LimiteOrdenesError:
            pass

    bloqueados_valor = dic_bloqueados.setdefault(symbol, {})
    if not silent and precio not in bloqueados_valor:
        print(f'  {symbol}: buy limit @ {precio:.2f} bloqueado temporalmente (límite de órdenes en la cuenta)')
    bloqueados_valor[precio] = time.time()
    return False


def crear_ordenes_espera(lista_OA: list, lista_OE: list, lista_N: list,
                          valor: str, L: float, a: float, lotajes: dict,
                          dic_bloqueados: dict, precio_max_saliente: float = None):
    """
    Para cada soporte en lista_N que no tenga ya una orden activa o pendiente,
    crea una orden buy limit si el precio actual está al menos a distancia `a` USD por encima.

    Regla de reemplazo: cuando este ciclo se canceló al menos un buy limit
    (precio_max_saliente = el más cercano al precio), un soporte también entra si
    queda por debajo del promedio entre el precio actual y ese buy limit saliente.
    Recupera la cobertura cercana al precio que si no se perdería, porque el filtro
    de distancia `a` deja el primer soporte de reemplazo al menos `a` bajo el precio.

    Si la cuenta alcanza su límite de posiciones/órdenes (retcode 10040), se libera
    la orden más lejana del precio entre todos los activos y se reintenta una vez
    (`_ejecutar_con_liberacion`); los soportes bloqueados temporalmente (en
    `dic_bloqueados[valor]`) no se reintentan hasta pasado X1_RETRY_BLOQUEADOS_S.
    """
    P0 = obtener_precio_actual(valor, modo='B')
    lista_OAE = lista_OA + lista_OE
    umbral_reemplazo = None
    if precio_max_saliente is not None and precio_max_saliente < P0:
        umbral_reemplazo = (P0 + precio_max_saliente) / 2
    ejecutadas = []
    bloqueadas = []
    bloqueados_valor = dic_bloqueados.setdefault(valor, {})

    for Pi in sorted(lista_N, reverse=True):
        if Pi in lista_OAE:
            continue
        ts_bloqueo = bloqueados_valor.get(Pi)
        if ts_bloqueo is not None and (time.time() - ts_bloqueo) < X1_RETRY_BLOQUEADOS_S:
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
            if _ejecutar_con_liberacion(request, valor, lotajes[valor], Pi, dic_bloqueados, silent=True):
                ejecutadas.append(Pi)
                bloqueados_valor.pop(Pi, None)
            elif Pi in bloqueados_valor:
                bloqueadas.append(Pi)

    if ejecutadas:
        print(f'  {valor}: {len(ejecutadas)} órdenes ejecutadas desde {min(ejecutadas)} hasta {max(ejecutadas)}')
    if bloqueadas:
        print(f'  {valor}: {len(bloqueadas)} buy limits bloqueados temporalmente entre '
              f'{min(bloqueadas):.2f} y {max(bloqueadas):.2f} (límite de órdenes en la cuenta)')


def cambiar_SL(orden, valor: str, sl: float, silent: bool = False) -> bool:
    """Modifica el SL. Retorna True solo si MT5 confirma el cambio Y la posición sigue abierta.

    silent=True omite el print individual de éxito (usado por trailing_stop, que ya
    imprime un resumen agregado por activo al final del ciclo)."""
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
        _print_throttled(valor, 'cambiar_sl_none', f'  {valor}: cambiar_SL failed: {mt5.last_error()}')
        return False
    elif result.retcode != mt5.TRADE_RETCODE_DONE:
        _print_throttled(valor, result.retcode,
                          f'  {valor}: Error modificando SL orden {orden.ticket}: retcode={result.retcode}')
        return False
    posiciones = mt5.positions_get(ticket=orden.ticket)
    if not posiciones:
        print(f'  SL enviado pero posición {orden.ticket} ya fue cerrada durante la modificación')
        return False
    if not silent:
        print(f'  {valor}: SL actualizado: orden {orden.ticket} → {posiciones[0].sl:.2f}')
    return True


def trailing_stop(actual_OA: list, valor: str, L: float, a: float, b: float,
                   lotajes: dict, dic_seguimiento: dict, dic_bloqueados: dict):
    """
    Para cada posición abierta:
    - Si no tiene SL y la ganancia >= a USD → pone el primer SL ganador y repone la orden
    - Si ya tiene SL y el nuevo SL calculado sube → mueve el SL al alza (trailing)

    b: distancia en USD que debe mantener el SL bajo el precio actual (normalizada por L).
    """
    if not actual_OA or not mercado_abierto(valor):
        return

    P0 = obtener_precio_actual(valor, modo='B')
    sl_nuevo = P0 - b / L
    n_cambios_sl = 0

    for orden in actual_OA:
        sl = orden.sl
        Pi = orden.price_open
        cambios = False
        ganancia = (P0 - Pi) * L

        if sl == 0:
            if ganancia >= a:
                sl_ok = cambiar_SL(orden, valor, sl_nuevo, silent=True)
                # Repone la orden de compra en el mismo soporte para mantener el nivel activo
                request = generate_request_buy_limit(
                    valor,
                    order_type=mt5.ORDER_TYPE_BUY_LIMIT,
                    volumen=lotajes[valor],
                    precio=Pi,
                )
                _ejecutar_con_liberacion(request, valor, lotajes[valor], Pi, dic_bloqueados)
                cambios = sl_ok
        else:
            if sl_nuevo > sl:
                if cambiar_SL(orden, valor, sl_nuevo, silent=True):
                    cambios = True
                elif valor in dic_seguimiento and orden.ticket in dic_seguimiento[valor]:
                    dic_seguimiento[valor].remove(orden.ticket)

        if cambios:
            n_cambios_sl += 1
            if valor not in dic_seguimiento:
                dic_seguimiento[valor] = []
            if orden.ticket not in dic_seguimiento[valor]:
                dic_seguimiento[valor].append(orden.ticket)

    if n_cambios_sl:
        print(f'  Cambio SL de {n_cambios_sl} operaciones del valor {valor}')


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
        clave = result.retcode if result is not None else 'order_send_none'
        _print_throttled(valor, clave, f'  {valor}: Error al cerrar posición {orden.ticket}: {mt5.last_error()}')
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
    """
    Por activo, cuánto falta que P0 se mueva para que:
    A) la OE pendiente más cercana se ejecute (pase a OA) — requiere que P0 baje.
    B) el soporte/resistencia de lista_N sin orden aún (ni OE ni OA) — porque está
       muy cerca bajo el precio (distancia < a) o porque está sobre el precio
       actual — pase a tener una OE declarada, lo que requiere que P0 suba hasta
       Precio_activacion_OE_OA = Precio_OE + a/L (mismo umbral que distancia_ok
       en crear_ordenes_espera). Solo se muestran soportes con
       Precio_activacion_OE_OA > P0 (Falta_sube_USD > 0): un soporte que ya
       cumple distancia_ok pero sigue sin OE por estar bloqueado
       (dic_bloqueados) no aparece acá.
    Usa el estado real de MT5 (positions_get/orders_get), no la clasificación
    teórica por distancia sobre lista_N.
    """
    datos = {}
    for valor in valores:
        P0 = obtener_precio_actual(valor, modo='B')
        N = n_sizes[valor]
        lista_N = leer_lista_N(valor, N)
        L = lotajes[valor] * units[valor]
        a_valor = a[valor]

        actual_OA = mt5.positions_get(symbol=valor)
        if actual_OA is None:
            raise RuntimeError(f'positions_get({valor}) retornó None: {mt5.last_error()}')
        actual_OE = mt5.orders_get(symbol=valor)
        if actual_OE is None:
            raise RuntimeError(f'orders_get({valor}) retornó None: {mt5.last_error()}')

        precios_declarados = {round(o.price_open, 2) for o in actual_OE} | \
                              {round(p.price_open, 2) for p in actual_OA}

        df_a = None
        if actual_OE:
            df_a = pd.DataFrame(sorted({round(o.price_open, 2) for o in actual_OE}, reverse=True),
                                 columns=['Precio_OE'])
            df_a['Falta_baja_USD'] = ((P0 - df_a['Precio_OE']) * L).round(2)
            df_a = df_a.sort_values('Falta_baja_USD').head(3).reset_index(drop=True)

        pendientes = [p for p in lista_N if round(p, 2) not in precios_declarados]
        df_b = None
        if pendientes:
            df_b = pd.DataFrame(pendientes, columns=['Precio_OE'])
            df_b['Precio_activacion_OE_OA'] = (df_b['Precio_OE'] + a_valor / L).round(2)
            df_b['Falta_sube_USD'] = ((df_b['Precio_activacion_OE_OA'] - P0) * L).round(2)
            df_b = df_b[df_b['Falta_sube_USD'] > 0]
            df_b = df_b.sort_values('Falta_sube_USD').head(3).reset_index(drop=True)
            df_b = df_b[['Precio_activacion_OE_OA', 'Precio_OE', 'Falta_sube_USD']]
            if df_b.empty:
                df_b = None

        datos[valor] = {'P0': P0, 'df_a': df_a, 'df_b': df_b}

    print('\n─── A) OE → OA: cuánto debe BAJAR P0 para ejecutar la OE más cercana ─────────')
    for valor in valores:
        d = datos[valor]
        print(f'\n{valor} | P0={d["P0"]:.2f}')
        if d['df_a'] is not None:
            print(d['df_a'].to_string(index=False))
        else:
            print('  Sin OE pendientes')

    print('\n─── B) Soporte/Resistencia → OE: cuánto debe SUBIR P0 para declarar el más cercano ─')
    for valor in valores:
        d = datos[valor]
        print(f'\n{valor} | P0={d["P0"]:.2f}')
        if d['df_b'] is not None:
            print(d['df_b'].to_string(index=False))
        else:
            print('  Todos los soportes de N ya tienen orden')


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

    # Validar que existe el JSON de soportes para el N configurado de cada activo.
    # Si falta, X1 igual arranca (leer_lista_N reintenta y salta el activo por
    # ciclo), pero sin este aviso el desfase (config.py desincronizado con lo que
    # X0 ya generó) queda silencioso durante horas.
    faltantes = [f'{valor}_{n_sizes[valor]}.json' for valor in VALORES
                 if not (CARPETA_N_PROD / f'{valor}_{n_sizes[valor]}.json').exists()]
    if faltantes:
        print(f'\n⚠ Faltan JSONs de soportes en {CARPETA_N_PROD} para el N configurado: '
              f'{", ".join(faltantes)}')
        print('  Revisa que config.py esté sincronizado con lo que X0 ya generó '
              '(n_sizes_ejecucion) — esos activos se saltarán cada ciclo hasta que aparezcan.')

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
    valores_inicializados = set()  # evita falso [OE > OA] con OA ya abiertas antes de arrancar X1
    dic_bloqueados = {}  # {valor: {precio: timestamp}} — buy limits lejanos liberados por retcode 10040
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

                    lista_OA, lista_OE, actual_OA, actual_OE, dic_seguimiento = obtener_conjuntos_actuales(valor, dic_seguimiento, pos_info, valores_inicializados)

                    # A y B: solo si el mercado permite nuevas órdenes; si está cerrado,
                    # no eliminar las OE existentes porque no se pueden reponer.
                    # Si hay un SL activo en el sistema (sl_activo_global), se saltan
                    # A/B para priorizar la revisión del trailing stop.
                    if mercado_abierto(valor) and not sl_activo_global:
                        precio_max_saliente = limpiar_ordenes_pendientes_no_validas(valor, actual_OE, lista_N)
                        crear_ordenes_espera(lista_OA, lista_OE, lista_N, valor, L, A[valor], LOTAJES, dic_bloqueados, precio_max_saliente)

                    # C: Trailing stop en posiciones abiertas
                    trailing_stop(actual_OA, valor, L, A[valor], B[valor], LOTAJES, dic_seguimiento, dic_bloqueados)

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
                total_bloqueados = sum(len(p) for p in dic_bloqueados.values())
                if total_bloqueados:
                    detalle = ', '.join(f'{v}:{len(p)}' for v, p in dic_bloqueados.items() if p)
                    print(f'  Buy limits bloqueados temporalmente: {total_bloqueados} ({detalle})')
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
