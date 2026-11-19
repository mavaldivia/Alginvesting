"""
x5_alt_aprendizaje.py

Aprendizaje por ventanas semanales de Q5-5 (docs/plans/plan_x5_alt_v2.md, 9.14): Regresión Lineal Múltiple (RLM) con
ridge de `Y` sobre los C2 de cada ventana, con `ret_medio` y `ret_vol` como controles aditivos (decidido 2026-11-19:
`Y = f(C2) + g(ret_medio, ret_vol)`), y un paso de Gradient Ascent sobre los C2. Matemática pura sobre el DataFrame de
`{valor}_ventanas.csv` ya filtrado a las ventanas que entran al aprendizaje: no toca MT5 ni X4, se prueba offline
(test_x5_alt_aprendizaje.py). La orquestación vive en X4_bckt_ventanas.py.

Los pesos de cada C1 se regresan como `w̃_i = w_i / Σ w_j`, omitiendo uno por grupo (con `Σ w̃ = 1` el último es
redundante y haría singular la regresión); las columnas constantes (un C1 de una variable, un peso en 0) no entran.
"""

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

import config_smart
from x5_alt_funciones import rangos_sorteo_c2

CONTROLES = ('ret_medio', 'ret_vol')
CAMPOS_ESCALARES = ('span', 'punto_medio', 'pendiente')
_PATRON_C2 = re.compile(r'^c2_(?P<c1>.+?)_(?:w_(?P<variable>.+)|(?P<campo>span|punto_medio|pendiente))$')
_TOL = 1e-12


# ─── Matriz de regresores ─────────────────────────────────────────────────────

def parsear_columnas_c2(columnas) -> dict:
    """{c1: {'pesos': {variable: columna}, 'campos': {campo: columna}}} desde las columnas `c2_*` de `_ventanas.csv`."""
    grupos = {}
    for col in columnas:
        m = _PATRON_C2.match(col)
        if m is None:
            continue
        g = grupos.setdefault(m['c1'], {'pesos': {}, 'campos': {}})
        if m['variable'] is not None:
            g['pesos'][m['variable']] = col
        else:
            g['campos'][m['campo']] = col
    return grupos


def _pesos_normalizados(df: pd.DataFrame, columnas: dict) -> pd.DataFrame:
    crudos = df[list(columnas.values())].fillna(0.0)
    crudos.columns = list(columnas)
    return crudos.div(crudos.sum(axis=1), axis=0)


def terminos_modelo(df: pd.DataFrame) -> tuple:
    """(regresores C2, peso omitido por C1). Un término es `('peso', c1, variable)` o `(campo, c1, None)`. Solo entran los
    que varían en `df`; de los pesos que varían se omite el último de cada C1."""
    terminos, omitidas = [], {}
    for c1, g in parsear_columnas_c2(df.columns).items():
        w = _pesos_normalizados(df, g['pesos'])
        vivos = [v for v in w.columns if w[v].std(ddof=0) > _TOL]
        if len(vivos) >= 2:
            terminos += [('peso', c1, v) for v in vivos[:-1]]
            omitidas[c1] = vivos[-1]
        terminos += [(campo, c1, None) for campo in CAMPOS_ESCALARES
                     if campo in g['campos'] and df[g['campos'][campo]].std(ddof=0) > _TOL]
    return terminos, omitidas


def nombre_termino(termino: tuple) -> str:
    campo, c1, variable = termino
    return f'{c1}_w_{variable}' if campo == 'peso' else f'{c1}_{campo}'


def matriz_c2(df: pd.DataFrame, terminos: list) -> np.ndarray:
    """Valores de los regresores C2 de cada ventana (filas) en el orden de `terminos`."""
    grupos = parsear_columnas_c2(df.columns)
    pesos = {c1: _pesos_normalizados(df, grupos[c1]['pesos']) for c1 in {t[1] for t in terminos if t[0] == 'peso'}}
    cols = [pesos[c1][variable].to_numpy(float) if campo == 'peso' else df[f'c2_{c1}_{campo}'].to_numpy(float)
            for campo, c1, variable in terminos]
    return np.column_stack(cols)


def vector_c2(c2: dict, terminos: list) -> np.ndarray:
    """Regresores C2 de un diccionario de C2 (`{c1: {'pesos', 'span', 'punto_medio', 'pendiente'}}`)."""
    x = []
    for campo, c1, variable in terminos:
        if campo == 'peso':
            pesos = c2[c1]['pesos']
            x.append(pesos[variable] / sum(pesos.values()))
        else:
            x.append(float(c2[c1][campo]))
    return np.array(x)


