"""Entry point: python -m agent

Usage:
    # Set environment variables (or write /etc/cert-agent/agent.conf):
    export CERT_AGENT_CP_URL=https://cp.example.com:8443
    export CERT_AGENT_CA_CERT=/etc/cert-agent/ca.crt
    export CERT_AGENT_NAME=web-node-01
    export CERT_AGENT_BOOTSTRAP_TOKEN=abc123...   # first-run only

    # Run:
    python -m agent
"""

import logging
import sys

from agent.config import AgentConfig
from agent.runner import run


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("agent")

    config = AgentConfig.from_env()
    errors = config.validate()
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        sys.exit(1)

    logger.info("cert-agent starting (name=%s, cp=%s)", config.agent_name, config.control_plane_url)
    try:
        run(config)
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
