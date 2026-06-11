# Alginvesting — Contexto para Claude

## Qué es este proyecto

Sistema de trading algorítmico personal. Identifica soportes y resistencias óptimos en activos financieros (crypto + acciones US) y ejecuta órdenes de compra de forma semi-automática en MetaTrader5 (MT5).

**No es un SaaS ni un producto para terceros.** Es una herramienta personal de inversión.

---

## Flujo de trabajo Mac ↔ Windows

```
Mac (Claude Code)           GitHub              Windows (ejecución)
─────────────────     ───────────────     ──────────────────────────
Desarrollo + refactor  →  git push   →    git pull
CLAUDE.md, docs        ←─────────────     (no tiene Claude)
                                          Ejecutar X0 (datos + soportes)
                                          Ejecutar X1 (trading live)
```

- El código se desarrolla en Mac y se ejecuta en Windows donde está MT5.
- `Alginvesting_base/` es el repo clonado de la versión Windows (solo lectura, referencia histórica).
- `Data/` se trackea en git (ver `docs/decisiones.md` 2026-06-07): contiene la historia de precios desde 2024-01-01 y MT5 solo entrega las últimas ~1000 velas, así que sin el CSV existente se pierde todo lo anterior. `conjuntos_N/` (JSONs de soportes) sigue fuera de git, se regenera corriendo X0.

---

## Arquitectura

### Scripts principales (en `scripts/`)

| Archivo | Propósito |
|---|---|
| `X0_data_supports.py` | **Etapa 1**: Descarga/actualiza CSVs de precios vía MT5. **Etapa 2**: Encuentra los N soportes/resistencias óptimos y los guarda en `conjuntos_N/` como JSON. `--opcion 0/1/2` |
| `X1_trading.py` | Loop semi-automático (`while True`): lee soportes, gestiona buy limits en MT5, trailing stop, y cierra posiciones si pérdida > `PERDIDA_MAX`. |
| `config.py` | Parámetros centralizados: rutas, `VALORES`, `n_sizes`, `n_sizes_ejecucion`, y configuración de X0 (algoritmo) y X1 (trading). |

### Directorios de datos

| Carpeta | Contenido |
|---|---|
| `Data/` | CSVs OHLCV H1 por activo (BTCUSD, ETHUSD, TSLA, GOOGL, NVDA, AMZN) — actualizados por X0, **trackeados en git** (historia desde 2024-01-01) |
| `Data_minuto/` | CSVs OHLCV M1 por activo — usados por X4 para simulación intra-vela; se alimentan incrementalmente igual que `Data/`. Fuera de git (regenerables). |
| `conjuntos_N/` | JSONs por activo — `{VALOR}_{N}.json` (soportes producción, leído por X1), `{VALOR}_{N}_delta.json` (delta adaptativo producción), `{VALOR}_{N}_bt.json` (cache bt: `{datetime: [soportes], ...}`), `{VALOR}_{N}_bt_delta.json` (delta adaptativo bt) — generados, fuera de git |

---

## Conceptos clave del dominio

- **N (n_sizes)**: Cantidad de soportes a mantener activos por activo. Varía por activo: BTCUSD/ETHUSD=130, resto=120.
- **M**: Número de precios candidatos evaluados por soporte en cada paso del optimizador (linspace equidistante entre soportes vecinos). Controla la granularidad de la búsqueda local — mayor M, barrido más fino pero más evaluaciones de FO por iteración.
- **Conjunto N**: Los N soportes óptimos elegidos por el algoritmo de optimización.
- **OA / OE**: Órdenes Abiertas (posición activa) / Órdenes en Espera (buy limit pendiente).
- **Trailing Stop**: SL que sigue el precio hacia arriba para proteger ganancias.
- **Beta**: Riesgo por operación como % de cuenta.
- **T**: Ventana de días históricos usada para calcular soportes (default: 60).
- **lambda_ponderador**: Ponderador en la función objetivo que balancea calidad de soportes vs. dispersión entre ellos.

---

## Algoritmo de búsqueda de soportes (X0)

### Paso 1 — `calcular_distancias`
Para cada vela `i`, busca la vela más cercana a la izquierda y derecha cuyo rango `[Low, High]` *contenga* el `Low` (o `High`) de la vela `i`. La distancia temporal entre ambas velas queda en `Low_left / Low_right / High_left / High_right`. Velas con distancias grandes en ambas direcciones son extremos aislados, candidatos naturales a soporte/resistencia.

