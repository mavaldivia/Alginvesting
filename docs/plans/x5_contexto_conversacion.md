# Contexto integral para continuar el rediseño de X5 / X5_alt

## Propósito

Este documento consolida el contexto técnico, las definiciones, las correcciones conceptuales y las decisiones conversadas sobre el proyecto X5 y su variante X5_alt.

Debe utilizarse como contexto de trabajo antes de modificar notebooks, scripts, configuraciones o documentos asociados. Cuando exista una contradicción entre una definición antigua y una decisión posterior, prevalece la sección “Definiciones vigentes” y la última decisión explícita.

El objetivo actual no es implementar inmediatamente reglas de trading. Primero se busca redefinir correctamente qué deben analizar X5_P1 y X5_P2 y qué hipótesis deben construirse para que, posteriormente, X5 pueda aprender o validar cómo configurar sus parámetros por activo.

---

## 1. Contexto general de X5

X5 es un sistema de trading algorítmico, llamado también “el cerebro”, que trabaja inicialmente con activos como:

    BTCUSD
    ETHUSD
    TSLA
    GOOGL
    NVDA
    AMZN

La idea es estudiar cada activo de forma independiente, utilizando su propio historial, sus propias variables de estado y sus propios parámetros.

### Restricción fundamental: análisis por activo

Todo el análisis que se está redefiniendo debe ser por activo, no por cuenta agregada ni mezclando activos.

    BTCUSD → historial, variables y parámetros propios
    ETHUSD → historial, variables y parámetros propios
    TSLA   → historial, variables y parámetros propios

No se deben utilizar, dentro del análisis actual:

- drawdown total de la cuenta;
- equity agregada de la cuenta;
- P&L flotante de la cuenta;
- exposición agregada entre activos;
- cantidad total de posiciones de la cuenta;
- capital comprometido global;
- estado de otros activos para decidir los parámetros de un activo.

Cuando se hable de drawdown en esta etapa, debe entenderse como drawdown del precio del activo.

---

## 2. Arquitectura conceptual histórica

### X0 — datos y soportes

Construye y evalúa soportes a partir de datos históricos de precio. La función objetivo de soportes utiliza factores de aislamiento, recencia, distancia, volumen y fuerza del rechazo.

### X1 — trading y gestión de órdenes

Gestiona las órdenes y sus estados:

1. Orden 0.
2. Orden en espera, OE.
3. Orden activa, OA.
4. Orden cerrada.

X1 crea órdenes en espera, activa posiciones, gestiona trailing stops, aplica cierres y registra resultados.

### X5 — exploración y optimización

Explora parámetros por activo y busca configuraciones que maximicen el resultado del recorrido completo del horizonte histórico. La idea inicial era barrer el horizonte temporal varias veces y encontrar parámetros que maximicen el dinero cerrado total, no solamente métricas parciales por operación.

### X5_alt — variante paralela y simplificada

X5_alt es una versión alternativa y simplificada. No reemplaza al X5 original.

Actualmente contiene:

- X5_P1.ipynb: construcción de una tabla maestra temporal.
- X5_P2.ipynb: investigación exploratoria y descriptiva sobre la tabla maestra.

La implementación de una futura Fase 3, X5_alternativo.py, debe esperar hasta observar resultados concretos de P1 y P2.

---

## 3. Estado actual de X5_P1.ipynb

X5_P1.ipynb recibe un activo mediante:

    valor = 'BTCUSD'

Su objetivo actual es construir una tabla continua, una fila por vela H1, combinando:

1. Precio OHLCV desde Data/{valor}.csv.
2. Indicadores técnicos de X3.
3. Variables fundamentales de X2 desde resources/x2/x2_history.json.

El notebook:

- ordena las velas por DateTime;
- elimina duplicados temporales;
- calcula indicadores técnicos sobre el histórico;
- elimina temporalmente las variables de distancia a soportes porque están fuera del alcance actual de v0;
- filtra los fundamentales por activo;
- utiliza merge_asof hacia atrás para mantener el último fundamental conocido;
- guarda el resultado como resources/x5_alt/{valor}_tabla_maestra.csv.

