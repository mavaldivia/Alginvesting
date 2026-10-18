# Plan — X5_alt_v2, Fase 2: parámetros como funciones dinámicas

> Continúa [`docs/plans/X5_alternativo.md`](X5_alternativo.md) sección 10 (X5_alt_v2). No la reemplaza — agrega la fase siguiente, una vez cerrados `X5_Q1.ipynb`/`X5_Q2.ipynb`/`X5_Q3.ipynb` (ver `X5_alternativo.md` §10.4, 2026-10-12).
> Documento rector de la fase anterior: [`x5_contexto_conversacion.md`](x5_contexto_conversacion.md) — sigue vigente, en particular su Instrucción de trabajo (§22): documentar datos → variables de estado → medir calidad/cobertura → hipótesis → backtesting condicional → validar fuera de muestra → **recién después** implementar funciones prescriptivas. Esta fase (Q4) hace el primer intento de ese último paso, pero como **calibración de diseño**, no como validación económica — esa queda para Q5.

---

## 0. Decisiones de esta sesión

Resueltas con Mauricio vía `/consultar` antes de escribir este plan:

1. **Target de calibración**: cada `f(x)` se ajusta ahora contra un **target de diseño** (sin requerir todavía un "valor óptimo histórico" de backtesting). La validación económica real (comparar el parámetro dinámico vs. el estático actual con resultados de `X4_backtester.py`) es una fase posterior (`X5_Q5.ipynb`), no bloquea esta.
2. **Alcance**: los **5 parámetros iniciales** — `N`, `A`, `factor_B`, `K`, `N_EXP` — más `LAMBDA` y `PERDIDA_MAX`, incorporados el 2026-10-18 por decisión de Mauricio (secciones 11 y 12 del notebook, tras cerrar `Q4-EXEC`). `LAMBDA` conserva su bloqueador de rango (ver §5, `Q4-L1`); `PERDIDA_MAX` aún no tiene variable elegida (`Q4-P1`). `LOTAJES_M` sigue fuera de alcance.
3. **Forma funcional**: sigmoide/logística acotada para todos los parámetros, con piso y techo **configurables por parámetro** (no necesariamente el rango completo de `X5_PARAM_RANGES` — ej. `factor_B` podría acotarse a `(0.3, 0.7)` en vez de `(0.2, 0.7)`). El mecanismo exacto de ajuste se detalla en §3-4.
4. **Estándar de documentación** (decisión posterior, 2026-10-17, ver `docs/context/decisiones.md`): `Q4`/`Q5` son notebooks "sobre el agua" — Mauricio se involucra directamente, a diferencia de `Q1`/`Q2`/`Q3`. Cada parámetro se documenta con Pregunta → Motivación → Metodología → Fundamento matemático → Ejecución → Resultados → Interpretación → Conclusión → Implicancias; el fundamento matemático se explica en detalle la primera vez (Sección 4, `N`) y se referencia sin repetir después.

El resto de este documento desarrolla cómo se implementan estas decisiones.

---

## 1. Qué es esto y por qué existe

`X5_Q1`/`X5_Q2`/`X5_Q3` (cerrados) construyeron evidencia descriptiva y una tabla de hipótesis `parámetro ↔ variable candidata` (`{valor}_q3_4_tabla_final.csv`). Esa tabla es el insumo directo de esta fase: no se repite el trabajo de `Q2`/`Q3`, se **reutiliza** su evidencia para decidir qué variables entran a cada función.

El objetivo de esta fase es que cada parámetro `P` de `config.py` deje de ser un valor fijo por activo y pase a ser `P_t = f(x_{1,t}, ..., x_{k,t})`, con `f` de una forma acotada, interpretable y con pocos parámetros ajustados — de forma que el sistema se vuelva más conservador cuando las condiciones del activo son malas y más agresivo cuando son buenas, sin perder los límites de seguridad ya validados en `X5_PARAM_RANGES`/`pars_configurables.md`.

