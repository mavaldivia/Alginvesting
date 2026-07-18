
"""
X4_backtester.py

Simula la estrategia completa (X0 + lógica de X1) sobre datos históricos,
avanzando vela H1 a vela H1. Recalcula soportes periódicamente, gestiona
un libro de órdenes en memoria, y registra cada trade cerrado en trades.json.

Uso:
  python scripts/X4_backtester.py                     # usa X4_VERSION_ACTIVA de config.py
  python scripts/X4_backtester.py --version V1
  python scripts/X4_backtester.py --version V1 --reset
"""

import argparse
import csv
import importlib.util
import json
import random
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from X0_data_supports import _procesar_valor_N, _bt_warm_start
from X3_technical_features import compute_snapshot


# ─── Config ───────────────────────────────────────────────────────────────────

def _cargar_config(version: str):
    base_dir = Path(__file__).parent.parent
    config_path = base_dir / 'resources' / 'x4' / f'version{version}' / f'config_{version}.py'
    if not config_path.exists():
        raise FileNotFoundError(f'Config no encontrada: {config_path}')
    spec = importlib.util.spec_from_file_location(f'config_{version}', config_path)
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return cfg


# ─── Carga de datos ───────────────────────────────────────────────────────────

def _cargar_datos_h1(cfg) -> dict:
    datos = {}
    for activo in cfg.valores:
        csv_path = cfg.CARPETA_DATA / f'{activo}.csv'
        if not csv_path.exists():
            print(f'  Advertencia: sin datos H1 para {activo} en {csv_path}, skip.')
            continue
        df = pd.read_csv(csv_path)
        df['DateTime'] = pd.to_datetime(df['DateTime'])
        df = (df.sort_values('DateTime')
                .drop_duplicates(subset=['DateTime'])
                .reset_index(drop=True))
        df = df[df['DateTime'] >= pd.Timestamp(cfg.fecha_inicio)].reset_index(drop=True)
        if len(df) == 0:
            print(f'  Advertencia: sin datos desde {cfg.fecha_inicio} para {activo}, skip.')
            continue
        print(f'  {activo}: {len(df)} velas H1 ({df["DateTime"].iloc[0]} → {df["DateTime"].iloc[-1]})')
        datos[activo] = df.set_index('DateTime')
    return datos


def _cargar_datos_m1(cfg) -> dict:
    datos = {}
    for activo in cfg.valores:
        csv_path = cfg.CARPETA_DATA_MINUTO / f'{activo}.csv'
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df['DateTime'] = pd.to_datetime(df['DateTime'])
            df = (df.sort_values('DateTime')
                    .drop_duplicates(subset=['DateTime'])
                    .reset_index(drop=True))
            datos[activo] = df.reset_index(drop=True)
        else:
            datos[activo] = None
    return datos


# ─── Checkpoint ───────────────────────────────────────────────────────────────

def _cargar_checkpoint(cfg) -> dict | None:
    ckpt_path = cfg.CARPETA_RESOURCES / 'checkpoint.json'
    if not ckpt_path.exists():
        return None
    with open(ckpt_path) as f:
        ckpt = json.load(f)
    for est_a in ckpt['por_activo'].values():
        est_a['OE'] = {float(k): v for k, v in est_a['OE'].items()}
        est_a['OA'] = {float(k): v for k, v in est_a['OA'].items()}
    print(f'  Checkpoint cargado: capital={ckpt["capital"]:.2f}, ts={ckpt["ts_ultimo_procesado"]}')
    return ckpt


def _guardar_checkpoint(estado: dict, cfg):
    cfg.CARPETA_RESOURCES.mkdir(parents=True, exist_ok=True)
    ckpt = {
        'version': cfg.version,
        'ts_ultimo_procesado': estado['ts_ultimo_procesado'],
        'ts_ultimo_recalculo': estado['ts_ultimo_recalculo'],
        'capital': estado['capital'],
        'por_activo': {
            activo: {
                'soportes': sorted(est_a['soportes']),
                'OE': {str(k): v for k, v in est_a['OE'].items()},
                'OA': {str(k): v for k, v in est_a['OA'].items()},
                'GC': est_a['GC'],
            }
            for activo, est_a in estado['por_activo'].items()
        },
    }
    with open(cfg.CARPETA_RESOURCES / 'checkpoint.json', 'w') as f:
        json.dump(ckpt, f, indent=2, default=str)


# ─── Recálculo de soportes ────────────────────────────────────────────────────

def _worker_recalcular(args):
    activo, N, carpeta_data, carpeta_n_prod, carpeta_n_bt, ts_actual, oa_bt = args
    _procesar_valor_N(
        activo, N,
        carpeta_data,
        carpeta_n_prod,
        carpeta_n_bt,
        [],          # ordenes_activas MT5 — vacío en bt
        ts_actual,   # fecha_hora_max → activa modo bt
        None,        # estado_compartido
        False,       # verbose
        oa_bt,       # ordenes_abiertas_bt
    )


def _recalcular_soportes(estado: dict, ts_actual, cfg):
    carpeta_n_prod = Path(__file__).parent.parent / 'resources' / 'conjuntos_N'
    tasks = []
    for activo in cfg.valores:
        if activo not in estado['por_activo']:
            continue
        N = cfg.n_sizes[activo]
        oa_bt = list(estado['por_activo'][activo]['OA'].keys())
        tasks.append((activo, N, cfg.CARPETA_DATA, carpeta_n_prod, cfg.CARPETA_N_BT, ts_actual, oa_bt))

    n_workers = min(len(tasks), 4)
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        list(executor.map(_worker_recalcular, tasks))

    # Cargar soportes recalculados desde cache bt
    for activo in cfg.valores:
        N = cfg.n_sizes[activo]
        nuevos = _bt_warm_start(cfg.CARPETA_N_BT, activo, N, ts_actual)
        if nuevos:
            estado['por_activo'][activo]['soportes'] = sorted(nuevos)
        elif not estado['por_activo'][activo]['soportes']:
            print(f'  Advertencia: sin soportes para {activo} tras recálculo.')

    estado['ts_ultimo_recalculo'] = ts_actual.isoformat()


# ─── Métricas de cuenta ───────────────────────────────────────────────────────

def _calcular_estado_cuenta(estado: dict, precios_cierre: dict, cfg) -> dict:
    balance = estado['capital']
    GA_global = 0.0
    margen_usado = 0.0
    n_OA = n_OE = 0

    for activo, est_a in estado['por_activo'].items():
        lote = cfg.LOTAJES[activo]
        units = cfg.UNITS[activo]
        apal = cfg.APALANCAMIENTO[activo]
        precio_actual = precios_cierre.get(activo, 0.0)
        for precio_ap in est_a['OA']:
            GA_global += (precio_actual - precio_ap) * lote * units
            margen_usado += precio_ap * lote * units / apal
            n_OA += 1
        n_OE += len(est_a['OE'])

    equity = balance + GA_global
    margen_libre = equity - margen_usado
    margin_level = (equity / margen_usado * 100) if margen_usado > 0 else None
    return {
        'balance': balance, 'equity': equity,
        'margen_usado': margen_usado, 'margen_libre': margen_libre,
        'margin_level': margin_level, 'n_OA': n_OA, 'n_OE': n_OE,
    }


