"""
params_din.py

Lectura de los C1 publicados (`config/active_parameters.json`, esquema `q5`, lo escribe `publicador_c1.py`) para X0
y X1 cuando `TIPO_EJECUCION = "din"` (Q5-5b). Un valor sin entrada válida cae a `config.py` solo para ese valor:
sin archivo, de otro esquema, sin candidata, `model_status != "trained"` o `calculado_en` más viejo que
`PARAMS_DIN_EDAD_MAX_MIN`. Cada cambio de estado de un valor (C1 publicados <-> config.py) se avisa una vez.
"""

import datetime
import json
import math
import re
from pathlib import Path

import config as cfg
import config_smart
import registro_din as reg

_cache = {'mtime': None, 'datos': None}
_estado_aviso = {}
_firma_registro = {}  # valor -> qué entrada (o motivo de caída) se registró por última vez
avisador = print  # X0 lo reemplaza por un print coordinado con su monitor en vivo


def _leer_archivo() -> dict | None:
    ruta = cfg.RUTA_ACTIVE_PARAMETERS
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        _cache.update(mtime=None, datos=None)
        return None
    if mtime != _cache['mtime']:
        try:
            datos = json.loads(ruta.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return _cache['datos']  # el publicador lo está reemplazando: se sigue con la lectura anterior
        _cache.update(mtime=mtime, datos=datos)
    return _cache['datos']


def _motivo_de_caida(valor: str, ahora: datetime.datetime) -> tuple:
    """(motivo, entrada): motivo None si la entrada es válida."""
    datos = _leer_archivo()
    if datos is None:
        return 'sin active_parameters.json', None
    if datos.get('esquema') != 'q5':
        return 'active_parameters.json de otro esquema', None
    entrada = datos.get('valores', {}).get(valor)
    if entrada is None:
        return 'sin candidata publicada', None
    if entrada.get('model_status') != 'trained':
        return f'model_status={entrada.get("model_status")}', None
    edad_min = (ahora - datetime.datetime.fromisoformat(entrada['calculado_en'])).total_seconds() / 60
    if edad_min > cfg.PARAMS_DIN_EDAD_MAX_MIN:
        return f'publicado hace {edad_min:.0f} min (máximo {cfg.PARAMS_DIN_EDAD_MAX_MIN})', None
    return None, entrada


def parametros_vigentes(valor: str, ahora: datetime.datetime | None = None, avisar: bool = True) -> dict | None:
    """Entrada publicada de `valor` ({N, K, N_EXP, LAMBDA, A, B, factor_B, p, PERDIDA_MAX, candidato, ...}) si rige
    el modo dinámico y es válida; None si X0/X1 deben usar `config.py` para este valor. `avisar=False` no imprime
    (el monitor de X0 la consulta en cada refresco)."""
    if cfg.TIPO_EJECUCION != 'din':
        return None
    ahora = ahora or datetime.datetime.now()
    motivo, entrada = _motivo_de_caida(valor, ahora)
    estado = ('din', entrada['candidato']) if entrada else ('est', motivo)
    if avisar and _estado_aviso.get(valor) != estado:
        _estado_aviso[valor] = estado
        avisador(f'  [params_din] {valor}: C1 publicados de {entrada["candidato"]}' if entrada
                 else f'  [params_din] {valor}: usando config.py ({motivo})')
    if avisar:
        # cada publicación nueva (calculado_en distinto) y cada caída a config.py: qué C1 leyó realmente este proceso
        firma = (entrada['candidato'], entrada['calculado_en']) if entrada else motivo
        if _firma_registro.get(valor) != firma:
            _firma_registro[valor] = firma
            if entrada:
                reg.registrar('c1_leidos', valor, **entrada)
            else:
                reg.registrar('usa_config', valor, motivo=motivo)
    return entrada


def n_vigente(valor: str, n_estatico: int, avisar: bool = True) -> int:
    """`N` que rige a `valor`: el publicado o, si no hay, el de `config.py`."""
    p = parametros_vigentes(valor, avisar=avisar)
    return int(p['N']) if p else n_estatico


def params_soporte(p: dict | None) -> dict | None:
    """{K, N_EXP, LAMBDA} para `_preparar_valor_N` desde una entrada publicada; None usa los de `config.py`."""
    return {'K': p['K'], 'N_EXP': p['N_EXP'], 'LAMBDA': p['LAMBDA']} if p else None


def z_virtual(realizado: float, flotante: float) -> float:
    """Z de la cuenta virtual de un valor (la que Q5 valida, 3000 USD por valor): capital inicial + P&L realizado desde
    `cuenta_desde` + P&L abierto. La cuenta de MT5 es una sola para los 7 valores."""
    return config_smart.CUENTA['capital_inicial'] + realizado + flotante


def cupo_oa(z: float, umbral: float) -> int:
    """Tope de Órdenes Abiertas, igual que `X4_backtester._paso_F`: floor(R_TOPE_OA · Z / umbral), con `umbral` la pérdida
    máxima en USD de una OA al lote que opera. Es el peor caso: si todas las OA permitidas llegaran a su umbral a la
    vez, la pérdida sería a lo más R_TOPE_OA · Z. Con Z bajo el umbral el cupo es 0 y no se abren posiciones nuevas."""
    return max(0, math.floor(config_smart.R_TOPE_OA * z / umbral))


def ruta_soportes(valor: str, N: int, carpeta: Path) -> Path:
    """`{valor}_{N}.json`. Tras un cambio de `N` publicado, X0 escribe el archivo nuevo recién en su próximo ciclo: mientras
    no exista se usa el más reciente de los demás `{valor}_{N'}.json` (los `_bt.json` no cuentan)."""
    nominal = carpeta / f'{valor}_{N}.json'
    if nominal.exists():
        return nominal
    patron = re.compile(rf'^{re.escape(valor)}_\d+\.json$')
    otros = [f for f in carpeta.glob(f'{valor}_*.json') if patron.match(f.name)]
    elegido = max(otros, key=lambda f: f.stat().st_mtime) if otros else nominal
    if reg.cada(f'respaldo_{valor}_{N}', 600):  # X1 la consulta en cada vuelta
        reg.registrar('soportes_respaldo', valor, N=N, nominal=nominal.name, usa=elegido.name if otros else None)
    return elegido


def sembrar_soportes(valor: str, N: int, carpeta: Path) -> None:
    """Warm start al cambiar `N` en vivo: si `{valor}_{N}.json` no existe, lo crea con el conjunto más reciente de otro `N`
    (X0 lo recorta o completa al tamaño pedido en `obtener_df_extremos`), en vez de partir de puntos aleatorios."""
    origen = ruta_soportes(valor, N, carpeta)
    destino = carpeta / f'{valor}_{N}.json'
    if origen != destino:
        destino.write_bytes(origen.read_bytes())
        reg.registrar('soportes_sembrados', valor, N=N, origen=origen.name, destino=destino.name)
