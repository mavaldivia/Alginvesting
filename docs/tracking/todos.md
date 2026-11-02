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

> **Diseño (decidido 2026-11-02, reemplaza al del 2026-10-23; ver `docs/context/decisiones.md`)**: para cada combinación valor × parámetro dinámico (`N`, `A`, `factor_B`, `K`, `N_EXP`, `LAMBDA`, `PERDIDA_MAX`) cada vuelta sortea los coeficientes `{w_i, span, punto_medio, pendiente}` y los mantiene **fijos desde `FECHA_INICIAL` (2022-01-01) hasta la última vela histórica**. Premio de la vuelta = valor de la cuenta de ese valor al final (cerrado + P&L abierto), dividido por el número de velas para normalizar. Tras cada vuelta se aprende del resultado, se corrigen los coeficientes y empieza una nueva; los valores corren en paralelo (un proceso por valor, `--activo`). Cada vuelta guarda además KPIs de performance para validar las funciones de `Q4`.
> **Construye sobre**: `X4_backtester.py` (modo `--x5` y `--activo`, `_aplicar_params_x5`, checkpoint y equity aislados por activo, `_calcular_estado_cuenta`/`_append_equity`) y `X4B_crear_version_backtesting.py` (versión aislada `resources/x4/version{V}/` con `config_{V}.py` congelado); de `Q4` toma `{valor}_q4_resumen.csv` (coeficientes de partida, `μ`/`σ`), `x5_alt_funciones.py` (matemática de `P̂_t`) y `config_smart.py` (pisos y techos editables en caliente). Nunca reimplementa X0/X1.
> **Riesgos abiertos**: (1) una observación por valor y vuelta, contra cientos del diseño por ventanas de 7 días: el aprendizaje depende de cuánto dure una vuelta y del paralelismo, y `Q5-1` lo mide antes de construir nada; (2) el caché de soportes de X4 está indexado por `N` (`{VALOR}_{N}_bt.json`) y con `N_t` dinámico el `N` cambia en cada recálculo, lo que rompe el warm start; (3) `μ`/`σ` de `Q4` usan todo el histórico (look-ahead): en un backtest honesto deben ser expanding o fijarse en un tramo inicial; (4) evaluar sobre la historia ya vista sobreestima, por eso se promueve solo sobre la cola nueva posterior a la elección (decisión 2026-10-23, se mantiene).

- [ ] **[Q5-1] Spike: costo de una vuelta completa e interfaz de parámetros dinámicos en X4**: correr X4 de `FECHA_INICIAL` a la última vela con los estáticos de un activo y medir cuánto dura; mapear dónde X4 lee `A`, `B`, `PERDIDA_MAX` (por barra) y `N`, `K`, `N_EXP`, `LAMBDA` (al recalcular soportes); resolver el warm start con `N` cambiante; decidir con 2 opciones y tradeoffs si corre como modo nuevo `--smart` de `X4_backtester.py` o como versión creada con `X4B` (`config_{V}.py` congelado). Con la duración medida se decide cuántas vueltas son viables por activo. [dep: —]
  - Claude: leer `ejecutar_backtest`, `_paso_*` y `_recalcular_soportes`, y presentar el mapa de inyección, el problema del caché por `N` y las 2 opciones con recomendación.
  - Mauricico: correr la vuelta de medición en Windows (un activo, estáticos) y pasar la duración; elegir entre las 2 opciones.
- [ ] **[Q5-2] Serie `P̂_t` causal por vuelta en `x5_alt_funciones.py`**: función que dados los coeficientes de una vuelta y la tabla de estado de `Q1` devuelve `P̂_t` barra a barra, importada por X4 (una sola implementación). Resolver el look-ahead de `μ`/`σ` (expanding o fijados en un tramo inicial, con 2 opciones). Rangos de sorteo de los coeficientes en `config_smart.py`. Prueba: con los coeficientes de `Q4` reproduce las columnas `*_hat` de `{valor}_q4_*.csv`. [dep: Q5-1]
  - Claude: implementar la función y la prueba de reproducción sobre `exp_Q4` (se puede validar en Mac).
  - Mauricico: elegir cómo se normalizan `μ`/`σ` en el backtest y los rangos de sorteo de `w_i`, `span`, `punto_medio` y `pendiente`.
