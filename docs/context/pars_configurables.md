# Parámetros configurables — definición exacta

Definición de los parámetros de `scripts/config.py` que X5 explora/optimiza por activo (`X5_PARAM_RANGES`, `config.py:316-329`), más los parámetros de scoring de X0 que los acompañan. Todos son por activo salvo donde se indica lo contrario. Valores listados = producción actual (`config.py`), no defaults de funciones.

---

## Parámetros de trading y gestión de riesgo (X1)

### A — margen de activación (USD)

Cumple dos roles en `X1_trading.py`, ambos como umbral de distancia en dólares:

1. **Filtro de creación de Órdenes en Espera (OE)** — en `crear_ordenes_espera` (`X1_trading.py:395-428`): un soporte solo recibe un buy limit si `(P0 - Pi) * L >= A`, donde `P0` es el precio actual, `Pi` el precio del soporte y `L = LOTAJES[valor] * UNITS[valor]` la exposición en USD por unidad de precio.
2. **Ganancia mínima para activar el primer Stop Loss (SL) ganador** — en `trailing_stop` (`X1_trading.py:480-529`): mientras la posición no tiene SL, se le pone el primero cuando `ganancia = (P0 - Pi) * L >= A`.

- **Ubicación**: `config.py:171-178`
- **Valor actual**: `3` (USD) para todos los activos
- **Rango de exploración X5**: `(2.0, 20.0)` (`config.py:320`)
- **↑ A**: exige que el precio se aleje más antes de abrir una OE nueva (menos órdenes activas, más espaciadas) y retrasa la activación del primer SL ganador (más margen antes de "asegurar" ganancia, pero más riesgo de devolver ganancia no realizada si el precio revierte).
- **↓ A**: OE más densas cerca del precio y SL ganador se activa con menos ganancia acumulada (protege antes, pero puede sacar de la posición con ganancias mínimas por ruido).

### B — distancia del trailing stop (USD)

Una vez que una posición ya tiene SL activo, `B` define a qué distancia en USD se mantiene el SL bajo el precio actual. En `trailing_stop` (`X1_trading.py:480-529`): `sl_nuevo = P0 - B / L`. El SL solo se mueve al alza (`sl_nuevo > sl` actual), nunca baja.

- **Ubicación**: `config.py:180-187`
- **Valor actual**: `1.5` (USD) para todos los activos
- **Rango de exploración X5**: `(0.5, 5.0)` (`config.py:321`)
- **↑ B**: SL más holgado — menos probabilidad de ser ejecutado por ruido de corto plazo, pero devuelve más ganancia flotante si el precio revierte antes de seguir subiendo.
- **↓ B**: SL más ajustado al precio — asegura ganancia más rápido, pero mayor probabilidad de cerrar la posición por una corrección menor antes de que continúe la tendencia.

> Nota: `A` y `B` no son directamente comparables en magnitud pese a estar en la misma unidad (USD) — `A` es un umbral de *ganancia acumulada* para gatillar el trailing, `B` es la *distancia que se mantiene* una vez gatillado.

### PERDIDA_MAX — pérdida máxima antes de cierre forzado (USD)

En `controlar_perdida_max` (`X1_trading.py:556-565`): si `perdida = (Pi - P0) * L > PERDIDA_MAX`, la posición se cierra a mercado de inmediato (`cerrar_posicion`), independiente del estado del trailing stop.

- **Ubicación**: `config.py:196-203`
- **Valor actual**: `120` (USD) para todos los activos
- **Rango de exploración X5**: `(100, 300)` (`config.py:328`)
- **↑ PERDIDA_MAX**: tolera mayor drawdown por posición antes de cortar — más margen para que el precio se recupere, pero mayor pérdida máxima realizable por operación.
- **↓ PERDIDA_MAX**: corta pérdidas antes — limita el downside por operación, pero mayor probabilidad de cerrar posiciones que habrían recuperado con más tiempo.

### LOTAJES_M — multiplicador de lote

Multiplicador aplicado al lote mínimo del broker: `LOTAJES[v] = LOTAJES_M[v] * MIN_LOTAJES[v]` (`config.py:216-226`). `LOTAJES_M` es el único de estos parámetros que actualmente **no varía** — está fijo en `1` para todos los activos y su rango de exploración en X5 es degenerado (`(1, 1)`), porque X5 siempre opera a lotaje mínimo por diseño.

- **Ubicación**: `config.py:216-223`
- **Valor actual**: `1` para todos los activos
- **Rango de exploración X5**: `(1, 1)` — fijo, no se explora (`config.py:327`, comentario explícito: "X5 siempre opera a lotaje mínimo")
- **↑ LOTAJES_M** (si se habilitara): mayor exposición en USD por posición (`L = LOTAJES[valor] * UNITS[valor]` crece) — amplifica tanto ganancias como pérdidas de cada trade, y con ello el efecto de `A`, `B` y `PERDIDA_MAX` (todos dependen de `L`).
- **↓ LOTAJES_M**: menor exposición por posición.

