# Revisión Exhaustiva del Cerebro X5 --- Alginvesting

## 1. Propósito de esta revisión

El objetivo es realizar una revisión exhaustiva del funcionamiento de
**X5**, entendido como el "cerebro" del sistema de Alginvesting.

La inquietud principal es asegurar que X5 esté resolviendo el problema
correcto. El objetivo no debe ser que **cada operación individual se
cierre en el punto más alto posible**, sino maximizar el resultado
económico acumulado a través del tiempo.

En otras palabras, una operación individual puede no tener el mejor
cierre posible y, aun así, formar parte de una estrategia global
superior si permite liberar capital, reducir riesgo, abrir mejores
oportunidades posteriores o mejorar el resultado acumulado.

La revisión debe partir desde esta función objetivo y avanzar hacia
atrás, cuestionando qué variables, parámetros, estados y mecanismos de
aprendizaje son realmente necesarios.

------------------------------------------------------------------------

## 2. Función objetivo global

La función objetivo conceptual de X5 debe ser la **ganancia acumulada
durante todo el horizonte temporal**.

Una formulación inicial es:

\[ `\max`{=tex}*{`\theta`{=tex}} `\sum`{=tex}*{i
`\in `{=tex}`\text{órdenes cerradas}`{=tex}}
Q_i(P\_{cierre,i}-P\_{apertura,i}) - Costos_i \]

donde:

-   (Q_i): lotaje o cantidad de la orden (i).
-   (P\_{apertura,i}): precio de apertura.
-   (P\_{cierre,i}): precio de cierre.
-   (Costos_i): comisiones, spread, funding u otros costos relevantes.
-   (`\theta`{=tex}): conjunto de parámetros configurables de X5.

La formulación deberá adaptarse correctamente a posiciones long/short y
a cualquier otra mecánica existente.

### Principio central

**La unidad de evaluación no es una operación aislada: es la trayectoria
completa de X5 sobre un horizonte temporal.**

Por lo tanto, puede ser óptimo:

-   cerrar una operación antes de su máximo;
-   aceptar una ganancia menor;
-   aceptar determinadas pérdidas;
-   reducir exposición;
-   liberar capital;
-   cambiar parámetros durante el tiempo;

si cualquiera de estas decisiones aumenta el resultado económico
acumulado.

------------------------------------------------------------------------

## 3. Auditoría del funcionamiento actual de X5

Antes de optimizar el cerebro, es necesario confirmar que el simulador y
la ejecución económica sean correctos.

### 3.1. Auditoría del lotaje mínimo

Se debe verificar exhaustivamente que X5 esté ejecutando correctamente
el **lotaje mínimo**.

Existe una señal de posible inconsistencia:

> En enero de 2024 aparecen órdenes cerradas con resultados superiores a
> USD 130 para Bitcoin.

Esto parece difícil de reconciliar con:

-   el lotaje mínimo configurado;
-   los precios de Bitcoin durante enero de 2024;
-   el rango mensual de precios de Bitcoin durante ese período.

Se debe reconstruir matemáticamente una muestra de operaciones para
comprobar:

\[ P&L `\approx `{=tex}Q(P\_{cierre}-P\_{apertura}) \]

ajustando la expresión según long/short, costos y demás reglas del
sistema.

La revisión debe comprobar:

1.  cómo se determina el lotaje;
2.  dónde se almacena;
3.  si cambia durante la vida de una orden;
4.  qué lotaje se utiliza efectivamente al cerrar;
5.  cómo se calcula el resultado económico;
6.  si existe alguna multiplicación, normalización o conversión
    adicional;
7.  si el lotaje mínimo se respeta en todos los caminos posibles del
    código.

### 3.2. Trazabilidad de cierres A → C

Cada vez que una orden cambie desde:

-   **A = Activa**
-   a **C = Cerrada**

X5 debe informar al menos:

-   lotaje de la orden;
-   precio de apertura;
-   precio de cierre.

Idealmente también debería permitir reconstruir:

-   P&L bruto;
-   costos;
-   P&L neto;
-   motivo de cierre;
-   fecha/hora de apertura;
-   fecha/hora de cierre.

El objetivo es que cada cierre pueda auditarse económicamente sin
ambigüedad.

------------------------------------------------------------------------

## 4. Reinicio de activos en modo Recolectar

Actualmente existe una lógica de reinicio en **Recolectar Demo**.

El modo **Recolectar normal (sin Demo)** también debe preguntar al
comienzo si se desea reiniciar los activos.

### Definición estricta de "reiniciar un activo"

Reiniciar un activo significa eliminar **absolutamente todo lo asociado
a ese activo**, incluyendo:

-   datos recolectados;
-   órdenes activas;
-   órdenes históricas;
-   estados internos;
-   resultados intermedios;
-   archivos persistentes;
-   registros persistentes;
-   cualquier información producida por ejecuciones anteriores.

Después del reinicio, el activo debe quedar en el mismo estado lógico
que tendría si **nunca hubiese sido procesado por X5**.

------------------------------------------------------------------------

## 5. Inventario de información: comenzar con Bitcoin

Antes de aumentar la sofisticación del cerebro, se quiere entender con
precisión qué información posee actualmente X5.

La primera iteración se realizará con **un solo activo: Bitcoin**.

Se debe construir una tabla integrada con tres familias principales:

> **Precio + Indicadores técnicos + Indicadores fundamentales**

Para cada variable se debería registrar, como mínimo:

  Campo                      Descripción
  -------------------------- ------------------------------------------
  Variable                   Nombre del indicador o dato
  Familia                    Precio / Técnico / Fundamental
  Definición                 Qué representa
  Fuente                     De dónde se obtiene
  Frecuencia teórica         Cada cuánto debería actualizarse
  Frecuencia real            Cada cuánto se está obteniendo realmente
  Timestamp                  Fecha/hora de observación
  Disponibilidad histórica   Desde cuándo existe
  Missing data               Cantidad/proporción faltante
  Uso actual en X5           Dónde se utiliza
  Parámetros relacionados    Qué parámetros podría explicar

El objetivo no es solamente inventariar variables, sino entender la
**frecuencia efectiva de información disponible para tomar decisiones**.

------------------------------------------------------------------------

## 6. Análisis exploratorio y visual

La tabulación debe acompañarse de análisis visual.

### 6.1. Fundamentales vs. precio

Contrastar los indicadores fundamentales con el precio de Bitcoin para
identificar:

-   relaciones contemporáneas;
-   relaciones rezagadas;
-   anticipación;
-   persistencia;
-   cambios de régimen;
-   señales que solo funcionan bajo determinadas condiciones;
-   variables redundantes;
-   variables sin capacidad explicativa aparente.

### 6.2. Técnicos vs. precio

Realizar el mismo ejercicio con los indicadores técnicos.

No se busca asumir que un indicador funciona porque sea
convencionalmente utilizado en trading. Se quiere observar empíricamente
qué información aporta.

### 6.3. Análisis adicionales

Según corresponda:

-   correlaciones;
-   correlaciones rezagadas;
-   scatter plots;
-   rolling correlations;
-   distribuciones condicionadas;
-   comportamiento por régimen;
-   análisis de volatilidad;
-   drawdown;
-   comportamiento previo/posterior a determinadas señales.

El propósito final es reducir el universo de información a variables que
realmente tengan utilidad para las decisiones de X5.

------------------------------------------------------------------------

## 7. El concepto de "estado" o "status"

Inicialmente se planteó la posibilidad de definir estados discretos, por
ejemplo:

1.  Muy sano
2.  Sano
3.  Medio
4.  Negativo
5.  Muy negativo

Esto podría permitir estudiar posteriormente transiciones entre estados
mediante herramientas como cadenas de Markov.

Sin embargo, no se debe imponer esta arquitectura antes de demostrar que
es necesaria.

### Principio de parsimonia

El **status debería explicarse mediante pocas variables relevantes**.

No interesa crear un estado basado en decenas de indicadores
redundantes. Interesa encontrar un conjunto pequeño de variables con
capacidad real para modificar la política óptima de X5.

------------------------------------------------------------------------

## 8. Drawdown como variable de salud y riesgo

El **drawdown** aparece como una variable particularmente importante.

La intuición económica es:

-   drawdown muy negativo → X5 debería actuar de manera más
    protegida/conservadora;
-   situación sana → X5 puede permitirse una política menos defensiva.

Por lo tanto, el drawdown podría afectar directamente parámetros
relacionados con:

-   exposición;
-   número de órdenes;
-   lotaje;
-   trailing;
-   agresividad de entrada;
-   protección de posiciones;
-   utilización de capital.

No obstante, estas relaciones deben validarse mediante backtesting y no
solamente asumirse.

------------------------------------------------------------------------

## 9. Cambio conceptual: no necesariamente un único estado global

Una conclusión importante de la conversación es que puede no ser
necesario crear un único "estado global" que gobierne todos los
parámetros.

Una arquitectura potencialmente más limpia es estudiar **cada parámetro
configurable por separado**.

Para cada parámetro (`\theta`{=tex}\_k):

\[ `\theta`{=tex}\_k = f_k(z_1,z_2,`\ldots`{=tex},z_m) \]