**Esta fase sigue sin tocar producción.** `X5_Q4.ipynb` (y `X5_Q5.ipynb` después) son notebooks de investigación — igual que `Q1`/`Q2`/`Q3`, no implementan reglas de trading ni escriben en `X0_data_supports.py`/`X1_trading.py`/`config.py`. El puente a producción (cómo `X1`/`X0` leerían estos `f(x)` en vivo) es una fase futura, fuera de alcance aquí — misma lógica que `Q3-3` aplicó a `X5_Q3.ipynb`.

---

## 2. Punto de partida: lo que ya hay

De `X5_alternativo.md` §10.5 y la tabla final de `Q3` (`BTCUSD_q3_4_tabla_final.csv`, `Q3-4`/`Q3-7`):

| Parámetro | Evidencia Q3 | Variables ya candidateadas |
|---|---|---|
| `N` | Alta (drawdown), volatilidad aún no testeada junto a `N` | `x3_drawdown_20` (Pearson 0.28, coseno 0.21 — la mejor de las 3 testeadas), `x3_drawdown_50`, `drawdown_7d` |
| `A` | Baja | `x3_atr_pct` (Pearson -0.013), `x3_bb_width` (redundante con `atr_pct`, Pearson 0.74 entre ambas — `Q2-12`) |
| `factor_B` | Baja (esperado — no es hipótesis de predicción de retorno) | `x3_atr_pct`, `adx_14`, `regimen_tendencia` (nominal, sin evidencia Q2) |
| `K` | Alta (`ruptura_rango`) / baja (`duracion_en_rango`) | `ruptura_rango` (Pearson 0.50), `duracion_en_rango` (≈0) |
| `N_EXP` | Baja | `cambio_volatilidad` (ratio volatilidad corta/larga — la "fórmula literal" del documento rector), `frecuencia_extremos_30d` |
| `LAMBDA` | Baja (bloqueada) | `x3_bb_width`, `duracion_en_rango` — **bloqueado**: rango de exploración documentado (`0.001`-`0.02`) no coincide con el valor productivo (`0.2`, `config.py:95`) |

La evidencia Q3 es correlación **descriptiva** contra `retorno_log_1h` — para `A`/`factor_B`/`K`/`N_EXP` es evidencia indirecta (no son hipótesis de predicción de retorno, sino de escala de mecánica de órdenes/soportes). Eso ya estaba documentado en `Q3-5`/`Q3-6` y sigue aplicando: no es un problema de esta fase, es la naturaleza del dato — la validación real de estos 4 parámetros vendrá de `Q5` (backtesting), no de la calidad de ajuste de `Q4`.

---

## 3. Forma funcional propuesta

### 3.1. Índice compuesto por parámetro

Cada parámetro usa 1 o 2 variables explicativas (nunca más — ver §5). Se combinan en un único índice de estado `s_t`:

```
z_{i,t} = (x_{i,t} - μ_i) / σ_i          # z-score, μ_i/σ_i fijos (calculados una sola vez sobre el histórico de calibración)

s_t = w_1 * z_{1,t} + w_2 * z_{2,t}       # w_2 = 1 - w_1; si k=1, w_1=1 y no hay z_2
```

`μ_i`/`σ_i` se congelan en el momento de calibrar (igual que cualquier normalización de un modelo entrenado) — no se recalculan en vivo. `w_1` es el único peso libre cuando `k=2` (se ajusta junto con el resto, ver 3.2) — con `k=1` no hay peso que ajustar.

