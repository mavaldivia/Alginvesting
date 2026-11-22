# X5 — Contexto consolidado de `X5_otros/` y `X5/`

> Fecha: 2026-11-22. Autor: Claude (Sonnet 5.5), a pedido de Mauricio, como parte de `[X5-1]`.
>
> **Para qué sirve este documento**: reunir en un solo lugar, con sus argumentos, todo lo que vale la pena saber del X5 anterior (macrobrain, X5_alt, X5_alt_v2) para **no volver a abrir `X5_otros/`**. `X5_otros/` existe solo en el Mac (615 MB, ignorado por git, sin copia en GitHub). Si algo importante no está aquí, es porque se decidió que no lo era; si se echa de menos, ver §12 (mapa de `X5_otros/`).
>
> **Documentos hermanos** (todos en `X5/`):
> - `x5_informe.pdf` (fuente `x5_informe.tex`): el informe con el diagnóstico y el plan paso a paso. Es lo que se lee primero.
> - `X5_v3.md` y `x5_v3_informe.pdf` (2026-11-21): cuestionamiento previo de X5_alt_v2. Aquí quedan **resumidos**; `X5_v3.md` conserva el detalle de métodos y números (§3 y §4 de ese archivo). Este documento lo supera cuando difieren (§4.13 lista las diferencias).
> - `docs/context/decisiones.md` (en git): bitácora de decisiones con fecha; aquí se cita por fecha.
>
> **Convención de siglas** (regla del proyecto): concepto completo primero y sigla entre paréntesis después. El glosario está en §11.

---

## 0. Estado en una página

1. **Qué es X5**: la pieza que decide, para cada activo, los parámetros con que trabajan X0 (búsqueda de soportes) y X1 (órdenes). Hoy esos parámetros son fijos en `config.py` (`N`=180, `A`=3 USD, `B`=1,5 USD, `PERDIDA_MAX`=200 USD, `K`=1, `N_EXP`=1,3, `LAMBDA`=0,2 para los 7 activos).
2. **Qué se hizo** (junio a noviembre de 2026): tres generaciones. (a) *macrobrain*: modelo de aprendizaje automático que predice el retorno de cada trade y busca parámetros que lo maximicen; (b) *X5_alt* y *X5_alt_v2*: análisis descriptivo de variables de estado (Q1–Q3), parámetros como funciones sigmoides del estado (Q4) y aprendizaje de los coeficientes de esas funciones con ventanas semanales de backtest (Q5); (c) diagnóstico del 2026-11-21: el aprendizaje no encontró señal.
3. **Qué se aprendió** (resumen; detalle en §4): el ruido de la semana domina todo; el backtest por ventanas no mide a X0 (búsqueda cortada por tiempo que entrega casi una grilla pareja); la etiqueta semanal con cuenta nueva no ve las pérdidas encadenadas; Q4 siempre perdió contra la configuración estática; la calibración de Q4 es circular; y las ventanas en barras, no en tiempo, y los parámetros en dólares, no en unidades de volatilidad, hacen que "el mismo valor" signifique cosas distintas entre activos y años.
4. **Qué decidió Mauricio el 2026-11-22**: (i) el objetivo es un **híbrido**: el retorno total de la cuenta continua es el criterio final, pero como es lento se usa la ganancia semanal pareada como filtro rápido; (ii) X5 **solo vale si hay dinamismo** (la mejor configuración estática es el piso a superar, no una meta final); (iii) el Mac queda **casi dedicado** (30 o más horas de cómputo por semana).
5. **Qué se propone**: un embudo en tres niveles, simple, que parte reparando el instrumento de medición (§ del informe). Todo lo demás depende de eso.
6. **Hallazgo nuevo de esta revisión** (no estaba en `X5_v3.md`): `scripts/X4_backtester.py` **no se puede importar hoy** (`ModuleNotFoundError: No module named 'x5_demo'`), porque importa `x5_demo` al principio y ese archivo se movió a `X5_otros/`. Rompe X4 completo, no solo el modo `--x5`. Detalle y arreglo propuesto en §9.

---

## 1. Misión y principios

### 1.1. Misión vigente

Los parámetros de primera categoría (C1) son los siete que consumen X0/X1: `N`, `A`, `factor_B` (con `B = factor_B · A`), `K`, `N_EXP`, `LAMBDA` y `PERDIDA_MAX`. La misión de X5 es que cada uno pueda ser una **función del estado del activo** y que esa función **mejore con el tiempo**, sin que X0/X1 repitan su lógica (principio "X4/X5 dependen de X0/X1, nunca duplican su lógica": ver `CLAUDE.md`).

El X5 anterior hizo explícita una jerarquía: C1 = f(C2), donde C2 son los coeficientes de una función sigmoide (`span`, `punto_medio`, `pendiente`, pesos de cada variable). Esa jerarquía se **abandona** como diseño (§4.9 y §6), pero se conserva el principio de separar *qué consume la producción* de *cómo se calcula*.

### 1.2. Principios que el proyecto ya se dio (vigentes)

De `X5_revision_exhaustiva_cerebro.md` (§19) y `x5_contexto_conversacion.md` (§20):

1. **Maximizar el sistema, no el trade**: la unidad de evaluación es la trayectoria completa de la cuenta sobre el horizonte, no una operación aislada. Puede ser óptimo cerrar antes del máximo, aceptar una ganancia menor o reducir exposición si sube el resultado acumulado.
2. **Confiabilidad antes que sofisticación**: verificar mecánica (lotaje, P&L, cierres) antes de modelos avanzados.
3. **Parsimonia y especialización**: cada parámetro depende solo de las pocas variables que tengan sentido para él (`θ_k = f_k(z_1…z_m)`), no de un estado global gigante.
4. **Evidencia antes que arquitectura** y **baseline primero**: toda sofisticación debe superar una configuración estática optimizada. *(El X5_alt_v2 invirtió este orden: fue a funciones dinámicas sin haber optimizado antes la estática. Es la raíz de varios problemas; ver §4.)*
5. **Validación fuera de muestra**, **riesgo como parte de la política**, **complejidad incremental**, **interpretabilidad**.
6. **Por activo, no por cuenta**: no usar drawdown, equity ni exposición de la cuenta agregada para explicar parámetros de un activo; "drawdown" significa drawdown del **precio** del activo. (En producción el cupo de órdenes del bróker sí acopla los activos; ver §8.)
7. **Sin fuga de información** (*leakage*: que el modelo use datos que en producción no existirían en ese instante): todo estadístico de estado se calcula con datos hasta `t` inclusive.
8. **Pre-registro**: escribir la dirección esperada de cada hipótesis y su criterio de éxito *antes* de mirar los datos.
9. **Estándar de reportes** (`docs/context/estandar_reportes_investigacion.md`, en git): lenguaje humano, cada ecuación con qué significa cada término, cada métrica con qué mide y qué límites tiene, y siempre separar resultado observado, hipótesis, evidencia estadística e incertidumbre.

### 1.3. Preguntas rectoras (de la revisión exhaustiva)

- Para cada pieza: ¿ayuda a maximizar la ganancia acumulada **ajustada por riesgo** a través del tiempo, o solo agrega complejidad?
- Para cada parámetro: ¿cuál es el conjunto **mínimo** de variables que hay que conocer para fijar razonablemente su valor óptimo ahora?

### 1.4. Decisiones de Mauricio del 2026-11-22

| Pregunta (de la revisión Opus del 2026-10-23, sin responder hasta hoy) | Respuesta |
|---|---|
| ¿Qué maximizar? | "Me encantaría la cuenta continua (retorno total) pero es muy lento; ideal un híbrido entre la ganancia pareada con tope de riesgo y el retorno total." |
| ¿Se acepta "mejor estática + tope de Órdenes Abiertas" como resultado final? | **No**: X5 solo vale si hay dinamismo. |
| ¿Cuánto cómputo? | Mac casi dedicado, 30 o más horas por semana. |

Interpretación operativa (a confirmar al revisar el informe): el nivel final de decisión es el **retorno total de la cuenta continua** con riesgo acotado; los niveles previos usan la ganancia semanal pareada como *filtro* barato. La mejor estática es el **rival a vencer**, no la meta.

---

## 2. La mecánica que X5 manipula

### 2.1. Soportes (X0)

Para cada vela `i` se calcula el aislamiento hacia la izquierda y la derecha (cuánto tarda otra vela en "contener" su `Low`/`High`). Cada vela tiene un puntaje `z = y · w · h_dist · v · f`:

- `y = Low_left + High_left + K·(Low_right + High_right)` (aislamiento; `K` pesa el futuro frente al pasado).
- `w = t^N_EXP`, con `t ∈ [0,1]` el tiempo normalizado sobre la ventana de historia (recencia; **ojo**: como la historia crece desde `FECHA_INICIAL`=2022-01-01, el peso efectivo de una vela de hace un año cambia con el tiempo aunque `N_EXP` sea fijo: era 0,41 a inicios de 2024 y hoy 0,74).
- `h_dist = 1 − dist²/dist_max` (proximidad al soporte asignado), `v` volumen de ticks normalizado, `f = 1 − |Close−Open|/(High−Low)` (fuerza del rechazo).
- Función objetivo `FO = mean(z) − LAMBDA · cv(H_n)`, con `cv(H_n)` el coeficiente de variación de las distancias entre soportes consecutivos (incluye el mínimo y el máximo del período como anclas).
- El optimizador `nuevo_optimizador_2` mueve cada soporte con candidatos locales (`M`=30 entre vecinos), un ajuste cuadrático si la curva es una U invertida, y un salto global (`M_SALTO`=60). Las Órdenes Abiertas (OA) son soportes fijos que entran a la FO. En producción corre en bloques de 15 min (`T_UPDATE_O0`) dentro de ciclos de 60 min (`T_UPDATE_CICLO_X0`) con arranque desde la solución anterior (*warm start*). En backtest corre hasta converger o hasta el tope de tiempo (`X4_TIEMPO_MAX_BUSQUEDA_SOPORTES_MIN`=6 min; las ventanas de X5_alt_v2 usaron 10 min).

