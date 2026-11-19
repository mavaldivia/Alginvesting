## TO DO

**Convención de priorización**: cada ítem pendiente lleva `(I:x C:y H:z → score)` — Impacto, Complejidad de desarrollo, Habilitación, escala 1–10. `score = √(I × H) / C`. Dentro de cada sección los ítems se ordenan de mayor a menor score.

**Convención de labores** (en todo el archivo): cada ítem lleva, cuando corresponde, sub-líneas `Claude:` (lo que hago yo, en Mac) y `Mauricico:` (lo que ejecuta/decide Mauricico, típicamente en Windows con MT5/datos reales, o decisiones que le competen). Si uno de los dos no tiene labor en ese ítem, no se escribe esa línea.

### X1 — Robustez y estabilidad

- [x] **Agrupar prints de órdenes ejecutadas/eliminadas**: en vez de un print por orden, mostrar resumen por activo: `{valor}: {h} órdenes ejecutadas (o eliminadas) desde {min_precio} hasta {max_precio}`.
  - Claude: implementar el agrupador de prints en `X1_trading.py`.
  - Mauricico: ejecutar X1 en Windows y confirmar el formato agrupado en vivo.

### X4 — X4_backtester.py

> Plan de implementación: [`docs/plans/x4_plan.md`](../plans/x4_plan.md)

- [ ] **X4.py**: implementar según `docs/plans/x4_plan.md`. Config, estructura de carpetas, lógica de trading y secuencia de fases ya documentadas. (I:9 C:8 H:9 → 1.13)
  - Claude: implementar `X4_backtester.py` completo según el plan (config, estructura de carpetas, lógica de trading, fases).
  - Mauricico: ejecutar el backtester en Windows con datos reales y validar resultados.

### X5 — X5_macro_brain.py

> Fusiona los roles originales de X5 y X6 (ver `docs/context/decisiones.md` 2026-06-26).
> Código y plan movidos a `Otros/` (ver [`docs/context/propuesta_restructuracion.md`](../context/propuesta_restructuracion.md)) — dejó de ser el foco día a día, sin cerrar estos pendientes.
> Plan de implementación: [`Otros/docs/plans/x5_plan.md`](../../Otros/docs/plans/x5_plan.md)

> **Pipeline de generación de datos**: `X5 --recolectar` lanza `X4 --x5` en modo backtesting multi-ciclo.
> X4 simula trades vela a vela capturando X3+X2 en OE/OA/OC y escribe a `resources/x5/{ACTIVO}_store.csv`.
> Al cruzar `X5_MIN_TRADES_TRAIN`, X5 entrena automáticamente el modelo LGBM.
> Items 1→2→5→4→3 son la secuencia de implementación; el orden de arriba es por score.





**Puntos a validar tras el reinicio de BTCUSD (2026-08-31)** — se detectó y corrigió un bug de desalineación de columnas en el store (ver `docs/context/decisiones.md`) y se cambió el target de `retorno_pct` a `retorno_usd`. Antes de confiar en datos/modelo nuevos:

- [ ] Antes de considerar el modelo confiable, revisar `resources/x5/Performance/BTCUSD_performance.json`: R² test positivo y no muy por debajo del train para el target `retorno` (ya redefinido en USD). (I:7 C:1 H:8 → 7.48)
  - Mauricico: revisar el JSON de performance en Windows y confirmar que el R² test es sano.
- [ ] Tras recolectar un lote nuevo, correr `--status` y confirmar que el conteo de OC coincide 1:1 con las filas realmente válidas (`retorno_usd` no vacío) — 0% de corrupción, a diferencia del 79.6% que tenía el store viejo. (I:6 C:1 H:7 → 6.48)
  - Mauricico: correr `X5 --status` en Windows y confirmar el conteo.
- [ ] Revisar 5-10 filas nuevas del store (con pandas/csv, no Excel) y confirmar rangos sanos: `hora`/`hora_oa` en [0,23], `x2_score`/`x2_score_oa` en [0,1], `retorno_usd` en escala de dólares razonable (no ~1e-5 como el `retorno_pct` viejo). (I:5 C:1 H:6 → 5.48)
  - Mauricico: revisar las filas del store en Windows (pandas/csv, no Excel).
- [ ] No abrir ni guardar `{ACTIVO}_store.csv` desde Excel mientras el backtester lo está escribiendo — riesgo de reintroducir corrupción de BOM/separador decimal (ver commits `fix(x4,x5)` recientes). (I:4 C:1 H:3 → 3.46)
  - Mauricico: evitar abrir/guardar el store desde Excel mientras el backtester lo está escribiendo.
- [ ] Si más adelante se activan los otros 5 activos, correr el mismo chequeo de corrupción (0% esperado) antes de asumir que sus stores están limpios — el bug era del código compartido, pero conviene confirmar con datos reales de cada uno. (I:5 C:2 H:5 → 2.50)
  - Mauricico: correr el mismo chequeo de corrupción para los otros activos en Windows.
- [ ] **Actualizar docs de X5**: revisar `X5_macro_brain.py` (`Otros/scripts/`) en su estado actual y actualizar `Otros/docs/plans/x5_plan.md` y `Otros/docs/plans/x5_plan_redes_neuronales.md` para que reflejen la implementación real (funciones existentes, estructura del store, CLI disponible, métricas calculadas). (I:3 C:3 H:3 → 1.00)
  - Claude: revisar `X5_macro_brain.py` y actualizar `x5_plan.md`/`x5_plan_redes_neuronales.md` para que reflejen la implementación real.
- [ ] **Head `flotante` con filas periódicas en FT-Transformer**: en LightGBM el target `pnl_flotante_activo` ya entrena con filas `('oc','periodico')`, pero en FTT los 3 heads comparten el mismo tensor `X` (solo filas `oc`), así que las periódicas no llegan al head flotante. Incorporarlas vía pase separado o Deep Sets en V2 (aplica cuando el store supere `X5_MIN_TRADES_FTT`). Ver `Otros/docs/plans/x5_opus_review.md` y TO DOs de `x5_plan.md`. (I:3 C:6 H:2 → 0.41)
  - Claude: implementar el pase separado o Deep Sets para incorporar las filas periódicas al head flotante en FTT.
  - Mauricico: ejecutar el entrenamiento en Windows una vez el store supere `X5_MIN_TRADES_FTT` y validar resultados.

### X5_alt — versión alternativa y simplificada de X5