**Suavizado del índice (regla general, decisión de Mauricio 2026-10-17)**: el movimiento de cada parámetro dinámico debe ser suave en el tiempo, salvo que el estado del activo cambie de forma sostenida (ej. una caída fuerte de precio en un día) — eso sí puede justificar un movimiento más fuerte del parámetro. Detectado en la validación visual de `N` (`Q4-6`): `N̂_t` sin suavizar saltaba hasta ±70 en una hora en períodos sin novedad real, porque variables como `x3_drawdown_20` resetean seguido contra su máximo rolling. Mecanismo elegido: un EMA causal corto (`suavizar_ema`, `x5_alt_funciones.py`) sobre `s_t` **antes** de `percentil_causal`/`curve_fit` — no un rate-limiter con reglas de excepción aparte. Validado contra el crash histórico más fuerte de la muestra (BTCUSD, -19% en 24h, jun-2022): con `span=6` el índice sigue llegando a piso/techo en pocas horas, solo se filtra el ruido bar-a-bar, no los movimientos reales sostenidos. `calibrar_parametro(..., span_suavizado=...)` expone el parámetro — cada sección de `Q4` (`N`, `A`, `factor_B`, `K`, `N_EXP`) define su propio `SPAN_SUAVIZADO_{PARAM}` (default sugerido: `6` barras H1, ajustable por parámetro si la validación visual lo pide).

### 3.2. Sigmoide acotada

```
P̂(s) = piso + (techo - piso) / (1 + exp(-pendiente * (s - punto_medio)))
```

- **`piso`/`techo`**: **configurables, no ajustados** — definidos por parámetro antes de calibrar (default: el rango de `X5_PARAM_RANGES`/`pars_configurables.md`; pueden acotarse más angosto, ej. `factor_B` en `(0.3, 0.7)` en vez de `(0.2, 0.7)`). Garantiza que `P̂` nunca sale del rango operativo ya validado.
- **`punto_medio`/`pendiente`** (y `w_1` si `k=2`): los **parámetros realmente ajustados** por `curve_fit` (ver §4). 2 o 3 números por combo — se mantiene deliberadamente chico para no sobreajustar con el historial disponible por activo.

Por qué esta forma y no otra (resuelto en el `/consultar`, documentado aquí por si se revisita):
- Acotada por diseño → nunca produce un valor fuera del rango ya validado por `X5_PARAM_RANGES`, a diferencia de un ajuste lineal sin tope.
- Transición suave (sin quiebres de tramo) → evita saltos de parámetro en vivo si el estado del activo oscila cerca de un límite de régimen.
- Pocos parámetros interpretables → `punto_medio` = "dónde está el punto de indiferencia del índice", `pendiente` = "qué tan abruptamente reacciona", `w_1` = "cuánto pesa cada variable" — cada uno se puede leer e inspeccionar visualmente en `Q4`, a diferencia de un modelo no paramétrico (árbol/GB).
- Generaliza igual a `k=1` y `k=2` sin cambiar de familia de función.

---

## 4. Mecanismo de calibración (sin backtesting todavía)

El problema: `curve_fit` necesita un objetivo `y_t` contra el cual minimizar error, pero no tenemos (todavía) un "valor óptimo histórico" de `N`/`A`/etc. por timestamp — eso requeriría el backtesting condicional que es, precisamente, lo que queda para `Q5`.

**Target sintético por percentil causal**: en vez de un target económico, se usa un target de diseño que solo codifica la *dirección* ya hipotetizada (de `Q3`) y los límites configurados:

```
q_t = percentil_causal(s_t)               # rango histórico de s_t usando SOLO datos hasta t (expanding, sin leakage — Principio 11 de x5_contexto_conversacion.md)
y*_t = piso + (techo - piso) * q_t         # si q_t=0 (peor condición histórica hasta t) -> y*_t=piso; si q_t=1 -> y*_t=techo
```

Y se ajusta `P̂(s_t; punto_medio, pendiente, w_1)` contra `y*_t` por mínimos cuadrados (`scipy.optimize.curve_fit`). En la práctica esto suaviza/parametriza un mapeo por percentiles en una curva con 2-3 constantes — es un ajuste de curva real (cumple el pedido literal), pero su calibración es por diseño (percentil + dirección), no por resultado económico.

