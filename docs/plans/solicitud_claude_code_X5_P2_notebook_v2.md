# Solicitud para Claude Code --- Construcción de `X5_P2.ipynb`

## Contexto

Estamos trabajando en la revisión y evolución de **X5**, el "cerebro" de
Alginvesting.

Hasta este punto, considerar como **baseline válido** todo lo definido
previamente en el documento de revisión exhaustiva de X5. En particular,
la arquitectura conceptual queda separada de la siguiente forma:

-   **X5_P1**: construye la información / tabla maestra.
-   **X5_P2**: entiende e investiga la información.
-   **P3 futuro**: utiliza el conocimiento obtenido para estudiar,
    gobernar y eventualmente optimizar los parámetros configurables de
    X5.

Actualmente existe un `X5_P2.py` que solamente carga la tabla maestra
generada por P1 e imprime dimensiones y rango temporal. Ese archivo **no
implementa realmente el análisis descrito en su documentación**.

La solicitud es transformar P2 en un verdadero **notebook de
investigación**, llamado:

`X5_P2.ipynb`

El foco inicial será un único activo:

`BTCUSD`

El input debe seguir siendo la tabla maestra construida por P1,
actualmente esperada en una ruta equivalente a:

`resources/x5_alt/{valor}_tabla_maestra.csv`

No recalcular en P2 aquello que corresponde a P1.

------------------------------------------------------------------------

# 1. Objetivo general de P2

`X5_P2.ipynb` debe ser un **notebook exhaustivo de investigación y
análisis exploratorio**.

Su función principal NO es optimizar X5 ni decidir todavía los valores
de parámetros como A, B, N, lotaje, etc.

Su función es responder:

> **¿Qué información tenemos y cómo se han relacionado históricamente el
> precio, los indicadores técnicos y los indicadores fundamentales?**

El notebook debe permitir:

-   explorar visualmente los datos;
-   entender frecuencias y disponibilidad;
-   estudiar relaciones históricas;
-   estudiar correlaciones;
-   analizar relaciones no lineales;
-   realizar análisis ceteris paribus;
-   estudiar estabilidad temporal;
-   estudiar relaciones bajo distintos regímenes;
-   identificar redundancias;
-   separar relaciones contemporáneas de relaciones temporales;
-   explorar, de manera secundaria, potencial predictivo;
-   generar hipótesis para el futuro P3.

La filosofía debe ser:

> **P1 = construir la información → P2 = entender la información → P3 =
> decidir qué hacer con ella.**

------------------------------------------------------------------------

# 2. Principio metodológico fundamental

Quiero una separación **muy explícita** entre tres capas:

1.  **Descriptiva / histórica**
2.  **Prospectiva / predictiva**
3.  **Implicancias / hipótesis para X5**

El **core de P2 debe estar en las relaciones históricas**, no en
predicción.

Como referencia conceptual:

-   aproximadamente **70--80%** del notebook debería ser
    descriptivo/histórico;
-   aproximadamente **15--20%** puede dedicarse a análisis
    prospectivo/predictivo;
-   aproximadamente **5--10%** debe traducir los hallazgos a hipótesis
    para X5.

No es necesario forzar exactamente esos porcentajes en cantidad de
celdas. Lo importante es respetar la prioridad conceptual.

------------------------------------------------------------------------

# 3. Requisito de documentación dentro del notebook

Este requisito es **obligatorio**.

## Cada sección y subsección relevante debe comenzar con una celda Markdown explicativa.

Antes de ejecutar código, el notebook debe explicar claramente:

-   qué se va a analizar;
-   por qué se analiza;
-   qué pregunta intenta responder;
-   qué métricas o gráficos se utilizarán;
-   cómo deben interpretarse;
-   qué limitaciones tiene ese análisis;
-   si el análisis es descriptivo, prospectivo o
    prescriptivo/hipotético.

No quiero un notebook compuesto por bloques de código consecutivos sin
narrativa.

Debe sentirse como un **documento de investigación reproducible**, donde
una persona pueda leerlo de arriba hacia abajo y entender el
razonamiento incluso antes de revisar el código.

### Ejemplo conceptual

Antes de una sección de correlaciones, incluir una celda Markdown
explicando, por ejemplo:

-   qué mide Pearson;
-   qué mide Spearman;
-   por qué interesa comparar ambos;
-   que correlación no implica causalidad;
-   que una correlación contemporánea no implica capacidad predictiva;
-   qué se observará en los resultados.

Después viene el código.

Aplicar esta lógica a **todo el notebook**.

Además, después de análisis importantes, cuando sea útil, agregar una
celda Markdown de **interpretación / hallazgos**, dejando claro qué
puede concluirse y qué no.

------------------------------------------------------------------------

# 4. PARTE I --- ANÁLISIS DESCRIPTIVO / HISTÓRICO

Esta debe ser la parte principal del notebook.

La pregunta rectora es:

> **¿Cómo se han relacionado históricamente el precio de Bitcoin, los
> indicadores técnicos y los fundamentales?**

No intentar predecir todavía.

------------------------------------------------------------------------