> Versión paralela a X5 (no la reemplaza). Contexto completo: [`docs/plans/X5_alternativo.md`](../plans/X5_alternativo.md)
> `X5_P1` y `X5_P2` reciben `{valor}` (el activo) como input — inicialmente `BTCUSD`.
> Especificación completa de `X5_P2.ipynb` (notebook exhaustivo de investigación, no un script de carga): [`docs/plans/solicitud_claude_code_X5_P2_notebook_v2.md`](../plans/solicitud_claude_code_X5_P2_notebook_v2.md).
> El orden de abajo es por score, no de implementación: Fase 1 (X5_P1) debe completarse antes que Fase 2 (X5_P2.ipynb). Dentro de Fase 2, respetar el orden narrativo de la sección 15 de ese documento: tabla maestra válida → auditoría inicial suficiente → core variable vs. precio → profundización de relaciones → cerrar lo descriptivo antes de dar protagonismo a lo prospectivo → hipótesis para P3 solo al final.

**Core descriptivo/histórico**

- [ ] **X5_P2 — auditoría e inventario inicial de la tabla maestra**: cargar la salida de X5_P1, validar `DateTime`, orden, duplicados, rango, tipos y construir el inventario de variables con familia Precio/Técnico/Fundamental/Otra, cobertura, missingness y frecuencia observada. Mantener esta sección concisa y orientada a habilitar rápido el core variable-precio. (I:8 C:2 H:8 → 4.00)
  - Claude: implementar la carga, validaciones e inventario de variables en el notebook.
  - Mauricico: ejecutar el notebook en Windows con datos reales y revisar el inventario resultante.
- [ ] **X5_P2 — frecuencia efectiva de actualización**: medir cada cuánto cambia realmente cada variable, diferenciando frecuencia de filas de llegada efectiva de nueva información; prestar especial atención a fundamentales y forward-fill. (I:8 C:2 H:8 → 4.00)
  - Claude: implementar el análisis de frecuencia efectiva por variable.
  - Mauricico: ejecutar en Windows y revisar resultados, especialmente fundamentales con forward-fill.
- [ ] **X5_P2 — no linealidades y umbrales**: ampliar el análisis variable-precio mediante cuantiles, bins, suavizados, extremos, posibles umbrales, saturaciones, formas U/U invertida y asimetrías, evitando asumir que Pearson/regresión lineal capturan toda la relación. (I:8 C:3 H:7 → 2.49)
  - Claude: implementar el análisis de cuantiles/bins/suavizados/umbrales en el notebook.
  - Mauricico: ejecutar en Windows y revisar los gráficos resultantes.
- [ ] **X5_P2 — variable vs. comportamiento histórico reciente del precio**: relacionar cada variable con retornos pasados del precio en distintos horizontes (`t-h → t`) para caracterizar qué venía ocurriendo con BTC cuando la variable toma determinados valores. Mantener este análisis dentro de la capa descriptiva, separado de retornos futuros. (I:8 C:3 H:7 → 2.49)
  - Claude: implementar el análisis de variable vs. retornos pasados por horizonte.
  - Mauricico: ejecutar en Windows y revisar resultados.
- [ ] **X5_P2 — estabilidad histórica de las relaciones**: medir Pearson/Spearman y, cuando corresponda, coeficientes ceteris paribus por períodos y ventanas móviles para detectar relaciones persistentes, inestables o cambios estructurales. (I:8 C:3 H:7 → 2.49)
  - Claude: implementar el cálculo de Pearson/Spearman/ceteris paribus por ventanas móviles.
  - Mauricico: ejecutar en Windows y revisar la estabilidad resultante.
- [ ] **X5_P2 — análisis por regímenes**: comparar las relaciones variable-precio bajo contextos como bull/bear/sideways, volatilidad alta/baja, drawdown y tendencia, definiendo cada régimen explícitamente y evitando segmentaciones arbitrarias. (I:8 C:4 H:7 → 1.87)
  - Claude: implementar la definición de regímenes y el análisis comparativo.
  - Mauricico: ejecutar en Windows y revisar resultados por régimen.
- [ ] **X5_P2 — relaciones entre variables y redundancia**: estudiar técnicos vs. técnicos, fundamentales vs. fundamentales y técnicos vs. fundamentales; identificar pares o grupos con información muy similar mediante correlaciones y, solo si aporta interpretabilidad, clustering/PCA. (I:7 C:3 H:6 → 2.16)
  - Claude: implementar el análisis de correlación/redundancia entre variables (y clustering/PCA si aporta).
  - Mauricico: ejecutar en Windows y revisar qué variables resultan redundantes.
- [ ] **X5_P2 — síntesis descriptiva y ranking de variables**: consolidar por variable frecuencia efectiva, Pearson, Spearman, relación con retornos históricos, no linealidad, estabilidad, régimen, redundancia y nivel de evidencia descriptiva. No convertir este ranking automáticamente en ranking predictivo. (I:8 C:3 H:6 → 2.31)
  - Claude: implementar la tabla de síntesis y ranking descriptivo.
  - Mauricico: revisar el ranking resultante.
- [ ] **X5_P2 — síntesis específica de técnicos y fundamentales**: generar una lectura consolidada separada de ambos universos, considerando especialmente las diferencias de frecuencia y disponibilidad de información. (I:6 C:3 H:4 → 1.63)
  - Claude: implementar la lectura consolidada separada por universo.
  - Mauricico: revisar la síntesis resultante.

**Prospectivo / potencial predictivo**

- [ ] **X5_P2 — relaciones temporales pasado/contemporáneo/futuro**: construir para variables relevantes una radiografía temporal que permita distinguir si una variable parece rezagada, contemporánea o potencialmente adelantada, separando explícitamente `X_t ↔ retorno pasado`, `X_t ↔ precio actual` y `X_t ↔ retorno futuro`. (I:8 C:3 H:7 → 2.49)
  - Claude: implementar la radiografía temporal por variable.
  - Mauricico: ejecutar en Windows y revisar resultados.
- [ ] **X5_P2 — variable actual vs. retornos futuros por horizonte**: estudiar asociación con retornos posteriores en horizontes coherentes con la granularidad disponible, dejando explícito que asociación histórica futura no equivale por sí sola a capacidad predictiva. (I:7 C:3 H:6 → 2.16)
  - Claude: implementar el análisis de asociación con retornos futuros por horizonte.
  - Mauricico: ejecutar en Windows y revisar resultados.
