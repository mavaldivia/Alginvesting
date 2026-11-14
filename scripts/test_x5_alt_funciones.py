"""
Pruebas de las funciones de Q5 de x5_alt_funciones.py (serie causal de cada C1, grilla, rangos de sorteo).

Usan los datos reales de Q1 y Q4 (resources/x5_alt/exp_Q1 y exp_Q4), sin mocks; el activo al que le falten
esos archivos se omite. Corren sin pytest:
    python scripts/test_x5_alt_funciones.py
"""

import copy
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
import config_smart
from x5_alt_funciones import (
    cargar_c2_q4,
    cargar_estructura_c1,
    drawdown_maximo,
    estadisticas_c1,
    lotajes_m,
    perdida_max_usd,
    premios_por_tramo,
    rangos_sorteo_c2,
    redondear_a_grilla,
    serie_c1,
    z_expanding,
)

EXP_Q1 = cfg.CARPETA_X5_ALT / 'exp_Q1'
EXP_Q4 = cfg.CARPETA_X5_ALT / 'exp_Q4'
ARCHIVO_Q4 = {'N': 'n', 'A': 'a', 'factor_B': 'factor_b', 'K': 'k', 'N_EXP': 'n_exp',
              'LAMBDA': 'lambda', 'PERDIDA_MAX': 'perdida_max'}


def _valores_disponibles():
    return [v for v in cfg.VALORES
            if (EXP_Q1 / f'{v}_tabla_estado_v2.csv').exists() and (EXP_Q4 / f'{v}_q4_resumen.csv').exists()]


def _tabla(valor):
    return pd.read_csv(EXP_Q1 / f'{valor}_tabla_estado_v2.csv', parse_dates=['DateTime'])


def _estructura():
    return cargar_estructura_c1(cfg.RUTA_ESTRUCTURA_C1)


def test_redondeo_ejemplo_del_plan():
    assert redondear_a_grilla(52.33, 40, 180, 10) == 50
    assert redondear_a_grilla(55.0, 40, 180, 10) == 60  # empate hacia arriba
    assert redondear_a_grilla(0.5, 0.2, 0.7, 0.05) == 0.5
    assert redondear_a_grilla(0.2501, 0.2, 0.7, 0.05) == 0.25
    assert redondear_a_grilla(999, 40, 180, 10) == 180  # nunca sale del rango


def test_perdida_max_usd():
    assert perdida_max_usd(0.04, 5000) == 200
    assert perdida_max_usd(0.04, -100) == 0


def test_premios_por_tramo_ejemplo_del_plan():
    z = np.full(42000, 3000.0)
    z[33599], z[-1] = 4200.0, 4500.0
    p = premios_por_tramo(z, 0.20)
    assert p['corte'] == 33600
    assert abs(p['premio_aprendizaje'] - 0.125) < 1e-12
    assert abs(p['premio_reservado'] - 300 / 8400) < 1e-12
    for malo in (np.full(1, 3000.0), np.array([3000.0, np.nan, 3000.0])):
        try:
            premios_por_tramo(malo, 0.20)
        except ValueError:
            continue
        raise AssertionError('debió rechazar una curva sin dos tramos o con NaN')


def test_drawdown_maximo():
    pct, usd = drawdown_maximo([3500, 2800, 3300], 3000)
    assert abs(usd + 700) < 1e-9 and abs(pct + 0.2) < 1e-12  # de 3500 a 2800
    assert drawdown_maximo([3100, 3200], 3000) == (0.0, 0.0)  # solo sube
    pct, usd = drawdown_maximo([2000], 3000)  # el capital inicial cuenta como el primer máximo
    assert abs(usd + 1000) < 1e-9


def test_estadisticas_c1():
    e = estadisticas_c1([50, 50, 60, 200, 200, 200], 50, 200)
    assert e['pasos'] == 3 and e['min'] == 50 and e['max'] == 200
    assert abs(e['pct_piso'] - 100 / 3) < 1e-9 and abs(e['pct_techo'] - 50) < 1e-9
    assert estadisticas_c1([0.3] * 5, 0.2, 0.7)['std'] == 0


def test_lotajes_m_ejemplos_del_plan():
    esperado = {3000: 1, 5999: 1, 6000: 2, 8999: 2, 9000: 3, 12000: 4, 0: 1, -10000: 1}
    for z, m in esperado.items():
        assert lotajes_m(z) == m, (z, lotajes_m(z), m)


def test_z_expanding_usa_solo_el_pasado():
    x = np.concatenate([np.random.default_rng(0).normal(size=200), [np.nan] * 3, np.random.default_rng(1).normal(size=50)])
    completo = z_expanding(x)
    parcial = z_expanding(x[:120])
    assert np.array_equal(completo[:120], parcial, equal_nan=True)
    assert np.all(completo[:29] == 0)  # menos de MIN_OBS_Z observaciones: neutro
    assert np.isnan(completo[200:203]).all()


def test_reproduce_columnas_hat_de_q4():
    estructura = _estructura()
    valores = _valores_disponibles()
    assert valores, 'faltan exp_Q1/exp_Q4 para probar'
    for valor in valores:
        tabla = _tabla(valor)
        resumen = pd.read_csv(EXP_Q4 / f'{valor}_q4_resumen.csv').set_index('parametro')
        c2_q4 = cargar_c2_q4(EXP_Q4 / f'{valor}_q4_resumen.csv')
        for parametro, c2 in c2_q4.items():
            rango = (resumen.loc[parametro, 'piso'], resumen.loc[parametro, 'techo'])
            serie = serie_c1(parametro, valor, c2, tabla, estructura, normalizacion='fija',
                             mu_sigma=c2['mu_sigma'], rango=rango, redondear=False)
            q4 = pd.read_csv(EXP_Q4 / f'{valor}_q4_{ARCHIVO_Q4[parametro]}.csv', parse_dates=['DateTime'])
            columna_hat = [c for c in q4.columns if c.endswith('_hat')][0]
            mio = pd.Series(serie['c1_sin_redondeo'], index=tabla['DateTime'])
            comparado = pd.concat([mio.rename('mio'), q4.set_index('DateTime')[columna_hat].rename('q4')], axis=1, join='inner')
            assert len(comparado) == len(q4), f'{valor} {parametro}: faltan filas'
            dif = (comparado['mio'] - comparado['q4']).abs().max()
            assert dif < 1e-6, f'{valor} {parametro}: diferencia máxima {dif:.3g} contra {columna_hat}'


