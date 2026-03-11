# Cert Control Plane Execution Checklist

Date: 2026-03-04
Source: [fix-plan.md](C:/Users/admin/Documents/github.com/sslagent/cert-control-plane/docs/fix-plan.md)

## A. Completed Items (Merged)

- [x] `P0-1` Serial overflow fix completed (`73b65ab`)
  - `serial` (`BIGINT`) replaced by `serial_hex` (`VARCHAR(40)`) in model/schema/issue paths.
- [x] `P0-2` CN-only auth baseline hardening completed (`c6505ed`)
  - NGINX forwards `X-Client-Serial`; backend validates CN + serial + non-revoked current cert.
- [x] `P0-3` Rollout false-complete bug fixed (`42498c6`)
  - Fail-fast behavior added; failed items can drive rollout to `FAILED`.
- [x] `P1-1` CA startup fail-fast completed (`bea6abb`)
  - `STRICT_CA_STARTUP=true` defaulted and enforced.
- [x] `P1-3` Missing reset-token endpoint completed (`8d5ae57`)
  - Added `POST /api/control/agents/{id}/reset-token` with audit log.
- [x] `P2` README/API path alignment completed (`b835901`)
  - `/api/control/audit-logs` aligned to `/api/control/audit`, plus security notes update.

- [x] `TASK-001` Legacy DB forward migration completed (`60c5544`)
  - Added `002_serial_hex_compat.py` with legacy backfill and fresh-DB no-op path.
- [x] `TASK-002` Fail-closed serial header validation completed (`8e0a5c4`)
  - Missing `X-Client-Serial` now rejected on authenticated agent endpoints.
- [x] `TASK-003` Structured auth deny reasons completed (`8e0a5c4`)
  - Added reason codes: `missing_client_cn`, `missing_client_serial`, `agent_not_active`, `no_current_cert`, `serial_mismatch`.
- [x] `TASK-004` Installer path resolution completed (`2ae898d`)
  - Removed incorrect nested `agent/agent` assumptions.
- [x] `TASK-005` Installer preflight/smoke completed (`2ae898d`)
  - Added file/command preflight and post-install import smoke checks.
- [x] `TASK-006` Audit action docs alignment completed (`ed6f59e`)
  - Added `agent_token_reset` and `rollout_batch_started`, removed stale action docs.
- [x] `TASK-007` Regression test baseline completed (`1c07fe5`)
  - Added 31 tests for G1-G4 flows.

## B. Follow-up Items (Post-Closure, Low Priority)

- [ ] `FOLLOWUP-001` Align agent client docstring with current API response
  - File: `agent/client.py`
  - Current text still says renew returns `serial`; should be `serial_hex`.
- [ ] `FOLLOWUP-002` Set explicit pytest-asyncio fixture loop scope
  - File: `pyproject.toml`
  - Add `asyncio_default_fixture_loop_scope` to eliminate future behavior warning.

## C. Validation Snapshot

- [x] `pytest tests/ -v -p no:cacheprovider` passed (`31 passed`).
- [x] `pytest -q` passed (`31 passed`) with non-blocking warnings.
- [x] `python -m compileall app agent tests scripts` passed.

## D. Done Criteria (Main Remediation)

- [x] Missing serial header is rejected on agent mTLS endpoints.
- [x] Legacy DB has a forward-compatible migration path.
- [x] Installer works with corrected paths and preflight checks.
- [x] Audit action documentation is consistent with emitted actions.
- [x] Regression tests exist and run.

## E. Status

- [x] Main remediation plan is closed.
- [ ] Optional low-priority follow-ups in Section B are pending.
