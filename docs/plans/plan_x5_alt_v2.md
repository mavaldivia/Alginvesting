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

5. **Cierre de `Q4` (2026-11-02)**: siete parámetros calibrados (`N`, `A`, `factor_B`, `K`, `N_EXP`, `LAMBDA`, `PERDIDA_MAX`); pisos y techos movidos a `scripts/config_smart.py` (cripto y acciones por separado); funciones finales documentadas en [`docs/context/funciones_pars_dinamicos.pdf`](../context/funciones_pars_dinamicos.pdf). Detalle y razones en `docs/context/decisiones.md`.
6. **Backtesting (2026-11-02)**: `Q5` pasa a ser el backtesting inteligente de horizonte completo (§9), que reemplaza el diseño por ventanas de 7 días del 2026-10-23. Se precisó el mismo día con la jerarquía de parámetros C1/C2, cadencias `N_VELAS`, cuenta de 3000 USD por valor, aprendizaje con RLM + Gradient Ascent, tramo reservado como compuerta y tres niveles de agregación pausados.

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

> Actualización 2026-10-23: en `X5_Q4` la variable de drawdown para `N` pasó de `x3_drawdown_20` a `drawdown_7d` (ver `docs/context/decisiones.md`).
| `A` | Baja | `x3_atr_pct` (Pearson -0.013), `x3_bb_width` (redundante con `atr_pct`, Pearson 0.74 entre ambas — `Q2-12`) |
| `factor_B` | Baja (esperado — no es hipótesis de predicción de retorno) | `x3_atr_pct`, `adx_14`, `regimen_tendencia` (nominal, sin evidencia Q2) |
| `K` | Alta (`ruptura_rango`) / baja (`duracion_en_rango`) | `ruptura_rango` (Pearson 0.50), `duracion_en_rango` (≈0) |
| `N_EXP` | Baja | `cambio_volatilidad` (ratio volatilidad corta/larga — la "fórmula literal" del documento rector), `frecuencia_extremos_30d` |
| `LAMBDA` | Baja (bloqueada) | `x3_bb_width`, `duracion_en_rango` — **bloqueado**: rango de exploración documentado (`0.001`-`0.02`) no coincide con el valor productivo (`0.2`, `config.py:95`) |

La evidencia Q3 es correlación **descriptiva** contra `retorno_log_1h` — para `A`/`factor_B`/`K`/`N_EXP` es evidencia indirecta (no son hipótesis de predicción de retorno, sino de escala de mecánica de órdenes/soportes). Eso ya estaba documentado en `Q3-5`/`Q3-6` y sigue aplicando: no es un problema de esta fase, es la naturaleza del dato — la validación real de estos 4 parámetros vendrá de `Q5` (backtesting), no de la calidad de ajuste de `Q4`.

---

## 3. Forma funcional propuesta

### 3.1. Índice compuesto por parámetro

Cada parámetro usa hoy 1 o 2 variables explicativas, salvo `N`, que desde 2026-11-02 usa 3. El máximo es tentativo (decisión de Mauricio, 2026-11-04): puede haber 3, 4 o más, y la lista de variables de un parámetro puede cambiar después de ver resultados (ver §9.12). Se combinan en un único índice de estado `s_t`:

```
z_{i,t} = (x_{i,t} - μ_i) / σ_i          # z-score, μ_i/σ_i fijos (calculados una sola vez sobre el histórico de calibración)

s_t = w_1 * z_{1,t} + w_2 * z_{2,t}       # w_2 = 1 - w_1; si k=1, w_1=1 y no hay z_2
                                          # N (k=3): s_t = 0.6*z_1 + 0.2*z_2 + 0.2*z_3, pesos fijos
```

`μ_i`/`σ_i` se congelan en el momento de calibrar (igual que cualquier normalización de un modelo entrenado) — no se recalculan en vivo. `w_1` es el único peso libre cuando `k=2` (se ajusta junto con el resto, ver 3.2) — con `k=1` no hay peso que ajustar. Con `k=3` (solo `N`) los pesos van fijos (`pesos_fijos` en `calibrar_parametro`), sin grilla ni ajuste.

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

Deliberadamente pocas en esta fase (restricción explícita de Mauricio, tentativa: ver §9.12 para agregar, quitar o cambiar variables). Reutilizan las variables ya evaluadas en `Q3` cuando la evidencia alcanza; cuando la hipótesis documentada pide una dimensión que `Q3` no testeó (caso de `N`, que según `X5_alternativo.md` §10.5 es `f(drawdown, volatilidad)` pero `Q3` solo testeó variables de drawdown), se agrega en `Q4`.