### 2.2. Órdenes (X1)

Progresión `O0* > OE > OA > OC` (el asterisco marca que O0 es opcional):

- **O0**: soporte aún por encima de `precio − margen`; todavía no se coloca.
- **OE** (Orden en Espera): buy limit colocada en un soporte.
- **OA** (Orden Abierta): la OE se ejecutó; posición activa.
- **OC** (Orden Cerrada): cerró por trailing stop, `PERDIDA_MAX` o stop loss.

Parámetros de operación, con la fórmula exacta de `X1_trading.py`:

| Parámetro | Dónde actúa | Fórmula | Valor hoy |
|---|---|---|---|
| `A` (USD) | (1) crear OE: `crear_ordenes_espera` | un soporte `Pi` recibe buy limit solo si `(P0 − Pi)·L ≥ A`, con `L = MIN_LOTAJES·UNITS` (lote **mínimo**, no el configurado) | 3 |
| | (2) primer stop ganador: `trailing_stop` | mientras la posición no tiene SL, se le pone el primero cuando `(P0 − Pi)·L_real ≥ A·m` | |
| `B` (USD) | `trailing_stop` | con SL activo: `sl_nuevo = P0 − B·m/L_real`; el SL solo sube | 1,5 (`factor_B` = B/A = 0,5) |
| `PERDIDA_MAX` (USD) | `controlar_perdida_max` | cierre a mercado si `(Pi − P0)·L_real > PERDIDA_MAX·m` | 200 |
| `LOTAJES_M` | tamaño | `LOTAJES = LOTAJES_M · MIN_LOTAJES` | 1 (la prueba de Q5-5b lo bajó de 2 a 1) |
| `N` | cantidad de soportes que X1 mantiene | | 180 |

`m = orden.volume / MIN_LOTAJES` (corregido el 2026-11-03; antes `A`, `B` y `PERDIDA_MAX` no escalaban con el lote real). Consecuencia: con el escalado, los tres equivalen a una **distancia de precio fija**: `A / (MIN_LOTAJES·UNITS)`. `MIN_LOTAJES` es 0,01 (BTCUSD, acciones) o 0,1 (ETHUSD); `UNITS` es 1 en cripto y 100 en acciones.

Ejemplo: BTCUSD, `A`=3 USD → distancia de precio 3/0,01 = **300 USD** para crear una OE o activar el primer SL. `PERDIDA_MAX`=200 → 20.000 USD de caída de precio. TSLA: `L = 0,01·100 = 1` → `A` = 3 USD de precio, `PERDIDA_MAX` = 200 USD de precio (≈50 % de un precio de 400).

`A` tiene **dos roles** que pueden empujar en direcciones distintas (`A_OE`: densidad de entradas; `A_TRAILING`: cuánto se espera antes de proteger). Hoy usan la misma distancia. Pendiente desde el 2026-09 si dividirlos.

### 2.3. Backtester (X4)

`scripts/X4_backtester.py` (en git) simula X0+X1 vela a vela con intra-vela de minuto (`Data_minuto/`), reutilizando `_procesar_valor_N`/`_bt_warm_start` de X0. Piezas que X5 usó y que siguen en git: `_cargar_datos_h1/m1`, `_recalcular_soportes(estado, ts, cfg, x5_mode)`, `_procesar_candle(...)`, `_append_equity(...)`, `_flush_json_list`, `_paso_B/D/E/F` (llenado, cierre por trailing, cierre por pérdida máxima, creación/cancelación de OE; `_paso_F` aplica el tope de OA si `cfg.R_TOPE_OA`), semillas deterministas por `(semilla, valor, ts)` (`SEMILLA_INTRAVELA`, `SEMILLA_BUSQUEDA`) y tope de tiempo `cfg.TIEMPO_MAX_BUSQUEDA_MIN`. **No modela spread, swap ni comisión** (el buy limit se llena cuando el `Low` toca el precio, y las velas de MT5 son de Bid).

### 2.4. Cuenta y riesgo definidos en Q5 (se conservan como reglas de trabajo)

- Cuenta por valor de 3.000 USD; `Z = cerrado + P&L abierto`.
- **Tope de Órdenes Abiertas**: cupo `floor(R_TOPE_OA · Z / umbral)` con `R_TOPE_OA = 0,5` y `umbral = p · 3000 · m`. Con las OA en el cupo, X4 cancela las OE y no crea nuevas; no cierra OA. Una vela que cae a través de varios soportes puede llenar más OE que el cupo. Ejemplo: umbral 132 USD → `Z=3000`: 11; `Z=1759`: 6; `Z<264`: 0 (no se opera). Motivo: en el bloque 9 de BTCUSD (2022-05-03) había 45 OA con umbral 81 USD (3.645 USD posibles contra `Z` = 1.759).
- `lotajes_m(Z) = max(1, (Z−6000)//3000 + 2)`: **se descartó** en las ventanas (se validó con `m=1`).
- Stop-out (nivel de margen ≤ 50 o `equity ≤ 0`): **no corta** la corrida; se registra un evento y se sigue "como si la cuenta fuera negativa".
- `p` (fracción de la cuenta) reemplaza a `PERDIDA_MAX` en USD: `umbral = p · 3000 · m`. La estática equivale a `p = 200/3000 = 0,067` (`P_ESTATICO`).

---

## 3. Historia en cinco etapas

| Etapa | Fechas | Qué intentó | Qué se construyó | Resultado | Por qué se detuvo |
|---|---|---|---|---|---|
| **1. macrobrain** (X5 original) | 2026-06-26 → 2026-09-12 | Un modelo que, dado el contexto (X2, X3, parámetros activos, estado de OA), predice el retorno de un trade; en inferencia busca los parámetros que lo maximicen. Primero dos módulos (X5 predice, X6 ajusta), fusionados el 2026-06-26. | `X5_macro_brain.py` (~1.660 líneas): LightGBM (500–5.000 trades cerrados) y FT-Transformer (>5.000), 3 objetivos (retorno, P&L flotante, P&L cerrado) y luego `retorno_acumulado_dia`; búsqueda con Optuna/ascenso de gradiente; "airbag" duro; recolección paralela por activo con `X4 --x5` (explorar/explotar cada 5 días simulados); store `resources/x5/{ACTIVO}_store.csv`. | Store de BTCUSD con 10.169 filas. Modelo **nunca validado económicamente**. Análisis exploratorio: `A` tenía alto efecto en retorno **por trade**, pero el objetivo real es retorno **acumulado** (el efecto cambió de `N_EXP` a `LAMBDA` al medir por tramos). | Demasiado complejo para iterar con confianza (decisión de crear X5_alt, 2026-09-12). Con 5.426 trades cerrados solo se formaban 194 tramos de parámetros. |
| **2. X5_alt v1** | 2026-09-12 → 2026-10-10 | Entender los datos antes de modelar: una tabla continua (una fila por vela H1) con precio + técnicos + fundamentales, y su relación con el precio. | `X5_P1.ipynb` (tabla maestra, 40.283 filas × 37 columnas BTCUSD), `X5_P2.ipynb` (variable vs precio, ceteris paribus, VIF). | Todo contra el **nivel** de `Close`: correlaciones "fuertes" que eran artefacto de tendencia compartida. | Se rediseñó el enfoque: lo que importa es qué **estado** hace conveniente qué configuración. |
| **3. X5_alt_v2: Q1–Q3** | 2026-10-10 → 2026-10-12 | Variables de estado del activo (Q1), core descriptivo (Q2) e hipótesis parámetro↔variable (Q3), siempre por activo. | `X5_Q1.ipynb` (72 columnas), `X5_Q2.ipynb` (63 variables contra 2 objetivos = 126 pares por activo, en 6 activos; 21 archivos por activo), `X5_Q3.ipynb` (tabla final). | Ver §4.1. | Cerrados; Q3 dejó hipótesis, no evidencia. |
| **4. X5_alt_v2: Q4** | 2026-10-15 → 2026-11-02 | Convertir cada hipótesis en una función `P̂_t = piso + (techo−piso)/(1+exp(−pendiente·(s_t−punto_medio)))` calibrada contra un objetivo sintético (percentil causal del propio índice). | `x5_alt_funciones.py`, `config_smart.py`, `X5_Q4.ipynb` (97 celdas, 7 parámetros × 7 activos), `funciones_pars_dinamicos.pdf`. | R² de 0,63–0,99 y signo correcto en 49/49 pares: **por construcción**, no por evidencia (§4.2). | Cerrada como "parametrización"; la validación económica se pasó a Q5. |
| **5. X5_alt_v2: Q5** | 2026-11-02 → 2026-11-21 | Aprender los C2 con backtests: primero vueltas completas (40–55 h cada una), luego **ventanas semanales** con cuenta nueva. Regresión Lineal Múltiple (RLM) de `Y` sobre los C2 + paso de ascenso de gradiente; compuerta por mediana contra la estática y contra Q4; publicador a X0/X1 solo en demo. | `X4S_backtesting_inteligente.py`, `X4_bckt_ventanas.py`, `x5_alt_aprendizaje.py`, `publicador_c1.py`, `params_din.py`, `registro_din.py`, 96 pruebas. 320 ventanas en BTCUSD y 306 en TSLA (627 conjuntos de soportes guardados). | Los C2 no explican `Y` por sobre el mercado de la semana; Q4 pierde contra la estática 5 de 5 años; la candidata de BTCUSD pasó la compuerta "por poco" (mediana +14,2 USD, media −34,1 USD) y la de TSLA no. | Mauricio concluyó que "la metodología no va por buen camino" (2026-11-21). |
| **6. X5_v3 y reinicio** | 2026-11-21 → hoy | Cuestionar Q5 y empezar de cero. | `X5/X5_v3.md` + informe; todo el X5 anterior a `X5_otros/`; X0/X1/`config.py` revertidos a antes de `Q5-5b`. | Propuesta "medir bien, después aprender". | Este informe la refina con las decisiones del 2026-11-22. |