- [ ] **[Q5-3] X4 con parámetros dinámicos, premio y KPIs por vuelta**: implementación según `Q5-1`, sin reimplementar X0/X1: `N`, `K`, `N_EXP`, `LAMBDA` se fijan en cada recálculo de soportes y `A`, `B = factor_B · A` y `PERDIDA_MAX` se leen por barra desde `P̂_t`. Registra el premio (cerrado + P&L abierto al final, dividido por el número de velas) y KPIs: valor final de la cuenta, drawdown máximo, número de trades, tasa de aciertos, tiempo en mercado, margen usado, stop-out y promedio de cada parámetro dinámico en la vuelta. Salida `resources/x5_alt/q5/{valor}_vueltas.csv`. [dep: Q5-2]
  - Claude: implementar la interfaz en X4, el premio y los KPIs, y la prueba de que con `P̂_t` constante igual al estático la vuelta reproduce el backtest actual.
  - Mauricico: ejecutar una vuelta en Windows con datos reales y revisar los KPIs.
- [ ] **[Q5-4] Orquestador de vueltas en paralelo y control estático**: un proceso por valor (`--activo`), sorteo Sobol de los coeficientes de los 7 parámetros (siempre los cuatro grupos, decisión 2026-11-02), ejecución de la vuelta y registro; la vuelta estática (configuración actual) se corre una vez por valor como referencia. Checkpoint reanudable por vuelta. [dep: Q5-3]
  - Claude: implementar el orquestador, el sorteo y el control estático.
  - Mauricico: dejar corriendo varias vueltas por activo en Windows.
- [ ] **[Q5-5] Modelo sustituto, muestreo guiado y evaluación fuera de muestra**: aprender de las vueltas y corregir los coeficientes para la siguiente: modelo sustituto coeficientes a premio, sorteo aleatorio al inicio y guiado después con un porcentaje fijo de exploración. Un candidato se promueve solo si supera al estático y a la calibración de `Q4` en la cola nueva posterior a su elección. Se reporta el drawdown máximo sin optimizarlo. [dep: Q5-4]
  - Claude: implementar el modelo sustituto, el muestreo guiado y la evaluación sobre la cola nueva.
  - Mauricico: dejar corriendo el proceso en Windows y revisar los resultados por vuelta.
- [ ] **[Q5-5b] Traspaso de la configuración candidata a X0/X1 con compuerta manual**: archivo de candidata aparte, aprobación de Mauricio, lectura vía `TIPO_EJECUCION="din"`. Pasa a automático con reglas de seguridad más adelante. [dep: Q5-5]
  - Claude: implementar la escritura de la candidata y la lectura en X0/X1 sin duplicar su lógica.
  - Mauricico: aprobar cada candidata mientras la compuerta sea manual.
- [ ] **[Q5-6] Probar los tres niveles de agregación (por `valor`, por `tipo_valor`, todos agregados)**: repetir la calibración de `Q4` y la comparación de `Q5-5` en cada nivel (con premio agregado = suma de los premios de los valores del grupo) y elegir por resultado fuera de muestra con criterio de parsimonia. Diseño en `docs/plans/plan_x5_alt_v2.md` §9.1. [dep: Q5-5]
  - Claude: implementar el ajuste agrupado por `tipo_valor` y global, y la tabla comparativa de los tres niveles.
  - Mauricico: decidir el nivel final por parámetro con la tabla.

**Transversales / implementación**

- [ ] **[TRANS-2] Generar `docs/plans/plan_x5_alt_v2.pdf`** en LaTeX (~10-12 páginas), mismo patrón que `x5_alt_v2.tex`/`.pdf` existente para `Q1`/`Q2`/`Q3` — documentando la Fase 2 (funciones dinámicas) con `Q4` ya calibrado (cerrado el 2026-11-02; las funciones finales ya están en `docs/context/funciones_pars_dinamicos.pdf`, reutilizar). Ojo con el nombre: ya existe `docs/plans/x5_alt_v2.pdf` (documenta `Q1`/`Q2`/`Q3`, sin prefijo `plan_`) — evaluar si conviene renombrar uno de los dos para no confundirlos. [dep: —]
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
