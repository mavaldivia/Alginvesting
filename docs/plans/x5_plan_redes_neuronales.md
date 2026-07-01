# X5 — Redes neuronales: explicación con peras y manzanas

> Complemento de `x5_plan.md`. Este documento explica el diseño del modelo en lenguaje llano, con analogías y glosario. No reemplaza el plan técnico — lo hace legible.

---

## El problema en una línea

Queremos un modelo que, dado "cómo está el mercado ahora" y "qué parámetros de configuración estamos usando", prediga "cuánto va a ganar (o perder) esta operación". Con eso podemos preguntarle: "¿qué parámetros maximizarían la ganancia predicha?".

---

## La analogía del chef

Imagina que eres un chef que ha cocinado miles de platos (operaciones) en cocinas de distintas condiciones (mercados). Llevas un registro de cada plato: qué ingredientes usaste (parámetros de config), cómo estaba la cocina ese día (contexto de mercado), y cómo quedó el plato (retorno de la operación).

Después de suficiente experiencia, el chef puede predecir: "si uso la receta A en una cocina caliente (mercado alcista), el plato sale 7/10. Si uso la receta B, sale 9/10". El modelo X5 es ese chef.

En inferencia — es decir, cuando el sistema está corriendo y necesita decidir qué parámetros usar — le preguntamos al chef: "¿qué receta me recomiendas para la cocina de hoy?". El chef evalúa las opciones y entrega la mejor.

---

## Qué entra al modelo (inputs)

Cada fila del dataset de entrenamiento representa **una operación cerrada**. Sus columnas son:

### 1. Contexto de mercado (X2 + X3)

Lo que sabíamos del mercado en el momento de abrir la orden.

- **X2** (fundamentales): ¿está el activo fundamentalmente sano? Score 0–1 basado en ratios financieros, tendencia histórica, sentimiento del mercado.
- **X3** (técnicas): ¿cómo se comportó el precio recientemente? RSI, medias móviles, volatilidad, distancia a soportes, etc.

Son ~100 números que describen el estado del mercado en ese momento. El modelo aprende a reconocer patrones en esos números.

### 2. Parámetros de configuración activos (config params)

Los parámetros que el sistema tenía configurados cuando se abrió esa orden: `K`, `N_EXP`, `LAMBDA`, `n_sizes_ejecucion`, `LOTAJES_M`, `A`, `B`.

Son los "ingredientes de la receta". El modelo aprende qué combinación de parámetros funciona mejor en cada tipo de mercado.

### 3. Estado del portfolio en ese momento

Cuántas posiciones abiertas había, cuánto capital estaba comprometido, cómo iban esas posiciones. Se representa como **estadísticas resumidas** (ver sección "El problema de las órdenes abiertas" más abajo).

### 4. Lo que queremos predecir (output / Y)

- `retorno_pct`: el retorno porcentual de esta operación cuando cerró.

Eso es todo lo que el modelo predice. A partir de esa predicción, el sistema busca los parámetros que la maximizan.

---

## V1: Gradient Boosting (LightGBM) — "el comité de expertos"

Antes de hablar de redes neuronales, la primera versión usa **Gradient Boosting** (LightGBM o XGBoost). No es una red neuronal, pero es el punto de partida más robusto para datos tabulares con pocas filas.

### Cómo funciona paso a paso

Supón que quieres predecir el retorno de una operación. Tienes 4 operaciones en el dataset:

```
Op A: RSI=30, K=1.0, mercado bajista  → retorno real = +3%
Op B: RSI=75, K=1.0, mercado alcista  → retorno real = +1%
Op C: RSI=30, K=0.7, mercado bajista  → retorno real = +4%
Op D: RSI=75, K=1.5, mercado alcista  → retorno real = -1%
```

**Ronda 0 — predicción inicial**: predice el promedio de todos los retornos = +1.75% para todos.
```
Error de A: 3% - 1.75% = +1.25%   (predijo poco)
Error de B: 1% - 1.75% = -0.75%   (predijo de más)
Error de C: 4% - 1.75% = +2.25%   (predijo poco)
Error de D: -1% - 1.75% = -2.75%  (predijo mucho de más)
```

