# Oportunidades de mejora — Alginvesting

Barrido de `scripts/` y `docs/` (2026-06-13). Hallazgos clasificados por archivo, ordenados
dentro de cada uno por severidad. Cada ítem lleva una etiqueta:

- 🔴 **Correctness/riesgo**: posible bug o comportamiento incorrecto con plata real.
- 🟠 **Robustez**: el código funciona pero se cae o degrada feo ante fallas esperables.
- 🟡 **Mantenibilidad/perf**: limpieza, rendimiento, deuda técnica, sin riesgo funcional.
- 🔵 **Doc desincronizada**: documentación que ya no refleja el código.

No incluye los ítems que ya están en `docs/todos.md` (X3–X6, backtester, etc.); esto es lo
que aparece al revisar el código existente, no el roadmap.

---

## `scripts/X1_trading.py`

El módulo que toca dinero real. Es donde están los hallazgos de mayor severidad.

### 🔴 `dic_seguimiento` indexa por el objeto posición completo, no por `ticket`
Líneas 86-92 (`obtener_conjuntos_actuales`) y 240-244 (`trailing_stop`).

`trailing_stop` hace `dic_seguimiento[valor].append(orden)` guardando el objeto `TradePosition`
(namedtuple de MT5) capturado en ese ciclo. En el ciclo siguiente, `obtener_conjuntos_actuales`
compara `if orden not in actual_OA` contra una lista **fresca** de posiciones traídas con
`positions_get`. Esos objetos nuevos traen campos que cambian tick a tick (`price_current`,
`profit`, `sl`, `time_update`), así que el objeto viejo guardado **nunca va a ser igual** al
nuevo aunque sea la misma posición → se la trata como "cerrada externamente" y se la saca del
seguimiento prematuramente. Efecto: el sistema deja de priorizar (no-sleep) esa posición en
trailing, y `trailing_stop` la vuelve a agregar recién cuando cambie el SL otra vez. Churn
constante y trailing menos reactivo de lo previsto.

**Fix**: indexar `dic_seguimiento` por `orden.ticket` (entero estable), no por el objeto.
Comparar `ticket not in {p.ticket for p in actual_OA}`.

### 🔴 `crear_ordenes_espera` no redondea `price_open` al deduplicar → órdenes duplicadas
Líneas 167-171 vs 95-99.

`leer_lista_N` redondea los soportes a 2 decimales (línea 62). En `crear_ordenes_espera`,
`lista_OAE = lista_OA + lista_OE` se arma con `p.price_open` **crudo** del broker (línea 168),
y luego se chequea `if Pi in lista_OAE` con `Pi` ya redondeado. La igualdad exacta float64 entre
un soporte redondeado y un `price_open` crudo casi nunca calza → el dedup falla y se puede crear
una segunda buy limit en un nivel que ya tenía orden. Nota la inconsistencia: `limpiar_ordenes_
pendientes_no_validas` (línea 98) **sí** hace `round(orden.price_open, 2)` antes de comparar.

**Fix**: redondear `price_open` a 2 decimales al construir `lista_OAE`, igual que en `limpiar_*`.

### 🔴 `ejecutar_orden` mata el loop completo (`sys.exit(1)`) ante cualquier retcode no listado
Líneas 146-154.

Si `order_send` devuelve un retcode que no está en el allowlist `[10006, 10044, 10018, 10031]`,
el código hace `mt5.shutdown(); sys.exit(1)` — termina todo el sistema de trading por **una**
orden rechazada (que puede ser transitoria: requote, precio inválido momentáneo, etc.). En un
`while True` que debe correr sin supervisión, un rechazo puntual no debería tumbar la gestión de
todas las posiciones abiertas (que quedan sin trailing ni control de pérdida).

**Fix**: loguear el error y `return` (seguir el ciclo), reservando el `sys.exit` solo para
fallas no recuperables (ej. conexión perdida, que conviene manejar aparte — ver siguiente).

