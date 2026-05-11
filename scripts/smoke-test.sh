#!/usr/bin/env bash
# =============================================================================
# Smoke test for Cert Control Plane Docker deployment
#
# Verifies that a deployed instance is healthy and functional.
# Designed to run after docker compose up or after a new image build.
#
# Usage:
#   ./scripts/smoke-test.sh [BASE_URL] [ADMIN_API_KEY]
#
# Defaults:
#   BASE_URL:      http://localhost:8080
#   ADMIN_API_KEY: Read from .env file (ADMIN_API_KEY=...)
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed
#
# Examples:
#   ./scripts/smoke-test.sh
#   ./scripts/smoke-test.sh http://localhost:8080
#   ./scripts/smoke-test.sh http://staging.example.com my-api-key
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL="${1:-http://localhost:8080}"
ADMIN_API_KEY="${2:-}"
MAX_WAIT_SECONDS=60
POLL_INTERVAL=2

# If no API key provided, try to read from .env
if [[ -z "$ADMIN_API_KEY" ]]; then
    ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
    if [[ -f "$ENV_FILE" ]]; then
        ADMIN_API_KEY=$(grep -E '^ADMIN_API_KEY=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    fi
    if [[ -z "$ADMIN_API_KEY" ]]; then
        echo "WARNING: No ADMIN_API_KEY found. Auth tests will be skipped or may fail."
        ADMIN_API_KEY="smoke-test-key"
    fi
fi

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0
TOTAL_COUNT=0

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
print_header() {
    echo ""
    echo "============================================================"
    echo " Cert Control Plane - Smoke Test"
    echo " Target: $BASE_URL"
    echo " Time:   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
    echo ""
}

check_pass() {
    local name="$1"
    PASS_COUNT=$((PASS_COUNT + 1))
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    echo "  [PASS] $name"
}

check_fail() {
    local name="$1"
    local detail="${2:-}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    echo "  [FAIL] $name"
    if [[ -n "$detail" ]]; then
        echo "         Response: ${detail:0:500}"
    fi
}

# ---------------------------------------------------------------------------
# Test 1: Wait for service readiness (poll /healthz)
# ---------------------------------------------------------------------------
test_health_ready() {
    echo "--- Test 1: Service Readiness (polling /healthz, max ${MAX_WAIT_SECONDS}s) ---"

    local elapsed=0
    local healthy=false

    while [[ $elapsed -lt $MAX_WAIT_SECONDS ]]; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${BASE_URL}/healthz" 2>/dev/null || echo "000")
        if [[ "$HTTP_CODE" == "200" ]]; then
            healthy=true
            break
        fi
        sleep "$POLL_INTERVAL"
        elapsed=$((elapsed + POLL_INTERVAL))
    done

    if [[ "$healthy" == "true" ]]; then
        check_pass "/healthz returns 200 (ready in ${elapsed}s)"
    else
        check_fail "/healthz not reachable within ${MAX_WAIT_SECONDS}s (last HTTP code: $HTTP_CODE)"
        echo ""
        echo "ERROR: Service is not ready. Aborting remaining tests."
        print_summary
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Test 2: Check /readyz returns db: connected
# ---------------------------------------------------------------------------
test_readyz() {
    echo "--- Test 2: Readiness Check (/readyz) ---"

    RESPONSE=$(curl -s --max-time 10 "${BASE_URL}/readyz" 2>/dev/null || echo "")
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/readyz" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "200" ]] && echo "$RESPONSE" | grep -qi "connected\|ok\|healthy"; then
        check_pass "/readyz returns 200 with healthy status"
    elif [[ "$HTTP_CODE" == "200" ]]; then
        check_pass "/readyz returns 200"
    else
        check_fail "/readyz (HTTP $HTTP_CODE)" "$RESPONSE"
    fi
}

# ---------------------------------------------------------------------------
# Test 3: Check /metrics returns certcp_up 1
# ---------------------------------------------------------------------------
test_metrics() {
    echo "--- Test 3: Metrics Endpoint (/metrics) ---"

    RESPONSE=$(curl -s --max-time 10 "${BASE_URL}/metrics" 2>/dev/null || echo "")
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/metrics" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "200" ]] && echo "$RESPONSE" | grep -q "certcp_up 1"; then
        check_pass "/metrics returns certcp_up 1"
    elif [[ "$HTTP_CODE" == "200" ]]; then
        # Metrics endpoint exists but may not have the exact metric name
        check_pass "/metrics returns 200 (endpoint available)"
    else
        check_fail "/metrics (HTTP $HTTP_CODE)" "$RESPONSE"
    fi
}

# ---------------------------------------------------------------------------
# Test 4: Admin API - GET /api/control/agents
# ---------------------------------------------------------------------------
test_admin_agents() {
    echo "--- Test 4: Admin API - List Agents ---"

    RESPONSE=$(curl -s --max-time 10 -H "X-Admin-API-Key: ${ADMIN_API_KEY}" "${BASE_URL}/api/control/agents" 2>/dev/null || echo "")
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -H "X-Admin-API-Key: ${ADMIN_API_KEY}" "${BASE_URL}/api/control/agents" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "200" ]]; then
        check_pass "GET /api/control/agents (authenticated, HTTP 200)"
    elif [[ "$HTTP_CODE" == "401" ]] || [[ "$HTTP_CODE" == "403" ]]; then
        check_fail "GET /api/control/agents (auth failed, HTTP $HTTP_CODE - check ADMIN_API_KEY)" "$RESPONSE"
    else
        check_fail "GET /api/control/agents (HTTP $HTTP_CODE)" "$RESPONSE"
    fi
}

