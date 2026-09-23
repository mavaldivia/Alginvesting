"""
X0_data_supports.py

Etapa 1 (--opcion 0 o 2): Descarga velas OHLCV H1 (Data/) y M1 (Data_minuto/) desde MetaTrader5.
Etapa 2 (--opcion 1 o 2): Busca N soportes/resistencias óptimos por activo usando un optimizador
                           de búsqueda local y guarda los resultados en resources/conjuntos_N/.

Uso:
    python X0_data_supports.py               # opcion=2: ambas etapas
    python X0_data_supports.py --opcion 0    # solo descarga de datos
    python X0_data_supports.py --opcion 1    # solo búsqueda de soportes
"""

import argparse
import concurrent.futures
import datetime
import json
import multiprocessing
from collections import Counter

# Suprimir stdout en procesos worker antes de que importen matplotlib/mplfinance.
# Los workers usan spawn en Windows/macOS; sus prints interfieren con el cursor ANSI del monitor.
if multiprocessing.current_process().name != 'MainProcess':
    import os, sys
    sys.stdout = open(os.devnull, 'w')
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # los plots siempre se guardan a archivo, nunca se muestran;
                       # sin esto los workers (spawn) intentan abrir un backend GUI
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import mplfinance as mpf
import numpy as np
import pandas as pd
import tqdm
try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.text import Text
except ImportError:
    sys.exit('Falta instalar rich en revenAI: pip install rich')

warnings.filterwarnings('ignore')

from config import (
    CARPETA_DATA, CARPETA_DATA_MINUTO, CARPETA_N_PROD, CARPETA_PLOTS, CARPETA_LOGS,
    VALORES, FECHA_INICIAL,
    K, N_EXP, BLOQUE_DISTANCIAS, parametros_soportes,
    M, M_COARSE, LAMBDA, MAX_ITERS, MAX_CAMBIOS, DELTA_INICIAL, FACTOR_DELTA,
    GRAFICAR_EXTREMOS, GRAFICAR_FO, GRAFICAR_SOPORTES, GRAFICAR_ZOOM,
    n_sizes, n_sizes_ejecucion, N_MAX_MODELS, reiniciar_x0,
)
from X3_technical_features import actualizar_features as _x3_actualizar_features


# ─── Utilidades ───────────────────────────────────────────────────────────────

def json_act(file_path: str, variable=None, mode: str = 'open',
            intentos: int = 3, espera: float = 0.1):
    """Guarda (mode='save') o carga (mode='open') una lista de soportes en disco como JSON.

    El guardado es atómico (escribe a un .tmp y hace os.replace) para que un lector
    concurrente (X1) nunca vea el archivo truncado a mitad de escritura.

    La lectura reintenta ante OSError transitorios (sync de OneDrive u otro proceso
    escribiendo el mismo archivo), igual que `_leer_json_reintentos` para los cache bt.
    Los errores se relanzan (nunca sys.exit): un worker de ProcessPoolExecutor que hace
    sys.exit() termina en SystemExit, que al no ser Exception escapa del `except Exception`
    de _ciclo_activo y mata el script completo sin dejar rastro.
    """
    path = f'{file_path}.json'
    if mode == 'save':
        try:
            tmp_path = f'{path}.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(sorted(variable), f)
            os.replace(tmp_path, path)
            return None
        except Exception as e:
            console.print(f'Error json_act (save, {path}): {e}')
            raise

    for intento in range(intentos):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except OSError as e:
            if intento == intentos - 1:
                console.print(f'Error json_act (open, {path}): {e}')
                raise
            time.sleep(espera)
        except Exception as e:
            console.print(f'Error json_act (open, {path}): {e}')
            raise


def notacion_cientifica(numero: float, decimales: int = 2) -> str:
    if numero == 0:
        return '0'
    exp = int(np.floor(np.log10(abs(numero))))
    base = numero / (10 ** exp)
    return f'{base:.{decimales}f} x E{exp}'


# Console único del proceso principal: todo print concurrente con el Live del monitor
# (_ciclo_activo x N activos, _x2_watchdog, _log_error) debe salir por acá — es lo que le
# permite a rich.Live pausar el redraw, imprimir la línea "normal" en el scroll de arriba,
# y redibujar el bloque en vivo debajo sin corromperlo. Un print() suelto (o un segundo
# Console) escribe ANSI sin coordinar con el Live y revive el desync de _monitor_tabla
# (ver docs/context/decisiones.md, 2026-09-21).
console = Console()

# Compartido por todos los hilos del proceso principal (_ciclo_activo x N activos,
# _x2_watchdog) para que los print() de varias líneas salgan completos y nunca se
# intercalen entre sí — Console.print ya es thread-safe por su cuenta, pero varias
# llamadas separadas (ej. banner + detalle) igual pueden alternarse entre hilos sin este lock.
_stdout_lock = threading.Lock()


def _log_error(carpeta_logs: Path, contexto: str, exc: Exception) -> None:
    """Imprime el traceback completo de exc y lo agrega a {carpeta_logs}/errores.log.

    Complementa el mensaje corto de cada bloque try/except del loop principal: sin
    el traceback completo, diagnosticar la causa raíz de un error que ya no está
    en pantalla (o que nunca se vio, si la consola no se monitoreaba) depende de
    reproducirlo. El log es acumulativo, uno por línea de contexto con su traceback.
    """
    carpeta_logs.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    tb = traceback.format_exc()
    with _stdout_lock:
        console.print(Text(f'\n[{ts}] {contexto}: {exc}\n{tb}', style='bold red'))
    with open(carpeta_logs / 'errores.log', 'a') as f:
        f.write(f'\n[{ts}] {contexto}: {exc}\n{tb}')


# ─── Funciones del algoritmo ──────────────────────────────────────────────────

def _vecino_mas_cercano(valores: np.ndarray, low: np.ndarray, high: np.ndarray,
                        t: np.ndarray, block_size: int = BLOQUE_DISTANCIAS,
                        verbose: bool = True) -> tuple:
    """
    Para cada i, busca el j más cercano a la izquierda y a la derecha (en índice)
    cuyo rango [low[j], high[j]] contiene valores[i]. Devuelve las distancias
    temporales (t[i] - t[j] / t[j] - t[i]), con NaN cuando no hay vecino.

    Procesa por bloques de filas para vectorizar con numpy sin construir la
    matriz (n x n) completa, que no entra en memoria para series largas (n ~ 30k+).
    """
    n = len(valores)
    col = np.arange(n)
    dist_izq = np.full(n, np.nan)
    dist_der = np.full(n, np.nan)

    for inicio in tqdm.tqdm(range(0, n, block_size), disable=not verbose):
        fin = min(inicio + block_size, n)
        filas = np.arange(inicio, fin)
        v = valores[inicio:fin][:, None]
        contiene = (low[None, :] <= v) & (v <= high[None, :])

        izq = contiene & (col[None, :] < filas[:, None])
        idx_izq = (n - 1) - izq[:, ::-1].argmax(axis=1)
        hay_izq = izq.any(axis=1)
        dist_izq[inicio:fin] = np.where(hay_izq, t[filas] - t[idx_izq], np.nan)

        der = contiene & (col[None, :] > filas[:, None])
        idx_der = der.argmax(axis=1)
        hay_der = der.any(axis=1)
        dist_der[inicio:fin] = np.where(hay_der, t[idx_der] - t[filas], np.nan)

    return dist_izq, dist_der


def calcular_distancias(df: pd.DataFrame, find_low: bool = True, find_high: bool = True,
                        verbose: bool = True) -> pd.DataFrame:
    """
    Para cada vela i, busca la vela más cercana (izquierda y derecha en tiempo)
    cuyo rango [Low, High] contenga el Low (o High) de la vela i.
    La distancia temporal entre ambas velas es la columna Low_left / Low_right (o High_*).

    Una vela con distancias grandes en ambas direcciones es un "extremo aislado",
    candidato natural a soporte o resistencia.
    """
    df = df.copy()
    low = df['Low'].to_numpy()
    high = df['High'].to_numpy()
    t = df['t'].to_numpy()
    max_t = t.max()

    if find_low:
        df['Low_left'], df['Low_right'] = _vecino_mas_cercano(low, low, high, t, verbose=verbose)
    if find_high:
        df['High_left'], df['High_right'] = _vecino_mas_cercano(high, low, high, t, verbose=verbose)

    # Velas sin vecino (extremos del dataset): distancia hasta el borde del período
    if find_low:
        df['Low_left'] = df['Low_left'].fillna(df['t'])
        df['Low_right'] = df['Low_right'].fillna(max_t - df['t'])
    if find_high:
        df['High_left'] = df['High_left'].fillna(df['t'])
        df['High_right'] = df['High_right'].fillna(max_t - df['t'])

    return df


def obtener_df_extremos(df_0: pd.DataFrame, k: float, n_exp: float, N: int,
                         conjunto_N: set = set(), ocp: int = 0, verbose: bool = True,
                         identificador: str = '') -> tuple:
    """
    Calcula las columnas y (aislamiento) y w (recencia) usadas por la FO.
    Inicializa conjunto_N con puntos aleatorios si viene vacío o incompleto.
    ocp: órdenes de compra ya planificadas en la plataforma (fijas, no se optimizan).
    """
    df_extremos = calcular_distancias(df_0, verbose=verbose)

    if 'High_left' in df_extremos.columns:
        df_extremos['y'] = (df_extremos['High_left'] + df_extremos['Low_left']
                            + k * (df_extremos['High_right'] + df_extremos['Low_right']))
    else:
        df_extremos['y'] = df_extremos['Low_left'] + k * df_extremos['Low_right']

    df_extremos['w'] = df_extremos['t'] ** n_exp
    df_extremos['v'] = df_extremos['Tick_Volume'] / df_extremos['Tick_Volume'].max()

    rango = df_extremos['High'] - df_extremos['Low']
    df_extremos['f'] = 1 - (df_extremos['Close'] - df_extremos['Open']).abs() / rango

    p_min = df_extremos['Low'].min()
    p_max = df_extremos['Low'].max()

    ordenes_en_espera = N - ocp
    L = len(conjunto_N)

    if L < ordenes_en_espera:
        delta = ordenes_en_espera - L
        conjunto_N = conjunto_N.union(set(np.random.uniform(p_min, p_max, delta).tolist()))
    elif L > ordenes_en_espera:
        elementos_a_remover = set(random.sample(list(conjunto_N), L - ordenes_en_espera))
        conjunto_N = conjunto_N.difference(elementos_a_remover)

    if len(conjunto_N) != N:
        _log_diagnostico_conjunto_N(identificador, 'obtener_df_extremos_padding', {
            'N': N, 'ocp': ocp, 'ordenes_en_espera': ordenes_en_espera,
            'L_original': L, 'len_final': len(conjunto_N),
        })
        raise RuntimeError(f'Error en tamaño conjunto_N: {len(conjunto_N)} != {N}')

    return df_extremos, conjunto_N