### Paso 2 — Scoring por vela (`obtener_df_extremos`)
- `y` (aislamiento): `Low_left + High_left + K * (Low_right + High_right)`
- `w` (recencia): `t^N_EXP`, donde `t ∈ [0,1]` normalizado; velas recientes pesan más.
- `v` (volumen): `Tick_Volume / Tick_Volume.max()`, normalizado a `[0,1]`; proxy de actividad/participación en ese nivel de precio (`Real_Volume` viene vacío en los CSV de MT5, así que se usa `Tick_Volume`).
- `f` (fuerza del rechazo): `1 - |Close - Open| / (High - Low)`, en `[0,1]`; proporción del rango de la vela que fue "mecha" en vez de cuerpo — una vela con cuerpo chico y rango grande indica que el precio visitó el extremo y fue rechazado con fuerza, señal de un nivel más respetado. Direccional-agnóstico (no distingue rechazo al alza/baja), consistente con cómo `y` ya combina aislamiento de `Low` y `High` en una sola señal.

### Paso 3 — Función objetivo (`calcular_FO`)
Se asigna cada vela al soporte más cercano del conjunto N. Luego:
- `h_dist = 1 - dist²/dist_max` (proximidad normalizada al soporte asignado)
- `z = producto de los factores activos en `parametros_soportes` (config.py)`: por defecto `y * w * h_dist * v * f`. El diccionario permite activar/desactivar cada uno para experimentar con el scoring sin tocar el código.
- `FO = mean(z) - LAMBDA * cv(H_n)`
  - `mean(z)`: calidad promedio de asignación (combinación de los factores activos: aislamiento, recencia, proximidad, volumen, fuerza del rechazo)
  - `cv(H_n)`: coeficiente de variación de las distancias entre soportes consecutivos — penaliza que los N soportes se concentren en una zona del rango

### Paso 4 — Optimizador de búsqueda local (`nuevo_optimizador_2`)
En cada iteración, para cada soporte `i` del conjunto N:
1. Genera M precios candidatos equidistantes (linspace) entre los soportes vecinos `i-1` e `i+1`.
2. Evalúa la FO para cada candidato.
3. Si la curva FO(candidato) tiene forma de U invertida → ajuste cuadrático para hallar el máximo analítico exacto.
4. Si no → toma el candidato con mayor FO.
5. Acepta el cambio solo si la mejora relativa supera `DELTA_INICIAL`.

Si ningún soporte mejora en la vuelta actual → expande a todos los soportes y reintenta. Si aún no hay mejora → convergencia.

Versión activa: `nuevo_optimizador_2`.

---

## Parámetros del algoritmo — efecto de cada uno

Definidos en `scripts/config.py:42-55`. Valores listados = los usados en producción (no los defaults de las funciones, que pueden diferir).

### N — cantidad de soportes (`config.py`: 130 BTCUSD/ETHUSD, 120 el resto)
- **↑ N**: más cobertura del rango de precios y entradas más finas, pero capital más fragmentado por posición y mayor costo computacional (`calcular_FO` se llama del orden de N×M veces por iteración del optimizador).
- **↓ N**: posiciones más concentradas (mayor peso por entrada), optimización más rápida, cobertura más gruesa del rango.

### K = 1 — peso del aislamiento futuro vs. pasado en `y = Low_left + High_left + K*(Low_right + High_right)`
- **K = 1** (actual): el aislamiento hacia atrás (pasado) y hacia adelante (futuro respecto a la vela, no al presente) pesan igual.
- **↑ K**: prioriza velas cuyo nivel permaneció "intacto" mucho tiempo después de formarse — favorece niveles ya validados por el tiempo transcurrido.
- **↓ K**: prioriza el aislamiento previo a la formación de la vela — favorece el contexto que la originó por sobre su validación posterior.

### N_EXP = 1.3 — exponente de recencia en `w = t^N_EXP`, con `t ∈ [0,1]`
- **N_EXP = 1.3** (actual, convexo): los pesos crecen más que proporcionalmente con `t` — las velas recientes dominan la FO, las antiguas casi no influyen.
- **↑ N_EXP**: acentúa esa concentración en lo reciente — más reactivo a cambios de régimen, menos memoria del historial.
- **↓ N_EXP** (hacia 1, o cóncavo si <1): reparte el peso de forma más pareja entre todo el historial — más estable, menos sensible a movimientos recientes.

### M = 30 — candidatos evaluados por soporte en cada paso del optimizador
Genera M precios equidistantes (`linspace`) entre los soportes vecinos y evalúa la FO en cada uno.
- **↑ M**: barrido más fino entre soportes vecinos → más probabilidad de hallar el óptimo local exacto (o una buena base para el ajuste cuadrático), pero cada paso cuesta M evaluaciones de `calcular_FO` adicionales.
- **↓ M**: pasos más rápidos, pero candidatos más espaciados → más riesgo de saltarse el máximo real entre dos soportes vecinos.

### LAMBDA = 1/500 — penalización por dispersión desigual: `FO = mean(z) - LAMBDA * cv(H_n)`
- **↑ LAMBDA**: castiga con más fuerza que los soportes se amontonen en una zona del rango — empuja el conjunto N hacia una distribución más pareja en precio, aunque sacrifique algo de `mean(z)` (calidad de asignación).
- **↓ LAMBDA**: la FO se guía casi solo por `mean(z)` — permite que los soportes se concentren donde hay más "evidencia" (velas aisladas y recientes), aunque dejen huecos grandes en otras zonas del rango.

