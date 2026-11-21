"""
Pruebas de params_din.py (lectura de los C1 publicados en X0/X1 con respaldo a config.py, Q5-5b).

Sin MT5 ni datos: archivos temporales. Corren sin pytest:
    python scripts/test_params_din.py
"""

import datetime
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
import params_din
import registro_din

REGISTRO_PRUEBAS = Path(tempfile.mkdtemp()) / 'eventos.jsonl'  # que ninguna prueba escriba en resources/
cfg.RUTA_REGISTRO_DIN = REGISTRO_PRUEBAS
AHORA = datetime.datetime.now()  # n_vigente usa el reloj real: las entradas se fechan respecto a él


def _entrada(candidato='candidato_040', hace_min=5, **extra):
    return {'model_status': 'trained', 'candidato': candidato,
            'calculado_en': (AHORA - datetime.timedelta(minutes=hace_min)).isoformat(timespec='seconds'),
            'N': 120, 'K': 1.2, 'N_EXP': 1.4, 'LAMBDA': 0.25, 'A': 4.0, 'B': 6.0, 'factor_B': 1.5, 'p': 0.05,
            'PERDIDA_MAX': 150.0, **extra}


def _escenario(tmp, valores=None, esquema='q5', modo='din'):
    """Redirige las rutas a `tmp`, reinicia el estado del módulo y escribe el archivo (si `valores` no es None)."""
    cfg.RUTA_ACTIVE_PARAMETERS = Path(tmp) / 'active_parameters.json'
    cfg.TIPO_EJECUCION = modo
    params_din._cache.update(mtime=None, datos=None)
    params_din._estado_aviso.clear()
    params_din._firma_registro.clear()
    cfg.RUTA_REGISTRO_DIN = Path(tmp) / 'eventos.jsonl'
    avisos = []
    params_din.avisador = avisos.append
    if valores is not None:
        _escribir(valores, esquema)
    return avisos


def _escribir(valores, esquema='q5'):
    cfg.RUTA_ACTIVE_PARAMETERS.write_text(json.dumps({'esquema': esquema, 'valores': valores}))


def _restaurar():
    cfg.TIPO_EJECUCION = 'est'
    cfg.RUTA_REGISTRO_DIN = REGISTRO_PRUEBAS
    params_din.avisador = print


def _eventos(ruta=None):
    ruta = Path(ruta or cfg.RUTA_REGISTRO_DIN)
    return [json.loads(linea) for linea in ruta.read_text(encoding='utf-8').splitlines()] if ruta.exists() else []


def test_modo_est_no_lee_nada():
    with tempfile.TemporaryDirectory() as tmp:
        _escenario(tmp, {'BTCUSD': _entrada()}, modo='est')
        assert params_din.parametros_vigentes('BTCUSD', AHORA) is None
        assert params_din.n_vigente('BTCUSD', 180) == 180
    _restaurar()


def test_entrada_valida_rige_y_n_vigente_la_usa():
    with tempfile.TemporaryDirectory() as tmp:
        avisos = _escenario(tmp, {'BTCUSD': _entrada()})
        p = params_din.parametros_vigentes('BTCUSD', AHORA)
        assert p['N'] == 120 and p['A'] == 4.0
        assert params_din.n_vigente('BTCUSD', 180) == 120
        assert params_din.params_soporte(p) == {'K': 1.2, 'N_EXP': 1.4, 'LAMBDA': 0.25}
        assert params_din.params_soporte(None) is None
        assert avisos == ['  [params_din] BTCUSD: C1 publicados de candidato_040']  # un solo aviso aunque se consulte dos veces
    _restaurar()


def test_cada_causa_de_caida_vuelve_a_config_para_ese_valor():
    with tempfile.TemporaryDirectory() as tmp:
        casos = {
            'sin archivo': None,
            'esquema': {'BTCUSD': _entrada()},
            'sin candidata': {'ETHUSD': _entrada()},
            'untrained': {'BTCUSD': _entrada(model_status='untrained')},
            'viejo': {'BTCUSD': _entrada(hace_min=cfg.PARAMS_DIN_EDAD_MAX_MIN + 1)},
        }
        for nombre, valores in casos.items():
            avisos = _escenario(tmp, valores, esquema='x5_original' if nombre == 'esquema' else 'q5')
            assert params_din.parametros_vigentes('BTCUSD', AHORA) is None, nombre
            assert params_din.n_vigente('BTCUSD', 180) == 180, nombre
            assert len(avisos) == 1 and 'usando config.py' in avisos[0], (nombre, avisos)
            cfg.RUTA_ACTIVE_PARAMETERS.unlink(missing_ok=True)
    _restaurar()


def test_un_valor_cae_sin_arrastrar_a_los_demas():
    with tempfile.TemporaryDirectory() as tmp:
        _escenario(tmp, {'BTCUSD': _entrada(), 'TSLA': _entrada(model_status='untrained')})
        assert params_din.parametros_vigentes('BTCUSD', AHORA) is not None
        assert params_din.parametros_vigentes('TSLA', AHORA) is None
    _restaurar()


def test_recuperacion_se_avisa_y_el_archivo_nuevo_se_relee():
    with tempfile.TemporaryDirectory() as tmp:
        avisos = _escenario(tmp, {'BTCUSD': _entrada(model_status='untrained')})
        assert params_din.parametros_vigentes('BTCUSD', AHORA) is None
        _escribir({'BTCUSD': _entrada('candidato_050')})
        os.utime(cfg.RUTA_ACTIVE_PARAMETERS, (time.time() + 5, time.time() + 5))  # mtime distinto aunque el FS sea grueso
        assert params_din.parametros_vigentes('BTCUSD', AHORA)['candidato'] == 'candidato_050'
        assert len(avisos) == 2 and 'candidato_050' in avisos[1]
    _restaurar()


