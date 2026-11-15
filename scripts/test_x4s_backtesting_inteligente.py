"""
Pruebas de X4S_backtesting_inteligente.py (cuenta, lote por Z, cadencias, stop-out, reproducibilidad, premios,
registro, poda de curvas y versiones de estructura).

Las que corren vueltas usan vueltas cortas reales de BTCUSD (Data/, Data_minuto/ y exp_Q1/exp_Q4 de Q1/Q4), sin mocks
de datos ni de la búsqueda de soportes, con N = 20 para que cada búsqueda converja en segundos y no la corte el tope
de tiempo (si lo hiciera, el resultado dependería del reloj y no sería reproducible). Si faltan los datos se omiten.
Todo lo que escriben va a un directorio temporal (`CARPETA_Q5` se redirige), nunca a resources/x5_alt/q5.
Sin pytest:
    python scripts/test_x4s_backtesting_inteligente.py
"""

import contextlib
import copy
import io
import json
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
import X4S_backtesting_inteligente as s
from x5_alt_funciones import lotajes_m

VALOR = 'BTCUSD'
HASTA = '2022-03-04'


def _hay_datos() -> bool:
    return ((gc.CARPETA_DATA / f'{VALOR}.csv').exists() and (gc.CARPETA_DATA_MINUTO / f'{VALOR}.csv').exists()
            and (gc.CARPETA_X5_ALT / 'exp_Q1' / f'{VALOR}_tabla_estado_v2.csv').exists())


def _c1_n20() -> pd.DataFrame:
    tabla, _, _ = s.cargar_insumos(VALOR)
    c1 = s.c1_estaticos(VALOR, pd.DatetimeIndex(tabla['DateTime']))
    c1['N'] = 20
    return c1


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


def _vuelta(c1: pd.DataFrame, semilla: int = 5, hasta=HASTA, nombre: str = 'test') -> dict:
    with _q5_temporal() as q5, contextlib.redirect_stdout(io.StringIO()):
        carpeta = q5 / VALOR / nombre
        s.preparar_carpeta(carpeta, True)
        return s.ejecutar_vuelta(VALOR, c1, carpeta, semilla, hasta)


@contextlib.contextmanager
def _cuenta(**cambios):
    original = dict(config_smart.CUENTA)
    config_smart.CUENTA.update(cambios)
    try:
        yield
    finally:
        config_smart.CUENTA.clear()
        config_smart.CUENTA.update(original)


@contextlib.contextmanager
def _n_velas(n: int):
    tipo = config_smart.tipo_valor(VALOR)
    original = config_smart.N_VELAS[tipo]
    config_smart.N_VELAS[tipo] = n
    try:
        yield
    finally:
        config_smart.N_VELAS[tipo] = original


class _Interrumpido(Exception):
    pass


def _estructura_de_prueba() -> dict:
    return {
        'N': {'version': 1, 'variables': [{'nombre': 'a', 'transformacion': 'identidad', 'columnas': ['a'], 'signo': 1, 'activa': True}]},
        'K': {'version': 1, 'variables': [{'nombre': 'b', 'transformacion': 'identidad', 'columnas': ['b'], 'signo': 1, 'activa': True}]},
    }


# ─── Sin datos: matemática, registro y formato ────────────────────────────────

def test_c1_operacion_usa_la_vela_anterior():
    idx = pd.date_range('2022-03-01', periods=6, freq='h')
    c1 = pd.DataFrame({'A': range(6), 'factor_B': np.arange(6) / 10, 'p': np.arange(6) / 100, 'N': 1}, index=idx)
    op = s.c1_operacion(c1)
    assert list(op.columns) == ['A', 'factor_B', 'p']
    assert op.iloc[0].tolist() == c1[['A', 'factor_B', 'p']].iloc[0].tolist()
    assert op.iloc[5].tolist() == c1[['A', 'factor_B', 'p']].iloc[4].tolist()


