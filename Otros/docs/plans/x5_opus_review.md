# X5 — Opus Review: plan de trabajo

> Documento de control de esta sesión de revisión de X5. Cada paso se marca como `[x]` al completarse.
> Fuente de verdad del progreso: este archivo.

---

## Prompt original (copiado tal cual)

```
MANDATORIO: Como puede que me quede sin tokens, lo primero que debes hacer es crear en plans un md que se llame
x5_opus_review y planificar. Se parar toda la pedida en puntos concretos de tal forma que los hagas de
manera secuencial y los vayas marcando como done. Al comienzo de ese md, copia este propmt tal cual te lo estoy entregando

Básicamente quiero que revises x5_macro_brain.py, corrijas detalles si los encuentras, además de actualizar plans/x5_plan.md,
plans/x5_plan_redes_neuronales.md en base a este código y cosas que tengan sentido que puedan faltar (crea en ese caso
un TO DO en x5_plan.md

-Además, crea en x5_plan.md, un paso a paso (al final) para entender como ejecutar exte código (porque sigo medio confundido), considerando
que no existe ahora ningun dato de entrenamiento y espero primero un modo que haga backtesting paralelos en todos los valore sy vaya recopilando datos para despues entrenar los modelos
de ML definidos. Estas ejecuciones deben ser ciclicas y se deben ir corrigiendo (en verdad la recoleccion de datos y en el entrenamiento deben ser paralelos, para que los parametros
se vayan corrigiendo en cada valor). Cuando un ciclo se acaba en un valor, comienza nuevamente el backtesting desde la fecha inicial

- Finalmente, crea un PDF que contenga toda la info de x5_plan y x5_plan_redes_neuronales que sea basado en latex y con diagramas / dibujos perfectamente
entendibles para poder imprimirlo y leerlo

Recuerda mis limitaciones técnicas e intenta explicar con peras y manzanas sabiendo que tengo conocimientos en modelos de ML básicos, Redes Neuronales (FFNN y LSTM - Convolucionales)
+ train / test + gradient descent + backpropagation, etc...pero eso nomás. Necesito entender muy bien esta etapa para poder ir iterando, ya que es el cerebro del funcionamiento
```

---

## Objetivo global

1. Revisar `scripts/X5_macro_brain.py` contra el código real de X4 (`--x5`) y `config.py`. Detectar bugs/desalineaciones.
2. Actualizar `docs/plans/x5_plan.md` y `docs/plans/x5_plan_redes_neuronales.md` para que reflejen la **implementación real** (funciones, schema del store, CLI, métricas).
3. Registrar como `TO DO` en `x5_plan.md` lo que tenga sentido y falte.
4. Agregar al final de `x5_plan.md` un **paso a paso de ejecución** (desde cero, sin datos), explicado con peras y manzanas.
5. Generar un **PDF LaTeX** con diagramas, imprimible, que fusione ambos planes.

---

## Hallazgos de la revisión de código (resumen)

> Detalle completo en el Paso 1. Se listan aquí para que queden registrados aunque se corte la sesión.

- **H1 (importante)** — Desalineación de targets store ↔ modelo. X4 (`_construir_fila_oc`) solo escribe `retorno_pct` como variable objetivo. Las columnas `pnl_flotante_activo` (`TARGET_FLOTANTE`) y `pnl_cerrado_activo_sesion` (`TARGET_CERRADO`) que X5 usa como targets **no existen en el store**.
  - LGBM: los heads `flotante` y `cerrado` se omiten (`len(X)=0 < 20`) → solo se entrena `retorno`, y `_entrenar_lgbm` retorna `exito=False`.
  - FTT: `y_f`/`y_c` se rellenan con `np.zeros` → esos heads entrenan contra 0 (ruido, no crashea).
- **H2** — Los registros `tipo_registro='periodico'` **nunca entran al entrenamiento** (X5 filtra `'oc'`) y su target teórico `pnl_flotante_activo` tampoco se escribe. Todo el diseño de "registros periódicos para rachas bajistas" está inerte hoy.
- **H3** — Schema del store real más pobre que el documentado: no hay `pnl_usd`, `ticket`, `precio_entrada/salida`, `pnl_flotante_activo`, `pnl_cerrado_activo_oc`. Solo timestamps + params + X2/X3 OE/OA + portfolio + `retorno_pct`.
- **H4 (menor)** — `_features_temporales_ahora()` usa `pd.Timestamp.now()`: válido para inferencia en vivo (Fase 2), no para reconstruir contexto histórico.
- **H5 (menor)** — En el store, `n_ejecucion = cfg.n_sizes[activo]` (X4), pero el baseline/rango de X5 usan `n_sizes_ejecucion`. Revisar coherencia del parámetro que se registra vs. el que se optimiza.
- **H6 (menor/eficiencia)** — `_recolectar` recarga el CSV completo de cada activo en cada marcador `[MES_BT]`. O(n) repetido; aceptable a esta escala.
- **H7 (diseño vs. pedido)** — El `--recolectar` actual es **secuencial entre activos** (X4 recorre los valores en un loop dentro de un proceso), no paralelo. El reinicio desde `fecha_inicio` sí ocurre por ciclo. La "corrección de params" es a nivel de ciclo (explore/exploit), no vela a vela.

