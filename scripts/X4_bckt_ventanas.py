"""
X4_bckt_ventanas.py

Backtesting inteligente por ventanas semanales (docs/plans/plan_x5_alt_v2.md, sección 9.14) para un valor. Una
ventana es una semana de backtest que parte en `t*`: cuenta nueva de 3000 USD con `lotajes_m = 1`, una sola búsqueda
de soportes en `t*` (sin warm start, tope `TIEMPO_MAX_BUSQUEDA_VENTANA_MIN`) y label `Y = cerrado + P&L abierto − 3000`.

Importa de X4S_backtesting_inteligente.py los C1, la config de X4 y el registro, y de X4_backtester.py el paso por vela
y la búsqueda de soportes; no reimplementa X0 ni X1. Un proceso por valor.

Orquestador (Q5-4): `t* ∈ [0, T]` es el índice de vela H1 desde `FECHA_INICIO_BT` (`t = 0`), con `T` el mayor `t` cuya
semana completa cabe en los datos. En cada visita se elige un `t*` con `visitas(t*) = min_t visitas(t)`; los empates se
resuelven por bisección (0, T, T/2, T/4, 3T/4, ...), así que cualquier corte deja cobertura pareja de la historia. Al
visitarlos todos empieza otra ronda, y si llegan datos nuevos sus `t` (0 visitas) entran primero. Las visitas se leen de
`{valor}_ventanas.csv`: volver a lanzar el script reanuda.

Cada `t*` es reservado (`FRACCION_RESERVADA`, hash fijo de semilla, valor y `t*`) o de aprendizaje:
  reservado     corre la configuración estática (`estatica`) y los C2 de Q4 (`q4`) con las mismas reglas de cuenta; cada
                ronda repite ambas con otra semilla de la intra-vela, lo que mide el ruido de `Y` (`replica_de`)
  aprendizaje   corre unos C2 sorteados por Sobol (`sobol`); cuando exista Q5-5 los entregará el aprendizaje

`t*` es la vela donde se buscan los soportes (queda congelada, como en X4); la semana operada son las velas siguientes
hasta `t* + VENTANA_DIAS` días y `C_0` es el cierre de `t*`.

Registro en resources/x5_alt/q5/:
  {valor}_ventanas.csv          una fila por ventana
  ventanas/{valor}/{id}/        trades.json, events.json, equity_*.csv, conjuntos_N/ y x4.log (lo que imprime X4)

Uso:
  python scripts/X4_bckt_ventanas.py --activo BTCUSD                      # corre hasta Ctrl+C; volver a lanzar reanuda
  python scripts/X4_bckt_ventanas.py --activo BTCUSD --max_ventanas 32
  python scripts/X4_bckt_ventanas.py --activo BTCUSD --t_star 0 500       # solo la siguiente visita de esos t*
"""

import argparse
import contextlib
import datetime
import hashlib
import io
import sys
import time
import warnings
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.stats import qmc

sys.path.insert(0, str(Path(__file__).parent))
import config as gc
import config_smart
import X4_backtester as x4
import X4S_backtesting_inteligente as s
from x5_alt_funciones import drawdown_maximo, estadisticas_c1, rangos_sorteo_c2

FASES_RESERVADA = ('estatica', 'q4')
COLUMNAS_REGISTRO = ['id', 'ts_star', 'ronda', 'tramo', 'fase']


# ─── Datos ────────────────────────────────────────────────────────────────────

