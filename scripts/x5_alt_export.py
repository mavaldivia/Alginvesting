"""
x5_alt_export.py

Empaqueta en un .zip los outputs de un notebook X5_Q1/Q2/Q3 (X5_alt_v2) guardados en
resources/x5_alt/, para bajarlo desde Windows (donde corren con Data/X2/X3 actualizados)
y pasarlo a Claude en Mac.

No es un script standalone. Se importa y llama con:
    from x5_alt_export import exportar_zip
    exportar_zip('X5_Q1', [path_tabla, path_catalogo])
"""

import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import CARPETA_X5_ALT


def exportar_zip(nombre_notebook: str, archivos: list[Path]) -> Path:
    CARPETA_X5_ALT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    path_zip = CARPETA_X5_ALT / f'{nombre_notebook}_{timestamp}.zip'
    with zipfile.ZipFile(path_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for archivo in archivos:
            zf.write(archivo, arcname=archivo.name)
    print(f"{nombre_notebook}: zip con {len(archivos)} archivo(s) guardado en {path_zip}")
    return path_zip
