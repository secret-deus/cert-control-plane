# Cert Control Plane Remediation Plan

Date: 2026-03-03
Scope: Server (`app/`), Agent (`agent/`), NGINX gateway (`nginx/`), schema (`alembic/`), and docs.

## 1. Goals

This plan addresses the highest-risk correctness and security issues discovered in review and defines a phased implementation path.

Release gates for the next production-ready version:

1. Certificate issuance and renewal must not fail due to schema overflow.
2. Revoked or superseded certificates must be denied at runtime, not only marked in DB.
3. Rollout status must accurately report failures and avoid false `completed` states.
4. Startup behavior must fail fast on missing CA in strict mode.

## 2. Priority Issues

| Priority | Issue | Risk | Primary Files |
|---|---|---|---|
| P0 | Certificate serial uses `x509.random_serial_number()` but DB stores `BIGINT` | Registration/renewal can fail at runtime | `app/core/crypto.py`, `app/models.py`, `alembic/versions/001_initial.py` |
| P0 | Agent auth is CN-only; revoked/superseded cert can still pass if CA trusts it | Revocation ineffective; identity binding too weak | `nginx/nginx.conf`, `app/api/agent.py`, `app/registry/store.py` |
| P0 | Rollout can end as `completed` even when items failed | Operational false positive and unsafe rollout reporting | `app/orchestrator/rollout.py` |
| P1 | CA missing at startup only logs warning | Late 500 errors during register/renew | `app/main.py`, `app/core/crypto.py` |
| P1 | Agent install script paths are inconsistent | Installation failure on target nodes | `agent/scripts/install.sh` |
| P1 | Agent recovery log references non-existent endpoint (`reset-token`) | Operator runbook mismatch | `agent/runner.py`, `app/api/control.py` |
| P2 | API docs mismatch (`/api/control/audit-logs` vs `/api/control/audit`) and weak test coverage | Integration friction and regressions | `README.md`, `app/api/control.py`, test suite to be added |

## 3. Phased Delivery

## P0 - Blocking Fixes

### P0-1: Serial number storage redesign

Decision:

- Store certificate serial as canonical lowercase hex string (`serial_hex`) instead of `BIGINT`.
- Keep uniqueness constraint on `serial_hex`.
- Expose serial as string in API responses to avoid integer precision loss in downstream clients.

Implementation:

1. Add DB column `serial_hex VARCHAR(40)` with unique index.
2. Backfill existing rows from `serial` to hex.
3. Update ORM model and schemas to use `serial_hex`.
4. Update issuance paths (`register`, `renew`) to persist `format(serial, "x")`.
5. Keep compatibility temporarily:
   - During migration window, read old `serial` if needed.
   - Remove `serial` only in a follow-up migration after verification.

Acceptance criteria:

1. 100 consecutive register/renew operations succeed with no overflow.
2. DB uniqueness on serial still enforced.
3. API contract clearly documents serial as string.

Rollback:

1. Code rollback is safe if old `serial` column remains intact.
2. If migration fails mid-way, stop writes and restore from DB backup snapshot.

### P0-2: Runtime identity binding to active cert

Decision:

- Strengthen mTLS application-layer validation from `CN-only` to `CN + certificate serial`.
- Trust only the currently active, non-revoked certificate in DB.

Implementation:

1. NGINX (8443) forwards serial from client cert:
   - Add `X-Client-Serial: $ssl_client_serial`.
2. Backend resolver validates:
   - `Agent.name == X-Client-CN`
   - Current certificate for that agent exists
   - Current certificate is not revoked
   - Current certificate serial matches `X-Client-Serial` (normalized hex)
3. Reject requests with stale, revoked, or mismatched certs.
4. Clarify semantics:
   - `revoke` means immediate auth denial for that cert.
   - Rotation uses renewal/rollout flow, not revoke-first workflow.

Acceptance criteria:

1. Old cert is rejected immediately after renewal.
2. Revoked cert is rejected for all agent endpoints.
3. Valid current cert continues to pass heartbeat/renew/bundle.

Rollback:

1. Temporary feature flag `STRICT_AGENT_CERT_BINDING` can disable serial match while keeping logs.
2. If critical incident occurs, revert to CN-only as emergency fallback and audit all accesses.

### P0-3: Rollout terminal-state correctness

Decision:

- `completed` means all items are `COMPLETED` (or intentionally rolled back), not merely terminal.
- Any `FAILED` item must produce rollout-level failure signal.