### Redefinición necesaria de P1

P1 fue construido como una tabla maestra inicial. Ahora se considera necesario ampliarlo para que no sea solo una unión de columnas, sino también una capa de documentación y calidad de datos.

P1 debería explicar mejor, para cada variable:

- nombre del campo;
- fuente;
- significado;
- unidad;
- fórmula de cálculo;
- granularidad esperada;
- granularidad observada;
- primera fecha disponible;
- última fecha disponible;
- cobertura;
- porcentaje de valores faltantes;
- si se aplica forward-fill;
- edad de la información cuando se propaga;
- limitaciones de interpretación.

También debería producir variables más útiles para X5, no necesariamente incorporar todos los indicadores disponibles. Se debe evaluar qué campos técnicos realmente ayudan a explicar el comportamiento de los parámetros y cuáles solo generan relaciones triviales.

---

## 4. Estado actual de X5_P2.ipynb

X5_P2.ipynb carga:

    resources/x5_alt/{valor}_tabla_maestra.csv

El notebook actual realiza principalmente:

- inventario inicial de variables;
- clasificación en familias Técnico/Fundamental/Otra;
- correlaciones Pearson, Spearman y Kendall;
- gráficos de series normalizadas;
- scatter con regresión lineal;
- precio promedio por deciles;
- regresión ceteris paribus;
- VIF para multicolinealidad;
- comparación entre especificación completa y reducida.

### Problema detectado en el enfoque de P2

El análisis actual de correlaciones no responde suficientemente a la pregunta de trading.

Por ejemplo, estudiar si Close está altamente correlacionado con SMA_20, SMA_50 o SMA_200 produce resultados previsiblemente altos porque las medias móviles se construyen a partir del propio precio. Esa correlación no ayuda a decidir cómo configurar N, A o factor_B.

El interés real no es:

> “¿Qué variables están correlacionadas con el nivel del precio?”

El interés real es:

> “¿Qué variables describen el estado del activo y podrían explicar qué configuración de X5 conviene utilizar en ese estado?”

Por lo tanto, P2 debe evolucionar desde un análisis genérico variable-precio hacia un análisis de:

    estado del activo → hipótesis de configuración → validación por backtesting

---

## 5. Definiciones vigentes de parámetros independientes

Después de redefinir B, la lista de parámetros independientes queda así:

    N
    A
    factor_B
    K
    N_EXP
    LAMBDA
    LOTAJES_M

PERDIDA_MAX queda temporalmente en pausa porque se está evaluando moverla a una capa externa de gestión de riesgo.

B ya no es independiente:

    B = factor_B * A

El rango tentativo de factor_B es:

    factor_B ∈ [0.2, 0.7]

El valor histórico productivo de referencia era aproximadamente:

    A = 3
    B = 1.5
    factor_B = 1.5 / 3 = 0.5

---

## 6. Parámetro N

### Qué controla

N, también llamado n_sizes_ejecucion, representa la cantidad de soportes activos que X1 mantiene para un activo.

Más soportes implican:

- cobertura más amplia del rango;
- entradas más finas o densas;
- capital más fragmentado;
- mayor número potencial de posiciones.

Menos soportes implican:

- cobertura más gruesa;
- posiciones más concentradas;
- menor cantidad de niveles activos.

### Hipótesis vigente

La hipótesis inicial se refiere exclusivamente al estado del activo:

    drawdown del activo sano + volatilidad baja o normal
    → N alto

    drawdown profundo/no sano + volatilidad alta
    → N bajo

La intuición es que, cuando el activo se encuentra en una mala condición y además se mueve con alta amplitud, conviene reducir la cantidad de soportes activos para protegerse de una exposición demasiado fragmentada o de demasiadas entradas.

### Variables candidatas para explicar N