def _calcular_GA(est_a: dict, precio_actual: float, lote: float, units: int) -> float:
    return sum((precio_actual - p) * lote * units for p in est_a['OA'])


# ─── Eventos y trades ─────────────────────────────────────────────────────────

def _evt(tipo: str, activo: str, ts, cfg, usa_intravela: bool = False, **kwargs) -> dict:
    e = {
        'ts': ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
        'version': cfg.version, 'activo': activo,
        'tipo': tipo, 'usa_intravela': usa_intravela,
    }
    e.update(kwargs)
    return e


def _registrar_trade(pos: dict, precio_ap: float, precio_cierre: float,
                     motivo: str, ts_cierre, activo: str, N: int,
                     capital_estado: float, cfg) -> dict:
    # Usa el capital al momento de apertura si está disponible, si no el actual
    capital = pos.get('capital_apertura', capital_estado)
    lote = cfg.LOTAJES[activo]
    units = cfg.UNITS[activo]
    L = lote * units
    retorno_usd = (precio_cierre - precio_ap) * L
    ts_ap = pd.Timestamp(pos['ts_apertura'])
    trade_id = f"{activo}_{ts_ap.strftime('%Y%m%dT%H%M')}_{precio_ap:.1f}"
    return {
        'id': trade_id,
        'version': cfg.version,
        'activo': activo,
        'N': N,
        'soporte_nivel': precio_ap,
        'timestamp_apertura': pos['ts_apertura'],
        'precio_apertura': precio_ap,
        'lote': lote, 'L': L,
        'timestamp_cierre': ts_cierre.isoformat(),
        'precio_cierre': precio_cierre,
        'motivo_cierre': motivo,
        'retorno_usd': round(retorno_usd, 4),
        'retorno_pct': round(retorno_usd / capital, 6) if capital > 0 else 0.0,
        'duracion_velas_h1': pos.get('duracion_velas', 0),
        'drawdown_max_usd': round(pos.get('drawdown_max', 0.0), 4),
        'ganancia_flotante_max_usd': round(pos.get('ganancia_max', 0.0), 4),
        'capital_cuenta_apertura': round(capital, 2),
        'usa_intravela': pos.get('usa_intravela', False),
        'parametros': {
            'A': cfg.A, 'B': cfg.B, 'PERDIDA_MAX': cfg.PERDIDA_MAX_BT,
            'N': N, 'K': cfg.K, 'LAMBDA': cfg.LAMBDA, 'N_EXP': cfg.N_EXP,
            'LOTAJE': lote, 'UNITS': units,
        },
        'features_x2': None,
        'features_x3': None,
    }


# ─── Pasos A → F ──────────────────────────────────────────────────────────────

def _paso_A(est_a: dict, activo: str, ts, cfg, events: list, usa_iv: bool = False):
    """Cancela OE cuyo soporte ya no está en la lista actual."""
    soportes_set = set(est_a['soportes'])
    a_eliminar = [p for p in list(est_a['OE'].keys()) if p not in soportes_set]
    for precio in a_eliminar:
        events.append(_evt('OE_eliminada', activo, ts, cfg, usa_iv, precio=precio, motivo='soporte_desactivado'))
        del est_a['OE'][precio]


def _margen_libre_actual(estado: dict, precios: dict, cfg, extra_usado: float = 0.0) -> float:
    mc = _calcular_estado_cuenta(estado, precios, cfg)
    return mc['margen_libre'] - extra_usado


def _paso_B(est_a: dict, candle, activo: str, ts, estado: dict, precios: dict,
            capital_ap: float, cfg, events: list, trades: list, usa_iv: bool = False,
            x5_ctx=None):
    """Ejecuta OE. Detecta gap de mercado."""
    lote = cfg.LOTAJES[activo]
    units = cfg.UNITS[activo]
    apal = cfg.APALANCAMIENTO[activo]
    N = cfg.n_sizes[activo]

    # Detectar gap: OEs con precio >= Open
    oes_gap = sorted([p for p in est_a['OE'] if p >= candle['Open']])
    if oes_gap:
        precio_gap = min(oes_gap)
        for precio_oe in oes_gap:
            if precio_oe not in est_a['OE']:
                continue
            margen_nueva = precio_gap * lote * units / apal
            if _margen_libre_actual(estado, precios, cfg) - margen_nueva < cfg.MARGEN_LIBRE_MIN_BT:
                events.append(_evt('OE_eliminada', activo, ts, cfg, usa_iv,
                                   precio=precio_oe, motivo='margen_insuficiente'))
                del est_a['OE'][precio_oe]
                continue
            _oe_d = est_a['OE'].pop(precio_oe)
            ts_creacion = _oe_d.get('ts_creacion', ts.isoformat())
            _oa_entry = {
                'lote': lote, 'sl': 0,
                'ts_apertura': ts.isoformat(),
                'capital_apertura': estado['capital'],
                'ganancia_max': 0.0, 'drawdown_max': 0.0,
                'usa_intravela': usa_iv, 'duracion_velas': 0,
            }
            if x5_ctx is not None:
                _oa_entry['ts_oe_creacion'] = ts_creacion
                _oa_entry['x3_oe'] = _oe_d.get('x3_oe', {})
                _oa_entry['x2_oe'] = _oe_d.get('x2_oe', {})
                _oa_entry['x3_oa'] = x5_ctx['x3']
                _oa_entry['x2_oa'] = x5_ctx['x2']
            est_a['OA'][precio_gap] = _oa_entry
            events.append(_evt('OE_ejecutada', activo, ts, cfg, usa_iv,
                               precio=precio_oe, precio_ejecucion=precio_gap,
                               lote=lote, ts_oe_creacion=ts_creacion, es_gap=True))

    # Caso normal: OEs por debajo del Open
    for precio_oe in sorted([p for p in list(est_a['OE'].keys()) if p < candle['Open']]):
        if precio_oe not in est_a['OE']:
            continue
        if candle['Low'] <= precio_oe:
            margen_nueva = precio_oe * lote * units / apal
            if _margen_libre_actual(estado, precios, cfg) - margen_nueva < cfg.MARGEN_LIBRE_MIN_BT:
                events.append(_evt('OE_eliminada', activo, ts, cfg, usa_iv,
                                   precio=precio_oe, motivo='margen_insuficiente'))
                del est_a['OE'][precio_oe]
                continue
            _oe_d = est_a['OE'].pop(precio_oe)
            ts_creacion = _oe_d.get('ts_creacion', ts.isoformat())
            _oa_entry = {
                'lote': lote, 'sl': 0,
                'ts_apertura': ts.isoformat(),
                'capital_apertura': estado['capital'],
                'ganancia_max': 0.0, 'drawdown_max': 0.0,
                'usa_intravela': usa_iv, 'duracion_velas': 0,
            }
            if x5_ctx is not None:
                _oa_entry['ts_oe_creacion'] = ts_creacion
                _oa_entry['x3_oe'] = _oe_d.get('x3_oe', {})
                _oa_entry['x2_oe'] = _oe_d.get('x2_oe', {})
                _oa_entry['x3_oa'] = x5_ctx['x3']
                _oa_entry['x2_oa'] = x5_ctx['x2']
            est_a['OA'][precio_oe] = _oa_entry
            events.append(_evt('OE_ejecutada', activo, ts, cfg, usa_iv,
                               precio=precio_oe, precio_ejecucion=precio_oe,
                               lote=lote, ts_oe_creacion=ts_creacion, es_gap=False))


