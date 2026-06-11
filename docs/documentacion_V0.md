# Documentación técnica V0 — Alginvesting

Este archivo registra el detalle técnico de las mejoras y análisis realizados sobre el proyecto,
como complemento a la bitácora resumida en `docs/records.md`.

---

## [2026-06-11] Análisis de convergencia de `nuevo_optimizador_2`

### Contexto

`nuevo_optimizador_2` es el motor central del proyecto: toma un conjunto de N soportes,
y en cada iteración desplaza de a uno los soportes hacia posiciones que maximizan la FO.
Esta sesión tuvo como objetivo analizar su comportamiento actual e identificar mejoras
algorítmicas concretas para que converja más rápido, sin cambiar la lógica de negocio.

No se tocó el código de producción. Las mejoras quedan pendientes de implementar en `X0_aux.py`
(ver TO DO, sección X0).

---

### Anatomía del cuello de botella

Para entender dónde está el costo, hay que seguir el flujo de ejecución:

**Por cada iteración `j`:**
- Para cada soporte `i` en `casos_moviles` (inicialmente N soportes):
  - Genera `M-2` candidatos equidistantes entre los soportes vecinos `i-1` e `i+1`.
  - Para cada candidato `k` (loop Python de `M-2` iteraciones):
    - Construye una lista nueva de N soportes (reemplaza `dic_N[i]` por `k`).
    - Llama a `calcular_FO(df_extremos, set(lista_iter), lambda)`.
      - Internamente: `asignar_soporte` via `np.searchsorted` → O(n log N)
      - Luego: compute `dist`, `h_dist`, `z = producto de factores` → O(n)
      - Luego: `cv(H_n)` sobre gaps entre N soportes consecutivos → O(N)
  - Si la curva FO(candidato) es cóncava → ajuste cuadrático + 1 FO extra.
  - Si hay mejora > `delta_inicial`: acepta, rompe el inner loop.

**Costo total por iteración completa:**
`N × (M-2) × O(n)` donde `n` ≈ 21k velas para BTCUSD.

Con N=100, M=30, n=21000: **≈ 56 millones de operaciones por iteración**.

El dominante absoluto es `calcular_FO`, que corre `N × M` veces y procesa `n` filas cada vez.

---

### Sugerencias de mejora

Las sugerencias están ordenadas de mayor a menor impacto esperado.

---

#### Sugerencia 1 — Evaluación incremental de la FO

**Descripción técnica**

Cuando el soporte `i` se desplaza de `old_val` a `new_val`, no todas las `n` velas cambian de
soporte asignado. Solo cambian las velas cuyo soporte más cercano era `old_val` o podría pasar
a ser `new_val`. En la práctica, eso es el entorno inmediato de `i` en el eje de precios:
aproximadamente las velas asignadas al soporte `i`, más las asignadas a `i-1` e `i+1` (los
vecinos en el conjunto N ordenado).

Adicionalmente, `cv(H_n)` depende de los gaps entre soportes consecutivos. Solo 2 de los N-1
gaps cambian cuando se mueve el soporte `i`: el gap `(i-1, i)` y el gap `(i, i+1)`. Los demás
quedan idénticos.

La idea es precalcular `asignaciones[i]` (conjunto de filas del dataframe asignadas al soporte i)
una vez al inicio de cada iteración, y en cada evaluación de candidato solo recomputar:
- Las filas en `asignaciones[i-1] ∪ asignaciones[i] ∪ asignaciones[i+1]`
- Las dos contribuciones al `cv(H_n)` afectadas

**Impacto esperado**

El tamaño esperado de la zona afectada es `n × 3 / N` ≈ `21000 × 3 / 100` ≈ 630 filas,
versus las 21000 actuales. Eso representa un speedup de **~30-35x en la evaluación de FO**,
que es el paso dominante.

Traducido a tiempo de ejecución total: si hoy una corrida de BTCUSD N=100 tarda 20 minutos,
esta mejora la podría dejar en ~35-40 segundos, manteniendo resultados idénticos.

**Complejidad de implementación**: Alta — requiere refactorizar `calcular_FO` para aceptar una
estructura de datos incremental, y mantener `asignaciones` actualizada tras cada cambio aceptado.

---

#### Sugerencia 2 — Inicialización inteligente del conjunto N (warm start de calidad)

**Descripción técnica**

Actualmente, cuando no existe un JSON previo (cold start), el conjunto N se inicializa con
`np.random.uniform(p_min, p_max, N)`, es decir, precios completamente aleatorios en el rango.
Esto obliga al optimizador a hacer un viaje largo desde una posición aleatoria hasta la zona
de alta FO.