## 4.1. Configuración y carga

Permitir definir al comienzo:

-   activo;
-   rutas;
-   parámetros generales;
-   horizontes temporales relevantes;
-   configuraciones de visualización que sean necesarias.

Inicialmente:

`valor = 'BTCUSD'`

Cargar la tabla maestra producida por P1.

Validar como mínimo:

-   existencia del archivo;
-   `DateTime`;
-   orden cronológico;
-   duplicados;
-   dimensiones;
-   rango temporal;
-   tipos de datos.

Mostrar un resumen inicial claro.

------------------------------------------------------------------------

## 4.2. Auditoría e inventario de variables

Construir una tabla resumen para todas las variables.

Idealmente incluir:

  Campo                  Descripción
  ---------------------- ----------------------------------------------------
  Variable               Nombre
  Tipo                   Numérica, categórica, etc.
  Familia                Precio / Técnico / Fundamental / Otra
  Definición             Si está disponible o puede inferirse con seguridad
  Primera observación    Inicio de cobertura
  Última observación     Fin de cobertura
  Observaciones          Cantidad
  Nulos                  Cantidad
  \% nulos               Cobertura
  Valores únicos         Variabilidad
  Frecuencia observada   Frecuencia de filas
  Frecuencia efectiva    Cada cuánto cambia realmente
  Estadísticos           Según corresponda

El objetivo es entender exactamente **qué información tiene X5**.

------------------------------------------------------------------------

## 4.3. Frecuencia efectiva de actualización

Este punto es especialmente importante.

No basta con saber que la tabla tiene, por ejemplo, frecuencia horaria.

Una variable fundamental podría repetirse durante muchas filas y
actualizarse solo una vez al día o una vez por semana.

Calcular, cuando sea posible:

-   intervalo entre observaciones;
-   intervalo entre cambios efectivos;
-   mediana;
-   promedio;
-   percentiles;
-   irregularidad;
-   número de actualizaciones reales.

Esto permitirá saber con qué frecuencia **realmente llega nueva
información**.

------------------------------------------------------------------------

## 4.4. Estadística descriptiva

Para cada variable relevante:

-   media;
-   mediana;
-   desviación estándar;
-   percentiles;
-   mínimo/máximo;
-   distribución;
-   asimetría si aporta valor;
-   outliers;
-   missingness.

Incluir visualizaciones cuando sean informativas.

------------------------------------------------------------------------

## 4.5. Evolución temporal

Analizar visualmente:

-   precio de Bitcoin;
-   cada variable;
-   precio + variable;
-   series normalizadas cuando las escalas sean incompatibles;
-   períodos relevantes;
-   cambios estructurales;
-   episodios extremos.

La idea es poder **mirar la historia** antes de calcular relaciones
agregadas.

Evitar gráficos ilegibles. Si existen muchas variables, generar análisis
sistemáticos y organizados.

------------------------------------------------------------------------

## 4.6. Relación contemporánea variable--precio

Analizar:

\[ X_t `\leftrightarrow `{=tex}Precio_t \]

Para cada variable relevante considerar:

-   scatter plot;
-   Pearson;
-   Spearman;
-   regresión simple descriptiva;
-   tendencia visual;
-   cuantiles/bins;
-   posibles no linealidades.

La pregunta es:

> Cuando históricamente X tomó determinados valores, ¿cómo se encontraba
> el precio de Bitcoin en ese mismo momento?

Dejar explícito que esto **no implica causalidad ni capacidad
predictiva**.

------------------------------------------------------------------------

## 4.7. Variable vs. comportamiento histórico reciente del precio

Aquí utilizar retornos **hacia atrás**.

Definir retorno como cambio porcentual del precio:

\[ R\_{t-h`\rightarrow `{=tex}t} = `\frac{P_t-P_{t-h}}{P_{t-h}}`{=tex}
\]

Analizar, según la granularidad disponible:

-   últimas horas;
-   últimas 24 horas;
-   últimos días;
-   última semana;
-   eventualmente ventanas mayores.

La pregunta es:

> Cuando X se encuentra en cierto nivel, ¿qué venía ocurriendo con
> Bitcoin?

Esto permite caracterizar el contexto histórico asociado a cada
variable.

------------------------------------------------------------------------

## 4.8. Relaciones entre variables

No limitar el análisis a variable vs. precio.

Estudiar:

-   técnicos vs. técnicos;
-   fundamentales vs. fundamentales;
-   técnicos vs. fundamentales;
-   precio vs. volatilidad;
-   drawdown vs. volatilidad;
-   tendencia vs. fundamentales;
-   otras combinaciones relevantes.

Incluir:

-   matriz de correlaciones;
-   Pearson/Spearman;
-   identificación de pares altamente relacionados;
-   análisis de redundancia;
-   clustering o PCA solo si aportan valor interpretativo.

No utilizar técnicas complejas solamente porque estén disponibles.

------------------------------------------------------------------------

## 4.9. No linealidades

No asumir que todas las relaciones son lineales.

Investigar:

-   cuantiles;
-   bins;
-   curvas suavizadas;
-   scatter plots;
-   comportamiento en extremos;
-   posibles umbrales;
-   formas U / U invertida;
-   saturaciones;
-   asimetrías.

Por ejemplo, una variable podría no tener relación con el precio en
valores normales pero sí comportarse de manera diferente sobre el
percentil 90.

------------------------------------------------------------------------

## 4.10. Ceteris paribus histórico

Este es uno de los componentes centrales de P2.

La pregunta es:

> **Históricamente, manteniendo razonablemente constantes otras
> condiciones, ¿cómo se ha relacionado una variable X con el precio o
> con el comportamiento del mercado?**

Puede utilizarse regresión multivariable u otras herramientas
apropiadas.

Ejemplo conceptual:

\[ Precio_t = `\beta`{=tex}\_0 + `\beta`{=tex}\_1 X_t + `\beta`{=tex}\_2
Volatilidad_t + `\beta`{=tex}\_3 Tendencia_t + `\epsilon`{=tex}\_t \]

El objetivo NO es predecir el precio futuro.

El objetivo es estudiar si una relación observada entre X y precio sigue
existiendo al controlar por otras variables.

Considerar:

-   coeficientes;
-   signo;
-   magnitud estandarizada cuando corresponda;
-   significancia/intervalos;
-   multicolinealidad;
-   sensibilidad a especificaciones;
-   no linealidad;
-   estabilidad temporal.

No confundir asociación condicional con causalidad.

------------------------------------------------------------------------

## 4.11. Regímenes

Investigar si las relaciones cambian según el contexto.

Posibles segmentaciones:

-   bull;
-   bear;
-   sideways;
-   volatilidad alta/baja;
-   drawdown sano/deteriorado;
-   tendencia;
-   períodos temporales;
-   otros regímenes que los datos justifiquen.

Ejemplo conceptual:

\[ Corr(X,Precio `\mid `{=tex}Bull) \]

versus:

\[ Corr(X,Precio `\mid `{=tex}Bear) \]

No imponer regímenes arbitrarios si no aportan valor. Documentar
claramente cómo se define cada uno.

------------------------------------------------------------------------

## 4.12. Estabilidad histórica

Una relación global puede esconder cambios importantes a través del
tiempo.

Analizar:

-   correlación por año;
-   correlación por semestre/trimestre si corresponde;
-   rolling correlation;
-   estabilidad de signo;
-   estabilidad de coeficientes;
-   cambios estructurales.

Ejemplo:

Una correlación global de 0.6 podría esconder:

-   2022: +0.9
-   2023: +0.8
-   2024: -0.1
-   2025: +0.2

El notebook debe permitir detectar este tipo de situaciones.

------------------------------------------------------------------------

## 4.13. Bloque específico de indicadores técnicos

Crear una sección que sintetice los hallazgos de los indicadores
técnicos.

Para cada técnico relevante:

-   frecuencia;
-   relación con precio;
-   relación con comportamiento histórico reciente;
-   correlación;
-   no linealidad;
-   régimen;
-   estabilidad;
-   redundancia con otros técnicos.

------------------------------------------------------------------------

## 4.14. Bloque específico de indicadores fundamentales

Realizar un análisis equivalente para fundamentales.

Prestar especial atención a que la frecuencia de actualización de
fundamentales puede ser distinta a la frecuencia del precio.

Evitar generar falsa cantidad de observaciones independientes
simplemente porque un valor fundamental se repite durante muchas filas.

------------------------------------------------------------------------

## 4.15. Ranking descriptivo de variables

Construir una tabla resumen por variable.

Como referencia:

  ---------------------------------------------------------------------------------------------------------------------------
  Variable   Tipo     Frecuencia    Corr.   Spearman Relación    No       Depende   Estabilidad   Redundancia   Evidencia
                        efectiva   precio     precio retorno     lineal   de                                    descriptiva
                                                     histórico            régimen                               
  ---------- ------ ------------ -------- ---------- ----------- -------- --------- ------------- ------------- -------------

  ---------------------------------------------------------------------------------------------------------------------------

No convertir automáticamente este ranking en un ranking predictivo.

El objetivo es sintetizar **qué tan interesante y robusta parece
históricamente cada variable**.

------------------------------------------------------------------------

# 5. PARTE II --- ANÁLISIS PROSPECTIVO / POTENCIAL PREDICTIVO

Esta sección debe estar claramente separada de la Parte I.

Debe presentarse como una **extensión secundaria del notebook**, no como
su objetivo principal.

La pregunta cambia a:

> **¿Una variable observada en t contiene información asociada con lo
> que ocurrió posteriormente?**

------------------------------------------------------------------------

## 5.1. Retornos futuros

Definir:

\[ R\_{t`\rightarrow `{=tex}t+h} = `\frac{P_{t+h}-P_t}{P_t}`{=tex} \]

Estudiar distintos horizontes apropiados a la granularidad real.

Por ejemplo:

-   +1h;
-   +6h;
-   +12h;
-   +24h;
-   +3d;
-   +7d.

No forzar horizontes que no tengan sentido para los datos.

------------------------------------------------------------------------

