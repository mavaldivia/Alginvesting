"""
X5_macro_brain.py

Surrogate model de Alginvesting. Aprende la relación:
    f(contexto X2+X3, config_params) → retorno_esperado
y optimiza config_params en inferencia para cada activo.

Modos (3 + casilla --train):
  python scripts/X5_macro_brain.py --recolectar   # genera datos + auto-entrena; pregunta el alcance al inicio
  python scripts/X5_macro_brain.py --recolectar --demo  # recorrido guiado de 1 activo, store/modelo demo, con pausas
  python scripts/X5_macro_brain.py --infer         # recomienda params con el modelo actual → active_parameters.json
  python scripts/X5_macro_brain.py --infer --train # reentrena desde el store y luego recomienda
  python scripts/X5_macro_brain.py --status        # diagnóstico: n_trades y modelo activo por activo

`--train` es una casilla, no un modo: solo tiene efecto junto a `--infer`
(reentrena antes de recomendar). `--recolectar` ya entrena por su cuenta.

`--recolectar` (sin --demo) pregunta al inicio el alcance: todos los activos
en paralelo y en silencio (comportamiento histórico), o uno solo en un
recorrido oficial guiado — mismos prints y gráficos detallados que --demo
(D01..D09, narrador de x5_demo), pero sobre el store/modelo REALES del
activo y sin pausas (Enter): nunca debe quedar esperando input.

Fases de rollout:
  Fase 1 (TIPO_EJECUCION="est"): --recolectar llena el store con backtesting
    (X4 --x5) y entrena los modelos por activo. --infer recomienda params y
    escribe active_parameters.json. X1 no lee ese archivo todavía.
  Fase 2 (TIPO_EJECUCION="din"): X1 escribe la OC al store y llama --infer al
    cierre de cada vela H1. X1 lee active_parameters.json por activo; activos
    con model_status="untrained" hacen fallback automático a config.py.
"""

import argparse
import json
import os
import pickle
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
import x5_demo

# ─── Imports opcionales ──────────────────────────────────────────────────────

try:
    import lightgbm as lgb
    _LGBM_OK = True
except ImportError:
    _LGBM_OK = False
    lgb = None  # type: ignore

try:
    import torch
    import torch.nn as nn
    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False
    torch = None  # type: ignore
    nn = None     # type: ignore

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    _OPTUNA_OK = True
except ImportError:
    _OPTUNA_OK = False
    optuna = None  # type: ignore

# ─── Rutas ───────────────────────────────────────────────────────────────────

CARPETA_X5          = cfg.CARPETA_X5
CARPETA_MODELS      = CARPETA_X5 / 'models'
CARPETA_PERFORMANCE = CARPETA_X5 / 'Performance'
ACTIVE_PARAMS       = cfg.BASE_DIR / 'config' / 'active_parameters.json'

# ─── Festivos (features temporales) ──────────────────────────────────────────

_HOLIDAYS = {date.fromisoformat(d) for d in cfg.X5_US_HOLIDAYS}

# ─── Columnas de features ────────────────────────────────────────────────────

# Columnas de config params en el store (en este orden exacto)
PARAM_STORE_COLS = [
    'n_ejecucion', 'K', 'N_EXP', 'LAMBDA', 'A', 'B', 'LOTAJES_M', 'PERDIDA_MAX',
]

# Nombres enteros o que requieren redondeo diferenciado
_PARAM_INT_COLS = {'n_ejecucion', 'LOTAJES_M'}

# Mapping: nombre en store → clave en X5_PARAM_RANGES (solo si difiere)
_PARAM_TO_RANGE_KEY = {'n_ejecucion': 'n_sizes_ejecucion'}

# Mapping: nombre en store → clave en active_parameters.json (solo si difiere)
_PARAM_TO_JSON_KEY = {'n_ejecucion': 'n_sizes_ejecucion'}

TEMPORAL_COLS = [
    'hora', 'dia_semana', 'dia_mes', 'mes',
    'ds_lun', 'ds_mar', 'ds_mie', 'ds_jue', 'ds_vie', 'ds_sab', 'ds_dom',
    *[f'mes_{i}' for i in range(1, 13)],
    'dias_hasta_festivo', 'dias_desde_festivo', 'es_vispera_festivo', 'es_post_festivo',
]

PORTFOLIO_COLS = [
    'n_ordenes_abiertas', 'n_ordenes_espera', 'exposicion_usd',
    'mean_retorno_pct_abierto', 'std_retorno_pct_abierto',
    'retorno_promedio_ultimas_5_oc',
]

TARGET_RETORNO  = 'retorno_pct'            # Y de filas 'oc'
TARGET_FLOTANTE = 'pnl_flotante_activo'    # Y de filas 'oc' y 'periodico'
TARGET_CERRADO  = 'pnl_cerrado_activo'     # Y de filas 'oc'

# ─── Store ───────────────────────────────────────────────────────────────────

def _demo_suf() -> str:
    """Sufijo del namespace demo ('_demo' o ''). En X5 --recolectar --demo el
    store y el modelo se aíslan de producción vía env X5_DEMO_SUFFIX."""
    return os.environ.get('X5_DEMO_SUFFIX', '')


def _cargar_store(activo: str) -> pd.DataFrame:
    path = CARPETA_X5 / f'{activo}_store{_demo_suf()}.csv'
    if not path.exists():
        return pd.DataFrame()
    # on_bad_lines='skip': una ejecución interrumpida a mitad de fila puede dejar
    # una línea parcial/concatenada en el CSV; se descarta esa fila en vez de
    # abortar toda la carga del store.
    return pd.read_csv(path, low_memory=False, on_bad_lines='skip')


def _n_oc(store: pd.DataFrame) -> int:
    if store.empty or 'tipo_registro' not in store.columns:
        return 0
    return int((store['tipo_registro'] == 'oc').sum())


def _seleccionar_tipo(n_oc: int) -> str:
    if n_oc < cfg.X5_MIN_TRADES_TRAIN:
        return 'untrained'
    if n_oc < cfg.X5_MIN_TRADES_FTT:
        return 'lgbm'
    return 'ftt'

# ─── Params baseline ─────────────────────────────────────────────────────────

def _params_baseline(activo: str) -> dict:
    """Params de config.py sin modificar. Se devuelven cuando el modelo no está entrenado."""
    return {
        'n_sizes_ejecucion': cfg.n_sizes_ejecucion[activo],
        'K':           cfg.K,
        'N_EXP':       cfg.N_EXP,
        'LAMBDA':      cfg.LAMBDA,
        'A':           cfg.A[activo],
        'B':           cfg.B[activo],
        'LOTAJES_M':   cfg.LOTAJES_M[activo],
        'PERDIDA_MAX': cfg.PERDIDA_MAX[activo],
    }

# ─── Feature columns ─────────────────────────────────────────────────────────

def _feature_cols_de_store(store: pd.DataFrame) -> list:
    """
    Determina el vector de features en orden reproducible.
    Se guarda junto al modelo para garantizar consistencia en inferencia.

    Orden: config params | temporal OE | X2 OE | X3 OE | portfolio |
           temporal OA | X2 OA | X3 OA.
    Excluye columnas _oc (información del futuro, no disponible en inferencia).
    """
    cols = set(store.columns)
    x2_oe = sorted(c for c in cols
                   if c.startswith('x2_') and not c.endswith('_oa') and not c.endswith('_oc'))
    x3_oe = sorted(c for c in cols
                   if c.startswith('x3_') and not c.endswith('_oa') and not c.endswith('_oc'))
    x2_oa = sorted(c for c in cols if c.startswith('x2_') and c.endswith('_oa'))
    x3_oa = sorted(c for c in cols if c.startswith('x3_') and c.endswith('_oa'))
    temp_oa = [f'{c}_oa' for c in TEMPORAL_COLS if f'{c}_oa' in cols]

    ordered = (PARAM_STORE_COLS + TEMPORAL_COLS + x2_oe + x3_oe +
               PORTFOLIO_COLS + temp_oa + x2_oa + x3_oa)
    return [c for c in ordered if c in cols]