Implementation:

1. Update orchestration logic:
   - After each batch finishes, if any item in current or prior batches is `FAILED`, mark rollout `FAILED`.
   - Stop scheduling next batches when failed (fail-fast default).
2. Keep `resume` behavior explicit:
   - Either retry failed items first, or require operator to rollback.
3. Add precise audit events:
   - `rollout_failed` includes failed item count and IDs.

Acceptance criteria:

1. Synthetic timeout failure causes rollout `FAILED`, not `COMPLETED`.
2. No new batches are opened after first failure unless operator action occurs.
3. Dashboard/API status aligns with item-level truth.

Rollback:

1. Revert orchestrator logic and re-run from snapshot if false failures spike.

## P1 - Hardening and Operability

### P1-1: Startup strict mode for CA availability

Implementation:

1. Add setting `STRICT_CA_STARTUP=true` (default true outside local dev).
2. On missing/unreadable CA files, fail app startup instead of warning-only.
3. Keep health endpoint but no degraded running mode in strict environment.

### P1-2: Fix agent installer paths and service assumptions

Implementation:

1. Correct `install.sh` source paths for:
   - package directory copy
   - env template copy
   - systemd unit copy
2. Add installer self-checks:
   - verify required files exist before copy
   - verify `python3 -m agent --help` (or import check) in install dir.

### P1-3: Resolve missing reset-token workflow

Implementation options (choose one):

1. Preferred: add `POST /api/control/agents/{id}/reset-token` and audit it.
2. Minimal: update agent logs/runbook to remove non-existent endpoint reference.

Recommendation:

- Implement endpoint because it is operationally necessary for compromised or desynced nodes.

### P1-4: API/doc consistency fixes

Implementation:

1. Align audit endpoint docs and implementation (`/api/control/audit` vs alias route).
2. Clean text encoding issues in README and service comments.

## P2 - Tests, Observability, and Release Hygiene

### P2-1: Test suite baseline

Add automated tests for:

1. Serial persistence and serialization format.
2. Agent auth binding (`CN + serial`) positive/negative paths.
3. Rollout transitions with success, timeout, and failure.
4. Revocation behavior and post-renew old-cert denial.
5. Installer path validation (script-level smoke test where feasible).

### P2-2: Operational telemetry

Add metrics and logs:

1. `agent_auth_denied_total` with reason labels.
2. `rollout_failed_items_total`.
3. `cert_renew_latency_seconds`.
4. Structured logs for cert mismatch (CN, presented serial, expected serial).

## 4. Database Migration Strategy

Recommended zero-downtime sequence:

1. Migration A:
   - Add `certificates.serial_hex` nullable + unique index.
2. Deploy A:
   - Dual-write: write both `serial` and `serial_hex` when possible.
3. Backfill:
   - Convert existing `serial` to hex in batches.
4. Migration B:
   - Make `serial_hex` non-null.
   - Switch reads to `serial_hex` only.
5. Migration C (optional cleanup):
   - Drop old `serial` column once stable.

If environment is non-production or no real data exists, a single migration that replaces `serial` directly is acceptable.

## 5. Validation Matrix

| Scenario | Expected Result |
|---|---|
| Register with new CSR | Certificate issued, serial stored in `serial_hex`, agent active |
| Renew with currently valid cert | New cert issued, old cert denied afterwards |
| Heartbeat with revoked cert | 403/401 denied with explicit reason |
| Rollout item timeout | Item `FAILED`, rollout `FAILED`, no next batch |
| Startup without CA in strict mode | Process exits at startup with clear error |
| Installer on clean host | Paths valid, unit starts successfully |

## 6. Delivery Plan

1. Day 1:
   - P0-1 schema and model changes
   - P0-2 NGINX header + backend auth binding
2. Day 2:
   - P0-3 rollout semantics
   - P1-1 startup strict mode
3. Day 3:
   - P1-2 installer fix
   - P1-3 reset-token endpoint or runbook correction
   - P1-4 docs alignment
4. Day 4:
   - P2 tests and release checklist

## 7. Release Checklist

1. All P0 acceptance criteria passed.
2. Migration rehearsal completed on staging snapshot.
3. Agent backward-compatibility verified for at least one old-version node.
4. Rollout failure simulation executed and observed.
5. Runbook updated for token reset and compromised cert handling.