- drawdown del precio del activo;
- profundidad del drawdown;
- duración del drawdown;
- tiempo desde el máximo reciente;
- velocidad de caída;
- velocidad de recuperación;
- volatilidad reciente;
- volatilidad corta versus larga;
- ATR relativo;
- ruido;
- tendencia y fuerza de tendencia;
- liquidez y spread;
- estado fundamental del activo.

### Drawdown del activo

No debe usarse drawdown de la cuenta. Deben construirse medidas sobre el precio del activo, por ejemplo:

    drawdown_activo = (precio_actual - maximo_historico_hasta_t) / maximo_historico_hasta_t

Además del máximo histórico, conviene calcular ventanas:

    drawdown_7d
    drawdown_30d
    drawdown_90d
    drawdown_365d
    drawdown_desde_maximo_historico

También interesa medir:

- duración del drawdown;
- profundidad máxima;
- tiempo desde el máximo;
- recuperación desde el mínimo;
- si la recuperación está confirmada o es solo un rebote.

---

## 7. Parámetro A

### Qué controla

A es un umbral monetario en USD y actualmente cumple dos funciones en X1.

#### A.1. Creación de Órdenes en Espera

Un soporte recibe un buy limit cuando:

    (P0 - Pi) * L >= A

donde:

- P0 es el precio actual;
- Pi es el precio del soporte;
- L = LOTAJES[valor] * UNITS[valor] es la exposición en USD por unidad de precio.

Un A alto exige que el soporte esté más alejado del precio actual antes de crear una OE.

Efectos:

- menos órdenes cercanas;
- entradas más separadas;
- menor densidad de órdenes.

#### A.2. Activación del primer trailing stop ganador

Mientras una posición no tiene stop loss, el primer stop ganador se activa cuando:

    ganancia = (P0 - Pi) * L >= A

Un A alto retrasa la activación del primer trailing stop. Esto permite que la posición tenga más margen antes de asegurar ganancias, pero también puede devolver más ganancia no realizada si el precio revierte.

### Hipótesis vigente

    volatilidad alta
    → A más alto

    volatilidad baja
    → A más bajo

La intuición es que, con alta volatilidad, conviene evitar órdenes excesivamente cercanas y exigir un movimiento más significativo.

### Complicación importante

A mezcla dos roles que pueden empujar en direcciones distintas:

- para las OE, un A alto filtra entradas cercanas;
- para el trailing, un A alto retrasa la protección de una posición ganadora.

Por eso, el efecto del drawdown del activo sobre A no tiene una dirección única.

Si el activo está en drawdown profundo:

- un A alto puede reducir nuevas entradas;
- pero también puede retrasar la activación del trailing.

Esto puede llevar posteriormente a separar conceptualmente:

    A_OE       = margen para crear órdenes en espera
    A_TRAILING = ganancia necesaria para activar el primer trailing

Por ahora se mantiene un único A y se debe medir el efecto neto mediante backtesting.

### Variables candidatas para A

- ATR absoluto y relativo;
- volatilidad realizada;
- ratio de volatilidad corta/larga;
- ruido;
- spread;
- liquidez;
- fuerza de tendencia;
- drawdown del activo;
- velocidad de cambio de volatilidad;
- estado fundamental e incertidumbre.

Como A está expresado en USD y el ATR normalmente está expresado en unidades de precio, puede considerarse:

    ATR_USD = ATR_precio * L

y luego:

    A = multiplicador_ATR * ATR_USD

Esto permitiría que A refleje la escala normal de movimiento del activo.

---

## 8. Factor_B y B

### Definición vigente

B no es un parámetro independiente:

    B = factor_B * A

factor_B es adimensional y tentativamente se explora en:

    0.2 ≤ factor_B ≤ 0.7

Si A = 3 y el B productivo histórico era 1.5:

    factor_B = 0.5

### Qué controla

Una vez activado el trailing stop, B determina la distancia monetaria que se mantiene entre el precio actual y el stop:

    sl_nuevo = P0 - B / L

