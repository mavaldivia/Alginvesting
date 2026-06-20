## TO DO

**Convención de priorización**: cada ítem pendiente lleva `(I:x C:y H:z → score)` — Impacto, Complejidad de desarrollo, Habilitación, escala 1–10. `score = √(I × H) / C`. Dentro de cada sección los ítems se ordenan de mayor a menor score.

### X1 — Robustez y estabilidad

### X0 — Validación post-revert (secuencial, alta prioridad)

> Contexto: se revirtió el optimizador a la lógica base de 8eefe88 para recuperar confianza en los resultados.
> Solo quedan speedups seguros: `calcular_FO_batch` (S6, vectorización numpy del loop M) y fase coarse/fine con `M_COARSE`.
> Ejecutar estos pasos en orden antes de seguir desarrollando X0.

- [ ] **1. Validar equidistancia con LAMBDA alto**: correr X0 con `LAMBDA = 5`, 1 activo (ej. BTCUSD), N pequeño (ej. 10-20), `verbose=True`. Los soportes finales deben ser aproximadamente equidistantes en el rango de precios. Si no → hay un bug en `calcular_FO` o `calcular_FO_batch`. (I:8 C:2 H:10 → 4.47)
- [ ] **3. Validar convergencia con LAMBDA normal**: con parámetros de producción (`LAMBDA = 1/500`, N real), verificar que FO crece monótonamente en cada cambio aceptado y que el optimizador converge (no cicla ni se queda sin mejoras prematuramente). (I:8 C:2 H:8 → 4.00)
- [ ] **Reporte final inconsistente — "no convergió" con iter=conv. arriba**: al terminar un ciclo, algunos combos del resumen muestran "no convergió" aunque en los logs individuales todos indiquen `iter=conv.`. Investigar si el flag `convergio` se propaga correctamente desde `nuevo_optimizador_2` hasta el resumen final de `buscar_soportes`. (I:4 C:2 H:6 → 2.45)

### X4 — X4_backtester.py

> Plan de implementación: [`docs/plans/x4_plan.md`](../plans/x4_plan.md)

- [ ] **X4B_crear_version_backtesting.py**: script con un único input `nombre_version` que crea la infraestructura completa de una versión (subdirectorios + `config_V.py`). Si la versión ya existe, pregunta si reiniciar. Al terminar, muestra la ruta del `config_V.py` para completar parámetros. (I:7 C:3 H:10 → 2.83)
- [ ] **X4.py**: implementar según `docs/plans/x4_plan.md`. Config, estructura de carpetas, lógica de trading y secuencia de fases ya documentadas. (I:9 C:8 H:9 → 1.13)

### X5 — X5_model_training.py

- [ ] **X5_model_training.py**: modelos supervisados sobre el store de trades. Predicciones: retorno esperado, probabilidad de pérdida, drawdown esperado, duración esperada. Evaluar overfitting (cross-val temporal, no aleatoria). Registrar qué modelos se probaron y por qué se eligió cada uno. (I:8 C:7 H:8 → 1.14)

### X6 — X6_macro_brain.py

- [ ] Definir schema de `config/active_parameters.json`: qué parámetros escribe X6 (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL, a, b, PERDIDA_MAX), con qué granularidad (por activo, global, o mixto). (I:5 C:2 H:7 → 2.96)
- [ ] Definir frecuencia de ejecución de X6: ¿diario? ¿antes de cada corrida de X0? ¿en el loop de X1? Requiere discusión. (I:4 C:2 H:5 → 2.24)
- [ ] **X6_macro_brain.py**: recomendación dinámica de parámetros. Lee features de X2/X3 y predicciones de X5. Output: `config/active_parameters.json` consumido por X0 y X1. Corre en Windows por ahora; idealmente compatible con Mac en el futuro. (I:9 C:8 H:5 → 0.84)

### Backlog

- [ ] Evaluar compatibilidad de librería MT5 en macOS — si se resuelve, simplifica mucho el flujo Mac↔Windows. (I:6 C:3 H:5 → 1.83)
- [ ] Revisar con Mauricio la lógica de scoring de `calcular_FO` — ya se agregaron `v` y `f` (lo de mayor impacto); queda pendiente discutir ajustes menores (ej. `h_dist` por volatilidad, conteo de retests) (I:2 C:3 H:2 → 0.67)

### Definir si hacer

Ítems válidos técnicamente pero cuyo valor real no está claro. Antes de implementarlos hay que decidir si efectivamente tienen sentido.

- [ ] Separar descarga de datos en módulo independiente (hoy está en X0) (I:4 C:5 H:4 → 0.80)
- [ ] **S7 — Criterio de parada por tasa de mejora**: agregar criterio adicional en `nuevo_optimizador_2` — si el promedio de las últimas `VENTANA_MEJORAS=10` mejoras aceptadas < `EPSILON_TASA=1e-6`, declarar convergencia aunque queden soportes sin evaluar. Complementa (no reemplaza) el criterio binario actual. Impacto principalmente cuando `delta_inicial` es muy pequeño. (I:1 C:2 H:1 → 0.50)

---