- [ ] **X5_P2 — validación temporal preliminar sin leakage**: si se prueban modelos o relaciones prospectivas, usar particiones temporales/walk-forward simples para verificar estabilidad fuera de muestra sin convertir P2 en un proyecto de forecasting. (I:7 C:4 H:5 → 1.48)
  - Claude: implementar las particiones walk-forward simples si se prueban relaciones prospectivas.
  - Mauricico: ejecutar en Windows y revisar la estabilidad fuera de muestra.

**Hipótesis para X5 / puente hacia P3**

- [ ] **X5_P2 — traducir evidencia robusta a hipótesis para parámetros X5**: transformar los hallazgos descriptivos/prospectivos en hipótesis explícitas del tipo `θ_k = f_k(X)`, sin implementarlas todavía como reglas de trading. Ejemplos candidatos: `N=f(drawdown)` y `A=f(volatilidad)`. (I:9 C:2 H:10 → 4.74)
  - Claude: redactar las hipótesis explícitas `θ_k = f_k(X)` a partir de los hallazgos.
  - Mauricico: revisar y validar las hipótesis propuestas.
- [ ] **X5_P2 — tabla final variable → parámetro candidato**: cerrar P2 con una tabla que documente variable explicativa, evidencia histórica, estabilidad, régimen, potencial prospectivo, parámetro X5 candidato, relación hipotética y prioridad de prueba en P3. (I:8 C:2 H:9 → 4.24)
  - Claude: construir la tabla final.
  - Mauricico: revisar y validar la tabla final.

**Transversales / implementación**

- [ ] **X5_P2 — documentación Markdown de investigación**: cada sección y subsección relevante debe comenzar obligatoriamente con una celda Markdown que explique objetivo, pregunta, metodología, interpretación y limitaciones antes del código; agregar interpretación posterior cuando el análisis lo amerite. (I:8 C:2 H:8 → 4.00)
  - Claude: agregar las celdas Markdown de objetivo/pregunta/metodología/interpretación en cada sección.
- [ ] **X5_P2 — revisar `X5_analisis_exploratorio.ipynb`**: revisar el notebook existente que ya hace un análisis ceteris paribus sobre el store de eventos de X5 actual y decidir qué lógica conviene reutilizar, adaptar o descartar para evitar duplicación innecesaria. (I:6 C:2 H:7 → 3.24)
  - Claude: revisar el notebook existente y proponer qué lógica reutilizar, adaptar o descartar.
  - Mauricico: confirmar la decisión antes de avanzar.
- [ ] **X5_P2 — orden del notebook por relevancia analítica**: estructurar cada parte desde el mapeo más importante/general hacia análisis progresivamente más particulares, manteniendo el bloque variable-precio como núcleo temprano de la fase descriptiva. (I:9 C:2 H:8 → 4.24)
  - Claude: estructurar el notebook en el orden narrativo acordado.
- [ ] **X5_P2 — ejecución end-to-end y validación final**: ejecutar el notebook completo desde cero, comprobar reproducibilidad, ausencia de errores, generación de tablas/gráficos y consistencia de resultados antes de considerar P2 terminado. (I:9 C:2 H:9 → 4.50)
  - Mauricico: ejecutar el notebook completo en Windows desde cero y validar reproducibilidad/resultados.

**X5_P1 relacionado**

- [ ] **X5_P1 — reporte de calidad de datos**: mantener en P1 la responsabilidad de validar la calidad de construcción de la tabla maestra: `% missing`, huecos temporales del precio, cobertura real de fundamentales y efecto de forward-fill. P2 debe consumir y contextualizar esta información, no reemplazar la responsabilidad de P1. (I:7 C:2 H:8 → 3.74)
  - Claude: implementar el reporte de calidad de datos en P1 (% missing, huecos, cobertura, forward-fill).
  - Mauricico: ejecutar en Windows y revisar el reporte.

**Fase 3**

- [ ] **Fase 3 (`X5_alternativo.py`) — no comenzar todavía**: definir su arquitectura y reglas recién después de observar resultados concretos de X5_P1 y X5_P2. P2 debe terminar en evidencia e hipótesis, no en reglas prescriptivas implementadas. (I:3 C:2 H:3 → 1.50)

**Puente hacia estudio de parámetros de X5 (post-P2)**

- [ ] **X5 — estudio posterior de parámetros manipulables y variables explicativas**: una vez terminado el análisis exploratorio de `X5_P2.ipynb`, usar sus resultados como insumo para estudiar de qué deberían depender los parámetros configurables de X5 (`N`, `A`, `B`, pérdida máxima, `K`, y cualquier otro relevante). Escapa parcialmente del alcance operativo de P2 — es puente hacia la siguiente etapa, no responsabilidad de implementación inmediata del notebook. Para cada parámetro: documentar qué controla, en qué etapa actúa, qué variables podrían explicarlo, signo esperado, rango permitido, riesgo económico asociado y cómo se validará. Hipótesis prioritaria ya registrada sobre `N`: no debería definirse a partir de relaciones genéricas del CSV de P2, sino tener relación directa (posiblemente única) con el drawdown de la cuenta para ese activo — `N = f(drawdown_del_valor)`, con la intuición de que a peor drawdown, `N` más defensivo/bajo. Resultado esperado: tabla `Parámetro X5 | Qué controla | Variable(s) candidata(s) | Hipótesis de relación | Evidencia (P2) | Cómo validar`, con `N` ya completo y el resto (`A`, `B`, pérdida máxima, `K`) por determinar según lo que arroje P2. Validación final: backtesting global. (I:10 C:4 H:10 → 2.50)
  - Claude: construir la tabla `Parámetro X5 | Qué controla | Variable(s) candidata(s) | Hipótesis | Evidencia (P2) | Cómo validar` a partir de los resultados de X5_P2.
  - Mauricico: validar la tabla resultante (en particular la hipótesis `N = f(drawdown_del_valor)`) y correr el backtesting global final en Windows.

### X5_alt_v2 — evolución paralela de X5_alt (Q1/Q2/Q3)