# ─── Feature preparation ─────────────────────────────────────────────────────

def _preparar_features(
    store: pd.DataFrame,
    feature_cols: list,
    target: str = TARGET_RETORNO,
    tipos_registro: tuple = ('oc',),
) -> tuple:
    """
    Retorna (X, y, sample_weight) para el target indicado.
    Aplica ponderación temporal exponencial: registros recientes pesan más.

    `tipos_registro` permite mezclar filas: p.ej. el head 'flotante'
    (pnl_flotante_activo) entrena con ('oc', 'periodico') porque ese target
    existe en ambos tipos; 'retorno' y 'cerrado' solo con ('oc',).
    """
    if store.empty:
        return np.array([]), np.array([]), np.array([])

    df = store[store['tipo_registro'].isin(tipos_registro)].copy()
    target_num = pd.to_numeric(df.get(target, pd.Series(dtype=float)), errors='coerce')
    df = df[target_num.notna()]
    if df.empty:
        return np.array([]), np.array([]), np.array([])

    X = np.zeros((len(df), len(feature_cols)), dtype=np.float32)
    for j, col in enumerate(feature_cols):
        if col in df.columns:
            X[:, j] = pd.to_numeric(df[col], errors='coerce').fillna(0).values

    y = pd.to_numeric(df[target], errors='coerce').fillna(0).values.astype(np.float32)

    if cfg.X5_WINDOW_TRAIN and len(X) > cfg.X5_WINDOW_TRAIN:
        X = X[-cfg.X5_WINDOW_TRAIN:]
        y = y[-cfg.X5_WINDOW_TRAIN:]

    n = len(X)
    # Decay exponencial: row 0 (más antiguo) tiene menor peso; row n-1 (más reciente) ≈ 1
    w = np.exp(cfg.X5_LAMBDA_DECAY * (np.arange(n) - n + 1)).astype(np.float32)
    w = w / w.mean()  # normalizar: media = 1 para no distorsionar la loss
    return X, y, w

# ─── Context actual ───────────────────────────────────────────────────────────

def _features_temporales_ahora() -> dict:
    ts = pd.Timestamp.now()
    d  = ts.date()
    dw = ts.dayofweek
    m  = ts.month
    futuros = sorted(h for h in _HOLIDAYS if h >= d)
    pasados = sorted((h for h in _HOLIDAYS if h <= d), reverse=True)
    dias_hasta = (futuros[0] - d).days if futuros else 30
    dias_desde = (d - pasados[0]).days if pasados else 30
    return {
        'hora':       ts.hour,
        'dia_semana': dw,
        'dia_mes':    ts.day,
        'mes':        m,
        'ds_lun': int(dw == 0), 'ds_mar': int(dw == 1), 'ds_mie': int(dw == 2),
        'ds_jue': int(dw == 3), 'ds_vie': int(dw == 4),
        'ds_sab': int(dw == 5), 'ds_dom': int(dw == 6),
        **{f'mes_{i}': int(m == i) for i in range(1, 13)},
        'dias_hasta_festivo': min(dias_hasta, 30),
        'dias_desde_festivo': min(dias_desde, 30),
        'es_vispera_festivo': int(dias_hasta <= 1),
        'es_post_festivo':    int(dias_desde <= 1),
    }


def _fecha_x2(e: dict) -> str:
    """Fecha efectiva de una entrada de x2_history (formato periodo o legacy 'date')."""
    return e.get('periodo_inicio') or e.get('date') or e.get('periodo_fin') or ''


def _extraer_x2(e: dict) -> dict:
    """Features de X2: scores + componentes aplanados (descarta raw/metadata).

    Debe producir las MISMAS claves que _extraer_x2 en X4 para que las columnas
    x2_* de inferencia coincidan con las del store.
    """
    out = {k: e[k] for k in ('score', 'score_cross', 'score_tendencia') if k in e}
    for k, v in (e.get('components') or {}).items():
        out[f'comp_{k}'] = v
    return out


def _x2_actual(activo: str) -> dict:
    """Último snapshot de X2 disponible para el activo."""
    path = cfg.CARPETA_FUNDAMENTALS / 'x2_history.json'
    if not path.exists():
        return {}
    with open(path) as f:
        hist = json.load(f)
    entradas = [e for e in hist if e.get('activo') == activo]
    if not entradas:
        return {}
    ultima = max(entradas, key=_fecha_x2)
    return _extraer_x2(ultima)


def _x3_actual(activo: str) -> dict:
    """Última fila de features técnicas (X3) para el activo."""
    path = cfg.CARPETA_FEATURES / f'{activo}.csv'
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if df.empty:
        return {}
    row = df.iloc[-1].to_dict()
    return {k: v for k, v in row.items() if k not in ('DateTime', 'Unnamed: 0')}


def _leer_contexto_actual(activo: str) -> dict:
    """
    Snapshot del contexto de mercado actual: features temporales, X2, X3.

    En Fase 1 no hay portfolio live — las features de portfolio se ponen a cero.
    En Fase 2, X1 podría pasar el estado del portfolio vía un archivo intermedio;
    por ahora se usan ceros como fallback seguro.

    Los features OA (al ejecutarse la orden) se aproximan como iguales a OE
    (asunción: la orden se ejecuta pronto). En Fase 2 con datos reales, X1
    podría proveer los snapshots de OA exactos.
    """
    temp = _features_temporales_ahora()
    x2   = _x2_actual(activo)
    x3   = _x3_actual(activo)

    ctx: dict = {}
    ctx.update(temp)                                # temporal OE
    for k, v in x2.items():
        ctx[f'x2_{k}'] = v                          # X2 OE
    for k, v in x3.items():
        ctx[f'x3_{k}'] = v                          # X3 OE
    for col in PORTFOLIO_COLS:
        ctx[col] = 0.0                              # portfolio: ceros (Fase 1)
    for k, v in temp.items():
        ctx[f'{k}_oa'] = v                          # temporal OA (proxy = OE)
    for k, v in x2.items():
        ctx[f'x2_{k}_oa'] = v                       # X2 OA (proxy = OE)
    for k, v in x3.items():
        ctx[f'x3_{k}_oa'] = v                       # X3 OA (proxy = OE)
    return ctx

# ─── Inference vector ─────────────────────────────────────────────────────────

def _construir_vector(contexto: dict, params_store: dict, feature_cols: list) -> np.ndarray:
    """
    Combina contexto fijo + params variables en el vector de features ordenado.
    params_store usa los nombres del store (n_ejecucion, K, ...).
    """
    full = {**contexto, **params_store}
    return np.array([float(full.get(c, 0.0)) for c in feature_cols], dtype=np.float32)

# ─── Métricas ML ─────────────────────────────────────────────────────────────

def _calcular_metricas(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """MAE, MSE, MAPE y R2 para un par (y_true, y_pred)."""
    if len(y_true) == 0:
        return {}
    mae = float(np.mean(np.abs(y_true - y_pred)))
    mse = float(np.mean((y_true - y_pred) ** 2))
    mask = np.abs(y_true) > 1e-8
    mape = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100) if mask.any() else None
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 1e-10 else None
    return {
        'MAE':  round(mae, 6),
        'MSE':  round(mse, 6),
        'MAPE': round(mape, 4) if mape is not None else None,
        'R2':   round(r2, 6)   if r2   is not None else None,
    }


