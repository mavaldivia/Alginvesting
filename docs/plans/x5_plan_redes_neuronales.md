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

Lo que sabíamos del mercado en **dos momentos clave**:

- **Al colocar el buy limit (OE)**: el contexto del mercado cuando el sistema decidió poner la orden.
- **Al ejecutarse la orden (OA)**: el contexto cuando el precio tocó el soporte y la posición se abrió. Entre OE y OA pueden pasar días — el mercado puede cambiar notablemente en ese tiempo.

En cambio, el contexto de **cuando cierra la posición (OC) no entra al modelo** — eso es el futuro, no está disponible en inferencia.

- **X2** (fundamentales): ¿está el activo fundamentalmente sano? Score 0–1 basado en ratios financieros, tendencia histórica, sentimiento del mercado.
- **X3** (técnicas): ¿cómo se comportó el precio recientemente? RSI, medias móviles, volatilidad, distancia a soportes, etc.

Son ~100 números por momento (OE y OA), ~200 en total por operación. El modelo aprende a reconocer patrones en esos números.

### 2. Parámetros de configuración activos (config params)

Los parámetros que el sistema tenía configurados cuando se abrió esa orden: `K`, `N_EXP`, `LAMBDA`, `n_sizes_ejecucion`, `LOTAJES_M`, `A`, `B`, `PERDIDA_MAX`.

Son los "ingredientes de la receta". El modelo aprende qué combinación de parámetros funciona mejor en cada tipo de mercado.

**Importante: todos los parámetros son por activo.** X5 entrena un modelo independiente para BTCUSD, TSLA, NVDA, etc. Los parámetros óptimos para BTC (muy volátil, 24/7) no son los mismos que para GOOGL (más estable, mercado horario). Cada activo tiene su propio set y sus propios rangos de búsqueda.

### 3. Features temporales

Cada vela tiene una marca de tiempo (timestamp). De ahí extraemos features que el modelo puede usar para detectar estacionalidad:

- **Hora del día** (0–23): los mercados de acciones tienen patrones claros — mayor volumen a la apertura (09:30 ET) y al cierre (16:00 ET). Para crypto (24/7), hay patrones de actividad institucional durante el horario europeo/americano.
- **Día de la semana**: los lunes suelen abrir con gaps acumulados del fin de semana; los viernes cierran posiciones antes del weekend. Codificado como dummies `ds_lun` a `ds_dom`.
- **Día del mes** y **mes**: útil para capturar patrones de fin de mes (rebalanceo de fondos), estacionalidad de Q4, enero effect, etc. Codificados como dummies.
- **Proximidad a festivos US**: `dias_hasta_festivo` y `dias_desde_festivo` (capped a 30 días). El día previo a un festivo US el volumen cae; el post-festivo puede abrir con gaps. Aplica a todos los activos — incluso crypto tiene menor actividad institucional en festivos US.

Son ~28 features adicionales por momento (OE), totalmente derivables del timestamp — sin requerir datos de mercado externos.

### 4. Estado del portfolio en ese momento

Cuántas posiciones abiertas había, cuánto capital estaba comprometido, cómo iban esas posiciones. Se representa como **estadísticas resumidas** (ver sección "El problema de las órdenes abiertas" más abajo).

### 5. Lo que queremos predecir (output / Y)

El modelo predice **tres variables** (ver sección "Multi-head" más abajo):

1. `retorno_pct` — retorno porcentual de esta operación
2. `pnl_abierto_activo_oc` — P&L flotante de las otras posiciones abiertas del activo cuando cerró esta
3. `pnl_cerrado_activo_oc` — P&L acumulado cerrado del activo en la sesión

La función objetivo que se maximiza en inferencia (la que guía la búsqueda de parámetros óptimos) es configurable. Propuesta inicial: `retorno_pct`, que es la señal más limpia — mide el resultado de una operación individual sin ruido de otras posiciones.

