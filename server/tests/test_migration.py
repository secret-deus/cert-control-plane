"""Regression tests for TASK-001: migration structure.

Validates that:
- 002 migration file exists with correct revision chain
- Both fresh DB and legacy DB paths are handled
- Schema expectations match the ORM model
"""

import importlib.util
import pathlib
import re

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSIONS_DIR = PROJECT_ROOT / "alembic" / "versions"


def _load_migration(filename: str):
    """Load a migration module by filename."""
    path = VERSIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"migration_{filename}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMigration001:
    def test_001_exists(self):
        assert (VERSIONS_DIR / "001_initial.py").is_file()

    def test_001_uses_serial_hex(self):
        """Fresh 001 should use serial_hex (not serial BIGINT)."""
        text = (VERSIONS_DIR / "001_initial.py").read_text(encoding="utf-8")
        assert "serial_hex" in text
        assert 'sa.String(40)' in text
        # Should NOT have the old BIGINT serial
        assert "BigInteger" not in text


class TestMigration002:
    def test_002_exists(self):
        assert (VERSIONS_DIR / "002_serial_hex_compat.py").is_file()

    def test_002_revision_chain(self):
        mod = _load_migration("002_serial_hex_compat.py")
        assert mod.revision == "002"
        assert mod.down_revision == "001"

    def test_002_has_upgrade_and_downgrade(self):
        mod = _load_migration("002_serial_hex_compat.py")
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)

    def test_002_handles_both_paths(self):
        """Migration source should handle both fresh DB and legacy DB."""
        text = (VERSIONS_DIR / "002_serial_hex_compat.py").read_text(encoding="utf-8")
        # Should check for existing columns
        assert "serial_hex" in text
        assert "serial" in text
        # Should use to_hex for backfill
        assert "to_hex" in text


class TestORMModelAlignment:
    def test_certificate_model_uses_serial_hex(self):
        """ORM Certificate model must use serial_hex, not serial."""
        from app.models import Certificate
        assert hasattr(Certificate, "serial_hex")
        # Verify it's a String column
        col = Certificate.__table__.columns["serial_hex"]
        assert str(col.type) == "VARCHAR(40)"
