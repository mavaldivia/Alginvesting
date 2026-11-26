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

### X5 — versión nueva, limpia y desde 0

> El X5 anterior (macrobrain, X5_alt y X5_alt_v2, con todos sus códigos y documentos) vive en `X5_otros/`: carpeta local, ignorada por git, que **no está en GitHub**. Sus TO DOs quedaron en `X5_otros/docs/tracking/todos_x5.md` y sus ítems cerrados en `X5_otros/docs/tracking/done_x5.md`. Nada de eso se retoma sin decidirlo en esta sección.
> Carpeta de trabajo de X5, en git: `X5/`. **Plan vigente: [`X5/x5_informe.pdf`](../../X5/x5_informe.pdf)** (fuente `x5_informe.tex`, 17 págs: diagnóstico, embudo de tres niveles, escalera del dinamismo, 7 fases y 4 bifurcaciones). **Contexto consolidado de `X5_otros/`: [`X5/contexto_x5.md`](../../X5/contexto_x5.md)** (para no volver a abrirla). `X5/X5_v3.md` y `x5_v3_informe.pdf` quedan como respaldo de números y métodos.
> **Decisiones de Mauricio (2026-11-22)**: (1) objetivo híbrido: ganancia semanal pareada como filtro rápido y retorno total de la cuenta continua como vara final; (2) X5 solo vale si hay dinamismo (la mejor estática es el rival a vencer, no una meta); (3) Mac casi dedicado, 30 o más horas de cómputo por semana.
> **En esta sección el orden de abajo ES el orden de ejecución** (no se prioriza por score). Cada ítem lleva `[dep: ...]`; si al empezar uno falta alguna dependencia sin marcar `[x]` en `done.md`, advertirlo y no avanzar con ese ítem. Las fases 2, 3, 4 y 5 terminan en una **bifurcación** (rama A/B/C): el criterio se anota en `decisiones.md` *antes* de correr la fase.
> **Backtester (X4) y X5 se coordinan**: `scripts/X4_backtester.py` se puede importar desde el 2026-11-24 (el piloto `[X5-P]` le sacó `x5_demo`), pero su modo `--x5` sigue roto. El resto del cambio de X4 se diseña junto con el motor de repetición de X5 (`[X5-4]`) y se implementa con él (`[X5-5]`), para que X5 llame a X4 sin duplicar su lógica. Para relanzar el orquestador antiguo de ventanas: `PYTHONPATH=scripts:X5_otros/scripts:X5_otros/Otros/scripts`.

- [ ] **[X5-1] Revisar el informe y el contexto de X5 y decidir** (primer pendiente, de Mauricio): leer `X5/x5_informe.pdf` (el §8 lista las 9 decisiones que necesita el arranque) y repasar `X5/contexto_x5.md` (§6 es la tabla rescatar/adaptar/descartar; §9, los residuos en archivos compartidos). Decidir qué se archiva, qué se respalda y qué umbrales de riesgo se usan. (I:9 C:4 H:10 → 2.37) [dep: —]
  - Claude: **hecho el 2026-11-22**: revisión completa de `X5_otros/` y `X5/`, informe de 17 páginas y contexto consolidado.
  - Mauricio: revisar el informe y el contexto; responder las decisiones 1 a 9 del §8 del informe (qué se archiva, respaldo de `X5_otros/`, reparar X4 coordinado con X5, tope de riesgo, bloque intocable, spread, pérdida máxima, orden de la escalera, prioridad de activos) y pedir los cambios que quiera.
- [ ] **[X5-2] Respaldo de `X5_otros/` y archivo de las piezas rescatadas**: respaldar `X5_otros/` fuera del Mac (lo irrecuperable: `resources/x5_alt/q5/`, 104 MB, y los PDF) y copiar a `X5/archivo/` las piezas que Mauricio apruebe en `[X5-1]` (§6 de `contexto_x5.md`). (I:7 C:2 H:8 → 3.74) [dep: X5-1]
  - Claude: copiar a `X5/archivo/` las piezas aprobadas y dejar un índice.
  - Mauricio: respaldar `X5_otros/` en un disco externo o la nube antes de moverlo o borrarlo.