def _paso_C(est_a: dict, precio_max: float, activo: str, ts, cfg, events: list, usa_iv: bool = False):
    """Trailing stop: actualiza SL cuando la posición alcanza ganancia suficiente."""
    lote = cfg.LOTAJES[activo]
    units = cfg.UNITS[activo]
    L = lote * units

    for precio_ap, pos in est_a['OA'].items():
        ga_flotante = (precio_max - precio_ap) * L
        pos['ganancia_max'] = max(pos.get('ganancia_max', 0.0), ga_flotante)

        sl = pos['sl']
        if sl == 0:
            if ga_flotante >= cfg.A:
                sl_nuevo = precio_max - cfg.B / L
                pos['sl'] = sl_nuevo
                # Reponer OE en el nivel de apertura
                if precio_ap not in est_a['OE']:
                    est_a['OE'][precio_ap] = {'lote': lote, 'ts_creacion': ts.isoformat()}
                events.append(_evt('SL_cambiado', activo, ts, cfg, usa_iv,
                                   precio_apertura=precio_ap, sl_anterior=0,
                                   sl_nuevo=sl_nuevo, precio_max_vela=precio_max))
        else:
            sl_nuevo = precio_max - cfg.B / L
            if sl_nuevo > sl:
                pos['sl'] = sl_nuevo
                events.append(_evt('SL_cambiado', activo, ts, cfg, usa_iv,
                                   precio_apertura=precio_ap, sl_anterior=sl,
                                   sl_nuevo=sl_nuevo, precio_max_vela=precio_max))


def _paso_D(est_a: dict, precio_min: float, activo: str, ts, estado: dict,
            capital_ap: float, N: int, cfg, events: list, trades: list, usa_iv: bool = False,
            x5_ctx=None):
    """Cierra posiciones cuya pérdida supera PERDIDA_MAX_BT."""
    lote = cfg.LOTAJES[activo]
    units = cfg.UNITS[activo]
    L = lote * units

    a_cerrar = [p for p, pos in est_a['OA'].items()
                if (p - precio_min) * L > cfg.PERDIDA_MAX_BT]
    for precio_ap in a_cerrar:
        pos = est_a['OA'].pop(precio_ap)
        # Actualizar drawdown_max
        dd = (precio_min - precio_ap) * L
        pos['drawdown_max'] = min(pos.get('drawdown_max', 0.0), dd)
        precio_cierre = precio_min
        retorno_usd = (precio_cierre - precio_ap) * L
        estado['capital'] += retorno_usd
        estado['por_activo'][activo]['GC'] += retorno_usd
        _trade = _registrar_trade(pos, precio_ap, precio_cierre, 'perdida_max',
                                  ts, activo, N, capital_ap, cfg)
        trades.append(_trade)
        if x5_ctx is not None and not usa_iv:
            _fila = _construir_fila_oc(activo, pos, _trade, ts, est_a,
                                        precio_cierre, cfg, x5_ctx['min_lotajes'])
            _append_x5_store(activo, _fila)
            est_a.setdefault('oc_recientes', []).append(_trade['retorno_pct'])
        events.append(_evt('posicion_cerrada', activo, ts, cfg, usa_iv,
                           precio_apertura=precio_ap, precio_cierre=precio_cierre,
                           motivo='perdida_max', retorno_usd=round(retorno_usd, 4), lote=lote))


def _paso_E(est_a: dict, precio_min: float, activo: str, ts, estado: dict,
            capital_ap: float, N: int, cfg, events: list, trades: list, usa_iv: bool = False,
            x5_ctx=None):
    """Cierra posiciones cuyo SL fue tocado."""
    lote = cfg.LOTAJES[activo]
    units = cfg.UNITS[activo]
    L = lote * units

    a_cerrar = [p for p, pos in est_a['OA'].items()
                if pos['sl'] > 0 and precio_min <= pos['sl']]
    for precio_ap in a_cerrar:
        pos = est_a['OA'].pop(precio_ap)
        dd = (precio_min - precio_ap) * L
        pos['drawdown_max'] = min(pos.get('drawdown_max', 0.0), dd)
        precio_cierre = pos['sl']
        retorno_usd = (precio_cierre - precio_ap) * L
        estado['capital'] += retorno_usd
        estado['por_activo'][activo]['GC'] += retorno_usd
        _trade = _registrar_trade(pos, precio_ap, precio_cierre, 'trailing_stop',
                                  ts, activo, N, capital_ap, cfg)
        trades.append(_trade)
        if x5_ctx is not None and not usa_iv:
            _fila = _construir_fila_oc(activo, pos, _trade, ts, est_a,
                                        precio_cierre, cfg, x5_ctx['min_lotajes'])
            _append_x5_store(activo, _fila)
            est_a.setdefault('oc_recientes', []).append(_trade['retorno_pct'])
        events.append(_evt('posicion_cerrada', activo, ts, cfg, usa_iv,
                           precio_apertura=precio_ap, precio_cierre=precio_cierre,
                           motivo='trailing_stop', retorno_usd=round(retorno_usd, 4), lote=lote))


def _paso_F(est_a: dict, precio_ref: float, activo: str, ts, estado: dict,
            precios: dict, cfg, events: list, usa_iv: bool = False, x5_ctx=None):
    """Crea OE en soportes con distancia suficiente, respetando el guard de margen."""
    lote = cfg.LOTAJES[activo]
    units = cfg.UNITS[activo]
    apal = cfg.APALANCAMIENTO[activo]
    L = lote * units
    margen_comprometido = 0.0  # margen reservado dentro de este ciclo por nuevas OE

    for soporte in sorted(est_a['soportes'], reverse=True):
        if soporte in est_a['OA'] or soporte in est_a['OE']:
            continue
        if (precio_ref - soporte) * L < cfg.A:
            continue
        margen_nueva = soporte * lote * units / apal
        if (_margen_libre_actual(estado, precios, cfg, margen_comprometido) - margen_nueva
                < cfg.MARGEN_LIBRE_MIN_BT):
            continue
        margen_comprometido += margen_nueva
        _oe_entry = {'lote': lote, 'ts_creacion': ts.isoformat()}
        if x5_ctx is not None:
            _oe_entry['x3_oe'] = x5_ctx['x3']
            _oe_entry['x2_oe'] = x5_ctx['x2']
        est_a['OE'][soporte] = _oe_entry
        events.append(_evt('OE_creada', activo, ts, cfg, usa_iv, precio=soporte, lote=lote))


