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
- `Data/` se trackea en git (ver `docs/decisiones.md` 2026-06-07): contiene la historia de precios desde 2024-01-01 y MT5 solo entrega las últimas ~1000 velas, así que sin el CSV existente se pierde todo lo anterior. `conjuntosN2/` (JSONs de soportes) sigue fuera de git, se regenera corriendo X0.

---

## Arquitectura

### Scripts principales (en `scripts/`)

| Archivo | Propósito |
|---|---|
| `X0_data_supports.py` | **Etapa 1**: Descarga/actualiza CSVs de precios vía MT5. **Etapa 2**: Encuentra los N soportes/resistencias óptimos y los guarda en `conjuntosN2/` como JSON. `--opcion 0/1/2` |
| `X1_trading.py` | Loop semi-automático (`while True`): lee soportes, gestiona buy limits en MT5, trailing stop, y cierra posiciones si pérdida > `PERDIDA_MAX`. |
| `config.py` | Parámetros centralizados: rutas, `VALORES`, `n_sizes`, `n_sizes_ejecucion`, y configuración de X0 (algoritmo) y X1 (trading). |

### Directorios de datos

| Carpeta | Contenido |
|---|---|
| `Data/` | CSVs OHLCV por activo (BTCUSD, ETHUSD, TSLA, GOOGL, NVDA, AMZN) — actualizados por X0, **trackeados en git** (historia desde 2024-01-01) |
| `conjuntosN2/` | JSONs con N soportes óptimos por activo — `{VALOR}_{N}_beta.json` (en optimización) / `{VALOR}_{N}.json` (productivo) — generados, fuera de git |

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

### Paso 3 — Función objetivo (`calcular_FO`)
Se asigna cada vela al soporte más cercano del conjunto N. Luego:
- `h_dist = 1 - dist²/dist_max` (proximidad normalizada al soporte asignado)
- `z = y * w * h_dist`
- `FO = mean(z) - LAMBDA * cv(H_n)`
  - `mean(z)`: calidad promedio de asignación (aislamiento × recencia × proximidad)
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
- Pickles con sufijo `_beta` = versión en optimización (no productiva).
- Sin hardcodear rutas fuera de `config.py`.
- `docs/decisiones.md` registra decisiones técnicas relevantes.

---

## TO DO

### Inmediato
- [x] Migrar X0 (notebook) a `scripts/X0_data_supports.py`
- [x] Migrar X1 (notebook) a `scripts/X1_trading.py`
  - Mismas reglas que X0: solo lo estrictamente necesario, misma lógica
  - Agregada lógica: si pérdida > `PERDIDA_MAX` → cerrar la operación (`controlar_perdida_max`)

### Mejoras X0 (después de migrar X1)
- [x] **Paralelización**: la búsqueda de soportes es independiente por cada par (valor, N) → paralelizar con `multiprocessing` o `concurrent.futures`. Ej: BTCUSD-130, ETHUSD-130, TSLA-120, etc. corriendo simultáneamente.
- [x] Velocidad: `calcular_distancias` vectorizada con numpy por bloques (evita matriz n×n completa) — ~19x más rápido (33.9s → 1.8s en BTCUSD, n=21213), resultados idénticos byte a byte
- [x] Velocidad: `asignar_soporte` vectorizada con `np.searchsorted` (búsqueda binaria del soporte más cercano, O(n log N) en vez de O(n×N) con `apply`) — ~45-178x más rápido (0.26s → 0.0014s en BTCUSD, N=130), resultados idénticos byte a byte
- [x] Parámetros: documentado el efecto de cada uno (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL) en la nueva sección "Parámetros del algoritmo — efecto de cada uno"
- [x] Storage: migrado `conjuntosN2/` de pickle a JSON (`json_act` en X0 y X1) — `conjunto_N` es solo un set de ~50-130 floats, parquet quedaba descartado por sobredimensionado; JSON permite inspeccionar los soportes a simple vista
- [x] Config: mover parámetros a un archivo de configuración separado (`config.py`)
- [ ] Reorganizar `config.py` en grupos temáticos (ej. velocidad del modelo, performance/calidad del modelo, visualizaciones, etc.) en vez del agrupamiento actual por script (X0/X1)
- [ ] Velocidad lógica del optimizador: explorar `DELTA_INICIAL` adaptativo — partir con un umbral más alto y, si ningún soporte/resistencia logra superarlo, bajarlo progresivamente (en vez de un valor fijo)
- [ ] Revisar con Mauricio la lógica de scoring de `calcular_FO` (qué hace que un punto sea buen soporte/resistencia) — discutir si vale la pena agregar algo al cálculo actual de `y`, `w`, `h_dist`