El stop solo se mueve hacia arriba; nunca retrocede.

factor_B controla qué proporción de A se utiliza como margen del trailing:

- factor bajo → trailing relativamente ajustado;
- factor alto → trailing relativamente holgado.

### Hipótesis iniciales

    volatilidad alta
    → factor_B más alto

para evitar que fluctuaciones normales activen el stop demasiado pronto.

    volatilidad baja
    → factor_B más bajo

para asegurar ganancias con mayor rapidez.

También se considera:

    tendencia fuerte y persistente
    → factor_B más alto

para permitir que la posición continúe desarrollándose.

    mercado lateral o muy ruidoso
    → factor_B bajo o intermedio

Esta última relación debe comprobarse con backtesting, porque un trailing muy ajustado puede cerrar por ruido y uno muy holgado puede devolver demasiada ganancia.

### Interacción A–factor_B

No deben optimizarse como si fueran independientes:

    B = factor_B * A

Un A alto y un factor_B alto producen un B absoluto mucho mayor.

Combinaciones iniciales:

| Contexto del activo | A | factor_B | Intuición |
|---|---:|---:|---|
| Baja volatilidad, tendencia clara | Bajo/medio | Bajo/medio | Entradas cercanas y protección rápida |
| Alta volatilidad, tendencia clara | Alto | Medio/alto | Menos entradas y trailing más holgado |
| Alta volatilidad, lateral | Alto | Por validar | Filtrar entradas y medir tolerancia del trailing |
| Drawdown profundo y deterioro | Alto para filtrar OE | Bajo/medio para proteger | Menor exposición nueva y menor tolerancia en posiciones |
| Recuperación del drawdown | Medio | Medio/alto | Permitir recuperación sin configuración demasiado agresiva |

La dualidad de roles de A debe considerarse al interpretar estos resultados.

---

## 9. ATR, True Range, volatilidad, ruido, liquidez e incertidumbre

### True Range

El True Range no es simplemente la diferencia entre dos cierres. Tampoco es siempre High - Low.

Para una vela:

    TR = máximo de:

    High - Low
    |High - Cierre anterior|
    |Low - Cierre anterior|

La interpretación correcta es:

> El True Range es la máxima distancia absoluta recorrida por la vela actual, tomando en cuenta los extremos de la vela y cualquier salto respecto del cierre anterior.

El cierre actual no participa directamente. Participan High actual, Low actual y Close anterior.

Ejemplo:

    Cierre anterior = 100
    High actual     = 112
    Low actual      = 110
    Close actual    = 111

    High - Low               = 2
    |High - cierre anterior| = 12
    |Low - cierre anterior|  = 10

    TR = 12

Aunque el rango interno de la vela es 2, la distancia real respecto del cierre anterior fue 12.

### ATR

El ATR es un promedio móvil de varios True Range, normalmente de 14 períodos:

    ATR_14 = promedio_móvil(TR, 14)

El ATR mide la magnitud típica del movimiento, no su dirección.

Debe distinguirse entre:

- ATR absoluto: unidades de precio;
- ATR relativo: ATR / precio;
- desviación estándar de retornos: dispersión porcentual de los retornos.

### Ruido

Ruido es movimiento sin dirección persistente.

Ejemplo:

    100 → 103 → 99 → 104 → 98 → 102

El precio se mueve mucho, pero no avanza claramente.

Medidas candidatas:

- cambios de signo en los retornos;
- ratio entre movimiento total y movimiento neto;
- mechas largas;
- ATR alto con retorno acumulado bajo;
- autocorrelación negativa de retornos cortos.

Una medida intuitiva sería:

    ruido = movimiento_total / |movimiento_neto|

### Liquidez

Liquidez es la facilidad para ejecutar una orden sin mover demasiado el precio.

Variables candidatas:

- spread;
- Tick Volume;
- volumen relativo;
- frecuencia de operaciones;
- slippage;
- profundidad del mercado, si está disponible;
- impacto de una orden sobre el precio.

