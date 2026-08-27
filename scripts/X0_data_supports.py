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

warnings.filterwarnings('ignore')

from config import (
    CARPETA_DATA, CARPETA_DATA_MINUTO, CARPETA_N_PROD, CARPETA_PLOTS, CARPETA_LOGS,
    VALORES, FECHA_INICIAL,
    K, N_EXP, BLOQUE_DISTANCIAS, parametros_soportes,
    M, M_COARSE, LAMBDA, MAX_ITERS, DELTA_INICIAL, FACTOR_DELTA,
    GRAFICAR_EXTREMOS, GRAFICAR_FO, GRAFICAR_SOPORTES, GRAFICAR_ZOOM,
    n_sizes, n_sizes_ejecucion, N_MAX_MODELS, reiniciar_x0,
)
from X3_technical_features import actualizar_features as _x3_actualizar_features


# ─── Utilidades ───────────────────────────────────────────────────────────────

def json_act(file_path: str, variable=None, mode: str = 'open'):
    """Guarda (mode='save') o carga (mode='open') una lista de soportes en disco como JSON.

    El guardado es atómico (escribe a un .tmp y hace os.replace) para que un lector
    concurrente (X1) nunca vea el archivo truncado a mitad de escritura.
    """
    path = f'{file_path}.json'
    try:
        if mode == 'save':
            tmp_path = f'{path}.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(sorted(variable), f)
            os.replace(tmp_path, path)
            return None
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f'Error json_act ({mode}, {path}): {e}')
        sys.exit(1)