**Qué reporta `Q4` sobre la calidad de este ajuste** (ninguno es "validación", son diagnósticos de que la curva aproxima bien el target de diseño):
- `R²` de `P̂` vs. `y*_t` (bondad de ajuste de la sigmoide al target sintético).
- Elasticidad en el punto medio: `dP̂/ds |_{punto_medio} = pendiente * (techo - piso) / 4`.
- Serie temporal `P̂_t` vs. el valor estático actual, a doble eje con el precio — para que Mauricio inspeccione visualmente si el comportamiento dinámico "hace sentido" en episodios históricos conocidos (ej. un drawdown fuerte de BTCUSD).
- Signo de `pendiente` vs. la dirección ya hipotetizada en `Q3` — si no coincide, se marca como alerta explícita en el notebook (no se fuerza el signo en el ajuste, se reporta si contradice la hipótesis).

**Qué NO resuelve esta fase** (deliberado, va a `Q5`): si el parámetro dinámico efectivamente mejora el resultado económico vs. el estático. El buen ajuste de `Q4` es necesario pero no suficiente.

---

## 5. Combinaciones parámetro↔variable de esta fase

Deliberadamente limitadas (restricción explícita de Mauricio). Reutilizan las variables ya evaluadas en `Q3` cuando la evidencia alcanza; cuando la hipótesis documentada pide una dimensión que `Q3` no testeó (caso de `N`, que según `X5_alternativo.md` §10.5 es `f(drawdown, volatilidad)` pero `Q3` solo testeó variables de drawdown), se agrega en `Q4`.

| Parámetro | `k` | Variables (`x_1`, `x_2`) | Rango productivo (`piso`, `techo`) default | Nota |
|---|---|---|---|---|
| `N` | 2 | `x3_drawdown_20`, `x3_atr_pct` | `(50, 200)` BTCUSD/ETHUSD, `(40, 180)` resto (`X5_PARAM_RANGES['n_sizes_ejecucion']`) | `x3_atr_pct` no estaba en la tabla `Q3-4` para `N` — se agrega para completar la hipótesis `drawdown + volatilidad` de `X5_alternativo.md` §10.5. |
| `A` | 1 | `x3_atr_pct` | `(2.0, 20.0)` USD (`X5_PARAM_RANGES['A']`) | Se descarta `x3_bb_width` por redundante con `atr_pct` (`Q2-12`, Pearson 0.74). Nota explícita en el notebook: `A` se calibra **único**, sin separar `A_OE`/`A_TRAILING` — decisión pendiente de `x5_contexto_conversacion.md` §21 que esta fase no resuelve (ver §7). |
| `factor_B` | 2 | `x3_atr_pct`, `adx_14` | `(0.2, 0.7)` (tentativo, `x5_contexto_conversacion.md` §8 — **no está en `X5_PARAM_RANGES`** todavía, ver §6) | Se descarta `regimen_tendencia` (nominal, no apto para índice continuo); `adx_14` cubre la dimensión de tendencia. |
| `K` | 1 | `ruptura_rango` | `(0.5, 2.0)` (`X5_PARAM_RANGES['K']`) | Se descarta `duracion_en_rango` (evidencia ≈0 en `Q3-4`). |
| `N_EXP` | 1 | `cambio_volatilidad` | `(0.5, 3.0)` (`X5_PARAM_RANGES['N_EXP']`) | Se descarta `frecuencia_extremos_30d` para mantener `k=1` — es secundaria según `Q3-6`. |

Total: **5 parámetros, 7 combinaciones parámetro-variable** (2+1+2+1+1). `x3_atr_pct` se reutiliza en `N`/`A`/`factor_B` — eso no viola la restricción (que es sobre cuántas variables explican *cada* parámetro, no sobre cuántos parámetros puede explicar una misma variable).

`LAMBDA` queda fuera de esta tabla — ver `Q4-9`/§7.

---

## 6. Gaps de config detectados (no se resuelven en esta fase, se documentan)