| Parámetro | `k` | Variables (`x_1`, `x_2`) | Rango productivo (`piso`, `techo`) default | Nota |
|---|---|---|---|---|
| `N` | 3 | `x3_drawdown_20`, `x3_atr_pct`, `ln_razon_vol_30d` | `(50, 200)` BTCUSD/ETHUSD, `(40, 180)` resto (`X5_PARAM_RANGES['n_sizes_ejecucion']`) | `x3_atr_pct` no estaba en la tabla `Q3-4` para `N` — se agrega para completar la hipótesis `drawdown + volatilidad` de `X5_alternativo.md` §10.5. Desde 2026-11-02 suma `ln_razon_vol_30d = ln(vol_alcista_30d / vol_bajista_30d)` (columnas de Q1, ventana 30d; razón > 0 sube `N`), pesos fijos `[0.6, 0.2, 0.2]` — única excepción al límite de 2 variables, pedido de Mauricio (`decisiones.md` 2026-11-02). Hoy la variable de drawdown es `drawdown_30d`, ver nota del 2026-10-23. |
| `A` | 2 | `x3_atr_pct`, `ln_razon_vol_30d` | `(2.0, 20.0)` USD (`X5_PARAM_RANGES['A']`) | Se descarta `x3_bb_width` por redundante con `atr_pct` (`Q2-12`, Pearson 0.74). Desde 2026-11-02 suma `ln_razon_vol_30d` (la misma de `N`), pesos fijos `[0.7, 0.3]` y sin invertir ninguna de las dos (razón > 0 sube `A`; hipótesis de Mauricio, no estaba en `Q3`). Nota explícita en el notebook: `A` se calibra **único**, sin separar `A_OE`/`A_TRAILING` — decisión pendiente de `x5_contexto_conversacion.md` §21 que esta fase no resuelve (ver §7). |
| `factor_B` | 2 | `x3_atr_pct`, `adx_14` | `(0.2, 0.7)` (tentativo, `x5_contexto_conversacion.md` §8 — **no está en `X5_PARAM_RANGES`** todavía, ver §6) | Se descarta `regimen_tendencia` (nominal, no apto para índice continuo); `adx_14` cubre la dimensión de tendencia. |
| `K` | 1 | `-abs(ruptura_rango)` | `(0.5, 2.0)` (`X5_PARAM_RANGES['K']`) | Se descarta `duracion_en_rango` (evidencia ≈0 en `Q3-4`). Valor absoluto invertido: una ruptura al alza y una a la baja son ambas un nivel que no se sostuvo. La evidencia "alta" de `Q3-4` para `ruptura_rango` es mecánica (Pearson 0.50 solo con el retorno de la misma hora), así que la variable descansa en la hipótesis. |
| `N_EXP` | 1 | `cambio_volatilidad` | `(0.5, 3.0)` (`X5_PARAM_RANGES['N_EXP']`) | Se descarta `frecuencia_extremos_30d` para mantener `k=1` — es secundaria según `Q3-6`. Evidencia de `Q2`/`Q3` baja; descansa en la hipótesis. |
| `LAMBDA` | 2 | `x3_bb_width`, `duracion_en_rango` | `(0.05, 0.5)` (decisión 2026-11-02; contiene el productivo 0.2, el rango `(0.001, 0.02)` de `X5_PARAM_RANGES` lo dejaba fuera) | Pesos por grilla (salen `[0.2, 0.8]`/`[0.3, 0.7]`). Evidencia baja. |
| `PERDIDA_MAX` | 1 | `drawdown_7d` | `(100, 300)` USD | Sin hipótesis en `Q3`; elegida con la evidencia de `Q2` (alta y estable en los 7 activos contra el retorno de la hora siguiente). Pausada como posible capa externa de riesgo (`x5_contexto_conversacion.md` §10). |

Total: **7 parámetros, 12 combinaciones parámetro-variable** (3+2+2+1+1+2+1). `x3_atr_pct` se reutiliza en `N`/`A`/`factor_B` — eso no viola la restricción (que es sobre cuántas variables explican *cada* parámetro, no sobre cuántos parámetros puede explicar una misma variable).

Los pisos y techos de la columna "Rango" ya no se leen de `config.py` sino de `scripts/config_smart.py`, separados en cripto y acciones.

---

## 6. Gaps de config detectados (no se resuelven en esta fase, se documentan)

- **`factor_B` no está en `X5_PARAM_RANGES`**: `config.py:350-363` todavía explora `'B'` directo en USD (`(0.5, 5.0)`), no `factor_B` como multiplicador adimensional de `A` — la redefinición `B = factor_B * A` (`x5_contexto_conversacion.md`, decisión confirmada §21) nunca se propagó a `X5_PARAM_RANGES`. `Q4` usa el rango tentativo de `factor_B` documentado en el texto (`(0.2, 0.7)`), no un rango formal de `config.py`. Corregir `X5_PARAM_RANGES` es un cambio de producción fuera de esta fase — queda anotado en `docs/context/decisiones.md` si se decide abordarlo.
- **`K`/`N_EXP`/`LAMBDA` son globales en producción, no por activo** (`pars_configurables.md`, sección "Parámetros de scoring del algoritmo de soportes"). `Q4` los calibra **por activo** igual que el resto (consistente con la convención `Q1`-`Q3` de nunca mezclar activos), pero si la hipótesis se confirma en `Q5`, llevarlos a producción exigiría antes decidir si pasan a ser por-activo también en `X0` — decisión arquitectónica fuera de esta fase, solo se deja señalada.

---

## 7. Qué queda explícitamente fuera de esta fase

- Separar `A` en `A_OE`/`A_TRAILING` (decisión pendiente, `x5_contexto_conversacion.md` §21) — `A` se calibra único por ahora; si más adelante se decide separarlo, la misma familia de función se replica dos veces sin cambios de diseño.
- (Resuelto el 2026-11-02) El rango de `LAMBDA` queda en `(0.05, 0.5)` en `config_smart.py`.
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
- **Estructura final (2026-11-02)**: secciones 4 `N`, 5 `A`, 6 `factor_B`, 7 `K`, 8 `N_EXP`, 9 `LAMBDA`, 10 `PERDIDA_MAX`, 11 resumen consolidado y 12 export a zip.
- **Sección 11 — Resumen consolidado**: tabla con bondad de ajuste, elasticidad, signo, estático y suavidad por parámetro y activo, más variables, pesos y `μ`/`σ` para reconstruir `P̂_t`, en `{valor}_q4_resumen.csv`.
- **Sección 12 — Export a zip** (`exportar_zip`, mismo patrón que `Q1`/`Q2`/`Q3`).

