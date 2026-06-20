# Guía Git: Mac → Windows

## Cómo está configurado

`Data/`, `Data_minuto/` y `resources/` están en `.gitignore`: git no los trackea en ninguna máquina. Esto garantiza que:

- X0 puede modificar `Data/` y `resources/` en Windows sin que git lo detecte.
- Un `git pull` en Windows nunca sobreescribirá esas carpetas.
- Mac y Windows pueden tener contenidos distintos en esas carpetas — Windows siempre tiene prioridad sobre su propio contenido.

Solo se sincronizan vía git los archivos de código y documentación (`scripts/`, `docs/`, `CLAUDE.md`, etc.).

---

## Resumen

| Carpeta | Mecanismo | Efecto en git pull |
|---|---|---|
| `Data/` | `.gitignore` | git no la ve; nunca se toca |
| `Data_minuto/` | `.gitignore` | git no la ve; nunca se toca |
| `resources/` | `.gitignore` | git no la ve; nunca se toca |
| `scripts/`, `docs/`, configs | Trackeados | Se actualizan con pull |

---

## Notas

- No se necesita `--skip-worktree` ni ninguna configuración especial en Windows.
- Mac no tiene MT5, así que nunca generará contenido en `Data/` ni `resources/`. No hay riesgo de conflicto.
- Para el paso a paso operacional, ver [`paso_a_paso_git.md`](paso_a_paso_git.md).
