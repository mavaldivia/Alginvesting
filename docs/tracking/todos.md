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
> Plan de implementación: [`docs/plans/x5_plan.md`](../plans/x5_plan.md)

- [ ] **[PRIORIDAD 1] Construir X5_macro_brain.py**: implementar el surrogate model completo (entrenamiento LightGBM → FT-Transformer + inferencia por gradient ascent/Optuna) y el modo `--vela` de aprendizaje continuo, con base en `docs/plans/x5_plan.md` y `docs/plans/x5_plan_redes_neuronales.md`. El backtester (`x5_macrobrain.py`) ya existe — este ítem cubre la capa de modelo. (I:10 C:9 H:10 → 1.11)
- [ ] **X5_macro_brain.py**: surrogate model (X2+X3+config_params → retorno predicho) + optimización sobre config_params en inferencia. Output: `config/active_parameters.json` consumido por X0 y X1. (I:9 C:8 H:5 → 0.84)

### Backlog

- [ ] Evaluar compatibilidad de librería MT5 en macOS — si se resuelve, simplifica mucho el flujo Mac↔Windows. (I:6 C:3 H:5 → 1.83)
- [ ] Revisar con Mauricio la lógica de scoring de `calcular_FO` — ya se agregaron `v` y `f` (lo de mayor impacto); queda pendiente discutir ajustes menores (ej. `h_dist` por volatilidad, conteo de retests) (I:2 C:3 H:2 → 0.67)

### Definir si hacer

Ítems válidos técnicamente pero cuyo valor real no está claro. Antes de implementarlos hay que decidir si efectivamente tienen sentido.

- [ ] Separar descarga de datos en módulo independiente (hoy está en X0) (I:4 C:5 H:4 → 0.80)
- [ ] **S7 — Criterio de parada por tasa de mejora**: agregar criterio adicional en `nuevo_optimizador_2` — si el promedio de las últimas `VENTANA_MEJORAS=10` mejoras aceptadas < `EPSILON_TASA=1e-6`, declarar convergencia aunque queden soportes sin evaluar. Complementa (no reemplaza) el criterio binario actual. Impacto principalmente cuando `delta_inicial` es muy pequeño. (I:1 C:2 H:1 → 0.50)

---
