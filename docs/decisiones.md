# Decisiones técnicas — Alginvesting

## 2026-06-03 — Migración de notebooks a .py

**Decisión:** migrar X0 y X1 de `.ipynb` a `.py`.
**Razón:** facilita control de versiones, ejecución en Windows sin Jupyter, y mantiene el código más limpio para refactors con Claude Code.
**Descartado:** mantener notebooks para todo — dificulta el diff en git y el flujo Mac→Windows.
**Excepción:** módulos nuevos con componente visual importante pueden iniciar como `.ipynb` durante exploración.

## 2026-06-03 — Alginvesting_base como solo lectura

**Decisión:** `Alginvesting_base/` se agrega al `.gitignore` del nuevo proyecto y se trata como referencia histórica inmutable.
**Razón:** es el repo clonado desde Windows (versión anterior). Mezclar código nuevo con ese directorio genera confusión.

## 2026-06-03 — Migración X0: eliminación de versiones obsoletas del optimizador

**Decisión:** en `X0_data_supports.py` se conservó solo `nuevo_optimizador_2`. Se eliminaron `buscar_soportes_optimos` v1–v5, `nuevo_optimizador_0/1`, `obtener_df_extremos` V1, y funciones de OC/SL (pertenecen a X1).
**Razón:** el notebook acumuló versiones históricas del algoritmo. Solo V2 del optimizador se llamaba en la ejecución real.
**Parámetro `prueba260417`:** era un flag siempre `True` → se eliminó y se dejó solo el branch activo (ajuste cuadrático + fallback idxmax).

## 2026-06-03 — Data/ y conjuntosN2/ fuera de git (revertida 2026-06-07, ver más abajo)

**Decisión:** los archivos generados (CSVs de precios y pickles de soportes) no se trackean en git.
**Razón:** son artefactos de ejecución, se regeneran corriendo X0 en Windows. Incluirlos en git es ruido y pesa.

## 2026-06-07 — Vectorización de `calcular_distancias` por bloques

**Decisión:** reemplazar el doble loop Python (`for i / for j` con `.loc` escalar) por `_vecino_mas_cercano`, que vectoriza con numpy procesando la serie en bloques de filas (`BLOQUE_DISTANCIAS = 2000`).
**Razón:** con `FECHA_INICIAL='2024-01-01'` las series superan 20k velas (BTCUSD ≈ 21k). El loop puro tardaba ~34s por (valor, N); vectorizado toma ~1.8s — mismos resultados byte a byte.
**Descartado:** construir la matriz booleana (n × n) completa de una sola vez — para n≈21k son ~450M elementos, demasiada memoria considerando que corre en paralelo (`ProcessPoolExecutor`) para ~48 pares (valor, N). El procesamiento por bloques acota la memoria a `block_size × n` por iteración.

## 2026-06-07 — Data/ vuelve a trackearse en git (revierte la decisión del 2026-06-03)

**Decisión:** sacar `Data/` del `.gitignore` y trackear los CSVs de precios en git.
**Razón:** `descargar_datos` solo trae las últimas 1000 velas H1 de MT5 (~41 días) y hace merge + `drop_duplicates` con el CSV existente. Si el CSV no existe (ej. checkout nuevo en Windows sin `Data/`), se pierde toda la historia previa a esa ventana — en este caso, ~2 años desde `FECHA_INICIAL=2024-01-01`. Versionar `Data/` en git asegura que esa historia viaje con el repo y no dependa de copiar carpetas a mano entre máquinas.
**Costo aceptado:** ~14MB iniciales (10 activos) que crecerán con cada actualización — el repo va a pesar más con el tiempo.