# ─── Intra-vela ───────────────────────────────────────────────────────────────

def _necesita_intravela(est_a: dict, candle, L: float, cfg) -> bool:
    rango = candle['High'] - candle['Low']
    for precio_ap, pos in est_a['OA'].items():
        sl = pos['sl']
        if sl == 0:
            if rango * L >= cfg.A and (precio_ap - candle['Low']) * L >= cfg.PERDIDA_MAX_BT:
                return True
        else:
            sl_nuevo = candle['High'] - cfg.B / L
            if sl_nuevo > sl and candle['Low'] <= sl_nuevo:
                return True
    for precio_oe in est_a['OE']:
        if candle['Low'] <= precio_oe:
            if rango * L >= cfg.A or (precio_oe - candle['Low']) * L >= cfg.PERDIDA_MAX_BT:
                return True
    return False


def _escalar_bloque_m1(bloque_raw: pd.DataFrame, candle_h1) -> pd.DataFrame:
    bloque = bloque_raw[['Open', 'High', 'Low', 'Close']].copy().reset_index(drop=True)
    orig_high = bloque['High'].max()
    orig_low = bloque['Low'].min()
    h1_high = candle_h1['High']
    h1_low = candle_h1['Low']
    h1_open = candle_h1['Open']
    h1_close = candle_h1['Close']

    orig_rango = orig_high - orig_low
    h1_rango = h1_high - h1_low

    if orig_rango == 0 or h1_rango == 0:
        for col in ['Open', 'High', 'Low', 'Close']:
            bloque[col] = h1_close
        return bloque

    scale = h1_rango / orig_rango
    for col in ['Open', 'High', 'Low', 'Close']:
        bloque[col] = h1_low + (bloque[col] - orig_low) * scale

    bloque.loc[0, 'Open'] = h1_open
    bloque.loc[len(bloque) - 1, 'Close'] = h1_close
    return bloque


def _simular_intravela(est_a: dict, candle_h1, activo: str, ts, estado: dict,
                        precios: dict, capital_ap: float, N: int, datos_m1,
                        cfg, events: list, trades: list):
    if datos_m1 is None or len(datos_m1) < 60:
        return

    t = random.randint(0, len(datos_m1) - 60)
    bloque = _escalar_bloque_m1(datos_m1.iloc[t: t + 60], candle_h1)

    for _, vela_m1 in bloque.iterrows():
        _paso_B(est_a, vela_m1, activo, ts, estado, precios, capital_ap, cfg, events, trades, usa_iv=True)
        _paso_C(est_a, vela_m1['High'], activo, ts, cfg, events, usa_iv=True)
        _paso_D(est_a, vela_m1['Low'], activo, ts, estado, capital_ap, N, cfg, events, trades, usa_iv=True)
        _paso_E(est_a, vela_m1['Low'], activo, ts, estado, capital_ap, N, cfg, events, trades, usa_iv=True)
        _paso_F(est_a, vela_m1['Close'], activo, ts, estado, precios, cfg, events, usa_iv=True)


# ─── Procesamiento por vela ───────────────────────────────────────────────────

def _procesar_candle(ts, candle, activo: str, est_a: dict, estado: dict,
                     datos_m1, precios: dict, N: int,
                     cfg, events: list, trades: list, x5_ctx=None):
    lote = cfg.LOTAJES[activo]
    units = cfg.UNITS[activo]
    L = lote * units
    capital_ap = estado['capital']

    # Actualizar contadores por vela (duracion y drawdown flotante)
    for precio_ap, pos in est_a['OA'].items():
        pos['duracion_velas'] = pos.get('duracion_velas', 0) + 1
        dd_flotante = (candle['Low'] - precio_ap) * L
        pos['drawdown_max'] = min(pos.get('drawdown_max', 0.0), dd_flotante)

    # Paso A: siempre primero
    _paso_A(est_a, activo, ts, cfg, events)

    usar_iv = _necesita_intravela(est_a, candle, L, cfg)

    if usar_iv and datos_m1 is not None and len(datos_m1) >= 60:
        _simular_intravela(est_a, candle, activo, ts, estado, precios, capital_ap, N, datos_m1, cfg, events, trades)
    else:
        if usar_iv:
            print(f'  [{ts}] {activo}: intra-vela necesaria pero sin datos M1, degradando a H1.')
        _paso_B(est_a, candle, activo, ts, estado, precios, capital_ap, cfg, events, trades, x5_ctx=x5_ctx)
        _paso_C(est_a, candle['High'], activo, ts, cfg, events)
        _paso_D(est_a, candle['Low'], activo, ts, estado, capital_ap, N, cfg, events, trades, x5_ctx=x5_ctx)
        _paso_E(est_a, candle['Low'], activo, ts, estado, capital_ap, N, cfg, events, trades, x5_ctx=x5_ctx)
        _paso_F(est_a, candle['Close'], activo, ts, estado, precios, cfg, events, x5_ctx=x5_ctx)


# ─── Equity CSV ───────────────────────────────────────────────────────────────

def _append_equity(ts, estado: dict, precios: dict, cfg) -> dict:
    mc = _calcular_estado_cuenta(estado, precios, cfg)

    eq_g = cfg.CARPETA_RESOURCES / 'equity_global.csv'
    write_hdr = not eq_g.exists()
    with open(eq_g, 'a', newline='') as f:
        w = csv.writer(f)
        if write_hdr:
            w.writerow(['ts', 'balance', 'equity', 'margen_usado', 'margen_libre',
                        'margin_level', 'n_OA', 'n_OE'])
        w.writerow([
            ts.isoformat(),
            round(mc['balance'], 4), round(mc['equity'], 4),
            round(mc['margen_usado'], 4), round(mc['margen_libre'], 4),
            round(mc['margin_level'], 4) if mc['margin_level'] is not None else '',
            mc['n_OA'], mc['n_OE'],
        ])

    eq_a = cfg.CARPETA_RESOURCES / 'equity_activos.csv'
    write_hdr_a = not eq_a.exists()
    with open(eq_a, 'a', newline='') as f:
        w = csv.writer(f)
        if write_hdr_a:
            w.writerow(['ts', 'activo', 'GC', 'GA', 'GT'])
        for activo, est_a in estado['por_activo'].items():
            lote = cfg.LOTAJES[activo]
            units = cfg.UNITS[activo]
            precio_a = precios.get(activo, 0.0)
            GC = est_a['GC']
            GA = _calcular_GA(est_a, precio_a, lote, units)
            w.writerow([ts.isoformat(), activo, round(GC, 4), round(GA, 4), round(GC + GA, 4)])

    return mc