Un activo puede tener el mismo ATR que otro, pero ser mucho más riesgoso de operar si tiene baja liquidez.

### Incertidumbre

Incertidumbre es la falta de confianza sobre cuál será el comportamiento siguiente del activo.

No es igual a volatilidad:

- volatilidad = cuánto se mueve el precio;
- incertidumbre = qué tan difícil es anticipar el siguiente comportamiento.

Puede haber alta volatilidad y baja incertidumbre si existe una tendencia clara. También puede haber baja volatilidad y alta incertidumbre si el activo está comprimido, con señales contradictorias, cerca de una ruptura.

Proxies posibles:

- divergencia entre indicadores;
- cambios frecuentes de régimen;
- volatilidad creciendo rápidamente;
- fundamentales contradictorios;
- información fundamental antigua;
- retornos extremos;
- baja estabilidad temporal de las relaciones.

---

## 10. PERDIDA_MAX: decisión temporalmente pausada

PERDIDA_MAX actualmente cierra una posición cuando:

    perdida = (Pi - P0) * L

supera el umbral.

Inicialmente se discutió tratarla como una función del activo utilizando MAE, ATR, drawdown y tendencia. Después surgió una redefinición más estructural:

PERDIDA_MAX podría ser una variable externa de gestión de riesgo, por ejemplo:

    RIESGO_MAX_PCT

y:

    PERDIDA_MAX_USD = RIESGO_MAX_PCT * CAPITAL_BASE

La versión más coherente con el tratamiento independiente por activo sería:

    PERDIDA_MAX_USD = RIESGO_MAX_PCT * CAPITAL_BASE_ACTIVO

No se ha tomado una decisión definitiva. Por ahora:

- no se profundiza en PERDIDA_MAX;
- no se incluye como foco de P2;
- queda pausada como posible capa externa de gestión de riesgo.

---

## 11. Parámetro LOTAJES_M

LOTAJES_M multiplica el lote mínimo del broker:

    LOTAJES[valor] = LOTAJES_M[valor] * MIN_LOTAJES[valor]

Actualmente:

    LOTAJES_M = 1

Su rango X5 es degenerado:

    (1, 1)

Por diseño, X5 opera a lotaje mínimo. Por lo tanto, aunque forma parte del inventario de parámetros, no es prioritario analizarlo como función del estado histórico del activo mientras permanezca fijo.

---

## 12. Parámetro K

En X0:

    y = Low_left + High_left + K * (Low_right + High_right)

K pondera el aislamiento temporal futuro respecto del pasado.

- left: distancia temporal hacia atrás hasta la vela más cercana que contiene el Low/High relevante;
- right: distancia temporal hacia adelante.

Interpretación:

- K alto: mayor valor a que el nivel haya permanecido intacto después de formarse;
- K bajo: mayor valor relativo al contexto previo a la formación.

Variables candidatas:

- persistencia histórica de niveles;
- frecuencia de retesteo;
- tasa de rechazo posterior;
- estabilidad del régimen;
- cambios de tendencia;
- simetría entre aislamiento previo y posterior.

Hipótesis:

    mercado estable y niveles persistentes
    → K más alto

    muchos cambios de régimen o rupturas
    → K más bajo

Inicialmente conviene estudiarlo como parámetro relativamente estable por activo, no necesariamente dinámico en cada vela.

---

## 13. Parámetro N_EXP

En X0:

    w = t ** N_EXP

donde:

- t = 0: vela más antigua del período;
- t = 1: vela más reciente.

N_EXP controla cuánto se concentra el peso en observaciones recientes.

- N_EXP alto: las velas recientes dominan más;
- N_EXP bajo: se conserva más memoria histórica.

Variables candidatas:

- cambio de régimen;
- ratio de volatilidad corta/larga;
- aceleración de la tendencia;
- variación reciente de máximos y mínimos;
- pérdida de efectividad de soportes antiguos;
- estabilidad de relaciones históricas.

