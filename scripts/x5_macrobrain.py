
"""
x5.py

Backtester de X5: genera el store de trades para entrenar el surrogate model.

Corre un loop explore/exploit por activo (un ciclo = recorrido completo del historial H1
desde FECHA_INICIAL hasta hoy). Cada activo corre en un proceso independiente. Se puede
detener (Ctrl+C) y retomar — cada proceso retoma desde su último checkpoint.

Uso:
  python scripts/x5.py                       # todos los activos en paralelo (loop continuo)
  python scripts/x5.py --activo BTCUSD       # solo un activo
  python scripts/x5.py --ciclos 10           # correr N ciclos por activo y detener
  python scripts/x5.py --status             # progreso de cada activo
  python scripts/x5.py --reset              # descarta checkpoints y parte de cero
"""

import argparse
import csv
import json
import multiprocessing
import random
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg

# ─── Rutas ────────────────────────────────────────────────────────────────────

CARPETA_X5    = cfg.CARPETA_X5
CARPETA_CKPT  = CARPETA_X5 / 'checkpoints'
CARPETA_N_BT  = cfg.BASE_DIR / 'resources' / 'conjuntos_N'

# ─── Features temporales ─────────────────────────────────────────────────────

_HOLIDAYS = {date.fromisoformat(d) for d in cfg.X5_US_HOLIDAYS}


def _features_temporales(ts: pd.Timestamp) -> dict:
    d = ts.date()
    dw = ts.dayofweek
    m = ts.month

    futuros = sorted(h for h in _HOLIDAYS if h >= d)
    pasados = sorted((h for h in _HOLIDAYS if h <= d), reverse=True)
    dias_hasta = (futuros[0] - d).days if futuros else 30
    dias_desde = (d - pasados[0]).days if pasados else 30

    return {
        'hora':       ts.hour,
        'dia_semana': dw,
        'dia_mes':    ts.day,
        'mes':        m,
        'ds_lun': int(dw == 0), 'ds_mar': int(dw == 1), 'ds_mie': int(dw == 2),
        'ds_jue': int(dw == 3), 'ds_vie': int(dw == 4),
        'ds_sab': int(dw == 5), 'ds_dom': int(dw == 6),
        **{f'mes_{i}': int(m == i) for i in range(1, 13)},
        'dias_hasta_festivo': min(dias_hasta, 30),
        'dias_desde_festivo': min(dias_desde, 30),
        'es_vispera_festivo': int(dias_hasta <= 1),
        'es_post_festivo':    int(dias_desde <= 1),
    }


# ─── Loaders X2 / X3 ─────────────────────────────────────────────────────────

def _cargar_x2_history() -> dict:
    path = cfg.CARPETA_FUNDAMENTALS / 'x2_history.json'
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _x2_snapshot(activo: str, ts: pd.Timestamp, x2_history: dict) -> dict:
    """Snapshot de X2 más reciente con fecha <= ts."""
    entradas = x2_history.get(activo, [])
    if not entradas:
        return {}
    dia_str = ts.date().isoformat()
    candidatos = [e for e in entradas if e.get('fecha', '') <= dia_str]
    if not candidatos:
        return {}
    snap = max(candidatos, key=lambda e: e.get('fecha', ''))
    return {k: v for k, v in snap.items() if k != 'fecha'}


def _cargar_x3(activo: str) -> pd.DataFrame | None:
    path = cfg.CARPETA_FEATURES / f'{activo}.csv'
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if 'DateTime' in df.columns:
        df['DateTime'] = pd.to_datetime(df['DateTime'])
        df = df.set_index('DateTime').sort_index()
    return df


def _x3_snapshot(ts: pd.Timestamp, x3_df: pd.DataFrame | None) -> dict:
    """Fila de X3 en ts o la vela anterior más cercana."""
    if x3_df is None or len(x3_df) == 0:
        return {}
    idx = x3_df.index.asof(ts)
    if pd.isna(idx):
        return {}
    return x3_df.loc[idx].to_dict()


# ─── Soportes ─────────────────────────────────────────────────────────────────