- **`factor_B` no está en `X5_PARAM_RANGES`**: `config.py:350-363` todavía explora `'B'` directo en USD (`(0.5, 5.0)`), no `factor_B` como multiplicador adimensional de `A` — la redefinición `B = factor_B * A` (`x5_contexto_conversacion.md`, decisión confirmada §21) nunca se propagó a `X5_PARAM_RANGES`. `Q4` usa el rango tentativo de `factor_B` documentado en el texto (`(0.2, 0.7)`), no un rango formal de `config.py`. Corregir `X5_PARAM_RANGES` es un cambio de producción fuera de esta fase — queda anotado en `docs/context/decisiones.md` si se decide abordarlo.
- **`K`/`N_EXP`/`LAMBDA` son globales en producción, no por activo** (`pars_configurables.md`, sección "Parámetros de scoring del algoritmo de soportes"). `Q4` los calibra **por activo** igual que el resto (consistente con la convención `Q1`-`Q3` de nunca mezclar activos), pero si la hipótesis se confirma en `Q5`, llevarlos a producción exigiría antes decidir si pasan a ser por-activo también en `X0` — decisión arquitectónica fuera de esta fase, solo se deja señalada.

---

## 7. Qué queda explícitamente fuera de esta fase

- Separar `A` en `A_OE`/`A_TRAILING` (decisión pendiente, `x5_contexto_conversacion.md` §21) — `A` se calibra único por ahora; si más adelante se decide separarlo, la misma familia de función se replica dos veces sin cambios de diseño.
- Resolver el rango real de `LAMBDA` de antemano — `Q4-L1` lo deja como paso obligatorio *antes* de calibrar `LAMBDA` (bloqueador heredado de `Q3-6`).
- Cualquier cambio a `X0_data_supports.py`/`X1_trading.py`/`config.py` de producción — el puente a producción (cómo X1 leería `P̂(s_t)` en vivo, con qué cadencia de refresco, fallback si falta algún insumo) es una fase futura, análoga a `TIPO_EJECUCION="din"` de X5 original.
- Validación económica/backtesting — eso es `X5_Q5.ipynb` (§9).

---

## 8. Estructura de `X5_Q4.ipynb`

Mismo patrón de `Q1`/`Q2`/`Q3`: `valores` (lista, default `['BTCUSD']`), reutiliza loaders existentes sin recalcular, cierra con `exportar_zip`. Una sección por parámetro, cada una con: índice compuesto, ajuste, gráficos, diagnóstico.

- **Sección 0 — Arranque**: carga `{valor}_tabla_estado_v2.csv` (`Q1-2`) + `{valor}_q2_5_export_metricas.json` (`Q2-5`) + `{valor}_q3_4_tabla_final.csv` (`Q3-4`). Sin recalcular nada de `Q1`-`Q3`.
- **Sección 1 — Utilidades compartidas**: importa `scripts/x5_alt_funciones.py` (nuevo módulo, ver §10) — sigmoide acotada, índice compuesto, percentil causal, ajuste por `curve_fit`, métricas de diagnóstico. Una sola implementación, las 5 secciones de parámetro la reutilizan (nunca reimplementan la fórmula).
- **Secciones 2-6 — Una por parámetro** (`N`, `A`, `factor_B`, `K`, `N_EXP`), mismo esqueleto en cada una:
  1. Construcción del índice compuesto `s_t`, ya suavizado con `span_suavizado` (ver §3.1) — gráfico de cada variable normalizada (sin suavizar) + el índice combinado (suavizado), a doble eje con `Close`.
  2. Ajuste de `punto_medio`/`pendiente`(/`w_1`) vía `curve_fit` contra el target sintético.
  3. Gráfico de la curva ajustada `P̂(s)` superpuesta sobre el scatter `(s_t, y*_t)`.
  4. Serie temporal `P̂_t` vs. el valor estático actual de producción, a doble eje con el precio — la pieza central para que Mauricio valide visualmente la hipótesis en episodios conocidos.
  5. Diagnóstico: `R²`, elasticidad en el punto medio, chequeo de signo vs. hipótesis `Q3`.
  6. Export: parámetros ajustados + serie `P̂_t` a `{valor}_q4_{parametro}.csv`.