def asignar_soporte(df: pd.DataFrame, soportes: set) -> pd.DataFrame:
    df = df.copy()
    soportes_arr = np.sort(np.array(list(soportes), dtype=np.float64))
    lows = df['Low'].to_numpy(dtype=np.float64)

    # Para cada Low, el soporte más cercano está entre el vecino izquierdo y derecho
    # en el array ordenado (búsqueda binaria en vez de comparar contra los N soportes)
    idx = np.searchsorted(soportes_arr, lows)
    idx_izq = np.clip(idx - 1, 0, len(soportes_arr) - 1)
    idx_der = np.clip(idx, 0, len(soportes_arr) - 1)
    izq, der = soportes_arr[idx_izq], soportes_arr[idx_der]

    df['soporte'] = np.where(np.abs(lows - izq) <= np.abs(lows - der), izq, der)
    return df


def calcular_FO(df_extremos: pd.DataFrame, conjunto_N: set, lambda_ponderador: float) -> tuple:
    """
    FO = mean(z) - lambda * cv(H_n)

    z = producto de los factores activos en `parametros_soportes` (config.py):
        y      → cuán aislada es la vela (candidato a soporte/resistencia)
        w      → peso temporal (velas recientes pesan más)
        h_dist → qué tan cerca está la vela del soporte asignado (normalizado)
        v      → volumen normalizado (Tick_Volume / max), proxy de actividad en ese nivel
        f      → fuerza del rechazo: proporción del rango que fue mecha (1 - |Close-Open|/(High-Low))

    cv(H_n) = std(H_n) / mean(H_n), donde H_n son las distancias entre soportes consecutivos,
    con P_min y P_max del período completo (df_extremos['Low']) como anclas de borde.
    Penaliza conjuntos donde los soportes están muy concentrados en una zona del rango,
    incluyendo cuando dejan un hueco grande entre el soporte extremo y el precio máximo/mínimo
    histórico (ej. una ruptura reciente que deja todos los soportes muy por debajo del precio).
    """
    df_extremos = asignar_soporte(df_extremos, conjunto_N)
    df_extremos['dist'] = (df_extremos['soporte'] - df_extremos['Low']) ** 2
    dist_max = df_extremos['dist'].max()
    df_extremos['h_dist'] = 1 - df_extremos['dist'] / dist_max

    factores = [nombre for nombre, activo in parametros_soportes.items() if activo]
    df_extremos['z'] = df_extremos[factores].prod(axis=1)

    p_min, p_max = df_extremos['Low'].min(), df_extremos['Low'].max()
    L_n = [p_min] + sorted(list(conjunto_N)) + [p_max]
    H_n = [L_n[i] - L_n[i - 1] for i in range(1, len(L_n))]
    cv_H = np.std(H_n) / np.mean(H_n)

    FO = float(df_extremos['z'].mean() - lambda_ponderador * cv_H)
    particion = [float(df_extremos['z'].mean()), float(cv_H)]
    return FO, df_extremos, particion


def calcular_FO_batch(df_extremos: pd.DataFrame, lista_N: list, idx_soporte: int,
                       candidatos: np.ndarray, lambda_ponderador: float,
                       dist_max_global: float = None) -> np.ndarray:
    """
    Evalúa la FO para todos los candidatos a soporte idx_soporte en una sola pasada vectorizada.
    Reemplaza el for-loop de M llamadas a calcular_FO en nuevo_optimizador_2.

    Para cada Low l_j, la distancia al soporte más cercano del conjunto {base ∪ c_k} es
    min(dist_base[j], |l_j - c_k|): se precomputa nearest_base una vez y se compara con
    los M candidatos via broadcasting (M_eff, n) sin iterar en Python.

    dist_max_global: si se pasa, normaliza h_dist con este valor fijo (igual que calcular_FO
    al inicio de la iteración) en vez de recomputarlo por candidato. Garantiza que la FO
    del batch es comparable con FO_base y evita el salto entre fases. h_dist se clipea a [0,1].

    cv(H_n) usa P_min/P_max de df_extremos['Low'] como anclas de borde, igual que calcular_FO.
    Los candidatos y base_soportes siempre caen dentro de [p_min, p_max] (así los genera
    nuevo_optimizador_2), por lo que concatenar sin reordenar preserva el orden ascendente.

    Returns: FO_values array (M_eff,)
    """
    if len(candidatos) == 0:
        return np.array([], dtype=np.float64)

    lows = df_extremos['Low'].to_numpy(dtype=np.float64)
    p_min, p_max = lows.min(), lows.max()
    M_eff = len(candidatos)

    # Base: soportes con idx_soporte removido (ya ordenados)
    base_soportes = np.array(lista_N[:idx_soporte] + lista_N[idx_soporte + 1:], dtype=np.float64)

    # Nearest support en base para cada Low (se computa una sola vez)
    idx_b = np.searchsorted(base_soportes, lows)
    idx_izq = np.clip(idx_b - 1, 0, len(base_soportes) - 1)
    idx_der = np.clip(idx_b, 0, len(base_soportes) - 1)
    izq_b, der_b = base_soportes[idx_izq], base_soportes[idx_der]
    nearest_base = np.where(np.abs(lows - izq_b) <= np.abs(lows - der_b), izq_b, der_b)
    dist_base_abs = np.abs(lows - nearest_base)  # shape (n,)

    # Para los M candidatos: nearest en {base ∪ c_k} = min(nearest_base, c_k) por distancia
    dist_to_cands = np.abs(lows[None, :] - candidatos[:, None])  # shape (M_eff, n)
    nearest_all = np.where(
        dist_to_cands < dist_base_abs[None, :],
        candidatos[:, None],
        nearest_base[None, :],
    )  # shape (M_eff, n)

    dist_sq = (nearest_all - lows[None, :]) ** 2
    if dist_max_global is not None:
        dm = max(dist_max_global, 1e-10)
        h_dist = np.clip(1.0 - dist_sq / dm, 0.0, 1.0)
    else:
        dist_max = dist_sq.max(axis=1)
        dist_max = np.where(dist_max == 0, 1.0, dist_max)
        h_dist = 1.0 - dist_sq / dist_max[:, None]  # shape (M_eff, n)

    factores = [nombre for nombre, activo in parametros_soportes.items() if activo]
    cols_fijos = [f for f in factores if f != 'h_dist']
    fixed = df_extremos[cols_fijos].prod(axis=1).to_numpy() if cols_fijos else np.ones(len(lows))
    z = (fixed[None, :] * h_dist) if 'h_dist' in factores else np.tile(fixed, (M_eff, 1))

    FO_means = z.mean(axis=1)  # shape (M_eff,)

    # cv(H_n): insertar c_k en base y calcular std/mean de gaps (loop O(M*N), trivial)
    insert_pos = np.searchsorted(base_soportes, candidatos)
    cv_Hn = np.empty(M_eff, dtype=np.float64)
    for k in range(M_eff):
        s_full = np.insert(base_soportes, insert_pos[k], candidatos[k])
        s_full = np.concatenate(([p_min], s_full, [p_max]))
        H_n = np.diff(s_full)
        mean_H = H_n.mean()
        cv_Hn[k] = H_n.std() / mean_H if mean_H != 0 else 0.0

    return FO_means - lambda_ponderador * cv_Hn


def evaluar_crecimiento_decrecimiento(df_plot: pd.DataFrame, metrica: str = 'y') -> bool:
    """
    True si la serie crece monotónicamente y luego decrece (forma de U invertida).
    Cuando se cumple, se puede ajustar una parábola para hallar el óptimo analíticamente.
    """
    df_plot = df_plot.reset_index(drop=True)
    crec, decrec = True, False
    for i in range(1, len(df_plot)):
        delta = df_plot[metrica][i] - df_plot[metrica][i - 1]
        if delta > 0 and decrec:
            return False
        if delta < 0 and crec:
            decrec = True
            crec = False
    return True