def notacion_cientifica(numero: float, decimales: int = 2) -> str:
    if numero == 0:
        return '0'
    exp = int(np.floor(np.log10(abs(numero))))
    base = numero / (10 ** exp)
    return f'{base:.{decimales}f} x E{exp}'


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
        sys.exit(f'Error en tamaño conjunto_N: {len(conjunto_N)} != {N}')

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

    cv(H_n) = std(H_n) / mean(H_n), donde H_n son las distancias entre soportes consecutivos.
    Penaliza conjuntos donde los soportes están muy concentrados en una zona del rango.
    """
    df_extremos = asignar_soporte(df_extremos, conjunto_N)
    df_extremos['dist'] = (df_extremos['soporte'] - df_extremos['Low']) ** 2
    dist_max = df_extremos['dist'].max()
    df_extremos['h_dist'] = 1 - df_extremos['dist'] / dist_max

    factores = [nombre for nombre, activo in parametros_soportes.items() if activo]
    df_extremos['z'] = df_extremos[factores].prod(axis=1)

    L_n = sorted(list(conjunto_N))
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

    Returns: FO_values array (M_eff,)
    """
    if len(candidatos) == 0:
        return np.array([], dtype=np.float64)

    lows = df_extremos['Low'].to_numpy(dtype=np.float64)
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
                         verbose: bool = True) -> tuple:
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
    """
    if verbose:
        print(f'Iniciando optimizador | max_iters={max_iters} | N={N} | M={M}')
    convergio = False
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
        sys.exit('Cantidad de ordenes activas es mayor a N')

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
        sys.exit(f'Error en tamaño conjunto_N tras inicialización: {len(conjunto_N)} != {N}')

    lista_N = sorted(list(conjunto_N))
    dic_N = {i: val for i, val in enumerate(lista_N)}
    casos_moviles = list(dic_N.keys())
    df_FO = pd.DataFrame()

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
            sys.exit(f'Error en tamaño conjunto_N en iteración {j}: {len(conjunto_N)} != {N}')

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
            'Iteracion': [j], 'FO': [FO_base],
            'FO1': [particion_FO[0]], 'FO2': [particion_FO[1]],
            'ratio': [particion_FO[0] / particion_FO[1]],
        })])

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
            print('MT5 no disponible — ordenes_activas vacías para todos los activos')
            return {v: [] for v in valores}
        result = {}
        for valor in valores:
            positions = mt5.positions_get(symbol=valor) or []
            result[valor] = [p.price_open for p in positions]
            if result[valor]:
                print(f'  {valor}: {len(result[valor])} posición(es) activa(s) → fija(s) en optimizador')
        mt5.shutdown()
        return result
    except ImportError:
        return {v: [] for v in valores}


def descargar_datos(valores: list, carpeta_data: Path):
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialize() falló: {mt5.last_error()}')

    for valor in valores:
        print(f'\nDescargando {valor}...')
        mt5.symbol_select(valor, True)
        rates = mt5.copy_rates_from_pos(valor, mt5.TIMEFRAME_H1, 0, 1000)

        if rates is None:
            print(f'  Sin datos para {valor}, skip')
            continue

        df = pd.DataFrame(rates)
        try:
            df['time'] = pd.to_datetime(df['time'], unit='s')
        except Exception as e:
            print(f'  Error al convertir tiempo para {valor}: {e}')
            continue

        df.columns = ['DateTime', 'Open', 'High', 'Low', 'Close', 'Tick_Volume', 'Spread', 'Real_Volume']

        # Merge con histórico: los datos nuevos tienen prioridad para pisar la última vela abierta
        csv_path = carpeta_data / f'{valor}.csv'
        if csv_path.exists():
            data_old = pd.read_csv(csv_path)
            data_old['DateTime'] = pd.to_datetime(data_old['DateTime'])
            df['DateTime'] = pd.to_datetime(df['DateTime'])
            data = (pd.concat([df, data_old])
                    .drop_duplicates(subset=['DateTime'])
                    .sort_values('DateTime')
                    .reset_index(drop=True))
        else:
            data = df

        data.to_csv(csv_path, index=False)
        print(f'  Guardado: {csv_path.name} ({len(data)} velas, último: {df["DateTime"].iloc[-1]})')

    mt5.shutdown()


def descargar_datos_minuto(valores: list, carpeta_data_minuto: Path):
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialize() falló: {mt5.last_error()}')

    for valor in valores:
        print(f'\nDescargando M1 {valor}...')
        mt5.symbol_select(valor, True)
        rates = mt5.copy_rates_from_pos(valor, mt5.TIMEFRAME_M1, 0, 1000)

        if rates is None:
            print(f'  Sin datos para {valor}, skip')
            continue

        df = pd.DataFrame(rates)
        try:
            df['time'] = pd.to_datetime(df['time'], unit='s')
        except Exception as e:
            print(f'  Error al convertir tiempo para {valor}: {e}')
            continue

        df.columns = ['DateTime', 'Open', 'High', 'Low', 'Close', 'Tick_Volume', 'Spread', 'Real_Volume']

        csv_path = carpeta_data_minuto / f'{valor}.csv'
        if csv_path.exists():
            data_old = pd.read_csv(csv_path)
            data_old['DateTime'] = pd.to_datetime(data_old['DateTime'])
            df['DateTime'] = pd.to_datetime(df['DateTime'])
            data = (pd.concat([df, data_old])
                    .drop_duplicates(subset=['DateTime'])
                    .sort_values('DateTime')
                    .reset_index(drop=True))
        else:
            data = df

        data.to_csv(csv_path, index=False)
        print(f'  Guardado: {csv_path.name} ({len(data)} velas M1, último: {df["DateTime"].iloc[-1]})')

    mt5.shutdown()


# ─── Etapa 2: Búsqueda de soportes óptimos ───────────────────────────────────

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
    with open(bt_path) as f:
        cache = json.load(f)
    candidatos = {k: v for k, v in cache.items() if pd.to_datetime(k) <= fecha_hora_max}
    if not candidatos:
        return None, set()
    mejor_t = max(candidatos, key=lambda k: pd.to_datetime(k))
    return mejor_t, set(candidatos[mejor_t])


def _bt_warm_start(carpeta_n_bt: Path, valor: str, N: int, fecha_hora_max) -> set:
    """Conjunto_N del cache bt más reciente con timestamp <= fecha_hora_max."""
    return _bt_solucion_previa(carpeta_n_bt, valor, N, fecha_hora_max)[1]


def _bt_guardar(carpeta_n_bt: Path, valor: str, N: int, fecha_hora_clave, conjunto_N: set):
    """Upsert de conjunto_N en el cache bt con clave = último datetime de los datos usados."""
    bt_path = carpeta_n_bt / f'{valor}_{N}_bt.json'
    cache = {}
    if bt_path.exists():
        with open(bt_path) as f:
            cache = json.load(f)
    cache[str(fecha_hora_clave)] = sorted(conjunto_N)
    with open(bt_path, 'w') as f:
        json.dump(cache, f)


def _log_diagnostico_conjunto_N(identificador: str, escenario: str, datos: dict):
    """Vuelca a un JSON el contexto de un fallo de tamaño en conjunto_N (len != N).

    Estos fallos hoy terminan en sys.exit() dentro de un worker de ProcessPoolExecutor:
    el proceso no imprime nada (stdout de worker silenciado) y el SystemExit, al no ser
    Exception, se propaga sin traceback hasta matar el script completo — sin dejar rastro.
    Este archivo es el único rastro que va a quedar cuando eso pase.
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
    """Agrega una entrada al log de convergencia de un combo (valor, N) en resources/x0/logs/."""
    CARPETA_LOGS.mkdir(parents=True, exist_ok=True)
    sufijo = '_bt' if es_bt else ''
    log_path = CARPETA_LOGS / f'{valor}_{N}{sufijo}.json'

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

    historial = []
    if log_path.exists():
        with open(log_path) as f:
            historial = json.load(f)
    historial.append(entrada)
    with open(log_path, 'w') as f:
        json.dump(historial, f, indent=2)


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
        estado_compartido[llave] = (cambios_netos, -1, FO_final, f'listo {round(duracion)}s')

    return {
        'valor': valor, 'N': N,
        't0': str(df['DateTime'].iloc[0]), 'tf': str(fecha_hora_clave),
        'n_velas': len(df),
        'warm_start_n': len(conjunto_N_prev), 'warm_start_t': ws_t,
        'FO_inicial': FO_ref, 'FO_final': FO_final,
        'convergio': convergio, 'duracion': round(duracion, 1),
        'plot': plot_generado,
    }


