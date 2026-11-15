"""
X4S_backtesting_inteligente.py

Una vuelta del backtesting inteligente (docs/plans/plan_x5_alt_v2.md, sección 9) para un valor: backtest
completo desde FECHA_INICIO_BT con los C2 fijos y los C1 cambiando en el tiempo, sobre una cuenta de 3000 USD
cuyo lote (`lotajes_m`) y pérdida máxima (`p · Z`) dependen de Z = cerrado + P&L abierto.

Importa de X4_backtester.py el paso por vela, la búsqueda de soportes, la cuenta y el equity; no reimplementa
X0 ni X1. Un proceso por valor. Esta vuelta no aprende ni sortea nada (eso es Q5-4 y Q5-5): mide el premio de
cada tramo y los KPIs y los registra en resources/x5_alt/q5/ (plan 9.10):
  {valor}_vueltas.csv       una fila por vuelta
  {valor}_seguimiento.csv   una fila por bloque de N_VELAS velas (lo mismo que el resumen en pantalla)
  {valor}_estructura_v{n}.json  estructura de variables de cada version_estructura, nunca se sobrescribe
  {valor}/{vuelta}/         trades.json, events.json, equity_*.csv, estado_x4s.pkl y x4.log (lo que imprime X4)

`estado_x4s.pkl` se reescribe al inicio de cada bloque y permite reanudar una vuelta interrumpida (`--reanudar`); se
borra cuando la vuelta termina.

Uso:
  python scripts/X4S_backtesting_inteligente.py --activo BTCUSD               # C2 de Q4 (primera vuelta)
  python scripts/X4S_backtesting_inteligente.py --activo BTCUSD --estatica    # control: C1 de config.py
  python scripts/X4S_backtesting_inteligente.py --activo BTCUSD --hasta 2022-04-15 --reset
  python scripts/X4S_backtesting_inteligente.py --activo BTCUSD --reanudar    # sigue la vuelta interrumpida
"""

import argparse
import contextlib
import csv
import datetime
import hashlib
import json
import os
import pickle
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as gc
import config_smart
import X4_backtester as x4
from x5_alt_funciones import (
    cargar_c2_q4, cargar_estructura_c1, drawdown_maximo, estadisticas_c1, lotajes_m, perdida_max_usd,
    premios_por_tramo, serie_c1,
)

# Cadencias (plan 9.2): el grupo de búsqueda cambia cada N_VELAS velas y obliga a buscar soportes de nuevo;
# el de operación se lee en cada vela.
C1_BUSQUEDA = ['N', 'K', 'N_EXP', 'LAMBDA']
C1_OPERACION = ['A', 'factor_B', 'p']
# Clave de config_smart con el piso y el techo de cada C1 de la vuelta (p es la fracción de Z, no el PERDIDA_MAX en USD).
CLAVE_RANGO = {'N': 'N', 'K': 'K', 'N_EXP': 'N_EXP', 'LAMBDA': 'LAMBDA', 'A': 'A', 'factor_B': 'factor_B',
               'p': 'PERDIDA_MAX_PCT'}
CURVAS_EQUITY = ('equity_global.csv', 'equity_activos.csv')
ARCHIVO_SNAPSHOT = 'estado_x4s.pkl'
VERSION_SNAPSHOT = 1


# ─── C1 vela a vela ───────────────────────────────────────────────────────────

def cargar_insumos(valor: str) -> tuple:
    """Tabla de estado de Q1, estructura de variables de cada C1 y C2 calibrados por Q4 para `valor`."""
    tabla = pd.read_csv(gc.CARPETA_X5_ALT / 'exp_Q1' / f'{valor}_tabla_estado_v2.csv', parse_dates=['DateTime'])
    estructura = cargar_estructura_c1(gc.RUTA_ESTRUCTURA_C1)
    c2_q4 = cargar_c2_q4(gc.CARPETA_X5_ALT / 'exp_Q4' / f'{valor}_q4_resumen.csv')
    return tabla, estructura, c2_q4


def c1_dinamicos(valor: str, c2: dict, tabla: pd.DataFrame, estructura: dict) -> pd.DataFrame:
    """Los 7 C1 vela a vela (ya en la grilla) a partir de los C2; `PERDIDA_MAX` queda como la fracción `p`."""
    cols = {parametro: serie_c1(parametro, valor, c2[parametro], tabla, estructura)['c1']
            for parametro in estructura}
    df = pd.DataFrame(cols, index=pd.DatetimeIndex(tabla['DateTime']))
    return df.rename(columns={'PERDIDA_MAX': 'p'})


def c1_estaticos(valor: str, indice: pd.DatetimeIndex) -> pd.DataFrame:
    """C1 constantes de la configuración actual (`config.py`), con `p` fijo equivalente: vuelta estática de control."""
    return pd.DataFrame({
        'N': gc.n_sizes_ejecucion[valor], 'K': gc.K, 'N_EXP': gc.N_EXP, 'LAMBDA': gc.LAMBDA,
        'A': gc.A[valor], 'factor_B': gc.B[valor] / gc.A[valor], 'p': config_smart.P_ESTATICO,
    }, index=indice)


def c1_operacion(c1: pd.DataFrame) -> pd.DataFrame:
    """C1 de operación (A, factor_B, p) que rige cada vela: los de la vela anterior, que es lo que se conoce al abrirla.
    La primera vela usa su propia fila."""
    op = c1[C1_OPERACION].shift(1)
    op.iloc[0] = c1[C1_OPERACION].iloc[0]
    return op


# ─── Configuración y carpetas de una vuelta ───────────────────────────────────

