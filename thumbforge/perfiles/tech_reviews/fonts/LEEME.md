# Tipografias de este perfil

Los archivos `.ttf` viajan **dentro del perfil**, y `skin.yaml` los referencia
por ruta de archivo (`fonts/DejaVuSans-Bold.ttf`), nunca por nombre de familia.
Una fuente instalada en Windows no existe en `python:3.12-slim`, y Pillow no
avisa: cae a la default y arruina el render.

## Incluidas

| Archivo | Familia | Licencia |
|---|---|---|
| `DejaVuSans-Bold.ttf` | DejaVu Sans Bold | Licencia DejaVu (derivada de Bitstream Vera), libre |
| `DejaVuSansMono-Bold.ttf` | DejaVu Sans Mono Bold | idem |

## Cambiar la tipografia

1. Copia el `.ttf` u `.otf` a esta carpeta.
2. Apunta `tipografia.titular.archivo` en `skin.yaml` al nombre nuevo.
3. `thumbforge doctor --perfil tech_reviews` confirma que Pillow la abre.