def cargar_datos(valor: str, previo: dict | None = None) -> dict:
    """H1 desde `FECHA_INICIO_BT` (se relee siempre: es barato y puede traer velas nuevas) y M1 completo (se relee solo
    si el archivo cambió: son millones de filas)."""
    cfg = SimpleNamespace(valores=[valor], fecha_inicio=config_smart.FECHA_INICIO_BT,
                          CARPETA_DATA=gc.CARPETA_DATA, CARPETA_DATA_MINUTO=gc.CARPETA_DATA_MINUTO)
    with contextlib.redirect_stdout(io.StringIO()):
        h1 = x4._cargar_datos_h1(cfg).get(valor)
    if h1 is None:
        raise SystemExit(f'Sin datos H1 de {valor} desde {cfg.fecha_inicio}.')
    ruta_m1 = gc.CARPETA_DATA_MINUTO / f'{valor}.csv'
    mtime = ruta_m1.stat().st_mtime if ruta_m1.exists() else None
    if previo is not None and previo['mtime_m1'] == mtime:
        m1 = previo['m1']
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            m1 = x4._cargar_datos_m1(cfg).get(valor)
    return {'h1': h1, 'm1': m1, 'mtime_m1': mtime}


def t_maximo(indice: pd.DatetimeIndex) -> int:
    """`T`: mayor `t` cuya semana completa cabe en los datos (`indice[t] + VENTANA_DIAS <= indice[-1]`). En crypto,
    con 1.000 + 168 velas, es 1.000. En acciones exige una vela en o después del cierre de la ventana, así que no hay
    ventanas cortadas por el fin de los datos."""
    limite = indice[-1] - pd.Timedelta(days=config_smart.VENTANA_DIAS)
    t = int(indice.searchsorted(limite, side='right')) - 1
    if t < 0:
        raise SystemExit('Los datos no alcanzan para una ventana completa.')
    return t


# ─── Selección de t* ──────────────────────────────────────────────────────────

def orden_biseccion(T: int) -> list:
    """Todos los `t` de 0 a `T` por bisección: los extremos, el punto medio, los puntos medios de esos intervalos, etc.
    Con T = 1000: 0, 1000, 500, 250, 750, 125, 375, 625, 875, ..."""
    orden = [0] if T == 0 else [0, T]
    cola = deque([(0, T)])
    while cola:
        a, b = cola.popleft()
        m = (a + b) // 2
        if m <= a or m >= b:
            continue
        orden.append(m)
        cola.append((a, m))
        cola.append((m, b))
    return orden


def elegir_t_star(visitas: dict, T: int, preferidos=()) -> int:
    """Un `t*` con `visitas(t*) = min_t visitas(t)` (los `t` sin registro tienen 0). Entre los de mínimo, primero uno de
    `preferidos` (visita a medias: completarla no cuesta una búsqueda de más) y, si no, el primero en orden de bisección."""
    orden = np.array(orden_biseccion(T))
    v = np.zeros(T + 1, dtype=int)
    for t, n in visitas.items():
        if 0 <= t <= T:
            v[t] = n
    en_minimo = orden[v[orden] == v.min()]
    preferidos = set(preferidos)
    return int(next((t for t in en_minimo if int(t) in preferidos), en_minimo[0]))


def es_reservada(valor: str, ts_star, semilla: int | None = None) -> bool:
    """Un `t*` es reservado si un hash fijo de (semilla, valor, `t*`) cae bajo `FRACCION_RESERVADA`. No depende de cuántas
    ventanas se hayan corrido: cada `t` tiene su condición desde siempre."""
    semilla = config_smart.SEMILLA_RESERVADAS if semilla is None else semilla
    h = hashlib.sha256(f'{semilla}|{valor}|{pd.Timestamp(ts_star).isoformat()}'.encode()).digest()
    return int.from_bytes(h[:8], 'big') / 2**64 < config_smart.FRACCION_RESERVADA


# ─── Registro y visitas ───────────────────────────────────────────────────────

def ruta_ventanas(valor: str) -> Path:
    return gc.CARPETA_Q5 / f'{valor}_ventanas.csv'


def leer_registro(valor: str) -> pd.DataFrame:
    ruta = ruta_ventanas(valor)
    if not ruta.exists():
        return pd.DataFrame(columns=COLUMNAS_REGISTRO)
    df = pd.read_csv(ruta)
    df['ts_star'] = pd.to_datetime(df['ts_star'])
    return df


