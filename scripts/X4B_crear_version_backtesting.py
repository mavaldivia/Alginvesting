"""
X4B_crear_version_backtesting.py

Crea la infraestructura completa de una versión de backtesting:
  resources/x4/version{V}/
    config_{V}.py
    resources_{V}/
      conjuntos_N/
      logs/

También registra la versión en la sección X4 de config.py.

Uso:
  python scripts/X4B_crear_version_backtesting.py V1
  python scripts/X4B_crear_version_backtesting.py        # pide el nombre interactivamente
"""

import argparse
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


# ─── Template de config_V.py ─────────────────────────────────────────────────

CONFIG_TEMPLATE = '''\
# resources/x4/version{V}/config_{V}.py
# Parámetros fijados al crear {V}. Sin imports de config.py — garantiza reproducibilidad
# aunque la configuración de producción cambie después.

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent  # raíz del proyecto

# ─── Versión y activos ───────────────────────────────────────────────────────
version = \'{V}\'
valores = [\'BTCUSD\', \'ETHUSD\']
n_sizes = {{\'BTCUSD\': 70, \'ETHUSD\': 70}}

# ─── Fechas ──────────────────────────────────────────────────────────────────
fecha_inicio = \'2026-01-10\'
fecha_fin    = \'F\'   # \'F\' = hasta la última vela disponible; no cierra posiciones al terminar

# ─── Capital y riesgo ────────────────────────────────────────────────────────
capital_inicial     = 3000.0   # USD
PERDIDA_MAX_BT      = 120.0    # USD
MARGEN_LIBRE_MIN_BT = 50.0     # USD — buffer mínimo de margen libre para abrir/ejecutar OE

# ─── Recálculo de soportes ───────────────────────────────────────────────────
delta_recalculo_soportes = 1    # días (puede ser fraccionario, ej. 0.5 = 12h)
hora_recalculo           = 23   # hora UTC (aplica solo cuando delta_recalculo_soportes es entero)

# ─── Algoritmo de soportes (parámetros de X0 fijados para esta versión) ─────
K     = 1
N_EXP = 1.3
parametros_soportes = {{
    \'y\': True, \'w\': True, \'h_dist\': True, \'v\': True, \'f\': True,
}}
LAMBDA            = 1 / 5
M                 = 30
M_COARSE          = 5
DELTA_INICIAL     = 1e-4
FACTOR_DELTA      = 0.7
BLOQUE_DISTANCIAS = 2000
MAX_ITERS         = 10000

# ─── Trading ─────────────────────────────────────────────────────────────────
A = 6     # ganancia mínima en USD para activar el primer SL ganador
B = 2     # distancia en USD (normalizada por L) que mantiene el SL bajo el precio actual
LOTAJES        = {{\'BTCUSD\': 0.01, \'ETHUSD\': 0.1}}
UNITS          = {{\'BTCUSD\': 1,    \'ETHUSD\': 1}}
APALANCAMIENTO = {{\'BTCUSD\': 400,  \'ETHUSD\': 400}}

# ─── Rutas ───────────────────────────────────────────────────────────────────
_VERSION_DIR        = Path(__file__).parent
CARPETA_RESOURCES   = _VERSION_DIR / f\'resources_{{version}}\'
CARPETA_N_BT        = CARPETA_RESOURCES / \'conjuntos_N\'
CARPETA_LOGS_BT     = CARPETA_RESOURCES / \'logs\'
CARPETA_DATA        = BASE_DIR / \'Data\'
CARPETA_DATA_MINUTO = BASE_DIR / \'Data_minuto\'
'''


# ─── Bloque X4 para config.py ────────────────────────────────────────────────

X4_SECTION_HEADER = '\n# ─── X4 — Backtester ─────────────────────────────────────────────────────────\n'


def _leer_config_py():
    path = BASE_DIR / 'scripts' / 'config.py'
    return path.read_text(encoding='utf-8')


def _escribir_config_py(contenido):
    path = BASE_DIR / 'scripts' / 'config.py'
    path.write_text(contenido, encoding='utf-8')


def _registrar_version_en_config(version, fecha_inicio, fecha_fin):
    """Agrega o actualiza la sección X4 en config.py."""
    contenido = _leer_config_py()

    if '# ─── X4 — Backtester' in contenido:
        # Actualizar X4_VERSIONES existente: agregar la versión si no está
        if f"'{version}'" in contenido:
            return  # ya registrada
        # Insertar nueva entrada antes del cierre del dict
        patron = r"(X4_VERSIONES\s*=\s*\{[^}]*)\}"
        match = re.search(patron, contenido, re.DOTALL)
        if match:
            entrada = f"    '{version}': {{'fecha_inicio': '{fecha_inicio}', 'fecha_fin': '{fecha_fin}'}},\n"
            nuevo = match.group(1) + entrada + '}'
            contenido = contenido[:match.start()] + nuevo + contenido[match.end():]
            _escribir_config_py(contenido)
        return

    # Agregar sección X4 al final
    bloque = (
        X4_SECTION_HEADER
        + f"X4_VERSION_ACTIVA = '{version}'\n"
        + "X4_VERSIONES = {\n"
        + f"    '{version}': {{'fecha_inicio': '{fecha_inicio}', 'fecha_fin': '{fecha_fin}'}},\n"
        + "}\n"
    )
    _escribir_config_py(contenido.rstrip() + '\n' + bloque)


# ─── Lógica principal ─────────────────────────────────────────────────────────

def _normalizar_version(raw):
    """'v1', '1', 'V1' → 'V1'"""
    raw = raw.strip().upper()
    if not raw.startswith('V'):
        raw = 'V' + raw
    if not re.match(r'^V\d+$', raw):
        print(f"Error: nombre de versión inválido '{raw}'. Usa formato V1, V2, …")
        sys.exit(1)
    return raw


def crear_version(version):
    version_dir = BASE_DIR / 'resources' / 'x4' / f'version{version}'
    config_path = version_dir / f'config_{version}.py'
    resources_dir = version_dir / f'resources_{version}'

    if version_dir.exists():
        resp = input(f"La versión {version} ya existe en {version_dir}.\n¿Reiniciar infraestructura? (s/N): ").strip().lower()
        if resp not in ('s', 'si', 'sí', 'y', 'yes'):
            print("Cancelado.")
            sys.exit(0)

    # Crear directorios
    (resources_dir / 'conjuntos_N').mkdir(parents=True, exist_ok=True)
    (resources_dir / 'logs').mkdir(parents=True, exist_ok=True)

    # Escribir config_V.py
    config_path.write_text(CONFIG_TEMPLATE.format(V=version), encoding='utf-8')

    # Registrar en config.py
    _registrar_version_en_config(version, '2026-01-10', 'F')

    print(f"\nVersioné {version} creada:")
    print(f"  {version_dir}/")
    print(f"    config_{version}.py")
    print(f"    resources_{version}/conjuntos_N/")
    print(f"    resources_{version}/logs/")
    print(f"\nCompleta los parámetros en:\n  {config_path}")


def main():
    parser = argparse.ArgumentParser(description='Crea infraestructura de una versión de backtesting X4.')
    parser.add_argument('nombre_version', nargs='?', help='Nombre de la versión, ej. V1')
    args = parser.parse_args()

    if args.nombre_version:
        raw = args.nombre_version
    else:
        raw = input("Nombre de la versión (ej. V1): ")

    version = _normalizar_version(raw)
    crear_version(version)


if __name__ == '__main__':
    main()
