"""X5-P: piloto exploratorio de operación sobre soportes guardados (BTCUSD, 4 meses).

Los soportes se buscan una vez por semana con la búsqueda de X0 (vía X4, con calentamiento) y se guardan por mes;
después X4 los lee (`SOPORTES_PRECALCULADOS`) y opera el mes completo con cuenta continua para cada configuración
de `A`, `factor_B`, pérdida máxima y tope de OA. Pre-registro: `docs/context/decisiones.md` (2026-11-24).

  caffeinate -i python scripts/X5_piloto.py construir --mes 2023-10   # 1 a 2 h, un proceso por mes
  caffeinate -i python scripts/X5_piloto.py validar              # repite 5 ventanas viejas con sus soportes
  caffeinate -i python scripts/X5_piloto.py grilla               # 81 configuraciones x 4 meses
  caffeinate -i python scripts/X5_piloto.py ruido                # la configuración actual con 2 semillas más
  python scripts/X5_piloto.py analizar                           # tablas del pre-registro sobre resultados.csv
"""
import argparse
import contextlib
import io
import itertools
import json
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import config as gc
import X4_backtester as x4

VALOR = 'BTCUSD'
N = gc.n_sizes_ejecucion[VALOR]
MESES = ['2022-06', '2023-10', '2025-02', '2025-06']
SEMANAS_CALENTAMIENTO = 2
SEMILLA_BUSQUEDA = 7
SEMILLA_INTRAVELA = 1
SEMILLAS_RUIDO = [2, 3]
CAPITAL = 3000.0

ORIGEN_VENTANAS = gc.BASE_DIR / 'X5_otros' / 'resources' / 'x5_alt' / 'q5'
R_TOPE_VENTANAS = 0.5  # `config_smart.R_TOPE_OA` de las ventanas viejas (fase estática)

ACTUAL = {'A': 3.0, 'factor_B': 0.5, 'perdida_max': 200.0, 'r_tope': None}
GRILLA = {'A': [1.5, 3.0, 6.0], 'factor_B': [0.3, 0.5, 0.7],
          'perdida_max': [100.0, 200.0, 300.0], 'r_tope': [None, 0.5, 1.0]}

RAIZ = gc.BASE_DIR / 'resources' / 'x5' / 'piloto'
RESULTADOS = RAIZ / 'resultados.csv'


def carpeta_soportes(mes: str) -> Path:
    return RAIZ / 'soportes' / mes


def construir_cfg(mes: str, params: dict, carpeta_run: Path, semilla: int, precalculados: bool,
                  ini=None, fin=None, cache: Path | None = None, delta_dias: int = 7) -> SimpleNamespace:
    """Config que X4 espera: el mes `mes` completo (o `ini`/`fin`), parámetros de búsqueda de `config.py` y los de
    operación de `params`. `fin` es exclusivo."""
    ini = pd.Timestamp(ini if ini is not None else f'{mes}-01')
    fin = pd.Timestamp(fin) if fin is not None else ini + pd.offsets.MonthBegin(1)
    return SimpleNamespace(
        version=f'piloto_{mes}', valores=[VALOR], n_sizes={VALOR: N},
        fecha_inicio=str(ini), fecha_fin=str(fin),
        capital_inicial=CAPITAL, MARGEN_LIBRE_MIN_BT=50.0, STOP_OUT_LEVEL=50,
        A=params['A'], B=params['factor_B'] * params['A'],
        PERDIDA_MAX_BT=params['perdida_max'], R_TOPE_OA=params['r_tope'],
        delta_recalculo_soportes=delta_dias,  # 7 = semanal, igual que los soportes guardados
        K=gc.K, N_EXP=gc.N_EXP, LAMBDA=gc.LAMBDA,
        LOTAJES={VALOR: gc.MIN_LOTAJES[VALOR] * gc.LOTAJES_M[VALOR]}, MIN_LOTAJES={VALOR: gc.MIN_LOTAJES[VALOR]},
        UNITS={VALOR: gc.UNITS[VALOR]}, APALANCAMIENTO={VALOR: gc.APALANCAMIENTO[VALOR]},
        CARPETA_RESOURCES=carpeta_run, CARPETA_N_BT=cache or carpeta_soportes(mes), CARPETA_LOGS_BT=carpeta_run / 'logs',
        CARPETA_DATA=gc.CARPETA_DATA, CARPETA_DATA_MINUTO=gc.CARPETA_DATA_MINUTO,
        SEMILLA_INTRAVELA=semilla, SEMILLA_BUSQUEDA=SEMILLA_BUSQUEDA, SOPORTES_PRECALCULADOS=precalculados,
    )


