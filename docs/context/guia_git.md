# Guía Git: Mac → Windows

## El problema

`resources/` y `Data_minuto/` están en `.gitignore` — git nunca los toca. Sin problema.

`Data/` **sí está trackeado en git**. Si haces `git pull` en Windows sin configuración previa, git sobrescribirá los CSV con la versión de Mac (que puede ser más antigua), perdiendo las actualizaciones que X0 ha corrido en Windows.

La solución es marcar los archivos de `Data/` con `--skip-worktree` en el clon de Windows: git los ignora al hacer pull, dejándolos intactos.

---

## Setup inicial (solo una vez en Windows)

Después de clonar el repo (`git clone ...`), ejecutar desde la raíz del proyecto:

```bash
git update-index --skip-worktree Data/AAPL.csv
git update-index --skip-worktree Data/AMZN.csv
git update-index --skip-worktree Data/BTCUSD.csv
git update-index --skip-worktree Data/ETHUSD.csv
git update-index --skip-worktree Data/GOOGL.csv
git update-index --skip-worktree Data/META.csv
git update-index --skip-worktree Data/MSFT.csv
git update-index --skip-worktree Data/NFLX.csv
git update-index --skip-worktree Data/NVDA.csv
git update-index --skip-worktree Data/TSLA.csv
```

O en una sola línea (PowerShell):

```powershell
Get-ChildItem Data\*.csv | ForEach-Object { git update-index --skip-worktree $_.FullName }
```

O en Git Bash / cmd:

```bash
for f in Data/*.csv; do git update-index --skip-worktree "$f"; done
```

Verificar que quedó bien:

```bash
git ls-files -v Data/ | grep "^S"
# Cada línea debe empezar con "S" (skip-worktree activo)
```

---

## Workflow normal (Mac → Windows)

**En Mac** (desarrollo):

```bash
git add -A
git commit -m "descripción del cambio"
git push
```

**En Windows** (antes de correr X0/X1):

```bash
git pull
```

`Data/`, `Data_minuto/` y `resources/` quedan intactos. El resto (scripts, docs, config) se actualiza.

---

## Si se agrega un activo nuevo a Data/

Cuando Mac agrega un CSV nuevo (ej. `Data/SPY.csv`) y lo sube:

1. `git pull` en Windows lo descarga normalmente (es un archivo nuevo, no existía antes).
2. Marcar el nuevo archivo para que futuros pulls no lo pisen:

```bash
git update-index --skip-worktree Data/SPY.csv
```

---

## Si quieres forzar actualizar Data/ desde Mac (caso excepcional)

```bash
# Quitar skip-worktree
git update-index --no-skip-worktree Data/BTCUSD.csv  # o todos los que corresponda

# Stash cambios locales si los hay
git stash

# Pull
git pull

# Volver a activar skip-worktree
git update-index --skip-worktree Data/BTCUSD.csv
```

---

## Resumen rápido

| Carpeta | Mecanismo | Efecto en git pull |
|---|---|---|
| `resources/` | `.gitignore` | git no la ve; nunca se toca (incluye conjuntos_N, x0, x2, x3) |
| `Data_minuto/` | `.gitignore` | git no la ve; nunca se toca |
| `Data/` | `--skip-worktree` (solo Windows) | git la ve pero no la modifica |
| Todo lo demás | trackeado normalmente | se actualiza con pull |

---

## Notas

- `--skip-worktree` vive en `.git/index` del clon local — no se propaga a otros clones ni aparece en GitHub. Hay que aplicarlo una sola vez por máquina.
- Si hay un conflicto grave (git pull se queja de que Data/ tiene cambios locales), el stash antes del pull lo resuelve.
