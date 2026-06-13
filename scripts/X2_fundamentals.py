"""
X2_fundamentals.py

Score fundamental por activo en [0, 1].
Acciones: yfinance (ROE, márgenes, FCF, crecimiento, valorización, deuda, analistas).
Crypto: yfinance + CoinGecko + Fear & Greed (alternative.me).
Output: fundamentals/scores.json + fundamentals/x2_history.json

Score final = (1 - W_TENDENCIA) × score_cross + W_TENDENCIA × score_tendencia
  score_cross:     normalización min-max entre activos del universo (hoy)
  score_tendencia: evolución del activo respecto a sí mismo (vs. hace DIAS_TENDENCIA días)
                   → 0.5 neutral si hay menos de 7 días de historia acumulada

Guard de día: saltea si ya se ejecutó hoy, salvo --forzar.
"""

import argparse
import json
import math
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    BASE_DIR,
    CARPETA_FUNDAMENTALS,
    DIAS_TENDENCIA,
    PESOS_CRYPTO,
    PESOS_STOCK,
    VALORES,
    W_TENDENCIA,
)

_CRYPTO = {'BTCUSD', 'ETHUSD'}

_YF_TICKER = {
    'BTCUSD': 'BTC-USD',
    'ETHUSD': 'ETH-USD',
    'TSLA': 'TSLA',
    'GOOGL': 'GOOGL',
    'NVDA': 'NVDA',
    'AMZN': 'AMZN',
}

_CG_ID = {
    'BTCUSD': 'bitcoin',
    'ETHUSD': 'ethereum',
}

_CAMPOS_STOCK  = ['roe', 'margins', 'fcf_yield', 'rev_growth', 'earn_growth',
                  'forward_pe', 'ev_ebitda', 'debt_eq', 'short_pct', 'analyst']
_CAMPOS_CRYPTO = ['hash', 'vol_mcap', 'supply_ratio', 'mcap',
                  'momentum_7d', 'momentum_30d', 'fear_greed']

# Campos donde un valor más bajo es mejor (se invierten en score cross y en delta de tendencia)
_CAMPOS_INVERTIDOS = {'forward_pe', 'ev_ebitda', 'debt_eq', 'short_pct', 'supply_ratio'}

# Campos excluidos de tendencia (señales macro, no propias del activo)
_EXCLUIR_TENDENCIA = {'fear_greed'}

_DIAS_MIN_TENDENCIA = 7  # días mínimos de historia para activar score_tendencia


# ─── Normalización ────────────────────────────────────────────────────────────

def _to_float(v) -> float | None:
    """Convierte a float; retorna None si no es numérico o es inf/nan."""
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _minmax(values: list) -> list:
    """Min-max; None/str/inf → 0.5 (neutral). Con <2 valores válidos → todos 0.5."""
    floats = [_to_float(v) for v in values]
    valid = [v for v in floats if v is not None]
    if len(valid) < 2 or max(valid) == min(valid):
        return [0.5 for _ in floats]
    mn, mx = min(valid), max(valid)
    return [(v - mn) / (mx - mn) if v is not None else 0.5 for v in floats]


def _norm_field(field: str, universe: list, invert: bool = False) -> dict:
    """Min-max de `field` sobre el universo; retorna {_id: score_normalizado}."""
    keys = [d['_id'] for d in universe]
    vals = [d.get(field) for d in universe]
    normed = _minmax(vals)
    if invert:
        normed = [1.0 - v for v in normed]
    return dict(zip(keys, normed))


def _norm_sym(x) -> float:
    """tanh(x/50) escalado a [0,1]. Para cambios porcentuales con signo."""
    if x is None or not math.isfinite(x):
        return 0.5
    return (math.tanh(x / 50.0) + 1.0) / 2.0


# ─── Fetchers ─────────────────────────────────────────────────────────────────

