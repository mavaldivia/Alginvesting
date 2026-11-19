"""
Pruebas de X4_bckt_ventanas.py (orden de bisección y selección de t*, reservadas, visitas, solape con reservadas,
sorteo Sobol de los C2, ventana con cuenta limpia y reproducible, visita reservada, réplicas y visita a medias).

Las que corren ventanas usan datos reales de BTCUSD (Data/, Data_minuto/ y exp_Q1/exp_Q4 de Q1/Q4), sin mocks de datos
ni de la búsqueda de soportes. Las ventanas con C1 estáticos usan N = 20 para que la búsqueda converja en segundos y no la
corte el tope de tiempo (si lo hiciera, el resultado dependería del reloj y no sería reproducible); las de Q4 y Sobol
no pueden bajar N, así que usan un tope corto y solo se prueba que se registren, no que sean reproducibles.
Todo lo que escriben va a un directorio temporal (`CARPETA_Q5` se redirige), nunca a resources/x5_alt/q5.
Sin pytest:
    python scripts/test_x4_bckt_ventanas.py
"""

import contextlib
import io
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as gc
import config_smart
import X4_bckt_ventanas as v
import X4S_backtesting_inteligente as s

VALOR = 'BTCUSD'
TOPE_CORTO_MIN = 0.1


def _hay_datos() -> bool:
    return ((gc.CARPETA_DATA / f'{VALOR}.csv').exists() and (gc.CARPETA_DATA_MINUTO / f'{VALOR}.csv').exists()
            and (gc.CARPETA_X5_ALT / 'exp_Q1' / f'{VALOR}_tabla_estado_v2.csv').exists()
            and (gc.CARPETA_X5_ALT / 'exp_Q4' / f'{VALOR}_q4_resumen.csv').exists())


@contextlib.contextmanager
def _q5_temporal():
    original = gc.CARPETA_Q5
    tmp = Path(tempfile.mkdtemp()).resolve()
    gc.CARPETA_Q5 = tmp / 'q5'
    try:
        yield gc.CARPETA_Q5
    finally:
        gc.CARPETA_Q5 = original
        shutil.rmtree(tmp, ignore_errors=True)


@contextlib.contextmanager
def _config(**cambios):
    """Cambia atributos de `config_smart` y de `config` (n_sizes_ejecucion) durante la prueba: `tope` en minutos y `n`."""
    original = (config_smart.TIEMPO_MAX_BUSQUEDA_VENTANA_MIN, dict(gc.n_sizes_ejecucion))
    if 'tope' in cambios:
        config_smart.TIEMPO_MAX_BUSQUEDA_VENTANA_MIN = cambios['tope']
    if 'n' in cambios:
        gc.n_sizes_ejecucion[VALOR] = cambios['n']
    try:
        yield
    finally:
        config_smart.TIEMPO_MAX_BUSQUEDA_VENTANA_MIN = original[0]
        gc.n_sizes_ejecucion.clear()
        gc.n_sizes_ejecucion.update(original[1])


def _insumos():
    datos = v.cargar_datos(VALOR)
    tabla, estructura, c2_q4 = s.cargar_insumos(VALOR)
    return datos, tabla, estructura, c2_q4


def _t_con_reserva(datos, reservada: bool, desde: int = 0) -> int:
    return next(t for t in range(desde, desde + 500) if v.es_reservada(VALOR, datos['h1'].index[t]) == reservada)


def _c2_base_de_prueba() -> dict:
    return {
        'N': {'pesos': {'a': 0.6, 'b': 0.4, 'c': 0.0}, 'span': 12, 'punto_medio': 0.2, 'pendiente': 1.5},
        'K': {'pesos': {'d': 1.0}, 'span': 8, 'punto_medio': -0.1, 'pendiente': 0.8},
    }


# ─── Sin datos: selección de t*, reservadas, visitas y Sobol ──────────────────

def test_orden_biseccion_extremos_punto_medio_y_luego_los_medios():
    assert v.orden_biseccion(1000)[:9] == [0, 1000, 500, 250, 750, 125, 375, 625, 875]
    assert v.orden_biseccion(0) == [0]
    assert v.orden_biseccion(1) == [0, 1]


def test_orden_biseccion_cubre_cada_t_una_sola_vez():
    for T in (2, 7, 100, 1001):
        orden = v.orden_biseccion(T)
        assert sorted(orden) == list(range(T + 1)), T