Además, los **registros periódicos** (filas del store que se generan aunque no haya OC) usan `pnl_flotante_activo` como Y — el P&L no realizado de todas las posiciones abiertas del activo en ese momento. Eso permite al modelo aprender cómo va el portfolio durante rachas bajistas sostenidas (ver sección "El problema de las rachas bajistas").

---

## Arquitectura end-to-end

Antes de entrar en cada pieza por separado, aquí está el cuadro completo: desde los inputs hasta los outputs, pasando por el modelo.

```
┌──────────────────────── INPUTS (~240 features, vector de tamaño fijo) ─────────────────────┐
│                                                                                             │
│  X2 en OE  (~12)  ─┐                                                                       │
│  X3 en OE  (~25)  ─┤                                                                       │
│  Temporal en OE   ─┤                                                                       │
│  (~28)            ─┼── todo se concatena en un vector plano de ~240 columnas ──────────►  │
│  Config params    ─┤   (tamaño siempre fijo — ver "¿Es dinámica?" más abajo)               │
│  (8)              ─┤                                                                       │
│  Portfolio ctx    ─┤                                                                       │
│  (~7)             ─┤                                                                       │
│  X2 en OA  (~12)  ─┤                                                                       │
│  X3 en OA  (~25)  ─┘                                                                       │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                            ↓
┌──────────────────────────── MODELO (uno por activo) ────────────────────────────────────────┐
│                                                                                             │
│  < 500 OC   →  untrained:  devuelve config.py sin modificar                                │
│                    ↓                                                                        │
│  500–5.000 OC → lgbm:    3 modelos LightGBM independientes, uno por output                │
│                    ↓                                                                        │
│  > 5.000 OC  →  ftt:     1 FT-Transformer con trunk compartido + 3 heads                  │
│                                                                                             │
│  La transición es automática y por activo — BTCUSD puede estar en ftt                      │
│  mientras TSLA sigue en lgbm.                                                              │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                            ↓
┌────────────────────────── OUTPUTS (3 predicciones) ─────────────────────────────────────────┐
│                                                                                             │
│  retorno_pct             ← target principal para inferencia                                │
│  pnl_abierto_activo_oc   ← cuánto ganan/pierden las otras posiciones abiertas              │
│  pnl_cerrado_activo_oc   ← P&L acumulado cerrado del activo en la sesión                  │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                            ↓
                    INFERENCIA: dado el contexto actual (X2+X3+temporal+portfolio, fijo),
                    busca los config_params que maximizan retorno_pct predicho.
                    lgbm → Optuna (~200 trials)  |  ftt → gradient ascent
```

---

## ¿Es dinámica la arquitectura?

Sí, en tres sentidos distintos:

**1. La arquitectura escala con los datos (dinámica por volumen)**

El sistema no arranca con una arquitectura fija. Empieza sin modelo (`untrained`), sube a LightGBM cuando hay suficientes datos, y sube a FT-Transformer cuando hay muchos más. La transición es automática, por activo, y se controla con dos umbrales en `config.py` (`X5_MIN_TRADES_TRAIN`, `X5_MIN_TRADES_FTT`). Cada activo vive en su propia fase sin afectar a los demás.

**2. El portfolio tiene inputs de longitud variable (dinámica en inputs)**

El número de órdenes abiertas (OA) en cualquier momento varía: a veces hay 2, a veces hay 8. Una red neuronal necesita inputs de tamaño fijo — esto se resuelve de dos formas según la versión:

- **V1 (lgbm)**: se calculan estadísticas resumidas del portfolio (n_ordenes, media y desviación del retorno flotante, exposición %). Siempre son 7 números, sin importar cuántas OA haya.
- **V2 (ftt)**: se usa mean pooling (Deep Sets) — cada OA se convierte en un vector de 4 features, y se promedian todos. El resultado es siempre un vector de 4 números, independientemente de cuántas órdenes haya.

En ambos casos, el vector de entrada al modelo es de tamaño fijo (~240 features).

**3. El modelo aprende continuamente (dinámica en tiempo)**

