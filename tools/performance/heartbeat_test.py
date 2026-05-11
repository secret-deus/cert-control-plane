"""
Agent heartbeat performance test using Locust.

Tests the control plane's ability to handle concurrent agent heartbeats.

Usage:
    # Run with Locust Web UI (default port 8089):
    locust -f heartbeat_test.py --host http://localhost:8080

    # Run headless mode (CI-friendly):
    locust -f heartbeat_test.py --headless --host http://localhost:8080 \
        --users 100 --spawn-rate 10 --run-time 60s

    # Run with custom settings:
    locust -f heartbeat_test.py --headless --host http://localhost:8080 \
        --users 200 --spawn-rate 20 --run-time 5m --html report.html

SLA Targets:
    - p95 response time < 500ms
    - p99 response time < 1000ms
    - Error rate < 1%

Requirements:
    - Python 3.9+
    - locust >= 2.0 (pip install locust)
    - A running Cert Control Plane instance

Environment Variables:
    - PERF_AGENT_TOKEN: Agent token for authentication (default: perf-test-token-12345)
    - PERF_ADMIN_API_KEY: Admin API key (default: test-admin-api-key)
"""

import os
import random
import time

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner

# ---------------------------------------------------------------------------
# SLA Configuration
# ---------------------------------------------------------------------------
SLA_P95_MS = int(os.environ.get("SLA_P95_MS", "500"))
SLA_P99_MS = int(os.environ.get("SLA_P99_MS", "1000"))
SLA_ERROR_RATE_PCT = float(os.environ.get("SLA_ERROR_RATE_PCT", "1.0"))

# ---------------------------------------------------------------------------
# Failure reason counters (custom event tracking)
# ---------------------------------------------------------------------------
failure_categories = {
    "timeout": 0,
    "auth_error": 0,
    "server_error": 0,
    "validation_error": 0,
    "connection_error": 0,
    "unknown": 0,
}