### 🟠 Sin resiliencia de conexión MT5 en el loop
`obtener_precio_actual` (líneas 69-72) hace `tick.bid` sin chequear que `tick` no sea `None`.
Si MT5 pierde conexión a media sesión, `symbol_info_tick` devuelve `None` → `AttributeError`
no manejado → crash del loop. Para un proceso que corre horas/días, conviene chequear `tick is
None` y reintentar `mt5.initialize()` con backoff antes de seguir.

### 🟡 `import os` sin uso
Línea 18. Eliminar.

### 🟡 Cadencias con números mágicos derivados de `TS`
`i % int(5 / TS)` (línea 350, limpieza cada ~5s) e `i % int(5000 / TS)` (línea 368, info cada
~5000s). Funcionan, pero los `5` y `5000` quedan hardcodeados en el loop. Si algún día se
quieren tunear (o los gobierna X6), conviene subirlos a `config.py` como `SEG_LIMPIEZA` /
`SEG_INFO`.

---

## `scripts/config.py`

### 🔴 `n_sizes` (lo que genera X0) está desacoplado de `n_sizes_ejecucion` (lo que lee X1)
Líneas 43-46 vs 49-56.

Hoy `n_sizes` solo tiene `GOOGL: [70,80,90,100]` y `ETHUSD: [70,100]` — o sea, X0 genera
`conjuntos_N/prod/GOOGL_70.json … GOOGL_100.json` y `ETHUSD_70/100`. Pero X1 lee con
`n_sizes_ejecucion`: `BTCUSD_130`, `ETHUSD_130`, `GOOGL_120`, etc. **Ninguno de los N que X1
consume es generado por X0 con el config actual.** Si corres X0 y después X1 desde cero, X1
hace `sys.exit` en `leer_lista_N` por no encontrar `{valor}_130.json`. Parece estado de
experimentación (arriba hay un bloque comentado con todos los activos), pero es un pie de
producción peligroso.

**Fix**: dejar claro en el archivo qué bloque es "experimentación" vs "producción", o validar al
inicio de X1 que existan los N de `n_sizes_ejecucion` antes de entrar al loop. Idealmente, que
X0 garantice generar los N que X1 va a leer.

### 🔴 `FECHA_INICIAL = '2022-01-01'` contradice toda la documentación (que dice `2024-01-01`)
Línea 60. `CLAUDE.md`, `README.md` y `docs/decisiones.md` (×3) afirman consistentemente
`2024-01-01` y razonan sobre "~21k velas / ~2 años". Con 2022 son ~4 años y ~35k velas — cambia
los supuestos de memoria/tiempo de `_vecino_mas_cercano` y de la historia trackeada en `Data/`.
O el código quedó con un valor de prueba, o la doc está atrasada. Hay que decidir cuál es el
correcto y sincronizar. (Recordar: la memoria marca `FECHA_INICIAL` como tentativa — razón de
más para no dejar que código y doc divergan en silencio.)

### 🟡 Bloque viejo de `n_sizes` comentado con triple-quote
Líneas 26-41. Se está usando un string `"""..."""` como comentario para guardar versiones
anteriores de `n_sizes`. Crea un literal de string en memoria (trivial) y ensucia. Mejor
borrarlo (git ya tiene la historia) o moverlo a un comentario `#`.

### 🔵 `N_MAX_MODELS = 6` pero la doc dice `None`
Línea 95. `docs/documentacion_V0.md` (línea 374) documenta `N_MAX_MODELS = None` como default.
Hoy está en 6 (que con el `n_sizes` actual de 6 combos equivale a "todos", quizás por eso pasó
desapercibido). Sincronizar doc o código.

---

## `scripts/X0_data_supports.py`

El motor del proyecto. Mucho de esto es perf/limpieza; el código es correcto en lo grueso.

### 🟡 `df_FO` se arma con `pd.concat` dentro del loop → O(iteraciones²)
Líneas 596 y 690-694. Cada iteración del optimizador hace
`df_FO = pd.concat([df_FO, pd.DataFrame({...})])`. Concatenar en loop reasigna y recopia el
DataFrame completo cada vez — cuadrático en el nº de iteraciones (que puede ser miles). Acumular
las filas en una lista de dicts y hacer **un** `pd.DataFrame(lista)` al final. Solo se usa para
graficar/loguear, así que el fix es seguro.