def nuevo_optimizador_2(N: int, df_extremos: pd.DataFrame, conjunto_N: set,
                         lambda_ponderador: float, ordenes_activas: list = [],
                         M: int = 100, max_iters: int = 1000,
                         prueba_cercanos: bool = False,
                         delta_inicial: float = 1e-4,
                         estado_compartido=None, llave: str = '',
                         verbose: bool = True, max_cambios: int = MAX_CAMBIOS) -> tuple:
    """
    Optimizador de búsqueda local sobre el conjunto N de soportes.

    En cada iteración j:
      Para cada soporte i (en orden de casos_moviles):
        - Genera M candidatos equidistantes entre el soporte anterior y el siguiente.
        - Evalúa todos en una pasada numpy vectorizada (calcular_FO_batch).
        - Si los puntos forman una U invertida → ajuste cuadrático para hallar el óptimo exacto.
        - Si no → toma el candidato con mayor FO.
        - Acepta el cambio solo si la mejora relativa supera delta_inicial.
      Si ningún soporte mejoró → expande casos_moviles a todos y vuelve a intentar.
      Si aun así no mejora → converge, sale del loop.

    ordenes_activas: precios fijos (ya están ejecutados en la plataforma, no se mueven).
    prueba_cercanos: si True, prioriza vecinos del soporte cambiado en la siguiente iteración.
    max_cambios: tope de cambios aceptados; al alcanzarse, corta y retorna la mejor solución
      hallada hasta ese punto con convergio=False (evita ciclos que nunca convergen).
    """
    if verbose:
        print(f'Iniciando optimizador | max_iters={max_iters} | N={N} | M={M}')
    convergio = False
    limite_cambios_alcanzado = False
    cambios = 0
    max_pasos = 0  # máx. posición alcanzada en el inner loop antes de aceptar un cambio

    # Inicializar conjunto_N respetando las ordenes activas
    delta = N - len(set(ordenes_activas)) - len(conjunto_N)
    delta2 = N - len(set(ordenes_activas))

    if delta2 < 0:
        _log_diagnostico_conjunto_N(llave, 'ordenes_activas_mayor_a_N', {
            'N': N, 'ordenes_activas': sorted(set(ordenes_activas)),
            'len_ordenes_activas': len(set(ordenes_activas)),
        })
        raise RuntimeError('Cantidad de ordenes activas es mayor a N')

    p_min = df_extremos['Low'].min()
    p_max = df_extremos['Low'].max()
    if verbose:
        print(f'Rango de precios: [{p_min:.2f}, {p_max:.2f}]')

    conjunto_N_pre_oa = set(conjunto_N)
    reset_completo = delta < 0 and delta2 > 0
    if delta >= 0:
        conjunto_N = conjunto_N.union(set(np.random.uniform(p_min, p_max, delta).tolist()))
    elif delta2 > 0:
        conjunto_N = set(np.random.uniform(p_min, p_max, delta2).tolist())

    conjunto_N = conjunto_N.union(set(ordenes_activas))

    if len(conjunto_N) != N:
        _log_diagnostico_conjunto_N(llave, 'init_post_union_oa', {
            'N': N, 'delta': delta, 'delta2': delta2, 'reset_completo_por_oa': reset_completo,
            'ordenes_activas': sorted(set(ordenes_activas)),
            'ya_presentes_en_conjunto_previo': sorted(set(ordenes_activas) & conjunto_N_pre_oa),
            'len_conjunto_previo': len(conjunto_N_pre_oa), 'len_final': len(conjunto_N),
        })
        raise RuntimeError(f'Error en tamaño conjunto_N tras inicialización: {len(conjunto_N)} != {N}')

    lista_N = sorted(list(conjunto_N))
    dic_N = {i: val for i, val in enumerate(lista_N)}
    casos_moviles = list(dic_N.keys())
    df_FO = pd.DataFrame()

    # Si se agotan max_iters sin convergencia real, no se detiene: se reinicia el
    # contador y se abre un nuevo ciclo tomando dic_N (mejor solución hallada) como
    # punto de partida. Sin tope de ciclos — corre indefinidamente hasta converger.
    ciclo = 1
    iter_offset = 0
    while True:
        for j in range(max_iters):
            lista_N = list(dic_N.values())
            conjunto_N = set(lista_N)

            if len(conjunto_N) != N:
                duplicados = {v: c for v, c in Counter(lista_N).items() if c > 1}
                indices_por_duplicado = {v: [k for k, val in dic_N.items() if val == v] for v in duplicados}
                _log_diagnostico_conjunto_N(llave, 'mid_loop_iteracion', {
                    'N': N, 'iteracion': j, 'cambios_hasta_ahora': cambios,
                    'valores_duplicados': duplicados,
                    'indices_por_duplicado': indices_por_duplicado,
                    'p_min': p_min, 'p_max': p_max,
                    'dic_N_min': min(dic_N.values()), 'dic_N_max': max(dic_N.values()),
                })
                raise RuntimeError(f'Error en tamaño conjunto_N en iteración {j}: {len(conjunto_N)} != {N}')

            FO_base, df_extremos, particion_FO = calcular_FO(df_extremos, conjunto_N, lambda_ponderador)
            dist_max_iter = float(df_extremos['dist'].max())
            mejora = False

            if estado_compartido is not None and llave:
                estado_compartido[llave] = (cambios, max_pasos, FO_base, 'corriendo')

            for pos, i in enumerate(tqdm.tqdm(casos_moviles, disable=not verbose)):
                if dic_N[i] in ordenes_activas:
                    continue  # no se mueve este soporte, ya está ejecutado en la plataforma
                cota_inf = dic_N[i - 1] if (i - 1) in dic_N else p_min
                cota_sup = dic_N[i + 1] if (i + 1) in dic_N else p_max

                # Candidatos equidistantes; se excluyen los extremos para evitar duplicar soportes vecinos
                casos_random = np.linspace(cota_inf, cota_sup, M)[1:-1]

                # Evalúa todos los M candidatos en una sola pasada numpy vectorizada
                FO_values = calcular_FO_batch(df_extremos, lista_N, i, casos_random, lambda_ponderador,
                                              dist_max_global=dist_max_iter)
                df_plot = pd.DataFrame({'caso': casos_random, 'FO_iter': FO_values})

                cumplen_logica = evaluar_crecimiento_decrecimiento(df_plot, 'FO_iter')
                if cumplen_logica:
                    coef = np.polyfit(df_plot['caso'], df_plot['FO_iter'], 2)
                    a_c, b_c, _ = coef
                    caso = float(np.clip(-b_c / (2 * a_c), cota_inf + 1e-8, cota_sup - 1e-8))
                    FO_iter = float(calcular_FO_batch(df_extremos, lista_N, i,
                                                       np.array([caso]), lambda_ponderador,
                                                       dist_max_global=dist_max_iter)[0])
                else:
                    idx_max = int(df_plot['FO_iter'].argmax())
                    caso = float(df_plot['caso'].iloc[idx_max])
                    FO_iter = float(df_plot['FO_iter'].iloc[idx_max])

                mejora_rel = (FO_iter - FO_base) / abs(FO_base)
                if mejora_rel > delta_inicial:
                    if verbose:
                        print(f'  Mejora {mejora_rel:.6f} en soporte i={i}, nuevo={caso:.2f}')
                    mejora = True
                    cambios += 1
                    max_pasos = max(max_pasos, pos + 1)
                    if estado_compartido is not None and llave:
                        estado_compartido[llave] = (cambios, max_pasos, FO_iter, 'corriendo')
                    i_change = i
                    nuevo_value = caso
                    lista_iter = lista_N[:]
                    lista_iter[i] = caso
                    FO_proper, df_extremos, particion_FO = calcular_FO(df_extremos, set(lista_iter),
                                                                        lambda_ponderador)
                    FO_base = FO_proper  # FO real (no batch) para plot y verbose

                if mejora:
                    break

            if not mejora:
                if len(casos_moviles) == len(dic_N):
                    convergio = True
                    break  # ya se probaron todos los soportes sin mejora → convergencia
                if verbose:
                    print('Sin mejora en casos actuales → ampliando a todos los soportes')
                casos_moviles = list(dic_N.keys())
            else:
                dic_N[i_change] = nuevo_value
                if verbose:
                    print(f'FO {j}: {notacion_cientifica(FO_base, 4)} | '
                          f'[{notacion_cientifica(particion_FO[0], 4)}, {notacion_cientifica(particion_FO[1], 4)}]')

                if prueba_cercanos:
                    vecinos = [i_change - 1, i_change + 1, i_change]
                    resto = [c for c in casos_moviles if c not in vecinos]
                    random.shuffle(resto)
                    casos_moviles = vecinos + resto
                else:
                    random.shuffle(casos_moviles)

            casos_moviles = [c for c in casos_moviles if 0 <= c < len(dic_N)]

            df_FO = pd.concat([df_FO, pd.DataFrame({
                'Iteracion': [iter_offset + j], 'FO': [FO_base],
                'FO1': [particion_FO[0]], 'FO2': [particion_FO[1]],
                'ratio': [particion_FO[0] / particion_FO[1]],
            })])

            if cambios >= max_cambios:
                limite_cambios_alcanzado = True
                if verbose:
                    print(f'--- Límite de {max_cambios} cambios alcanzado, '
                          f'se toma la mejor solución hallada hasta ahora ---')
                break

        if convergio or limite_cambios_alcanzado:
            break
        iter_offset += max_iters
        ciclo += 1
        casos_moviles = list(dic_N.keys())
        if verbose:
            print(f'--- Ciclo {ciclo}: {max_iters} iteraciones agotadas sin convergencia, '
                  f'reinicio desde la mejor solución encontrada hasta ahora ---')

    conjunto_N = set(dic_N.values())
    return conjunto_N, df_extremos, df_FO, convergio, cambios, max_pasos


# ─── Visualizaciones ──────────────────────────────────────────────────────────

def _guardar_plot(nombre_subcarpeta: str, nombre_archivo: str):
    carpeta = CARPETA_PLOTS / nombre_subcarpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    plt.savefig(carpeta / f'{nombre_archivo}.png', bbox_inches='tight')
    plt.close()


def graficar_df_extremos(df_extremos: pd.DataFrame, valor: str = '', N: int = 0,
                          graficar: bool = False):
    if not graficar:
        return
    fig, axes = plt.subplots(2, 2, figsize=(21, 10))
    fig.suptitle(f'Extremos — {valor} N={N}', fontsize=14)
    for ax, col, color, titulo in zip(
        axes.flat,
        ['y', 'w', 'h_dist', 'z'],
        ['r', 'm', 'c', 'black'],
        ['y (aislamiento)', 'w (recencia)', 'h_dist (ajuste a soporte)', 'z = y·w·h_dist'],
    ):
        ax.plot(df_extremos['DateTime'], df_extremos[col], color=color)
        ax.set_title(titulo)
        ax.grid()
    plt.tight_layout()
    _guardar_plot('Extremos', f'{valor}_{N}')


def graficar_performance_FO(df_FO: pd.DataFrame, valor: str = '', N: int = 0,
                             graficar: bool = False):
    if not graficar or len(df_FO) <= 1:
        return
    _, ax1 = plt.subplots(figsize=(21, 7))
    ax1.plot(df_FO['Iteracion'], df_FO['FO'], color='b', label='FO')
    ax1.set_ylabel('FO')
    ax1.grid()
    plt.title(f'Evolución FO por iteración — {valor} N={N}')
    _guardar_plot('FO', f'{valor}_{N}')


