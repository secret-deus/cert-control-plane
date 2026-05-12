"""Smoke tests for local certificate deployment and rollback behavior."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from agent.runner import _deploy_cert_update


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _make_config(reload_cmd: str = "nginx -s reload"):
    return SimpleNamespace(nginx_reload_cmd=reload_cmd)


def test_deploy_cert_update_success(tmp_path: Path):
    local_path = tmp_path / "nginx" / "api.crt"
    key_path = local_path.with_suffix(".key")
    chain_path = local_path.with_suffix(".chain.crt")

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text("old-cert", encoding="utf-8")
    key_path.write_text("old-key", encoding="utf-8")

    update = {
        "local_path": str(local_path),
        "cert_pem": "new-cert",
        "key_pem": "new-key",
        "chain_pem": "new-chain",
    }

    with patch("subprocess.run", return_value=Mock(returncode=0, stderr="")) as run_mock:
        _deploy_cert_update(_make_config("reload-ok"), update)

    run_mock.assert_called_once()
    assert _read(local_path) == "new-cert\nnew-chain\n"
    assert _read(key_path) == "new-key"
    assert not chain_path.exists()
    assert not local_path.with_suffix(".crt.old").exists()
    assert not key_path.with_suffix(".key.old").exists()
    assert not chain_path.with_suffix(".chain.crt.old").exists()


def test_deploy_cert_update_runs_reload_without_shell(tmp_path: Path):
    local_path = tmp_path / "nginx" / "api.crt"
    local_path.parent.mkdir(parents=True, exist_ok=True)

    update = {
        "local_path": str(local_path),
        "cert_pem": "new-cert",
    }

    with patch("subprocess.run", return_value=Mock(returncode=0, stderr="")) as run_mock:
        _deploy_cert_update(_make_config("nginx -s reload"), update)

    run_mock.assert_called_once_with(
        ["nginx", "-s", "reload"],
        shell=False,
        capture_output=True,
        text=True,
    )


def test_deploy_cert_update_restores_files_on_reload_failure(tmp_path: Path):
    local_path = tmp_path / "nginx" / "api.crt"
    key_path = local_path.with_suffix(".key")
    chain_path = local_path.with_suffix(".chain.crt")

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text("old-cert", encoding="utf-8")
    key_path.write_text("old-key", encoding="utf-8")
    chain_path.write_text("old-chain", encoding="utf-8")

    update = {
        "local_path": str(local_path),
        "cert_pem": "new-cert",
        "key_pem": "new-key",
        "chain_pem": "new-chain",
    }

    with patch("subprocess.run", return_value=Mock(returncode=1, stderr="reload failed")):
        with pytest.raises(RuntimeError, match="nginx reload failed"):
            _deploy_cert_update(_make_config("reload-fail"), update)

    assert _read(local_path) == "old-cert"
    assert _read(key_path) == "old-key"
    assert _read(chain_path) == "old-chain"
    assert not local_path.with_suffix(".crt.old").exists()
    assert not key_path.with_suffix(".key.old").exists()
    assert not chain_path.with_suffix(".chain.crt.old").exists()