### DELTA_INICIAL = 1e-4 — mejora relativa mínima para aceptar un cambio: `(FO_iter - FO_base)/FO_base > DELTA_INICIAL`
- **↑ DELTA_INICIAL**: exige mejoras más significativas para mover un soporte → converge más rápido (menos iteraciones), pero puede detenerse en un óptimo más alejado del ideal.
- **↓ DELTA_INICIAL**: acepta mejoras más marginales → resultado más fino, pero más iteraciones y más riesgo de aceptar cambios por ruido numérico.

---

## Activos operados

```python
valores = ['BTCUSD', 'ETHUSD', 'TSLA', 'GOOGL', 'NVDA', 'AMZN']
```

---

## Entorno

- Conda: `revenAI` (Python 3.11)
- Librerías clave: `MetaTrader5`, `yfinance`, `pandas`, `numpy`, `matplotlib`, `mplfinance`
- En Windows: requiere MT5 instalado y cuenta de broker configurada
- En Mac: desarrollo solo (MT5 no disponible en macOS)

---

## Convenciones de este proyecto

- `snake_case` para variables y funciones. `PascalCase` para clases.
- Archivos `.py` en producción. `.ipynb` solo para exploración visual de nuevos módulos.
- Parámetros clave centralizados en `config.py`.
- Archivos en `conjuntos_N/`: `{VALOR}_{N}.json` es el único archivo de soportes (X0 escribe, X1 lee).
- Sin hardcodear rutas fuera de `config.py`.
- `docs/decisiones.md` registra decisiones técnicas relevantes.

---

## TO DO

**Convención de priorización**: cada ítem pendiente lleva `(I:x C:y H:z → score)` — Impacto, Complejidad de desarrollo, Habilitación, escala 1–10. `score = √(I × H) / C`. Dentro de cada sección los ítems se ordenan de mayor a menor score.

### Prioridad_0

Urgencias transversales. Una vez completadas (`[x]`), el ítem se mueve a su sección correcta.

- [ ] **Tiempo de ejecución al final de cada script**: al terminar `X0_data_supports.py`, `X1_trading.py` y cualquier script Python del proyecto, imprimir el tiempo total transcurrido (formato `HH:MM:SS` o segundos si < 60 s). Implementar con `time.time()` en el `if __name__ == '__main__'` de cada script. (I:3 C:1 H:2 → 2.45)

### X0 — X0_data_supports.py

