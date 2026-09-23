[1] Transversal
Dame un md
/Users/macasaez/Desktop/claude_projects_v2/Alginvesting/docs/context/pars_configurables.md
Con la definición específica y lo más exacta posible de estos parámetros configurables

A, B, PERDIDA_MAX, LOTAJES_M, LAMBDA, K, N_EXP (si es que falta algún otro)

[2] [OK] new_todo X1: que no se eliminen OE si no se pueden poner nuevas por mercado cerrado
Hay dos tipos de eliminación / colocación de ordenes (en un activo específico)
a. Reemplazo de todas las OEs, por nuevas O0s
b. Una O0 pasa a OE porque el precio ha subido y tiene suficiente "margen"
Independiente del caso, cada vez que elimines ordenes (OEs) por alguna razón (creo que aqui tambien hay dos razones, la misma a anterior + c)
c corresponde a eliminar OEs de bajo precio (que estén lejos del precio actual) para no saturar el sistema de OEs (creo).
Si el caso es a, quiero que siempre, primero verifiques que el mercado está abierto y se podrán colocar nuevas ordenes. No me sirve que en el reemplazo hagas: elimar OEs y luego no puedas convertir las nuevas O0s en OEs
Además, en cada reemplazo quiero que, después de confirmar, hagas lo siguiente en orden para reemplazar
i) Elimina el 20% de las OEs (las que salen) con precio más alto, de > a <
ii) Coloca las nuevas O0s como OEs (las que entran) (crea los buy limints). Todos, de > a <
iii) Elimina el 80% restante de las OEs (las que salen) de > a <

[3] [OK] Multiplicar siempre A, b y perdida_max por lotajes_m en cada caso, cada vez que se crea una OE en particular (cuando se crea el buy limit)
Es decir, si esa orden de compra específica se convierte en OA y luego OC, actuará con A, b y perdida_max, "aumentado" o "multiplicado" por lotajes_m de esa orden específica

[4] Detallar como quiero los logs en X0

[5] Revisar logs de x1 en usd de subida y de bajada considerando lotajes_m mayor a 1