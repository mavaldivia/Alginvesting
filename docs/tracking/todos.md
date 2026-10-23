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
> **Fase 2 — funciones dinámicas (`Q4`/`Q5`)**: con `Q1`/`Q2`/`Q3` cerrados (2026-10-12), el plan completo de esta fase (forma funcional, mecanismo de calibración, combinaciones parámetro↔variable, alcance de cada notebook) vive en [`docs/plans/plan_x5_alt_v2.md`](../plans/plan_x5_alt_v2.md) — no duplicar acá, solo los ítems. Módulo compartido `scripts/x5_alt_funciones.py` ya implementado y probado (matemática pura, no requiere `Data`/MT5).

**Q1 — X5_Q1.ipynb (tabla maestra + variables de estado del activo)**

**Q2 — X5_Q2.ipynb (core descriptivo: correlación clásica + coseno + regímenes + estabilidad + export)**

**Q3 — X5_Q3.ipynb (hipótesis parámetro↔variable + tabla final)**

**Q4 — X5_Q4.ipynb (calibración de diseño: sigmoide acotada por parámetro, `plan_x5_alt_v2.md`)**

> **Lista estrictamente secuencial** (a pedido explícito de Mauricio, 2026-10-15): cada parámetro se trabaja en 3 pasos consecutivos — *implementar* (código) → *ejecutar* (correr `X5_Q4.ipynb` de punta a punta en Windows con datos reales) → *revisar visuales y validar* (gate humano: Mauricio mira los gráficos/diagnóstico de esa sección y confirma si la hipótesis se sostiene, antes de pasar al siguiente parámetro). No saltar pasos ni adelantar el parámetro siguiente sin cerrar los 3 del anterior.

- [ ] **[Q4-5] Ejecutar X5_Q4.ipynb** (con la Sección N ya agregada): correr de punta a punta en Windows, 7 activos (incluye MSFT), datos reales — confirmar sin errores. [dep: Q4-4]
  - Mauricico: ejecutar el notebook de punta a punta en Windows, 7 activos (incluye MSFT), datos reales, y confirmar que corre sin errores.
- [ ] **[Q4-6] Revisar visuales de la Sección N y validar**: Mauricio revisa la curva ajustada, la serie `N̂_t` vs. estático y el diagnóstico — confirma o ajusta la hipótesis antes de seguir a `A`. [dep: Q4-5]
  - Mauricico: revisar la curva ajustada, la serie `N̂_t` vs. estático y el diagnóstico; confirmar o ajustar la hipótesis.
  - Estado (2026-10-23): en curso. Mauricio revisó hasta 4.3 (con `drawdown_7d` ya aplicado, se ve mejor) y empieza la lectura de 4.4.
- [ ] **[Q4-7] Implementar Sección A: `A = f(x3_atr_pct)`**: mismo esqueleto que `N` con `k=1`. Nota explícita en el notebook: se calibra `A` único, sin separar `A_OE`/`A_TRAILING` (decisión pendiente, `x5_contexto_conversacion.md` §21). Rango `(2.0, 20.0)` USD. [dep: Q4-6]
  - Claude: implementar la Sección A (mismo esqueleto que N, `k=1`, con la nota sobre `A_OE`/`A_TRAILING`) en el notebook.
- [ ] **[Q4-8] Ejecutar X5_Q4.ipynb** (con la Sección A ya agregada). [dep: Q4-7]
  - Mauricico: ejecutar el notebook en Windows y confirmar que corre sin errores.
- [ ] **[Q4-9] Revisar visuales de la Sección A y validar**. [dep: Q4-8]
  - Mauricico: revisar curva, serie y diagnóstico de A; confirmar o ajustar la hipótesis.
- [ ] **[Q4-10] Implementar Sección factor_B: `factor_B = f(x3_atr_pct, adx_14)`**: mismo esqueleto con `k=2`. Rango tentativo `(0.2, 0.7)` — no está en `X5_PARAM_RANGES` todavía (`plan_x5_alt_v2.md` sección 6). [dep: Q4-9]
  - Claude: implementar la Sección factor_B (`k=2`, rango tentativo) en el notebook.
- [ ] **[Q4-11] Ejecutar X5_Q4.ipynb** (con la Sección factor_B ya agregada). [dep: Q4-10]
  - Mauricico: ejecutar el notebook en Windows y confirmar que corre sin errores.
- [ ] **[Q4-12] Revisar visuales de la Sección factor_B y validar**. [dep: Q4-11]
  - Mauricico: revisar curva, serie y diagnóstico de factor_B; confirmar o ajustar la hipótesis.