# ─── Soportes semanales ───────────────────────────────────────────────────────

def semanas_a_calcular(mes: str) -> list:
    """Un conjunto por semana, desde `SEMANAS_CALENTAMIENTO` antes del mes: así la primera semana del mes ya parte
    de la solución de la anterior y no de una búsqueda en frío."""
    ini = pd.Timestamp(f'{mes}-01')
    fin = ini + pd.offsets.MonthBegin(1)
    return [t for t in (ini + pd.Timedelta(days=7 * k) for k in range(-SEMANAS_CALENTAMIENTO, 5)) if t < fin]


def _ya_calculado(mes: str, ts: pd.Timestamp) -> bool:
    """X0 guarda cada conjunto con la clave del último dato usado (ts o la vela anterior)."""
    archivo = carpeta_soportes(mes) / f'{VALOR}_{N}_bt.json'
    if not archivo.exists():
        return False
    return any(ts - pd.Timedelta(hours=2) < pd.Timestamp(k) <= ts for k in json.loads(archivo.read_text()))


def construir_soportes(mes: str) -> None:
    cfg = construir_cfg(mes, ACTUAL, carpeta_soportes(mes) / 'build', SEMILLA_INTRAVELA, precalculados=False)
    semanas = semanas_a_calcular(mes)
    carpeta_soportes(mes).mkdir(parents=True, exist_ok=True)
    for i, ts in enumerate(semanas, 1):
        if _ya_calculado(mes, ts):
            print(f'[{mes}] {i}/{len(semanas)} {ts} ya estaba', flush=True)
            continue
        t0 = time.time()
        estado = {'por_activo': {VALOR: {'OA': {}, 'soportes': []}}}
        x4._recalcular_soportes(estado, ts, cfg)
        print(f'[{mes}] {i}/{len(semanas)} {ts} listo en {time.time() - t0:.0f} s', flush=True)


# ─── Operar el mes ────────────────────────────────────────────────────────────

def _clave(mes: str, params: dict, semilla: int) -> str:
    r = 'sin' if params['r_tope'] is None else params['r_tope']
    return f"{mes}|{params['A']}|{params['factor_B']}|{params['perdida_max']}|{r}|{semilla}"


def _operar(cfg: SimpleNamespace, carpeta: Path) -> dict:
    """Corre X4 con `cfg` (carpeta propia, borrada al terminar) y resume la cuenta continua."""
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            x4.ejecutar_backtest(cfg, reset=False)
        eq = pd.read_csv(carpeta / 'equity_global.csv')
        trades = carpeta / 'trades.json'
        n_trades = len(json.loads(trades.read_text())) if trades.exists() else 0
        stop_out = bool(json.loads((carpeta / 'checkpoint.json').read_text()).get('stop_out', False))
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    serie = pd.concat([pd.Series([CAPITAL]), eq['equity']], ignore_index=True)
    caida_usd = float((serie.cummax() - serie).max())
    return {
        'resultado_usd': round(float(serie.iloc[-1]) - CAPITAL, 2),
        'cerrado_usd': round(float(eq['balance'].iloc[-1]) - CAPITAL, 2),
        'caida_max_usd': round(caida_usd, 2),
        'caida_max_pct': round(100 * float(((serie.cummax() - serie) / serie.cummax()).max()), 2),
        'n_trades': n_trades, 'max_OA': int(eq['n_OA'].max()), 'n_OA_final': int(eq['n_OA'].iloc[-1]),
        'stop_out': stop_out, 'velas': len(eq), 'segundos': round(time.time() - t0, 1),
    }


