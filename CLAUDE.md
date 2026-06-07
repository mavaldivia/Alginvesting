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
- `Data/` se trackea en git (ver `docs/decisiones.md` 2026-06-07): contiene la historia de precios desde 2024-01-01 y MT5 solo entrega las últimas ~1000 velas, así que sin el CSV existente se pierde todo lo anterior. `conjuntosN2/` (pickles de soportes) sigue fuera de git, se regenera corriendo X0.

---

## Arquitectura

### Scripts principales (en `scripts/`)

| Archivo | Propósito |
|---|---|
| `X0_data_supports.py` | **Etapa 1**: Descarga/actualiza CSVs de precios vía MT5. **Etapa 2**: Encuentra los N soportes/resistencias óptimos y los guarda en `conjuntosN2/` como pickle. `--opcion 0/1/2` |
| `X1_trading.py` | Loop semi-automático (`while True`): lee soportes, gestiona buy limits en MT5, trailing stop, y cierra posiciones si pérdida > `PERDIDA_MAX`. |
| `transversal.py` | Parámetros globales: `n_sizes`, `n_sizes_ejecucion`. |

### Directorios de datos

| Carpeta | Contenido |
|---|---|
| `Data/` | CSVs OHLCV por activo (BTCUSD, ETHUSD, TSLA, GOOGL, NVDA, AMZN) — actualizados por X0, **trackeados en git** (historia desde 2024-01-01) |
| `conjuntosN2/` | Pickles con N soportes óptimos por activo — `{VALOR}_{N}_beta.pkl` (en optimización) / `{VALOR}_{N}.pkl` (productivo) — generados, fuera de git |

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
- Parámetros clave centralizados en `transversal.py`.
- Pickles con sufijo `_beta` = versión en optimización (no productiva).
- Sin hardcodear rutas fuera de `transversal.py`.
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
- [ ] Velocidad: `calcular_FO` llama `asignar_soporte` con `apply` O(n×N) — evaluar `cdist` o broadcasting
- [ ] Parámetros: documentar mejor el efecto de cada parámetro (N, LAMBDA, K, N_EXP, M, DELTA_INICIAL)
- [ ] Storage: evaluar si pickle es lo mejor para `conjuntosN2/` o si conviene JSON/parquet
- [ ] Config: mover parámetros a un archivo de configuración separado (`config.py`)

### Infraestructura
- [x] Rama `base_v0` → estado original (notebooks, estructura Windows)
- [x] Rama `dev` → trabajo activo. Push inicial: migración X0 + X1 a .py
- [ ] Próximo push a `dev`: después de mejoras X0 (paralelización, velocidad)
- [ ] Definir cuándo y cómo mergear `dev` → `master` (primera versión estable)
- [ ] Crear skill/comando `/push` para git push a rama desde Claude Code

### Backlog
- [ ] **BIG PICTURE**: Mauricio tiene que explicar la visión completa del proyecto — hacia dónde va, qué quiere lograr con esta base, qué es realmente Alginvesting a largo plazo. Hacer esto antes de tomar decisiones de arquitectura mayores.
- [ ] Backtesting histórico: simular desde enero 2026 con parámetros dinámicos (búsqueda de nuevos soportes, cierre de operaciones, tracking de cuenta)
- [ ] Evaluar incorporar X2_Intravela al scope
- [ ] Separar descarga de datos en módulo independiente (hoy está en X0)

---

## Referencia base

`Alginvesting_base/` contiene la versión anterior (Windows, notebooks). Solo lectura. No modificar.

---

## Última actualización

**2026-06-07** — Vectorizar calcular_distancias + setup skills record/guardar

`calcular_distancias` en `X0_data_supports.py` reemplaza el doble loop O(n²) con `.loc` por `_vecino_mas_cercano`, vectorizado con numpy por bloques (`BLOQUE_DISTANCIAS`). Resultados idénticos byte a byte, ~19x más rápido (33.9s → 1.8s en BTCUSD, n=21.213). `Data/` pasa a trackearse en git (revierte la decisión del 2026-06-03): MT5 solo entrega ~1000 velas por descarga, así que sin el CSV existente se pierde la historia previa a `FECHA_INICIAL=2024-01-01`. Se crearon las skills globales `record` y `guardar` (registro de sesiones en `docs/records.md` + commit/push encadenado).

**2026-06-06** — Paralelizar búsqueda de soportes por (valor, N)

`n_sizes` en `Transversal.py` pasa de un único N por activo a una lista de N candidatos (grid search: 50 a 120). `buscar_soportes` en `X0_data_supports.py` ahora arma todos los pares `(valor, N)` y los procesa en paralelo con `ProcessPoolExecutor` vía `_procesar_valor_N`. `promover_a_productivo` itera sobre cada N de la lista.