## 5.2. Relaciones temporales: pasado, contemporáneo y futuro

Para variables relevantes, construir una radiografía temporal alrededor
de t.

Conceptualmente:

\[ -7d,;-3d,;-1d,;-12h,;0,;+12h,;+1d,;+3d,;+7d \]

La idea es investigar si una variable parece:

-   rezagada;
-   contemporánea;
-   potencialmente adelantada.

Distinguir claramente:

\[ X_t `\leftrightarrow `{=tex}R\_{t-h`\rightarrow `{=tex}t} \]

de:

\[ X_t `\leftrightarrow `{=tex}R\_{t`\rightarrow `{=tex}t+h} \]

Esto permite detectar casos donde una variable simplemente reacciona a
movimientos que ya ocurrieron.

------------------------------------------------------------------------

## 5.3. Potencial predictivo preliminar

Explorar:

-   correlaciones con retornos futuros;
-   estabilidad por horizonte;
-   estabilidad temporal;
-   signo;
-   no linealidad;
-   comportamiento por régimen.

No construir todavía un sistema productivo de predicción.

No confundir asociación histórica con capacidad predictiva real.

------------------------------------------------------------------------

## 5.4. Validación temporal preliminar

Si se prueban modelos predictivos simples, evitar leakage.

Respetar orden temporal.

Utilizar, cuando corresponda:

-   train/test temporal;
-   walk-forward simple;
-   evaluación fuera de muestra.

Esto es exploratorio.

El desarrollo serio de modelos predictivos no es el core de P2.

------------------------------------------------------------------------

# 6. PARTE III --- IMPLICANCIAS E HIPÓTESIS PARA X5

Esta sección debe ser corta y explícitamente diferenciada.

P2 **no debe decidir automáticamente cómo configurar X5**.

Debe transformar hallazgos en **hipótesis que deberán comprobarse
posteriormente**.

Ejemplo:

Hallazgo descriptivo:

> En períodos de volatilidad elevada, históricamente los movimientos del
> precio presentan mayor amplitud.

Hipótesis para P3:

\[ A=f(Volatilidad) \]

con posible relación:

\[ `\frac{\partial A}{\partial Volatilidad}`{=tex}\>0 \]

Otro ejemplo:

Hallazgo:

> Drawdowns deteriorados están asociados a contextos de mayor riesgo.

Hipótesis:

\[ N=f(Drawdown) \]

con una política más defensiva cuando el drawdown empeora.

Estas relaciones **no deben darse por ciertas solamente porque tengan
sentido intuitivo**.

P2 genera la hipótesis.

P3 deberá comprobar si utilizarla realmente mejora la función objetivo
global de X5.

------------------------------------------------------------------------

# 7. Tabla final de hipótesis para P3

Cerrar el notebook con una tabla similar a:

  ----------------------------------------------------------------------------------------------------
  Variable      Evidencia   Estabilidad   Régimen   Potencial     Parámetro   Relación     Prioridad
  explicativa   histórica                           prospectivo   X5          hipotética   de prueba
                                                                  candidato                
  ------------- ----------- ------------- --------- ------------- ----------- ------------ -----------

  ----------------------------------------------------------------------------------------------------

Ejemplos conceptuales:

-   Drawdown → N
-   Volatilidad reciente → A
-   Volatilidad + P&L latente → B

No limitarse a estos ejemplos si los datos sugieren relaciones
adicionales.

------------------------------------------------------------------------

# 8. Filosofía estadística

Durante todo el notebook:

### No confundir correlación con causalidad

Una relación fuerte no demuestra causalidad.

### No confundir relación contemporánea con predicción

\[ Corr(X_t,P_t) \]

no significa que X pueda anticipar:

\[ P\_{t+h} \]

### No confundir repetición de datos con información nueva

Especialmente importante para fundamentales.

### No asumir linealidad

Investigar relaciones no lineales.

### No asumir estabilidad

Una relación puede existir solamente durante determinados períodos o
regímenes.

### No sobrecomplicar

Utilizar modelos complejos solamente cuando respondan una pregunta
concreta.

### Favorecer interpretabilidad

El objetivo de P2 es **entender**, no maximizar una métrica de machine
learning.

------------------------------------------------------------------------

# 9. Requisitos visuales

El notebook debe ser altamente visual, pero organizado.

Utilizar según corresponda:

-   line plots;
-   scatter plots;
-   histogramas;
-   boxplots;
-   heatmaps;
-   rolling correlations;
-   gráficos por cuantiles;
-   comparaciones por régimen;
-   gráficos de coeficientes;
-   otras visualizaciones justificadas.

Cada gráfico debe tener:

-   título claro;
-   ejes identificados;
-   unidades cuando corresponda;
-   leyenda si es necesaria;
-   tamaño legible.

Evitar producir cientos de gráficos sin estructura.

Si se automatizan gráficos por variable, organizarlos de manera que el
notebook siga siendo navegable.

------------------------------------------------------------------------

# 10. Reproducibilidad y calidad de código

El notebook debe:

-   ejecutarse de arriba hacia abajo;
-   evitar estado oculto;
-   utilizar funciones auxiliares cuando reduzcan repetición;
-   mantener el análisis legible;
-   reutilizar `config.py` y las rutas existentes cuando corresponda;
-   no duplicar lógica de P1;
-   manejar errores razonablemente;
-   documentar supuestos;
-   mantener nombres consistentes;
-   evitar hardcodes innecesarios;
-   funcionar inicialmente para `BTCUSD`, pero quedar razonablemente
    preparado para otro `valor`.

Si se necesitan dependencias adicionales, justificar su uso y
mantenerlas al mínimo razonable.

------------------------------------------------------------------------

# 11. Relación con el actual `X5_P2.py`

Revisar el actual `X5_P2.py`.

Actualmente su función real es básicamente:

1.  localizar la tabla maestra;
2.  cargarla;
3.  imprimir dimensiones;
4.  imprimir rango temporal.

La nueva implementación debe ser `X5_P2.ipynb`.

Reutilizar del `.py` aquello que tenga sentido, especialmente:

-   configuración;
-   rutas;
-   carga de tabla.

No mantener dos implementaciones divergentes innecesariamente.

Decidir qué hacer con `X5_P2.py` después de revisar las convenciones del
repositorio: eliminarlo, dejarlo como helper o reemplazarlo, pero evitar
confusión sobre cuál es el P2 oficial.

------------------------------------------------------------------------

# 12. Resultado esperado

Al terminar `X5_P2.ipynb`, quiero poder responder con evidencia
preguntas como:

-   ¿Qué variables existen realmente?
-   ¿Cuáles son técnicas y cuáles fundamentales?
-   ¿Cada cuánto llega información nueva de cada una?
-   ¿Cómo se ha relacionado históricamente cada variable con el precio
    de BTC?
-   ¿Cómo se relaciona con los movimientos que BTC venía experimentando?
-   ¿Pearson y Spearman cuentan historias similares?
-   ¿Existen relaciones no lineales?
-   ¿Existen umbrales?
-   ¿Qué relaciones desaparecen al controlar por otras variables?
-   ¿Qué variables son redundantes?
-   ¿Qué relaciones cambian por régimen?
-   ¿Qué relaciones son estables a través del tiempo?
-   ¿Qué indicadores parecen reaccionar al precio?
-   ¿Cuáles podrían contener información adelantada?
-   ¿Qué resultados son solamente descriptivos?
-   ¿Qué resultados tienen potencial predictivo?
-   ¿Qué hipótesis concretas merece la pena llevar a P3?
-   ¿Qué pocas variables podrían explicar cada parámetro configurable de
    X5?

El notebook debe terminar entregando **conocimiento estructurado**, no
una estrategia de trading terminada.

------------------------------------------------------------------------

# 13. Principio final

El objetivo de P2 puede resumirse así:

> **Investigar exhaustivamente la relación histórica entre Precio +
> Indicadores Técnicos + Indicadores Fundamentales, entender su
> estructura temporal y condicional, y convertir los hallazgos robustos
> en hipótesis explícitas que posteriormente puedan probarse para
> gobernar los parámetros configurables de X5.**

Mantener siempre la separación:

> **DESCRIBIR → EXPLORAR POTENCIAL PREDICTIVO → FORMULAR HIPÓTESIS**

y no saltar directamente desde una correlación a una regla de trading.

Finalmente, antes de dar por terminado el trabajo, ejecutar el notebook
completo desde cero y comprobar que todas las celdas corren en orden y
que las tablas y visualizaciones se generan correctamente.


---

# 14. Orden obligatorio de relevancia dentro del notebook

Además de separar el notebook en las tres grandes capas definidas anteriormente, existe una regla adicional de diseño:

> **Dentro de cada parte, las secciones deben presentarse desde el análisis más relevante y general hacia el análisis más específico, complementario o de menor prioridad.**

El orden del notebook debe reflejar la importancia analítica para X5, y no simplemente el orden tradicional de un análisis estadístico.

Esto es especialmente importante en la **Parte I — Descriptiva / Histórica**, que constituye el core de P2.

## 14.1. Qué considero central en la fase descriptiva

Después de una carga/auditoría inicial mínima necesaria para interpretar correctamente los datos, el notebook debe llegar rápidamente al análisis que considero central:

> **medir y visualizar cómo se relaciona cada variable con el precio de BTC.**

Para cada variable técnica o fundamental relevante quiero poder observar, de forma sistemática:

1. su evolución histórica junto al precio;
2. su relación visual con el precio;
3. scatter plots variable vs. precio;
4. correlación Pearson;
5. correlación Spearman;
6. dirección y fuerza de la asociación;
7. relación mediante cuantiles/bins;
8. otras medidas descriptivas de asociación que aporten información real;
9. posibles relaciones no lineales;
10. estabilidad de esa relación a través del tiempo.

Este bloque debe aparecer **muy arriba en P2**, porque constituye una de las preguntas principales del notebook.

La auditoría, calidad y frecuencia de datos son necesarias para interpretar correctamente estos resultados, pero no deben transformar el comienzo del notebook en una exploración excesivamente larga antes de llegar a variable vs. precio.