def _get_stock_data(valor: str) -> dict:
    t = yf.Ticker(_YF_TICKER[valor])
    info = t.info

    fcf  = info.get('freeCashflow')
    mcap = info.get('marketCap')
    fcf_yield = (fcf / mcap) if (fcf and mcap and mcap > 0) else None

    analyst_score = None
    try:
        for attr in ('recommendations_summary', 'recommendations'):
            recs = getattr(t, attr, None)
            if recs is not None and not recs.empty:
                latest   = recs.iloc[-1]
                pos_cols = ['strongBuy', 'buy']
                all_cols = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
                total    = sum(float(latest[c]) for c in all_cols if c in latest.index)
                positive = sum(float(latest[c]) for c in pos_cols if c in latest.index)
                if total > 0:
                    analyst_score = positive / total
                break
    except Exception:
        pass

    return {
        '_id':        valor,
        'roe':        info.get('returnOnEquity'),
        'margins':    info.get('profitMargins'),
        'fcf_yield':  fcf_yield,
        'rev_growth': info.get('revenueGrowth'),
        'earn_growth':info.get('earningsGrowth'),
        'forward_pe': info.get('forwardPE'),
        'ev_ebitda':  info.get('enterpriseToEbitda'),
        'debt_eq':    info.get('debtToEquity'),
        'short_pct':  info.get('shortPercentOfFloat'),
        'analyst':    analyst_score,
    }


def _get_fear_greed() -> float | None:
    try:
        r = requests.get('https://api.alternative.me/fng/?limit=1', timeout=10)
        if r.status_code == 200:
            return int(r.json()['data'][0]['value'])
    except Exception:
        pass
    return None


def _get_crypto_data(valor: str, fear_greed: float | None) -> dict:
    t    = yf.Ticker(_YF_TICKER[valor])
    info = t.info

    cg = {}
    try:
        r = requests.get(
            'https://api.coingecko.com/api/v3/coins/markets',
            params={
                'vs_currency': 'usd',
                'ids': _CG_ID[valor],
                'price_change_percentage': '7d,30d',
            },
            timeout=10,
        )
        if r.status_code == 200:
            items = r.json()
            if items:
                cg = items[0]
    except Exception:
        pass

    mcap       = info.get('marketCap')       or cg.get('market_cap')
    vol24      = info.get('volume24Hr')      or cg.get('total_volume')
    circ       = info.get('circulatingSupply') or cg.get('circulating_supply')
    max_supply = info.get('maxSupply')       or cg.get('max_supply')

    vol_mcap     = (vol24 / mcap)         if (vol24 and mcap and mcap > 0)               else None
    supply_ratio = (circ / max_supply)    if (max_supply and circ and max_supply > 0)    else None

    return {
        '_id':          valor,
        'hash':         info.get('netHashesPerSecond'),
        'vol_mcap':     vol_mcap,
        'supply_ratio': supply_ratio,
        'mcap':         mcap,
        'momentum_7d':  cg.get('price_change_percentage_7d_in_currency'),
        'momentum_30d': cg.get('price_change_percentage_30d_in_currency'),
        'fear_greed':   fear_greed,
    }


# ─── Score cross-sectional (universo) ────────────────────────────────────────

def _score_stock(data: dict, universe: list, pesos: dict) -> dict:
    vid = data['_id']

    def n(field, invert=False):
        return _norm_field(field, universe, invert=invert)[vid]

    components = {
        'roe':        n('roe'),
        'margins':    n('margins'),
        'fcf_yield':  n('fcf_yield'),
        'rev_growth': n('rev_growth'),
        'earn_growth':n('earn_growth'),
        'forward_pe': n('forward_pe', invert=True),
        'ev_ebitda':  n('ev_ebitda',  invert=True),
        'debt_eq':    n('debt_eq',    invert=True),
        'short_pct':  n('short_pct',  invert=True),
        'analyst':    n('analyst'),
    }
    score = sum(pesos[k] * v for k, v in components.items() if k in pesos)
    return {'score_cross': round(score, 4),
            'components':  {k: round(v, 4) for k, v in components.items()}}


def _score_crypto(data: dict, universe: list, pesos: dict) -> dict:
    vid = data['_id']

    def n(field, invert=False):
        return _norm_field(field, universe, invert=invert)[vid]

    fg = data.get('fear_greed')
    components = {
        'hash':         n('hash'),
        'vol_mcap':     n('vol_mcap'),
        'supply':       n('supply_ratio', invert=True),
        'mcap':         n('mcap'),
        'momentum_7d':  _norm_sym(data.get('momentum_7d')),
        'momentum_30d': _norm_sym(data.get('momentum_30d')),
        'fear_greed':   (fg / 100.0) if fg is not None else 0.5,
    }
    score = sum(pesos[k] * v for k, v in components.items() if k in pesos)
    return {'score_cross': round(score, 4),
            'components':  {k: round(v, 4) for k, v in components.items()}}


# ─── Score de tendencia (longitudinal) ───────────────────────────────────────

