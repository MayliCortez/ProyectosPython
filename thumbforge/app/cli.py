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


def cmd_corpus(args: argparse.Namespace) -> int:
    """Descarga y anota el corpus del perfil.

    Dos pasos en un solo comando porque ese es el orden natural: se
    recolectan los videos y despues se anotan las miniaturas. `--refrescar`
    pisa la cache, `--limite` acota para probar rapido.
    """
    from .cache import Cache
    from .modulos import anotador, recolector

    perfil = mod_perfiles.cargar_perfil(args.perfil)
    cache = Cache()

    try:
        r = recolector.recolectar(perfil, cache, refrescar=args.refrescar,
                                   limite=args.limite)
    except ErrorThumbforge as exc:
        print(f"M1: {exc}", file=sys.stderr)
        return 2
    print(tabla.titulo("M1 recolector"))
    print(f"videos: {r.escritos} escritos, {r.ids_encontrados} encontrados, "
          f"{r.descartados_shorts} shorts, {r.descartados_recientes} recientes, "
          f"{r.llamadas_red} llamadas de red, {r.fuentes} fuentes")
    print(f"archivo: {r.archivo}")
    for a in (r.avisos or [])[:5]:
        print(f"  aviso: {a}")

    if args.solo == "recolectar":
        return 0

    try:
        a = anotador.anotar(perfil, cache, refrescar=args.refrescar,
                            limite=args.limite)
    except ErrorThumbforge as exc:
        print(f"M2: {exc}", file=sys.stderr)
        return 2
    print(tabla.titulo("M2 anotador"))
    print(f"anotaciones: {a.anotados} anotadas, {a.reutilizados} reusadas, "
          f"{a.desde_cache} desde cache, {a.fallidos} con error, "
          f"{a.sin_miniatura} sin miniatura, {a.llamadas_red} llamadas de red")
    print(f"archivo: {a.archivo}")
    return 0