def c2_desde_fila(fila: pd.Series) -> dict:
    """C2 completos que corrió una ventana, desde sus columnas `c2_*` de `_ventanas.csv` (un peso vacío vale 0)."""
    def valor(col):
        return 0.0 if pd.isna(fila[col]) else float(fila[col])
    return {c1: {'pesos': {v: valor(col) for v, col in g['pesos'].items()}, 'span': int(round(valor(g['campos']['span']))),
                 'punto_medio': valor(g['campos']['punto_medio']), 'pendiente': valor(g['campos']['pendiente'])}
            for c1, g in parsear_columnas_c2(fila.index).items()}


# ─── RLM con ridge ────────────────────────────────────────────────────────────

def _expandir(z: np.ndarray, p: int, grado: int) -> np.ndarray:
    """Regresores estandarizados `z` (p de C2 y luego los controles) más, en grado 2, los productos cruzados entre C2
    (sin cuadrados y sin controles: el mercado de la semana entra solo de forma aditiva)."""
    if grado == 1:
        return z
    i, j = np.triu_indices(p, k=1)
    return np.column_stack([z, z[:, i] * z[:, j]])


@dataclass
class Modelo:
    terminos: list
    omitidas: dict
    grado: int
    alpha: float
    r2_cv: float
    n: int
    escalador: StandardScaler
    ridge: Ridge

    def predecir(self, x_c2: np.ndarray) -> float:
        """`Y` predicho para unos C2, con los controles en su media (el término aditivo no cambia entre candidatos)."""
        p = len(self.terminos)
        x = np.r_[np.asarray(x_c2, dtype=float), self.escalador.mean_[p:]]
        z = self.escalador.transform(x[None, :])
        return float(self.ridge.predict(_expandir(z, p, self.grado))[0])

    def coeficientes(self) -> dict:
        """Coeficientes de primer orden sobre variables estandarizadas, comparables entre sí (los cruzados del grado 2
        no se listan)."""
        nombres = [nombre_termino(t) for t in self.terminos] + list(CONTROLES)
        return dict(zip(nombres, (float(c) for c in self.ridge.coef_[:len(nombres)])))


