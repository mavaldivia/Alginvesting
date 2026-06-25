# Guía Git — Flujo Mac → GitHub → Windows

## Principio base

**Mac**: desarrollo y versionado del código.  
**Windows**: ejecución. Nunca hace commit ni push.  
**GitHub**: intermediario de una sola dirección (Mac → GitHub → Windows).

Las carpetas `Data/`, `Data_minuto/` y `resources/` son **exclusivas de Windows** — están en `.gitignore` y git nunca las toca en ningún lado.

---

## Flujo detallado

### En Mac (después de cambios)

1. Verificar qué cambió:
   ```bash
   git status
   git diff
   ```

2. Stagear:
   ```bash
   git add -A
   ```

3. Commitear:
   ```bash
   git commit -m "descripción del cambio"
   ```

4. Pushear a la rama activa:
   ```bash
   git push origin dev      # durante desarrollo
   git push origin master   # para producción en Windows
   ```

### En Windows (para actualizar al estado de GitHub)

El objetivo es una **copia exacta** del repo remoto, sin tocar `Data/`, `Data_minuto/` ni `resources/`.

```bash
git fetch origin
git reset --hard origin/master
```

`git reset --hard` reemplaza todo el código local con el estado de GitHub. Las carpetas en `.gitignore` (`Data/`, `Data_minuto/`, `resources/`) **no son afectadas** — git las ignora completamente.

> Si se trabaja desde `dev` antes de pasar a producción, usar `origin/dev` en vez de `origin/master`.

---

## Qué NO hacer en Windows

- No ejecutar `git add`, `git commit` ni `git push`.
- No ejecutar `git clean -fd` — eliminaría `Data/` y `resources/` aunque estén en gitignore si nunca fueron committed.
- No modificar archivos `.py` directamente en Windows.

---

## Qué está en git y qué no

| Carpeta / Archivo | ¿En git? | ¿Quién la actualiza? |
|---|---|---|
| `scripts/` | Sí | Mac |
| `docs/` | Sí | Mac |
| `CLAUDE.md`, `config.py`, etc. | Sí | Mac |
| `Data/` | No (.gitignore) | Windows (X0) |
| `Data_minuto/` | No (.gitignore) | Windows (X0) |
| `resources/` | No (.gitignore) | Windows (X0, X1, X2) |

---

## Resumen (Windows)

```bash
git fetch origin
git reset --hard origin/master
```

Eso es todo. `Data/`, `Data_minuto/` y `resources/` quedan intactas.