def _monitor_tabla(estado, tuplas, stop_event):
    n = len(tuplas)
    for _ in range(n):
        sys.stdout.write('\n')
    sys.stdout.flush()

    def redraw():
        sys.stdout.write(f'\033[{n}A')
        for v, N in tuplas:
            llave = f'{v}_{N}'
            cambios, iters, FO, estado_str = estado.get(llave, (0, 0, None, 'esperando'))
            fo_str = f'{FO:.4e}' if FO is not None else '---'
            iter_str = str(iters) if iters >= 0 else 'conv.'
            line = f'{v} {N}: pasos={cambios:<6} iter={iter_str:<8} FO={fo_str:<14} [{estado_str}]'
            sys.stdout.write(f'\r{line:<75}\n')
        sys.stdout.flush()

    while not stop_event.is_set():
        redraw()
        time.sleep(1)
    redraw()


def _seleccionar_combos(valores: list, n_sizes: dict, carpeta_n_prod: Path, n_max=None) -> list:
    """
    Retorna la lista de tuplas (valor, N) a procesar en el próximo ciclo.

    Si n_max es None o >= total de combos: retorna todos, ordenados por antigüedad del JSON
    (misma lógica que antes).
    Si n_max < total: selecciona los n_max con mayor delta_inicial (más prometedores,
    es decir, los que tienen más terreno que ganar en la próxima corrida), con tie-break
    aleatorio. Dentro de los seleccionados, mantiene el orden por antigüedad del JSON.
    """
    tuplas = []
    for valor in valores:
        if valor not in n_sizes:
            continue
        for N in n_sizes[valor]:
            json_path = carpeta_n_prod / f'{valor}_{N}.json'
            delta_path = carpeta_n_prod / f'{valor}_{N}_delta.json'

            if delta_path.exists():
                with open(delta_path) as f:
                    delta = json.load(f)['delta_inicial']
            else:
                delta = DELTA_INICIAL

            fecha_mtime = (datetime.datetime.fromtimestamp(json_path.stat().st_mtime)
                           if json_path.exists() else datetime.datetime(2000, 1, 1))
            tuplas.append((valor, N, delta, fecha_mtime))

    if not tuplas:
        return []

    if n_max is None or n_max <= 0 or n_max >= len(tuplas):
        return [(v, n) for v, n, _, _ in sorted(tuplas, key=lambda x: x[3])]

    # Shuffle para tie-break aleatorio antes de ordenar por delta desc (sort estable)
    random.shuffle(tuplas)
    seleccionados = sorted(tuplas, key=lambda x: -x[2])[:n_max]
    return [(v, n) for v, n, _, _ in sorted(seleccionados, key=lambda x: x[3])]


