# Propuesta de reestructuración — Alginvesting

> **Ejecutada.** Esta propuesta se implementó completa: los archivos listados en §3/§4 ya están
> en sus rutas nuevas, `docs/done.md` se reconcilió y eliminó, `.gitignore`/`CLAUDE.md`/`README.md`
> se actualizaron, y los imports/rutas hardcodeadas afectadas se corrigieron (detalle en §8). El
> árbol de abajo describe el estado actual, no una propuesta pendiente.

## 1. Objetivo

Separar lo que hoy es el **núcleo operativo del proyecto** (lo que se lee, ejecuta o edita en el
día a día) de todo lo que es **histórico, superseded o fuera de foco**, para que abrir el repo
comunique de inmediato "esto es lo que importa hoy".

## 2. Criterio de clasificación

| Se queda en su lugar (vigente) | Va a `Otros/` |
|---|---|
| Se ejecuta, se importa, o se edita activamente | Nadie lo corre ni lo edita hoy |
| Es la versión más reciente de un documento/guía | Es una versión anterior ya superseded |
| Foco de trabajo actual (X5_alt, X0–X4) | X5 original — sigue existiendo pero dejó de ser el foco día a día |
| Referenciado desde `CLAUDE.md`, `todos.md` o el código | Referenciado solo por su propia versión anterior |