- [ ] **X0_aux.py — testear mejoras de convergencia (fase 2)**: crear script auxiliar `scripts/X0_aux.py` para probar las sugerencias del análisis de convergencia (documentadas en `docs/documentacion_V0.md`) de forma aislada y medible. Baseline: corrida de referencia de un (valor, N) con el optimizador actual. Medir impacto de cada mejora en velocidad y calidad (FO final, iteraciones, cambios) antes de migrar a producción. (I:6 C:3 H:7 → 2.16)
- [x] **Logs de convergencia**: al converger cada combo (valor, N) — o (valor, N, max_datetime) en modo bt — guardar JSON en `docs/X0/logs/` con: clave de la tupla, t_inicio, t_fin, duración, iteraciones, FO final, delta_final, convergio (I:5 C:4 H:6 → 1.37)
- [x] **N_MAX_MODELS + loop continuo**: parámetro `N_MAX_MODELS` en `config.py` — selecciona los N pares (valor, N) con mayor `delta_inicial` actual (tie-break aleatorio), los ejecuta en paralelo, y al terminar el último reinicia el ciclo completo (incluyendo descarga MT5 si opción 1 activa) en un `while True` (I:8 C:6 H:7 → 1.25)
- [ ] Separar descarga de datos en módulo independiente (hoy está en X0) (I:4 C:5 H:4 → 0.80)
- [ ] **Formato de outputs en paralelo (baja prioridad)**: cuando converge un par (valor, N), mostrar el tiempo en minutos que tardó en converger — solo al converger, no en cada iteración (I:2 C:3 H:2 → 0.67)
- [ ] Revisar con Mauricio la lógica de scoring de `calcular_FO` — ya se agregaron `v` y `f` (lo de mayor impacto); queda pendiente discutir ajustes menores (ej. `h_dist` por volatilidad, conteo de retests) (I:2 C:3 H:2 → 0.67)
- [x] **Sugerencias de convergencia**: 7 mejoras algorítmicas documentadas en `docs/documentacion_V0.md` — FO incremental, inicialización inteligente, M adaptativo, priorización por historial, prueba_cercanos, vectorización loop M, criterio parada por tasa. Ordenadas por impacto/complejidad.
- [x] Migrar X0 (notebook) a `scripts/X0_data_supports.py`
- [x] **Paralelización**: la búsqueda de soportes es independiente por cada par (valor, N) → paralelizar con `multiprocessing` o `concurrent.futures`. Ej: BTCUSD-130, ETHUSD-130, TSLA-120, etc. corriendo simultáneamente.
- [x] Velocidad: `calcular_distancias` vectorizada con numpy por bloques (evita matriz n×n completa) — ~19x más rápido (33.9s → 1.8s en BTCUSD, n=21213), resultados idénticos byte a byte
- [x] Velocidad: `asignar_soporte` vectorizada con `np.searchsorted` (búsqueda binaria del soporte más cercano, O(n log N) en vez de O(n×N) con `apply`) — ~45-178x más rápido (0.26s → 0.0014s en BTCUSD, N=130), resultados idénticos byte a byte
- [x] Parámetros: documentado el efecto de cada uno (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL) en la nueva sección "Parámetros del algoritmo — efecto de cada uno"
- [x] Storage: migrado `conjuntos_N/` de pickle a JSON (`json_act` en X0 y X1) — `conjunto_N` es solo un set de ~50-130 floats, parquet quedaba descartado por sobredimensionado; JSON permite inspeccionar los soportes a simple vista
- [x] Config: mover parámetros a un archivo de configuración separado (`config.py`)
- [x] Reorganizar `config.py` en grupos temáticos (rutas, activos, datos históricos, calidad del algoritmo, velocidad/cómputo, visualizaciones, trading) en vez del agrupamiento por script (X0/X1)
- [x] **Fix bug crítico en el optimizador**: condición de mejora `(FO_iter - FO_base) / FO_base > delta` era siempre falsa porque la FO es negativa — denominador negativo invertía el signo. Corregido a `/ abs(FO_base)`. El optimizador nunca había aceptado ningún cambio desde que la FO pasó a ser negativa.
- [x] **Fix bug `idxmax` con índices duplicados**: `df_plot` se construía con `pd.concat` acumulando filas con índice 0; `df_plot.loc[idxmax(), 'caso']` devolvía una Serie en vez de un escalar. Corregido con `argmax()` + `iloc`.
- [x] **Monitor de progreso en vivo**: `buscar_soportes` usa `multiprocessing.Manager().dict()` compartido entre workers + hilo monitor que redibuja una tabla cada segundo. Muestra por cada (valor, N): cambios aceptados, `max_pasos` (máximo de posiciones recorridas en el inner loop antes de aceptar un cambio), y FO actual. Workers corren con `verbose=False` (sin prints ni tqdm).
- [x] **Títulos en gráficos**: todas las funciones de visualización reciben `valor` y `N` y muestran título `"Tipo — VALOR N=N"`.
- [x] **Guardar plots en disco**: `plt.show()` reemplazado por `plt.savefig()` en `plots/{Extremos,FO,Soportes,Zoom}/{valor}_{N}.png`. Carpetas se crean automáticamente; archivos se sobreescriben.
- [x] **Info previa secuencial**: antes de lanzar el executor, `buscar_soportes` imprime en orden (sin mezcla) el rango de fechas, último cierre, warm start y delta para cada (valor, N).
- [x] Velocidad lógica del optimizador: `DELTA_INICIAL` adaptativo — delta se reduce (`* FACTOR_DELTA = 0.7`) solo cuando el optimizador converge; si no converge, el delta se mantiene. Estado persistido en `{valor}_{N}_delta.json` con `{'delta_inicial', 'convergio'}`. Órdenes activas de MT5 (`positions_get`) se pasan como soportes fijos al optimizador vía `obtener_ordenes_activas_mt5` (falla gracefully si MT5 no disponible). (I:6 C:5 H:3 → 0.85)

### X1 — X1_trading.py

- [x] Migrar X1 (notebook) a `scripts/X1_trading.py`
  - Mismas reglas que X0: solo lo estrictamente necesario, misma lógica
  - Agregada lógica: si pérdida > `PERDIDA_MAX` → cerrar la operación (`controlar_perdida_max`)

### X2 — X2_fundamentals.py

- [ ] Definir y evaluar fuentes de datos para X2: yfinance, MT5, investing.com, CoinGecko, Glassnode u otras. Qué cubre cada una, qué tan confiable y actualizable es. (I:5 C:2 H:8 → 3.16)
- [ ] **X2_fundamentals.py**: score fundamental por activo. Acciones: yfinance (ingresos, EPS, P/E, EV/EBITDA, ROE, ROA, FCF, deuda, market cap). Crypto: yfinance + fuentes on-chain (CoinGecko u otras). Output: score de confianza por activo en rango [0, 1]. (I:7 C:6 H:6 → 1.08)

### X3 — X3_technical_features.py

- [ ] **X3_technical_features.py**: indicadores técnicos (SMA, EMA, RSI, MACD, ATR, Bollinger, momentum, volatilidad, drawdown, tendencia, distancia a soportes). Variables de contexto operativo (precio, volumen relativo, capital disponible, exposición actual, órdenes abiertas, pérdida/ganancia flotante, densidad de soportes). (I:7 C:5 H:7 → 1.40)

