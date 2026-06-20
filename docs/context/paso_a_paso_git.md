# Paso a paso: Git en Windows (solo pull)

En Windows solo se hace `git pull`. Nunca push. El desarrollo ocurre en Mac.

---

## Primera vez (setup inicial)

### 1. Clonar el repo

```powershell
git clone https://github.com/mavaldivia/Alginvesting.git
cd Alginvesting
```

Si ya está clonado, saltar al paso 2.

### 2. Marcar Data/ para que git pull no la pise

`Data/` está trackeada en git, pero en Windows X0 la actualiza con velas nuevas. Hay que decirle a git que ignore los cambios locales en esos archivos:

```powershell
Get-ChildItem Data\*.csv | ForEach-Object { git update-index --skip-worktree $_.FullName }
```

Verificar que quedó bien (todas deben mostrar `S` al inicio):

```powershell
git ls-files -v Data/
```

Esto se hace **una sola vez** por máquina. El flag vive en `.git/index` local — no afecta a Mac ni a GitHub.

### 3. Verificar qué carpetas son seguras

| Carpeta | Estado | ¿git pull la toca? |
|---|---|---|
| `Data/` | Trackeada + skip-worktree | No — protegida por skip-worktree |
| `Data_minuto/` | Gitignoreada | No — git no la ve |
| `resources/` | Gitignoreada | No — git no la ve |
| `scripts/`, `docs/`, `config.py`, etc. | Trackeados normalmente | Sí — se actualizan |

---

## Cada vez que quieras actualizar el código

```powershell
git pull origin dev
```

Listo. `Data/`, `Data_minuto/` y `resources/` quedan exactamente como estaban.

---

## Si Mac agrega un CSV nuevo a Data/ (nuevo activo)

Después del `git pull` que lo descarga por primera vez, marcarlo también:

```powershell
git update-index --skip-worktree Data\NUEVO_ACTIVO.csv
```

---

## Si git pull se queja de conflicto en Data/

Ocurre si skip-worktree no estaba activo y hay diferencias locales:

```powershell
# 1. Guardar cambios locales
git stash

# 2. Pull
git pull origin dev

# 3. Restaurar Data/ local (descartar la versión de Mac)
git checkout stash -- Data/

# 4. Volver al estado limpio
git stash drop

# 5. Activar skip-worktree para evitar que se repita
Get-ChildItem Data\*.csv | ForEach-Object { git update-index --skip-worktree $_.FullName }
```
