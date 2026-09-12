# Paso a paso: Git Mac ↔ Windows

El desarrollo ocurre en **Mac**. Windows solo recibe cambios (`git pull`), nunca hace push.

`Data/`, `Data_minuto/` y `resources/` están en `.gitignore`: git nunca las ve ni las toca, en ninguna máquina. Windows siempre conserva su contenido local sin importar qué tenga Mac.

---

## Primera vez en Windows

```powershell
git clone https://github.com/mavaldivia/Alginvesting.git
cd Alginvesting
```

Eso es todo. No hay configuración adicional.

---

## Flujo normal

### Mac — desarrollo y push

```bash
# Desarrollar en Claude Code...
git add scripts/config.py docs/tracking/todos.md  # archivos específicos
git commit -m "descripción del cambio"
git push origin dev
```

### Windows — recibir cambios antes de ejecutar X0/X1

```powershell
git pull origin dev
```

`Data/`, `Data_minuto/` y `resources/` quedan intactos. Solo se actualizan scripts, docs y config.

---

## Qué se actualiza con git pull

| Carpeta / archivo | Estado | ¿git pull lo toca? |
|---|---|---|
| `Data/` | Gitignoreada | No |
| `Data_minuto/` | Gitignoreada | No |
| `resources/` | Gitignoreada | No |
| `scripts/*.py` | Trackeado | Sí — se actualiza |
| `docs/` | Trackeado | Sí — se actualiza |
| `config.py`, `CLAUDE.md`, `.gitignore` | Trackeados | Sí — se actualizan |

---

## Ejecución de scripts

| Script | Dónde corre |
|---|---|
| `X0_data_supports.py` | **Windows** (requiere MT5) |
| `X1_trading.py` | **Windows** (requiere MT5) |
| `X2_fundamentals.py` | **Windows** (llamado por X0) |
| `X3_technical_features.py` | **Windows** (llamado por X0) |
| Desarrollo, refactors, docs | **Mac** (Claude Code) |