- [ ] **[Q4-13] Implementar Sección K: `K = f(ruptura_rango)`**: mismo esqueleto con `k=1`. Rango `(0.5, 2.0)`. Nota: `K` es global en producción, se calibra por activo solo para este análisis (`plan_x5_alt_v2.md` sección 6). [dep: Q4-12]
  - Claude: implementar la Sección K (`k=1`, rango `(0.5,2.0)`, con la nota sobre `K` global) en el notebook.
- [ ] **[Q4-14] Ejecutar X5_Q4.ipynb** (con la Sección K ya agregada). [dep: Q4-13]
  - Mauricico: ejecutar el notebook en Windows y confirmar que corre sin errores.
- [ ] **[Q4-15] Revisar visuales de la Sección K y validar**. [dep: Q4-14]
  - Mauricico: revisar curva, serie y diagnóstico de K; confirmar o ajustar la hipótesis.
- [ ] **[Q4-16] Implementar Sección N_EXP: `N_EXP = f(cambio_volatilidad)`**: mismo esqueleto con `k=1`. Rango `(0.5, 3.0)`. Misma nota que `K` sobre parámetros globales. [dep: Q4-15]
  - Claude: implementar la Sección N_EXP (`k=1`, rango `(0.5,3.0)`) en el notebook.
- [ ] **[Q4-17] Ejecutar X5_Q4.ipynb** (con la Sección N_EXP ya agregada). [dep: Q4-16]
  - Mauricico: ejecutar el notebook en Windows y confirmar que corre sin errores.
- [ ] **[Q4-18] Revisar visuales de la Sección N_EXP y validar**. [dep: Q4-17]
  - Mauricico: revisar curva, serie y diagnóstico de N_EXP; confirmar o ajustar la hipótesis.
- [ ] **[Q4-19] Implementar resumen consolidado** (los 5 parámetros de esta fase: `N`,`A`,`factor_B`,`K`,`N_EXP`): tabla única por activo con R², elasticidad y coincidencia de signo vs. hipótesis Q3. Export `{valor}_q4_resumen.csv`. [dep: Q4-18]
  - Claude: implementar la tabla única por activo (R², elasticidad, coincidencia de signo) y el export `{valor}_q4_resumen.csv`.
- [ ] **[Q4-20] Ejecutar X5_Q4.ipynb y revisar el resumen consolidado**: correr de punta a punta, Mauricio revisa la tabla completa (los 5 parámetros juntos) antes del cierre formal. [dep: Q4-19]
  - Mauricico: ejecutar el notebook de punta a punta en Windows y revisar la tabla consolidada de los 5 parámetros antes del cierre formal.
- [ ] **[Q4-EXEC] Cierre de la Fase 2 principal**: la celda de `exportar_zip('X5_Q4')` ya existe (Sección 10, no la 12 del scaffold original — numeración real quedó distinta al scaffold). Falta correr `X5_Q4.ipynb` una última vez de punta a punta (7 activos, incluye MSFT) y confirmar el zip generado con las secciones 4-9 completas. [dep: Q4-20]
  - Mauricico: correr `X5_Q4.ipynb` una última vez de punta a punta (7 activos, incluye MSFT) en Windows y confirmar el zip generado.

**Q4 — `LAMBDA`** (entra al alcance de la fase por decisión de Mauricio, 2026-10-18; Sección 11 del notebook)

- [ ] **[Q4-L1] Resolver el rango real de `LAMBDA`**: decidir con Mauricio si se usa `(0.001,0.02)` (rango de exploración documentado) o `0.2` (valor productivo, `config.py:95`) como referencia de `piso`/`techo` — bloqueador heredado de `Q3-6`. Sin esto resuelto, no avanzar a `Q4-L2`. [dep: Q4-EXEC]
  - Claude: presentar las dos opciones de rango (`(0.001,0.02)` exploración vs. `0.2` productivo) con sus tradeoffs.
  - Mauricico: decidir cuál usar como referencia de piso/techo.
- [ ] **[Q4-L2] Implementar Sección LAMBDA: `LAMBDA = f(x3_bb_width, duracion_en_rango)`**: mismo esqueleto con `k=2`, usando el rango decidido en `Q4-L1`. [dep: Q4-L1]
  - Claude: implementar la Sección LAMBDA (`k=2`, con el rango ya decidido) en el notebook.
- [ ] **[Q4-L3] Ejecutar X5_Q4.ipynb** (con la Sección LAMBDA ya agregada). [dep: Q4-L2]
  - Mauricico: ejecutar el notebook en Windows y confirmar que corre sin errores.