def contar_visitas(df: pd.DataFrame, indice: pd.DatetimeIndex) -> tuple:
    """(visitas completas por `t`, {t: (ronda, fases hechas)} de las visitas a medias). Una visita de aprendizaje es una
    ventana; una reservada son dos (`estatica` y `q4`). Las filas cuyo `ts_star` ya no está en los datos se ignoran."""
    posicion = {ts: i for i, ts in enumerate(indice)}
    visitas, parciales = {}, {}
    for (ts, ronda), g in df.groupby(['ts_star', 'ronda']):
        t = posicion.get(pd.Timestamp(ts))
        if t is None:
            continue
        completa = g['tramo'].iloc[0] != 'reservada' or set(FASES_RESERVADA) <= set(g['fase'])
        if completa:
            visitas[t] = visitas.get(t, 0) + 1
        else:
            parciales[t] = (int(ronda), set(g['fase']))
    return visitas, parciales


def ventanas_de_aprendizaje(df: pd.DataFrame) -> pd.DataFrame:
    """Ventanas que pueden entrar al aprendizaje: las de `tramo = aprendizaje` que no se solapan en velas con ninguna
    reservada (dos ventanas se solapan si sus `t*` distan menos de `VENTANA_DIAS`). Se calcula al leer, no al correr,
    porque una reservada visitada después cambia el estado de las de aprendizaje que ya estaban registradas."""
    aprendizaje = df[df['tramo'] == 'aprendizaje']
    reservadas = np.sort(df.loc[df['tramo'] == 'reservada', 'ts_star'].drop_duplicates().to_numpy())
    if len(reservadas) == 0 or aprendizaje.empty:
        return aprendizaje
    ts = aprendizaje['ts_star'].to_numpy()
    ancho = np.timedelta64(config_smart.VENTANA_DIAS, 'D')
    izq = np.searchsorted(reservadas, ts - ancho, side='right')  # primera reservada con t_res > ts - ancho
    der = np.searchsorted(reservadas, ts + ancho, side='left')   # primera reservada con t_res >= ts + ancho
    return aprendizaje[izq == der]


# ─── C2 por Sobol ─────────────────────────────────────────────────────────────

def _dimensiones(c2_base: dict) -> tuple:
    """(rangos de cada C1, dimensiones libres). Una dimensión libre es un peso, `span`, `punto_medio` o `pendiente` con
    rango (min < max); un C1 con una variable o una variable sin peso base no sortea ese peso."""
    rangos = {c1: rangos_sorteo_c2(c2) for c1, c2 in c2_base.items()}
    libres = []
    for c1, r in rangos.items():
        libres += [(c1, 'peso', nombre, lo, hi) for nombre, (lo, hi) in r['pesos'].items() if hi > lo]
        libres += [(c1, campo, None, *r[campo]) for campo in ('span', 'punto_medio', 'pendiente')]
    return rangos, libres


def punto_sobol(d: int, k: int, semilla: int | None = None) -> np.ndarray:
    """Punto `k` (desde 0) de la secuencia Sobol con scramble de `d` dimensiones: el mismo `k` da el mismo punto, así una
    ventana interrumpida y repetida sortea los mismos C2."""
    semilla = config_smart.SEMILLA_SOBOL if semilla is None else semilla
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')  # scipy avisa si el total de puntos no es potencia de 2
        sampler = qmc.Sobol(d=d, scramble=True, seed=semilla)
        if k:
            sampler.fast_forward(k)
        return sampler.random(1)[0]