def operar_mes(mes: str, params: dict, semilla: int) -> dict:
    RAIZ.mkdir(parents=True, exist_ok=True)
    carpeta = Path(tempfile.mkdtemp(prefix=f'{mes}_', dir=RAIZ))
    cfg = construir_cfg(mes, params, carpeta, semilla, precalculados=True)
    return {'clave': _clave(mes, params, semilla), 'mes': mes, **params, 'semilla': semilla, **_operar(cfg, carpeta)}


# ─── Validación contra las ventanas viejas ────────────────────────────────────

def validar(n: int = 5) -> bool:
    """Repite `n` ventanas de la fase estática del X5 anterior con sus soportes guardados y compara `Y`.

    Las ventanas viejas operaban 168 velas desde la siguiente a t*, con cuenta nueva de 3.000 USD y tope de OA 0,5.
    Se excluyen las que tuvieron stop-out (allí la ventana vieja seguía y X4 se detiene)."""
    d = pd.read_csv(ORIGEN_VENTANAS / f'{VALOR}_ventanas.csv')
    e = d[(d['fase'] == 'estatica') & (d['stop_outs'] == 0) & (d['n_trades'] > 0)].sort_values('ts_star')
    elegidas = e.iloc[[int(i) for i in pd.Series(range(n)).mul(len(e) - 1).div(n - 1).round()]]
    filas = []
    for _, r in elegidas.iterrows():
        ts = pd.Timestamp(r['ts_star'])
        cache = Path(tempfile.mkdtemp(prefix='cache_', dir=RAIZ))
        shutil.copy(ORIGEN_VENTANAS / 'ventanas' / VALOR / r['id'] / 'conjuntos_N' / f'{VALOR}_{N}_bt.json', cache)
        carpeta = Path(tempfile.mkdtemp(prefix='val_', dir=RAIZ))
        params = {'A': r['c1_A_media'], 'factor_B': r['c1_factor_B_media'],
                  'perdida_max': round(r['c1_p_media'] * CAPITAL, 6), 'r_tope': R_TOPE_VENTANAS}
        cfg = construir_cfg('', params, carpeta, int(r['semilla']), precalculados=True, ini=ts,
                            fin=ts + pd.Timedelta(days=7, hours=1), cache=cache, delta_dias=8)
        nuevo = _operar(cfg, carpeta)
        shutil.rmtree(cache, ignore_errors=True)
        filas.append({'id': r['id'], 'Y_viejo': round(r['Y'], 4), 'Y_nuevo': nuevo['resultado_usd'],
                      'dif': round(nuevo['resultado_usd'] - r['Y'], 4), 'velas': nuevo['velas'],
                      'segundos': nuevo['segundos']})
    tabla = pd.DataFrame(filas)
    print(tabla.to_string(index=False))
    ok = bool((tabla['dif'].abs() < 0.01).all())
    print('REPRODUCE (dif < 0,01 USD en todas)' if ok else 'NO REPRODUCE')
    return ok


def _tarea(args: tuple) -> dict:
    return operar_mes(*args)


def ejecutar(tareas: list, workers: int) -> None:
    """Corre las tareas que no están en `resultados.csv` y agrega cada fila apenas termina (se puede reanudar)."""
    hechas = set(pd.read_csv(RESULTADOS)['clave']) if RESULTADOS.exists() else set()
    pendientes = [t for t in tareas if _clave(*t) not in hechas]
    print(f'{len(pendientes)} por correr, {len(tareas) - len(pendientes)} ya estaban', flush=True)
    RAIZ.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futuros = [ex.submit(_tarea, t) for t in pendientes]
        for i, f in enumerate(as_completed(futuros), 1):
            fila = f.result()
            pd.DataFrame([fila]).to_csv(RESULTADOS, mode='a', header=not RESULTADOS.exists(), index=False)
            trans = time.time() - t0
            print(f'{i}/{len(pendientes)} {fila["clave"]} -> {fila["resultado_usd"]:+.0f} USD | '
                  f'faltan ~{trans / i * (len(pendientes) - i) / 60:.0f} min', flush=True)


def tareas_grilla() -> list:
    combos = [dict(zip(GRILLA, v)) for v in itertools.product(*GRILLA.values())]
    return [(mes, p, SEMILLA_INTRAVELA) for p in combos for mes in MESES]