Con FT-Transformer: el modelo da un paso de gradiente por cada vela nueva (~cada hora), actualizando sus pesos en tiempo real. Con LightGBM: reentrena cada ~48 horas sobre el store acumulado. En ambos casos, el modelo de mañana sabe algo que el de hoy no sabía.

**Lo que NO es dinámico**: el número de features de entrada es fijo (~240 columnas) — no crece con más datos. Las dimensiones internas del FT-Transformer (tamaño del embedding D, número de capas) son fijas una vez definidas. Solo los pesos aprendidos cambian.

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

### Hiperparámetros por defecto (paper original)

Los valores a continuación provienen del paper original: *Revisiting Deep Learning Models for Tabular Data* (Gorishniy et al., 2021). Son el punto de partida para X5 — se pueden ajustar si la validación lo justifica.

| Hiperparámetro | Valor | Qué controla |
|---|---|---|
| `d` (dimensión del embedding) | 192 | Tamaño del vector por feature después del Feature Tokenizer |
| `n_layers` | 3 | Número de bloques Transformer apilados |
| `n_heads` | 8 | Cabezas de atención paralelas en Multi-Head Attention |
| `d_ffn` (MLP interno) | 256 ≈ 4/3 × d | Tamaño de la capa oculta del MLP dentro de cada bloque |
| `dropout_attention` | 0.0 | Fracción de pesos de atención que se apagan durante entrenamiento |
| `dropout_ffn` | 0.0 | Fracción de neuronas del MLP interno que se apagan |

Con ~240 features de entrada y estos valores, el FT-Transformer de X5 tiene del orden de **500 k–1 M parámetros** — compacto para datos tabulares, no requiere GPU de alta gama.

---

## Cómo funciona la atención — explicación profunda

### El problema que resuelve

En una Red Neuronal (NN) tipo Perceptrón Multicapa (MLP), cada feature entra de forma independiente. El modelo puede aprender "un RSI alto es mala señal", pero no puede aprender "un RSI alto es mala señal... pero solo cuando la volatilidad también es alta Y K > 1.2". Eso requiere capturar la interacción entre tres features al mismo tiempo.

La atención resuelve eso: permite que cada feature ajuste su representación según el contexto de todas las demás.

### La analogía: la reunión de equipo

Imagina que eres parte de un equipo de 5 personas en una reunión. Cada persona representa una feature:

- **RSI** dice: "el precio está sobrecomprado, RSI = 78"
- **K** dice: "el parámetro de peso futuro es 1.5"
- **Volatilidad** dice: "el mercado está muy agitado"
- **n_sizes** dice: "hay 90 soportes activos"
- **Score fundamental** dice: "BTC está fundamentalmente sano"

En una MLP, cada persona escribe sus conclusiones en un papel y las manda directamente a la salida. **No se hablan entre sí.**

En un Transformer, **antes de escribir sus conclusiones, cada persona escucha a las demás y ajusta lo que va a decir según lo que oyó**. RSI puede pensar: "soy alto, normalmente eso es mala señal — pero escuché que la volatilidad también es alta y el score fundamental es positivo. En ese contexto, quizás no sea tan mala señal". Y ajusta su representación en consecuencia.

### El mecanismo concreto: Q, K, V

Para que una feature pueda "preguntar" a las demás, el Transformer le asigna tres vectores:

- **Q (Query)**: "¿qué información busco en mis compañeras?"
- **K (Key)**: "¿qué información ofrezco a las demás?"
- **V (Value)**: "la información que realmente comparto si me encuentran relevante"

La transformación es:
```
Q_i = embedding_i × W_Q    (W_Q es una matriz aprendida, compartida por todas las features)
K_i = embedding_i × W_K
V_i = embedding_i × W_V
```

**Cómo RSI le "pregunta" a las demás:**

RSI tiene su `Q_RSI`. Para saber cuánto le importa cada compañera, calcula el producto interno (dot product) entre su Query y el Key de cada una:

```
score(RSI, Volatilidad)      = Q_RSI · K_Volatilidad   →  8.3   (alta relevancia)
score(RSI, K)                = Q_RSI · K_K              →  5.1
score(RSI, n_sizes)          = Q_RSI · K_n_sizes        →  2.2
score(RSI, Score_fundamental)= Q_RSI · K_fund           →  4.7
```

Luego aplica **softmax** para convertir esos scores en pesos que sumen 1:

```
pesos = softmax([8.3, 5.1, 2.2, 4.7])
      = [0.47, 0.22, 0.05, 0.26]
         Vol.   K    n_sz  fund
```

El nuevo embedding de RSI es la suma ponderada de los Values de todas las features según esos pesos:

```
embedding_RSI_nuevo = 0.47 × V_Volatilidad
                    + 0.22 × V_K
                    + 0.05 × V_n_sizes
                    + 0.26 × V_fund
```

Lo que pasó: RSI "absorbió" información de las otras features proporcionalmente a cuánto le importaban. Su nuevo embedding ya no es solo "soy RSI = 78". Es "soy RSI = 78 en un contexto de alta volatilidad con score fundamental sano y K = 1.5".

Y esto ocurre **simultáneamente para todas las features** — cada una actualiza su representación mirando a las demás.

### Multi-head: mirar desde varios ángulos

Con una sola cabeza de atención, cada feature solo puede "mirar" a las demás desde un ángulo. **Atención multi-cabeza** (Multi-Head Attention o MHA) corre el mecanismo varias veces en paralelo, con matrices `W_Q`, `W_K`, `W_V` distintas por cabeza:

```
Cabeza 1: aprende relaciones técnicas          → RSI ↔ Volatilidad ↔ MACD
Cabeza 2: aprende relaciones params-contexto   → K ↔ tendencia ↔ n_sizes
Cabeza 3: aprende relaciones de riesgo         → LOTAJES_M ↔ exposición ↔ drawdown
...
```

Los resultados de todas las cabezas se concatenan y se proyectan en un vector final. Así el modelo captura múltiples tipos de relaciones al mismo tiempo, sin que una interfiera con la otra.

### Capas: de lo simple a lo abstracto

Un único bloque de atención captura relaciones directas entre features. Pero algunos patrones son más abstractos — "el efecto de K depende de la volatilidad, que a su vez depende del régimen de mercado, que se infiere combinando Score + MACD + tendencia".

Por eso el Transformer apila varias capas:

```
Input (embeddings del Feature Tokenizer)
         ↓
Capa 1: atención directa entre features
         ↓
Capa 2: atención entre representaciones ya contextualizadas de la Capa 1
         ↓
Capa 3: atención sobre representaciones aún más abstractas
         ↓
Output (embeddings ricos en contexto, listos para el trunk y los heads)
```

Cada capa ve el mundo un nivel más arriba. Capa 1 aprende "RSI alto + Volatilidad alta". Capa 2 puede aprender "ese patrón se combina con K bajo de cierta manera". Capa 3 puede capturar el régimen completo.

Para datos tabulares como los de X5, 2–4 capas suele ser suficiente. Los Modelos de Lenguaje Grandes (LLMs) como Claude usan 32–96 capas porque el lenguaje es vastamente más complejo.

### Dentro de cada bloque Transformer

Cada capa no es solo atención pura. El bloque completo es:

```
                   x (embedding de entrada)
                         ↓
               ┌── Layer Norm ────┐
               │                 │
               ↓                 │  ← conexión residual
        Multi-Head Attention      │
               ↓                 │
               └───── + ─────────┘
                         ↓
               ┌── Layer Norm ────┐
               │                 │
               ↓                 │  ← conexión residual
              MLP (2 capas densas)│
               ↓                 │
               └───── + ─────────┘
                         ↓
               x' (embedding enriquecido)
```

Dos detalles clave:

**Conexión residual**: el embedding de entrada se suma al resultado de la atención (y al del MLP). Garantiza que si la capa no aporta nada útil, puede aprender a devolver el input intacto — el gradiente fluye sin degradarse en redes profundas. Sin esto, apilar más de 2–3 capas es muy difícil de entrenar.

**MLP después de la atención**: una vez que cada feature absorbió contexto de las demás, pasa por un Perceptrón Multicapa pequeño (2 capas densas con activación no lineal, independiente por feature). Añade capacidad para transformar la representación enriquecida de formas más complejas que la atención sola.

### Cómo aplica al FT-Transformer de X5

En X5, las "personas en la reunión" son las ~240 features tokenizadas: cada columna del store (RSI, K, LOTAJES_M, score_fundamental, n_ordenes_abiertas, etc.) se convierte en un embedding de dimensión D antes de entrar al Transformer.

```
RSI = 72.3  →  embedding D-dim  ──┐
K = 1.0     →  embedding D-dim  ──┤
MACD = ...  →  embedding D-dim  ──┼──  L capas Transformer, H heads  ──► trunk ──► 3 heads
LAMBDA = .. →  embedding D-dim  ──┤
...         →  embedding D-dim  ──┘
```

La atención aprende qué features interactúan para predecir el retorno. Por ejemplo:
- Descubre que `LOTAJES_M` importa más cuando `n_ordenes_abiertas` es alto (exposición compuesta).
- Descubre que `K` interactúa con `sma_ratio_50_200` de formas distintas según régimen.

Esas interacciones son imposibles de capturar con una MLP o con LightGBM de forma explícita — el Transformer las descubre por sí solo durante el entrenamiento.

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

## El problema de las rachas bajistas — registros periódicos

### El gap del store solo-OC

Imagina este escenario:

```
Lunes 09:00  → BTC abre en $95.000. El sistema tiene 8 posiciones abiertas.
Lunes 15:00  → BTC cae a $92.000. Posiciones en rojo. Ninguna cierra (aún no toca stop loss).
Martes 10:00 → BTC cae a $88.000. Más rojo. Ninguna cierra.
Miércoles    → BTC cae a $83.000. Recién empieza a cerrar posiciones por PERDIDA_MAX.
```

Si el store solo guarda filas al cerrar órdenes, durante **3 días de caída** el modelo no recibió ningún registro nuevo. No sabe que el portfolio estaba sangrando. Cuando finalmente llega la OC del miércoles, ya es demasiado tarde — el daño está hecho.

### La solución: registros periódicos

Cada 4 velas H1 (configurable), aunque no haya ninguna OC, el backtester guarda una fila con el estado actual:

```
timestamp          | tipo       | rsi_14 | drawdown_20 | pnl_flotante_activo | n_ejecucion | LOTAJES_M
-------------------+------------+--------+-------------+---------------------+-------------+----------
Lunes 09:00        | periodico  |   52   |    -0.01    |         0           |     130     |     1
Lunes 13:00        | periodico  |   41   |    -0.03    |       -180          |     130     |     1
Lunes 17:00        | periodico  |   35   |    -0.05    |       -420          |     130     |     1
Martes 09:00       | periodico  |   28   |    -0.08    |       -890          |     130     |     1
Martes 13:00       | periodico  |   24   |    -0.12    |      -1350          |     130     |     1
...
Miércoles 11:00    | oc         |   22   |    -0.15    |      -1800          |     130     |     1   ← recién aquí cerró
```

Ahora el modelo sí tiene señal: "cuando el RSI bajó de 30 y el drawdown superó -0.08 con LOTAJES_M=1 y N=130, el `pnl_flotante` siguió deteriorándose". Con eso puede aprender que en ese contexto conviene reducir N y bajar LOTAJES_M antes de que el stop loss empiece a ejecutarse.

### Variable objetivo de los registros periódicos

La Y de un registro periódico es `pnl_flotante_activo` — el P&L flotante de todas las posiciones abiertas del activo en ese momento. Es negativo durante rachas bajistas, positivo cuando las posiciones van ganando.

