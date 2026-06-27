
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
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from X0_data_supports import _procesar_valor_N, _bt_warm_start


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
            capital_ap: float, cfg, events: list, trades: list, usa_iv: bool = False):
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
            ts_creacion = est_a['OE'].pop(precio_oe).get('ts_creacion', ts.isoformat())
            est_a['OA'][precio_gap] = {
                'lote': lote, 'sl': 0,
                'ts_apertura': ts.isoformat(),
                'capital_apertura': estado['capital'],
                'ganancia_max': 0.0, 'drawdown_max': 0.0,
                'usa_intravela': usa_iv, 'duracion_velas': 0,
            }
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
            ts_creacion = est_a['OE'].pop(precio_oe).get('ts_creacion', ts.isoformat())
            est_a['OA'][precio_oe] = {
                'lote': lote, 'sl': 0,
                'ts_apertura': ts.isoformat(),
                'capital_apertura': estado['capital'],
                'ganancia_max': 0.0, 'drawdown_max': 0.0,
                'usa_intravela': usa_iv, 'duracion_velas': 0,
            }
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
            capital_ap: float, N: int, cfg, events: list, trades: list, usa_iv: bool = False):
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
        trades.append(_registrar_trade(pos, precio_ap, precio_cierre, 'perdida_max',
                                       ts, activo, N, capital_ap, cfg))
        events.append(_evt('posicion_cerrada', activo, ts, cfg, usa_iv,
                           precio_apertura=precio_ap, precio_cierre=precio_cierre,
                           motivo='perdida_max', retorno_usd=round(retorno_usd, 4), lote=lote))


def _paso_E(est_a: dict, precio_min: float, activo: str, ts, estado: dict,
            capital_ap: float, N: int, cfg, events: list, trades: list, usa_iv: bool = False):
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
        trades.append(_registrar_trade(pos, precio_ap, precio_cierre, 'trailing_stop',
                                       ts, activo, N, capital_ap, cfg))
        events.append(_evt('posicion_cerrada', activo, ts, cfg, usa_iv,
                           precio_apertura=precio_ap, precio_cierre=precio_cierre,
                           motivo='trailing_stop', retorno_usd=round(retorno_usd, 4), lote=lote))


def _paso_F(est_a: dict, precio_ref: float, activo: str, ts, estado: dict,
            precios: dict, cfg, events: list, usa_iv: bool = False):
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
        est_a['OE'][soporte] = {'lote': lote, 'ts_creacion': ts.isoformat()}
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
                     cfg, events: list, trades: list):
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
        _paso_B(est_a, candle, activo, ts, estado, precios, capital_ap, cfg, events, trades)
        _paso_C(est_a, candle['High'], activo, ts, cfg, events)
        _paso_D(est_a, candle['Low'], activo, ts, estado, capital_ap, N, cfg, events, trades)
        _paso_E(est_a, candle['Low'], activo, ts, estado, capital_ap, N, cfg, events, trades)
        _paso_F(est_a, candle['Close'], activo, ts, estado, precios, cfg, events)


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


# ─── Loop principal ───────────────────────────────────────────────────────────

def ejecutar_backtest(cfg, reset: bool = False):
    t_inicio = time.time()
    print(f'\n{"═"*60}')
    print(f' X4 Backtester — versión {cfg.version}')
    print(f'{"═"*60}')

    cfg.CARPETA_RESOURCES.mkdir(parents=True, exist_ok=True)
    cfg.CARPETA_N_BT.mkdir(parents=True, exist_ok=True)
    cfg.CARPETA_LOGS_BT.mkdir(parents=True, exist_ok=True)

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
            _procesar_candle(
                ts, candle, activo,
                estado['por_activo'][activo],
                estado, datos_m1.get(activo), precios_ts, N,
                cfg, events_log, trades_log,
            )
            cierre_previo[activo] = candle['Close']

        # Paso G: snapshot equity
        mc = _append_equity(ts, estado, precios_ts, cfg)

        estado['ts_ultimo_procesado'] = ts.isoformat()
        velas_procesadas += 1

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


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from config import X4_VERSION_ACTIVA

    parser = argparse.ArgumentParser(description='X4 Backtester')
    parser.add_argument('--version', type=str, default=X4_VERSION_ACTIVA,
                        help=f'Versión a ejecutar (default: {X4_VERSION_ACTIVA})')
    parser.add_argument('--reset', action='store_true',
                        help='Ignorar checkpoint existente y partir de cero')
    args = parser.parse_args()

    cfg = _cargar_config(args.version)
    ejecutar_backtest(cfg, reset=args.reset)
