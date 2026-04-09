"""Regression tests for TASK-004/005: installer path resolution.

Validates that the install.sh script references correct source paths
relative to the agent/ directory layout.
"""

import pathlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CLIENT_DIR = pathlib.Path(__file__).resolve().parent.parent
AGENT_DIR = CLIENT_DIR / "agent"
INSTALL_SCRIPT = AGENT_DIR / "scripts" / "install.sh"
INSTALL_SCRIPT_PS1 = AGENT_DIR / "scripts" / "install.ps1"
AGENT_ENV_EXAMPLE = AGENT_DIR / "agent.env.example"
ROOT_ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
START_SH = PROJECT_ROOT / "start.sh"
STARTUP_PS1 = PROJECT_ROOT / "startup.ps1"


class TestInstallerPaths:
    def test_install_script_exists(self):
        assert INSTALL_SCRIPT.is_file(), f"install.sh not found at {INSTALL_SCRIPT}"

    def test_no_double_agent_path(self):
        """Script must NOT reference $PROJECT_DIR/agent/ (double nesting)."""
        text = INSTALL_SCRIPT.read_text(encoding="utf-8")
        # $PROJECT_DIR already IS agent/, so $PROJECT_DIR/agent/ is wrong
        assert '$PROJECT_DIR/agent/' not in text, (
            "install.sh still references $PROJECT_DIR/agent/ — "
            "PROJECT_DIR is already the agent directory"
        )

    def test_references_correct_service_file(self):
        """Service file should be $PROJECT_DIR/cert-agent.service, not nested."""
        text = INSTALL_SCRIPT.read_text(encoding="utf-8")
        assert '$PROJECT_DIR/cert-agent.service' in text

    def test_references_correct_env_example(self):
        """Env config should be generated to $CONFIG_DIR/agent.env."""
        text = INSTALL_SCRIPT.read_text(encoding="utf-8")
        assert '$CONFIG_DIR/agent.env' in text

    def test_copies_py_files_correctly(self):
        """Script should copy *.py from PROJECT_DIR, not from nested dir."""
        text = INSTALL_SCRIPT.read_text(encoding="utf-8")
        assert '$PROJECT_DIR"/*.py' in text or "$PROJECT_DIR/*.py" in text or \
               '"$PROJECT_DIR"/*.py' in text

    def test_required_source_files_exist(self):
        """All files referenced by preflight checks should exist in repo."""
        expected_files = [
            "__init__.py",
            "__main__.py",
            "runner.py",
            "client.py",
            "config.py",
            "crypto.py",
            "deployer.py",
            "pyproject.toml",
            "agent.env.example",
            "cert-agent.service",
        ]
        for fname in expected_files:
            assert (AGENT_DIR / fname).is_file(), f"Required source file missing: {fname}"

    def test_has_preflight_checks(self):
        """Script must include preflight checks."""
        text = INSTALL_SCRIPT.read_text(encoding="utf-8")
        assert "preflight" in text.lower()
        assert "_require_file" in text or "require_file" in text

    def test_has_smoke_test(self):
        """Script must include post-install smoke test."""
        text = INSTALL_SCRIPT.read_text(encoding="utf-8")
        assert "smoke" in text.lower()
        assert "import agent" in text

    def test_install_ps1_exists(self):
        assert INSTALL_SCRIPT_PS1.is_file(), f"install.ps1 not found at {INSTALL_SCRIPT_PS1}"

    def test_install_scripts_use_current_agent_config_model(self):
        shell_text = INSTALL_SCRIPT.read_text(encoding="utf-8")
        ps_text = INSTALL_SCRIPT_PS1.read_text(encoding="utf-8")

        for text in (shell_text, ps_text):
            assert "CERT_AGENT_CERT_TABLE" in text
            assert "CERT_AGENT_POLL_INTERVAL" in text
            assert "CERT_AGENT_BOOTSTRAP_TOKEN" not in text
            assert "CERT_AGENT_RENEW_BEFORE_DAYS" not in text
            assert "CERT_AGENT_MAX_AUTH_FAILURES" not in text

    def test_agent_env_example_uses_current_fields(self):
        text = AGENT_ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "CERT_AGENT_CP_URL" in text
        assert "CERT_AGENT_NAME" in text
        assert "CERT_AGENT_TOKEN" in text
        assert "CERT_AGENT_CERT_TABLE" in text
        assert "CERT_AGENT_POLL_INTERVAL" in text
        assert "CERT_AGENT_BOOTSTRAP_TOKEN" not in text
        assert "CERT_AGENT_RENEW_BEFORE_DAYS" not in text
        assert "CERT_AGENT_MAX_AUTH_FAILURES" not in text

    def test_root_env_example_has_current_backend_settings(self):
        text = ROOT_ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "CA_KEY_ENCRYPTION_KEY" in text
        assert "ADMIN_API_KEY" in text
        assert "DEFAULT_BATCH_SIZE" in text
        assert "STRICT_CA_STARTUP" not in text
        assert "CERT_VALIDITY_DAYS" not in text
        assert "BOOTSTRAP_TOKEN_EXPIRE_HOURS" not in text

    def test_start_scripts_generate_current_default_env(self):
        shell_text = START_SH.read_text(encoding="utf-8")
        ps_text = STARTUP_PS1.read_text(encoding="utf-8")

        for text in (shell_text, ps_text):
            assert "DEFAULT_BATCH_SIZE=10" in text
            assert "ROLLOUT_ITEM_TIMEOUT_MINUTES=10" in text
            assert "BOOTSTRAP_TOKEN_EXPIRE_HOURS" not in text
            assert "STRICT_CA_STARTUP" not in text