# ─── Flush a disco ────────────────────────────────────────────────────────────

def _flush_json_list(items: list, path: Path):
    if not items:
        return
    existing = []
    if path.exists():
        with open(path) as f:
            existing = json.load(f)
    existing.extend(items)
    with open(path, 'w') as f:
        json.dump(existing, f, indent=2, default=str)
    items.clear()


# ─── X5 — Captura y escritura al store ───────────────────────────────────────

def _features_temporales_ts(ts: pd.Timestamp) -> dict:
    import config as _gc
    from datetime import date as _date
    hdays = {_date.fromisoformat(d) for d in _gc.X5_US_HOLIDAYS}
    d, dw, m = ts.date(), ts.dayofweek, ts.month
    fut = sorted(h for h in hdays if h >= d)
    pas = sorted((h for h in hdays if h <= d), reverse=True)
    dh = (fut[0] - d).days if fut else 30
    dd = (d - pas[0]).days if pas else 30
    return {
        'hora': ts.hour, 'dia_semana': dw, 'dia_mes': ts.day, 'mes': m,
        'ds_lun': int(dw == 0), 'ds_mar': int(dw == 1), 'ds_mie': int(dw == 2),
        'ds_jue': int(dw == 3), 'ds_vie': int(dw == 4),
        'ds_sab': int(dw == 5), 'ds_dom': int(dw == 6),
        **{f'mes_{i}': int(m == i) for i in range(1, 13)},
        'dias_hasta_festivo': min(dh, 30), 'dias_desde_festivo': min(dd, 30),
        'es_vispera_festivo': int(dh <= 1), 'es_post_festivo': int(dd <= 1),
    }


def _leer_x2_bt(activo: str, fecha_str: str, carpeta_fundamentals: Path) -> dict:
    path = carpeta_fundamentals / 'x2_history.json'
    if not path.exists():
        return {}
    with open(path) as f:
        hist = json.load(f)
    entradas = hist.get(activo, [])
    if not entradas:
        return {}
    candidatas = [e for e in entradas if e.get('fecha', '') <= fecha_str] or entradas
    ultima = max(candidatas, key=lambda e: e.get('fecha', ''))
    return {k: v for k, v in ultima.items() if k != 'fecha'}


def _compute_x5_snapshot(activo: str, df_activo: pd.DataFrame,
                          ts: pd.Timestamp, soportes: list,
                          carpeta_fundamentals: Path) -> tuple:
    df_hasta = df_activo[df_activo.index <= ts].reset_index()
    try:
        x3 = compute_snapshot(df_hasta, soportes)
    except Exception:
        x3 = {}
    x2 = _leer_x2_bt(activo, ts.date().isoformat(), carpeta_fundamentals)
    return x3, x2


def _contexto_portfolio_x5(est_a: dict, precio_cierre: float,
                            lote: float, units: int) -> dict:
    OA = est_a['OA']
    retornos_pct = [(precio_cierre - p) / p for p in OA] if OA else []
    mean_ret = sum(retornos_pct) / len(retornos_pct) if retornos_pct else 0.0
    std_ret = (sum((r - mean_ret) ** 2 for r in retornos_pct) / len(retornos_pct)) ** 0.5 \
              if len(retornos_pct) > 1 else 0.0
    oc_rec = est_a.get('oc_recientes', [])
    ret_ult5 = sum(oc_rec[-5:]) / len(oc_rec[-5:]) if oc_rec else 0.0
    # P&L flotante (no realizado) en USD de las OA aún abiertas del activo.
    pnl_flotante = sum((precio_cierre - p) * lote * units for p in OA)
    return {
        'n_ordenes_abiertas':            len(OA),
        'n_ordenes_espera':              len(est_a['OE']),
        'exposicion_usd':                round(sum(p * lote * units for p in OA), 4),
        'mean_retorno_pct_abierto':      round(mean_ret, 6),
        'std_retorno_pct_abierto':       round(std_ret, 6),
        'retorno_promedio_ultimas_5_oc': round(ret_ult5, 6),
        'pnl_flotante_activo':           round(pnl_flotante, 4),
    }


def _construir_fila_oc(activo: str, pos: dict, trade: dict,
                        ts_oc: pd.Timestamp, est_a: dict, precio_cierre: float,
                        cfg, min_lotajes: dict) -> dict:
    lote, units = cfg.LOTAJES[activo], cfg.UNITS[activo]
    base_l = min_lotajes.get(activo, lote)
    lotajes_m = max(1, round(lote / base_l)) if base_l > 0 else 1

    ts_oe = pd.Timestamp(pos.get('ts_oe_creacion', ts_oc.isoformat()))
    ts_oa = pd.Timestamp(pos.get('ts_apertura', ts_oc.isoformat()))
    temp_oe = _features_temporales_ts(ts_oe)
    temp_oa = _features_temporales_ts(ts_oa)
    x3_oe = pos.get('x3_oe', {})
    x2_oe = pos.get('x2_oe', {})
    x3_oa = pos.get('x3_oa', {})
    x2_oa = pos.get('x2_oa', {})
    portfolio = _contexto_portfolio_x5(est_a, precio_cierre, lote, units)

    fila: dict = {
        'tipo_registro': 'oc', 'activo': activo,
        'timestamp_oe': ts_oe.isoformat(),
        'timestamp_oa': ts_oa.isoformat(),
        'timestamp_oc': ts_oc.isoformat(),
        'n_ejecucion': cfg.n_sizes[activo], 'K': cfg.K,
        'N_EXP': cfg.N_EXP, 'LAMBDA': cfg.LAMBDA,
        'A': cfg.A, 'B': cfg.B,
        'LOTAJES_M': lotajes_m, 'PERDIDA_MAX': cfg.PERDIDA_MAX_BT,
    }
    fila.update(temp_oe)
    fila.update({f'x2_{k}': v for k, v in x2_oe.items()})
    fila.update({f'x3_{k}': v for k, v in x3_oe.items()})
    fila.update(portfolio)
    fila.update({f'{k}_oa': v for k, v in temp_oa.items()})
    fila.update({f'x2_{k}_oa': v for k, v in x2_oa.items()})
    fila.update({f'x3_{k}_oa': v for k, v in x3_oa.items()})
    # Targets del modelo X5
    fila['pnl_cerrado_activo'] = round(est_a.get('GC', 0.0), 4)  # P&L cerrado acumulado del activo
    fila['retorno_pct'] = trade['retorno_pct']
    return fila


