# Tipografias de este perfil

Los archivos `.ttf` viajan **dentro del perfil**, y `skin.yaml` los referencia
por ruta de archivo (`fonts/LiberationSans-Bold.ttf`), nunca por nombre de
familia. Una fuente instalada en Windows no existe en `python:3.12-slim`, y
Pillow no avisa: cae a la default y arruina el render.

## Incluidas

| Archivo | Familia | Licencia |
|---|---|---|
| `LiberationSans-Bold.ttf` | Liberation Sans Bold | SIL Open Font License 1.1 |
| `LiberationSans-Regular.ttf` | Liberation Sans | SIL Open Font License 1.1 |

## Cambiar la tipografia

1. Copia el `.ttf` u `.otf` a esta carpeta.
2. Apunta `tipografia.titular.archivo` en `skin.yaml` al nombre nuevo.
3. `thumbforge doctor --perfil true_crime` confirma que Pillow la abre.