def sortear_c2(c2_base: dict, k: int, semilla: int | None = None) -> dict:
    """C2 completos de la ventana de aprendizaje `k` (desde 0), sorteados con Sobol en los rangos cercanos a Q4
    (`rangos_sorteo_c2`). Los pesos van sin normalizar; `span` se redondea a entero."""
    rangos, libres = _dimensiones(c2_base)
    c2 = {c1: {'pesos': {n: lo for n, (lo, _) in r['pesos'].items()}, 'span': int(round(r['span'][0])),
               'punto_medio': r['punto_medio'][0], 'pendiente': r['pendiente'][0]} for c1, r in rangos.items()}
    for u, (c1, campo, nombre, lo, hi) in zip(punto_sobol(len(libres), k, semilla), libres):
        v = lo + u * (hi - lo)
        if campo == 'peso':
            c2[c1]['pesos'][nombre] = float(v)
        else:
            c2[c1][campo] = int(round(v)) if campo == 'span' else float(v)
    return c2


# ─── Una ventana ──────────────────────────────────────────────────────────────

def ejecutar_ventana(valor: str, t_star: int, c1: pd.DataFrame, carpeta: Path, semilla: int, datos: dict,
                     id_ventana: str) -> dict:
    """Corre la ventana que parte en `t_star` con los C1 de `c1` (índice DateTime, columnas N, K, N_EXP, LAMBDA, A,
    factor_B, p; mismas reglas que `ejecutar_vuelta` de X4S).

    Los C1 del grupo de búsqueda (N, K, N_EXP, LAMBDA) se leen de la fila de `t*`, los mismos datos de la búsqueda; los
    de operación, de la fila de la vela anterior. La cuenta parte limpia (3000 USD, sin órdenes) con `lotajes_m = 1` y
    umbral de pérdida `p · 3000`; el tope de Órdenes Abiertas (OA) lo aplica X4 con `R_TOPE_OA`. Las Órdenes en Espera
    (OE) que queden al cierre se cancelan sin efecto y las OA se valoran a mercado. El stop-out no corta la ventana.
    Lo que imprime X4 va a `x4.log` en `carpeta`."""
    h1, m1 = datos['h1'], datos['m1']
    cfg = s.construir_cfg(valor, carpeta, semilla)
    cfg.X5_WARM_START_SOPORTES = False
    cfg.TIEMPO_MAX_BUSQUEDA_MIN = config_smart.TIEMPO_MAX_BUSQUEDA_VENTANA_MIN
    cfg.CARPETA_N_BT.mkdir(parents=True, exist_ok=True)
    capital = cfg.capital_inicial

    ts_star = h1.index[t_star]
    velas = h1[(h1.index > ts_star) & (h1.index <= ts_star + pd.Timedelta(days=config_smart.VENTANA_DIAS))]
    n = len(velas)
    c1 = c1.reindex(h1.index, method='ffill')
    necesarias = c1.loc[[ts_star, *velas.index]]
    faltantes = necesarias.columns[necesarias.isna().any()].tolist()
    if faltantes:
        raise ValueError(f'C1 sin valor en {faltantes} en la ventana de t*={ts_star}: la tabla de Q1 no la cubre')
    c1_op = s.c1_operacion(c1)

    estado = {'capital': capital, 'GC_global': 0.0,
              'por_activo': {valor: {'soportes': [], 'OE': {}, 'OA': {}, 'GC': 0.0}},
              'ts_ultimo_procesado': None, 'ts_ultimo_recalculo': None}
    trades_log: list = []
    events_log: list = []
    equity = np.full(n, np.nan)
    en_mercado = np.zeros(n, dtype=bool)
    margen_usado = np.zeros(n)
    aplicado = {k: np.full(n, np.nan) for k in ('A', 'B', 'factor_B', 'p', 'umbral_usd')}
    stop_outs, en_stop_out = 0, False
    consola = sys.stdout
    t0 = time.monotonic()

    with open(carpeta / 'x4.log', 'a', encoding='utf-8') as log, contextlib.redirect_stdout(log):
        print(f'[{valor} | {id_ventana}] t*={ts_star} ({t_star}): buscando soportes, luego {n} velas hasta '
              f'{velas.index[-1]}', file=consola, flush=True)
        info = s._buscar_soportes(estado, cfg, valor, ts_star, c1.loc[ts_star], None)
        if not estado['por_activo'][valor]['soportes']:
            raise RuntimeError(f'[{valor}] {ts_star}: la búsqueda no entregó soportes')
        for i, (ts, candle) in enumerate(velas.iterrows()):
            fila = c1_op.loc[ts]
            cfg.A = float(fila['A'])
            cfg.B = float(fila['factor_B']) * cfg.A
            cfg.PERDIDA_MAX_BT = float(fila['p']) * capital
            precios = {valor: candle['Close']}
            x4._procesar_candle(ts, candle, valor, estado['por_activo'][valor], estado, m1, precios,
                                cfg.n_sizes[valor], cfg, events_log, trades_log)
            mc = x4._append_equity(ts, estado, precios, cfg)
            estado['ts_ultimo_procesado'] = ts.isoformat()

            equity[i], en_mercado[i], margen_usado[i] = mc['equity'], mc['n_OA'] > 0, mc['margen_usado']
            for nombre, v in (('A', cfg.A), ('B', cfg.B), ('factor_B', float(fila['factor_B'])),
                              ('p', float(fila['p'])), ('umbral_usd', cfg.PERDIDA_MAX_BT)):
                aplicado[nombre][i] = v

            ml = mc['margin_level']
            quemada = mc['equity'] <= 0 or (ml is not None and mc['margen_usado'] > 0 and ml <= cfg.STOP_OUT_LEVEL)
            if quemada and not en_stop_out:
                stop_outs += 1
                events_log.append({'tipo': 'stop_out', 'ts': ts.isoformat(), 'equity': round(mc['equity'], 4),
                                   'balance': round(mc['balance'], 4), 'margen_usado': round(mc['margen_usado'], 4),
                                   'margin_level': round(ml, 4) if ml is not None else None, 'n_OA': mc['n_OA']})
                print(f'[{valor} | {id_ventana}] *** STOP OUT {ts}: Z={mc["equity"]:,.2f} (la ventana sigue) ***',
                      file=consola, flush=True)
            en_stop_out = quemada
        x4._flush_json_list(trades_log, carpeta / 'trades.json')
        x4._flush_json_list(events_log, carpeta / 'events.json')

    cierres = np.r_[float(h1['Close'].iloc[t_star]), velas['Close'].to_numpy(dtype=float)]
    retornos_h = cierres[1:] / cierres[:-1] - 1
    est_a = estado['por_activo'][valor]
    z_final = float(equity[-1])
    return {
        'valor': valor, 'id': id_ventana, 't_star': t_star, 'ts_star': ts_star, 'indice': velas.index,
        'equity': equity, 'en_mercado': en_mercado, 'margen_usado': margen_usado, 'aplicado': aplicado,
        'retornos_trades': [t['retorno_usd'] for t in trades_log], 'stop_outs': stop_outs, 'info': info,
        'c1_busqueda': {k: float(c1.loc[ts_star, k]) for k in s.C1_BUSQUEDA},
        'Y': z_final - capital, 'cerrado': estado['capital'] - capital, 'pnl_abierto': z_final - estado['capital'],
        'n_OA_cierre': len(est_a['OA']), 'n_OE_cierre': len(est_a['OE']),
        'ret_medio': float(retornos_h.mean()), 'ret_vol': float(retornos_h.std(ddof=1)) if n >= 2 else float('nan'),
        'semilla': semilla, 'duracion_s': time.monotonic() - t0,
    }