## 14.2. Jerarquía conceptual deseada

Como orientación, la Parte I debería avanzar aproximadamente desde:

### Nivel 1 — Mapeo general
- qué variables existen;
- qué cobertura tienen;
- cómo evoluciona el precio;
- cómo evolucionan las variables.

### Nivel 2 — Core descriptivo variable vs. precio
- gráficos;
- series superpuestas;
- scatter plots;
- Pearson;
- Spearman;
- medidas adicionales de asociación;
- cuantiles/bins;
- ranking inicial de relaciones.

### Nivel 3 — Profundización de las relaciones
- no linealidades;
- comportamiento histórico reciente del precio;
- relaciones entre variables;
- redundancia;
- ceteris paribus.

### Nivel 4 — Condicionalidad y estabilidad
- regímenes;
- rolling relationships;
- estabilidad histórica;
- cambios estructurales.

### Nivel 5 — Síntesis especializada
- lectura conjunta de técnicos;
- lectura conjunta de fundamentales;
- ranking descriptivo consolidado.

Después de esto recién debe comenzar la Parte II prospectiva/predictiva.

No interpretar esta jerarquía de forma mecánica: si al revisar los datos existe una dependencia metodológica que obliga a adelantar una comprobación, hacerlo. Sin embargo, mantener siempre la lógica general de **más importante/general → más específico/complementario**.

---


## Aclaración sobre el primer To Do

El **primer To Do de implementación** debe ser crear `X5_P2.ipynb` como Jupyter Notebook y definir su arranque obligatorio:

1. declarar `valor`;
2. inicialmente usar `valor = 'BTCUSD'`;
3. construir la ruta del CSV asociado;
4. leer `{valor}_tabla_maestra.csv`;
5. dejar esa tabla cargada como DataFrame;
6. ejecutar todo el análisis posterior desde esa tabla.

Este primer To Do debe aparecer explícitamente al comienzo de la lista de pendientes de implementación.

---

# 15. To Dos

## Convención de priorización

Cada ítem pendiente debe expresarse con:

`(I:x C:y H:z → score)`

donde:

- **I = Impacto**, escala 1–10.
- **C = Complejidad de desarrollo**, escala 1–10.
- **H = Habilitación**, escala 1–10: cuánto habilita o desbloquea análisis posteriores.
- **score = √(I × H) / C**.

Dentro de cada bloque, ordenar los ítems de mayor a menor score.

**Importante:** el score define prioridad, pero no elimina dependencias técnicas. Si un ítem necesita otro para poder ejecutarse correctamente, respetar la dependencia aunque el segundo tenga menor score.

## To Dos — X5_P2

### Core descriptivo / histórico

- **X5_P2 — mapeo visual y estadístico variable vs. precio:** para cada `x3_*`, `x2_*` y cualquier otra variable explicativa relevante, generar el núcleo del análisis descriptivo: serie temporal junto al precio, series normalizadas cuando corresponda, scatter variable-precio, Pearson, Spearman, dirección/fuerza de asociación, cuantiles/bins y medidas adicionales de asociación que aporten valor. Este es el core analítico de P2 y debe quedar muy arriba en el notebook. **(I:10 C:3 H:10 → 3.33)**

- **X5_P2 — ceteris paribus histórico:** estandarizar variables y estimar el efecto/asociación de cada variable controlando por las demás, revisando multicolinealidad, signo, magnitud, estabilidad y sensibilidad. Revisar y reutilizar cuando corresponda el enfoque manual con numpy/scipy ya utilizado en `X5_analisis_exploratorio.ipynb`, sin asumir que debe copiarse literalmente. **(I:9 C:3 H:8 → 2.83)**

- **X5_P2 — auditoría e inventario inicial de la tabla maestra:** cargar la salida de X5_P1, validar `DateTime`, orden, duplicados, rango, tipos y construir el inventario de variables con familia Precio/Técnico/Fundamental/Otra, cobertura, missingness y frecuencia observada. Mantener esta sección concisa y orientada a habilitar rápidamente el core variable-precio. **(I:8 C:2 H:8 → 4.00)**

- **X5_P2 — frecuencia efectiva de actualización:** medir cada cuánto cambia realmente cada variable, diferenciando frecuencia de filas de llegada efectiva de nueva información; prestar especial atención a fundamentales y forward-fill. **(I:8 C:2 H:8 → 4.00)**

- **X5_P2 — no linealidades y umbrales:** ampliar el análisis variable-precio mediante cuantiles, bins, suavizados, extremos, posibles umbrales, saturaciones, formas U/U invertida y asimetrías, evitando asumir que Pearson/regresión lineal capturan toda la relación. **(I:8 C:3 H:7 → 2.49)**

- **X5_P2 — variable vs. comportamiento histórico reciente del precio:** relacionar cada variable con retornos pasados del precio en distintos horizontes (`t-h → t`) para caracterizar qué venía ocurriendo con BTC cuando la variable toma determinados valores. Mantener este análisis dentro de la capa descriptiva, separado de retornos futuros. **(I:8 C:3 H:7 → 2.49)**

