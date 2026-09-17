## TO DO

**Convención de priorización**: cada ítem pendiente lleva `(I:x C:y H:z → score)` — Impacto, Complejidad de desarrollo, Habilitación, escala 1–10. `score = √(I × H) / C`. Dentro de cada sección los ítems se ordenan de mayor a menor score.

### X1 — Robustez y estabilidad

- [x] **Agrupar prints de órdenes ejecutadas/eliminadas**: en vez de un print por orden, mostrar resumen por activo: `{valor}: {h} órdenes ejecutadas (o eliminadas) desde {min_precio} hasta {max_precio}`.

### X0 — Validación post-revert (secuencial, alta prioridad)

> Contexto: se revirtió el optimizador a la lógica base de 8eefe88 para recuperar confianza en los resultados.
> Solo quedan speedups seguros: `calcular_FO_batch` (S6, vectorización numpy del loop M) y fase coarse/fine con `M_COARSE`.
> Ejecutar estos pasos en orden antes de seguir desarrollando X0.

- [ ] **1. Validar equidistancia con LAMBDA alto**: correr X0 con `LAMBDA = 5`, 1 activo (ej. BTCUSD), N pequeño (ej. 10-20), `verbose=True`. Los soportes finales deben ser aproximadamente equidistantes en el rango de precios. Si no → hay un bug en `calcular_FO` o `calcular_FO_batch`. (I:8 C:2 H:10 → 4.47)
- [ ] **3. Validar convergencia con LAMBDA normal**: con parámetros de producción (`LAMBDA = 1/500`, N real), verificar que FO crece monótonamente en cada cambio aceptado y que el optimizador converge (no cicla ni se queda sin mejoras prematuramente). (I:8 C:2 H:8 → 4.00)
- [ ] **Reporte final inconsistente — "no convergió" con iter=conv. arriba**: al terminar un ciclo, algunos combos del resumen muestran "no convergió" aunque en los logs individuales todos indiquen `iter=conv.`. Investigar si el flag `convergio` se propaga correctamente desde `nuevo_optimizador_2` hasta el resumen final de `buscar_soportes`. (I:4 C:2 H:6 → 2.45)

### X4 — X4_backtester.py

> Plan de implementación: [`docs/plans/x4_plan.md`](../plans/x4_plan.md)

- [ ] **X4.py**: implementar según `docs/plans/x4_plan.md`. Config, estructura de carpetas, lógica de trading y secuencia de fases ya documentadas. (I:9 C:8 H:9 → 1.13)

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
- [ ] Tras recolectar un lote nuevo, correr `--status` y confirmar que el conteo de OC coincide 1:1 con las filas realmente válidas (`retorno_usd` no vacío) — 0% de corrupción, a diferencia del 79.6% que tenía el store viejo. (I:6 C:1 H:7 → 6.48)
- [ ] Revisar 5-10 filas nuevas del store (con pandas/csv, no Excel) y confirmar rangos sanos: `hora`/`hora_oa` en [0,23], `x2_score`/`x2_score_oa` en [0,1], `retorno_usd` en escala de dólares razonable (no ~1e-5 como el `retorno_pct` viejo). (I:5 C:1 H:6 → 5.48)
- [ ] No abrir ni guardar `{ACTIVO}_store.csv` desde Excel mientras el backtester lo está escribiendo — riesgo de reintroducir corrupción de BOM/separador decimal (ver commits `fix(x4,x5)` recientes). (I:4 C:1 H:3 → 3.46)
- [ ] Si más adelante se activan los otros 5 activos, correr el mismo chequeo de corrupción (0% esperado) antes de asumir que sus stores están limpios — el bug era del código compartido, pero conviene confirmar con datos reales de cada uno. (I:5 C:2 H:5 → 2.50)
- [ ] **Actualizar docs de X5**: revisar `X5_macro_brain.py` (`Otros/scripts/`) en su estado actual y actualizar `Otros/docs/plans/x5_plan.md` y `Otros/docs/plans/x5_plan_redes_neuronales.md` para que reflejen la implementación real (funciones existentes, estructura del store, CLI disponible, métricas calculadas). (I:3 C:3 H:3 → 1.00)
- [ ] **Head `flotante` con filas periódicas en FT-Transformer**: en LightGBM el target `pnl_flotante_activo` ya entrena con filas `('oc','periodico')`, pero en FTT los 3 heads comparten el mismo tensor `X` (solo filas `oc`), así que las periódicas no llegan al head flotante. Incorporarlas vía pase separado o Deep Sets en V2 (aplica cuando el store supere `X5_MIN_TRADES_FTT`). Ver `Otros/docs/plans/x5_opus_review.md` y TO DOs de `x5_plan.md`. (I:3 C:6 H:2 → 0.41)