def _score_tendencia(valor: str, raw_hoy: dict, historia: list, dias: int) -> float:
    """
    Mide cómo evolucionaron los fundamentales del activo respecto a sí mismo
    en los últimos `dias` días. Retorna 0.5 si no hay historia suficiente.

    Para cada campo: delta_pct = (hoy - ref) / |ref| × 100.
    Campos invertidos (menor = mejor): el delta se niega antes de normalizar.
    Normalización: _norm_sym(delta_pct) — tanh centrado en 0%, output [0,1].
    """
    hoy = date.today()

    entradas = sorted(
        [e for e in historia if e.get('activo') == valor and e.get('raw')],
        key=lambda e: e['date'],
    )
    if not entradas:
        return 0.5

    mas_antigua = date.fromisoformat(entradas[0]['date'])
    dias_disp   = (hoy - mas_antigua).days
    if dias_disp < _DIAS_MIN_TENDENCIA:
        return 0.5

    # Entrada más cercana a (hoy - dias), sin sobrepasar hoy
    fecha_obj = hoy - timedelta(days=min(dias, dias_disp))
    ref_entry = min(
        entradas,
        key=lambda e: abs((date.fromisoformat(e['date']) - fecha_obj).days),
    )
    raw_ref = ref_entry['raw']

    campos = _CAMPOS_CRYPTO if valor in _CRYPTO else _CAMPOS_STOCK
    deltas = []
    for campo in campos:
        if campo in _EXCLUIR_TENDENCIA:
            continue
        v_hoy = _to_float(raw_hoy.get(campo))
        v_ref = _to_float(raw_ref.get(campo))
        if v_hoy is None or v_ref is None or v_ref == 0:
            continue
        delta_pct = (v_hoy - v_ref) / abs(v_ref) * 100.0
        if campo in _CAMPOS_INVERTIDOS:
            delta_pct = -delta_pct
        deltas.append(_norm_sym(delta_pct))

    return round(sum(deltas) / len(deltas), 4) if deltas else 0.5


# ─── Validadores de consistencia ─────────────────────────────────────────────

def _validar_datos(data: dict, es_crypto: bool) -> list:
    """Comprueba completitud de los datos crudos."""
    campos_check = [c for c in (_CAMPOS_CRYPTO if es_crypto else _CAMPOS_STOCK)
                    if c != 'analyst']
    nulos  = [c for c in campos_check if data.get(c) is None]
    avisos = []
    if nulos:
        avisos.append(f"campos nulos ({len(nulos)}/{len(campos_check)}): {', '.join(nulos)}")
    if len(nulos) > len(campos_check) // 2:
        avisos.append("ADVERTENCIA — más del 50% de campos sin datos (posible fallo de API)")
    return avisos


def _validar_score(result: dict) -> list:
    """Comprueba que el score resultante no sea sospechoso."""
    avisos = []
    score  = result['score']
    comps  = result['components']

    if score <= 0.05:
        en_min = [k for k, v in comps.items() if v <= 0.05]
        avisos.append(f"score muy bajo ({score:.3f}) — mínimo del universo: {', '.join(en_min)}")
    elif score >= 0.95:
        en_max = [k for k, v in comps.items() if v >= 0.95]
        avisos.append(f"score muy alto ({score:.3f}) — máximo del universo: {', '.join(en_max)}")

    neutros = [k for k, v in comps.items() if abs(v - 0.5) < 0.02]
    if len(neutros) > len(comps) * 0.6:
        avisos.append(
            f"{len(neutros)}/{len(comps)} componentes neutros (0.5) — posible fallo de API o empate"
        )
    return avisos


def _imprimir_datos_crudos(universe: list, es_crypto: bool):
    """Tabla de valores crudos (pre-normalización) para diagnóstico."""
    campos = _CAMPOS_CRYPTO if es_crypto else _CAMPOS_STOCK
    col_w  = 14
    header = f"{'Campo':<15}" + ''.join(f"{d['_id']:>{col_w}}" for d in universe)
    print(header)
    print('-' * len(header))
    for campo in campos:
        vals = []
        for d in universe:
            v = d.get(campo)
            if v is None:
                vals.append('None')
            elif isinstance(v, float):
                vals.append(f'{v:.4g}')
            else:
                vals.append(str(v))
        print(f"{campo:<15}" + ''.join(f"{v:>{col_w}}" for v in vals))
    print()


# ─── Orquestación ─────────────────────────────────────────────────────────────

