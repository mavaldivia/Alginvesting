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
> - **Cuenta por valor**: 3000 USD de capital inicial; `Z = cerrado + P&L abierto`; `lotajes_m = max(1, (Z − 6000) // 3000 + 2)`; `perdida_max_USD = p · 3000 · m` por orden abierta, por tramos de `lotajes_m` (ej. `p = 0.04`: `m = 1` → 120 USD; `Z = 6000`, `m = 2` → 240 USD), con un tope de Órdenes Abiertas (OA) `floor(0,5 · Z / umbral)` (`R_TOPE_OA`; `Q5-3b`, 2026-11-18).
> - **Aprendizaje**: premio del tramo de aprendizaje `Z_tongo = Z al corte / velas hasta el corte` (el tramo reservado no entra); Sobol en las primeras vueltas, luego Regresión Lineal Múltiple (RLM) `Z_tongo = f(C2)` con `GRADO` de `config_smart.py` (1 por defecto, 2 suma productos cruzados) y Gradient Ascent para mover levemente cada C2.
> - **Compuerta**: el último tramo de la historia (20% por defecto) no se usa para aprender; un candidato se promueve solo si supera al estático y a `Q4` en ese tramo, y se confirma con velas nuevas y aprobación manual antes de producción.
> - **Stop-out**: la vuelta no se corta; sigue "como si el valor de la cuenta fuera negativo" y el evento se registra como KPI.
> - **Registro y monitoreo** (`plan_x5_alt_v2.md` §9.10): toda vuelta registra siempre sus datos (`{valor}_vueltas.csv`, `{valor}_seguimiento.csv`, `{valor}_aprendizaje.csv` más los archivos de X4) y cada `n_velas`, después de la búsqueda de soportes, imprime un resumen con status, cerrado, P&L abierto, `Z`, `lotajes_m`, trades, drawdown, C1 vigentes y FO de la búsqueda.
> - **Ejecución** (§9.11): los 7 valores (incluido MSFT) corren en paralelo, un proceso por valor, independientes entre sí.
> - **Pausado**: la prueba de tres niveles de agregación (`Q5-6`); por ahora cada valor independiente.
> **Decisiones de Mauricio (convención de este bloque)**: todo lo que Mauricio debe aclarar está marcado `[DECIDE MAURICIO]` dentro del ítem donde se necesita, con valor por defecto cuando existe. Como los ítems se ejecutan en orden, al empezar cada uno Claude lista sus `[DECIDE MAURICIO]` y espera la respuesta antes de implementar; los marcados `(después de ver resultados)` se deciden con datos de una corrida del mismo ítem o de uno anterior. Si Mauricio responde "defaults", se usan los valores sugeridos. Resumen (`Q5-1`, `Q5-2` y las de `Q5-3` ya resueltos, ver `decisiones.md` 2026-11-14): `Q5-4` y `Q5-5` (candidato, umbral de promoción, paso del gradiente, grado y `ret_medio`/`ret_vol`) resueltos el 2026-11-19, ver `decisiones.md`; `Q5-5b` cómo llegan los C1 a X0/X1 (publicador o en línea), reglas de cuenta en X1, `K`/`N_EXP`/`LAMBDA` por valor y velas nuevas exigidas (opciones y recomendación ya escritas en el ítem); `Q5-5c` largo de la ventana y las decisiones "después de ver resultados"; `Q5-6` normalización del target agrupado.
> **Construye sobre**: `X4_backtester.py` (modo `--x5` y `--activo`, `_aplicar_params_x5`, checkpoint y equity aislados por activo, `_calcular_estado_cuenta`/`_append_equity`); el backtesting inteligente es un script nuevo (`X4S_backtesting_inteligente.py`, nombre provisional) que importa de `X4_backtester.py`, sin modo `--smart` ni `X4B` (decidido 2026-11-03); de `Q4` toma `{valor}_q4_resumen.csv` (coeficientes de partida, `μ`/`σ`), `x5_alt_funciones.py` (matemática de `P̂_t`) y `config_smart.py`. Nunca reimplementa X0/X1.
> **Riesgos abiertos** (detalle en `plan_x5_alt_v2.md` §9.9): (1) una observación por valor y vuelta contra 26 dimensiones: `Q5-1` mide cuánto dura una vuelta; (2) X4 usa un solo `cfg.LOTAJES[activo]` por activo y `lotajes_m(Z)` exige un lote por posición; (3) el caché de soportes está indexado por `N` y con `N` dinámico rompe el warm start; (4) `μ`/`σ` de `Q4` usan todo el histórico (look-ahead); (5) `N_VELAS` de acciones (35) y los pasos son valores por defecto sin verificar.

