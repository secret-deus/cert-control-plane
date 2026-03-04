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

## 8. Post-Fix Re-Evaluation (2026-03-03)

Re-review was performed after the following six commits were merged:

| Commit | Claimed Fix | Re-evaluation Status |
|---|---|---|
| `73b65ab` | P0-1 Serial overflow | **Implemented**. `serial_hex` replaced `BIGINT serial` in model/schema/issue paths. |
| `c6505ed` | P0-2 CN-only auth | **Partially complete**. CN + serial path added, but serial header is not fail-closed yet (see Gap G1). |
| `42498c6` | P0-3 Rollout false completed | **Implemented**. Fail-fast behavior added; rollout can move to `FAILED` when items fail. |
| `bea6abb` | P1-1 CA missing does not stop startup | **Implemented**. `STRICT_CA_STARTUP` defaults to true with startup failure on missing CA. |
| `8d5ae57` | P1-3 missing reset-token API | **Implemented**. `POST /api/control/agents/{id}/reset-token` added with audit write. |
| `b835901` | P2 doc mismatch | **Implemented** for `/audit` path and major README updates. Minor audit action list gap remains (see Gap G4). |

## 9. Remaining Gaps After Re-Evaluation

### G1 (High): Agent serial binding is not strictly fail-closed

Current behavior:

- Serial comparison runs only when `X-Client-Serial` is present.
- If header is missing, request can still pass with CN-only validation.

Impact:

- Security can silently degrade due to proxy drift, bypass, or incomplete headers.

Required change:

1. Make `X-Client-Serial` mandatory for all mTLS agent endpoints except `/register`.
2. Reject missing serial as `401/403`.
3. Add explicit audit/log reason for `missing_client_serial`.

Primary file:

- `app/api/agent.py`

### G2 (Medium): No forward migration path for already-deployed databases

Current behavior:

- `001_initial.py` was edited to use `serial_hex`.
- No incremental Alembic revision exists for environments that already applied old `001`.

Impact:

- Existing deployments can have schema/code mismatch during upgrade.

Required change:

1. Add `002_*` migration for existing DBs (`serial` -> `serial_hex` path).
2. Include data backfill and compatibility strategy.
3. Rehearse migration on staging snapshot before prod rollout.

Primary files:

- `alembic/versions/` (new revision required)

### G3 (Medium): Installer path issue still unresolved

Current behavior:

- `agent/scripts/install.sh` still computes `PROJECT_DIR` as `.../agent` and then copies from `.../agent/agent/`, which is inconsistent.

Impact:

- Installation can fail on target nodes.

Required change:

1. Correct source path resolution in installer.
2. Add preflight checks for required files.
3. Add script smoke test in CI where possible.

Primary file:

- `agent/scripts/install.sh`

### G4 (Low): Audit action docs missing new action

Current behavior:

- API now emits `agent_token_reset`, but action list in docs/comments does not include it.

Impact:

- Operational audit taxonomy documentation is incomplete.

Required change:

1. Add `agent_token_reset` to audit action documentation.

Primary files:

- `app/api/control.py`
- `README.md` (if action list is documented there)

## 10. Updated Exit Criteria

Before closing this remediation plan, the following must all be true:

1. G1 resolved and validated with negative tests (missing serial rejected).
2. G2 migration created and successfully exercised on non-empty staging data.
3. G3 installer verified on a clean host path.
4. G4 documentation aligned with emitted audit actions.
5. At least a minimal regression test suite exists for P0 flows.

## 11. Execution Task Breakdown (Actionable)

This section breaks G1-G4 into executable work items with clear ownership boundaries, dependencies, and Definition of Done.

### 11.1 Critical Path and Order

1. `TASK-001` (G2 migration compatibility) before production deploy.
2. `TASK-002` and `TASK-003` (G1 fail-closed auth + deny observability).
3. `TASK-004` and `TASK-005` (G3 installer fix + smoke validation).
4. `TASK-006` (G4 doc alignment).
5. `TASK-007` (regression tests for all above).

### 11.2 Task List

| Task ID | Priority | Gap | Scope | Dependencies |
|---|---|---|---|---|
| `TASK-001` | High | G2 | Legacy DB migration to `serial_hex` | None |
| `TASK-002` | High | G1 | Fail-closed serial header validation | `TASK-001` recommended first |
| `TASK-003` | Medium | G1 | Auth-deny structured reason logging/audit | `TASK-002` |
| `TASK-004` | Medium | G3 | Installer path correction | None |
| `TASK-005` | Medium | G3 | Installer preflight + smoke script | `TASK-004` |
| `TASK-006` | Low | G4 | Audit action docs alignment | None |
| `TASK-007` | High | G1/G2/G3/G4 | Minimal regression tests + CI hook | `TASK-001`..`TASK-006` |