def _guardar_performance(activo: str, tipo_modelo: str, n_train: int, n_test: int,
                         metricas: dict) -> None:
    """Persiste métricas en resources/x5/Performance/{activo}_performance.json como historial.

    Aislado del demo vía `_demo_suf()`, igual que el store y el modelo."""
    CARPETA_PERFORMANCE.mkdir(parents=True, exist_ok=True)
    path = CARPETA_PERFORMANCE / f'{activo}{_demo_suf()}_performance.json'
    entrada = {
        'timestamp':   datetime.now().isoformat(timespec='seconds'),
        'tipo_modelo': tipo_modelo,
        'n_train':     n_train,
        'n_test':      n_test,
        'targets':     metricas,
    }
    historial: list = []
    if path.exists():
        with open(path) as f:
            contenido = json.load(f)
        historial = contenido if isinstance(contenido, list) else [contenido]
    historial.append(entrada)
    with open(path, 'w') as f:
        json.dump(historial, f, indent=2)
    print(f'  [{activo}] Performance → {path.relative_to(cfg.BASE_DIR)}')

# ─── Model directories ────────────────────────────────────────────────────────

def _model_dir(activo: str) -> Path:
    return CARPETA_MODELS / f'{activo}{_demo_suf()}'

# ─── LightGBM ────────────────────────────────────────────────────────────────

def _entrenar_lgbm(activo: str, store: pd.DataFrame) -> bool:
    if not _LGBM_OK:
        print(f'  [{activo}] lightgbm no instalado → pip install lightgbm')
        return False

    feature_cols = _feature_cols_de_store(store)
    out = _model_dir(activo)
    out.mkdir(parents=True, exist_ok=True)

    # 'flotante' (pnl_flotante_activo) aprovecha además las filas periódicas:
    # capturan el deterioro del portfolio durante rachas bajistas sin OC.
    targets = {
        'retorno':  (TARGET_RETORNO,  ('oc',)),
        'flotante': (TARGET_FLOTANTE, ('oc', 'periodico')),
        'cerrado':  (TARGET_CERRADO,  ('oc',)),
    }

    exito = True
    metricas: dict = {}
    n_train_total = n_test_total = 0
    for key, (target_col, tipos_reg) in targets.items():
        X, y, w = _preparar_features(store, feature_cols, target_col, tipos_reg)
        if len(X) < 20:
            print(f'  [{activo}] LightGBM {key}: solo {len(X)} filas — omitido.')
            exito = False
            continue

        split = max(10, int(len(X) * 0.8))
        X_tr, y_tr, w_tr = X[:split], y[:split], w[:split]
        X_val, y_val     = X[split:], y[split:]
        n_train_total = split
        n_test_total  = len(X_val)

        lgb_params = {
            'objective': 'regression', 'metric': 'rmse',
            'n_estimators': 1000, 'learning_rate': 0.05,
            'num_leaves': 31, 'min_child_samples': 10,
            'subsample': 0.8, 'colsample_bytree': 0.8,
            'reg_alpha': 0.1, 'reg_lambda': 0.1,
            'verbose': -1,
        }
        model = lgb.LGBMRegressor(**lgb_params)
        if len(X_val) >= 10:
            cbs = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)]
            model.fit(X_tr, y_tr, sample_weight=w_tr,
                      eval_set=[(X_val, y_val)], callbacks=cbs)
            best_iter = getattr(model, 'best_iteration_', lgb_params['n_estimators'])
        else:
            model.fit(X_tr, y_tr, sample_weight=w_tr)
            best_iter = lgb_params['n_estimators']

        metricas[key] = {
            'train': _calcular_metricas(y_tr, model.predict(X_tr)),
            'test':  _calcular_metricas(y_val, model.predict(X_val)) if len(X_val) > 0 else {},
        }

        with open(out / f'{activo}_lgbm_{key}.pkl', 'wb') as f:
            pickle.dump(model, f)
        print(f'  [{activo}] LGBM {key}: {split} train | {len(X_val)} val | iter={best_iter}')

    with open(out / f'{activo}_lgbm_features.json', 'w') as f:
        json.dump(feature_cols, f)
    if metricas:
        _guardar_performance(activo, 'lgbm', n_train_total, n_test_total, metricas)
    return exito


def _cargar_lgbm(activo: str):
    out = _model_dir(activo)
    feat_path = out / f'{activo}_lgbm_features.json'
    if not feat_path.exists():
        return None
    with open(feat_path) as f:
        feature_cols = json.load(f)
    models = {}
    for key in ('retorno', 'flotante', 'cerrado'):
        p = out / f'{activo}_lgbm_{key}.pkl'
        if p.exists():
            with open(p, 'rb') as f:
                models[key] = pickle.load(f)
    return (models, feature_cols) if models else None

# ─── FT-Transformer ──────────────────────────────────────────────────────────