- [ ] **[Q5-5a] Variables de estado de Q1 como módulo importable (`scripts/x5_alt_variables.py`)** *(surgido el 2026-11-19 al preparar `Q5-5b`)*: hoy las 8 funciones que arman la tabla de estado (`_cargar_tabla_base`, `_filtrar_y_transformar_tecnicos` y las seis `_variables_*`: drawdown, volatilidad, liquidez, fundamentales, ruido y tendencia/régimen) viven solo dentro de `X5_Q1.ipynb` (celdas 5 a 19) y el backtest lee su resultado ya calculado (`exp_Q1/{valor}_tabla_estado_v2.csv`). Eso cuesta dos cosas: (1) producción no puede calcular los C1 de la candidata, porque `serie_c1` necesita esa tabla al día; (2) los backtests no pueden usar datos más nuevos que la última corrida del notebook (`_insumos_vigentes` recorta H1 y M1 a la última fecha de la tabla, así que `T` no crece con datos nuevos). Se extraen a un módulo que `X5_Q1.ipynb` importa, sin duplicar (el catálogo de documentación `METADATA_VARIABLES` queda en el notebook). Prueba de aceptación: el módulo reproduce las tablas de `exp_Q1` de los 7 valores (mismas columnas, `np.allclose`) y es causal: el valor en `t` no cambia si se recortan las velas posteriores; sin esto la candidata filtraría futuro en vivo. (I:7 C:5 H:9 → 1.59) [dep: —]
  - Claude: extraer las funciones, hacer que `X5_Q1.ipynb` las importe y escribir `test_x5_alt_variables.py` (sin MT5). Se puede hacer mientras corren BTCUSD y TSLA: es cómputo liviano, no compite por CPU.
  - Mauricio (labor): la prueba necesita `resources/x3/{valor}.csv` y `resources/x2/` de los 7 valores; hoy en el Mac solo está `resources/x3/ETHUSD.csv` (de junio) y el historial de X2 cubre 2026-06-12 a 2026-09-21. Copiarlos desde Windows, o correr la prueba allá.