- [ ] **[X5-3] Pre-registro: objetivo, umbrales y bloque intocable**: escribir en `decisiones.md` el objetivo híbrido con sus umbrales (pérdida en la cola y caída máxima de la cuenta continua), el bloque de confirmación intocable (propuesta: desde 2026-04-01), si se cobra spread, qué hacer con la pérdida máxima, la prueba del candidato nulo (debe pasar menos del 10 % de las veces) y la estructura de carpetas (`scripts/X5_*.py`, `X5/`, `resources/x5/`). (I:8 C:2 H:9 → 4.24) [dep: X5-1]
  - Claude: redactar el pre-registro con los criterios de cada fase y la plantilla del Anexo B del informe.
  - Mauricio: fijar los umbrales y la fecha del bloque intocable.
- [ ] **[X5-4] Diseño conjunto X4 ↔ motor de X5 (sin tocar código)**: especificar en un documento corto qué debe cambiar en `X4_backtester.py` y qué hace el motor nuevo de X5, para que se coordinen y X5 no duplique lógica de X0/X1/X4: quitar el modo `--x5` (el `import x5_demo` ya se sacó en `[X5-P]`); absorber `SOPORTES_PRECALCULADOS`, `fecha_fin` y `scripts/X5_piloto.py`; exponer como funciones importables la *búsqueda de soportes* y la *operación de una semana* por separado; conservar `R_TOPE_OA`, semillas (`SEMILLA_INTRAVELA`, `SEMILLA_BUSQUEDA`) y el tope de tiempo de la búsqueda; spread opcional al llenar; contrato de `construir_cfg`; banco de soportes indexado por `N`, `K`, `N_EXP` y `LAMBDA`; cuenta continua con soportes del banco. Incluye qué partes del modo `--x5` se borran y cómo se verifica que el modo por versión sigue funcionando. (I:9 C:3 H:10 → 3.16) [dep: X5-1, X5-3]
  - Claude: leer `X4_backtester.py` completo y entregar el diseño (interfaz, qué se quita, qué se agrega, pruebas) para aprobación.
  - Mauricio: aprobar o ajustar el diseño antes de que se escriba una línea.
- [ ] **[X5-5] Reparar X4 e implementar el motor de repetición (Fases 0b y 1)**: aplicar el diseño de `[X5-4]`: X4 funciona sin el modo `--x5`; motor `buscar_soportes` / `operar_semana(valor, t*, soportes, config, semilla)`; reproducir 20 ventanas con su configuración guardada (error menor a 0,01 USD); medir el ruido (dos semillas de la intra-vela en 20 `t*`, búsqueda repetida en 10 `t*`); spread opcional; registro CSV. Criterio: `import X4_backtester` funciona, una corrida corta reproduce un resultado conocido y cada semana-configuración cuesta de 2 a 4 s. (I:10 C:6 H:10 → 1.67) [dep: X5-4]
  - Claude: implementar X4 + motor y sus pruebas (causalidad y reproducción).
  - Mauricio: correr en Mac (`caffeinate -i`) la validación de reproducción y de ruido.
- [ ] **[X5-6] Residuos del X5 anterior en archivos compartidos**: borrar el bloque del macrobrain de `config.py` (líneas 336 a 441), reescribir comentarios de `X0_data_supports.py`, recortar `docs/plans/documentacion.html` y `algoritmos.tex` a X4, actualizar `vision.md`, `CLAUDE.md` y los planes de X2/X3/X4 (detalle en `contexto_x5.md` §9). (I:4 C:3 H:4 → 1.33) [dep: X5-5]
  - Claude: limpiar sin tocar las bitácoras (`records.md`, `decisiones.md`, `prompts.md`, `done.md`).