### 🟡 Doble inicialización del `conjunto_N`
`obtener_df_extremos` (líneas 194-205) dimensiona y completa `conjunto_N` llamando a
`_inicializar_conjunto_smart`, y acto seguido `nuevo_optimizador_2` (líneas 570-589) **vuelve a
hacer exactamente lo mismo** sobre el conjunto que ya recibió dimensionado. Es trabajo duplicado
y, peor, dos lugares que hay que mantener en sync. Conviene que el dimensionamiento viva en un
solo lado. Relacionado: el parámetro `ocp` de `obtener_df_extremos` (línea 171) siempre llega en
0 desde el único call site (línea 968) — es un grado de libertad muerto.

### 🟡 `evaluar_crecimiento_decrecimiento` acepta también curvas monótonas (nombre ≠ lógica)
Líneas 524-538. La función dice detectar "U invertida" (crece y luego decrece), pero por como
está el loop, una curva **monótona decreciente** también devuelve `True` y dispara el ajuste
cuadrático (líneas 632-638), que asume un máximo interior. Hoy el `np.clip` a
`(cota_inf, cota_sup)` (línea 636) tapa el caso (el vértice queda en un extremo), así que no
explota, pero es frágil: el ajuste parabólico se aplica a datos no cóncavos. Vale documentar el
supuesto real o endurecer el detector. Además itera con acceso escalar de pandas
(`df_plot[metrica][i]`) — sobre arrays de M~30 conviene pasar a numpy.

### 🟡 `df_plot` como DataFrame para arrays diminutos en el hot path
Línea 629. Por cada candidato/soporte/iteración se crea un `pd.DataFrame` de M filas solo para
pasarlo a `evaluar_crecimiento_decrecimiento` y sacar un `argmax`. Operar directo sobre los
arrays numpy (`casos_random`, `FO_values`) evita construir miles de DataFrames chicos.

### 🟡 Imports muertos: `os` y `mplfinance as mpf`
Líneas 19 y 28. Ninguno se usa en el archivo. `mplfinance` ni siquiera está en la lista de
librerías clave del README como dependencia real de X0. Eliminar ambos.

### 🟡 Argumentos default mutables
`obtener_df_extremos(..., conjunto_N: set = set())` (línea 171),
`nuevo_optimizador_2(..., ordenes_activas: list = [])` (línea 542),
`_procesar_valor_N(..., ordenes_activas: list = [])` (línea 889). Hoy no se mutan in-place
(se usan `union`/lectura), así que no hay bug activo, pero es el footgun clásico de Python.
Cambiar a `None` + asignación dentro de la función.

### 🟡 `warnings.filterwarnings('ignore')` global
Línea 33. Silencia **todos** los warnings del proceso, incluyendo `SettingWithCopyWarning`,
divisiones por cero de numpy y `FutureWarning` de pandas que podrían estar avisando de bugs
reales (ej. el `df_extremos.loc[...] = ...` de `_actualizar_estado`). Mejor acotar a las
categorías específicas que molestan.

### 🟡 Coarse-to-fine no varía `delta_inicial` entre fases (desvío del diseño S3)
Líneas 978-988. Las dos fases (M_COARSE y M) se llaman ambas con `delta_inicial=delta_actual`.
El diseño documentado de la Sugerencia 3 (`docs/documentacion_V0.md` líneas 133-135) proponía
delta alto en coarse y bajo en fine. No es un bug, pero la fase coarse no está aprovechando que
podría aceptar saltos más grandes con un delta mayor. Evaluar si conviene cerrar el diseño.

### 🟡 Reproducibilidad: sin semilla de RNG
Cold start usa `np.random.uniform` (`_inicializar_conjunto_smart`, fallback) y `_seleccionar_
combos` usa `random.shuffle` (línea 1112). Sin seed, dos corridas del mismo combo no son
reproducibles — incómodo cuando X4/backtesting quiera comparar resultados. Considerar un
`SEED` opcional en `config.py`.

