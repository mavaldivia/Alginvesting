## TO DO

**Convención de priorización**: cada ítem pendiente lleva `(I:x C:y H:z → score)` — Impacto, Complejidad de desarrollo, Habilitación, escala 1–10. `score = √(I × H) / C`. Dentro de cada sección los ítems se ordenan de mayor a menor score.

### Prioridad_0

Urgencias transversales. Una vez completadas, el ítem se mueve a `docs/done.md` en su sección correcta.

- [ ] **Tiempo de ejecución al final de cada script**: al terminar `X0_data_supports.py`, `X1_trading.py` y cualquier script Python del proyecto, imprimir el tiempo total transcurrido (formato `HH:MM:SS` o segundos si < 60 s). Implementar con `time.time()` en el `if __name__ == '__main__'` de cada script. (I:3 C:1 H:2 → 2.45)

### X0 — X0_data_supports.py

- [ ] Revisar con Mauricio la lógica de scoring de `calcular_FO` — ya se agregaron `v` y `f` (lo de mayor impacto); queda pendiente discutir ajustes menores (ej. `h_dist` por volatilidad, conteo de retests) (I:2 C:3 H:2 → 0.67)

### X3 — X3_technical_features.py

- [ ] **X3_technical_features.py**: indicadores técnicos (SMA, EMA, RSI, MACD, ATR, Bollinger, momentum, volatilidad, drawdown, tendencia, distancia a soportes). Variables de contexto operativo (precio, volumen relativo, capital disponible, exposición actual, órdenes abiertas, pérdida/ganancia flotante, densidad de soportes). (I:7 C:5 H:7 → 1.40)

### X4 — X4_backtester.py

- [ ] Definir schema del store de trades históricos: qué se guarda por cada orden simulada (activo, timestamps, precio entrada/salida, parámetros usados, features fundamentales y técnicas al momento de apertura, retorno, drawdown máximo, ganancia flotante máxima, duración, motivo de cierre). (I:5 C:2 H:9 → 3.35)
- [ ] **Estructura de carpetas y configs por versión de backtesting**: crear `x4_backtesting/config/` con un archivo `config_[version].py` por versión (ej. `config_V1.py`), con la misma estructura que `config.py` de producción. Cada archivo define los parámetros exactos usados en esa corrida (activos, N, K, LAMBDA, A, B, TS, PERDIDA_MAX, fechas, etc.). Permite reproducir cualquier versión de backtesting de forma exacta. (I:5 C:2 H:8 → 3.16)
- [ ] **DELTA_INICIAL por (valor, N, version)**: en backtesting, `delta_inicial` depende solo del trío `(valor, N, version)`, no de `max_datetime`. Se ajusta con `FACTOR_DELTA` cada vez que el optimizador converge para ese trio, al igual que en producción. Archivo de estado: `{valor}_{N}_{version}_bt_delta.json` (I:7 C:3 H:8 → 2.49)
- [ ] **Descarga incremental de `Data_minuto/`**: en X0, agregar descarga de datos M1 desde MT5 con la misma lógica incremental que `Data/` (merge + drop_duplicates). Pre-requisito para simulación intra-vela en X4. Fuera de git (regenerable). (I:6 C:3 H:8 → 2.31)
- [ ] **Config de versiones para backtesting**: sección en `config.py` con `version = 'V1'` (str activo) y `fechas_version = {'V1': ['2023-01-01', 'F']}`. `'F'` = hasta la última vela disponible. Al reiniciar con la misma versión, el sistema retoma desde el último snapshot guardado. Las órdenes simuladas se gatillan de forma ficticia sobre precios reales (I:8 C:5 H:8 → 1.60)
- [ ] **Simulación intra-vela en X4**: subrutina embebida en X4_backtester. Trigger: `hay_soporte_en_rango and (puede_activar_ts or puede_activar_perdida_max)`, donde `hay_soporte_en_rango = Low <= max(soportes_activos)`, `puede_activar_ts = (H-L) > A/(lote*units)`, `puede_activar_perdida_max = (H-L) > PERDIDA_MAX/(lote*units)`. Método: 60 registros M1 aleatorios de `Data_minuto/` escalados linealmente para calzar el OHLC H1. Diseño en `docs/decisiones.md` 2026-06-08. (I:7 C:5 H:7 → 1.40)
- [ ] **X4_backtester.py**: simulación histórica desde 2024-01-01 con parámetros dinámicos (búsqueda de nuevos soportes cada N días, cierre de operaciones por trailing stop o pérdida máxima, tracking de cuenta). Es la fuente primaria de training data para X5. (I:9 C:8 H:9 → 1.13)

### X5 — X5_model_training.py

- [ ] **X5_model_training.py**: modelos supervisados sobre el store de trades. Predicciones: retorno esperado, probabilidad de pérdida, drawdown esperado, duración esperada. Evaluar overfitting (cross-val temporal, no aleatoria). Registrar qué modelos se probaron y por qué se eligió cada uno. (I:8 C:7 H:8 → 1.14)

### X6 — X6_macro_brain.py

- [ ] Definir schema de `config/active_parameters.json`: qué parámetros escribe X6 (N, K, N_EXP, M, LAMBDA, DELTA_INICIAL, a, b, PERDIDA_MAX), con qué granularidad (por activo, global, o mixto). (I:5 C:2 H:7 → 2.96)
- [ ] Definir frecuencia de ejecución de X6: ¿diario? ¿antes de cada corrida de X0? ¿en el loop de X1? Requiere discusión. (I:4 C:2 H:5 → 2.24)
- [ ] **X6_macro_brain.py**: recomendación dinámica de parámetros. Lee features de X2/X3 y predicciones de X5. Output: `config/active_parameters.json` consumido por X0 y X1. Corre en Windows por ahora; idealmente compatible con Mac en el futuro. (I:9 C:8 H:5 → 0.84)

### Transversal

- [ ] Evaluar compatibilidad de librería MT5 en macOS — si se resuelve, simplifica mucho el flujo Mac↔Windows. (I:6 C:3 H:5 → 1.83)

### Definir si hacer

Ítems válidos técnicamente pero cuyo valor real no está claro. Antes de implementarlos hay que decidir si efectivamente tienen sentido.

- [ ] Separar descarga de datos en módulo independiente (hoy está en X0) (I:4 C:5 H:4 → 0.80)
- [ ] **S7 — Criterio de parada por tasa de mejora**: agregar criterio adicional en `nuevo_optimizador_2` — si el promedio de las últimas `VENTANA_MEJORAS=10` mejoras aceptadas < `EPSILON_TASA=1e-6`, declarar convergencia aunque queden soportes sin evaluar. Complementa (no reemplaza) el criterio binario actual. Impacto principalmente cuando `delta_inicial` es muy pequeño. (I:1 C:2 H:1 → 0.50)

---