```
Comparación de Y por tipo de registro:

tipo="oc"         → Y = retorno_pct de la operación cerrada (ej. -2.3%)
tipo="periodico"  → Y = pnl_flotante_activo en USD (ej. -$890)
```

Son distintas variables en la misma columna. Al entrenar, el modelo aprende dos cosas complementarias:
- Con registros OC: "qué combinación de params genera operaciones rentables"
- Con registros periódicos: "qué combinación de params mantiene el portfolio sano durante adversidad"

### Un registro periódico solo se genera si hay posiciones abiertas

Si el activo no tiene órdenes abiertas en ese momento, no hay `pnl_flotante_activo` que observar — el registro se omite. Solo tiene sentido capturar el estado del portfolio cuando hay algo expuesto al mercado.

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

## El ciclo por vela — cómo aprende el modelo "en todo momento"

Esta sección responde a la pregunta: ¿cómo funciona exactamente el loop de aprendizaje continuo?

### El ciclo completo (4 pasos, cada hora)

Imagina que el reloj marca las 10:00 y acaba de cerrar la vela de las 09:00–10:00.

```
── Fin de la vela de las 09:00–10:00 ─────────────────────────────────────────

Paso 1: Capturar lo que pasó
  - ¿Hubo alguna orden que cerró en esta hora? Si sí → guardar registro "oc":
      features_vela + params_usados + retorno_pct_final
  - ¿Hay posiciones abiertas? Si sí → guardar registro "periodico":
      features_vela + params_usados + pnl_flotante_actual
  → Estos registros nuevos se añaden al store

  Paso 1b: Actualizar el modelo con esos registros nuevos
    - Red Neuronal: dar 1 paso de gradiente con los datos nuevos (aprendizaje online)
    - LightGBM: acumular. Cada ~48 velas (2 días), reentrenar completo

── Apertura de la vela de las 10:00–11:00 ───────────────────────────────────

Paso 2: Observar la cocina de hoy
  - Leer X2 (score fundamental del activo hoy)
  - Leer X3 (RSI, MACD, volatilidad, ATR... de la última vela)
  → "La cocina de las 10:00 está así"

Paso 3: Pedirle al chef que recomiende la receta
  - El modelo (ya actualizado con los datos de las 09:00–10:00) recibe el contexto
  - Responde: "para BTC con estos features, usa K=1.2, N_EXP=1.4, LAMBDA=1/300, n_sizes=90..."
  → Se escribe en config/active_parameters.json

Paso 4: Ejecutar
  - X1 lee config/active_parameters.json
  - Coloca buy limits con esos params para la vela 10:00–11:00
```

### ¿Qué significa "siempre aprendiendo"?

Con Red Neuronal (aprendizaje online), el modelo actualiza sus pesos en cada Paso 1b. Literalmente, el modelo de las 10:00 sabe algo que el modelo de las 09:00 no sabía.

Con LightGBM (batch frecuente), el modelo acumula registros y cada ~48 horas hace un reentrenamiento completo. No es "online" en sentido estricto, pero el efecto práctico es similar: el modelo se mantiene actualizado con la historia reciente.

### Ejemplo concreto: BTC en una semana volátil

```
Lunes 09:00   → Paso 1: nada cerró. 3 posiciones abiertas, PnL −$400. Guarda "periodico".
                Paso 1b: NN aprende que K=1 + RSI=72 + PnL_flotante=−0.4% → no es buena señal
                Paso 2: RSI=72, score_fundamental=0.61
                Paso 3: modelo recomienda reducir N_EXP a 1.1 (más conservador)
                Paso 4: X1 usa N_EXP=1.1 para las nuevas órdenes de las 09:00–10:00

Lunes 10:00   → Paso 1: tampoco cerró nada. PnL flotante = −$600. Otro "periodico".
                Paso 1b: NN refuerza: "con estas condiciones, el sistema está sufriendo"
                Paso 3: modelo recomienda bajar n_sizes_ejecucion a 70 (menos exposición)
                Paso 4: X1 usa n_sizes=70

Lunes 14:00   → Paso 1: 2 posiciones cerraron. Retorno −3.2% y −2.8%. Guarda 2 registros "oc".
                Paso 1b: NN aprende: "K=1 + RSI_alto + mercado bajista → mal resultado"
                Paso 3: modelo ahora recomienda parámetros más defensivos (A alto, LAMBDA bajo)
```

