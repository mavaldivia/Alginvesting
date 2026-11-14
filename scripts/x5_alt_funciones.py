"""
x5_alt_funciones.py

Utilidades compartidas de X5_alt_v2 Fase 2 (parámetros como funciones dinámicas,
ver docs/plans/plan_x5_alt_v2.md). Matemática pura — no depende de Data/MT5, se
puede desarrollar y probar en Mac. Se importa desde X5_Q4.ipynb (una sola
implementación, cada sección de parámetro la reutiliza en vez de reimplementar
la fórmula).

No es un script standalone. Se importa con:
    from x5_alt_funciones import calibrar_parametro
"""

import json

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

import config_smart


class _FenwickRankTree:
    """Árbol de Fenwick sobre coordenadas comprimidas — cuenta prefijo O(log n) por inserción/consulta."""

    def __init__(self, n_valores_unicos: int):
        self._conteo = np.zeros(n_valores_unicos + 1, dtype=np.int64)
        self._n = n_valores_unicos

    def insertar(self, idx: int) -> None:
        idx += 1
        while idx <= self._n:
            self._conteo[idx] += 1
            idx += idx & (-idx)

    def prefijo(self, idx: int) -> int:
        """Suma de conteos en [0, idx] (idx en coordenadas 0-based; -1 → 0)."""
        idx += 1
        total = 0
        while idx > 0:
            total += self._conteo[idx]
            idx -= idx & (-idx)
        return int(total)


def percentil_causal(serie: np.ndarray) -> np.ndarray:
    """
    Percentil histórico de cada punto de `serie`, usando solo s_0..s_t (inclusive) —
    nunca datos futuros (Principio 11, x5_contexto_conversacion.md). Empates resueltos
    por rango promedio (como scipy.stats.rankdata(method='average')).

    percentil_t = rank_promedio(s_t entre s_0..s_t) / (t+1) ∈ (0, 1]
    """
    serie = np.asarray(serie, dtype=float)
    n = len(serie)
    valores_unicos, idx_comprimido = np.unique(serie, return_inverse=True)
    arbol = _FenwickRankTree(len(valores_unicos))

    percentiles = np.empty(n, dtype=float)
    for t in range(n):
        idx = int(idx_comprimido[t])
        arbol.insertar(idx)
        count_leq = arbol.prefijo(idx)
        count_less = arbol.prefijo(idx - 1)
        rank_promedio = (count_less + count_leq) / 2.0
        percentiles[t] = rank_promedio / (t + 1)
    return percentiles


def z_score(x: np.ndarray) -> tuple[np.ndarray, float, float]:
    """z-score con mu/sigma congelados — se recalculan una sola vez al calibrar, no en vivo."""
    x = np.asarray(x, dtype=float)
    mu, sigma = float(np.mean(x)), float(np.std(x))
    if sigma == 0:
        raise ValueError("z_score: desviación estándar nula — variable constante, no sirve como explicativa.")
    return (x - mu) / sigma, mu, sigma


def suavizar_ema(x: np.ndarray, span: float) -> np.ndarray:
    """
    EMA causal (usa solo s_0..s_t, sin leakage — Principio 11 de
    x5_contexto_conversacion.md): s_ema_t = alpha*s_t + (1-alpha)*s_ema_{t-1}.
    `span` en barras (H1 → horas). Ver plan_x5_alt_v2.md sección 3.1 — por qué
    se suaviza el índice compuesto en vez de rate-limitar el parámetro final:
    un EMA corto ya deja pasar movimientos sostenidos (un drawdown real se
    mantiene extremo muchas barras seguidas y el EMA lo alcanza en pocas horas)
    y solo filtra el ruido bar-a-bar de variables como `x3_drawdown_20`, que
    resetea seguido contra su máximo rolling.
    """
    return pd.Series(x).ewm(span=span, adjust=False).mean().to_numpy()