### X4 — X4_backtester.py

- [ ] Definir schema del store de trades históricos: qué se guarda por cada orden simulada (activo, timestamps, precio entrada/salida, parámetros usados, features fundamentales y técnicas al momento de apertura, retorno, drawdown máximo, ganancia flotante máxima, duración, motivo de cierre). (I:5 C:2 H:9 → 3.35)
- [ ] **DELTA_INICIAL por (valor, N, version)**: en backtesting, `delta_inicial` depende solo del trío `(valor, N, version)`, no de `max_datetime`. Se ajusta con `FACTOR_DELTA` cada vez que el optimizador converge para ese trio, al igual que en producción. Archivo de estado: `{valor}_{N}_{version}_bt_delta.json` (I:7 C:3 H:8 → 2.49)
- [ ] **Config de versiones para backtesting**: sección en `config.py` con `version = 'V1'` (str activo) y `fechas_version = {'V1': ['2023-01-01', 'F']}`. `'F'` = hasta la última vela disponible. Al reiniciar con la misma versión, el sistema retoma desde el último snapshot guardado. Las órdenes simuladas se gatillan de forma ficticia sobre precios reales (I:8 C:5 H:8 → 1.60)
- [ ] **X4_backtester.py**: simulación histórica desde 2024-01-01 con parámetros dinámicos (búsqueda de nuevos soportes cada N días, cierre de operaciones por trailing stop o pérdida máxima, tracking de cuenta). Es la fuente primaria de training data para X5. (I:9 C:8 H:9 → 1.13)
- [x] **Fecha/hora máxima por tupla (valor, N) para backtesting**: `_procesar_valor_N` acepta `fecha_hora_max` opcional — filtra datos hasta ese datetime, usa warm start desde `{valor}_{N}_bt.json` (cache `{datetime: [soportes]}`), delta desde `{valor}_{N}_bt_delta.json`. Sin look-ahead: la clave guardada es `df['DateTime'].iloc[-1]` (último dato realmente usado). Lookup: `max(t1 <= t0)`. X4 llama esta función directamente con `fecha_hora_max=t`. X0 producción sin cambios. (I:10 C:5 H:8 → 1.26)
- [x] Evaluar incorporar X1.5_intravela al scope (renombrado de X2_Intravela; numeración 1.5 para no desplazar la visión) (I:6 C:7 H:5 → 0.78) — decisión: no es un script separado, la lógica va embebida en X4 como subrutina de simulación intra-vela. Ver `docs/decisiones.md` 2026-06-08.
- [x] Revisar los mensajes "SEGUIR EXPLICACION" en `prompts` (líneas 57 y 62) — quedaron explicaciones pendientes de continuar (lógica de `X2_Intravela` para el caso borde de abrir y cerrar una orden dentro de la misma vela horaria)

### X5 — X5_model_training.py

- [ ] **X5_model_training.py**: modelos supervisados sobre el store de trades. Predicciones: retorno esperado, probabilidad de pérdida, drawdown esperado, duración esperada. Evaluar overfitting (cross-val temporal, no aleatoria). Registrar qué modelos se probaron y por qué se eligió cada uno. (I:8 C:7 H:8 → 1.14)

### X6 — X6_macro_brain.py

- [ ] Definir schema de `config/active_parameters.json`: qué parámetros escribe X6 (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL, a, b, PERDIDA_MAX), con qué granularidad (por activo, global, o mixto). (I:5 C:2 H:7 → 2.96)
- [ ] Definir frecuencia de ejecución de X6: ¿diario? ¿antes de cada corrida de X0? ¿en el loop de X1? Requiere discusión. (I:4 C:2 H:5 → 2.24)
- [ ] **X6_macro_brain.py**: recomendación dinámica de parámetros. Lee features de X2/X3 y predicciones de X5. Output: `config/active_parameters.json` consumido por X0 y X1. Corre en Windows por ahora; idealmente compatible con Mac en el futuro. (I:9 C:8 H:5 → 0.84)

### Transversal

- [x] **Modificar skill `/todos`**: al preguntar qué sección elegir, mostrar nombre del grupo + cantidad de ítems pendientes + score del ítem más prioritario del grupo. Omitir grupos sin pendientes.
- [ ] Evaluar compatibilidad de librería MT5 en macOS — si se resuelve, simplifica mucho el flujo Mac↔Windows. (I:6 C:3 H:5 → 1.83)
- [x] Definir cuándo y cómo mergear `dev` → `master` (primera versión estable) — ver `docs/decisiones.md` 2026-06-07: merge solo tras validar X0+X1 en Windows con MT5 real, vía merge commit normal (sin squash)
- [x] Crear skill/comando `/push` para git push a rama desde Claude Code (I:3 C:2 H:4 → 1.73) — cubierto por la skill global `/update-push` (commit + push a la rama actual, con actualización de CLAUDE.md/README.md)
- [x] **BIG PICTURE**: Mauricio explicó la visión completa — ver `docs/vision.md`. Arquitectura X0→X6 definida, orden de construcción declarado, decisiones de diseño registradas. (I:9 C:8 H:9 → 1.13)
- [x] Rama `base_v0` → estado original (notebooks, estructura Windows)
- [x] Rama `dev` → trabajo activo. Push inicial: migración X0 + X1 a .py
- [x] Próximo push a `dev`: después de mejoras X0 (paralelización, velocidad) — ya estaba en `origin/dev` (commits hasta `c92a8f0`)

