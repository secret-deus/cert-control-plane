#!/usr/bin/env bash
# =============================================================================
# One-click performance test runner for Cert Control Plane
#
# Handles the full lifecycle: environment check, service startup, test data
# seeding, Locust execution, and report generation.
#
# Prerequisites:
#   - docker & docker compose
#   - python3
#   - locust (pip install locust)
#
# Usage:
#   ./scripts/run-perf-test.sh [OPTIONS]
#
# Options:
#   --users N        Number of concurrent users (default: 50)
#   --duration Xs    Test duration, e.g. 60s, 5m (default: 60s)
#   --host URL       Target host (default: http://localhost:8080)
#   --test NAME      Test to run: heartbeat, cert_sync, all (default: all)
#   --skip-setup     Skip docker compose and test data setup
#   --skip-cleanup   Skip test data cleanup after run
#   --help           Show this help message
#
# Examples:
#   ./scripts/run-perf-test.sh
#   ./scripts/run-perf-test.sh --users 100 --duration 5m
#   ./scripts/run-perf-test.sh --test heartbeat --users 200
#   ./scripts/run-perf-test.sh --skip-setup --host http://staging:8080
#
# Output:
#   tmp/perf-report-{date}.md  - Markdown performance report
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration & Defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PERF_DIR="$PROJECT_DIR/tools/performance"
TMP_DIR="$PROJECT_DIR/tmp"

USERS=50
DURATION="60s"
HOST="http://localhost:8080"
TEST_NAME="all"
SKIP_SETUP=false
SKIP_CLEANUP=false
SPAWN_RATE=""

ADMIN_API_KEY=""
REPORT_DATE=$(date '+%Y%m%d-%H%M%S')
REPORT_FILE="$TMP_DIR/perf-report-${REPORT_DATE}.md"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --users)
            USERS="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --test)
            TEST_NAME="$2"
            shift 2
            ;;
        --skip-setup)
            SKIP_SETUP=true
            shift
            ;;
        --skip-cleanup)
            SKIP_CLEANUP=true
            shift
            ;;
        --help|-h)
            head -35 "$0" | tail -30
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Calculate spawn rate (10% of users per second, minimum 1)
SPAWN_RATE=$(( USERS / 10 ))
if [[ $SPAWN_RATE -lt 1 ]]; then
    SPAWN_RATE=1
fi

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
info() { echo "[INFO]  $*"; }
warn() { echo "[WARN]  $*"; }
error() { echo "[ERROR] $*" >&2; }

check_command() {
    if ! command -v "$1" &>/dev/null; then
        error "$1 is not installed or not in PATH"
        return 1
    fi
}

wait_for_service() {
    local url="$1"
    local max_wait="${2:-60}"
    local elapsed=0

    info "Waiting for service at $url (max ${max_wait}s)..."
    while [[ $elapsed -lt $max_wait ]]; do
        if curl -s -o /dev/null -w "" --max-time 3 "$url/healthz" 2>/dev/null; then
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url/healthz" 2>/dev/null || echo "000")
            if [[ "$HTTP_CODE" == "200" ]]; then
                info "Service is ready (took ${elapsed}s)"
                return 0
            fi
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    error "Service not ready after ${max_wait}s"
    return 1
}

