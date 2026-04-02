#!/bin/sh
set -eu

CERT_DIR="/etc/nginx/certs"
CERT_PATH="${CERT_DIR}/api.example.com.crt"
KEY_PATH="${CERT_DIR}/api.example.com.key"
CHAIN_PATH="${CERT_DIR}/api.example.com.chain.crt"
EDGE_AGENT_CMD="${EDGE_AGENT_CMD:-python -m agent}"

mkdir -p "${CERT_DIR}" /var/lib/cert-agent

if [ ! -f "${CERT_PATH}" ] || [ ! -f "${KEY_PATH}" ]; then
  openssl req -x509 -nodes -newkey rsa:2048 \
    -subj "/CN=bootstrap.local" \
    -days 1 \
    -keyout "${KEY_PATH}" \
    -out "${CERT_PATH}" >/dev/null 2>&1
fi

if [ ! -f "${CHAIN_PATH}" ]; then
  : > "${CHAIN_PATH}"
fi

nginx
exec sh -lc "${EDGE_AGENT_CMD}"
