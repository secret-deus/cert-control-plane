#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:18080}"
ADMIN_API_KEY="${ADMIN_API_KEY:-}"
NAMESPACE="${NAMESPACE:-cert-control-plane-e2e}"
WORKDIR="${WORKDIR:-tmp/k8s-secret-e2e}"
SERVER_MODE="${SERVER_MODE:-host}"

if [[ -z "$ADMIN_API_KEY" ]]; then
  echo "ADMIN_API_KEY is required" >&2
  exit 1
fi

for cmd in kubectl minikube curl openssl python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

mkdir -p "$WORKDIR"

if ! minikube status >/dev/null 2>&1; then
  minikube start
fi

SA_KUBECONFIG="$WORKDIR/sa.kubeconfig"
NAMESPACE="$NAMESPACE" OUTPUT="$SA_KUBECONFIG" SERVER_MODE="$SERVER_MODE" \
  "$(dirname "$0")/minikube-create-sa-kubeconfig.sh" >/dev/null
kubectl -n "$NAMESPACE" delete secret new-tls replace-tls moved-tls --ignore-not-found >/dev/null

api_json() {
  local method="$1"
  local path="$2"
  local payload="${3:-}"
  if [[ $# -lt 3 && ! -t 0 ]]; then
    payload="$(cat)"
  fi
  if [[ -n "$payload" ]]; then
    curl -fsS -X "$method" "$CONTROL_PLANE_URL$path" \
      -H "X-Admin-API-Key: $ADMIN_API_KEY" \
      -H "Content-Type: application/json" \
      --data-binary "$payload"
  else
    curl -fsS -X "$method" "$CONTROL_PLANE_URL$path" \
      -H "X-Admin-API-Key: $ADMIN_API_KEY"
  fi
}

json_get() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

make_cert() {
  local cn="$1"
  local prefix="$2"
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$WORKDIR/${prefix}.key" \
    -out "$WORKDIR/${prefix}.crt" \
    -days 30 \
    -subj "/CN=${cn}" >/dev/null 2>&1
}

upload_cert() {
  local name="$1"
  local prefix="$2"
  python3 - "$name" "$WORKDIR/${prefix}.crt" "$WORKDIR/${prefix}.key" <<'PY' | api_json POST /api/control/external-certs
import json, sys
name, cert_path, key_path = sys.argv[1:]
print(json.dumps({
    "name": name,
    "description": "minikube k8s secret e2e",
    "cert_pem": open(cert_path, encoding="utf-8").read(),
    "key_pem": open(key_path, encoding="utf-8").read(),
    "chain_pem": None,
    "provider": "manual",
    "external_id": name,
}))
PY
}

create_cluster_payload() {
  python3 - "$SA_KUBECONFIG" "$NAMESPACE" <<'PY'
import json, sys
kubeconfig_path, namespace = sys.argv[1:]
print(json.dumps({
    "name": "minikube-e2e",
    "environment": "dev",
    "kubeconfig": open(kubeconfig_path, encoding="utf-8").read(),
    "default_namespace": namespace,
}))
PY
}

create_assignment_payload() {
  local cluster_id="$1"
  local cert_id="$2"
  local secret_name="$3"
  python3 - "$cluster_id" "$cert_id" "$NAMESPACE" "$secret_name" <<'PY'
import json, sys
cluster_id, cert_id, namespace, secret_name = sys.argv[1:]
print(json.dumps({
    "cluster_id": cluster_id,
    "namespace": namespace,
    "secret_name": secret_name,
    "external_cert_id": cert_id,
}))
PY
}

confirm_payload() {
  local dry_run_id="$1"
  python3 - "$dry_run_id" <<'PY'
import json, sys
print(json.dumps({"dry_run_id": sys.argv[1]}))
PY
}

secret_serial() {
  local secret_name="$1"
  kubectl -n "$NAMESPACE" get secret "$secret_name" -o jsonpath='{.data.tls\.crt}' \
    | python3 -c 'import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))' \
    | openssl x509 -noout -serial
}

echo "[1/8] Create cluster target"
CLUSTER_ID="$(create_cluster_payload | api_json POST /api/control/kubernetes/clusters | json_get id)"
api_json POST "/api/control/kubernetes/clusters/${CLUSTER_ID}/test-connection" >/dev/null

echo "[2/8] Deploy new Secret"
make_cert "new.example.com" "new"
NEW_CERT_ID="$(upload_cert "new-example-com" "new" | json_get id)"
NEW_ASSIGNMENT_ID="$(create_assignment_payload "$CLUSTER_ID" "$NEW_CERT_ID" "new-tls" | api_json POST /api/control/kubernetes/assignments | json_get id)"
NEW_DRY_RUN_ID="$(api_json POST "/api/control/kubernetes/assignments/${NEW_ASSIGNMENT_ID}/deploy/dry-run" | json_get id)"
api_json POST "/api/control/kubernetes/assignments/${NEW_ASSIGNMENT_ID}/deploy/confirm" "$(confirm_payload "$NEW_DRY_RUN_ID")" >/dev/null
secret_serial "new-tls"

echo "[3/8] Adopt existing old Secret"
make_cert "replace.example.com" "old"
kubectl -n "$NAMESPACE" delete secret replace-tls --ignore-not-found >/dev/null
kubectl -n "$NAMESPACE" create secret tls replace-tls --cert "$WORKDIR/old.crt" --key "$WORKDIR/old.key" >/dev/null
OLD_CERT_ID="$(upload_cert "replace-example-com-old" "old" | json_get id)"
REPLACE_ASSIGNMENT_ID="$(create_assignment_payload "$CLUSTER_ID" "$OLD_CERT_ID" "replace-tls" | api_json POST /api/control/kubernetes/assignments | json_get id)"
ADOPT_DRY_RUN_ID="$(api_json POST "/api/control/kubernetes/assignments/${REPLACE_ASSIGNMENT_ID}/adopt/dry-run" | json_get id)"
api_json POST "/api/control/kubernetes/assignments/${REPLACE_ASSIGNMENT_ID}/adopt/confirm" "$(confirm_payload "$ADOPT_DRY_RUN_ID")" >/dev/null

echo "[4/8] Replace old Secret with renewed cert"
make_cert "replace.example.com" "renewed"
upload_cert "replace-example-com-renewed" "renewed" >/dev/null
DEPLOY_DRY_RUN_ID="$(api_json POST "/api/control/kubernetes/assignments/${REPLACE_ASSIGNMENT_ID}/deploy/dry-run" | json_get id)"
api_json POST "/api/control/kubernetes/assignments/${REPLACE_ASSIGNMENT_ID}/deploy/confirm" "$(confirm_payload "$DEPLOY_DRY_RUN_ID")" >/dev/null
secret_serial "replace-tls"

echo "[5/8] Roll back latest replacement"
ROLLBACK_DRY_RUN_ID="$(api_json POST "/api/control/kubernetes/assignments/${REPLACE_ASSIGNMENT_ID}/rollback/dry-run" | json_get id)"
api_json POST "/api/control/kubernetes/assignments/${REPLACE_ASSIGNMENT_ID}/rollback/confirm" "$(confirm_payload "$ROLLBACK_DRY_RUN_ID")" >/dev/null
secret_serial "replace-tls"

echo "[6/8] Manually change deployment target"
MOVE_ASSIGNMENT_ID="$(create_assignment_payload "$CLUSTER_ID" "$NEW_CERT_ID" "moved-tls" | api_json POST /api/control/kubernetes/assignments | json_get id)"
MOVE_DRY_RUN_ID="$(api_json POST "/api/control/kubernetes/assignments/${MOVE_ASSIGNMENT_ID}/deploy/dry-run" | json_get id)"
api_json POST "/api/control/kubernetes/assignments/${MOVE_ASSIGNMENT_ID}/deploy/confirm" "$(confirm_payload "$MOVE_DRY_RUN_ID")" >/dev/null
secret_serial "moved-tls"

echo "[7/8] Validate assignments"
api_json POST "/api/control/kubernetes/assignments/${NEW_ASSIGNMENT_ID}/validate" >/dev/null
api_json POST "/api/control/kubernetes/assignments/${REPLACE_ASSIGNMENT_ID}/validate" >/dev/null
api_json POST "/api/control/kubernetes/assignments/${MOVE_ASSIGNMENT_ID}/validate" >/dev/null

echo "[8/8] Done"
api_json GET /api/control/kubernetes/operations?limit=20 >/dev/null
echo "K8s Secret E2E completed against ${CONTROL_PLANE_URL} namespace=${NAMESPACE}"