if _TORCH_OK:
    class _FeatureTokenizer(nn.Module):
        """
        Convierte cada feature escalar en un vector de dimensión d.
        Cada feature tiene sus propios pesos W y sesgo b aprendidos.
        """
        def __init__(self, n_features: int, d: int):
            super().__init__()
            self.W = nn.Parameter(torch.empty(n_features, d))
            self.b = nn.Parameter(torch.zeros(n_features, d))
            nn.init.kaiming_uniform_(self.W, a=0.01)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # x: (B, F) → (B, F, D)
            return x.unsqueeze(-1) * self.W.unsqueeze(0) + self.b.unsqueeze(0)

    class _TransformerBlock(nn.Module):
        """
        Bloque Transformer (pre-norm): LayerNorm → MHA → residual → LayerNorm → FFN → residual.
        La variante pre-norm es más estable en entrenamiento.
        """
        def __init__(self, d: int, n_heads: int, d_ffn: int, dropout: float = 0.0):
            super().__init__()
            self.norm1 = nn.LayerNorm(d)
            self.attn  = nn.MultiheadAttention(d, n_heads, dropout=dropout, batch_first=True)
            self.norm2 = nn.LayerNorm(d)
            self.ffn   = nn.Sequential(
                nn.Linear(d, d_ffn),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(d_ffn, d),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            h = self.norm1(x)
            h, _ = self.attn(h, h, h)
            x = x + h
            h = self.ffn(self.norm2(x))
            return x + h

    class FTTransformer(nn.Module):
        """
        Feature Tokenizer + Transformer con trunk compartido y 3 heads de salida.
        V2 del surrogate model de X5 (se activa cuando el store supera X5_MIN_TRADES_FTT).

        Hiperparámetros por defecto del paper original (Gorishniy et al., 2021):
          d=192, n_layers=3, n_heads=8, d_ffn=256.
        Con ~240 features → ~700k parámetros. No requiere GPU de alta gama.
        """
        def __init__(self, n_features: int,
                     d: int = 192, n_layers: int = 3, n_heads: int = 8,
                     d_ffn: int = 256, dropout: float = 0.0):
            super().__init__()
            self.tokenizer    = _FeatureTokenizer(n_features, d)
            self.blocks       = nn.ModuleList([
                _TransformerBlock(d, n_heads, d_ffn, dropout) for _ in range(n_layers)
            ])
            self.norm_out     = nn.LayerNorm(d)
            self.head_retorno  = nn.Linear(d, 1)
            self.head_flotante = nn.Linear(d, 1)
            self.head_cerrado  = nn.Linear(d, 1)

        def forward(self, x: torch.Tensor):
            # x: (B, F) → tokens: (B, F, D) → mean pool → (B, D) → 3 predicciones
            t = self.tokenizer(x)
            for block in self.blocks:
                t = block(t)
            pooled = self.norm_out(t).mean(dim=1)  # mean pool sobre features
            return (
                self.head_retorno(pooled).squeeze(-1),
                self.head_flotante(pooled).squeeze(-1),
                self.head_cerrado(pooled).squeeze(-1),
            )

else:
    FTTransformer = None  # type: ignore


def _entrenar_ftt(activo: str, store: pd.DataFrame) -> bool:
    if not _TORCH_OK:
        print(f'  [{activo}] torch no instalado → pip install torch')
        return False

    feature_cols = _feature_cols_de_store(store)
    out = _model_dir(activo)
    out.mkdir(parents=True, exist_ok=True)

    X, y_r, w = _preparar_features(store, feature_cols, TARGET_RETORNO, ('oc',))
    if len(X) < 50:
        print(f'  [{activo}] FTT: solo {len(X)} filas OC — insuficientes.')
        return False

    n = len(X)
    # Los 3 heads del FTT comparten el mismo tensor X (filas OC), así que los
    # 3 targets se leen sobre 'oc'. El aprovechamiento de filas periódicas para
    # el head 'flotante' (vía Deep Sets / pase separado) queda como TO DO en V2.
    _, y_f, _ = _preparar_features(store, feature_cols, TARGET_FLOTANTE, ('oc',))
    _, y_c, _ = _preparar_features(store, feature_cols, TARGET_CERRADO, ('oc',))
    # Alinear longitud con X (mismas filas OC)
    y_f = y_f[:n] if len(y_f) >= n else np.zeros(n, dtype=np.float32)
    y_c = y_c[:n] if len(y_c) >= n else np.zeros(n, dtype=np.float32)

    split = max(10, int(n * 0.8))

    # Normalización columna a columna (solo sobre train)
    col_mean = X[:split].mean(axis=0, keepdims=True)
    col_std  = np.where(X[:split].std(axis=0, keepdims=True) > 1e-8,
                        X[:split].std(axis=0, keepdims=True), 1.0)
    X_norm = ((X - col_mean) / col_std).astype(np.float32)
    scaler = {'mean': col_mean.tolist(), 'std': col_std.tolist()}

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model  = FTTransformer(n_features=len(feature_cols)).to(device)
    opt    = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

    X_t   = torch.tensor(X_norm[:split], device=device)
    y_rt  = torch.tensor(y_r[:split],  device=device)
    y_ft  = torch.tensor(y_f[:split],  device=device)
    y_ct  = torch.tensor(y_c[:split],  device=device)
    w_t   = torch.tensor(w[:split],    device=device)

    EPOCHS = 50
    BATCH  = min(256, split)
    model.train()
    for epoch in range(EPOCHS):
        perm       = torch.randperm(split, device=device)
        total_loss = 0.0
        for start in range(0, split, BATCH):
            idx = perm[start:start + BATCH]
            p_r, p_f, p_c = model(X_t[idx])
            l_r = ((p_r - y_rt[idx]) ** 2 * w_t[idx]).mean()
            l_f = ((p_f - y_ft[idx]) ** 2 * w_t[idx]).mean()
            l_c = ((p_c - y_ct[idx]) ** 2 * w_t[idx]).mean()
            loss = l_r + 0.3 * l_f + 0.3 * l_c
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total_loss += loss.item()
        if (epoch + 1) % 10 == 0:
            print(f'  [{activo}] FTT epoch {epoch + 1:>3}/{EPOCHS} | loss={total_loss:.4f}')

    torch.save({
        'state_dict': model.state_dict(),
        'n_features':  len(feature_cols),
        'scaler':      scaler,
    }, out / f'{activo}_ftt.pt')
    with open(out / f'{activo}_ftt_features.json', 'w') as f:
        json.dump(feature_cols, f)
    print(f'  [{activo}] FTT entrenado con {split} filas OC (train) | {n - split} (test).')

    # Métricas train / test
    model.eval()
    X_all_t = torch.tensor(X_norm, device=device)
    with torch.no_grad():
        p_r_all, p_f_all, p_c_all = model(X_all_t)
    p_r_np = p_r_all.cpu().numpy()
    p_f_np = p_f_all.cpu().numpy()
    p_c_np = p_c_all.cpu().numpy()
    metricas_ftt = {
        'retorno': {
            'train': _calcular_metricas(y_r[:split], p_r_np[:split]),
            'test':  _calcular_metricas(y_r[split:], p_r_np[split:]) if n > split else {},
        },
        'flotante': {
            'train': _calcular_metricas(y_f[:split], p_f_np[:split]),
            'test':  _calcular_metricas(y_f[split:], p_f_np[split:]) if n > split else {},
        },
        'cerrado': {
            'train': _calcular_metricas(y_c[:split], p_c_np[:split]),
            'test':  _calcular_metricas(y_c[split:], p_c_np[split:]) if n > split else {},
        },
    }
    _guardar_performance(activo, 'ftt', split, n - split, metricas_ftt)
    return True


def _cargar_ftt(activo: str):
    out        = _model_dir(activo)
    model_path = out / f'{activo}_ftt.pt'
    feat_path  = out / f'{activo}_ftt_features.json'
    if not model_path.exists() or not feat_path.exists():
        return None
    with open(feat_path) as f:
        feature_cols = json.load(f)
    # weights_only=False: requerido para cargar clases custom.
    # Seguro porque el archivo fue generado localmente por este script.
    ckpt = torch.load(model_path, map_location='cpu', weights_only=False)
    model = FTTransformer(n_features=ckpt['n_features'])
    model.load_state_dict(ckpt['state_dict'])
    model.eval()
    scaler = {
        'mean': np.array(ckpt['scaler']['mean'], dtype=np.float32),
        'std':  np.array(ckpt['scaler']['std'],  dtype=np.float32),
    }
    return model, scaler, feature_cols

# ─── Airbag ───────────────────────────────────────────────────────────────────

def _aplicar_airbag(activo: str, params: dict) -> dict:
    """
    Regla de seguridad explícita (no aprendida): si el precio cayó más de
    AIRBAG_THRESHOLD en las últimas 4 velas H1, fuerza lotaje y N mínimos.
    """
    path = cfg.CARPETA_DATA / f'{activo}.csv'
    if not path.exists():
        return params
    df = pd.read_csv(path, usecols=['DateTime', 'Close'])
    df = df.sort_values('DateTime').tail(5)
    if len(df) < 5:
        return params
    p_ini = float(df['Close'].iloc[0])
    p_fin = float(df['Close'].iloc[-1])
    caida = (p_fin - p_ini) / p_ini if p_ini > 0 else 0.0
    threshold = cfg.X5_AIRBAG_THRESHOLD.get(activo, 0.05)
    if caida < -threshold:
        print(f'  [{activo}] AIRBAG activado: caída {caida:.1%} > {threshold:.0%}')
        params = params.copy()
        params['LOTAJES_M'] = 1
        params['n_sizes_ejecucion'] = cfg.X5_N_MINIMO.get(activo, 20)
    return params

# ─── Inferencia: helpers de rangos ────────────────────────────────────────────

# Rangos inyectables desde X4 (--x5). Si está seteado, _rango lo usa en vez de
# cfg.X5_PARAM_RANGES, de modo que explore (config_x5) y exploit muestreen del
# mismo espacio de params. None → usa los rangos globales de config.py (live).
_RANGES_OVERRIDE = None


def _rango(param_store: str, activo: str) -> tuple:
    """Rango de búsqueda para el param (nombre de store) del activo dado."""
    ranges = _RANGES_OVERRIDE if _RANGES_OVERRIDE is not None else cfg.X5_PARAM_RANGES
    range_key = _PARAM_TO_RANGE_KEY.get(param_store, param_store)
    return ranges[range_key][activo]

# ─── Inferencia LightGBM (Optuna) ────────────────────────────────────────────

def _inferir_lgbm(activo: str, models: dict, contexto: dict, feature_cols: list) -> dict:
    """
    Busca los config_params que maximizan retorno_pct predicho mediante Optuna
    (optimización bayesiana: concentra los trials en zonas prometedoras del espacio).
    """
    if not _OPTUNA_OK:
        print(f'  [{activo}] optuna no instalado → pip install optuna')
        return _params_baseline(activo)
    model_r = models.get('retorno')
    if model_r is None:
        return _params_baseline(activo)

    def objective(trial):
        p = {
            'n_ejecucion': trial.suggest_int(
                'n_ejecucion', int(_rango('n_ejecucion', activo)[0]),
                int(_rango('n_ejecucion', activo)[1]),
            ),
            'K':           trial.suggest_float('K',    *_rango('K',    activo)),
            'N_EXP':       trial.suggest_float('N_EXP', *_rango('N_EXP', activo)),
            # LAMBDA tiene rango pequeño positivo → log scale para mejor cobertura
            'LAMBDA':      trial.suggest_float('LAMBDA', *_rango('LAMBDA', activo), log=True),
            'A':           trial.suggest_float('A',    *_rango('A',    activo)),
            'B':           trial.suggest_float('B',    *_rango('B',    activo)),
            'LOTAJES_M':   trial.suggest_int(
                'LOTAJES_M', int(_rango('LOTAJES_M', activo)[0]),
                int(_rango('LOTAJES_M', activo)[1]),
            ),
            'PERDIDA_MAX': trial.suggest_float('PERDIDA_MAX', *_rango('PERDIDA_MAX', activo)),
        }
        vec = _construir_vector(contexto, p, feature_cols)
        return float(model_r.predict([vec])[0])

    study = optuna.create_study(
        direction='maximize',
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=cfg.X5_N_OPTUNA_TRIALS, show_progress_bar=False)
    best = study.best_params

    return {
        'n_sizes_ejecucion': int(best['n_ejecucion']),
        'K':           round(best['K'],           4),
        'N_EXP':       round(best['N_EXP'],       4),
        'LAMBDA':      round(best['LAMBDA'],       6),
        'A':           round(best['A'],            2),
        'B':           round(best['B'],            2),
        'LOTAJES_M':   int(best['LOTAJES_M']),
        'PERDIDA_MAX': round(best['PERDIDA_MAX'],  1),
    }

# ─── Inferencia FTT (gradient ascent) ────────────────────────────────────────

def _inferir_ftt(
    activo: str,
    model: 'FTTransformer',
    scaler: dict,
    contexto: dict,
    feature_cols: list,
) -> dict:
    """
    Gradient ascent sobre el espacio de config_params con el contexto fijo.
    Técnica: los params se optimizan como variables de entrada (no se tocan
    los pesos del modelo). Se repite desde X5_ASCENT_RESTARTS puntos aleatorios
    para evitar mínimos locales.

    Truco de implementación: se construye el vector de entrada como:
        x = contexto_fijo + P @ params_t
    donde P es una matriz de proyección (constante). Esto mantiene el grafo
    diferenciable w.r.t. params_t a través de operaciones matriciales estándar.
    """
    mean = scaler['mean'].flatten()
    std  = scaler['std'].flatten()
    n_feat = len(feature_cols)

    # Índices de los config params dentro de feature_cols
    param_indices = [i for i, c in enumerate(feature_cols) if c in PARAM_STORE_COLS]
    param_names   = [feature_cols[i] for i in param_indices]
    n_params      = len(param_indices)

    if n_params == 0:
        return _params_baseline(activo)

    # Vector de contexto con posiciones de params puestas a 0
    base = np.array([float(contexto.get(c, 0.0)) for c in feature_cols], dtype=np.float32)
    for i in param_indices:
        base[i] = 0.0
    base_norm = (base - mean) / std  # normalizado

    # Matriz de proyección P: P[j, idx] = 1 si el j-ésimo param va en feature_cols[idx]
    # Permite: x = base_norm + (P * params_t.unsqueeze(1)).sum(0)
    # El gradiente fluye a través de params_t porque P es constante.
    P = torch.zeros(n_params, n_feat, dtype=torch.float32)
    for j, idx in enumerate(param_indices):
        P[j, idx] = 1.0
    context_t = torch.tensor(base_norm, dtype=torch.float32)

    # Rangos normalizados para el clamping durante el ascent
    lo_norm = np.zeros(n_params, dtype=np.float32)
    hi_norm = np.zeros(n_params, dtype=np.float32)
    for j, name in enumerate(param_names):
        lo, hi = _rango(name, activo)
        idx = param_indices[j]
        lo_norm[j] = (lo - float(mean[idx])) / float(std[idx])
        hi_norm[j] = (hi - float(mean[idx])) / float(std[idx])
    lo_t = torch.tensor(lo_norm)
    hi_t = torch.tensor(hi_norm)

    best_p_norm = None
    best_score  = -np.inf

    model.eval()
    for _ in range(cfg.X5_ASCENT_RESTARTS):
        # Inicialización aleatoria uniforme dentro del rango normalizado
        init  = (lo_norm + np.random.rand(n_params).astype(np.float32) * (hi_norm - lo_norm))
        p_t   = torch.tensor(init, requires_grad=True, dtype=torch.float32)
        opt_a = torch.optim.Adam([p_t], lr=cfg.X5_ASCENT_LR)

        for _ in range(cfg.X5_ASCENT_STEPS):
            x = (context_t + (P * p_t.unsqueeze(1)).sum(0)).unsqueeze(0)
            pred_r, _, _ = model(x)
            (-pred_r.squeeze()).backward()  # gradient ascent = descend on negativo
            opt_a.step()
            opt_a.zero_grad()
            with torch.no_grad():
                p_t.clamp_(lo_t, hi_t)

        with torch.no_grad():
            x = (context_t + (P * p_t.unsqueeze(1)).sum(0)).unsqueeze(0)
            score = model(x)[0].item()

        if score > best_score:
            best_score  = score
            best_p_norm = p_t.detach().clone()

    if best_p_norm is None:
        return _params_baseline(activo)

    # Desnormalizar y construir el dict de params
    result: dict = {}
    for j, name in enumerate(param_names):
        idx = param_indices[j]
        val = float(best_p_norm[j]) * float(std[idx]) + float(mean[idx])
        lo, hi = _rango(name, activo)
        val = float(np.clip(val, lo, hi))
        json_key = _PARAM_TO_JSON_KEY.get(name, name)
        if name in _PARAM_INT_COLS:
            result[json_key] = int(round(val))
        elif name == 'LAMBDA':
            result[json_key] = round(val, 6)
        else:
            result[json_key] = round(val, 4)
    # Rellenar con baseline cualquier param no incluido en feature_cols del store
    baseline = _params_baseline(activo)
    return {**baseline, **result}

# ─── Pipeline principal ───────────────────────────────────────────────────────

def _entrenar(activo: str) -> str:
    """Entrena el modelo apropiado según el tamaño del store. Retorna el tipo entrenado."""
    store = _cargar_store(activo)
    n     = _n_oc(store)
    tipo  = _seleccionar_tipo(n)
    if tipo == 'untrained':
        falta = cfg.X5_MIN_TRADES_TRAIN - n
        print(f'  [{activo}] Sin datos suficientes ({n} OC). Faltan {falta} más.')
        return tipo
    print(f'  [{activo}] Entrenando {tipo.upper()} con {n} OC...')
    if tipo == 'lgbm':
        _entrenar_lgbm(activo, store)
    else:
        _entrenar_ftt(activo, store)
    return tipo


def cargar_modelo_para_activo(activo: str) -> tuple:
    """Carga el modelo del activo una sola vez, para reuso externo (X4 --x5).

    Retorna (tipo, bundle):
      - tipo: 'untrained' | 'lgbm' | 'ftt'
      - bundle: lo que devuelve _cargar_lgbm/_cargar_ftt, o None si no hay modelo
        entrenado (cuenta insuficiente o archivo ausente).
    """
    tipo = _seleccionar_tipo(_n_oc(_cargar_store(activo)))
    if tipo == 'untrained':
        return 'untrained', None
    bundle = _cargar_lgbm(activo) if tipo == 'lgbm' else _cargar_ftt(activo)
    if bundle is None:
        return 'untrained', None
    return tipo, bundle


def inferir_con_contexto(activo: str, tipo: str, bundle, contexto: dict,
                         param_ranges: dict | None = None) -> dict:
    """Infiere params con un contexto inyectado (as-of-t histórico), sin leer 'now'.

    No aplica airbag: en recolección se busca variedad causal en el store,
    incluida la de regímenes de caída (el airbag es una capa de seguridad live,
    no de datos). `param_ranges` (config_x5) asegura que explore y exploit
    muestreen del mismo espacio; None → rangos globales de config.py.
    """
    global _RANGES_OVERRIDE
    _RANGES_OVERRIDE = param_ranges
    try:
        if tipo == 'lgbm':
            models, feature_cols = bundle
            return _inferir_lgbm(activo, models, contexto, feature_cols)
        model, scaler, feature_cols = bundle
        return _inferir_ftt(activo, model, scaler, contexto, feature_cols)
    finally:
        _RANGES_OVERRIDE = None


def _inferir_params(activo: str, contexto: dict | None = None) -> tuple:
    """
    Carga el modelo guardado e infiere los params óptimos.
    contexto=None → usa el contexto actual (live, Fase 2). Si se inyecta un
    contexto (backtest as-of-t), se usa ese. Retorna (params_dict_json, model_status).
    """
    tipo, bundle = cargar_modelo_para_activo(activo)
    if tipo == 'untrained':
        return _params_baseline(activo), 'untrained'
    if contexto is None:
        contexto = _leer_contexto_actual(activo)
    params = inferir_con_contexto(activo, tipo, bundle, contexto)
    params = _aplicar_airbag(activo, params)
    return params, tipo

# ─── Output JSON ──────────────────────────────────────────────────────────────

def _escribir_active_parameters(resultados: dict) -> None:
    """
    Escribe config/active_parameters.json haciendo *merge* (no overwrite):
    actualiza solo las claves de los activos en `resultados` y preserva las
    demás. Necesario para el modo paralelo (--infer --activo X), donde varios
    procesos actualizan cada uno su activo. Escritura atómica (tmp + replace).

    resultados: {activo: (params_dict, model_status)}
    """
    ACTIVE_PARAMS.parent.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    if ACTIVE_PARAMS.exists():
        try:
            with open(ACTIVE_PARAMS) as f:
                out = json.load(f)
        except (json.JSONDecodeError, OSError):
            out = {}
    out['generated_at'] = datetime.now().isoformat(timespec='seconds')
    for activo, (params, status) in resultados.items():
        out[activo] = {'model_status': status, **params}
    tmp = ACTIVE_PARAMS.with_suffix('.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(out, f, indent=2)
    tmp.replace(ACTIVE_PARAMS)
    print(f'\n  → {ACTIVE_PARAMS}')

# ─── Status ───────────────────────────────────────────────────────────────────

def _mostrar_status() -> None:
    print(f'\n{"═" * 72}')
    print(f'  X5 — Surrogate model status')
    print(f'{"═" * 72}')

    for activo in cfg.VALORES:
        store = _cargar_store(activo)
        n     = _n_oc(store)
        total = len(store)
        tipo  = _seleccionar_tipo(n)
        out   = _model_dir(activo)
        lgbm_ok = (out / f'{activo}_lgbm_retorno.pkl').exists()
        ftt_ok  = (out / f'{activo}_ftt.pt').exists()

        if tipo == 'untrained':
            falta   = cfg.X5_MIN_TRADES_TRAIN - n
            detalle = f'faltan {falta} OC para entrenar'
        elif tipo == 'lgbm':
            falta   = cfg.X5_MIN_TRADES_FTT - n
            m_ok    = 'modelo ok' if lgbm_ok else 'SIN MODELO — ejecutar --train'
            detalle = f'{m_ok} | {falta} OC para FTT'
        else:
            m_ok    = 'modelo ok' if ftt_ok else 'SIN MODELO — ejecutar --train'
            detalle = m_ok

        print(f'  {activo:<8}  {n:>5} OC  {total:>7} filas  [{tipo:<9}]  {detalle}')

    if ACTIVE_PARAMS.exists():
        with open(ACTIVE_PARAMS) as f:
            ap = json.load(f)
        print(f'\n  active_parameters.json — generado: {ap.get("generated_at", "?")}')
        for activo in cfg.VALORES:
            if activo in ap:
                s    = ap[activo].get('model_status', '?')
                n_sz = ap[activo].get('n_sizes_ejecucion', '?')
                lm   = ap[activo].get('LOTAJES_M', '?')
                k    = ap[activo].get('K', '?')
                print(f'    {activo}: status={s:<9}  N={n_sz}  LM={lm}  K={k}')
    print(f'{"═" * 72}\n')

# ─── Recolectar ───────────────────────────────────────────────────────────────

def _worker_recolectar_activo(activo: str, x4_path: Path, n_ciclos: int) -> tuple:
    """
    Worker de UN activo (corre en su propio hilo, en paralelo con los demás).

    Bucle de ciclos independientes:
      1. Lanza X4 --x5 --activo {activo}: un backtest completo desde
         `fecha_inicio`, con recursos X4 aislados (`bt_{activo}`). X4 decide
         internamente si arranca una pasada nueva desde cero o retoma el
         checkpoint de una pasada anterior que quedó a mitad de camino (ver
         `ejecutar_backtest` en X4_backtester.py) — un ciclo que ya terminó
         siempre da paso a una pasada nueva.
      2. Al terminar el ciclo, cuenta las OC del store del activo.
      3. Si ya superó X5_MIN_TRADES_TRAIN, entrena/reentrena el modelo del
         activo → los ciclos EXPLOIT siguientes ya usan el modelo recién
         entrenado (los params se van corrigiendo por activo).
      4. Si la pasada completó (llegó al final de los datos o hizo stop-out),
         el siguiente ciclo arranca una pasada nueva desde `fecha_inicio` con
         params distintos — así se mantiene la diversidad de exploración.

    Termina al agotar `n_ciclos` (config_x5.N_CICLOS_BT) ciclos o alcanzar
    X5_MIN_TRADES_FTT OC. El stdout de X4 se captura para no entrelazar salidas.
    """
    n_ini = _n_oc(_cargar_store(activo))
    for ciclo in range(1, n_ciclos + 1):
        cmd = [sys.executable, str(x4_path), '--x5', '--activo', activo]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                               encoding='utf-8', errors='replace')
        n = _n_oc(_cargar_store(activo))
        if proc.returncode != 0:
            tail = ((proc.stderr or '') or (proc.stdout or ''))[-500:]
            print(f'  [{activo}] ciclo {ciclo}: X4 error (cód {proc.returncode}).\n{tail}')
            break
        print(f'  [{activo}] ciclo {ciclo}/{n_ciclos}: {n} OC '
              f'(Δ{n - n_ini:+d} desde el inicio)')
        if n >= cfg.X5_MIN_TRADES_TRAIN:
            _entrenar(activo)  # entrena/reentrena → EXPLOIT usa el modelo actualizado
        if n >= cfg.X5_MIN_TRADES_FTT:
            print(f'  [{activo}] alcanzó {cfg.X5_MIN_TRADES_FTT} OC (umbral FTT). Fin del activo.')
            break
    return activo, _n_oc(_cargar_store(activo))


def _cargar_config_x5():
    """Config dedicada del pipeline X5 (independiente de las versiones de X4).

    Se carga directo desde scripts/config_x5_default.py (versionada en git,
    igual que config.py) — sin copia a resources/x5/, para que un fix en la
    plantilla llegue a todas las máquinas con un simple git pull.
    """
    import importlib.util
    p = Path(__file__).parent / 'config_x5_default.py'
    if not p.exists():
        raise FileNotFoundError(f'Config X5 no encontrada: {p}')
    spec = importlib.util.spec_from_file_location('config_x5', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _recolectar_preguntar_reinicio_todos(activos: list, cfg_x5) -> None:
    """Pregunta reinicio por cada activo antes de lanzar la recolección paralela
    (item 3/4: mismo inicio y mismo significado de 'reiniciar' que el modo
    guiado). Sin TTY (cron / no interactivo) no pregunta nada — comportamiento
    histórico intacto, ningún activo se toca."""
    if not sys.stdin or not sys.stdin.isatty():
        return
    os.environ.pop('X5_DEMO_SUFFIX', None)  # namespace producción
    for a in activos:
        if _demo_preguntar_reinicio(a):
            _borrar_checkpoints_activo(a, cfg_x5, '')


def _recolectar() -> None:
    """
    Orquesta la generación de datos para X5 con **backtesting paralelo por activo**.

    Lanza un worker por activo (ThreadPoolExecutor). Cada worker corre sus
    ciclos de X4 --x5 de forma independiente y entrena su propio modelo al
    cruzar el umbral. Los activos avanzan en paralelo y a distinto ritmo.

    Aislamiento: cada worker usa `bt_{activo}` para el checkpoint/equity de X4
    (no colisionan). El store por activo (`resources/x5/{ACTIVO}_store.csv`) ya
    es independiente por activo. Los activos y N_CICLOS_BT salen de config_x5.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    x4_path = Path(__file__).parent / 'X4_backtester.py'
    if not x4_path.exists():
        print(f'  X4_backtester.py no encontrado en {x4_path}')
        return

    cfg_x5   = _cargar_config_x5()
    activos  = cfg_x5.valores
    n_ciclos = cfg_x5.N_CICLOS_BT

    _recolectar_preguntar_reinicio_todos(activos, cfg_x5)

    n_ini    = {a: _n_oc(_cargar_store(a)) for a in activos}

    print(f'\n{"═" * 72}')
    print(f'  X5 --recolectar (paralelo)  |  config: config_x5  '
          f'|  ciclos máx/activo: {n_ciclos}')
    print(f'{"═" * 72}')
    print(f'  Estado inicial (OC en store):')
    for a in activos:
        print(f'    {a:<8}  {n_ini[a]:>6} OC  (umbral train: {cfg.X5_MIN_TRADES_TRAIN})')
    print(f'\n  Lanzando {len(activos)} workers en paralelo...\n')

    with ThreadPoolExecutor(max_workers=len(activos)) as ex:
        futs = {ex.submit(_worker_recolectar_activo, a, x4_path, n_ciclos): a
                for a in activos}
        for fut in as_completed(futs):
            a = futs[fut]
            try:
                _, n_fin = fut.result()
                print(f'  ✔ [{a}] terminó: {n_ini[a]} → {n_fin} OC')
            except Exception as e:
                print(f'  [ERROR] [{a}] worker falló: {e}')

    print(f'\n{"═" * 72}\n  Recolección finalizada. Estado final:')
    _mostrar_status()


# ─── Recolectar demo (guiado, 1 activo) ───────────────────────────────────────

def _demo_pedir_activo(activos: list) -> str | None:
    """Muestra los activos disponibles numerados y devuelve el elegido."""
    if not sys.stdin or not sys.stdin.isatty():
        print('  El modo demo es interactivo: requiere una terminal (stdin TTY).')
        return None
    print('\n  Activos disponibles:')
    for i, a in enumerate(activos, 1):
        print(f'    {i}. {a}')
    while True:
        sel = input('\n  Ingresa el número del activo para el demo '
                    '(q para salir): ').strip()
        if sel.lower() in ('q', 'quit', 'salir'):
            return None
        if sel.isdigit() and 1 <= int(sel) <= len(activos):
            return activos[int(sel) - 1]
        print('  Entrada inválida. Intenta de nuevo.')


def _demo_preguntar_reinicio(activo: str | None = None) -> bool:
    """Pregunta si reiniciar `activo` desde cero (mismo significado en demo y
    en oficial: ver `_borrar_checkpoints_activo`).

    Devuelve True si el usuario elige reiniciar (se deben borrar todos los
    checkpoints), False si elige continuar (checkpoint acumulativo)."""
    etiqueta = f'[{activo}] ' if activo else ''
    while True:
        resp = input(f'\n  {etiqueta}¿Reiniciar este activo desde cero? '
                     '(0 = no, acumular  |  1 = sí, borrar checkpoints) [0/1]: ').strip()
        if resp in ('0', '1'):
            return resp == '1'
        print('  Entrada inválida. Ingresa 0 o 1.')


def _borrar_resistente(fn, *args, intentos: int = 10, espera: float = 0.5,
                        espera_max: float = 5.0) -> None:
    """Reintenta un borrado (unlink/rmtree) que puede fallar transitoriamente
    por locks de OneDrive/antivirus en Windows sobre archivos recién
    modificados (PermissionError / WinError 5).

    Backoff exponencial (0.5s, 1s, 2s, 4s, 5s, 5s...) hasta ~35s totales: el
    lock de OneDrive sobre un archivo recién escrito puede tardar bastante más
    que 1-2s en soltarse (confirmado en la práctica: 5 intentos a 0.4s no
    alcanzaban y solo se resolvía borrando manualmente minutos después)."""
    for i in range(intentos):
        try:
            fn(*args)
            return
        except PermissionError:
            if i == intentos - 1:
                raise
            time.sleep(min(espera * (2 ** i), espera_max))


def _borrar_checkpoints_activo(activo: str, cfg_x5, suf: str) -> None:
    """Borra TODO lo asociado a `activo` en el namespace `suf` ('' = producción/
    oficial, '_demo' = demo): store, estado del narrador, modelo, historial de
    performance, checkpoint/cache/logs/equity del backtest (bt_{activo}{suf}/,
    incluye conjuntos_N/) y los gráficos de búsqueda de soportes.

    Mismo alcance en ambos namespaces (item 4 — reiniciar = como si el activo
    nunca se hubiera procesado): en oficial esto borra datos reales acumulados,
    no solo los del demo."""
    import shutil

    for p in (CARPETA_X5 / f'{activo}_store{suf}.csv',
              CARPETA_X5 / f'{activo}{suf}_state.json',
              CARPETA_PERFORMANCE / f'{activo}{suf}_performance.json'):
        if p.exists():
            _borrar_resistente(p.unlink)

    md = CARPETA_MODELS / f'{activo}{suf}'
    if md.exists():
        _borrar_resistente(shutil.rmtree, md)

    base_res = cfg_x5.CARPETA_RESOURCES
    bt_dir = base_res.parent / f'{base_res.name}_{activo}{suf}'
    if bt_dir.exists():
        _borrar_resistente(shutil.rmtree, bt_dir)

    plots_dir = CARPETA_X5 / 'demo_plots' / activo
    if plots_dir.exists():
        _borrar_resistente(shutil.rmtree, plots_dir)

    etiqueta = 'demo' if suf else 'oficial'
    print(f'  {activo} ({etiqueta}) reiniciado desde cero: store, modelo, '
          f'checkpoint/cache de backtest y gráficos borrados.')


def _recolectar_preguntar_alcance() -> str:
    """Al inicio de `--recolectar` (sin --demo): todos los activos en paralelo
    y en silencio (comportamiento histórico), o uno solo en un recorrido
    oficial guiado (mismos prints/gráficos que --demo, pero sin pausas).

    Sin TTY (uso no interactivo / cron) cae a 'todos' para no romper ejecuciones
    automatizadas existentes."""
    if not sys.stdin or not sys.stdin.isatty():
        return 'todos'
    while True:
        resp = input('\n  ¿Recolectar para todos los activos en paralelo, o '
                     'para uno solo? (0 = todos, 1 = uno) [0/1]: ').strip()
        if resp in ('0', '1'):
            return 'todos' if resp == '0' else 'uno'
        print('  Entrada inválida. Ingresa 0 o 1.')


def _recolectar_guiado(activo: str, cfg_x5, n_ciclos: int, *, oficial: bool) -> None:
    """
    Recorrido guiado y detallado de X5 --recolectar sobre UN solo activo.

    A diferencia de `_recolectar` (paralelo, silencioso), este recorrido:
      - corre los ciclos de forma SECUENCIAL, con el stdout/stdin de X4
        heredado, para que el narrador (x5_demo) explique en detalle cada
        suceso nuevo (D01..D09) y guarde el gráfico de cada búsqueda de
        soportes;
      - en --demo (oficial=False): trabaja sobre un store y modelo DEMO
        aislados ({activo}_store_demo.csv y models/{activo}_demo) y PAUSA
        (Enter) en cada suceso nuevo;
      - en recolección oficial de un activo (oficial=True): trabaja sobre el
        store y modelo REALES del activo (sin sufijo) y nunca pausa:
        --recolectar debe correr hasta el final sin esperar input.
      En ambos casos se pregunta si reiniciar desde cero (mismo significado
      en los dos namespaces — ver `_borrar_checkpoints_activo`).
    """
    x4_path = Path(__file__).parent / 'X4_backtester.py'
    if not x4_path.exists():
        print(f'  X4_backtester.py no encontrado en {x4_path}')
        return

    etiqueta_store = 'store' if oficial else 'store demo'

    print(f'\n{"═" * 72}')
    if oficial:
        print(f'  X5 --recolectar (oficial, 1 activo)  |  activo: {activo}')
    else:
        print(f'  X5 --recolectar --demo  |  recorrido guiado paso a paso (1 activo)')
    print(f'{"═" * 72}')
    if oficial:
        print('  Mismo recorrido explicado que --demo (D01..D09): mismos prints')
        print('  y gráficos, pero sobre datos reales y sin pausas (Enter).')
    else:
        print('  Cada suceso nuevo del pipeline se explica con un ID único (D01..D09)')
        print('  y se pausa la primera vez que aparece. Una vez visto el bucle')
        print('  recurrente completo, deja de pausar salvo en hitos nuevos.')

    # Namespace demo aislado (store + modelo) solo en --demo. El env lo hereda
    # el subproceso X4; X5_DEMO_PAUSAR='0' → mismo narrador pero sin pausas.
    if oficial:
        os.environ.pop('X5_DEMO_SUFFIX', None)
    else:
        os.environ['X5_DEMO_SUFFIX'] = '_demo'
    os.environ['X5_DEMO_ACTIVO'] = activo
    os.environ['X5_DEMO_PAUSAR'] = '0' if oficial else '1'

    store_path = CARPETA_X5 / f'{activo}_store{_demo_suf()}.csv'
    n_prev = _n_oc(_cargar_store(activo))
    print(f'\n  Estado actual de {activo}: {n_prev} OC en el {etiqueta_store}.')

    if _demo_preguntar_reinicio():
        _borrar_checkpoints_activo(activo, cfg_x5, _demo_suf())
        n_prev = 0
    else:
        print(f'  Continuando: se acumulará sobre el checkpoint existente '
              f'({n_prev} OC en el {etiqueta_store}).')

    x5_demo.activar(activo, pausar=not oficial)

    print(f'\n  Activo: {activo}  |  ciclos máx: {n_ciclos}  '
          f'|  umbral train: {cfg.X5_MIN_TRADES_TRAIN} OC')
    print(f'  {etiqueta_store.capitalize()}: {store_path.name}\n')

    for ciclo in range(1, n_ciclos + 1):
        print(f'\n{"─" * 72}')
        print(f'  Iniciando ciclo {ciclo}/{n_ciclos} de {activo} '
              f'(X4 decide: pasada nueva desde fecha_inicio, o retomar '
              f'checkpoint si quedó interrumpido)')
        print(f'{"─" * 72}')
        os.environ['X5_DEMO_CICLO'] = str(ciclo)  # queda en el nombre de los PNG
        cmd = [sys.executable, str(x4_path), '--x5', '--activo', activo]
        proc = subprocess.run(cmd)  # stdio heredado → pausas del narrador en X4 (si aplica)
        n = _n_oc(_cargar_store(activo))
        if proc.returncode != 0:
            print(f'  ciclo {ciclo}: X4 terminó con error (cód {proc.returncode}).')
            break
        print(f'\n  ciclo {ciclo}/{n_ciclos} completado: {n} OC en el {etiqueta_store}.')
        if n >= cfg.X5_MIN_TRADES_TRAIN:
            x5_demo.evento('D08', activo=activo, n_oc=n,
                           umbral=cfg.X5_MIN_TRADES_TRAIN)
            _entrenar(activo)
        if n >= cfg.X5_MIN_TRADES_FTT:
            break

    n_fin = _n_oc(_cargar_store(activo))
    x5_demo.evento('D09', activo=activo, n_oc=n_fin, store_demo=store_path.name)
    print(f'\n{"═" * 72}')
    if oficial:
        print(f'  Recolección oficial finalizada para {activo}: '
              f'{n_fin} OC en {store_path.name}')
    else:
        print(f'  Demo finalizado para {activo}: {n_fin} OC en {store_path.name}')
        print(f'  (store y modelo demo aislados; tus datos reales quedaron intactos)')
    print(f'{"═" * 72}\n')


def _recolectar_demo() -> None:
    """Pregunta el activo (lista numerada) y corre el recorrido guiado en
    modo --demo (store/modelo aislados, con pausas)."""
    cfg_x5  = _cargar_config_x5()
    activo = _demo_pedir_activo(cfg_x5.valores)
    if activo is None:
        print('  Demo cancelado.')
        return
    _recolectar_guiado(activo, cfg_x5, cfg_x5.N_CICLOS_BT, oficial=False)


def _recolectar_uno_oficial(activo: str, cfg_x5) -> None:
    """Corre el recorrido guiado sobre el store/modelo REALES de un activo
    (sin pausas): misma narración y gráficos que --demo, en producción."""
    _recolectar_guiado(activo, cfg_x5, cfg_x5.N_CICLOS_BT, oficial=True)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='X5 Surrogate Model — ajusta config_params dinámicamente por activo'
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--recolectar', action='store_true',
                     help='Genera datos (X4 --x5) + auto-entrena. Pregunta al inicio: '
                          'todos los activos en paralelo, o uno solo en recorrido oficial guiado')
    grp.add_argument('--infer',      action='store_true',
                     help='Recomienda params con el modelo actual → active_parameters.json')
    grp.add_argument('--status',     action='store_true',
                     help='Diagnóstico: n_trades y modelo activo por activo')
    parser.add_argument('--train',   action='store_true',
                        help='Casilla: con --infer, reentrena antes de recomendar')
    parser.add_argument('--demo',    action='store_true',
                        help='Con --recolectar: recorrido guiado paso a paso de UN activo (lo pregunta al inicio)')
    parser.add_argument('--activo', default=None,
                        help='Procesar solo este activo (ej. BTCUSD)')
    args = parser.parse_args()

    if args.status:
        _mostrar_status()
        return

    if args.recolectar:
        if args.demo:
            _recolectar_demo()
        elif _recolectar_preguntar_alcance() == 'todos':
            _recolectar()
        else:
            cfg_x5 = _cargar_config_x5()
            activo = _demo_pedir_activo(cfg_x5.valores)
            if activo is None:
                print('  Recolección cancelada.')
            else:
                _recolectar_uno_oficial(activo, cfg_x5)
        return

    # --infer (único modo de inferencia). --train (opcional) reentrena antes.
    activos = [args.activo] if args.activo else cfg.VALORES

    if args.train:
        print('\n─── Reentrenamiento ──────────────────────────────────────')
        for activo in activos:
            _entrenar(activo)

    print('\n─── Inferencia ───────────────────────────────────────────')
    resultados: dict = {}
    for activo in activos:
        params, status = _inferir_params(activo)
        resultados[activo] = (params, status)
        n_sz = params.get('n_sizes_ejecucion', '?')
        lm   = params.get('LOTAJES_M', '?')
        k    = params.get('K', '?')
        print(f'  [{activo}]  {status:<9}  N={n_sz}  K={k}  LM={lm}')
    _escribir_active_parameters(resultados)


if __name__ == '__main__':
    main()
