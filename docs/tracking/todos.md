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

### X5_v3 — versión nueva de X5, limpia y desde 0

> El X5 anterior (macrobrain, X5_alt y X5_alt_v2, con todos sus códigos y documentos) vive en `X5_otros/`: carpeta local, ignorada por git, que **no está en GitHub**. Sus TO DOs quedaron en `X5_otros/docs/tracking/todos_x5.md` y sus ítems cerrados en `X5_otros/docs/tracking/done_x5.md`. Nada de eso se retoma sin decidirlo en esta sección.
> Punto de partida: el cuestionamiento de X5_alt_v2 (`X5_otros/docs/plans/X5_v3.md` y `x5_v3_informe.pdf`) y lo que se rescate de `X5_otros/`.

- [ ] **[X5v3-1] Revisar `X5_otros/` completo y decidir qué rescatar**: recorrer todo el contenido de `X5_otros/` (código, notebooks, planes, decisiones y resultados) y clasificar cada pieza como rescatar, adaptar o descartar, con su argumento, para armar una versión de X5 limpia y desde 0. (I:9 C:4 H:10 → 2.37) [dep: —]
  - Claude: leer todo `X5_otros/` (scripts, los notebooks Q1 a Q4 y `x5_alt_variables.py`, que el cuestionamiento del 2026-11-21 no leyó línea a línea, y los docs) y entregar la tabla pieza → rescatar/adaptar/descartar con argumento. Incluir los residuos de X5 que quedaron en archivos compartidos: constantes de X5 en `config.py`, el modo `--x5` de `X4_backtester.py` (importa `X5_macro_brain` y `config_x5_default.py`, que ya no están en git), `docs/plans/documentacion.html`, `docs/plans/algoritmos.tex` y las menciones en `records.md`, `decisiones.md` y `README.md`.
  - Mauricio: revisar la tabla y decidir qué se rescata antes de escribir una línea del X5 nuevo.


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