- **X5_P2 — estabilidad histórica de las relaciones:** medir Pearson/Spearman y, cuando corresponda, coeficientes ceteris paribus por períodos y ventanas móviles para detectar relaciones persistentes, inestables o cambios estructurales. **(I:8 C:3 H:7 → 2.49)**

- **X5_P2 — análisis por regímenes:** comparar las relaciones variable-precio bajo contextos como bull/bear/sideways, volatilidad alta/baja, drawdown y tendencia, definiendo cada régimen explícitamente y evitando segmentaciones arbitrarias. **(I:8 C:4 H:7 → 1.87)**

- **X5_P2 — relaciones entre variables y redundancia:** estudiar técnicos vs. técnicos, fundamentales vs. fundamentales y técnicos vs. fundamentales; identificar pares o grupos que contienen información muy similar mediante correlaciones y, solo si aporta interpretabilidad, clustering/PCA. **(I:7 C:3 H:6 → 2.16)**

- **X5_P2 — síntesis descriptiva y ranking de variables:** consolidar por variable frecuencia efectiva, Pearson, Spearman, relación con retornos históricos, no linealidad, estabilidad, régimen, redundancia y nivel de evidencia descriptiva. No convertir este ranking automáticamente en ranking predictivo. **(I:8 C:3 H:6 → 2.31)**

- **X5_P2 — síntesis específica de técnicos y fundamentales:** generar una lectura consolidada separada de ambos universos, considerando especialmente las diferencias de frecuencia y disponibilidad de información. **(I:6 C:3 H:4 → 1.63)**

### Prospectivo / potencial predictivo

- **X5_P2 — relaciones temporales pasado/contemporáneo/futuro:** construir para variables relevantes una radiografía temporal que permita distinguir si una variable parece rezagada, contemporánea o potencialmente adelantada, separando explícitamente `X_t ↔ retorno pasado`, `X_t ↔ precio actual` y `X_t ↔ retorno futuro`. **(I:8 C:3 H:7 → 2.49)**

- **X5_P2 — variable actual vs. retornos futuros por horizonte:** estudiar asociación con retornos posteriores en horizontes coherentes con la granularidad disponible, dejando explícito que asociación histórica futura no equivale por sí sola a capacidad predictiva. **(I:7 C:3 H:6 → 2.16)**

- **X5_P2 — validación temporal preliminar sin leakage:** si se prueban modelos o relaciones prospectivas, utilizar particiones temporales/walk-forward simples para verificar estabilidad fuera de muestra sin convertir P2 en un proyecto de forecasting. **(I:7 C:4 H:5 → 1.48)**

### Hipótesis para X5 / puente hacia P3

- **X5_P2 — traducir evidencia robusta a hipótesis para parámetros X5:** transformar los hallazgos descriptivos/prospectivos en hipótesis explícitas del tipo `θ_k = f_k(X)`, sin implementarlas todavía como reglas de trading. Ejemplos candidatos: `N=f(drawdown)` y `A=f(volatilidad)`. **(I:9 C:2 H:10 → 4.74)**

- **X5_P2 — tabla final variable → parámetro candidato:** cerrar P2 con una tabla que documente variable explicativa, evidencia histórica, estabilidad, régimen, potencial prospectivo, parámetro X5 candidato, relación hipotética y prioridad de prueba en P3. **(I:8 C:2 H:9 → 4.24)**

### Transversales / implementación

- **X5_P2 — documentación Markdown de investigación:** cada sección y subsección relevante debe comenzar obligatoriamente con una celda Markdown que explique objetivo, pregunta, metodología, interpretación y limitaciones antes del código; agregar interpretación posterior cuando el análisis lo amerite. **(I:8 C:2 H:8 → 4.00)**

- **X5_P2 — revisar `X5_analisis_exploratorio.ipynb`:** revisar el notebook existente que ya realiza análisis ceteris paribus sobre el store de eventos de X5 actual y decidir qué lógica conviene reutilizar, adaptar o descartar para evitar duplicación innecesaria. **(I:6 C:2 H:7 → 3.24)**

- **X5_P2 — convertir P2 oficialmente a notebook:** crear `X5_P2.ipynb` como implementación oficial de investigación, reutilizando del actual `X5_P2.py` la carga/configuración que tenga sentido y evitando dos implementaciones divergentes. **(I:7 C:2 H:8 → 3.74)**

- **X5_P2 — orden del notebook por relevancia analítica:** estructurar cada parte desde el mapeo más importante/general hacia análisis progresivamente más particulares, manteniendo el bloque variable-precio como núcleo temprano de la fase descriptiva. **(I:9 C:2 H:8 → 4.24)**

- **X5_P2 — ejecución end-to-end y validación final:** ejecutar el notebook completo desde cero, comprobar reproducibilidad, ausencia de errores, generación de tablas/gráficos y consistencia de resultados antes de considerar P2 terminado. **(I:9 C:2 H:9 → 4.50)**

### X5_P1 relacionado