def _cargar_soportes(activo: str, n: int, ts: pd.Timestamp) -> list[float]:
    """
    Carga soportes del cache bt (lista de precios computada por X4/X0 a distintos t).
    Usa el snapshot más reciente con key <= ts.
    Fallback: soportes de producción actuales.
    """
    bt_path = CARPETA_N_BT / f'{activo}_{n}_bt.json'
    if bt_path.exists():
        with open(bt_path) as f:
            bt = json.load(f)
        ts_str = ts.isoformat()
        candidatos = [(k, v) for k, v in bt.items() if k <= ts_str]
        if candidatos:
            _, soportes = max(candidatos, key=lambda x: x[0])
            return sorted(soportes)

    prod_path = CARPETA_N_BT / f'{activo}_{n}.json'
    if prod_path.exists():
        with open(prod_path) as f:
            data = json.load(f)
        soportes = data.get('soportes', data) if isinstance(data, dict) else data
        return sorted(soportes)

    return []


# ─── Checkpoint ───────────────────────────────────────────────────────────────

def _ckpt_path(activo: str) -> Path:
    return CARPETA_CKPT / f'{activo}_ckpt.json'


def _cargar_ckpt(activo: str) -> dict | None:
    p = _ckpt_path(activo)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def _guardar_ckpt(activo: str, ciclo: int, tipo_ciclo: str, params: dict,
                  ts_ultimo: str | None, estado_serial: dict,
                  ultimas_5_oc: list, n_oc_total: int):
    CARPETA_CKPT.mkdir(parents=True, exist_ok=True)
    ckpt = {
        'activo': activo, 'ciclo': ciclo, 'tipo_ciclo': tipo_ciclo,
        'params': params, 'ts_ultimo': ts_ultimo,
        'estado': estado_serial,
        'ultimas_5_oc': ultimas_5_oc,
        'n_oc_total': n_oc_total,
    }
    with open(_ckpt_path(activo), 'w') as f:
        json.dump(ckpt, f, indent=2, default=str)


def _serializar_estado(estado: dict) -> dict:
    """Convierte claves float a str para JSON."""
    return {
        'oe': {str(k): v for k, v in estado['oe'].items()},
        'oa': {str(k): v for k, v in estado['oa'].items()},
        'pnl_cerrado': estado['pnl_cerrado'],
    }


def _deserializar_estado(s: dict) -> dict:
    return {
        'oe': {float(k): v for k, v in s['oe'].items()},
        'oa': {float(k): v for k, v in s['oa'].items()},
        'pnl_cerrado': s['pnl_cerrado'],
    }


def _estado_inicial() -> dict:
    return {'oe': {}, 'oa': {}, 'pnl_cerrado': 0.0}


# ─── Store CSV ────────────────────────────────────────────────────────────────

_COLS_BASE = [
    'tipo_registro', 'activo', 'ciclo', 'tipo_ciclo',
    'timestamp_oe', 'timestamp_oa', 'timestamp_oc', 'timestamp_registro',
    'n_ejecucion', 'K', 'N_EXP', 'LAMBDA', 'A', 'B', 'LOTAJES_M', 'PERDIDA_MAX',
    'precio_entrada', 'precio_salida', 'pnl_usd', 'retorno_pct',
    'pnl_flotante_activo', 'pnl_cerrado_activo_sesion',
    'n_ordenes_abiertas', 'n_ordenes_espera', 'exposicion_usd',
    'mean_retorno_pct_abierto', 'std_retorno_pct_abierto',
    'retorno_promedio_ultimas_5_oc',
    'hora', 'dia_semana', 'dia_mes', 'mes',
    'ds_lun', 'ds_mar', 'ds_mie', 'ds_jue', 'ds_vie', 'ds_sab', 'ds_dom',
    *[f'mes_{i}' for i in range(1, 13)],
    'dias_hasta_festivo', 'dias_desde_festivo', 'es_vispera_festivo', 'es_post_festivo',
]


def _store_path(activo: str) -> Path:
    return CARPETA_X5 / f'{activo}_store.csv'