> Evoluciona a la sección **X5_alt** de arriba sin reemplazarla — v1 (`X5_P1.ipynb`/`X5_P2.ipynb`) queda congelada en `scripts/otros_strings/` como referencia histórica; sus ítems pendientes de arriba se mantienen intactos pero sin más trabajo activo.
> **Documento rector** (prevalece sobre cualquier definición anterior en caso de contradicción): [`docs/plans/x5_contexto_conversacion.md`](../plans/x5_contexto_conversacion.md). Parámetros `Y` a explicar, con su definición exacta: [`docs/context/pars_configurables.md`](../context/pars_configurables.md). Contexto y estado de avance: [`docs/plans/X5_alternativo.md`](../plans/X5_alternativo.md), sección 10.
> Tres notebooks en `scripts/`, parametrizados por `valores` — **lista** de activos, declarada al comienzo de cada notebook, default `['BTCUSD']` (a diferencia del `valor` singular de v1) —, todo el análisis por activo (nunca drawdown/exposición de cuenta agregada): `X5_Q1.ipynb` (tabla + variables de estado), `X5_Q2.ipynb` (core descriptivo: correlación clásica + coseno + regímenes + estabilidad + export), `X5_Q3.ipynb` (hipótesis parámetro↔variable + tabla final).
> **En esta sección el orden de abajo ES el orden de implementación** (a diferencia del resto del TO DO, aquí no se prioriza por score): cada ítem quedó ubicado después de todos sus `[dep: ...]`, así que trabajarlos de arriba hacia abajo, en orden, nunca topa con una dependencia pendiente. Dentro de cada notebook se respeta además el orden narrativo ya validado (core variable-precio primero, profundización después, regímenes/estabilidad al final de la capa descriptiva en Q2; hipótesis individuales antes de la tabla final en Q3).
> **Convención de dependencias (solo esta sección)**: cada ítem lleva un ID entre corchetes al inicio del título y un tag `[dep: ...]` al final (`[dep: —]` si no depende de nada). El score `(I:x C:y H:z → score)` se conserva solo como referencia de impacto — no determina el orden de lectura ni de ejecución aquí. Si se reordena o agrega un ítem más adelante, verificar que siga después de todos sus `[dep: ...]`; si al empezar un ítem falta alguna dependencia sin marcar `[x]` (movida a `done.md`), **advertir explícitamente cuál falta y no avanzar con ese ítem**.
> **Export a zip (Windows → Mac)**: cada notebook `X5_Q*.ipynb` debe cerrar con una celda que llame a `exportar_zip(nombre_notebook, archivos)` (`scripts/x5_alt_export.py`) sobre los archivos que generó en `resources/x5_alt/` — ya implementado en `X5_Q1.ipynb` (Sección 11); replicar al construir `X5_Q2.ipynb` (ítem `[Q2-5]` o `[Q2-EXEC]`) y `X5_Q3.ipynb` (ítem `[Q3-4]` o `[Q3-EXEC]`). Detalle en `docs/plans/X5_alternativo.md` sección 10.2.
> **Fase 2 — funciones dinámicas (`Q4`/`Q5`)**: con `Q1`/`Q2`/`Q3` cerrados (2026-10-12) y `Q4` cerrado (2026-11-02; funciones finales en [`docs/context/funciones_pars_dinamicos.pdf`](../context/funciones_pars_dinamicos.pdf), pisos y techos en `scripts/config_smart.py`), el plan completo de esta fase (forma funcional, mecanismo de calibración, combinaciones parámetro↔variable, alcance de cada notebook) vive en [`docs/plans/plan_x5_alt_v2.md`](../plans/plan_x5_alt_v2.md) — no duplicar acá, solo los ítems. Módulo compartido `scripts/x5_alt_funciones.py` ya implementado y probado (matemática pura, no requiere `Data`/MT5).

**Q1 — X5_Q1.ipynb (tabla maestra + variables de estado del activo)**

**Q2 — X5_Q2.ipynb (core descriptivo: correlación clásica + coseno + regímenes + estabilidad + export)**

**Q3 — X5_Q3.ipynb (hipótesis parámetro↔variable + tabla final)**

**Q4 — X5_Q4.ipynb (calibración de diseño: sigmoide acotada por parámetro, `plan_x5_alt_v2.md`)**

**Q5 — Backtesting inteligente (validación económica: puente a `X4_backtester.py`, `plan_x5_alt_v2.md` sección 9)**