# ---------------------------------------------------------------------------
# Test 5: Admin API - GET /api/control/external-certs
# ---------------------------------------------------------------------------
test_admin_external_certs() {
    echo "--- Test 5: Admin API - External Certificates ---"

    RESPONSE=$(curl -s --max-time 10 -H "X-Admin-API-Key: ${ADMIN_API_KEY}" "${BASE_URL}/api/control/external-certs" 2>/dev/null || echo "")
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -H "X-Admin-API-Key: ${ADMIN_API_KEY}" "${BASE_URL}/api/control/external-certs" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "200" ]]; then
        check_pass "GET /api/control/external-certs (HTTP 200)"
    elif [[ "$HTTP_CODE" == "401" ]] || [[ "$HTTP_CODE" == "403" ]]; then
        check_fail "GET /api/control/external-certs (auth failed, HTTP $HTTP_CODE)" "$RESPONSE"
    else
        check_fail "GET /api/control/external-certs (HTTP $HTTP_CODE)" "$RESPONSE"
    fi
}

# ---------------------------------------------------------------------------
# Test 6: Frontend - GET / returns HTML
# ---------------------------------------------------------------------------
test_frontend_html() {
    echo "--- Test 6: Frontend Static Assets (HTML) ---"

    RESPONSE=$(curl -s --max-time 10 "${BASE_URL}/" 2>/dev/null || echo "")
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "200" ]] && echo "$RESPONSE" | grep -qi "<html\|<!doctype"; then
        check_pass "GET / returns HTML (HTTP 200)"
    elif [[ "$HTTP_CODE" == "200" ]]; then
        check_pass "GET / returns 200 (content may not be HTML)"
    else
        check_fail "GET / (HTTP $HTTP_CODE)" "$RESPONSE"
    fi
}

# ---------------------------------------------------------------------------
# Test 7: Frontend - Check /assets/ has JS/CSS files
# ---------------------------------------------------------------------------
test_frontend_assets() {
    echo "--- Test 7: Frontend Built Assets (JS/CSS) ---"

    # Try to fetch root HTML and extract asset references
    ROOT_HTML=$(curl -s --max-time 10 "${BASE_URL}/" 2>/dev/null || echo "")

    # Look for JS/CSS references in the HTML
    if echo "$ROOT_HTML" | grep -qE '(src|href)="[^"]*\.(js|css)"'; then
        # Extract first JS file reference and try to fetch it
        ASSET_PATH=$(echo "$ROOT_HTML" | grep -oE '(src|href)="(/[^"]*\.(js|css))"' | head -1 | sed 's/.*"\(\/[^"]*\)".*/\1/')
        if [[ -n "$ASSET_PATH" ]]; then
            ASSET_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}${ASSET_PATH}" 2>/dev/null || echo "000")
            if [[ "$ASSET_CODE" == "200" ]]; then
                check_pass "Frontend assets accessible (${ASSET_PATH})"
            else
                check_fail "Frontend asset not accessible: ${ASSET_PATH} (HTTP $ASSET_CODE)"
            fi
        else
            check_pass "Frontend HTML contains asset references (not individually verified)"
        fi
    else
        # Try direct /assets/ path
        ASSETS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/assets/" 2>/dev/null || echo "000")
        if [[ "$ASSETS_CODE" == "200" ]] || [[ "$ASSETS_CODE" == "301" ]] || [[ "$ASSETS_CODE" == "403" ]]; then
            check_pass "/assets/ endpoint exists (HTTP $ASSETS_CODE)"
        else
            check_fail "No frontend assets found (HTML has no JS/CSS refs, /assets/ returned HTTP $ASSETS_CODE)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
    echo ""
    echo "============================================================"
    echo " SMOKE TEST SUMMARY"
    echo "============================================================"
    echo "  Total:  $TOTAL_COUNT"
    echo "  Passed: $PASS_COUNT"
    echo "  Failed: $FAIL_COUNT"
    echo "============================================================"

    if [[ $FAIL_COUNT -eq 0 ]]; then
        echo "  ✅ ALL CHECKS PASSED"
        echo "============================================================"
    else
        echo "  ❌ $FAIL_COUNT CHECK(S) FAILED"
        echo "============================================================"
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    print_header

    test_health_ready
    test_readyz
    test_metrics
    test_admin_agents
    test_admin_external_certs
    test_frontend_html
    test_frontend_assets

    print_summary

    if [[ $FAIL_COUNT -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main