Hipótesis:

    mercado estable y repetitivo
    → N_EXP más bajo

    cambio de régimen o volatilidad creciente
    → N_EXP más alto

Este es un buen candidato a depender dinámicamente del estado del activo.

---

## 14. Parámetro LAMBDA

La función objetivo de soportes es:

    FO = mean(z) - LAMBDA * cv(H_n)

donde:

    z = y * w * h_dist * v * f

cv(H_n) es el coeficiente de variación de las distancias entre soportes consecutivos, incluyendo P_min y P_max como anclas de borde.

LAMBDA penaliza que los soportes se amontonen en una zona del rango.

- LAMBDA alto: distribución más pareja, sacrificando posiblemente parte de mean(z);
- LAMBDA bajo: se prioriza evidencia individual y se permite concentración.

Variables candidatas:

- amplitud del rango reciente;
- densidad de soportes candidatos;
- concentración alrededor del precio actual;
- huecos en la cobertura del rango;
- mercado lateral versus tendencial;
- volatilidad relativa;
- capacidad de reacción histórica en distintas zonas.

Hipótesis:

    mercado lateral o rango amplio con soportes muy concentrados
    → LAMBDA más alto

    tendencia fuerte con evidencia naturalmente concentrada
    → LAMBDA más bajo

LAMBDA debe analizarse considerando N, porque la penalización por distribución cambia según la cantidad de soportes.

### Inconsistencia que debe resolverse

El valor productivo actual documentado es:

    LAMBDA = 1/5 = 0.2

Pero el rango de exploración X5 informado es:

    (0.001, 0.02)

Ese rango no cubre el valor productivo actual. Antes de optimizar LAMBDA hay que decidir si:

- el valor 0.2 es realmente el productivo vigente;
- el rango X5 está desactualizado;
- la escala de la función objetivo cambió;
- debe redefinirse el rango.

No se deben sacar conclusiones de una exploración que no contiene el valor productivo de referencia.

---

## 15. Qué debe medir realmente P2

P2 debe dejar de centrarse en correlaciones simples entre variables y el nivel del precio.

El objetivo es construir variables de estado del activo y estudiar si esas variables explican diferencias en la conveniencia de distintas configuraciones.

### Variables de estado del activo

#### Precio y retornos

- retornos logarítmicos;
- retornos acumulados a 6h, 24h, 3d y 7d;
- retorno neto versus movimiento total;
- posición en rango móvil;
- distancia normalizada a máximos y mínimos.

#### Volatilidad

- ATR absoluto;
- ATR relativo al precio;
- desviación estándar móvil de retornos;
- volatilidad realizada;
- volatilidad corta/larga;
- cambio de volatilidad;
- volatilidad alcista versus bajista;
- frecuencia de movimientos extremos.

#### Drawdown del activo

- drawdown desde máximo histórico;
- drawdown de 7d, 30d, 90d y 365d;
- profundidad;
- duración;
- velocidad de caída;
- recuperación desde mínimo;
- tiempo desde máximo.

#### Tendencia y régimen

- pendiente de medias móviles;
- distancia normalizada a medias móviles;
- ADX o fuerza tendencial;
- persistencia de retornos;
- proporción de velas alcistas;
- bull/bear/sideways;
- ruptura o permanencia dentro de rango.

#### Ruido

- cambios de signo de retornos;
- relación movimiento total/movimiento neto;
- mechas;
- reversals de corto plazo;
- ATR alto con retorno acumulado bajo.

#### Liquidez

- spread;
- Tick Volume normalizado;
- volumen relativo;
- cambios bruscos de volumen;
- slippage, si existe;
- profundidad, si existe.

#### Fundamentales

- nivel del score;
- cambio del score;
- dirección del cambio;
- magnitud del cambio;
- edad desde la última actualización;
- frecuencia efectiva de actualización;
- estabilidad;
- contradicción entre componentes;
- calidad de la fuente.

---

