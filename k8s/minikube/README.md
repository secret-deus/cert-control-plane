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

## Reset

Delete the local minikube deployment and database PVC:

```bash
kubectl delete namespace cert-control-plane
```

This removes local PostgreSQL data in the namespace.