load_env() {
    local env_file="$PROJECT_DIR/.env"
    if [[ -f "$env_file" ]]; then
        ADMIN_API_KEY=$(grep -E '^ADMIN_API_KEY=' "$env_file" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    fi
    if [[ -z "$ADMIN_API_KEY" ]]; then
        ADMIN_API_KEY="test-admin-api-key"
    fi
}

# ---------------------------------------------------------------------------
# Step 1: Check prerequisites
# ---------------------------------------------------------------------------
step_check_prereqs() {
    info "Checking prerequisites..."

    local missing=0

    if ! check_command docker; then
        missing=$((missing + 1))
    fi

    if ! docker compose version &>/dev/null 2>&1; then
        if ! docker-compose version &>/dev/null 2>&1; then
            error "docker compose (or docker-compose) is not available"
            missing=$((missing + 1))
        fi
    fi

    if ! check_command python3; then
        missing=$((missing + 1))
    fi

    if ! check_command locust; then
        error "locust not found. Install with: pip install locust"
        missing=$((missing + 1))
    fi

    if ! check_command curl; then
        missing=$((missing + 1))
    fi

    if [[ $missing -gt 0 ]]; then
        error "$missing prerequisite(s) missing. Aborting."
        exit 1
    fi

    info "All prerequisites satisfied."
}

# ---------------------------------------------------------------------------
# Step 2: Start docker compose (if needed)
# ---------------------------------------------------------------------------
step_start_services() {
    if [[ "$SKIP_SETUP" == "true" ]]; then
        info "Skipping service setup (--skip-setup)"
        return
    fi

    info "Starting docker compose services..."
    cd "$PROJECT_DIR"

    # Check if services are already running
    if docker compose ps --status running 2>/dev/null | grep -q "server"; then
        info "Services already running."
    else
        docker compose up -d
        info "Docker compose started."
    fi

    # Wait for service to be ready
    wait_for_service "$HOST" 90
}

# ---------------------------------------------------------------------------
# Step 3: Create test data
# ---------------------------------------------------------------------------
step_create_test_data() {
    if [[ "$SKIP_SETUP" == "true" ]]; then
        info "Skipping test data creation (--skip-setup)"
        return
    fi

    info "Creating test data (registering agents, uploading certificates)..."

    # Register a few test agents
    for i in $(seq 1 3); do
        curl -s -X POST "${HOST}/api/agent/register" \
            -H "Content-Type: application/json" \
            -d "{\"hostname\": \"perf-agent-${i}\", \"ip\": \"10.0.0.${i}\", \"os\": \"linux\"}" \
            -o /dev/null 2>/dev/null || true
    done

    # Approve agents via admin API
    AGENTS_JSON=$(curl -s -H "X-Admin-API-Key: ${ADMIN_API_KEY}" "${HOST}/api/control/agents" 2>/dev/null || echo "[]")
    if echo "$AGENTS_JSON" | python3 -c "import sys, json; data=json.load(sys.stdin); [print(a.get('id','')) for a in (data if isinstance(data, list) else data.get('items', data.get('agents', [])))]" 2>/dev/null | head -5 | while read -r AGENT_ID; do
        if [[ -n "$AGENT_ID" ]]; then
            curl -s -X POST "${HOST}/api/control/agents/${AGENT_ID}/approve" \
                -H "X-Admin-API-Key: ${ADMIN_API_KEY}" \
                -o /dev/null 2>/dev/null || true
        fi
    done; then
        true
    fi

    info "Test data created."
}

# ---------------------------------------------------------------------------
# Step 4: Run Locust performance tests
# ---------------------------------------------------------------------------
step_run_tests() {
    info "Running performance tests..."
    info "  Users:     $USERS"
    info "  Duration:  $DURATION"
    info "  Spawn Rate: $SPAWN_RATE/s"
    info "  Host:      $HOST"
    info "  Test:      $TEST_NAME"
    echo ""

    mkdir -p "$TMP_DIR"

    local CSV_PREFIX="$TMP_DIR/perf-stats-${REPORT_DATE}"
    local HTML_REPORT="$TMP_DIR/perf-report-${REPORT_DATE}.html"
    local test_files=()

    case "$TEST_NAME" in
        heartbeat)
            test_files=("$PERF_DIR/heartbeat_test.py")
            ;;
        cert_sync)
            test_files=("$PERF_DIR/cert_sync_test.py")
            ;;
        all)
            test_files=("$PERF_DIR/heartbeat_test.py" "$PERF_DIR/cert_sync_test.py")
            ;;
        *)
            error "Unknown test: $TEST_NAME (use: heartbeat, cert_sync, all)"
            exit 1
            ;;
    esac

    local overall_exit=0

    for test_file in "${test_files[@]}"; do
        local test_basename
        test_basename=$(basename "$test_file" .py)
        info "--- Running: $test_basename ---"

        local csv_out="$TMP_DIR/perf-${test_basename}-${REPORT_DATE}"

        set +e
        locust \
            -f "$test_file" \
            --headless \
            --host "$HOST" \
            --users "$USERS" \
            --spawn-rate "$SPAWN_RATE" \
            --run-time "$DURATION" \
            --csv "$csv_out" \
            --html "${csv_out}.html" \
            --only-summary 2>&1 | tee "$TMP_DIR/perf-${test_basename}-${REPORT_DATE}.log"

        local exit_code=${PIPESTATUS[0]}
        set -e

        if [[ $exit_code -ne 0 ]]; then
            warn "Test $test_basename exited with code $exit_code"
            overall_exit=1
        fi
    done

    return $overall_exit
}

