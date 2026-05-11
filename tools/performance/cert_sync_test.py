"""
Certificate synchronization performance test.

Tests the performance of batch certificate sync operations,
simulating agents with varying numbers of managed certificates.

Usage:
    # Run with Locust Web UI (default port 8089):
    locust -f cert_sync_test.py --host http://localhost:8080

    # Run headless mode (CI-friendly):
    locust -f cert_sync_test.py --headless --host http://localhost:8080 \
        --users 100 --spawn-rate 10 --run-time 60s

    # Stress test with heavy sync users:
    locust -f cert_sync_test.py --headless --host http://localhost:8080 \
        --users 50 --spawn-rate 5 --run-time 5m --html report.html

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
    - SLA_P95_MS: p95 latency threshold in ms (default: 500)
    - SLA_P99_MS: p99 latency threshold in ms (default: 1000)
    - SLA_ERROR_RATE_PCT: Max error rate percentage (default: 1.0)
"""

import os
import random
from datetime import datetime, timedelta, timezone

from locust import HttpUser, task, between, events

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
    "payload_too_large": 0,
    "unexpected_response": 0,
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
        elif status == 413:
            failure_categories["payload_too_large"] += 1
            return "payload_too_large"
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


class CertSyncUser(HttpUser):
    """
    Simulates an agent performing certificate synchronization.

    Each user represents one agent with multiple certificate paths.
    """

    wait_time = between(25, 35)  # 30s interval
    weight = 6  # 60% normal sync users

    def on_start(self):
        """Initialize agent with certificate paths."""
        self.agent_token = os.environ.get("PERF_AGENT_TOKEN", "perf-test-token-12345")

        # Simulate different numbers of certificates per agent
        num_certs = random.choices(
            [1, 2, 3, 5, 10],
            weights=[30, 30, 20, 15, 5]
        )[0]

        self.cert_paths = [
            f"/etc/nginx/ssl/cert{i}.crt"
            for i in range(num_certs)
        ]

        # Initialize with random timestamps
        now = datetime.now(tz=timezone.utc)
        self.cert_not_after = [
            (now + timedelta(days=random.randint(10, 365))).isoformat()
            for _ in range(num_certs)
        ]

    @task(10)
    def fetch_certs(self):
        """Perform certificate sync."""
        payload = {
            "certs": [
                {
                    "local_path": path,
                    "current_not_after": not_after
                }
                for path, not_after in zip(self.cert_paths, self.cert_not_after)
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
                try:
                    data = response.json()
                except Exception:
                    failure_categories["unexpected_response"] += 1
                    response.failure("Invalid JSON response")
                    return

                # Validate response structure
                if "updates" not in data and "certs" not in data:
                    failure_categories["unexpected_response"] += 1
                    response.failure("Response missing 'updates' or 'certs' field")
                    return

                # Simulate processing updates
                updates = data.get("updates", data.get("certs", []))
                for update in updates:
                    if isinstance(update, dict) and update.get("has_update"):
                        pass  # In real scenario, would write files

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

    @task(1)
    def heartbeat(self):
        """Send heartbeat to maintain agent status."""
        with self.client.post(
            "/api/agent/heartbeat",
            json={"status": "ok"},
            headers={"X-Agent-Token": self.agent_token},
            name="/api/agent/heartbeat",
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


class HeavySyncUser(HttpUser):
    """
    Simulates agents with many certificates (stress test).

    Each agent manages 20-50 certificate paths.
    """

    wait_time = between(25, 35)
    weight = 4  # 40% heavy sync users

    def on_start(self):
        """Initialize with many certificates."""
        self.agent_token = os.environ.get("PERF_AGENT_TOKEN", "heavy-test-token-67890")

        # Large number of certs per agent
        num_certs = random.randint(20, 50)
        self.cert_paths = [
            f"/etc/nginx/ssl/cert{i}.crt"
            for i in range(num_certs)
        ]

        now = datetime.now(tz=timezone.utc)
        self.cert_not_after = [
            (now + timedelta(days=random.randint(5, 180))).isoformat()
            for _ in range(num_certs)
        ]

    @task
    def heavy_fetch(self):
        """Perform heavy certificate sync."""
        payload = {
            "certs": [
                {
                    "local_path": path,
                    "current_not_after": not_after,
                }
                for path, not_after in zip(self.cert_paths, self.cert_not_after)
            ]
        }

        with self.client.post(
            "/api/agent/fetch-certs",
            json=payload,
            headers={"X-Agent-Token": self.agent_token},
            name="/api/agent/fetch-certs (heavy)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    response.success()
                except Exception:
                    failure_categories["unexpected_response"] += 1
                    response.failure("Invalid JSON response for heavy payload")
            elif response.status_code == 413:
                category = categorize_failure(response=response)
                response.failure(f"Payload too large [{category}]")
            elif response.status_code == 0:
                category = categorize_failure(exception=response.error)
                response.failure(f"Connection error [{category}]")
            else:
                category = categorize_failure(response=response)
                response.failure(
                    f"Status {response.status_code} [{category}]: "
                    f"{response.text[:200]}"
                )
