"""
q5_empaquetar_medicion.py

Empaqueta en un solo zip todo lo que Claude necesita de una corrida de medición de X4
(Q5-1): la salida de consola, la configuración, el checkpoint y el log de cada búsqueda de
soportes (duración, iteraciones, convergencia), más un resumen y los datos del equipo.

Solo lee archivos que X4/X0 ya escribieron en disco, así que sirve en cualquier momento:
con la corrida terminada, interrumpida, o con una ventana nueva después de reanudar.

Uso (desde la raíz del proyecto):
    python scripts/q5_empaquetar_medicion.py V4
Salida: resources/x4/versionV4/medicion_V4.zip
"""

import argparse
import datetime
import json
import os
import platform
import statistics
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import BASE_DIR, CARPETA_LOGS


def _creacion(path: Path) -> datetime.datetime:
    st = path.stat()
    return datetime.datetime.fromtimestamp(getattr(st, 'st_birthtime', st.st_ctime))


def _leer_busquedas(desde: datetime.datetime) -> list:
    # El log de X0 es global y de solo-append: mezcla corridas de otras versiones, por eso
    # se filtra por la hora real de inicio de cada búsqueda.
    entradas = []
    for log in sorted(CARPETA_LOGS.glob('*_bt.jsonl')):
        for linea in log.read_text().splitlines():
            e = json.loads(linea)
            if datetime.datetime.fromisoformat(e['t_inicio']) >= desde:
                entradas.append(e)
    return sorted(entradas, key=lambda e: e['t_inicio'])


def _resumen(busquedas: list) -> dict:
    if not busquedas:
        return {'n_busquedas': 0}
    dur = [b['duracion_s'] for b in busquedas]
    t_ini = [datetime.datetime.fromisoformat(b['t_inicio']) for b in busquedas]
    t_fin = [datetime.datetime.fromisoformat(b['t_fin']) for b in busquedas]
    # Tiempo entre el fin de una búsqueda y el inicio de la siguiente = simulación de las
    # velas intermedias. Un hueco muy mayor a la mediana es una interrupción, no simulación.
    huecos = [(t_ini[k + 1] - t_fin[k]).total_seconds() for k in range(len(busquedas) - 1)]
    med_hueco = statistics.median(huecos) if huecos else 0
    return {
        'n_busquedas': len(busquedas),
        'n_convergieron': sum(b['convergio'] for b in busquedas),
        'duracion_busqueda_s': {
            'primera': dur[0], 'mediana': statistics.median(dur), 'max': max(dur), 'suma': round(sum(dur), 1),
        },
        'iteraciones_mediana': statistics.median(b['iteraciones'] for b in busquedas),
        'reloj': {
            'primer_inicio': busquedas[0]['t_inicio'], 'ultimo_fin': busquedas[-1]['t_fin'],
            'total_h': round((t_fin[-1] - t_ini[0]).total_seconds() / 3600, 2),
        },
        'entre_busquedas_s': {'mediana': med_hueco, 'max': max(huecos) if huecos else 0},
        'posibles_interrupciones': [
            {'despues_de': busquedas[k]['clave'], 'hueco_min': round(h / 60, 1)}
            for k, h in enumerate(huecos) if med_hueco and h > 10 * med_hueco
        ],
    }


def _equipo() -> dict:
    info = {
        'so': platform.platform(), 'procesador': platform.processor(),
        'cpu_logicas': os.cpu_count(), 'python': platform.python_version(),
    }
    try:
        import psutil
        info['ram_gb'] = round(psutil.virtual_memory().total / 1024 ** 3, 1)
    except ImportError:
        info['ram_gb'] = 'n/d (psutil no instalado)'
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument('version', help='ej. V4')
    args = parser.parse_args()

    carpeta = BASE_DIR / 'resources' / 'x4' / f'version{args.version}'
    if not carpeta.exists():
        sys.exit(f'No existe {carpeta}')

    busquedas = _leer_busquedas(_creacion(carpeta))
    resumen = {'version': args.version, 'generado': datetime.datetime.now().isoformat(timespec='seconds'),
               'equipo': _equipo(), **_resumen(busquedas)}

    archivos = sorted(carpeta.glob(f'salida_{args.version}*.txt'))
    archivos += [carpeta / f'config_{args.version}.py',
                 carpeta / f'resources_{args.version}' / 'checkpoint.json']
    archivos = [a for a in archivos if a.exists()]

    ruta_zip = carpeta / f'medicion_{args.version}.zip'
    with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for a in archivos:
            zf.write(a, arcname=a.name)
        zf.writestr('busquedas_soportes.jsonl', ''.join(json.dumps(b) + '\n' for b in busquedas))
        zf.writestr('resumen.json', json.dumps(resumen, indent=2))

    print(json.dumps(resumen, indent=2))
    print(f'\nZip con {len(archivos) + 2} archivo(s): {ruta_zip}')


if __name__ == '__main__':
    main()
