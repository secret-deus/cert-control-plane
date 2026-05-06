#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT_DIR"

AGENT_NAME="${SMOKE_AGENT_NAME:-edge-node-live-1}"
COMMON_NAME="${SMOKE_COMMON_NAME:-api.example.com}"
LOCAL_PATH="${SMOKE_LOCAL_PATH:-/etc/nginx/certs/api.example.com.crt}"
VALID_DAYS="${SMOKE_CERT_DAYS:-30}"
EDGE_SERVICE="${SMOKE_EDGE_SERVICE:-edge-node}"
EDGE_OVERLAY="${SMOKE_EDGE_OVERLAY:-}"
PUBLIC_PORT="${SMOKE_PUBLIC_PORT:-9444}"

compose_base() {
  docker compose "$@"
}

compose_edge() {
  if [ -n "$EDGE_OVERLAY" ]; then
    docker compose -f docker-compose.yml -f tools/agent-smoke/docker-compose.edge.yml -f "$EDGE_OVERLAY" "$@"
  else
    docker compose -f docker-compose.yml -f tools/agent-smoke/docker-compose.edge.yml "$@"
  fi
}

echo "[1/4] rebuilding control plane and edge node"
compose_base up -d --build db app
for attempt in $(seq 1 60); do
  if compose_base exec -T app python - <<'PY' >/dev/null 2>&1
import urllib.request

with urllib.request.urlopen("http://localhost:8000/healthz", timeout=2) as resp:
    raise SystemExit(0 if resp.status == 200 else 1)
PY
  then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "control plane did not become healthy" >&2
    compose_base logs app --tail=120 >&2 || true
    exit 1
  fi
  sleep 2
done

echo "[2/4] stopping stale edge node and resetting smoke agent identity"
compose_edge rm -sf "$EDGE_SERVICE" >/dev/null 2>&1 || true

compose_base exec -T app env SMOKE_AGENT_NAME="$AGENT_NAME" python - <<'PY'
import json
import os
import urllib.request

admin_key = os.environ["ADMIN_API_KEY"]
agent_name = os.environ["SMOKE_AGENT_NAME"]
base = "http://localhost:8000/api/control"


def request(method: str, path: str) -> dict:
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"X-Admin-API-Key": admin_key},
        method=method,
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else {}


deleted = 0
skip = 0
limit = 500
while True:
    agents = request("GET", f"/agents?skip={skip}&limit={limit}").get("items", [])
    for agent in agents:
        if agent["name"] == agent_name:
            request("DELETE", f"/agents/{agent['id']}")
            print(f"deleted stale agent {agent_name} ({agent['id']})")
            deleted += 1
    if len(agents) < limit:
        break
    skip += limit

if deleted == 0:
    print(f"no stale agent named {agent_name}")
PY

compose_edge up -d --build "$EDGE_SERVICE"

echo "[3/4] approving agent, generating cert, uploading and assigning"
RESULT=$(
  compose_base exec -T app env \
    SMOKE_AGENT_NAME="$AGENT_NAME" \
    SMOKE_COMMON_NAME="$COMMON_NAME" \
    SMOKE_LOCAL_PATH="$LOCAL_PATH" \
    SMOKE_VALID_DAYS="$VALID_DAYS" \
    python - <<'PY'
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

admin_key = os.environ["ADMIN_API_KEY"]
agent_name = os.environ["SMOKE_AGENT_NAME"]
common_name = os.environ["SMOKE_COMMON_NAME"]
local_path = os.environ["SMOKE_LOCAL_PATH"]
valid_days = int(os.environ["SMOKE_VALID_DAYS"])
base = "http://localhost:8000/api/control"


def request(method: str, path: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"X-Admin-API-Key": admin_key}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else {}


agent = None
for _ in range(30):
    agents = request("GET", "/agents").get("items", [])
    agent = next((item for item in agents if item["name"] == agent_name), None)
    if agent is not None:
        break
    import time
    time.sleep(2)

if agent is None:
    raise SystemExit(f"Agent {agent_name!r} not found after waiting")

if agent["status"] == "pending_approval":
    request("POST", f"/agents/{agent['id']}/approve")

now = datetime.now(tz=timezone.utc)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=5))
    .not_valid_after(now + timedelta(days=valid_days))
    .sign(key, hashes.SHA256())
)
cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
key_pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()

name = f"smoke-{common_name}-{now.strftime('%Y%m%d%H%M%S')}"
upload = request("POST", "/external-certs", {
    "name": name,
    "description": "Generated by tools/agent-smoke/run-live-smoke.sh",
    "provider": "smoke-test",
    "cert_pem": cert_pem,
    "key_pem": key_pem,
    "chain_pem": None,
    "external_id": None,
})
request("POST", f"/agents/{agent['id']}/assign-cert", {
    "external_cert_id": upload["id"],
    "local_path": local_path,
})

print(f"AGENT_ID={agent['id']}")
print(f"CERT_ID={upload['id']}")
print(f"SERIAL_HEX={upload['serial_hex']}")
print(f"NOT_AFTER={upload['not_after']}")
print(f"LOCAL_PATH={local_path}")
PY
)

printf '%s\n' "$RESULT"
SERIAL_HEX=$(printf '%s\n' "$RESULT" | sed -n 's/^SERIAL_HEX=//p' | tr 'A-Z' 'a-z' | sed 's/^0*//')

echo "[4/4] waiting for agent deployment"
ATTEMPTS=0
CURRENT_SERIAL=""
while [ "$ATTEMPTS" -lt 30 ]; do
  CURRENT_SERIAL=$(
    compose_edge exec -T "$EDGE_SERVICE" env LOCAL_PATH="$LOCAL_PATH" sh -lc \
      'openssl x509 -in "$LOCAL_PATH" -noout -serial 2>/dev/null | cut -d= -f2' 2>/dev/null || true
  )
  CURRENT_SERIAL=$(printf '%s' "$CURRENT_SERIAL" \
      | tr 'A-Z' 'a-z' \
      | sed 's/^0*//'
  )
  if [ -n "$CURRENT_SERIAL" ] && [ "$CURRENT_SERIAL" = "$SERIAL_HEX" ]; then
    break
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  sleep 2
done

if [ "${CURRENT_SERIAL:-}" != "$SERIAL_HEX" ]; then
  echo "smoke failed: edge node did not deploy expected serial $SERIAL_HEX" >&2
  compose_edge logs --tail=120 "$EDGE_SERVICE" >&2 || true
  exit 1
fi

echo "[done] deployed certificate on edge node"
compose_edge exec -T "$EDGE_SERVICE" env LOCAL_PATH="$LOCAL_PATH" sh -lc \
  'openssl x509 -in "$LOCAL_PATH" -noout -serial -subject -dates'

echo "public endpoint: https://localhost:${PUBLIC_PORT}"
