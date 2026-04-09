"""Regression test for TASK-006: audit action documentation alignment.

Verifies that every action= string emitted in the codebase appears in the
documented action list of the GET /audit endpoint description.
"""

import ast
import pathlib
import re

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _extract_emitted_actions() -> set[str]:
    """Walk Python files and extract all ``action="..."`` string values."""
    actions: set[str] = set()
    pattern = re.compile(r'action\s*=\s*"([^"]+)"')
    for py_file in PROJECT_ROOT.joinpath("app").rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            actions.add(match.group(1))
    # Exclude non-audit action references (e.g. pending_action="renew")
    actions.discard("renew")
    return actions


def _extract_documented_actions() -> set[str]:
    """Parse the documented action list from the GET /audit endpoint description."""
    control_py = PROJECT_ROOT / "app" / "api" / "control.py"
    text = control_py.read_text(encoding="utf-8")

    # Find the description block containing documented audit actions.
    # Look for the backtick-delimited action names.
    pattern = re.compile(r"`(\w+)`")
    in_audit_description = False
    actions: set[str] = set()

    for line in text.splitlines():
        if "覆盖的操作" in line:
            in_audit_description = True
            continue
        if in_audit_description:
            matches = pattern.findall(line)
            if matches:
                actions.update(matches)
            elif line.strip() == '"""' or line.strip() == "":
                if actions:
                    break  # End of the action list block

    return actions


class TestAuditActionAlignment:
    def test_all_emitted_actions_are_documented(self):
        """Every action emitted in code must appear in the documented list."""
        emitted = _extract_emitted_actions()
        documented = _extract_documented_actions()

        missing = emitted - documented
        assert not missing, (
            f"Actions emitted in code but not documented: {missing}. "
            f"Update the GET /audit endpoint description in control.py."
        )

    def test_no_stale_documented_actions(self):
        """Every documented action should actually be emitted somewhere in code."""
        emitted = _extract_emitted_actions()
        documented = _extract_documented_actions()

        stale = documented - emitted
        assert not stale, (
            f"Actions documented but never emitted in code: {stale}. "
            f"Remove stale entries or implement the missing code path."
        )

    def test_documented_actions_not_empty(self):
        """Sanity check: the parser found some documented actions."""
        documented = _extract_documented_actions()
        assert len(documented) >= 10, (
            f"Expected at least 10 documented actions, found {len(documented)}. "
            f"The parser may be broken."
        )