---

## Referencia base

`Alginvesting_base/` contiene la versión anterior (Windows, notebooks). Solo lectura. No modificar.

---

## Última actualización

**2026-06-11** — N_MAX_MODELS + loop continuo en X0_data_supports.py

`N_MAX_MODELS = None` en `config.py` (None = todos los combos, entero = top N por delta). Nuevo helper `_seleccionar_combos`: lee `delta_inicial` de cada `_delta.json`, ordena desc por delta (tie-break random), retorna los top N_MAX_MODELS. `buscar_soportes` acepta `n_max` y delega en el helper. `--loop` flag en argparse: activa `while True` que reinicia el ciclo completo (descarga + soportes) al terminar. Sin `--loop`, comportamiento idéntico al anterior. Ctrl+C sale limpiamente mostrando cuántos ciclos corrieron.

**2026-06-11** — Logs de convergencia implementados en X0_data_supports.py

`_guardar_log_convergencia` en `X0_data_supports.py`: al terminar cada `_procesar_valor_N`, guarda entrada JSON en `docs/X0/logs/{valor}_{N}.json` (producción) o `{valor}_{N}_bt.json` (bt). Campos: `clave`, `t_inicio`, `t_fin`, `duracion_s`, `iteraciones`, `cambios`, `FO_inicial`, `FO_final`, `delta_final`, `convergio`. Cada archivo es una lista que se acumula entre corridas. `t_inicio` capturado al inicio de la función (incluye carga de datos + distancias + optimizador). `CARPETA_LOGS` agregado a `config.py`.

**2026-06-11** — Análisis de convergencia de `nuevo_optimizador_2` + X0_aux al TO DO

7 sugerencias de mejora documentadas en `docs/documentacion_V0.md`: FO incremental (~30-35x en eval FO), inicialización inteligente (60-80% menos iters en cold start), M adaptativo coarse-to-fine (~58% menos evaluaciones), priorización por historial, activar `prueba_cercanos`, vectorización del loop M, y criterio de parada por tasa. Agregado ítem `X0_aux.py` al TO DO de X0 (I:6 C:3 H:7 → 2.16) como fase 2 de esta etapa. Sin cambios de código en producción.

**2026-06-10** — TO DO: nuevos ítems X0/X4 + skill /todos completada

Agregados 4 ítems al TO DO: "Formato outputs en paralelo" (X0, baja prioridad), "DELTA_INICIAL por (valor, N, version)" (X4, score 2.49), "Config versiones backtesting" (X4, score 1.60), y "Modificar skill /todos" (Transversal — marcado directamente como completado, ya estaba implementado). Confirmada la lógica de diseño: DELTA en backtesting depende solo de (valor, N, version), no de max_datetime.

**2026-06-10** — Fixes al optimizador + monitor de progreso en vivo + mejoras de visualización

Fix crítico: condición de mejora en `nuevo_optimizador_2` usaba `FO_base` (negativo) en el denominador — el optimizador nunca había aceptado cambios. Corregido con `abs(FO_base)`. Fix secundario: `df_plot.loc[idxmax()]` fallaba con índices duplicados tras `pd.concat`; corregido con `argmax()` + `iloc`. Implementado monitor de progreso en vivo: `multiprocessing.Manager().dict()` compartido entre workers + hilo monitor que redibuja tabla cada segundo (cambios, max_pasos, FO, estado). Workers con `verbose=False` suprimen tqdm y prints. Info previa por combo (rango, cierre, warm start, delta) se imprime secuencialmente antes del executor. Plots guardados en `plots/{Extremos,FO,Soportes,Zoom}/{valor}_{N}.png` en vez de `plt.show()`. Títulos con `"Tipo — VALOR N=N"` en todos los gráficos. `buscar_soportes` omite activos ausentes en `n_sizes`.

**2026-06-09** — conjuntos_N + sin _beta + bt cache para backtesting

Renombrada carpeta `conjuntosN2/` → `conjuntos_N/`. Eliminado sufijo `_beta`: X0 escribe directo a `{VALOR}_{N}.json`, X1 lee directo desde ahí; eliminada `promover_a_productivo` y su import `shutil`. Implementado cache de backtesting: `_bt_warm_start` y `_bt_guardar` en `X0_data_supports.py`; parámetro `fecha_hora_max=None` en `_procesar_valor_N` — cuando se pasa un datetime activa modo bt (filtra datos, warm start desde `_bt.json`, delta desde `_bt_delta.json`, upsert con clave = último datetime real usado). Prioridad 0 del TO DO marcada como completada.

