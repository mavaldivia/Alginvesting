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

import numpy as np
from scipy.optimize import curve_fit


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


def indice_compuesto(variables: list[np.ndarray], pesos: list[float] | None = None) -> dict:
    """
    Combina 1 o 2 variables explicativas (ya en sus unidades crudas) en un único
    índice de estado s_t = sum(w_i * z_i_t). Restricción deliberada a 1-2 variables
    por parámetro (ver plan_x5_alt_v2.md sección 5 — combinaciones limitadas).
    """
    if len(variables) not in (1, 2):
        raise ValueError(
            "indice_compuesto soporta 1 o 2 variables explicativas por parámetro "
            "(restricción deliberada — ver plan_x5_alt_v2.md sección 5)."
        )
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

    Devuelve dict con: s, pesos, normalizacion, punto_medio, pendiente, r2,
    elasticidad_punto_medio, y_objetivo, y_ajustado.
    """
    k = len(variables)
    if k == 1:
        compuesto = indice_compuesto(variables)
        s = compuesto['s']
        y_objetivo = piso + (techo - piso) * percentil_causal(s)
        ajuste = _ajustar_sigmoide(s, y_objetivo, piso, techo)
        return {**compuesto, **ajuste}

    if grid_pesos is None:
        grid_pesos = np.linspace(0.1, 0.9, 9)

    mejor = None
    for w1 in grid_pesos:
        compuesto = indice_compuesto(variables, pesos=[w1, 1 - w1])
        s = compuesto['s']
        y_objetivo = piso + (techo - piso) * percentil_causal(s)
        ajuste = _ajustar_sigmoide(s, y_objetivo, piso, techo)
        if mejor is None or ajuste['r2'] > mejor['r2']:
            mejor = {**compuesto, **ajuste}
    return mejor
