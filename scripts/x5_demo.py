"""
x5_demo.py

Narrador guiado del modo `X5 --recolectar --demo` (un solo activo).

Se comparte entre X5 (orquestador) y X4 (backtest, corre como subproceso). Cada
suceso relevante del pipeline tiene un ID único (D01..D10). La PRIMERA vez
que aparece un ID se imprime una explicación detallada de qué se hizo y se pausa
(Enter). Las veces siguientes ese mismo evento no vuelve a imprimirse ni a
pausar.

Cuando ya se mostraron todos los eventos del BUCLE RECURRENTE (recálculo de
soportes, gráfico de la búsqueda, elección de params EXPLORE, OE creadas, OA
abiertas, OC cerradas y avance de mes) se anuncia que ese comportamiento se
repetirá hasta la
convergencia; desde ahí solo los HITOS nuevos (EXPLOIT con modelo,
entrenamiento, convergencia) vuelven a pausar.

El estado de qué IDs ya se explicaron vive en un JSON por activo
(resources/x5/{ACTIVO}_demo_state.json) para sobrevivir entre el proceso X5 y
los sucesivos subprocesos X4: si el demo se pausa y se reanuda, no se re-explica
lo ya visto.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import config as cfg

_ANCHO = 66
_LINEA = '─' * _ANCHO
_DOBLE = '═' * _ANCHO

# categoria: 'recurrente' (se repite cada ciclo) | 'hito' (aparece una vez / tarde)
# (categoria, titulo, [parrafos])
EVENTOS: dict[str, tuple] = {
    'D01': ('recurrente', 'Recálculo de soportes (cold start / periódico)', [
        'Se re-optimizaron DESDE CERO los soportes del activo usando los '
        'parámetros vigentes del tramo (K, N_EXP, LAMBDA). Ocurre en dos '
        'momentos: al iniciar el ciclo (cold start, sobre todo el histórico '
        'hasta la fecha de inicio) y luego cada delta_recalculo_soportes días '
        'dentro del backtest.',
        'Cada recálculo descarta el cache anterior para no heredar soportes '
        'calculados con parámetros viejos: los soportes siempre reflejan los '
        'params del momento.',
    ]),
    'D02': ('recurrente', 'EXPLORE — params aleatorios del tramo', [
        'El motor eligió los parámetros AL AZAR dentro de los rangos '
        'permitidos (X5_PARAM_RANGES): n_sizes, K, N_EXP, LAMBDA, A, B, '
        'LOTAJES_M y PERDIDA_MAX.',
        'Se hace EXPLORE cuando todavía no hay modelo entrenado, o con '
        'probabilidad EXPLORATION_RATE aunque exista modelo. Así se genera '
        'variedad causal en el store y se evita el sesgo de selección de '
        'entrenar siempre sobre los mismos params.',
    ]),
    'D03': ('recurrente', 'OE creada — Orden en Espera (buy limit)', [
        'Se colocó una Orden en Espera (OE): un buy limit en un soporte, '
        'esperando que el precio BAJE hasta ese nivel para comprar.',
        'Solo se crea si el soporte está suficientemente lejos del precio '
        'actual (distancia >= A) y queda margen libre suficiente en la cuenta.',
    ]),
    'D04': ('recurrente', 'OA abierta — la OE se ejecutó (posición activa)', [
        'El precio tocó el nivel de una OE y ésta se ejecutó: pasó a ser una '
        'Orden Abierta (OA), una posición de compra viva.',
        'Desde acá la posición puede subir (activando el trailing stop que '
        'protege ganancias) o bajar (arriesgando el cierre por PERDIDA_MAX).',
    ]),
    'D05': ('recurrente', 'OC cerrada — se agregó una fila al store de X5', [
        'Una posición se cerró (Orden Cerrada, OC) por trailing stop o por '
        'superar PERDIDA_MAX.',
        'Al cerrarse se construye una fila con TODO el contexto (features X2 '
        'fundamentales, X3 técnicas, portfolio y los params del tramo) más el '
        'retorno realizado, y se agrega al store del activo. Ese store es '
        'exactamente lo que después entrena al modelo de X5.',
    ]),
    'D06': ('hito', 'EXPLOIT — inferencia con el modelo (as-of-t)', [
        'Por PRIMERA vez el motor NO eligió params al azar: usó el modelo '
        'entrenado para INFERIR los mejores params dado el contexto de mercado '
        'al día simulado t (as-of-t, sin mirar el futuro).',
        'Esto ocurre con probabilidad (1 - EXPLORATION_RATE) una vez que el '
        'store cruzó el umbral de entrenamiento y el modelo ya existe. Marca la '
        'transición de exploración pura a explotación del modelo.',
    ]),
    'D07': ('recurrente', 'Avance de mes en el backtest', [
        'El backtest terminó de procesar un mes calendario del histórico y '
        'avanzó al siguiente. X4 emite un marcador [MES_BT] por cada mes '
        'completado; es solo una señal de progreso temporal del backtest.',
    ]),
    'D08': ('hito', 'Umbral de entrenamiento cruzado → se entrena el modelo', [
        'El store del activo alcanzó el mínimo de OC para entrenar '
        '(X5_MIN_TRADES_TRAIN). Se entrena/reentrena el modelo: LightGBM '
        'primero y FT-Transformer al cruzar X5_MIN_TRADES_FTT.',
        'Desde el próximo ciclo, los tramos EXPLOIT ya usan este modelo recién '
        'entrenado: los params se van corrigiendo con lo aprendido.',
    ]),
    'D10': ('recurrente', 'Gráfico de soportes/resistencias de esta búsqueda', [
        'Cada vez que se recalculan los soportes se guarda un PNG con los precios '
        'que alimentaron la búsqueda (de t0 a tf, donde tf es el t simulado del '
        'backtest) y los N niveles encontrados sobre ellos.',
        'Los niveles bajo el precio de tf se dibujan en verde (soportes: ahí se '
        'colocan los buy limit) y los que quedan sobre él en rojo (resistencias). '
        'La línea negra es el precio en tf. El archivo queda en '
        'resources/x5/demo_plots/{ACTIVO}/ con el ciclo, el N y el t en el nombre, '
        'así que puedes revisar después cómo se movieron los soportes tramo a tramo.',
    ]),
    'D09': ('hito', 'Convergencia — fin del demo', [
        'El demo terminó: el activo alcanzó el umbral de OC objetivo o se '
        'agotaron los ciclos configurados (N_CICLOS_BT).',
        'El store demo y el modelo demo quedaron aislados de los datos reales '
        '(sufijo _demo), así que nada de esto tocó tu store de producción.',
    ]),
}

RECURRENTES = {eid for eid, (cat, *_) in EVENTOS.items() if cat == 'recurrente'}


def _envolver(txt: str) -> str:
    return textwrap.fill(txt, width=_ANCHO + 4,
                         initial_indent='  ', subsequent_indent='  ')


def _fmt_datos(datos: dict) -> str:
    partes = []
    for k, v in datos.items():
        if isinstance(v, float):
            v = f'{v:.4f}'
        partes.append(f'{k}={v}')
    return '  '.join(partes)


class DemoNarrator:
    def __init__(self, activo: str):
        self.activo = activo
        self.path = cfg.CARPETA_X5 / f'{activo}_demo_state.json'
        self.seen: set[str] = set()
        self.announced = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text())
            self.seen = set(d.get('seen', []))
            self.announced = bool(d.get('announced', False))
        except Exception:
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(
            {'activo': self.activo, 'seen': sorted(self.seen),
             'announced': self.announced}, indent=2))
        tmp.replace(self.path)

    def reset(self) -> None:
        self.seen = set()
        self.announced = False
        if self.path.exists():
            self.path.unlink()

    def progreso(self) -> tuple[int, int]:
        return len(self.seen), len(EVENTOS)

    def evento(self, eid: str, **datos) -> None:
        if eid in self.seen or eid not in EVENTOS:
            return
        self._load()  # otro proceso (X4/X5) pudo haberlo visto ya
        if eid in self.seen:
            return
        self._explicar(eid, datos)
        self.seen.add(eid)
        self._save()
        self._pausa(f'  Presiona Enter para continuar (evento {eid})...')
        if not self.announced and RECURRENTES <= self.seen:
            self.announced = True
            self._save()
            self._anunciar_repeticion()

    def _explicar(self, eid: str, datos: dict) -> None:
        cat, titulo, parrafos = EVENTOS[eid]
        etiqueta = 'HITO' if cat == 'hito' else 'evento recurrente'
        print()
        print(_LINEA)
        print(f'  [{eid}] {titulo}')
        print(f'  ({etiqueta} — primera aparición)')
        print(_LINEA)
        for i, p in enumerate(parrafos):
            if i:
                print()
            print(_envolver(p))
        if datos:
            print(f'\n  Datos: {_fmt_datos(datos)}')
        print()
        sys.stdout.flush()

    def _anunciar_repeticion(self) -> None:
        print()
        print(_DOBLE)
        print('  Ya viste todos los eventos del BUCLE RECURRENTE de X5:')
        print('  recálculo de soportes (con su gráfico), elección de params')
        print('  (EXPLORE), OE creadas, OA abiertas, OC cerradas y avance de mes.')
        print()
        print('  Este comportamiento se repetirá durante las siguientes')
        print('  iteraciones hasta la convergencia. Desde aquí ya NO se pausará')
        print('  en cada repetición: el demo solo se detendrá cuando aparezca')
        print('  un HITO nuevo (EXPLOIT con modelo, entrenamiento, convergencia).')
        print(_DOBLE)
        sys.stdout.flush()
        self._pausa('  Presiona Enter para continuar sin pausas...')

    @staticmethod
    def _pausa(msg: str) -> None:
        if not sys.stdin or not sys.stdin.isatty():
            return
        try:
            input(msg)
        except EOFError:
            pass


# ─── API de módulo (singleton) ────────────────────────────────────────────────

_NARRATOR: DemoNarrator | None = None


def activar(activo: str) -> DemoNarrator:
    global _NARRATOR
    _NARRATOR = DemoNarrator(activo)
    return _NARRATOR


def esta_activo() -> bool:
    return _NARRATOR is not None


def evento(eid: str, **datos) -> None:
    if _NARRATOR is not None:
        _NARRATOR.evento(eid, **datos)


def abrir_archivo(ruta) -> None:
    """Abre un archivo generado por el demo (gráficos) en el visor del sistema.

    Best-effort: si no hay entorno gráfico o el visor falla, el archivo igual quedó
    guardado y su ruta ya se imprimió."""
    if _NARRATOR is None or not getattr(cfg, 'X5_DEMO_ABRIR_PLOTS', True):
        return
    ruta = str(ruta)
    if ruta.startswith('ERROR'):
        return
    try:
        if sys.platform.startswith('win'):
            os.startfile(ruta)  # noqa: S606 — visor por defecto de Windows
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', ruta], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(['xdg-open', ruta], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except Exception:
        pass
