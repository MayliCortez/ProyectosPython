# ProyectosPython

Este repositorio contiene varios proyectos en Python que resuelven distintos problemas. Cada proyecto tiene su propio propósito y estructura. A continuación, se describe brevemente cada uno de ellos.

## Proyectos

### 1. **CalculadoraEstadisticas**
Este proyecto incluye una calculadora para realizar cálculos estadísticos básicos sobre un conjunto de datos. El script `calculadora_estadisticas.py` permite a los usuarios obtener estadísticas como la media, mediana, desviación estándar, entre otros.

- **Archivos:**
  - `calculadora_estadisticas.py`: Script principal con la implementación de la calculadora.
  - `README.md`: Documentación específica del proyecto.

### 2. **CalculadoraPromediosCSV**
Este proyecto permite calcular promedios de calificaciones a partir de un archivo CSV. El script `calculadora_promedios_csv.py` lee las calificaciones desde un archivo CSV llamado `calificaciones.csv` y calcula el promedio de cada estudiante.

- **Archivos:**
  - `calculadora_promedios_csv.py`: Script para calcular los promedios de los estudiantes.
  - `calificaciones.csv`: Archivo CSV que contiene las calificaciones de los estudiantes.
  - `README.md`: Documentación específica del proyecto.

### 3. **n8n-docker**
Setup completo de **n8n Community Edition** (gratuito) con Docker Compose y PostgreSQL. Permite levantar una instancia local de n8n para crear automatizaciones y workflows.

- **Archivos:**
  - `docker-compose.yml`: Definición de servicios (n8n + PostgreSQL).
  - `.env.example`: Plantilla de variables de entorno.
  - `local-files/`: Carpeta compartida con n8n para leer/escribir archivos.
  - `README.md`: Instrucciones completas de uso.

## Requisitos

Para ejecutar estos proyectos, necesitas tener Python instalado en tu sistema. Además, algunos proyectos pueden requerir librerías adicionales que se pueden instalar utilizando `pip`.

## Instalación

1. Clona este repositorio en tu máquina local:
   ```bash
   git clone https://github.com/MayliCortez/ProyectosPython.git
   ```

2. Navega a la carpeta del proyecto que deseas ejecutar:
   ```bash
   cd ProyectosPython/CalculadoraEstadisticas
   ```
   o
   ```bash
   cd ProyectosPython/CalculadoraPromediosCSV
   ```

3. Ejecuta el script Python correspondiente:
   ```bash
   python calculadora_estadisticas.py
   ```
   o
   ```bash
   python calculadora_promedios_csv.py
   ```

## Contribuciones

Si deseas contribuir a este proyecto, por favor abre un *pull request* con tus sugerencias o mejoras. Asegúrate de seguir las buenas prácticas de codificación y de realizar pruebas antes de enviar tus cambios.

## Licencia

Este proyecto está bajo la Licencia MIT. Puedes ver más detalles en el archivo `LICENSE`.
```