def test_agregar_fila_csv_con_columnas_nuevas():
    with _q5_temporal() as q5:
        ruta = q5 / 'x.csv'
        s.agregar_fila_csv(ruta, {'id': 'a', 'c2_N_w_x': 0.5, 'premio': 1.0})
        s.agregar_fila_csv(ruta, {'id': 'b', 'c2_N_w_x': 0.4, 'premio': 2.0})
        s.agregar_fila_csv(ruta, {'id': 'c', 'c2_N_w_x': 0.3, 'c2_N_w_nueva': 0.2, 'premio': 3.0})
        df = pd.read_csv(ruta)
    assert df['id'].tolist() == ['a', 'b', 'c']
    assert df['c2_N_w_nueva'].tolist() == [0.0, 0.0, 0.2]  # las filas viejas valen 0 en la variable nueva
    assert df['premio'].tolist() == [1.0, 2.0, 3.0]


def test_version_estructura_se_archiva_sin_sobrescribir():
    with _q5_temporal() as q5:
        est = _estructura_de_prueba()
        assert s.registrar_version_estructura(VALOR, est) == 1
        assert s.registrar_version_estructura(VALOR, est) == 1  # misma combinación de versiones: mismo número

        con_variable_nueva = copy.deepcopy(est)
        con_variable_nueva['N']['variables'].append(
            {'nombre': 'c', 'transformacion': 'identidad', 'columnas': ['c'], 'signo': 1, 'activa': True})
        assert s.registrar_version_estructura(VALOR, con_variable_nueva) == 1  # agregar una variable no es versión nueva

        redefinida = copy.deepcopy(est)
        redefinida['K']['version'] = 2
        assert s.registrar_version_estructura(VALOR, redefinida) == 2
        assert s.registrar_version_estructura(VALOR, est) == 1  # volver a la anterior reutiliza su número
        assert sorted(p.name for p in q5.glob('*_estructura_v*.json')) == [f'{VALOR}_estructura_v1.json', f'{VALOR}_estructura_v2.json']
        v1 = json.loads((q5 / f'{VALOR}_estructura_v1.json').read_text(encoding='utf-8'))
        assert v1['versiones'] == {'N': 1, 'K': 1} and len(v1['estructura']['N']['variables']) == 1  # v1 quedó como se archivó


def test_poda_conserva_la_estatica_y_las_mejores_por_premio_de_aprendizaje():
    with _q5_temporal() as q5:
        filas = [('est', 'estatica', 0.01, 0.9), ('a', 'q4', 0.05, 0.0), ('b', 'q4', 0.09, 0.0),
                 ('c', 'q4', 0.02, 0.99), ('d', 'q4', 0.07, 0.0)]  # el premio reservado de 'c' es el mayor y no cuenta
        for id_, fase, p_apr, p_res in filas:
            s.agregar_fila_csv(q5 / f'{VALOR}_vueltas.csv',
                               {'id': id_, 'fase': fase, 'premio_aprendizaje': p_apr, 'premio_reservado': p_res})
            carpeta = q5 / VALOR / id_
            carpeta.mkdir(parents=True)
            for nombre in (*s.CURVAS_EQUITY, 'trades.json'):
                (carpeta / nombre).write_text('x')
        podadas = s.podar_curvas(VALOR, mejores=2)
        assert sorted(podadas) == ['a', 'c']
        assert not (q5 / VALOR / 'a' / 'equity_global.csv').exists()
        assert (q5 / VALOR / 'b' / 'equity_global.csv').exists() and (q5 / VALOR / 'd' / 'equity_activos.csv').exists()
        assert (q5 / VALOR / 'est' / 'equity_global.csv').exists()
        assert (q5 / VALOR / 'a' / 'trades.json').exists()  # solo se borran las curvas de equity