def resumir_ventana(res: dict, c2: dict | None, estructura: dict, tramo: str, fase: str, ronda: int,
                    replica_de: str, version_estructura: int) -> dict:
    """Fila de `{valor}_ventanas.csv` (plan 9.14 y 9.10): identificación, C2 completos (todas las variables de la
    estructura, las no usadas valen 0), C1 de la ventana, `Y`, variables de mercado y KPIs. `c2` es None en la estática."""
    valor, equity = res['valor'], res['equity']
    capital = config_smart.CUENTA['capital_inicial']
    dd_pct, dd_usd = drawdown_maximo(equity, capital)
    ret = np.array(res['retornos_trades'], dtype=float)
    n_posiciones = len(ret) + res['n_OA_cierre']  # cada posición abierta en la ventana o cerró (trade) o sigue abierta
    info = res['info'] or {}
    fila = {
        'id': res['id'], 'valor': valor, 't_star': res['t_star'], 'ts_star': str(res['ts_star']), 'tramo': tramo,
        'fase': fase, 'ronda': ronda, 'replica_de': replica_de, 'semilla': res['semilla'],
        'version_estructura': version_estructura,
        'fecha_ejecucion': datetime.datetime.now().isoformat(timespec='seconds'),
        'ts_fin': str(res['indice'][-1]), 'n_velas': len(equity),
    }
    if c2 is not None:
        for c1_nombre, entrada in estructura.items():
            c = c2[c1_nombre]
            for v in entrada['variables']:
                fila[f'c2_{c1_nombre}_w_{v["nombre"]}'] = float(c['pesos'].get(v['nombre'], 0.0))
            fila[f'c2_{c1_nombre}_span'] = int(c['span'])
            fila[f'c2_{c1_nombre}_punto_medio'] = float(c['punto_medio'])
            fila[f'c2_{c1_nombre}_pendiente'] = float(c['pendiente'])
    fila.update({f'c1_{k}': v for k, v in res['c1_busqueda'].items()})
    for nombre in s.C1_OPERACION:
        piso, techo = config_smart.rango(s.CLAVE_RANGO[nombre], valor)
        for k, v in estadisticas_c1(res['aplicado'][nombre], piso, techo).items():
            fila[f'c1_{nombre}_{k}'] = v
    fila.update({
        'Y': res['Y'], 'cerrado': res['cerrado'], 'pnl_abierto': res['pnl_abierto'],
        'ret_medio': res['ret_medio'], 'ret_vol': res['ret_vol'],
        'drawdown_max_pct': 100 * dd_pct, 'drawdown_max_usd': dd_usd,
        'n_trades': len(ret), 'tasa_aciertos_pct': float(100 * (ret > 0).mean()) if len(ret) else float('nan'),
        'tiempo_en_mercado_pct': float(100 * res['en_mercado'].mean()),
        'margen_usado_prom': float(res['margen_usado'].mean()), 'margen_usado_max': float(res['margen_usado'].max()),
        'stop_outs': res['stop_outs'], 'n_OA_cierre': res['n_OA_cierre'], 'n_OE_cierre': res['n_OE_cierre'],
        'frac_oa_abiertas_cierre': res['n_OA_cierre'] / n_posiciones if n_posiciones else float('nan'),
        'sin_trades': n_posiciones == 0,
        'FO_inicial': info.get('FO_inicial'), 'FO_final': info.get('FO_final'), 'convergio': info.get('convergio'),
        'busqueda_s': info.get('duracion'), 'busqueda_cortada': bool(info.get('tiempo_agotado', False)),
        'duracion_min': res['duracion_s'] / 60,
    })
    return fila