def _construir_fila_periodica(activo: str, ts: pd.Timestamp, est_a: dict,
                               x3: dict, x2: dict, precio_cierre: float,
                               cfg, min_lotajes: dict) -> dict:
    lote, units = cfg.LOTAJES[activo], cfg.UNITS[activo]
    base_l = min_lotajes.get(activo, lote)
    lotajes_m = max(1, round(lote / base_l)) if base_l > 0 else 1
    temp = _features_temporales_ts(ts)
    portfolio = _contexto_portfolio_x5(est_a, precio_cierre, lote, units)
    fila: dict = {
        'tipo_registro': 'periodico', 'activo': activo,
        'timestamp_oe': '', 'timestamp_oa': '', 'timestamp_oc': ts.isoformat(),
        'n_ejecucion': cfg.n_sizes[activo], 'K': cfg.K,
        'N_EXP': cfg.N_EXP, 'LAMBDA': cfg.LAMBDA,
        'A': cfg.A, 'B': cfg.B,
        'LOTAJES_M': lotajes_m, 'PERDIDA_MAX': cfg.PERDIDA_MAX_BT,
    }
    fila.update(temp)
    fila.update({f'x2_{k}': v for k, v in x2.items()})
    fila.update({f'x3_{k}': v for k, v in x3.items()})
    fila.update(portfolio)  # incluye pnl_flotante_activo (target Y de las filas periódicas)
    fila.update({f'{k}_oa': '' for k in temp})
    fila.update({f'x2_{k}_oa': '' for k in x2})
    fila.update({f'x3_{k}_oa': '' for k in x3})
    # Targets: pnl_flotante_activo (en portfolio) es el Y del registro periódico.
    # pnl_cerrado_activo se registra para consistencia de columnas; retorno_pct no aplica.
    fila['pnl_cerrado_activo'] = round(est_a.get('GC', 0.0), 4)
    fila['retorno_pct'] = ''
    return fila


def _append_x5_store(activo: str, fila: dict) -> None:
    import config as _gc
    store_path = _gc.CARPETA_X5 / f'{activo}_store.csv'
    store_path.parent.mkdir(parents=True, exist_ok=True)
    write_hdr = not store_path.exists()
    with open(store_path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(fila.keys()), extrasaction='ignore')
        if write_hdr:
            w.writeheader()
        w.writerow(fila)


# ─── Loop principal ───────────────────────────────────────────────────────────