def test_resumen_en_pantalla_lleva_prefijo_en_todas_las_lineas():
    fila = {
        'vuelta': 'q4_s0', 'valor': VALOR, 'bloque': 37, 'bloques_total': 250, 'tramo': 'aprendizaje',
        'ts': '2024-03-04 08:00:00', 'pct_velas': 14.8, 'eta_s': 4800, 'status': 'normal', 'margin_level': 412.0,
        'n_OA': 3, 'n_OE': 5, 'cerrado': 3210.4, 'pnl_abierto': -85.1, 'Z': 3125.3, 'lotajes_m': 1,
        'trades_bloque': 6, 'ganados_bloque': 4, 'trades_acum': 212, 'aciertos_acum_pct': 61.0, 'drawdown_max_pct': -9.8,
        'N': 120, 'K': 1.1, 'N_EXP': 1.6, 'LAMBDA': 0.2, 'A_prom': 6.5, 'B_prom': 3.2, 'p_prom': 0.045,
        'umbral_usd': 140.0, 'FO_inicial': 0.12, 'FO_final': 0.15, 'convergio': True, 'busqueda_s': 41.0,
        'busqueda_cortada': False,
    }
    lineas = s.formatear_resumen(fila)
    assert len(lineas) == 6 and all(l.startswith(f'[{VALOR} | q4_s0]') for l in lineas)
    assert 'bloque 37/250' in lineas[0] and 'ETA 1h20m' in lineas[0] and '14.8%' in lineas[0]
    assert 'lotajes_m 1' in lineas[2] and 'umbral última vela 140 USD' in lineas[4] and 'convergió, 41 s' in lineas[5]
    sin_busqueda = {**fila, 'FO_inicial': None, 'FO_final': None, 'busqueda_s': None, 'busqueda_cortada': None, 'convergio': None}
    assert len(s.formatear_resumen(sin_busqueda)) == 5


# ─── Con datos reales: vueltas cortas ─────────────────────────────────────────

def test_c1_sin_cobertura_falla_antes_de_buscar():
    if not _hay_datos():
        return
    c1 = _c1_n20()
    c1 = c1[c1.index >= '2022-03-02']  # la vuelta parte el 2022-03-01: la primera vela no tiene C1
    try:
        _vuelta(c1)
    except ValueError as e:
        assert 'C1 sin valor' in str(e)
    else:
        raise AssertionError('debió fallar por falta de C1 en la primera vela')


def test_misma_semilla_misma_vuelta():
    if not _hay_datos():
        return
    c1 = _c1_n20()
    a, b = _vuelta(c1, semilla=5), _vuelta(c1, semilla=5)
    assert len(a['retornos']) > 5, 'la vuelta corta debe tener trades para que la prueba valga'
    assert not any(bu['info']['tiempo_agotado'] for bu in a['busquedas'] if bu['info']), 'la búsqueda tocó el tope de tiempo'
    assert np.array_equal(a['equity'], b['equity'])
    assert a['retornos'] == b['retornos']


def test_lote_sigue_a_z_y_la_vuelta_termina_en_el_ultimo_c1():
    if not _hay_datos():
        return
    c1 = _c1_n20()
    ultimo = pd.Timestamp('2022-03-03 06:00')
    with _cuenta(capital_inicial=9000.0), _q5_temporal() as q5, contextlib.redirect_stdout(io.StringIO()):  # Z = 9000 -> lotajes_m = 3
        carpeta = q5 / VALOR / 'test_lote'
        s.preparar_carpeta(carpeta, True)
        res = s.ejecutar_vuelta(VALOR, c1[c1.index <= ultimo], carpeta)
        ev = pd.read_json(carpeta / 'events.json')
    assert res['indice'][-1] <= ultimo and len(res['indice']) > 40
    assert res['m_max'] == 3
    creadas = ev[ev['tipo'] == 'OE_creada']
    assert len(creadas) > 0
    z_previa = pd.Series(np.r_[9000.0, res['equity'][:-1]], index=res['indice'])
    for ts, lote in zip(pd.to_datetime(creadas['ts']), creadas['lote']):
        esperado = lotajes_m(z_previa[ts]) * gc.MIN_LOTAJES[VALOR]
        assert abs(lote - esperado) < 1e-9, (ts, lote, esperado)


