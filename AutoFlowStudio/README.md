# ⚡ AutoFlow Studio

Extensión de navegador (Manifest V3) que convierte **Google Flow**
(`labs.google/fx/tools/flow`) en una **máquina de generación por lotes**:
pega muchos prompts y la extensión los envía uno por uno, espera el
resultado, lo descarga y sigue con el siguiente — con cola en vivo,
reintentos, delays anti rate-limit y auto-descarga.

Es una **implementación propia y desde cero**, inspirada en la categoría de
herramientas tipo *VEO Automation / Auto Flow*. No incluye ni reutiliza el
código de ninguna extensión de terceros: automatiza Google Flow (una web
pública) mediante técnicas estándar de extensiones.

---

## ✨ Funcionalidades

| Área | Qué hace |
|------|----------|
| **Modos** | Texto→Video, Frame→Video, Ingredientes→Video, Texto→Imagen, Imagen→Imagen |
| **Entrada por lotes** | Pega prompts separados por **línea en blanco**, o importa `.txt` / `.csv` / `.tsv` |
| **Cola en vivo** | Estados `En espera → Generando → Descargando → Completado / Fallido` |
| **Reintentos** | 0–20 intentos automáticos con backoff exponencial |
| **Delays** | Rango aleatorio (ms) entre envíos para evitar *rate-limit* |
| **Concurrencia** | 1–6 trabajos a la vez |
| **Auto-descarga** | Video 720p/1080p/4K/GIF · Imagen 1K/2K/4K, con subcarpeta por proyecto y prefijo de nombre |
| **Modelos** | Video: Veo 3.1 Lite/Fast/Quality, Omni Flash · Imagen: Nano Banana 2 / Pro / 2 Lite |
| **Anti "Unusual Activity"** | Detecta el aviso y aplica un enfriamiento antes de reintentar |
| **UI** | Panel flotante arrastrable y redimensible, tema claro/oscuro, i18n (es/en), log en vivo |
| **Pausa / Reanudar / Detener** | Control total del lote sin perder la cola |

---

## 📦 Instalación (cargar sin empaquetar)

### Microsoft Edge
1. Abre `edge://extensions/`.
2. Activa **Modo de desarrollador** (abajo a la izquierda).
3. Clic en **Cargar desempaquetada**.
4. Selecciona la carpeta `AutoFlowStudio/`.
5. Fija el icono ⚡ en la barra si quieres acceso rápido.

### Google Chrome / Brave
Igual pero en `chrome://extensions/` → **Cargar descomprimida**.

> Para que la **auto-descarga** funcione sin diálogos, desactiva
> *"Preguntar dónde guardar cada archivo antes de descargarlo"* en los
> ajustes de descargas del navegador.

---

## 🚀 Uso

1. Entra a un **proyecto** de Google Flow (`.../tools/flow/project/...`).
2. Aparece el panel flotante **⚡ AutoFlow Studio** arriba a la derecha.
3. Elige el **modo** (pestañas), pega tus prompts (uno por bloque, separados
   por una línea en blanco) o **Importar archivo**.
4. **➕ Agregar a la cola** → **▶ Iniciar**.
5. Observa la cola y el log. Usa **⏸ Pausar** / **⏹ Detener** cuando quieras.

Ajusta modelo, duración, relación de aspecto, resolución, delays, reintentos,
etc. en **⚙ Ajustes** (se guardan solos).

---

## 🔧 Ajuste de selectores (paso de 5 minutos)

Como el HTML de Google Flow está ofuscado y cambia entre versiones, la capa
de automatización vive aislada en **`lib/flow-adapter.js`**, en el objeto
`SELECTORS`. Usa varias estrategias (texto visible, `aria-label`,
`placeholder`, `data-testid`, CSS) para no ser frágil.

Si algún clic no funciona tras un cambio de Google:

1. En Flow, abre **F12 → Inspeccionar** el botón/campo que falla.
2. Copia su texto, `aria-label` o una clase estable.
3. Añádelo al patrón correspondiente en `SELECTORS` (o pásalo por
   `settings.selectorsOverride` sin tocar el código).

No hace falta tocar nada más: el resto del motor es agnóstico del DOM.

---

## 🧪 Pruebas

```bash
npm install          # instala jsdom + playwright (sin descargar navegadores)
npm test             # unitarias + integración (jsdom, sin navegador)
npm run test:unit    # solo lógica pura (parsers, motor de cola)
npm run test:e2e     # Playwright + Chromium real (correr en tu máquina)
```

- **`test/unit.test.cjs`** — 23 pruebas de la lógica pura (parser de prompts,
  CSV, motor de cola con concurrencia/reintentos/stop, helpers del adaptador).
- **`test/integration.test.mjs`** — 20 pruebas con **jsdom**: carga los
  scripts reales de la extensión contra un DOM que imita Flow y verifica el
  montaje del panel, la cola, la automatización del adaptador (escribe prompt,
  genera, descarga) y el popup.
- **`test/e2e.mjs`** — prueba **end-to-end con navegador real** (Playwright).
  Carga la extensión de verdad e intercepta `labs.google` con una página mock.
  Requiere poder lanzar Chromium, así que **córrela en tu equipo**, no en
  entornos que bloqueen el navegador.

---

## 🏗️ Arquitectura

```
AutoFlowStudio/
├─ manifest.json            # MV3: permisos, content scripts, background, popup
├─ background/
│  └─ service-worker.js     # descargas (chrome.downloads) + click confiable (debugger)
├─ content/
│  ├─ inject.js             # monta el panel flotante y orquesta todo
│  └─ panel.css             # estilos del panel (prefijo .afs)
├─ lib/                     # lógica pura y reutilizable (UMD: navegador + node)
│  ├─ prompt-parser.js      # texto → lista de prompts
│  ├─ csv-parser.js         # CSV/TSV sin dependencias
│  ├─ queue-engine.js       # cola: concurrencia, reintentos, delays, pausa/stop
│  ├─ flow-adapter.js       # 🔑 automatización del DOM de Google Flow (SELECTORS)
│  ├─ store.js              # ajustes + chrome.storage (fallback en memoria)
│  └─ i18n.js               # traducciones (es/en)
├─ popup/                   # popup de la barra del navegador
├─ icons/                   # iconos generados (rayo ⚡)
└─ test/                    # unit (node) + integración (jsdom) + e2e (playwright)
```

**Flujo:** `inject.js` construye la UI y el `QueueEngine`; por cada job el
motor llama a `FlowAdapter.processJob()`, que escribe el prompt, pulsa
*Generar*, espera el resultado en el DOM, extrae su URL y pide a
`service-worker.js` que lo descargue con `chrome.downloads`.

---

## ⚠️ Notas honestas

- Los **selectores de Google Flow** son la única parte que depende de la
  versión viva de la web; si Google cambia la interfaz, ajústalos en
  `flow-adapter.js` (ver arriba). Todo lo demás es estable y testeado.
- La extensión **solo actúa en `labs.google`** (declarado en `host_permissions`).
- No envía datos a ningún servidor: la configuración vive en `chrome.storage`
  local del navegador.

## 📄 Licencia

MIT.
