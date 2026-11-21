"""
Pruebas de registro_din.py (registro único de la validación en Windows de Q5-5b).

Sin MT5 ni datos: archivos temporales. Corren sin pytest:
    python scripts/test_registro_din.py
"""

import datetime
import json
import multiprocessing
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
import registro_din as reg

RUTA_ORIGINAL = cfg.RUTA_REGISTRO_DIN


def _leer(ruta):
    return [json.loads(linea) for linea in Path(ruta).read_text(encoding='utf-8').splitlines()]


def _restaurar():
    cfg.RUTA_REGISTRO_DIN = RUTA_ORIGINAL
    reg.PROCESO = None
    reg._ultimo.clear()


def _escritor(ruta, proceso, n):
    cfg.RUTA_REGISTRO_DIN = Path(ruta)
    reg.PROCESO = proceso
    for i in range(n):
        reg.registrar('prueba', 'BTCUSD', i=i, relleno='x' * 400)


def test_una_linea_json_por_evento_con_tipos_de_numpy_y_fechas():
    with tempfile.TemporaryDirectory() as tmp:
        cfg.RUTA_REGISTRO_DIN = Path(tmp) / 'sub' / 'eventos.jsonl'  # la carpeta se crea sola
        reg.PROCESO = 'X1'
        reg.registrar('x1_z', 'TSLA', z=np.float64(2950.5), cupo=np.int64(5), cuando=datetime.datetime(2026, 11, 20, 10),
                      carpeta=Path('a/b'), tope_oa=False)
        reg.registrar('inicio')
        filas = _leer(cfg.RUTA_REGISTRO_DIN)
    _restaurar()
    assert len(filas) == 2
    f = filas[0]
    assert (f['proceso'], f['evento'], f['valor'], f['z'], f['cupo'], f['tope_oa']) == ('X1', 'x1_z', 'TSLA', 2950.5, 5, False)
    assert f['cuando'] == '2026-11-20 10:00:00' and 'ts' in f
    assert 'valor' not in filas[1]


def test_cada_limita_por_clave():
    reg._ultimo.clear()
    assert reg.cada('a', 3600) is True
    assert reg.cada('a', 3600) is False
    assert reg.cada('b', 3600) is True  # otra clave
    assert reg.cada('c', 0) is True and reg.cada('c', 0) is True
    _restaurar()


def test_un_fallo_al_escribir_no_detiene_al_proceso():
    with tempfile.TemporaryDirectory() as tmp:
        archivo = Path(tmp) / 'es_un_archivo'
        archivo.write_text('')
        cfg.RUTA_REGISTRO_DIN = archivo / 'eventos.jsonl'  # la "carpeta" es un archivo
        reg.registrar('x1_z', 'BTCUSD')  # no debe lanzar
    _restaurar()


def test_iniciar_deja_el_arranque_con_la_configuracion_vigente():
    with tempfile.TemporaryDirectory() as tmp:
        cfg.RUTA_REGISTRO_DIN = Path(tmp) / 'eventos.jsonl'
        reg.iniciar('publicador', una_vez=True)
        f = _leer(cfg.RUTA_REGISTRO_DIN)[0]
        assert reg.PROCESO == 'publicador'
    _restaurar()
    assert f['evento'] == 'inicio' and f['proceso'] == 'publicador' and f['una_vez'] is True
    assert f['tipo_ejecucion'] == cfg.TIPO_EJECUCION and f['lotajes_m'] == cfg.LOTAJES_M
    assert f['valores'] == cfg.VALORES and f['pid'] > 0 and 'commit' in f


def test_procesos_en_paralelo_no_mezclan_lineas():
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / 'eventos.jsonl'
        procesos = [multiprocessing.Process(target=_escritor, args=(str(ruta), f'P{k}', 200)) for k in range(4)]
        for p in procesos:
            p.start()
        for p in procesos:
            p.join()
        filas = _leer(ruta)  # una línea cortada o mezclada no parsea
    assert len(filas) == 800
    for k in range(4):
        assert [f['i'] for f in filas if f['proceso'] == f'P{k}'] == list(range(200))


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
