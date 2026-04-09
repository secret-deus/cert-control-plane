#!/bin/sh
set -eu

AGENT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT_DIR="${AGENT_DIR}/dist"
TARGETOS="${TARGETOS:-linux}"
TARGETARCH="${TARGETARCH:-amd64}"

mkdir -p "${OUT_DIR}"

docker build \
  -f "${AGENT_DIR}/Dockerfile" \
  --build-arg TARGETOS="${TARGETOS}" \
  --build-arg TARGETARCH="${TARGETARCH}" \
  --output "type=local,dest=${OUT_DIR}" \
  "${AGENT_DIR}"

echo "built ${OUT_DIR}/cert-agent"
