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

## 2026-06-03 — Data/ y conjuntosN2/ fuera de git

**Decisión:** los archivos generados (CSVs de precios y pickles de soportes) no se trackean en git.
**Razón:** son artefactos de ejecución, se regeneran corriendo X0 en Windows. Incluirlos en git es ruido y pesa.