---

## 9. Backtesting inteligente (`Q5`) — puente a `X4_backtester.py`

Decidido el 2026-11-02 y precisado el mismo día con la jerarquía de parámetros C1/C2, las dos cadencias de actualización, la cuenta de 3000 USD por valor y el aprendizaje con Regresión Lineal Múltiple (RLM) + Gradient Ascent (ver `docs/context/decisiones.md`). Reemplaza el diseño por ventanas de 7 días del 2026-10-23. Para cada valor, una **vuelta** es un backtest completo desde el 2022-03-01 (`FECHA_INICIO_BT`, fija: 60 días de calentamiento) hasta la última vela histórica, con los coeficientes C2 fijos durante toda la vuelta; las búsquedas de soportes usan datos desde `FECHA_INICIAL` (2022-01-01, `config.py`); al terminar se aprende de ella y se corrigen los C2 para la siguiente. Cada valor se trata de forma independiente (un proceso por valor, `--activo`).

Se desarrolla sobre lo que ya existe: `X4_backtester.py` (modo `--x5` y `--activo`, `_aplicar_params_x5`, checkpoint y equity aislados por activo); el backtesting inteligente es un **script nuevo** (`X4S_backtesting_inteligente.py`, nombre provisional) que importa de `X4_backtester.py`, sin modo `--smart` ni `X4B` (decidido 2026-11-03); de `Q4` toma `{valor}_q4_resumen.csv`, `x5_alt_funciones.py` y `config_smart.py`. Nunca reimplementa X0/X1.

### 9.0. Jerarquía de parámetros: C1 y C2

| Categoría | Qué es | Parámetros |
|---|---|---|
| **Primera categoría (C1)** | Los siete parámetros configurables que usan X0/X1, por valor `v` | `N`, `A`, `factor_B`, `K`, `N_EXP`, `LAMBDA`, `PERDIDA_MAX` (esta última como fracción `p` de la cuenta, ver 9.3) |
| **Segunda categoría (C2)** | Los coeficientes de la función que produce cada C1: `C1(v) = f(C2(v))`, con la sigmoide acotada de §3 | por cada C1: `span` del suavizado, `punto_medio`, `pendiente` y pesos `w_i` de sus variables |

Los pesos se normalizan: `w̃_i = w_i / Σ_j w_j`, de modo que `Σ w̃_i = 1`. El sorteo y el aprendizaje mueven los `w_i`; la función usa los `w̃_i`.

Los C2 que `Q5` siempre calibra (decidido 2026-11-02): para **cada** C1, los cuatro grupos `w_1, ..., w_n`, `span`, `punto_medio` y `pendiente`. En `Q4` los pesos de `N` y `A` y el `span` van fijos a mano y solo `punto_medio`/`pendiente` se ajustan contra el target sintético; esos valores quedan como punto de partida y de comparación, no como valores finales. `piso`/`techo` y las ventanas de las variables (hoy 30 días en `drawdown_30d` y `ln_razon_vol_30d`) no se calibran por ahora.

**Dimensión del problema.** `N` tiene 3 variables (2 pesos libres), `A`, `factor_B` y `LAMBDA` tienen 2 (1 peso libre cada uno), `K`, `N_EXP` y `PERDIDA_MAX` tienen 1 (peso trivialmente 1). Total: 7 parámetros × 3 (`span`, `punto_medio`, `pendiente`) + 5 pesos libres = **26 grados de libertad** por valor con la estructura actual. En general son `21 + Σ(k_c − 1)`, con `k_c` el número de variables del C1 `c`; agregar una variable suma una dimensión (§9.12).

### 9.1. Lógica de `Q5` para cada valor `v`

1. Inicializar los C2 de cada C1 (primera vuelta: valores de `Q4`; siguientes: los que entregue el aprendizaje, ver 9.5).
2. Calcular `w̃_i` para cada C1.
3. Ejecutar el backtest sobre toda la historia, actualizando los C1 con las cadencias de 9.2.
4. Al terminar el horizonte, tomar las mediciones de la vuelta y corregir los C2: **etapa de aprendizaje** (9.5).

### 9.2. Cadencias de actualización de los C1

| Grupo | C1 | Cuándo se recalcula | Por qué |
|---|---|---|---|
| (a) búsqueda de soportes | `N`, `K`, `N_EXP`, `LAMBDA` | cada `n_velas` velas H1 (`N_VELAS` en `config_smart.py`, por tipo de valor) | Son los parámetros del algoritmo de X0: al cambiarlos hay que **hacer una búsqueda nueva de soportes** antes de seguir el backtest |
| (b) operación | `A`, `factor_B` (con `B = factor_B · A`), `PERDIDA_MAX` | cada vela H1 | Están asociados directo a la ejecución de órdenes: pueden cambiar de forma continua |