def graficar_soportes_all(df_0: pd.DataFrame, conjunto_N: set, valor: str = '', N: int = 0,
                           graficar: bool = False, zoom: bool = False, ordenes_activas: list = []):
    if not graficar and not zoom:
        return
    df_plot = df_0.tail(100) if zoom else df_0
    p_min, p_max = df_plot['Low'].min(), df_plot['High'].max()
    sufijo = ' (zoom)' if zoom else ''
    fig, ax = plt.subplots(figsize=(21, 7))
    ax.set_title(f'Soportes{sufijo} — {valor} N={N}')
    line_low, = ax.plot(df_plot['DateTime'], df_plot['Low'], color='b', label='Low')
    line_high, = ax.plot(df_plot['DateTime'], df_plot['High'], color='g', label='High')

    oa_set = set(ordenes_activas)
    soportes_normales = [s for s in sorted(conjunto_N) if s not in oa_set]
    soportes_oa = [s for s in sorted(conjunto_N) if s in oa_set]

    for s in soportes_normales:
        if p_min <= s <= p_max:
            ax.axhline(y=s, color='r', linestyle='--', alpha=0.5)
    for s in soportes_oa:
        if p_min <= s <= p_max:
            ax.axhline(y=s, color='black', linestyle='-', linewidth=1.2, alpha=0.85)

    legend_handles = [
        line_low,
        line_high,
        Line2D([0], [0], color='r', linestyle='--', alpha=0.5,
               label=f'Soportes ({len(soportes_normales)})'),
    ]
    if soportes_oa:
        legend_handles.append(
            Line2D([0], [0], color='black', linestyle='-', linewidth=1.2,
                   label=f'OA — órdenes activas ({len(soportes_oa)})')
        )
    ax.legend(handles=legend_handles)
    ax.grid()
    subcarpeta = 'Zoom' if zoom else 'Soportes'
    _guardar_plot(subcarpeta, f'{valor}_{N}')


def graficar_soportes_demo(df_0: pd.DataFrame, conjunto_N: set, ruta_png: Path,
                            valor: str, N: int, ordenes_activas: list = []) -> Path:
    """
    Guarda en `ruta_png` el gráfico de los precios usados en esta búsqueda (t0 → tf)
    con el conjunto N encontrado.

    El algoritmo entrega una sola lista de niveles; acá se separan visualmente según
    dónde quedó el precio en tf: los que están por debajo actúan como soportes
    (zona de compra) y los que quedan por encima como resistencias.
    """
    precio_ref = float(df_0['Close'].iloc[-1])
    t0, tf = df_0['DateTime'].iloc[0], df_0['DateTime'].iloc[-1]
    p_min, p_max = df_0['Low'].min(), df_0['High'].max()
    oa_set = set(ordenes_activas)

    fig, ax = plt.subplots(figsize=(21, 8))
    ax.plot(df_0['DateTime'], df_0['Low'], color='tab:blue', linewidth=0.8, label='Low')
    ax.plot(df_0['DateTime'], df_0['High'], color='tab:green', linewidth=0.8, label='High')

    n_sop = n_res = 0
    for s in sorted(conjunto_N):
        if not (p_min <= s <= p_max):
            continue
        if s in oa_set:
            ax.axhline(y=s, color='black', linestyle='-', linewidth=1.2, alpha=0.9)
            continue
        es_soporte = s <= precio_ref
        ax.axhline(y=s, color='tab:green' if es_soporte else 'tab:red',
                   linestyle='--', linewidth=0.7, alpha=0.45)
        n_sop += es_soporte
        n_res += not es_soporte

    ax.axhline(y=precio_ref, color='black', linestyle='-', linewidth=1.6)

    handles = [
        Line2D([0], [0], color='tab:blue', label='Low'),
        Line2D([0], [0], color='tab:green', label='High'),
        Line2D([0], [0], color='tab:green', linestyle='--',
               label=f'Soportes — bajo el precio ({n_sop})'),
        Line2D([0], [0], color='tab:red', linestyle='--',
               label=f'Resistencias — sobre el precio ({n_res})'),
        Line2D([0], [0], color='black', linewidth=1.6,
               label=f'Precio en tf ({precio_ref:.2f})'),
    ]
    if oa_set:
        handles.append(Line2D([0], [0], color='black', linewidth=1.2,
                              label=f'OA — órdenes abiertas ({len(oa_set)})'))
    ax.legend(handles=handles, loc='upper left', fontsize=9)
    ax.set_title(f'{valor} — N={N} soportes/resistencias\n'
                 f't0 = {t0}   →   tf = {tf}   ({len(df_0)} velas H1)')
    ax.grid(alpha=0.3)
    plt.tight_layout()

    ruta_png = Path(ruta_png)
    ruta_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ruta_png, dpi=110)
    plt.close(fig)
    return ruta_png


# ─── Etapa 1: Descarga de datos desde MT5 ────────────────────────────────────

def obtener_ordenes_activas_mt5(valores: list) -> dict:
    """
    Retorna {valor: [precios de posiciones abiertas]} desde MT5.
    Solo incluye posiciones ejecutadas (OA), no órdenes pendientes (OE).
    Si MT5 no está disponible (Mac, error), retorna listas vacías sin abortar.
    """
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            console.print('MT5 no disponible — ordenes_activas vacías para todos los activos')
            return {v: [] for v in valores}
        result = {}
        for valor in valores:
            positions = mt5.positions_get(symbol=valor) or []
            result[valor] = [p.price_open for p in positions]
            if result[valor]:
                console.print(f'  {valor}: {len(result[valor])} posición(es) activa(s) → fija(s) en optimizador')
        mt5.shutdown()
        return result
    except ImportError:
        return {v: [] for v in valores}


def _leer_csv_reintentos(csv_path: Path, intentos: int = 5, espera: float = 0.5) -> pd.DataFrame:
    """Lee un CSV con reintentos ante OSError transitorios (sync de OneDrive u otro
    proceso escribiendo el mismo archivo), mismo patrón que `json_act`.

    Sin esto, una lectura que agarra el archivo a mitad de un sync puede devolver
    una versión parcial sin lanzar excepción — y el merge subsiguiente la escribiría
    como si fuera el histórico completo, perdiendo todo lo anterior en silencio."""
    for intento in range(intentos):
        try:
            return pd.read_csv(csv_path)
        except OSError:
            if intento == intentos - 1:
                raise
            time.sleep(espera)


def _guardar_csv_atomico(data: pd.DataFrame, csv_path: Path) -> None:
    """Escribe a un .tmp y hace os.replace, para que un lector concurrente nunca
    vea el archivo truncado a mitad de escritura (mismo patrón que json_act)."""
    tmp_path = csv_path.with_suffix(csv_path.suffix + '.tmp')
    data.to_csv(tmp_path, index=False)
    os.replace(tmp_path, csv_path)


def _mergear_con_historico(df: pd.DataFrame, csv_path: Path) -> pd.DataFrame:
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    if csv_path.exists():
        data_old = _leer_csv_reintentos(csv_path)
        data_old['DateTime'] = pd.to_datetime(data_old['DateTime'])
        return (pd.concat([df, data_old])
                .drop_duplicates(subset=['DateTime'])
                .sort_values('DateTime')
                .reset_index(drop=True))
    return df


def descargar_datos(valores: list, carpeta_data: Path, verbose: bool = True):
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialize() falló: {mt5.last_error()}')

    for valor in valores:
        if verbose:
            console.print(f'\nDescargando {valor}...')
        mt5.symbol_select(valor, True)
        rates = mt5.copy_rates_from_pos(valor, mt5.TIMEFRAME_H1, 0, 1000)

        if rates is None:
            if verbose:
                console.print(f'  Sin datos para {valor}, skip')
            continue

        df = pd.DataFrame(rates)
        try:
            df['time'] = pd.to_datetime(df['time'], unit='s')
        except Exception as e:
            if verbose:
                console.print(f'  Error al convertir tiempo para {valor}: {e}')
            continue

        df.columns = ['DateTime', 'Open', 'High', 'Low', 'Close', 'Tick_Volume', 'Spread', 'Real_Volume']

        # Merge con histórico: los datos nuevos tienen prioridad para pisar la última vela abierta
        csv_path = carpeta_data / f'{valor}.csv'
        data = _mergear_con_historico(df, csv_path)
        _guardar_csv_atomico(data, csv_path)
        if verbose:
            console.print(f'  Guardado: {csv_path.name} ({len(data)} velas, último: {df["DateTime"].iloc[-1]})')

    mt5.shutdown()


def detectar_gap_bt_eth(carpeta_data: Path, fecha_desde: datetime.datetime,
                         umbral_horas: float = 3.0):
    """Revisa BTCUSD/ETHUSD (mercado 24/7 — cualquier hueco real en H1 es anómalo, a
    diferencia de las acciones que tienen huecos normales por horario de mercado) buscando
    velas faltantes en la serie desde `fecha_desde`. Devuelve el datetime de inicio del
    hueco más antiguo encontrado (o None si no hay ninguno) — sirve como fecha de partida
    para un backfill automático, igual al bug que dejó `Data/` con historia truncada tras
    un sync de OneDrive."""
    gap_mas_antiguo = None
    for valor in ('BTCUSD', 'ETHUSD'):
        csv_path = carpeta_data / f'{valor}.csv'
        if not csv_path.exists():
            continue
        df = _leer_csv_reintentos(csv_path)
        df['DateTime'] = pd.to_datetime(df['DateTime'])
        df = df[df['DateTime'] >= fecha_desde].sort_values('DateTime').reset_index(drop=True)
        if len(df) < 2:
            continue
        gaps = df['DateTime'].diff()
        for idx in gaps[gaps > pd.Timedelta(hours=umbral_horas)].index:
            inicio_gap = df['DateTime'].iloc[idx - 1]
            if gap_mas_antiguo is None or inicio_gap < gap_mas_antiguo:
                gap_mas_antiguo = inicio_gap
    return gap_mas_antiguo