def ajustar_rlm(df: pd.DataFrame, grado: int | None = None) -> Modelo:
    """Ajusta `Y` sobre los C2 y los controles de las ventanas de `df`. La penalización ridge se elige por validación
    cruzada de `PLIEGUES_CV` pliegues y `r2_cv` es el R² fuera de pliegue con esa penalización: ≈ 0 o negativo significa
    que los C2 aún no explican `Y` mejor que su media."""
    grado = config_smart.GRADO if grado is None else grado
    df = df.dropna(subset=['Y', *CONTROLES]).reset_index(drop=True)
    if len(df) < 2 * config_smart.PLIEGUES_CV:
        raise ValueError(f'{len(df)} ventanas: se necesitan al menos {2 * config_smart.PLIEGUES_CV} para ajustar la RLM')
    terminos, omitidas = terminos_modelo(df)
    p = len(terminos)
    x = np.column_stack([matriz_c2(df, terminos), df[list(CONTROLES)].to_numpy(float)])
    y = df['Y'].to_numpy(float)
    escalador = StandardScaler().fit(x)
    f = _expandir(escalador.transform(x), p, grado)
    cv = KFold(config_smart.PLIEGUES_CV, shuffle=True, random_state=config_smart.SEMILLA_CV)
    alpha = float(RidgeCV(alphas=config_smart.ALPHAS_RIDGE, cv=cv).fit(f, y).alpha_)
    fuera = cross_val_predict(Ridge(alpha=alpha), f, y, cv=cv)
    r2_cv = 1.0 - float(((y - fuera) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    return Modelo(terminos, omitidas, grado, alpha, r2_cv, len(df), escalador, Ridge(alpha=alpha).fit(f, y))


# ─── Gradient Ascent ──────────────────────────────────────────────────────────

def gradiente(modelo: Modelo, x0: np.ndarray) -> np.ndarray:
    """Derivada de `Y` predicho respecto de cada regresor C2 (unidades originales) en `x0`, por diferencias centrales:
    sirve igual en grado 1 (son los coeficientes) y en grado 2 (depende del punto)."""
    h = modelo.escalador.scale_[:len(x0)] * 1e-3
    g = np.empty(len(x0))
    for j in range(len(x0)):
        arriba, abajo = x0.copy(), x0.copy()
        arriba[j] += h[j]
        abajo[j] -= h[j]
        g[j] = (modelo.predecir(arriba) - modelo.predecir(abajo)) / (2 * h[j])
    return g


def _limites_pesos(pesos_caja: dict) -> dict:
    """Intervalo alcanzable de `w̃_j` cuando cada peso crudo `w_i` está en su caja `(lo_i, hi_i)` de `rangos_sorteo_c2`."""
    limites = {}
    for j, (lo, hi) in pesos_caja.items():
        otros_lo = sum(l for i, (l, _) in pesos_caja.items() if i != j)
        otros_hi = sum(h for i, (_, h) in pesos_caja.items() if i != j)
        limites[j] = (lo / (lo + otros_hi) if lo + otros_hi > 0 else 0.0,
                      hi / (hi + otros_lo) if hi + otros_lo > 0 else 0.0)
    return limites


def limites_c2(c2_base: dict) -> tuple:
    """(rangos de sorteo de `rangos_sorteo_c2` por C1, intervalo alcanzable de `w̃` de cada variable por C1)."""
    rangos = {c1: rangos_sorteo_c2(c2) for c1, c2 in c2_base.items()}
    return rangos, {c1: _limites_pesos(r['pesos']) for c1, r in rangos.items()}


def proponer_c2(modelo: Modelo, c2_actual: dict, c2_base: dict, paso: float | None = None) -> dict:
    """Un paso de Gradient Ascent desde `c2_actual`: el regresor de mayor efecto sobre `Y` (derivada × rango) se mueve
    `paso` de su rango y los demás en proporción a su efecto, así los de efecto casi nulo apenas se mueven. Cada regresor
    se recorta a su rango de sorteo (`c2_base` es la calibración de Q4), los pesos de cada C1 se renormalizan a suma 1 y
    `span` se redondea a entero. Devuelve C2 completos; los C1 sin regresores libres quedan como estaban."""
    paso = config_smart.PASO_GRADIENTE if paso is None else paso
    rangos, limites_w = limites_c2(c2_base)
    limites = np.array([limites_w[c1][variable] if campo == 'peso' else rangos[c1][campo]
                        for campo, c1, variable in modelo.terminos], dtype=float)
    x0 = vector_c2(c2_actual, modelo.terminos)
    ancho = limites[:, 1] - limites[:, 0]
    efecto = gradiente(modelo, x0) * ancho
    mayor = np.abs(efecto).max()
    x1 = x0 if mayor <= 0 else np.clip(x0 + paso * ancho * efecto / mayor, limites[:, 0], limites[:, 1])
    return _c2_desde_vector(x1, modelo, c2_actual, limites_w)


def _c2_desde_vector(x: np.ndarray, modelo: Modelo, c2_actual: dict, limites_w: dict) -> dict:
    """C2 completos a partir de los regresores `x`: el peso omitido de cada C1 es lo que falta para sumar 1; luego todos
    los pesos se recortan a su intervalo y se renormalizan."""
    valores = dict(zip(modelo.terminos, x))
    nuevo = {c1: {'pesos': dict(c['pesos']), 'span': c['span'], 'punto_medio': c['punto_medio'],
                  'pendiente': c['pendiente']} for c1, c in c2_actual.items()}
    for c1, c in nuevo.items():
        for campo in CAMPOS_ESCALARES:
            if (campo, c1, None) in valores:
                v = valores[(campo, c1, None)]
                c[campo] = int(round(v)) if campo == 'span' else float(v)
        if c1 in modelo.omitidas:
            total = sum(c['pesos'].values())
            w = {v: p / total for v, p in c['pesos'].items()}
            w.update({t[2]: valores[t] for t in modelo.terminos if t[0] == 'peso' and t[1] == c1})
            omitida = modelo.omitidas[c1]
            w[omitida] = 1.0 - sum(p for v, p in w.items() if v != omitida)
            w = {v: float(np.clip(p, *limites_w[c1][v])) for v, p in w.items()}
            suma = sum(w.values())
            c['pesos'] = {v: p / suma for v, p in w.items()}
    return nuevo