def construir_cfg(valor: str, carpeta: Path, semilla: int) -> SimpleNamespace:
    """Config que X4 espera, armada desde `config.py`/`config_smart.py` (no hay carpeta de versión). `A`, `B`,
    `PERDIDA_MAX_BT`, `K`, `N_EXP`, `LAMBDA`, `LOTAJES` y `n_sizes` los reescribe la vuelta cada vela o cada bloque."""
    cuenta = config_smart.CUENTA
    return SimpleNamespace(
        version=f'Q5_{valor}', valores=[valor], n_sizes={valor: gc.n_sizes_ejecucion[valor]},
        fecha_inicio=config_smart.FECHA_INICIO_BT, fecha_fin='F',
        capital_inicial=cuenta['capital_inicial'],
        A=gc.A[valor], B=gc.B[valor], PERDIDA_MAX_BT=0.0,
        MARGEN_LIBRE_MIN_BT=cuenta['margen_libre_min'], STOP_OUT_LEVEL=cuenta['stop_out_level'],
        K=gc.K, N_EXP=gc.N_EXP, LAMBDA=gc.LAMBDA,
        LOTAJES={valor: gc.MIN_LOTAJES[valor]}, MIN_LOTAJES={valor: gc.MIN_LOTAJES[valor]},
        UNITS={valor: gc.UNITS[valor]}, APALANCAMIENTO={valor: gc.APALANCAMIENTO[valor]},
        CARPETA_RESOURCES=carpeta, CARPETA_N_BT=carpeta / 'conjuntos_N', CARPETA_LOGS_BT=carpeta / 'logs',
        CARPETA_DATA=gc.CARPETA_DATA, CARPETA_DATA_MINUTO=gc.CARPETA_DATA_MINUTO,
        SEMILLA_INTRAVELA=semilla, SEMILLA_BUSQUEDA=semilla, X5_WARM_START_SOPORTES=True,
    )


def preparar_carpeta(carpeta: Path, reset: bool) -> None:
    """Carpeta de la vuelta vacía: X4 agrega a los CSV/JSON que encuentra, así que una vuelta nueva nunca
    reutiliza una carpeta con datos. `reset` la borra, solo si está dentro de `CARPETA_Q5`."""
    if carpeta.exists() and any(carpeta.iterdir()):
        if not reset:
            raise SystemExit(f'La carpeta {carpeta} ya tiene datos de otra vuelta; usa --reset o --carpeta distinta.')
        if gc.CARPETA_Q5.resolve() not in carpeta.resolve().parents:
            raise SystemExit(f'--reset solo borra dentro de {gc.CARPETA_Q5}, no {carpeta}.')
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)


# ─── Búsqueda de soportes con N dinámico ──────────────────────────────────────

def _sembrar_cache_n(cfg: SimpleNamespace, valor: str, n_nuevo: int, n_previo: int | None) -> None:
    """El caché de soportes de X0 es un archivo por N (`{valor}_{N}_bt.json`): al cambiar N el warm start se
    perdería. Se copia al archivo del N nuevo la última solución del N anterior; X0 la recorta o completa
    al tamaño pedido (`obtener_df_extremos`)."""
    if n_previo is None or n_nuevo == n_previo:
        return
    origen = cfg.CARPETA_N_BT / f'{valor}_{n_previo}_bt.json'
    if not origen.exists():
        return
    cache_origen = json.loads(origen.read_text())
    ultima = max(cache_origen, key=pd.to_datetime)
    destino = cfg.CARPETA_N_BT / f'{valor}_{n_nuevo}_bt.json'
    cache_destino = json.loads(destino.read_text()) if destino.exists() else {}
    cache_destino[ultima] = cache_origen[ultima]
    destino.write_text(json.dumps(cache_destino))


def _buscar_soportes(estado: dict, cfg: SimpleNamespace, valor: str, ts, fila_c1: pd.Series,
                     n_previo: int | None) -> dict | None:
    """Fija N/K/N_EXP/LAMBDA de la fila y recalcula los soportes con la búsqueda de X0 (vía X4)."""
    cfg.K, cfg.N_EXP, cfg.LAMBDA = float(fila_c1['K']), float(fila_c1['N_EXP']), float(fila_c1['LAMBDA'])
    cfg.n_sizes[valor] = int(fila_c1['N'])
    _sembrar_cache_n(cfg, valor, cfg.n_sizes[valor], n_previo)
    infos = x4._recalcular_soportes(estado, ts, cfg, x5_mode=True)
    return infos[0] if infos else None


# ─── Registro en CSV ──────────────────────────────────────────────────────────

