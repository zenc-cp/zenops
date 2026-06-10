"""Tests for the claw-runtime git-hardening scripts (zenc-cp/zenops#1).

Drives the bash scripts via subprocess so the artifacts shipped to nanoclaw-az
are tested as-is. Skipped automatically if bash is not on PATH (e.g. plain
Windows hosts without Git-for-Windows).
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy"
PRE_COMMIT = DEPLOY / "claw-runtime-pre-commit-hook.sh"
DRIFT = DEPLOY / "claw-runtime-drift-check.sh"
INIT = DEPLOY / "claw-runtime-git-init.sh"


def _find_bash() -> str | None:
    """Prefer a real bash; fall back to Git-for-Windows bash on Windows hosts.

    The WindowsApps `bash.exe` shim launches the Microsoft Store WSL installer
    when no distro is registered, which hangs forever in CI / non-interactive
    runs — skip it explicitly.
    """
    candidates = []
    found = shutil.which("bash")
    if found and "WindowsApps" not in found:
        candidates.append(found)
    for extra in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        "/bin/bash",
        "/usr/bin/bash",
    ):
        if Path(extra).exists() and extra not in candidates:
            candidates.append(extra)
    return candidates[0] if candidates else None


BASH = _find_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def _to_bash_path(p: Path | str) -> str:
    """Convert a Windows path to a bash-friendly form when needed."""
    s = str(p)
    if os.name == "nt" and BASH and "Git" in BASH and len(s) > 2 and s[1] == ":":
        drive = s[0].lower()
        return "/" + drive + s[2:].replace("\\", "/")
    return s


# ---------------------------------------------------------------- pre-commit --

BYPASS_DIFF = textwrap.dedent(
    """\
    diff --git a/mcp-server.py b/mcp-server.py
    index 1111111..2222222 100644
    --- a/mcp-server.py
    +++ b/mcp-server.py
    @@ -42,3 +42,4 @@ def _check_auth(request):
    -    token = request.headers.get("Authorization")
    -    return token == EXPECTED_BEARER
    +    return True
    """
)

CLEAN_DIFF = textwrap.dedent(
    """\
    diff --git a/mcp-server.py b/mcp-server.py
    index 1111111..3333333 100644
    --- a/mcp-server.py
    +++ b/mcp-server.py
    @@ -100,3 +100,4 @@ def list_models():
    -    return models
    +    # cosmetic: docstring tweak
    +    return models
    """
)

PASS_BYPASS_DIFF = textwrap.dedent(
    """\
    diff --git a/mcp-server.py b/mcp-server.py
    --- a/mcp-server.py
    +++ b/mcp-server.py
    @@ -42,3 +42,4 @@ def _check_auth(request):
    -    return token == EXPECTED_BEARER
    +    pass
    """
)


def _run_pre_commit(diff_text: str, tmp_path: Path) -> subprocess.CompletedProcess:
    diff_file = tmp_path / "fake.diff"
    diff_file.write_text(diff_text)
    env = {**os.environ, "DIFF_OVERRIDE": _to_bash_path(diff_file)}
    return subprocess.run(
        [BASH, _to_bash_path(PRE_COMMIT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def test_pre_commit_warns_on_return_true_bypass(tmp_path):
    res = _run_pre_commit(BYPASS_DIFF, tmp_path)
    assert res.returncode == 0, res.stderr
    assert "WARN" in res.stderr
    assert "_check_auth" in res.stderr
    assert "return True" in res.stderr


def test_pre_commit_warns_on_pass_bypass(tmp_path):
    res = _run_pre_commit(PASS_BYPASS_DIFF, tmp_path)
    assert res.returncode == 0
    assert "WARN" in res.stderr
    assert "pass" in res.stderr


def test_pre_commit_silent_on_clean_diff(tmp_path):
    res = _run_pre_commit(CLEAN_DIFF, tmp_path)
    assert res.returncode == 0
    assert "WARN" not in res.stderr


def test_pre_commit_silent_on_empty_diff(tmp_path):
    res = _run_pre_commit("", tmp_path)
    assert res.returncode == 0
    assert res.stderr.strip() == ""


# ----------------------------------------------------------------- drift -----


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def _seed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "claw"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "mcp-server.py").write_text("# initial\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def _run_drift(repo: Path, threshold: int) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "CLAW_DIR": _to_bash_path(repo),
        "DRIFT_MAX_MINUTES": str(threshold),
    }
    return subprocess.run(
        [BASH, _to_bash_path(DRIFT)],
        env=env,
        capture_output=True,
        text=True,
    )


def test_drift_clean_tree_exits_zero_silent(tmp_path):
    repo = _seed_repo(tmp_path)
    res = _run_drift(repo, threshold=15)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert res.stdout.strip() == ""


def test_drift_recent_dirty_tree_within_grace_exits_zero(tmp_path):
    repo = _seed_repo(tmp_path)
    (repo / "mcp-server.py").write_text("# edited just now\n")
    res = _run_drift(repo, threshold=15)
    assert res.returncode == 0
    assert "DRIFT" not in res.stdout


def test_drift_old_dirty_tree_exits_two_with_file_list(tmp_path):
    repo = _seed_repo(tmp_path)
    target = repo / "mcp-server.py"
    target.write_text("# stale edit\n")
    past = time.time() - 30 * 60
    os.utime(target, (past, past))
    res = _run_drift(repo, threshold=15)
    assert res.returncode == 2, (res.stdout, res.stderr)
    assert "DRIFT ALARM" in res.stdout
    assert "mcp-server.py" in res.stdout


# ------------------------------------------------------------------ init -----


def test_init_is_idempotent_and_creates_repo(tmp_path):
    claw = tmp_path / "claw"
    claw.mkdir()
    (claw / "mcp-server.py").write_text("# placeholder\n")
    env = {**os.environ, "CLAW_DIR": _to_bash_path(claw)}

    r1 = subprocess.run([BASH, _to_bash_path(INIT)], env=env, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    assert (claw / ".git").is_dir()
    assert (claw / ".gitignore").exists()

    log_before = subprocess.run(
        ["git", "-C", str(claw), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    r2 = subprocess.run([BASH, _to_bash_path(INIT)], env=env, capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr

    log_after = subprocess.run(
        ["git", "-C", str(claw), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert log_before == log_after


def test_scripts_start_with_bash_shebang():
    for script in (INIT, PRE_COMMIT, DRIFT):
        assert script.exists(), script
        first = script.read_text().splitlines()[0]
        assert first.startswith("#!/usr/bin/env bash"), (script, first)
        _ = stat.S_IXUSR
