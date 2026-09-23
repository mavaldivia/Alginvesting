[1] [OK] Transversal
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
/new_todo X0
En X0 quiero hacer un cambio en los logs
Cuando ejecute el script, quiero la misma información INICIAL de siempre
Ejecuciones por hora y por minuto para cada activo, X2, X3, deltas actuales, cold-warm starts, etc (lo mismo de siempre)
Luego de eso, quiero MANDATORIAMENTE lo siguiente

UNA LINEA POR ACTIVO, QUE SEA REEMPLAZADA

Espero ver algo así

[Ciclo 0] BTCUSD_180: cambios=10152 pasos_max=18 FO=-4.186e-02 [corriendo]
[Ciclo 0] ETHUSD_180: ....
....

[Ciclo 0] TSLA_180: ...

A partir de ese momento, no se debe generar ninguna linea de código, simplemente, la linea de cada activo debe ser reemplazada y mostrarse secuancialmente de la siguiente manera (ejemplo para BTC)
* Recuerda: Es REEMPLAZAR la linea de ese activo

[Ciclo 0]: BTCUSD_180: Calculando distancias
[Ciclo 0] BTCUSD_180: cambios=10152 pasos_max=18 FO=-4.186e-02 [corriendo]
[Ciclo_0] BTCUSD_180: Convergencia
[Ciclo_0] BTCUSD_180: Actualizando data por hora
[Ciclo_0] BTCUSD_180: Actualizando data por minuto
[Ciclo_0] BTCUSD_180: Actualizando X2
[Ciclo_0] BTCUSD_180: Actualizando X3
[Ciclo_1] BTCUSD_180: Calculando distancias
..... (se repite, con el nuevo ciclo)

[5] [OK] Revisar logs de x1 en usd de subida y de bajada considerando lotajes_m mayor a 1
/new_todo X1:
En los logs, de X1 con usd de subida y de bajada, para no tener problemas con el lotaje, mejor pon la diferencia en usd del precio del activo directamente