def test_stop_out_no_corta_la_vuelta():
    if not _hay_datos():
        return
    c1 = _c1_n20()
    with _cuenta(stop_out_level=10 ** 9):  # con cualquier posición abierta el nivel de margen queda bajo el umbral
        res = _vuelta(c1)
    assert res['stop_outs'] >= 1
    assert not np.isnan(res['equity']).any(), 'la vuelta debe llegar a la última vela'


def test_vuelta_registrada_premios_kpis_y_seguimiento():
    if not _hay_datos():
        return
    c1 = _c1_n20()
    _, estructura, c2_q4 = s.cargar_insumos(VALOR)
    consola = io.StringIO()
    with _q5_temporal() as q5, contextlib.redirect_stdout(consola):
        fila = s.correr_vuelta(VALOR, c1, 'test_reg', semilla=5, c2=c2_q4, fase='q4', hasta=HASTA)
        vueltas = pd.read_csv(q5 / f'{VALOR}_vueltas.csv')
        seguimiento = pd.read_csv(q5 / f'{VALOR}_seguimiento.csv')
        log_x4 = (q5 / VALOR / 'test_reg' / 'x4.log').read_text(encoding='utf-8')
        trades = pd.read_json(q5 / VALOR / 'test_reg' / 'trades.json')
        resumen = json.loads((q5 / VALOR / 'test_reg' / 'resumen.json').read_text(encoding='utf-8'))
        version = s.registrar_version_estructura(VALOR, estructura)
        archivo_estructura = (q5 / f'{VALOR}_estructura_v{version}.json').exists()

    assert len(vueltas) == 1 and vueltas.loc[0, 'id'] == 'test_reg' and vueltas.loc[0, 'version_estructura'] == 1
    assert archivo_estructura
    # C2 completos: una columna por variable de la estructura, más span, punto_medio y pendiente de cada C1
    for c1_nombre, entrada in estructura.items():
        for v in entrada['variables']:
            assert f'c2_{c1_nombre}_w_{v["nombre"]}' in vueltas.columns
        assert {f'c2_{c1_nombre}_span', f'c2_{c1_nombre}_punto_medio', f'c2_{c1_nombre}_pendiente'} <= set(vueltas.columns)
    # premios: la definición del plan sobre la curva de Z
    n, corte = fila['n_velas'], fila['corte_velas']
    assert corte == int(n * (1 - config_smart.FRACCION_RESERVADA))
    assert abs(fila['premio_aprendizaje'] - fila['z_corte'] / corte) < 1e-9
    assert abs(fila['premio_reservado'] - (fila['z_final'] - fila['z_corte']) / (n - corte)) < 1e-9
    # KPIs
    assert fila['n_trades'] == len(trades) > 5 and 0 <= fila['tasa_aciertos_pct'] <= 100
    assert fila['drawdown_max_pct'] <= 0 and fila['lotajes_m_max'] >= 1 and fila['stop_outs'] == 0
    assert fila['n_busquedas'] == 1 and fila['n_busquedas_cortadas'] == 0
    # resumen.json: lo mismo que la fila y la consola, más tiempos, búsquedas y bloques
    assert resumen['vuelta']['n_trades'] == fila['n_trades'] and len(resumen['resumen_final']) == 4
    assert resumen['tiempos']['computo_s'] > 0 and resumen['tiempos']['reloj_s'] >= resumen['tiempos']['computo_s'] - 0.5
    assert len(resumen['busquedas']) == 1 and resumen['busquedas_resumen']['cortadas'] == 0
    assert len(resumen['bloques']) == 2 and resumen['equity_fin_de_mes'] and resumen['config']['hasta'] == str(HASTA)
    for c1_nombre in ('N', 'K', 'N_EXP', 'LAMBDA', 'A', 'factor_B', 'p'):
        assert {f'c1_{c1_nombre}_{k}' for k in ('media', 'std', 'min', 'max', 'pct_piso', 'pct_techo', 'pasos')} <= set(vueltas.columns)
    assert vueltas.loc[0, 'c1_N_media'] == 20 and vueltas.loc[0, 'c1_N_pasos'] == 1
    # seguimiento: bloque 0 (cold start) y el cierre del único bloque, con el mismo Z que la vuelta
    assert seguimiento['bloque'].tolist() == [0, 1] and (seguimiento['vuelta'] == 'test_reg').all()
    assert abs(seguimiento['Z'].iloc[-1] - fila['z_final']) < 1e-6
    assert seguimiento['trades_acum'].iloc[-1] == fila['n_trades']
    assert seguimiento[['A_prom', 'B_prom', 'p_prom', 'umbral_usd']].notna().all().all()  # también en el bloque 0
    # consola: todas las líneas del resumen con el prefijo; lo de X4 quedó en x4.log
    salida = consola.getvalue()
    assert f'[{VALOR} | test_reg] bloque 0/1' in salida and 'FIN DE VUELTA' in salida
    assert '[A→C]' not in salida and '[A→C]' in log_x4


