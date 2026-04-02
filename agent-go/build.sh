#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT_DIR="${ROOT_DIR}/dist"
TARGETOS="${TARGETOS:-linux}"
TARGETARCH="${TARGETARCH:-amd64}"

mkdir -p "${OUT_DIR}"

docker build \
  -f "${ROOT_DIR}/agent-go/Dockerfile" \
  --build-arg TARGETOS="${TARGETOS}" \
  --build-arg TARGETARCH="${TARGETARCH}" \
  --output "type=local,dest=${OUT_DIR}" \
  "${ROOT_DIR}"

echo "built ${OUT_DIR}/cert-agent"
