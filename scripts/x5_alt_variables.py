"""
x5_alt_variables.py

Variables de estado del activo de X5_alt_v2 (tabla de Q1: precio + X3 + X2 + drawdown, volatilidad, liquidez,
fundamentales, ruido y tendencia/régimen), como módulo importable. Antes vivían solo dentro de X5_Q1.ipynb; ahora el
notebook las importa (una sola implementación) y producción puede calcular la tabla al día para `serie_c1`.

Todas son causales: el valor en `t` solo usa velas ≤ `t` (rolling hacia atrás, `diff`/`shift` positivos, `cummax`,
`ewm` con adjust=False), así que recortar las velas posteriores no cambia las filas anteriores. El catálogo de
documentación por variable (`METADATA_VARIABLES`) queda en el notebook.

No es un script standalone. Se importa con:
    from x5_alt_variables import cargar_tabla_base, construir_tabla_estado
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg  # noqa: E402
from X3_technical_features import _calcular_todos_indicadores, _wilder_ema  # noqa: E402  (reusa X3 en vez de reimplementar indicadores)

_COLS_X2 = ['DateTime', 'x2_score', 'x2_score_cross', 'x2_score_tendencia']


def cargar_precio(valor):
    # El CSV no viene ordenado por fecha y puede traer velas duplicadas (ver X5_P1 §1)
    df_precio = pd.read_csv(cfg.CARPETA_DATA / f'{valor}.csv')
    df_precio['DateTime'] = pd.to_datetime(df_precio['DateTime'])
    return (df_precio.sort_values('DateTime')
                     .drop_duplicates(subset=['DateTime'])
                     .reset_index(drop=True))


def cargar_registros_x2(valor):
    # x2_history.json trae todos los activos mezclados — filtramos por {valor}
    with open(cfg.CARPETA_FUNDAMENTALS / 'x2_history.json') as f:
        x2_hist = json.load(f)
    return [e for e in x2_hist if e.get('activo') == valor]


def armar_tabla_base(df_precio, registros_x2):
    # X3 sobre el histórico completo (no incremental) para que indicadores con
    # warm-up largo (EMA, RSI, SMA 200) sean correctos desde la primera vela útil.
    # conjunto_N vacío = sin distancia a soportes (fuera de v0, igual que X5_P1 §2).
    df_x3 = _calcular_todos_indicadores(df_precio, set())
    df_x3 = df_x3.drop(columns=['dist_nearest_support', 'dist_floor_support', 'density_2pct'])
    df_x3 = df_x3.rename(columns={c: f'x3_{c}' for c in df_x3.columns if c != 'datetime'})

    df_x2 = pd.DataFrame([
        {
            'DateTime': pd.to_datetime(e.get('periodo_inicio') or e['date']),
            'x2_score': e.get('score'),
            'x2_score_cross': e.get('score_cross'),
            'x2_score_tendencia': e.get('score_tendencia'),
        }
        for e in registros_x2
    ], columns=_COLS_X2)
    # columns= evita que un activo sin registros aún (ej. MSFT recién agregado a VALORES) quede con
    # un DataFrame sin columnas; el cast explícito evita el MergeError de merge_asof por dtype
    # object (DateTime vacío) vs. datetime64 cuando no hay filas para inferir el tipo. Los scores igual: sin filas
    # quedan object y np.sign/diff de variables_fundamentales fallan.
    df_x2['DateTime'] = pd.to_datetime(df_x2['DateTime'])
    df_x2[_COLS_X2[1:]] = df_x2[_COLS_X2[1:]].astype(float)
    df_x2 = df_x2.sort_values('DateTime').reset_index(drop=True)  # merge_asof exige orden ascendente

    # Precio y X3 comparten índice/orden → join exacto por DateTime
    tabla = df_precio.merge(df_x3, left_on='DateTime', right_on='datetime').drop(columns=['datetime'])
    # merge_asof(direction='backward') = forward-fill del último score de X2 conocido
    return pd.merge_asof(tabla, df_x2, on='DateTime', direction='backward')


def cargar_tabla_base(valor):
    return armar_tabla_base(cargar_precio(valor), cargar_registros_x2(valor))


def filtrar_y_transformar_tecnicos(df):
    atr = df['x3_atr_14']
    for w in cfg.X3_VENTANAS['sma']:
        col = f'x3_sma_{w}'
        df[f'distancia_sma_{w}'] = (df['Close'] - df[col]) / atr
        df[f'pendiente_sma_{w}'] = (df[col].diff(w) / w) / atr
    for w in cfg.X3_VENTANAS['ema']:
        col = f'x3_ema_{w}'
        df[f'distancia_ema_{w}'] = (df['Close'] - df[col]) / atr
        df[f'pendiente_ema_{w}'] = (df[col].diff(w) / w) / atr

    # niveles crudos descartados (trivial vs. Close); se conservan x3_sma_dist_*/x3_ema_dist_* (ya normalizados por Close)
    cols_crudas = [f'x3_sma_{w}' for w in cfg.X3_VENTANAS['sma']] + [f'x3_ema_{w}' for w in cfg.X3_VENTANAS['ema']]
    return df.drop(columns=cols_crudas)


def variables_drawdown(df):
    close = df['Close']
    cummax = close.cummax()
    df['drawdown_historico'] = (close - cummax) / cummax

    nuevo_maximo = close >= cummax
    episodio = nuevo_maximo.cumsum()
    df['duracion_drawdown'] = close.groupby(episodio).cumcount()
    min_episodio = close.groupby(episodio).cummin()
    df['recuperacion_desde_minimo'] = (close - min_episodio) / min_episodio
    df['velocidad_caida'] = df['drawdown_historico'] / df['duracion_drawdown'].replace(0, np.nan)

    for dias, horas in [(7, 168), (30, 720), (90, 2160), (365, 8760)]:
        rolling_max = close.rolling(horas, min_periods=1).max()
        df[f'drawdown_{dias}d'] = (close - rolling_max) / rolling_max

    return df


def variables_volatilidad(df):
    close = df['Close']
    log_ret = np.log(close / close.shift(1))

    df['cambio_volatilidad'] = df['x3_vol_24h'] / df['x3_vol_7d']

    ret_up = log_ret.where(log_ret > 0)
    ret_down = log_ret.where(log_ret < 0)
    df['vol_alcista_30d'] = ret_up.rolling(720, min_periods=50).std(ddof=1) * np.sqrt(8760)
    df['vol_bajista_30d'] = ret_down.rolling(720, min_periods=50).std(ddof=1) * np.sqrt(8760)

    umbral = 2 * log_ret.expanding(min_periods=100).std(ddof=1)
    extremo = log_ret.abs() > umbral
    df['frecuencia_extremos_30d'] = extremo.rolling(720, min_periods=50).mean()

    return df


def variables_liquidez(df):
    spread = df['Spread']
    media_spread_30d = spread.rolling(720, min_periods=50).mean()
    df['spread_relativo'] = spread / media_spread_30d

    vol = df['Tick_Volume']
    media_30d = vol.rolling(720, min_periods=50).mean()
    std_30d = vol.rolling(720, min_periods=50).std(ddof=1)
    df['tick_volume_z'] = (vol - media_30d) / std_30d
    df['volumen_relativo'] = vol / media_30d

    return df


def variables_fundamentales(df):
    score = df['x2_score']
    cambio = score.diff()
    df['fundamental_cambio'] = cambio
    df['fundamental_direccion_cambio'] = np.sign(cambio)
    df['fundamental_magnitud_cambio'] = cambio.abs()

    actualizo = cambio.fillna(0) != 0
    grupo = actualizo.cumsum()
    df['fundamental_edad'] = df.groupby(grupo).cumcount()

    df['fundamental_frecuencia_efectiva_90d'] = actualizo.rolling(2160, min_periods=50).mean()
    df['fundamental_estabilidad_90d'] = score.rolling(2160, min_periods=50).std(ddof=1)

    df['fundamental_contradiccion'] = (df['x2_score_cross'] - 0.5) * (df['x2_score_tendencia'] - 0.5)

    return df


def variables_ruido(df):
    close = df['Close']
    log_ret = np.log(close / close.shift(1))

    signo = np.sign(log_ret)
    df['ruido_cambios_signo_30d'] = (signo != signo.shift(1)).rolling(720, min_periods=50).mean()

    retorno_30d = np.log(close / close.shift(720))
    movimiento_total_30d = log_ret.abs().rolling(720, min_periods=50).sum()
    df['ruido_ratio_movimiento_30d'] = movimiento_total_30d / retorno_30d.abs().replace(0, np.nan)

    rango = df['High'] - df['Low']
    mecha = (rango - (df['Close'] - df['Open']).abs()) / rango.replace(0, np.nan)
    df['ruido_mecha_30d'] = mecha.rolling(720, min_periods=50).mean()

    df['ruido_atr_sin_direccion_30d'] = df['x3_atr_pct'].rolling(720, min_periods=50).mean() / retorno_30d.abs().replace(0, np.nan)

    return df


def variables_tendencia_regimen(df):
    high, low, close = df['High'], df['Low'], df['Close']

    # ADX de Wilder: +DM/-DM y TR suavizados igual que _calcular_atr (mismo _wilder_ema)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)

    w_adx = cfg.X3_VENTANAS['atr']
    tr_suavizado = _wilder_ema(tr, w_adx)
    plus_di = 100 * _wilder_ema(plus_dm, w_adx) / tr_suavizado
    minus_di = 100 * _wilder_ema(minus_dm, w_adx) / tr_suavizado
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df['adx_14'] = _wilder_ema(dx, w_adx)

    pendiente = df['x3_trend_slope_50']
    sin_historia = df['adx_14'].isna() | pendiente.isna()
    regimen = np.select(
        [df['adx_14'] < 20, pendiente > 0, pendiente < 0],
        ['sideways', 'bull', 'bear'],
        default='sideways',
    )
    df['regimen_tendencia'] = pd.Series(regimen, index=df.index).mask(sin_historia)

    w_rango = cfg.X3_VENTANAS['drawdown'][0]
    max_previo = high.rolling(w_rango).max().shift(1)
    min_previo = low.rolling(w_rango).min().shift(1)
    sin_rango = max_previo.isna() | min_previo.isna()
    ruptura = np.select([close > max_previo, close < min_previo], [1, -1], default=0).astype(float)
    df['ruptura_rango'] = pd.Series(ruptura, index=df.index).mask(sin_rango)

    hubo_ruptura = df['ruptura_rango'].fillna(0) != 0
    episodio_rango = hubo_ruptura.cumsum()
    df['duracion_en_rango'] = close.groupby(episodio_rango).cumcount()

    return df


def construir_tabla_estado(tabla_base):
    """Tabla de estado completa a partir de la base (mismo orden de columnas que `{valor}_tabla_estado_v2.csv`)."""
    df = filtrar_y_transformar_tecnicos(tabla_base)
    for aplicar in (variables_drawdown, variables_volatilidad, variables_liquidez,
                    variables_fundamentales, variables_ruido, variables_tendencia_regimen):
        df = aplicar(df)
    return df