# ---------------------------------------------------------------------------
# Step 5: Generate Markdown report
# ---------------------------------------------------------------------------
step_generate_report() {
    info "Generating performance report: $REPORT_FILE"

    cat > "$REPORT_FILE" <<EOF
# Performance Test Report

- **Date**: $(date '+%Y-%m-%d %H:%M:%S')
- **Host**: $HOST
- **Users**: $USERS
- **Duration**: $DURATION
- **Spawn Rate**: ${SPAWN_RATE}/s
- **Test**: $TEST_NAME

## Summary

EOF

    # Parse CSV stats files and append to report
    local found_stats=false
    for csv_file in "$TMP_DIR"/perf-*-"${REPORT_DATE}"_stats.csv; do
        if [[ ! -f "$csv_file" ]]; then
            continue
        fi
        found_stats=true

        local test_name
        test_name=$(basename "$csv_file" | sed "s/perf-//;s/-${REPORT_DATE}_stats.csv//")

        echo "### Test: $test_name" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        echo "| Metric | Value |" >> "$REPORT_FILE"
        echo "|--------|-------|" >> "$REPORT_FILE"

        # Parse the Aggregated row from CSV
        if grep -q "Aggregated" "$csv_file"; then
            local agg_line
            agg_line=$(grep "Aggregated" "$csv_file")

            # CSV columns: Type,Name,Request Count,Failure Count,Median Response Time,
            # Average Response Time,Min Response Time,Max Response Time,Average Content Size,
            # Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,99%,99.9%,99.99%,100%
            local req_count fail_count median avg_rt min_rt max_rt rps fail_rate p50 p95 p99

            req_count=$(echo "$agg_line" | awk -F',' '{print $3}')
            fail_count=$(echo "$agg_line" | awk -F',' '{print $4}')
            median=$(echo "$agg_line" | awk -F',' '{print $5}')
            avg_rt=$(echo "$agg_line" | awk -F',' '{print $6}')
            min_rt=$(echo "$agg_line" | awk -F',' '{print $7}')
            max_rt=$(echo "$agg_line" | awk -F',' '{print $8}')
            rps=$(echo "$agg_line" | awk -F',' '{print $10}')
            p50=$(echo "$agg_line" | awk -F',' '{print $12}')
            p95=$(echo "$agg_line" | awk -F',' '{print $17}')
            p99=$(echo "$agg_line" | awk -F',' '{print $18}')

            # Calculate failure rate
            if [[ -n "$req_count" ]] && [[ "$req_count" != "0" ]]; then
                fail_rate=$(python3 -c "print(f'{int(${fail_count:-0})/int(${req_count})*100:.2f}%')" 2>/dev/null || echo "N/A")
            else
                fail_rate="N/A"
            fi

            echo "| Total Requests | $req_count |" >> "$REPORT_FILE"
            echo "| Failed Requests | $fail_count |" >> "$REPORT_FILE"
            echo "| Failure Rate | $fail_rate |" >> "$REPORT_FILE"
            echo "| Requests/s (RPS) | $rps |" >> "$REPORT_FILE"
            echo "| p50 Latency (ms) | $p50 |" >> "$REPORT_FILE"
            echo "| p95 Latency (ms) | $p95 |" >> "$REPORT_FILE"
            echo "| p99 Latency (ms) | $p99 |" >> "$REPORT_FILE"
            echo "| Min Latency (ms) | $min_rt |" >> "$REPORT_FILE"
            echo "| Max Latency (ms) | $max_rt |" >> "$REPORT_FILE"
            echo "| Avg Latency (ms) | $avg_rt |" >> "$REPORT_FILE"
        fi

        echo "" >> "$REPORT_FILE"
    done

    if [[ "$found_stats" == "false" ]]; then
        echo "> No CSV stats files found. Check test output logs for details." >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
    fi

    # Add SLA section
    cat >> "$REPORT_FILE" <<EOF
## SLA Targets

| SLA Metric | Target | Status |
|-----------|--------|--------|
| p95 Latency | < 500ms | Check test output |
| p99 Latency | < 1000ms | Check test output |
| Error Rate | < 1% | Check test output |

## Configuration

\`\`\`
Users: $USERS
Duration: $DURATION
Spawn Rate: ${SPAWN_RATE}/s
Host: $HOST
Test: $TEST_NAME
\`\`\`

## Files

- Logs: \`tmp/perf-*-${REPORT_DATE}.log\`
- CSV Stats: \`tmp/perf-*-${REPORT_DATE}_stats.csv\`
- HTML Report: \`tmp/perf-*-${REPORT_DATE}.html\`
EOF

    info "Report saved to: $REPORT_FILE"
}

# ---------------------------------------------------------------------------
# Step 6: Cleanup test data (optional)
# ---------------------------------------------------------------------------
step_cleanup() {
    if [[ "$SKIP_CLEANUP" == "true" ]]; then
        info "Skipping cleanup (--skip-cleanup)"
        return
    fi

    info "Cleaning up test data..."

    # Remove test agents (best effort)
    AGENTS_JSON=$(curl -s -H "X-Admin-API-Key: ${ADMIN_API_KEY}" "${HOST}/api/control/agents" 2>/dev/null || echo "[]")
    echo "$AGENTS_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    agents = data if isinstance(data, list) else data.get('items', data.get('agents', []))
    for a in agents:
        if a.get('hostname','').startswith('perf-agent-'):
            print(a.get('id',''))
except: pass
" 2>/dev/null | while read -r AGENT_ID; do
        if [[ -n "$AGENT_ID" ]]; then
            curl -s -X DELETE "${HOST}/api/control/agents/${AGENT_ID}" \
                -H "X-Admin-API-Key: ${ADMIN_API_KEY}" \
                -o /dev/null 2>/dev/null || true
        fi
    done

    info "Cleanup complete."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo ""
    echo "============================================================"
    echo " Cert Control Plane - Performance Test Runner"
    echo " $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
    echo ""

    load_env
    step_check_prereqs
    step_start_services
    step_create_test_data

    local test_exit=0
    step_run_tests || test_exit=$?

    step_generate_report
    step_cleanup

    echo ""
    echo "============================================================"
    if [[ $test_exit -eq 0 ]]; then
        echo " ✅ Performance tests completed successfully"
    else
        echo " ⚠️  Performance tests completed with warnings (exit: $test_exit)"
    fi
    echo " Report: $REPORT_FILE"
    echo "============================================================"
    echo ""

    exit $test_exit
}

main