- **Sección 7 — `LAMBDA`** (condicional a resolver `Q4-9` primero — puede quedar vacía/pendiente si no se resuelve en la misma sesión).
- **Sección 8 — Resumen consolidado**: tabla única con bondad de ajuste + elasticidad por combo, `{valor}_q4_resumen.csv`.
- **Sección 9 — Export a zip** (`exportar_zip`, mismo patrón que `Q1`/`Q2`/`Q3`).

---

## 9. `X5_Q5.ipynb` — fase posterior (solo alcance, no se implementa todavía)

Puente a `X4_backtester.py`: para cada combo de `Q4`, correr el parámetro dinámico `P̂_t` vs. el estático actual sobre el mismo período histórico y comparar resultado económico real (no solo bondad de ajuste a un target sintético). Requiere antes diseñar el "backtesting condicional por régimen" que `x5_contexto_conversacion.md` §21 deja como decisión pendiente — por eso no se desglosa en detalle aquí (ver `Q5-1` en los TODOs: ese diseño es un paso previo, no una sección más del notebook). Walk-forward / fuera de muestra por activo, consistente con el Principio 10 de `x5_contexto_conversacion.md`.

---

## 10. Entregables de esta sesión

Lo que se crea/modifica ahora (además de este documento):

- `docs/tracking/todos.md` — ítems `[Q4-1]` a `[Q4-EXEC]` y semilla de `Q5` en la sección `X5_alt_v2`.
- `docs/plans/X5_alternativo.md` — puntero breve a este plan desde §10.
- `scripts/x5_alt_funciones.py` — módulo compartido, **implementado y probado** (sigmoide acotada, índice compuesto, percentil causal, ajuste `curve_fit`, diagnóstico). No requiere `Data`/MT5 — es matemática pura, se puede desarrollar y validar en Mac.
- `scripts/X5_Q4.ipynb` — scaffold: Sección 0 (arranque) y Sección 1 (import de utilidades) con código; Secciones 2-9 como encabezados markdown pendientes de implementar (misma mecánica para todas, se desarrollan ítem por ítem en sesiones siguientes vía `/todos`, cada una ejecutada de punta a punta en Windows con datos reales — Mac no tiene `Data`/`resources/x2`/`resources/x3`).

`X5_Q5.ipynb` no se crea todavía — su diseño depende de la decisión pendiente de backtesting condicional (§9).

Pendiente para una sesión futura (ya en los TODOs, no se hace ahora): `docs/plans/plan_x5_alt_v2.pdf` en LaTeX (~10-12 páginas), mismo patrón que `x5_alt_v2.tex`/`.pdf` existente para `Q1`/`Q2`/`Q3`.

---

## 11. Riesgos / limitaciones abiertas

- **Historial corto por activo**: ajustar 2-3 parámetros por combo es deliberadamente poco, pero igual puede sobreajustar en activos con pocas velas o regímenes poco variados (ej. activos listados más recientemente) — revisar visualmente antes de confiar en el ajuste.
- **Percentil causal con ventana expanding**: al principio del histórico el percentil es poco informativo (pocos datos para comparar) — los primeros tramos de la serie `P̂_t` deben leerse con cautela, no como señal real.
- **`atr_pct` reutilizado en 3 parámetros** (`N`, `A`, `factor_B`): si `atr_pct` tiene algún problema de calidad/cobertura de datos, contamina las 3 calibraciones a la vez — vale la pena un chequeo de calidad de esa columna específica antes de calibrar.
- **Buen ajuste a un target sintético no implica utilidad económica** — riesgo central de esta fase, mitigado por mantener `Q5` como gate obligatorio antes de cualquier wiring a producción.
