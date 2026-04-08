"""
Certificate synchronization performance test.

Tests the performance of batch certificate sync operations.
"""

import random
from datetime import datetime, timedelta, timezone
from locust import HttpUser, task, between


class CertSyncUser(HttpUser):
    """
    Simulates an agent performing certificate synchronization.

    Each user represents one agent with multiple certificate paths.
    """

    wait_time = between(25, 35)  # 30s interval

    def on_start(self):
        """Initialize agent with certificate paths."""
        self.agent_token = "perf-test-token-12345"

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
            catch_response=True
        ) as response:
            if response.status_code == 200:
                # Parse response to check for updates
                data = response.json()
                updates = data.get("updates", [])

                # Simulate processing updates
                for update in updates:
                    if update.get("has_update"):
                        # In real scenario, would write files
                        pass

                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(1)
    def heartbeat(self):
        """Send heartbeat to maintain agent status."""
        self.client.post(
            "/api/agent/heartbeat",
            json={"status": "ok"},
            headers={"X-Agent-Token": self.agent_token},
            name="/api/agent/heartbeat"
        )


class HeavySyncUser(HttpUser):
    """
    Simulates agents with many certificates (stress test).

    Each agent manages 20-50 certificate paths.
    """

    wait_time = between(25, 35)

    def on_start(self):
        """Initialize with many certificates."""
        self.agent_token = "heavy-test-token-67890"

        # Large number of certs per agent
        num_certs = random.randint(20, 50)
        self.cert_paths = [
            f"/etc/nginx/ssl/cert{i}.crt"
            for i in range(num_certs)
        ]

    @task
    def heavy_fetch(self):
        """Perform heavy certificate sync."""
        payload = {
            "certs": [
                {"local_path": path, "current_not_after": None}
                for path in self.cert_paths
            ]
        }

        self.client.post(
            "/api/agent/fetch-certs",
            json=payload,
            headers={"X-Agent-Token": self.agent_token},
            name="/api/agent/fetch-certs (heavy)"
        )