def _interrumpir(parche: str, nombre: str, n_llamada: int, despues_de_ejecutar: bool):
    """Hace que la `n_llamada`-ésima llamada a `s.<parche>` (o `s.x4.<parche>`) levante `_Interrumpido`, antes o después
    de correr la original: simula matar el proceso en ese punto. Devuelve (instalar, restaurar)."""
    destino = s.x4 if parche.startswith('_procesar') else s
    original, llamadas = getattr(destino, parche), {'n': 0}

    def envoltura(*a, **k):
        llamadas['n'] += 1
        if llamadas['n'] == n_llamada and not despues_de_ejecutar:
            raise _Interrumpido(nombre)
        r = original(*a, **k)
        if llamadas['n'] == n_llamada:
            raise _Interrumpido(nombre)
        return r

    return (lambda: setattr(destino, parche, envoltura)), (lambda: setattr(destino, parche, original))


def _comparar_vuelta_reanudada(parche: str, n_llamada: int, despues_de_ejecutar: bool) -> None:
    c1 = _c1_n20()
    with _n_velas(48), _q5_temporal() as q5, contextlib.redirect_stdout(io.StringIO()):
        completa = q5 / VALOR / 'completa'
        s.preparar_carpeta(completa, True)
        a = s.ejecutar_vuelta(VALOR, c1, completa, 5, '2022-03-07')
        assert len(a['busquedas']) >= 3 and not any(b['info']['tiempo_agotado'] for b in a['busquedas'] if b['info'])

        cortada = q5 / VALOR / 'cortada'
        s.preparar_carpeta(cortada, True)
        instalar, restaurar = _interrumpir(parche, 'kill', n_llamada, despues_de_ejecutar)
        instalar()
        try:
            s.ejecutar_vuelta(VALOR, c1, cortada, 5, '2022-03-07')
        except _Interrumpido:
            pass
        else:
            raise AssertionError('la vuelta debió interrumpirse')
        finally:
            restaurar()
        assert (cortada / s.ARCHIVO_SNAPSHOT).exists()
        b = s.ejecutar_vuelta(VALOR, c1, cortada, 5, '2022-03-07', reanudar=True)

        assert np.array_equal(a['equity'], b['equity'])
        assert a['retornos'] == b['retornos'] and a['stop_outs'] == b['stop_outs']
        for k in a['aplicado']:
            assert np.array_equal(a['aplicado'][k], b['aplicado'][k], equal_nan=True), k
        assert len(a['busquedas']) == len(b['busquedas'])
        for archivo in ('trades.json', 'events.json'):
            assert json.loads((completa / archivo).read_text()) == json.loads((cortada / archivo).read_text()), archivo
        for archivo in s.CURVAS_EQUITY:
            assert (completa / archivo).read_bytes() == (cortada / archivo).read_bytes(), archivo
        for ruta in (completa / 'conjuntos_N').glob('*_bt.json'):
            assert json.loads(ruta.read_text()) == json.loads((cortada / 'conjuntos_N' / ruta.name).read_text()), ruta.name
        seg = pd.read_csv(q5 / f'{VALOR}_seguimiento.csv')
        reloj = ['vuelta', 'eta_s', 'busqueda_s']  # dependen del reloj o del nombre de la vuelta
        sa = seg[seg['vuelta'] == 'completa'].drop(columns=reloj).reset_index(drop=True)
        sb = seg[seg['vuelta'] == 'cortada'].drop(columns=reloj).reset_index(drop=True)
        pd.testing.assert_frame_equal(sa, sb)