Ejemplo con `N_VELAS = 168`: en la vela 168, 336, 504, ... el backtest toma los valores de `N`, `K`, `N_EXP` y `LAMBDA` que entregan sus funciones en ese instante, los lleva a la grilla (9.4) y recalcula los soportes con esos valores; entre medio, `A`, `factor_B` y `PERDIDA_MAX` cambian en cada vela. Hoy X4 recalcula los soportes por días (`delta_recalculo_soportes * 24` horas, `X4_backtester.py:1113`; 5 días en `config_x5_default.py`); `X5_RECALC_SOPORTES_CADA` de `config.py` no lo usa X4. `N_VELAS` lo reemplaza en el script nuevo, como un contador de velas.

### 9.3. Cuenta del valor: capital, lotaje y pérdida máxima

Cada valor opera con una cuenta propia que parte con **3000 USD** (hoy `X5_CAPITAL_BT = 1_000_000`, sin restricción de margen: con 3000 USD el margen sí limita). Sea `Z = cerrado + P&L abierto` del valor en ese momento.

- **Lotaje**: `lotajes_m = max(1, (Z − 6000) // 3000 + 2)`. Con `Z` = 3000 → 1; 5999 → 1; 6000 → 2; 8999 → 2; 9000 → 3; 12000 → 4. Se fija **al crear la Orden en Espera (OE)**, como en X1 (el buy limit lleva su volumen); una OE que espera conserva su `m` aunque `Z` cambie después (decidido 2026-11-03).
- **Pérdida máxima**: `perdida_max_USD = p · Z`, con `p` la fracción que entrega la función dinámica (`PERDIDA_MAX_PCT`, rango `(0.03, 0.06)` en `config_smart.py`, es decir 90-180 USD sobre los 3000 USD iniciales). Una orden abierta (OA) se cierra cuando su pérdida en USD supera ese umbral, **sin escalar por lotaje**. Ejemplo: `p = 0.04`, `cerrado = 6000`, `P&L = −1000` → `Z = 5000` → `perdida_max_USD = 200`.
- `A` y `B` siguen en USD **a lotaje mínimo**: como en X1 se escalan por `m = lote / MIN_LOTAJES` (`a_efectivo = A · m`, `b_efectivo = B · m`, `X1_trading.py:898-902`), de modo que la distancia en precio no depende del lote, y el filtro de creación de OE (`distancia_ok`) usa `MIN_LOTAJES` (`X1_trading.py:523`). X4 hoy no escala (`X4_backtester.py:477-478`, `:590`) y solo coincide con X1 cuando `m = 1`; el script nuevo lo alinea (decidido 2026-11-03).
- **`PERDIDA_MAX` realizada** en X4: `p · max(Z, 0)` por orden. X1 escala `PERDIDA_MAX` por `m` (`X1_trading.py:962-967`), así que a producción se le entregaría `p · Z / m` (`Q5-5b`); coinciden en posiciones abiertas con el `m` vigente.

`PERDIDA_MAX` en USD (`(100, 300)`) se mantiene en `config_smart.py` solo para que `X5_Q4.ipynb` siga reproducible; las funciones de `Q4` se ajustaron contra un target de percentil, así que su `punto_medio`/`pendiente` no dependen de la escala del rango.

### 9.4. Grilla de pasos permitidos

Cada C1 tiene `piso`, `techo` y `paso` en `config_smart.py` (`RANGOS_*` y `PASOS_*`, separados en crypto y acción). El valor que entrega la función se lleva al permitido más cercano, anclado en el piso: `piso + round((x − piso) / paso) · paso`.

Ejemplo: `N` en acciones con rango `(40, 180)` y paso 10 permite `[40, 50, ..., 180]`; si la función entrega 52.33, queda en 50.

Pasos por defecto (Mauricio los ajusta): `N` 10, `A` 0.5, `factor_B` 0.05, `K` 0.1, `N_EXP` 0.1, `LAMBDA` 0.05, `PERDIDA_MAX_PCT` 0.005. Cada uno cuadra exactamente con su rango. Los C2 no tienen grilla salvo `span`, que debe ser un entero de velas ≥ 1.

### 9.5. Etapa de aprendizaje

Al terminar la vuelta de un valor `v`, cada C2 es un regresor: `w̃_1^N, w̃_2^N, spanN, pmN, pendienteN, w̃^A, ...`. El resultado que aprende cada vuelta es el premio del **tramo de aprendizaje** (9.6): `Z_tongo = Z al corte / velas hasta el corte`, donde el corte es el 80% de la historia (por defecto). El tramo reservado del final no entra al aprendizaje. Se supone `Z_tongo = f(C2)`:

- **Grado 1 (por defecto, `GRADO = 1`)**: `Z_tongo = h_0 + Σ_i h_i · p_i`.
- **Grado 2 (`GRADO = 2`)**: suma los productos cruzados, por ejemplo con 3 regresores `y = h_0 + h_1 x_1 + h_2 x_2 + h_3 x_3 + h_4 x_1 x_2 + h_5 x_1 x_3 + h_6 x_2 x_3` (sin cuadrados).

Con una RLM se estiman los `h_i` y con **Gradient Ascent** se mueve levemente cada `p_i` en la dirección que sube `Z_tongo`. Mientras hay pocos registros se usa **muestreo Sobol** (secuencia casi aleatoria que cubre el espacio de los 26 C2 de forma pareja); pasado un umbral de vueltas se cambia a RLM + Gradient Ascent.

