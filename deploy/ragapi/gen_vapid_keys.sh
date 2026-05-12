#!/bin/bash

# Generador de claves VAPID para WebPush
# Requiere openssl
# Uso: ./generate_vapid_keys.sh

generate_vapid_keys() {
  # Crear carpeta temporal
  mkdir -p vapid_keys
  cd vapid_keys
  # Generar clave privada EC (prime256v1 es el estándar para VAPID)
  #openssl ecparam -name prime256v1 -genkey -noout -out vapid_private.pem 2>/dev/null

  # Extraer clave pública
  openssl ec -in vapid_private.pem -pubout -out vapid_public.pem 2>/dev/null

  # Convertir a formato base64 URL-safe (sin padding)
  PRIVATE_KEY=$(openssl ec -in vapid_private.pem -outform DER 2>/dev/null | tail -c +8 | head -c 32 | base64 | tr -d '=' | tr '+/' '-_')
  PUBLIC_KEY=$(openssl ec -in vapid_private.pem -pubout -outform DER 2>/dev/null | tail -c 65 | base64 | tr -d '=' | tr '+/' '-_' | tr -d '[:space:]')

  # Mostrar resultados
  echo "🔑 Claves VAPID generadas:"
  echo "----------------------------------------"
  echo "VAPID PUBLIC KEY:"
  echo $PUBLIC_KEY
  echo ""
  echo "VAPID PRIVATE KEY:"
  echo $PRIVATE_KEY
  echo "----------------------------------------"
  echo "ℹ️ Estas claves son compatibles con WebPush (RFC 8292)"
  echo "Guárdalas en un lugar seguro y NO compartas la clave privada"

  # Opcional: Guardar en archivo .env
  echo "VAPID_PUBLIC_KEY=$PUBLIC_KEY" >> .env
  echo "VAPID_PRIVATE_KEY=$PRIVATE_KEY" >> .env
  echo ""
  echo "✅ Las claves también se han guardado en el archivo .env"
}

# Verificar dependencias
if ! command -v openssl &> /dev/null; then
  echo "❌ Error: openssl no está instalado"
  echo "Instálalo con:"
  echo "  Ubuntu/Debian: sudo apt install openssl"
  echo "  macOS: brew install openssl"
  exit 1
fi

generate_vapid_keys