## 16. Cómo deben interpretarse las medias móviles

No interesa principalmente saber si Close está altamente correlacionado con SMA_20, SMA_50 o SMA_200. Eso es esperable porque las medias móviles se construyen con el propio precio.

Sí pueden ser útiles transformaciones como:

    distancia_SMA50 = (Close - SMA50) / ATR
    pendiente_SMA50 = cambio_de_SMA50 / ATR

También:

- pendiente de la media;
- aceleración de la pendiente;
- distancia del precio a la media en unidades de ATR;
- cruce normalizado;
- duración sobre/debajo de la media;
- diferencia entre tendencia corta y larga.

Estas transformaciones describen el estado del activo; el nivel bruto de la media aporta mucho menos.

---

## 17. Cómo estudiar A y factor_B correctamente

No basta con correlacionar A o factor_B con una variable. La relación debe evaluarse mediante simulación.

La estructura correcta sería:

    estado histórico del activo X_t
    → configuración propuesta θ_t
    → ejecución de X1
    → resultado de trading

Ejemplo:

    volatilidad alta
    drawdown profundo
    tendencia bajista
    ruido alto

    → probar A alto y factor_B bajo/medio
    → medir resultado de órdenes y trailing

Métricas de evaluación:

- dinero cerrado total;
- retorno;
- cantidad de operaciones;
- proporción de operaciones ganadoras;
- duración de posiciones;
- MAE;
- MFE;
- dinero devuelto por trailing;
- frecuencia de activación del trailing;
- cantidad de órdenes en espera creadas;
- estabilidad temporal;
- desempeño por régimen.

Para A se debe separar el efecto en:

1. densidad/distancia de nuevas OE;
2. retraso de activación del primer trailing.

Para factor_B se debe estudiar:

1. frecuencia de stop por ruido;
2. ganancia protegida;
3. ganancia devuelta antes del cierre;
4. capacidad de capturar tendencias largas.

---

## 18. Cómo estudiar K, N_EXP y LAMBDA

Estos tres parámetros actúan dentro del algoritmo de soportes, por lo que el análisis debe tener dos niveles.

### Nivel 1: efecto sobre los soportes

Medir:

- cantidad de soportes;
- calidad individual;
- recencia;
- cobertura del rango;
- concentración;
- distancia entre niveles;
- simetría de aislamiento;
- estabilidad de los niveles.

### Nivel 2: efecto posterior en X1

Usar esos soportes en la simulación y medir:

- órdenes creadas;
- órdenes activadas;
- cierres;
- dinero cerrado;
- MAE/MFE;
- duración;
- estabilidad por período.

No debe concluirse que un valor es bueno solo porque genera soportes visualmente bien distribuidos. Debe demostrar utilidad operativa en X1.

---

## 19. Orden de trabajo recomendado

### Etapa A — redefinir la tabla maestra

Revisar P1 para que documente bien los campos, sus fuentes y su calidad.

### Etapa B — construir variables de estado del activo

Prioridad inicial:

1. drawdown del activo;
2. ATR y volatilidad relativa;
3. ruido;
4. tendencia/régimen;
5. liquidez;
6. fundamentales y antigüedad de la información.

### Etapa C — analizar N

Construir y evaluar:

    N = f(drawdown_activo, volatilidad, régimen, liquidez, ...)

### Etapa D — analizar A y factor_B conjuntamente

Mantener:

    B = factor_B * A

y estudiar la interacción entre ambos, separando los efectos de A sobre OE y trailing.

### Etapa E — revisar la arquitectura de PERDIDA_MAX

Decidir si se mantiene como parámetro por activo o si se transforma en riesgo porcentual externo. Por ahora está pausada.

### Etapa F — analizar K, N_EXP y LAMBDA

Primero medir su efecto sobre soportes; después, su efecto en X1 y en el resultado económico.

### Etapa G — recién después crear hipótesis dinámicas