Con 26 regresores, el grado 1 tiene 27 coeficientes y el grado 2 tiene 352 (1 + 26 + 325 productos cruzados). Con el grado 2 la RLM solo es identificable con muchas vueltas o con regularización (ridge), y cada vuelta aporta una sola observación por valor. Por eso el grado por defecto es 1 y el umbral para dejar Sobol debe superar el número de coeficientes (sugerido: 32 vueltas, potencia de 2, que conserva el balance de la secuencia). Los pesos se regresan como `w̃` omitiendo uno por grupo (con `Σ w̃ = 1` el último es redundante y haría singular la regresión); tras cada paso de gradiente se proyectan de vuelta al símplex. El paso del gradiente es una fracción del rango de cada C2 y siempre se recorta a sus límites. Estos detalles se fijan en `Q5-5`.

### 9.6. Compuerta de promoción: tramo reservado

Evaluar con la misma historia con la que se aprendió sobreestima: el candidato siempre se ve bueno. Por eso el último tramo de la historia (por defecto el 20% de las velas, parámetro en `config_smart.py` cuando lo consuma `Q5-3`) **no se usa para aprender**.

- En la misma vuelta se miden dos premios: el del tramo de aprendizaje (`Z` al corte / velas hasta el corte) y el del tramo reservado (`Z_final − Z` al corte, dividido por las velas del tramo). La vuelta no se parte: los C2 y la cuenta son continuos.
- El aprendizaje (9.5) usa solo el premio del tramo de aprendizaje; el tramo reservado nunca alimenta la RLM, porque si lo hiciera dejaría de ser fuera de muestra y solo serviría para decidir si el candidato pasa.
- Ejemplo con 42.000 velas y corte en la 33.600: si `Z` al corte es 4.200, el premio de aprendizaje es 4.200 / 33.600 = 0.125. Si `Z_final` es 4.500, el premio del tramo reservado es (4.500 − 4.200) / 8.400 ≈ 0.036, y se compara con el del estático y el de `Q4` sobre esas mismas 8.400 velas.
- Un candidato se promueve solo si supera a la vuelta estática de control y a la calibración de `Q4` en el tramo reservado. Antes de pasar a producción se confirma además con velas nuevas posteriores a su elección, con aprobación manual de Mauricio (`Q5-5b`).
- La vuelta estática de control corre con las mismas reglas de cuenta (3000 USD, `lotajes_m(Z)`, `perdida_max = p · Z` con `p` fijo equivalente al estático actual; el estático de 200 USD equivale a `p ≈ 0.067`, fuera del rango `(0.03, 0.06)`, decisión pendiente de Mauricio en `Q5-3`) para que la diferencia venga solo de los C1.

### 9.7. Stop-out

La vuelta **no se corta** al hacer stop-out: sigue hasta el final "como si el valor de la cuenta fuera negativo" (decisión de Mauricio 2026-11-02). Hoy X4 hace `break` cuando `equity ≤ 0` o el nivel de margen baja de `STOP_OUT_LEVEL` (`X4_backtester.py:1199-1224`); en el modo inteligente eso se reemplaza por un evento registrado como KPI. Reglas operativas (supuesto a confirmar en `Q5-3`):

- `lotajes_m` queda acotado por el `max(1, ·)`.
- `perdida_max_USD = p · max(Z, 0)`: con `Z < 0` el umbral negativo cerraría incluso posiciones en ganancia.
- El control de margen existente de X4 sigue impidiendo abrir posiciones nuevas sin margen libre.

### 9.8. Prueba de tres niveles de agregación (pausada)

Decidido el 2026-10-21 y **pausado el 2026-11-02**: por ahora cada valor se calibra de forma independiente (un juego de C2 por valor y por parámetro). Se retoma cuando el ciclo por valor funcione (`Q5-6`). El diseño se conserva:

`Q4` calibra hoy cada parámetro **por activo** (`valor`). Antes de dar por buena esa granularidad, `Q5` debería comparar tres niveles de agregación del mismo ajuste:

| Nivel | Qué se agrupa | Juegos de parámetros por cada `P` | Riesgo |
|---|---|---|---|
| Por `valor` | Un ajuste por activo (BTCUSD, ETHUSD, TSLA, GOOGL, NVDA, AMZN, MSFT) | 7 | Sobreajuste: pocos datos por ajuste |
| Por `tipo_valor` | Un ajuste para cryptos (BTCUSD, ETHUSD) y otro para acciones (TSLA, GOOGL, NVDA, AMZN, MSFT) | 2 | Mezcla activos con dinámica distinta dentro del grupo |
| Todos agregados | Un solo ajuste para los 7 activos | 1 | Pierde la especificidad de cada activo |

Reglas de la comparación:
- Se compara el resultado económico (backtesting con `X4_backtester.py`, sin reimplementar su lógica) y también el `R²` fuera de muestra, no solo el `R²` dentro de muestra (que siempre favorece al nivel más granular).
- Los ajustes agrupados usan `s_t` ya normalizado en z-score por activo (escala comparable entre activos). Falta definir si el target `y*_t` del agrupado se normaliza por activo antes de juntar los datos, porque el rango de `N` y de los otros parámetros depende del activo.
- Con 3 o más variables explicativas la grilla de `w` crece rápido (símplex de `n-1` pesos libres); pasar a un optimizador (Nelder-Mead sobre el símplex) en vez de grilla completa.
- `K`, `N_EXP` y `LAMBDA` son globales en producción: para ellos el nivel "todos agregados" es el operativamente relevante; los otros dos niveles solo informan si vale la pena hacerlos por activo en `X0`.
- Gana el nivel más agregado cuyo resultado fuera de muestra no sea peor que el más granular (criterio de parsimonia); el desempate lo decide Mauricio.