def ejecutar_backtest(cfg, reset: bool = False, x5_mode: bool = False,
                      min_lotajes: dict | None = None):
    t_inicio = time.time()
    print(f'\n{"═"*60}')
    print(f' X4 Backtester — versión {cfg.version}')
    print(f'{"═"*60}')

    cfg.CARPETA_RESOURCES.mkdir(parents=True, exist_ok=True)
    cfg.CARPETA_N_BT.mkdir(parents=True, exist_ok=True)
    cfg.CARPETA_LOGS_BT.mkdir(parents=True, exist_ok=True)

    if x5_mode:
        import config as _gc_x5
        _carpeta_fundamentals_x5 = _gc_x5.CARPETA_FUNDAMENTALS
        _min_lotajes_x5 = min_lotajes if min_lotajes is not None else dict(cfg.LOTAJES)
        _freq_periodico = _gc_x5.X5_FREQ_REGISTRO_PERIODICO
    else:
        _carpeta_fundamentals_x5 = None
        _min_lotajes_x5 = {}
        _freq_periodico = 0

    print('\nCargando datos H1...')
    datos_h1 = _cargar_datos_h1(cfg)
    if not datos_h1:
        print('Sin datos H1 disponibles. Saliendo.')
        return

    print('Cargando datos M1...')
    datos_m1 = _cargar_datos_m1(cfg)
    for activo in cfg.valores:
        if datos_m1.get(activo) is None:
            print(f'  {activo}: sin M1 — intra-vela degradará a H1.')
        else:
            print(f'  {activo}: {len(datos_m1[activo])} velas M1 disponibles.')

    # Estado inicial
    estado = None
    if not reset:
        print('\nBuscando checkpoint...')
        estado = _cargar_checkpoint(cfg)

    if estado is None:
        print('Iniciando desde cero.')
        estado = {
            'capital': cfg.capital_inicial,
            'GC_global': 0.0,
            'por_activo': {
                activo: {'soportes': [], 'OE': {}, 'OA': {}, 'GC': 0.0}
                for activo in cfg.valores
            },
            'ts_ultimo_procesado': None,
            'ts_ultimo_recalculo': None,
        }

    # Cold start: recalcular soportes si algún activo no tiene
    necesita_cold = any(
        not estado['por_activo'][a]['soportes']
        for a in cfg.valores if a in datos_h1
    )
    if necesita_cold:
        ts_cold = pd.Timestamp(cfg.fecha_inicio)
        print(f'\nCold start: recalculando soportes hasta {ts_cold} ...')
        print('(puede tardar varios minutos)')
        _recalcular_soportes(estado, ts_cold, cfg)
        _guardar_checkpoint(estado, cfg)
        print('Cold start completado.\n')

    ts_ultimo = (pd.Timestamp(estado['ts_ultimo_procesado'])
                 if estado['ts_ultimo_procesado'] else None)

    trades_log: list = []
    events_log: list = []
    velas_procesadas = 0
    cierre_previo: dict = {a: None for a in cfg.valores}
    mes_actual: str | None = None  # para [MES_BT] markers en x5_mode

    # Timestamps unión de todos los activos
    all_ts = sorted(set().union(*[set(df.index) for df in datos_h1.values()]))

    print(f'Loop: {len(all_ts)} timestamps disponibles'
          + (f', reanudando desde {ts_ultimo}' if ts_ultimo else '') + '\n')

    def _fmt_dur(s):
        s = int(s)
        h, r = divmod(s, 3600)
        m, seg = divmod(r, 60)
        return f'{h:02d}:{m:02d}:{seg:02d}'

    for ts in all_ts:
        # Actualizar cierre_previo (incluso para velas ya procesadas post-checkpoint)
        for activo, df in datos_h1.items():
            if ts in df.index and ts_ultimo is not None and ts <= ts_ultimo:
                cierre_previo[activo] = df.loc[ts, 'Close']

        if ts_ultimo is not None and ts <= ts_ultimo:
            continue

        # Check recálculo de soportes
        ts_rec = (pd.Timestamp(estado['ts_ultimo_recalculo'])
                  if estado['ts_ultimo_recalculo'] else None)
        if ts_rec is not None:
            horas = (ts - ts_rec).total_seconds() / 3600
            umbral = cfg.delta_recalculo_soportes * 24
            if cfg.delta_recalculo_soportes == int(cfg.delta_recalculo_soportes):
                disparar = horas >= umbral and ts.hour == cfg.hora_recalculo
            else:
                disparar = horas >= umbral
            if disparar:
                print(f'  [{ts}] Recalculando soportes...')
                _recalcular_soportes(estado, ts, cfg)
                estado['ts_ultimo_procesado'] = ts.isoformat()
                _flush_json_list(trades_log, cfg.CARPETA_RESOURCES / 'trades.json')
                _flush_json_list(events_log, cfg.CARPETA_RESOURCES / 'events.json')
                for activo, df in datos_h1.items():
                    if ts in df.index:
                        cierre_previo[activo] = df.loc[ts, 'Close']
                continue  # vela congelada

        # Precios de cierre para esta vela (Close de cada activo o último conocido)
        precios_ts: dict = {}
        for activo, df in datos_h1.items():
            if ts in df.index:
                precios_ts[activo] = df.loc[ts, 'Close']
            elif cierre_previo.get(activo):
                precios_ts[activo] = cierre_previo[activo]

        # Procesar cada activo
        for activo, df in datos_h1.items():
            if ts not in df.index:
                continue
            candle = df.loc[ts]
            N = cfg.n_sizes[activo]

            x5_ctx_a = None
            if x5_mode:
                _x3, _x2 = _compute_x5_snapshot(
                    activo, df, ts,
                    estado['por_activo'][activo]['soportes'],
                    _carpeta_fundamentals_x5,
                )
                x5_ctx_a = {'x3': _x3, 'x2': _x2, 'min_lotajes': _min_lotajes_x5}

            _procesar_candle(
                ts, candle, activo,
                estado['por_activo'][activo],
                estado, datos_m1.get(activo), precios_ts, N,
                cfg, events_log, trades_log, x5_ctx_a,
            )
            cierre_previo[activo] = candle['Close']

            # Registro periódico: cada _freq_periodico velas con al menos 1 OA
            if x5_mode and x5_ctx_a is not None and _freq_periodico > 0:
                est_a_p = estado['por_activo'][activo]
                if est_a_p['OA']:
                    cnt = est_a_p.get('x5_velas_cnt', 0) + 1
                    est_a_p['x5_velas_cnt'] = cnt
                    if cnt % _freq_periodico == 0:
                        _fila_p = _construir_fila_periodica(
                            activo, ts, est_a_p,
                            x5_ctx_a['x3'], x5_ctx_a['x2'],
                            candle['Close'], cfg, _min_lotajes_x5,
                        )
                        _append_x5_store(activo, _fila_p)

        # Paso G: snapshot equity
        mc = _append_equity(ts, estado, precios_ts, cfg)

        estado['ts_ultimo_procesado'] = ts.isoformat()
        velas_procesadas += 1

        # [MES_BT] marker — X5 --recolectar escucha estas líneas en stdout
        if x5_mode:
            mes_ts = ts.strftime('%Y-%m')
            if mes_actual is not None and mes_ts != mes_actual:
                print(f'[MES_BT] {mes_actual}', flush=True)
            mes_actual = mes_ts

        # Stop-out: equity <= 0 o margin level bajo el umbral con posiciones abiertas
        stop_out_level = getattr(cfg, 'STOP_OUT_LEVEL', 50)
        ml = mc['margin_level']
        cuenta_quemada = (
            mc['equity'] <= 0
            or (ml is not None and mc['margen_usado'] > 0 and ml <= stop_out_level)
        )
        if cuenta_quemada:
            events_log.append({
                'tipo': 'stop_out',
                'ts': ts.isoformat(),
                'equity': round(mc['equity'], 4),
                'balance': round(mc['balance'], 4),
                'margen_usado': round(mc['margen_usado'], 4),
                'margin_level': round(ml, 4) if ml is not None else None,
                'n_OA': mc['n_OA'],
            })
            estado['stop_out'] = True
            _guardar_checkpoint(estado, cfg)
            _flush_json_list(trades_log, cfg.CARPETA_RESOURCES / 'trades.json')
            _flush_json_list(events_log, cfg.CARPETA_RESOURCES / 'events.json')
            print(f'\n  *** STOP OUT [{ts}] ***')
            print(f'  equity={mc["equity"]:.2f}  balance={mc["balance"]:.2f}'
                  f'  margin_level={f"{ml:.1f}%" if ml is not None else "N/A"}'
                  f'  OA={mc["n_OA"]}')
            break

        # Checkpoint + flush cada 24 velas
        if velas_procesadas % 24 == 0:
            _guardar_checkpoint(estado, cfg)
            _flush_json_list(trades_log, cfg.CARPETA_RESOURCES / 'trades.json')
            _flush_json_list(events_log, cfg.CARPETA_RESOURCES / 'events.json')
            trades_path = cfg.CARPETA_RESOURCES / 'trades.json'
            n_trades = len(json.load(open(trades_path))) if trades_path.exists() else 0
            print(f'  [{ts}] eq={mc["equity"]:.2f} bal={mc["balance"]:.2f} | OA={mc["n_OA"]} OE={mc["n_OE"]} | trades={n_trades}')

    # Fin de datos
    _guardar_checkpoint(estado, cfg)
    _flush_json_list(trades_log, cfg.CARPETA_RESOURCES / 'trades.json')
    _flush_json_list(events_log, cfg.CARPETA_RESOURCES / 'events.json')

    if x5_mode and mes_actual is not None:
        print(f'[MES_BT] {mes_actual}', flush=True)

    dur = time.time() - t_inicio
    print(f'\n{"═"*60}')
    if estado.get('stop_out'):
        print(f' STOP OUT — cuenta quemada tras {velas_procesadas} velas procesadas')
    else:
        print(f' Backtest completado: {velas_procesadas} velas procesadas')
    print(f' Capital final:       {estado["capital"]:.2f} USD '
          f'(inicio: {cfg.capital_inicial:.2f})')
    n_oa = sum(len(e['OA']) for e in estado['por_activo'].values())
    print(f' Posiciones abiertas al cierre: {n_oa}  (sin cerrar — fecha_fin=F)')
    print(f' Tiempo total: {_fmt_dur(dur)}')
    print(f'{"═"*60}')


# ─── X5 — modo explore/exploit ───────────────────────────────────────────────

def _generar_params_explore(cfg, cfg_global) -> dict:
    """Params aleatorios por activo dentro de X5_PARAM_RANGES."""
    ranges = cfg_global.X5_PARAM_RANGES
    result = {}
    for activo in cfg.valores:
        n_lo, n_hi = ranges['n_sizes_ejecucion'][activo]
        lm_lo, lm_hi = ranges['LOTAJES_M'][activo]
        result[activo] = {
            'n_sizes_ejecucion': random.randint(int(n_lo), int(n_hi)),
            'K':           random.uniform(*ranges['K'][activo]),
            'N_EXP':       random.uniform(*ranges['N_EXP'][activo]),
            'LAMBDA':      random.uniform(*ranges['LAMBDA'][activo]),
            'A':           random.uniform(*ranges['A'][activo]),
            'B':           random.uniform(*ranges['B'][activo]),
            'LOTAJES_M':   random.randint(int(lm_lo), int(lm_hi)),
            'PERDIDA_MAX': random.uniform(*ranges['PERDIDA_MAX'][activo]),
        }
    return result