Un caso explícito del usuario: **`X5_macro_brain.py` y todo lo que gira en torno a él** ("X5
original") se considera hoy en desuso operativo — aunque `docs/tracking/todos.md` todavía tiene
ítems pendientes sobre él (ver nota en §5). Esto no es un juicio sobre su calidad ni una decisión
de descontinuarlo: refleja que el trabajo activo de esta etapa es `X5_alt` (`X5_P1`/`X5_P2`).

## 3. Árbol propuesto (nivel proyecto)

```
Alginvesting/
├── CLAUDE.md
├── README.md
├── .gitignore                      (actualizado: Alginvesting_base/ → Otros/Alginvesting_base/, quitada scripts/Otros)
├── config/                         # generado, fuera de git
├── Data/  Data_minuto/  resources/ # generados, fuera de git
│
├── scripts/
│   ├── config.py
│   ├── X0_data_supports.py
│   ├── X1_trading.py
│   ├── X2_fundamentals.py
│   ├── X3_technical_features.py
│   ├── X4_backtester.py
│   ├── X4B_crear_version_backtesting.py
│   ├── X5_P1.ipynb
│   └── X5_P2.py
│   (__pycache__/ eliminado — se regenera solo)
│
├── docs/
│   ├── context/
│   │   ├── decisiones.md
│   │   ├── vision.md
│   │   └── guia_git_v2.md
│   ├── plans/
│   │   ├── documentacion.html
│   │   ├── X5_alternativo.md
│   │   ├── X5_revision_exhaustiva_cerebro.md
│   │   ├── x2_plan.md
│   │   ├── x3_plan.md
│   │   ├── x4_plan.md
│   │   └── algoritmos.tex / algoritmos.pdf   (caso mixto, ver §5)
│   └── tracking/
│       ├── todos.md
│       ├── done.md                 (ya reconciliado con el docs/done.md eliminado, ver §5)
│       └── records.md
│
└── Otros/
    ├── Alginvesting_base/          # referencia histórica Windows, ya solo lectura
    ├── prompts                     # log fundacional de prompts, ya extraído a decisiones/todos
    ├── scripts/
    │   ├── X5_macro_brain.py
    │   ├── config_x5_default.py
    │   ├── x5_demo.py
    │   └── X5_analisis_exploratorio.ipynb
    └── docs/
        ├── context/
        │   ├── documentacion_V0.md
        │   ├── guia_git.md
        │   ├── paso_a_paso_git.md
        │   └── correcciones_x5.md
        ├── plans/
        │   ├── x5_plan.md
        │   ├── x5_plan_redes_neuronales.md
        │   ├── x5_opus_review.md
        │   ├── x5_documento.tex / x5_documento.pdf
        │   └── x5_documento_extendido.tex / x5_documento_extendido.pdf
        └── tracking/
            └── oportunidad de mejora.md
```

`Otros/` espeja internamente la carpeta de origen de cada archivo (`Otros/docs/plans/...`,
`Otros/scripts/...`) para no perder trazabilidad de dónde vino cada cosa.

## 4. Detalle por archivo — qué se mueve y por qué

### `scripts/` → `Otros/scripts/`

| Archivo | Motivo |
|---|---|
| `X5_macro_brain.py` | X5 original — reemplazado como foco por X5_alt |
| `config_x5_default.py` | Config exclusiva de X5 original |
| `x5_demo.py` | Demo interactivo de X5 original (`--recolectar --demo`) |
| `X5_analisis_exploratorio.ipynb` | Notebook exploratorio sobre el *store* de X5 original |

### `docs/context/` → `Otros/docs/context/`

| Archivo | Motivo |
|---|---|
| `guia_git.md` | Primera versión de la guía Mac↔Windows (jun-19), supersedida por `guia_git_v2.md` (jun-24) |
| `paso_a_paso_git.md` | Misma guía, otra redacción (jun-19); mismo contenido que `guia_git_v2.md` cubre hoy |
| `documentacion_V0.md` | Bitácora técnica "V0" (jun-11); su rol de bitácora lo cumple hoy `decisiones.md` |
| `correcciones_x5.md` | Correcciones puntuales sobre X5 original |

### `docs/plans/` → `Otros/docs/plans/`

| Archivo | Motivo |
|---|---|
| `x5_plan.md` | Plan de implementación de X5 original |
| `x5_plan_redes_neuronales.md` | Detalle de arquitectura NN de X5 original |
| `x5_opus_review.md` | Revisión puntual de X5 original |
| `x5_documento.tex` / `.pdf` | Documento explicativo "X5, el cerebro" — versión original |
| `x5_documento_extendido.tex` / `.pdf` | Versión extendida del mismo documento |

### `docs/tracking/` → `Otros/docs/tracking/`

| Archivo | Motivo |
|---|---|
| `oportunidad de mejora.md` | Auditoría puntual fechada 2026-06-13; su propio encabezado aclara que no reemplaza el TO DO — es un snapshot histórico de una revisión de código específica |

### Raíz → `Otros/`

| Archivo | Motivo |
|---|---|
| `Alginvesting_base/` | Ya documentado en `CLAUDE.md` como solo lectura / referencia histórica. Vive en la raíz al mismo nivel que todo lo activo, lo cual estorba a la jerarquía nueva |
| `prompts` | Log crudo de prompts fundacionales del proyecto. Los pendientes que contenía ("SEGUIR EXPLICACION") ya fueron revisados y cerrados (ver `docs/tracking/done.md`, sección Transversal) |

## 5. Casos que requirieron decisión (no eran solo reordenar)

### `docs/done.md` — duplicado activo de `docs/tracking/done.md` (resuelto)

Encontré **dos archivos `done.md` distintos**, ambos con commits recientes:

- `docs/tracking/done.md` (68 KB) — el histórico completo, con secciones X0–X4, Transversal, etc.
- `docs/done.md` (3.6 KB) — contenía *solo* ítems recientes (X5_macro_brain, X1, X5_P1, X5_P2) que
  **no estaban** en `docs/tracking/done.md`. Es decir, no era basura: tenía registros que el otro no tenía.

Origen probable: en jun-19 (`8623c882`) `docs/done.md` se movió a `docs/tracking/done.md` como
parte de una reestructuración anterior. En algún momento posterior, una sesión volvió a escribir
en `docs/done.md` (ruta vieja) en vez de `docs/tracking/done.md` — probablemente porque leyó una
ubicación desactualizada.

**Resolución**: se fusionó el contenido de `docs/done.md` dentro de `docs/tracking/done.md`
(4 ítems, ver commit) y se eliminó `docs/done.md`.

### `algoritmos.tex` / `algoritmos.pdf` — documento mixto (X4 + X5 original)

Un solo documento LaTeX cubre tanto X4 (vigente) como "X5 — Cerebro macro" (X5 original). No se
puede clasificar entero en un bucket sin partirlo. Propuesta: dejarlo en `docs/plans/` (no
moverlo a `Otros/`) porque su sección de X4 sigue siendo válida, dejando una nota de que la
sección de X5 describe la implementación original y quedará desactualizada si `X5_alt` la
reemplaza más adelante.

### `X5_revision_exhaustiva_cerebro.md` y `X5_alternativo.md` — no son "X5 original"

Aunque llevan "X5" en el nombre, ambos son trabajo conceptual **vigente** (el primero, editado
hoy, es una revisión de la función objetivo y arquitectura de X5 como concepto; el segundo es el
plan activo de `X5_alt`). Ninguno describe la implementación de `X5_macro_brain.py`, así que no
califican para `Otros/` bajo el criterio de §2.

### `X4_backtester.py` importa `X5_macro_brain` y `x5_demo` en tiempo de ejecución (resuelto)

Verificado en el código: `X4_backtester.py` hacía `import x5_demo` a nivel de módulo, y dentro de
`_seleccionar_params_x5`/`_aplicar_seleccion_x5` hacía `import X5_macro_brain as X5` — el modo
`X4 --x5` (recolección de datos + selección de parámetros exploit) depende en tiempo de ejecución
de `X5_macro_brain.py`.

Esto no cambia la clasificación de `X4_backtester.py` (sigue siendo vigente: también se usa para
backtesting general de X0, sin `--x5`). Se agregó `Otros/scripts/` al `sys.path` de
`X4_backtester.py` para que ambos imports sigan resolviendo tras el movimiento — detalle completo
en §8.

### Pendientes de `X5_macro_brain.py` en `docs/tracking/todos.md`

La sección "X5 — X5_macro_brain.py" de `todos.md` sigue teniendo ítems sin marcar (revisar
performance del modelo, actualizar `x5_plan.md`, etc.). Mover el código a `Otros/` no cierra esos
ítems — si se retoma X5 original más adelante, el código vuelve a `scripts/` y esos TO DOs siguen
vigentes desde donde quedaron.

## 6. Qué NO cambia

- `Data/`, `Data_minuto/`, `resources/`, `config/active_parameters.json`: generados, fuera de git,
  se mantienen donde están (los escribe Windows).
- `.claude/`: configuración de Claude Code, no es parte del contenido del proyecto.
- `docs/context/decisiones.md`, `docs/tracking/records.md`: bitácoras históricas fechadas — no se
  reescriben con las rutas nuevas (mismo criterio que ya tenían entradas viejas apuntando a rutas
  pre-restructuración de jun-19).

## 7. Pasos ejecutados

1. Reconciliado `docs/done.md` → `docs/tracking/done.md` (4 ítems fusionados) y eliminado el duplicado.
2. Creada `Otros/` con la estructura de §3; movidos con `git mv` los archivos versionados de §4 y con
   `mv` `Alginvesting_base/` (no versionado).
3. `.gitignore`: `Alginvesting_base/` → `Otros/Alginvesting_base/`; eliminada la entrada legada `scripts/Otros`.
4. Actualizados `CLAUDE.md` (tabla de scripts, sección nueva "Otros/", referencia base) y `README.md`
   (tabla de módulos, árbol de directorios, link a `guia_git_v2.md`) y los links de `docs/tracking/todos.md`
   hacia `Otros/docs/plans/...`.
5. Ajustados los imports/rutas de `X4_backtester.py` (ver §8) para que el modo `--x5` siga funcionando.

## 8. Rutas hardcodeadas corregidas (encontradas al ejecutar, no estaban en la propuesta original)

Mover archivos con dependencias por ruta relativa (`Path(__file__).parent...`) requirió ajustar,
además de lo previsto en el §5 original:

| Archivo | Antes | Después | Por qué |
|---|---|---|---|
| `scripts/X4_backtester.py` | `sys.path` solo incluía su propio dir | + `Otros/scripts/` | para que `import x5_demo` y el `import X5_macro_brain` (lazy) seguido resuelvan |
| `scripts/X4_backtester.py` (`_cargar_config_x5`) | `Path(__file__).parent / 'config_x5_default.py'` | `Path(__file__).parent.parent / 'Otros/scripts/config_x5_default.py'` | el archivo se movió, `X4_backtester.py` no |
| `Otros/scripts/X5_macro_brain.py` (x2, líneas ~1395/1560) | `Path(__file__).parent / 'X4_backtester.py'` | `Path(__file__).parent.parent.parent / 'scripts/X4_backtester.py'` | invocan `X4_backtester.py` como subproceso; ese script se quedó en `scripts/`, no se movió con `X5_macro_brain.py` |
| `Otros/scripts/config_x5_default.py` | `BASE_DIR = Path(__file__).parent.parent` | `...parent.parent.parent` | el archivo bajó un nivel más de profundidad (`scripts/` → `Otros/scripts/`); sin este fix, `CARPETA_DATA`/`resources/x5` habrían apuntado dentro de `Otros/` |
| `Otros/scripts/X5_analisis_exploratorio.ipynb` (celda de imports) | fallback `Path(__file__).resolve().parent` | fallback `Path.cwd().resolve().parent.parent / 'scripts'` | `__file__` no existe de forma confiable en un kernel Jupyter; el fallback asumía (correctamente, antes) que el notebook vivía junto a `config.py` |

Verificado en el entorno conda `revenAI` (`/opt/anaconda3/envs/revenAI/bin/python3`): `import X4_backtester`,
`import X5_macro_brain`, `X4_backtester._cargar_config_x5()` y la resolución de `SCRIPTS_DIR` del notebook
resuelven a las rutas correctas (`scripts/config.py`, `Otros/scripts/config_x5_default.py`, `Data/`,
`resources/`) sin depender de MT5 (su import es lazy, dentro de funciones — no bloquea en Mac).