def test_reanudar_tras_matar_a_mitad_de_un_bloque_da_la_misma_vuelta():
    if not _hay_datos():
        return
    _comparar_vuelta_reanudada('_procesar_candle', 60, False)  # vela 60 = a mitad del segundo bloque


def test_reanudar_tras_matar_justo_despues_de_una_busqueda_da_la_misma_vuelta():
    if not _hay_datos():
        return
    _comparar_vuelta_reanudada('_buscar_soportes', 3, True)  # la búsqueda del 3er bloque ya escribió su caché


def test_reanudar_rechaza_carpeta_sin_snapshot_y_reset():
    if not _hay_datos():
        return
    c1 = _c1_n20()
    with _q5_temporal() as q5, contextlib.redirect_stdout(io.StringIO()):
        carpeta = q5 / VALOR / 'vieja'
        carpeta.mkdir(parents=True)
        (carpeta / 'trades.json').write_text('[]')
        for kwargs, texto in (({'reanudar': True}, f'no {s.ARCHIVO_SNAPSHOT}'), ({'reanudar': True, 'reset': True}, 'se excluyen')):
            try:
                s.correr_vuelta(VALOR, c1, 'vieja', **kwargs)
            except SystemExit as e:
                assert texto in str(e), str(e)
            else:
                raise AssertionError(f'debió rechazarse: {kwargs}')


def test_reanudar_rechaza_snapshot_de_otros_c1():
    if not _hay_datos():
        return
    c1 = _c1_n20()
    with _n_velas(48), _q5_temporal() as q5, contextlib.redirect_stdout(io.StringIO()):
        carpeta = q5 / VALOR / 'cortada'
        s.preparar_carpeta(carpeta, True)
        instalar, restaurar = _interrumpir('_procesar_candle', 'kill', 60, False)
        instalar()
        try:
            s.ejecutar_vuelta(VALOR, c1, carpeta, 5, '2022-03-07')
        except _Interrumpido:
            pass
        finally:
            restaurar()
        otros = c1.copy()
        otros['A'] = otros['A'] * 2
        try:
            s.ejecutar_vuelta(VALOR, otros, carpeta, 5, '2022-03-07', reanudar=True)
        except SystemExit as e:
            assert 'cambiaron' in str(e)
        else:
            raise AssertionError('debió rechazar el snapshot de otros C1')


def test_vuelta_terminada_borra_su_snapshot():
    if not _hay_datos():
        return
    c1 = _c1_n20()
    with _q5_temporal() as q5, contextlib.redirect_stdout(io.StringIO()):
        s.correr_vuelta(VALOR, c1, 'fin', semilla=5, hasta=HASTA)
        assert not (q5 / VALOR / 'fin' / s.ARCHIVO_SNAPSHOT).exists()


if __name__ == '__main__':
    pruebas =[(n, f) for n, f in sorted(globals().items()) if n.startswith('test_') and callable(f)]
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
