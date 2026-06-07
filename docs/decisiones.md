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

## 2026-06-07 — Vectorización de `asignar_soporte` con búsqueda binaria

**Decisión:** reemplazar `df['Low'].apply(lambda x: min(soportes, key=...))` por `np.searchsorted` sobre el array ordenado de soportes, comparando solo contra el vecino izquierdo y derecho.
**Razón:** `calcular_FO` (que llama `asignar_soporte`) se invoca miles de veces por iteración del optimizador (hasta N×M ≈ 13.000 con N=130, M=100). El `apply` original es O(n×N) — con n≈40k velas y N=130 son ~5M comparaciones en Python puro por llamada. La búsqueda binaria baja esto a O(n log N), vectorizado en numpy: ~45-178x más rápido (0.26s → 0.0014s por llamada en BTCUSD), mismos resultados byte a byte verificados contra datos reales.
**Nota sobre empates:** en un empate exacto de distancias, el original depende del orden de iteración del `set` de Python (arbitrario, basado en hash) mientras la versión nueva elige el soporte menor. En la práctica esto no ocurre: `conjunto_N` se construye solo con floats continuos (`np.random.uniform`, `np.linspace`, `np.polyfit`) y `ordenes_activas=[]` en el único call site — la probabilidad de un empate exacto en float64 es ≈0.

## 2026-06-07 — Documentación del efecto de cada parámetro del algoritmo en CLAUDE.md

**Decisión:** agregar la sección "Parámetros del algoritmo — efecto de cada uno" (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL) directamente en `CLAUDE.md`, no en un doc aparte de `docs/`.
**Razón:** es contenido de referencia que se necesita consultar en cada sesión de trabajo sobre el algoritmo (tuning, debugging de resultados) — `CLAUDE.md` se carga siempre, un doc en `docs/` requeriría abrirlo a mano.
**Nota:** la descripción de cada parámetro es matemática/direccional (qué pasa al subir o bajar el valor); las decisiones de "cuál es el valor correcto" siguen siendo criterio del usuario, no se proponen valores nuevos.

## 2026-06-07 — Data/ vuelve a trackearse en git (revierte la decisión del 2026-06-03)

**Decisión:** sacar `Data/` del `.gitignore` y trackear los CSVs de precios en git.
**Razón:** `descargar_datos` solo trae las últimas 1000 velas H1 de MT5 (~41 días) y hace merge + `drop_duplicates` con el CSV existente. Si el CSV no existe (ej. checkout nuevo en Windows sin `Data/`), se pierde toda la historia previa a esa ventana — en este caso, ~2 años desde `FECHA_INICIAL=2024-01-01`. Versionar `Data/` en git asegura que esa historia viaje con el repo y no dependa de copiar carpetas a mano entre máquinas.
**Costo aceptado:** ~14MB iniciales (10 activos) que crecerán con cada actualización — el repo va a pesar más con el tiempo.
