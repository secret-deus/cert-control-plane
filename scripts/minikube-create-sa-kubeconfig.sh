#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-cert-control-plane-e2e}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-cert-control-plane-secret-writer}"
OUTPUT="${OUTPUT:-tmp/minikube-cert-control-plane-sa.kubeconfig}"
SERVER_MODE="${SERVER_MODE:-host}"
PRINT_STDOUT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --service-account)
      SERVICE_ACCOUNT="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    --server-mode)
      SERVER_MODE="$2"
      shift 2
      ;;
    --stdout)
      PRINT_STDOUT=true
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

for cmd in kubectl python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

mkdir -p "$(dirname "$OUTPUT")"

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE" >/dev/null

kubectl apply -n "$NAMESPACE" -f - >/dev/null <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ${SERVICE_ACCOUNT}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ${SERVICE_ACCOUNT}
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ${SERVICE_ACCOUNT}
subjects:
  - kind: ServiceAccount
    name: ${SERVICE_ACCOUNT}
    namespace: ${NAMESPACE}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: ${SERVICE_ACCOUNT}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: ${SERVICE_ACCOUNT}-namespace-reader
rules:
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ${SERVICE_ACCOUNT}-${NAMESPACE}-namespace-reader
subjects:
  - kind: ServiceAccount
    name: ${SERVICE_ACCOUNT}
    namespace: ${NAMESPACE}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: ${SERVICE_ACCOUNT}-namespace-reader
EOF

TOKEN="$(kubectl -n "$NAMESPACE" create token "$SERVICE_ACCOUNT")"
CURRENT_CONTEXT="$(kubectl config current-context)"

if [[ "$SERVER_MODE" == "in-cluster" ]]; then
  SERVER="https://kubernetes.default.svc"
  CA_DATA="$(kubectl -n default get configmap kube-root-ca.crt -o jsonpath='{.data.ca\.crt}' | base64 | tr -d '\n')"
else
  SERVER="$(kubectl config view --raw -o jsonpath="{.clusters[?(@.name==\"${CURRENT_CONTEXT}\")].cluster.server}")"
  if [[ -z "$SERVER" ]]; then
    CLUSTER_NAME="$(kubectl config view --raw -o jsonpath="{.contexts[?(@.name==\"${CURRENT_CONTEXT}\")].context.cluster}")"
    SERVER="$(kubectl config view --raw -o jsonpath="{.clusters[?(@.name==\"${CLUSTER_NAME}\")].cluster.server}")"
    CA_DATA="$(kubectl config view --raw -o jsonpath="{.clusters[?(@.name==\"${CLUSTER_NAME}\")].cluster.certificate-authority-data}")"
  else
    CA_DATA="$(kubectl config view --raw -o jsonpath="{.clusters[?(@.name==\"${CURRENT_CONTEXT}\")].cluster.certificate-authority-data}")"
  fi
fi

python3 - "$OUTPUT" "$SERVER" "$TOKEN" "$CA_DATA" "$NAMESPACE" "$SERVICE_ACCOUNT" <<'PY'
import sys
from pathlib import Path

import yaml

output, server, token, ca_data, namespace, service_account = sys.argv[1:]
config = {
    "apiVersion": "v1",
    "kind": "Config",
    "current-context": f"{service_account}@{namespace}",
    "clusters": [
        {
            "name": "target",
            "cluster": {
                "server": server,
                "certificate-authority-data": ca_data,
            },
        }
    ],
    "users": [
        {
            "name": service_account,
            "user": {"token": token},
        }
    ],
    "contexts": [
        {
            "name": f"{service_account}@{namespace}",
            "context": {
                "cluster": "target",
                "user": service_account,
                "namespace": namespace,
            },
        }
    ],
}
Path(output).write_text(yaml.safe_dump(config), encoding="utf-8")
PY

if [[ "$PRINT_STDOUT" == "true" ]]; then
  cat "$OUTPUT"
else
  echo "$OUTPUT"
fi