La formulación futura podría ser:

    N_t = f_N(estado_activo_t)
    A_t = f_A(estado_activo_t)
    factor_B_t = f_B(estado_activo_t)
    K_t = f_K(estado_activo_t)
    N_EXP_t = f_N_EXP(estado_activo_t)
    LAMBDA_t = f_LAMBDA(estado_activo_t)

Pero estas funciones no deben implementarse antes de estudiar resultados históricos y backtesting.

---

## 20. Principios que deben mantenerse

1. Todo se analiza por activo.
2. No usar variables de cuenta para explicar parámetros del activo en esta etapa.
3. No tratar B como independiente.
4. Mantener B = factor_B * A.
5. No confundir correlación con utilidad operativa.
6. No usar el nivel del precio como principal variable explicativa.
7. Preferir retornos, volatilidad, drawdown, régimen, ruido y transformaciones normalizadas.
8. Diferenciar volatilidad de ruido, liquidez e incertidumbre.
9. P2 debe producir evidencia e hipótesis, no reglas prescriptivas definitivas.
10. Las hipótesis se validan con backtesting temporal y, cuando corresponda, walk-forward.
11. No mezclar datos futuros de forma que produzca leakage.
12. Documentar limitaciones de datos fundamentales, especialmente la baja frecuencia y el forward-fill.
13. Tratar LOTAJES_M como fijo mientras X5 opere siempre al mínimo.
14. Revisar la escala/rango de LAMBDA antes de optimizarlo.
15. No iniciar Fase 3 hasta tener resultados concretos de P1/P2.

---

## 21. Estado de decisiones al cierre de la conversación

### Decisiones confirmadas

- X5 se analiza por activo, no por cuenta.
- El drawdown relevante es el drawdown del precio del activo.
- El foco de razonamiento comenzó con N, luego A y factor_B.
- B se redefine como B = factor_B * A.
- factor_B se considera tentativamente dentro de [0.2, 0.7].
- N tiende a ser mayor con drawdown sano y volatilidad baja/normal.
- N tiende a ser menor con drawdown profundo y volatilidad alta.
- A tiende a ser mayor con volatilidad alta y menor con volatilidad baja.
- PERDIDA_MAX queda pausada y podría trasladarse a una capa externa de riesgo.
- No se debe incluir P&L flotante de cuenta ni exposición agregada.
- P2 no debe limitarse a correlaciones entre precio y medias móviles.
- P1 debe mejorar la documentación y calidad de los campos, especialmente fundamentales.

### Decisiones pendientes

- Definir si A debe dividirse en A_OE y A_TRAILING.
- Definir si A será fijo por activo o dinámico en el tiempo.
- Definir si factor_B será fijo por activo o dinámico.
- Definir el tratamiento definitivo de PERDIDA_MAX.
- Definir rango correcto de LAMBDA.
- Determinar qué fundamentales están realmente disponibles y son suficientemente frecuentes.
- Definir el universo final de variables técnicas que entrarán a P1.
- Definir cómo se realizará el backtesting condicional por régimen.
- Decidir si K será estático o dinámico.
- Decidir si N_EXP y LAMBDA deben depender del estado actual del activo o solo optimizarse como valores por activo.

---

## 22. Instrucción de trabajo para Claude

Antes de modificar X5_P1.ipynb, X5_P2.ipynb o cualquier script, leer este documento completo y respetar estas definiciones.

No implementar todavía funciones dinámicas definitivas del tipo N=f(X) o A=f(X) solo porque existan hipótesis intuitivas. Primero:

1. documentar los datos;
2. construir variables de estado del activo;
3. medir su calidad y cobertura;
4. generar hipótesis explícitas;
5. diseñar backtesting condicional;
6. validar fuera de muestra;
7. recién después implementar reglas o funciones prescriptivas.

El objetivo no es descubrir qué variables “predicen el precio” en abstracto. El objetivo es entender qué condiciones históricas del activo hacen más conveniente una configuración específica del sistema X5 y validar esa conveniencia mediante resultados operativos y económicos.