Contexto cronológico adicional que conviene recordar:

- 2026-10-23: segunda revisión independiente (Opus, `x5_alt_v2_opus.tex`, 11 páginas) con hallazgos que `X5_v3.md` **no** recoge casi todos; están en §4.2 a §4.5 y §4.10.
- 2026-11-06: medición en Mac (BTCUSD, `N`=180 fijo): una vuelta completa tomó ~56 h de reloj (cota superior: incluía suspensiones del Mac); 245 búsquedas semanales de ~13,8 min en promedio, casi el tope de 15 min de entonces. 32 vueltas habrían sido ~75 días por valor. De ahí las ventanas.
- 2026-11-14: se comprobó que el Mac se suspende y que las duraciones medidas contaban la suspensión (usar siempre `caffeinate -i`).

---

## 4. Hallazgos (con cifras)

Cifras de ventanas: el análisis de `X5_v3.md` usó 287 ventanas de BTCUSD y 273 de TSLA; hoy hay **320 y 306** (los procesos siguieron corriendo hasta el 2026-11-21 23:06; hoy no hay ninguno activo). Las conclusiones no cambian; los conteos de abajo son los de hoy cuando se indica "hoy".

### 4.1. Evidencia descriptiva (Q2): el nivel engaña y lo que sobrevive es mecánico

- Contra el **nivel** de `Close`, `drawdown_historico`, `fundamental_edad` y `x3_atr_14` salían con Pearson 0,67–0,87; contra el **retorno** de la hora, |Pearson| < 0,01. Es tendencia compartida, no relación.
- Ranking contra `retorno_log_1h` (BTCUSD): 19 de 54 variables con evidencia "alta" (todas "alta" estables entre años y regímenes); casi todas son distancia/posición a medias móviles (`x3_ema_dist_12` 0,53, `ruptura_rango`, `x3_bb_pos`…) más `x3_drawdown_20/50`, `x3_macd_hist`. **Esa evidencia es mecánica**: es la correlación con el retorno *de la misma vela*, que la variable ya contiene. Con el retorno de la vela siguiente cae a cero (revisión Opus, 2026-10-23; p. ej. `ruptura_rango`: 0,4996 con la misma hora contra 0,0 con la siguiente).
- Estabilidad: de 108 pares variable/target en BTCUSD, 55 estables, 3 inestables y **50 con cambio de signo entre años**. Con ventanas móviles de coseno de 30/90/180 días, 12 de 108 dependen de la ventana elegida.
- Redundancia: 46 pares con |Pearson| > 0,85, todos técnico-técnico; ceteris paribus: 29 de 54 variables con VIF > 10 (R² 0,970 contra `Close`, 0,705 contra `retorno_log_1h`).
- Información mutua y correlación de distancia (Székely–Rizzo): varias variables de volatilidad/volumen tienen `distance_corr` 0,17–0,34 con Pearson casi nulo, o sea dependencia no lineal real (`x3_vol_24h`, `x3_atr_pct`, `tick_volume_z`, `x3_bb_width`…).
- Fundamentales: `x2_history.json` solo cubre 2026-06-12 a 2026-09-21; cero actualizaciones reales en el histórico 2022–2026, así que `x2_score` es `NaN` en toda la tabla. **No hay fundamentales usables hacia atrás** (usarlos metería *look-ahead*). Solo `fear_greed` (alternative.me, historial diario) sería reconstruible, sin verificar.
- El coseno sin centrar no agrega información: contra el retorno equivale a Pearson atenuado por la media de la variable.

### 4.2. Q4 no puede fallar (la calibración es circular)

El objetivo es el percentil causal del propio índice, así que cualquier variable da un buen ajuste: el indicador de fuerza relativa (RSI) da R² = 0,98 y el ruido puro 0,998; invertir la hipótesis de `N` da exactamente el mismo R² y el mismo signo "correcto". Q4 aporta una **parametrización**, no una calibración. Además, las constantes (`μ`, `σ`, punto medio, pendiente) se ajustaron con todo el historial (información futura): si se ajusta solo con la primera mitad, `N̂` cambia en la segunda entre 6 y 14 soportes en promedio (p90 hasta 19).

### 4.3. El `N` dinámico es, sobre todo, un `N` más bajo

El percentil reparte el tiempo parejo entre piso y techo, así que `N̂` vive cerca del centro del rango: promedio 117–135 contra 180 fijos, **bajo 180 el 95–100 % del tiempo**. En acciones, 180 *es* el techo. Comparar dinámico contra estático mide nivel, no dinamismo. Necesita un control **igualado** (`N` fijo ≈ promedio de `N̂`). Cambios por día (redondeo a múltiplos de 10): 0,4–1,5.

### 4.4. El mecanismo económico de `N` es de riesgo, no de retorno

Por quintiles del índice de `N` (promedio de los 7 activos): retorno de los 7 días siguientes +2,65 % (estado adverso) contra +2,29 % (sano), o sea no empeora; la caída máxima de esos 7 días (MAE, *Maximum Adverse Excursion*) pasa de −5,73 % (sano) a −8,64 % (adverso), en los 7 activos sin excepción. En cripto el retorno a 30 días sí es peor en estado adverso (BTC −0,5 % contra +3,7 %); en varias acciones es mejor (TSLA +14,4 % contra −6,1 %). Conclusión: reducir `N` en estados adversos es **gestión de riesgo** y con "retorno total sin drawdown" se descartaría por la vara equivocada. Referencia: Moreira y Muir (2017), *Volatility-Managed Portfolios*.

### 4.5. Unidades: ventanas en barras y parámetros en dólares

- Todas las ventanas (Q1/X3) están en **número de velas** suponiendo 24 por día. En cripto es cierto; en acciones no: TSLA, NVDA, AMZN y MSFT tienen 10 velas H1 por día con datos y GOOGL 7 (sesión distinta en el bróker). "30 días" = 720 velas = 72 días de mercado (103 en GOOGL); "7 días" = 168 velas = 17 (24 en GOOGL); `span`=12 = 1,2 días. La anualización `√8760` no corresponde en acciones. Esto probablemente explica la anomalía de TSLA en el análisis de `N` (`falso_sano` ≈ 0,48 con cualquier ventana). **No es una corrección de una línea**: están hardcodeadas en `x5_alt_variables.py` (720, 168, 2160, 8760) y en `config.X3_VENTANAS`.
- `A`, `B` y `PERDIDA_MAX` están en dólares. Medidos como distancia de precio y en unidades de ATR (*Average True Range*, promedio del rango verdadero de una vela H1):

| Activo | Precio mediano (365 d) | `A` en ATR | `B` en ATR | `PERDIDA_MAX` como % del precio | ¿Se habría activado en 2022–2026? |
|---|---|---|---|---|---|
| BTCUSD | 77.303 | 0,64 | 0,32 | 25,9 % | sí |
| ETHUSD | 2.320 | 1,59 | 0,79 | 86,2 % | sí |
| TSLA | 399 | 0,73 | 0,37 | 50,1 % | sí |
| GOOGL | 335 | 1,14 | 0,57 | 59,6 % | **no** |
| NVDA | 197 | 1,69 | 0,85 | 101,5 % | **no** |
| AMZN | 243 | 1,69 | 0,85 | 82,5 % | **no** |
| MSFT | 448 | 0,99 | 0,50 | 44,6 % | por poco |

  Además "el mismo `A`" cambia con el tiempo: en BTCUSD pedía 1,9 ATR en 2023 y 0,5 ATR en 2025; en NVDA 11,4 ATR en 2022 y 1,7 ATR en 2026. Es decir, **el valor estático ya se mueve con el precio** y en sentido contrario al de la hipótesis. `PERDIDA_MAX` en GOOGL/NVDA/AMZN no actúa nunca: esas posiciones operan sin stop de pérdida efectivo.
