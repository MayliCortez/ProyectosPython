"""CLI de thumbforge.

    thumbforge run      --perfil gdc --guion guiones/ep08.md
    thumbforge corpus   --perfil gdc --refrescar
    thumbforge reglas   --perfil gdc
    thumbforge doctor
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import doctor as mod_doctor
from . import perfiles as mod_perfiles
from . import politicas, rutas, tabla
from .errores import ErrorThumbforge

VERSION = "0.1.0"


def _cargar_env() -> None:
    """Lee .env sin pisar variables ya presentes en el entorno."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    for candidato in (rutas.RAIZ_APP / ".env", Path.cwd() / ".env"):
        if candidato.is_file():
            load_dotenv(candidato, override=False)


# --- comandos ----------------------------------------------------------------
def cmd_doctor(args: argparse.Namespace) -> int:
    con_red = not (args.sin_red or args.quiet)
    rep = mod_doctor.ejecutar(con_red=con_red, perfil=args.perfil)
    codigo = mod_doctor.codigo_salida(rep)

    if args.quiet:
        if codigo:
            print(f"doctor: {len(rep.errores)} error(es)", file=sys.stderr)
        return codigo

    mod_doctor.imprimir(rep, formato_json=args.json)
    return codigo


def cmd_perfiles(args: argparse.Namespace) -> int:
    perfiles = mod_perfiles.cargar_todos()
    if not perfiles:
        print(f"No hay perfiles en {rutas.dir_perfiles()}.")
        return 1

    filas = []
    for p in perfiles:
        orden = ", ".join(p.get("politica_base_visual.orden_preferencia") or [])
        filas.append([
            p.slug,
            ", ".join(p.alias) or "-",
            p.nombre,
            str(p.get("copy.max_palabras")),
            "si" if p.get("personas_reales.generar_con_ia") else "no",
            orden,
        ])
    print(tabla.tabla(
        ["Perfil", "Alias", "Nombre", "Copy max", "IA sobre personas", "Orden de base visual"],
        filas))

    if args.detalle:
        for p in perfiles:
            print(tabla.titulo(f"{p.slug} - politica completa"))
            print(politicas.politica_para_prompt(p))
            print(f"\ncampos_extra_anotacion: "
                  f"{', '.join(p.campos_extra_anotacion()) or '(ninguno)'}")
            fuentes = {rol: str(ruta.relative_to(p.raiz)) if ruta.is_relative_to(p.raiz) else str(ruta)
                       for rol, ruta in p.fuentes_declaradas().items()}
            print(f"tipografias: {json.dumps(fuentes, ensure_ascii=False)}")
    return 0


def cmd_politica(args: argparse.Namespace) -> int:
    """Evalua conceptos contra el perfil. Sirve para probar la abstraccion
    sin gastar una sola llamada de red."""
    perfil = mod_perfiles.cargar_perfil(args.perfil)

    texto = sys.stdin.read() if args.concepto == "-" else Path(args.concepto).read_text("utf-8")
    datos = json.loads(texto)
    conceptos = datos if isinstance(datos, list) else datos.get("conceptos", [datos])

    veredictos = politicas.evaluar_conceptos(conceptos, perfil, titulo=args.titulo)

    print(f"Perfil: {perfil.slug} ({perfil.nombre})")
    filas = [[v.concepto_id,
              tabla.OK if v.ok and not v.diferidas else (tabla.AVISO if v.ok else tabla.ERROR),
              f"{len(v.duras)} dura(s), {len(v.diferidas)} diferida(s)"]
             for v in veredictos]
    print(tabla.tabla(["Concepto", "Estado", "Violaciones"], filas))
    print()
    for v in veredictos:
        print(v.informe())
        print()
    return 0 if all(v.ok for v in veredictos) else 1


def _pendiente(paso: int, que: str):
    def _cmd(args: argparse.Namespace) -> int:
        print(f"'{que}' llega en el paso {paso} del orden de construccion.")
        print("Paso 1 entrega: esqueleto, sistema de perfiles y 'thumbforge doctor'.")
        return 3
    return _cmd


# --- parser ------------------------------------------------------------------
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="thumbforge",
        description="Motor de miniaturas multi-nicho. El motor no sabe nada del nicho: "
                    "todo lo especifico vive en perfiles/.",
    )
    p.add_argument("--version", action="version", version=f"thumbforge {VERSION}")
    sub = p.add_subparsers(dest="comando", required=True)

    d = sub.add_parser("doctor", help="Verifica claves, volumenes, perfiles y entorno")
    d.add_argument("--sin-red", action="store_true", help="Omite las llamadas de prueba")
    d.add_argument("--quiet", action="store_true",
                   help="Solo codigo de salida; implica --sin-red (lo usa el healthcheck)")
    d.add_argument("--json", action="store_true", help="Salida en JSON")
    d.add_argument("--perfil", help="Verifica solo este perfil")
    d.set_defaults(func=cmd_doctor)

    pl = sub.add_parser("perfiles", help="Lista los perfiles disponibles y su politica")
    pl.add_argument("--detalle", action="store_true", help="Vuelca la politica completa")
    pl.set_defaults(func=cmd_perfiles)

    po = sub.add_parser("politica",
                        help="Evalua conceptos JSON contra la politica de un perfil")
    po.add_argument("--perfil", required=True)
    po.add_argument("--concepto", required=True, help="Archivo JSON, o '-' para stdin")
    po.add_argument("--titulo", help="Titulo del video, para el control no_duplicar_titulo")
    po.set_defaults(func=cmd_politica)

    r = sub.add_parser("run", help="Guion -> 3 miniaturas + QA")
    r.add_argument("--perfil", required=True)
    r.add_argument("--guion", required=True)
    r.set_defaults(func=_pendiente(7, "run"))

    c = sub.add_parser("corpus", help="Recolecta y anota el corpus del perfil")
    c.add_argument("--perfil", required=True)
    c.add_argument("--refrescar", action="store_true")
    c.set_defaults(func=_pendiente(4, "corpus"))

    g = sub.add_parser("reglas", help="Genera corpus/reglas.md a partir del corpus")
    g.add_argument("--perfil", required=True)
    g.set_defaults(func=_pendiente(5, "reglas"))

    return p


def main(argv: list[str] | None = None) -> int:
    _cargar_env()
    args = construir_parser().parse_args(argv)
    try:
        return args.func(args)
    except ErrorThumbforge as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrumpido.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
