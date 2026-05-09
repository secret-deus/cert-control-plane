#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:18080}"
ADMIN_API_KEY="${ADMIN_API_KEY:-}"
WORKDIR="${WORKDIR:-tmp/k8s-secret-real-simulation}"
SERVER_MODE="${SERVER_MODE:-host}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d%H%M%S)}"

NS_A="${NS_A:-certcp-real-edge-a}"
NS_B="${NS_B:-certcp-real-edge-b}"
NS_C="${NS_C:-certcp-real-edge-c}"
SA_NAME="${SA_NAME:-cert-control-plane-secret-writer}"

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$WORKDIR"

if ! minikube status >/dev/null 2>&1; then
  minikube start
fi

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

api_status() {
  local method="$1"
  local path="$2"
  local outfile="$3"
  local payload="${4:-}"
  if [[ -n "$payload" ]]; then
    curl -sS -X "$method" "$CONTROL_PLANE_URL$path" \
      -H "X-Admin-API-Key: $ADMIN_API_KEY" \
      -H "Content-Type: application/json" \
      --data-binary "$payload" \
      -o "$outfile" \
      -w "%{http_code}"
  else
    curl -sS -X "$method" "$CONTROL_PLANE_URL$path" \
      -H "X-Admin-API-Key: $ADMIN_API_KEY" \
      -o "$outfile" \
      -w "%{http_code}"
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

cert_serial() {
  local prefix="$1"
  openssl x509 -in "$WORKDIR/${prefix}.crt" -noout -serial | cut -d= -f2
}

secret_serial() {
  local namespace="$1"
  local secret_name="$2"
  kubectl -n "$namespace" get secret "$secret_name" -o jsonpath='{.data.tls\.crt}' \
    | python3 -c 'import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))' \
    | openssl x509 -noout -serial \
    | cut -d= -f2
}

secret_cn() {
  local namespace="$1"
  local secret_name="$2"
  kubectl -n "$namespace" get secret "$secret_name" -o jsonpath='{.data.tls\.crt}' \
    | python3 -c 'import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))' \
    | openssl x509 -noout -subject
}

upload_cert() {
  local name="$1"
  local prefix="$2"
  python3 - "$name" "$WORKDIR/${prefix}.crt" "$WORKDIR/${prefix}.key" <<'PY' | api_json POST /api/control/external-certs
import json
import sys

name, cert_path, key_path = sys.argv[1:]
print(json.dumps({
    "name": name,
    "description": "minikube real topology simulation",
    "cert_pem": open(cert_path, encoding="utf-8").read(),
    "key_pem": open(key_path, encoding="utf-8").read(),
    "chain_pem": None,
    "provider": "manual",
    "external_id": name,
}))
PY
}

kubeconfig_path() {
  local edge="$1"
  echo "$WORKDIR/${edge}.kubeconfig"
}

create_sa_kubeconfig() {
  local namespace="$1"
  local edge="$2"
  NAMESPACE="$namespace" \
    SERVICE_ACCOUNT="$SA_NAME" \
    OUTPUT="$(kubeconfig_path "$edge")" \
    SERVER_MODE="$SERVER_MODE" \
    "$SCRIPT_DIR/minikube-create-sa-kubeconfig.sh" >/dev/null
}

create_cluster_payload() {
  local edge="$1"
  local namespace="$2"
  local kubeconfig="$3"
  python3 - "$edge" "$namespace" "$kubeconfig" "$RUN_ID" <<'PY'
import json
import sys

edge, namespace, kubeconfig_path, run_id = sys.argv[1:]
print(json.dumps({
    "name": f"real-{edge}-{run_id}",
    "environment": "minikube-real",
    "kubeconfig": open(kubeconfig_path, encoding="utf-8").read(),
    "default_namespace": namespace,
}))
PY
}

create_assignment_payload() {
  local cluster_id="$1"
  local cert_id="$2"
  local namespace="$3"
  local secret_name="$4"
  python3 - "$cluster_id" "$cert_id" "$namespace" "$secret_name" <<'PY'
import json
import sys

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
import json
import sys

print(json.dumps({"dry_run_id": sys.argv[1]}))
PY
}

test_connection() {
  local cluster_id="$1"
  api_json POST "/api/control/kubernetes/clusters/${cluster_id}/test-connection" >/dev/null
}

deploy_assignment() {
  local assignment_id="$1"
  local dry_run_id
  dry_run_id="$(api_json POST "/api/control/kubernetes/assignments/${assignment_id}/deploy/dry-run" | json_get id)"
  api_json POST "/api/control/kubernetes/assignments/${assignment_id}/deploy/confirm" "$(confirm_payload "$dry_run_id")" >/dev/null
}

adopt_assignment() {
  local assignment_id="$1"
  local dry_run_id
  dry_run_id="$(api_json POST "/api/control/kubernetes/assignments/${assignment_id}/adopt/dry-run" | json_get id)"
  api_json POST "/api/control/kubernetes/assignments/${assignment_id}/adopt/confirm" "$(confirm_payload "$dry_run_id")" >/dev/null
}

rollback_assignment() {
  local assignment_id="$1"
  local dry_run_id
  dry_run_id="$(api_json POST "/api/control/kubernetes/assignments/${assignment_id}/rollback/dry-run" | json_get id)"
  api_json POST "/api/control/kubernetes/assignments/${assignment_id}/rollback/confirm" "$(confirm_payload "$dry_run_id")" >/dev/null
}

create_cluster() {
  local edge="$1"
  local namespace="$2"
  local kubeconfig="$3"
  create_cluster_payload "$edge" "$namespace" "$kubeconfig" | api_json POST /api/control/kubernetes/clusters | json_get id
}

for namespace in "$NS_A" "$NS_B" "$NS_C"; do
  kubectl get namespace "$namespace" >/dev/null 2>&1 || kubectl create namespace "$namespace" >/dev/null
  kubectl -n "$namespace" delete secret api-tls rbac-denied-tls --ignore-not-found >/dev/null
done

echo "[1/10] Create three target namespaces and least-privilege SA kubeconfigs"
create_sa_kubeconfig "$NS_A" "edge-a"
create_sa_kubeconfig "$NS_B" "edge-b"
create_sa_kubeconfig "$NS_C" "edge-c"

echo "[2/10] Register three Kubernetes cluster targets in control plane"
CLUSTER_A_ID="$(create_cluster edge-a "$NS_A" "$(kubeconfig_path edge-a)")"
CLUSTER_B_ID="$(create_cluster edge-b "$NS_B" "$(kubeconfig_path edge-b)")"
CLUSTER_C_ID="$(create_cluster edge-c "$NS_C" "$(kubeconfig_path edge-c)")"
test_connection "$CLUSTER_A_ID"
test_connection "$CLUSTER_B_ID"
test_connection "$CLUSTER_C_ID"

echo "[3/10] Deploy a brand-new certificate to edge-a"
make_cert "real-edge-a-${RUN_ID}.example.test" "edge-a-new"
EDGE_A_CERT_ID="$(upload_cert "real-edge-a-${RUN_ID}" "edge-a-new" | json_get id)"
EDGE_A_ASSIGNMENT_ID="$(create_assignment_payload "$CLUSTER_A_ID" "$EDGE_A_CERT_ID" "$NS_A" api-tls | api_json POST /api/control/kubernetes/assignments | json_get id)"
deploy_assignment "$EDGE_A_ASSIGNMENT_ID"
EDGE_A_EXPECTED_SERIAL="$(cert_serial edge-a-new)"
EDGE_A_ACTUAL_SERIAL="$(secret_serial "$NS_A" api-tls)"

echo "[4/10] Adopt an existing old certificate on edge-b"
make_cert "real-edge-b-${RUN_ID}.example.test" "edge-b-old"
kubectl -n "$NS_B" create secret tls api-tls --cert "$WORKDIR/edge-b-old.crt" --key "$WORKDIR/edge-b-old.key" >/dev/null
EDGE_B_CERT_ID="$(upload_cert "real-edge-b-${RUN_ID}" "edge-b-old" | json_get id)"
EDGE_B_ASSIGNMENT_ID="$(create_assignment_payload "$CLUSTER_B_ID" "$EDGE_B_CERT_ID" "$NS_B" api-tls | api_json POST /api/control/kubernetes/assignments | json_get id)"
adopt_assignment "$EDGE_B_ASSIGNMENT_ID"
EDGE_B_OLD_SERIAL="$(cert_serial edge-b-old)"

echo "[5/10] Replace edge-b old certificate with a renewed certificate"
make_cert "real-edge-b-${RUN_ID}.example.test" "edge-b-renewed"
upload_cert "real-edge-b-${RUN_ID}" "edge-b-renewed" >/dev/null
deploy_assignment "$EDGE_B_ASSIGNMENT_ID"
EDGE_B_RENEWED_EXPECTED_SERIAL="$(cert_serial edge-b-renewed)"
EDGE_B_RENEWED_ACTUAL_SERIAL="$(secret_serial "$NS_B" api-tls)"

echo "[6/10] Roll back edge-b to the latest previous Secret snapshot"
rollback_assignment "$EDGE_B_ASSIGNMENT_ID"
EDGE_B_ROLLBACK_SERIAL="$(secret_serial "$NS_B" api-tls)"

echo "[7/10] Manually move edge-a certificate target to edge-c"
EDGE_C_ASSIGNMENT_ID="$(create_assignment_payload "$CLUSTER_C_ID" "$EDGE_A_CERT_ID" "$NS_C" api-tls | api_json POST /api/control/kubernetes/assignments | json_get id)"
deploy_assignment "$EDGE_C_ASSIGNMENT_ID"
EDGE_C_SERIAL="$(secret_serial "$NS_C" api-tls)"
api_json DELETE "/api/control/kubernetes/assignments/${EDGE_A_ASSIGNMENT_ID}" >/dev/null
EDGE_A_SECRET_AFTER_MOVE="$(secret_serial "$NS_A" api-tls)"

echo "[8/10] Validate active assignments"
api_json POST "/api/control/kubernetes/assignments/${EDGE_B_ASSIGNMENT_ID}/validate" >/dev/null
api_json POST "/api/control/kubernetes/assignments/${EDGE_C_ASSIGNMENT_ID}/validate" >/dev/null

echo "[9/10] Verify namespace RBAC blocks cross-namespace writes"
RBAC_ASSIGNMENT_ID="$(create_assignment_payload "$CLUSTER_A_ID" "$EDGE_A_CERT_ID" "$NS_B" rbac-denied-tls | api_json POST /api/control/kubernetes/assignments | json_get id)"
RBAC_OUT="$WORKDIR/rbac-denied-response.json"
RBAC_STATUS="$(api_status POST "/api/control/kubernetes/assignments/${RBAC_ASSIGNMENT_ID}/deploy/dry-run" "$RBAC_OUT")"
api_json DELETE "/api/control/kubernetes/assignments/${RBAC_ASSIGNMENT_ID}" >/dev/null
if [[ "$RBAC_STATUS" != "403" ]]; then
  echo "Expected RBAC dry-run status 403, got ${RBAC_STATUS}" >&2
  cat "$RBAC_OUT" >&2
  exit 1
fi
if kubectl -n "$NS_B" get secret rbac-denied-tls >/dev/null 2>&1; then
  echo "RBAC negative test unexpectedly created rbac-denied-tls in ${NS_B}" >&2
  exit 1
fi

echo "[10/10] Summary"
cat <<EOF
run_id=${RUN_ID}
control_plane=${CONTROL_PLANE_URL}
edge_a_cluster_id=${CLUSTER_A_ID}
edge_b_cluster_id=${CLUSTER_B_ID}
edge_c_cluster_id=${CLUSTER_C_ID}
edge_a_assignment_deleted=${EDGE_A_ASSIGNMENT_ID}
edge_b_assignment_active=${EDGE_B_ASSIGNMENT_ID}
edge_c_assignment_active=${EDGE_C_ASSIGNMENT_ID}
edge_a_expected_serial=${EDGE_A_EXPECTED_SERIAL}
edge_a_actual_serial=${EDGE_A_ACTUAL_SERIAL}
edge_a_secret_after_move_serial=${EDGE_A_SECRET_AFTER_MOVE}
edge_b_old_serial=${EDGE_B_OLD_SERIAL}
edge_b_renewed_expected_serial=${EDGE_B_RENEWED_EXPECTED_SERIAL}
edge_b_renewed_actual_serial=${EDGE_B_RENEWED_ACTUAL_SERIAL}
edge_b_rollback_serial=${EDGE_B_ROLLBACK_SERIAL}
edge_c_serial=${EDGE_C_SERIAL}
rbac_cross_namespace_status=${RBAC_STATUS}
edge_a_secret_subject_after_move=$(secret_cn "$NS_A" api-tls)
edge_b_secret_subject_after_rollback=$(secret_cn "$NS_B" api-tls)
edge_c_secret_subject=$(secret_cn "$NS_C" api-tls)
EOF