### X5_alt — versión alternativa y simplificada de X5

> Versión paralela a X5 (no la reemplaza). Contexto completo: [`docs/plans/X5_alternativo.md`](../plans/X5_alternativo.md)
> `X5_P1` y `X5_P2` reciben `{valor}` (el activo) como input — inicialmente `BTCUSD`.
> Especificación completa de `X5_P2.ipynb` (notebook exhaustivo de investigación, no un script de carga): [`docs/plans/solicitud_claude_code_X5_P2_notebook_v2.md`](../plans/solicitud_claude_code_X5_P2_notebook_v2.md).
> El orden de abajo es por score, no de implementación: Fase 1 (X5_P1) debe completarse antes que Fase 2 (X5_P2.ipynb). Dentro de Fase 2, respetar el orden narrativo de la sección 15 de ese documento: tabla maestra válida → auditoría inicial suficiente → core variable vs. precio → profundización de relaciones → cerrar lo descriptivo antes de dar protagonismo a lo prospectivo → hipótesis para P3 solo al final.

**Core descriptivo/histórico**

- [ ] **X5_P2 — ceteris paribus histórico**: estandarizar variables y estimar el efecto/asociación de cada una controlando por las demás, revisando multicolinealidad, signo, magnitud, estabilidad y sensibilidad. Revisar y reutilizar cuando corresponda el enfoque manual con numpy/scipy ya usado en `X5_analisis_exploratorio.ipynb`, sin asumir que debe copiarse literalmente. (I:9 C:3 H:8 → 2.83)
- [ ] **X5_P2 — auditoría e inventario inicial de la tabla maestra**: cargar la salida de X5_P1, validar `DateTime`, orden, duplicados, rango, tipos y construir el inventario de variables con familia Precio/Técnico/Fundamental/Otra, cobertura, missingness y frecuencia observada. Mantener esta sección concisa y orientada a habilitar rápido el core variable-precio. (I:8 C:2 H:8 → 4.00)
- [ ] **X5_P2 — frecuencia efectiva de actualización**: medir cada cuánto cambia realmente cada variable, diferenciando frecuencia de filas de llegada efectiva de nueva información; prestar especial atención a fundamentales y forward-fill. (I:8 C:2 H:8 → 4.00)
- [ ] **X5_P2 — no linealidades y umbrales**: ampliar el análisis variable-precio mediante cuantiles, bins, suavizados, extremos, posibles umbrales, saturaciones, formas U/U invertida y asimetrías, evitando asumir que Pearson/regresión lineal capturan toda la relación. (I:8 C:3 H:7 → 2.49)
- [ ] **X5_P2 — variable vs. comportamiento histórico reciente del precio**: relacionar cada variable con retornos pasados del precio en distintos horizontes (`t-h → t`) para caracterizar qué venía ocurriendo con BTC cuando la variable toma determinados valores. Mantener este análisis dentro de la capa descriptiva, separado de retornos futuros. (I:8 C:3 H:7 → 2.49)
- [ ] **X5_P2 — estabilidad histórica de las relaciones**: medir Pearson/Spearman y, cuando corresponda, coeficientes ceteris paribus por períodos y ventanas móviles para detectar relaciones persistentes, inestables o cambios estructurales. (I:8 C:3 H:7 → 2.49)
- [ ] **X5_P2 — análisis por regímenes**: comparar las relaciones variable-precio bajo contextos como bull/bear/sideways, volatilidad alta/baja, drawdown y tendencia, definiendo cada régimen explícitamente y evitando segmentaciones arbitrarias. (I:8 C:4 H:7 → 1.87)
- [ ] **X5_P2 — relaciones entre variables y redundancia**: estudiar técnicos vs. técnicos, fundamentales vs. fundamentales y técnicos vs. fundamentales; identificar pares o grupos con información muy similar mediante correlaciones y, solo si aporta interpretabilidad, clustering/PCA. (I:7 C:3 H:6 → 2.16)
- [ ] **X5_P2 — síntesis descriptiva y ranking de variables**: consolidar por variable frecuencia efectiva, Pearson, Spearman, relación con retornos históricos, no linealidad, estabilidad, régimen, redundancia y nivel de evidencia descriptiva. No convertir este ranking automáticamente en ranking predictivo. (I:8 C:3 H:6 → 2.31)
- [ ] **X5_P2 — síntesis específica de técnicos y fundamentales**: generar una lectura consolidada separada de ambos universos, considerando especialmente las diferencias de frecuencia y disponibilidad de información. (I:6 C:3 H:4 → 1.63)