- [ ] **[X5-7] Fase 2 — ¿Cuánto vale X0 frente a una grilla pareja? (bifurcación I)**: en 20 a 40 `t*` de BTCUSD y TSLA, comparar soportes de calidad de producción (búsqueda encadenada) con la grilla de las ventanas: desigualdad de las distancias y resultado de la estática en pares. Ramas: I-A (X0 ≈ grilla: banco sintético), I-B (X0 > grilla: banco de producción, 24 a 40 h por valor), I-C (según el activo). (I:9 C:5 H:9 → 1.80) [dep: X5-5]
  - Claude: preparar y analizar el experimento y proponer la rama con su evidencia.
  - Mauricio: dejar corriendo el cómputo (10 a 20 h) y elegir la rama.
- [ ] **[X5-8] Fase 3 — Unidades de mercado y mejor estática (bifurcación II)**: pasar `A`, `B` y la pérdida máxima a unidades de ATR y las variables de estado a tiempo (días de mercado); barrido factorial de operación sobre el banco (unas 100 configuraciones × 240 semanas); cuenta continua (nivel 2) para los 10 a 20 finalistas y la etiqueta de cohorte. Entrega la mejor estática por activo (con su meseta) y deja probado D1. (I:10 C:7 H:9 → 1.36) [dep: X5-7]
  - Claude: adaptar `x5_alt_variables.py` (ventanas en tiempo, sin fundamentales) y correr el barrido.
  - Mauricio: elegir la rama II (mejora, paisaje plano o estática actual ya óptima).
- [ ] **[X5-9] Fase 4 — La escalera del dinamismo (bifurcación III)**: probar D1 a D6 con pre-registro, contraste pareado por semana, bloques con purga y control de comparaciones múltiples; orden propuesto D1, D4, D2, D3, D5. Ramas: III-A (hay heterogeneidad: política mínima), III-B (no: subir de peldaño y, si se agota, replanteo), III-C (solo en un tipo de activo). (I:10 C:8 H:8 → 1.12) [dep: X5-8]
  - Claude: ejecutar cada peldaño con su criterio y su criterio de abandono.
  - Mauricio: elegir la rama III; si la escalera se agota, decidir cuál de los replanteos del §6 del informe seguir.
- [ ] **[X5-10] Fase 5 — Examen y riesgo (bifurcación IV)**: los finalistas pasan al nivel 3 (X4 continuo con X0 real, spread y bloque intocable, una sola vez); media pareada contra la mejor estática con intervalo del 90 % sobre 0, cola no peor en más de 10 % y sin peor caída máxima; decidir la pérdida máxima y el tope de Órdenes Abiertas como política de riesgo. (I:10 C:5 H:8 → 1.79) [dep: X5-9]
  - Claude: correr el examen y registrar cuántas evaluaciones se hicieron.
  - Mauricio: decidir la promoción.
- [ ] **[X5-11] Fase 6 — Puente a demo**: solo para lo validado: publicar por valor con el patrón del publicador anterior (archivo atómico, respaldo a `config.py`, registro JSON Lines) y tope de Órdenes Abiertas en X1 sobre cuenta virtual; pruebas en Windows (`history_deals_get`); demo hacia adelante de al menos 4 semanas. (I:8 C:7 H:5 → 0.90) [dep: X5-10]
  - Claude: implementar la lectura en X0/X1 sin duplicar lógica.
  - Mauricio: probar en Windows y dejar correr la demo.
- [ ] **[X5-12] Extender a los otros 5 valores**: actualizar `Data/` y `Data_minuto/` desde Windows y repetir las fases 2 a 5 para ETHUSD, GOOGL, NVDA, AMZN y MSFT (acciones con 7 a 10 velas por día: ventanas en días de mercado). (I:6 C:4 H:4 → 1.22) [dep: X5-8]
  - Mauricio: actualizar los datos desde Windows.
  - Claude: correr las fases por valor.


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