> **Actualización 2026-11-17**: el aprendizaje pasa de vueltas completas a **ventanas semanales** (`Q5-3c`, `Q5-4`, `Q5-5`; diseño en `plan_x5_alt_v2.md` §9.14): cada ventana parte en un `t*` (bisección sobre la historia), con cuenta nueva de 3000 USD, `lotajes_m = 1` y una sola búsqueda de soportes; el label es `Y = cerrado + P&L abierto − 3000`. Sin vuelta completa: la validación es fuera de muestra por `t*`. Los puntos *Una vuelta*, *Aprendizaje* y *Compuerta* de abajo quedan reemplazados por eso; cuenta, stop-out, registro y paralelismo se mantienen.
> **Diseño (decidido 2026-11-02, precisado el mismo día; reemplaza al del 2026-10-23; ver `docs/context/decisiones.md` y `plan_x5_alt_v2.md` §9)**. Lo conceptual completo vive en el plan; acá solo lo necesario para trabajar cada ítem.
> - **Parámetros**: los 7 de primera categoría (C1: `N`, `A`, `factor_B`, `K`, `N_EXP`, `LAMBDA`, `PERDIDA_MAX`) salen de una función de los de segunda categoría (C2: `span`, `punto_medio`, `pendiente` y pesos `w_i`, normalizados `w̃_i = w_i / Σ w_j`). 26 grados de libertad por valor.
> - **Una vuelta** por valor = backtest completo desde el 2022-03-01 (`FECHA_INICIO_BT`, fija, 60 días de calentamiento; los soportes usan datos desde `FECHA_INICIAL`, 2022-01-01) hasta la última vela con los C2 fijos; al terminar se aprende y se corrigen los C2. Cada valor es independiente (un proceso por valor, `--activo`).
> - **Cadencias**: cada `n_velas` (`N_VELAS` en `config_smart.py`: 168 crypto, 35 acción, por defecto) se recalculan `N`, `K`, `N_EXP`, `LAMBDA` y se hace una búsqueda nueva de soportes; cada vela se recalculan `A`, `factor_B` (con `B = factor_B · A`) y `PERDIDA_MAX`. Cada C1 se lleva al valor permitido más cercano de su grilla (`PASOS_*` en `config_smart.py`).
> - **Cuenta por valor**: 3000 USD de capital inicial; `Z = cerrado + P&L abierto`; `lotajes_m = max(1, (Z − 6000) // 3000 + 2)`; `perdida_max_USD = p · Z` por orden abierta, sin escalar por lotaje (ej. `p = 0.04`, `Z = 5000` → 200 USD).
> - **Aprendizaje**: premio del tramo de aprendizaje `Z_tongo = Z al corte / velas hasta el corte` (el tramo reservado no entra); Sobol en las primeras vueltas, luego Regresión Lineal Múltiple (RLM) `Z_tongo = f(C2)` con `GRADO` de `config_smart.py` (1 por defecto, 2 suma productos cruzados) y Gradient Ascent para mover levemente cada C2.
> - **Compuerta**: el último tramo de la historia (20% por defecto) no se usa para aprender; un candidato se promueve solo si supera al estático y a `Q4` en ese tramo, y se confirma con velas nuevas y aprobación manual antes de producción.
> - **Stop-out**: la vuelta no se corta; sigue "como si el valor de la cuenta fuera negativo" y el evento se registra como KPI.
> - **Registro y monitoreo** (`plan_x5_alt_v2.md` §9.10): toda vuelta registra siempre sus datos (`{valor}_vueltas.csv`, `{valor}_seguimiento.csv`, `{valor}_aprendizaje.csv` más los archivos de X4) y cada `n_velas`, después de la búsqueda de soportes, imprime un resumen con status, cerrado, P&L abierto, `Z`, `lotajes_m`, trades, drawdown, C1 vigentes y FO de la búsqueda.
> - **Ejecución** (§9.11): los 7 valores (incluido MSFT) corren en paralelo, un proceso por valor, independientes entre sí.
> - **Pausado**: la prueba de tres niveles de agregación (`Q5-6`); por ahora cada valor independiente.
> **Decisiones de Mauricio (convención de este bloque)**: todo lo que Mauricio debe aclarar está marcado `[DECIDE MAURICIO]` dentro del ítem donde se necesita, con valor por defecto cuando existe. Como los ítems se ejecutan en orden, al empezar cada uno Claude lista sus `[DECIDE MAURICIO]` y espera la respuesta antes de implementar; los marcados `(después de ver resultados)` se deciden con datos de una corrida del mismo ítem o de uno anterior. Si Mauricio responde "defaults", se usan los valores sugeridos. Resumen (`Q5-1`, `Q5-2` y las de `Q5-3` ya resueltos, ver `decisiones.md` 2026-11-14): `Q5-4` vueltas Sobol y criterio de término; `Q5-5` candidato, umbral de promoción, paso del gradiente y grado; `Q5-5b` reglas de cuenta en X0/X1, `K`/`N_EXP`/`LAMBDA` por valor y velas nuevas exigidas; `Q5-6` normalización del target agrupado.
> **Construye sobre**: `X4_backtester.py` (modo `--x5` y `--activo`, `_aplicar_params_x5`, checkpoint y equity aislados por activo, `_calcular_estado_cuenta`/`_append_equity`); el backtesting inteligente es un script nuevo (`X4S_backtesting_inteligente.py`, nombre provisional) que importa de `X4_backtester.py`, sin modo `--smart` ni `X4B` (decidido 2026-11-03); de `Q4` toma `{valor}_q4_resumen.csv` (coeficientes de partida, `μ`/`σ`), `x5_alt_funciones.py` (matemática de `P̂_t`) y `config_smart.py`. Nunca reimplementa X0/X1.
> **Riesgos abiertos** (detalle en `plan_x5_alt_v2.md` §9.9): (1) una observación por valor y vuelta contra 26 dimensiones: `Q5-1` mide cuánto dura una vuelta; (2) X4 usa un solo `cfg.LOTAJES[activo]` por activo y `lotajes_m(Z)` exige un lote por posición; (3) el caché de soportes está indexado por `N` y con `N` dinámico rompe el warm start; (4) `μ`/`σ` de `Q4` usan todo el histórico (look-ahead); (5) `N_VELAS` de acciones (35) y los pasos son valores por defecto sin verificar.

- [ ] **[Q5-3b] Riesgo por cuenta: umbral de pérdida por tramos de `lotajes_m` y tope de órdenes** *(APLAZADO 2026-11-18: las ventanas de `Q5-3c` corren sin tope de órdenes ni umbral por tramos; se retoma si las ventanas muestran que hace falta)*: la vuelta `q4_s0_v2` de BTCUSD (2026-11-15) repitió el desplome de la anterior: en el bloque 9 (2022-05-03) había 45 Órdenes Abiertas (OA) con un umbral de 81 USD cada una (unos 3.600 USD posibles contra `Z = 1.759`) y en el bloque 10 el cerrado cayó de 2.958 a 396 USD. Con `perdida_max = p · Z` el riesgo se mide por posición, no por cuenta, así que varias posiciones perdiendo a la vez pueden superar `Z`. Se detuvo la vuelta; las nuevas con estos C1 volverían a quebrar. (I:9 C:5 H:8 → 1.80) [dep: Q5-3]
  - Mauricio (decidido 2026-11-15): el umbral deja de ser `p · Z` continuo y pasa a tramos como `lotajes_m`: `perdida_max_USD = p · 3000 · m` (`m = lotajes_m(Z)`; con `p = 0.044` y `m = 1` son 132 USD fijos mientras `Z < 6000`); el rango de `p` sigue 3 % a 6 % para todos los tramos. X1 ya escala su `PERDIDA_MAX` por el múltiplo de lote, así que el esquema es coherente con producción.
  - Claude (propuesto, sin implementar): como el umbral ya no baja con la cuenta, hace falta un tope sobre las órdenes: `máx. órdenes = r · Z / umbral`, con `r` la fracción de `Z` que se acepta perder si todas llegan a su umbral. Ej. con `r = 0.5`, `p = 0.044`, `m = 1`: `Z = 3000` → 11 órdenes; `Z = 1759` → 6; `Z = 400` → 1; bajo `Z ≈ 264` no se abren órdenes. Se implementaría en `_paso_F` de `X4_backtester.py` (junto al guard de margen) y en `config_smart.py`; X1 no se toca hasta `Q5-5b` (hoy `lotajes_m(Z)` y `p · Z` solo existen en X4/X4S). Pruebas en `test_x4s_backtesting_inteligente.py`.
  - Resuelto 2026-11-18: `r = 0,5` fijo, parámetro de `config_smart.py` editable en caliente (no es un C1, el sorteo Sobol se mantiene en 26 dimensiones). Significa que si todas las órdenes permitidas llegaran a su umbral a la vez, la pérdida máxima sería el 50 % de `Z`; el tope solo bloquea órdenes nuevas, no cierra las ya abiertas.
  - Resuelto 2026-11-18: el tope cuenta solo las Órdenes Abiertas (OA): se mantiene la escalera de Órdenes en Espera (OE) y se cancelan al llenarse el cupo (consecuencia aceptada: una vela que cae a través de muchos soportes puede llenar varias OE a la vez y pasarse del tope). Bajo `Z ≈ 264` (= umbral 132 USD / `r` 0,5) el tope da 0 órdenes y la cuenta deja de operar: confirmado.
  - Al retomar: partir explicando qué es `Z` con el ejemplo del bloque 9 (`cerrado 2.957,97 + P&L abierto -1.199,10 = Z 1.758,87`), porque en la sesión del 2026-11-15 Mauricio pidió aclararlo antes de decidir `r` y qué cuenta contra el tope; después reformular las dos preguntas con ese ejemplo.
