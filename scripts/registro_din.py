"""
registro_din.py

Registro único de la validación en Windows de Q5-5b (publicador_c1.py, X0 y X1 con `TIPO_EJECUCION = "din"`): una línea
JSON por evento, de los tres procesos, en `config.RUTA_REGISTRO_DIN`, para pasarle a Claude (Mac) un solo archivo.
Cada proceso llama `iniciar('X1')` al arrancar y `registrar(evento, valor, **datos)` en los puntos que importan. Cada
línea trae `ts` (hora local de Windows), `proceso`, `evento`, `valor` (si aplica) y los datos del evento. Un fallo al
escribir (por ejemplo, el archivo bloqueado) no detiene al proceso que registra.

Lectura rápida del archivo:
    pandas.read_json('resources/validacion_din/eventos.jsonl', lines=True)
"""

import datetime
import json
import os
import platform
import subprocess
import threading
import time

import config as cfg

PROCESO = None  # lo fija `iniciar`; en los workers del pool de X0 queda None (ahí no se registra)
_lock = threading.Lock()  # X0 registra desde un hilo por activo
_ultimo = {}


def _serializable(obj):
    return obj.item() if hasattr(obj, 'item') else str(obj)  # numpy -> escalar; datetime, Path, etc. -> texto


def registrar(evento: str, valor: str | None = None, **datos) -> None:
    registro = {'ts': datetime.datetime.now().isoformat(timespec='seconds'), 'proceso': PROCESO, 'evento': evento}
    if valor is not None:
        registro['valor'] = valor
    registro.update(datos)
    linea = json.dumps(registro, ensure_ascii=False, default=_serializable) + '\n'
    try:
        with _lock:
            cfg.RUTA_REGISTRO_DIN.parent.mkdir(parents=True, exist_ok=True)
            with open(cfg.RUTA_REGISTRO_DIN, 'a', encoding='utf-8') as f:  # una sola escritura por línea: procesos distintos no se mezclan
                f.write(linea)
    except OSError:
        pass


def cada(clave: str, segundos: float) -> bool:
    """True como máximo una vez cada `segundos` por `clave`: para fotos periódicas y avisos que se repetirían."""
    ahora = time.monotonic()
    if ahora - _ultimo.get(clave, float('-inf')) >= segundos:
        _ultimo[clave] = ahora
        return True
    return False


def _commit() -> str | None:
    try:
        salida = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=cfg.BASE_DIR, capture_output=True,
                                text=True, timeout=5)
        return salida.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def iniciar(proceso: str, **extra) -> None:
    """Primer evento de cada arranque: qué código y qué configuración rigen esta corrida."""
    global PROCESO
    PROCESO = proceso
    registrar('inicio', pid=os.getpid(), commit=_commit(), python=platform.python_version(),
              sistema=platform.platform(), zona_horaria_local_s=-time.timezone, tipo_ejecucion=cfg.TIPO_EJECUCION,
              lotajes_m=cfg.LOTAJES_M, n_sizes_ejecucion=cfg.n_sizes_ejecucion, valores=cfg.VALORES,
              t_update_o0=cfg.T_UPDATE_O0, t_update_ciclo_x0=cfg.T_UPDATE_CICLO_X0,
              params_din_edad_max_min=cfg.PARAMS_DIN_EDAD_MAX_MIN, **extra)
