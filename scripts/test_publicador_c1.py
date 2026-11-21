"""
Pruebas de publicador_c1.py (Q5-5b: candidata -> C1 vigentes en active_parameters.json).

Sin mocks de datos: las de cadencia usan C1 sintéticos; la de punta a punta usa los datos reales (`Data/`, X2 y
`resources/x5_alt/exp_Q1` + `exp_Q4`) y se omite si faltan. Las rutas de salida se redirigen a una carpeta temporal.
Corren sin pytest:
    python scripts/test_publicador_c1.py
"""

import datetime
import json
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
import config_smart
import publicador_c1 as pub
from x5_alt_funciones import c1_dinamicos, cargar_c2_q4, cargar_estructura_c1

cfg.RUTA_REGISTRO_DIN = Path(tempfile.mkdtemp()) / 'eventos.jsonl'  # que ninguna prueba escriba en resources/
AHORA = datetime.datetime(2026, 11, 20, 10, 0, 0)
VALOR = 'BTCUSD'


def _c1_sintetico(n=400):
    indice = pd.date_range('2026-01-01', periods=n, freq='h')
    i = np.arange(n)
    return pd.DataFrame({'N': 40 + i % 100, 'K': 1.0 + 0.001 * i, 'N_EXP': 1.3, 'LAMBDA': 0.2, 'A': 3 + 0.01 * i,
                         'factor_B': 1.5, 'p': 0.05}, index=indice)


def _previo(c1, velas_atras, candidato='candidato_040'):
    return {'candidato': candidato, 'busqueda_desde': str(c1.index[-1 - velas_atras]),
            'N': 999, 'K': 9.0, 'N_EXP': 9.0, 'LAMBDA': 9.0}


def _redirigir(tmp):
    cfg.RUTA_CANDIDATAS = Path(tmp) / 'candidatas'
    cfg.RUTA_ACTIVE_PARAMETERS = Path(tmp) / 'active_parameters.json'
    cfg.RUTA_REGISTRO_DIN = Path(tmp) / 'eventos.jsonl'


def test_sin_previo_refresca_todo():
    c1 = _c1_sintetico()
    e = pub.entrada_publicada(VALOR, c1, 'candidato_040', None, AHORA)
    fila = c1.iloc[-1]
    assert e['N'] == int(fila['N']) and e['K'] == fila['K'] and e['A'] == fila['A']
    assert e['busqueda_desde'] == e['ultima_vela'] == str(c1.index[-1])
    assert e['B'] == round(fila['factor_B'] * fila['A'], 6)
    assert e['PERDIDA_MAX'] == round(fila['p'] * config_smart.CUENTA['capital_inicial'], 2)
    assert e['model_status'] == 'trained' and e['calculado_en'] == '2026-11-20T10:00:00'


def test_dentro_del_bloque_arrastra_busqueda_y_actualiza_operacion():
    c1 = _c1_sintetico()
    previo = _previo(c1, 10)
    e = pub.entrada_publicada(VALOR, c1, 'candidato_040', previo, AHORA)
    assert (e['N'], e['K'], e['N_EXP'], e['LAMBDA']) == (999, 9.0, 9.0, 9.0)
    assert e['busqueda_desde'] == previo['busqueda_desde'] and e['ultima_vela'] == str(c1.index[-1])
    assert e['A'] == c1['A'].iloc[-1] and e['p'] == c1['p'].iloc[-1]


def test_cuenta_desde_se_abre_una_vez_y_se_arrastra():
    c1 = _c1_sintetico()
    ahora_epoch = int(AHORA.timestamp())
    assert pub.entrada_publicada(VALOR, c1, 'candidato_040', None, AHORA)['cuenta_desde'] == ahora_epoch
    previo = {**_previo(c1, 10), 'cuenta_desde': 123}
    mas_tarde = AHORA + datetime.timedelta(hours=5)
    assert pub.entrada_publicada(VALOR, c1, 'candidato_040', previo, mas_tarde)['cuenta_desde'] == 123
    assert pub.entrada_publicada(VALOR, c1, 'candidato_050', previo, mas_tarde)['cuenta_desde'] == 123  # otra candidata, misma cuenta
    assert pub.entrada_publicada(VALOR, c1, 'candidato_040', _previo(c1, 10), mas_tarde)['cuenta_desde'] == int(mas_tarde.timestamp())


def test_cumplido_el_bloque_refresca():
    c1 = _c1_sintetico()
    n_velas = config_smart.N_VELAS[config_smart.tipo_valor(VALOR)]
    antes = pub.entrada_publicada(VALOR, c1, 'candidato_040', _previo(c1, n_velas - 1), AHORA)
    assert antes['N'] == 999
    en_el_limite = pub.entrada_publicada(VALOR, c1, 'candidato_040', _previo(c1, n_velas), AHORA)
    assert en_el_limite['N'] == int(c1['N'].iloc[-1]) and en_el_limite['busqueda_desde'] == str(c1.index[-1])


def test_otra_candidata_o_busqueda_desconocida_refresca():
    c1 = _c1_sintetico()
    e = pub.entrada_publicada(VALOR, c1, 'candidato_041', _previo(c1, 10), AHORA)
    assert e['N'] == int(c1['N'].iloc[-1])
    previo = _previo(c1, 10)
    previo['busqueda_desde'] = '2020-01-01 00:00:00'
    assert pub.entrada_publicada(VALOR, c1, 'candidato_040', previo, AHORA)['N'] == int(c1['N'].iloc[-1])


