#!/usr/bin/env sh
# Generate self-signed TLS certificates for Loom Nginx reverse proxy
set -eu

CERT_DIR="${1:-/etc/nginx/certs}"
mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_DIR/tls.crt" ] || [ ! -f "$CERT_DIR/tls.key" ]; then
    echo "Generating self-signed TLS certificate in $CERT_DIR..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$CERT_DIR/tls.key" \
        -out "$CERT_DIR/tls.crt" \
        -subj "/C=US/ST=State/L=City/O=Loom/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,DNS:nginx,IP:127.0.0.1"
    chmod 600 "$CERT_DIR/tls.key"
    chmod 644 "$CERT_DIR/tls.crt"
    echo "Certificate generated successfully."
else
    echo "TLS certificate already exists in $CERT_DIR."
fi
