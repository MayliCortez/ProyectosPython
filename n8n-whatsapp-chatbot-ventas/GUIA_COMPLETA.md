# Chatbot WhatsApp con IA para Ventas de Mentorias

Chatbot inteligente que responde WhatsApp automaticamente usando n8n + Evolution API + Claude AI. Disenado para vender mentorias y membresías de comunidad mientras estas en live o ocupada.

---

## Que hace este bot

- Responde mensajes de WhatsApp automaticamente con IA
- Usa tecnicas de venta: empatia, espejo emocional, cierre suave
- NO responde a contactos bloqueados (papa, mama, novio)
- NO responde en grupos
- Suena natural, NO como robot
- Publica estados de WhatsApp automaticamente
- Configurable con un solo archivo JSON

---

## Requisitos

- Una computadora con Docker instalado
- Cuenta de WhatsApp (la que usas normalmente)
- API Key de Anthropic (Claude) - obtener en: https://console.anthropic.com
- Conexion a internet

---

## Instalacion paso a paso

### Paso 1: Instalar Docker

Si no tienes Docker:
- **Windows**: https://docs.docker.com/desktop/install/windows-install/
- **Mac**: https://docs.docker.com/desktop/install/mac-install/
- **Linux**: `curl -fsSL https://get.docker.com | sh`

### Paso 2: Levantar los servicios

Abre terminal en la carpeta del proyecto y ejecuta:

```bash
docker compose up -d
```

Esto levanta:
- **n8n** en http://localhost:5678 (motor de automatizacion)
- **Evolution API** en http://localhost:8080 (conexion WhatsApp)
- **PostgreSQL** (base de datos)
- **Redis** (cache)

### Paso 3: Configurar Evolution API

1. Abre http://localhost:8080/manager
2. Usa la API Key: `tu_api_key_segura_cambiar` (cambiala en docker-compose.yml)
3. Crea una nueva instancia (nombre: `mi-whatsapp`)
4. Te mostrara un **codigo QR**
5. Abre WhatsApp en tu celular > Dispositivos vinculados > Vincular dispositivo
6. Escanea el QR
7. Configura el webhook:
   - URL: `http://n8n-chatbot:5678/webhook/whatsapp-webhook`
   - Eventos: `MESSAGES_UPSERT`

### Paso 4: Configurar n8n

1. Abre http://localhost:5678
2. Crea tu cuenta de n8n (primera vez)
3. Ve a **Workflows > Import from File**
4. Importa `workflows/chatbot_whatsapp_ventas.json`
5. Importa `workflows/publicar_estados.json` (opcional)

### Paso 5: Configurar credenciales en n8n

En el workflow importado, necesitas configurar:

**Para Claude AI (nodo "Claude AI - Generar Respuesta"):**
- En el nodo HTTP Request, cambia el header `x-api-key` por tu API key de Anthropic

**Para Evolution API (nodo "Enviar Respuesta WhatsApp"):**
- Cambia la URL con el nombre de tu instancia
- Cambia el header `apikey` por tu API key de Evolution

### Paso 6: Activar el workflow

Click en el toggle de activacion (esquina superior derecha del workflow).

---

## Como modificar el bot facilmente

### Cambiar productos/precios

En el nodo **"Preparar Prompt de Ventas"**, busca la seccion `productos` y modifica:

```javascript
productos: [
  {
    nombre: 'Mentoria Individual 1:1',
    precio: '$97 USD',
    descripcion: 'Tu descripcion aqui',
    beneficios: 'Beneficio 1, beneficio 2, etc'
  },
  // Agrega mas productos aqui
],
```

### Agregar una promocion

En el mismo nodo, cambia:

```javascript
promocionActiva: true,
promocion: {
  nombre: 'Black Friday',
  descuento: '50% de descuento',
  codigo: 'BLACK50',
  fechaFin: '30 de noviembre',
  mensaje: 'Aprovecha el 50% de descuento solo esta semana'
},
```

