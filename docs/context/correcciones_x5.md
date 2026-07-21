# Correcciones X5 — desacople de la recolección respecto a las versiones de X4

## Síntoma

`python scripts/X5_macro_brain.py --recolectar` fallaba con:

```
KeyError: 'GOOGL'   (y 'TSLA', 'NVDA', 'AMZN')
  X4_backtester.py:1139, en ejecutar_x5_ciclo
    'n_sizes_ejecucion': cfg.n_sizes[activo],
```

Solo BTCUSD/ETHUSD sobrevivían; los otros 4 activos morían en el ciclo 1.

## Causa raíz (arquitectural, no un archivo faltante)

La recolección de X5 estaba **acoplada a los configs congelados de las versiones de X4**:

1. `X5 --recolectar` tenía `--version` con default `'V1'` y se lo pasaba a cada worker.
2. El worker lanzaba `X4_backtester.py --x5 --version V1 --activo {A}`.
3. X4, incluso en modo `--x5`, hacía `cfg = _cargar_config(args.version)` → cargaba
   `resources/x4/versionV1/config_V1.py`.
4. Ese `config_V1.py` está congelado con `valores = ['BTCUSD', 'ETHUSD']` y
   `n_sizes = {'BTCUSD': 70, 'ETHUSD': 70}` → `cfg.n_sizes['GOOGL']` → `KeyError`.

El problema conceptual: **la recolección de X5 no tiene relación con las versiones
V0/V1/... de X4** (esas son experimentos de backtesting con parámetros fijos). Ya
existía `resources/x5/config_x5.py` — pensado para esto, con los 6 activos, sus
`X5_PARAM_RANGES`, `EXPLORATION_RATE`, `N_CICLOS_BT` y A/B/PERDIDA_MAX por activo —
pero **el cableado nunca se hizo**: X4 seguía leyendo el config de versión, y los
rangos/exploración salían de `config.py` (main), no de `config_x5.py`.

## Solución — X4 en modo `--x5` usa `config_x5.py`

### `resources/x5/config_x5.py`
- Agregado `version = 'x5'` (X4 lo usa en prints; no es una versión de X4).
- Agregadas rutas de aislamiento del backtest por activo:
  `CARPETA_RESOURCES = _X5_DIR / 'bt'` y `CARPETA_LOGS_BT`. Cada worker deriva
  `bt_{activo}` para checkpoint/equity/logs → los 6 procesos paralelos no colisionan.

### `scripts/X4_backtester.py`
- Nuevo `_cargar_config_x5()`: carga `resources/x5/config_x5.py`.
- `__main__`: si `--x5`, usa `_cargar_config_x5()` en vez de `_cargar_config(version)`.
  El flag `--version` se ignora en modo `--x5`.
- `_generar_params_explore(cfg)`: lee `cfg.X5_PARAM_RANGES` (antes venía de
  `config.py` main vía `cfg_global`). Eliminado el parámetro `cfg_global`.
- `ejecutar_x5_ciclo`: usa `cfg.EXPLORATION_RATE` (de config_x5, antes
  `config.py`). Eliminado `import config as cfg_global`.
- **Colapso de dicts por activo**: en `config_x5`, `A`/`B`/`PERDIDA_MAX_BT` son dict
  por activo, pero el core de X4 los usa como escalares. Como cada proceso `--x5`
  corre un solo activo, al fijar `cfg.valores = [activo]` se reemplazan esos tres
  por su valor escalar de ese activo. (Sin esto también rompería, aparte del
  KeyError de `n_sizes`.)

### `scripts/X5_macro_brain.py`
- Eliminado `--version` del CLI y de `_recolectar` / `_worker_recolectar_activo`.
- Nuevo `_cargar_config_x5()` en X5: lee `valores` y `N_CICLOS_BT` desde
  `config_x5.py` (antes `cfg.VALORES` y `cfg.X5_N_CICLOS_BT` de `config.py` main).
- El worker ya no pasa `--version V1` a X4; el n.º de ciclos viene por parámetro.

## Verificación

- Corrida aislada `X4_backtester.py --x5 --activo GOOGL`: arranca como "versión x5",
  N=180, hace cold start, ejecuta el backtest y genera trades. Sin KeyError.
- `X5_macro_brain.py --recolectar`: los 6 workers (incluidos TSLA/GOOGL/NVDA/AMZN)
  corren en paralelo leyendo `config_x5`. Sin errores en el arranque.

## Pendiente / notas

- `resources/x4/versionV1/config_V1.py` y el template de
  `X4B_crear_version_backtesting.py` siguen con solo 2 activos. Es correcto: son
  para el backtesting de versiones de X4, no para X5. No se tocaron.
- La ruta hardcodeada `carpeta_n_prod` en `_recalcular_soportes` (X4:139) apunta a
  `resources/conjuntos_N` de producción — compartida entre versiones y X5 como
  warm-start de soportes. No se modificó.