### 9.9. Riesgos abiertos

Las decisiones que Mauricio debe tomar están en `docs/tracking/todos.md`, marcadas `[DECIDE MAURICIO]` en el ítem de `Q5` donde se necesitan.

- **Una observación por valor y vuelta contra 26 dimensiones**: el aprendizaje depende de cuántas vueltas caben; `Q5-1` mide la duración de una vuelta antes de construir nada.
- **Lote por posición**: X4 usa un solo `cfg.LOTAJES[activo]` por activo en `_paso_B`/`C`/`D`/`E`/`F`, `_calcular_estado_cuenta` y `_registrar_trade`. Con `lotajes_m(Z)` dinámico cada posición necesita su propio volumen. Decidido en `Q5-1` (2026-11-03): se fija al crear la Orden en Espera (OE). Cada OE y OA de X4 ya guarda `'lote'` (`X4_backtester.py:405`, `:441`, `:482`, `:599`), así que el cambio es leer ese campo en vez de `cfg.LOTAJES[activo]` (9 lugares), no rediseñar la estructura.
- **Intra-vela aleatoria**: `_simular_intravela` elige el bloque M1 con `random.randint` sin semilla (`X4_backtester.py:662`), así que dos vueltas con los mismos C2 dan premios distintos, lo que agrega ruido a una observación por vuelta y rompe la prueba de reproducibilidad de `Q5-3`. Se siembra por `(valor, ts)`.
- **Caché de soportes indexado por `N`** (`{VALOR}_{N}_bt.json`): con `N_t` dinámico cambia en cada recálculo y rompe el warm start (solución previa como punto de partida).
- **`μ`/`σ` de `Q4` usan todo el histórico** (look-ahead): en el backtest deben ser expanding o fijarse en un tramo inicial.
- **Premio no lineal**: `lotajes_m` sube con `Z`, así que ganar temprano compone y pesa más que ganar tarde; el premio por tramo reservado y el control estático con las mismas reglas lo hacen comparable.
- **`PERDIDA_MAX`, `A` y `B` con `m > 1`** (resuelto en `Q5-1`, 2026-11-03): X1 escala los tres por `m = orden.volume / MIN_LOTAJES` (el comentario de `config.py:234` es el correcto) y X4 no escala nada, así que solo coinciden con `m = 1`, el caso de toda la recolección de X5 (`LOTAJES_M = (1,1)`). Reglas del script nuevo en 9.3; `pars_configurables.md` corregido.
- **`N_VELAS` de acciones** (35) es un supuesto (~7 velas H1 por día × 5 días). El `Data/` local (hasta 2026-06-02) da 10 velas por día en TSLA, NVDA, AMZN y MSFT y 7 en GOOGL, así que 50 equivale a una semana; confirmar en Windows (decisión en `Q5-3`).
- **Primera búsqueda de soportes**: la ventana de X0 crece desde `FECHA_INICIAL` (`X0_data_supports.py:1151`), así que arrancar el backtest en esa misma fecha deja el cold start sin datos. Se resuelve con el inicio fijo en 2022-03-01.
- **7 procesos a la vez**: CPU y memoria (datos H1 y M1 por proceso, búsquedas de soportes simultáneas) y volumen de lo que se registra por vuelta; `Q5-1` lo mide y `Q5-3` define la retención de curvas (9.10, 9.11).

### 9.10. Registro de datos y resumen en vivo

Toda vuelta registra siempre sus datos, sin opción para apagarlo: son la materia prima del aprendizaje y de la revisión de Mauricio. Se reutiliza lo que X4 ya escribe (`trades.json`, `events.json` con los stop-out, `equity_global.csv`, `equity_activos.csv` vía `_append_equity`, checkpoint) y se agregan los archivos propios de `Q5` en `resources/x5_alt/q5/`, todos por valor:

| Archivo | Una fila por | Contenido |
|---|---|---|
| `{valor}_vueltas.csv` | vuelta | id, `version_estructura` (9.12), `semilla` de la intra-vela, `replica_de` (id de la vuelta que repite, vacío si es original; 9.13), fase (Sobol o RLM), los C2 completos (de todas las variables que alguna vez estuvieron en la estructura de cada C1), por cada C1: media, desviación estándar, mínimo, máximo, porcentaje de velas en `piso` y en `techo` y cantidad de pasos distintos de la grilla usados (9.13), promedio de cada C1, premio del tramo de aprendizaje y del reservado, KPIs (valor final de la cuenta, drawdown máximo, trades, tasa de aciertos, tiempo en mercado, margen usado, stop-outs, `lotajes_m` máximo), duración |
| `{valor}_seguimiento.csv` | resumen cada `n_velas` de cada vuelta | exactamente los datos del resumen en pantalla (ver abajo), para poder reconstruir la vuelta sin releer la consola |
| `{valor}_aprendizaje.csv` | vuelta | fase, número de filas usadas, coeficientes `h_i` de la RLM con su error estándar (o intervalo bootstrap), `R²`, error de predicción dejando una vuelta fuera (leave-one-out), número de condición, paso de gradiente y C2 propuestos para la vuelta siguiente |

La serie de C1 vela a vela se reconstruye desde los C2 y la tabla de estado de `Q1`, así que no se guarda. La curva de `equity` por vela sí se necesita (drawdown, gráficos); `Q5-3` define cuántas vueltas se conservan completas (todas, o las mejores y la estática) para no acumular cientos de MB por valor.

