"""
X0_data_supports.py

Etapa 1 (--opcion 0 o 2): Descarga velas OHLCV H1 desde MetaTrader5 y actualiza los CSVs en Data/.
Etapa 2 (--opcion 1 o 2): Busca N soportes/resistencias óptimos por activo usando un optimizador
                           de búsqueda local y guarda los resultados en conjuntosN2/.

Uso:
    python X0_data_supports.py               # opcion=2: ambas etapas
    python X0_data_supports.py --opcion 0    # solo descarga de datos
    python X0_data_supports.py --opcion 1    # solo búsqueda de soportes
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import random
import shutil
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd
import tqdm

warnings.filterwarnings('ignore')

from config import (
    CARPETA_DATA, CARPETA_N2,
    VALORES, FECHA_INICIAL,
    K, N_EXP, BLOQUE_DISTANCIAS, parametros_soportes,
    M, LAMBDA, MAX_ITERS,
    GRAFICAR_EXTREMOS, GRAFICAR_FO, GRAFICAR_SOPORTES, GRAFICAR_ZOOM,
    n_sizes,
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


# ─── Funciones del algoritmo ──────────────────────────────────────────────────

def _vecino_mas_cercano(valores: np.ndarray, low: np.ndarray, high: np.ndarray,
                        t: np.ndarray, block_size: int = BLOQUE_DISTANCIAS) -> tuple:
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

    for inicio in tqdm.tqdm(range(0, n, block_size)):
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


def calcular_distancias(df: pd.DataFrame, find_low: bool = True, find_high: bool = True) -> pd.DataFrame:
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
        df['Low_left'], df['Low_right'] = _vecino_mas_cercano(low, low, high, t)
    if find_high:
        df['High_left'], df['High_right'] = _vecino_mas_cercano(high, low, high, t)

    # Velas sin vecino (extremos del dataset): distancia hasta el borde del período
    if find_low:
        df['Low_left'] = df['Low_left'].fillna(df['t'])
        df['Low_right'] = df['Low_right'].fillna(max_t - df['t'])
    if find_high:
        df['High_left'] = df['High_left'].fillna(df['t'])
        df['High_right'] = df['High_right'].fillna(max_t - df['t'])

    return df


def obtener_df_extremos(df_0: pd.DataFrame, k: float, n_exp: float, N: int,
                         conjunto_N: set = set(), ocp: int = 0) -> tuple:
    """
    Calcula las columnas y (aislamiento) y w (recencia) usadas por la FO.
    Inicializa conjunto_N con puntos aleatorios si viene vacío o incompleto.
    ocp: órdenes de compra ya planificadas en la plataforma (fijas, no se optimizan).
    """
    df_extremos = calcular_distancias(df_0)

    if 'High_left' in df_extremos.columns:
        df_extremos['y'] = (df_extremos['High_left'] + df_extremos['Low_left']
                            + k * (df_extremos['High_right'] + df_extremos['Low_right']))
    else:
        df_extremos['y'] = df_extremos['Low_left'] + k * df_extremos['Low_right']

    df_extremos['w'] = df_extremos['t'] ** n_exp
    df_extremos['v'] = df_extremos['Tick_Volume'] / df_extremos['Tick_Volume'].max()

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
                         delta_inicial: float = 1e-4) -> tuple:
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
    print(f'Iniciando optimizador | max_iters={max_iters} | N={N} | M={M}')

    # Inicializar conjunto_N respetando las ordenes activas
    delta = N - len(ordenes_activas) - len(conjunto_N)
    delta2 = N - len(ordenes_activas)

    if delta2 < 0:
        sys.exit('Cantidad de ordenes activas es mayor a N')

    p_min = df_extremos['Low'].min()
    p_max = df_extremos['Low'].max()
    print(f'Rango de precios: [{p_min:.2f}, {p_max:.2f}]')

    if delta >= 0:
        conjunto_N = conjunto_N.union(set(np.random.uniform(p_min, p_max, delta).tolist()))
    elif delta2 > 0:
        conjunto_N = set(np.random.uniform(p_min, p_max, delta2).tolist())

    conjunto_N = conjunto_N.union(set(ordenes_activas))

    if len(conjunto_N) != N:
        sys.exit(f'Error en tamaño conjunto_N tras inicialización: {len(conjunto_N)} != {N}')

    lista_N = sorted(list(conjunto_N))
    dic_N = {i: val for i, val in enumerate(lista_N)}
    casos_moviles = list(dic_N.keys())
    df_FO = pd.DataFrame()

    for j in range(max_iters):
        lista_N = list(dic_N.values())
        conjunto_N = set(lista_N)

        if len(conjunto_N) != N:
            sys.exit(f'Error en tamaño conjunto_N en iteración {j}: {len(conjunto_N)} != {N}')

        FO_base, df_extremos, particion_FO = calcular_FO(df_extremos, conjunto_N, lambda_ponderador)
        mejora = False

        for i in tqdm.tqdm(casos_moviles):
            cota_inf = dic_N[i - 1] if (i - 1) in dic_N else p_min
            cota_sup = dic_N[i + 1] if (i + 1) in dic_N else p_max

            # Candidatos equidistantes; se excluyen los extremos para evitar duplicar soportes vecinos
            casos_random = np.linspace(cota_inf, cota_sup, M)[1:-1]

            # Evaluar todos los candidatos y guardar FO de cada uno
            df_plot = pd.DataFrame()
            df_ext_iter, part_iter = None, None
            for caso in casos_random:
                lista_iter = lista_N[:]
                lista_iter.remove(dic_N[i])
                lista_iter.append(caso)
                FO_iter, df_ext_iter, part_iter = calcular_FO(df_extremos, set(lista_iter), lambda_ponderador)
                df_plot = pd.concat([df_plot, pd.DataFrame({'caso': [caso], 'FO_iter': [FO_iter]})])
            # Nota: al salir del loop, df_ext_iter y part_iter corresponden al ÚLTIMO caso evaluado.
            # Si cumplen_logica=False, se usan estos valores (comportamiento del notebook original).

            cumplen_logica = evaluar_crecimiento_decrecimiento(df_plot, 'FO_iter')
            if cumplen_logica:
                # Ajuste cuadrático para encontrar el máximo analítico
                coef = np.polyfit(df_plot['caso'], df_plot['FO_iter'], 2)
                a_c, b_c, _ = coef
                caso = -b_c / (2 * a_c)
                lista_iter = lista_N[:]
                lista_iter.remove(dic_N[i])
                lista_iter.append(caso)
                FO_iter, df_ext_iter, part_iter = calcular_FO(df_extremos, set(lista_iter), lambda_ponderador)
            else:
                caso = float(df_plot.loc[df_plot['FO_iter'].idxmax(), 'caso'])
                FO_iter = float(df_plot['FO_iter'].max())

            if (FO_iter - FO_base) / FO_base > delta_inicial:
                print(f'  Mejora {(FO_iter - FO_base) / FO_base:.6f} en soporte i={i}, nuevo={caso:.2f}')
                mejora = True
                FO_base = FO_iter
                i_change = i
                nuevo_value = caso
                df_extremos = df_ext_iter.copy()
                particion_FO = part_iter[:]

            if mejora:
                break

        if not mejora:
            if len(casos_moviles) == len(dic_N):
                break  # ya se probaron todos los soportes sin mejora → convergencia
            print('Sin mejora en casos actuales → ampliando a todos los soportes')
            casos_moviles = list(dic_N.keys())
        else:
            dic_N[i_change] = nuevo_value
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

    return conjunto_N, df_extremos, df_FO


# ─── Visualizaciones ──────────────────────────────────────────────────────────

def graficar_df_extremos(df_extremos: pd.DataFrame, graficar: bool = False):
    if not graficar:
        return
    fig, axes = plt.subplots(2, 2, figsize=(21, 10))
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
    plt.show()


def graficar_performance_FO(df_FO: pd.DataFrame, graficar: bool = False):
    if not graficar or len(df_FO) <= 1:
        return
    _, ax1 = plt.subplots(figsize=(21, 7))
    ax1.plot(df_FO['Iteracion'], df_FO['FO'], color='b', label='FO')
    ax1.set_ylabel('FO')
    ax1.grid()
    plt.title('Evolución FO por iteración')
    plt.show()


def graficar_soportes_all(df_0: pd.DataFrame, conjunto_N: set,
                           graficar: bool = False, zoom: bool = False):
    if not graficar and not zoom:
        return
    df_plot = df_0.tail(100) if zoom else df_0
    p_min, p_max = df_plot['Low'].min(), df_plot['High'].max()
    plt.figure(figsize=(21, 7))
    plt.plot(df_plot['DateTime'], df_plot['Low'], color='b', label='Low')
    plt.plot(df_plot['DateTime'], df_plot['High'], color='g', label='High')
    for s in sorted(conjunto_N):
        if p_min <= s <= p_max:
            plt.axhline(y=s, color='r', linestyle='--', alpha=0.5)
    plt.grid()
    plt.legend()
    plt.show()


# ─── Etapa 1: Descarga de datos desde MT5 ────────────────────────────────────

def descargar_datos(valores: list, carpeta_data: Path):
    import MetaTrader5 as mt5

    if not mt5.initialize():
        sys.exit(f'MT5 initialize() falló: {mt5.last_error()}')

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

def _procesar_valor_N(valor: str, N: int, carpeta_data: Path, carpeta_n2: Path):
    """Worker para ProcessPoolExecutor: procesa un único par (valor, N)."""
    print(f'\n{"="*55}\nProcesando {valor} N={N}')

    csv_path = carpeta_data / f'{valor}.csv'
    if not csv_path.exists():
        print(f'  CSV no encontrado: {csv_path}, skip')
        return

    df = pd.read_csv(csv_path)
    df = df.sort_values('DateTime').reset_index(drop=True)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df = df[df['DateTime'] >= FECHA_INICIAL].reset_index(drop=True)

    if len(df) == 0:
        print(f'  Sin datos desde {FECHA_INICIAL}, skip')
        return

    print(f'  Rango: {df["DateTime"].iloc[0]} → {df["DateTime"].iloc[-1]} ({len(df)} velas)')
    print(f'  Último cierre: {df["Close"].iloc[-1]:.2f}')

    dt_min = df['DateTime'].min()
    df['t'] = (df['DateTime'] - dt_min).dt.total_seconds() / 3600
    df['t'] = df['t'] / df['t'].max()

    beta_path = carpeta_n2 / f'{valor}_{N}_beta'
    conjunto_N_prev = set()
    if Path(f'{beta_path}.json').exists():
        conjunto_N_prev = set(json_act(str(beta_path)))
        print(f'  Warm start: {len(conjunto_N_prev)} soportes cargados desde JSON')

    print('  Calculando distancias...')
    df_extremos, conjunto_N = obtener_df_extremos(df, K, N_EXP, N, conjunto_N_prev)

    FO_ref, _, _ = calcular_FO(df_extremos, conjunto_N, LAMBDA)
    print(f'  FO inicial: {notacion_cientifica(FO_ref)}')

    conjunto_N, df_extremos, df_FO = nuevo_optimizador_2(
        N, df_extremos, conjunto_N, LAMBDA,
        ordenes_activas=[], M=M, max_iters=MAX_ITERS,
    )

    graficar_df_extremos(df_extremos, graficar=GRAFICAR_EXTREMOS)
    graficar_performance_FO(df_FO, graficar=GRAFICAR_FO)
    graficar_soportes_all(df, conjunto_N, graficar=GRAFICAR_SOPORTES, zoom=GRAFICAR_ZOOM)

    json_act(str(beta_path), conjunto_N, 'save')
    print(f'  Guardado: {beta_path}.json')


def buscar_soportes(valores: list, n_sizes: dict, carpeta_data: Path, carpeta_n2: Path):
    # Construir todas las tuplas (valor, N) y ordenar por antigüedad del beta
    tuplas = []
    for valor in valores:
        for N in n_sizes[valor]:
            beta_path = carpeta_n2 / f'{valor}_{N}_beta.json'
            fecha = (datetime.datetime.fromtimestamp(beta_path.stat().st_mtime)
                     if beta_path.exists() else datetime.datetime(2000, 1, 1))
            tuplas.append((valor, N, fecha))

    tuplas_ordenadas = [(v, n) for v, n, _ in sorted(tuplas, key=lambda x: x[2])]
    print('Orden de procesamiento:', tuplas_ordenadas)

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(_procesar_valor_N, v, n, carpeta_data, carpeta_n2): (v, n)
            for v, n in tuplas_ordenadas
        }
        for future in concurrent.futures.as_completed(futures):
            valor, N = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f'Error en ({valor}, N={N}): {exc}')


def promover_a_productivo(valores: list, n_sizes: dict, carpeta_n2: Path):
    """
    Mueve _beta.json → {valor}_{N}.json y mantiene una copia en _beta.json.
    El archivo productivo (sin _beta) es el que lee X1 para operar.
    """
    print('\nPromoviendo resultados a productivo...')
    for valor in valores:
        for N in n_sizes[valor]:
            beta_path = carpeta_n2 / f'{valor}_{N}_beta.json'
            prod_path = carpeta_n2 / f'{valor}_{N}.json'

            if not beta_path.exists():
                print(f'  {valor} N={N}: no existe _beta.json, skip')
                continue

            if prod_path.exists():
                prod_path.unlink()

            beta_path.rename(prod_path)
            shutil.copy(prod_path, beta_path)
            print(f'  {valor} N={N}: {prod_path.name} actualizado')


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='X0: datos + soportes')
    parser.add_argument('--opcion', type=int, default=2,
                        choices=[0, 1, 2],
                        help='0=solo datos, 1=solo soportes, 2=ambos (default)')
    args = parser.parse_args()

    CARPETA_DATA.mkdir(parents=True, exist_ok=True)
    CARPETA_N2.mkdir(parents=True, exist_ok=True)

    if args.opcion in (0, 2):
        print('\n── Etapa 1: Descarga de datos ──────────────────────────')
        descargar_datos(VALORES, CARPETA_DATA)

    if args.opcion in (1, 2):
        print('\n── Etapa 2: Búsqueda de soportes ───────────────────────')
        buscar_soportes(VALORES, n_sizes, CARPETA_DATA, CARPETA_N2)
        promover_a_productivo(VALORES, n_sizes, CARPETA_N2)
