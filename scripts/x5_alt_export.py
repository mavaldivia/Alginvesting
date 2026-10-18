"""
x5_alt_export.py

Convención de inputs/outputs de los notebooks X5_Qi (X5_alt_v2): cada Qi lee y
escribe exclusivamente en resources/x5_alt/exp_Qi/ (su propia carpeta), busca
inputs de otro Qj en resources/x5_alt/exp_Qj/, y al final empaqueta su carpeta
completa en resources/x5_alt/exp_Qi.zip para bajarlo desde Windows (donde
corren con Data/X2/X3 actualizados) y pasarlo a Claude en Mac.

No es un script standalone. Se importa y llama con:
    from x5_alt_export import carpeta_exp, limpiar_exp, exportar_zip
    CARPETA_EXP = limpiar_exp('X5_Q1')   # al inicio del notebook — limpia exp_Q1
    ...                                   # cada celda escribe en CARPETA_EXP / f'{valor}_xxx.csv'
    exportar_zip('X5_Q1')                 # al final — comprime exp_Q1 completa en exp_Q1.zip
"""

import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import CARPETA_X5_ALT


def _qi(nombre_notebook: str) -> str:
    return nombre_notebook.rsplit('_', 1)[-1]


def carpeta_exp(nombre_notebook: str) -> Path:
    """resources/x5_alt/exp_Qi/ del notebook indicado (ej. 'X5_Q1' -> exp_Q1)."""
    carpeta = CARPETA_X5_ALT / f'exp_{_qi(nombre_notebook)}'
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def limpiar_exp(nombre_notebook: str) -> Path:
    """Vacía exp_Qi y la deja lista para esta corrida (se llama al inicio del notebook).

    Borra el contenido en vez de la carpeta misma: en Windows/OneDrive el
    directorio puede quedar con un handle abierto (sync, otro kernel) y el
    rmdir final de shutil.rmtree(carpeta) tira PermissionError aunque los
    archivos de adentro sí se pudieron borrar.
    """
    carpeta = CARPETA_X5_ALT / f'exp_{_qi(nombre_notebook)}'
    carpeta.mkdir(parents=True, exist_ok=True)
    for item in carpeta.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    return carpeta


def exportar_zip(nombre_notebook: str) -> Path:
    """Comprime exp_Qi completa (todo lo que el notebook exportó) en exp_Qi.zip, reemplazando el anterior."""
    qi = _qi(nombre_notebook)
    carpeta = carpeta_exp(nombre_notebook)
    archivos = sorted(a for a in carpeta.iterdir() if a.is_file())
    path_zip = CARPETA_X5_ALT / f'exp_{qi}.zip'
    if path_zip.exists():
        path_zip.unlink()
    with zipfile.ZipFile(path_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for archivo in archivos:
            zf.write(archivo, arcname=archivo.name)
    print(f"{nombre_notebook}: zip con {len(archivos)} archivo(s) guardado en {path_zip}")
    return path_zip
