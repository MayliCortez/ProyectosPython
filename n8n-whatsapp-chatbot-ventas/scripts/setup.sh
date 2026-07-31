#!/bin/bash

# ============================================
# Script de instalacion - Chatbot WhatsApp n8n
# ============================================

set -e

echo "============================================"
echo "  Chatbot WhatsApp con n8n - Instalacion"
echo "============================================"
echo ""

# Verificar Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker no esta instalado."
    echo "Instala Docker desde: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose no esta instalado."
    exit 1
fi

echo "[1/4] Levantando servicios con Docker..."
docker compose up -d

echo ""
echo "[2/4] Esperando a que los servicios inicien..."
sleep 15

echo ""
echo "[3/4] Verificando servicios..."

# Verificar n8n
if curl -s -o /dev/null -w "%{http_code}" http://localhost:5678 | grep -q "200\|301\|302"; then
    echo "  n8n: OK (http://localhost:5678)"
else
    echo "  n8n: Iniciando... espera unos segundos mas"
fi

# Verificar Evolution API
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 | grep -q "200\|301"; then
    echo "  Evolution API: OK (http://localhost:8080)"
else
    echo "  Evolution API: Iniciando... espera unos segundos mas"
fi

echo ""
echo "[4/4] Listo!"
echo ""
echo "============================================"
echo "  SIGUIENTE PASO: Configuracion"
echo "============================================"
echo ""
echo "1. Abre n8n en tu navegador:"
echo "   http://localhost:5678"
echo "   Usuario: admin"
echo "   Password: CambiameYA2024"
echo ""
echo "2. Abre Evolution API Manager:"
echo "   http://localhost:8080/manager"
echo "   API Key: tu_api_key_segura_cambiar"
echo ""
echo "3. En Evolution API:"
echo "   - Crea una instancia nueva"
echo "   - Escanea el QR con tu WhatsApp"
echo "   - Configura el webhook apuntando a:"
echo "     http://n8n-chatbot:5678/webhook/whatsapp-webhook"
echo ""
echo "4. En n8n:"
echo "   - Importa el workflow desde:"
echo "     workflows/chatbot_whatsapp_ventas.json"
echo "   - Importa tambien (opcional):"
echo "     workflows/publicar_estados.json"
echo "   - Configura las credenciales"
echo "   - Activa los workflows"
echo ""
echo "5. Edita la configuracion en:"
echo "   config/bot_config.json"
echo ""
echo "============================================"