def test_elegir_t_star_siempre_toma_un_minimo_de_visitas():
    T, visitas = 20, {}
    for _ in range(3 * (T + 1)):
        t = v.elegir_t_star(visitas, T)
        cuenta = [visitas.get(x, 0) for x in range(T + 1)]
        assert visitas.get(t, 0) == min(cuenta)
        visitas[t] = visitas.get(t, 0) + 1
    assert all(visitas[t] == 3 for t in range(T + 1))


def test_elegir_t_star_primera_ronda_sigue_la_biseccion():
    T, visitas, elegidos = 1000, {}, []
    for _ in range(9):
        t = v.elegir_t_star(visitas, T)
        visitas[t] = 1
        elegidos.append(t)
    assert elegidos == [0, 1000, 500, 250, 750, 125, 375, 625, 875]


def test_datos_nuevos_entran_antes_de_repetir_ningun_t():
    visitas = {t: 1 for t in range(21)}  # T = 20 ya visitado completo una vez
    elegidos = []
    for _ in range(5):
        t = v.elegir_t_star(visitas, 25)
        visitas[t] = visitas.get(t, 0) + 1
        elegidos.append(t)
    assert sorted(elegidos) == [21, 22, 23, 24, 25]
    assert elegidos == [25, 21, 23, 22, 24]  # el extremo nuevo primero y luego el tramo nuevo en orden de bisección


def test_elegir_t_star_prefiere_la_visita_a_medias_entre_los_de_minimo():
    visitas = {0: 1, 1000: 1}  # mínimo 0 en el resto; el primero en bisección sería 500
    assert v.elegir_t_star(visitas, 1000) == 500
    assert v.elegir_t_star(visitas, 1000, preferidos={375}) == 375
    assert v.elegir_t_star(visitas, 1000, preferidos={0}) == 500  # 0 no está en el mínimo: no se prefiere


def test_reservadas_son_el_20_por_ciento_y_estables():
    idx = pd.date_range('2022-03-01', periods=5000, freq='h')
    marcas = [v.es_reservada(VALOR, ts) for ts in idx]
    assert abs(np.mean(marcas) - config_smart.FRACCION_RESERVADA) < 0.03
    assert marcas == [v.es_reservada(VALOR, ts) for ts in idx]
    assert marcas != [v.es_reservada('ETHUSD', ts) for ts in idx]
    assert marcas != [v.es_reservada(VALOR, ts, semilla=1) for ts in idx]


def test_t_maximo_crypto_y_accion():
    idx = pd.date_range('2022-03-01', periods=1000 + 169, freq='h')  # 169 velas: t = 1000 es la última con 168 velas después
    assert v.t_maximo(idx) == 1000
    # acción: velas H1 solo de lunes a viernes 10-15; la semana completa de t exige una vela en o después de t + 7 días
    dias = pd.bdate_range('2022-03-07', periods=15)
    idx = pd.DatetimeIndex([d + pd.Timedelta(hours=h) for d in dias for h in range(10, 16)])
    T = v.t_maximo(idx)
    assert idx[T] + pd.Timedelta(days=config_smart.VENTANA_DIAS) <= idx[-1]
    assert idx[T + 1] + pd.Timedelta(days=config_smart.VENTANA_DIAS) > idx[-1]


def test_contar_visitas_completas_y_a_medias():
    idx = pd.date_range('2022-03-01', periods=50, freq='h')
    filas = [
        {'ts_star': idx[3], 'ronda': 1, 'tramo': 'reservada', 'fase': 'estatica'},
        {'ts_star': idx[3], 'ronda': 1, 'tramo': 'reservada', 'fase': 'q4'},
        {'ts_star': idx[3], 'ronda': 2, 'tramo': 'reservada', 'fase': 'estatica'},   # a medias
        {'ts_star': idx[7], 'ronda': 1, 'tramo': 'aprendizaje', 'fase': 'sobol'},
        {'ts_star': idx[9], 'ronda': 1, 'tramo': 'reservada', 'fase': 'q4'},          # a medias
        {'ts_star': pd.Timestamp('2030-01-01'), 'ronda': 1, 'tramo': 'aprendizaje', 'fase': 'sobol'},  # fuera de los datos
    ]
    visitas, parciales = v.contar_visitas(pd.DataFrame(filas), idx)
    assert visitas == {3: 1, 7: 1}
    assert parciales == {3: (2, {'estatica'}), 9: (1, {'q4'})}
    assert v.contar_visitas(pd.DataFrame(columns=v.COLUMNAS_REGISTRO), idx) == ({}, {})


