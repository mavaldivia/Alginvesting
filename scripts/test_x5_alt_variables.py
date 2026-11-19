"""
Pruebas de x5_alt_variables.py (variables de estado de Q1 como módulo).

Usan los datos reales (Data/{valor}.csv y resources/x5_alt/exp_Q1), sin mocks; el activo al que le falten esos
archivos se omite. Dos propiedades:
  - reproduce la tabla que dejó X5_Q1.ipynb (`{valor}_tabla_estado_v2.csv`) en las velas que ambas cubren;
  - es causal: recortar las velas posteriores a `t` no cambia las filas hasta `t` (si no, la candidata filtraría
    futuro en vivo).
Corren sin pytest:
    python scripts/test_x5_alt_variables.py
"""

import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
from x5_alt_variables import armar_tabla_base, cargar_precio, cargar_registros_x2, construir_tabla_estado

EXP_Q1 = cfg.CARPETA_X5_ALT / 'exp_Q1'

# columnas que dependen del historial de X2 (hoy en el Mac cubre menos que el de Windows, con el que se corrió Q1)
COLS_X2 = {
    'x2_score', 'x2_score_cross', 'x2_score_tendencia', 'fundamental_cambio', 'fundamental_direccion_cambio',
    'fundamental_magnitud_cambio', 'fundamental_edad', 'fundamental_frecuencia_efectiva_90d',
    'fundamental_estabilidad_90d', 'fundamental_contradiccion',
}
VELAS_CAUSALIDAD = 6000  # las últimas; basta para cubrir las ventanas de hasta 90 días (2160 velas)


def _valores_disponibles():
    return [v for v in cfg.VALORES
            if (EXP_Q1 / f'{v}_tabla_estado_v2.csv').exists() and (cfg.CARPETA_DATA / f'{v}.csv').exists()]


def _tabla_q1(valor):
    return pd.read_csv(EXP_Q1 / f'{valor}_tabla_estado_v2.csv', parse_dates=['DateTime'])


def _registros_sinteticos(df_precio, cada_velas=200):
    # Un score nuevo cada `cada_velas` velas (tocan todas las columnas de X2 sin depender del historial real)
    fechas = df_precio['DateTime'].iloc[::cada_velas]
    return [{'date': str(f.date()), 'activo': 'X', 'score': 0.3 + 0.4 * ((i * 7) % 10) / 10,
             'score_cross': 0.2 + 0.5 * ((i * 3) % 10) / 10, 'score_tendencia': 0.1 + 0.6 * ((i * 9) % 10) / 10}
            for i, f in enumerate(fechas)]


def _serie_igual(a, b):
    if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
        # El MACD (ewm recursivo sobre ~42k velas) difiere ~1e-10 entre Windows y Mac por redondeo, no por lógica
        return np.allclose(a.to_numpy(float), b.to_numpy(float), rtol=1e-6, atol=1e-8, equal_nan=True)
    return bool(a.astype(object).where(a.notna(), 'NA').eq(b.astype(object).where(b.notna(), 'NA')).all())


def _columnas_distintas(a, b, columnas):
    return [c for c in columnas if not _serie_igual(a[c], b[c])]


def test_reproduce_tabla_de_q1():
    usados = 0
    for valor in _valores_disponibles():
        q1 = _tabla_q1(valor).set_index('DateTime')
        # Mismo punto de partida que Q1: drawdown_historico y la volatilidad expanding dependen de dónde parte la serie
        precio = cargar_precio(valor)
        precio = precio[precio['DateTime'] >= q1.index.min()].reset_index(drop=True)
        registros = cargar_registros_x2(valor)
        tabla = construir_tabla_estado(armar_tabla_base(precio, registros)).set_index('DateTime')

        assert list(tabla.columns) == list(q1.columns), f'{valor}: columnas u orden distintos a exp_Q1'
        # La última vela de cada lado puede haberse descargado a medio formar (en Q1 o en el Data local)
        comunes = tabla.index[:-1].intersection(q1.index[:-1])
        assert len(comunes) > 1000, f'{valor}: solo {len(comunes)} velas en común con exp_Q1'
        a, b = tabla.loc[comunes], q1.loc[comunes]
        columnas = list(q1.columns)
        if not _serie_igual(a['x2_score'], b['x2_score']):
            columnas = [c for c in columnas if c not in COLS_X2]
            print(f'  ({valor}: el historial de X2 local no coincide con el de Q1; se omiten {len(COLS_X2)} columnas de X2)')
        distintas = _columnas_distintas(a, b, columnas)
        assert not distintas, f'{valor}: difieren de exp_Q1 {distintas}'
        usados += 1
    assert usados, 'sin activos con Data y exp_Q1 en este equipo'


def test_causalidad_con_x2_sintetico():
    for valor in _valores_disponibles():
        precio = cargar_precio(valor).iloc[-VELAS_CAUSALIDAD:].reset_index(drop=True)
        registros = _registros_sinteticos(precio)
        completa = construir_tabla_estado(armar_tabla_base(precio, registros))
        for recorte in (1, 500, 2500):
            cortada = construir_tabla_estado(armar_tabla_base(precio.iloc[:-recorte].reset_index(drop=True), registros))
            assert len(cortada) == len(completa) - recorte
            distintas = _columnas_distintas(completa.iloc[:len(cortada)], cortada, completa.columns)
            assert not distintas, f'{valor}: recortar {recorte} velas cambia {distintas}'


def test_causalidad_con_x2_real():
    for valor in _valores_disponibles():
        registros = cargar_registros_x2(valor)
        precio = cargar_precio(valor).iloc[-VELAS_CAUSALIDAD:].reset_index(drop=True)
        completa = construir_tabla_estado(armar_tabla_base(precio, registros))
        cortada = construir_tabla_estado(armar_tabla_base(precio.iloc[:-500].reset_index(drop=True), registros))
        distintas = _columnas_distintas(completa.iloc[:len(cortada)], cortada, completa.columns)
        assert not distintas, f'{valor}: recortar 500 velas cambia {distintas}'


def test_activo_sin_registros_de_x2():
    valor = _valores_disponibles()[0]
    precio = cargar_precio(valor).iloc[-3000:].reset_index(drop=True)
    tabla = construir_tabla_estado(armar_tabla_base(precio, []))
    assert tabla['x2_score'].isna().all() and tabla['fundamental_contradiccion'].isna().all()
    assert tabla['drawdown_historico'].notna().all()


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