def _flush_store(activo: str, filas: list[dict]):
    if not filas:
        return
    CARPETA_X5.mkdir(parents=True, exist_ok=True)
    path = _store_path(activo)
    # Columnas dinámicas: base + cualquier feature X2/X3 presente
    extra = sorted({k for f in filas for k in f if k not in _COLS_BASE})
    cols = _COLS_BASE + extra
    write_header = not path.exists()
    with open(path, 'a', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        if write_header:
            w.writeheader()
        for fila in filas:
            w.writerow({c: fila.get(c, '') for c in cols})
    filas.clear()


# ─── Params ───────────────────────────────────────────────────────────────────

def _params_baseline(activo: str) -> dict:
    return {
        'K': cfg.K, 'N_EXP': cfg.N_EXP, 'LAMBDA': cfg.LAMBDA,
        'A': cfg.A, 'B': cfg.B,
        'LOTAJES_M': cfg.LOTAJES_M[activo],
        'n_ejecucion': cfg.n_sizes_ejecucion[activo],
        'PERDIDA_MAX': cfg.PERDIDA_MAX,
    }


def _samplear_params(activo: str) -> dict:
    def _u(key):
        lo, hi = cfg.X5_PARAM_RANGES[key][activo]
        return random.uniform(lo, hi)
    n_lo, n_hi = cfg.X5_PARAM_RANGES['n_sizes_ejecucion'][activo]
    lm_lo, lm_hi = cfg.X5_PARAM_RANGES['LOTAJES_M'][activo]
    return {
        'K': _u('K'), 'N_EXP': _u('N_EXP'), 'LAMBDA': _u('LAMBDA'),
        'A': _u('A'), 'B': _u('B'),
        'LOTAJES_M': random.randint(int(lm_lo), int(lm_hi)),
        'n_ejecucion': random.randint(int(n_lo), int(n_hi)),
        'PERDIDA_MAX': _u('PERDIDA_MAX'),
    }


# ─── Contexto operativo ───────────────────────────────────────────────────────

def _contexto_operativo(estado: dict, precio_actual: float, lote: float,
                         units: int, ultimas_5_oc: list) -> dict:
    oa = estado['oa']
    L = lote * units
    retornos = [(precio_actual - p) / p for p in oa] if oa else []
    exposicion = sum(p * lote * units for p in oa)
    return {
        'n_ordenes_abiertas':     len(oa),
        'n_ordenes_espera':       len(estado['oe']),
        'exposicion_usd':         round(exposicion, 4),
        'mean_retorno_pct_abierto': round(float(np.mean(retornos)), 6) if retornos else 0.0,
        'std_retorno_pct_abierto':  round(float(np.std(retornos)), 6) if retornos else 0.0,
        'retorno_promedio_ultimas_5_oc': round(float(np.mean(ultimas_5_oc)), 6) if ultimas_5_oc else 0.0,
    }


# ─── Simulación (pasos A–F, sin gestión de margen ni intra-vela) ─────────────

def _procesar_vela(
    ts: pd.Timestamp,
    candle: pd.Series,
    soportes: list[float],
    estado: dict,
    params: dict,
    lote: float,
    units: int,
    x2_snap: dict,
    x3_snap: dict,
    temp_snap: dict,
    ultimas_5_oc: list,
) -> list[dict]:
    """
    Simula pasos A→F de X1 para una vela H1.
    Retorna lista de trades cerrados en esta vela.
    """
    L = lote * units
    A = params['A']
    B = params['B']
    oe = estado['oe']
    oa = estado['oa']
    soportes_set = set(soportes)
    trades_cerrados = []
    precio_ref = candle['Close']

    # Paso A: cancelar OEs cuyo soporte ya no está activo
    for p in [k for k in list(oe.keys()) if k not in soportes_set]:
        del oe[p]

    # Actualizar duración y drawdown de OAs
    for p_ap, pos in oa.items():
        pos['duracion_velas'] = pos.get('duracion_velas', 0) + 1
        dd = (candle['Low'] - p_ap) * L
        pos['drawdown_max'] = min(pos.get('drawdown_max', 0.0), dd)

    # Paso B: ejecutar OEs
    # Gap: OEs con precio >= Open (mercado abrió por encima de la orden)
    for p_oe in sorted([p for p in list(oe.keys()) if p >= candle['Open']]):
        if p_oe not in oe:
            continue
        precio_exec = min(p_oe, candle['Open'])
        info_oe = oe.pop(p_oe)
        oa[precio_exec] = _nueva_oa(info_oe, ts, x2_snap, x3_snap, temp_snap)

    # Normal: OEs cuyo precio está entre Low y Open
    for p_oe in sorted([p for p in list(oe.keys()) if candle['Low'] <= p < candle['Open']]):
        if p_oe not in oe:
            continue
        info_oe = oe.pop(p_oe)
        oa[p_oe] = _nueva_oa(info_oe, ts, x2_snap, x3_snap, temp_snap)

    # Paso C: trailing stop
    for p_ap, pos in list(oa.items()):
        ga = (candle['High'] - p_ap) * L
        pos['ganancia_max'] = max(pos.get('ganancia_max', 0.0), ga)
        if pos['sl'] == 0:
            if ga >= A:
                pos['sl'] = candle['High'] - B / L
                # Reponer OE en el nivel de apertura (con snapshot actual)
                if p_ap not in oa and p_ap not in oe:
                    oe[p_ap] = _nueva_oe(ts, x2_snap, x3_snap, temp_snap,
                                          estado, precio_ref, lote, units, ultimas_5_oc)
        else:
            sl_nuevo = candle['High'] - B / L
            if sl_nuevo > pos['sl']:
                pos['sl'] = sl_nuevo

    # Paso D: cerrar por PERDIDA_MAX
    for p_ap in [p for p, pos in oa.items() if (p - candle['Low']) * L > params['PERDIDA_MAX']]:
        pos = oa.pop(p_ap)
        precio_cierre = candle['Low']
        pnl = (precio_cierre - p_ap) * L
        estado['pnl_cerrado'] += pnl
        trades_cerrados.append(_trade(ts, p_ap, precio_cierre, pnl, 'perdida_max', pos, lote, units))

    # Paso E: cerrar por trailing stop
    for p_ap in [p for p, pos in oa.items() if pos['sl'] > 0 and candle['Low'] <= pos['sl']]:
        pos = oa.pop(p_ap)
        precio_cierre = pos['sl']
        pnl = (precio_cierre - p_ap) * L
        estado['pnl_cerrado'] += pnl
        trades_cerrados.append(_trade(ts, p_ap, precio_cierre, pnl, 'trailing_stop', pos, lote, units))

    # Paso F: crear OEs en soportes libres con suficiente distancia al precio actual
    for soporte in sorted(soportes, reverse=True):
        if soporte in oa or soporte in oe:
            continue
        if (precio_ref - soporte) * L < A:
            continue
        oe[soporte] = _nueva_oe(ts, x2_snap, x3_snap, temp_snap,
                                  estado, precio_ref, lote, units, ultimas_5_oc)

    return trades_cerrados


def _nueva_oe(ts, x2, x3, temp, estado, precio_ref, lote, units, ultimas_5_oc) -> dict:
    """Crea el dict de una OE capturando snapshot en el momento de decisión."""
    ctx = _contexto_operativo(estado, precio_ref, lote, units, ultimas_5_oc)
    return {
        'ts_creacion': ts.isoformat(),
        'x2_oe': x2, 'x3_oe': x3, 'temp_oe': temp, 'ctx_oe': ctx,
    }


def _nueva_oa(info_oe: dict, ts: pd.Timestamp, x2_oa: dict, x3_oa: dict, temp_oa: dict) -> dict:
    """Crea el dict de una OA cuando se ejecuta la OE."""
    return {
        'sl': 0,
        'ts_apertura': ts.isoformat(),
        'ts_oe': info_oe.get('ts_creacion'),
        'x2_oe': info_oe.get('x2_oe', {}), 'x3_oe': info_oe.get('x3_oe', {}),
        'temp_oe': info_oe.get('temp_oe', {}), 'ctx_oe': info_oe.get('ctx_oe', {}),
        'x2_oa': x2_oa, 'x3_oa': x3_oa, 'temp_oa': temp_oa,
        'ganancia_max': 0.0, 'drawdown_max': 0.0, 'duracion_velas': 0,
    }


def _trade(ts, precio_ap, precio_cierre, pnl, motivo, pos, lote, units) -> dict:
    return {
        'ts_oc': ts, 'precio_ap': precio_ap, 'precio_cierre': precio_cierre,
        'pnl': pnl, 'motivo': motivo, 'pos': pos, 'lote': lote, 'units': units,
    }


# ─── Construcción de filas del store ──────────────────────────────────────────

def _fila_oc(activo: str, ciclo: int, tipo_ciclo: str, params: dict,
              tc: dict, estado: dict, ultimas_5_oc: list) -> dict:
    ts_oc = tc['ts_oc']
    pos = tc['pos']
    L = tc['lote'] * tc['units']
    pnl_flotante = sum((tc['precio_cierre'] - p) * L for p in estado['oa'])
    retorno_pct = tc['pnl'] / (tc['precio_ap'] * L) if tc['precio_ap'] * L != 0 else 0.0

    fila = {
        'tipo_registro': 'oc', 'activo': activo, 'ciclo': ciclo, 'tipo_ciclo': tipo_ciclo,
        'timestamp_oe':  pos.get('ts_oe'),
        'timestamp_oa':  pos.get('ts_apertura'),
        'timestamp_oc':  ts_oc.isoformat(),
        'timestamp_registro': '',
        'n_ejecucion': params['n_ejecucion'], 'K': params['K'], 'N_EXP': params['N_EXP'],
        'LAMBDA': params['LAMBDA'], 'A': params['A'], 'B': params['B'],
        'LOTAJES_M': params['LOTAJES_M'],
        'precio_entrada': tc['precio_ap'], 'precio_salida': tc['precio_cierre'],
        'pnl_usd': round(tc['pnl'], 4), 'retorno_pct': round(retorno_pct, 6),
        'pnl_flotante_activo': round(pnl_flotante, 4),
        'pnl_cerrado_activo_sesion': round(estado['pnl_cerrado'], 4),
        **pos.get('ctx_oe', {}),
        'retorno_promedio_ultimas_5_oc': round(float(np.mean(ultimas_5_oc)), 6) if ultimas_5_oc else 0.0,
    }

    # Features temporales y X2/X3 en OE (para el modelo)
    for k, v in (pos.get('temp_oe') or {}).items():
        fila[k] = v
    for k, v in (pos.get('x2_oe') or {}).items():
        fila[f'x2_{k}'] = v
    for k, v in (pos.get('x3_oe') or {}).items():
        fila[f'x3_{k}'] = v
    # Features en OA
    for k, v in (pos.get('temp_oa') or {}).items():
        fila[f'{k}_oa'] = v
    for k, v in (pos.get('x2_oa') or {}).items():
        fila[f'x2_{k}_oa'] = v
    for k, v in (pos.get('x3_oa') or {}).items():
        fila[f'x3_{k}_oa'] = v
    return fila


def _fila_periodica(activo: str, ciclo: int, tipo_ciclo: str, params: dict,
                     ts: pd.Timestamp, estado: dict, pnl_flotante: float,
                     temp: dict, x2: dict, x3: dict,
                     precio_actual: float, lote: float, units: int,
                     ultimas_5_oc: list) -> dict:
    ctx = _contexto_operativo(estado, precio_actual, lote, units, ultimas_5_oc)
    fila = {
        'tipo_registro': 'periodico', 'activo': activo, 'ciclo': ciclo, 'tipo_ciclo': tipo_ciclo,
        'timestamp_oe': '', 'timestamp_oa': '', 'timestamp_oc': '',
        'timestamp_registro': ts.isoformat(),
        'n_ejecucion': params['n_ejecucion'], 'K': params['K'], 'N_EXP': params['N_EXP'],
        'LAMBDA': params['LAMBDA'], 'A': params['A'], 'B': params['B'],
        'LOTAJES_M': params['LOTAJES_M'],
        'precio_entrada': '', 'precio_salida': '', 'pnl_usd': '',
        'retorno_pct': '', 'pnl_flotante_activo': round(pnl_flotante, 4),
        'pnl_cerrado_activo_sesion': round(estado['pnl_cerrado'], 4),
        **ctx,
    }
    for k, v in temp.items():
        fila[k] = v
    for k, v in x2.items():
        fila[f'x2_{k}'] = v
    for k, v in x3.items():
        fila[f'x3_{k}'] = v
    return fila


# ─── Backtester por activo ────────────────────────────────────────────────────

def _cargar_h1(activo: str) -> pd.DataFrame | None:
    path = cfg.CARPETA_DATA / f'{activo}.csv'
    if not path.exists():
        print(f'[{activo}] Sin datos H1 en {path}. Saltando.')
        return None
    df = pd.read_csv(path)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df = (df.sort_values('DateTime')
            .drop_duplicates(subset=['DateTime'])
            .reset_index(drop=True))
    df = df[df['DateTime'] >= pd.Timestamp(cfg.FECHA_INICIAL)].reset_index(drop=True)
    if len(df) == 0:
        print(f'[{activo}] Sin datos desde {cfg.FECHA_INICIAL}.')
        return None
    return df.set_index('DateTime')


def _backtester_activo(activo: str, stop_event: multiprocessing.Event,
                        max_ciclos: int | None = None):
    """Loop de backtesting para un activo. Corre hasta que stop_event se active."""
    print(f'[{activo}] Iniciando...')

    df_h1 = _cargar_h1(activo)
    if df_h1 is None:
        return

    x2_history = _cargar_x2_history()
    x3_df = _cargar_x3(activo)

    # Restaurar checkpoint
    ckpt = _cargar_ckpt(activo)
    if ckpt:
        ciclo = ckpt['ciclo']
        tipo_ciclo = ckpt['tipo_ciclo']
        params = ckpt['params']
        ts_ultimo = pd.Timestamp(ckpt['ts_ultimo']) if ckpt.get('ts_ultimo') else None
        estado = _deserializar_estado(ckpt['estado'])
        ultimas_5_oc = ckpt.get('ultimas_5_oc', [])
        n_oc_total = ckpt.get('n_oc_total', 0)
        print(f'[{activo}] Retomando ciclo {ciclo} ({tipo_ciclo}) | OC acumuladas: {n_oc_total}')
    else:
        ciclo = 0
        tipo_ciclo = 'explotacion'
        params = _params_baseline(activo)
        ts_ultimo = None
        estado = _estado_inicial()
        ultimas_5_oc = []
        n_oc_total = 0

    lote = cfg.MIN_LOTAJES[activo] * params['LOTAJES_M']
    units = cfg.UNITS[activo]
    soportes = []
    velas_en_ciclo = 0
    filas_buffer: list[dict] = []

    while not stop_event.is_set():
        # Inicio de nuevo ciclo
        ciclo_completo = ts_ultimo is not None and ts_ultimo >= df_h1.index[-1]
        if ts_ultimo is None or ciclo_completo:
            if ciclo > 0:
                _flush_store(activo, filas_buffer)
                print(f'[{activo}] Ciclo {ciclo} completado ({tipo_ciclo}) | OC total: {n_oc_total}')

            if max_ciclos is not None and ciclo >= max_ciclos:
                print(f'[{activo}] Límite de {max_ciclos} ciclos alcanzado.')
                break

            ciclo += 1
            tipo_ciclo = 'exploracion' if random.random() < cfg.X5_EXPLORATION_RATE else 'explotacion'
            params = _samplear_params(activo) if tipo_ciclo == 'exploracion' else _params_baseline(activo)
            lote = cfg.MIN_LOTAJES[activo] * params['LOTAJES_M']
            estado = _estado_inicial()
            ultimas_5_oc = []
            ts_ultimo = None
            velas_en_ciclo = 0
            soportes = []
            print(f'[{activo}] Ciclo {ciclo} | {tipo_ciclo} | '
                  f'A={params["A"]:.1f} B={params["B"]:.1f} '
                  f'N={params["n_ejecucion"]} LM={params["LOTAJES_M"]}')

        # Loop de velas
        for ts, candle in df_h1.iterrows():
            if stop_event.is_set():
                break
            if ts_ultimo is not None and ts <= ts_ultimo:
                continue

            # Actualizar soportes periódicamente
            if velas_en_ciclo % cfg.X5_RECALC_SOPORTES_CADA == 0:
                n_full = params['n_ejecucion']
                todos = _cargar_soportes(activo, n_full, ts)
                soportes = todos[:n_full]

            # Snapshots de esta vela
            temp = _features_temporales(ts)
            x2 = _x2_snapshot(activo, ts, x2_history)
            x3 = _x3_snapshot(ts, x3_df)
            precio_actual = float(candle['Close'])

            # P&L flotante actual
            L = lote * units
            pnl_flotante = sum((precio_actual - p) * L for p in estado['oa'])

            # Procesar vela
            trades = _procesar_vela(
                ts, candle, soportes, estado, params,
                lote, units, x2, x3, temp, ultimas_5_oc,
            )

            # Registrar OCs
            for tc in trades:
                ret = tc['pnl'] / (tc['precio_ap'] * L) if tc['precio_ap'] * L != 0 else 0.0
                ultimas_5_oc = (ultimas_5_oc + [ret])[-5:]
                n_oc_total += 1
                filas_buffer.append(_fila_oc(activo, ciclo, tipo_ciclo, params, tc, estado, ultimas_5_oc))

            # Registrar periódico (solo si hay posiciones abiertas)
            if velas_en_ciclo % cfg.X5_FREQ_REGISTRO_PERIODICO == 0 and len(estado['oa']) > 0:
                filas_buffer.append(_fila_periodica(
                    activo, ciclo, tipo_ciclo, params, ts, estado, pnl_flotante,
                    temp, x2, x3, precio_actual, lote, units, ultimas_5_oc,
                ))

            ts_ultimo = ts
            velas_en_ciclo += 1

            # Checkpoint periódico
            if velas_en_ciclo % cfg.X5_CKPT_INTERVAL == 0:
                _flush_store(activo, filas_buffer)
                _guardar_ckpt(activo, ciclo, tipo_ciclo, params,
                               ts_ultimo.isoformat(), _serializar_estado(estado),
                               ultimas_5_oc, n_oc_total)

        # Fin del recorrido de velas (ciclo completo o stop)
        _flush_store(activo, filas_buffer)
        _guardar_ckpt(activo, ciclo, tipo_ciclo, params,
                       ts_ultimo.isoformat() if ts_ultimo else None,
                       _serializar_estado(estado), ultimas_5_oc, n_oc_total)

        if stop_event.is_set():
            break

    print(f'[{activo}] Detenido. Ciclo {ciclo} | OC totales: {n_oc_total}')


# ─── Status ───────────────────────────────────────────────────────────────────

def _mostrar_status():
    print(f'\n{"═" * 55}')
    print(f'  X5 — Estado del backtesting')
    print(f'{"═" * 55}')
    for activo in cfg.VALORES:
        ckpt = _cargar_ckpt(activo)
        store = _store_path(activo)
        n_filas = 0
        n_oc = 0
        if store.exists():
            with open(store) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    n_filas += 1
                    if row.get('tipo_registro') == 'oc':
                        n_oc += 1
        if ckpt:
            print(f'  {activo:<8}  ciclo={ckpt["ciclo"]:>4}  '
                  f'{ckpt["tipo_ciclo"]:<12}  '
                  f'filas={n_filas:>6}  oc={n_oc:>5}  '
                  f'ts={ckpt.get("ts_ultimo", "—")[:10]}')
        else:
            print(f'  {activo:<8}  sin checkpoint  filas={n_filas:>6}  oc={n_oc:>5}')
    print(f'{"═" * 55}\n')


# ─── Orchestrador ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='X5 Backtester — genera store para el surrogate model')
    parser.add_argument('--activo', help='Correr solo este activo')
    parser.add_argument('--ciclos', type=int, default=None, help='Límite de ciclos por activo')
    parser.add_argument('--status', action='store_true', help='Mostrar progreso y salir')
    parser.add_argument('--reset', action='store_true', help='Descartar checkpoints y partir de cero')
    args = parser.parse_args()

    if args.status:
        _mostrar_status()
        return

    activos = [args.activo] if args.activo else cfg.VALORES

    if args.reset:
        for activo in activos:
            p = _ckpt_path(activo)
            if p.exists():
                p.unlink()
                print(f'  [{activo}] Checkpoint eliminado.')

    stop_event = multiprocessing.Event()

    procesos = []
    for activo in activos:
        p = multiprocessing.Process(
            target=_backtester_activo,
            args=(activo, stop_event, args.ciclos),
            name=f'x5-{activo}',
            daemon=True,
        )
        procesos.append(p)

    print(f'\nIniciando backtesting X5 — {len(activos)} activo(s) en paralelo')
    print('Ctrl+C para detener (se guarda checkpoint antes de salir)\n')

    for p in procesos:
        p.start()

    try:
        for p in procesos:
            p.join()
    except KeyboardInterrupt:
        print('\nDeteniendo... guardando checkpoints.')
        stop_event.set()
        for p in procesos:
            p.join(timeout=15)
        print('Listo.')


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    main()