- [ ] **[Q4-L4] Revisar visuales de la Sección LAMBDA y validar**. [dep: Q4-L3]
  - Mauricico: revisar curva, serie y diagnóstico de LAMBDA; confirmar o ajustar la hipótesis.

**Q4 — `PERDIDA_MAX`** (entra al alcance por decisión de Mauricio, 2026-10-18; Sección 12 del notebook, scaffold dejado)

- [ ] **[Q4-P1] Elegir variable(s) explicativa(s) de `PERDIDA_MAX` con evidencia**: `PERDIDA_MAX` no tiene hipótesis ni variable en `Q3`. Revisar la evidencia de `Q2` (`exp_Q2`) y proponer variable(s), signo esperado y argumento — nunca a priori. Confirmar rango de referencia `(100,300)` USD vs. valor productivo `200` (`config.py:385`; falta `MSFT`). [dep: Q4-EXEC]
  - Claude: analizar la evidencia disponible y presentar 2 candidatas con tradeoffs y recomendación.
  - Mauricico: elegir variable(s) e hipótesis de signo.
- [ ] **[Q4-P2] Implementar Sección PERDIDA_MAX**: mismo esqueleto con `k` según lo decidido en `Q4-P1`. [dep: Q4-P1]
  - Claude: implementar la Sección 12 en el notebook.
- [ ] **[Q4-P3] Ejecutar X5_Q4.ipynb** (con la Sección PERDIDA_MAX ya agregada). [dep: Q4-P2]
  - Mauricico: ejecutar el notebook y confirmar que corre sin errores.
- [ ] **[Q4-P4] Revisar visuales de la Sección PERDIDA_MAX y validar**. [dep: Q4-P3]
  - Mauricico: revisar curva, serie y diagnóstico; confirmar o ajustar la hipótesis.

**Q5 — X5_Q5.ipynb (validación económica: puente a X4_backtester.py, `plan_x5_alt_v2.md` sección 9)**

- [ ] **[Q5-1] X5_Q5 — diseñar el backtesting condicional por régimen**: decisión pendiente explícita de `x5_contexto_conversacion.md` §21 ("Definir cómo se realizará el backtesting condicional por régimen") — paso previo obligatorio, no una sección más del notebook. Sin esto resuelto no se desglosan más ítems de `Q5`. [dep: Q4-EXEC]
  - Claude: proponer el diseño del backtesting condicional por régimen (opciones y tradeoffs).
  - Mauricico: decidir el enfoque a implementar.
- [ ] **[Q5-2] X5_Q5 — comparar resultado económico de cada parámetro dinámico (Q4) vs. estático actual**: walk-forward / fuera de muestra por activo (Principio 10, `x5_contexto_conversacion.md`), usando `X4_backtester.py` sin reimplementar su lógica (Principio "X4/X5 dependen de X0/X1" de `CLAUDE.md`). [dep: Q5-1]
  - Claude: implementar la comparación walk-forward / fuera de muestra por activo en el notebook, usando `X4_backtester.py` sin reimplementar su lógica.
  - Mauricico: ejecutar en Windows con datos reales y revisar los resultados económicos por activo.
- [ ] **[Q5-3] X5_Q5 — probar los tres niveles de agregación (por `valor`, por `tipo_valor`, todos agregados)**: repetir la calibración de `Q4` y la comparación de `Q5-2` en cada nivel y elegir por resultado fuera de muestra con criterio de parsimonia. Diseño en `docs/plans/plan_x5_alt_v2.md` §9.1. [dep: Q5-2]
  - Claude: implementar el ajuste agrupado por `tipo_valor` y global, y la tabla comparativa de los tres niveles.
  - Mauricico: decidir el nivel final por parámetro con la tabla.

**Transversales / implementación**

- [ ] **[TRANS-2] Generar `docs/plans/plan_x5_alt_v2.pdf`** en LaTeX (~10-12 páginas), mismo patrón que `x5_alt_v2.tex`/`.pdf` existente para `Q1`/`Q2`/`Q3` — documentando la Fase 2 (funciones dinámicas) una vez `Q4` esté calibrado, para que refleje resultados reales y no solo el diseño. Ojo con el nombre: ya existe `docs/plans/x5_alt_v2.pdf` (documenta `Q1`/`Q2`/`Q3`, sin prefijo `plan_`) — evaluar si conviene renombrar uno de los dos para no confundirlos. [dep: Q4-EXEC]
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