**2026-06-09** — TO DO: fecha máxima por tupla valor-N en X4 (Prioridad 0)

Nuevo ítem en Prioridad 0: la estimación de soportes en el tiempo `t` debe usar solo velas hasta `t` (sin look-ahead), y la búsqueda debe ser un continuo temporal que actualiza `delta_inicial` progresivamente. Pendiente integrar con `_procesar_valor_N` y `{valor}_{N}_delta.json`. Se limpió texto suelto que había quedado en la sección Pendientes. Se eliminó el ítem "Backtesting histórico (X4)" del TO DO Principal (ya cubierto en TO DO Visión bajo X4_backtester).

**2026-06-08** — Diseño simulación intra-vela para X4_backtester

X1.5_intravela como script separado descartado. La lógica de simulación intra-vela se embebe en X4 como subrutina. Se agrega `Data_minuto/` al proyecto (CSVs M1, fuera de git, alimentados incrementalmente). Diseño del trigger: `hay_soporte_en_rango = Low <= max(soportes_activos)` AND (`H-L > A/(lot*units)` OR `H-L > PERDIDA_MAX/(lot*units)`). Escalado intra-vela: bloque aleatorio de 60 registros M1 escalado linealmente para calzar el OHLC de la vela horaria. Ver `docs/decisiones.md` 2026-06-08.

**2026-06-08** — Visión: arquitectura X0→X6 + TO DO Visión en CLAUDE.md

Se explicitó la visión completa del proyecto en `docs/vision.md`: arquitectura X0→X6 con X1.5_intravela en posición intermedia, decisiones de diseño (dónde corre X6, fuentes de training data, orden de construcción X2→X3→X4→X5→X6). Se creó el capítulo "TO DO Visión" en CLAUDE.md con 11 ítems organizados en 3 fases (Datos/features, Backtesting, Modelo/cerebro) más infraestructura transversal. BIG PICTURE marcado como completado.

**2026-06-08** — DELTA_INICIAL adaptativo + órdenes activas fijas en optimizador

Se refinó la lógica de `DELTA_INICIAL` adaptativo: el delta ahora solo se reduce (`* FACTOR_DELTA = 0.7`, antes `LAMBDA_DELTA = 0.9` en cada corrida) cuando el optimizador realmente converge — es decir, cuando sale por el break de "ningún soporte mejoró tras recorrer todos" y no por `max_iters`. `nuevo_optimizador_2` retorna `convergio: bool`; `_procesar_valor_N` aplica el factor solo si `convergio=True` y persiste `{'delta_inicial', 'convergio'}` en `{valor}_{N}_delta.json`.

Además, se implementó la integración de órdenes activas de MT5 como soportes fijos en el optimizador: `obtener_ordenes_activas_mt5(valores)` consulta `positions_get` (posiciones ejecutadas, no pendientes), hace su propio init/shutdown de MT5, y falla gracefully en Mac. El dict resultante se pasa a `buscar_soportes` → cada worker → `nuevo_optimizador_2` vía `ordenes_activas` (parámetro que ya existía pero siempre recibía `[]`).

**2026-06-07** — `DELTA_INICIAL` adaptativo entre corridas

Se conectó `DELTA_INICIAL` a `nuevo_optimizador_2` (hasta ahora no estaba enlazado — el optimizador usaba su propio default) y se hizo adaptativo *entre* corridas sucesivas de cada combo (valor, N): si existe estado previo en `conjuntos_N/{valor}_{N}_delta.json`, se usa `delta_actual = LAMBDA_DELTA * delta_previo` (`LAMBDA_DELTA = 0.9` en `config.py`); si no existe (cold start), se usa `DELTA_INICIAL` como semilla. La lógica: con warm start cercano al óptimo, exigir mejoras relativas cada vez más finas no dispara un costo proporcional en iteraciones, así que se puede "presionar" la precisión sin pagar el precio de un cold start. El estado se persiste en un archivo separado por combo (no junto a `conjunto_N`, para no tocar el formato que consume X1, y para evitar carreras con `ProcessPoolExecutor`). Detalle y alternativas descartadas en `docs/decisiones.md` 2026-06-07.

Además se agregó la sección "Prioridad 0" en el TO DO: revisar los mensajes "SEGUIR EXPLICACION" pendientes en `prompts` (explicaciones inconclusas sobre `X2_Intravela`).

**2026-06-07** — Agregar volumen (`v`) y fuerza del rechazo (`f`) al scoring de soportes y hacer el cálculo de `z` configurable