def test_serie_expanding_es_causal():
    estructura = _estructura()
    for valor in _valores_disponibles()[:2]:
        tabla = _tabla(valor)
        c2_q4 = cargar_c2_q4(EXP_Q4 / f'{valor}_q4_resumen.csv')
        corte = int(len(tabla) * 0.6)
        for parametro, c2 in c2_q4.items():
            completa = serie_c1(parametro, valor, c2, tabla, estructura)['c1']
            parcial = serie_c1(parametro, valor, c2, tabla.iloc[:corte].reset_index(drop=True), estructura)['c1']
            assert np.array_equal(completa[:corte], parcial, equal_nan=True), f'{valor} {parametro}: la serie usa datos futuros'


def test_c1_en_la_grilla_y_el_rango():
    estructura = _estructura()
    for valor in _valores_disponibles():
        tabla = _tabla(valor)
        c2_q4 = cargar_c2_q4(EXP_Q4 / f'{valor}_q4_resumen.csv')
        for parametro, c2 in c2_q4.items():
            clave = 'PERDIDA_MAX_PCT' if parametro == 'PERDIDA_MAX' else parametro
            piso, techo = config_smart.rango(clave, valor)
            paso = config_smart.paso(clave, valor)
            c1 = serie_c1(parametro, valor, c2, tabla, estructura)['c1']
            c1 = c1[~np.isnan(c1)]
            assert len(c1) > 0
            assert c1.min() >= piso and c1.max() <= techo, f'{valor} {parametro}: fuera de [{piso}, {techo}]'
            k = (c1 - piso) / paso
            assert np.allclose(k, np.round(k), atol=1e-6), f'{valor} {parametro}: valores fuera de la grilla'


def test_variable_nueva_con_peso_cero_no_cambia_la_serie():
    estructura = _estructura()
    valor = _valores_disponibles()[0]
    tabla = _tabla(valor)
    c2 = cargar_c2_q4(EXP_Q4 / f'{valor}_q4_resumen.csv')['N']
    base = serie_c1('N', valor, c2, tabla, estructura)
    ampliada = copy.deepcopy(estructura)
    ampliada['N']['variables'].append(
        {'nombre': 'x3_rsi_14', 'transformacion': 'identidad', 'columnas': ['x3_rsi_14'], 'signo': 1, 'activa': True})
    con_x3 = serie_c1('N', valor, c2, tabla, ampliada)
    assert np.array_equal(base['c1'], con_x3['c1'], equal_nan=True)
    assert con_x3['pesos']['x3_rsi_14'] == 0


def test_variable_inactiva_se_ignora():
    estructura = _estructura()
    valor = _valores_disponibles()[0]
    tabla = _tabla(valor)
    c2 = cargar_c2_q4(EXP_Q4 / f'{valor}_q4_resumen.csv')['A']
    inactiva = copy.deepcopy(estructura)
    inactiva['A']['variables'][1]['activa'] = False
    solo_atr = {'pesos': {'x3_atr_pct': 1.0}, 'span': c2['span'], 'punto_medio': c2['punto_medio'], 'pendiente': c2['pendiente']}
    a = serie_c1('A', valor, c2, tabla, inactiva)['c1']
    b = serie_c1('A', valor, solo_atr, tabla, estructura)['c1']
    assert np.array_equal(a, b, equal_nan=True)


def test_rangos_sorteo_cerca_de_q4():
    valor = _valores_disponibles()[0]
    c2_q4 = cargar_c2_q4(EXP_Q4 / f'{valor}_q4_resumen.csv')
    r = rangos_sorteo_c2(c2_q4['N'])
    pm, pe = c2_q4['N']['punto_medio'], c2_q4['N']['pendiente']
    assert np.allclose(r['punto_medio'], (pm - 0.5, pm + 0.5))
    assert np.allclose(r['pendiente'], (pe / 2, pe * 2))
    assert r['span'] == (6, 24)
    assert np.allclose(r['pesos']['drawdown_30d'], (0.4, 0.8))
    assert np.allclose(r['pesos']['-x3_atr_pct'], (0.05, 0.4))
    assert rangos_sorteo_c2(c2_q4['K'])['pesos']['-|ruptura_rango|'] == (1.0, 1.0)


def test_pesos_se_normalizan():
    estructura = _estructura()
    valor = _valores_disponibles()[0]
    tabla = _tabla(valor).iloc[:500]
    c2 = {'pesos': {'drawdown_30d': 3, '-x3_atr_pct': 1, 'ln_razon_vol_30d': 1}, 'span': 12, 'punto_medio': 0.0, 'pendiente': 1.0}
    pesos = serie_c1('N', valor, c2, tabla, estructura)['pesos']
    assert abs(sum(pesos.values()) - 1) < 1e-12 and abs(pesos['drawdown_30d'] - 0.6) < 1e-12


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
    print(f'\n{len(pruebas) - fallos}/{len(pruebas)} pruebas pasan; valores usados: {_valores_disponibles()}')
    sys.exit(1 if fallos else 0)
