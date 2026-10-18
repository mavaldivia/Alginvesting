# Estándar de reportes de investigación (Qx "sobre el agua")

Referencia permanente y reutilizable para cualquier notebook de investigación
de Alginvesting pensado para que Mauricio lo lea de principio a fin como un
informe — hoy `X5_Q4.ipynb`, a futuro `X5_Q5.ipynb` y cada nuevo parámetro
dinámico que se investigue después de `N` (~6-7 en total). Complementa, sin
reemplazar, la decisión "sobre el agua / bajo el agua" del 2026-10-17 en
`docs/context/decisiones.md` — ese documento registra la decisión y el por
qué; este documento es la plantilla operativa para aplicarla.

## 1. Filosofía

El notebook es un reporte que un Data Scientist Senior (Claude) le entrega a
un manager técnico (Mauricio): alguien con base matemática y experiencia en
modelos, series temporales y optimización, pero sin formación de Data
Scientist — hay vacíos reales en estadística, inferencia y metodologías
propias de la disciplina. El reporte no asume que Mauricio domina esos
conceptos, pero tampoco lo trata como alguien sin conocimientos técnicos.

Esto aplica **de la primera a la última celda**, sin excepción para las
secciones de preparación, carga de datos o utilidades compartidas. No existe
una "zona técnica" al principio y una "zona explicada" después — toda
celda markdown debe poder leerse como parte de la misma narrativa.

## 2. Estructura narrativa por análisis relevante

Para cada pregunta de investigación (ej. cada parámetro dinámico), la
secuencia conceptual es:

**Pregunta → Motivación → Metodología → Fundamento matemático → Ejecución →
Resultados → Interpretación → Conclusión → Implicancias.**

No hace falta crear una subsección markdown explícita para cada eslabón —
hay que usar criterio para que la lectura sea natural, no una checklist
visible. Las celdas de código están al servicio del reporte, nunca al
revés: todo gráfico, tabla o métrica se presenta como evidencia dentro de un
razonamiento, no como un resultado aislado que el lector tenga que
interpretar por su cuenta.

## 3. No repetir el fundamento matemático completo en cada sección

Cuando varias secciones comparten exactamente el mismo mecanismo (ej. los 5
parámetros de `Q4` comparten índice compuesto → suavizado EMA → percentil
causal → sigmoide por `curve_fit`), el fundamento matemático y la
metodología se explican **en detalle la primera vez que aparecen** y se
referencian, sin repetir, en las secciones siguientes — ahí solo cambia la
variable de entrada y el rango del parámetro. Repetir la explicación completa
en cada sección sería ruido, no rigor.

## 4. Lenguaje

- Humano, terrenal, directo, ejecutivo y pedagógico — no un curso genérico
  de estadística, siempre contextualizado en la investigación concreta.
- Toda la matemática necesaria puede usarse (ecuaciones, coeficientes,
  funciones, optimización) — pero cada ecuación se acompaña de qué
  representa cada componente, no solo la fórmula.
- Toda métrica estadística (R², z-score, percentil, p-valor, etc.) se
  explica: qué mide, cómo se interpreta, qué permite concluir y qué
  limitaciones tiene.
- Todo gráfico se acompaña de qué ejes/series muestra y qué patrón conviene
  buscar en él.
- Diferenciar siempre entre resultado observado, hipótesis, evidencia
  estadística e incertidumbre — nunca presentar una hipótesis como
  conclusión confirmada.

### Jerga a evitar (o explicar entre paréntesis la primera vez)

Palabras que no se entienden sin contexto previo de ciencia de datos/software
no se usan sueltas. Ejemplos ya corregidos en `X5_Q4.ipynb`:

- ~~"Gate de arranque"~~ → "requisito antes de correr este notebook".
- ~~"wiring a producción"~~ → "conectar [el parámetro] al sistema de
  producción real".
- "leakage" → se puede usar, pero siempre acompañada la primera vez de su
  traducción conceptual: "fuga de información (que el modelo use sin
  querer datos que en producción todavía no existirían en ese momento)".

Regla general: si un término técnico es imprescindible, se escribe primero
en lenguaje llano y el término entre paréntesis después — nunca al revés.

## 5. Qué sí puede quedar técnico sin narrar

Código que no aporta a la decisión (imports, configuración de `pandas`,
helpers internos sin relevancia conceptual) no necesita una explicación
extensa — pero sí una frase de contexto de por qué existe esa celda y qué
prepara para el lector, en vez de quedar sin ningún marco.

## 6. Ejemplo de referencia

`X5_Q4.ipynb`, Sección 4 (`N = f(drawdown, volatilidad)`) es el ejemplo
completo a imitar: subsecciones 4.0-4.8 cubren qué se investiga y por qué,
variables elegidas, metodología (z-score, índice compuesto, suavizado EMA,
percentil causal, sigmoide acotada, mínimos cuadrados), cómo leer cada
gráfico, diagnóstico numérico e implicancias. Las Secciones 0-3 del mismo
notebook (preparación, carga de outputs previos, alcance, utilidades
compartidas) aplican el mismo estándar a nivel de "reporte", aunque el
contenido ahí sea de preparación técnica — ver esas celdas como ejemplo de
cómo narrar configuración sin volverla un script técnico suelto.

## 7. Aplicación a futuros parámetros y a Q5

Cada parámetro dinámico futuro (más allá de `N`, `A`, `factor_B`, `K`,
`N_EXP`) puede tener sus propias variables, hipótesis, forma funcional y
procedimiento de validación — eso varía. Lo que no varía es la experiencia
de lectura descrita en este documento. Al construir `X5_Q5.ipynb` (validación
económica, puente a `X4_backtester.py` — bloqueado hoy por `[Q5-1]`, ver
`docs/tracking/todos.md`), este estándar aplica desde su primera celda,
igual que en `X5_Q4.ipynb`.