**Prospectivo / potencial predictivo**

- [ ] **X5_P2 — relaciones temporales pasado/contemporáneo/futuro**: construir para variables relevantes una radiografía temporal que permita distinguir si una variable parece rezagada, contemporánea o potencialmente adelantada, separando explícitamente `X_t ↔ retorno pasado`, `X_t ↔ precio actual` y `X_t ↔ retorno futuro`. (I:8 C:3 H:7 → 2.49)
- [ ] **X5_P2 — variable actual vs. retornos futuros por horizonte**: estudiar asociación con retornos posteriores en horizontes coherentes con la granularidad disponible, dejando explícito que asociación histórica futura no equivale por sí sola a capacidad predictiva. (I:7 C:3 H:6 → 2.16)
- [ ] **X5_P2 — validación temporal preliminar sin leakage**: si se prueban modelos o relaciones prospectivas, usar particiones temporales/walk-forward simples para verificar estabilidad fuera de muestra sin convertir P2 en un proyecto de forecasting. (I:7 C:4 H:5 → 1.48)

**Hipótesis para X5 / puente hacia P3**

- [ ] **X5_P2 — traducir evidencia robusta a hipótesis para parámetros X5**: transformar los hallazgos descriptivos/prospectivos en hipótesis explícitas del tipo `θ_k = f_k(X)`, sin implementarlas todavía como reglas de trading. Ejemplos candidatos: `N=f(drawdown)` y `A=f(volatilidad)`. (I:9 C:2 H:10 → 4.74)
- [ ] **X5_P2 — tabla final variable → parámetro candidato**: cerrar P2 con una tabla que documente variable explicativa, evidencia histórica, estabilidad, régimen, potencial prospectivo, parámetro X5 candidato, relación hipotética y prioridad de prueba en P3. (I:8 C:2 H:9 → 4.24)

**Transversales / implementación**

- [ ] **X5_P2 — documentación Markdown de investigación**: cada sección y subsección relevante debe comenzar obligatoriamente con una celda Markdown que explique objetivo, pregunta, metodología, interpretación y limitaciones antes del código; agregar interpretación posterior cuando el análisis lo amerite. (I:8 C:2 H:8 → 4.00)
- [ ] **X5_P2 — revisar `X5_analisis_exploratorio.ipynb`**: revisar el notebook existente que ya hace un análisis ceteris paribus sobre el store de eventos de X5 actual y decidir qué lógica conviene reutilizar, adaptar o descartar para evitar duplicación innecesaria. (I:6 C:2 H:7 → 3.24)
- [ ] **X5_P2 — orden del notebook por relevancia analítica**: estructurar cada parte desde el mapeo más importante/general hacia análisis progresivamente más particulares, manteniendo el bloque variable-precio como núcleo temprano de la fase descriptiva. (I:9 C:2 H:8 → 4.24)
- [ ] **X5_P2 — ejecución end-to-end y validación final**: ejecutar el notebook completo desde cero, comprobar reproducibilidad, ausencia de errores, generación de tablas/gráficos y consistencia de resultados antes de considerar P2 terminado. (I:9 C:2 H:9 → 4.50)

