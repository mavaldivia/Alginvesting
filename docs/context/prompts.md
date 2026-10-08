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


new_todo X0

Cambiar lógica de mejora y hacerlo por ciclos TEMPORALES

Si mejora FO, entonces se hace el cambio de soportes / resistencias (sale una O0 y entra una O0 nueva)
Cada 15 mins, se mapean los cambios a un JSON de soportes / resistencias para que X1 los lea y actualice (de O0 a OE)
Cada 1 hora, se actualiza data, data min, x2 y x3, además de incorporar las nuevas velas horarias si existen, calcular distancias en cada activo y comenzar (con los soportes / resistencias actualizados, una nueva FO inicial)
El delta inicial, factor delta, etc…ya no aplican

Ahora ese 15 mins y una hora (60 mins) son nuevos parámetros en config.py

T_UPDATE_O0 = 15
T_UPDATE_CICLO_X0 = 60

Manten el formato de los logs...cada activo a la izquierda debe decir [C {i} | A {j}] {valor}_{N}
C significa ciclo y A actualización (deben ser explicitamente "C" y "A"
i es el id del ciclo (sube 1 cada 60 mins en los parametros por default)
j es el id de la actualizacion (sube 1 cada 15 mins segun los parametros por default)


/new_todo Transversal
Tengo la impresiónhace poco de que, cuando mi pc se suspende, dejan de correr los códigos

Pasaron 15 hrs entre la tarde noche y hoy en la mañana

X0 estaba en C4 recién
En X1 tenía una OA con > 15 usd de ganancia, sin stop loss...cuando desbloquié el PC, se puso el SL

------------------

/new_todo X1

En general, he visto X0 y X1 funcionar bastante mejor el último tiempo! Eso si, hay una particularidad que no logro entender del todo bien

Mira este output (actual) de X1

AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: reemplazo abortado — ninguna de las 2 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  AMZN: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: reemplazo abortado — ninguna de las 2 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  AMZN: reemplazo — 119 OE eliminadas desde 82.89 hasta 251.96  lotaje_total=2.3800000000000017
  AMZN: reemplazo — 3 OE colocadas desde 127.16 hasta 130.01  lotaje=0.02
  GOOGL: 2 órdenes ejecutadas desde 345.87 hasta 348.68  lotaje=0.02
  AMZN: 47 órdenes ejecutadas desde 131.43 hasta 195.67  lotaje=0.02
  [OE > OA] BTCUSD  ticket=689777088  lotaje=0.02  ejecutada @ 81937.16
  AMZN: 17 órdenes ejecutadas desde 197.03 hasta 218.58  lotaje=0.02
  AMZN: 6 órdenes ejecutadas desde 219.91 hasta 226.56  lotaje=0.02
  AMZN: 2 órdenes ejecutadas desde 227.88 hasta 229.21  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 230.53 hasta 230.53  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 231.85 hasta 231.85  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 233.17 hasta 233.17  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 234.49 hasta 234.49  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 235.81 hasta 235.81  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 237.12 hasta 237.12  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 238.44 hasta 238.44  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 239.75 hasta 239.75  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 241.07 hasta 241.07  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 242.38 hasta 242.38  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 243.69 hasta 243.69  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 245.0 hasta 245.0  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 246.31 hasta 246.31  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 247.62 hasta 247.62  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 248.93 hasta 248.93  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 250.23 hasta 250.23  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 251.54 hasta 251.54  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 252.84 hasta 252.84  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 254.14 hasta 254.14  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 255.44 hasta 255.44  lotaje=0.02
  AMZN: 1 órdenes ejecutadas desde 92.88 hasta 92.88  lotaje=0.02
  TSLA: reemplazo — 106 OE eliminadas desde 103.71 hasta 371.67  lotaje_total=2.1200000000000014
  TSLA: reemplazo — 1 OE colocadas desde 103.72 hasta 103.72  lotaje=0.02
  NVDA: reemplazo — 174 OE eliminadas desde 13.34 hasta 233.77  lotaje_total=3.4800000000000026
  NVDA: reemplazo — 3 OE colocadas desde 75.70 hasta 83.34  lotaje=0.02
  TSLA: 31 órdenes ejecutadas desde 106.26 hasta 182.52  lotaje=0.02
  NVDA: 45 órdenes ejecutadas desde 87.16 hasta 229.97  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 185.07 hasta 185.07  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 187.61 hasta 187.61  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 190.16 hasta 190.16  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 192.71 hasta 192.71  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 195.25 hasta 195.25  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 197.8 hasta 197.8  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 200.35 hasta 200.35  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 202.9 hasta 202.9  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 205.45 hasta 205.45  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 208.0 hasta 208.0  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 210.55 hasta 210.55  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 213.1 hasta 213.1  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 215.65 hasta 215.65  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 218.2 hasta 218.2  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 220.75 hasta 220.75  lotaje=0.02
  [OE > OA] ETHUSD  ticket=689796219  lotaje=0.2  ejecutada @ 2508.96
  BTCUSD: reemplazo — 110 OE eliminadas desde 16097.54 hasta 81356.66  lotaje_total=2.2000000000000015
  BTCUSD: reemplazo — 110 OE colocadas desde 16096.90 hasta 81353.80  lotaje=0.02
  ETHUSD: reemplazo — 59 OE eliminadas desde 903.31 hasta 2343.76  lotaje_total=11.79999999999999
  ETHUSD: reemplazo — 59 OE colocadas desde 903.30 hasta 2343.75  lotaje=0.2
  TSLA: 59 órdenes ejecutadas desde 223.3 hasta 371.71  lotaje=0.02
  NVDA: 124 órdenes ejecutadas desde 13.35 hasta 231.25  lotaje=0.02
  AMZN: 30 órdenes ejecutadas desde 82.85 hasta 125.74  lotaje=0.02
  NVDA: reemplazo — 16 OE eliminadas desde 66.79 hasta 203.16  lotaje_total=0.32
  NVDA: reemplazo — 16 OE colocadas desde 66.80 hasta 203.17  lotaje=0.02
  AMZN: reemplazo — 119 OE eliminadas desde 85.72 hasta 254.14  lotaje_total=2.3800000000000017
  AMZN: reemplazo — 119 OE colocadas desde 85.71 hasta 254.13  lotaje=0.02
  BTCUSD: reemplazo — 110 OE eliminadas desde 16096.9 hasta 81353.8  lotaje_total=2.2000000000000015
  BTCUSD: reemplazo — 111 OE colocadas desde 16096.79 hasta 81436.80  lotaje=0.02
  ETHUSD: reemplazo — 42 OE eliminadas desde 1092.3 hasta 2485.36  lotaje_total=8.400000000000002
  ETHUSD: reemplazo — 43 OE colocadas desde 1092.29 hasta 2488.43  lotaje=0.2
  [OE > OA] TSLA  ticket=689866609  lotaje=0.02  ejecutada @ 371.71
  TSLA: reemplazo — 5 OE eliminadas desde 315.29 hasta 353.74  lotaje_total=0.1
  TSLA: reemplazo — 5 OE colocadas desde 315.30 hasta 353.75  lotaje=0.02
  NVDA: reemplazo — 7 OE eliminadas desde 61.7 hasta 176.37  lotaje_total=0.14
  NVDA: reemplazo — 7 OE colocadas desde 61.71 hasta 176.38  lotaje=0.02


[PREGUNTA 1] Por que se ven bloques como:
  TSLA: 1 órdenes ejecutadas desde 200.35 hasta 200.35  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 202.9 hasta 202.9  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 205.45 hasta 205.45  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 208.0 hasta 208.0  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 210.55 hasta 210.55  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 213.1 hasta 213.1  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 215.65 hasta 215.65  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 218.2 hasta 218.2  lotaje=0.02
  TSLA: 1 órdenes ejecutadas desde 220.75 hasta 220.75  lotaje=0.02

Con "una orden por linea" y no todo compactado? (lo mismo para amazon)

[PREGUNTA 2] En casos como este:
TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: reemplazo abortado — ninguna de las 124 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  NVDA: reemplazo abortado — ninguna de las 74 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  NVDA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  BTCUSD: reemplazo — 111 OE eliminadas desde 16097.72 hasta 81937.74  lotaje_total=2.2200000000000015
  BTCUSD: reemplazo — 111 OE colocadas desde 16097.54 hasta 81937.16  lotaje=0.02
  ETHUSD: reemplazo — 36 OE eliminadas desde 1092.31 hasta 2438.17  lotaje_total=7.200000000000004
  ETHUSD: reemplazo — 36 OE colocadas desde 1092.30 hasta 2438.16  lotaje=0.2
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  NVDA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  ETHUSD: 1 órdenes ejecutadas desde 2508.96 hasta 2508.96  lotaje=0.2
  NVDA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  AMZN: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  AMZN: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: reemplazo abortado — ninguna de las 2 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  AMZN: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: reemplazo abortado — ninguna de las 1 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  TSLA: Error al ejecutar orden: retcode=10044, comment=session closed
  NVDA: Error al ejecutar orden: retcode=10044, comment=session closed
  AMZN: reemplazo abortado — ninguna de las 2 OE candidatas pudo colocarse (mercado no operable pese a trade_mode/tick); no se toca ninguna OE
  AMZN: reemplazo — 119 OE eliminadas desde 82.89 hasta 251.96  lotaje_total=2.3800000000000017

Hay demasiadas notificaciones de que el mercado está cerrado (necesito solo una notificación por bloque [y cada vez que ejecute X1, en caso de reiniciarlo] de que el mercado de acciones está cerrado
Con bloque me refiero a: una noche, un fin de semana, un festivo, etc....Avisame que el mercado se cerró y no me vuelvas a avisar nada hasta que vuelva a abrir

Aclarame que entiendes bien los dos puntos antes de implementar