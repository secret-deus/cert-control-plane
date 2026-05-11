#!/bin/sh
set -eu

EDGE_PROCESS_CONFIG="${EDGE_PROCESS_CONFIG:-[]}"
EDGE_AGENT_CMD="${EDGE_AGENT_CMD:-python -m agent}"

mkdir -p /var/lib/cert-agent /etc/nginx/matrix /run

python - <<'PY'
import json
import os
import subprocess
from pathlib import Path

processes = json.loads(os.environ.get("EDGE_PROCESS_CONFIG", "[]"))
if not processes:
    raise SystemExit("EDGE_PROCESS_CONFIG is required")

for item in processes:
    name = item["name"]
    listen = int(item["listen"])
    cert_path = Path(item["cert_path"])
    key_path = cert_path.with_suffix(".key")
    response = item.get("response", name)

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    if not cert_path.exists() or not key_path.exists():
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-nodes",
                "-newkey",
                "rsa:2048",
                "-subj",
                f"/CN=bootstrap-{name}.local",
                "-days",
                "1",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    conf = Path(f"/etc/nginx/matrix/{name}.conf")
    conf.write_text(
        f"""
worker_processes 1;
pid /run/nginx-{name}.pid;

events {{
    worker_connections 128;
}}

http {{
    access_log /dev/stdout;
    error_log /dev/stderr info;

    server {{
        listen {listen} ssl;
        server_name _;

        ssl_certificate     {cert_path};
        ssl_certificate_key {key_path};
        ssl_protocols       TLSv1.2 TLSv1.3;

        location / {{
            add_header Content-Type text/plain;
            return 200 "{response}\\n";
        }}
    }}
}}
""",
        encoding="utf-8",
    )
PY

python - <<'PY'
import json
import os
import subprocess

for item in json.loads(os.environ["EDGE_PROCESS_CONFIG"]):
    subprocess.run(["nginx", "-c", f"/etc/nginx/matrix/{item['name']}.conf"], check=True)
PY

exec sh -lc "${EDGE_AGENT_CMD}"
