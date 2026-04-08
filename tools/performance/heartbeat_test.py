"""
Agent heartbeat performance test using Locust.

Tests the control plane's ability to handle concurrent agent heartbeats.
"""

import random
from locust import HttpUser, task, between
from locust.runners import logger


class AgentUser(HttpUser):
    """
    Simulates an agent sending periodic heartbeats.

    Each "user" represents one agent instance.
    """

    wait_time = between(25, 35)  # Simulate 30s heartbeat interval

    def on_start(self):
        """Setup: authenticate and get agent token."""
        self.agent_token = None
        self.agent_id = None

        # Mock agent registration
        self.agent_id = f"perf-test-agent-{random.randint(1, 10000)}"

        # In a real test, you would:
        # 1. Register the agent
        # 2. Get approved
        # 3. Store the agent_token

        # For testing, use a pre-generated token
        self.agent_token = "perf-test-token-12345"

    @task(10)
    def heartbeat(self):
        """Send heartbeat request."""
        self.client.post(
            "/api/agent/heartbeat",
            json={"status": "ok"},
            headers={"X-Agent-Token": self.agent_token},
            name="/api/agent/heartbeat"
        )

    @task(3)
    def fetch_certs(self):
        """Simulate certificate sync."""
        # Mock certificate paths
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

        self.client.post(
            "/api/agent/fetch-certs",
            json=payload,
            headers={"X-Agent-Token": self.agent_token},
            name="/api/agent/fetch-certs"
        )

    def on_stop(self):
        """Cleanup."""
        # In a real test, you would cleanup the test agent
        pass


class AdminUser(HttpUser):
    """
    Simulates an admin user checking dashboard and managing agents.
    """

    wait_time = between(5, 15)  # Admin checks every 5-15 seconds

    def on_start(self):
        """Setup admin authentication."""
        self.api_key = "test-admin-api-key"

    @task(5)
    def get_summary(self):
        """Get dashboard summary."""
        self.client.get(
            "/api/control/dashboard/summary",
            headers={"X-Admin-API-Key": self.api_key},
            name="/api/control/dashboard/summary"
        )

    @task(3)
    def list_agents(self):
        """List all agents."""
        self.client.get(
            "/api/control/agents?limit=50",
            headers={"X-Admin-API-Key": self.api_key},
            name="/api/control/agents"
        )

    @task(2)
    def get_agents_health(self):
        """Get agent health status."""
        self.client.get(
            "/api/control/dashboard/agents-health",
            headers={"X-Admin-API-Key": self.api_key},
            name="/api/control/dashboard/agents-health"
        )

    @task(1)
    def get_cert_alerts(self):
        """Get certificate alerts."""
        self.client.get(
            "/api/control/dashboard/cert-alerts",
            headers={"X-Admin-API-Key": self.api_key},
            name="/api/control/dashboard/cert-alerts"
        )