def formatear_resumen_ventana(fila: dict) -> list:
    """Cierre de la ventana en pantalla: `Y`, variables de mercado y KPIs, con el prefijo `[valor | id]`."""
    pre = f'[{fila["valor"]} | {fila["id"]}]'
    aciertos = fila['tasa_aciertos_pct']
    frac = fila['frac_oa_abiertas_cierre']
    cierre = ('cortada por tope de tiempo' if fila['busqueda_cortada']
              else 'convergió' if fila['convergio'] else 'sin converger')
    return [
        f'{pre} FIN {fila["tramo"]}/{fila["fase"]} ronda {fila["ronda"]}: Y {fila["Y"]:+,.2f} USD (cerrado '
        f'{fila["cerrado"]:+,.2f}, P&L abierto {fila["pnl_abierto"]:+,.2f}) | ret medio {100 * fila["ret_medio"]:+.3f}% '
        f'vol {100 * fila["ret_vol"]:.3f}% por hora | {fila["duracion_min"]:.1f} min',
        f'{pre}   KPIs    : {fila["n_trades"]} trades ({"—" if pd.isna(aciertos) else f"{aciertos:.0f}%"} ganados) | '
        f'{fila["n_OA_cierre"]} OA y {fila["n_OE_cierre"]} OE al cierre'
        f'{"" if pd.isna(frac) else f" ({100 * frac:.0f}% de las posiciones sigue abierta)"}'
        f'{" | SIN TRADES" if fila["sin_trades"] else ""} | drawdown máx {fila["drawdown_max_pct"]:.1f}% | '
        f'stop-outs {fila["stop_outs"]}',
        f'{pre}   C1      : N {fila["c1_N"]:.0f} | K {fila["c1_K"]:.1f} | N_EXP {fila["c1_N_EXP"]:.1f} | '
        f'LAMBDA {fila["c1_LAMBDA"]:.2f} | A prom {fila["c1_A_media"]:.1f} | p prom {fila["c1_p_media"]:.3f} | '
        f'FO {fila["FO_inicial"]:.1e} -> {fila["FO_final"]:.1e} ({cierre}, {fila["busqueda_s"]:.0f} s)',
    ]