donde las (z) son solamente las pocas variables explicativas relevantes
para ese parámetro.

### Ejemplo: parámetro N

Hipótesis:

> Si el drawdown es negativo, tiene sentido utilizar un N más bajo.

Entonces podría estudiarse inicialmente:

\[ N=f(Drawdown) \]

sin obligar a N a depender de volatilidad, fundamentales, RSI u otras
variables si estas no aportan valor.

### Ejemplo: parámetro A

Hipótesis:

> Si la volatilidad de los últimos días es alta, tiene sentido utilizar
> un A más alto.

Entonces:

\[ A=f(Volatilidad reciente) \]

### Ejemplo: parámetro B

Una hipótesis futura podría ser:

\[ B=f(Volatilidad, P&L latente) \]

si ambos factores tienen justificación económica y evidencia empírica.

------------------------------------------------------------------------

## 10. Principio de especialización por parámetro

Cada parámetro configurable debe analizarse respondiendo explícitamente:

1.  **¿Qué controla?**
2.  **¿En qué etapa de una orden actúa?**
3.  **¿Cuándo puede cambiar?**
4.  **¿Qué variables deberían explicarlo conceptualmente?**
5.  **¿Qué signo debería tener cada relación?**
6.  **¿Cuál es su rango permitido?**
7.  **¿Qué efecto tiene sobre riesgo y retorno?**
8.  **¿Cómo se valida que modificarlo agrega valor?**

Ejemplo de tabla conceptual:

  -----------------------------------------------------------------------
  Parámetro               Variables explicativas  Hipótesis
                          candidatas              
  ----------------------- ----------------------- -----------------------
  N                       Drawdown, eventualmente Drawdown deteriorado →
                          régimen                 N menor

  A                       Volatilidad reciente /  Volatilidad mayor → A
                          ATR / rango             mayor

  B                       Volatilidad, P&L        Adaptar
                          latente, drawdown       distancia/protección

  Lotaje                  Drawdown, volatilidad,  Mayor riesgo → menor
                          capital                 exposición

  Entrada                 Técnicos,               Mejor contexto → mayor
                          fundamentales,          disposición a entrar
                          tendencia               

  Salida                  P&L, volatilidad,       Ajustar
                          deterioro técnico       protección/cierre
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 11. Relaciones monotónicas y restricciones económicas

Cuando exista una relación económicamente justificable, se puede
considerar imponer restricciones monotónicas.

Por ejemplo, si una definición de drawdown/salud aumenta cuando la
situación mejora:

\[ `\frac{\partial N}{\partial Salud}`{=tex} \> 0 \]

O si la hipótesis establece que A debe aumentar con volatilidad:

\[ `\frac{\partial A}{\partial Volatilidad}`{=tex} \> 0 \]

Esto permite evitar que un modelo flexible "descubra" relaciones
espurias o económicamente absurdas simplemente por sobreajuste.

Las restricciones deben ser hipótesis comprobables, no dogmas
permanentes.

------------------------------------------------------------------------

## 12. Arquitectura conceptual propuesta

Una arquitectura simple y progresiva sería:

**Datos** ↓\
**Variables explicativas** ↓\
**Funciones de parámetros** ↓\
**Parámetros configurables de X5** ↓\
**Decisiones** ↓\
**Órdenes** ↓\
**P&L acumulado**

El objetivo final sería aprender funciones:

\[ f_A, f_B, f_N,`\ldots`{=tex} \]

que permitan maximizar el resultado acumulado.

Esto permite construir un X5 adaptativo sin saltar inmediatamente a
Reinforcement Learning o modelos de Markov.

------------------------------------------------------------------------

## 13. Baseline: optimización estática antes de modelos complejos

Antes de construir estados, Markov, MDP o RL, se debe establecer un
baseline sencillo.

Sea:

\[ `\theta`{=tex}=(A,B,N,`\ldots`{=tex}) \]

Se busca:

\[ `\theta`{=tex}\^\*=`\arg`{=tex}`\max`{=tex}\_{`\theta`{=tex}}
GananciaTotal(X5,`\theta`{=tex},T) \]

Procedimiento:

1.  elegir una combinación de parámetros;
2.  ejecutar X5 durante el horizonte completo;
3.  medir el resultado económico;
4.  cambiar los parámetros;
5.  repetir;
6.  encontrar configuraciones superiores;
7.  validar fuera de muestra.

La pregunta fundamental es:

> **¿Cuánto puede mejorar X5 simplemente encontrando mejores
> combinaciones de los parámetros que ya existen?**

Si la mejora es grande, existe evidencia de que el principal problema
está en la configuración.