def backfill_historico(valores: list, carpeta_data: Path, fecha_desde: datetime.datetime):
    """Trae el historial H1 completo disponible en el broker desde `fecha_desde` hasta hoy
    (vía copy_rates_range, sin el tope de 1000 velas de descargar_datos) y lo mergea con el
    CSV existente. Uso puntual (`--backfill`), no se llama desde el loop normal."""
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialize() falló: {mt5.last_error()}')

    # copy_rates_range exige datetimes timezone-aware en UTC (documentación oficial de
    # MetaTrader5); pasar naive dispara RES_E_INVALID_PARAMS (-2, "Terminal: invalid params").
    if fecha_desde.tzinfo is None:
        fecha_desde = fecha_desde.replace(tzinfo=datetime.timezone.utc)
    fecha_hasta = datetime.datetime.now(datetime.timezone.utc)
    for valor in valores:
        console.print(f'\nBackfill {valor} desde {fecha_desde.date()}...')
        mt5.symbol_select(valor, True)

        # copy_rates_range devuelve None (sin excepción) cuando el terminal todavía no
        # tiene esa historia cacheada localmente: la primera llamada dispara la descarga
        # al servidor del broker en segundo plano y el resultado no está listo todavía.
        # Reintentar con espera le da tiempo a esa descarga antes de rendirse.
        rates = None
        intentos_backfill = 5
        for intento in range(intentos_backfill):
            rates = mt5.copy_rates_range(valor, mt5.TIMEFRAME_H1, fecha_desde, fecha_hasta)
            if rates is not None and len(rates) > 0:
                break
            if intento < intentos_backfill - 1:
                console.print(f'  Sin datos aún (intento {intento + 1}/{intentos_backfill}, '
                              f'last_error={mt5.last_error()}), esperando descarga del broker...')
                time.sleep(3)

        if rates is None or len(rates) == 0:
            console.print(f'  Sin datos para {valor} tras {intentos_backfill} intentos '
                          f'(last_error={mt5.last_error()}) — probablemente el terminal no tiene '
                          f'esa historia cacheada. Abre el gráfico H1 de {valor} en MT5 y haz scroll '
                          f'hasta {fecha_desde.date()} para forzar la descarga, luego reintenta.')
            continue

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.columns = ['DateTime', 'Open', 'High', 'Low', 'Close', 'Tick_Volume', 'Spread', 'Real_Volume']

        csv_path = carpeta_data / f'{valor}.csv'
        data = _mergear_con_historico(df, csv_path)
        _guardar_csv_atomico(data, csv_path)
        console.print(f'  Guardado: {csv_path.name} ({len(data)} velas totales, {len(df)} traídas del broker, '
                      f'rango {data["DateTime"].min()} → {data["DateTime"].max()})')

    mt5.shutdown()


def descargar_datos_minuto(valores: list, carpeta_data_minuto: Path, verbose: bool = True):
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialize() falló: {mt5.last_error()}')

    for valor in valores:
        if verbose:
            console.print(f'\nDescargando M1 {valor}...')
        mt5.symbol_select(valor, True)
        rates = mt5.copy_rates_from_pos(valor, mt5.TIMEFRAME_M1, 0, 1000)

        if rates is None:
            if verbose:
                console.print(f'  Sin datos para {valor}, skip')
            continue

        df = pd.DataFrame(rates)
        try:
            df['time'] = pd.to_datetime(df['time'], unit='s')
        except Exception as e:
            if verbose:
                console.print(f'  Error al convertir tiempo para {valor}: {e}')
            continue

        df.columns = ['DateTime', 'Open', 'High', 'Low', 'Close', 'Tick_Volume', 'Spread', 'Real_Volume']

        csv_path = carpeta_data_minuto / f'{valor}.csv'
        data = _mergear_con_historico(df, csv_path)
        _guardar_csv_atomico(data, csv_path)
        if verbose:
            console.print(f'  Guardado: {csv_path.name} ({len(data)} velas M1, último: {df["DateTime"].iloc[-1]})')

    mt5.shutdown()


# ─── Etapa 2: Búsqueda de soportes óptimos ───────────────────────────────────

def _leer_json_reintentos(path: Path, intentos: int = 10, espera: float = 0.2) -> dict:
    """Lee un JSON reabriendo el archivo en cada intento ante OSError/JSONDecodeError/
    PermissionError transitorios (sync de OneDrive u otro proceso escribiendo el mismo
    cache al mismo tiempo — varios workers de ProcessPoolExecutor comparten este archivo
    en modo bt). Mismo patrón que `_flush_json_list` (X4_backtester.py) y `json_act`
    (X1_trading.py)."""
    for intento in range(intentos):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, PermissionError, OSError):
            if intento == intentos - 1:
                raise
            time.sleep(espera)


def _bt_solucion_previa(carpeta_n_bt: Path, valor: str, N: int, fecha_hora_max) -> tuple:
    """
    Solución previa del combo (valor, N) en el cache bt: la más reciente con
    timestamp t* <= fecha_hora_max. Retorna (t*, conjunto_N); (None, set()) si no hay.

    Es el warm start del backtesting: si ya se resolvió (valor, N) en un t anterior,
    ese conjunto sirve como solución inicial para resolver el t actual.
    """
    bt_path = carpeta_n_bt / f'{valor}_{N}_bt.json'
    if not bt_path.exists():
        return None, set()
    cache = _leer_json_reintentos(bt_path)
    candidatos = {k: v for k, v in cache.items() if pd.to_datetime(k) <= fecha_hora_max}
    if not candidatos:
        return None, set()
    mejor_t = max(candidatos, key=lambda k: pd.to_datetime(k))
    return mejor_t, set(candidatos[mejor_t])


def _bt_warm_start(carpeta_n_bt: Path, valor: str, N: int, fecha_hora_max) -> set:
    """Conjunto_N del cache bt más reciente con timestamp <= fecha_hora_max."""
    return _bt_solucion_previa(carpeta_n_bt, valor, N, fecha_hora_max)[1]


def _bt_guardar(carpeta_n_bt: Path, valor: str, N: int, fecha_hora_clave, conjunto_N: set):
    """Upsert de conjunto_N en el cache bt con clave = último datetime de los datos usados.

    Escritura atómica (tmp + os.replace): varios workers de ProcessPoolExecutor
    (uno por activo) pueden escribir su propio `{valor}_{N}_bt.json` mientras otro
    worker lee el mismo archivo vía `_bt_solucion_previa` — sin esto, un lector podía
    encontrar el archivo truncado a mitad de escritura (`OSError: [Errno 22]`).
    """
    bt_path = carpeta_n_bt / f'{valor}_{N}_bt.json'
    cache = _leer_json_reintentos(bt_path) if bt_path.exists() else {}
    cache[str(fecha_hora_clave)] = sorted(conjunto_N)
    tmp_path = bt_path.with_suffix(bt_path.suffix + '.tmp')
    with open(tmp_path, 'w') as f:
        json.dump(cache, f)
    os.replace(tmp_path, bt_path)


def _log_diagnostico_conjunto_N(identificador: str, escenario: str, datos: dict):
    """Vuelca a un JSON el contexto de un fallo de tamaño en conjunto_N (len != N).

    Estos fallos ocurren dentro de un worker de ProcessPoolExecutor, cuyo stdout está
    silenciado (línea ~24): sin este archivo, el print de contexto nunca se vería.
    El caller relanza como RuntimeError (nunca sys.exit) para que `except Exception` en
    _ciclo_activo lo capture, marque solo ese combo como error y siga con el resto.
    """
    carpeta = CARPETA_LOGS / 'diag_conjunto_N'
    carpeta.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    ruta = carpeta / f'{(identificador or "sin_id")}_{escenario}_{ts}.json'
    entrada = {'identificador': identificador, 'escenario': escenario,
               'timestamp': datetime.datetime.now().isoformat(), **datos}
    with open(ruta, 'w') as f:
        json.dump(entrada, f, indent=2, default=str)


def _guardar_log_convergencia(valor: str, N: int, es_bt: bool, clave_bt: str,
                              t_inicio: float, t_fin: float,
                              iteraciones: int, cambios: int,
                              FO_inicial: float, FO_final: float,
                              delta_final: float, convergio: bool):
    """Agrega una entrada al log de convergencia de un combo (valor, N) en resources/x0/logs/.

    Formato JSONL (una entrada por línea, solo apertura en modo 'a'): evita el
    read-modify-write de un array completo en cada guardado, que bajo sync de OneDrive
    o acceso concurrente de otro proceso al mismo archivo fallaba con OSError al leer.
    """
    CARPETA_LOGS.mkdir(parents=True, exist_ok=True)
    sufijo = '_bt' if es_bt else ''
    log_path = CARPETA_LOGS / f'{valor}_{N}{sufijo}.jsonl'

    clave = f'{valor}_{N}_{clave_bt}' if (es_bt and clave_bt) else f'{valor}_{N}'
    entrada = {
        'clave': clave,
        't_inicio': datetime.datetime.fromtimestamp(t_inicio).isoformat(),
        't_fin': datetime.datetime.fromtimestamp(t_fin).isoformat(),
        'duracion_s': round(t_fin - t_inicio, 2),
        'iteraciones': iteraciones,
        'cambios': cambios,
        'FO_inicial': round(FO_inicial, 8),
        'FO_final': round(FO_final, 8),
        'delta_final': delta_final,
        'convergio': convergio,
    }
    with open(log_path, 'a') as f:
        f.write(json.dumps(entrada) + '\n')