La mejora propone inicializar con los N precios con mayor score `y × w` (aislamiento × recencia)
en `df_extremos`. Estos son exactamente los candidatos naturales a soporte que el algoritmo
busca: velas aisladas y recientes. Arrancar desde ahí significa que el optimizador ya está
en una zona razonablemente buena, y puede dedicar sus iteraciones a afinar en lugar de explorar.

En la práctica:
```python
df_extremos['yw'] = df_extremos['y'] * df_extremos['w']
seeds = df_extremos.nlargest(N * 3, 'yw')['Low'].values  # sobre-muestrea para tener margen
# seleccionar N representativos con diversidad espacial (por ejemplo, quantiles del rango)
```

Esta lógica reemplaza el `np.random.uniform` en `obtener_df_extremos` solo para cold start.
El warm start existente (leer JSON previo) no se toca.

**Impacto esperado**

Para cold starts: reducción de 60-80% en iteraciones hasta convergencia. Un cold start que hoy
toma 500 iteraciones podría pasar a 100-150. Impacto menor para warm starts ya cercanos al óptimo,
que son el caso habitual en producción (gracias al delta adaptativo existente).

**Complejidad de implementación**: Baja-media — cambio localizado en `obtener_df_extremos`.

---

#### Sugerencia 3 — M adaptativo por fases (coarse-to-fine)

**Descripción técnica**

En lugar de usar M=30 candidatos en todas las iteraciones, dividir la optimización en dos fases:

- **Fase 1 (coarse)**: M=5. El optimizador corre hasta convergencia con solo 5 candidatos por
  soporte. Los candidatos son muy separados, pero bastan para identificar la zona correcta del
  espacio. Esta fase hace el trabajo pesado de exploración a bajo costo.

- **Fase 2 (fine)**: M=30. Toma el resultado de la fase 1 como warm start y refina con más
  candidatos. Las iteraciones necesarias son pocas porque los soportes ya están bien ubicados;
  la fase 2 solo ajusta a nivel fino.

El parámetro `delta_inicial` también puede ajustarse entre fases: comenzar con un delta alto en
la fase 1 (acepta cambios grandes) y reducirlo en la fase 2 (solo acepta refinamientos pequeños).

**Impacto esperado**

Si la fase 1 consume ~70% del número de iteraciones pero con M=5 en vez de M=30, el costo total
cae a ≈ `0.7 × N × 5 + 0.3 × N × 30 = 12.5N` vs el actual `N × 30`. Reducción del **58% en
evaluaciones de FO** con calidad final comparable o superior (la fase 2 garantiza refinamiento fino).

**Complejidad de implementación**: Baja — `nuevo_optimizador_2` acepta M como parámetro; solo hay
que llamarlo dos veces con configuraciones distintas, pasando el resultado de la primera como
`conjunto_N` inicial de la segunda.

---

#### Sugerencia 4 — Priorización de soportes por historial de mejoras

**Descripción técnica**

En el estado actual, después de aceptar un cambio en el soporte `i`, `casos_moviles` se reconstruye
con todos los soportes en orden aleatorio (`random.shuffle`). Esto trata a todos los soportes como
igualmente probables de mejorar en la siguiente iteración, lo cual es subóptimo: los soportes que
llevan muchas iteraciones sin cambiar probablemente ya están cerca de su óptimo local.

La mejora propone mantener un diccionario `mejora_acumulada[i]` que lleva un historial de las
mejoras aceptadas para cada soporte (media móvil exponencial). Al reconstruir `casos_moviles`,
ordenar los soportes de mayor a menor `mejora_acumulada[i]`, en lugar de aleatorio. Soportes con
historial de mejoras grandes van primero; soportes sin mejoras recientes van al final.

La lógica de aceptación y el criterio de convergencia no cambian.

**Impacto esperado**

Moderado en iteraciones totales. El beneficio es mayor en iteraciones tardías, cuando la mayoría
de los soportes ya convergieron y solo unos pocos siguen moviéndose. Explorarlos primero reduce
el número de soportes evaluados antes de encontrar la siguiente mejora. Estimación: 15-25% de
reducción en llamadas a `calcular_FO` en las iteraciones post-convergencia-parcial.

**Complejidad de implementación**: Baja — requiere mantener un dict con EMA de mejoras y
modificar el sort de `casos_moviles`. No toca `calcular_FO`.

---

#### Sugerencia 5 — Activar `prueba_cercanos=True` como default

**Descripción técnica**

El parámetro `prueba_cercanos` ya existe en `nuevo_optimizador_2` pero no está activo por defecto
(`False`). Cuando es `True`, después de aceptar un cambio en el soporte `i`, los vecinos `i-1`,
`i` e `i+1` pasan al frente de `casos_moviles` antes del shuffle. Esto es lógicamente correcto:
cuando `i` se mueve, los candidatos óptimos para `i-1` e `i+1` cambiaron (sus `cota_sup` y
`cota_inf` son distintos), así que es razonable re-evaluarlos primero.