### 🔵 Docstrings y labels desactualizados respecto al scoring actual
- `obtener_df_extremos` (línea 174) dice "Inicializa conjunto_N con puntos aleatorios" — ya no:
  usa `_inicializar_conjunto_smart` (smart seeding).
- `graficar_df_extremos` (línea 718) rotula `z = y·w·h_dist`, pero `z` hoy incluye también `v`
  (volumen) y `f` (fuerza del rechazo). El título del gráfico miente sobre la fórmula.

### 🟡 (Nota) La rama backtesting de `_procesar_valor_N` está inalcanzable hoy
Todo el camino `es_bt`/`fecha_hora_max` (warm start bt, `_bt_guardar`, `_bt_warm_start`) existe,
pero `buscar_soportes` siempre llama con `fecha_hora_max=None` (línea 1168). Es andamiaje legítimo
para X4, no un bug — pero hasta que X4 lo invoque, es código sin probar en ejecución. Conviene
una prueba mínima cuando se construya X4 (ver sección Transversal).

---

## `scripts/X2_fundamentals.py`

Bien estructurado y con validadores. Hallazgos sobre todo metodológicos.

### 🟠 Min-max cross-sectional sobre universo crypto de 2 elementos es degenerado
`_minmax` (líneas 80-87) necesita ≥2 valores válidos; con solo BTC y ETH, cada componente
normalizado da exactamente 0 y 1 (salvo empate) — el `score_cross` de crypto se vuelve un binario
"¿BTC o ETH es mejor en esta métrica?", sin matiz. Lo amortigua `score_tendencia` (longitudinal,
20%), pero el 80% cross queda muy grueso para crypto. Vale anotarlo como limitación conocida y,
a futuro, considerar normalizar crypto contra un universo mayor o contra su propia historia.

### 🟠 Llamadas de red sin reintento
`_get_stock_data` (`yf.Ticker().info`), `_get_crypto_data` (CoinGecko) y `_get_fear_greed`
(alternative.me) son single-shot con `try/except` → ante un fallo transitorio los campos quedan
`None` y el componente cae a 0.5 neutral silenciosamente. Los validadores avisan si >50% quedó
nulo, pero un par de campos caídos pasan sin ruido. Un retry con backoff corto (2-3 intentos)
sobre cada fetch reduce ese sesgo. `yf.Ticker().info` además es notoriamente lento/flaky — vale
la pena envolverlo.

### 🟡 Import de `config` inconsistente con X0/X1
Línea 28: X2 hace `sys.path.insert(0, str(Path(__file__).parent))` antes de `from config import`.
X0 y X1 importan `from config import ...` directo (confían en que Python pone `scripts/` en
`sys.path[0]` al ejecutar el archivo). Los tres funcionan al correrse como `python scripts/Xn.py`,
pero el mecanismo difiere entre archivos. Estandarizar (o convertir `scripts/` en paquete) para
que el import no dependa del CWD ni de trucos distintos por archivo.

---

## `docs/documentacion_V0.md`

### 🔵 Describe como "pendiente en X0_aux.py" trabajo que ya está implementado en X0
Líneas 17-18 y tabla de líneas 268-280: el documento dice que las 7 sugerencias quedan
"pendientes de implementar en `X0_aux.py`". Pero según el changelog y `CLAUDE.md`, **ya están
implementadas directamente en `X0_data_supports.py`**: S1 (FO incremental), S2 (init smart),
S3 (coarse-to-fine, parcial — ver arriba), S4 (priorización por `mejora_acumulada`), S5
(`prueba_cercanos=True` ya es default, línea 544), S6 (vectorización). El archivo `X0_aux.py`
nunca se creó. Solo S7 (criterio de parada por tasa) sigue pendiente (está en `todos.md`).

**Fix**: actualizar el doc para marcar qué quedó implementado, dónde, y que `X0_aux.py` se
descartó como ruta. Hoy un lector nuevo (o Claude en otra sesión) puede creer que nada de esto
existe todavía.

---

## `docs/decisiones.md`