**Resumen en pantalla**: cada vez que termina la búsqueda de soportes (cada `n_velas`), el backtest imprime un bloque con el status de la vuelta y de la cuenta. Todas las líneas llevan el prefijo del valor y de la vuelta, porque los 7 procesos escriben a la vez en la misma consola. Ejemplo con datos ficticios:

```
[BTCUSD | vuelta 12 | bloque 37/250 | aprendizaje | 2024-03-04 08:00 | 14.8%]  ETA 1h20m
  status   : normal | margen 412% | 3 OA, 5 OE
  cuenta   : cerrado 3,210.40 | P&L abierto -85.10 | Z 3,125.30 | lotajes_m 1
  bloque   : 6 trades (4 ganados) | acumulado 212 (61%) | drawdown máx -9.8%
  C1       : N 120 | K 1.1 | N_EXP 1.6 | LAMBDA 0.20 | A 6.5 | B 3.2 | p 0.045 (umbral 140 USD)
  soportes : FO 1.2e-1 -> 1.5e-1 (convergió, 41 s)
```

- **status** = estado de la cuenta (`normal`, `margen bajo` si el nivel de margen baja de `STOP_OUT_LEVEL`, `cuenta negativa` si `Z ≤ 0`) más el avance: vuelta, bloque `i` de `total`, tramo (aprendizaje o reservado), fecha del backtest, porcentaje de velas y ETA de la vuelta.
- **cuenta** = `cerrado`, `P&L abierto`, `Z = cerrado + P&L abierto` y `lotajes_m` vigente. **bloque** = trades cerrados desde el resumen anterior y acumulados, tasa de aciertos y drawdown máximo hasta ahora. **C1** = los valores vigentes tras la grilla y los promedios de `A`, `B` y `p` del bloque, con el umbral de pérdida en USD. **soportes** = lo que ya reporta `_informar_recalculo` (FO inicial y final, convergencia, duración).
- Al cerrar la vuelta se imprime un resumen final con el premio de cada tramo y los KPIs.

Se engancha justo después de la llamada a `_recalcular_soportes` (`X4_backtester.py:1123`) y reutiliza `_calcular_estado_cuenta` para balance, equity, margen y número de OA/OE.

### 9.11. Ejecución en paralelo de los 7 valores

Los 7 valores (`VALORES`: BTCUSD, ETHUSD, TSLA, GOOGL, NVDA, AMZN, MSFT) corren a la vez, un proceso por valor (`--activo`). Un lanzador (`Q5-4`) arranca los 7, cada uno con su propio checkpoint, caché de soportes aislado (`resources/x5/bt_{ACTIVO}/` ya existe), carpeta de registro y archivo de log.

- Los valores son independientes: cada proceso hace su ciclo completo (vuelta, aprendizaje, vuelta siguiente) sin esperar a los demás, así que cada valor puede acumular un número distinto de vueltas. Si uno falla, los otros siguen y solo ese se reanuda desde su checkpoint.
- Hoy X4 solo paraleliza la búsqueda de soportes (`_recalcular_soportes` abre un `ProcessPoolExecutor` de hasta 4 workers, uno por valor). Con un proceso por valor cada uno tendría una sola tarea, pero hay que medir en `Q5-1` el uso de CPU y de memoria de los 7 procesos a la vez (cada uno carga datos H1 y M1) y definir cuántos hilos y workers usa cada uno para no sobresuscribir el equipo.

### 9.12. Cambios de estructura: agregar, quitar o cambiar variables de un C1

Decidido el 2026-11-04. Después de varias vueltas Mauricio puede decidir que un C1 use otras variables (agregar `x3` a `{x1, x2}`, quitar `x2`, o cambiar `x2` por `x3`). El sistema debe absorberlo sin tocar código ni perder el aprendizaje acumulado: la estructura de cada C1 es un dato, no está fija en el código.

**Estructura como dato.** Para cada C1 se guarda la lista de **todas las variables que alguna vez usó** (con su `μ`/`σ` congelado, su ventana y su fórmula) y cuáles están activas. El aprendizaje, el sorteo Sobol y las filas de `{valor}_vueltas.csv` trabajan sobre la lista completa, con un peso `w_i` por variable (un peso en 0 desactiva la variable, porque la función usa `w̃_i = w_i / Σ w_j`).

| Cambio | Qué se hace | Qué pasa con las vueltas anteriores |
|---|---|---|
| Agregar `x3` | Entra con `w_3 = 0`: la función es idéntica a la anterior | Siguen siendo válidas: cada vuelta vieja es la misma vuelta con `w_3 = 0`, mismo `s_t`, misma serie del C1, mismo premio. Sin ruido ni indicadora de versión |
| Quitar `x2` | Se fija `w_2 = 0` y sale de la búsqueda (se puede reactivar) | Siguen siendo válidas: están contenidas en el modelo completo |
| Cambiar `x2` por `x3` | Agregar `x3` y quitar `x2`; el Gradient Ascent mueve el peso de una a otra de forma gradual, partiendo del mejor punto anterior | Siguen siendo válidas, sin reinicio de Sobol |
| Redefinir una variable que se queda (fórmula o ventana, `piso`/`techo`, forma de la sigmoide) | Nueva `version_estructura` del C1 | Ya no son reproducibles: se usa arranque por bloques (los demás C1 congelados en su mejor valor, Sobol solo sobre los regresores del C1 afectado), las filas viejas entran a la RLM con una variable indicadora de versión y sus premios quedan como benchmark que la versión nueva debe superar |

