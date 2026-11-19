"""
Pruebas de x5_alt_aprendizaje.py (RLM con ridge y Gradient Ascent de Q5-5).

Ventanas sintéticas con una relación conocida entre `Y` y los C2 (nombres de columna como los de `_ventanas.csv`, con C1 de
nombre compuesto como `N_EXP`), más un ajuste de humo con las ventanas reales de BTCUSD si existen. Sin MT5. Corren sin pytest:
    python scripts/test_x5_alt_aprendizaje.py
"""

import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
import config_smart
from x5_alt_aprendizaje import (
    ajustar_rlm,
    gradiente,
    limites_c2,
    matriz_c2,
    parsear_columnas_c2,
    proponer_c2,
    terminos_modelo,
    vector_c2,
)
from x5_alt_funciones import cargar_c2_q4

C2_BASE = {
    'N': {'pesos': {'a': 0.5, 'b': 0.3, 'c': 0.2}, 'span': 12, 'punto_medio': 0.0, 'pendiente': 3.0},
    'N_EXP': {'pesos': {'v': 1.0}, 'span': 12, 'punto_medio': 0.0, 'pendiente': 2.0},
    'K': {'pesos': {'r': 1.0}, 'span': 12, 'punto_medio': 0.0, 'pendiente': 2.0},
}


def _ventanas_sinteticas(n: int, y, semilla: int = 0) -> pd.DataFrame:
    """`n` ventanas con C2 sorteados uniformes en los rangos de `rangos_sorteo_c2(C2_BASE)` y `Y = y(df)`."""
    rng = np.random.default_rng(semilla)
    d = {}
    for c1, c in C2_BASE.items():
        for variable, w in c['pesos'].items():
            d[f'c2_{c1}_w_{variable}'] = rng.uniform(max(0.05, w - 0.2), min(1.0, w + 0.2), n) if len(c['pesos']) > 1 else 1.0
        d[f'c2_{c1}_span'] = rng.integers(6, 25, n)
        d[f'c2_{c1}_punto_medio'] = rng.uniform(-0.5, 0.5, n)
        d[f'c2_{c1}_pendiente'] = rng.uniform(c['pendiente'] / 2, c['pendiente'] * 2, n)
    d['ret_medio'] = rng.normal(0, 0.02, n)
    d['ret_vol'] = np.abs(rng.normal(0.005, 0.002, n))
    df = pd.DataFrame(d)
    w_a = df['c2_N_w_a'] / (df['c2_N_w_a'] + df['c2_N_w_b'] + df['c2_N_w_c'])
    df['w_a'] = w_a
    df['Y'] = y(df) + rng.normal(0, 0.1, n)
    return df


def _lineal(df):
    return 100 * df['w_a'] + 60 * df['c2_N_punto_medio'] - 25 * df['c2_K_pendiente'] + 500 * df['ret_medio']


def test_parseo_de_columnas_con_c1_compuesto():
    g = parsear_columnas_c2(['c2_N_EXP_w_cambio_volatilidad', 'c2_N_EXP_span', 'c2_factor_B_w_adx_14', 'c2_factor_B_pendiente',
                             'c2_N_w_x3_atr_pct', 'c2_K_w_-|ruptura_rango|', 'c2_PERDIDA_MAX_punto_medio', 'c1_N', 'Y'])
    assert set(g) == {'N_EXP', 'factor_B', 'N', 'K', 'PERDIDA_MAX'}
    assert g['N_EXP']['pesos'] == {'cambio_volatilidad': 'c2_N_EXP_w_cambio_volatilidad'}
    assert g['N_EXP']['campos'] == {'span': 'c2_N_EXP_span'}
    assert g['K']['pesos'] == {'-|ruptura_rango|': 'c2_K_w_-|ruptura_rango|'}
    assert g['PERDIDA_MAX']['campos'] == {'punto_medio': 'c2_PERDIDA_MAX_punto_medio'}


def test_terminos_omiten_constantes_y_un_peso_por_grupo():
    df = _ventanas_sinteticas(40, _lineal)
    terminos, omitidas = terminos_modelo(df)
    assert omitidas == {'N': 'c'}  # solo N tiene más de un peso que varía; se omite el último
    assert ('peso', 'N', 'a') in terminos and ('peso', 'N', 'b') in terminos and ('peso', 'N', 'c') not in terminos
    assert not any(t[0] == 'peso' and t[1] in ('N_EXP', 'K') for t in terminos)  # C1 de una variable: w̃ = 1 constante
    assert len(terminos) == 2 + 3 * 3  # 2 pesos libres de N y span, punto_medio, pendiente de los 3 C1


def test_matriz_normaliza_los_pesos_y_coincide_con_el_vector_de_un_c2():
    df = _ventanas_sinteticas(30, _lineal)
    terminos, _ = terminos_modelo(df)
    x = matriz_c2(df, terminos)
    j = terminos.index(('peso', 'N', 'a'))
    assert np.allclose(x[:, j], df['w_a'])
    fila = df.iloc[3]
    c2 = {c1: {'pesos': {v: fila[f'c2_{c1}_w_{v}'] for v in c['pesos']}, 'span': fila[f'c2_{c1}_span'],
               'punto_medio': fila[f'c2_{c1}_punto_medio'], 'pendiente': fila[f'c2_{c1}_pendiente']}
          for c1, c in C2_BASE.items()}
    assert np.allclose(vector_c2(c2, terminos), x[3])