- **X5_P1 — reporte de calidad de datos:** mantener en P1 la responsabilidad de validar la calidad de construcción de la tabla maestra: `% missing`, huecos temporales del precio, cobertura real de fundamentales y efecto de forward-fill. P2 debe consumir y contextualizar esta información, no reemplazar la responsabilidad de P1. **(I:7 C:2 H:8 → 3.74)**

### Fase 3

- **Fase 3 (`X5_alternativo.py`) — no comenzar todavía:** definir su arquitectura y reglas recién después de observar resultados concretos de X5_P1 y X5_P2. P2 debe terminar en evidencia e hipótesis, no en reglas prescriptivas implementadas. **(I:3 C:2 H:3 → 1.50)**


- **X5 — estudio posterior de parámetros manipulables y variables explicativas:** una vez terminado el análisis exploratorio de `X5_P2.ipynb`, utilizar sus resultados como insumo para estudiar de qué deberían depender los parámetros configurables/manipulables de X5. Este To Do **escapa parcialmente del alcance operativo de P2** y debe entenderse como puente hacia la siguiente etapa de investigación, no como una responsabilidad de implementación inmediata del notebook. El objetivo será construir, para cada parámetro manipulable, una hipótesis explícita del tipo `parámetro = f(pocas variables explicativas relevantes)`, evitando hacer depender todos los parámetros de todas las variables. Incluir al menos `N`, `A`, `B`, `pérdida máxima`, `K` y cualquier otro parámetro configurable relevante que exista en X5. Para cada uno, documentar: qué controla, en qué etapa actúa, qué variables podrían explicarlo, signo esperado de la relación, rango permitido, riesgo económico asociado y cómo se validará posteriormente. **(I:10 C:4 H:10 → 2.50)**

  **Hipótesis explícita sobre `N`:** registrar desde ya como hipótesis prioritaria que `N` **no debería definirse a partir de relaciones genéricas obtenidas desde el CSV de P2**, sino que podría tener una relación directa —e incluso posiblemente única— con el **drawdown de la cuenta asociado a ese valor/activo**. Conceptualmente:

  `N = f(drawdown_del_valor)`

  La intuición inicial es que, a medida que el drawdown empeora, X5 debería operar con un `N` más defensivo/bajo, reduciendo exposición o agresividad. Esta relación debe quedar anotada como hipótesis a contrastar posteriormente, no como regla definitiva.

  **Búsqueda para el resto de parámetros:** utilizar los hallazgos descriptivos, ceteris paribus, de régimen, estabilidad y potencial prospectivo de P2 para investigar qué pocas variables podrían gobernar parámetros como:

  - `A`;
  - `B`;
  - `pérdida máxima`;
  - `K`;
  - `N`;
  - cualquier otro parámetro manipulable/configurable detectado en X5.

  Para estos parámetros, P2 debe servir como fuente de evidencia para explorar relaciones con variables técnicas, fundamentales, de precio, volatilidad, tendencia, drawdown u otras que resulten justificadas por el análisis.

  El resultado esperado de esta etapa posterior es una tabla conceptual del tipo:

  | Parámetro X5 | Qué controla | Variable(s) explicativa(s) candidata(s) | Hipótesis de relación | Evidencia proveniente de P2 | Cómo validar |
  |---|---|---|---|---|---|
  | N | Agresividad/exposición asociada al valor | Drawdown de la cuenta para ese valor | Drawdown más negativo → N más defensivo/bajo | Hipótesis inicial prioritaria | Backtesting global |
  | A | Según definición vigente en X5 | Variables candidatas surgidas de P2 | Por determinar | P2 | Backtesting global |
  | B | Según definición vigente en X5 | Variables candidatas surgidas de P2 | Por determinar | P2 | Backtesting global |
  | Pérdida máxima | Límite de pérdida/riesgo | Variables de riesgo/regímenes candidatas | Por determinar | P2 | Backtesting global |
  | K | Según definición vigente en X5 | Variables candidatas surgidas de P2 | Por determinar | P2 | Backtesting global |

  El criterio de fondo debe mantenerse: **cada parámetro debería depender de pocas variables con justificación económica/estadística**, y P2 debe servir como fuente de evidencia para formular esas dependencias antes de optimizarlas.


## Nota sobre orden de implementación

Aunque los To Dos se prioricen mediante score, la construcción efectiva de `X5_P2.ipynb` debe respetar las dependencias y el orden narrativo de investigación.

En particular:

1. disponer de una tabla maestra válida;
2. realizar una auditoría inicial suficiente para saber qué se está analizando;
3. llegar rápidamente al **core variable vs. precio**;
4. profundizar desde relaciones generales hacia análisis más particulares;
5. completar la investigación descriptiva antes de dar protagonismo a la sección prospectiva;
6. formular hipótesis para P3 solamente después de observar la evidencia;
7. no comenzar Fase 3 hasta cerrar P1/P2.

El criterio rector es:

> **Primero entender qué variables existen; inmediatamente después entender cómo se relacionan históricamente con el precio; luego profundizar en por qué, cuándo y bajo qué condiciones cambia esa relación.**