def _generar_params_exploit(cfg, base_dir: Path, baseline: dict, activo=None) -> dict:
    """
    Llama a X5 --infer y lee active_parameters.json.
    Activos con model_status='untrained' usan baseline (config_V1).
    Si `activo` está dado (modo paralelo por activo), infiere solo ese activo.
    """
    x5_path = base_dir / 'scripts' / 'X5_macro_brain.py'
    active_params_path = base_dir / 'config' / 'active_parameters.json'
    cmd = [sys.executable, str(x5_path), '--infer']
    if activo is not None:
        cmd += ['--activo', activo]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
        )
        if proc.returncode != 0 or not active_params_path.exists():
            print(f'  X5 --infer falló (código {proc.returncode}) → fallback a baseline')
            return baseline
        with open(active_params_path) as f:
            ap = json.load(f)
    except Exception as e:
        print(f'  X5 --infer error: {e} → fallback a baseline')
        return baseline

    result = {}
    for activo in cfg.valores:
        b = baseline[activo]
        if activo not in ap or ap[activo].get('model_status') == 'untrained':
            result[activo] = b
            continue
        d = ap[activo]
        result[activo] = {
            'n_sizes_ejecucion': int(d.get('n_sizes_ejecucion', b['n_sizes_ejecucion'])),
            'K':           float(d.get('K',           b['K'])),
            'N_EXP':       float(d.get('N_EXP',       b['N_EXP'])),
            'LAMBDA':      float(d.get('LAMBDA',       b['LAMBDA'])),
            'A':           float(d.get('A',            b['A'])),
            'B':           float(d.get('B',            b['B'])),
            'LOTAJES_M':   int(d.get('LOTAJES_M',     b['LOTAJES_M'])),
            'PERDIDA_MAX': float(d.get('PERDIDA_MAX',  b['PERDIDA_MAX'])),
        }
    return result


def _aplicar_params_x5(cfg, params: dict, min_lotajes: dict):
    """
    Muta cfg con los params del ciclo.
    Params escalares (K, N_EXP, LAMBDA, A, B, PERDIDA_MAX_BT): usa primer activo.
    Params por activo (n_sizes, LOTAJES): aplica individualmente.
    """
    p0 = params[cfg.valores[0]]
    cfg.K             = p0['K']
    cfg.N_EXP         = p0['N_EXP']
    cfg.LAMBDA        = p0['LAMBDA']
    cfg.A             = p0['A']
    cfg.B             = p0['B']
    cfg.PERDIDA_MAX_BT = p0['PERDIDA_MAX']
    for activo in cfg.valores:
        p = params[activo]
        cfg.n_sizes[activo] = p['n_sizes_ejecucion']
        base = min_lotajes.get(activo, cfg.LOTAJES[activo])
        cfg.LOTAJES[activo] = p['LOTAJES_M'] * base


def _imprimir_ciclo_x5(tipo: str, params: dict, cfg):
    p0 = params[cfg.valores[0]]
    print(f'\n{"─"*60}')
    print(f' {tipo}  |  K={p0["K"]:.4f}  N_EXP={p0["N_EXP"]:.4f}'
          f'  LAMBDA={p0["LAMBDA"]:.6f}')
    print(f'         A={p0["A"]:.2f}  B={p0["B"]:.2f}'
          f'  PERDIDA_MAX={p0["PERDIDA_MAX"]:.1f}')
    for activo in cfg.valores:
        p = params[activo]
        print(f'  {activo}: N={p["n_sizes_ejecucion"]}  LOTAJES_M={p["LOTAJES_M"]}')
    print(f'{"─"*60}')


def ejecutar_x5_ciclo(cfg, activo=None):
    """
    Un ciclo de X5 backtesting: decide explore/exploit, aplica params,
    corre el backtest desde cero emitiendo [MES_BT] markers en stdout.
    Llamado una vez por X5 --recolectar para cada ciclo externo.

    Si `activo` está dado, el ciclo corre SOLO ese activo con recursos X4
    aislados (`resources_{version}_{activo}`), de modo que X5 --recolectar
    pueda lanzar un proceso por activo en paralelo sin colisionar en el
    checkpoint/equity compartido de la versión.
    """
    import config as cfg_global

    base_dir = Path(__file__).parent.parent

    if activo is not None:
        cfg.valores = [activo]
        base_res = cfg.CARPETA_RESOURCES
        cfg.CARPETA_RESOURCES = base_res.parent / f'{base_res.name}_{activo}'
        cfg.CARPETA_N_BT      = cfg.CARPETA_RESOURCES / 'conjuntos_N'
        cfg.CARPETA_LOGS_BT   = cfg.CARPETA_RESOURCES / 'logs'

    min_lotajes = dict(cfg.LOTAJES)  # capturar antes de mutar

    baseline = {
        activo: {
            'n_sizes_ejecucion': cfg.n_sizes[activo],
            'K':           cfg.K,
            'N_EXP':       cfg.N_EXP,
            'LAMBDA':      cfg.LAMBDA,
            'A':           cfg.A,
            'B':           cfg.B,
            'LOTAJES_M':   1,
            'PERDIDA_MAX': cfg.PERDIDA_MAX_BT,
        }
        for activo in cfg.valores
    }

    es_explore = random.random() < cfg_global.X5_EXPLORATION_RATE
    tipo = 'EXPLORE' if es_explore else 'EXPLOIT'

    if es_explore:
        params = _generar_params_explore(cfg, cfg_global)
    else:
        params = _generar_params_exploit(cfg, base_dir, baseline, activo=activo)

    _aplicar_params_x5(cfg, params, min_lotajes)
    _imprimir_ciclo_x5(tipo, params, cfg)
    ejecutar_backtest(cfg, reset=True, x5_mode=True, min_lotajes=min_lotajes)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from config import X4_VERSION_ACTIVA

    parser = argparse.ArgumentParser(description='X4 Backtester')
    parser.add_argument('--version', type=str, default=X4_VERSION_ACTIVA,
                        help=f'Versión a ejecutar (default: {X4_VERSION_ACTIVA})')
    parser.add_argument('--reset', action='store_true',
                        help='Ignorar checkpoint existente y partir de cero')
    parser.add_argument('--x5', action='store_true',
                        help='Modo X5: explore/exploit de params, emite [MES_BT] markers para X5 --recolectar')
    parser.add_argument('--activo', type=str, default=None,
                        help='En modo --x5: correr solo este activo con recursos aislados (paralelismo de X5 --recolectar)')
    args = parser.parse_args()

    cfg = _cargar_config(args.version)
    if args.x5:
        ejecutar_x5_ciclo(cfg, activo=args.activo)
    else:
        ejecutar_backtest(cfg, reset=args.reset)
