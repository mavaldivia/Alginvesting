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
- Los archivos generados (`Data/`, `conjuntosN2/`) se crean en Windows al correr X0, no se trackean en git.

---

## Arquitectura

### Scripts principales (en `scripts/`)

| Archivo | Propósito |
|---|---|
| `X0_data_supports.py` | **Etapa 1**: Descarga/actualiza CSVs de precios vía MT5. **Etapa 2**: Encuentra los N soportes/resistencias óptimos y los guarda en `conjuntosN2/` como pickle. `--opcion 0/1/2` |
| `X1_trading.py` | Loop semi-automático (`while True`): lee soportes, gestiona buy limits en MT5, trailing stop, y cierra posiciones si pérdida > `PERDIDA_MAX`. |
| `transversal.py` | Parámetros globales: `n_sizes`, `n_sizes_ejecucion`. |

### Directorios de datos (generados, no en git)

| Carpeta | Contenido |
|---|---|
| `Data/` | CSVs OHLCV por activo (BTCUSD, ETHUSD, TSLA, GOOGL, NVDA, AMZN) — actualizados por X0 |
| `conjuntosN2/` | Pickles con N soportes óptimos por activo — `{VALOR}_{N}_beta.pkl` (en optimización) / `{VALOR}_{N}.pkl` (productivo) |

---

## Conceptos clave del dominio

- **N (n_sizes)**: Cantidad de soportes a mantener activos por activo. Varía por activo: BTCUSD/ETHUSD=130, resto=120.
- **M**: Cantidad de soportes candidatos (pool mayor del que se selecciona N).
- **Conjunto N**: Los N soportes óptimos elegidos por el algoritmo de optimización.
- **OA / OE**: Órdenes Abiertas (posición activa) / Órdenes en Espera (buy limit pendiente).
- **Trailing Stop**: SL que sigue el precio hacia arriba para proteger ganancias.
- **Beta**: Riesgo por operación como % de cuenta.
- **T**: Ventana de días históricos usada para calcular soportes (default: 60).
- **lambda_ponderador**: Ponderador en la función objetivo que balancea calidad de soportes vs. dispersión entre ellos.

---

## Algoritmo de búsqueda de soportes (X0)

1. Calcular `df_extremos`: para cada vela, distancias al mínimo anterior/futuro más cercano.
2. Generar M candidatos (particiones uniformes del rango de precios).
3. Optimización iterativa: reemplazar uno a uno los elementos del conjunto N por candidatos de M, eligiendo el que mejore la función objetivo (FO).
4. FO: mide qué tan bien los N soportes "atraen" los mínimos históricos, penalizando distribución desigual entre soportes.
5. Versión activa: `nuevo_optimizador_2` (la más reciente en X0).

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
- [ ] **Paralelización**: la búsqueda de soportes es independiente por cada par (valor, N) → paralelizar con `multiprocessing` o `concurrent.futures`. Ej: BTCUSD-130, ETHUSD-130, TSLA-120, etc. corriendo simultáneamente.
- [ ] Velocidad: `calcular_distancias` es O(n²) con loops Python puros — evaluar vectorización numpy
- [ ] Velocidad: `calcular_FO` llama `asignar_soporte` con `apply` O(n×N) — evaluar `cdist` o broadcasting
- [ ] Parámetros: documentar mejor el efecto de cada parámetro (N, LAMBDA, K, N_EXP, M, DELTA_INICIAL)
- [ ] Storage: evaluar si pickle es lo mejor para `conjuntosN2/` o si conviene JSON/parquet
- [ ] Config: mover parámetros a un archivo de configuración separado (`config.py`)

### Infraestructura
- [ ] Crear skill/comando `/push` para git push a rama desde Claude Code
- [ ] Definir estrategia de ramas (main productivo, feature branches) — revisar pronto

### Backlog
- [ ] **BIG PICTURE**: Mauricio tiene que explicar la visión completa del proyecto — hacia dónde va, qué quiere lograr con esta base, qué es realmente Alginvesting a largo plazo. Hacer esto antes de tomar decisiones de arquitectura mayores.
- [ ] Backtesting histórico: simular desde enero 2026 con parámetros dinámicos (búsqueda de nuevos soportes, cierre de operaciones, tracking de cuenta)
- [ ] Evaluar incorporar X2_Intravela al scope
- [ ] Separar descarga de datos en módulo independiente (hoy está en X0)

---

## Referencia base

`Alginvesting_base/` contiene la versión anterior (Windows, notebooks). Solo lectura. No modificar.