**Ronda 1 — primer árbol**: en vez de predecir el retorno, este árbol aprende a predecir los **errores** de la ronda 0. Puede aprender reglas simples como:
```
si RSI < 50 → corregir hacia arriba (+1.5%)
si RSI >= 50 Y K > 1.2 → corregir hacia abajo (-2%)
```
Ahora las predicciones mejoran: A sube a +3.25%, D baja a -0.25%.

**Ronda 2 — segundo árbol**: aprende a predecir los errores que **aún quedan** después del árbol 1. Puede aprender: "si K < 0.8 → corregir hacia arriba un poco más".

**Y así 500 veces.** La predicción final es la suma de todas las correcciones:
```
retorno_predicho = promedio_inicial + corrección_árbol_1 + corrección_árbol_2 + ... + corrección_árbol_500
```

Cada árbol es simple ("si X entonces Y"). La potencia viene de acumular cientos de correcciones pequeñas y específicas. El término "gradient" viene de que las correcciones se calculan usando el gradiente matemático del error — lo que garantiza que cada árbol apunta en la dirección óptima de mejora.

**Por qué empezar aquí**:
- Funciona muy bien con datasets pequeños (<50k filas).
- No requiere normalización ni ajustes finos.
- Es interpretable: puedes ver qué features importaron más.
- El único contra: no es diferenciable, así que la búsqueda de parámetros óptimos en inferencia es más lenta (ver sección de inferencia).

---

## V2: FT-Transformer — "el modelo de atención sobre features"

Cuando el dataset crezca (~5k+ operaciones), el salto natural es el **FT-Transformer** (Feature Tokenizer + Transformer).

### Paso 1 — Feature Tokenizer: convertir cada número en un vector

En una red neuronal común (FFNN/MLP), cada feature entra como un número. El problema es que el modelo trata todos los números de la misma manera, sin saber que "RSI" y "K" son conceptualmente distintos.

El **Feature Tokenizer** convierte cada feature en un **vector** (embedding). La transformación concreta es:

```
embedding_i = valor_i × W_i + b_i
```

Donde:
- `valor_i` es el número original (ej. RSI = 72.3)
- `W_i` es un **vector de pesos** de tamaño D, único para esa feature (aprendido durante el entrenamiento)
- `b_i` es un **vector de sesgo** de tamaño D, también único para esa feature (aprendido)
- El resultado es un vector de D números

**Ejemplo concreto** con D = 3 (en la práctica D = 64 o más):

```
RSI tiene su propio W_RSI = [0.5, -0.2, 0.8]  y  b_RSI = [0.1, 0.3, -0.1]

RSI = 72.3  →  72.3 × [0.5, -0.2, 0.8] + [0.1, 0.3, -0.1]
             =  [36.15, -14.46, 57.84] + [0.1, 0.3, -0.1]
             =  [36.25, -14.16, 57.74]

K tiene su propio W_K = [0.1, 0.9, -0.3]  y  b_K = [-0.2, 0.0, 0.5]

K = 1.0     →  1.0 × [0.1, 0.9, -0.3] + [-0.2, 0.0, 0.5]
             =  [-0.1, 0.9, 0.2]
```

La clave: **cada feature tiene sus propios W y b, que el modelo aprende durante el entrenamiento**. No son fijos de antemano — el modelo descubre por sí solo qué transformación es útil para cada feature. Al final, RSI=72 "significa" algo distinto que RSI=30, y esa diferencia queda representada en el vector resultante de manera que el Transformer pueda aprovecharla.

Comparado con una MLP donde RSI entra como "72.3" directamente: la MLP ve un número; el FT-Transformer ve un vector de 64 números que captura "qué implica que RSI esté en este nivel" según lo aprendido.

### Paso 2 — Transformer: atención entre features

Después de tokenizar, el mecanismo de **atención** (el mismo que usan los LLMs como yo) permite que cada feature "mire" a las demás y ajuste su representación según el contexto.