- [ ] **[Q5-5b] Traspaso de la configuración candidata a X0/X1 con compuerta manual**: llevar a producción la candidata que pase la compuerta de `Q5-5c` sin que X0/X1 dupliquen la lógica de Q5: archivo de candidata aparte, confirmación con velas nuevas posteriores a la elección, aprobación de Mauricio y lectura vía `TIPO_EJECUCION="din"`; pasa a automático con reglas de seguridad más adelante. **Estado verificado el 2026-11-19** (no suponer lo contrario): (1) `TIPO_EJECUCION = "din"` está documentado en `config.py`, pero X0, X1 y X4 no leen `config/active_parameters.json` (ese archivo es del X5 original): el mecanismo hay que construirlo; (2) X1 usa `A[valor]`, `B[valor]`, `PERDIDA_MAX[valor]` y `LOTAJES` estáticos y ya escala `a`, `b` y `perdida_max` por `orden.volume / MIN_LOTAJES[valor]` (`X1_trading.py:1003` y `:1067`), igual que el `perdida_max = p · 3000 · m` de Q5 con `PERDIDA_MAX[valor] = p · 3000`; en producción no existen `lotajes_m(Z)` (el lote sale del `LOTAJES_M` fijo) ni el tope de Órdenes Abiertas (OA); (3) X0 acepta `params_soporte = {K, N_EXP, LAMBDA}` (X4 lo usa) pero la producción pasa `None`; `N` sale de `n_sizes_ejecucion[valor]` y los archivos son `{VALOR}_{N}.json`, así que con `N` dinámico cambian el nombre y el warm start (riesgo 3 de `plan_x5_alt_v2.md` §9.9); (4) los C1 salen de `serie_c1`, que necesita la tabla de estado de Q1 al día: eso lo resuelve `Q5-5a`. (I:9 C:7 H:5 → 0.96) [dep: Q5-5a]
  - Claude: implementar la escritura de la candidata y la lectura en X0/X1 sin duplicar su lógica (con la opción elegida abajo), el manejo de `N` dinámico (archivo y warm start) y el respaldo a `config.py` si el JSON falta o está viejo.
  - [DECIDE MAURICIO] (antes de implementar) (1) cómo llegan los C1 a X0/X1. **Opción A (recomendada), publicador**: un script en Windows calcula cada hora, con la tabla de `Q5-5a`, los C1 de la candidata en la última vela (`serie_c1`) y escribe `config/active_parameters.json` por valor (`N`, `K`, `N_EXP`, `LAMBDA`, `A`, `factor_B`, `p`); X0 y X1 solo lo leen. X1 no importa matemática de Q5, pero hay un proceso más que mantener. **Opción B, en línea**: X0/X1 importan `serie_c1` y calculan los C1 ellos mismos; sin archivo intermedio, pero el lazo de trading de X1 pasa a depender de la tabla de estado y de X3/X2.
  - [DECIDE MAURICIO] (antes de implementar) (2) reglas de cuenta de Q5 en X1. **Opción 1, solo C1**: X1 sigue con lote fijo y sin tope de OA (más simple, pero la candidata se validó con el tope `floor(0,5 · Z / umbral)` y en vivo correría sin él: más OA abiertas a la vez). **Opción 2 (recomendada), C1 + tope de OA**: X1 aplica el tope con la `Z` real de la cuenta y mantiene el lote fijo; `lotajes_m(Z)` dinámico queda fuera porque las ventanas se validaron con `m = 1`.
  - [DECIDE MAURICIO] (antes de implementar) (3) `K`, `N_EXP` y `LAMBDA` son globales en X0 y Q5 los calibra por valor: con la opción A pasan a armarse por valor desde el JSON (X0 ya acepta `params_soporte`; no cambia el algoritmo, solo qué se le pasa), recomendado; (4) cuántas velas nuevas, o semanas de datos nuevos, se exigen antes de aprobar una candidata (sugerencia sin evidencia: 4 semanas, 672 velas en crypto).
  - Mauricio (labor): aprobar cada candidata mientras la compuerta sea manual.