def agregar_fila_csv(ruta: Path, fila: dict) -> None:
    """Agrega una fila a un CSV de registro. Si trae columnas que el archivo no tiene (una variable nueva en la
    estructura) reescribe con la unión de columnas; los pesos `c2_*_w_*` de las filas viejas valen 0 (plan 9.12)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        with open(ruta, newline='', encoding='utf-8') as f:
            columnas = next(csv.reader(f), [])
        if set(fila) <= set(columnas):
            with open(ruta, 'a', newline='', encoding='utf-8') as f:
                csv.DictWriter(f, fieldnames=columnas).writerow(fila)
            return
        df = pd.concat([pd.read_csv(ruta), pd.DataFrame([fila])], ignore_index=True)
        for col in df.columns:
            if col.startswith('c2_') and '_w_' in col:
                df[col] = df[col].fillna(0.0)
    else:
        df = pd.DataFrame([fila])
    df.to_csv(ruta, index=False)


def quitar_vuelta_de_csv(ruta: Path, id_vuelta: str, columna: str) -> None:
    """Borra las filas de una vuelta que se repite con --reset, para no dejar ids duplicados."""
    if not ruta.exists():
        return
    df = pd.read_csv(ruta)
    if (df[columna] == id_vuelta).any():
        df[df[columna] != id_vuelta].to_csv(ruta, index=False)


def registrar_version_estructura(valor: str, estructura: dict) -> int:
    """`version_estructura` de la vuelta: número de la combinación de versiones de los C1 (campo `version` de cada
    entrada de la estructura). Agregar o quitar una variable no la cambia (plan 9.12); redefinir una sí. La primera vez
    que aparece una combinación se archiva la estructura completa en `{valor}_estructura_v{n}.json`, sin sobrescribir."""
    versiones = {c1: entrada['version'] for c1, entrada in estructura.items()}
    existentes = {}
    for ruta in gc.CARPETA_Q5.glob(f'{valor}_estructura_v*.json'):
        guardado = json.loads(ruta.read_text(encoding='utf-8'))
        existentes[guardado['version_estructura']] = guardado['versiones']
    for n, v in existentes.items():
        if v == versiones:
            return n
    n = max(existentes, default=0) + 1
    gc.CARPETA_Q5.mkdir(parents=True, exist_ok=True)
    (gc.CARPETA_Q5 / f'{valor}_estructura_v{n}.json').write_text(json.dumps({
        'version_estructura': n, 'valor': valor, 'versiones': versiones,
        'archivada': datetime.datetime.now().isoformat(timespec='seconds'),
        'nota': 'mu/sigma no se guardan: son causales (ventana expansiva) y salen de la tabla de estado de Q1.',
        'estructura': estructura,
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    return n


# ─── Resumen en pantalla ──────────────────────────────────────────────────────

def _fmt_eta(segundos) -> str:
    if segundos is None or pd.isna(segundos):
        return '—'
    h, resto = divmod(int(segundos), 3600)
    return f'{h}h{resto // 60:02d}m' if h else f'{resto // 60}m'


def formatear_resumen(fila: dict) -> list:
    """Líneas del resumen de un bloque (plan 9.10), todas con el prefijo `[valor | vuelta]` porque los 7 procesos
    escriben en la misma consola."""
    pre = f'[{fila["valor"]} | {fila["vuelta"]}]'
    ml = fila['margin_level']
    aciertos = fila['aciertos_acum_pct']
    if fila['busqueda_cortada']:
        cierre = 'cortada por tope de tiempo'
    else:
        cierre = 'convergió' if fila['convergio'] else 'sin converger'
    lineas = [
        f'{pre} bloque {fila["bloque"]}/{fila["bloques_total"]} | {fila["tramo"]} | {fila["ts"]} | '
        f'{fila["pct_velas"]:.1f}%  ETA {_fmt_eta(fila["eta_s"])}',
        f'{pre}   status   : {fila["status"]} | margen {"—" if ml is None else f"{ml:,.0f}%"} | '
        f'{fila["n_OA"]} OA, {fila["n_OE"]} OE',
        f'{pre}   cuenta   : cerrado {fila["cerrado"]:,.2f} | P&L abierto {fila["pnl_abierto"]:+,.2f} | '
        f'Z {fila["Z"]:,.2f} | lotajes_m {fila["lotajes_m"]}',
        f'{pre}   bloque   : {fila["trades_bloque"]} trades ({fila["ganados_bloque"]} ganados) | '
        f'acumulado {fila["trades_acum"]} ({"—" if aciertos is None else f"{aciertos:.0f}%"}) | '
        f'drawdown máx {fila["drawdown_max_pct"]:.1f}%',
        f'{pre}   C1       : N {fila["N"]} | K {fila["K"]:.1f} | N_EXP {fila["N_EXP"]:.1f} | LAMBDA {fila["LAMBDA"]:.2f} | '
        f'A prom {fila["A_prom"]:.1f} | B prom {fila["B_prom"]:.1f} | p prom {fila["p_prom"]:.3f} (umbral última vela {fila["umbral_usd"]:,.0f} USD)',
    ]
    if fila['FO_inicial'] is not None:
        lineas.append(f'{pre}   soportes : FO {fila["FO_inicial"]:.1e} -> {fila["FO_final"]:.1e} '
                      f'({cierre}, {fila["busqueda_s"]:.0f} s)')
    return lineas


def formatear_resumen_final(fila: dict) -> list:
    """Cierre de la vuelta: premio de cada tramo y KPIs."""
    pre = f'[{fila["valor"]} | {fila["id"]}]'
    return [
        f'{pre} FIN DE VUELTA {fila["ts_inicio"]} → {fila["ts_fin"]} ({fila["n_velas"]} velas, {fila["duracion_min"]:.0f} min)',
        f'{pre}   premio   : aprendizaje {fila["premio_aprendizaje"]:.4f} (Z al corte {fila["z_corte"]:,.2f} en {fila["corte_velas"]} velas) | '
        f'reservado {fila["premio_reservado"]:.4f} (Z final {fila["z_final"]:,.2f})',
        f'{pre}   KPIs     : {fila["n_trades"]} trades ({fila["tasa_aciertos_pct"]:.0f}% ganados) | '
        f'drawdown máx {fila["drawdown_max_pct"]:.1f}% ({fila["drawdown_max_usd"]:,.0f} USD) | '
        f'stop-outs {fila["stop_outs"]} | lotajes_m máx {fila["lotajes_m_max"]} (prom {fila["lotajes_m_prom"]:.2f})',
        f'{pre}   mercado  : {fila["tiempo_en_mercado_pct"]:.0f}% de las velas con OA | margen usado prom '
        f'{fila["margen_usado_prom"]:,.0f} máx {fila["margen_usado_max"]:,.0f} USD | '
        f'{fila["n_busquedas"]} búsquedas ({fila["n_busquedas_cortadas"]} cortadas por el tope)',
    ]


# ─── Reanudación ──────────────────────────────────────────────────────────────

def _huella(c1: pd.DataFrame, semilla: int, hasta, n_total: int, n_velas: int, corte: int, capital: float) -> str:
    """Identifica los insumos de la vuelta: si cambian entre la interrupción y la reanudación, el estado guardado ya
    no corresponde a lo que se va a seguir simulando."""
    h = hashlib.sha256(pd.util.hash_pandas_object(c1, index=True).to_numpy().tobytes())
    h.update(f'{semilla}|{hasta}|{n_total}|{n_velas}|{corte}|{capital}'.encode())
    return h.hexdigest()


def _escribir_atomico(ruta: Path, objeto) -> None:
    tmp = ruta.with_suffix(ruta.suffix + '.tmp')
    with open(tmp, 'wb') as f:
        pickle.dump(objeto, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, ruta)


def _cargar_snapshot(ruta: Path, huella: str) -> dict:
    if not ruta.exists():
        raise SystemExit(f'No hay {ruta.name} en {ruta.parent}: la vuelta no tiene nada que reanudar.')
    with open(ruta, 'rb') as f:
        snap = pickle.load(f)
    if snap.get('version') != VERSION_SNAPSHOT:
        raise SystemExit(f'{ruta.name} es de otra versión del formato ({snap.get("version")}); usa --reset.')
    if snap['huella'] != huella:
        raise SystemExit('Los C1, la semilla o la cuenta cambiaron desde que se guardó el estado de la vuelta; '
                         'usa --reset para empezarla de nuevo.')
    return snap


def _truncar_archivo(ruta: Path, tam: int) -> None:
    if ruta.exists() and ruta.stat().st_size > tam:
        with open(ruta, 'r+b') as f:
            f.truncate(tam)


def _truncar_lista_json(ruta: Path, n: int) -> None:
    if not ruta.exists():
        return
    items = json.loads(ruta.read_text())
    if len(items) > n:
        ruta.write_text(json.dumps(items[:n], indent=2, default=str))


def _truncar_seguimiento(ruta: Path, id_vuelta: str, n: int) -> None:
    """Deja solo las primeras `n` filas de la vuelta; las filas de otras vueltas no se tocan."""
    if not ruta.exists():
        return
    df = pd.read_csv(ruta)
    propias = df['vuelta'] == id_vuelta
    sobran = propias & (propias.cumsum() > n)
    if sobran.any():
        df[~sobran].to_csv(ruta, index=False)


def _truncar_cache_bt(carpeta_n_bt: Path, ts_corte) -> None:
    """Quita del caché de soportes las búsquedas posteriores al snapshot: la reanudación las rehace y no deben
    servirle de warm start (la vuelta sin interrupción no las tenía)."""
    for ruta in carpeta_n_bt.glob('*_bt.json'):
        cache = json.loads(ruta.read_text())
        vigentes = {k: v for k, v in cache.items() if pd.Timestamp(k) <= ts_corte}
        if len(vigentes) != len(cache):
            ruta.write_text(json.dumps(vigentes))


def _restaurar_archivos(carpeta: Path, cfg: SimpleNamespace, ruta_seguimiento: Path, id_vuelta: str, snap: dict,
                        ts_corte) -> None:
    """Deja los archivos de la vuelta como estaban al guardar el snapshot: lo escrito después (velas y bloques que
    la reanudación va a rehacer) se descarta para no duplicarlo."""
    for nombre, tam in snap['tam_equity'].items():
        _truncar_archivo(carpeta / nombre, tam)
    for nombre, clave in (('trades.json', 'trades'), ('events.json', 'events')):
        _truncar_lista_json(carpeta / nombre, snap['n_json'][clave])
    _truncar_seguimiento(ruta_seguimiento, id_vuelta, snap['n_filas_seg'])
    _truncar_cache_bt(cfg.CARPETA_N_BT, ts_corte)


# ─── Una vuelta ───────────────────────────────────────────────────────────────

def ejecutar_vuelta(valor: str, c1: pd.DataFrame, carpeta: Path, semilla: int = 0, hasta=None,
                    id_vuelta: str | None = None, reanudar: bool = False) -> dict:
    """Corre una vuelta de `valor` con los C1 de `c1` (índice DateTime, columnas N, K, N_EXP, LAMBDA, A, factor_B, p).

    Los C1 del grupo de búsqueda se leen de la fila de la vela donde se busca (datos hasta ese instante, los mismos
    de la búsqueda); los de operación, de la fila de la vela anterior, que es lo que se conoce al abrir la vela.
    Como en X4, la vela donde se recalculan los soportes queda congelada (no se opera): la búsqueda ya vio su cierre.
    La vuelta termina en la última vela que tenga fila en `c1` (o `hasta`) y no se corta con el stop-out.

    Cada `N_VELAS` velas imprime el resumen del bloque y lo agrega a `{valor}_seguimiento.csv`; lo que imprime X4
    (cada trade cerrado, cada búsqueda) va a `x4.log` en la carpeta de la vuelta. Devuelve las series vela a vela
    (equity, lote, margen, C1 aplicados) para calcular premios y KPIs con `resumir_vuelta`.

    Al inicio de cada bloque (con su búsqueda ya hecha) guarda `estado_x4s.pkl`. Con `reanudar=True` carga ese estado,
    descarta de los archivos lo escrito después y sigue desde la vela siguiente. Las semillas de la intra-vela y de la
    búsqueda salen de (semilla, valor, ts), no de un generador con estado, así que el resultado es el mismo que sin
    interrupción salvo en las búsquedas cortadas por el tope de tiempo, que dependen del reloj.
    """
    cfg = construir_cfg(valor, carpeta, semilla)
    cfg.CARPETA_N_BT.mkdir(parents=True, exist_ok=True)
    id_vuelta = id_vuelta or carpeta.name
    capital = cfg.capital_inicial
    n_velas = config_smart.N_VELAS[config_smart.tipo_valor(valor)]
    consola = sys.stdout

    h1 = x4._cargar_datos_h1(cfg).get(valor)
    if h1 is None:
        raise SystemExit(f'Sin datos H1 de {valor} desde {cfg.fecha_inicio}.')
    m1 = x4._cargar_datos_m1(cfg).get(valor)

    fin = min(h1.index.max(), c1.index.max())
    if hasta is not None:
        fin = min(fin, pd.Timestamp(hasta))
    h1 = h1[h1.index <= fin]
    c1 = c1.reindex(h1.index, method='ffill')
    faltantes = c1.columns[c1.isna().any()].tolist()
    if faltantes:
        raise ValueError(f'C1 sin valor en {faltantes} (primera vela sin dato: '
                         f'{c1[c1[faltantes].isna().any(axis=1)].index[0]}): la tabla de Q1 no cubre desde {cfg.fecha_inicio}')
    c1_op = c1_operacion(c1)

    n_total = len(h1)
    corte = int(n_total * (1 - config_smart.FRACCION_RESERVADA))
    bloques_total = (n_total - 1) // n_velas + 1
    ruta_seguimiento = gc.CARPETA_Q5 / f'{valor}_seguimiento.csv'

    estado = {'capital': capital, 'GC_global': 0.0,
              'por_activo': {valor: {'soportes': [], 'OE': {}, 'OA': {}, 'GC': 0.0}},
              'ts_ultimo_procesado': None, 'ts_ultimo_recalculo': None}
    trades_log: list = []
    events_log: list = []
    retornos: list = []            # (ts_cierre, retorno_usd) de todos los trades; trades_log se vacía al flushear
    busquedas: list = []
    nombres_aplicado = ['N', 'K', 'N_EXP', 'LAMBDA', 'A', 'B', 'factor_B', 'p', 'umbral_usd']
    aplicado = {k: np.full(n_total, np.nan) for k in nombres_aplicado}
    equity = np.full(n_total, np.nan)
    m_serie = np.ones(n_total, dtype=int)
    en_mercado = np.zeros(n_total, dtype=bool)
    margen_usado = np.zeros(n_total)
    series = [equity, m_serie, en_mercado, margen_usado, *aplicado.values()]

    mc = {'balance': capital, 'equity': capital, 'margen_usado': 0.0, 'margin_level': None, 'n_OA': 0, 'n_OE': 0}
    z = capital
    i_busqueda, n_previo, n_ret_previo = None, None, 0
    stop_outs, en_stop_out = 0, False
    n_json = {'trades': 0, 'events': 0}  # items ya volcados a trades.json / events.json
    n_filas_seg, duracion_previa_s, i_inicio = 0, 0.0, 0

    ruta_snapshot = carpeta / ARCHIVO_SNAPSHOT
    huella = _huella(c1, semilla, hasta, n_total, n_velas, corte, capital)
    if reanudar:
        snap = _cargar_snapshot(ruta_snapshot, huella)
        estado, retornos, busquedas, aplicado = snap['estado'], snap['retornos'], snap['busquedas'], snap['aplicado']
        equity, m_serie, en_mercado, margen_usado = snap['equity'], snap['m_serie'], snap['en_mercado'], snap['margen_usado']
        series = [equity, m_serie, en_mercado, margen_usado, *aplicado.values()]
        mc, z, i_busqueda, n_previo, n_ret_previo = snap['mc'], snap['z'], snap['i_busqueda'], snap['n_previo'], snap['n_ret_previo']
        stop_outs, en_stop_out = snap['stop_outs'], snap['en_stop_out']
        n_json, n_filas_seg, duracion_previa_s, i_inicio = snap['n_json'], snap['n_filas_seg'], snap['duracion_s'], snap['siguiente']
        _restaurar_archivos(carpeta, cfg, ruta_seguimiento, id_vuelta, snap, h1.index[i_busqueda])
        fila_busqueda = c1.iloc[i_busqueda]  # lo que `_buscar_soportes` dejó fijado en cfg para el bloque en curso
        cfg.K, cfg.N_EXP, cfg.LAMBDA = float(fila_busqueda['K']), float(fila_busqueda['N_EXP']), float(fila_busqueda['LAMBDA'])
        cfg.n_sizes[valor] = int(fila_busqueda['N'])
    t0 = time.monotonic() - duracion_previa_s  # sin la suspensión del equipo: ETA y duración son tiempo de cómputo

    def decir(texto: str) -> None:
        print(texto, file=consola, flush=True)

    def flush() -> None:
        retornos.extend((t['timestamp_cierre'], t['retorno_usd']) for t in trades_log)
        n_json['trades'] += x4._flush_json_list(trades_log, carpeta / 'trades.json')
        n_json['events'] += x4._flush_json_list(events_log, carpeta / 'events.json')

    def guardar_snapshot(i: int) -> None:
        """Estado completo con la vela `i` recién congelada (búsqueda hecha, filas y JSON ya volcados), para seguir
        desde la `i + 1`. Guarda también el tamaño de los archivos que crecen por vela, para podarlos al reanudar."""
        _escribir_atomico(ruta_snapshot, {
            'version': VERSION_SNAPSHOT, 'huella': huella, 'siguiente': i + 1, 'i_busqueda': i_busqueda,
            'estado': estado, 'retornos': retornos, 'busquedas': busquedas, 'aplicado': aplicado, 'equity': equity,
            'm_serie': m_serie, 'en_mercado': en_mercado, 'margen_usado': margen_usado, 'mc': mc, 'z': z,
            'n_previo': n_previo, 'n_ret_previo': n_ret_previo, 'stop_outs': stop_outs, 'en_stop_out': en_stop_out,
            'n_json': dict(n_json), 'n_filas_seg': n_filas_seg, 'duracion_s': time.monotonic() - t0,
            'tam_equity': {nombre: (carpeta / nombre).stat().st_size for nombre in CURVAS_EQUITY
                           if (carpeta / nombre).exists()},
        })

    def fila_seguimiento(i: int, ts, info: dict | None, k: int) -> dict:
        ini = i_busqueda if i_busqueda is not None else 0
        ret_bloque = np.array([r[1] for r in retornos[n_ret_previo:]])
        ret_total = np.array([r[1] for r in retornos])
        ml = mc['margin_level']
        if z <= 0:
            status = 'cuenta negativa'
        elif ml is not None and mc['margen_usado'] > 0 and ml <= cfg.STOP_OUT_LEVEL:
            status = 'margen bajo'
        else:
            status = 'normal'

        if i == 0:  # cold start: aún no hay velas, se muestran los C1 de operación con que parte la primera
            f0 = c1_op.iloc[0]
            a_prom, p_prom = float(f0['A']), float(f0['p'])
            b_prom, umbral = float(f0['factor_B']) * a_prom, perdida_max_usd(p_prom, z)
        else:
            a_prom, b_prom, p_prom = (float(np.nanmean(aplicado[k][ini:i])) for k in ('A', 'B', 'p'))
            umbral = aplicado['umbral_usd'][i - 1]

        return {
            'vuelta': id_vuelta, 'valor': valor, 'bloque': k, 'bloques_total': bloques_total,
            'tramo': 'aprendizaje' if i - 1 < corte else 'reservado', 'ts': str(ts),
            'pct_velas': round(100 * min(i, n_total) / n_total, 2),
            'eta_s': (time.monotonic() - t0) / i * (n_total - i) if i > 0 else None,
            'status': status, 'margin_level': ml, 'n_OA': mc['n_OA'], 'n_OE': mc['n_OE'],
            'margen_usado': mc['margen_usado'],
            'cerrado': estado['capital'], 'pnl_abierto': z - estado['capital'], 'Z': z, 'lotajes_m': lotajes_m(z),
            'trades_bloque': len(ret_bloque), 'ganados_bloque': int((ret_bloque > 0).sum()),
            'trades_acum': len(ret_total),
            'aciertos_acum_pct': float(100 * (ret_total > 0).mean()) if len(ret_total) else None,
            'drawdown_max_pct': 100 * drawdown_maximo(equity[:i], capital)[0] if i > 0 else 0.0,
            'N': cfg.n_sizes[valor], 'K': cfg.K, 'N_EXP': cfg.N_EXP, 'LAMBDA': cfg.LAMBDA,
            'A_prom': a_prom, 'B_prom': b_prom, 'p_prom': p_prom, 'umbral_usd': umbral,
            'FO_inicial': info['FO_inicial'] if info else None, 'FO_final': info['FO_final'] if info else None,
            'convergio': info['convergio'] if info else None, 'busqueda_s': info['duracion'] if info else None,
            'busqueda_cortada': bool(info['tiempo_agotado']) if info else None,
        }

    def registrar_bloque(i: int, ts, info: dict | None, k: int) -> None:
        nonlocal n_ret_previo, n_filas_seg
        fila = fila_seguimiento(i, ts, info, k)
        for linea in formatear_resumen(fila):
            decir(linea)
        agregar_fila_csv(ruta_seguimiento, fila)
        n_ret_previo = len(retornos)
        n_filas_seg += 1

    decir(f'[{valor} | {id_vuelta}] vuelta: {h1.index[0]} → {h1.index[-1]} ({n_total} velas H1, corte del aprendizaje en la '
          f'{corte}), búsqueda cada {n_velas} velas, carpeta {carpeta}')
    if reanudar:
        decir(f'[{valor} | {id_vuelta}] reanudada desde la vela {i_inicio} ({h1.index[i_busqueda]}, bloque '
              f'{i_busqueda // n_velas}/{bloques_total})')

    with open(carpeta / 'x4.log', 'a', encoding='utf-8') as log, contextlib.redirect_stdout(log):
        if reanudar:
            print(f'\n=== VUELTA REANUDADA desde la vela {i_inicio} (bloque iniciado en {h1.index[i_busqueda]}) ===')
        for i, (ts, candle) in enumerate(h1.iloc[i_inicio:].iterrows(), start=i_inicio):
            if i_busqueda is None or i - i_busqueda >= n_velas:
                info = _buscar_soportes(estado, cfg, valor, ts, c1.iloc[i], n_previo)
                if not estado['por_activo'][valor]['soportes']:
                    raise RuntimeError(f'[{valor}] {ts}: la búsqueda no entregó soportes')
                busquedas.append({'ts': ts, 'i': i, 'info': info})
                n_previo = cfg.n_sizes[valor]
                flush()
                registrar_bloque(i, ts, info, i // n_velas)
                congelada = i_busqueda is not None
                i_busqueda = i
                if congelada:
                    for s in series:
                        s[i] = s[i - 1]
                    guardar_snapshot(i)
                    continue

            fila = c1_op.iloc[i]
            m = lotajes_m(z)
            cfg.LOTAJES[valor] = m * cfg.MIN_LOTAJES[valor]
            cfg.A = float(fila['A'])
            cfg.B = float(fila['factor_B']) * cfg.A
            cfg.PERDIDA_MAX_BT = perdida_max_usd(float(fila['p']), z)

            precios = {valor: candle['Close']}
            x4._procesar_candle(ts, candle, valor, estado['por_activo'][valor], estado, m1, precios,
                                cfg.n_sizes[valor], cfg, events_log, trades_log)
            mc = x4._append_equity(ts, estado, precios, cfg)
            z = mc['equity']
            estado['ts_ultimo_procesado'] = ts.isoformat()

            equity[i], m_serie[i] = z, m
            en_mercado[i], margen_usado[i] = mc['n_OA'] > 0, mc['margen_usado']
            for nombre, v in (('N', cfg.n_sizes[valor]), ('K', cfg.K), ('N_EXP', cfg.N_EXP), ('LAMBDA', cfg.LAMBDA),
                              ('A', cfg.A), ('B', cfg.B), ('factor_B', float(fila['factor_B'])),
                              ('p', float(fila['p'])), ('umbral_usd', cfg.PERDIDA_MAX_BT)):
                aplicado[nombre][i] = v

            ml = mc['margin_level']
            quemada = mc['equity'] <= 0 or (ml is not None and mc['margen_usado'] > 0 and ml <= cfg.STOP_OUT_LEVEL)
            if quemada and not en_stop_out:
                stop_outs += 1
                events_log.append({'tipo': 'stop_out', 'ts': ts.isoformat(), 'equity': round(mc['equity'], 4),
                                   'balance': round(mc['balance'], 4), 'margen_usado': round(mc['margen_usado'], 4),
                                   'margin_level': round(ml, 4) if ml is not None else None, 'n_OA': mc['n_OA']})
                decir(f'[{valor} | {id_vuelta}] *** STOP OUT {ts}: Z={z:,.2f} (la vuelta sigue) ***')
            en_stop_out = quemada

        flush()
        x4._guardar_checkpoint(estado, cfg)
    registrar_bloque(n_total, h1.index[-1], None, bloques_total)

    return {'valor': valor, 'id': id_vuelta, 'estado': estado, 'indice': h1.index, 'equity': equity,
            'm_serie': m_serie, 'en_mercado': en_mercado, 'margen_usado': margen_usado, 'aplicado': aplicado,
            'retornos': retornos, 'busquedas': busquedas, 'stop_outs': stop_outs, 'm_max': int(m_serie.max()),
            'semilla': semilla, 'corte': corte, 'duracion_s': time.monotonic() - t0}


# ─── Premios, KPIs y registro de la vuelta ────────────────────────────────────

def resumir_vuelta(res: dict, c2: dict | None, estructura: dict, fase: str, replica_de: str,
                   version_estructura: int) -> dict:
    """Fila de `{valor}_vueltas.csv` (plan 9.10): identificación, C2 completos (todas las variables de la estructura,
    las no usadas valen 0), estadísticas de cada C1, premio de cada tramo y KPIs. `c2` es None en la estática."""
    valor, equity = res['valor'], res['equity']
    capital = config_smart.CUENTA['capital_inicial']
    prem = premios_por_tramo(equity, config_smart.FRACCION_RESERVADA)
    dd_pct, dd_usd = drawdown_maximo(equity, capital)
    ret = np.array([r[1] for r in res['retornos']])
    infos = [b['info'] for b in res['busquedas'] if b['info']]
    fila = {
        'id': res['id'], 'valor': valor, 'fase': fase, 'replica_de': replica_de, 'semilla': res['semilla'],
        'version_estructura': version_estructura,
        'fecha_ejecucion': datetime.datetime.now().isoformat(timespec='seconds'),
        'ts_inicio': str(res['indice'][0]), 'ts_fin': str(res['indice'][-1]), 'n_velas': len(equity),
        'corte_velas': prem['corte'],
    }
    if c2 is not None:
        for c1_nombre, entrada in estructura.items():
            c = c2[c1_nombre]
            for v in entrada['variables']:
                fila[f'c2_{c1_nombre}_w_{v["nombre"]}'] = float(c['pesos'].get(v['nombre'], 0.0))
            fila[f'c2_{c1_nombre}_span'] = int(c['span'])
            fila[f'c2_{c1_nombre}_punto_medio'] = float(c['punto_medio'])
            fila[f'c2_{c1_nombre}_pendiente'] = float(c['pendiente'])
    fila.update({k: prem[k] for k in ('premio_aprendizaje', 'premio_reservado', 'z_corte', 'z_final')})
    fila.update({
        'drawdown_max_pct': 100 * dd_pct, 'drawdown_max_usd': dd_usd,
        'n_trades': len(ret), 'tasa_aciertos_pct': float(100 * (ret > 0).mean()) if len(ret) else float('nan'),
        'tiempo_en_mercado_pct': float(100 * res['en_mercado'].mean()),
        'margen_usado_prom': float(res['margen_usado'].mean()), 'margen_usado_max': float(res['margen_usado'].max()),
        'stop_outs': res['stop_outs'], 'lotajes_m_max': res['m_max'], 'lotajes_m_prom': float(res['m_serie'].mean()),
        'n_busquedas': len(res['busquedas']), 'n_busquedas_cortadas': sum(bool(i['tiempo_agotado']) for i in infos),
        'duracion_busquedas_s': float(sum(i['duracion'] for i in infos)),
        'duracion_min': res['duracion_s'] / 60,
    })
    for nombre, clave in CLAVE_RANGO.items():
        piso, techo = config_smart.rango(clave, valor)
        for k, v in estadisticas_c1(res['aplicado'][nombre], piso, techo).items():
            fila[f'c1_{nombre}_{k}'] = v
    return fila


def _json_limpio(o):
    """Tipos numpy a nativos, fechas a texto y NaN/inf a None, para que el JSON sea válido."""
    if isinstance(o, dict):
        return {str(k): _json_limpio(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_limpio(v) for v in o]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    return o


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(['git', *args], cwd=Path(__file__).parent, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def escribir_resumen_json(carpeta: Path, res: dict, fila: dict, inicio: datetime.datetime, reloj_s: float,
                          hasta) -> Path:
    """`resumen.json` en la carpeta de la vuelta: todo lo necesario para revisarla sin la consola. `reloj_s` es el
    tiempo de reloj (cuenta la suspensión del equipo) y `fila['duracion_min']` el de cómputo; la diferencia es la pausa."""
    valor, id_vuelta = res['valor'], res['id']
    seguimiento = pd.read_csv(gc.CARPETA_Q5 / f'{valor}_seguimiento.csv')
    busquedas = [{'ts': b['ts'], 'N': b['info']['N'], 'n_velas': b['info']['n_velas'],
                  'warm_start_n': b['info']['warm_start_n'], 'duracion_s': b['info']['duracion'],
                  'convergio': b['info']['convergio'], 'cortada': bool(b['info']['tiempo_agotado']),
                  'FO_inicial': b['info']['FO_inicial'], 'FO_final': b['info']['FO_final']}
                 for b in res['busquedas'] if b['info']]
    dur = np.array([b['duracion_s'] for b in busquedas])
    equity = pd.Series(res['equity'], index=res['indice'])
    computo_s = res['duracion_s']
    doc = {
        'vuelta': fila,
        'resumen_final': formatear_resumen_final(fila),
        'tiempos': {
            'inicio': inicio.isoformat(timespec='seconds'), 'computo_s': computo_s, 'reloj_s': reloj_s,
            'pausa_estimada_s': reloj_s - computo_s, 'busquedas_s': float(dur.sum()),
            'busquedas_pct_del_computo': float(100 * dur.sum() / computo_s),
        },
        'busquedas_resumen': {
            'n': len(busquedas), 'cortadas': sum(b['cortada'] for b in busquedas),
            'sin_converger': sum(not b['convergio'] for b in busquedas),
            'duracion_s': {'min': dur.min(), 'mediana': np.median(dur), 'p90': np.percentile(dur, 90), 'max': dur.max()},
        },
        'busquedas': busquedas,
        'bloques': seguimiento[seguimiento['vuelta'] == id_vuelta].to_dict('records'),
        'equity_fin_de_mes': {str(m): float(v) for m, v in equity.groupby(equity.index.to_period('M')).last().items()},
        'entorno': {
            'host': platform.node(), 'sistema': platform.platform(), 'python': platform.python_version(),
            'cpus': os.cpu_count(), 'commit': _git('rev-parse', '--short', 'HEAD'),
            'cambios_sin_commit': bool(_git('status', '--porcelain')),
        },
        'config': {
            'hasta': str(hasta) if hasta else None, 'FECHA_INICIAL': gc.FECHA_INICIAL,
            'FECHA_INICIO_BT': config_smart.FECHA_INICIO_BT, 'N_VELAS': config_smart.N_VELAS,
            'FRACCION_RESERVADA': config_smart.FRACCION_RESERVADA, 'CUENTA': config_smart.CUENTA,
            'tope_busqueda_min': gc.X4_TIEMPO_MAX_BUSQUEDA_SOPORTES_MIN,
            'tope_fase_gruesa_min': gc.X4_TIEMPO_MAX_FASE_GRUESA_MIN, 'MAX_ITERS': gc.MAX_ITERS,
            'MAX_CAMBIOS': gc.MAX_CAMBIOS, 'M': gc.M, 'M_COARSE': gc.M_COARSE, 'M_SALTO': gc.M_SALTO,
        },
    }
    ruta = carpeta / 'resumen.json'
    # una clave por línea: legible sin que las listas de búsquedas y bloques ocupen miles de líneas
    ruta.write_text('{\n' + ',\n'.join(f'{json.dumps(k)}: {json.dumps(_json_limpio(v), ensure_ascii=False)}'
                                        for k, v in doc.items()) + '\n}\n', encoding='utf-8')
    return ruta


def podar_curvas(valor: str, mejores: int | None = None) -> list:
    """Conserva las curvas de equity de las vueltas estáticas y de las `mejores` con más premio de aprendizaje (nunca
    el reservado) y borra las de las demás; trades, eventos y registro se conservan. Devuelve los ids podados."""
    mejores = config_smart.CURVAS_MEJORES if mejores is None else mejores
    ruta = gc.CARPETA_Q5 / f'{valor}_vueltas.csv'
    if not ruta.exists():
        return []
    df = pd.read_csv(ruta)
    conservar = set(df.loc[df['fase'] == 'estatica', 'id'])
    conservar |= set(df[df['fase'] != 'estatica'].nlargest(mejores, 'premio_aprendizaje')['id'])
    podadas = []
    for id_vuelta in df['id']:
        if id_vuelta in conservar:
            continue
        borrados = [(gc.CARPETA_Q5 / valor / id_vuelta / f) for f in CURVAS_EQUITY]
        if any(p.exists() for p in borrados):
            for p in borrados:
                p.unlink(missing_ok=True)
            podadas.append(id_vuelta)
    return podadas


def correr_vuelta(valor: str, c1: pd.DataFrame, nombre: str, semilla: int = 0, c2: dict | None = None,
                  fase: str = 'q4', replica_de: str = '', hasta=None, reset: bool = False,
                  reanudar: bool = False) -> dict:
    """Vuelta completa con su registro: corre, calcula premios y KPIs, agrega la fila a `{valor}_vueltas.csv` y poda
    las curvas de equity. `nombre` es el id de la vuelta (y de su carpeta). Devuelve la fila registrada.

    `reanudar` sigue la vuelta interrumpida desde su último `estado_x4s.pkl`. Si la carpeta no existe o está vacía
    empieza una vuelta nueva (así un lanzador puede pasarlo siempre); si tiene datos pero no snapshot, falla."""
    estructura = cargar_estructura_c1(gc.RUTA_ESTRUCTURA_C1)
    carpeta = gc.CARPETA_Q5 / valor / nombre
    if reanudar:
        if reset:
            raise SystemExit('--reanudar y --reset se excluyen: uno sigue la vuelta y el otro la borra.')
        if not (carpeta / ARCHIVO_SNAPSHOT).exists():
            if carpeta.exists() and any(carpeta.iterdir()):
                raise SystemExit(f'{carpeta} tiene datos pero no {ARCHIVO_SNAPSHOT}: la vuelta ya terminó o corrió sin '
                                 f'reanudación. Usa --reset o un --nombre distinto.')
            reanudar = False
    if not reanudar:
        preparar_carpeta(carpeta, reset)
        if reset:
            quitar_vuelta_de_csv(gc.CARPETA_Q5 / f'{valor}_vueltas.csv', nombre, 'id')
            quitar_vuelta_de_csv(gc.CARPETA_Q5 / f'{valor}_seguimiento.csv', nombre, 'vuelta')
    inicio, t_reloj = datetime.datetime.now(), time.time()
    res = ejecutar_vuelta(valor, c1, carpeta, semilla, hasta, id_vuelta=nombre, reanudar=reanudar)
    reloj_s = time.time() - t_reloj
    fila = resumir_vuelta(res, c2, estructura, fase, replica_de, registrar_version_estructura(valor, estructura))
    agregar_fila_csv(gc.CARPETA_Q5 / f'{valor}_vueltas.csv', fila)
    for linea in formatear_resumen_final(fila):
        print(linea, flush=True)
    ruta_resumen = escribir_resumen_json(carpeta, res, fila, inicio, reloj_s, hasta)
    print(f'[{valor} | {nombre}] resumen completo en {ruta_resumen}', flush=True)
    (carpeta / ARCHIVO_SNAPSHOT).unlink(missing_ok=True)
    podadas = podar_curvas(valor)
    if podadas:
        print(f'[{valor} | {nombre}] curvas de equity borradas de: {", ".join(podadas)}', flush=True)
    return fila


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description='Una vuelta del backtesting inteligente para un valor.')
    ap.add_argument('--activo', required=True, choices=gc.VALORES)
    ap.add_argument('--estatica', action='store_true', help='vuelta de control con los C1 de config.py')
    ap.add_argument('--semilla', type=int, default=0, help='semilla de la intra-vela y de la búsqueda de soportes')
    ap.add_argument('--hasta', help='última fecha a simular (pruebas cortas)')
    ap.add_argument('--nombre', help='id de la vuelta (por defecto {q4|estatica}_s{semilla})')
    ap.add_argument('--reset', action='store_true', help='borra la vuelta si ya existe (carpeta y filas de los CSV)')
    ap.add_argument('--reanudar', action='store_true',
                    help='sigue la vuelta interrumpida desde su último estado_x4s.pkl (sin snapshot ni datos, la empieza)')
    args = ap.parse_args()

    tabla, estructura, c2_q4 = cargar_insumos(args.activo)
    if args.estatica:
        c1, c2, fase = c1_estaticos(args.activo, pd.DatetimeIndex(tabla['DateTime'])), None, 'estatica'
    else:
        c1, c2, fase = c1_dinamicos(args.activo, c2_q4, tabla, estructura), c2_q4, 'q4'
    nombre = args.nombre or f'{fase}_s{args.semilla}'
    correr_vuelta(args.activo, c1, nombre, args.semilla, c2, fase, hasta=args.hasta, reset=args.reset,
                  reanudar=args.reanudar)


if __name__ == '__main__':
    main()