- Propuesta de Opus que sigue vigente: expresar `A` y `B` como múltiplos de volatilidad, `A_t = k_A · ATR_t · L_min` y `B_t = k_B · ATR_t · L_min` (con `factor_B = k_B/k_A`). Eso **ya es** la hipótesis "volatilidad alta → `A` alto" con un solo número, sin sigmoide ni percentil. Para separar `A_OE` de `A_TRAILING`, dos multiplicadores (`k_OE`, `k_TS`).

### 4.6. La configuración actual gana poco y seguido, y pierde mucho y rara vez

En BTCUSD (lote real 0,02 BTC): la ganancia mínima asegurada es ≈3 USD por posición (el SL queda 150 USD bajo el precio cuando el precio sube 300) y la pérdida máxima 400 USD: **una pérdida borra ~130 ganancias mínimas**. El dinero **cerrado** se ve suave y creciente mientras las pérdidas se acumulan como flotante en posiciones abiertas. Hay que medir sobre el **valor de mercado** de la cuenta (cerrado + flotante), con drawdown, mayor pérdida flotante y capital comprometido máximo.

### 4.7. El ruido de la semana domina (y por qué conviene parear)

- R² de validación cruzada de `Y ~ ret_medio + ret_vol`: 0,14 (BTCUSD), 0,13 (TSLA). Con el número de trades sube a 0,60 / 0,45. Dos configuraciones en la misma semana se parecen mucho: correlación de `Y` candidata–Q4 0,94 / 0,97; Q4–estática 0,72 / 0,60; candidata–estática 0,60 / 0,81. Lo común de las semanas es **el camino completo del precio**, no dos números resumen.
- Ganancia de varianza al comparar en la misma semana (var de `Y` / var de la diferencia): candidata−Q4 5,7× / 16,8×; Q4−estática 2,0× / 1,5×; candidata−estática 1,5× / 2,9×.
- Potencia (80 %, 5 %): con σ de la diferencia Q4−estática de 309 USD (BTCUSD) y 75 USD (TSLA), detectar δ = 25 USD/semana exige ~1.199 semanas pareadas (BTCUSD) y 71 (TSLA); δ = 50 USD: 300 y 18. La historia entera tiene ~240 semanas.
- Colas pesadas: curtosis en exceso 26,3 (BTCUSD) y 8,0 (TSLA); el 5 % de semanas con mayor `Y` aporta el 60 % / 47 % de la suma. Una semana (2025-01-17) dio +2.653 USD a la estática sobre una mediana de 152. La media muestral de 26 semanas es casi lotería; por eso la compuerta pasó a mediana (2026-11-19), pero la RLM seguía ajustando por mínimos cuadrados, el estadístico que esas semanas dominan.
- `ret_medio`/`ret_vol` se miden *después* de `t*`: no existen en producción al elegir los C1.

### 4.8. El backtest por ventanas no prueba a X0

Cada ventana dura 10,0 min: 600 s de búsqueda de soportes en frío y ~2 s de la semana operada (**99,7 % del cómputo en la búsqueda**). La búsqueda es cortada por el tope en el 99,7 % (BTCUSD hoy) y el 92,5 % (TSLA) de las ventanas, y converge ~0–1 %. El resultado es casi una **grilla pareja**: coeficiente de variación de las distancias entre soportes consecutivos 0,041 (BTCUSD; p10–p90 0,017–0,068) y 0,025 (TSLA) contra **0,14–0,31** en los soportes de producción (AMZN 0,237, BTCUSD 0,222, ETHUSD 0,142, GOOGL 0,234, NVDA 0,314, TSLA 0,253). Ejemplo: en BTCUSD `N`=170 las primeras distancias son 1.222,5; 1.223,1… USD. `FO_final` mediana −0,0066: la penalización `LAMBDA·cv` domina a `mean(z)` y con arranque en frío (`X5_WARM_START_SOPORTES = False`) y tope de 10 min el optimizador gasta su presupuesto igualando distancias. Matiz: los archivos de producción son de una versión de X0 anterior a los saltos del 2026-11-03; la diferencia (5–10×) parece demasiado grande para atribuirla a eso, pero falta confirmarlo. Correlación de rangos entre uniformidad de la grilla y parámetros de búsqueda: `K` 0,03, `LAMBDA` −0,07, `N` 0,49 (`N` fija el paso). Y la búsqueda se repite para cada configuración aunque `A`, `factor_B` y `p` **no la afectan** (con cuenta nueva no hay OA en `t*`, así que los soportes dependen solo de `t*`, `N`, `K`, `N_EXP`, `LAMBDA`, semilla y tiempo).

### 4.9. Aprendizaje: instrumento débil, signos que se cancelan, saturación

- **C2 contra `Y`**: R² con solo los controles de mercado +0,096 (TSLA) / +0,159 (BTCUSD); con los 26 C2 + controles +0,004 / +0,090; prueba de permutación (barajar filas de C2) p = 0,93 / 0,66. El mismo resultado con 7 C1 en vez de 26 C2, con `Y` recortado y con `Y` en rangos. En fase `rlm`, R² fuera de pliegue 0,10–0,20 (BTCUSD, últimas 15 corridas), −0,16 a +0,01 (TSLA).
- **Instrumento débil**: R² lineal de cada C1 contra sus propios C2 entre 0,08 y 0,70 (p. ej. `N` 0,18/0,13; `A` 0,17/0,08; `K` 0,43/0,70; `LAMBDA` 0,27/0,51). Entre 57 % y 92 % de la variación de los C1 la pone el estado del activo, no el sorteo. Regresar `Y` sobre los C1 observados no sirve (confusión: el estado mueve a los C1 y a `Y`). **La salida es de diseño: aleatorizar los C1 directamente dentro del mismo `t*`.**
- **Derivadas que cambian de signo**: `∂C1/∂pendiente ∝ (s − punto_medio)` y `∂C1/∂w̃_i ∝ (z_i − z_j)`: un modelo lineal en C2 estima el promedio de efectos de signo opuesto. Fracción de ventanas con el C1 sobre el centro de su rango (BTCUSD): `N` 0,75; `K` 0,64; `N_EXP` 0,68; `LAMBDA` 0,31; `A` 0,27; `factor_B` 0,42; `p` 0,46.
- **Saturación**: pendientes medianas de 8–12 en unidades de z (`c2_K_pendiente` 8,1 en BTCUSD, 9,4 en TSLA): `K` es un interruptor; 63 % de las ventanas de BTCUSD tienen `K` en el 10 % extremo de su rango (`σ'(u)≈0`).
- **El ascenso de gradiente camina haya señal o no**: se normaliza por el efecto máximo (el C2 de mayor efecto se mueve siempre 10 % de su rango). La penalización ridge elegida por validación cruzada queda en el tope (1.000) en 27 de las primeras 40 propuestas de BTCUSD y 64 % de TSLA: el modelo dice "no hay señal" y el paso es completo igual. En TSLA deriva a las esquinas (`c2_N_pendiente` en su mínimo 0,92, `c2_K_pendiente` en su máximo 9,42).
- **Sin exploración después de Sobol**: pasada la fase de 32 ventanas, la dispersión de los C2 cae (0,29 Sobol → 0,23 BTCUSD y 0,17 TSLA en `rlm`): más datos con menos variación en los regresores.
- **Signos impuestos**: el sorteo de pendiente va entre Q4/2 y Q4·2 (nunca cruza 0) y los pesos tienen piso 0,05; el aprendizaje no puede descubrir que una dirección estaba al revés (que además viene de Q3, con evidencia mecánica).
- **Forma sobreparametrizada**: sin `span`, `piso + (techo−piso)·σ(pendiente·(Σ w̃_i z_i − punto_medio))` ≡ `piso + (techo−piso)·σ(a + Σ b_i z_i)`; los mismos k+1 números, sin símplex ni acople. `span` sobra para `N`, `K`, `N_EXP`, `LAMBDA`.
- **El parámetro que sí mueve algo** (correlación de rangos del residuo de `Y` tras restar el mercado con cada C1 realizado, ventanas de aprendizaje): `p` en BTCUSD ρ = −0,22 (p = 0,004; probablemente efecto de exposición: `cupo = floor(0,5·Z/(p·3000))`, con `p`=0,067 el cupo es 7 y con 0,042 es 11); `A` en TSLA ρ = −0,16 (p = 0,04) y `B` −0,17 (p = 0,03). `N`, `K`, `N_EXP`, `LAMBDA`: sin señal, pero con la búsqueda cortada en el 100 % de las ventanas eso prueba que hoy **no se pueden medir**, no que no importen. `A` contra número de trades ρ = −0,32 (BTCUSD), −0,64 (TSLA). Por cuartiles de `A` en TSLA: `A` 2,3 → residuo +19,9 y 20,1 trades; 15,3 → −12,6 y 2,3 trades.

### 4.10. Q4 contra la estática y la "meseta" de `A`

