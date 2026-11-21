"""
publicador_c1.py

Publicador de Q5-5b (decisiones.md 2026-11-19): convierte la candidata de cada valor
(`config/candidatas/{valor}_candidata.json`, que escribe `X4_bckt_ventanas.py --evaluar_candidato` al pasar la
compuerta) en los C1 vigentes y los escribe en `config/active_parameters.json`; X0 y X1 solo lo leen
(`TIPO_EJECUCION = "din"`). Corre en Windows, donde están `Data/` y el historial de X2. Un valor sin candidata no
aparece en el archivo y X0/X1 usan `config.py` para él.

Cadencias (plan_x5_alt_v2.md §9.2), como en el backtesting inteligente: `A`, `factor_B` y `p` se recalculan en cada
corrida (cada vela); `N`, `K`, `N_EXP` y `LAMBDA` solo cada `N_VELAS` velas o al cambiar de candidata, y el resto del
tiempo se arrastran del archivo anterior: cambiar `N` cada hora cambia el archivo de soportes y el warm start.

Los C1 son los de la última vela cerrada: se asume que la última fila de `Data/` es la vela en formación (X0 la deja
así), igual que `c1_operacion` del backtest, que rige cada vela con los C1 de la anterior.

Uso:
  python scripts/publicador_c1.py                  # bucle, cada PUBLICADOR_PERIODO_MIN minutos
  python scripts/publicador_c1.py --una_vez        # una pasada y termina
  python scripts/publicador_c1.py --activos BTCUSD TSLA
"""

import argparse
import datetime
import json
import os
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg  # noqa: E402
import config_smart  # noqa: E402
import registro_din as reg  # noqa: E402
from x5_alt_funciones import c1_dinamicos, cargar_estructura_c1  # noqa: E402
from x5_alt_variables import armar_tabla_base, cargar_precio, cargar_registros_x2, construir_tabla_estado  # noqa: E402

ESQUEMA = 'q5'


# ─── Candidata (la escribe X4_bckt_ventanas en Mac, la lee el publicador en Windows) ──────────────────────────

def ruta_candidata(valor: str) -> Path:
    return cfg.RUTA_CANDIDATAS / f'{valor}_candidata.json'