def test_ventanas_de_aprendizaje_excluye_las_que_se_solapan_con_una_reservada():
    base = pd.Timestamp('2022-03-01')
    dia = pd.Timedelta(days=1)
    filas = [
        {'id': 'res', 'ts_star': base + 20 * dia, 'tramo': 'reservada'},
        {'id': 'res_q4', 'ts_star': base + 20 * dia, 'tramo': 'reservada'},
        {'id': 'cerca_antes', 'ts_star': base + 14 * dia, 'tramo': 'aprendizaje'},          # 6 días antes: se solapa
        {'id': 'justo_7_antes', 'ts_star': base + 13 * dia, 'tramo': 'aprendizaje'},       # 7 días: no hay velas en común
        {'id': 'cerca_despues', 'ts_star': base + 26 * dia + pd.Timedelta(hours=23), 'tramo': 'aprendizaje'},
        {'id': 'justo_7_despues', 'ts_star': base + 27 * dia, 'tramo': 'aprendizaje'},
        {'id': 'lejos', 'ts_star': base + 60 * dia, 'tramo': 'aprendizaje'},
    ]
    ok = v.ventanas_de_aprendizaje(pd.DataFrame(filas))
    assert set(ok['id']) == {'justo_7_antes', 'justo_7_despues', 'lejos'}
    sin_reservadas = pd.DataFrame(filas[2:])
    assert len(v.ventanas_de_aprendizaje(sin_reservadas)) == 5


def test_punto_sobol_es_reproducible_por_indice_y_distinto_entre_indices():
    a, b = v.punto_sobol(6, 3), v.punto_sobol(6, 3)
    assert np.array_equal(a, b) and a.shape == (6,)
    assert ((a >= 0) & (a < 1)).all()
    assert not np.array_equal(a, v.punto_sobol(6, 4))
    assert not np.array_equal(a, v.punto_sobol(6, 3, semilla=7))


def test_sortear_c2_respeta_rangos_y_fija_lo_que_no_se_sortea():
    base = _c2_base_de_prueba()
    rangos, libres = v._dimensiones(base)
    # N: 2 pesos con peso base > 0, span, punto_medio, pendiente; K: una sola variable (peso fijo), span, punto_medio, pendiente
    assert len(libres) == 5 + 3
    for k in range(8):
        c2 = v.sortear_c2(base, k)
        for c1 in base:
            r = rangos[c1]
            assert isinstance(c2[c1]['span'], int) and r['span'][0] <= c2[c1]['span'] <= r['span'][1]
            assert r['punto_medio'][0] <= c2[c1]['punto_medio'] <= r['punto_medio'][1]
            assert r['pendiente'][0] <= c2[c1]['pendiente'] <= r['pendiente'][1]
            for nombre, (lo, hi) in r['pesos'].items():
                assert lo <= c2[c1]['pesos'][nombre] <= hi
        assert c2['N']['pesos']['c'] == 0.0 and c2['K']['pesos']['d'] == 1.0
    assert v.sortear_c2(base, 2) == v.sortear_c2(base, 2)
    assert v.sortear_c2(base, 2) != v.sortear_c2(base, 3)


# ─── Con datos: una ventana ───────────────────────────────────────────────────

def _c1_n20(tabla) -> pd.DataFrame:
    c1 = s.c1_estaticos(VALOR, pd.DatetimeIndex(tabla['DateTime']))
    c1['N'] = 20
    return c1


def _ventana(datos, c1, t_star: int, semilla: int, nombre: str = 'test') -> dict:
    with _q5_temporal() as q5, contextlib.redirect_stdout(io.StringIO()):
        carpeta = q5 / 'ventanas' / VALOR / nombre
        s.preparar_carpeta(carpeta, True)
        return v.ejecutar_ventana(VALOR, t_star, c1, carpeta, semilla, datos, nombre)


