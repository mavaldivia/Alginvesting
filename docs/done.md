## Done

### X5 — X5_macro_brain.py

- [x] **X4: modo `--x5` — captura X3/X2 y escritura al store**: implementado en `X4_backtester.py`. (a) `ts_oe_creacion` propagado desde OE al OA en `_paso_B`; (b) `_paso_F` guarda `x3_oe`/`x2_oe` en el dict OE; (c) `_paso_B` captura `x3_oa`/`x2_oa` al ejecutar la OA; (d) `_paso_D`/`_paso_E` construyen fila `tipo_registro="oc"` completa (params, temporal OE/OA, X3/X2 OE/OA, portfolio, `retorno_pct`) y la escriben a `resources/x5/{ACTIVO}_store.csv`; (e) fila `tipo_registro="periodico"` cada `X5_FREQ_REGISTRO_PERIODICO` velas con OA activas. Nuevos helpers: `_features_temporales_ts`, `_leer_x2_bt`, `_compute_x5_snapshot`, `_contexto_portfolio_x5`, `_construir_fila_oc`, `_construir_fila_periodica`, `_append_x5_store`. `min_lotajes` se pasa desde `ejecutar_x5_ciclo` a `ejecutar_backtest` para calcular `LOTAJES_M` correctamente.

### X1 — X1_trading.py

- [x] **Config de X1 alineado al formato de X5 (por activo) + N=250**: en `config.py`, `n_sizes` y `n_sizes_ejecucion` → 250 en todos los activos; `A`/`B`/`PERDIDA_MAX` convertidos de escalar a dict por activo manteniendo su valor actual (4 / 1.5 / 120). `X1_trading.py` ahora indexa `A[valor]`/`B[valor]`/`PERDIDA_MAX[valor]` en `crear_ordenes_espera`, `trailing_stop`, `controlar_perdida_max` e `informacion` (firma `a: dict`). `X5_macro_brain._params_baseline` lee `cfg.A[activo]`/`cfg.B[activo]`/`cfg.PERDIDA_MAX[activo]`. X4/X5 ya estaban en formato X5 → sin cambios de valor. `TIPO_EJECUCION` queda `"est"` (fija, sin dinamismo hasta validar X5). `config.py` ya está versionado (no en `.gitignore`), así que sincroniza a Windows por `git pull`.