def test_c1_sin_dato_en_la_ultima_vela_cerrada_falla():
    c1 = _c1_sintetico()
    c1.iloc[-1, c1.columns.get_loc('A')] = np.nan
    try:
        pub.entrada_publicada(VALOR, c1, 'candidato_040', None, AHORA)
    except ValueError:
        return
    raise AssertionError('debía fallar con un C1 NaN')


def test_guardar_candidata_deja_vigente_e_historial():
    c2 = {'A': {'pesos': {'x': np.float64(0.4), 'y': 0.6}, 'span': np.int64(12), 'punto_medio': 0.1, 'pendiente': 2.0}}
    with tempfile.TemporaryDirectory() as tmp:
        _redirigir(tmp)
        pub.guardar_candidata(VALOR, 'candidato_040', c2, {'n': 6})
        pub.guardar_candidata(VALOR, 'candidato_050', c2, {'n': 6})
        vigente = pub.cargar_candidata(VALOR)
        historial = (cfg.RUTA_CANDIDATAS / f'{VALOR}_historial.jsonl').read_text().splitlines()
    assert vigente['candidato'] == 'candidato_050' and vigente['c2'] == {
        'A': {'pesos': {'x': 0.4, 'y': 0.6}, 'span': 12, 'punto_medio': 0.1, 'pendiente': 2.0}}
    assert [json.loads(h)['candidato'] for h in historial] == ['candidato_040', 'candidato_050']
    assert pub.cargar_candidata('NO_EXISTE') is None


def test_archivo_del_x5_original_se_ignora():
    with tempfile.TemporaryDirectory() as tmp:
        _redirigir(tmp)
        cfg.RUTA_ACTIVE_PARAMETERS.write_text(json.dumps({'generated_at': 'x', 'BTCUSD': {'model_status': 'untrained'}}))
        assert pub.cargar_publicado() == {}


def test_publicar_punta_a_punta_reproduce_los_c1_del_backtest():
    tabla_q1 = cfg.CARPETA_X5_ALT / 'exp_Q1' / f'{VALOR}_tabla_estado_v2.csv'
    q4 = cfg.CARPETA_X5_ALT / 'exp_Q4' / f'{VALOR}_q4_resumen.csv'
    if not (tabla_q1.exists() and q4.exists() and (cfg.CARPETA_DATA / f'{VALOR}.csv').exists()):
        print('  (omitida: faltan datos de BTCUSD)')
        return
    c2 = {c1: {k: v for k, v in c.items() if k != 'mu_sigma'} for c1, c in cargar_c2_q4(q4).items()}
    with tempfile.TemporaryDirectory() as tmp:
        _redirigir(tmp)
        pub.guardar_candidata(VALOR, 'q4', c2, {})
        publicado = pub.publicar([VALOR, 'ETHUSD_SIN_CANDIDATA'], AHORA)
        archivo = json.loads(cfg.RUTA_ACTIVE_PARAMETERS.read_text())
        segunda = pub.publicar([VALOR], AHORA + datetime.timedelta(hours=1))
        eventos = [json.loads(linea) for linea in cfg.RUTA_REGISTRO_DIN.read_text(encoding='utf-8').splitlines()]
    assert archivo['esquema'] == 'q5' and list(archivo['valores']) == [VALOR]
    e = publicado[VALOR]
    assert all(np.isfinite(e[k]) for k in ('N', 'K', 'N_EXP', 'LAMBDA', 'A', 'B', 'p', 'PERDIDA_MAX'))
    # segunda pasada con los mismos datos: la búsqueda se arrastra (no pasaron N_VELAS velas)
    assert segunda[VALOR]['busqueda_desde'] == e['busqueda_desde']
    assert [(x['evento'], x['valor'], x.get('busqueda_refrescada')) for x in eventos] == [
        ('publicado', VALOR, True), ('sin_candidata', 'ETHUSD_SIN_CANDIDATA', None), ('publicado', VALOR, False)]
    assert eventos[0]['N'] == e['N'] and eventos[0]['candidato'] == 'q4'

    # los C1 que arma el publicador desde Data/ coinciden con los del backtest (tabla de Q1) en las velas comunes;
    # tolerancia mínima: dos fuentes con ruido de ~1e-10 pueden caer a lados distintos de un paso de la grilla
    tabla = pd.read_csv(tabla_q1, parse_dates=['DateTime'])
    c1_bt = c1_dinamicos(VALOR, c2, tabla, cargar_estructura_c1(cfg.RUTA_ESTRUCTURA_C1))
    c1_pub = pub.c1_vela_cerrada(VALOR, c2)
    comunes = c1_pub.index.intersection(c1_bt.index[:-1])[-3000:]
    assert len(comunes) > 1000, f'solo {len(comunes)} velas comunes'
    iguales = np.isclose(c1_pub.loc[comunes].to_numpy(float), c1_bt.loc[comunes].to_numpy(float), rtol=1e-6)
    assert iguales.mean() > 0.999, f'solo {iguales.mean():.4f} de los C1 coinciden con el backtest'


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
