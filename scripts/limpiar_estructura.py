"""
Limpia carpetas que quedaron fuera de la arquitectura vigente del proyecto.

Contexto
--------
El repo se desarrolla en Mac y se ejecuta en Windows (ver CLAUDE.md). Windows
acumula carpetas que Mac ya no tiene: restos de reorganizaciones previas,
respaldos manuales, carpetas de una estructura antigua, etc. Este script
compara la estructura real de carpetas contra una "estructura válida" de
referencia (JSON) y ofrece borrar, una por una y con confirmación explícita,
las que sobran.

Cómo definir la estructura válida
----------------------------------
Archivo JSON con dos listas de rutas relativas a la raíz del proyecto
(separador '/', incluso en Windows):

  - "validas": carpetas que deben existir tal cual. Si una carpeta válida
    tiene hijos declarados en la lista (ej. "docs" y "docs/plans"), el
    script desciende a revisarlos. Si no tiene hijos declarados (ej.
    "scripts"), cualquier subcarpeta encontrada ahí se considera fuera de
    arquitectura.
  - "opacas": carpetas cuyo contenido es dinámico/generado (ej. Data/,
    resources/) y por lo tanto NUNCA se revisa por dentro ni se propone
    eliminar, sin importar lo que contengan.

Cualquier carpeta que no sea "valida", ni "opaca", ni un ancestro necesario
de una "valida" (ej. "docs" es ancestro de "docs/plans") se considera fuera
de la arquitectura vigente.

Por defecto se usa scripts/estructura_valida.json (junto a este script).
Editarlo ahí a medida que la arquitectura cambie.

Priorización jerárquica
------------------------
El recorrido es por niveles (BFS). En cuanto una carpeta se clasifica como
fuera de arquitectura, se agrega a la lista de candidatas y NO se sigue
bajando dentro de ella — así, si "A" completa sobra, se pregunta solo por
"A" y nunca por "A/B" o "A/C".

Cómo ejecutar
-------------
    python scripts/limpiar_estructura.py [--raiz RUTA] [--estructura ARCHIVO.json] [--dry-run]

  --raiz RUTA         Raíz del proyecto a revisar (default: directorio actual).
  --estructura RUTA   JSON de estructura válida (default: scripts/estructura_valida.json).
  --dry-run           Modo simulación: solo lista qué se eliminaría, no borra ni pregunta nada.

Confirmar o rechazar eliminaciones
------------------------------------
Sin --dry-run, por cada carpeta fuera de arquitectura se muestra su ruta
completa y un resumen (archivos, subcarpetas, tamaño) y se pregunta:

    [Y] eliminar  /  [N] conservar

"Y" borra la carpeta completa con todo su contenido (shutil.rmtree). "N" la
conserva y el script sigue con la siguiente candidata. No hay opción de
"eliminar todo sin confirmar" — cada carpeta se confirma individualmente.

Medidas de seguridad
----------------------
- Solo se opera sobre carpetas, nunca se borran archivos sueltos.
- Las carpetas "opacas" jamás se revisan ni se pueden proponer para borrar.
- Rutas del JSON con ".." o absolutas se rechazan al cargar (no se puede
  apuntar fuera del proyecto).
- Se ignoran symlinks al recorrer (no se sigue ni se borra a través de ellos).
- Carpetas de caché conocidas (__pycache__, .ipynb_checkpoints,
  .pytest_cache) y ".git" se ignoran siempre, no se preguntan ni se cuentan
  como fuera de arquitectura.
- --dry-run permite ver el resultado completo antes de borrar nada.
- Si no hay terminal interactiva para responder (EOF), se asume "N"
  (conservar) en vez de fallar o borrar por defecto.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

IGNORAR_SIEMPRE = {".git", "__pycache__", ".ipynb_checkpoints", ".pytest_cache"}


def _validar_rutas_relativas(rutas, campo):
    for r in rutas:
        p = Path(r)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(f"Ruta inválida en '{campo}' de la estructura: {r!r}")


def cargar_estructura(path: Path) -> tuple[set[str], set[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validas_raw = data.get("validas", [])
    opacas_raw = data.get("opacas", [])
    _validar_rutas_relativas(validas_raw, "validas")
    _validar_rutas_relativas(opacas_raw, "opacas")
    validas = {Path(p).as_posix() for p in validas_raw}
    opacas = {Path(p).as_posix() for p in opacas_raw}
    return validas, opacas


def _es_ancestro_de_valida(rel: str, validas: set[str]) -> bool:
    prefijo = rel + "/"
    return any(v.startswith(prefijo) for v in validas)


def clasificar(rel: str, validas: set[str], opacas: set[str]) -> str:
    if rel in opacas:
        return "opaca"
    if rel in validas or _es_ancestro_de_valida(rel, validas):
        return "seguir"
    return "invalida"


def recorrer(raiz: Path, validas: set[str], opacas: set[str]) -> list[Path]:
    invalidas = []
    pendientes = [raiz]
    while pendientes:
        actual = pendientes.pop(0)
        try:
            hijos = sorted(p for p in actual.iterdir() if p.is_dir() and not p.is_symlink())
        except PermissionError as e:
            print(f"  (sin permiso para leer {actual}: {e})", file=sys.stderr)
            continue
        for hijo in hijos:
            if hijo.name in IGNORAR_SIEMPRE:
                continue
            rel = hijo.relative_to(raiz).as_posix()
            estado = clasificar(rel, validas, opacas)
            if estado == "invalida":
                invalidas.append(hijo)
            elif estado == "seguir":
                pendientes.append(hijo)
    return invalidas


def resumir(path: Path) -> str:
    n_archivos = n_carpetas = tam = 0
    for p in path.rglob("*"):
        if p.is_file():
            n_archivos += 1
            try:
                tam += p.stat().st_size
            except OSError:
                pass
        elif p.is_dir():
            n_carpetas += 1
    return f"{n_archivos} archivo(s), {n_carpetas} subcarpeta(s), {tam / 1_048_576:.1f} MB"


def confirmar(path: Path) -> bool:
    print(f"\n¿Estás seguro de que deseas eliminar esta carpeta y todo su contenido?\n  {path}\n  ({resumir(path)})")
    while True:
        try:
            resp = input("  Presiona Y para eliminar o N para conservarla > ").strip().lower()
        except EOFError:
            print("  (sin entrada interactiva disponible, se conserva por defecto)")
            return False
        if resp in ("y", "s"):
            return True
        if resp == "n":
            return False
        print("  Respuesta no válida, usa Y o N.")


def main():
    parser = argparse.ArgumentParser(
        description="Limpia carpetas fuera de la arquitectura vigente del proyecto.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--raiz", default=".", help="Raíz del proyecto a revisar (default: directorio actual).")
    parser.add_argument(
        "--estructura",
        default=None,
        help="JSON de estructura válida (default: estructura_valida.json junto a este script).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo lista qué se eliminaría, sin preguntar ni borrar nada.",
    )
    args = parser.parse_args()

    raiz = Path(args.raiz).resolve()
    estructura_path = Path(args.estructura).resolve() if args.estructura else Path(__file__).with_name("estructura_valida.json")

    if raiz == raiz.anchor:
        print(f"La raíz indicada ({raiz}) es la raíz del sistema de archivos, abortando por seguridad.", file=sys.stderr)
        sys.exit(1)
    if not raiz.is_dir():
        print(f"La raíz indicada no existe o no es una carpeta: {raiz}", file=sys.stderr)
        sys.exit(1)
    if not estructura_path.exists():
        print(f"No se encontró el archivo de estructura válida: {estructura_path}", file=sys.stderr)
        sys.exit(1)

    validas, opacas = cargar_estructura(estructura_path)

    print(f"Raíz del proyecto: {raiz}")
    print(f"Estructura de referencia: {estructura_path}")
    print(f"Carpetas dinámicas (no se revisan por dentro): {', '.join(sorted(opacas)) or '(ninguna)'}")

    invalidas = recorrer(raiz, validas, opacas)

    if not invalidas:
        print("\nNo se encontraron carpetas fuera de la arquitectura vigente.")
        return

    print(f"\n{len(invalidas)} carpeta(s) fuera de la arquitectura vigente:")
    for p in invalidas:
        print(f"  - {p.relative_to(raiz)}")

    if args.dry_run:
        print("\n(modo simulación: no se eliminó nada)")
        return

    eliminadas, conservadas = [], []
    for p in invalidas:
        if confirmar(p):
            try:
                shutil.rmtree(p)
                eliminadas.append(p)
                print(f"  Eliminada: {p}")
            except OSError as e:
                print(f"  Error al eliminar {p}: {e}")
        else:
            conservadas.append(p)
            print(f"  Conservada: {p}")

    print(f"\nResumen: {len(eliminadas)} eliminada(s), {len(conservadas)} conservada(s).")


if __name__ == "__main__":
    main()
