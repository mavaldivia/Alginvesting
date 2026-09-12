## Done

### X5 — X5_macro_brain.py

- [x] **X4: modo `--x5` — captura X3/X2 y escritura al store**: implementado en `X4_backtester.py`. (a) `ts_oe_creacion` propagado desde OE al OA en `_paso_B`; (b) `_paso_F` guarda `x3_oe`/`x2_oe` en el dict OE; (c) `_paso_B` captura `x3_oa`/`x2_oa` al ejecutar la OA; (d) `_paso_D`/`_paso_E` construyen fila `tipo_registro="oc"` completa (params, temporal OE/OA, X3/X2 OE/OA, portfolio, `retorno_pct`) y la escriben a `resources/x5/{ACTIVO}_store.csv`; (e) fila `tipo_registro="periodico"` cada `X5_FREQ_REGISTRO_PERIODICO` velas con OA activas. Nuevos helpers: `_features_temporales_ts`, `_leer_x2_bt`, `_compute_x5_snapshot`, `_contexto_portfolio_x5`, `_construir_fila_oc`, `_construir_fila_periodica`, `_append_x5_store`. `min_lotajes` se pasa desde `ejecutar_x5_ciclo` a `ejecutar_backtest` para calcular `LOTAJES_M` correctamente.

### X1 — X1_trading.py

- [x] **Config de X1 alineado al formato de X5 (por activo) + N=250**: en `config.py`, `n_sizes` y `n_sizes_ejecucion` → 250 en todos los activos; `A`/`B`/`PERDIDA_MAX` convertidos de escalar a dict por activo manteniendo su valor actual (4 / 1.5 / 120). `X1_trading.py` ahora indexa `A[valor]`/`B[valor]`/`PERDIDA_MAX[valor]` en `crear_ordenes_espera`, `trailing_stop`, `controlar_perdida_max` e `informacion` (firma `a: dict`). `X5_macro_brain._params_baseline` lee `cfg.A[activo]`/`cfg.B[activo]`/`cfg.PERDIDA_MAX[activo]`. X4/X5 ya estaban en formato X5 → sin cambios de valor. `TIPO_EJECUCION` queda `"est"` (fija, sin dinamismo hasta validar X5). `config.py` ya está versionado (no en `.gitignore`), así que sincroniza a Windows por `git pull`.

### X5_P1 — X5_P1.ipynb

- [x] Confirmar con Mauricio las decisiones de la sección 5 de `X5_alternativo.md` antes de escribir código: frecuencia H1 + forward-fill de X2 confirmado, fuente de precio `Data/BTCUSD.csv` tal cual confirmado, parámetros de configuración (K, N_EXP, LAMBDA, etc.) descartados. Distancia a soportes: se aclaró el concepto (feature de X3 que mide cercanía al soporte más próximo) y se confirmó omitirla por ahora.
- [x] **X5_P1 — crear notebook y cargar precio**: creado `scripts/X5_P1.ipynb`, parametrizado por `{valor}` (`BTCUSD`); lee `Data/{valor}.csv`, parsea `DateTime`, ordena y elimina duplicados.
- [x] **X5_P1 — calcular indicadores técnicos**: llama `_calcular_todos_indicadores(df, set())` de `X3_technical_features.py` sobre el histórico completo, sin distancia a soportes (columnas `dist_nearest_support`/`dist_floor_support`/`density_2pct` descartadas); columnas prefijadas `x3_*`.
- [x] **X5_P1 — mergear fundamentales de X2**: carga `resources/x2/x2_history.json`, filtra por `{valor}`, extrae `score`/`score_cross`/`score_tendencia` como `x2_*` y pega a la tabla H1 con `merge_asof` (dirección `backward`).
- [x] **X5_P1 — ensamblar DataFrame final**: una fila por vela H1 con columnas de precio (OHLCV) + `x3_*` + `x2_*` (37 columnas, 40.283 filas para BTCUSD).
- [x] **X5_P1 — guardar tabla final**: a `resources/x5_alt/{valor}_tabla_maestra.csv`. Nueva ruta `CARPETA_X5_ALT` agregada a `config.py`. Nota: el precio en Mac termina 2026-06-02 y los únicos 2 registros de X2 para BTCUSD son 2026-06-12/14 (posteriores), así que hoy `x2_score` queda NaN en el 100% de las filas — limitación de datos ya anticipada en el plan, no un bug.