**Límite al agregar una variable.** Las filas viejas tienen todas `w_3 = 0`, así que la RLM no puede estimar el efecto de `w̃_3` hasta que existan vueltas con `w_3 > 0`. Tras el cambio hace falta una exploración corta (Sobol solo sobre `w̃_3` y el `punto_medio`/`pendiente` de ese C1, con el resto en su mejor valor) antes de volver al Gradient Ascent. Cuántas vueltas requiere se mide, no se supone.

**Qué debe cumplir la implementación (`Q5-2`, `Q5-4`, `Q5-5`).**
- La lista de variables por C1 sale de un archivo de estructura (no de constantes del código) y es lo que construye la lista de C2, las columnas de `{valor}_vueltas.csv`, el sorteo Sobol y los regresores de la RLM.
- `{valor}_vueltas.csv` guarda los C2 de todas las variables que alguna vez estuvieron en la estructura (las no usadas en esa vuelta valen 0) y la columna `version_estructura`.
- La RLM usa solo los regresores de variables que tienen variación en las filas disponibles; una columna constante se omite.
- Una variable nueva debe existir en la tabla de estado de `Q1` para todo el histórico, con `μ`/`σ` calculados en el mismo tramo que las otras variables del C1.
- El `w̃` que aprende el sistema es evidencia para decidir cambios: un `w̃_i` cercano a 0 tras muchas vueltas indica que esa variable no aporta. La decisión de cambiar variables no se toma con el premio del tramo reservado (9.6), para que siga siendo fuera de muestra.

### 9.13. Preparación para el análisis posterior y las sugerencias de cambio de C2

Decidido el 2026-11-04. Después de varias vueltas Mauricio pedirá a Claude un análisis estadístico de lo registrado y sugerencias de cambio de los C2 (rangos de sorteo, variables, `span`, `punto_medio`, `pendiente`, pesos). Por eso `Q5` registra desde la primera vuelta lo que ese análisis necesita; reconstruir después lo que no se guardó no siempre es posible.

**Qué hay que poder responder, y con qué dato**

| Pregunta del análisis | Dato que lo permite |
|---|---|
| ¿Qué C2 mueven el premio y con qué certeza? | `h_i` con error estándar y `R²` por vuelta (`aprendizaje.csv`); error leave-one-out para saber si la RLM predice de verdad fuera de las vueltas con que se ajustó |
| ¿Una diferencia de premio entre dos vueltas es efecto o ruido? | Vueltas de réplica: mismos C2 con otra `semilla` de la intra-vela, para estimar la varianza del premio dado un C2 fijo |
| ¿Algún C1 está mal calibrado? | Porcentaje de velas en `piso`/`techo`, desviación estándar y pasos de grilla usados por C1 y vuelta: un C1 pegado al piso o al techo la mayor parte del tiempo indica `pendiente` o `punto_medio` mal puestos; uno casi constante, que su variable no se mueve |
| ¿Una variable aporta? | `w̃` aprendido por variable a lo largo de las vueltas; tendencia a 0 sugiere quitarla (9.12) |
| ¿Hay sobreajuste al tramo de aprendizaje? | Premio del tramo de aprendizaje contra el del reservado por vuelta (9.6), sin usar el reservado para decidir |
| ¿Cuándo funciona y cuándo no? | `{valor}_seguimiento.csv`: `Z`, trades, drawdown y C1 vigentes cada `n_velas` en **todas** las vueltas; la curva de `equity` completa solo en las vueltas que `Q5-3` decida conservar |
| ¿Se repite entre valores? | Los 7 valores usan las mismas columnas; la comparación entre valores sale de unir los CSV |
| ¿La búsqueda de soportes distorsionó la vuelta? | Duración de cada búsqueda y cuántas cortó el tope de 15 min (ya en `seguimiento.csv`) más su total por vuelta en `vueltas.csv`: el corte por tiempo hace que el resultado dependa de la velocidad del equipo |

**Requisitos para que el análisis sea posible**
- Los archivos de estructura de cada `version_estructura` (9.12) se guardan completos y nunca se sobrescriben (`resources/x5_alt/q5/{valor}_estructura_v{n}.json`, con las variables, sus `μ`/`σ`, ventanas y activas), para reconstruir la serie de cada C1 vela a vela desde los C2 y la tabla de estado de `Q1`.
- Cada vuelta guarda su `semilla`, y existen vueltas de réplica (al menos de la vuelta estática de control y de la mejor vuelta) para medir el ruido del premio. Sin esa estimación no se puede decir si un C2 "mejoró" o solo tuvo suerte.
- Con menos vueltas que coeficientes el análisis no es concluyente; el análisis lo declara y se limita a lo descriptivo (saturación de los C1, tendencia de `w̃`) en vez de afirmar efectos.
- Toda sugerencia de cambio de variables lleva su argumento estadístico, no se elige a priori.

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
- **Riesgos de `Q5`** (una observación por vuelta contra 26 dimensiones, lote por posición en X4, caché por `N`, look-ahead de `μ`/`σ`): viven en §9.9.
- **Buen ajuste a un target sintético no implica utilidad económica** — riesgo central de esta fase, mitigado por mantener `Q5` como gate obligatorio antes de cualquier wiring a producción.