def test_archivo_a_medio_escribir_conserva_la_lectura_anterior():
    with tempfile.TemporaryDirectory() as tmp:
        _escenario(tmp, {'BTCUSD': _entrada()})
        assert params_din.parametros_vigentes('BTCUSD', AHORA) is not None
        cfg.RUTA_ACTIVE_PARAMETERS.write_text('{"esquema": "q5", "valores": {')
        os.utime(cfg.RUTA_ACTIVE_PARAMETERS, (time.time() + 5, time.time() + 5))
        assert params_din.parametros_vigentes('BTCUSD', AHORA)['candidato'] == 'candidato_040'
    _restaurar()


def test_avisar_false_no_imprime():
    with tempfile.TemporaryDirectory() as tmp:
        avisos = _escenario(tmp, {'BTCUSD': _entrada()})
        params_din.n_vigente('BTCUSD', 180, avisar=False)
        assert avisos == [] and _eventos() == []
    _restaurar()


def test_registro_anota_cada_publicacion_nueva_y_cada_caida_una_vez():
    with tempfile.TemporaryDirectory() as tmp:
        _escenario(tmp, {'BTCUSD': _entrada(), 'TSLA': _entrada(model_status='untrained')})
        for _ in range(3):  # consultar varias veces no repite el evento
            params_din.parametros_vigentes('BTCUSD', AHORA)
            params_din.parametros_vigentes('TSLA', AHORA)
        _escribir({'BTCUSD': _entrada(hace_min=1)})  # publicación nueva de BTCUSD; TSLA ya no está
        os.utime(cfg.RUTA_ACTIVE_PARAMETERS, (time.time() + 5, time.time() + 5))
        params_din.parametros_vigentes('BTCUSD', AHORA)
        params_din.parametros_vigentes('TSLA', AHORA)
        eventos = _eventos()
    _restaurar()
    assert [(e['evento'], e['valor'], e.get('motivo')) for e in eventos] == [
        ('c1_leidos', 'BTCUSD', None), ('usa_config', 'TSLA', 'model_status=untrained'),
        ('c1_leidos', 'BTCUSD', None), ('usa_config', 'TSLA', 'sin candidata publicada')]
    assert eventos[0]['N'] == 120 and eventos[0]['candidato'] == 'candidato_040' and eventos[0]['PERDIDA_MAX'] == 150.0


def test_z_virtual_y_cupo_de_oa():
    capital = 3000.0
    assert params_din.z_virtual(0.0, 0.0) == capital
    assert params_din.z_virtual(-200.0, 50.0) == capital - 150.0
    # umbral de 132 USD (p = 0.044, m = 1): igual que los casos de X4 (`_paso_F`)
    assert params_din.cupo_oa(3000.0, 132.0) == 11
    assert params_din.cupo_oa(263.0, 132.0) == 0 and params_din.cupo_oa(264.0, 132.0) == 1
    assert params_din.cupo_oa(-500.0, 132.0) == 0
    assert params_din.cupo_oa(3000.0, 264.0) == 5  # al doble de lote el umbral se duplica y el cupo baja


def test_ruta_soportes_nominal_y_respaldo_al_mas_reciente():
    registro_din._ultimo.clear()
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp)
        assert params_din.ruta_soportes('BTCUSD', 120, carpeta) == carpeta / 'BTCUSD_120.json'  # nada: la nominal
        (carpeta / 'BTCUSD_180.json').write_text('[1, 2]')
        (carpeta / 'BTCUSD_150.json').write_text('[3]')
        os.utime(carpeta / 'BTCUSD_150.json', (time.time() + 5, time.time() + 5))
        (carpeta / 'BTCUSD_90_bt.json').write_text('{}')  # el caché bt no cuenta
        os.utime(carpeta / 'BTCUSD_90_bt.json', (time.time() + 50, time.time() + 50))
        (carpeta / 'ETHUSD_60.json').write_text('[9]')  # otro valor
        assert params_din.ruta_soportes('BTCUSD', 120, carpeta) == carpeta / 'BTCUSD_150.json'
        (carpeta / 'BTCUSD_120.json').write_text('[4]')
        assert params_din.ruta_soportes('BTCUSD', 120, carpeta) == carpeta / 'BTCUSD_120.json'
    respaldos = [e for e in _eventos(REGISTRO_PRUEBAS) if e['evento'] == 'soportes_respaldo']
    assert [(e['N'], e['nominal'], e['usa']) for e in respaldos] == [(120, 'BTCUSD_120.json', None)]  # el resto va throttled


def test_sembrar_soportes_copia_solo_si_falta():
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp)
        (carpeta / 'BTCUSD_180.json').write_text('[1, 2, 3]')
        params_din.sembrar_soportes('BTCUSD', 120, carpeta)
        assert (carpeta / 'BTCUSD_120.json').read_text() == '[1, 2, 3]'
        (carpeta / 'BTCUSD_120.json').write_text('[7]')  # ya optimizado por X0: no se pisa
        params_din.sembrar_soportes('BTCUSD', 120, carpeta)
        assert (carpeta / 'BTCUSD_120.json').read_text() == '[7]'
        params_din.sembrar_soportes('TSLA', 100, carpeta)  # sin ningún archivo: no hace nada
        assert not (carpeta / 'TSLA_100.json').exists()
    sembrados = [e for e in _eventos(REGISTRO_PRUEBAS) if e['evento'] == 'soportes_sembrados']
    assert [(e['valor'], e['origen'], e['destino']) for e in sembrados] == [('BTCUSD', 'BTCUSD_180.json', 'BTCUSD_120.json')]


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