---

## Decisiones (confirmadas por el usuario)

- **D1 — PDF**: ✅ Instalar `tectonic` (1 binario vía brew), generar `.tex` con diagramas TikZ y compilar el PDF localmente.
- **D2 — Alcance de correcciones**: ✅ **Corregir pipeline completo**. X4 escribe los 3 targets (`retorno_pct`, `pnl_flotante_activo`, `pnl_cerrado_activo`) + target de registros periódicos; X5 los consume. Cambia el schema del store.
- **D3 — Paralelismo de recolección**: ✅ **Rediseñar `--recolectar`** para lanzar un proceso X4 por activo en paralelo, cada uno reiniciando desde `fecha_inicial` al cerrar su ciclo, con auto-train al cruzar el umbral.
- **D4 — Simplificar modos CLI** (pedido posterior del usuario): ✅ **3 modos + casilla `--train`**. Modos mutuamente excluyentes: `--recolectar` (genera datos + entrena), `--infer` (recomienda params), `--status` (diagnóstico). `--train` pasa a ser flag opcional (`--infer --train` = reentrena y luego recomienda). Se **elimina `--vela`** (era copia exacta de `--infer`).

---

## Pasos (secuenciales)

- [x] **Paso 0 — Contexto**: leer X5_macro_brain.py, ambos planes, bloque X5 de config.py y modo `--x5` de X4. Verificar toolchain PDF.
- [x] **Paso 1 — Crear este plan** con el prompt verbatim y los hallazgos.
- [x] **Paso 2 — Resolver D1/D2/D3/D4** con el usuario (AskUserQuestion). Confirmadas las 4.
- [x] **Paso 3 — Correcciones al código** (X4 + X5). Detalle:
  - X4 `_contexto_portfolio_x5`: calcula `pnl_flotante_activo` (P&L flotante USD de las OA).
  - X4 `_construir_fila_oc` / `_construir_fila_periodica`: escriben `pnl_cerrado_activo` (= `est_a['GC']`) y `pnl_flotante_activo`. Los 3 targets quedan poblados; los registros periódicos ya tienen su Y (`pnl_flotante_activo`).
  - X4 paralelismo: `ejecutar_x5_ciclo(cfg, activo=None)` aísla `resources_{version}_{activo}`; CLI `--activo`; `_generar_params_exploit(..., activo)` → `X5 --infer --activo`.
  - X5 targets: `TARGET_CERRADO='pnl_cerrado_activo'`. `_preparar_features(tipos_registro=('oc',))`; head `flotante` entrena con `('oc','periodico')`.
  - X5 CLI: 3 modos (`--recolectar`,`--infer`,`--status`) + casilla `--train`. `--vela` eliminado.
  - X5 `_recolectar`: paralelo por activo (ThreadPoolExecutor, 1 worker/activo, auto-train por ciclo).
  - X5 `_escribir_active_parameters`: merge + escritura atómica (soporta `--infer --activo` en paralelo).
  - Validado: `py_compile` OK; `--help`, `--vela`(rechazado), `--status`, `--infer`, `--infer --activo` (merge) OK.
- [x] **Paso 4 — Actualizar `x5_plan.md`**: cabecera de estado, estructura de código real (3 modos + `--train`), schema real del store, funciones/métricas reales, TO DOs derivados de la revisión.
- [x] **Paso 5 — Actualizar `x5_plan_redes_neuronales.md`**: caja de estado (diseño→código), nota Fase 2 en "ciclo por vela", glosario de modos.
- [x] **Paso 6 — Paso a paso de ejecución** al final de `x5_plan.md` (desde cero, recolección paralela, con peras y manzanas).
- [x] **Paso 7 — PDF LaTeX**: `docs/plans/x5_documento.tex` (+ `x5_documento.pdf`, 6 pág A4) con 8 diagramas TikZ (pipeline, arquitectura escalable, store, gradient boosting, feature tokenizer, atención Q/K/V, multi-head, recolección paralela). Compilado con tectonic, verificado visualmente (poppler). Sin overfull/errores.
- [x] **Paso 8 — Cierre**: decisiones registradas en `docs/context/decisiones.md` (2026-07-18); `.gitignore` actualizado (`config/active_parameters.json`). Resumen entregado al usuario.

---

## PDFs generados

- `docs/plans/x5_documento.pdf` — versión corta (6 pág, resumen visual).
- `docs/plans/x5_documento_extendido.pdf` — **versión extendida (34 pág)**: guía completa con
  capítulos, ejemplos numéricos y ~20 diagramas TikZ (pipeline, store, gradient boosting,
  feature tokenizer, atención Q/K/V, bloque Transformer, multi-head, gradient ascent,
  explore/exploit, recolección paralela, fases). Cubre todo el contenido de ambos planes.

```bash
cd docs/plans && tectonic x5_documento.tex             # → x5_documento.pdf (corto)
cd docs/plans && tectonic x5_documento_extendido.tex   # → x5_documento_extendido.pdf (extendido)
```
