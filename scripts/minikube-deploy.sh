#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
NAMESPACE="${NAMESPACE:-cert-control-plane}"
MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-minikube}"
IMAGE="${IMAGE:-cert-control-plane-app:minikube}"
LOCAL_PORT="${LOCAL_PORT:-18080}"
SECRET_NAME="cert-control-plane-secrets"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

random_hex() {
  openssl rand -hex 32
}

random_fernet_key() {
  python3 - <<'PY'
import base64
import os

print(base64.urlsafe_b64encode(os.urandom(32)).decode())
PY
}

require_cmd kubectl
require_cmd minikube
require_cmd docker
require_cmd openssl
require_cmd python3
require_cmd curl

if ! minikube -p "${MINIKUBE_PROFILE}" status >/dev/null 2>&1; then
  echo "[1/6] minikube profile ${MINIKUBE_PROFILE} is not running; starting minikube"
  minikube -p "${MINIKUBE_PROFILE}" start
else
  echo "[1/6] minikube profile ${MINIKUBE_PROFILE} is running"
fi

echo "[2/6] building app image in minikube: ${IMAGE}"
eval "$(minikube -p "${MINIKUBE_PROFILE}" docker-env)"
docker build \
  -t "${IMAGE}" \
  -f "${ROOT_DIR}/server/Dockerfile" \
  "${ROOT_DIR}/server"

echo "[3/6] applying namespace"
kubectl apply -f "${ROOT_DIR}/k8s/minikube/namespace.yaml"

if kubectl -n "${NAMESPACE}" get secret "${SECRET_NAME}" >/dev/null 2>&1; then
  echo "[4/6] reusing existing secret ${SECRET_NAME}"
else
  echo "[4/6] creating local-only secret ${SECRET_NAME}"
  ADMIN_API_KEY_VALUE="${ADMIN_API_KEY:-$(random_hex)}"
  CA_KEY_ENCRYPTION_KEY_VALUE="${CA_KEY_ENCRYPTION_KEY:-$(random_fernet_key)}"
  POSTGRES_PASSWORD_VALUE="${POSTGRES_PASSWORD:-$(openssl rand -hex 16)}"

  kubectl -n "${NAMESPACE}" create secret generic "${SECRET_NAME}" \
    --from-literal=ADMIN_API_KEY="${ADMIN_API_KEY_VALUE}" \
    --from-literal=CA_KEY_ENCRYPTION_KEY="${CA_KEY_ENCRYPTION_KEY_VALUE}" \
    --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD_VALUE}"

  echo "created local-only secret ${SECRET_NAME}"
  echo "read the generated Admin API Key with:"
  echo "  kubectl -n ${NAMESPACE} get secret ${SECRET_NAME} -o jsonpath='{.data.ADMIN_API_KEY}' | base64 -d && echo"
fi

echo "[5/6] applying Kubernetes manifests"
kubectl apply -k "${ROOT_DIR}/k8s/minikube"
kubectl -n "${NAMESPACE}" set image deployment/cert-control-plane app="${IMAGE}"
kubectl -n "${NAMESPACE}" rollout restart deployment/cert-control-plane

echo "[6/6] waiting for rollouts"
kubectl -n "${NAMESPACE}" rollout status deployment/cert-control-plane-db --timeout=180s
kubectl -n "${NAMESPACE}" rollout status deployment/cert-control-plane --timeout=240s

echo "verifying health through temporary port-forward on localhost:${LOCAL_PORT}"
TMP_LOG="$(mktemp -t certcp-minikube-port-forward.XXXXXX.log)"
kubectl -n "${NAMESPACE}" port-forward svc/cert-control-plane "${LOCAL_PORT}:8080" >"${TMP_LOG}" 2>&1 &
PF_PID="$!"
cleanup() {
  kill "${PF_PID}" >/dev/null 2>&1 || true
  rm -f "${TMP_LOG}"
}
trap cleanup EXIT

for attempt in $(seq 1 60); do
  if HEALTH_RESPONSE="$(curl -fsS "http://127.0.0.1:${LOCAL_PORT}/healthz" 2>/dev/null)"; then
    echo "${HEALTH_RESPONSE}"
    echo
    break
  fi
  if [ "${attempt}" -eq 60 ]; then
    echo "health check failed; port-forward log:" >&2
    cat "${TMP_LOG}" >&2 || true
    exit 1
  fi
  sleep 1
done

echo
echo "minikube deployment is ready."
echo "Open a local tunnel:"
echo "  kubectl -n ${NAMESPACE} port-forward svc/cert-control-plane ${LOCAL_PORT}:8080"
echo "Dashboard:"
echo "  http://localhost:${LOCAL_PORT}/dashboard"
echo "Read Admin API Key:"
echo "  kubectl -n ${NAMESPACE} get secret ${SECRET_NAME} -o jsonpath='{.data.ADMIN_API_KEY}' | base64 -d && echo"