def _cargar_pesos_override(default_stock: dict, default_crypto: dict) -> tuple:
    """Lee overrides de pesos desde config/active_parameters.json si existen."""
    path = BASE_DIR / 'config' / 'active_parameters.json'
    if not path.exists():
        return default_stock, default_crypto
    try:
        params = json.loads(path.read_text())
        return (params.get('PESOS_STOCK', default_stock),
                params.get('PESOS_CRYPTO', default_crypto))
    except Exception:
        return default_stock, default_crypto


def _cargar_historial(carpeta: Path) -> list:
    path = carpeta / 'x2_history.json'
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def calcular_scores(
    valores: list,
    pesos_stock: dict,
    pesos_crypto: dict,
    w_tendencia: float,
    dias_tendencia: int,
    carpeta: Path,
) -> tuple:
    """Retorna (scores, raw_data)."""
    stocks  = [v for v in valores if v not in _CRYPTO]
    cryptos = [v for v in valores if v in _CRYPTO]

    print('Descargando datos fundamentales...')

    stock_universe = []
    for v in stocks:
        print(f'  {v}...', end=' ', flush=True)
        try:
            d      = _get_stock_data(v)
            avisos = _validar_datos(d, es_crypto=False)
            print('OK' + (f' [{"; ".join(avisos)}]' if avisos else ''))
        except Exception as e:
            print(f'ERROR ({e})')
            d = {'_id': v}
        stock_universe.append(d)

    fear_greed = _get_fear_greed()
    print(f'  Fear & Greed Index: {fear_greed}')

    crypto_universe = []
    for v in cryptos:
        print(f'  {v}...', end=' ', flush=True)
        try:
            d      = _get_crypto_data(v, fear_greed)
            avisos = _validar_datos(d, es_crypto=True)
            print('OK' + (f' [{"; ".join(avisos)}]' if avisos else ''))
        except Exception as e:
            print(f'ERROR ({e})')
            d = {'_id': v}
        crypto_universe.append(d)

    # Historia previa (sin la entrada de hoy — aún no guardada)
    historia = _cargar_historial(carpeta)

    ts       = datetime.now().isoformat(timespec='seconds')
    scores   = {}
    raw_data = {}
    avisos_score = []

    for data in stock_universe:
        v     = data['_id']
        cross = _score_stock(data, stock_universe, pesos_stock)
        tend  = _score_tendencia(v, data, historia, dias_tendencia)
        score_final = (1 - w_tendencia) * cross['score_cross'] + w_tendencia * tend
        result = {
            'score':           round(score_final, 4),
            'score_cross':     cross['score_cross'],
            'score_tendencia': tend,
            'components':      cross['components'],
            'ts':              ts,
        }
        scores[v]   = result
        raw_data[v] = {k: data.get(k) for k in _CAMPOS_STOCK}
        for a in _validar_score(result):
            avisos_score.append(f'  {v}: {a}')

    for data in crypto_universe:
        v     = data['_id']
        cross = _score_crypto(data, crypto_universe, pesos_crypto)
        tend  = _score_tendencia(v, data, historia, dias_tendencia)
        score_final = (1 - w_tendencia) * cross['score_cross'] + w_tendencia * tend
        result = {
            'score':           round(score_final, 4),
            'score_cross':     cross['score_cross'],
            'score_tendencia': tend,
            'components':      cross['components'],
            'ts':              ts,
        }
        scores[v]   = result
        raw_data[v] = {k: data.get(k) for k in _CAMPOS_CRYPTO}
        for a in _validar_score(result):
            avisos_score.append(f'  {v}: {a}')

    if avisos_score:
        print('\nAvisos de score:')
        for a in avisos_score:
            print(a)

    print('\nDatos crudos — acciones:')
    _imprimir_datos_crudos(stock_universe, es_crypto=False)
    print('Datos crudos — crypto:')
    _imprimir_datos_crudos(crypto_universe, es_crypto=True)

    return scores, raw_data


# ─── Persistencia ─────────────────────────────────────────────────────────────

def guardar_scores(scores: dict, carpeta: Path):
    carpeta.mkdir(parents=True, exist_ok=True)
    # _metadata permite a X6 verificar antigüedad sin calcularla
    payload = {
        '_metadata': {'ultima_ejecucion': date.today().isoformat()},
        **scores,
    }
    path = carpeta / 'scores.json'
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f'scores.json → {path}')