- En ventanas reservadas Q4 pierde contra la estática en **33 de 44** `t*` (BTCUSD) y **36 de 47** (TSLA), p < 0,001; hoy BTCUSD tiene 50 y TSLA 51 pares: estática media 146,5 / 53,1 USD, Q4 52,9 / 3,6; candidata BTCUSD 187,2 (26 `t*`), TSLA 8,5 (24). Por año (suma de `Y` en `t*` reservados) la estática gana a Q4 en 10 de 10 año-valor (BTCUSD 2022: −174 contra −771 … 2025: 4.724 contra 2.740; TSLA 2022: 504 contra −294 … 2025: 911 contra 235). En BTCUSD, 2025 concentra el 77 % de lo que gana la estática.
- Niveles medios de los C1: estática `N`=180, `K`=1,0, `N_EXP`=1,3, `LAMBDA`=0,20, `A`=3,0, `factor_B`=0,50, `p`=0,067; Q4 BTCUSD 144 / 1,25 / 1,74 / 0,27 / 8,8 / 0,43 / 0,048; candidata BTCUSD 169 / 1,84 / 2,32 / 0,20 / 6,0 / 0,41 / 0,042; Q4 TSLA 127 / 1,24 / 1,75 / 0,27 / 7,5 / 0,46 / 0,047; candidata TSLA 133 / 0,60 / 1,40 / 0,28 / 7,7 / 0,35 / 0,048.
- **Lectura**: el aprendizaje de BTCUSD partió de Q4 (`A`=8,8) y caminó hacia la estática (`A`=6,0; la estática usa 3,0): gastó ~130 ventanas (~22 h) redescubriendo, a medias, que **`A` bajo opera más** y que la ventana semanal premia la rotación (en el análisis del 2026-11-19: todos los trades cerrados ganan; las pérdidas solo aparecen como P&L abierto). La estática de BTCUSD promedia +145 USD/semana (mediana 63) sobre 3.000 USD: ~250 % anual si fuera cierto; **nadie verificó** que una cuenta continua con la estática se acerque a eso.
- Para `A`: el valor estático (3 USD) está pegado al piso del rango (2–20 USD); en TSLA el mejor cuartil de `A` también está en el piso. Hay que bajar el piso por debajo de 2.

### 4.11. La ventana semanal con cuenta nueva ve la mitad buena

| | Ventanas semanales BTCUSD | Vuelta continua `q4_s0`/`q4_s0_v2` (configuración Q4) |
|---|---|---|
| Trades cerrados ganadores | 98,8 % (mediana 100 %) | 72,9 % |
| Cierres por pérdida máxima | ~1 % | 27 % (233 de 870: −30,5 USD promedio, −7.117 USD total; contra 637 por trailing: +6,5 USD promedio, +4.166 total) |
| Resultado | `Y` medio +68 USD/semana | 3.000 → 4.581 (2022-04-05) → **396** (2022-05-10) → 46 USD (2022-09-27), sin operar después |

Contexto: la vuelta continua corrió antes de `Q5-3b` (umbral que se achicaba con la cuenta, sin tope de OA) y hay una espiral documentada (65 cierres por pérdida máxima en una semana de mayo de 2022). El tope `r`=0,5 la limita, no la elimina. El riesgo de esta estrategia vive en **secuencias de semanas** (pérdidas correlacionadas que ocupan el cupo); una ventana con cuenta nueva cada semana no las ve. Además la semana **trunca el ciclo de las órdenes**: las OE sin llenar dan `Y`=0 (3 de 24 ventanas iniciales de BTCUSD, con el precio en mínimos históricos) y las OA se valoran a mercado sin cerrar su trailing.

### 4.12. Costos de transacción: no modelados

Con la columna `Spread` de `Data/` (punto 0,01, lote mínimo): costo medio por trade 0,14 USD (BTCUSD) / 0,08 (TSLA); por ventana 6,0 / 1,0 USD; 9 % / 4 % de la suma de `Y`. No cambia ninguna conclusión de la comparación estática/Q4/candidata. El **swap** (financiamiento nocturno de CFD) puede pesar más en posiciones que quedan semanas abiertas y no está estimado (se puede medir con los deals de MT5 que registra `registro_din.py`, `x1_realizado`).

### 4.13. Diferencias entre este documento y `X5_v3.md`

1. Conteos de ventanas actualizados (320/306 en vez de 287/273).
2. Se incorporan 9 hallazgos de la revisión del 2026-10-23 que `X5_v3.md` no usó (§4.2, 4.3, 4.4, 4.5, 4.6 y el diseño de máscara de `N` de §6.3).
3. Se registran las decisiones del 2026-11-22 (§1.4).
4. Se descubre el X4 roto (§9) y la instrucción de relanzamiento incompleta de `decisiones.md` (falta la ruta de `x5_demo`).
5. `X5_v3.md` §8–§9 queda como **propuesta previa**; el plan vigente es el del informe nuevo.

### 4.14. Lecciones del macrobrain (qué no repetir)

- Un modelo grande sobre pocas filas: 5.426 trades cerrados → 194 tramos de parámetros; ni el FT-Transformer ni LightGBM llegaron a validarse económicamente.
- **P contra P×Q**: un `A` alto gana en retorno promedio por trade y pierde en cuántas veces cierra; el objetivo es el acumulado en el tiempo. El target correcto fue `Δ(P&L cerrado + P&L flotante)` por tramo de parámetros, no la suma de `retorno_usd` por tramo de cierre (una OA abierta en el tramo T se evalúa con el `A`/`B` **actual** en cada vela, no con el vigente al abrir; sumar por cierre da crédito de más).
- El store aleatorizado explora parámetros pero nunca fue pareado: el sesgo de selección se citó (`x5_plan.md`, sugerencia 1) y no se resolvió; en Q5 se resolvió con el **control pareado** (misma semana, misma semilla), que es la mejor idea estadística heredada (§5).
- Bugs reales que costaron días y que el motor nuevo debe evitar: (a) los soportes ignoraban los parámetros explorados y heredaban el caché entre ciclos; (b) el recálculo no se disparaba en acciones porque exigía la hora 23 UTC y las velas de acciones solo cubren su sesión; (c) las operaciones resueltas por intra-vela nunca recibían el contexto de X5, sesgando el store hacia ganadoras; (d) el store tenía columnas desalineadas (~80 % de filas corruptas en BTCUSD) y se escribía no atómicamente (corrupto al interrumpir); (e) `OSError` por bloqueos de OneDrive en Windows (relectura sin reintento y escritura no atómica de `trades.json`); (f) el reset ignoraba el checkpoint; (g) rango de precio degenerado (`p_min == p_max`) tumbaba el subproceso; (h) el store en formato es-CL (`;` y `,`) y BOM de Excel.

---

## 5. Lo que está bien y se conserva

1. **La pregunta**: parámetros como función del estado del activo que mejoran con el tiempo. Sigue siendo la misión.
2. **El arnés de ventanas**: importa X0/X1 sin duplicar lógica, es reanudable desde el CSV, determinista por semillas y guarda los soportes de cada ventana. Es la base del motor de repetición.
3. **Aleatorización independiente del estado y pareo por `t*` con la misma semilla**: la idea estadísticamente más valiosa del diseño (ganancia de varianza de 1,5× a 17×).
4. **El tope de Órdenes Abiertas por cuenta (`Q5-3b`)**: control de riesgo real y simple, más útil que cualquier C1 dinámico visto.
5. **Disciplina de proceso**: investigación separada de producción, pre-registro de hipótesis, trabajo por activo, causalidad (percentil/EMA/`μ`-`σ` causales; prueba de que recortar velas no cambia el pasado), decisiones con sus descartes, y la advertencia propia de Q4 de que el R² sale "casi por construcción".
6. **Convenciones de ejecución**: `caffeinate -i`, carpetas de salida por corrida, escritura atómica (`tmp` + `os.replace`), reintento ante bloqueos de OneDrive, registro en JSON Lines, prefijo `[valor | id]` en cada línea de consola cuando corren procesos en paralelo.

---

## 6. Inventario y veredicto por pieza

Leyenda: **Rescatar** (se usa casi igual), **Adaptar** (se usa con cambios que se indican), **Descartar** (no se usa; queda archivado si Mauricio decide archivar), **Archivar** (se copia a `X5/archivo/` por su valor de referencia). Todas las rutas son relativas a `X5_otros/`.

### 6.1. Código (`scripts/`)