**Por qué importa**: una MLP simple aprende la importancia de cada feature por separado. El Transformer aprende interacciones: "cuando K es alto Y el RSI está sobrecomprado, el retorno esperado baja — pero si K es bajo, esa combinación no importa tanto".

Esas interacciones cruzadas entre parámetros de config y contexto de mercado son exactamente lo que X5 necesita aprender.

### Comparativa MLP vs FT-Transformer

```
MLP:
  RSI ──┐
  K ────┼── capas densas ── retorno_pct
  MACD ─┘
  (cada feature entra independiente)

FT-Transformer:
  RSI ──→ embedding ──┐
  K ────→ embedding ──┼── atención mutua ── capas densas ── retorno_pct
  MACD ─→ embedding ──┘
  (las features "se hablan entre sí" antes de pasar por las capas densas)
```

---

## Multi-head: predecir 3 cosas a la vez

El modelo predice tres variables objetivo simultáneamente:

1. `retorno_pct` — retorno de esta operación
2. `pnl_abierto_activo_oc` — P&L flotante de otras posiciones abiertas cuando cerró esta
3. `pnl_cerrado_activo_oc` — P&L acumulado cerrado del activo en la sesión

En vez de entrenar 3 modelos separados, usamos una arquitectura **multi-head**:

```
                    features (X2 + X3 + params + portfolio)
                                    ↓
                    ┌─────────── Trunk ───────────┐
                    │  (capas compartidas que      │
                    │   aprenden representaciones  │
                    │   generales del problema)    │
                    └──────────────────────────────┘
                         ↙         ↓         ↘
                      Head 1    Head 2    Head 3
                    retorno_   pnl_ab_   pnl_cerr_
                      pct        oc         oc
```

**Analogía**: un médico hace la misma revisión al paciente (el trunk) y luego da tres diagnósticos distintos (los heads): cardiovascular, respiratorio, metabólico. La revisión es compartida; las conclusiones son independientes.

**Por qué funciona mejor que 3 modelos separados**: el trunk aprende representaciones útiles para las tres tareas a la vez. Eso actúa como una forma de regularización — el modelo no puede sobreajustarse a una sola señal ruidosa si tiene que explicar tres variables al mismo tiempo.

---

## Inferencia: cómo encontrar los parámetros óptimos

Una vez entrenado el modelo, queremos usarlo al revés: dado el contexto de mercado actual (X2+X3 de ahora), ¿qué parámetros de config maximizan el retorno predicho?

### Con LightGBM (V1): búsqueda por muestreo

No es diferenciable, así que no podemos hacer matemática continua sobre él. La estrategia es:

1. Fijar el contexto de mercado actual (X2+X3).
2. Probar muchas combinaciones de parámetros — con Optuna (búsqueda bayesiana) o un grid.
3. Para cada combinación, preguntarle al modelo: "¿cuánto predicho que gano con estos params en este contexto?".
4. Quedarse con la combinación que maximiza la predicción.

Es como pedirle al comité de expertos que evalúe 200 recetas diferentes y diga cuál prefiere para la cocina de hoy.

### Con NN (V2): gradient ascent

Una red neuronal es una función matemática diferenciable. Eso significa que podemos calcular: "si subo K en 0.01, ¿el retorno predicho sube o baja, y cuánto?".

**Gradient ascent** aprovecha eso:

1. Fijar el contexto de mercado actual (no se toca).
2. Inicializar los parámetros de config en algún punto del espacio.
3. Calcular el gradiente: "en qué dirección cambiar los params para subir el retorno predicho".
4. Dar un paso en esa dirección.
5. Repetir hasta llegar a un máximo.

**Analogía**: es como estar con los ojos vendados en una colina y querer llegar a la cima. En cada paso, tocas el suelo con el pie para sentir hacia dónde sube la pendiente y avanzas en esa dirección. El gradient ascent es eso, pero matemático.