- [ ] **[Q5-5c] Ejecución del aprendizaje y evaluación del candidato (BTCUSD; TSLA en paralelo)** *(desdoblado de `Q5-3c` y `Q5-5` el 2026-11-19: su construcción está en `done.md`; esto es lo que queda por correr y decidir)*: llegar a 32 ventanas Sobol válidas en BTCUSD (14 al 2026-11-19), pasar a la fase `rlm`, evaluar el candidato con `--evaluar_candidato` y cerrar las decisiones abiertas con esos datos. TSLA corre en paralelo para comprobar que el esquema funciona con una acción (50 velas H1 por ventana; 5 ventanas al 2026-11-19). (I:9 C:3 H:9 → 3.00) [dep: Q5-5]
  - Mauricio (labor): dejar corriendo `caffeinate -i python scripts/X4_bckt_ventanas.py --activo BTCUSD` y lo mismo con `--activo TSLA` (el Mac se suspendió buena parte del 2026-11-19: 4 ventanas entre las 13:48 y las 16:29). Al pasar de 32 ventanas Sobol válidas, detener (Ctrl+C) y relanzar el mismo comando: con el código nuevo la siguiente ventana de aprendizaje sale `rlm`. Con dos procesos a la vez `Y` depende de la carga del equipo (tope de 10 min de reloj).
  - Mauricio (labor): con unas ventanas `rlm`, revisar `{valor}_aprendizaje.csv` (R² fuera de pliegue) y correr `python scripts/X4_bckt_ventanas.py --activo BTCUSD --evaluar_candidato` (misma `--semilla` de los controles; ~10 min por `t*` reservado, ~1 h con 6). Con el resultado decidir si la candidata pasa a `Q5-5b`.
  - Claude: preparar el experimento del largo de ventana: `--ventana_dias` por corrida (hoy `VENTANA_DIAS` es global en `config_smart.py`) y el largo en el id de la ventana, para correr la estática y `Q4` a 3 semanas en unos 4 `t*` reservados y compararlas con la semana. Ejecutarlo cuando termine la fase Sobol, para no competir por CPU.
  - [DECIDE MAURICIO] (después de ver resultados): largo de la ventana. Con 28 ventanas de BTCUSD (2026-11-19): todos los trades cerrados ganan (las pérdidas solo aparecen como P&L abierto), la fracción de posiciones abiertas al cierre promedia 0,23 y 3 ventanas no tuvieron trades; la estática (`A = 3`, el piso de `A`) hace 152 trades por ventana contra 25 de `Q4` y 11 de Sobol, lo que apunta a que la semana premia la rotación. Con el experimento de arriba, decidir si alargar a 2–4 semanas.
  - [DECIDE MAURICIO] (después de ver resultados): (1) ventanas sin Órdenes en Espera bajo el precio en `t*` (3 de 24, con el precio en mínimos históricos): `Y = 0` no informa sobre los C2, ¿excluirlas de la RLM?; (2) colas pesadas de `Y` (unas pocas semanas dominan la RLM): ¿winsorizar o normalizar `Y` por `ret_vol`?; (3) criterio de "no hay señal": si el R² fuera de pliegue sigue ≈ 0 tras las 32 ventanas, ¿seguir hasta N ventanas, reducir dimensiones con `Q5-7` o detener?; (4) ajustar el paso del gradiente, probar `GRADO = 2` (con `GRADO = 1` el ascenso termina en una esquina del rango de sorteo) y dejar una fracción de Sobol durante la fase `rlm`.
- [ ] **[Q5-4b] Lanzador de los 7 valores en paralelo** *(desdoblado de `Q5-4` el 2026-11-19: BTCUSD sigue solo con `--activo BTCUSD`; este ítem es lo demás)*: un lanzador que arranca los demás valores (uno por proceso, incluido MSFT), cada uno independiente, con su propio registro y log; si uno cae, los otros siguen y solo ese se reanuda (omite las ventanas ya registradas). Antes de lanzar varios a la vez hay que medir CPU y memoria: con el tope de 10 min por búsqueda, `Y` depende de la carga de la máquina. (I:6 C:4 H:5 → 1.37) [dep: Q5-4]
  - Claude: implementar el lanzador y el log por proceso.
  - Mauricio (labor): medir CPU y memoria con 2 y luego con los 7 procesos a la vez, y dejarlos corriendo.
- [ ] **[Q5-7] Análisis de las ventanas y sugerencias de cambio de C2**: cuando haya ventanas acumuladas, Mauricio pide a Claude el análisis estadístico de `resources/x5_alt/q5/` y sugerencias de cambio de los C2 (rangos de sorteo, `span`, `punto_medio`, `pendiente`, pesos y variables, ver `plan_x5_alt_v2.md` §9.12 y §9.13). El análisis cubre: efecto de cada C2 sobre el premio con error estándar y error leave-one-out de la Regresión Lineal Múltiple (RLM), ruido de `Y` con las ventanas de réplica, saturación de cada C1 en `piso`/`techo`, tendencia de `w̃` por variable, `Y` de las ventanas de aprendizaje contra las reservadas, consistencia entre los 7 valores. Si hay menos ventanas que coeficientes, se limita a lo descriptivo. Cada sugerencia de variable lleva su argumento. (I:8 C:5 H:7 → 1.50) [dep: Q5-5c]
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