def test_ventana_cuenta_limpia_semana_completa_y_label():
    if not _hay_datos():
        return
    datos, tabla, _, _ = _insumos()
    c1 = _c1_n20(tabla)
    res = _ventana(datos, c1, 100, semilla=5)
    h1 = datos['h1']
    assert len(res['equity']) == 168 and res['indice'][0] == h1.index[101] and res['indice'][-1] == h1.index[268]
    assert not np.isnan(res['equity']).any()
    assert abs(res['Y'] - (res['equity'][-1] - config_smart.CUENTA['capital_inicial'])) < 1e-9
    assert abs(res['Y'] - (res['cerrado'] + res['pnl_abierto'])) < 1e-9
    cierres = h1['Close'].iloc[100:269].to_numpy()
    r = cierres[1:] / cierres[:-1] - 1
    assert abs(res['ret_medio'] - r.mean()) < 1e-12 and abs(res['ret_vol'] - r.std(ddof=1)) < 1e-12
    assert res['c1_busqueda'] == {'N': 20.0, 'K': gc.K, 'N_EXP': gc.N_EXP, 'LAMBDA': gc.LAMBDA}
    # sin órdenes heredadas: antes de que se ejecute la primera OE el equity es el capital inicial
    primera_oa = int(np.argmax(res['en_mercado'])) if res['en_mercado'].any() else len(res['equity'])
    assert (res['equity'][:primera_oa] == config_smart.CUENTA['capital_inicial']).all()


def test_ventana_misma_semilla_mismo_y_y_otra_semilla_puede_cambiarlo():
    if not _hay_datos():
        return
    datos, tabla, _, _ = _insumos()
    c1 = _c1_n20(tabla)
    a, b = _ventana(datos, c1, 0, semilla=5), _ventana(datos, c1, 0, semilla=5)
    assert a['Y'] == b['Y'] and np.array_equal(a['equity'], b['equity'])
    assert a['retornos_trades'] == b['retornos_trades']


def test_ventana_sin_cobertura_de_c1_falla_antes_de_buscar():
    if not _hay_datos():
        return
    datos, tabla, _, _ = _insumos()
    c1 = _c1_n20(tabla)
    c1.loc[c1.index >= datos['h1'].index[150], 'A'] = np.nan
    try:
        _ventana(datos, c1, 100, semilla=5)
    except ValueError as e:
        assert 'no la cubre' in str(e)
    else:
        raise AssertionError('debió rechazar la ventana sin C1')


def test_tope_de_busqueda_de_la_ventana_llega_a_x4():
    if not _hay_datos():
        return
    datos, tabla, _, _ = _insumos()
    c1 = _c1_n20(tabla)
    capturado = {}
    original = s.x4._recalcular_soportes

    def espia(estado, ts, cfg, x5_mode=False):
        capturado['tope'] = cfg.TIEMPO_MAX_BUSQUEDA_MIN
        capturado['warm'] = cfg.X5_WARM_START_SOPORTES
        return original(estado, ts, cfg, x5_mode)

    s.x4._recalcular_soportes = espia
    try:
        with _config(tope=0.5):
            _ventana(datos, c1, 0, semilla=5)
    finally:
        s.x4._recalcular_soportes = original
    assert capturado == {'tope': 0.5, 'warm': False}


# ─── Con datos: visitas, réplicas y reanudación ───────────────────────────────

def test_visita_reservada_registra_estatica_y_q4_y_la_ronda_2_es_replica():
    if not _hay_datos():
        return
    datos, tabla, estructura, c2_q4 = _insumos()
    t = _t_con_reserva(datos, True)
    with _q5_temporal() as q5, contextlib.redirect_stdout(io.StringIO()), _config(tope=TOPE_CORTO_MIN, n=20):
        v.correr_visita(VALOR, t, datos, tabla, estructura, c2_q4, semilla_base=3)
        df = v.leer_registro(VALOR)
        assert list(df['fase']) == ['estatica', 'q4'] and set(df['tramo']) == {'reservada'}
        assert set(df['ronda']) == {1} and set(df['t_star']) == {t} and (df['replica_de'].fillna('') == '').all()
        assert df['semilla'].nunique() == 1  # las dos configuraciones comparten semilla: control pareado
        assert v.contar_visitas(df, datos['h1'].index) == ({t: 1}, {})
        assert not df[['Y', 'ret_medio', 'ret_vol', 'duracion_min']].isna().all().any()
        assert {'sin_trades', 'stop_outs', 'n_trades', 'drawdown_max_usd', 'c1_N', 'c1_A_media'} <= set(df.columns)

        v.correr_visita(VALOR, t, datos, tabla, estructura, c2_q4, semilla_base=3)
        df = v.leer_registro(VALOR)
        r2 = df[df['ronda'] == 2]
        assert list(r2['fase']) == ['estatica', 'q4']
        assert list(r2['replica_de']) == [f'{VALOR}_t{t:06d}_r1_estatica', f'{VALOR}_t{t:06d}_r1_q4']
        assert (r2['semilla'] == 4).all()
        assert (q5 / 'ventanas' / VALOR / f'{VALOR}_t{t:06d}_r1_q4' / 'x4.log').exists()


