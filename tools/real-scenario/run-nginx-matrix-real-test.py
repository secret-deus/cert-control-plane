#!/usr/bin/env python3
"""Real Docker scenario test for multiple nginx machines/processes/path mapping."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


ROOT = Path(__file__).resolve().parents[2]
RUN_ID = os.environ.get("RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
CP_URL = os.environ.get("CONTROL_PLANE_URL", "http://127.0.0.1:8080").rstrip("/")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY") or "prod-smoke-admin-key"
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK", "certcp_smoke_default")
IMAGE = os.environ.get("NGINX_MATRIX_IMAGE", "cert-control-plane-nginx-matrix:latest")
OUT_DIR = ROOT / "tmp" / "real-scenario"
OUT_FILE = OUT_DIR / f"nginx-matrix-result-{RUN_ID}.json"


@dataclass(frozen=True)
class ProcessTarget:
    name: str
    internal_port: int
    host_port: int
    cert_path: str
    cn: str


@dataclass(frozen=True)
class EdgeTarget:
    container: str
    agent_name: str
    processes: list[ProcessTarget]


def run(cmd: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def api(method: str, path: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"X-Admin-API-Key": ADMIN_API_KEY}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{CP_URL}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else {}


def wait_control_plane() -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{CP_URL}/readyz", timeout=3) as resp:
                if resp.status == 200 and b'"connected"' in resp.read():
                    return
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"control plane not ready: {CP_URL}")


def normalize_serial(value: str) -> str:
    value = value.strip().splitlines()[-1]
    if "=" in value:
        value = value.split("=", 1)[1]
    return value.lower().lstrip("0")


def make_cert(cn: str, days: int) -> tuple[str, str, str, str]:
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem, format(cert.serial_number, "x").lower(), cert.not_valid_after_utc.isoformat()


def upload_cert(name: str, cn: str, days: int) -> dict:
    cert_pem, key_pem, serial, not_after = make_cert(cn, days)
    resp = api(
        "POST",
        "/api/control/external-certs",
        {
            "name": name,
            "description": f"real nginx matrix test {RUN_ID}",
            "provider": "real-scenario",
            "external_id": f"{name}-{RUN_ID}",
            "cert_pem": cert_pem,
            "key_pem": key_pem,
            "chain_pem": None,
        },
    )
    resp["_expected_serial"] = serial
    resp["_expected_not_after"] = not_after
    return resp


def list_agents() -> list[dict]:
    items: list[dict] = []
    skip = 0
    while True:
        page = api("GET", f"/api/control/agents?skip={skip}&limit=100")
        batch = page.get("items", [])
        items.extend(batch)
        if len(batch) < 100:
            return items
        skip += 100


def delete_stale_agents(edges: list[EdgeTarget]) -> None:
    names = {edge.agent_name for edge in edges}
    for agent in list_agents():
        if agent["name"] in names:
            api("DELETE", f"/api/control/agents/{agent['id']}")


def build_image() -> None:
    run(["docker", "build", "-t", IMAGE, "-f", "tools/real-scenario/nginx-matrix.Dockerfile", "."])


def start_edges(edges: list[EdgeTarget]) -> None:
    for edge in edges:
        run(["docker", "rm", "-f", edge.container], check=False, capture=True)
        proc_config = [
            {
                "name": proc.name,
                "listen": proc.internal_port,
                "cert_path": proc.cert_path,
                "response": proc.name,
            }
            for proc in edge.processes
        ]
        cert_table = [{"local_path": proc.cert_path} for proc in edge.processes]
        reload_cmd = " && ".join(
            f"nginx -s reload -c /etc/nginx/matrix/{proc.name}.conf" for proc in edge.processes
        )
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            edge.container,
            "--network",
            DOCKER_NETWORK,
        ]
        for proc in edge.processes:
            cmd += ["-p", f"127.0.0.1:{proc.host_port}:{proc.internal_port}"]
        cmd += [
            "-e",
            "CERT_AGENT_CP_URL=http://app:8000",
            "-e",
            f"CERT_AGENT_NAME={edge.agent_name}",
            "-e",
            f"CERT_AGENT_CERT_TABLE={json.dumps(cert_table)}",
            "-e",
            "CERT_AGENT_STATE_DIR=/var/lib/cert-agent",
            "-e",
            f"CERT_AGENT_NGINX_RELOAD_CMD={reload_cmd}",
            "-e",
            "CERT_AGENT_HEARTBEAT_INTERVAL=2",
            "-e",
            "CERT_AGENT_POLL_INTERVAL=2",
            "-e",
            f"EDGE_PROCESS_CONFIG={json.dumps(proc_config)}",
            "-e",
            "PYTHONUNBUFFERED=1",
            IMAGE,
        ]
        run(cmd, capture=True)


def approve_agents(edges: list[EdgeTarget]) -> dict[str, dict]:
    wanted = {edge.agent_name for edge in edges}
    found: dict[str, dict] = {}
    deadline = time.time() + 90
    while time.time() < deadline:
        for agent in list_agents():
            if agent["name"] in wanted:
                found[agent["name"]] = agent
        if wanted <= set(found):
            break
        time.sleep(2)
    missing = wanted - set(found)
    if missing:
        raise RuntimeError(f"agents not registered: {sorted(missing)}")
    for agent in list(found.values()):
        if agent["status"] == "pending_approval":
            api("POST", f"/api/control/agents/{agent['id']}/approve")
    time.sleep(5)
    return {agent["name"]: agent for agent in list_agents() if agent["name"] in wanted}


def assign(agent_id: str, cert_id: str, path: str) -> dict:
    return api(
        "POST",
        f"/api/control/agents/{agent_id}/assign-cert",
        {"external_cert_id": cert_id, "local_path": path},
    )


def container_serial(container: str, path: str) -> str:
    result = run(["docker", "exec", container, "openssl", "x509", "-in", path, "-noout", "-serial"], capture=True)
    return normalize_serial(result.stdout or "")


def endpoint_serial(port: int) -> str:
    cmd = (
        f"openssl s_client -connect 127.0.0.1:{port} -servername localhost </dev/null 2>/dev/null "
        "| openssl x509 -noout -serial"
    )
    result = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    return normalize_serial(result.stdout)


def wait_serial(container: str, path: str, port: int, expected: str) -> dict:
    expected_norm = normalize_serial(expected)
    last_file = ""
    last_endpoint = ""
    for _ in range(90):
        try:
            last_file = container_serial(container, path)
            last_endpoint = endpoint_serial(port)
            if last_file == expected_norm and last_endpoint == expected_norm:
                return {"file_serial": last_file, "endpoint_serial": last_endpoint}
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(
        f"serial did not converge for {container}:{path}; expected={expected_norm} "
        f"file={last_file} endpoint={last_endpoint}"
    )


def agent_info(agent_id: str) -> dict:
    return {
        "detail": api("GET", f"/api/control/agents/{agent_id}/detail"),
        "assignments": api("GET", f"/api/control/agents/{agent_id}/assignments"),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    edges = [
        EdgeTarget(
            container=f"certcp-real-edge-a-{RUN_ID}",
            agent_name=f"real-edge-a-{RUN_ID}",
            processes=[
                ProcessTarget(
                    name="edge-a-main",
                    internal_port=9443,
                    host_port=9551,
                    cert_path="/etc/nginx/certs/edge-a.crt",
                    cn=f"edge-a-{RUN_ID}.example.test",
                )
            ],
        ),
        EdgeTarget(
            container=f"certcp-real-edge-b-{RUN_ID}",
            agent_name=f"real-edge-b-{RUN_ID}",
            processes=[
                ProcessTarget(
                    name="edge-b-main",
                    internal_port=9443,
                    host_port=9552,
                    cert_path="/opt/custom/tls/edge-b.pem",
                    cn=f"renew-{RUN_ID}.example.test",
                )
            ],
        ),
        EdgeTarget(
            container=f"certcp-real-edge-c-{RUN_ID}",
            agent_name=f"real-edge-c-{RUN_ID}",
            processes=[
                ProcessTarget(
                    name="edge-c-one",
                    internal_port=9443,
                    host_port=9553,
                    cert_path="/srv/nginx-one/tls/edge-c-one.crt",
                    cn=f"edge-c-one-{RUN_ID}.example.test",
                ),
                ProcessTarget(
                    name="edge-c-two",
                    internal_port=9444,
                    host_port=9554,
                    cert_path="/srv/nginx-two/tls/edge-c-two.pem",
                    cn=f"edge-c-two-{RUN_ID}.example.test",
                ),
            ],
        ),
    ]

    evidence: dict = {
        "run_id": RUN_ID,
        "control_plane_url": CP_URL,
        "docker_network": DOCKER_NETWORK,
        "edges": [],
        "renewal": {},
        "agent_info": {},
    }

    wait_control_plane()
    build_image()
    delete_stale_agents(edges)
    start_edges(edges)
    agents = approve_agents(edges)

    renew_edge = edges[1]

    for edge in edges:
        agent = agents[edge.agent_name]
        edge_result = {
            "container": edge.container,
            "agent_name": edge.agent_name,
            "agent_id": agent["id"],
            "processes": [],
        }
        if edge == renew_edge:
            edge_result["processes"].append(
                {
                    "process": edge.processes[0].name,
                    "host_port": edge.processes[0].host_port,
                    "cert_path": edge.processes[0].cert_path,
                    "subject_cn": edge.processes[0].cn,
                    "covered_by": "renewal_flow",
                }
            )
            evidence["edges"].append(edge_result)
            continue
        for proc in edge.processes:
            cert = upload_cert(f"{proc.cn}-initial", proc.cn, 45)
            assign(agent["id"], cert["id"], proc.cert_path)
            serials = wait_serial(edge.container, proc.cert_path, proc.host_port, cert["_expected_serial"])
            edge_result["processes"].append(
                {
                    "process": proc.name,
                    "host_port": proc.host_port,
                    "cert_path": proc.cert_path,
                    "subject_cn": proc.cn,
                    "cert_id": cert["id"],
                    "expected_serial": normalize_serial(cert["_expected_serial"]),
                    **serials,
                }
            )
        evidence["edges"].append(edge_result)

    renew_proc = renew_edge.processes[0]
    renew_agent = agents[renew_edge.agent_name]
    old_cert = upload_cert(f"{renew_proc.cn}-old", renew_proc.cn, 10)
    assign(renew_agent["id"], old_cert["id"], renew_proc.cert_path)
    old_serials = wait_serial(
        renew_edge.container,
        renew_proc.cert_path,
        renew_proc.host_port,
        old_cert["_expected_serial"],
    )
    new_cert = upload_cert(f"{renew_proc.cn}-renewed", renew_proc.cn, 120)
    new_serials = wait_serial(
        renew_edge.container,
        renew_proc.cert_path,
        renew_proc.host_port,
        new_cert["_expected_serial"],
    )
    evidence["renewal"] = {
        "agent_name": renew_edge.agent_name,
        "cert_path": renew_proc.cert_path,
        "subject_cn": renew_proc.cn,
        "old_cert_id": old_cert["id"],
        "renewed_cert_id": new_cert["id"],
        "same_cert_record_reused": old_cert["id"] == new_cert["id"],
        "old_expected_serial": normalize_serial(old_cert["_expected_serial"]),
        "old_file_serial": old_serials["file_serial"],
        "renewed_expected_serial": normalize_serial(new_cert["_expected_serial"]),
        "renewed_file_serial": new_serials["file_serial"],
        "renewed_endpoint_serial": new_serials["endpoint_serial"],
    }

    refreshed_agents = {agent["name"]: agent for agent in list_agents() if agent["name"] in {e.agent_name for e in edges}}
    for edge in edges:
        agent = refreshed_agents[edge.agent_name]
        info = agent_info(agent["id"])
        assignments = info["assignments"]
        assignment_count = len(assignments.get("items", [])) if isinstance(assignments, dict) else len(assignments)
        evidence["agent_info"][edge.agent_name] = {
            "id": agent["id"],
            "status": agent["status"],
            "last_seen": agent.get("last_seen"),
            "cert_paths": agent.get("cert_paths"),
            "assignment_count": assignment_count,
            "detail_keys": sorted(info["detail"].keys()),
        }

    OUT_FILE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(f"RESULT_FILE={OUT_FILE}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        raise