| Pieza | Veredicto | Qué es y argumento |
|---|---|---|
| `x5_alt_variables.py` (≈250 líneas, 4 pruebas) | **Adaptar** | Las 8 familias de variables de estado como módulo causal (drawdown, volatilidad, liquidez, ruido, tendencia/régimen, técnicos normalizados por ATR). Reutiliza `_calcular_todos_indicadores` y `_wilder_ema` de X3. **Cambios**: ventanas en tiempo calendario o días de mercado (hoy 720/168/2160/8760 barras); quitar fundamentales (sin histórico); quedarse con ~10–15 variables candidatas por familia (volatilidad, tendencia, drawdown, rango, volumen), no 72; mantener la prueba de causalidad. |
| `x5_alt_funciones.py` (455 líneas, 14 pruebas) | **Adaptar parcial** | **Rescatar**: `drawdown_maximo` (pct y USD, con el capital inicial como primer punto), `redondear_a_grilla`, `z_expanding` (z-score causal con mínimo de 30 observaciones), `suavizar_ema`, `sigmoide_acotada` (por si una política usa sigmoide), `estadisticas_c1` (media/desviación/% en piso y techo de una serie). **Descartar**: `calibrar_parametro` y `percentil_causal` (calibración circular, §4.2), `indice_compuesto`, `serie_c1`/`c1_dinamicos`/`cargar_c2_q4`/`rangos_sorteo_c2` (jerarquía C1=f(C2)), `lotajes_m`, `premios_por_tramo` (tramos de vuelta completa). |
| `config_smart.py` (147 líneas) | **Adaptar** | Rescatar los bloques `CUENTA` (3.000 USD, margen libre mínimo 50, stop-out 50), `R_TOPE_OA`=0,5, `FECHA_INICIO_BT`='2022-03-01', `VENTANA_DIAS`=7, `TIEMPO_MAX_BUSQUEDA_VENTANA_MIN`, semillas, `P_ESTATICO`=0,067, `N_VELAS`, rangos y pasos de grilla como *punto de partida* (con los cambios: piso de `A` bajo 2 USD). Descartar `SORTEO_C2`, `GRADO`, ridge, `UMBRAL_VENTANAS_SOBOL`, `PASO_GRADIENTE`. |
| `x5_alt_aprendizaje.py` (232 líneas, 9 pruebas) | **Descartar** | RLM con ridge y ascenso de gradiente sobre C2. No encontró señal (§4.9); el diseño se abandona. Idea a recordar: validación cruzada de 5 pliegues sobre ventanas. |
| `X4_bckt_ventanas.py` (614 líneas, 25 pruebas) | **Adaptar (núcleo)** | **Rescatar**: `ejecutar_ventana` (líneas 333–422), el corazón (partir en dos: *buscar* soportes y *operar* la semana); `cargar_datos`/`t_maximo`; selector de `t*` (`orden_biseccion`, `elegir_t_star`, `contar_visitas`) y reserva por hash (`es_reservada`); registro CSV (`resumir_ventana`). **Descartar**: Sobol, `proponer_ventana_rlm`, compuerta por mediana, `evaluar_candidato`, dependencia de `publicador_c1`. |
| `X4S_backtesting_inteligente.py` (≈760 líneas, 19 pruebas) | **Adaptar parcial** | **Rescatar**: `construir_cfg` (la `SimpleNamespace` que X4 espera), `preparar_carpeta`, `_buscar_soportes`, `c1_operacion` (usa para la vela los valores de operación de la vela anterior: lo que se conoce al abrirla), `c1_estaticos`, `agregar_fila_csv` (unión de columnas). **Descartar**: vuelta completa, snapshot `estado_x4s.pkl`, `registrar_version_estructura`. El patrón de reanudación (huella de C1/semilla/cuenta) es reutilizable si hace falta una cuenta continua larga. |
| `publicador_c1.py`, `params_din.py`, `registro_din.py` (+25 pruebas) | **Descartar ahora**; **rescatar el patrón** | Publicador de C1 a `config/active_parameters.json` (esquema `q5`), lectura con respaldo por activo a `config.py` si el archivo falta, es de otro esquema o pasó `PARAMS_DIN_EDAD_MAX_MIN`=120 min, y registro JSON Lines de eventos. Reutilizar el patrón solo cuando exista un C1 dinámico validado; nunca sin que X0/X1 lo lean sin duplicar lógica. |
| `x5_alt_export.py` | **Descartar** | Convención `exp_Qi` + zip Windows→Mac para notebooks. Los experimentos nuevos corren en Mac (`feedback_backtesting_corre_en_mac`). |
| `q5_empaquetar_medicion.py`, `docs/plans/config_V4_medicion_q5_1.py`, `instrucciones_Q5.md` | **Descartar** | Medición de la vuelta completa (obsoleta). |
| `X5_macro_brain.py`, `config_x5_default.py`, `x5_demo.py` (`Otros/scripts/`) | **Descartar** (archivar) | macrobrain; X4 sigue importando `x5_demo` (§9). |
| `test_x5_alt_variables.py`, `test_x5_alt_funciones.py` | **Adaptar** | El patrón de causalidad (recortar velas no cambia las filas anteriores) y de reproducción de un resultado archivado. |
| Los otros 6 archivos de pruebas (63 pruebas) | **Descartar** con su módulo | |
| `X5_Q1.ipynb` … `X5_Q4.ipynb`, `otros_strings/X5_P1/P2.ipynb`, `X5_analisis_exploratorio.ipynb` | **Descartar** | Q4 pesa 16,8 MB (84 imágenes). El catálogo `METADATA_VARIABLES` de Q1 (fuente, significado, unidad, fórmula, ffill, limitaciones por variable) **se rescata al md** de variables cuando se defina el universo nuevo. El estándar de reporte ya vive en `docs/context/`. |
| `config/estructura_c1.json`, `config/candidatas/BTCUSD_*` | **Descartar** | Estructura C1/C2 y candidata `candidato_096` (útil solo como prueba de mecánica). |

### 6.2. Documentos

| Pieza | Veredicto |
|---|---|
| `docs/plans/x5_contexto_conversacion.md` (1.027 líneas), `X5_alternativo.md`, `X5_revision_exhaustiva_cerebro.md`, `docs/context/pars_configurables.md` | Su contenido conceptual está consolidado en §1, §2 y §4. **Descartar** como archivos (no hay nada que releer). |
| `docs/plans/plan_x5_alt_v2.md` | **Descartar**; rescatado: §9.3 (cuenta y tope de OA, aquí §2.4) y §9.14 (ventanas, aquí §3 y §6). |
| `docs/context/x5_alt_v2_opus.tex/.pdf` (11 págs) | **Archivar el PDF**: revisión independiente con análisis propios; sus hallazgos están en §4, pero el PDF tiene figuras y el detalle de métodos. |
| `docs/context/funciones_pars_dinamicos.tex/.pdf`, `docs/plans/x5_alt_v2.tex/.pdf`, `x5_documento*.tex/.pdf`, `x5_plan.md`, `x5_plan_redes_neuronales.md`, `x5_opus_review.md`, `correcciones_x5.md`, `propuesta_restructuracion.md`, `solicitud_claude_code_X5_P2_notebook_v2/v3.md`, `todos_x5.md`, `done_x5.md` | **Descartar**. Contenido relevante consolidado en §3 y §4. |

### 6.3. Ideas de diseño rescatables (no son código)

1. **Pareo por semana**: comparar siempre `Y_θ − Y_ref` en el mismo `t*` y con la misma semilla.
2. **Motor de repetición**: la búsqueda de soportes depende solo de (`t*`, `N`, `K`, `N_EXP`, `LAMBDA`, semilla, tiempo); `A`, `factor_B` y `p` no la afectan. Guardar los soportes y simular la semana con muchas combinaciones de operación cuesta segundos.
3. **Máscara de activación de `N`**: X0 calcula una sola vez el conjunto para un `N` máximo (200) y X1 usa un subconjunto de tamaño `N_t` (uno de cada dos si es la mitad, o los de mejor puntaje individual). Los conjuntos de distinto `N` **no están anidados** (coincidencia de soportes entre `N`=70 y 100: 47–53 % contra 37–49 % de una ubicación al azar), así que cambiar `N` en vivo obliga a reoptimizar desde un punto peor y a reemplazar muchas OE. Con la máscara los conjuntos quedan anidados por construcción. Sumar cuantización a ~3 niveles e histéresis (cambiar de nivel solo si el nuevo se sostiene varias horas). Con `N`=180 había 10–21 soportes dentro del 10 % bajo el precio, espaciados 0,4–0,8 % del precio (0,5–1,3 ATR): la misma escala que exige `A`; **`A` y `N` interactúan**.
4. **Frenar la exposición con riesgo**: el efecto económico de `N` es de riesgo (§4.4); el tope de OA es el mismo mecanismo más simple.
5. **Estático igualado**: comparar un parámetro dinámico contra uno estático fijado en el **mismo promedio** (§4.3).
6. **Cuota de penalización para `LAMBDA`**: en vez de un rango absoluto, medir en el óptimo de producción qué fracción de la FO es `LAMBDA·cv(H_n)` frente a `mean(z)` y explorar esa fracción (2 %–50 %). Así el rango no queda obsoleto cada vez que cambia la escala de la FO (probablemente lo que pasó con (0,001; 0,02) cuando entraron `v`, `f` y las anclas de `cv`).
7. **`K`, `N_EXP`, `LAMBDA` no son buenos candidatos a dinámicos** (revisión Opus): actúan sobre una FO que pondera 2022→hoy; `N_EXP` con una variable de 24 h contra 7 d es un desajuste de escalas; moverlos cada hora cambia lo que el optimizador persigue. Estudiarlos como estáticos con métricas de soporte (de los soportes tocados, qué fracción produjo un rebote de al menos 1 ATR).

---

## 7. Datos disponibles (`X5_otros/resources/`, 615 MB)