### N (n_sizes_ejecucion) — cantidad de soportes activos en producción

**Falta en la lista original pero es parte de la misma familia**: es el único otro parámetro por activo que X5 explora junto a `K`, `N_EXP`, `LAMBDA`, `A`, `B`, `LOTAJES_M`, `PERDIDA_MAX` (`X5_PARAM_RANGES`, `config.py:316-329`). Define cuántos soportes mantiene activos X1 para ese activo (ver también la sección N en `CLAUDE.md`).

- **Ubicación**: `config.py:65-72` (`n_sizes_ejecucion`)
- **Valor actual**: `120` para todos los activos
- **Rango de exploración X5**: `(50, 200)` para BTCUSD/ETHUSD, `(40, 180)` para TSLA/GOOGL/NVDA/AMZN (`config.py:322-325`)
- **↑ N**: más cobertura del rango de precios y entradas más finas, pero capital más fragmentado por posición.
- **↓ N**: posiciones más concentradas, cobertura más gruesa del rango.

---

## Parámetros de scoring del algoritmo de soportes (X0)

Usados en `obtener_df_extremos` y `calcular_FO` (`X0_data_supports.py:194-287`). A diferencia de los anteriores, no son por activo — son globales salvo que X5 los sobrescriba vía `params_soporte` (`X0_data_supports.py:1046-1064`).

### K — peso del aislamiento futuro vs. pasado

En `obtener_df_extremos` (`X0_data_supports.py:204-208`): `y = Low_left + High_left + K * (Low_right + High_right)`, donde `_left`/`_right` son las distancias temporales a la vela más cercana que contiene el `Low`/`High` de la vela evaluada, hacia atrás y hacia adelante respectivamente. `y` es el componente de aislamiento de la Función Objetivo (FO).

- **Ubicación**: `config.py:82`
- **Valor actual**: `1` (aislamiento pasado y futuro pesan igual)
- **Rango de exploración X5**: `(0.5, 2.0)` (`config.py:317`)
- **↑ K**: prioriza velas cuyo nivel permaneció intacto mucho tiempo después de formarse (aislamiento futuro) — favorece niveles ya validados por el tiempo transcurrido.
- **↓ K**: prioriza el aislamiento previo a la formación de la vela — favorece el contexto que la originó por sobre su validación posterior.

### N_EXP — exponente de recencia

En `obtener_df_extremos` (`X0_data_supports.py:210`): `w = t^N_EXP`, con `t ∈ [0,1]` normalizado (0 = vela más antigua del período, 1 = más reciente). `w` es el componente de recencia de `z` en la FO.

- **Ubicación**: `config.py:83`
- **Valor actual**: `1.3` (convexo — las velas recientes dominan)
- **Rango de exploración X5**: `(0.5, 3.0)` (`config.py:318`)
- **↑ N_EXP**: acentúa la concentración del peso en lo reciente — más reactivo a cambios de régimen, menos memoria del historial.
- **↓ N_EXP** (hacia 1, o cóncavo si `< 1`): reparte el peso más parejo entre todo el historial — más estable, menos sensible a movimientos recientes.

### LAMBDA — penalización por dispersión desigual

En `calcular_FO` (`X0_data_supports.py:255-287`): `FO = mean(z) - LAMBDA * cv(H_n)`, donde `z = y * w * h_dist * v * f` (producto de los factores activos en `parametros_soportes`, `config.py:87-93`) y `cv(H_n) = std(H_n) / mean(H_n)` es el coeficiente de variación de las distancias entre soportes consecutivos (`H_n`), incluyendo `P_min`/`P_max` del período completo como anclas de borde.

- **Ubicación**: `config.py:95`
- **Valor actual en `config.py`**: `1/5 = 0.2`
- **Rango de exploración X5**: `(1/1000, 1/50)` = `(0.001, 0.02)` (`config.py:319`)
- **↑ LAMBDA**: castiga con más fuerza que los soportes se amontonen en una zona del rango — empuja el conjunto N hacia una distribución más pareja en precio, aunque sacrifique algo de `mean(z)`.
- **↓ LAMBDA**: la FO se guía casi solo por `mean(z)` — permite que los soportes se concentren donde hay más evidencia (velas aisladas y recientes), aunque dejen huecos grandes en otras zonas del rango.

> **Nota**: `CLAUDE.md` (sección "Parámetros del algoritmo") documentaba `LAMBDA = 1/500`, desactualizado desde que `config.py:95` pasó a `1/5` (valor confirmado como el real de producción). Corregido en `CLAUDE.md`. El rango de exploración de X5 (`0.001`–`0.02`, `config.py:319`) quedó centrado en el valor viejo (`1/500 ≈ 0.002`) y no cubre el actual (`1/5 = 0.2`) — separado, fuera del alcance de este documento.