# ─── Orquestador ──────────────────────────────────────────────────────────────

def c1_de_la_ventana(fase: str, valor: str, tabla: pd.DataFrame, estructura: dict, c2: dict | None) -> pd.DataFrame:
    if fase == 'estatica':
        return s.c1_estaticos(valor, pd.DatetimeIndex(tabla['DateTime']))
    return s.c1_dinamicos(valor, c2, tabla, estructura)


def correr_ventana(valor: str, t_star: int, ronda: int, tramo: str, fase: str, c2: dict | None, datos: dict,
                   tabla: pd.DataFrame, estructura: dict, semilla_base: int) -> dict:
    """Corre una ventana y la registra en `{valor}_ventanas.csv`; devuelve la fila. `ronda` cambia la semilla de la
    intra-vela y de la búsqueda (`semilla_base + ronda - 1`): las dos configuraciones de un `t*` reservado comparten
    semilla (control pareado) y las rondas siguientes son réplicas de la primera."""
    id_ventana = f'{valor}_t{t_star:06d}_r{ronda}_{fase}'
    replica_de = f'{valor}_t{t_star:06d}_r1_{fase}' if ronda > 1 and tramo == 'reservada' else ''
    carpeta = gc.CARPETA_Q5 / 'ventanas' / valor / id_ventana
    s.preparar_carpeta(carpeta, reset=True)
    c1 = c1_de_la_ventana(fase, valor, tabla, estructura, c2)
    res = ejecutar_ventana(valor, t_star, c1, carpeta, semilla_base + ronda - 1, datos, id_ventana)
    fila = resumir_ventana(res, c2, estructura, tramo, fase, ronda, replica_de,
                           s.registrar_version_estructura(valor, estructura))
    s.agregar_fila_csv(ruta_ventanas(valor), fila)
    for linea in formatear_resumen_ventana(fila):
        print(linea, flush=True)
    return fila


def correr_visita(valor: str, t_star: int, datos: dict, tabla: pd.DataFrame, estructura: dict, c2_q4: dict,
                  semilla_base: int) -> list:
    """Una visita a `t_star`: la ventana de aprendizaje o, si es reservado, la estática y la de Q4. Retoma una visita a
    medias (solo corre las configuraciones que le faltan). Devuelve las filas registradas."""
    ts_star = datos['h1'].index[t_star]
    df = leer_registro(valor)
    visitas, parciales = contar_visitas(df, datos['h1'].index)
    reservada = es_reservada(valor, ts_star)
    ronda = visitas.get(t_star, 0) + 1
    hechas = parciales[t_star][1] if t_star in parciales else set()
    tramo, fases = ('reservada', FASES_RESERVADA) if reservada else ('aprendizaje', ('sobol',))
    print(f'[{valor}] visita a t*={t_star} ({ts_star}) | {tramo} | ronda {ronda} | T={t_maximo(datos["h1"].index)}',
          flush=True)
    filas = []
    for fase in fases:
        if fase in hechas:
            continue
        c2 = {'estatica': None, 'q4': c2_q4}.get(fase)
        if fase == 'sobol':
            c2 = sortear_c2(c2_q4, int((df['fase'] == 'sobol').sum()))
        filas.append(correr_ventana(valor, t_star, ronda, tramo, fase, c2, datos, tabla, estructura, semilla_base))
        df = leer_registro(valor)
    return filas