### Infraestructura
- [x] Rama `base_v0` → estado original (notebooks, estructura Windows)
- [x] Rama `dev` → trabajo activo. Push inicial: migración X0 + X1 a .py
- [x] Próximo push a `dev`: después de mejoras X0 (paralelización, velocidad) — ya estaba en `origin/dev` (commits hasta `c92a8f0`)
- [ ] Crear skill/comando `/push` para git push a rama desde Claude Code
- [ ] Definir cuándo y cómo mergear `dev` → `master` (primera versión estable)

### Backlog
- [ ] Separar descarga de datos en módulo independiente (hoy está en X0)
- [ ] Evaluar incorporar X2_Intravela al scope
- [ ] **BIG PICTURE**: Mauricio tiene que explicar la visión completa del proyecto — hacia dónde va, qué quiere lograr con esta base, qué es realmente Alginvesting a largo plazo. Hacer esto antes de tomar decisiones de arquitectura mayores.
- [ ] Backtesting histórico: simular desde enero 2026 con parámetros dinámicos (búsqueda de nuevos soportes, cierre de operaciones, tracking de cuenta)

---

## Referencia base

`Alginvesting_base/` contiene la versión anterior (Windows, notebooks). Solo lectura. No modificar.

---

## Última actualización

**2026-06-07** — Renombrar transversal.py a config.py y centralizar parámetros

`Transversal.py` pasa a llamarse `config.py` y concentra ahora todos los parámetros del proyecto: lo que ya tenía (`n_sizes`, `n_sizes_ejecucion`) más rutas (`BASE_DIR`, `CARPETA_DATA`, `CARPETA_N2`), `VALORES`, y los parámetros que estaban hardcodeados directamente en `X0_data_supports.py` (`FECHA_INICIAL`, `K`, `N_EXP`, `BLOQUE_DISTANCIAS`, `M`, `LAMBDA`, `MAX_ITERS`, `DELTA_INICIAL`, flags `GRAFICAR_*`) y en `X1_trading.py` (`A`, `B`, `TS`, `PERDIDA_MAX`, `PRUEBA_TRAILING_STOP`, `LOTAJES`, `UNITS`). Ambos scripts ahora importan todo desde `config`. Se unificó el orden de `VALORES` (difería entre X0 y X1) al de X0. Ver `docs/decisiones.md` para el detalle de la decisión y por qué se optó por consolidar todo en un solo archivo en lugar de la opción acotada que había quedado registrada en `docs/records.md`.

**2026-06-07** — Migrar conjuntosN2 de pickle a JSON

`conjunto_N` es solo un `set` de ~50-130 floats (niveles de precio) — pickle no aportaba nada frente a JSON, que además permite inspeccionar los soportes a simple vista (parquet quedó descartado por sobredimensionado para este tamaño). `pickle_act` se reemplazó por `json_act` en `X0_data_supports.py` y `X1_trading.py` (`sorted(set)` al guardar, `set(list)`/`list` al cargar), y los archivos pasan de `{valor}_{N}_beta.pkl` / `{valor}_{N}.pkl` a `.json` en todo el flujo (warm start, guardado, `promover_a_productivo`, `leer_lista_N`). Se quitó `*.pkl` de `.gitignore` (redundante, `conjuntosN2/` ya está ignorado como carpeta).

**2026-06-07** — Vectorizar calcular_distancias + asignar_soporte, setup skills record/guardar

`calcular_distancias` en `X0_data_supports.py` reemplaza el doble loop O(n²) con `.loc` por `_vecino_mas_cercano`, vectorizado con numpy por bloques (`BLOQUE_DISTANCIAS`). Resultados idénticos byte a byte, ~19x más rápido (33.9s → 1.8s en BTCUSD, n=21.213). `asignar_soporte` reemplaza el `apply` con `min(soportes, key=...)` (O(n×N)) por `np.searchsorted` (búsqueda binaria, O(n log N)) — ~45-178x más rápido (0.26s → 0.0014s en BTCUSD, N=130), mismos resultados byte a byte; relevante porque `calcular_FO` la invoca miles de veces por iteración del optimizador. Se agregó la sección "Parámetros del algoritmo — efecto de cada uno" documentando qué hace subir/bajar cada uno (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL). `Data/` pasa a trackearse en git (revierte la decisión del 2026-06-03): MT5 solo entrega ~1000 velas por descarga, así que sin el CSV existente se pierde la historia previa a `FECHA_INICIAL=2024-01-01`. Se crearon las skills globales `record` y `guardar` (registro de sesiones en `docs/records.md` + commit/push encadenado).

**2026-06-06** — Paralelizar búsqueda de soportes por (valor, N)

`n_sizes` en `Transversal.py` pasa de un único N por activo a una lista de N candidatos (grid search: 50 a 120). `buscar_soportes` en `X0_data_supports.py` ahora arma todos los pares `(valor, N)` y los procesa en paralelo con `ProcessPoolExecutor` vía `_procesar_valor_N`. `promover_a_productivo` itera sobre cada N de la lista.