**X5_P1 relacionado**

- [ ] **X5_P1 — reporte de calidad de datos**: mantener en P1 la responsabilidad de validar la calidad de construcción de la tabla maestra: `% missing`, huecos temporales del precio, cobertura real de fundamentales y efecto de forward-fill. P2 debe consumir y contextualizar esta información, no reemplazar la responsabilidad de P1. (I:7 C:2 H:8 → 3.74)

**Fase 3**

- [ ] **Fase 3 (`X5_alternativo.py`) — no comenzar todavía**: definir su arquitectura y reglas recién después de observar resultados concretos de X5_P1 y X5_P2. P2 debe terminar en evidencia e hipótesis, no en reglas prescriptivas implementadas. (I:3 C:2 H:3 → 1.50)

**Puente hacia estudio de parámetros de X5 (post-P2)**

- [ ] **X5 — estudio posterior de parámetros manipulables y variables explicativas**: una vez terminado el análisis exploratorio de `X5_P2.ipynb`, usar sus resultados como insumo para estudiar de qué deberían depender los parámetros configurables de X5 (`N`, `A`, `B`, pérdida máxima, `K`, y cualquier otro relevante). Escapa parcialmente del alcance operativo de P2 — es puente hacia la siguiente etapa, no responsabilidad de implementación inmediata del notebook. Para cada parámetro: documentar qué controla, en qué etapa actúa, qué variables podrían explicarlo, signo esperado, rango permitido, riesgo económico asociado y cómo se validará. Hipótesis prioritaria ya registrada sobre `N`: no debería definirse a partir de relaciones genéricas del CSV de P2, sino tener relación directa (posiblemente única) con el drawdown de la cuenta para ese activo — `N = f(drawdown_del_valor)`, con la intuición de que a peor drawdown, `N` más defensivo/bajo. Resultado esperado: tabla `Parámetro X5 | Qué controla | Variable(s) candidata(s) | Hipótesis de relación | Evidencia (P2) | Cómo validar`, con `N` ya completo y el resto (`A`, `B`, pérdida máxima, `K`) por determinar según lo que arroje P2. Validación final: backtesting global. (I:10 C:4 H:10 → 2.50)

### Backlog

- [ ] Evaluar compatibilidad de librería MT5 en macOS — si se resuelve, simplifica mucho el flujo Mac↔Windows. (I:6 C:3 H:5 → 1.83)
- [ ] Revisar con Mauricio la lógica de scoring de `calcular_FO` — ya se agregaron `v` y `f` (lo de mayor impacto); queda pendiente discutir ajustes menores (ej. `h_dist` por volatilidad, conteo de retests) (I:2 C:3 H:2 → 0.67)

### Definir si hacer

Ítems válidos técnicamente pero cuyo valor real no está claro. Antes de implementarlos hay que decidir si efectivamente tienen sentido.

- [ ] Separar descarga de datos en módulo independiente (hoy está en X0) (I:4 C:5 H:4 → 0.80)
- [ ] **S7 — Criterio de parada por tasa de mejora**: agregar criterio adicional en `nuevo_optimizador_2` — si el promedio de las últimas `VENTANA_MEJORAS=10` mejoras aceptadas < `EPSILON_TASA=1e-6`, declarar convergencia aunque queden soportes sin evaluar. Complementa (no reemplaza) el criterio binario actual. Impacto principalmente cuando `delta_inicial` es muy pequeño. (I:1 C:2 H:1 → 0.50)

---