def tareas_ruido() -> list:
    return [(mes, ACTUAL, s) for s in SEMILLAS_RUIDO for mes in MESES]


# ─── Análisis (reglas del pre-registro) ───────────────────────────────────────

def analizar() -> None:
    d = pd.read_csv(RESULTADOS)
    d['r_tope'] = d['r_tope'].fillna('sin').astype(str)
    claves = ['A', 'factor_B', 'perdida_max', 'r_tope']
    pd.set_option('display.width', 200)
    base = d[d['semilla'] == SEMILLA_INTRAVELA]
    actual = base[(base['A'] == ACTUAL['A']) & (base['factor_B'] == ACTUAL['factor_B'])
                  & (base['perdida_max'] == ACTUAL['perdida_max']) & (base['r_tope'] == 'sin')].set_index('mes')
    print('\n== La configuración actual en cada mes (semilla 1) ==')
    print(actual[['resultado_usd', 'caida_max_usd', 'caida_max_pct', 'n_trades', 'max_OA', 'stop_out']].to_string())

    ruido = d[(d['A'] == ACTUAL['A']) & (d['factor_B'] == ACTUAL['factor_B']) & (d['perdida_max'] == ACTUAL['perdida_max'])
              & (d['r_tope'] == 'sin')].pivot(index='mes', columns='semilla', values='resultado_usd')
    if ruido.shape[1] > 1:
        print('\n== Ruido: la actual con otras semillas de la simulación dentro de la hora (USD) ==')
        print(ruido.to_string())
        umbral = (ruido.sub(ruido[SEMILLA_INTRAVELA], axis=0).abs().max(axis=1)).reindex(actual.index)
    else:
        umbral = pd.Series(0.0, index=actual.index)

    print('\n== Qué parámetro mueve más el resultado (promedio de los 4 meses, USD) ==')
    efecto = []
    for c in claves:
        m = base.groupby(c)['resultado_usd'].mean()
        efecto.append((c, m.max() - m.min()))
        print(f'-- {c}: ' + ' | '.join(f'{k}: {v:+.0f}' for k, v in m.items()) + f'   (rango {m.max() - m.min():.0f})')
    print('Orden por rango:', ' > '.join(c for c, _ in sorted(efecto, key=lambda x: -x[1])))
    print('\n== Caída máxima promedio (USD) por valor ==')
    for c in claves:
        m = base.groupby(c)['caida_max_usd'].mean()
        print(f'-- {c}: ' + ' | '.join(f'{k}: {v:.0f}' for k, v in m.items()))

    print('\n== Regla 3: le gana a la actual en TODOS los meses por más que el ruido, con caída no peor ==')
    gana = []
    for params, g in base.groupby(claves):
        g = g.set_index('mes')
        if len(g) < len(MESES):
            continue
        mejora = g['resultado_usd'] - actual['resultado_usd']
        if ((mejora > umbral).all() and (g['caida_max_usd'] <= actual['caida_max_usd']).all()):
            gana.append({**dict(zip(claves, params)), 'mejora_prom_usd': round(mejora.mean(), 1),
                         **{f'dif_{m}': round(v, 0) for m, v in mejora.items()}})
    if gana:
        print(pd.DataFrame(gana).sort_values('mejora_prom_usd', ascending=False).head(15).to_string(index=False))
    else:
        print('Ninguna configuración cumple la regla.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paso', choices=['construir', 'validar', 'grilla', 'ruido', 'analizar'])
    ap.add_argument('--mes', choices=MESES, help='solo con `construir`: un mes (un proceso por mes)')
    ap.add_argument('--workers', type=int, default=6)
    args = ap.parse_args()
    if args.paso == 'construir':
        if args.mes is None:
            sys.exit('construir necesita --mes (lanza un proceso por mes para que corran en paralelo)')
        construir_soportes(args.mes)
    elif args.paso == 'analizar':
        analizar()
    elif args.paso == 'validar':
        sys.exit(0 if validar() else 1)
    elif args.paso == 'grilla':
        ejecutar(tareas_grilla(), args.workers)
    else:
        ejecutar(tareas_ruido(), args.workers)