Para desactivar la promo: cambia `promocionActiva` a `false`.

### Bloquear contactos

En el nodo **"Procesar Mensaje"**, modifica el array:

```javascript
const contactosBloqueados = [
  '521234567890',  // Papa
  '521234567891',  // Mama
  '521234567892'   // Novio
];
```

Formato: codigo de pais + numero, sin + ni espacios.

### Agregar instrucciones extras

En el nodo **"Preparar Prompt de Ventas"**:

```javascript
instruccionesExtra: 'Esta semana estamos promocionando el curso de redes. Si preguntan por eso, decir que abre el lunes con precio de lanzamiento de $47.'
```

### Cambiar el tono del bot

Modifica el `systemPrompt` en el nodo **"Preparar Prompt de Ventas"**. La seccion PERSONALIDAD controla como habla.

### Cambiar los estados automaticos

En el workflow de estados, nodo **"Seleccionar Estado"**, modifica el array `estados`:

```javascript
const estados = [
  'Tu primer estado aqui',
  'Tu segundo estado aqui',
  // Agrega todos los que quieras
];
```

### Cambiar horarios de estados

En el nodo **"Horarios de Estados"**, modifica las horas del schedule trigger.

---

## Cambiar el modelo de IA

En el nodo **"Claude AI - Generar Respuesta"**, cambia el campo `model` en el body JSON:

| Modelo | Velocidad | Calidad | Costo |
|--------|-----------|---------|-------|
| `claude-haiku-4-5-20251001` | Muy rapida | Buena | Bajo |
| `claude-sonnet-4-20250514` | Rapida | Muy buena | Medio |
| `claude-opus-4-20250918` | Normal | Excelente | Alto |

Para usar **OpenAI** en lugar de Claude, cambia la URL del nodo HTTP Request a `https://api.openai.com/v1/chat/completions` y ajusta el body al formato de OpenAI.

---

## Estructura del proyecto

```
n8n-whatsapp-chatbot-ventas/
├── docker-compose.yml              # Servicios (n8n, Evolution API, DB)
├── GUIA_COMPLETA.md                # Esta guia
├── config/
│   ├── bot_config.json             # Configuracion del bot (referencia)
│   └── prompt_ventas.md            # Prompt completo de ventas (referencia)
├── workflows/
│   ├── chatbot_whatsapp_ventas.json  # Workflow principal del chatbot
│   └── publicar_estados.json        # Workflow de estados automaticos
└── scripts/
    └── setup.sh                    # Script de instalacion automatica
```

---

## Solucion de problemas

**El bot no responde:**
1. Verifica que el workflow esta activo en n8n
2. Revisa que WhatsApp esta conectado en Evolution API
3. Revisa los logs: `docker compose logs -f n8n`

**Responde en grupos:**
- Verifica que el nodo "Filtrar Grupos" esta conectado correctamente

**Responde a contactos bloqueados:**
- Verifica que los numeros estan bien escritos en el nodo "Procesar Mensaje"
- Formato correcto: solo numeros, sin +, sin espacios

**Error de IA:**
- Verifica tu API key de Anthropic
- Revisa que tienes credito disponible en tu cuenta

**WhatsApp se desconecta:**
- Es normal que se desconecte ocasionalmente
- Ve a Evolution API manager y reconecta escaneando QR

---

## Costos estimados

- **Evolution API**: Gratis (self-hosted)
- **n8n**: Gratis (self-hosted)
- **Claude AI**: ~$0.003-0.015 por mensaje (depende del modelo)
  - Con Haiku: ~300 mensajes por $1 USD
  - Con Sonnet: ~100 mensajes por $1 USD

---

## Seguridad

- Cambia las passwords por defecto en `docker-compose.yml`
- Cambia la API Key de Evolution API
- No compartas tu API key de Anthropic
- Los datos de conversacion se guardan localmente en tu computadora
