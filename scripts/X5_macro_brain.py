"""
X5_macro_brain.py

Surrogate model de Alginvesting. Aprende la relación:
    f(contexto X2+X3, config_params) → retorno_esperado
y optimiza config_params en inferencia para cada activo.

Modos:
  python scripts/X5_macro_brain.py --vela   # inferir params con modelo actual (cada vela H1)
  python scripts/X5_macro_brain.py --train  # reentrenar desde cero con el store acumulado
  python scripts/X5_macro_brain.py --infer  # inferir sin reentrenar
  python scripts/X5_macro_brain.py --status # diagnóstico: n_trades, modelo activo por activo

Fases de rollout:
  Fase 1 (TIPO_EJECUCION="est"): --train entrena el modelo sobre el store generado
    por x5_macrobrain.py (backtester). --vela y --infer solo infieren params y
    escriben active_parameters.json. X1 no lee ese archivo todavía.
  Fase 2 (TIPO_EJECUCION="din"): X1 escribe la OC al store y llama --vela al
    cierre de cada vela H1. X5 actualiza el modelo e infiere. X1 lee
    active_parameters.json por activo; activos con model_status="untrained"
    hacen fallback automático a config.py.
"""

import argparse
import json
import pickle
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg

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

TARGET_RETORNO  = 'retorno_pct'
TARGET_FLOTANTE = 'pnl_flotante_activo'
TARGET_CERRADO  = 'pnl_cerrado_activo_sesion'

# ─── Store ───────────────────────────────────────────────────────────────────

def _cargar_store(activo: str) -> pd.DataFrame:
    path = CARPETA_X5 / f'{activo}_store.csv'
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


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
        'A':           cfg.A,
        'B':           cfg.B,
        'LOTAJES_M':   cfg.LOTAJES_M[activo],
        'PERDIDA_MAX': cfg.PERDIDA_MAX,
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
    tipo_registro: str = 'oc',
) -> tuple:
    """
    Retorna (X, y, sample_weight) para el target indicado.
    Aplica ponderación temporal exponencial: registros recientes pesan más.
    """
    if store.empty:
        return np.array([]), np.array([]), np.array([])

    df = store[store['tipo_registro'] == tipo_registro].copy()
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


def _x2_actual(activo: str) -> dict:
    """Último snapshot de X2 disponible para el activo."""
    path = cfg.CARPETA_FUNDAMENTALS / 'x2_history.json'
    if not path.exists():
        return {}
    with open(path) as f:
        hist = json.load(f)
    entradas = hist.get(activo, [])
    if not entradas:
        return {}
    ultima = max(entradas, key=lambda e: e.get('fecha', ''))
    return {k: v for k, v in ultima.items() if k != 'fecha'}


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
    """Persiste métricas en resources/x5/Performance/{activo}_performance.json como historial."""
    CARPETA_PERFORMANCE.mkdir(parents=True, exist_ok=True)
    path = CARPETA_PERFORMANCE / f'{activo}_performance.json'
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
    return CARPETA_MODELS / activo

# ─── LightGBM ────────────────────────────────────────────────────────────────

def _entrenar_lgbm(activo: str, store: pd.DataFrame) -> bool:
    if not _LGBM_OK:
        print(f'  [{activo}] lightgbm no instalado → pip install lightgbm')
        return False

    feature_cols = _feature_cols_de_store(store)
    out = _model_dir(activo)
    out.mkdir(parents=True, exist_ok=True)

    targets = {
        'retorno':  (TARGET_RETORNO,  'oc'),
        'flotante': (TARGET_FLOTANTE, 'oc'),
        'cerrado':  (TARGET_CERRADO,  'oc'),
    }

    exito = True
    metricas: dict = {}
    n_train_total = n_test_total = 0
    for key, (target_col, tipo_reg) in targets.items():
        X, y, w = _preparar_features(store, feature_cols, target_col, tipo_reg)
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

    X, y_r, w = _preparar_features(store, feature_cols, TARGET_RETORNO, 'oc')
    if len(X) < 50:
        print(f'  [{activo}] FTT: solo {len(X)} filas OC — insuficientes.')
        return False

    n = len(X)
    _, y_f, _ = _preparar_features(store, feature_cols, TARGET_FLOTANTE, 'oc')
    _, y_c, _ = _preparar_features(store, feature_cols, TARGET_CERRADO, 'oc')
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

def _rango(param_store: str, activo: str) -> tuple:
    """Rango de búsqueda para el param (nombre de store) del activo dado."""
    range_key = _PARAM_TO_RANGE_KEY.get(param_store, param_store)
    return cfg.X5_PARAM_RANGES[range_key][activo]

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


def _inferir_params(activo: str) -> tuple:
    """
    Carga el modelo guardado e infiere los params óptimos para el contexto actual.
    Retorna (params_dict_json, model_status).
    En Fase 1 = solo inferencia (pasos 2-4 del ciclo por vela). No hay captura live.
    """
    store = _cargar_store(activo)
    n     = _n_oc(store)
    tipo  = _seleccionar_tipo(n)

    if tipo == 'untrained':
        return _params_baseline(activo), 'untrained'

    contexto = _leer_contexto_actual(activo)

    if tipo == 'lgbm':
        loaded = _cargar_lgbm(activo)
        if loaded is None:
            print(f'  [{activo}] Modelo LGBM no encontrado → ejecutar --train primero.')
            return _params_baseline(activo), 'untrained'
        models, feature_cols = loaded
        params = _inferir_lgbm(activo, models, contexto, feature_cols)

    else:  # ftt
        loaded = _cargar_ftt(activo)
        if loaded is None:
            print(f'  [{activo}] Modelo FTT no encontrado → ejecutar --train primero.')
            return _params_baseline(activo), 'untrained'
        model, scaler, feature_cols = loaded
        params = _inferir_ftt(activo, model, scaler, contexto, feature_cols)

    params = _aplicar_airbag(activo, params)
    return params, tipo

# ─── Output JSON ──────────────────────────────────────────────────────────────

def _escribir_active_parameters(resultados: dict) -> None:
    """
    Escribe config/active_parameters.json.
    resultados: {activo: (params_dict, model_status)}
    """
    ACTIVE_PARAMS.parent.mkdir(parents=True, exist_ok=True)
    out: dict = {'generated_at': datetime.now().isoformat(timespec='seconds')}
    for activo, (params, status) in resultados.items():
        out[activo] = {'model_status': status, **params}
    with open(ACTIVE_PARAMS, 'w') as f:
        json.dump(out, f, indent=2)
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

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='X5 Surrogate Model — ajusta config_params dinámicamente por activo'
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--vela',   action='store_true',
                     help='Inferir params con el modelo actual (producción, cada vela H1)')
    grp.add_argument('--train',  action='store_true',
                     help='Reentrenar modelo desde cero con el store acumulado')
    grp.add_argument('--infer',  action='store_true',
                     help='Solo inferir params sin reentrenar')
    grp.add_argument('--status', action='store_true',
                     help='Diagnóstico: n_trades y modelo activo por activo')
    parser.add_argument('--activo', default=None,
                        help='Procesar solo este activo (ej. BTCUSD)')
    args = parser.parse_args()

    if args.status:
        _mostrar_status()
        return

    activos = [args.activo] if args.activo else cfg.VALORES

    if args.train:
        print('\n─── Reentrenamiento ──────────────────────────────────────')
        for activo in activos:
            _entrenar(activo)

    if args.train or args.infer or args.vela:
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