def test_visita_a_medias_solo_corre_lo_que_falta():
    if not _hay_datos():
        return
    datos, tabla, estructura, c2_q4 = _insumos()
    t = _t_con_reserva(datos, True, desde=40)
    with _q5_temporal(), contextlib.redirect_stdout(io.StringIO()), _config(tope=TOPE_CORTO_MIN, n=20):
        v.correr_visita(VALOR, t, datos, tabla, estructura, c2_q4, semilla_base=0)
        df = v.leer_registro(VALOR)
        df[df['fase'] != 'q4'].to_csv(v.ruta_ventanas(VALOR), index=False)  # como si se hubiera interrumpido tras la estática
        visitas, parciales = v.contar_visitas(v.leer_registro(VALOR), datos['h1'].index)
        assert visitas == {} and parciales == {t: (1, {'estatica'})}
        assert v.elegir_t_star(visitas, 1000, preferidos=parciales) == t
        filas = v.correr_visita(VALOR, t, datos, tabla, estructura, c2_q4, semilla_base=0)
        assert [f['fase'] for f in filas] == ['q4']
        assert v.contar_visitas(v.leer_registro(VALOR), datos['h1'].index) == ({t: 1}, {})


def test_visita_de_aprendizaje_usa_sobol_con_indice_creciente_y_registra_c2():
    if not _hay_datos():
        return
    datos, tabla, estructura, c2_q4 = _insumos()
    t1, t2 = _t_con_reserva(datos, False), _t_con_reserva(datos, False, desde=60)
    with _q5_temporal(), contextlib.redirect_stdout(io.StringIO()), _config(tope=TOPE_CORTO_MIN):
        f1 = v.correr_visita(VALOR, t1, datos, tabla, estructura, c2_q4, semilla_base=0)
        f2 = v.correr_visita(VALOR, t2, datos, tabla, estructura, c2_q4, semilla_base=0)
        assert [f['fase'] for f in f1 + f2] == ['sobol', 'sobol'] and f1[0]['tramo'] == 'aprendizaje'
        esperado = [v.sortear_c2(c2_q4, k) for k in (0, 1)]
        for fila, c2 in zip(f1 + f2, esperado):
            for c1_nombre, c in c2.items():
                assert fila[f'c2_{c1_nombre}_span'] == c['span']
                assert abs(fila[f'c2_{c1_nombre}_punto_medio'] - c['punto_medio']) < 1e-12
        assert f1[0]['c2_N_span'] != f2[0]['c2_N_span'] or f1[0]['c2_N_punto_medio'] != f2[0]['c2_N_punto_medio']


def test_correr_con_t_star_solo_visita_esos_y_termina():
    if not _hay_datos():
        return
    datos, _, _, _ = _insumos()
    t = _t_con_reserva(datos, False, desde=80)
    with _q5_temporal(), contextlib.redirect_stdout(io.StringIO()), _config(tope=TOPE_CORTO_MIN):
        n = v.correr(VALOR, t_stars=[t])
        df = v.leer_registro(VALOR)
        assert n == 1 and list(df['t_star']) == [t]


def test_correr_con_max_ventanas_sigue_la_biseccion():
    if not _hay_datos():
        return
    with _q5_temporal(), contextlib.redirect_stdout(io.StringIO()), _config(tope=TOPE_CORTO_MIN, n=20):
        n = v.correr(VALOR, max_ventanas=2)
        df = v.leer_registro(VALOR)
        T = v.t_maximo(v._insumos_vigentes(VALOR, None)[0]['h1'].index)
        assert n >= 2
        assert df['t_star'].iloc[0] == 0 and T >= df['t_star'].max()
        assert set(df['t_star']) <= {0, T}


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
    print(f'\n{len(pruebas) - fallos}/{len(pruebas)} pruebas pasan; datos disponibles: {_hay_datos()}')
    sys.exit(1 if fallos else 0)