Es mucho más eficiente que probar 200 combinaciones manualmente. El contra: puede quedar atrapado en un máximo local (una colina pequeña, no la más alta). Se mitiga repitiendo el proceso desde varios puntos de inicio aleatorios.

---

## El problema de las órdenes abiertas (Deep Sets)

Al momento de abrir una nueva orden (OE), el sistema puede tener N órdenes abiertas en ese activo. N varía: a veces 2, a veces 8.

El problema: **una red neuronal espera inputs de tamaño fijo**. No puedes decirle "aquí hay 3 órdenes" en un momento y "aquí hay 7" en otro.

### Solución V1: estadísticas resumidas

En vez de pasar las órdenes individuales, pasas un resumen estadístico:

```
n_ordenes_abiertas = 4
mean_retorno_pct_abierto = +1.2%   ← promedio de lo que ganan las 4 órdenes ahora
std_retorno_pct_abierto = 0.8%    ← qué tan dispersas están esas ganancias
exposicion_pct_cuenta = 12%        ← % del capital comprometido
```

Siempre son 4 números, sin importar cuántas órdenes haya. El modelo nunca ve las órdenes individuales.

### Solución V2: Deep Sets (mean pooling)

Si queremos que el modelo aprenda de las características individuales de cada orden (sin que el orden en que las listemos importe), usamos **mean pooling**:

1. Cada orden se convierte en un vector pequeño: `[retorno_pct_flotante, horas_abierta, distancia_entrada_pct, lotaje_relativo]`.
2. Se promedian todos esos vectores → un vector único de tamaño fijo.
3. Ese vector se concatena con el resto de los features.

**Por qué el orden no importa**: si tienes 3 órdenes y las promedias, el resultado es el mismo independientemente de si las listas como [A, B, C] o [C, A, B]. Eso se llama **permutation-invariant** — el modelo no aprende a darle importancia al "orden #1 siempre es la más antigua", que sería un sesgo artificial.

---

## Overfitting: el estudiante que memoriza

**Overfitting** = el modelo aprende los datos de entrenamiento de memoria en vez de aprender patrones generalizables.

**Analogía**: un estudiante que memoriza las respuestas exactas de los exámenes anteriores. Saca 100 en los exámenes pasados, pero cuando el profesor cambia la redacción de la pregunta, falla. El modelo hizo lo mismo: aprendió el ruido específico de cada trade, no el patrón general.

### Señales de overfitting

- El error en el dataset de entrenamiento es muy bajo, pero el error en operaciones nuevas es alto.
- El modelo recomienda siempre los mismos parámetros extremos (se "pegó" a lo que funcionó en el pasado).

### Cómo lo mitigamos

1. **Normalizar en porcentaje, no en USD**: si el modelo ve P&L en dólares, aprende que "ganar $500 en una cuenta grande es peor que ganar $500 en una cuenta chica". En %, la señal es la misma.

2. **Dropout**: durante el entrenamiento, se "apagan" aleatoriamente algunas neuronas en cada pasada. Fuerza al modelo a no depender de ninguna neurona específica — tiene que aprender redundancia.

3. **Regularización L2**: penaliza pesos muy grandes en la red. Evita que el modelo ponga todo el peso en una sola feature.

4. **Cross-validación temporal**: en vez de dividir el dataset aleatoriamente en train/test, siempre entrenamos con el pasado y validamos con el futuro. Así el modelo nunca "ve el futuro" durante el entrenamiento.

5. **Multi-head**: predecir 3 variables a la vez obliga al trunk a aprender representaciones generales, no sobreajustadas a una sola señal ruidosa.

---

## El sesgo de selección (problema contrafactual)

Este es el problema más sutil y el más importante.

**El problema**: el dataset solo contiene operaciones que se hicieron con los parámetros que el sistema consideraba "buenos" en ese momento. Nunca vemos qué hubiera pasado con otros parámetros — porque nunca los probamos.

**Analogía**: quieres saber qué restaurante de la ciudad es mejor. Pero solo vas siempre al mismo porque te parece bueno. Al final del año tienes 200 reseñas de ese restaurante, cero del resto. No puedes concluir que es el mejor — nunca probaste los otros.

