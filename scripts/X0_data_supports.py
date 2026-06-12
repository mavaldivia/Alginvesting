"""
X0_data_supports.py

Etapa 1 (--opcion 0 o 2): Descarga velas OHLCV H1 desde MetaTrader5 y actualiza los CSVs en Data/.
Etapa 2 (--opcion 1 o 2): Busca N soportes/resistencias óptimos por activo usando un optimizador
                           de búsqueda local y guarda los resultados en conjuntos_N/.

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
import os
import random
import sys
import threading
import time
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd
import tqdm

warnings.filterwarnings('ignore')

from config import (
    CARPETA_DATA, CARPETA_N_PROD, CARPETA_N_BT, CARPETA_PLOTS, CARPETA_LOGS,
    VALORES, FECHA_INICIAL,
    K, N_EXP, BLOQUE_DISTANCIAS, parametros_soportes,
    M, M_COARSE, LAMBDA, MAX_ITERS, DELTA_INICIAL, FACTOR_DELTA,
    GRAFICAR_EXTREMOS, GRAFICAR_FO, GRAFICAR_SOPORTES, GRAFICAR_ZOOM,
    n_sizes, N_MAX_MODELS,
)


# ─── Utilidades ───────────────────────────────────────────────────────────────

def json_act(file_path: str, variable=None, mode: str = 'open'):
    """Guarda (mode='save') o carga (mode='open') una lista de soportes en disco como JSON."""
    path = f'{file_path}.json'
    try:
        with open(path, 'w' if mode == 'save' else 'r') as f:
            if mode == 'save':
                json.dump(sorted(variable), f)
                return None
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


def _inicializar_conjunto_smart(df_extremos: pd.DataFrame, n: int) -> set:
    """
    Selecciona n precios de df_extremos con alta score y*w y diversidad espacial.
    Divide el rango de Low en n cuantiles y elige el Low con mayor y*w en cada uno.
    Fallback a uniform si faltan columnas (nunca debería ocurrir en producción).
    """
    if n <= 0:
        return set()
    if not {'y', 'w', 'Low'}.issubset(df_extremos.columns):
        p_min, p_max = df_extremos['Low'].min(), df_extremos['Low'].max()
        return set(np.random.uniform(p_min, p_max, n).tolist())

    df = df_extremos[['Low', 'y', 'w']].copy()
    df['score'] = df['y'] * df['w']
    df = df.sort_values('Low').reset_index(drop=True)

    result = set()
    for chunk_idx in np.array_split(np.arange(len(df)), n):
        if len(chunk_idx) == 0:
            continue
        chunk = df.iloc[chunk_idx]
        result.add(float(chunk['Low'].iloc[int(chunk['score'].argmax())]))

    # Completar si hay duplicados (precio repetido en dos cuantiles distintos)
    if len(result) < n:
        p_min, p_max = df_extremos['Low'].min(), df_extremos['Low'].max()
        while len(result) < n:
            result.add(float(np.random.uniform(p_min, p_max)))

    return result


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
                         conjunto_N: set = set(), ocp: int = 0, verbose: bool = True) -> tuple:
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
        conjunto_N = conjunto_N.union(_inicializar_conjunto_smart(df_extremos, delta))
    elif L > ordenes_en_espera:
        elementos_a_remover = set(random.sample(list(conjunto_N), L - ordenes_en_espera))
        conjunto_N = conjunto_N.difference(elementos_a_remover)

    if len(conjunto_N) != N:
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
                       candidatos: np.ndarray, lambda_ponderador: float) -> np.ndarray:
    """
    Evalúa la FO para todos los candidatos a soporte idx_soporte en una sola pasada vectorizada.
    Reemplaza el for-loop de M llamadas a calcular_FO en nuevo_optimizador_2.

    Para cada Low l_j, la distancia al soporte más cercano del conjunto {base ∪ c_k} es
    min(dist_base[j], |l_j - c_k|): se precomputa nearest_base una vez y se compara con
    los M candidatos via broadcasting (M_eff, n) sin iterar en Python.

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