def _procesar_valor_N(valor: str, N: int, carpeta_data: Path,
                      carpeta_n_prod: Path, carpeta_n_bt: Path,
                      ordenes_activas: list = [], fecha_hora_max=None,
                      estado_compartido=None, verbose: bool = True,
                      ordenes_abiertas_bt: list = [],
                      params_soporte: dict = None, cold_start: bool = False,
                      warm_start: bool = True, ruta_plot=None):
    """Worker para ProcessPoolExecutor: procesa un único par (valor, N).

    fecha_hora_max: datetime opcional. Si se pasa, modo backtesting — filtra datos hasta
                   esa fecha/hora y usa/actualiza el cache _bt.json en lugar de producción.
    ordenes_abiertas_bt: en modo bt, precios de posiciones abiertas (OA) que no deben moverse.
                         Son buy limits que ya se ejecutaron y siguen activas en la simulación.
    params_soporte: dict opcional {K, N_EXP, LAMBDA} que sobrescribe las globales de config.py.
                    Lo usa X4 --x5 para calcular soportes con los params explorados del ciclo.
    cold_start: si True, ignora el delta adaptado del combo y parte del delta semilla
                (DELTA_INICIAL). X4 --x5 lo activa: cambian los params en cada tramo, así que
                heredar la presión acumulada dejaría al optimizador satisfecho de entrada.
    warm_start: si True (default), usa como solución inicial la solución previa del mismo
                combo (valor, N) — cache bt con t* <= fecha_hora_max en backtesting, JSON de
                producción si no. Con False parte de puntos aleatorios.
    ruta_plot:  si se pasa, guarda ahí el gráfico de precios (t0 → tf) con los soportes
                encontrados. Usado por el modo demo de X5, donde también aplica en bt.

    Retorna un dict con la metadata de la corrida (rango usado, warm start, FO, duración)
    o None si el combo se saltó por falta de datos.
    """
    t_inicio = time.time()
    es_bt = fecha_hora_max is not None
    K_      = params_soporte['K']      if params_soporte else K
    N_EXP_  = params_soporte['N_EXP']  if params_soporte else N_EXP
    LAMBDA_ = params_soporte['LAMBDA'] if params_soporte else LAMBDA
    llave = f'{valor}_{N}'
    if verbose:
        print(f'\n{"="*55}\nProcesando {valor} N={N}' + (f' [bt hasta {fecha_hora_max}]' if es_bt else ''))
    if estado_compartido is not None:
        estado_compartido[llave] = (0, 0, 0.0, 'preparando')

    csv_path = carpeta_data / f'{valor}.csv'
    if not csv_path.exists():
        if verbose:
            print(f'  CSV no encontrado: {csv_path}, skip')
        if estado_compartido is not None:
            estado_compartido[llave] = (0, 0, 0.0, 'sin CSV')
        return

    df = pd.read_csv(csv_path)
    df = df.sort_values('DateTime').drop_duplicates(subset=['DateTime']).reset_index(drop=True)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df = df[df['DateTime'] >= FECHA_INICIAL].reset_index(drop=True)
    if es_bt:
        df = df[df['DateTime'] <= fecha_hora_max].reset_index(drop=True)

    if len(df) == 0:
        if verbose:
            print(f'  Sin datos para el rango solicitado, skip')
        if estado_compartido is not None:
            estado_compartido[llave] = (0, 0, 0.0, 'sin datos')
        return

    # Con <2 velas (o rango de precio degenerado) no hay varianza para generar
    # N soportes distintos: np.random.uniform(p_min, p_max, N) con p_min==p_max
    # produce N floats idénticos que colapsan a 1 elemento al pasar a set(),
    # y obtener_df_extremos revienta con RuntimeError. Se salta igual que
    # "sin datos" en vez de crashear todo el backtest.
    if len(df) < 2 or df['Low'].max() == df['Low'].min():
        if verbose:
            print(f'  Rango de precio degenerado ({len(df)} vela(s)), skip')
        if estado_compartido is not None:
            estado_compartido[llave] = (0, 0, 0.0, 'rango degenerado')
        return

    fecha_hora_clave = df['DateTime'].iloc[-1]
    if verbose:
        print(f'  Rango: {df["DateTime"].iloc[0]} → {fecha_hora_clave} ({len(df)} velas)')
        if not es_bt:
            print(f'  Último cierre: {df["Close"].iloc[-1]:.2f}')

    dt_min = df['DateTime'].min()
    df['t'] = (df['DateTime'] - dt_min).dt.total_seconds() / 3600
    df['t'] = df['t'] / df['t'].max()

    # Warm start: solución previa del mismo combo (valor, N) resuelta en un t* < t
    json_path = carpeta_n_prod / f'{valor}_{N}'  # ruta de guardado en producción
    ws_t = None
    if not warm_start:
        conjunto_N_prev = set()
        if verbose:
            print('  Warm start desactivado: partiendo de puntos aleatorios')
    elif es_bt:
        ws_t, conjunto_N_prev = _bt_solucion_previa(carpeta_n_bt, valor, N, fecha_hora_max)
        if verbose:
            print(f'  Warm start bt: {len(conjunto_N_prev)} soportes desde t*={ws_t}'
                  if conjunto_N_prev else '  Warm start bt: sin solución previa')
    else:
        conjunto_N_prev = set()
        if Path(f'{json_path}.json').exists():
            conjunto_N_prev = set(json_act(str(json_path)))
            ws_t = str(datetime.datetime.fromtimestamp(
                Path(f'{json_path}.json').stat().st_mtime).replace(microsecond=0))
            if verbose:
                print(f'  Warm start: {len(conjunto_N_prev)} soportes desde JSON (t*={ws_t})')

    # Delta
    delta_path = (carpeta_n_bt if es_bt else carpeta_n_prod) / (
        f'{valor}_{N}_bt_delta.json' if es_bt else f'{valor}_{N}_delta.json'
    )
    if cold_start:
        delta_actual = DELTA_INICIAL
        if verbose:
            print(f'  delta_inicial semilla (params nuevos): {notacion_cientifica(delta_actual)}')
    elif delta_path.exists():
        with open(delta_path) as f:
            delta_actual = json.load(f)['delta_inicial']
        if verbose:
            print(f'  delta_inicial cargado: {notacion_cientifica(delta_actual)}')
    else:
        delta_actual = DELTA_INICIAL
        if verbose:
            print(f'  delta_inicial semilla (sin estado previo): {notacion_cientifica(delta_actual)}')

    if verbose:
        print('  Calculando distancias...')
    if estado_compartido is not None:
        estado_compartido[llave] = (0, 0, 0.0, 'calc. distancias')
    df_extremos, conjunto_N = obtener_df_extremos(df, K_, N_EXP_, N, conjunto_N_prev, verbose=verbose,
                                                   identificador=llave)

    FO_ref, _, _ = calcular_FO(df_extremos, conjunto_N, LAMBDA_)
    if verbose:
        print(f'  FO inicial: {notacion_cientifica(FO_ref)}')
    if estado_compartido is not None:
        estado_compartido[llave] = (0, 0, FO_ref, 'iniciando')

    oa = ordenes_abiertas_bt if es_bt else ordenes_activas
    if oa and verbose:
        print(f'  Órdenes activas fijas: {[round(p, 2) for p in oa]}')
    # Fase 1: exploración barata con M_COARSE
    conjunto_N, df_extremos, df_FO_1, _, cambios_1, max_pasos_1 = nuevo_optimizador_2(
        N, df_extremos, conjunto_N, LAMBDA_,
        ordenes_activas=oa, M=M_COARSE, max_iters=MAX_ITERS, delta_inicial=delta_actual,
        estado_compartido=estado_compartido, llave=llave, verbose=verbose,
    )
    # Fase 2: refinamiento fino con M (warm start desde resultado de fase 1)
    conjunto_N, df_extremos, df_FO_2, convergio, cambios_2, max_pasos_2 = nuevo_optimizador_2(
        N, df_extremos, conjunto_N, LAMBDA_,
        ordenes_activas=oa, M=M, max_iters=MAX_ITERS, delta_inicial=delta_actual,
        estado_compartido=estado_compartido, llave=llave, verbose=verbose,
    )
    if not df_FO_2.empty:
        df_FO_2['Iteracion'] += len(df_FO_1)
    df_FO = pd.concat([df_FO_1, df_FO_2], ignore_index=True)
    max_pasos = max(max_pasos_1, max_pasos_2)
    # Soportes cuya posición final difiere del warm start inicial
    cambios_netos = len(conjunto_N_prev - conjunto_N) if conjunto_N_prev else N
    if verbose:
        print(f'  Cambios netos (vs. warm start) {valor} {N}: {cambios_netos}')

    if not es_bt:
        graficar_df_extremos(df_extremos, valor=valor, N=N, graficar=GRAFICAR_EXTREMOS)
        graficar_performance_FO(df_FO, valor=valor, N=N, graficar=GRAFICAR_FO)
        graficar_soportes_all(df, conjunto_N, valor=valor, N=N, graficar=GRAFICAR_SOPORTES, zoom=GRAFICAR_ZOOM,
                              ordenes_activas=oa)

    plot_generado = None
    if ruta_plot is not None:
        try:
            plot_generado = str(graficar_soportes_demo(df, conjunto_N, ruta_plot,
                                                       valor, N, ordenes_activas=oa))
        except Exception as e:
            plot_generado = f'ERROR: {e}'

    # Guardar soportes
    if es_bt:
        _bt_guardar(carpeta_n_bt, valor, N, fecha_hora_clave, conjunto_N)
        if verbose:
            print(f'  Guardado bt: {valor}_{N}_bt.json [{fecha_hora_clave}]')
    else:
        json_act(str(json_path), conjunto_N, 'save')
        if verbose:
            print(f'  Guardado: {json_path}.json')

    FO_final, _, _ = calcular_FO(df_extremos, conjunto_N, LAMBDA_)

    # Si la mejora neta es menor que delta_actual, el warm start era esencialmente óptimo:
    # el optimizador cicló sin ganar terreno real (inner loop rompe al primer vecino mejorable,
    # nunca completa el scan completo). Tratar como convergido para que delta se reduzca.
    if not convergio and abs(FO_ref) > 0:
        if abs((FO_final - FO_ref) / abs(FO_ref)) < delta_actual:
            convergio = True

    # Guardar delta
    delta_next = delta_actual * FACTOR_DELTA if convergio else delta_actual
    estado_delta = (f'convergió → {notacion_cientifica(delta_actual)} → {notacion_cientifica(delta_next)}'
                    if convergio else f'no convergió → delta sin cambio ({notacion_cientifica(delta_actual)})')
    if verbose:
        print(f'  Delta: {estado_delta}')
    with open(delta_path, 'w') as f:
        json.dump({'delta_inicial': delta_next, 'convergio': convergio}, f)
    if verbose:
        print(f'  Guardado: {delta_path.name}')
    t_fin = time.time()

    clave_bt = str(fecha_hora_clave) if es_bt else ''
    _guardar_log_convergencia(
        valor, N, es_bt, clave_bt,
        t_inicio, t_fin,
        len(df_FO), cambios_netos,
        FO_ref, FO_final,
        delta_next, convergio,
    )
    duracion = t_fin - t_inicio
    if verbose:
        mins = int(duracion // 60)
        segs = duracion % 60
        print(f'  Log guardado: {valor}_{N}{"_bt" if es_bt else ""}.json '
              f'({mins}m {segs:.1f}s | iters={len(df_FO)} | convergio={convergio})')

    if estado_compartido is not None:
        estado_compartido[llave] = (cambios_netos, -1, FO_final, 'convergencia')

    return {
        'valor': valor, 'N': N,
        't0': str(df['DateTime'].iloc[0]), 'tf': str(fecha_hora_clave),
        'n_velas': len(df),
        'warm_start_n': len(conjunto_N_prev), 'warm_start_t': ws_t,
        'FO_inicial': FO_ref, 'FO_final': FO_final,
        'convergio': convergio, 'duracion': round(duracion, 1),
        'plot': plot_generado,
    }


# Mapeo estado_str → texto de fase mostrado en la línea en vivo de cada combo. Los estados
# no listados acá (ej. 'corriendo', 'ERROR: ...') tienen formato especial en _texto_linea_combo;
# cualquier estado nuevo no mapeado cae al fallback (se muestra tal cual, ver abajo).
_FASES = {
    'esperando': 'Esperando',
    'preparando': 'Preparando',
    'iniciando': 'Iniciando optimizador',
    'sin CSV': 'Sin CSV',
    'sin datos': 'Sin datos',
    'rango degenerado': 'Rango de precio degenerado',
    'actualizando data (hora)': 'Actualizando data por hora',
    'actualizando data (minuto)': 'Actualizando data por minuto',
    'actualizando X3': 'Actualizando X3',
    'calc. distancias': 'Calculando distancias',
    'convergencia': 'Convergencia',
}


def _texto_linea_combo(v: str, n: int, ciclo: int, cambios: int, iters: int, FO, estado_str: str) -> Text:
    prefijo = f'[Ciclo {ciclo}] {v}_{n}: '
    if estado_str == 'corriendo':
        fo_str = f'{FO:.3e}' if FO is not None else '---'
        return Text(f'{prefijo}cambios={cambios} pasos_max={iters} FO={fo_str} [corriendo]')
    if estado_str.startswith('ERROR'):
        return Text(prefijo + estado_str, style='bold red')
    return Text(prefijo + _FASES.get(estado_str, estado_str))


def _texto_linea_x2(x2_estado: dict) -> Text:
    """X2 corre desacoplado del ciclo de cada activo (scoring cross-sectional sobre todo
    VALORES, ver _x2_watchdog) — no tiene sentido matemático re-correrlo por activo, así
    que su estado se muestra en una línea global propia en vez de dentro de cada combo."""
    texto = x2_estado.get('texto', 'esperando')
    if texto == 'actualizando':
        return Text('X2 (global): actualizando datos fundamentales...', style='dim')
    if texto == 'ERROR':
        return Text('X2 (global): ERROR en última corrida (ver errores.log)', style='bold red')
    ultima_ok = x2_estado.get('ultima_ok')
    if ultima_ok is None:
        return Text('X2 (global): esperando primera corrida', style='dim')
    mins = int((time.time() - ultima_ok) // 60)
    return Text(f'X2 (global): OK — última corrida hace {mins}min', style='dim')


def _construir_tabla_viva(estado_compartido, ciclos_estado, x2_estado: dict, combos: list) -> Group:
    lineas = []
    for v, n in combos:
        llave = f'{v}_{n}'
        cambios, iters, FO, estado_str = estado_compartido.get(llave, (0, 0, None, 'esperando'))
        ciclo = ciclos_estado.get(v, 0)
        lineas.append(_texto_linea_combo(v, n, ciclo, cambios, iters, FO, estado_str))
    lineas.append(_texto_linea_x2(x2_estado))
    return Group(*lineas)


def _x2_watchdog(x2_estado: dict, stop_event, intervalo_seg: int = 3600):
    """X2 corre desacoplado del ciclo de cada activo: el scoring normaliza cada activo
    contra el mínimo/máximo del universo completo (VALORES), así que no existe una versión
    'solo para un activo'. Ya trae guard de un día (_ya_ejecutado_hoy), así que reintentar
    cada intervalo es barato — la mayoría de las llamadas son no-op.

    Corre con stdout/stderr capturados (no heredados): un subprocess escribiendo directo a
    la consola no está coordinado con el Console del Live (son procesos de SO distintos, no
    hilos) y corrompería el redraw igual que el problema que este mismo cambio busca evitar.
    El output capturado se imprime de una sola vez, a través del Console compartido, al terminar.
    """
    x2_script = Path(__file__).parent / 'X2_fundamentals.py'
    while not stop_event.is_set():
        x2_estado['texto'] = 'actualizando'
        try:
            result = subprocess.run([sys.executable, str(x2_script)], check=False,
                                    capture_output=True, text=True)
            salida = ((result.stdout or '') + (result.stderr or '')).rstrip()
            with _stdout_lock:
                console.print('\n── X2: Datos fundamentales (global) ────────────────────')
                if salida:
                    console.print(salida)
            x2_estado['texto'] = 'ok'
            x2_estado['ultima_ok'] = time.time()
        except Exception as e:
            x2_estado['texto'] = 'ERROR'
            _log_error(CARPETA_LOGS, 'X2 falló (subprocess), continuando', e)
        stop_event.wait(intervalo_seg)


def _live_monitor(live: Live, estado_compartido, ciclos_estado, x2_estado: dict, combos: list,
                  stop_event, intervalo_seg: float = 1.0):
    """Redibuja el bloque de líneas en vivo (una por combo + una de X2 global) cada
    intervalo_seg. Reemplaza al _monitor_log anterior (que imprimía una línea nueva por
    cada cambio de estado, sin sobrescribir nunca — ver histórico en decisiones.md). Acá el
    redraw lo coordina rich.Live: cualquier console.print() concurrente se intercala arriba
    del bloque sin corromperlo, en vez de desincronizar el cursor a mano como en los intentos
    previos (_monitor_tabla)."""
    while not stop_event.is_set():
        live.update(_construir_tabla_viva(estado_compartido, ciclos_estado, x2_estado, combos))
        stop_event.wait(intervalo_seg)


def _info_previa_combo(v: str, n: int, carpeta_data: Path, carpeta_n_prod: Path):
    """Diagnóstico pre-corrida (rango de precios, warm start, delta_inicial, FO previa) para
    un combo — se imprime desde el hilo del activo (proceso principal) porque los workers del
    ProcessPoolExecutor tienen stdout silenciado (ver comentario al inicio del archivo)."""
    csv_path = carpeta_data / f'{v}.csv'
    lineas_out = [f'\n{"="*55}\nProcesando {v} N={n}']
    if not csv_path.exists():
        lineas_out.append(f'  CSV no encontrado: {csv_path}')
        with _stdout_lock:
            console.print('\n'.join(lineas_out))
        return
    df_info = pd.read_csv(csv_path, usecols=['DateTime', 'Close'])
    df_info['DateTime'] = pd.to_datetime(df_info['DateTime'])
    df_info = (df_info.sort_values('DateTime').drop_duplicates(subset=['DateTime'])
               .reset_index(drop=True))
    df_info = df_info[df_info['DateTime'] >= FECHA_INICIAL].reset_index(drop=True)
    if len(df_info):
        lineas_out.append(f'  Rango: {df_info["DateTime"].iloc[0]} → {df_info["DateTime"].iloc[-1]} ({len(df_info)} velas)')
        lineas_out.append(f'  Último cierre: {df_info["Close"].iloc[-1]:.2f}')
    json_path = carpeta_n_prod / f'{v}_{n}'
    if Path(f'{json_path}.json').exists():
        prev = set(json_act(str(json_path)))
        t_prev = datetime.datetime.fromtimestamp(
            Path(f'{json_path}.json').stat().st_mtime).replace(microsecond=0)
        lineas_out.append(f'  Warm start: {len(prev)} soportes desde la solución de t*={t_prev}')
    else:
        lineas_out.append('  Warm start: sin solución previa (arranque aleatorio)')
    delta_path = carpeta_n_prod / f'{v}_{n}_delta.json'
    if delta_path.exists():
        with open(delta_path) as f:
            delta_val = json.load(f)['delta_inicial']
        lineas_out.append(f'  delta_inicial: {notacion_cientifica(delta_val)}')
    else:
        lineas_out.append(f'  delta_inicial: {notacion_cientifica(DELTA_INICIAL)} (semilla)')
    log_path = CARPETA_LOGS / f'{v}_{n}.jsonl'
    if log_path.exists():
        with open(log_path) as f:
            lineas = [linea for linea in f if linea.strip()]
        if lineas:
            lineas_out.append(f'  FO warm start (última corrida): {notacion_cientifica(json.loads(lineas[-1])["FO_final"])}')
    with _stdout_lock:
        console.print('\n'.join(lineas_out))


def _resumen_combo(v: str, n: int, res: dict):
    dur = res['duracion']
    mins = int(dur // 60)
    segs = dur % 60
    tiempo_str = f'{mins}m {segs:.1f}s' if mins > 0 else f'{segs:.1f}s'
    conv_str = 'convergió' if res['convergio'] else 'no convergió'
    ws = (f'warm start {res["warm_start_n"]} @ t*={res["warm_start_t"]}'
          if res['warm_start_n'] else 'sin solución previa')
    with _stdout_lock:
        console.print(f'  {v} N={n}: {tiempo_str} | {conv_str} | '
                      f'precios {res["t0"]} → {res["tf"]} ({res["n_velas"]} velas) | {ws}')


def _ciclo_activo(valor: str, n_list: list, carpeta_data: Path, carpeta_data_minuto: Path,
                   carpeta_n_prod: Path, executor, estado_compartido, ciclos_estado,
                   mt5_lock, stop_event, opcion: int, max_ciclos: int):
    """Loop independiente por activo: descarga sus datos, actualiza X3, busca sus soportes
    hasta convergencia, y arranca el siguiente ciclo de inmediato — sin esperar a los demás
    activos, que siguen en el suyo propio (ver ciclos_estado). Las llamadas a MT5 se
    serializan con mt5_lock (la API no es thread-safe para llamadas concurrentes); el cómputo
    pesado del optimizador sigue corriendo en paralelo real vía el ProcessPoolExecutor
    compartido entre los 6 hilos de activo.

    Solo el primer ciclo (ciclo 0) imprime el diagnóstico completo (banner, descargas,
    _info_previa_combo, _resumen_combo) — de ahí en más cada fase (descarga hora/minuto,
    X3, distancias, optimizador, convergencia) se refleja únicamente en la línea en vivo
    del monitor vía estado_compartido, sin generar líneas nuevas en pantalla.
    """
    ciclo = 0
    while not stop_event.is_set():
        ciclos_estado[valor] = ciclo
        es_primer_ciclo = (ciclo == 0)
        if es_primer_ciclo:
            with _stdout_lock:
                console.print(f'\n── {valor}: ciclo {ciclo} ──')
        try:
            if opcion in (0, 2):
                for n in n_list:
                    estado_compartido[f'{valor}_{n}'] = (0, 0, None, 'actualizando data (hora)')
                with mt5_lock:
                    try:
                        descargar_datos([valor], carpeta_data, verbose=es_primer_ciclo)
                    except Exception as e:
                        _log_error(CARPETA_LOGS, f'Descarga H1 falló para {valor}, continuando', e)
                    if valor in ('BTCUSD', 'ETHUSD'):
                        try:
                            fecha_inicial_dt = datetime.datetime.strptime(FECHA_INICIAL, '%Y-%m-%d')
                            gap = detectar_gap_bt_eth(carpeta_data, fecha_inicial_dt)
                            if gap is not None:
                                console.print(f'\n⚠ Vacío detectado en BTC/ETH desde {gap} — '
                                              f'backfill automático para todos los activos')
                                backfill_historico(VALORES, carpeta_data, gap)
                        except Exception as e:
                            _log_error(CARPETA_LOGS, 'Detección/backfill de vacíos falló, continuando', e)
                    for n in n_list:
                        estado_compartido[f'{valor}_{n}'] = (0, 0, None, 'actualizando data (minuto)')
                    try:
                        descargar_datos_minuto([valor], carpeta_data_minuto, verbose=es_primer_ciclo)
                    except Exception as e:
                        _log_error(CARPETA_LOGS, f'Descarga M1 falló para {valor}, continuando', e)

                csv_h1 = carpeta_data / f'{valor}.csv'
                if csv_h1.exists():
                    try:
                        for n in n_list:
                            estado_compartido[f'{valor}_{n}'] = (0, 0, None, 'actualizando X3')
                        df_v = pd.read_csv(csv_h1)
                        n_prod = n_sizes_ejecucion.get(valor, 120)
                        json_path = carpeta_n_prod / f'{valor}_{n_prod}.json'
                        conjunto_n_v = (set(json.load(open(json_path)))
                                        if json_path.exists() else set())
                        _x3_actualizar_features(valor, df_v, conjunto_n_v, verbose=es_primer_ciclo,
                                                console=console)
                    except Exception as e:
                        _log_error(CARPETA_LOGS, f'X3 falló para {valor}, continuando', e)

            if opcion in (1, 2):
                with mt5_lock:
                    ordenes_activas = obtener_ordenes_activas_mt5([valor]).get(valor, [])
                for n in n_list:
                    llave = f'{valor}_{n}'
                    if es_primer_ciclo:
                        _info_previa_combo(valor, n, carpeta_data, carpeta_n_prod)
                    estado_compartido[llave] = (0, 0, None, 'esperando')
                    future = executor.submit(_procesar_valor_N, valor, n, carpeta_data, carpeta_n_prod,
                                              None, ordenes_activas, None, estado_compartido, False)
                    try:
                        res = future.result()
                        if res is not None and es_primer_ciclo:
                            _resumen_combo(valor, n, res)
                    except Exception as exc:
                        prev = estado_compartido.get(llave, (0, 0, None, 'ERROR'))
                        estado_compartido[llave] = (prev[0], prev[1], prev[2], f'ERROR: {str(exc)[:30]}')
                        _log_error(CARPETA_LOGS, f'Error en combo ({valor}, N={n})', exc)
        except Exception as e:
            _log_error(CARPETA_LOGS, f'Error en ciclo {ciclo} de {valor}. Reintentando en el próximo ciclo', e)

        ciclo += 1
        if max_ciclos > 0 and ciclo >= max_ciclos:
            break


def _reset_x0_state():
    """Elimina logs, soportes y plots de X0, y resetea reiniciar_x0 = False en config.py."""
    print('\n── Reinicio X0 ──────────────────────────────────────────')
    for carpeta in [CARPETA_LOGS, CARPETA_N_PROD, CARPETA_PLOTS]:
        if carpeta.exists():
            shutil.rmtree(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        print(f'  Limpiada: {carpeta}')

    config_path = Path(__file__).parent / 'config.py'
    texto = config_path.read_text()
    texto = texto.replace('reiniciar_x0 = True', 'reiniciar_x0 = False')
    config_path.write_text(texto)
    print('  reiniciar_x0 = False en config.py')


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='X0: datos + soportes')
    parser.add_argument('--opcion', type=int, default=2,
                        choices=[0, 1, 2],
                        help='0=solo datos, 1=solo soportes, 2=ambos (default)')
    parser.add_argument('--ciclos', type=int, default=0,
                        help='Número de ciclos por activo a ejecutar (cada activo cuenta el '
                             'suyo, de forma independiente). 0 = infinito (default).')
    parser.add_argument('--backfill', type=str, default=None, metavar='YYYY-MM-DD',
                        help='Trae historial H1 completo desde esta fecha vía MT5 '
                             '(copy_rates_range, sin tope de 1000 velas), lo mergea '
                             'con el CSV existente y termina. No entra al loop.')
    args = parser.parse_args()

    CARPETA_DATA.mkdir(parents=True, exist_ok=True)
    CARPETA_DATA_MINUTO.mkdir(parents=True, exist_ok=True)
    CARPETA_N_PROD.mkdir(parents=True, exist_ok=True)

    if args.backfill:
        fecha_desde = datetime.datetime.strptime(args.backfill, '%Y-%m-%d')
        backfill_historico(VALORES, CARPETA_DATA, fecha_desde)
        sys.exit(0)

    t_inicio_script = time.time()

    def _fmt_duracion(s):
        s = int(s)
        if s < 60:
            return f'{s}s'
        h, rem = divmod(s, 3600)
        m, seg = divmod(rem, 60)
        return f'{h:02d}:{m:02d}:{seg:02d}'

    console.print(f'\nLAMBDA = {LAMBDA} ({notacion_cientifica(LAMBDA)})')

    if reiniciar_x0:
        _reset_x0_state()

    combos = [(v, n) for v in VALORES for n in n_sizes.get(v, [])]
    x2_estado = {'texto': 'esperando', 'ultima_ok': None}

    try:
        with multiprocessing.Manager() as manager:
            estado_compartido = manager.dict({f'{v}_{n}': (0, 0, None, 'esperando') for v, n in combos})
            ciclos_estado = manager.dict({v: 0 for v in VALORES})
            stop_event = threading.Event()
            mt5_lock = threading.Lock()

            # auto_refresh=False: el redraw lo dispara _live_monitor a su propio ritmo
            # (live.update(..., refresh=True)), no el timer interno de Live — un solo
            # reloj conduciendo el redraw, más predecible que dos corriendo en paralelo.
            # redirect_stdout/redirect_stderr=True (default) es la red de seguridad: cualquier
            # print() suelto que se nos haya escapado (o de una librería de terceros, ej. MT5)
            # también queda coordinado con el redraw en vez de corromperlo.
            tabla_inicial = _construir_tabla_viva(estado_compartido, ciclos_estado, x2_estado, combos)
            with Live(tabla_inicial, console=console, auto_refresh=False) as live:
                threading.Thread(target=_x2_watchdog, args=(x2_estado, stop_event), daemon=True).start()
                threading.Thread(target=_live_monitor,
                                  args=(live, estado_compartido, ciclos_estado, x2_estado, combos, stop_event),
                                  daemon=True).start()

                # N_MAX_MODELS acá limita cuántos combos corren a la vez en el pool compartido
                # (antes limitaba cuántos se seleccionaban por ciclo global; ese concepto ya no
                # existe con ciclos independientes por activo).
                with concurrent.futures.ProcessPoolExecutor(max_workers=N_MAX_MODELS or None) as executor:
                    hilos = []
                    for valor in VALORES:
                        t = threading.Thread(
                            target=_ciclo_activo,
                            args=(valor, n_sizes.get(valor, []), CARPETA_DATA, CARPETA_DATA_MINUTO,
                                  CARPETA_N_PROD, executor, estado_compartido, ciclos_estado,
                                  mt5_lock, stop_event, args.opcion, args.ciclos),
                            daemon=True,
                        )
                        t.start()
                        hilos.append(t)
                    for t in hilos:
                        t.join()

                stop_event.set()

    except KeyboardInterrupt:
        stop_event.set()
        console.print('\nDetenido por el usuario.')
    finally:
        console.print(f'Tiempo total: {_fmt_duracion(time.time() - t_inicio_script)}')
