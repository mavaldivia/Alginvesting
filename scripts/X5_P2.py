"""X5_P2 — Análisis ceteris paribus vs. precio sobre la tabla maestra de X5_P1.

Segundo script de X5_alt (ver docs/plans/X5_alternativo.md). Toma como input
la tabla generada por X5_P1.ipynb (resources/x5_alt/{valor}_tabla_maestra.csv)
y corre el análisis (correlaciones, regresión ceteris paribus, gráficos) sobre
ella. No recalcula nada de X5_P1 — si la tabla no existe, hay que correr
X5_P1.ipynb primero para ese activo.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import config as cfg  # noqa: E402


def cargar_tabla_maestra(valor: str) -> pd.DataFrame:
    path = cfg.CARPETA_X5_ALT / f'{valor}_tabla_maestra.csv'
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Corré X5_P1.ipynb para {valor} antes de X5_P2."
        )
    tabla = pd.read_csv(path, parse_dates=['DateTime'])
    return tabla


def main():
    parser = argparse.ArgumentParser(
        description='X5_P2 — análisis ceteris paribus sobre la tabla maestra de X5_P1'
    )
    parser.add_argument('--valor', default='BTCUSD',
                        help='Activo a analizar (default: BTCUSD)')
    args = parser.parse_args()

    tabla = cargar_tabla_maestra(args.valor)
    print(f"Tabla maestra cargada: {args.valor} — {tabla.shape[0]} filas x {tabla.shape[1]} columnas")
    print(f"Rango: {tabla['DateTime'].min()} → {tabla['DateTime'].max()}")


if __name__ == '__main__':
    main()