| Carpeta | Contenido | Tamaño | Valor |
|---|---|---|---|
| `x5_alt/q5/ventanas/{valor}/{id}/` | Por ventana: `trades.json`, `events.json`, `equity_*.csv`, `conjuntos_N/{valor}_{N}_bt.json` (soportes: `{datetime: [precios]}`), `x4.log`. 321 carpetas BTCUSD + 306 TSLA = **627 conjuntos de soportes** | 89 MB | **Oro**: insumo del motor de repetición; no se regenera sin ~10 min por conjunto. El nombre solo trae `N`; `K`, `N_EXP`, `LAMBDA` están en la fila de la ventana en `{valor}_ventanas.csv` (y los soportes casi no dependen de ellos, §4.8). |
| `x5_alt/q5/{valor}_ventanas.csv` | Una fila por ventana (94 columnas): `id`, `ts_star`, `tramo` (aprendizaje/reservada), `fase` (sobol/rlm/estatica/q4/candidato_NNN), `ronda`, `semilla`, C1 (`c1_N/K/N_EXP/LAMBDA`; para A/factor_B/p: media, desviación, mín, máx, % en piso y techo, pasos), `Y`, `cerrado`, `pnl_abierto`, `ret_medio`, `ret_vol`, `drawdown_max_pct/usd`, `n_trades`, `tasa_aciertos_pct`, `tiempo_en_mercado_pct`, `margen_usado_*`, `stop_outs`, `n_OA_cierre`, `n_OE_cierre`, `frac_oa_abiertas_cierre`, `sin_trades`, `FO_inicial/final`, `convergio`, `busqueda_s`, `busqueda_cortada`, `duracion_min`, más 33 columnas `c2_*` | 0,6 MB | **Oro**: baseline para estimar ruido y reproducir resultados. Hoy: BTCUSD 320 filas (145 `rlm`, 49 `sobol`, 50 estática, 50 Q4, 26 candidata), TSLA 306 (127, 53, 51, 51, 24). |
| `x5_alt/q5/{valor}_aprendizaje.csv`, `_compuerta.csv`, `_seguimiento.csv`, `_vueltas.csv`, `_estructura_v1.json` | Ajustes de la RLM, comparaciones de la compuerta, resumen por bloque de las vueltas completas | <1 MB | Descartar (queda como historial). |
| `x5_alt/q5/BTCUSD/` | Vueltas completas `q4_s0` y `q4_s0_v2` (3.000 → 4.581 → 396 → 46 USD) | 14 MB | **Archivar** el `equity` y `trades`: única evidencia de cuenta continua con la configuración Q4. |
| `x5_alt/exp_Q1/` | `{valor}_tabla_estado_v2.csv` (72 columnas; BTCUSD/ETHUSD 41.971 filas, TSLA 11.967, NVDA 11.977, AMZN 11.976, GOOGL 8.376; 2022-01-01 → 2026-10-16) y catálogo de variables, 7 activos | 147 MB | Regenerable desde `Data/` con `x5_alt_variables.py`; **no archivar**. |
| `x5_alt/exp_Q2/`, `exp_Q3/`, `exp_Q4/` | Salidas de los notebooks (21, 5 y 63 archivos por activo) | 218 MB | Descartar (regenerables o sin uso). `exp_Q4/{valor}_q4_resumen.csv` tiene los C2 de Q4. |
| `x5/` | Stores del macrobrain (`{ACTIVO}_store.csv`, BTCUSD 10.169 filas), `bt_{ACTIVO}/` (checkpoints, `trades.json`, equity), `Performance/` | 30 MB | Descartar. |

Datos del proyecto que X5 nuevo necesita y **sí están en el repo/Windows**: `Data/{VALOR}.csv` (OHLCV H1; columnas `DateTime, Open, High, Low, Close, Tick_Volume, Spread, Real_Volume`; no viene ordenado ni sin duplicados: ordenar y eliminar), `Data_minuto/{VALOR}.csv` (M1, para intra-vela). Las copias del Mac pueden estar desactualizadas (el 2026-11-19 solo BTCUSD y TSLA estaban al día; el resto llegaba hasta 2026-06-02).

---

## 8. Trampas operativas (lo que costó caro aprender)

1. **El Mac se suspende**: usar `caffeinate -i` delante de todo comando largo en Mac. Las duraciones medidas antes del 2026-11-14 incluían suspensión. El resultado de una búsqueda con tope de tiempo depende de la velocidad y la carga del equipo (dos procesos a la vez cambian `Y`).
2. **Backtests corren en Mac; Windows solo tiene MT5** (X0 datos, X1 operación). `Data/`, `Data_minuto/` y `resources/` están fuera de git.
3. **Tope de tiempo de la búsqueda**: con tope, la reproducibilidad exacta no vale (el resultado depende de la velocidad). Con convergencia sí: la búsqueda se siembra por `(semilla, valor, ts)` (`zlib.crc32`) y la intra-vela también.
4. **El caché de soportes de X4 está indexado por `N` y `ts`** (`_bt_warm_start(cfg.CARPETA_N_BT, activo, N, ts)`), no por `K`/`N_EXP`/`LAMBDA`. En las ventanas no afecta (carpeta propia y arranque en frío); un banco de soportes debe indexarse por los **cuatro** parámetros de búsqueda.
5. **Solapes**: dos ventanas de 7 días se solapan si sus `t*` distan menos de 168 horas. El selector no lo evitaba y descartaba después: 26 % de las corridas tiradas; el 64 % de los intervalos entre `t*` válidos consecutivos de BTCUSD es menor a 168 h, así que el `n` efectivo es menor al conteo de ventanas.
6. **Cuenta nueva por ventana**: `Y = cerrado + P&L abierto − 3000`; las OE sin llenar al cierre se cancelan; las OA se valoran a mercado. `t*` es la vela donde se buscan los soportes (queda congelada); la semana operada son las velas siguientes; `C_0` es el cierre de `t*`. `ret_medio` y `ret_vol` son retornos hora a hora **de la semana misma** (fracción, no porcentaje; `ret_vol` con `ddof=1`), no de los 7 días previos.
7. **Acciones**: 35–50 velas H1 por ventana de 7 días (un `Data/` local mostró 10 por día en TSLA/NVDA/AMZN/MSFT y 7 en GOOGL); el recálculo no puede exigir una hora exacta (la sesión no cubre las 23 UTC).
8. **Las posiciones de OneDrive**: Windows con la carpeta bajo OneDrive: `shutil.rmtree` falla (`WinError 5`) por handles; usar borrado del contenido, escritura atómica y reintento. Excel corrompe los CSV (BOM, separador decimal): no abrirlos mientras un proceso los escribe.
9. **Límites del bróker**: órdenes pendientes limitadas (retcode 10040 y "liberación por límite de órdenes" de X1): el `N` de un activo compite con los demás en producción; la sesión cerrada hace que el bróker elimine OE (`[session closed]`).
10. **Para relanzar el orquestador de ventanas** (si se quisiera): `PYTHONPATH=scripts:X5_otros/scripts:X5_otros/Otros/scripts caffeinate -i python X5_otros/scripts/X4_bckt_ventanas.py --activo BTCUSD`. La instrucción de `decisiones.md` (2026-11-21) omite la tercera ruta (`x5_demo`) y falla; la combinación de tres rutas se verificó importando el módulo. Hoy no hay procesos corriendo.

---

## 9. Residuos en archivos compartidos (para `[X5-1]` y la Fase 0 del plan)

| Archivo | Qué quedó | Gravedad | Acción propuesta |
|---|---|---|---|
| `scripts/X4_backtester.py:36` (`import x5_demo`) | **`import X4_backtester` falla** (`ModuleNotFoundError: No module named 'x5_demo'`). El archivo agrega al `sys.path` `Otros/scripts/` (vacío; el real es `X5_otros/Otros/scripts/`). | **Alta**: X4 entero no arranca, también sin `--x5`. | Sacar el modo `--x5` de X4 (≈ líneas 900–1060 `store`, 1397–1500 explorar/explotar, ganchos `x5_ctx` en `_paso_B/D/E/F`, ~15 llamadas `x5_demo.evento`, `[MES_BT]`, `_cargar_config_x5`, `_seleccionar_params_x5`) y verificar que el modo por versión (`--version`) y el uso desde un `X4_bckt_ventanas` nuevo siguen funcionando. Se diseña junto con el motor de repetición de X5 (`[X5-4]` y `[X5-5]` de `todos.md`), no por separado; **no se hizo en esta revisión**. |
| `scripts/X4_backtester.py` (otros) | Se conservan los parámetros que Q5 agregó y que sirven: `cfg.R_TOPE_OA` (tope de OA en `_paso_F`), `cfg.SEMILLA_INTRAVELA`/`SEMILLA_BUSQUEDA`, `cfg.TIEMPO_MAX_BUSQUEDA_MIN`, `cfg.X5_WARM_START_SOPORTES`. | Baja | **Conservar**; el tope de OA y las semillas son necesarios para el motor nuevo. |
| `scripts/config.py` líneas 336–441 | Bloque "X5 — Backtester y surrogate model": `CARPETA_X5`, `X5_EXPLORATION_RATE`, `X5_CAPITAL_BT`, … `X5_PARAM_RANGES` (395), `X5_US_HOLIDAYS` (411); `CARPETA_X5_ALT` (445), `CARPETA_Q5` (449), `RUTA_ESTRUCTURA_C1`; comentarios en 106, 108, 112, 151, 185, 329–332. | Media | Borrar el bloque del macrobrain; decidir si el nuevo X5 necesita rutas propias (carpeta `X5/` en git; salidas en `resources/x5/`). Comprobar antes que nada más lo lea. |
| `scripts/X0_data_supports.py` | 7 menciones en docstrings/comentarios (`params_soporte`, `cold_start`, "lo usa X4 --x5", "modo demo de X5"). | Baja | Reescribir los comentarios; la funcionalidad (`params_soporte`, `tiempo_limite_s`, `warm_start`) la usa X4 y **se queda**. |
| `scripts/X1_trading.py`, `X2`, `X3`, `X4B_crear_version_backtesting.py` | Sin residuos relevantes (X1 solo contiene "12x5s"). | — | — |
| `docs/plans/documentacion.html` (272 KB, 268 menciones) | "X4 & X5 — de la vela horaria al parámetro recomendado": documento interactivo del macrobrain. | Media | Recortar a X4 (o archivar). |
| `docs/plans/algoritmos.tex/.pdf` (39 págs, 136 menciones) | Documento mixto X4 + X5 original. La parte de X4 es vigente. | Media | Quitar la sección "X5 — Cerebro macro" y los modos `--x5` de X4. |
| `README.md` (121 menciones) | Casi todas en el listado de commits (histórico); 1 línea del árbol de módulos. | Baja | Dejar el historial; revisar solo la tabla de módulos. |
| `CLAUDE.md` (12 menciones) | Nota de X5 que apunta a `X5_otros/` y `X5/`; ejemplos con "X4 --x5" en la tabla de warm start. | Media | Actualizar la nota de X5 (punteros a este md y al informe) y quitar la fila "X5 (`X4 --x5`)". |
| `docs/context/decisiones.md` (131), `docs/tracking/records.md` (433), `docs/context/prompts.md` (20), `docs/tracking/done.md` (13) | Bitácoras históricas. | — | **No se reescriben.** |
| `docs/context/vision.md` | Menciona `X5_model_training.py` y `X6_macro_brain` (obsoleto desde el 2026-06-26). | Baja | Actualizar el diagrama de flujo. |
| `docs/plans/x2_plan.md`, `x3_plan.md`, `x4_plan.md` | Mencionan a X5/X6 como consumidores. | Baja | Revisar al final. |
| `.gitignore` | Líneas 32–33: `X5_otros/`. | — | Se mantiene. |

