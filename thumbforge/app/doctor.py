"""`thumbforge doctor`.

El comando que decide si compartir esto es viable. Sin el, cada instalacion
nueva en otra maquina es una sesion de depuracion a ciegas.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import perfiles as mod_perfiles
from . import proveedores as mod_proveedores
from . import rutas, tabla
from .errores import ErrorPerfil

MIN_LIBRE_GB = 1.0


@dataclass
class Chequeo:
    seccion: str
    item: str
    estado: str          # OK | AVISO | ERROR
    detalle: str = ""
    # Hallazgos sueltos: se listan uno por linea en el resumen, sin unirlos
    # en una sola cadena que despues haya que volver a partir.
    detalles: list[str] = field(default_factory=list)


@dataclass
class Reporte:
    chequeos: list[Chequeo] = field(default_factory=list)

    def add(self, seccion: str, item: str, estado: str, detalle: str = "",
            detalles: list[str] | None = None) -> None:
        self.chequeos.append(Chequeo(seccion, item, estado, detalle, list(detalles or [])))

    @property
    def errores(self) -> list[Chequeo]:
        return [c for c in self.chequeos if c.estado == tabla.ERROR]

    @property
    def avisos(self) -> list[Chequeo]:
        return [c for c in self.chequeos if c.estado == tabla.AVISO]

    def secciones(self) -> list[str]:
        vistas: list[str] = []
        for c in self.chequeos:
            if c.seccion not in vistas:
                vistas.append(c.seccion)
        return vistas


# --- secciones ---------------------------------------------------------------
def _chequear_entorno(rep: Reporte) -> None:
    py = platform.python_version()
    estado = tabla.OK if sys.version_info >= (3, 12) else tabla.AVISO
    rep.add("Entorno", "Python", estado, f"{py} ({platform.python_implementation()})")

    maquina = platform.machine()
    arq = {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        maquina, maquina)
    soportada = arq in ("amd64", "arm64")
    rep.add("Entorno", "Arquitectura", tabla.OK if soportada else tabla.AVISO,
            f"{arq} ({maquina}) - la imagen se publica para amd64 y arm64")

    rep.add("Entorno", "Sistema", tabla.OK, f"{platform.system()} {platform.release()}")

    en_contenedor = Path("/.dockerenv").exists() or os.environ.get("TF_EN_CONTENEDOR") == "1"
    rep.add("Entorno", "Contexto", tabla.OK,
            "dentro de contenedor" if en_contenedor else "host (fuera de contenedor)")

    try:
        from PIL import Image, features  # noqa: F401
        import PIL

        detalle = f"Pillow {PIL.__version__}"
        # Nombres tal como los registra PIL.features: 'freetype2' es el modulo,
        # 'jpg' y 'zlib' son codecs. Sin freetype2 no hay texto en el render.
        requeridos = ("jpg", "zlib", "freetype2")
        faltantes = [c for c in requeridos if not features.check(c)]
        if faltantes:
            rep.add("Entorno", "Pillow", tabla.ERROR,
                    f"{detalle} sin soporte para {', '.join(faltantes)}")
        else:
            rep.add("Entorno", "Pillow", tabla.OK, f"{detalle} con {', '.join(requeridos)}")
    except Exception as exc:  # noqa: BLE001
        rep.add("Entorno", "Pillow", tabla.ERROR, f"no importa: {exc}")

    if en_contenedor:
        try:
            rep.add("Entorno", "Usuario", tabla.OK,
                    f"uid={os.getuid()} gid={os.getgid()} - "
                    f"los archivos de ./salida salen con este dueno")
        except AttributeError:  # pragma: no cover - Windows
            pass


def _chequear_volumenes(rep: Reporte) -> None:
    for nombre in rutas.VOLUMENES:
        ruta = rutas.dir_volumen(nombre)
        if not ruta.exists():
            try:
                ruta.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                rep.add("Volumenes", nombre, tabla.ERROR, f"no existe y no se puede crear: {exc}")
                continue

        if not ruta.is_dir():
            rep.add("Volumenes", nombre, tabla.ERROR, f"{ruta} existe pero no es un directorio")
            continue

        prueba = ruta / ".thumbforge_escritura"
        try:
            prueba.write_text("ok", encoding="utf-8")
            prueba.unlink()
        except OSError as exc:
            rep.add("Volumenes", nombre, tabla.ERROR,
                    f"{ruta} no acepta escritura ({exc.strerror or exc}). "
                    f"En Docker suele ser UID/GID: revisa 'user:' en compose.yaml")
            continue

        try:
            uso = shutil.disk_usage(ruta)
            libre_gb = uso.free / 1024 ** 3
            estado = tabla.OK if libre_gb >= MIN_LIBRE_GB else tabla.AVISO
            detalle = f"{ruta} - escritura ok, {libre_gb:.1f} GB libres"
        except OSError:
            estado, detalle = tabla.OK, f"{ruta} - escritura ok"
        rep.add("Volumenes", nombre, estado, detalle)


def _chequear_proveedores(rep: Reporte, con_red: bool) -> None:
    for prov in mod_proveedores.PROVEEDORES:
        etiqueta = f"{prov.nombre}"
        if not prov.configurado():
            rep.add("Proveedores", etiqueta, tabla.AVISO,
                    f"falta {prov.var_entorno} en .env - sin esto no corre: {prov.usos}")
            continue

        ok_formato, detalle_formato = prov.formato_plausible()
        if not ok_formato:
            rep.add("Proveedores", etiqueta, tabla.ERROR,
                    f"{prov.var_entorno}: {detalle_formato}")
            continue

        if not con_red:
            sin_clave = "sin clave requerida" if not prov.requiere_clave else detalle_formato
            rep.add("Proveedores", etiqueta, tabla.OK, f"{sin_clave}; llamada de prueba omitida")
            continue

        ok_ping, detalle_ping = prov.ping()
        if ok_ping:
            rep.add("Proveedores", etiqueta, tabla.OK, detalle_ping)
        elif prov.requiere_clave:
            # Hay clave y con formato valido: si falla, el problema es la
            # credencial o la habilitacion de la API. Eso si bloquea.
            rep.add("Proveedores", etiqueta, tabla.ERROR,
                    f"la clave existe pero la llamada de prueba fallo: {detalle_ping}")
        else:
            # Fuente sin clave: un fallo aca es alcanzabilidad (red, proxy,
            # bloqueo del proveedor), no configuracion rota. No frena a doctor.
            rep.add("Proveedores", etiqueta, tabla.AVISO,
                    f"no se pudo alcanzar: {detalle_ping} - revisa red o proxy salientes")


def _chequear_perfiles(rep: Reporte, solo: str | None = None) -> None:
    base = rutas.dir_perfiles()
    encontrados = mod_perfiles.listar_perfiles(base)

    if not encontrados:
        rep.add("Perfiles", "(ninguno)", tabla.ERROR,
                f"no hay carpetas con perfil.yaml en {base}")
        return

    for ruta in encontrados:
        if solo and mod_perfiles.normalizar(ruta.name) != mod_perfiles.normalizar(solo):
            continue
        try:
            perfil = mod_perfiles.cargar_perfil_en(ruta)
        except ErrorPerfil as exc:
            rep.add("Perfiles", ruta.name, tabla.ERROR, str(exc))
            continue

        problemas = perfil.validar()
        peor = tabla.OK
        detalles: list[str] = []
        for p in problemas:
            if p.nivel == tabla.ERROR:
                peor = tabla.ERROR
            elif p.nivel == tabla.AVISO and peor != tabla.ERROR:
                peor = tabla.AVISO
            if p.nivel != tabla.OK:
                detalles.append(p.detalle)

        if peor == tabla.OK:
            fuentes = perfil.fuentes_declaradas()
            rep.add("Perfiles", perfil.slug, peor,
                    f"{perfil.nombre} - {len(fuentes)} tipografia(s) cargables, "
                    f"copy max {perfil.get('copy.max_palabras')} palabras")
        else:
            rep.add("Perfiles", perfil.slug, peor,
                    f"{len(detalles)} problema(s): {detalles[0]}", detalles=detalles)


# --- ejecucion ---------------------------------------------------------------
def ejecutar(con_red: bool = True, perfil: str | None = None) -> Reporte:
    rep = Reporte()
    _chequear_entorno(rep)
    _chequear_volumenes(rep)
    _chequear_proveedores(rep, con_red)
    _chequear_perfiles(rep, perfil)
    return rep


ANCHO_DETALLE = 92


def _una_linea(texto: str, limite: int | None = None) -> str:
    """Aplana saltos de linea (los errores de YAML traen varios) y recorta.
    El texto completo siempre se imprime abajo, en el resumen."""
    plano = " | ".join(p.strip() for p in texto.splitlines() if p.strip())
    if limite and len(plano) > limite:
        return plano[: limite - 1] + "…"
    return plano


def imprimir(rep: Reporte, formato_json: bool = False) -> None:
    if formato_json:
        print(json.dumps(
            {"chequeos": [c.__dict__ for c in rep.chequeos],
             "errores": len(rep.errores), "avisos": len(rep.avisos)},
            ensure_ascii=False, indent=2))
        return

    for seccion in rep.secciones():
        filas = [[c.item, c.estado, _una_linea(c.detalle, ANCHO_DETALLE)]
                 for c in rep.chequeos if c.seccion == seccion]
        print(tabla.titulo(seccion))
        print(tabla.tabla(["Item", "Estado", "Detalle"], filas))

    print()
    if rep.errores:
        print(f"{len(rep.errores)} error(es) que impiden trabajar:")
        for c in rep.errores:
            if c.detalles:
                print(f"  - {c.seccion}/{c.item}:")
                for detalle in c.detalles:
                    print(f"      {_una_linea(detalle)}")
            else:
                print(f"  - {c.seccion}/{c.item}: {_una_linea(c.detalle)}")
    if rep.avisos:
        print(f"{len(rep.avisos)} aviso(s):")
        for c in rep.avisos:
            print(f"  - {c.seccion}/{c.item}: {_una_linea(c.detalle)}")
    if not rep.errores and not rep.avisos:
        print("Todo en orden.")


def codigo_salida(rep: Reporte) -> int:
    return 1 if rep.errores else 0