La mejora propone activarlo por defecto y documentar el razonamiento.

**Impacto esperado**

Bajo-moderado en tiempo total, pero mejora la coherencia del proceso: en lugar de esperar a que
el shuffle coloque a los vecinos, se garantiza que la próxima iteración los visita. Puede reducir
en 10-20% el número de iteraciones en problemas con alta dependencia entre soportes adyacentes
(rangos de precios estrechos con N alto).

**Complejidad de implementación**: Mínima — cambiar `prueba_cercanos: bool = False` a `True`
en la firma de `nuevo_optimizador_2`. Ya implementado, solo falta activar.

---

#### Sugerencia 6 — Vectorización del loop interno de candidatos

**Descripción técnica**

Dentro del inner loop de `nuevo_optimizador_2`, los M candidatos para el soporte `i` se evalúan
con un for-loop Python:

```python
for caso in casos_random:  # M iteraciones con overhead Python
    lista_iter = lista_N[:]       # copia de lista N elementos
    lista_iter.remove(dic_N[i])   # O(N) búsqueda lineal
    lista_iter.append(caso)
    FO_iter, ... = calcular_FO(df_extremos, set(lista_iter), lambda)
```

La oportunidad es construir todos los M conjuntos de soportes como una matriz `(M, N)` de numpy,
y pasar los M candidatos a una versión vectorizada de `asignar_soporte` que opere sobre la matriz
completa. Internamente, `np.searchsorted` acepta una matriz 2D (axis argument).

Esto elimina el loop Python de M iteraciones y permite a numpy paralelizar la evaluación.

**Impacto esperado**

Moderado y complementario con Sugerencia 1. Eliminar el overhead Python de un loop de M=30
iteraciones puede dar 2-4x de speedup en la fase de evaluación de candidatos, independientemente
de lo que tarde `calcular_FO` en sí. Más impactante si M sube (con Sugerencia 3, la fase fine
podría usar M=50+).

**Complejidad de implementación**: Media — requiere refactorizar `calcular_FO` para aceptar una
matriz de conjuntos N como input, no un set. Cambio profundo pero acotado.

---

#### Sugerencia 7 — Criterio de parada por tasa de mejora decreciente

**Descripción técnica**

El criterio de convergencia actual es binario: "ningún soporte mejoró en una pasada completa".
Esto puede generar iteraciones tardías muy costosas donde se acepta algún cambio marginal que
apenas mueve la FO, solo para reiniciar el ciclo completo.

La propuesta es un criterio adicional (no reemplaza el actual): si el promedio de las últimas
K mejoras aceptadas es menor que `epsilon_tasa` (parámetro nuevo, más restrictivo que
`delta_inicial`), declarar convergencia aunque queden soportes sin evaluar.

```python
VENTANA_MEJORAS = 10       # K iteraciones a promediar
EPSILON_TASA = 1e-6        # tasa mínima de mejora promedio para continuar
```

La idea es que si el optimizador lleva 10 iteraciones aceptando solo mejoras de 1e-7, la
diferencia entre el resultado actual y el convergido es despreciable para el objetivo de trading.

**Impacto esperado**

Bajo en la mayoría de los casos (el delta adaptativo ya presiona hacia convergencia rápida).
Puede tener impacto en corridas donde `delta_inicial` quedó muy pequeño y el optimizador pasa
muchas iteraciones aceptando micro-mejoras. Estimación: 5-15% de reducción en iteraciones en
corridas con delta < 1e-6.

**Complejidad de implementación**: Baja — agregar buffer de mejoras recientes y check al final
de cada iteración en `nuevo_optimizador_2`.

---

### Resumen de impacto vs. complejidad

| Sugerencia | Impacto esperado | Complejidad | Prioridad de testing |
|---|---|---|---|
| 1. FO incremental | 30-35x en FO eval | Alta | 1 (mayor ganancia) |
| 2. Inicialización inteligente | 60-80% menos iters en cold start | Baja-media | 2 |
| 3. M adaptativo (coarse-to-fine) | ~58% menos evaluaciones FO | Baja | 3 |
| 4. Priorización por historial | 15-25% menos llamadas tardías | Baja | 4 |
| 5. `prueba_cercanos=True` | 10-20% menos iters | Mínima | 5 (ya existe) |
| 6. Vectorización loop M | 2-4x en inner loop | Media | 6 |
| 7. Criterio parada por tasa | 5-15% en casos límite | Baja | 7 |

El orden de testing recomendado es: implementar primero las de baja complejidad (2, 3, 4, 5, 7)
en `X0_aux.py` para tener una línea base de comparación, y luego atacar la Sugerencia 1
(la de mayor impacto pero más invasiva) con los tests ya establecidos como referencia.

---