---

## 10. Preguntas abiertas históricas y su estado

De la revisión Opus del 2026-10-23, sin respuesta hasta el 2026-11-22:

| Pregunta | Estado |
|---|---|
| ¿Qué quieres maximizar exactamente? | **Respondida** (2026-11-22): híbrido (§1.4). Falta fijar el tope de caída máxima y de la cola. |
| ¿`PERDIDA_MAX` debe actuar o no? | Abierta. Hoy no actúa nunca en 3 de 7 activos. Si debe actuar, hay que redefinirla en unidades de mercado (ATR, % del precio o presupuesto de riesgo). |
| ¿Por qué 180 soportes? | Abierta. Si fue un ajuste a mano, los estáticos de distinto nivel pueden ser más informativos que el dinamismo. |
| ¿Cuánta rotación de órdenes toleras en producción? | Abierta. Fija la cuantización y la histéresis de un `N` dinámico. |
| ¿Cuánto cómputo semanal en Windows/Mac? | **Respondida**: Mac casi dedicado, 30+ h/semana. |
| ¿Sistema por activo o cartera? | Abierta. Hoy es por activo; el cupo de órdenes del bróker y el capital común hacen que en producción compitan. |
| ¿Dividir `A` en `A_OE` y `A_TRAILING`? | Abierta (desde 2026-09). Con la normalización por ATR se resuelve con dos multiplicadores. |
| ¿Fecha del tramo final intocable? | Propuesta (Opus): desde 2026-04-01; `X5_v3.md` propuso las últimas 26 semanas (desde mayo de 2026). Decidir. |

---

## 11. Glosario (concepto primero)

- **Parámetros de primera categoría (C1)**: los siete que consumen X0/X1 (`N`, `A`, `factor_B`, `K`, `N_EXP`, `LAMBDA`, `PERDIDA_MAX`).
- **Parámetros de segunda categoría (C2)**: los coeficientes de la función que producía cada C1 (`span`, `punto_medio`, `pendiente`, pesos). Diseño abandonado.
- **Orden en Espera (OE)**, **Orden Abierta (OA)**, **Orden Cerrada (OC)**, **O0**: estados de una orden (§2.2).
- **Rango verdadero promedio (ATR, *Average True Range*)**: promedio móvil de 14 velas del rango verdadero `TR = max(High−Low, |High−Close_prev|, |Low−Close_prev|)`; mide la magnitud típica del movimiento sin dirección. `ATR_14`.
- **Excursión adversa máxima (MAE, *Maximum Adverse Excursion*)**: la mayor caída desde el precio de entrada (o desde un cierre) hasta el mínimo posterior dentro de un horizonte.
- **Pérdida condicional en la cola (CVaR, *Conditional Value at Risk*)**: promedio del peor 10 % de resultados (`CVaR10%`, redondeado hacia arriba).
- **Regresión Lineal Múltiple (RLM)**; **Gradient Boosting (GB)**; **Modelo Aditivo Generalizado (GAM)**; **Red Neuronal de Propagación Hacia Adelante (FFNN)**; **Optimización Bayesiana (BO)**; **Proceso Gaussiano (GP)**.
- **Efecto fijo por semana**: modelar `Y_wj = α_w + efecto_j + ε`, donde `α_w` absorbe todo lo común a la semana `w` (el camino del precio) y solo queda lo que cambia entre configuraciones `j`.
- **Pareo / diferencia pareada**: comparar `Y_w(θ) − Y_w(ref)` en la misma semana y con la misma semilla.
- **Control estático igualado**: estático fijado en el promedio del dinámico.
- **Meseta**: región amplia de configuraciones con resultado parecido (preferible a un pico aislado, que suele ser ruido).
- **Fuga de información (*leakage*)** y **mirar al futuro (*look-ahead*)**: usar datos que en producción no existirían en ese instante.
- **Prueba de permutación**: barajar la columna de interés y recalcular el estadístico para ver cuánto se parece el real al que sale por azar.
- **Control de falsos descubrimientos (FDR, *False Discovery Rate*, Benjamini–Hochberg)**: corrección cuando se prueban muchas variables.
- **Soporte** y **conjunto N**: precios óptimos hallados por X0; ver `CLAUDE.md`.

---

## 12. Mapa de `X5_otros/` (por si hay que restaurar algo)

```
X5_otros/                       615 MB, solo en el Mac, ignorado por git
├── config/
│   ├── estructura_c1.json              variables de cada C1 (diseño C1=f(C2))
│   └── candidatas/BTCUSD_candidata.json, BTCUSD_historial.jsonl
├── docs/
│   ├── context/    pars_configurables.md, propuesta_restructuracion.md,
│   │               x5_alt_v2_opus.tex/.pdf, funciones_pars_dinamicos.tex/.pdf
│   ├── plans/      plan_x5_alt_v2.md, X5_alternativo.md, X5_revision_exhaustiva_cerebro.md,
│   │               x5_contexto_conversacion.md, instrucciones_Q5.md, config_V4_medicion_q5_1.py,
│   │               solicitud_claude_code_X5_P2_notebook_v2/v3.md, x5_alt_v2.tex/.pdf
│   └── tracking/   todos_x5.md, done_x5.md
├── Otros/          (macrobrain y planes previos)
│   ├── docs/context/correcciones_x5.md
│   ├── docs/plans/ x5_plan.md, x5_plan_redes_neuronales.md, x5_opus_review.md,
│   │               x5_documento.tex/.pdf, x5_documento_extendido.tex/.pdf
│   └── scripts/    X5_macro_brain.py, config_x5_default.py, x5_demo.py,
│                   X5_analisis_exploratorio.ipynb
├── scripts/        x5_alt_variables.py, x5_alt_funciones.py, x5_alt_aprendizaje.py, x5_alt_export.py,
│                   config_smart.py, X4S_backtesting_inteligente.py, X4_bckt_ventanas.py,
│                   publicador_c1.py, params_din.py, registro_din.py, q5_empaquetar_medicion.py,
│                   test_*.py (8), X5_Q1..Q4.ipynb, otros_strings/X5_P1.ipynb, X5_P2.ipynb,
│                   test_x4_bckt_ventanas.py, X4_bckt_ventanas.py
└── resources/      x5/ (stores macrobrain, 30 MB) y x5_alt/ (exp_Q1..Q4, q5/, 585 MB)
```

**Riesgo**: `X5_otros/` no tiene copia fuera del Mac. Lo irrecuperable es (a) `resources/x5_alt/q5/` (104 MB: ventanas, soportes, vueltas completas) y (b) los PDF y el código. Todo lo demás es regenerable o ya está consolidado aquí. Recomendación (decisión de Mauricio): antes de borrar o mover `X5_otros/`, archivar (i) `scripts/` y `docs/` (≈18 MB) y (ii) `resources/x5_alt/q5/` comprimido (≈100 MB) en un respaldo fuera del repo (disco externo o nube).

---

## 13. Qué se necesita de este documento al empezar el X5 nuevo (índice rápido)

| Si necesitas… | Mira |
|---|---|
| Entender qué hace cada parámetro y sus unidades | §2 y §4.5 |
| Saber por qué no se sigue con C1 = f(C2) | §4.2, §4.9 |
| Saber qué datos ya existen y cuánto cuestan de regenerar | §7 |
| Reutilizar la simulación de una semana | §6.1 (`X4_bckt_ventanas.py`, `X4S_…`), §6.3 (2) |
| No tropezar con lo mismo de nuevo | §8 y §4.14 |
| Arreglar X4 antes de usarlo | §9 (fila 1) |
| Ver qué ya se decidió y no volver a proponerlo | §3, §4 y `docs/context/decisiones.md` por fecha |