# ─── Estado incremental para S1 ──────────────────────────────────────────────

def _init_estado_incremental(df_extremos: pd.DataFrame, lista_N_arr: np.ndarray,
                              lambda_ponderador: float) -> dict:
    """
    Precomputa el estado para evaluación incremental O(3n/N) en nuevo_optimizador_2.
    dist_max_global se fija al inicializar — válido para búsqueda local donde los
    soportes se desplazan pequeñas distancias entre iteraciones.
    """
    factores = [name for name, active in parametros_soportes.items() if active]
    lows = df_extremos['Low'].to_numpy(dtype=np.float64)
    n = len(lows)
    N = len(lista_N_arr)

    idx_b = np.searchsorted(lista_N_arr, lows)
    idx_izq = np.clip(idx_b - 1, 0, N - 1)
    idx_der = np.clip(idx_b, 0, N - 1)
    dist_izq = np.abs(lows - lista_N_arr[idx_izq])
    dist_der = np.abs(lows - lista_N_arr[idx_der])
    asignaciones = np.where(dist_izq <= dist_der, idx_izq, idx_der)

    dist_sq = (lista_N_arr[asignaciones] - lows) ** 2
    dist_max_global = float(dist_sq.max()) if dist_sq.max() > 0 else 1.0

    cols_fijos = [f for f in factores if f != 'h_dist']
    fixed_z = (df_extremos[cols_fijos].prod(axis=1).to_numpy()
               if cols_fijos else np.ones(n, dtype=np.float64))

    h_dist = 1.0 - dist_sq / dist_max_global
    z = (fixed_z * h_dist if 'h_dist' in factores else fixed_z.copy()).astype(np.float64)
    z_sum = float(z.sum())

    H_n = np.diff(lista_N_arr).copy()
    N_gaps = len(H_n)
    H_sum = float(H_n.sum())
    H_sq_sum = float((H_n ** 2).sum())
    H_mean = H_sum / N_gaps if N_gaps > 0 else 0.0
    H_var = max(0.0, H_sq_sum / N_gaps - H_mean ** 2) if N_gaps > 0 else 0.0
    cv_Hn = float(np.sqrt(H_var) / H_mean) if H_mean != 0 else 0.0

    return {
        'lows': lows, 'n': n,
        'asignaciones': asignaciones,
        'dist_max_global': dist_max_global,
        'fixed_z': fixed_z, 'z': z, 'z_sum': z_sum,
        'H_n': H_n, 'H_sum': H_sum, 'H_sq_sum': H_sq_sum,
        'factores': factores,
        'mean_z': z_sum / n, 'cv_Hn': cv_Hn,
        'FO': z_sum / n - lambda_ponderador * cv_Hn,
    }


