#!/usr/bin/env python3
"""TDD tests for hermes-edit-config helper.

Pure-Python execution test via subprocess against a temp filesystem
with stubbed sudo/chattr (no actual root or immutable bit needed).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "hermes-edit-config.sh"


@pytest.fixture
def harness(tmp_path: Path) -> dict:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "sudo").write_text('#!/bin/bash\nexec "$@"\n')
    (bindir / "chattr").write_text('#!/bin/bash\nexit 0\n')
    for stub in ("sudo", "chattr"):
        (bindir / stub).chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["HOME"] = str(tmp_path)
    return {"env_file": env_file, "env": env, "tmp": tmp_path}


def _run(args, harness, expect_rc=0):
    result = subprocess.run(
        ["bash", str(SCRIPT)] + args,
        capture_output=True, text=True, env=harness["env"], timeout=15,
    )
    assert result.returncode == expect_rc, (
        f"rc={result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result


def test_upsert_appends_new_key(harness):
    _run(["--file", str(harness["env_file"]), "NEW_KEY=newval"], harness)
    content = harness["env_file"].read_text()
    assert "NEW_KEY=newval" in content
    assert "FOO=bar" in content
    assert "BAZ=qux" in content


def test_upsert_updates_existing_key_in_place(harness):
    _run(["--file", str(harness["env_file"]), "FOO=changed"], harness)
    content = harness["env_file"].read_text()
    assert content.count("FOO=changed") == 1
    assert "FOO=bar" not in content
    assert "BAZ=qux" in content


def test_get_returns_existing_value(harness):
    result = _run(["--file", str(harness["env_file"]), "--get", "FOO"], harness)
    assert result.stdout.strip() == "bar"


def test_get_returns_empty_for_missing_key(harness):
    result = _run(["--file", str(harness["env_file"]), "--get", "MISSING"], harness)
    assert result.stdout.strip() == ""


def test_missing_target_file_exits_2(harness):
    _run(["--file", "/nonexistent/path.env", "FOO=x"], harness, expect_rc=2)


def test_backup_preserves_original_contents(harness):
    original = harness["env_file"].read_text()
    _run(["--file", str(harness["env_file"]), "NEW_KEY=val"], harness)
    backups = list(harness["env_file"].parent.glob(".env.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == original


def test_get_returns_latest_when_duplicate_keys(harness):
    harness["env_file"].write_text("FOO=first\nFOO=second\nBAZ=qux\n", encoding="utf-8")
    result = _run(["--file", str(harness["env_file"]), "--get", "FOO"], harness)
    assert result.stdout.strip() == "second"
