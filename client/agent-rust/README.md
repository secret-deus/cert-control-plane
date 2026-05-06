# Cert Agent (Rust)

A high-performance certificate agent written in Rust for the Cert Control Plane.

## Features

- **TOFU Registration**: Automatically register with the control plane using fingerprint-based authentication
- **Certificate Synchronization**: Periodically fetch and deploy certificates
- **Hot Reload**: Automatic service reload after certificate updates
- **Secure Storage**: Private keys stored with restricted permissions (0600)
- **Cross-Platform**: Builds for Linux (amd64, arm64) and macOS (arm64)

## Quick Start

### Download Binary

Download the latest release for your platform:

```bash
# Linux amd64
wget https://github.com/your-org/cert-control-plane/releases/latest/download/cert-agent-linux-amd64

# Linux arm64
wget https://github.com/your-org/cert-control-plane/releases/latest/download/cert-agent-linux-arm64

# macOS arm64
wget https://github.com/your-org/cert-control-plane/releases/latest/download/cert-agent-darwin-arm64

chmod +x cert-agent*
sudo mv cert-agent* /usr/local/bin/cert-agent
```

### Configuration

Create a configuration file at `/etc/cert-agent/agent.toml`:

```toml
# Control plane URL (required)
cp_url = "https://cp.example.com"

# Unique agent name (required)
name = "web-server-01"

# State directory for storing keys and tokens
state_dir = "/var/lib/cert-agent"

# Heartbeat interval in seconds
heartbeat_interval = 30

# Approval polling interval in seconds
poll_interval = 5

# Command to reload TLS service after cert update
reload_cmd = "nginx -s reload"

# Certificate table: maps local paths to cert names
[[cert_table]]
local_path = "/etc/nginx/ssl/api.example.com.crt"
cert_name = "api.example.com"

[[cert_table]]
local_path = "/etc/nginx/ssl/static.example.com.crt"
cert_name = "static.example.com"
```

### Run as Systemd Service

Create `/etc/systemd/system/cert-agent.service`:

```ini
[Unit]
Description=Cert Control Plane Agent
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cert-agent
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cert-agent
sudo systemctl start cert-agent
sudo systemctl status cert-agent
```

## Configuration Reference

### Environment Variables

All configuration options can be set via environment variables with the `CERT_AGENT__` prefix:

```bash
export CERT_AGENT__CP_URL="https://cp.example.com"
export CERT_AGENT__NAME="web-server-01"
export CERT_AGENT__HEARTBEAT_INTERVAL=60
```

### Configuration File Locations

The agent searches for configuration files in this order:

1. `/etc/cert-agent/agent.toml`
2. `./agent.toml` (current directory)
3. Environment variables (highest priority)

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `cp_url` | string | Control plane URL (e.g., `https://cp.example.com`) |
| `name` | string | Unique agent name |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `state_dir` | string | `/var/lib/cert-agent` | Directory for storing keys and tokens |
| `heartbeat_interval` | integer | 30 | Heartbeat interval in seconds |
| `poll_interval` | integer | 5 | Registration polling interval in seconds |
| `reload_cmd` | string | `nginx -s reload` | Command to reload TLS service |
| `cert_table` | array | `[]` | List of certificate mappings |

### Certificate Table

Each entry in the `cert_table` array has the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `local_path` | string | Absolute path where the certificate should be deployed |
| `cert_name` | string | Human-readable name matching the control plane assignment |

## How It Works

### 1. Registration (TOFU)

On first run, the agent:

1. Generates a new RSA 2048-bit key pair
2. Computes the public key fingerprint (SHA-256)
3. Sends registration request to control plane
4. Waits for admin approval
5. Receives and stores `agent_token`

```
[Agent] --name, fingerprint--> [Control Plane]
[Agent] <--pending-- [Control Plane]
... (admin approves) ...
[Agent] --poll status--> [Control Plane]
[Agent] <--approved, agent_token-- [Control Plane]
```

### 2. Heartbeat

The agent periodically sends heartbeat to the control plane:

```json
POST /api/agent/heartbeat
X-Agent-Token: <token>

{
  "status": "ok"
}
```

### 3. Certificate Synchronization

At each heartbeat interval, the agent:

1. Reads local certificate files
2. Extracts `not_after` from each certificate
3. Sends batch request to control plane
4. Receives updates (cert, key, chain)
5. Writes files to disk
6. Reloads TLS service

```
[Agent] --local certs with not_after--> [Control Plane]
[Agent] <--updated certs with new not_after-- [Control Plane]
[Agent] --write to disk--> [Filesystem]
[Agent] --reload command--> [nginx]
```

## Building from Source

### Prerequisites

- Rust 1.70 or later
- Cargo

### Build

```bash
cd agent-rust

# Debug build
cargo build

# Release build (optimized)
cargo build --release

# Cross-compile for Linux
cargo build --release --target x86_64-unknown-linux-musl
```

### Run Tests

```bash
cargo test
```

### Build for Multiple Platforms

Use the provided build script:

```bash
./build-linux.sh
```

This will produce binaries in `dist/`:
- `cert-agent-linux-amd64`
- `cert-agent-linux-arm64` (if cross-compiler available)

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| Config | `/etc/cert-agent/agent.toml` | Agent configuration |
| Private Key | `/var/lib/cert-agent/agent.key` | Agent identity key |
| Agent Token | `/var/lib/cert-agent/agent.token` | Authentication token |

## Security Considerations

### Private Key Storage

- Agent identity key (`agent.key`) is stored with 0600 permissions
- Certificate private keys are written with 0600 permissions
- Only root can read private keys

### Network Security

- All communication uses HTTPS
- Agent token is sent via `X-Agent-Token` header
- Never log or expose the agent token

### File Permissions

```bash
# Verify permissions
ls -la /var/lib/cert-agent/
# Should show:
# -rw------- agent.key
# -rw------- agent.token
```

## Troubleshooting

### Agent Won't Start

1. Check configuration file exists and is valid:
   ```bash
   cat /etc/cert-agent/agent.toml
   ```

2. Verify required fields are set:
   ```bash
   CERT_AGENT__CP_URL=https://cp.example.com \
   CERT_AGENT__NAME=test-agent \
   /usr/local/bin/cert-agent
   ```

3. Check logs:
   ```bash
   RUST_LOG=debug /usr/local/bin/cert-agent
   ```

### Registration Timeout

If registration is pending too long:

1. Check control plane is accessible:
   ```bash
   curl -k https://cp.example.com/healthz
   ```

2. Verify agent appears in control plane dashboard (pending approval)

3. Approve the agent manually

### Certificate Not Updating

1. Check certificate table configuration:
   ```bash
   grep -A 2 "cert_table" /etc/cert-agent/agent.toml
   ```

2. Verify assignments exist in control plane

3. Check file permissions:
   ```bash
   ls -la /etc/nginx/ssl/
   ```

4. Manually trigger fetch:
   ```bash
   curl -k -X POST https://cp.example.com/api/agent/fetch-certs \
     -H "X-Agent-Token: <token>" \
     -H "Content-Type: application/json" \
     -d '{"certs": [{"local_path": "/etc/nginx/ssl/test.crt"}]}'
   ```

## Comparison with Python Agent

| Feature | Rust Agent | Python Agent |
|---------|------------|--------------|
| Binary Size | ~8 MB | ~50 MB (with dependencies) |
| Memory Usage | ~10 MB | ~30-50 MB |
| Startup Time | Instant | ~1-2 seconds |
| Dependencies | Static binary | Python runtime + packages |
| Performance | High | Moderate |
| Ease of Development | Moderate | Easy |

## License

[Your License Here]

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.