def indice_compuesto(
    variables: list[np.ndarray],
    pesos: list[float] | None = None,
    span_suavizado: float | None = None,
) -> dict:
    """
    Combina 1, 2 o 3 variables explicativas (ya en sus unidades crudas) en un único
    índice de estado s_t = sum(w_i * z_i_t). Restricción deliberada a 1-2 variables
    por parámetro (ver plan_x5_alt_v2.md sección 5 — combinaciones limitadas); la única
    excepción es `N` con 3 (decisión de Mauricio, 2026-11-02), que exige `pesos` explícitos.

    `span_suavizado` (opcional, en barras): aplica `suavizar_ema` sobre s_t antes
    de devolverlo — por defecto (`None`) no suaviza. Regla general de la fase
    (decisión de Mauricio, 2026-10-17): el movimiento de cada parámetro dinámico
    debe ser suave en el tiempo salvo que el estado del activo cambie de forma
    sostenida (ej. una caída fuerte de precio en un día) — un EMA causal corto
    sobre el índice, no un suavizado del parámetro ya calibrado, es el mecanismo
    elegido para cumplir esto en los 5 parámetros de esta fase.
    """
    if len(variables) not in (1, 2, 3):
        raise ValueError(
            "indice_compuesto soporta 1 a 3 variables explicativas por parámetro "
            "(restricción deliberada — ver plan_x5_alt_v2.md sección 5)."
        )
    if len(variables) == 3 and pesos is None:
        raise ValueError("indice_compuesto con 3 variables exige `pesos` explícitos (sin default parejo).")
    zs, normalizacion = [], []
    for x in variables:
        z, mu, sigma = z_score(x)
        zs.append(z)
        normalizacion.append({'mu': mu, 'sigma': sigma})

    if pesos is None:
        pesos = [1.0 / len(variables)] * len(variables)
    pesos = np.asarray(pesos, dtype=float)
    pesos = pesos / pesos.sum()

    s = np.zeros_like(zs[0])
    for w, z in zip(pesos, zs):
        s = s + w * z

    if span_suavizado is not None:
        s = suavizar_ema(s, span_suavizado)

    return {'s': s, 'pesos': pesos.tolist(), 'normalizacion': normalizacion}


