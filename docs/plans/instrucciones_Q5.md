# Instrucciones Q5-1: medir cuánto dura una vuelta de backtest (Windows)

Este archivo y la configuración que usa el paso 2 (`config_V4_medicion_q5_1.py`) viajan por git: están en `docs/plans/` y llegan con `git pull`.

## Para qué

Medir cuánto tarda un backtest completo de BTCUSD con parámetros estáticos, desde el 2022-03-01 hasta la última vela. Con esa duración se decide cuántas vueltas por valor caben en el aprendizaje del backtesting inteligente (Q5-4). Ejemplo: si una vuelta dura 3 horas, 32 vueltas son 4 días de computador por valor; si dura 20 minutos, son 10 horas.

## Antes de empezar

- Todos los comandos se corren en PowerShell, desde la raíz del proyecto.
- Debe existir `Data\BTCUSD.csv` y `Data_minuto\BTCUSD.csv`, con datos al día.
- No suspendas ni apagues el equipo mientras corre: puede tardar horas.

## Pasos

1. Trae los cambios, activa el entorno y crea la versión de backtesting `V4`:
   ```
   git pull
   conda activate revenAI
   python scripts/X4B_crear_version_backtesting.py V4
   git checkout -- scripts/config.py
   ```
   X4B registra la versión en `scripts/config.py`; el `git checkout` descarta ese cambio para que no estorbe el próximo `git pull`. El registro no se necesita para correr con `--version`.

2. Copia la configuración ya armada sobre la que creó X4B:
   ```
   copy docs\plans\config_V4_medicion_q5_1.py resources\x4\versionV4\config_V4.py
   ```

3. Corre el backtest completo, guardando la salida en un archivo con fecha y hora (así una ventana nueva después de una interrupción no pisa la salida anterior; `-u` evita que Python retenga líneas en un buffer al usar el pipe):
   ```
   python -u scripts/X4_backtester.py --version V4 --reset 2>&1 | Tee-Object -FilePath "resources\x4\versionV4\salida_V4_$(Get-Date -Format yyyyMMdd_HHmm).txt"
   ```

4. Cuando termine (o en cualquier momento, aunque la corrida esté interrumpida o aún corriendo), empaqueta todo en un solo zip:
   ```
   python scripts/q5_empaquetar_medicion.py V4
   ```
   Genera `resources\x4\versionV4\medicion_V4.zip` con la salida de consola de todas las ventanas, `config_V4.py`, `checkpoint.json`, el log de cada búsqueda de soportes (duración, iteraciones, si convergió; filtrado a esta corrida) y `resumen.json` con el modelo de CPU, la RAM y los tiempos agregados. Envía ese zip a Claude, en el Mac, más:
   - Si la última línea de la salida dice "Backtest completado" o "STOP OUT".
   - Si había otros procesos pesados corriendo. Si `resumen.json` dice que `psutil` no está instalado, la cantidad de RAM del equipo.

## Qué configuración se usa

| Parámetro | Valor | Por qué |
|---|---|---|
| Activo | BTCUSD | el más pesado: ~38 700 velas H1 desde 2022, contra ~11 000 de las acciones |
| `N` (cantidad de soportes) | 180 | `n_sizes_ejecucion` de `config.py` |
| `A`, `B`, `PERDIDA_MAX_BT` | 3, 1.5, 200 | valores de producción |
| Recálculo de soportes | cada 7 días (168 velas) | cadencia de crypto en `config_smart.py` |
| Inicio del backtest | 2022-03-01 | 60 días de calentamiento; los soportes usan datos desde `FECHA_INICIAL` (2022-01-01) |
| `capital_inicial` | 1 000 000 USD | solo para medir: con 3000 USD el stop-out probablemente corta la corrida antes del final y subestima la duración |

## Si algo sale distinto

- **X4B pregunta "La versión V4 ya existe... ¿Reiniciar infraestructura?"**: responde `N`, repite con otro número (por ejemplo `V5`) y en el archivo copiado cambia `version = 'V4'` por `version = 'V5'`. Copia el archivo a `resources\x4\versionV5\config_V5.py` y corre con `--version V5`.
- **`git pull` se queja de `scripts/config.py`**: corre `git checkout -- scripts/config.py` y repite el `git pull`.
- **`Config no encontrada`**: revisa que el paso 2 dejó el archivo en `resources\x4\versionV4\config_V4.py`.
- **`Sin datos H1 disponibles`**: falta `Data\BTCUSD.csv` o está vacío.
- **Dice "STOP OUT"**: no repitas; envíame la salida tal como quedó.
- **Se interrumpe** (corte de luz, cierre de ventana): retoma sin `--reset` (el checkpoint se guarda cada 24 velas), con el mismo comando del paso 3 sin `--reset`:
  ```
  python -u scripts/X4_backtester.py --version V4 2>&1 | Tee-Object -FilePath "resources\x4\versionV4\salida_V4_$(Get-Date -Format yyyyMMdd_HHmm).txt"
  ```
  No necesitas anotar nada: el zip del paso 4 junta la salida de todas las ventanas, y `resumen.json` marca los huecos largos entre búsquedas como posibles interrupciones.
- **Repetir la medición**: el caché de soportes (`resources\x4\versionV4\resources_V4\conjuntos_N`) sirve de punto de partida a la búsqueda siguiente, incluso con `--reset`, y una repetición mediría menos de lo real. Antes de repetir, borra esa carpeta.

## Qué viene después

Con la duración, Claude cierra Q5-1 y sigue con Q5-2 (serie causal de los parámetros y grilla de pasos). Si necesitas repetir la medición con otro activo (por ejemplo una acción), avísame antes de cambiar la configuración.