- [ ] **[Q5-3c] Ventana semanal en X4S: cuenta nueva, una búsqueda de soportes en `t*` y label `Y`** *(decidido 2026-11-17: el aprendizaje pasa de vueltas completas a ventanas semanales, ver `plan_x5_alt_v2.md` §9.14)*: nuevo modo de `X4S_backtesting_inteligente.py` (importa de `X4_backtester.py`, sin reimplementar X0/X1) que ejecuta una **ventana**: una semana de backtest que parte en `t*`. Reglas: (1) cuenta nueva de 3000 USD con `lotajes_m = 1` fijo y sin órdenes heredadas de otra ventana; (2) los soportes se buscan una sola vez, en `t*`, con la historia desde `FECHA_INICIAL` hasta `t*`, con el algoritmo de X0 y un tope de 10 min (parámetro propio en `config_smart.py`, distinto del tope de 6 min de X4/X5), sin warm start entre ventanas (el caché depende del orden en que corren); (3) los C2 de la ventana (sorteados o propuestos por el aprendizaje) fijan `N`, `K`, `N_EXP` y `LAMBDA` en `t*` (la ventana equivale a un `N_VELAS` en crypto, así que `N_VELAS` no interviene) y `A`, `factor_B` y `PERDIDA_MAX` se leen por vela; (4) la ventana dura una semana de calendario (`VENTANA_DIAS = 7` en `config_smart.py`): 168 velas H1 en crypto y las velas H1 de esos 7 días en acciones (35–50, confirmado 2026-11-18); (5) label `Y = cerrado + P&L abierto − 3000` al cerrar la ventana (Órdenes Abiertas (OA) valoradas a mercado, Órdenes en Espera (OE) canceladas sin efecto); stop-out sin corte, como en 9.7; (6) sin tope de órdenes ni umbral de pérdida por tramos (`Q5-3b` aplazado el 2026-11-18): `PERDIDA_MAX` sigue siendo un C1 y rige como en `Q5-3`, `p · max(Z, 0)` por orden. Variables de mercado de la ventana (siempre de la ventana misma, hora por hora, nunca de los 7 días previos a `t*`; confirmado 2026-11-18), solo con precios de cierre: con `C_0` el cierre previo a `t*` y `C_1, …, C_n` los cierres de la semana, `r_i = C_i / C_{i−1} − 1`; `ret_medio = (1/n) Σ r_i` y `ret_vol` = desviación estándar muestral de los `r_i` (retornos porcentuales, no precios). Se registran siempre, aunque el aprendizaje aún no las use. Registro por ventana en `resources/x5_alt/q5/{valor}_ventanas.csv` (id, `t*`, fecha, `semilla`, `replica_de`, fase (Sobol o aprendizaje), C2 completos, C1 de la ventana, `Y`, `ret_medio`, `ret_vol`, KPIs: drawdown máximo, trades, tasa de aciertos, tiempo en mercado, margen usado, stop-outs, `frac_oa_abiertas_cierre` (OA abiertas al cierre / posiciones abiertas en la ventana), `sin_trades` (ninguna OE se ejecutó, `Y = 0`), duración de cómputo). La unidad reanudable pasa a ser la ventana (~10 min): `--reanudar` omite las ventanas ya registradas. (I:9 C:6 H:9 → 1.50) [dep: Q5-3]
  - Claude: implementar el modo ventana, el registro y las pruebas (`test_x4s_backtesting_inteligente.py`: misma semilla y mismos C2 dan el mismo `Y`; la cuenta parte limpia en cada `t*`); reutilizar `_procesar_candle`, la cuenta y los KPIs de `Q5-3`.
  - Resuelto 2026-11-18: en acciones la ventana también son 7 días de calendario, hora a hora (35–50 velas H1 según el activo); `ret_vol` es la desviación estándar muestral de los `r_i`.
  - Resuelto 2026-11-18: `Q5-3` cerrado sin la corrida de vuelta completa (movido a `done.md`); en acciones el retorno entre la última vela de una sesión y la primera de la siguiente (salto nocturno) entra tal cual en `ret_medio` y `ret_vol`, porque son cierres de velas correlativas; sin columna aparte.
  - [DECIDE MAURICIO] (después de ver resultados): largo de la ventana. Una semana trunca el ciclo de las órdenes: las OE sin llenar dan `Y = 0` y las OA abiertas al cierre se valoran a mercado sin cerrar su trailing stop, lo que premia configuraciones de rotación rápida. Con `frac_oa_abiertas_cierre` y el porcentaje de ventanas `sin_trades` de las primeras ventanas, decidir si alargar a 2–4 semanas.
  - Mauricico (labor, pendiente): ejecutar unas pocas ventanas en Windows con datos reales (BTCUSD y una acción) y revisar `{valor}_ventanas.csv` y el resumen en pantalla.