### 🔵 La decisión del 2026-06-07 sobre delta adaptativo quedó superada y no se anotó
Líneas 86-91 describen el mecanismo con `LAMBDA_DELTA = 0.9` aplicado en **cada** corrida. El
código actual usa `FACTOR_DELTA = 0.7` aplicado **solo al converger** (config.py línea 83;
CLAUDE.md cambelog 2026-06-08). La entrada de decisiones.md no se actualizó ni se marcó como
superada, así que conviven dos descripciones contradictorias del mismo mecanismo. Agregar una
nota de "superado por 2026-06-08" para no confundir.

### 🔵 Referencias a `2024-01-01` (ver `config.py`)
Líneas 29 y 47 razonan sobre `FECHA_INICIAL='2024-01-01'` y "~2 años", contra el `2022-01-01`
real del código. Mismo problema de sincronización que el ítem de `config.py`.

---

## `docs/vision.md`

### 🔵 `X1.5_intravela.py` figura como módulo separado, pero se decidió embeberlo en X4
"Arquitectura Deseada" (líneas 254-281) lista `X1.5_intravela.py` como archivo propio. La
decisión del 2026-06-08 (`decisiones.md` líneas 70-73) descartó X1.5 como script independiente y
movió la lógica intra-vela a una subrutina dentro de X4. `vision.md` es aspiracional, pero vale
una nota para que no se reinterprete como pendiente de crear un archivo.

---

## Transversal (todo el repo)

### 🔴 No hay ningún test automatizado
No existe carpeta `tests/` ni archivos `test_*.py`. El proyecto acumuló varios refactors validados
"byte a byte a mano" (vectorización de `calcular_distancias`, `asignar_soporte`, y sobre todo la
**FO incremental** S1, que reimplementa `calcular_FO` con aritmética incremental frágil). No hay
nada que impida que un cambio futuro rompa esa equivalencia en silencio — en un sistema que
después gatilla órdenes con plata real.

**Mínimo de alto valor**: un test de regresión que, sobre un CSV chico, compare
`_fo_incremental_batch` / `_actualizar_estado` contra `calcular_FO` recalculada desde cero tras
cada cambio aceptado, y verifique que coinciden dentro de tolerancia. Es la pieza más riesgosa y
la más barata de blindar. Encaja con la preferencia global de "tests de integración sobre
unitarios, no mockear".

### 🟡 Lógica `json_act` duplicada entre X0 y X1
La misma función `json_act` está copiada en `X0_data_supports.py` (líneas 47-58) y
`X1_trading.py` (líneas 39-50). Igual que `_fmt_duracion` (X0 líneas 1217-1223 / X1 líneas
323-329). Candidatos a un pequeño módulo `utils.py` compartido en `scripts/`.

### 🟡 `sys.exit` dentro de workers de `ProcessPoolExecutor`
Varias funciones de X0 (`json_act`, `obtener_df_extremos`, `nuevo_optimizador_2`) hacen
`sys.exit(...)` ante errores. Corriendo dentro de un worker, eso se propaga como excepción al
future (lo captura `buscar_soportes` líneas 1176-1179), así que no tumba el proceso padre — pero
mezcla "abortar el programa" con "fallar esta tarea". Conviene que las funciones del algoritmo
levanten excepciones específicas y que solo el `__main__` decida si aborta.

---

## Resumen de prioridad sugerida

Si hubiera que atacar en orden de impacto/riesgo:

1. **X1 — `dic_seguimiento` por ticket** (🔴 trailing roto sutilmente).
2. **X1 — redondeo en `crear_ordenes_espera`** (🔴 órdenes duplicadas).
3. **X1 — no matar el loop por una orden** + resiliencia de conexión MT5 (🔴/🟠).
4. **config — `n_sizes` vs `n_sizes_ejecucion`** (🔴 X0 no genera lo que X1 lee).
5. **config/docs — resolver `FECHA_INICIAL` 2022 vs 2024** (🔴 doc/código).
6. **Transversal — test de regresión de la FO incremental** (🔴 blindaje barato).
7. Resto: perf (`pd.concat` en loop), limpieza (imports muertos, defaults mutables,
   `warnings`), y sincronización de docs (`documentacion_V0`, `decisiones`, `vision`).