El modelo no esperó al lunes siguiente para aprender del crash del lunes — aprendió vela por vela mientras ocurría.

### La diferencia clave respecto al diseño anterior

**Antes (batch):** el modelo entrenaba periódicamente (ej. cada 100 trades) en una sesión separada `--train`. Entre sesiones, usaba el modelo antiguo aunque el mercado hubiera cambiado drásticamente.

**Ahora (continuo):** el modelo se actualiza en cada vela. El ciclo `--vela` hace todo: captura → aprende → recomienda. No hay una sesión de entrenamiento separada en producción normal — el aprendizaje es parte del loop de trading.

---

## El airbag — cuando el modelo no reacciona a tiempo

El modelo aprende patrones del pasado. Un crash repentino puede ser tan diferente a todo lo que vio antes que no reaccione a tiempo: recomienda params normales mientras el precio cae 8% en 4 horas.

Para ese caso existe el **airbag**: una regla explícita, no aprendida, que actúa de forma independiente a lo que el modelo recomiende.

```
Si en las últimas 4 velas H1 el precio cayó más del umbral configurado:
  → forzar LOTAJES_M al mínimo (1)
  → forzar n_sizes_ejecucion al mínimo permitido
  → no abrir nuevas órdenes hasta que el precio se recupere a la mitad del umbral
```

El airbag es el último recurso — existe pero no debería ser el mecanismo principal. La idea es que, con suficiente historia de crashes, el modelo aprenda a recomendar params conservadores antes de que el airbag se active. Si el airbag se dispara frecuentemente, es señal de que el modelo necesita más datos de ese tipo de escenario.

Los umbrales por activo (`AIRBAG_THRESHOLD`) van en `config.py`: 8% para crypto, 5% para acciones.

---

## Estado sin entrenar (UNTRAINED)

Antes de que el store tenga suficientes trades (~500 por activo), X5 no tiene con qué entrenar un modelo útil. En ese estado:

- X5 devuelve los parámetros de `config.py` tal cual — no toca nada.
- X1 sigue operando con los params manuales.
- El campo `model_status` en `config/active_parameters.json` vale `"untrained"` para ese activo.

El estado avanza automáticamente:

```
Menos de 500 trades  → untrained (X1 usa config.py)
500 a 5.000 trades   → lgbm     (X1 usa params del modelo V1)
Más de 5.000 trades  → ftt      (X1 usa params del modelo V2)
```

Cada activo avanza de forma independiente: BTCUSD puede estar en `lgbm` mientras TSLA sigue en `untrained` dentro de la misma corrida.

---

## Glosario