- [ ] **[Q5-4] Orquestador por valor y muestreo por ventanas: `t*` en bisección, C2 por Sobol y control estático**: al comienzo solo BTCUSD (`--activo BTCUSD`, decidido 2026-11-18); después, un lanzador que arranca los demás valores (uno por proceso, incluido MSFT), cada uno independiente, con su propio registro y log; si uno cae, los otros siguen y solo ese se reanuda (omite las ventanas ya registradas). Antes de lanzar varios a la vez hay que medir CPU y memoria: con el tope de 10 min por búsqueda, `Y` depende de la carga de la máquina. Con `T_tot` velas de historia desde `FECHA_INICIO_BT` (2022-03-01, `t = 0`) y `T = T_tot − semana`, los `t*` se eligen por bisección: los extremos `0` y `T`, el punto medio `T/2`, los puntos medios de esos intervalos (`T/4`, `3T/4`) y así sucesivamente (ejemplo con `T = 1000`: 0, 1000, 500, 250, 750, 125, 375, 625, 875, …); cualquier prefijo de la secuencia cubre la historia de forma pareja, así que se puede detener en cualquier momento. Los C2 de cada ventana se sortean con Sobol (siempre los cuatro grupos, 26 dimensiones) en las primeras ventanas y después los entrega el aprendizaje (`Q5-5`). **Ventanas reservadas**: el 20% de las ventanas (`FRACCION_RESERVADA` en `config_smart.py`), elegidas al azar con semilla fija entre los `t*` de la bisección (no un tramo final del calendario). No entran al aprendizaje, ni tampoco las ventanas de aprendizaje que se solapen en velas con una reservada (solo ocurre pasadas ~250 ventanas, `T/168`). **Control estático**: en cada ventana reservada se corren la configuración estática actual (`P_ESTATICO = 0.067`) y los C2 de la calibración de `Q4`, con las mismas reglas de cuenta, y el candidato cada vez que se evalúa una promoción, para comparar por la diferencia de `Y` en la misma `t*`. Costo estimado (inferido de los ~10 min por búsqueda de `Q5-3`, sin medir): 10–12 min por ventana; 32 ventanas ≈ 6 h por valor; ~250 ventanas sin solape (con ~42.000 velas en BTCUSD) ≈ 46 h por valor. (I:8 C:5 H:8 → 1.60) [dep: Q5-3c]
  - Claude: implementar el orquestador, el generador de `t*` (bisección con tramo reservado), el sorteo Sobol y el control estático y `Q4` en las ventanas reservadas.
  - Claude: cada ventana registra su `semilla` de la intra-vela y se programan ventanas de réplica (mismos `t*` y C2, otra semilla) del estático y de la mejor, para medir el ruido de `Y` (`plan_x5_alt_v2.md` §9.13). [DECIDE MAURICIO] cuántas réplicas (por defecto 3 sobre la estática).
  - [DECIDE MAURICIO] (antes de implementar): (1) ventanas Sobol antes de pasar al aprendizaje: 32 por defecto (potencia de 2 sobre los 27 coeficientes del grado 1, o 29 con las dos variables de mercado; el 16 del 2026-11-10 era para vueltas de ~50 h y ya no aplica); (2) criterio de término por valor: máximo de ventanas, tiempo máximo o correr hasta que Mauricio lo detenga (con bisección cualquier corte deja cobertura pareja); (3) confirmar el 20% de ventanas reservadas al azar con exclusión de las solapadas (cada reservada cuesta ~10 min por configuración: estático, `Q4` y cada candidato evaluado).
  - Mauricico (labor): dejar corriendo las ventanas por activo en Windows.
- [ ] **[Q5-5] Aprendizaje por ventanas (RLM + Gradient Ascent) y compuerta en las ventanas reservadas**: tras cada ventana de aprendizaje, Regresión Lineal Múltiple (RLM) de `Y` sobre los C2 del valor y las variables de mercado `ret_medio` y `ret_vol` (forma de entrada por definir, ver abajo), con `GRADO` de `config_smart.py` (1 por defecto: 27 coeficientes solo con C2; 2 agrega productos cruzados sin cuadrados: 352) y regularización ridge; los pesos entran como `w̃` omitiendo uno por grupo para evitar la colinealidad `Σ w̃ = 1`. Gradient Ascent mueve cada C2 un paso (fracción de su rango, recortado a los límites; `w̃` se proyecta al símplex; `span` redondeado a entero). Se usa Sobol hasta superar el umbral de ventanas de `Q5-4` y RLM + Gradient Ascent después; `t*` sigue su bisección sin depender del aprendizaje. Compuerta: un candidato se promueve solo si supera al estático y a la calibración de `Q4` en las ventanas reservadas (diferencia de `Y` en la misma `t*`); se reporta el drawdown máximo sin optimizarlo. Sin vuelta completa: la validación final es fuera de muestra, en las ventanas reservadas al azar. Para elegir la penalización ridge y el `GRADO` se usa validación cruzada (cross-validation) de 5 pliegues (20% al azar cada uno, semilla fija) sobre las ventanas de aprendizaje: mide el error fuera de pliegue reajustando solo la RLM, sin backtests extra. (I:9 C:7 H:7 → 1.13) [dep: Q5-4]
  - Claude: implementar el modelo, el paso de gradiente, el cambio de fase y la evaluación sobre las ventanas reservadas.
  - Claude: la RLM y el sorteo trabajan sobre la lista completa de variables de la estructura (columnas constantes omitidas); `{valor}_ventanas.csv` lleva `version_estructura`; al agregar una variable, exploración corta (Sobol solo sobre `w̃` nuevo y el `punto_medio`/`pendiente` del C1) antes de volver al Gradient Ascent; ante una redefinición, arranque por bloques con indicadora de versión (§9.12).
  - [DECIDE MAURICIO] (por definir, dejado para darle una vuelta el 2026-11-17): cómo entran `ret_medio` y `ret_vol` al modelo. La idea de Mauricio es "aislar ese efecto" del mercado de la semana sobre `Y`. Opciones planteadas: controles aditivos `Y = f(C2) + g(ret_medio, ret_vol)` (29 coeficientes en grado 1; los C2 óptimos no dependen del régimen) o interacciones C2 × régimen (81 coeficientes; en producción habría que estimar el régimen futuro). Ojo: ambas variables se miden después de `t*`, así que no sirven para elegir C2 en producción salvo estimándolas. No bloquea `Q5-3c` ni `Q5-4`: se registran desde la primera ventana.
  - [DECIDE MAURICIO] (antes de implementar): (1) qué se evalúa en las ventanas reservadas como candidato (los C2 que propone la RLM + Gradient Ascent tras `k` ventanas, o los de mejor `Y` medio) y cuándo "supera" al estático y a `Q4` (basta superarlo o se exige un margen mínimo); (2) umbral de ventanas para pasar de Sobol a RLM (por defecto, el de `Q5-4`); (3) paso del gradiente (por defecto 10% del rango de cada C2) y grado inicial (`GRADO = 1`).
  - [DECIDE MAURICIO] (después de ver resultados): ajustar el paso del gradiente, probar `GRADO = 2` (por el error de la validación cruzada) y decidir si dejar una fracción de ventanas con Sobol durante la fase RLM (si el Gradient Ascent concentra los C2, la RLM pierde variación para estimar).
  - [DECIDE MAURICIO] (después de ver resultados; pospuesto el 2026-11-18): (1) criterio de "no hay señal": si tras las ventanas Sobol el R² fuera de pliegue queda en ≈ 0, seguir hasta N ventanas, reducir dimensiones con `Q5-7` o detener; (2) colas pesadas de `Y` (unas pocas semanas de caída dominan la RLM): winsorizar `Y` o normalizarlo por `ret_vol`.
  - Mauricico (labor): dejar corriendo el proceso en Windows y revisar los resultados por ventana.