**Consecuencia**: el modelo aprende que "los parámetros actuales son buenos" simplemente porque son los únicos que vio, no porque realmente lo sean.

**Solución — exploración deliberada por ciclo completo**: aleatorizar los parámetros al **inicio de cada ciclo de backtesting**, no vela por vela.

### Por qué aleatorizar por ciclo entero es mejor que por vela

Recuerda que el loop de backtesting recorre desde `FECHA_INICIAL` hasta `t` (hoy) y luego reinicia. Cada ciclo cubre ~2 años de historia: mercados alcistas, bajistas, laterales, crashes.

Si aleatorizas los params **al inicio del ciclo** y los mantienes fijos durante todo el recorrido, obtienes algo valioso: el modelo ve "cómo funcionaron ESTOS params en TODO tipo de mercado". Puede aprender que K=1.5 funciona bien en bull market pero falla en crashes, porque en el mismo ciclo hay ambos escenarios.

Si aleatorizas vela por vela, los params cambian en cada vela y el modelo no puede atribuir el resultado al contexto — hay demasiado ruido.

### Implementación: ciclos de exploración vs. explotación

Designar explícitamente el tipo de cada ciclo al inicio:

```
Ciclo 1: EXPLOTACIÓN  → params = config.py (baseline manual)
Ciclo 2: EXPLORACIÓN  → params = samplear_aleatorio()
Ciclo 3: EXPLOTACIÓN  → params = mejor set conocido por X5
Ciclo 4: EXPLORACIÓN  → params = samplear_aleatorio()
Ciclo 5: EXPLOTACIÓN  → params = mejor set conocido por X5
...
```

Una proporción de 30% exploración / 70% explotación es un punto de partida razonable. El parámetro `EXPLORATION_RATE` va en `config.py`.

Los ciclos de exploración generan P&L peor en el backtesting — eso no importa. El objetivo de esos ciclos no es rendir bien, sino **generar datos de entrenamiento variados**. Son los ciclos más valiosos para que el modelo aprenda qué params funcionan en qué contexto.

---

## No-estacionariedad: el mercado cambia de personalidad

Un modelo entrenado en el bull market de 2024 puede ser inútil en el bear market de 2026. Los patrones que aprendió ya no aplican.

Esto se llama **concept drift** — el "concepto" que el modelo aprendió (la relación entre contexto, params y retorno) cambió en el mundo real.

**Solución recomendada — ponderación temporal exponencial**: entrenar con todo el historial, pero darle más peso a las operaciones recientes. Una operación de hace 2 años influye poco; una de la semana pasada influye mucho.

```
peso de una operación = e^(-λ × días_de_antigüedad)
```

Donde `λ` controla qué tan rápido decae el peso. Con `λ` alto, el modelo "olvida" rápido el pasado; con `λ` bajo, da más peso a la historia.

---

## Glosario