def _escribir_atomico(ruta: Path, objeto) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + '.tmp')
    tmp.write_text(json.dumps(objeto, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, ruta)


def guardar_candidata(valor: str, candidato: str, c2: dict, metricas: dict) -> Path:
    """Deja `c2` como la candidata vigente de `valor` y la agrega al historial (`{valor}_historial.jsonl`), para poder
    volver a una anterior copiando su registro sobre `{valor}_candidata.json`."""
    registro = {
        'valor': valor, 'candidato': candidato,
        'fecha': datetime.datetime.now().isoformat(timespec='seconds'), 'metricas': metricas,
        'c2': {c1: {'pesos': {v: float(w) for v, w in c['pesos'].items()}, 'span': int(c['span']),
                    'punto_medio': float(c['punto_medio']), 'pendiente': float(c['pendiente'])}
               for c1, c in c2.items()},
    }
    _escribir_atomico(ruta_candidata(valor), registro)
    with open(cfg.RUTA_CANDIDATAS / f'{valor}_historial.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(registro, ensure_ascii=False) + '\n')
    return ruta_candidata(valor)


def cargar_candidata(valor: str) -> dict | None:
    ruta = ruta_candidata(valor)
    return json.loads(ruta.read_text(encoding='utf-8')) if ruta.exists() else None


# ─── C1 vigentes ──────────────────────────────────────────────────────────────

def c1_vela_cerrada(valor: str, c2: dict) -> pd.DataFrame:
    """C1 vela a vela hasta la última vela cerrada, con la tabla de estado de Q1 construida desde `Data/` y X2."""
    tabla = construir_tabla_estado(armar_tabla_base(cargar_precio(valor), cargar_registros_x2(valor)))
    estructura = cargar_estructura_c1(cfg.RUTA_ESTRUCTURA_C1)
    return c1_dinamicos(valor, c2, tabla, estructura).iloc[:-1]


def entrada_publicada(valor: str, c1: pd.DataFrame, candidato: str, previo: dict | None,
                      ahora: datetime.datetime) -> dict:
    """Entrada de `valor` en `active_parameters.json`: `c1` llega hasta la última vela cerrada y `previo` es la entrada
    anterior del mismo valor (None si no había). El grupo de búsqueda se refresca si no hay entrada previa, cambió la
    candidata o pasaron `N_VELAS` velas desde la última búsqueda; si no, se arrastra el de `previo`. `cuenta_desde` (epoch)
    abre la cuenta virtual del valor para el tope de OA de X1 y se arrastra siempre; para reiniciarla se borra la entrada."""
    fila = c1.iloc[-1]
    if fila.isna().any():
        raise ValueError(f'{valor}: C1 sin dato en la última vela cerrada ({c1.index[-1]}): {fila[fila.isna()].index.tolist()}')
    n_velas = config_smart.N_VELAS[config_smart.tipo_valor(valor)]

    velas_desde = None
    if previo is not None and previo['candidato'] == candidato:
        desde = pd.Timestamp(previo['busqueda_desde'])
        pos = c1.index.searchsorted(desde)
        if pos < len(c1) and c1.index[pos] == desde:
            velas_desde = len(c1) - 1 - pos
    refrescar = velas_desde is None or velas_desde >= n_velas

    busqueda = fila if refrescar else previo
    busqueda_desde = c1.index[-1] if refrescar else pd.Timestamp(previo['busqueda_desde'])
    a, factor_b, p = float(fila['A']), float(fila['factor_B']), float(fila['p'])
    return {
        'model_status': 'trained', 'candidato': candidato,
        'calculado_en': ahora.isoformat(timespec='seconds'),
        'ultima_vela': str(c1.index[-1]), 'busqueda_desde': str(busqueda_desde),
        'cuenta_desde': previo['cuenta_desde'] if previo and 'cuenta_desde' in previo else int(ahora.timestamp()),
        'N': int(busqueda['N']), 'K': float(busqueda['K']), 'N_EXP': float(busqueda['N_EXP']),
        'LAMBDA': float(busqueda['LAMBDA']),
        'A': a, 'B': round(factor_b * a, 6), 'factor_B': factor_b, 'p': p,
        'PERDIDA_MAX': round(p * config_smart.CUENTA['capital_inicial'], 2),
    }


# ─── Archivo ──────────────────────────────────────────────────────────────────

def cargar_publicado() -> dict:
    """Entradas por valor del `active_parameters.json` vigente; vacío si no existe o es del X5 original (otro esquema)."""
    ruta = cfg.RUTA_ACTIVE_PARAMETERS
    if not ruta.exists():
        return {}
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    return datos['valores'] if datos.get('esquema') == ESQUEMA else {}


def publicar(valores: list, ahora: datetime.datetime | None = None) -> dict:
    """Una pasada: recalcula la entrada de cada valor con candidata y reescribe `active_parameters.json`. Si un valor
    falla (por ejemplo, `Data/` a medio escribir por X0) conserva su entrada anterior, que X0/X1 descartan solos al
    pasar `PARAMS_DIN_EDAD_MAX_MIN`."""
    ahora = ahora or datetime.datetime.now()
    previos = cargar_publicado()
    nuevos = {}
    for valor in valores:
        candidata = cargar_candidata(valor)
        if candidata is None:
            reg.registrar('sin_candidata', valor)
            continue
        try:
            c1 = c1_vela_cerrada(valor, candidata['c2'])
            nuevos[valor] = entrada_publicada(valor, c1, candidata['candidato'], previos.get(valor), ahora)
        except Exception:
            detalle = traceback.format_exc()
            print(f'[publicador] {valor}: error, se conserva la entrada anterior\n{detalle}', flush=True)
            reg.registrar('error', valor, conserva_anterior=valor in previos, traceback=detalle)
            if valor in previos:
                nuevos[valor] = previos[valor]
            continue
        e = nuevos[valor]
        previo = previos.get(valor)
        refrescada = previo is None or previo['candidato'] != e['candidato'] or previo['busqueda_desde'] != e['busqueda_desde']
        reg.registrar('publicado', valor, busqueda_refrescada=refrescada, **e)
        estado = 'búsqueda refrescada' if refrescada else f'búsqueda desde {e["busqueda_desde"]}'
        print(f'[publicador] {valor} {e["candidato"]} | vela {e["ultima_vela"]} | N {e["N"]} K {e["K"]} '
              f'N_EXP {e["N_EXP"]} LAMBDA {e["LAMBDA"]} | A {e["A"]} B {e["B"]} p {e["p"]} | {estado}', flush=True)
    _escribir_atomico(cfg.RUTA_ACTIVE_PARAMETERS,
                      {'esquema': ESQUEMA, 'generated_at': ahora.isoformat(timespec='seconds'), 'valores': nuevos})
    return nuevos


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--una_vez', action='store_true', help='una pasada y termina (por defecto, bucle)')
    ap.add_argument('--activos', nargs='+', default=cfg.VALORES, help='valores a publicar (por defecto, todos)')
    args = ap.parse_args()
    reg.iniciar('publicador', una_vez=args.una_vez, activos=args.activos)
    while True:
        publicar(args.activos)
        if args.una_vez:
            return
        time.sleep(cfg.PUBLICADOR_PERIODO_MIN * 60)


if __name__ == '__main__':
    main()