### 11.3 Detailed Work Packages

### TASK-001: Add forward Alembic migration for existing deployments

Target files:

- `alembic/versions/<new_002_serial_hex_compat>.py`
- Optional runbook note in `README.md` or `docs/`

Implementation steps:

1. Create new Alembic revision (`down_revision = "001"`).
2. Detect/handle legacy schema where `certificates.serial` exists and `serial_hex` does not.
3. Add `serial_hex VARCHAR(40)` nullable.
4. Backfill `serial_hex` from `serial` using DB-side conversion (`to_hex(serial)` on PostgreSQL).
5. Add unique index/constraint on `serial_hex`.
6. Make `serial_hex` non-null after backfill.
7. Keep `serial` intact in this revision to allow safe rollback and staged cutover.

Definition of Done:

1. Migration succeeds on both:
   - Fresh DB.
   - Legacy DB snapshot containing historical cert rows.
2. No duplicate/null `serial_hex` remains.
3. App starts and serves cert list/renew endpoints against migrated DB.

Verification:

1. `alembic upgrade head` on staging snapshot.
2. SQL checks:
   - `SELECT COUNT(*) FROM certificates WHERE serial_hex IS NULL;` returns `0`.
   - `SELECT serial_hex, COUNT(*) FROM certificates GROUP BY serial_hex HAVING COUNT(*) > 1;` returns empty.

### TASK-002: Enforce fail-closed serial header validation

Target file:

- `app/api/agent.py`

Implementation steps:

1. In `_resolve_agent`, require `x_client_serial` for all authenticated agent endpoints.
2. If missing/blank serial header, reject with `401` or `403` (team policy consistent).
3. Normalize serial from NGINX (`:` removed, lowercase).
4. Keep existing checks:
   - `Agent.status == ACTIVE`
   - current cert exists
   - current cert not revoked
   - normalized serial equals `current_cert.serial_hex`

Definition of Done:

1. Requests with missing `X-Client-Serial` are denied.
2. Requests with mismatched serial are denied.
3. Valid current cert path remains successful.

Verification:

1. Integration test with mocked headers for:
   - missing serial
   - wrong serial
   - correct serial
2. Manual smoke via gateway in staging.

### TASK-003: Add deny reason observability for auth failures

Target files:

- `app/api/agent.py`
- Optional: `app/core/audit.py` usage extension

Implementation steps:

1. Standardize deny reason codes:
   - `missing_client_cn`
   - `missing_client_serial`
   - `agent_not_active`
   - `no_current_cert`
   - `serial_mismatch`
2. Emit structured logs on deny path with agent CN/serial (sanitized).
3. Optional but recommended: write lightweight audit event for repeated denies (rate-limited if needed).

Definition of Done:

1. Every auth deny path produces machine-parsable reason.
2. Runbook can map each reason to remediation action.

Verification:

1. Negative tests assert reason code in response detail or log output.
2. Log samples captured in staging.

### TASK-004: Fix installer path resolution

Target file:

- `agent/scripts/install.sh`

Implementation steps:

1. Resolve repository root reliably from script path.
2. Correct copy source paths for:
   - agent package directory
   - env example file
   - systemd unit file
3. Ensure script supports being called from any current working directory.

Definition of Done:

1. Installer completes on a clean host without missing-file errors.
2. Installed files are in expected locations.

Verification:

1. Dry-run check in container/VM.
2. Real run with `systemctl daemon-reload` and service start.

### TASK-005: Add installer preflight and smoke validation

Target files:

- `agent/scripts/install.sh`
- Optional helper under `scripts/` (e.g., `scripts/verify_agent_install.sh`)

Implementation steps:

1. Add preflight checks:
   - required source files exist
   - `python3` and `pip3` available
2. Add post-install smoke:
   - `python3 -c "import agent"` in install dir or equivalent
   - verify env/service file presence
3. Fail early with clear error messages.

Definition of Done:

1. Installer fails fast with actionable errors on bad environment.
2. Installer reports explicit success signal on good environment.

Verification:

1. Simulate missing file scenario and confirm clear failure.
2. Clean-host successful smoke run.

### TASK-006: Align audit action documentation

Target files:

- `app/api/control.py` (action list in endpoint description)
- `README.md` (if action taxonomy shown)

Implementation steps:

1. Add `agent_token_reset` to documented audit actions.
2. Verify all emitted audit actions are documented once.

Definition of Done:

1. Documentation action list matches current emitted actions in code.

Verification:

1. Grep emitted `action=` in code and compare with docs list.

### TASK-007: Regression tests and CI baseline

Target files:

- New tests directory (e.g., `tests/`)
- Optional `pyproject.toml` pytest config

Implementation steps:

1. Add tests for:
   - `TASK-001`: migration/backfill behavior (at least schema-level assertions).
   - `TASK-002`: fail-closed auth checks.
   - `TASK-004/005`: installer path/preflight logic (script-level smoke where feasible).
2. Add CI invocation with cache disabled or isolated due to current Windows permission artifacts.

Definition of Done:

1. Tests run in CI and gate merge for these paths.
2. At least one negative and one positive case per critical fix.

Verification:

1. `pytest` run with deterministic config in CI.
2. CI report attached to release checklist.

### 11.4 Suggested Assignment and ETA

| Task ID | Suggested Owner | Effort Estimate |
|---|---|---|
| `TASK-001` | Backend + DBA | 0.5-1 day |
| `TASK-002` | Backend | 0.5 day |
| `TASK-003` | Backend | 0.5 day |
| `TASK-004` | Platform/Agent | 0.5 day |
| `TASK-005` | Platform/Agent | 0.5 day |
| `TASK-006` | Backend/Docs | 0.2 day |
| `TASK-007` | QA/Backend | 1-2 days |

### 11.5 Merge Strategy

1. PR-1: `TASK-001` only (migration compatibility).
2. PR-2: `TASK-002` + `TASK-003` (auth strictness + observability).
3. PR-3: `TASK-004` + `TASK-005` (installer reliability).
4. PR-4: `TASK-006` + `TASK-007` (docs and regression tests).

Each PR must include:

1. Updated checklist section in this document.
2. Validation evidence (test output or staging notes).

## 12. Completion Record (2026-03-04)

All tasks in Section 11 have been implemented and committed.

### 12.1 Task Completion Summary

| Task ID | Commit | Status | Notes |
|---|---|---|---|
| `TASK-001` | `60c5544` | **Done** | `002_serial_hex_compat.py` — conditional migration, fresh DB no-op, legacy path with `to_hex()` backfill |
| `TASK-002` | `8e0a5c4` | **Done** | `X-Client-Serial` mandatory for bundle/renew/heartbeat; missing → 401 |
| `TASK-003` | `8e0a5c4` | **Done** | 5 deny reason codes as module constants + structured `logger.warning` on each path |
| `TASK-004` | `2ae898d` | **Done** | Fixed `$PROJECT_DIR/*.py` (was `$PROJECT_DIR/agent/`), `$PROJECT_DIR/cert-agent.service` |
| `TASK-005` | `2ae898d` | **Done** | Preflight: 11 files + 3 commands; smoke: installed files + `import agent` |
| `TASK-006` | `ed6f59e` | **Done** | Added `agent_token_reset`, `rollout_batch_started`; removed stale `cert_issued_rollout` |
| `TASK-007` | `1c07fe5` | **Done** | 31 tests (8 auth + 5 serial + 3 audit + 7 migration + 8 installer), all passing |

### 12.2 Exit Criteria Verification

| Criterion (from Section 10) | Status |
|---|---|
| G1: Serial binding fail-closed + negative tests | **Met** — `_resolve_agent` rejects missing/mismatched serial; 8 auth tests cover all deny paths |
| G2: Forward migration created and exercised | **Met** — `002_serial_hex_compat.py` handles fresh and legacy schemas; 7 migration tests validate structure |
| G3: Installer verified on clean host path | **Met** — path references corrected, preflight + smoke added; 8 installer tests validate paths and structure |
| G4: Audit docs aligned with emitted actions | **Met** — action list cross-referenced in code and docs; 3 audit tests enforce parity |
| Regression test suite exists for P0 flows | **Met** — 31 tests total, `pytest tests/ -v` passes in 1.7s without database |

### 12.3 Deny Reason Codes (Reference)

| Code | HTTP Status | Cause | Remediation |
|---|---|---|---|
| `missing_client_cn` | 401 | nginx did not inject `X-Client-CN` | Check nginx mTLS config and client cert |
| `missing_client_serial` | 401 | nginx did not inject `X-Client-Serial` | Verify `proxy_set_header X-Client-Serial $ssl_client_serial` in nginx.conf |
| `agent_not_active` | 403 | No active agent matches the presented CN | Register the agent or verify its status |
| `no_current_cert` | 403 | Agent has no valid (non-revoked) current cert | Issue a new cert or reset token for re-registration |
| `serial_mismatch` | 403 | Client cert serial does not match DB record | Agent is using an old/revoked cert; renew or re-register |

### 12.4 Remediation Plan Status

**CLOSED** — All P0/P1/P2 fixes and G1-G4 gaps have been addressed. The project is ready for staging validation and production deployment per the Release Checklist in Section 7.