A partir de la revisión de la lógica de `calcular_FO` (TO DO "Revisar con Mauricio..."), se agregaron dos factores nuevos:
- `v` (volumen normalizado: `Tick_Volume / Tick_Volume.max()`, en `[0,1]`) como proxy de actividad/participación en cada nivel de precio — se usa `Tick_Volume` porque `Real_Volume` viene vacío (0.0) en los 10 CSV de `Data/`, consistente entre todos los activos.
- `f` (fuerza del rechazo: `1 - |Close - Open| / (High - Low)`, en `[0,1]`) — proporción del rango de la vela que fue "mecha" en vez de cuerpo; mide cuán abrupto fue el rebote del precio al tocar el extremo, de forma direccional-agnóstica (consistente con cómo `y` ya combina aislamiento de `Low` y `High`).

`z` deja de ser un producto fijo (`y * w * h_dist`) y pasa a ser el producto de los factores activos en el nuevo diccionario `parametros_soportes` (`config.py`), que permite activar/desactivar cada uno (`y`, `w`, `h_dist`, `v`, `f`) para experimentar con el scoring sin tocar el código. Cambios en `obtener_df_extremos` (cálculo de `v` y `f`) y `calcular_FO` (`z = df_extremos[factores].prod(axis=1)`) en `X0_data_supports.py`.

**2026-06-07** — Renombrar transversal.py a config.py y centralizar parámetros

`Transversal.py` pasa a llamarse `config.py` y concentra ahora todos los parámetros del proyecto: lo que ya tenía (`n_sizes`, `n_sizes_ejecucion`) más rutas (`BASE_DIR`, `CARPETA_DATA`, `CARPETA_N2`), `VALORES`, y los parámetros que estaban hardcodeados directamente en `X0_data_supports.py` (`FECHA_INICIAL`, `K`, `N_EXP`, `BLOQUE_DISTANCIAS`, `M`, `LAMBDA`, `MAX_ITERS`, `DELTA_INICIAL`, flags `GRAFICAR_*`) y en `X1_trading.py` (`A`, `B`, `TS`, `PERDIDA_MAX`, `PRUEBA_TRAILING_STOP`, `LOTAJES`, `UNITS`). Ambos scripts ahora importan todo desde `config`. Se unificó el orden de `VALORES` (difería entre X0 y X1) al de X0. Ver `docs/decisiones.md` para el detalle de la decisión y por qué se optó por consolidar todo en un solo archivo en lugar de la opción acotada que había quedado registrada en `docs/records.md`.

**2026-06-07** — Migrar conjuntosN2 de pickle a JSON

`conjunto_N` es solo un `set` de ~50-130 floats (niveles de precio) — pickle no aportaba nada frente a JSON, que además permite inspeccionar los soportes a simple vista (parquet quedó descartado por sobredimensionado para este tamaño). `pickle_act` se reemplazó por `json_act` en `X0_data_supports.py` y `X1_trading.py` (`sorted(set)` al guardar, `set(list)`/`list` al cargar), y los archivos pasan de `{valor}_{N}_beta.pkl` / `{valor}_{N}.pkl` a `.json` en todo el flujo (warm start, guardado, `promover_a_productivo`, `leer_lista_N`). Se quitó `*.pkl` de `.gitignore` (redundante, `conjuntos_N/` ya está ignorado como carpeta).

**2026-06-07** — Vectorizar calcular_distancias + asignar_soporte, setup skills record/guardar

`calcular_distancias` en `X0_data_supports.py` reemplaza el doble loop O(n²) con `.loc` por `_vecino_mas_cercano`, vectorizado con numpy por bloques (`BLOQUE_DISTANCIAS`). Resultados idénticos byte a byte, ~19x más rápido (33.9s → 1.8s en BTCUSD, n=21.213). `asignar_soporte` reemplaza el `apply` con `min(soportes, key=...)` (O(n×N)) por `np.searchsorted` (búsqueda binaria, O(n log N)) — ~45-178x más rápido (0.26s → 0.0014s en BTCUSD, N=130), mismos resultados byte a byte; relevante porque `calcular_FO` la invoca miles de veces por iteración del optimizador. Se agregó la sección "Parámetros del algoritmo — efecto de cada uno" documentando qué hace subir/bajar cada uno (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL). `Data/` pasa a trackearse en git (revierte la decisión del 2026-06-03): MT5 solo entrega ~1000 velas por descarga, así que sin el CSV existente se pierde la historia previa a `FECHA_INICIAL=2024-01-01`. Se crearon las skills globales `record` y `guardar` (registro de sesiones en `docs/records.md` + commit/push encadenado).

**2026-06-06** — Paralelizar búsqueda de soportes por (valor, N)

`n_sizes` en `Transversal.py` pasa de un único N por activo a una lista de N candidatos (grid search: 50 a 120). `buscar_soportes` en `X0_data_supports.py` ahora arma todos los pares `(valor, N)` y los procesa en paralelo con `ProcessPoolExecutor` vía `_procesar_valor_N`. `promover_a_productivo` itera sobre cada N de la lista.