def test_rlm_recupera_la_relacion_lineal_y_su_gradiente():
    df = _ventanas_sinteticas(80, _lineal)
    m = ajustar_rlm(df, grado=1)
    assert m.n == 80 and m.r2_cv > 0.95
    x0 = vector_c2({c1: {'pesos': c['pesos'], 'span': 12, 'punto_medio': 0.0, 'pendiente': c['pendiente']}
                    for c1, c in C2_BASE.items()}, m.terminos)
    g = dict(zip(m.terminos, gradiente(m, x0)))
    assert abs(g[('peso', 'N', 'a')] - 100) < 5
    assert abs(g[('punto_medio', 'N', None)] - 60) < 3
    assert abs(g[('pendiente', 'K', None)] + 25) < 1.5
    assert abs(g[('span', 'N', None)]) < 0.5  # no entra en Y
    assert m.coeficientes()['ret_medio'] > 0


def test_grado_2_captura_un_producto_cruzado():
    def cruzado(df):
        return 40 * df['c2_N_punto_medio'] * (df['c2_K_pendiente'] - 2.5)
    df = _ventanas_sinteticas(120, cruzado, semilla=1)
    assert ajustar_rlm(df, grado=1).r2_cv < 0.3
    assert ajustar_rlm(df, grado=2).r2_cv > 0.9


def test_pocas_ventanas_falla():
    df = _ventanas_sinteticas(9, _lineal)
    try:
        ajustar_rlm(df)
    except ValueError as e:
        assert 'al menos' in str(e)
    else:
        raise AssertionError('debió rechazar 9 ventanas')


def test_paso_mueve_mas_el_de_mayor_efecto_y_normaliza_pesos():
    m = ajustar_rlm(_ventanas_sinteticas(80, _lineal), grado=1)
    nuevo = proponer_c2(m, C2_BASE, C2_BASE, paso=0.10)
    # efecto = derivada × rango: pendiente de K (-25 × 3 = -75) > punto_medio de N (60 × 1) > w̃_a de N (~100 × 0.4)
    assert abs(nuevo['K']['pendiente'] - (2.0 - 0.10 * 3.0)) < 0.05  # el mayor efecto baja 10 % de su rango [1, 4]
    assert 0.05 < nuevo['N']['punto_medio'] - 0.0 < 0.11  # 10 % × (60 / 75) de su rango de 1,0
    assert abs(sum(nuevo['N']['pesos'].values()) - 1) < 1e-12
    assert nuevo['N']['pesos']['a'] > 0.5  # w̃_a sube
    assert isinstance(nuevo['N']['span'], int)
    assert nuevo['K']['pesos'] == {'r': 1.0} and nuevo['N_EXP']['pesos'] == {'v': 1.0}


def test_paso_se_recorta_al_rango_del_sorteo():
    m = ajustar_rlm(_ventanas_sinteticas(80, _lineal), grado=1)
    en_el_borde = {c1: dict(c) for c1, c in C2_BASE.items()}
    en_el_borde['K'] = dict(C2_BASE['K'], pendiente=1.0)  # piso del rango de K; el gradiente pide bajarla más
    en_el_borde['N'] = dict(C2_BASE['N'], punto_medio=0.5)  # techo; el gradiente pide subirla más
    nuevo = proponer_c2(m, en_el_borde, C2_BASE, paso=0.10)
    assert nuevo['K']['pendiente'] == 1.0 and nuevo['N']['punto_medio'] == 0.5
    _, limites_w = limites_c2(C2_BASE)
    for v, w in nuevo['N']['pesos'].items():
        assert limites_w['N'][v][0] - 1e-9 <= w <= limites_w['N'][v][1] + 1e-9


def test_humo_con_las_ventanas_reales_de_btcusd():
    ruta = cfg.CARPETA_Q5 / 'BTCUSD_ventanas.csv'
    q4 = cfg.CARPETA_X5_ALT / 'exp_Q4' / 'BTCUSD_q4_resumen.csv'
    if not ruta.exists() or not q4.exists():
        print('  (omitida: faltan BTCUSD_ventanas.csv o BTCUSD_q4_resumen.csv)')
        return
    df = pd.read_csv(ruta)
    df = df[df['fase'] == 'sobol']
    if len(df) < 2 * config_smart.PLIEGUES_CV:
        print('  (omitida: pocas ventanas Sobol)')
        return
    terminos, omitidas = terminos_modelo(df)
    assert len(terminos) == 26 and set(omitidas) == {'N', 'A', 'factor_B', 'LAMBDA'}
    assert matriz_c2(df, terminos).shape == (len(df), 26)
    m = ajustar_rlm(df)
    assert np.isfinite(m.r2_cv) and m.alpha in config_smart.ALPHAS_RIDGE
    c2_q4 = cargar_c2_q4(q4)
    nuevo = proponer_c2(m, c2_q4, c2_q4)
    assert set(nuevo) == set(c2_q4)
    for c1, c in nuevo.items():
        assert abs(sum(c['pesos'].values()) - 1) < 1e-9 and isinstance(c['span'], int)


if __name__ == '__main__':
    pruebas = [(n, f) for n, f in sorted(globals().items()) if n.startswith('test_') and callable(f)]
    fallos = 0
    for nombre, f in pruebas:
        try:
            f()
            print(f'PASS {nombre}')
        except Exception:
            fallos += 1
            print(f'FAIL {nombre}')
            traceback.print_exc()
    print(f'\n{len(pruebas) - fallos}/{len(pruebas)} pruebas pasan')
    sys.exit(1 if fallos else 0)
