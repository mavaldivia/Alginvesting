"""
X3_technical_features.py

Genera features técnicas incrementales (indicadores de precio/volumen) para cada activo.
Llamado desde X0 tras descargar datos H1.
Output: resources/x3/{valor}.csv  (columna datetime + una columna por feature)

No es un script standalone. Se importa y llama con:
    from X3_technical_features import actualizar_features
    actualizar_features(valor, df_ohlcv, conjunto_N)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import CARPETA_FEATURES, X3_VENTANAS


# ─── Indicadores técnicos (internos) ─────────────────────────────────────────

def _wilder_ema(series: pd.Series, w: int) -> pd.Series:
    """EMA de Wilder: alpha = 1/w, adjust=False (idéntico a Wilder 1978)."""
    return series.ewm(alpha=1.0 / w, adjust=False).mean()


def _calcular_sma(close: pd.Series, ventanas: list) -> dict:
    out = {}
    for w in ventanas:
        sma = close.rolling(w).mean()
        out[f'sma_{w}'] = sma
        out[f'sma_dist_{w}'] = (close - sma) / close
    return out


def _calcular_ema(close: pd.Series, ventanas: list) -> dict:
    out = {}
    for w in ventanas:
        ema = close.ewm(span=w, adjust=False).mean()
        out[f'ema_{w}'] = ema
        out[f'ema_dist_{w}'] = (close - ema) / close
    return out


def _calcular_rsi(close: pd.Series, w: int) -> dict:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = _wilder_ema(gain, w)
    avg_loss = _wilder_ema(loss, w)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return {f'rsi_{w}': 100.0 - (100.0 / (1.0 + rs))}


def _calcular_macd(close: pd.Series, fast: int, slow: int, signal: int) -> dict:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return {
        'macd': macd,
        'macd_signal': macd_signal,
        'macd_hist': macd - macd_signal,
    }


def _calcular_atr(high: pd.Series, low: pd.Series, close: pd.Series, w: int) -> dict:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = _wilder_ema(tr, w)
    return {f'atr_{w}': atr, 'atr_pct': atr / close}


def _calcular_bollinger(close: pd.Series, w: int, k: float) -> dict:
    mu = close.rolling(w).mean()
    sigma = close.rolling(w).std(ddof=0)
    upper = mu + k * sigma
    lower = mu - k * sigma
    band_width = upper - lower
    return {
        'bb_width': band_width / mu,
        'bb_pos': (close - lower) / band_width,
    }


def _calcular_roc(close: pd.Series, ventanas: list) -> dict:
    return {f'roc_{w}': (close - close.shift(w)) / close.shift(w) for w in ventanas}


def _calcular_volatilidad(close: pd.Series, ventanas: list) -> dict:
    _labels = {24: 'vol_24h', 168: 'vol_7d'}
    log_ret = np.log(close / close.shift(1))
    out = {}
    for w in ventanas:
        label = _labels.get(w, f'vol_{w}h')
        out[label] = log_ret.rolling(w).std(ddof=1) * np.sqrt(8760)
    return out


def _calcular_drawdown(close: pd.Series, ventanas: list) -> dict:
    out = {}
    for w in ventanas:
        rolling_max = close.rolling(w).max()
        out[f'drawdown_{w}'] = (close - rolling_max) / rolling_max
    return out


def _calcular_trend_slope(close: pd.Series, ventanas: list) -> dict:
    def _ols_slope(y: np.ndarray) -> float:
        n = len(y)
        x = np.arange(1, n + 1, dtype=float)
        xm = x.mean()
        denom = ((x - xm) ** 2).sum()
        if denom == 0:
            return np.nan
        return ((x - xm) * (y - y.mean())).sum() / denom

    out = {}
    for w in ventanas:
        slope = close.rolling(w).apply(_ols_slope, raw=True)
        out[f'trend_slope_{w}'] = (slope * w) / close
    return out


def _calcular_dist_soportes(close: pd.Series, conjunto_N: set, delta: float) -> dict:
    nan_series = pd.Series(np.nan, index=close.index)
    if not conjunto_N:
        return {
            'dist_nearest_support': nan_series.copy(),
            'dist_floor_support': nan_series.copy(),
            'density_2pct': nan_series.copy(),
        }

    soportes = np.array(sorted(conjunto_N), dtype=float)
    c = close.values.astype(float)
    N = len(soportes)

    # nearest: soporte con menor distancia absoluta
    c_col = c.reshape(-1, 1)
    s_row = soportes.reshape(1, -1)
    nearest_idx = np.argmin(np.abs(c_col - s_row), axis=1)
    dist_nearest = (c - soportes[nearest_idx]) / c

    # floor: soporte inmediatamente inferior al precio
    floor_idx = np.searchsorted(soportes, c, side='right') - 1
    valid_floor = floor_idx >= 0
    s_floor = np.where(valid_floor, soportes[np.clip(floor_idx, 0, N - 1)], np.nan)
    dist_floor = np.where(valid_floor, (c - s_floor) / c, np.nan)

    # density ±delta%
    rel_diffs = np.abs(c_col - s_row) / c_col
    density = (rel_diffs <= delta).sum(axis=1) / N

    return {
        'dist_nearest_support': pd.Series(dist_nearest, index=close.index),
        'dist_floor_support': pd.Series(dist_floor, index=close.index),
        'density_2pct': pd.Series(density.astype(float), index=close.index),
    }


# ─── Función de cálculo completo ─────────────────────────────────────────────

def _calcular_todos_indicadores(df: pd.DataFrame, conjunto_N: set) -> pd.DataFrame:
    """
    Calcula todos los indicadores sobre el df completo.
    df debe tener columnas DateTime, High, Low, Close (con índice entero reseteado).
    Retorna DataFrame con columna 'datetime' + una columna por feature.
    """
    v = X3_VENTANAS
    close = df['Close']
    high  = df['High']
    low   = df['Low']

    features: dict = {}
    features.update(_calcular_sma(close, v['sma']))
    features.update(_calcular_ema(close, v['ema']))
    features.update(_calcular_rsi(close, v['rsi']))
    features.update(_calcular_macd(close, *v['macd']))
    features.update(_calcular_atr(high, low, close, v['atr']))
    features.update(_calcular_bollinger(close, *v['bb']))
    features.update(_calcular_roc(close, v['roc']))
    features.update(_calcular_volatilidad(close, v['vol']))
    features.update(_calcular_drawdown(close, v['drawdown']))
    features.update(_calcular_trend_slope(close, v['trend_slope']))
    features.update(_calcular_dist_soportes(close, conjunto_N, v['density_delta']))

    df_out = pd.DataFrame(features, index=df.index)
    df_out.insert(0, 'datetime', df['DateTime'].values)
    return df_out


# ─── API pública ─────────────────────────────────────────────────────────────

def compute_snapshot(df_ohlcv: pd.DataFrame, soportes: list) -> dict:
    """
    Retorna features técnicas de la última vela del slice OHLCV dado.

    Parámetros
    ----------
    df_ohlcv : DataFrame OHLCV hasta el timestamp actual (DateTime + OHLC + volumen)
    soportes : lista de soportes activos del activo

    Retorna dict[str, float] — una entrada por feature, sin 'datetime'.
    Llamar con el slice completo hasta el ts de interés para garantizar
    correctitud de indicadores con warm-up largo (EMA, RSI).
    """
    df = df_ohlcv.copy()
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df = (df.sort_values('DateTime')
            .drop_duplicates('DateTime')
            .reset_index(drop=True))

    df_feat = _calcular_todos_indicadores(df, set(soportes))
    return df_feat.iloc[-1].drop('datetime').to_dict()


def actualizar_features(valor: str, df_ohlcv: pd.DataFrame, conjunto_N: set) -> None:
    """
    Actualiza resources/x3/{valor}.csv con las filas nuevas de df_ohlcv.

    Parámetros
    ----------
    valor      : ticker del activo (ej. 'BTCUSD')
    df_ohlcv   : DataFrame OHLCV H1 completo (columna DateTime + OHLC + volumen)
    conjunto_N : set de N soportes activos del activo (puede ser vacío → NaN en dist_*)
    """
    CARPETA_FEATURES.mkdir(parents=True, exist_ok=True)
    csv_path = CARPETA_FEATURES / f'{valor}.csv'

    # Último datetime ya computado
    ultimo_t = None
    if csv_path.exists():
        try:
            df_prev = pd.read_csv(csv_path, usecols=['datetime'], parse_dates=['datetime'])
            if not df_prev.empty:
                ultimo_t = df_prev['datetime'].max()
        except Exception:
            pass

    # Preparar df de entrada
    df = df_ohlcv.copy()
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df = (df.sort_values('DateTime')
            .drop_duplicates('DateTime')
            .reset_index(drop=True))

    # Computar todos los indicadores sobre el DF completo (garantiza correctitud de EMA/RSI)
    df_feat = _calcular_todos_indicadores(df, conjunto_N)

    # Solo filas nuevas
    if ultimo_t is not None:
        df_nuevas = df_feat[df_feat['datetime'] > ultimo_t]
    else:
        df_nuevas = df_feat

    if df_nuevas.empty:
        print(f'  X3 {valor}: sin filas nuevas')
        return

    primer_escritura = not csv_path.exists() or ultimo_t is None
    df_nuevas.to_csv(
        csv_path,
        mode='w' if primer_escritura else 'a',
        header=primer_escritura,
        index=False,
    )
    print(f'  X3 {valor}: {len(df_nuevas)} filas → {csv_path.name}')