def _insumos_vigentes(valor: str, previo: dict | None) -> tuple:
    """(datos, tabla de Q1, estructura de C1, C2 de Q4): H1 y M1 recortados a lo que cubre la tabla (sin C1 no hay ventana)."""
    datos = cargar_datos(valor, previo)
    tabla, estructura, c2_q4 = s.cargar_insumos(valor)
    fin = min(datos['h1'].index.max(), pd.Timestamp(tabla['DateTime'].max()))
    datos['h1'] = datos['h1'][datos['h1'].index <= fin]
    return datos, tabla, estructura, c2_q4


def correr(valor: str, semilla_base: int = 0, max_ventanas: int | None = None, max_horas: float | None = None,
           t_stars: list | None = None) -> int:
    """Bucle del orquestador: visita `t*` tras `t*` hasta Ctrl+C, `max_ventanas` o `max_horas`. Con `t_stars` visita solo
    esos y termina. Datos, tabla de Q1 y registro se releen en cada visita, así que los datos nuevos se toman solos.
    Devuelve cuántas ventanas corrió."""
    inicio, corridas, datos = time.monotonic(), 0, None
    pendientes = list(t_stars) if t_stars else None
    try:
        while True:
            if max_ventanas is not None and corridas >= max_ventanas:
                print(f'[{valor}] {corridas} ventanas corridas (--max_ventanas).', flush=True)
                break
            if max_horas is not None and (time.monotonic() - inicio) / 3600 >= max_horas:
                print(f'[{valor}] {max_horas} h cumplidas (--max_horas).', flush=True)
                break
            datos, tabla, estructura, c2_q4 = _insumos_vigentes(valor, datos)
            T = t_maximo(datos['h1'].index)
            if pendientes is not None:
                if not pendientes:
                    break
                t_star = pendientes.pop(0)
                if not 0 <= t_star <= T:
                    raise SystemExit(f't* = {t_star} fuera de [0, {T}].')
            else:
                visitas, parciales = contar_visitas(leer_registro(valor), datos['h1'].index)
                t_star = elegir_t_star(visitas, T, preferidos=parciales)
            corridas += len(correr_visita(valor, t_star, datos, tabla, estructura, c2_q4, semilla_base))
    except KeyboardInterrupt:
        print(f'\n[{valor}] detenido; la ventana en curso no se registró y se rehace al volver a lanzar.', flush=True)
    return corridas


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description='Backtesting inteligente por ventanas semanales para un valor.')
    ap.add_argument('--activo', required=True, choices=gc.VALORES)
    ap.add_argument('--semilla', type=int, default=0, help='semilla base de la intra-vela y de la búsqueda de soportes')
    ap.add_argument('--max_ventanas', type=int, help='detiene el orquestador tras esa cantidad de ventanas')
    ap.add_argument('--max_horas', type=float, help='detiene el orquestador tras esas horas de reloj')
    ap.add_argument('--t_star', type=int, nargs='+',
                    help='visita solo la siguiente ronda de estos t* (índice de vela desde FECHA_INICIO_BT) y termina')
    args = ap.parse_args()
    correr(args.activo, args.semilla, args.max_ventanas, args.max_horas, args.t_star)


if __name__ == '__main__':
    main()
