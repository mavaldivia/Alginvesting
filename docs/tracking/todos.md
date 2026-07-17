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

> **Pipeline de generación de datos**: `X5 --recolectar` lanza `X4 --x5` en modo backtesting multi-ciclo.
> X4 simula trades vela a vela capturando X3+X2 en OE/OA/OC y escribe a `resources/x5/{ACTIVO}_store.csv`.
> Al cruzar `X5_MIN_TRADES_TRAIN`, X5 entrena automáticamente el modelo LGBM.
> Items 1→2→5→4→3 son la secuencia de implementación; el orden de arriba es por score.

- [ ] **1. Ampliar `config_V1.py` a los 6 activos**: agregar `TSLA`, `GOOGL`, `NVDA`, `AMZN` a `resources/x4/versionV1/config_V1.py` con sus `LOTAJES`, `UNITS`, `APALANCAMIENTO` y `n_sizes` (tomar valores de `config.py`). Agregar parámetros de recolección: `EXPLORATION_RATE = 0.30` (fracción de ciclos con params aleatorios) y `N_CICLOS_BT = 10` (ciclos del loop explore/exploit). Sin este paso, X4 --x5 solo genera datos de 2 activos. (I:8 C:1 H:9 → 8.49)

- [ ] **2. X3: exponer `compute_snapshot(df_ohlcv, soportes)`**: nueva función pública en `X3_technical_features.py` que recibe un slice OHLCV (todas las velas hasta el timestamp actual) y una lista de soportes, y retorna `dict[str, float]` con los valores de features de la última fila, sin escribir a disco. Internamente llama a `_calcular_todos_indicadores` y extrae la última fila como dict. X4 la llama en OE y en OA para capturar el estado del mercado en cada momento. (I:8 C:2 H:10 → 4.47)

- [ ] **3. X5: `--recolectar` — orquestador del pipeline**: nuevo modo CLI en `X5_macro_brain.py`. Lanza `X4_backtester.py --version V1 --x5` como subprocess. Monitorea `resources/x5/{ACTIVO}_store.csv` (n OC por activo) e imprime progreso al terminar cada ciclo. Al cruzar `X5_MIN_TRADES_TRAIN` por primer activo entrenado, llama `--train` automáticamente y sigue recolectando. Termina al agotar `N_CICLOS_BT` o si todos los activos superaron `X5_MIN_TRADES_TRAIN`. CLI: `python X5_macro_brain.py --recolectar [--version V1]`. (I:8 C:3 H:6 → 2.67)

- [ ] **4. X4: multi-ciclo explore/exploit en modo `--x5`**: al terminar el historial en modo `--x5`, reiniciar el loop desde `cfg.fecha_inicio` con nuevos params. En cada ciclo: sortear si es exploración (`random() < cfg.EXPLORATION_RATE`) → params aleatorios uniformes dentro de `X5_PARAM_RANGES`; o explotación → llamar `X5_macro_brain.py --infer` para obtener los mejores params actuales (fallback a `config_V1` si modelo no entrenado). Imprimir al inicio de cada ciclo qué params se usan y si es explore/exploit. Checkpoint se resetea entre ciclos (nueva simulación desde cero cada vez). (I:8 C:4 H:7 → 1.87)

- [ ] **5. X4: modo `--x5` — captura X3/X2 y escritura al store**: agregar flag `--x5` a X4. Cambios internos: (a) propagar `ts_oe_creacion` desde el dict OE al dict OA cuando se ejecuta la orden (hoy solo va al evento); (b) en paso F al crear OE: llamar `compute_snapshot(df_hasta_ts, soportes)` y guardar `x3_oe` + leer X2 de `x2_history.json` para ese día (zeros si no hay entrada) y guardar `x2_oe` en el dict OE; (c) en paso B al ejecutar OA: capturar `x3_oa` y `x2_oa` en el mismo momento y guardarlos en el dict OA; (d) en pasos D/E al cerrar OC: construir fila CSV con `tipo_registro="oc"`, `timestamp_oe/oa/oc`, params activos (`n_ejecucion`, `K`, `N_EXP`, `LAMBDA`, `A`, `B`, `LOTAJES_M`, `PERDIDA_MAX`), features X3/X2 en OE y OA (con sufijo `_oa`), features temporales para ts_oe (misma lógica que `_features_temporales_ahora` en X5 pero para un ts dado), contexto portfolio (`n_ordenes_abiertas`, `n_ordenes_espera`, `exposicion_usd`, `mean_retorno_pct_abierto`, `std_retorno_pct_abierto`, `retorno_promedio_ultimas_5_oc`), y `retorno_pct` como target. Hacer append al CSV en `resources/x5/{ACTIVO}_store.csv`. (e) cada `X5_FREQ_REGISTRO_PERIODICO` velas con al menos 1 OA activa: escribir fila `tipo_registro="periodico"` con el estado actual del portfolio y X3/X2 del momento. (I:9 C:5 H:9 → 1.80)


### Backlog

- [ ] Evaluar compatibilidad de librería MT5 en macOS — si se resuelve, simplifica mucho el flujo Mac↔Windows. (I:6 C:3 H:5 → 1.83)
- [ ] Revisar con Mauricio la lógica de scoring de `calcular_FO` — ya se agregaron `v` y `f` (lo de mayor impacto); queda pendiente discutir ajustes menores (ej. `h_dist` por volatilidad, conteo de retests) (I:2 C:3 H:2 → 0.67)

### Definir si hacer

Ítems válidos técnicamente pero cuyo valor real no está claro. Antes de implementarlos hay que decidir si efectivamente tienen sentido.

- [ ] Separar descarga de datos en módulo independiente (hoy está en X0) (I:4 C:5 H:4 → 0.80)
- [ ] **S7 — Criterio de parada por tasa de mejora**: agregar criterio adicional en `nuevo_optimizador_2` — si el promedio de las últimas `VENTANA_MEJORAS=10` mejoras aceptadas < `EPSILON_TASA=1e-6`, declarar convergencia aunque queden soportes sin evaluar. Complementa (no reemplaza) el criterio binario actual. Impacto principalmente cuando `delta_inicial` es muy pequeño. (I:1 C:2 H:1 → 0.50)

---
