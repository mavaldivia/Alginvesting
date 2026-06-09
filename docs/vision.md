# CONTEXTO ESTRATÉGICO COMPLETO — ALGINVESTING

## Contexto actual

Alginvesting es un sistema de trading algorítmico personal cuyo objetivo actual es identificar soportes y resistencias óptimos sobre distintos activos financieros y ejecutar órdenes de compra semi-automáticamente a través de MetaTrader5.

Actualmente existen:
- X0: generación de soportes y resistencias.
- X1: ejecución de órdenes y gestión operativa.

Parámetros actuales relevantes:
- N
- K
- N_EXP
- M
- LAMBDA
- DELTA_INICIAL
- a
- b
- PERDIDA_MAX

## Historia

En enero operé una versión previa del algoritmo con aproximadamente 3.000 USD de capital real, prácticamente todos mis ahorros líquidos.

La estrategia operaba principalmente BTC y ETH.

La combinación de:
- N demasiado agresivo
- ausencia de control robusto de pérdidas
- muchas órdenes abiertas
- alta volatilidad

terminó provocando la pérdida total de la cuenta en aproximadamente diez días.

Mes y medio antes había obtenido ganancias relevantes en demo utilizando una estrategia similar, lo que probablemente generó una falsa sensación de confianza.

La conclusión es que el problema no necesariamente era la hipótesis central del sistema, sino la ausencia de una capa superior capaz de adaptar riesgo y parámetros al contexto.

---

# Visión

No quiero construir simplemente un algoritmo de soportes y resistencias.

Quiero construir un sistema adaptativo capaz de aprender continuamente cómo operar cada activo.

Los soportes son una herramienta.

El objetivo real es optimizar decisiones.

---

# Cerebro Macro

Quiero una capa superior de inteligencia que gobierne todo el sistema.

Su trabajo no será abrir o cerrar órdenes directamente.

Su trabajo será decidir:

- qué activos operar
- cuándo operarlos
- con qué riesgo operarlos
- con qué parámetros operarlos

No quiero parámetros fijos.

Quiero parámetros aprendidos.

---

# Capa Fundamental (X2)

La capa fundamental debe estudiar diariamente cada activo.

Para acciones:
- ingresos
- utilidades
- márgenes
- crecimiento
- EPS
- P/E
- EV/EBITDA
- ROE
- ROA
- market cap
- free cash flow
- deuda
- y cualquier ratio relevante

Para crypto:
- market cap
- volumen
- dominancia
- liquidez
- actividad de red
- métricas on-chain
- adopción
- y cualquier proxy razonable

## Objetivo

Generar un score de confianza.

Ejemplo:

"Probabilidad de que este activo valga más en el futuro".

## Qué gobierna

### Habilitación del activo

- operar
- reducir exposición
- suspender compras
- deshabilitar

### Incidencia estructural sobre N

Mayor confianza:
- mayor N

Menor confianza:
- menor N

---

# Capa Técnica

Los técnicos explican el momento actual del activo.

Indicadores mínimos:

- SMA
- EMA
- RSI
- MACD
- ATR
- Bollinger Bands
- Momentum
- Volatilidad
- Drawdown
- Tendencia
- Distancia a soportes y resistencias

Además, cualquier variable explicativa razonable:

- precio actual
- volumen relativo
- volatilidad reciente
- capital disponible
- exposición actual
- órdenes abiertas
- pérdida flotante
- ganancia flotante
- densidad de soportes
- etc.

---

# Parámetros gobernados por el cerebro

Actualmente:

- N
- K
- N_EXP
- M
- LAMBDA
- DELTA_INICIAL
- a
- b
- PERDIDA_MAX

## a

Ganancia mínima para activar trailing stop.

## b

Distancia del trailing stop respecto al precio.

Cuando el precio sube:

SL_new = Precio_Actual - b

siempre que el nuevo stop quede más arriba que el anterior.

---

# Aprendizaje Continuo

No quiero una colección infinita de IFs.

Quiero que el sistema aprenda.

Cada orden debe transformarse en un ejemplo de entrenamiento.

Registrar:

- activo
- timestamp apertura
- timestamp cierre
- precio entrada
- precio salida
- parámetros utilizados
- features fundamentales
- features técnicas
- contexto operativo
- retorno
- drawdown máximo
- ganancia máxima flotante
- duración
- motivo de cierre

---

# Objetivo de Aprendizaje

La unidad de aprendizaje debe ser la orden individual.

Cada orden representa:

- contexto
- decisión
- consecuencia

---

# Estrategia de Modelado

No comenzar con Reinforcement Learning.

Etapa 1:
- modelos supervisados

Predicciones:
- retorno esperado
- probabilidad de pérdida
- drawdown esperado
- duración esperada

Etapa 2:
- recomendación de parámetros

Etapa 3:
- evaluar RL cuando exista suficiente histórico

---

# Arquitectura Deseada

X0_data_supports.py
→ soportes y resistencias

X1_trading.py
→ ejecución real

X2_fundamentals.py
→ score fundamental

X3_technical_features.py
→ indicadores técnicos

X4_backtester.py
→ simulación histórica

X5_model_training.py
→ entrenamiento

X6_macro_brain.py
→ recomendación dinámica de parámetros

config/active_parameters.json
→ parámetros consumidos por X0 y X1

---

# Objetivo Final

Evolucionar desde:

Sistema de parámetros fijos

hacia:

Sistema adaptativo

capaz de aprender:

- qué activos operar
- cuándo operarlos
- con qué riesgo operarlos
- con qué parámetros operarlos

utilizando fundamentales, técnicos, contexto operativo y resultados históricos.

---

# Pregunta para Claude

Con toda esta visión:

- ¿Qué arquitectura propondrías?
- ¿Qué datos almacenarías?
- ¿Qué modelos utilizarías?
- ¿Cómo diseñarías el backtesting?
- ¿Cómo evitarías sobreajuste?
- ¿Cómo gobernarías los parámetros?
- ¿Qué harías diferente?

Critica la idea si es necesario.

Propón una mejor si la encuentras.