def buscar_soportes(valores: list, n_sizes: dict, carpeta_data: Path,
                    carpeta_n_prod: Path, carpeta_n_bt: Path,
                    ordenes_activas_mt5: dict = None, n_max=None):
    if ordenes_activas_mt5 is None:
        ordenes_activas_mt5 = {v: [] for v in valores}

    tuplas_ordenadas = _seleccionar_combos(valores, n_sizes, carpeta_n_prod, n_max)
    total_combos = sum(len(ns) for ns in n_sizes.values())
    filtrado = f'{len(tuplas_ordenadas)}/{total_combos} (top delta)' if (n_max and n_max < total_combos) else str(len(tuplas_ordenadas))
    print(f'Combos a procesar ({filtrado}):', tuplas_ordenadas)

    # Info previa por combo (secuencial, antes del monitor)
    for v, n in tuplas_ordenadas:
        csv_path = carpeta_data / f'{v}.csv'
        print(f'\n{"="*55}\nProcesando {v} N={n}')
        if not csv_path.exists():
            print(f'  CSV no encontrado: {csv_path}')
            continue
        df_info = pd.read_csv(csv_path, usecols=['DateTime', 'Close'])
        df_info['DateTime'] = pd.to_datetime(df_info['DateTime'])
        df_info = (df_info.sort_values('DateTime').drop_duplicates(subset=['DateTime'])
                   .reset_index(drop=True))
        df_info = df_info[df_info['DateTime'] >= FECHA_INICIAL].reset_index(drop=True)
        if len(df_info):
            print(f'  Rango: {df_info["DateTime"].iloc[0]} → {df_info["DateTime"].iloc[-1]} ({len(df_info)} velas)')
            print(f'  Último cierre: {df_info["Close"].iloc[-1]:.2f}')
        json_path = carpeta_n_prod / f'{v}_{n}'
        if Path(f'{json_path}.json').exists():
            prev = set(json_act(str(json_path)))
            t_prev = datetime.datetime.fromtimestamp(
                Path(f'{json_path}.json').stat().st_mtime).replace(microsecond=0)
            print(f'  Warm start: {len(prev)} soportes desde la solución de t*={t_prev}')
        else:
            print('  Warm start: sin solución previa (arranque aleatorio)')
        delta_path = carpeta_n_prod / f'{v}_{n}_delta.json'
        if delta_path.exists():
            with open(delta_path) as f:
                delta_val = json.load(f)['delta_inicial']
            print(f'  delta_inicial: {notacion_cientifica(delta_val)}')
        else:
            print(f'  delta_inicial: {notacion_cientifica(DELTA_INICIAL)} (semilla)')
        log_path = CARPETA_LOGS / f'{v}_{n}.json'
        if log_path.exists():
            with open(log_path) as f:
                log = json.load(f)
            if log:
                print(f'  FO warm start (última corrida): {notacion_cientifica(log[-1]["FO_final"])}')

    with multiprocessing.Manager() as manager:
        estado = manager.dict()
        for v, n in tuplas_ordenadas:
            estado[f'{v}_{n}'] = (0, 0, None, 'esperando')

        stop_event = threading.Event()
        monitor = threading.Thread(target=_monitor_tabla, args=(estado, tuplas_ordenadas, stop_event), daemon=True)
        monitor.start()

        resultados_tiempo = {}
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(_procesar_valor_N, v, n, carpeta_data, carpeta_n_prod, carpeta_n_bt,
                                ordenes_activas_mt5.get(v, []), None, estado, False): (v, n)
                for v, n in tuplas_ordenadas
            }
            for future in concurrent.futures.as_completed(futures):
                valor, N = futures[future]
                try:
                    resultados_tiempo[f'{valor}_{N}'] = future.result()
                except Exception as exc:
                    prev = estado.get(f'{valor}_{N}', (0, 0, None, 'ERROR'))
                    estado[f'{valor}_{N}'] = (prev[0], prev[1], prev[2], f'ERROR: {str(exc)[:30]}')
                    print(f'\nError en ({valor}, N={N}): {exc}')

        stop_event.set()
        monitor.join()

        print()
        for v, n in tuplas_ordenadas:
            res = resultados_tiempo.get(f'{v}_{n}')
            if res is None:
                continue
            dur = res['duracion']
            mins = int(dur // 60)
            segs = dur % 60
            tiempo_str = f'{mins}m {segs:.1f}s' if mins > 0 else f'{segs:.1f}s'
            conv_str = 'convergió' if res['convergio'] else 'no convergió'
            ws = (f'warm start {res["warm_start_n"]} @ t*={res["warm_start_t"]}'
                  if res['warm_start_n'] else 'sin solución previa')
            print(f'  {v} N={n}: {tiempo_str} | {conv_str} | '
                  f'precios {res["t0"]} → {res["tf"]} ({res["n_velas"]} velas) | {ws}')



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
                        help='Número de ciclos a ejecutar. 0 = infinito (default).')
    args = parser.parse_args()

    CARPETA_DATA.mkdir(parents=True, exist_ok=True)
    CARPETA_DATA_MINUTO.mkdir(parents=True, exist_ok=True)
    CARPETA_N_PROD.mkdir(parents=True, exist_ok=True)

    t_inicio_script = time.time()

    def _fmt_duracion(s):
        s = int(s)
        if s < 60:
            return f'{s}s'
        h, rem = divmod(s, 3600)
        m, seg = divmod(rem, 60)
        return f'{h:02d}:{m:02d}:{seg:02d}'

    print(f'\nLAMBDA = {LAMBDA} ({notacion_cientifica(LAMBDA)})')

    ciclo = 0
    _pendiente_reset = reiniciar_x0  # capturado al inicio; se consume una sola vez
    try:
        while True:
            ciclo += 1
            print(f'\n{"═"*55}\n CICLO {ciclo}'
                  + (f' — top {N_MAX_MODELS} combos' if N_MAX_MODELS else ' — todos los combos')
                  + f'\n{"═"*55}')

            try:
                print('\n── X2: Datos fundamentales ─────────────────────────────')
                try:
                    x2_script = Path(__file__).parent / 'X2_fundamentals.py'
                    subprocess.run([sys.executable, str(x2_script)], check=False)
                except Exception as e:
                    print(f'  Advertencia: X2 falló ({e}). Continuando.')

                if args.opcion in (0, 2):
                    print('\n── Etapa 1: Descarga de datos ──────────────────────────')
                    try:
                        descargar_datos(VALORES, CARPETA_DATA)
                    except Exception as e:
                        print(f'  Advertencia: descarga H1 falló ({e}). '
                              f'Continuando con datos existentes.')
                    try:
                        descargar_datos_minuto(VALORES, CARPETA_DATA_MINUTO)
                    except Exception as e:
                        print(f'  Advertencia: descarga M1 falló ({e}). '
                              f'Continuando con datos existentes.')

                    print('\n── X3: Features técnicas ────────────────────────────────')
                    for valor in VALORES:
                        csv_h1 = CARPETA_DATA / f'{valor}.csv'
                        if not csv_h1.exists():
                            print(f'  X3 {valor}: sin CSV H1, skip')
                            continue
                        try:
                            df_v = pd.read_csv(csv_h1)
                            n_prod = n_sizes_ejecucion.get(valor, 120)
                            json_path = CARPETA_N_PROD / f'{valor}_{n_prod}.json'
                            conjunto_n_v = (set(json.load(open(json_path)))
                                            if json_path.exists() else set())
                            _x3_actualizar_features(valor, df_v, conjunto_n_v)
                        except Exception as e:
                            print(f'  Advertencia: X3 falló para {valor} ({e}). Continuando.')

                if _pendiente_reset:
                    _reset_x0_state()
                    _pendiente_reset = False

                if args.opcion in (1, 2):
                    print('\n── Etapa 2: Búsqueda de soportes ───────────────────────')
                    print('Consultando posiciones activas en MT5...')
                    ordenes_activas_mt5 = obtener_ordenes_activas_mt5(VALORES)
                    buscar_soportes(VALORES, n_sizes, CARPETA_DATA, CARPETA_N_PROD, None, ordenes_activas_mt5,
                                    n_max=N_MAX_MODELS)

            except Exception as e:
                print(f'\nError en ciclo {ciclo}: {e}. Reintentando en el próximo ciclo.')

            if args.ciclos > 0 and ciclo >= args.ciclos:
                break

    except KeyboardInterrupt:
        print(f'\nDetenido por el usuario tras {ciclo} ciclo(s).')
    finally:
        print(f'Tiempo total: {_fmt_duracion(time.time() - t_inicio_script)}')