| Término | Qué significa en este proyecto |
|---|---|
| **Surrogate model** | Un modelo que "imita" el sistema real (el mercado + las operaciones) para poder hacer predicciones baratas. X5 es un surrogate: en vez de esperar a que el mercado decida, el modelo predice el resultado. |
| **Tabular data** | Datos organizados en filas y columnas, como una planilla Excel. Cada fila es una operación; cada columna es una feature. Diferente a imágenes (pixeles) o texto (palabras). |
| **Feature** | Una columna de input del modelo. Ej: `RSI`, `K`, `n_ordenes_abiertas`. |
| **Embedding** | Representación de un valor como un vector de números. Convierte "RSI = 72.3" en un vector de tamaño fijo que el modelo puede procesar con más riqueza. |
| **Atención / Attention** | Mecanismo que permite que una feature "mire" a las demás y ajuste su representación. Base de los Transformers (y de los LLMs). |
| **Q / K / V (Query, Key, Value)** | Los tres vectores que el Transformer deriva de cada embedding. Q = "qué busco", K = "qué ofrezco", V = "lo que comparto si me encuentran relevante". La atención se calcula como suma ponderada de Values, donde los pesos vienen del producto Q·K. |
| **Softmax** | Función que convierte un vector de números arbitrarios en probabilidades que suman 1. En atención: convierte los scores Q·K en pesos de mezcla. |
| **Multi-Head Attention (MHA)** | Ejecutar el mecanismo Q/K/V varias veces en paralelo (con pesos distintos por cabeza), concatenar los resultados y proyectarlos. Cada cabeza puede capturar un tipo distinto de relación entre features. |
| **Conexión residual** | Sumar el input de una capa a su output: `x' = capa(x) + x`. Permite que el gradiente fluya sin degradarse en redes con muchas capas. Sin esto, apilar más de 2–3 bloques es muy difícil de entrenar. |
| **Layer Norm (Normalización de capa)** | Normaliza los valores de un embedding para que tengan media 0 y desviación estándar 1 antes de cada sub-bloque. Estabiliza el entrenamiento. |
| **Transformer** | Arquitectura de red neuronal basada en atención. Originalmente para texto (BERT, GPT); adaptada para datos tabulares en el FT-Transformer. Cada bloque tiene: Layer Norm → Multi-Head Attention → conexión residual → Layer Norm → MLP → conexión residual. |
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
| **Store de trades** | El dataset de entrenamiento de X5: una tabla con dos tipos de fila — `"oc"` (una por trade cerrado, Y=retorno_pct) y `"periodico"` (una cada T velas H1, Y=pnl_flotante_activo). Ambos tipos comparten el mismo CSV por activo. |
| **Registro periódico** | Fila del store generada cada T velas H1 independientemente de si hay OC. Captura el estado del portfolio durante rachas adversas cuando ninguna orden cierra. Solo se genera si hay posiciones abiertas. |
| **pnl_flotante_activo** | P&L flotante (no realizado) de todas las posiciones abiertas de un activo en un momento dado. Variable objetivo de los registros periódicos. Negativo = posiciones en pérdida. |
| **Aprendizaje online** | El modelo actualiza sus pesos con cada nuevo dato (o mini-lote pequeño), sin esperar a acumular un dataset grande. Natural en Redes Neuronales vía un paso de gradiente por vela. |
| **Aprendizaje batch** | El modelo se reentrena sobre todo el dataset acumulado en una sola sesión. LightGBM usa este modo; el reentrenamiento completo ocurre cada `X5_RETRAIN_EVERY_N_VELAS` velas. |
| **`--vela`** | Modo normal de producción de X5: ejecuta los 4 pasos del ciclo por vela (capturar → actualizar modelo → inferir params → escribir active_parameters.json). Llamado por X1 en Fase 2 al cierre de cada vela H1. |
| **Airbag** | Regla explícita (no aprendida) que anula la recomendación del modelo cuando el precio cae más de un umbral en las últimas 4 velas H1. Fuerza params mínimos de seguridad independientemente de lo que X5 recomiende. |
| **model_status** | Campo en `config/active_parameters.json` que indica el estado del modelo por activo: `"untrained"` (sin datos suficientes), `"lgbm"` (V1 activo), `"ftt"` (V2 activo). X1 lo lee para decidir si usar los params del modelo o caer back a `config.py`. |
| **UNTRAINED** | Estado inicial de X5 para un activo cuando el store tiene menos de ~500 trades. En este estado X5 devuelve los params de `config.py` sin modificar. |
| **OE / OA context** | Los features de X2+X3 se capturan en dos momentos distintos: al colocar el buy limit (OE) y al ejecutarse la orden (OA). Ambos entran al modelo. Los features de OC (cierre) solo se guardan para análisis — no entran al modelo porque son información del futuro. |