| Término | Qué significa en este proyecto |
|---|---|
| **Surrogate model** | Un modelo que "imita" el sistema real (el mercado + las operaciones) para poder hacer predicciones baratas. X5 es un surrogate: en vez de esperar a que el mercado decida, el modelo predice el resultado. |
| **Tabular data** | Datos organizados en filas y columnas, como una planilla Excel. Cada fila es una operación; cada columna es una feature. Diferente a imágenes (pixeles) o texto (palabras). |
| **Feature** | Una columna de input del modelo. Ej: `RSI`, `K`, `n_ordenes_abiertas`. |
| **Embedding** | Representación de un valor como un vector de números. Convierte "RSI = 72.3" en un vector de tamaño fijo que el modelo puede procesar con más riqueza. |
| **Atención / Attention** | Mecanismo que permite que una feature "mire" a las demás y ajuste su representación. Base de los Transformers (y de los LLMs). |
| **Transformer** | Arquitectura de red neuronal basada en atención. Originalmente para texto (BERT, GPT); adaptada para datos tabulares en el FT-Transformer. |
| **FT-Transformer** | Feature Tokenizer + Transformer. Convierte cada feature en un embedding y luego aplica atención entre ellas. Estado del arte para datos tabulares con muchas interacciones entre features. |
| **Gradient Boosting** | Método de ML que entrena muchos árboles de decisión secuencialmente, donde cada árbol corrige los errores del anterior. LightGBM y XGBoost son implementaciones. No es una NN. |
| **LightGBM** | Implementación rápida de Gradient Boosting. Excelente para datasets tabulares pequeños. Se usa como V1 de X5. |
| **Multi-head** | Arquitectura donde el modelo tiene capas compartidas (trunk) y múltiples "cabezas" de salida, cada una prediciendo una variable distinta. |
| **Trunk / Backbone** | Las capas internas compartidas de una NN multi-head. Aprende representaciones generales del problema antes de las cabezas especializadas. |
| **Inferencia** | Usar el modelo ya entrenado para hacer predicciones. Opuesto a entrenamiento. En X5: dado el contexto actual, encontrar los params óptimos. |
| **Gradient ascent** | Técnica para maximizar una función dando pasos en la dirección de su gradiente. Se usa en inferencia cuando el modelo es una NN diferenciable: optimizamos los inputs de params para maximizar el retorno predicho. |
| **Gradiente** | Derivada de una función respecto a sus inputs. Indica "si cambio este input en esta dirección, la salida sube o baja, y cuánto". |
| **Diferenciable** | Una función es diferenciable si se puede calcular su gradiente. Las NN son diferenciables; los árboles de decisión no. |
| **Overfitting** | El modelo memoriza los datos de entrenamiento en vez de aprender patrones generalizables. Funciona perfecto en el pasado, mal en datos nuevos. |
| **Dropout** | Técnica de regularización: durante el entrenamiento, se apagan aleatoriamente algunas neuronas en cada pasada. Previene overfitting. |
| **Regularización L2** | Penalización a los pesos grandes en la red. Evita que el modelo dependa demasiado de cualquier feature individual. |
| **Cross-validación temporal** | Estrategia de validación donde siempre se entrena en el pasado y se valida en el futuro. Esencial en finanzas para no filtrar información futura al modelo. |
| **Counterfactual** | "¿Qué hubiera pasado si...?". El problema contrafactual en X5: nunca sabemos el resultado de los parámetros que NO usamos. |
| **Sesgo de selección** | El dataset no es representativo de todos los escenarios posibles porque solo captura los casos en que se tomó cierta decisión (los params "buenos"). |
| **Exploration vs exploitation** | Tensión entre usar lo mejor conocido (exploitation) y probar cosas nuevas para aprender más (exploration). En X5: a veces usar params aleatorios para generar datos variados. |
| **Concept drift** | El patrón que el modelo aprendió deja de ser válido porque el mundo cambió. En mercados: cambios de régimen (bull → bear). |
| **Permutation-invariant** | Una operación es permutation-invariant si su resultado no cambia al reordenar los inputs. El promedio de [3, 5, 7] es el mismo que el de [7, 3, 5]. |
| **Deep Sets** | Arquitectura para procesar conjuntos de tamaño variable de forma permutation-invariant. Cada elemento → embedding, luego pooling (ej. promedio) → vector fijo. |
| **Mean pooling** | Promediar un conjunto de vectores para obtener un vector único. La forma más simple de Deep Sets. |
| **Ponderación temporal exponencial** | Dar más peso a los datos recientes durante el entrenamiento con un factor que decae exponencialmente con la antigüedad. Mitiga concept drift. |
| **OE / OA / OC** | Orden en Espera (buy limit colocada) / Orden Abierta (posición activa) / Orden Cerrada (trade finalizado). |
| **retorno_pct** | Retorno porcentual de una operación: `(precio_salida - precio_entrada) / precio_entrada × 100`. Variable objetivo principal de X5. |
| **Store de trades** | El dataset de entrenamiento de X5: una tabla donde cada fila es una OC con su contexto (X2+X3 al momento de OE), los params activos, y el resultado. |