def _fo_incremental_batch(estado: dict, lista_N_arr: np.ndarray, i: int,
                           candidatos: np.ndarray, lambda_ponderador: float) -> np.ndarray:
    """
    Evalúa FO para M candidatos al soporte i en O(M × 3n/N).
    Solo recalcula filas asignadas a i-1, i, i+1; los demás aportan z_sum fijo.
    """
    M_eff = len(candidatos)
    if M_eff == 0:
        return np.array([], dtype=np.float64)

    lows = estado['lows']
    n = estado['n']
    asignaciones = estado['asignaciones']
    dist_max = estado['dist_max_global']
    fixed_z = estado['fixed_z']
    z = estado['z']
    z_sum = estado['z_sum']
    H_n = estado['H_n']
    H_sum = estado['H_sum']
    H_sq_sum = estado['H_sq_sum']
    factores = estado['factores']
    N = len(lista_N_arr)
    N_gaps = N - 1

    mask = asignaciones == i
    if i > 0:
        mask = mask | (asignaciones == i - 1)
    if i < N - 1:
        mask = mask | (asignaciones == i + 1)
    idx_aff = np.where(mask)[0]

    s_left = lista_N_arr[i - 1] if i > 0 else -np.inf
    s_right = lista_N_arr[i + 1] if i < N - 1 else np.inf

    # cv(H_n) incremental: solo cambian los 2 gaps adyacentes a i
    old_left = float(H_n[i - 1]) if i > 0 else 0.0
    old_right = float(H_n[i]) if i < N - 1 else 0.0
    new_left = (candidatos - lista_N_arr[i - 1]) if i > 0 else np.zeros(M_eff)
    new_right = (lista_N_arr[i + 1] - candidatos) if i < N - 1 else np.zeros(M_eff)

    H_sum_c = H_sum - old_left - old_right + new_left + new_right
    H_sq_c = H_sq_sum - old_left ** 2 - old_right ** 2 + new_left ** 2 + new_right ** 2
    H_mean_c = H_sum_c / N_gaps if N_gaps > 0 else np.zeros(M_eff)
    H_var_c = np.maximum(H_sq_c / N_gaps - H_mean_c ** 2, 0.0) if N_gaps > 0 else np.zeros(M_eff)
    cv_Hn_c = np.where(H_mean_c != 0, np.sqrt(H_var_c) / H_mean_c, 0.0)

    if len(idx_aff) == 0:
        return estado['mean_z'] - lambda_ponderador * cv_Hn_c

    lows_aff = lows[idx_aff]
    z_aff_old_sum = float(z[idx_aff].sum())

    d_left = np.abs(lows_aff - s_left)
    d_right = np.abs(lows_aff - s_right)
    d_cand = np.abs(lows_aff[None, :] - candidatos[:, None])  # (M_eff, |aff|)

    d_left_b = np.broadcast_to(d_left, (M_eff, len(idx_aff)))
    d_right_b = np.broadcast_to(d_right, (M_eff, len(idx_aff)))
    nearest_idx = np.argmin(np.stack([d_left_b, d_cand, d_right_b], axis=2), axis=2)

    nearest_val = np.where(
        nearest_idx == 0, s_left,
        np.where(nearest_idx == 1, candidatos[:, None], s_right),
    )
    dist_sq_aff = (nearest_val - lows_aff[None, :]) ** 2
    h_dist_aff = 1.0 - dist_sq_aff / dist_max

    z_aff_new = (fixed_z[idx_aff][None, :] * h_dist_aff
                 if 'h_dist' in factores
                 else np.broadcast_to(fixed_z[idx_aff], (M_eff, len(idx_aff))))

    z_sum_new = z_sum - z_aff_old_sum + z_aff_new.sum(axis=1)
    mean_z_new = z_sum_new / n

    return mean_z_new - lambda_ponderador * cv_Hn_c


