"""
market_status.py

Estados:

  abierto:
    - permite cerrar posiciones
    - permite abrir posiciones
    - permite declarar BUY LIMIT

  pre-market:
    - permite cerrar posiciones
    - NO permite abrir posiciones nuevas
    - NO permite declarar BUY LIMIT

  cerrado:
    - no permite operar

Para acciones estadounidenses:
  pre-market     04:00 - 09:30, hora de Nueva York
  sesión regular 09:30 - 16:00, hora de Nueva York

BTCUSD y ETHUSD mantienen la lógica original de mercado_abierto(),
porque no utilizan la sesión regular de acciones estadounidenses.

Próximo cambio de estado (hora, tiempo restante y estado nuevo): solo se declara
para acciones USA y solo si el estado leído de MT5 coincide con el del horario
regular. Se calcula con el horario fijo, sin feriados ni cierres anticipados.
Para crypto, o si MT5 contradice el horario (ej. sin ticks en plena sesión),
no es determinable y queda en None.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5

from config import VALORES
from X1_trading import _servidor_ahora, mercado_abierto


# Activos que operan según la sesión bursátil estadounidense
ACCIONES_USA = {
    'TSLA',
    'GOOGL',
    'NVDA',
    'AMZN',
    'MSFT',
}

ZONA_UTC = ZoneInfo('UTC')
ZONA_NUEVA_YORK = ZoneInfo('America/New_York')

INICIO_PREMARKET = time(4, 0)
INICIO_SESION_REGULAR = time(9, 30)
FIN_SESION_REGULAR = time(16, 0)

# (hora NY en que cambia el estado, estado que arranca a esa hora)
TRANSICIONES_ACCION_USA = (
    (INICIO_PREMARKET, 'pre-market'),
    (INICIO_SESION_REGULAR, 'abierto'),
    (FIN_SESION_REGULAR, 'cerrado'),
)


def ahora_nueva_york():
    """
    Hora actual en Nueva York, tomada del reloj del sistema.

    No se deriva de _servidor_ahora(): el tick.time de MT5 viene en hora del
    servidor del broker (no UTC), así que tratarlo como UTC desfasaría la
    sesión por el offset del broker.
    """
    return datetime.now(ZONA_NUEVA_YORK)


def _estado_segun_horario(ahora_ny):
    # Sábado o domingo
    if ahora_ny.weekday() >= 5:
        return 'cerrado'

    hora_ny = ahora_ny.time()

    if INICIO_PREMARKET <= hora_ny < INICIO_SESION_REGULAR:
        return 'pre-market'

    if INICIO_SESION_REGULAR <= hora_ny < FIN_SESION_REGULAR:
        return 'abierto'

    return 'cerrado'


def _proxima_transicion(ahora_ny):
    dia = ahora_ny.date()

    while True:
        if dia.weekday() < 5:
            for hora, estado in TRANSICIONES_ACCION_USA:
                momento = datetime.combine(dia, hora, tzinfo=ZONA_NUEVA_YORK)

                if momento > ahora_ny:
                    return momento, estado

        dia += timedelta(days=1)


def estado_accion_usa(valor, ahora_ny=None):
    ahora_ny = ahora_ny or ahora_nueva_york()

    estado = _estado_segun_horario(ahora_ny)

    # La ausencia de ticks o permisos sigue prevaleciendo
    if estado != 'cerrado' and not mercado_abierto(valor):
        return 'cerrado'

    return estado


def estado_mercado(valor, ahora_ny=None):
    info = mt5.symbol_info(valor)

    if info is None:
        return 'sin símbolo'

    if valor in ACCIONES_USA:
        return estado_accion_usa(valor, ahora_ny)

    return 'abierto' if mercado_abierto(valor) else 'cerrado'


def proximo_cambio(valor, estado, ahora_ny=None):
    """
    (momento en hora NY, estado nuevo, tiempo restante) del próximo cambio de
    estado, o None si no es determinable.
    """
    if valor not in ACCIONES_USA:
        return None

    ahora_ny = ahora_ny or ahora_nueva_york()

    if estado != _estado_segun_horario(ahora_ny):
        return None

    momento, estado_nuevo = _proxima_transicion(ahora_ny)

    # Se resta en UTC: entre dos fechas con distinto offset (cambio de hora
    # en EE.UU.) la resta directa en hora local ignoraría la hora de diferencia
    faltan = momento.astimezone(ZONA_UTC) - ahora_ny.astimezone(ZONA_UTC)

    return momento, estado_nuevo, faltan


def permisos_mercado(valor):
    ahora_ny = ahora_nueva_york()
    estado = estado_mercado(valor, ahora_ny)
    cambio = proximo_cambio(valor, estado, ahora_ny)

    return {
        'estado': estado,

        # En pre-market solo se permiten cierres
        'puede_cerrar': estado in ('abierto', 'pre-market'),

        # Solo en sesión regular
        'puede_abrir': estado == 'abierto',
        'puede_buy_limit': estado == 'abierto',

        'proximo_estado': cambio[1] if cambio else None,
        'proximo_cambio_ny': cambio[0] if cambio else None,
        'faltan': cambio[2] if cambio else None,
    }


def formato_duracion(delta):
    minutos = int(delta.total_seconds() // 60)
    dias, minutos = divmod(minutos, 1440)
    horas, minutos = divmod(minutos, 60)

    partes = []
    if dias:
        partes.append(f"{dias}d")
    if dias or horas:
        partes.append(f"{horas}h")
    partes.append(f"{minutos}m")

    return ' '.join(partes)


if __name__ == '__main__':
    if not mt5.initialize():
        raise SystemExit(
            f"No se pudo inicializar MT5: {mt5.last_error()}"
        )

    try:
        for valor in VALORES:
            mt5.symbol_select(valor, True)

        ahora_srv = datetime.fromtimestamp(
            _servidor_ahora(),
            tz=ZONA_UTC,
        )

        print(f"Hora servidor MT5: {ahora_srv:%Y-%m-%d %H:%M %a}")
        print(f"Hora Nueva York:   {ahora_nueva_york():%Y-%m-%d %H:%M %a %Z}")
        print()

        for valor in VALORES:
            permisos = permisos_mercado(valor)

            if permisos['faltan'] is None:
                siguiente = '-'
            else:
                siguiente = (
                    f"{permisos['proximo_estado']} en "
                    f"{formato_duracion(permisos['faltan'])} "
                    f"({permisos['proximo_cambio_ny']:%a %H:%M} NY)"
                )

            print(
                f"{valor:<8} "
                f"{permisos['estado']:<11} "
                f"cerrar={permisos['puede_cerrar']} "
                f"abrir={permisos['puede_abrir']} "
                f"buy_limit={permisos['puede_buy_limit']} "
                f"-> {siguiente}"
            )

    finally:
        mt5.shutdown()
