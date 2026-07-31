# Tipografias de este perfil

Los archivos `.ttf` viajan **dentro del perfil**, y `skin.yaml` los referencia
por ruta de archivo (`fonts/DejaVuSans-Bold.ttf`), nunca por nombre de familia.

Motivo: una fuente instalada en Windows no existe en `python:3.12-slim`. Si el
skin dijera `familia: "Arial Bold"`, Pillow no fallaria: caeria en silencio a
la fuente por defecto y el render saldria mal sin un solo mensaje de error.

## Incluidas

| Archivo | Familia | Licencia |
|---|---|---|
| `DejaVuSans-Bold.ttf` | DejaVu Sans Bold | Licencia DejaVu (derivada de Bitstream Vera), libre para uso y redistribucion |
| `DejaVuSans.ttf` | DejaVu Sans | idem |

## Cambiar la tipografia

1. Copia el `.ttf` u `.otf` a esta carpeta.
2. Apunta `tipografia.titular.archivo` en `skin.yaml` al nombre nuevo.
3. `thumbforge doctor --perfil aviacion_historica` confirma que Pillow la abre.