def _actualizar_estado(estado: dict, lista_N_arr: np.ndarray, i: int,
                        nuevo_valor: float, lambda_ponderador: float,
                        df_extremos: pd.DataFrame):
    """
    Actualiza estado incremental y df_extremos in-place tras aceptar soporte i → nuevo_valor.
    lista_N_arr se modifica in-place en el índice i.
    """
    lows = estado['lows']
    n = estado['n']
    asignaciones = estado['asignaciones']
    dist_max = estado['dist_max_global']
    fixed_z = estado['fixed_z']
    z = estado['z']
    H_n = estado['H_n']
    factores = estado['factores']
    N = len(lista_N_arr)

    mask = asignaciones == i
    if i > 0:
        mask = mask | (asignaciones == i - 1)
    if i < N - 1:
        mask = mask | (asignaciones == i + 1)
    idx_aff = np.where(mask)[0]

    s_left = lista_N_arr[i - 1] if i > 0 else -np.inf
    s_right = lista_N_arr[i + 1] if i < N - 1 else np.inf

    # H_n: calcular nuevos gaps antes de modificar lista_N_arr
    old_left = float(H_n[i - 1]) if i > 0 else 0.0
    old_right = float(H_n[i]) if i < N - 1 else 0.0
    new_left_val = float(nuevo_valor - lista_N_arr[i - 1]) if i > 0 else 0.0
    new_right_val = float(lista_N_arr[i + 1] - nuevo_valor) if i < N - 1 else 0.0

    estado['H_sum'] += -old_left - old_right + new_left_val + new_right_val
    estado['H_sq_sum'] += -old_left ** 2 - old_right ** 2 + new_left_val ** 2 + new_right_val ** 2
    if i > 0:
        H_n[i - 1] = new_left_val
    if i < N - 1:
        H_n[i] = new_right_val

    lista_N_arr[i] = nuevo_valor

    if len(idx_aff) > 0:
        lows_aff = lows[idx_aff]
        d_left = np.abs(lows_aff - s_left)
        d_cand = np.abs(lows_aff - nuevo_valor)
        d_right = np.abs(lows_aff - s_right)
        nearest_idx = np.argmin(np.stack([d_left, d_cand, d_right], axis=1), axis=1)
        new_assign = np.where(nearest_idx == 0, i - 1, np.where(nearest_idx == 1, i, i + 1))
        asignaciones[idx_aff] = new_assign

        nearest_val = np.where(nearest_idx == 0, s_left,
                               np.where(nearest_idx == 1, nuevo_valor, s_right))
        dist_sq_aff = (nearest_val - lows_aff) ** 2
        h_dist_aff = 1.0 - dist_sq_aff / dist_max
        z_aff_new = (fixed_z[idx_aff] * h_dist_aff if 'h_dist' in factores
                     else fixed_z[idx_aff].copy())

        estado['z_sum'] += float(z_aff_new.sum() - z[idx_aff].sum())
        z[idx_aff] = z_aff_new

        if 'soporte' in df_extremos.columns:
            df_extremos.loc[idx_aff, 'soporte'] = nearest_val
            df_extremos.loc[idx_aff, 'dist'] = dist_sq_aff
            df_extremos.loc[idx_aff, 'h_dist'] = h_dist_aff
            df_extremos.loc[idx_aff, 'z'] = z_aff_new

    N_gaps = N - 1
    H_mean = estado['H_sum'] / N_gaps if N_gaps > 0 else 0.0
    H_var = max(0.0, estado['H_sq_sum'] / N_gaps - H_mean ** 2) if N_gaps > 0 else 0.0
    cv_Hn = float(np.sqrt(H_var) / H_mean) if H_mean != 0 else 0.0
    mean_z = estado['z_sum'] / n
    estado['mean_z'] = mean_z
    estado['cv_Hn'] = cv_Hn
    estado['FO'] = mean_z - lambda_ponderador * cv_Hn


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
                         prueba_cercanos: bool = True,
                         delta_inicial: float = 1e-4,
                         estado_compartido=None, llave: str = '',
                         verbose: bool = True) -> tuple:
    """
    Optimizador de búsqueda local sobre el conjunto N de soportes.

    En cada iteración j:
      Para cada soporte i (en orden de casos_moviles):
        - Genera M candidatos equidistantes entre el soporte anterior y el siguiente.
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
    delta = N - len(ordenes_activas) - len(conjunto_N)
    delta2 = N - len(ordenes_activas)

    if delta2 < 0:
        sys.exit('Cantidad de ordenes activas es mayor a N')

    p_min = df_extremos['Low'].min()
    p_max = df_extremos['Low'].max()
    if verbose:
        print(f'Rango de precios: [{p_min:.2f}, {p_max:.2f}]')

    if delta >= 0:
        conjunto_N = conjunto_N.union(_inicializar_conjunto_smart(df_extremos, delta))
    elif delta2 > 0:
        conjunto_N = _inicializar_conjunto_smart(df_extremos, delta2)

    conjunto_N = conjunto_N.union(set(ordenes_activas))

    if len(conjunto_N) != N:
        sys.exit(f'Error en tamaño conjunto_N tras inicialización: {len(conjunto_N)} != {N}')

    lista_N = sorted(list(conjunto_N))
    dic_N = {i: val for i, val in enumerate(lista_N)}
    casos_moviles = list(dic_N.keys())
    mejora_acumulada = {i: 0.0 for i in dic_N}
    EMA_ALPHA = 0.3
    df_FO = pd.DataFrame()

    # Pre-init: una sola llamada a calcular_FO para inicializar df_extremos (soporte, dist, h_dist, z)
    # y luego construir el estado incremental que se mantiene actualizado en O(3n/N) por cambio.
    lista_N_arr = np.array(lista_N, dtype=np.float64)
    FO_base, df_extremos, particion_FO = calcular_FO(df_extremos, conjunto_N, lambda_ponderador)
    _estado = _init_estado_incremental(df_extremos, lista_N_arr, lambda_ponderador)

    for j in range(max_iters):
        lista_N = list(dic_N.values())
        conjunto_N = set(lista_N)

        if len(conjunto_N) != N:
            sys.exit(f'Error en tamaño conjunto_N en iteración {j}: {len(conjunto_N)} != {N}')

        FO_base = _estado['FO']
        particion_FO = [_estado['mean_z'], _estado['cv_Hn']]
        mejora = False

        if estado_compartido is not None and llave:
            prev_fo = estado_compartido.get(llave, (0, 0, None, ''))[2]
            fo_mostrar = FO_base if prev_fo is None else max(FO_base, prev_fo)
            estado_compartido[llave] = (cambios, max_pasos, fo_mostrar, 'corriendo')

        for pos, i in enumerate(tqdm.tqdm(casos_moviles, disable=not verbose)):
            cota_inf = dic_N[i - 1] if (i - 1) in dic_N else p_min
            cota_sup = dic_N[i + 1] if (i + 1) in dic_N else p_max

            # Candidatos equidistantes; se excluyen los extremos para evitar duplicar soportes vecinos
            casos_random = np.linspace(cota_inf, cota_sup, M)[1:-1]

            # Evaluación incremental: O(M × 3n/N) en vez de O(M × n)
            FO_values = _fo_incremental_batch(_estado, lista_N_arr, i, casos_random, lambda_ponderador)
            df_plot = pd.DataFrame({'caso': casos_random, 'FO_iter': FO_values})

            cumplen_logica = evaluar_crecimiento_decrecimiento(df_plot, 'FO_iter')
            if cumplen_logica:
                # Ajuste cuadrático; se clipa al rango válido para garantizar H_n positivos
                coef = np.polyfit(df_plot['caso'], df_plot['FO_iter'], 2)
                a_c, b_c, _ = coef
                caso = float(np.clip(-b_c / (2 * a_c), cota_inf + 1e-8, cota_sup - 1e-8))
                FO_iter = float(_fo_incremental_batch(
                    _estado, lista_N_arr, i, np.array([caso]), lambda_ponderador)[0])
            else:
                idx_max = int(df_plot['FO_iter'].argmax())
                caso = float(df_plot['caso'].iloc[idx_max])
                FO_iter = float(df_plot['FO_iter'].iloc[idx_max])

            mejora_rel = (FO_iter - FO_base) / abs(FO_base)
            if mejora_rel > delta_inicial:
                _actualizar_estado(_estado, lista_N_arr, i, caso, lambda_ponderador, df_extremos)
                if verbose:
                    print(f'  Mejora {mejora_rel:.6f} en soporte i={i}, nuevo={caso:.2f}')
                mejora_acumulada[i] = EMA_ALPHA * mejora_rel + (1 - EMA_ALPHA) * mejora_acumulada[i]
                mejora = True
                cambios += 1
                max_pasos = max(max_pasos, pos + 1)
                if estado_compartido is not None and llave:
                    prev_fo = estado_compartido.get(llave, (0, 0, None, ''))[2]
                    fo_mostrar = _estado['FO'] if prev_fo is None else max(_estado['FO'], prev_fo)
                    estado_compartido[llave] = (cambios, max_pasos, fo_mostrar, 'corriendo')
                FO_base = _estado['FO']
                particion_FO = [_estado['mean_z'], _estado['cv_Hn']]
                i_change = i
                nuevo_value = caso

            if mejora:
                break

        if not mejora:
            if len(casos_moviles) == len(dic_N):
                convergio = True
                break  # ya se probaron todos los soportes sin mejora → convergencia
            if verbose:
                print('Sin mejora en casos actuales → ampliando a todos los soportes')
            casos_moviles = sorted(dic_N.keys(), key=lambda c: -mejora_acumulada[c])
        else:
            dic_N[i_change] = nuevo_value
            if verbose:
                print(f'FO {j}: {notacion_cientifica(FO_base, 4)} | '
                      f'[{notacion_cientifica(particion_FO[0], 4)}, {notacion_cientifica(particion_FO[1], 4)}]')

            if prueba_cercanos:
                vecinos = [i_change - 1, i_change + 1, i_change]
                resto = sorted(
                    [c for c in casos_moviles if c not in vecinos],
                    key=lambda c: -mejora_acumulada[c],
                )
                casos_moviles = vecinos + resto
            else:
                casos_moviles = sorted(casos_moviles, key=lambda c: -mejora_acumulada[c])

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
                           graficar: bool = False, zoom: bool = False):
    if not graficar and not zoom:
        return
    df_plot = df_0.tail(100) if zoom else df_0
    p_min, p_max = df_plot['Low'].min(), df_plot['High'].max()
    sufijo = ' (zoom)' if zoom else ''
    plt.figure(figsize=(21, 7))
    plt.title(f'Soportes{sufijo} — {valor} N={N}')
    plt.plot(df_plot['DateTime'], df_plot['Low'], color='b', label='Low')
    plt.plot(df_plot['DateTime'], df_plot['High'], color='g', label='High')
    for s in sorted(conjunto_N):
        if p_min <= s <= p_max:
            plt.axhline(y=s, color='r', linestyle='--', alpha=0.5)
    plt.grid()
    plt.legend()
    subcarpeta = 'Zoom' if zoom else 'Soportes'
    _guardar_plot(subcarpeta, f'{valor}_{N}')


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
                    .reset_index(drop=True))
        else:
            data = df

        data.to_csv(csv_path, index=False)
        print(f'  Guardado: {csv_path.name} ({len(data)} velas, último: {df["DateTime"].iloc[-1]})')

    mt5.shutdown()


# ─── Etapa 2: Búsqueda de soportes óptimos ───────────────────────────────────

def _bt_warm_start(carpeta_n_bt: Path, valor: str, N: int, fecha_hora_max) -> set:
    """Retorna el conjunto_N del cache bt más reciente con timestamp <= fecha_hora_max."""
    bt_path = carpeta_n_bt / f'{valor}_{N}_bt.json'
    if not bt_path.exists():
        return set()
    with open(bt_path) as f:
        cache = json.load(f)
    candidatos = {k: v for k, v in cache.items() if pd.to_datetime(k) <= fecha_hora_max}
    if not candidatos:
        return set()
    mejor_t = max(candidatos, key=lambda k: pd.to_datetime(k))
    return set(candidatos[mejor_t])


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


def _guardar_log_convergencia(valor: str, N: int, es_bt: bool, clave_bt: str,
                              t_inicio: float, t_fin: float,
                              iteraciones: int, cambios: int,
                              FO_inicial: float, FO_final: float,
                              delta_final: float, convergio: bool):
    """Agrega una entrada al log de convergencia de un combo (valor, N) en docs/X0/logs/."""
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
                      estado_compartido=None, verbose: bool = True):
    """Worker para ProcessPoolExecutor: procesa un único par (valor, N).

    fecha_hora_max: datetime opcional. Si se pasa, modo backtesting — filtra datos hasta
                   esa fecha/hora y usa/actualiza el cache _bt.json en lugar de producción.
    """
    t_inicio = time.time()
    es_bt = fecha_hora_max is not None
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
    df = df.sort_values('DateTime').reset_index(drop=True)
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

    # Warm start
    if es_bt:
        conjunto_N_prev = _bt_warm_start(carpeta_n_bt, valor, N, fecha_hora_max)
        if verbose:
            print(f'  Warm start bt: {len(conjunto_N_prev)} soportes' if conjunto_N_prev
                  else '  Warm start bt: cold start')
    else:
        json_path = carpeta_n_prod / f'{valor}_{N}'
        conjunto_N_prev = set()
        if Path(f'{json_path}.json').exists():
            conjunto_N_prev = set(json_act(str(json_path)))
            if verbose:
                print(f'  Warm start: {len(conjunto_N_prev)} soportes cargados desde JSON')

    # Delta
    delta_path = (carpeta_n_bt if es_bt else carpeta_n_prod) / (
        f'{valor}_{N}_bt_delta.json' if es_bt else f'{valor}_{N}_delta.json'
    )
    if delta_path.exists():
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
    df_extremos, conjunto_N = obtener_df_extremos(df, K, N_EXP, N, conjunto_N_prev, verbose=verbose)

    FO_ref, _, _ = calcular_FO(df_extremos, conjunto_N, LAMBDA)
    if verbose:
        print(f'  FO inicial: {notacion_cientifica(FO_ref)}')

    oa = [] if es_bt else ordenes_activas
    if oa and verbose:
        print(f'  Órdenes activas fijas: {[round(p, 2) for p in oa]}')
    # Fase 1: exploración barata con M_COARSE
    conjunto_N, df_extremos, df_FO_1, _, cambios_1, max_pasos_1 = nuevo_optimizador_2(
        N, df_extremos, conjunto_N, LAMBDA,
        ordenes_activas=oa, M=M_COARSE, max_iters=MAX_ITERS, delta_inicial=delta_actual,
        estado_compartido=estado_compartido, llave=llave, verbose=verbose,
    )
    # Fase 2: refinamiento fino con M (warm start desde resultado de fase 1)
    conjunto_N, df_extremos, df_FO_2, convergio, cambios_2, max_pasos_2 = nuevo_optimizador_2(
        N, df_extremos, conjunto_N, LAMBDA,
        ordenes_activas=oa, M=M, max_iters=MAX_ITERS, delta_inicial=delta_actual,
        estado_compartido=estado_compartido, llave=llave, verbose=verbose,
    )
    df_FO_2['Iteracion'] += len(df_FO_1)
    df_FO = pd.concat([df_FO_1, df_FO_2], ignore_index=True)
    cambios = cambios_1 + cambios_2
    max_pasos = max(max_pasos_1, max_pasos_2)
    if verbose:
        print(f'  Cambios aceptados {valor} {N}: {cambios}')

    if not es_bt:
        graficar_df_extremos(df_extremos, valor=valor, N=N, graficar=GRAFICAR_EXTREMOS)
        graficar_performance_FO(df_FO, valor=valor, N=N, graficar=GRAFICAR_FO)
        graficar_soportes_all(df, conjunto_N, valor=valor, N=N, graficar=GRAFICAR_SOPORTES, zoom=GRAFICAR_ZOOM)

    # Guardar soportes
    if es_bt:
        _bt_guardar(carpeta_n_bt, valor, N, fecha_hora_clave, conjunto_N)
        if verbose:
            print(f'  Guardado bt: {valor}_{N}_bt.json [{fecha_hora_clave}]')
    else:
        json_act(str(json_path), conjunto_N, 'save')
        if verbose:
            print(f'  Guardado: {json_path}.json')

    FO_final, _, _ = calcular_FO(df_extremos, conjunto_N, LAMBDA)

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
        len(df_FO), cambios,
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
        estado_compartido[llave] = (cambios, -1, FO_final, 'listo')

    return round(duracion, 1), convergio


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
            line = f'{v} {N}: cambios={cambios:<6} iter={iter_str:<8} FO={fo_str:<14} [{estado_str}]'
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
        df_info = df_info[df_info['DateTime'] >= FECHA_INICIAL].reset_index(drop=True)
        if len(df_info):
            print(f'  Rango: {df_info["DateTime"].iloc[0]} → {df_info["DateTime"].iloc[-1]} ({len(df_info)} velas)')
            print(f'  Último cierre: {df_info["Close"].iloc[-1]:.2f}')
        json_path = carpeta_n_prod / f'{v}_{n}'
        if Path(f'{json_path}.json').exists():
            prev = set(json_act(str(json_path)))
            print(f'  Warm start: {len(prev)} soportes')
        else:
            print('  Warm start: cold start')
        delta_path = carpeta_n_prod / f'{v}_{n}_delta.json'
        if delta_path.exists():
            with open(delta_path) as f:
                delta_val = json.load(f)['delta_inicial']
            print(f'  delta_inicial: {notacion_cientifica(delta_val)}')
        else:
            print(f'  delta_inicial: {notacion_cientifica(DELTA_INICIAL)} (semilla)')

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
                    duracion, convergio_flag = future.result()
                    resultados_tiempo[f'{valor}_{N}'] = (duracion, convergio_flag)
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
            dur, conv = res
            mins = int(dur // 60)
            segs = dur % 60
            tiempo_str = f'{mins}m {segs:.1f}s' if mins > 0 else f'{segs:.1f}s'
            conv_str = 'convergió' if conv else 'no convergió'
            print(f'  {v} N={n}: {tiempo_str} | {conv_str}')



# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='X0: datos + soportes')
    parser.add_argument('--opcion', type=int, default=2,
                        choices=[0, 1, 2],
                        help='0=solo datos, 1=solo soportes, 2=ambos (default)')
    parser.add_argument('--loop', action='store_true',
                        help='Ejecutar en bucle continuo (while True). '
                             'Al terminar cada ciclo reinicia desde el principio. '
                             'Usa N_MAX_MODELS de config.py para seleccionar combos por ciclo.')
    args = parser.parse_args()

    CARPETA_DATA.mkdir(parents=True, exist_ok=True)
    CARPETA_N_PROD.mkdir(parents=True, exist_ok=True)
    CARPETA_N_BT.mkdir(parents=True, exist_ok=True)

    ciclo = 0
    try:
        while True:
            ciclo += 1
            if args.loop:
                print(f'\n{"═"*55}\n CICLO {ciclo}'
                      + (f' — top {N_MAX_MODELS} combos' if N_MAX_MODELS else ' — todos los combos')
                      + f'\n{"═"*55}')

            try:
                if args.opcion in (0, 2):
                    print('\n── Etapa 1: Descarga de datos ──────────────────────────')
                    try:
                        descargar_datos(VALORES, CARPETA_DATA)
                    except Exception as e:
                        if args.loop:
                            print(f'  Advertencia: descarga de datos falló ({e}). '
                                  f'Continuando con datos existentes.')
                        else:
                            raise

                if args.opcion in (1, 2):
                    print('\n── Etapa 2: Búsqueda de soportes ───────────────────────')
                    print('Consultando posiciones activas en MT5...')
                    ordenes_activas_mt5 = obtener_ordenes_activas_mt5(VALORES)
                    buscar_soportes(VALORES, n_sizes, CARPETA_DATA, CARPETA_N_PROD, CARPETA_N_BT, ordenes_activas_mt5,
                                    n_max=N_MAX_MODELS)

            except Exception as e:
                if args.loop:
                    print(f'\nError en ciclo {ciclo}: {e}. Reintentando en el próximo ciclo.')
                else:
                    raise

            if not args.loop:
                break

    except KeyboardInterrupt:
        print(f'\nDetenido por el usuario tras {ciclo} ciclo(s).')