def guardar_historial(scores: dict, raw_data: dict, carpeta: Path):
    """Upsert por (fecha, activo) en x2_history.json. Incluye raw values para tendencia."""
    path    = carpeta / 'x2_history.json'
    historia = []
    if path.exists():
        try:
            historia = json.loads(path.read_text())
        except Exception:
            historia = []

    hoy      = date.today().isoformat()
    historia = [
        e for e in historia
        if not (e.get('date') == hoy and e.get('activo') in scores)
    ]

    for activo, data in scores.items():
        historia.append({
            'date':            hoy,
            'activo':          activo,
            'score':           data['score'],
            'score_cross':     data['score_cross'],
            'score_tendencia': data['score_tendencia'],
            'components':      data['components'],
            'raw':             raw_data.get(activo, {}),
        })

    path.write_text(json.dumps(historia, indent=2, ensure_ascii=False))
    print(f'x2_history.json → {path} ({len(historia)} entradas totales)')


def _ya_ejecutado_hoy(carpeta: Path) -> bool:
    path = carpeta / 'x2_last_run.json'
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text()).get('fecha') == date.today().isoformat()
    except Exception:
        return False


def _dias_desde_ultima_ejecucion(carpeta: Path) -> int | None:
    """Días transcurridos desde la última ejecución exitosa. None si nunca se ejecutó."""
    path = carpeta / 'x2_last_run.json'
    if not path.exists():
        return None
    try:
        ultima = date.fromisoformat(json.loads(path.read_text())['fecha'])
        return (date.today() - ultima).days
    except Exception:
        return None


def _marcar_ejecutado(carpeta: Path):
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / 'x2_last_run.json').write_text(
        json.dumps({'fecha': date.today().isoformat()})
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    t0 = time.time()

    parser = argparse.ArgumentParser()
    parser.add_argument('--forzar', action='store_true',
                        help='Re-ejecuta aunque ya se haya corrido hoy')
    args = parser.parse_args()

    if not args.forzar and _ya_ejecutado_hoy(CARPETA_FUNDAMENTALS):
        print('X2 ya ejecutado hoy. Usando scores.json existente.')
        path = CARPETA_FUNDAMENTALS / 'scores.json'
        if path.exists():
            data   = json.loads(path.read_text())
            scores = {k: v for k, v in data.items() if not k.startswith('_')}
            print(f"\n{'Activo':<8}  {'Score':>6}  {'Cross':>6}  {'Tend':>8}")
            print('-' * 36)
            for v in VALORES:
                if v in scores:
                    s    = scores[v]
                    tend = s.get('score_tendencia', 'n/d')
                    tend_str = f'{tend:.4f}' if isinstance(tend, float) else str(tend)
                    print(f"{v:<8}  {s['score']:>6.4f}  {s.get('score_cross', '-'):>6}  {tend_str:>8}")
        elapsed = time.time() - t0
        print(f'\nX2 completado en {elapsed:.1f}s')
        sys.exit(0)

    # Aviso si se saltó algún día
    dias = _dias_desde_ultima_ejecucion(CARPETA_FUNDAMENTALS)
    if dias is not None and dias > 1:
        print(f'ADVERTENCIA: última ejecución hace {dias} día(s) — puede haber gaps en el historial.')

    pesos_stock, pesos_crypto = _cargar_pesos_override(PESOS_STOCK, PESOS_CRYPTO)

    scores, raw_data = calcular_scores(
        VALORES, pesos_stock, pesos_crypto,
        W_TENDENCIA, DIAS_TENDENCIA, CARPETA_FUNDAMENTALS,
    )
    guardar_scores(scores, CARPETA_FUNDAMENTALS)
    guardar_historial(scores, raw_data, CARPETA_FUNDAMENTALS)
    _marcar_ejecutado(CARPETA_FUNDAMENTALS)

    print(f"\n{'Activo':<8}  {'Score':>6}  {'Cross':>6}  {'Tend':>8}  Componentes principales")
    print('-' * 78)
    for v in VALORES:
        if v in scores:
            s        = scores[v]
            comps    = '  '.join(f"{k}={val:.2f}" for k, val in list(s['components'].items())[:3])
            tend     = s['score_tendencia']
            tend_str = f'{tend:.4f}' if tend != 0.5 else '0.5(n/d)'
            print(f"{v:<8}  {s['score']:>6.4f}  {s['score_cross']:>6.4f}  {tend_str:>8}  {comps}")

    elapsed = time.time() - t0
    print(f'\nX2 completado en {elapsed:.1f}s')
