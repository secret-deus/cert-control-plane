# Minikube Deployment

This directory deploys the single-port Cert Control Plane stack to local minikube.

## Topology

- Namespace: `cert-control-plane`
- App image: `cert-control-plane-app:minikube`
- PostgreSQL: `postgres:16-alpine` with a local PVC
- App Service: `cert-control-plane`, NodePort `30080`
- Dashboard, Control API, and Agent API share the same app port.

## Deploy

From the repository root:

```bash
bash scripts/minikube-deploy.sh
```

The script:

1. Checks `minikube` and `kubectl`.
2. Points Docker at minikube's Docker daemon and builds `server/Dockerfile`.
3. Creates or reuses `cert-control-plane-secrets`.
4. Applies the Kubernetes manifests.
5. Waits for both Deployments.
6. Verifies `/healthz` through a temporary port-forward.

Set `MINIKUBE_PROFILE` if your local profile is not named `minikube`.

## Access

Use either port-forward:

```bash
kubectl -n cert-control-plane port-forward svc/cert-control-plane 18080:8080
open http://localhost:18080/dashboard
```

Or minikube's service helper:

```bash
minikube service -n cert-control-plane cert-control-plane --url
```

Read the generated Admin API Key:

```bash
kubectl -n cert-control-plane get secret cert-control-plane-secrets \
  -o jsonpath='{.data.ADMIN_API_KEY}' | base64 -d && echo
```

## Kubernetes Secret E2E

Phase 5 writes business TLS Secrets through an uploaded ServiceAccount kubeconfig.
For local minikube validation, generate that kubeconfig first:

```bash
NAMESPACE=cert-control-plane-e2e \
OUTPUT=tmp/minikube-cert-control-plane-sa.kubeconfig \
bash scripts/minikube-create-sa-kubeconfig.sh
```

If the control plane runs inside minikube, generate an in-cluster kubeconfig:

```bash
SERVER_MODE=in-cluster \
NAMESPACE=cert-control-plane-e2e \
OUTPUT=tmp/minikube-cert-control-plane-sa.kubeconfig \
bash scripts/minikube-create-sa-kubeconfig.sh
```

Run the real K8s Secret E2E flow against a reachable control plane:

```bash
export ADMIN_API_KEY="$(kubectl -n cert-control-plane get secret cert-control-plane-secrets \
  -o jsonpath='{.data.ADMIN_API_KEY}' | base64 -d)"
export CONTROL_PLANE_URL="http://127.0.0.1:18080"

bash scripts/minikube-k8s-secret-e2e.sh
```

The E2E script uses the real Kubernetes API and covers:

- new TLS Secret deployment
- existing Secret adopt
- old certificate replacement with renewed cert material
- latest rollback
- manual target change by deploying the same certificate to another Secret
- read-back validation through `kubectl get secret`

## Real Topology Simulation

Use the multi-target simulation when validating behavior closer to production:

```bash
export ADMIN_API_KEY="$(kubectl -n cert-control-plane get secret cert-control-plane-secrets \
  -o jsonpath='{.data.ADMIN_API_KEY}' | base64 -d)"
export CONTROL_PLANE_URL="http://127.0.0.1:18080"

bash scripts/minikube-k8s-secret-real-simulation.sh
```

The simulation creates three independent target namespaces:

- `certcp-real-edge-a`
- `certcp-real-edge-b`
- `certcp-real-edge-c`

Each namespace receives its own ServiceAccount kubeconfig with namespace-scoped
Secret write permissions. The script registers three Kubernetes targets in the
control plane and verifies:

- brand-new TLS Secret deployment on edge A
- adopt, replacement, and latest rollback on edge B
- manual target move by deploying the edge A certificate to edge C and deleting
  the old edge A assignment record
- real Kubernetes read-back serial checks
- RBAC negative path: edge A credentials cannot dry-run or write a Secret in
  edge B's namespace

## Reset

Delete the local minikube deployment and database PVC:

```bash
kubectl delete namespace cert-control-plane
```

This removes local PostgreSQL data in the namespace.