def categorize_failure(response=None, exception=None):
    """Classify failure into a category for reporting."""
    if exception:
        exc_str = str(exception).lower()
        if "timeout" in exc_str or "timed out" in exc_str:
            failure_categories["timeout"] += 1
            return "timeout"
        elif "connection" in exc_str:
            failure_categories["connection_error"] += 1
            return "connection_error"
        else:
            failure_categories["unknown"] += 1
            return "unknown"

    if response is not None:
        status = response.status_code
        if status in (401, 403):
            failure_categories["auth_error"] += 1
            return "auth_error"
        elif status >= 500:
            failure_categories["server_error"] += 1
            return "server_error"
        elif status in (400, 422):
            failure_categories["validation_error"] += 1
            return "validation_error"
        else:
            failure_categories["unknown"] += 1
            return "unknown"

    failure_categories["unknown"] += 1
    return "unknown"


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Check SLA compliance and report failure categories on test completion."""
    stats = environment.runner.stats.total

    # --- Failure category summary ---
    total_failures = sum(failure_categories.values())
    if total_failures > 0:
        print("\n" + "=" * 60)
        print("FAILURE CATEGORY BREAKDOWN")
        print("=" * 60)
        for category, count in sorted(failure_categories.items(), key=lambda x: -x[1]):
            if count > 0:
                pct = (count / total_failures) * 100
                print(f"  {category:<20}: {count:>6} ({pct:.1f}%)")
        print("=" * 60)

    # --- SLA Checks ---
    print("\n" + "=" * 60)
    print("SLA COMPLIANCE CHECK")
    print("=" * 60)

    sla_passed = True

    # p95 check
    p95 = stats.get_response_time_percentile(0.95) or 0
    if p95 > SLA_P95_MS:
        print(f"  [FAIL] p95 latency: {p95:.0f}ms > {SLA_P95_MS}ms")
        sla_passed = False
    else:
        print(f"  [PASS] p95 latency: {p95:.0f}ms <= {SLA_P95_MS}ms")

    # p99 check
    p99 = stats.get_response_time_percentile(0.99) or 0
    if p99 > SLA_P99_MS:
        print(f"  [FAIL] p99 latency: {p99:.0f}ms > {SLA_P99_MS}ms")
        sla_passed = False
    else:
        print(f"  [PASS] p99 latency: {p99:.0f}ms <= {SLA_P99_MS}ms")

    # Error rate check
    total_requests = stats.num_requests + stats.num_failures
    error_rate = (stats.num_failures / total_requests * 100) if total_requests > 0 else 0
    if error_rate > SLA_ERROR_RATE_PCT:
        print(f"  [FAIL] Error rate: {error_rate:.2f}% > {SLA_ERROR_RATE_PCT}%")
        sla_passed = False
    else:
        print(f"  [PASS] Error rate: {error_rate:.2f}% <= {SLA_ERROR_RATE_PCT}%")

    print("=" * 60)
    if not sla_passed:
        print("  ❌ SLA CHECK FAILED")
        environment.process_exit_code = 1
    else:
        print("  ✅ ALL SLA CHECKS PASSED")

    print()


class AgentUser(HttpUser):
    """
    Simulates an agent sending periodic heartbeats.

    Each "user" represents one agent instance.
    """

    wait_time = between(25, 35)  # Simulate 30s heartbeat interval
    weight = 7  # 70% of users are agents

    def on_start(self):
        """Setup: authenticate and get agent token."""
        self.agent_token = os.environ.get("PERF_AGENT_TOKEN", "perf-test-token-12345")
        self.agent_id = f"perf-test-agent-{random.randint(1, 10000)}"

    @task(10)
    def heartbeat(self):
        """Send heartbeat request."""
        with self.client.post(
            "/api/agent/heartbeat",
            json={"status": "ok"},
            headers={"X-Agent-Token": self.agent_token},
            name="/api/agent/heartbeat",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 0:
                category = categorize_failure(exception=response.error)
                response.failure(f"Connection error [{category}]")
            else:
                category = categorize_failure(response=response)
                response.failure(
                    f"Status {response.status_code} [{category}]: "
                    f"{response.text[:200]}"
                )

    @task(3)
    def fetch_certs(self):
        """Simulate certificate sync."""
        cert_paths = [
            f"/etc/nginx/ssl/cert{i}.crt"
            for i in range(random.randint(1, 5))
        ]

        payload = {
            "certs": [
                {"local_path": path, "current_not_after": None}
                for path in cert_paths
            ]
        }

        with self.client.post(
            "/api/agent/fetch-certs",
            json=payload,
            headers={"X-Agent-Token": self.agent_token},
            name="/api/agent/fetch-certs",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "updates" not in data and "certs" not in data:
                    response.failure("Response missing expected fields")
                else:
                    response.success()
            elif response.status_code == 0:
                category = categorize_failure(exception=response.error)
                response.failure(f"Connection error [{category}]")
            else:
                category = categorize_failure(response=response)
                response.failure(
                    f"Status {response.status_code} [{category}]: "
                    f"{response.text[:200]}"
                )

    def on_stop(self):
        """Cleanup."""
        pass


class AdminUser(HttpUser):
    """
    Simulates an admin user checking dashboard and managing agents.
    """

    wait_time = between(5, 15)  # Admin checks every 5-15 seconds
    weight = 3  # 30% of users are admins

    def on_start(self):
        """Setup admin authentication."""
        self.api_key = os.environ.get("PERF_ADMIN_API_KEY", "test-admin-api-key")

    @task(5)
    def get_summary(self):
        """Get dashboard summary."""
        with self.client.get(
            "/api/control/dashboard/summary",
            headers={"X-Admin-API-Key": self.api_key},
            name="/api/control/dashboard/summary",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                category = categorize_failure(response=response)
                response.failure(
                    f"Status {response.status_code} [{category}]: "
                    f"{response.text[:200]}"
                )

    @task(3)
    def list_agents(self):
        """List all agents."""
        with self.client.get(
            "/api/control/agents?limit=50",
            headers={"X-Admin-API-Key": self.api_key},
            name="/api/control/agents",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, (list, dict)):
                    response.failure("Unexpected response format")
                else:
                    response.success()
            else:
                category = categorize_failure(response=response)
                response.failure(
                    f"Status {response.status_code} [{category}]: "
                    f"{response.text[:200]}"
                )

    @task(2)
    def get_agents_health(self):
        """Get agent health status."""
        with self.client.get(
            "/api/control/dashboard/agents-health",
            headers={"X-Admin-API-Key": self.api_key},
            name="/api/control/dashboard/agents-health",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                category = categorize_failure(response=response)
                response.failure(
                    f"Status {response.status_code} [{category}]: "
                    f"{response.text[:200]}"
                )

    @task(1)
    def get_cert_alerts(self):
        """Get certificate alerts."""
        with self.client.get(
            "/api/control/dashboard/cert-alerts",
            headers={"X-Admin-API-Key": self.api_key},
            name="/api/control/dashboard/cert-alerts",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                category = categorize_failure(response=response)
                response.failure(
                    f"Status {response.status_code} [{category}]: "
                    f"{response.text[:200]}"
                )