def cmd_reglas(args: argparse.Namespace) -> int:
    """Genera perfiles/<slug>/corpus/reglas.md a partir del corpus anotado."""
    from .modulos import patrones

    perfil = mod_perfiles.cargar_perfil(args.perfil)
    try:
        informe = patrones.analizar(perfil)
    except ErrorThumbforge as exc:
        print(f"M3: {exc}", file=sys.stderr)
        return 2
    ruta = patrones.escribir_reglas(informe)
    print(f"reglas escritas: {ruta}")

    reglas = informe.reglas_activas()
    corpus = len(informe.corpus.reglas) if informe.corpus else 0
    ctr = len(informe.ctr.reglas) if informe.ctr else 0
    print(f"{len(reglas)} regla(s) activa(s): {ctr} del CTR propio, "
          f"{corpus} del corpus ajeno.")
    if informe.conflictos:
        print(f"{len(informe.conflictos)} conflicto(s) entre las dos fuentes: "
              f"revisa la seccion de conflictos en {ruta.name}.")
    for aviso in (informe.avisos or [])[:5]:
        print(f"  aviso: {aviso}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Guion -> 3 miniaturas + QA.

    Con --conceptos se saltea M4 y se parte de un brief ya escrito: es el
    camino que no necesita claves de API y el que permite auditar el render
    sin gastar una llamada.
    """
    from .cache import Cache
    from .modulos import qa as mod_qa
    from .modulos import render as mod_render

    perfil = mod_perfiles.cargar_perfil(args.perfil)
    cache = Cache()
    salida = rutas.dir_salida()

    if args.conceptos and args.guion:
        print("Elegi uno: --conceptos (brief ya hecho, sin llamadas al modelo) "
              "o --guion (arma el brief con M4, necesita clave de LLM).",
              file=sys.stderr)
        return 2

    if args.conceptos:
        datos = json.loads(Path(args.conceptos).read_text("utf-8"))
        conceptos = datos if isinstance(datos, list) else datos.get("conceptos", [datos])
    elif args.guion:
        from .modulos import brief as mod_brief
        try:
            guion_texto = Path(args.guion).read_text("utf-8")
        except OSError as exc:
            print(f"No pude leer {args.guion}: {exc}", file=sys.stderr)
            return 2
        try:
            resultado = mod_brief.generar_conceptos(
                perfil, guion_texto, cache,
                titulo=args.titulo, nombre_guion=Path(args.guion).name)
        except ErrorThumbforge as exc:
            print(f"M4: {exc}", file=sys.stderr)
            return 2
        conceptos = resultado.conceptos
        for a in getattr(resultado, "avisos", []) or []:
            print(f"M4: {a}")
        for r in getattr(resultado, "rechazados", []) or []:
            cid = r.get("id") if isinstance(r, dict) else getattr(r, "concepto_id", "?")
            print(f"M4 descarto {cid}: {r}")
    else:
        print("Necesito --guion (con clave de LLM) o --conceptos (brief ya hecho). "
              "Sin uno de los dos no hay que renderizar.", file=sys.stderr)
        return 2

    imagenes = [Path(p) for p in (args.imagen or [])]
    if imagenes and len(imagenes) not in (1, len(conceptos)):
        print(f"Pasaste {len(imagenes)} imagen(es) para {len(conceptos)} conceptos: "
              f"tiene que ser una sola (se usa para todos) o una por concepto.",
              file=sys.stderr)
        return 2

    resultados, fallidos = [], []
    for i, concepto in enumerate(conceptos):
        base = None
        if imagenes:
            base = imagenes[0] if len(imagenes) == 1 else imagenes[i]
        try:
            resultados.append(mod_render.renderizar(concepto, perfil, cache,
                                                    imagen_local=base, salida=salida))
        except ErrorThumbforge as exc:
            fallidos.append((concepto.get("id", f"#{i}"), str(exc)))

    if fallidos:
        print(tabla.titulo("Conceptos rechazados"))
        for cid, motivo in fallidos:
            print(f"{cid}:\n{motivo}\n")
    if not resultados:
        print("Ningun concepto llego a render.", file=sys.stderr)
        return 1

    filas = [[r.concepto_id, r.ruta.name, f"{r.bytes:,}", str(r.calidad),
              r.eleccion.nombre, r.decision_texto.color] for r in resultados]
    print(tabla.titulo("Miniaturas"))
    print(tabla.tabla(["Concepto", "Archivo", "Bytes", "Calidad", "Ancla", "Color"], filas))

    informe = mod_qa.revisar(resultados, perfil)
    ruta_qa = mod_qa.escribir_qa(informe)
    ruta_creditos = mod_render.escribir_creditos(
        [a for r in resultados for a in r.atribuciones])
    ruta_brief = salida / f"{perfil.slug}_brief.json"
    ruta_brief.write_text(json.dumps(conceptos, ensure_ascii=False, indent=2), "utf-8")

    print(tabla.titulo("QA"))
    filas = [[v.concepto_id, tabla.OK if v.ok else tabla.ERROR,
              f"{v.contraste_p5:.2f}:1", f"{v.legibilidad.puntaje:.2f}",
              str(len(v.hallazgos))] for v in informe.variantes]
    print(tabla.tabla(["Concepto", "Estado", "Contraste p5", "Legibilidad", "Hallazgos"],
                      filas))
    for v in informe.variantes:
        for h in v.hallazgos:
            print(f"  {v.concepto_id}: {h}")
    for par in informe.pares:
        if par.demasiado_parecidas:
            print(f"  {par.a} y {par.b} son demasiado parecidas: {par.motivo}")

    print(f"\nEn {salida}:")
    for r in resultados:
        print(f"  {r.ruta.name}")
    for p in (ruta_brief, ruta_qa, ruta_creditos):
        print(f"  {p.name}")

    if informe.a_reemplazar():
        print(f"\nM4 tiene que reemplazar: {', '.join(informe.a_reemplazar())}")
    return 0 if informe.ok else 1


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
    r.add_argument("--guion", help="Guion en Markdown (necesita M4 y claves de API)")
    r.add_argument("--conceptos",
                   help="Brief ya hecho en JSON: saltea M4 y no toca la red")
    r.add_argument("--imagen", action="append",
                   help="Base visual local. Una sola para todos los conceptos, "
                        "o repetir el flag una vez por concepto")
    r.add_argument("--titulo", help="Titulo del video, para el control "
                                     "no_duplicar_titulo del perfil (usar con --guion)")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("corpus", help="Recolecta y anota el corpus del perfil")
    c.add_argument("--perfil", required=True)
    c.add_argument("--refrescar", action="store_true",
                   help="Ignora la cache y vuelve a pedir todo")
    c.add_argument("--limite", type=int,
                   help="Acota los videos a los N de mayor outlier_score")
    c.add_argument("--solo", choices=["recolectar", "anotar"], default=None,
                   help="Corre solo uno de los dos pasos")
    c.set_defaults(func=cmd_corpus)

    g = sub.add_parser("reglas", help="Genera corpus/reglas.md a partir del corpus")
    g.add_argument("--perfil", required=True)
    g.set_defaults(func=cmd_reglas)

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