- [ ] **[Q5-5b] Traspaso de la configuración candidata a X0/X1 con compuerta manual**: archivo de candidata aparte; antes de aprobar, confirmación con velas nuevas posteriores a la elección; aprobación de Mauricio; lectura vía `TIPO_EJECUCION="din"`. Hay que decidir cómo llegan a X0/X1 las reglas de cuenta propias de `Q5` (`lotajes_m(Z)`, `perdida_max = p · Z`, grilla de pasos), que hoy no existen en producción. Pasa a automático con reglas de seguridad más adelante. (I:9 C:6 H:5 → 1.12) [dep: Q5-5]
  - Claude: implementar la escritura de la candidata y la lectura en X0/X1 sin duplicar su lógica.
  - [DECIDE MAURICIO] (antes de implementar): (1) cómo llegan a X0/X1 las reglas de cuenta de `Q5` (`lotajes_m(Z)`, `perdida_max = p · Z`, grilla de pasos): Claude presenta 2 opciones; (2) `K`, `N_EXP` y `LAMBDA` son globales en X0 y `Q5` los calibra por valor: decidir si pasan a ser por valor en X0 (decisión arquitectónica, `plan_x5_alt_v2.md` §6); (3) cuántas velas nuevas, o meses de datos nuevos, se exigen antes de aprobar una candidata.
  - Mauricico (labor): aprobar cada candidata mientras la compuerta sea manual.
- [ ] **[Q5-7] Análisis de las ventanas y sugerencias de cambio de C2**: cuando haya ventanas acumuladas, Mauricio pide a Claude el análisis estadístico de `resources/x5_alt/q5/` y sugerencias de cambio de los C2 (rangos de sorteo, `span`, `punto_medio`, `pendiente`, pesos y variables, ver `plan_x5_alt_v2.md` §9.12 y §9.13). El análisis cubre: efecto de cada C2 sobre el premio con error estándar y error leave-one-out de la Regresión Lineal Múltiple (RLM), ruido de `Y` con las ventanas de réplica, saturación de cada C1 en `piso`/`techo`, tendencia de `w̃` por variable, `Y` de las ventanas de aprendizaje contra las reservadas, consistencia entre los 7 valores. Si hay menos ventanas que coeficientes, se limita a lo descriptivo. Cada sugerencia de variable lleva su argumento. (I:8 C:5 H:7 → 1.50) [dep: Q5-5]
  - Claude: preparar el análisis (notebook o script según convenga) y proponer los cambios con su evidencia; no aplicarlos sin que Mauricio los confirme.
  - Mauricico: pedir el análisis cuando haya suficientes vueltas y decidir qué sugerencias aplicar.
- [ ] **[Q5-6] (PAUSADO) Probar los tres niveles de agregación (por `valor`, por `tipo_valor`, todos agregados)**: pausado el 2026-11-02, por ahora cada valor se calibra independiente. Al retomarlo: repetir la calibración de `Q4` y la comparación de `Q5-5` en cada nivel (con premio agregado = suma de los premios de los valores del grupo) y elegir por resultado fuera de muestra con criterio de parsimonia. Diseño en `docs/plans/plan_x5_alt_v2.md` §9.8. (I:5 C:6 H:3 → 0.65) [dep: Q5-5]
  - Claude: implementar el ajuste agrupado por `tipo_valor` y global, y la tabla comparativa de los tres niveles.
  - [DECIDE MAURICIO] (al retomarlo): si el target `y*_t` del ajuste agrupado se normaliza por activo antes de juntar los datos (`plan_x5_alt_v2.md` §9.8).
  - Mauricico: decidir el nivel final por parámetro con la tabla.

**Transversales / implementación**

- [ ] **[TRANS-2] Generar `docs/plans/plan_x5_alt_v2.pdf`** en LaTeX (~10-12 páginas), mismo patrón que `x5_alt_v2.tex`/`.pdf` existente para `Q1`/`Q2`/`Q3` — documentando la Fase 2 (funciones dinámicas) con `Q4` ya calibrado (cerrado el 2026-11-02; las funciones finales ya están en `docs/context/funciones_pars_dinamicos.pdf`, reutilizar). Ojo con el nombre: ya existe `docs/plans/x5_alt_v2.pdf` (documenta `Q1`/`Q2`/`Q3`, sin prefijo `plan_`) — evaluar si conviene renombrar uno de los dos para no confundirlos. (I:3 C:4 H:2 → 0.61) [dep: —]
  - Claude: generar el documento LaTeX/PDF (~10-12 páginas) con los resultados reales de la Fase 2.
  - Mauricico: decidir si renombrar `x5_alt_v2.pdf` existente para evitar confusión entre ambos documentos.

### Backlog

- [ ] Evaluar compatibilidad de librería MT5 en macOS — si se resuelve, simplifica mucho el flujo Mac↔Windows. (I:6 C:3 H:5 → 1.83)
  - Claude: investigar si existe soporte oficial o no oficial de `MetaTrader5` para macOS.
  - Mauricico: decidir si vale la pena migrar el flujo si se confirma compatibilidad.
- [ ] Revisar con Mauricio la lógica de scoring de `calcular_FO` — ya se agregaron `v` y `f` (lo de mayor impacto); queda pendiente discutir ajustes menores (ej. `h_dist` por volatilidad, conteo de retests) (I:2 C:3 H:2 → 0.67)
  - Claude: preparar el análisis de los ajustes menores propuestos (`h_dist` por volatilidad, conteo de retests).
  - Mauricico: discutir y decidir cuáles implementar.

### Definir si hacer

Ítems válidos técnicamente pero cuyo valor real no está claro. Antes de implementarlos hay que decidir si efectivamente tienen sentido.

- [ ] Separar descarga de datos en módulo independiente (hoy está en X0) (I:4 C:5 H:4 → 0.80)
  - Mauricico: decidir si vale la pena separar este módulo antes de implementarlo.
- [ ] **S7 — Criterio de parada por tasa de mejora**: agregar criterio adicional en `nuevo_optimizador_2` — si el promedio de las últimas `VENTANA_MEJORAS=10` mejoras aceptadas < `EPSILON_TASA=1e-6`, declarar convergencia aunque queden soportes sin evaluar. Complementa (no reemplaza) el criterio binario actual. Impacto principalmente cuando `delta_inicial` es muy pequeño. (I:1 C:2 H:1 → 0.50)
  - Mauricico: decidir si implementar este criterio adicional en `nuevo_optimizador_2`.

---