def _ajustar_sigmoide(s: np.ndarray, y_objetivo: np.ndarray, piso: float, techo: float) -> dict:
    """Ajusta punto_medio/pendiente de la sigmoide acotada (piso/techo fijos) contra y_objetivo."""
    def f(s_, punto_medio, pendiente):
        return sigmoide_acotada(s_, piso, techo, punto_medio, pendiente)

    p0 = [float(np.median(s)), 1.0]
    (punto_medio, pendiente), _ = curve_fit(f, s, y_objetivo, p0=p0, maxfev=10000)
    y_ajustado = f(s, punto_medio, pendiente)

    ss_res = float(np.sum((y_objetivo - y_ajustado) ** 2))
    ss_tot = float(np.sum((y_objetivo - np.mean(y_objetivo)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float('nan')
    elasticidad = pendiente * (techo - piso) / 4

    return {
        'punto_medio': float(punto_medio),
        'pendiente': float(pendiente),
        'r2': r2,
        'elasticidad_punto_medio': float(elasticidad),
        'y_objetivo': y_objetivo,
        'y_ajustado': y_ajustado,
    }


def sigmoide_acotada(s: np.ndarray, piso: float, techo: float, punto_medio: float, pendiente: float) -> np.ndarray:
    """P̂(s) = piso + (techo - piso) / (1 + exp(-pendiente * (s - punto_medio))) — ver plan_x5_alt_v2.md sección 3.2."""
    return piso + (techo - piso) / (1 + np.exp(-pendiente * (s - punto_medio)))


def calibrar_parametro(
    variables: list[np.ndarray],
    piso: float,
    techo: float,
    grid_pesos: np.ndarray | None = None,
    span_suavizado: float | None = None,
    pesos_fijos: list[float] | None = None,
) -> dict:
    """
    Calibra P̂(x) = sigmoide_acotada(índice_compuesto(variables), piso, techo, ·, ·)
    contra el target sintético por percentil causal (plan_x5_alt_v2.md sección 4).

    Con 1 variable: ajusta (punto_medio, pendiente) directo.
    Con 2 variables: además del ajuste de (punto_medio, pendiente), explora el peso
    w_1 en `grid_pesos` (default linspace(0.1, 0.9, 9)) y se queda con el de mejor R²
    — un peso libre más no se puede ajustar junto con (punto_medio, pendiente) en el
    mismo curve_fit porque el propio target (percentil causal) depende de w_1; se
    resuelve como un perfil de verosimilitud sobre w_1 en vez de un ajuste conjunto.

    `span_suavizado` (opcional, en barras): pasa directo a `indice_compuesto` — el
    ajuste completo (target sintético incluido) se calibra ya sobre el índice
    suavizado, no como un parche posterior sobre `y_ajustado`.

    `pesos_fijos` (opcional): pesos de `indice_compuesto` sin explorar grilla — obligatorio
    con 3 variables (no hay perfil de verosimilitud sobre 2 pesos libres a la vez), válido
    también con 2.

    Devuelve dict con: s, pesos, normalizacion, punto_medio, pendiente, r2,
    elasticidad_punto_medio, y_objetivo, y_ajustado.
    """
    k = len(variables)
    if k == 3 and pesos_fijos is None:
        raise ValueError("calibrar_parametro con 3 variables exige `pesos_fijos`.")
    if k == 1 or pesos_fijos is not None:
        compuesto = indice_compuesto(variables, pesos=pesos_fijos, span_suavizado=span_suavizado)
        s = compuesto['s']
        y_objetivo = piso + (techo - piso) * percentil_causal(s)
        ajuste = _ajustar_sigmoide(s, y_objetivo, piso, techo)
        return {**compuesto, **ajuste}

    if grid_pesos is None:
        grid_pesos = np.linspace(0.1, 0.9, 9)

    mejor = None
    for w1 in grid_pesos:
        compuesto = indice_compuesto(variables, pesos=[w1, 1 - w1], span_suavizado=span_suavizado)
        s = compuesto['s']
        y_objetivo = piso + (techo - piso) * percentil_causal(s)
        ajuste = _ajustar_sigmoide(s, y_objetivo, piso, techo)
        if mejor is None or ajuste['r2'] > mejor['r2']:
            mejor = {**compuesto, **ajuste}
    return mejor


# ─── Q5: serie causal de cada C1 a partir de sus C2 (plan_x5_alt_v2.md 9.0-9.4, 9.12) ───────────

MIN_OBS_Z = 30  # observaciones mínimas para que la ventana expansiva entregue un z-score; antes, z = 0 (neutro)
_TRANSFORMACIONES = ('identidad', 'ln_razon', 'abs')
_CLAVE_Q5 = {'PERDIDA_MAX': 'PERDIDA_MAX_PCT'}  # en el backtesting inteligente PERDIDA_MAX es la fracción p de Z


def cargar_estructura_c1(ruta) -> dict:
    """Lee `config/estructura_c1.json` (variables de cada C1; ver su `_comentario`). Valida lo que la función usa."""
    with open(ruta, encoding='utf-8') as f:
        estructura = {k: v for k, v in json.load(f).items() if not k.startswith('_')}
    for c1, entrada in estructura.items():
        nombres = [v['nombre'] for v in entrada['variables']]
        if len(set(nombres)) != len(nombres):
            raise ValueError(f"estructura {c1}: nombres de variable repetidos {nombres}")
        for v in entrada['variables']:
            if v['transformacion'] not in _TRANSFORMACIONES:
                raise ValueError(f"estructura {c1}.{v['nombre']}: transformacion '{v['transformacion']}' no soportada")
            if v['signo'] not in (1, -1):
                raise ValueError(f"estructura {c1}.{v['nombre']}: signo debe ser 1 o -1")
    return estructura


def _columna_variable(tabla: pd.DataFrame, variable: dict) -> np.ndarray:
    cols = [tabla[c].to_numpy(dtype=float) for c in variable['columnas']]
    t = variable['transformacion']
    if t == 'identidad':
        x = cols[0]
    elif t == 'abs':
        x = np.abs(cols[0])
    else:  # ln_razon
        x = np.log(cols[0] / cols[1])
    return variable['signo'] * x


def z_expanding(x: np.ndarray, min_obs: int = MIN_OBS_Z) -> np.ndarray:
    """
    z-score causal con ventana expansiva: en cada t usa solo x_0..x_t (inclusive) para la media y la
    desviación estándar (ddof=0), a diferencia de `z_score`, que usa toda la serie (look-ahead). Con menos
    de `min_obs` observaciones válidas o desviación nula entrega 0; un x_t sin dato (NaN) entrega NaN.
    """
    s = pd.Series(np.asarray(x, dtype=float))
    media = s.expanding(min_periods=min_obs).mean()
    desv = s.expanding(min_periods=min_obs).std(ddof=0)
    z = ((s - media) / desv).where(desv > 0, 0.0)
    z[s.isna()] = np.nan
    return z.to_numpy()


def redondear_a_grilla(x, piso: float, techo: float, paso: float) -> np.ndarray:
    """Lleva x al valor permitido más cercano de la grilla `piso + k * paso` (plan 9.4); ej. N acciones (40, 180, 10): 52.33 -> 50."""
    x = np.asarray(x, dtype=float)
    k = np.floor((x - piso) / paso + 0.5)
    return np.round(np.clip(piso + k * paso, piso, techo), 10)


def perdida_max_usd(p: float, z: float) -> float:
    """Umbral de pérdida por orden abierta: p * Z (plan 9.3). Con Z < 0 el umbral es 0 (confirmado en Q5-3)."""
    return p * max(z, 0.0)


def lotajes_m(z: float) -> int:
    """Múltiplo del lote mínimo según Z = cerrado + P&L abierto (plan 9.3): max(1, (Z - 6000) // 3000 + 2).

    Z = 3000 -> 1; 5999 -> 1; 6000 -> 2; 8999 -> 2; 9000 -> 3; 12000 -> 4. Con Z negativo queda en 1."""
    cuenta = config_smart.CUENTA
    return max(1, int((z - cuenta['z_base_lote']) // cuenta['paso_lote']) + 2)


def premios_por_tramo(equity, fraccion_reservada: float) -> dict:
    """
    Premio de cada tramo de una vuelta a partir de la curva de Z vela a vela (plan 9.5 y 9.6). El corte es por
    número de velas: las primeras `corte = int(n * (1 - fraccion_reservada))` son el tramo de aprendizaje.

    premio_aprendizaje = Z al corte / velas hasta el corte
    premio_reservado   = (Z final - Z al corte) / velas del tramo reservado

    Ej. con 42.000 velas y fraccion 0.2: corte = 33.600; Z al corte 4.200 -> 0.125; Z final 4.500 -> 0.0357.
    """
    z = np.asarray(equity, dtype=float)
    if np.isnan(z).any():
        raise ValueError('premios_por_tramo: la curva de Z tiene NaN')
    n = len(z)
    corte = int(n * (1 - fraccion_reservada))
    if corte < 1 or n - corte < 1:
        raise ValueError(f'premios_por_tramo: {n} velas no alcanzan para dos tramos con fraccion {fraccion_reservada}')
    z_corte, z_final = float(z[corte - 1]), float(z[-1])
    return {'corte': corte, 'z_corte': z_corte, 'z_final': z_final,
            'premio_aprendizaje': z_corte / corte, 'premio_reservado': (z_final - z_corte) / (n - corte)}


def drawdown_maximo(equity, capital_inicial: float) -> tuple:
    """(pct, usd) de la peor caída de Z desde su máximo previo, ambos <= 0; el capital inicial cuenta como primer punto."""
    z = np.r_[float(capital_inicial), np.asarray(equity, dtype=float)]
    caida = z - np.maximum.accumulate(z)
    pct = caida / np.maximum.accumulate(z)  # el máximo previo es >= capital_inicial > 0
    return float(pct.min()), float(caida.min())


def estadisticas_c1(serie, piso: float, techo: float) -> dict:
    """Resumen de un C1 durante una vuelta (plan 9.13): media, desviación, extremos, % de velas en piso y en techo,
    y cuántos valores distintos de la grilla usó (un C1 pegado al piso/techo o casi constante está mal calibrado)."""
    s = np.asarray(serie, dtype=float)
    return {'media': float(s.mean()), 'std': float(s.std()), 'min': float(s.min()), 'max': float(s.max()),
            'pct_piso': float(100 * np.isclose(s, piso).mean()), 'pct_techo': float(100 * np.isclose(s, techo).mean()),
            'pasos': int(len(np.unique(np.round(s, 10))))}


def serie_c1(
    parametro: str,
    valor: str,
    c2: dict,
    tabla: pd.DataFrame,
    estructura: dict,
    normalizacion: str = 'expanding',
    mu_sigma: dict | None = None,
    rango: tuple | None = None,
    redondear: bool = True,
) -> dict:
    """
    Serie vela a vela de un C1 (`parametro`) para `valor`, dados sus C2 y la tabla de estado de Q1.

    c2: {'pesos': {nombre_variable: w_i}, 'span': int, 'punto_medio': float, 'pendiente': float}.
        Variable de la estructura sin peso en `pesos` o con `activa: false` -> w = 0; los pesos se
        normalizan `w̃_i = w_i / Σ w_j`. `span` se redondea a entero >= 1.
    normalizacion: 'expanding' (por defecto, causal) o 'fija' (con `mu_sigma` {nombre: (mu, sigma)}; solo
        para reproducir Q4, que usa mu/sigma de todo el histórico).
    rango: (piso, techo); por defecto el de `config_smart` (para PERDIDA_MAX, el de PERDIDA_MAX_PCT).
    redondear: lleva el C1 a la grilla de `config_smart.paso` (la serie sin redondear va siempre en 'c1_sin_redondeo').

    Devuelve {'s': índice suavizado, 'c1_sin_redondeo', 'c1', 'pesos': {nombre: w̃}}. Mismas filas que `tabla`;
    los NaN de variables sin dato (inicio de ventanas) pasan como NaN.
    """
    variables = estructura[parametro]['variables']
    pesos_c2 = c2['pesos']
    desconocidas = set(pesos_c2) - {v['nombre'] for v in variables}
    if desconocidas:
        raise ValueError(f"{parametro}: pesos para variables que no están en la estructura: {sorted(desconocidas)}")
    w = np.array([float(pesos_c2.get(v['nombre'], 0.0)) if v['activa'] else 0.0 for v in variables])
    if w.sum() <= 0:
        raise ValueError(f"{parametro}: todos los pesos son 0")
    w_norm = w / w.sum()

    s = np.zeros(len(tabla))
    for wi, v in zip(w_norm, variables):
        if wi == 0:
            continue
        x = _columna_variable(tabla, v)
        if normalizacion == 'expanding':
            z = z_expanding(x)
        elif normalizacion == 'fija':
            mu, sigma = mu_sigma[v['nombre']]
            z = (x - mu) / sigma
        else:
            raise ValueError(f"normalizacion '{normalizacion}' no soportada")
        s = s + wi * z

    span = max(1, int(round(c2['span'])))
    s = suavizar_ema(s, span)

    clave = _CLAVE_Q5.get(parametro, parametro)
    piso, techo = rango if rango is not None else config_smart.rango(clave, valor)
    sin_redondeo = sigmoide_acotada(s, piso, techo, c2['punto_medio'], c2['pendiente'])
    c1 = redondear_a_grilla(sin_redondeo, piso, techo, config_smart.paso(clave, valor)) if redondear else sin_redondeo
    return {
        's': s,
        'c1_sin_redondeo': sin_redondeo,
        'c1': c1,
        'pesos': {v['nombre']: float(wi) for v, wi in zip(variables, w_norm)},
    }


def cargar_c2_q4(ruta_resumen_csv) -> dict:
    """
    C2 que calibró Q4 de cada C1, desde `{valor}_q4_resumen.csv`: {C1: {'pesos': {nombre: w}, 'span', 'punto_medio',
    'pendiente', 'mu_sigma': {nombre: (mu, sigma)}}}. Son el punto de partida de Q5 y la base de `rangos_sorteo_c2`.
    """
    resumen = pd.read_csv(ruta_resumen_csv)
    c2 = {}
    for _, fila in resumen.iterrows():
        nombres = json.loads(fila['variables'])
        pesos = json.loads(fila['pesos'])
        norm = json.loads(fila['normalizacion'])
        c2[fila['parametro']] = {
            'pesos': dict(zip(nombres, pesos)),
            'span': int(fila['span_suavizado']),
            'punto_medio': float(fila['punto_medio']),
            'pendiente': float(fila['pendiente']),
            'mu_sigma': {n: (m['mu'], m['sigma']) for n, m in zip(nombres, norm)},
        }
    return c2


def rangos_sorteo_c2(c2_base: dict) -> dict:
    """
    Rango del sorteo Sobol de los C2 de un C1 cerca de su calibración `c2_base` (reglas en `config_smart.SORTEO_C2`).
    Devuelve {'pesos': {nombre: (min, max)}, 'span': (min, max), 'punto_medio': (min, max), 'pendiente': (min, max)}.
    Un C1 con una sola variable no sortea su peso (queda en (1, 1)); una variable sin peso base queda en (0, 0).
    """
    cfg = config_smart.SORTEO_C2
    pesos_base = c2_base['pesos']
    una_variable = sum(1 for w in pesos_base.values() if w > 0) == 1
    pesos = {}
    for nombre, w in pesos_base.items():
        if w <= 0:
            pesos[nombre] = (0.0, 0.0)
        elif una_variable:
            pesos[nombre] = (1.0, 1.0)
        else:
            pesos[nombre] = (max(cfg['peso_min'], w - cfg['peso_delta']), min(1.0, w + cfg['peso_delta']))
    pm, pe = c2_base['punto_medio'], c2_base['pendiente']
    extremos_pe = sorted((pe / cfg['pendiente_factor'], pe * cfg['pendiente_factor']))
    return {
        'pesos': pesos,
        'span': tuple(cfg['span']),
        'punto_medio': (pm - cfg['punto_medio_delta'], pm + cfg['punto_medio_delta']),
        'pendiente': tuple(extremos_pe),
    }