Luego se puede estudiar si la configuración óptima cambia
sistemáticamente según las condiciones del mercado.

------------------------------------------------------------------------

## 14. Del parámetro constante al parámetro adaptativo

El siguiente nivel es comparar:

### Modelo estático

\[ `\theta `{=tex}= constante \]

versus:

### Modelo adaptativo

\[ `\theta`{=tex}=f(estado) \]

o, preferiblemente cuando corresponda:

\[ `\theta`{=tex}\_k=f_k(variables específicas) \]

La segunda formulación es especialmente atractiva porque evita que todos
los parámetros dependan de un gran estado común.

La complejidad debe agregarse solamente cuando mejore el resultado
**out-of-sample**.

------------------------------------------------------------------------

## 15. Markov, MDP y Reinforcement Learning

La idea de estados discretos puede llevar a estudiar una **cadena de
Markov en tiempo discreto**, pero hay que distinguir conceptos.

### Cadena de Markov

Describe principalmente transiciones:

\[ P(S\_{t+1}`\mid `{=tex}S_t) \]

Es útil si interesa entender cómo evoluciona el sistema entre estados.

### MDP

X5 no solamente observa estados: también toma decisiones que pueden
afectar resultados futuros.

Por eso, si se llega a una arquitectura basada en estados y acciones, el
problema se parece más a un **Markov Decision Process (MDP)**:

**Estado → Acción → Transición → Recompensa**

### Reinforcement Learning

RL podría utilizarse posteriormente para aprender una política:

\[ `\pi`{=tex}(a`\mid `{=tex}s) \]

que maximice recompensa acumulada.

Sin embargo, no debería ser el punto de partida.

La secuencia preferida es:

**Optimización estática → parámetros adaptativos → estados si agregan
valor → MDP/Markov si se justifican → RL solo si entrega mejora
adicional robusta.**

------------------------------------------------------------------------

## 16. Roadmap priorizado

  ----------------------------------------------------------------------------------------
  \#         Título                Impacto 0--10 Tiempo       Incertidumbre Dependencias
                                                 estimado             0--10 
                                                 con IA                     
  ---------- -------------------- -------------- ---------- --------------- --------------
  1          Definir función                  10 2--4 h                   4 Ninguna
             objetivo global                                                

  2          Auditar lotaje                   10 2--5 h                   7 Ninguna
             mínimo                                                         

  3          Trazabilidad A→C                  8 1--2 h                   2 Ninguna

  4          Inventario Precio +               9 3--6 h                   4 Ninguna
             Técnicos +                                                     
             Fundamentales                                                  

  5          Análisis visual                   9 4--8 h                   7 4
             exploratorio                                                   

  6          Identificar pocas                10 4--8 h                   9 4, 5
             variables                                                      
             explicativas                                                   
             relevantes                                                     

  7          Estudiar cada                    10 Variable                 8 1, 4, 5, 6
             parámetro                                                      
             configurable                                                   

  8          Formalizar                       10 4--10 h                  9 7
             relaciones                                                     
             parámetro-variable                                             

  9          Analizar drawdown                10 4--8 h                   7 6, 7
             como mecanismo                                                 
             defensivo                                                      

  10         Mapear todos los                 10 3--6 h                   5 1
             parámetros                                                     
             configurables                                                  

  11         Optimización                     10 6--15 h                  7 1, 2, 10
             estática baseline                                              

  12         Parámetros                       10 1--3 días                9 7, 8, 11
             adaptativos                                                    

  13         Evaluar estados                   8 4--10 h                  9 6, 12
             discretos de salud                                             

  14         Evaluar Markov / MDP              7 1--3 días               10 13

  15         Evaluar RL /                      8 3--10+                  10 12, 14
             optimización                        días                       
             secuencial avanzada                                            

  16         Reinicio completo en              6 2--4 h                   3 Ninguna
             Recolectar                                                     
  ----------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 17. Dependencias principales

### Camino de confiabilidad

**Auditar lotaje → asegurar trazabilidad de operaciones → confiar en los
resultados económicos.**

No tiene sentido optimizar X5 si el simulador puede estar calculando
incorrectamente el lotaje o el P&L.

### Camino de entendimiento de datos

**Inventariar variables → visualizar → identificar variables útiles →
reducir dimensionalidad conceptual.**

### Camino de optimización

**Función objetivo → mapear parámetros → baseline estático → estudiar
cada parámetro → funciones adaptativas → estados/MDP/RL solo si son
necesarios.**

------------------------------------------------------------------------

## 18. Métricas para priorizar el trabajo

Además del impacto, cada iniciativa puede evaluarse con:

### Impacto

Escala 0--10.

¿Cuánto puede cambiar la calidad final de X5?

### Incertidumbre

Escala 0--10.

¿Cuánto desconocemos actualmente sobre esta pieza?

Una tarea de alto impacto y alta incertidumbre merece investigación
temprana.

### Esfuerzo

Horas o días estimados de implementación utilizando IA.

### Dependencias

Restricción dura.

Si B depende de A, **A debe realizarse antes que B**, independientemente
del score de prioridad.

### Evidencia obtenida

Escala sugerida 0--10:

-   0: intuición;
-   2: hipótesis conceptual;
-   4: evidencia visual;
-   6: backtesting inicial;
-   8: validación temporal/out-of-sample;
-   10: evidencia robusta y repetible.

La evolución deseada es:

> **Intuición → hipótesis → análisis → backtesting → evidencia
> out-of-sample.**

### Potencial de simplificación

También puede medirse 0--10.

¿Cuánto permite esta tarea eliminar reglas, variables o complejidad
innecesaria?

Esta métrica es especialmente relevante para X5 porque uno de los
riesgos identificados es **complicar demasiado el cerebro cuando el
objetivo real puede resolverse mediante unas pocas relaciones bien
elegidas**.

------------------------------------------------------------------------

## 19. Principios de diseño que emergen de la revisión

### 19.1. Maximizar el sistema, no el trade

Una operación no debe juzgarse aisladamente.

### 19.2. Confiabilidad antes que sofisticación

Antes de ML avanzado, verificar lotaje, P&L y transiciones de órdenes.

### 19.3. Parsimonia

Utilizar pocas variables explicativas cuando sea posible.

### 19.4. Especialización

Cada parámetro debería depender solamente de las variables que tengan
sentido para él.

### 19.5. Interpretabilidad

Debe poder explicarse por qué X5 eligió determinado valor de A, B, N,
lotaje, etc.

### 19.6. Evidencia antes que arquitectura

No implementar Markov, MDP o RL simplemente porque sean técnicamente
atractivos.

### 19.7. Baseline primero

Toda sofisticación debe superar una configuración estática optimizada.

### 19.8. Validación fuera de muestra

No basta con maximizar el resultado sobre el período utilizado para
aprender.

### 19.9. Riesgo como parte de la política

Drawdown, volatilidad y exposición deben formar parte explícita del
análisis.

### 19.10. Complejidad incremental

Agregar una nueva variable, estado o modelo solo cuando demuestre valor
adicional.

------------------------------------------------------------------------

## 20. Hipótesis de trabajo actual

La hipótesis más prometedora después de esta discusión es:

> **X5 puede construirse como un conjunto de políticas pequeñas e
> interpretables, donde cada parámetro configurable depende
> dinámicamente de unas pocas variables explicativas relevantes, y todas
> esas funciones son entrenadas/evaluadas en función de su capacidad
> para maximizar el resultado económico acumulado durante el horizonte
> temporal.**

Ejemplos:

\[ N=f(Drawdown) \]

\[ A=f(Volatilidad reciente) \]

\[ B=f(Volatilidad, P&L latente) \]

en lugar de comenzar inmediatamente con:

> "Existe un único estado multidimensional complejo que un gran modelo
> debe interpretar para decidir todo".

------------------------------------------------------------------------

## 21. Pregunta rectora para cada componente de X5

Para cada regla, parámetro o modelo existente, preguntar:

> **¿Esta pieza ayuda realmente a maximizar la ganancia acumulada
> ajustada por el riesgo a través del tiempo, o solamente agrega
> complejidad?**

Y para cada parámetro:

> **¿Cuál es el conjunto mínimo de variables que necesito conocer para
> determinar razonablemente su valor óptimo en este momento?**

Estas dos preguntas deberían guiar la reconstrucción del cerebro de X5.

------------------------------------------------------------------------

## 22. Próximo enfoque recomendado

La siguiente fase práctica debería concentrarse en cuatro frentes:

1.  **Validar la mecánica económica:** lotaje, P&L y cierres.
2.  **Construir la tabla maestra de Bitcoin:** precio + técnicos +
    fundamentales + frecuencia.
3.  **Inventariar todos los parámetros configurables de X5** y
    documentar exactamente qué controla cada uno.
4.  **Tomar los parámetros uno por uno** y plantear qué pocas variables
    podrían explicarlos, comenzando por relaciones intuitivamente
    fuertes como:
    -   drawdown → N;
    -   volatilidad reciente → A.

A partir de esa base, los datos y el backtesting deberían decidir cuánto
más sofisticado necesita ser X5.
