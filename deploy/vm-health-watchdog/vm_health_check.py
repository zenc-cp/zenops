"""VM health watchdog — runs on nanoclaw-az via systemd timer.

Silent on success. Posts to Teams incoming webhook on failure.

Usage (CLI):
    WEBHOOK_URL=https://outlook.office.com/webhook/... \
        python3 vm_health_check.py

Exit codes:
    0 — all probes OK (silent)
    1 — at least one probe failed; alert posted
    2 — alert needed but WEBHOOK_URL unset (misconfig)
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List
from urllib.request import urlopen, Request


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Decision:
    alert: bool
    failed: List[ProbeResult] = field(default_factory=list)


# --- pure decision layer (unit-tested) ----------------------------------

def decide(results: List[ProbeResult]) -> Decision:
    failed = [r for r in results if not r.ok]
    return Decision(alert=bool(failed), failed=failed)


def format_alert(decision: Decision, host: str, now_iso: str) -> str:
    lines = [
        f"\u26a0\ufe0f VM health alert",
        f"host: {host}",
        f"ts:   {now_iso}",
        "failed:",
    ]
    for r in decision.failed:
        lines.append(f"  - {r.name}: {r.detail}")
    return "\n".join(lines)


# --- probe primitives (unit-tested with mocks) --------------------------

def probe_http(name: str, url: str, timeout: float = 5.0) -> ProbeResult:
    try:
        with urlopen(url, timeout=timeout) as resp:
            status = getattr(resp, "status", 0)
            if 200 <= status < 300:
                return ProbeResult(name=name, ok=True, detail=f"HTTP {status}")
            return ProbeResult(name=name, ok=False, detail=f"HTTP {status}")
    except Exception as e:
        return ProbeResult(name=name, ok=False, detail=str(e))


def probe_systemd_active(unit: str) -> ProbeResult:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=5,
        )
        state = (r.stdout or "").strip()
        if r.returncode == 0 and state == "active":
            return ProbeResult(name=unit, ok=True, detail=state)
        return ProbeResult(name=unit, ok=False, detail=state or (r.stderr or "").strip())
    except Exception as e:
        return ProbeResult(name=unit, ok=False, detail=str(e))


def probe_tcp(name: str, host: str, port: int, timeout: float = 3.0) -> ProbeResult:
    """Probe TCP reachability — for services with no HTTP health route.

    Catches the class of outage where a process is `systemctl active` but
    its inner socket never bound (e.g. hermes-gateway api_server platform
    refusing to start without API_SERVER_KEY, where the service unit still
    reports active because the parent process is up). See claw-stack-jp#165.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return ProbeResult(name=name, ok=True, detail=f"{host}:{port} reachable")
    except Exception as e:
        return ProbeResult(name=name, ok=False, detail=f"{host}:{port} {e}")


# --- collection + delivery ----------------------------------------------

def collect_probes() -> List[ProbeResult]:
    """Default probe set for nanoclaw-az. Overridden in tests."""
    return [
        probe_systemd_active("azure-auth-shim"),
        probe_systemd_active("design-e"),
        probe_systemd_active("hermes-gateway"),
        probe_systemd_active("hermes-workspace"),
        probe_systemd_active("zenops-consumer"),
        probe_http("shim", "http://127.0.0.1:8403/v1/models"),
        probe_http("hermes-workspace", "http://127.0.0.1:8092/health"),
        # claw-stack-jp#165: hermes-gateway api_server platform binds 8642 only
        # when API_SERVER_KEY is set. Outage 2026-06-03 to 2026-06-12 went
        # undetected because the service unit stayed "active" — only the
        # inner platform refused to start. TCP probe catches this class.
        probe_tcp("hermes-api-server", "127.0.0.1", 8642),
    ]


def post_webhook(url: str, text: str, timeout: float = 10.0) -> int:
    """POST a Teams-incoming-webhook MessageCard JSON. Returns HTTP status."""
    payload = json.dumps({"text": text}).encode("utf-8")
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return getattr(resp, "status", 0)


# --- entrypoint ---------------------------------------------------------

def main() -> int:
    results = collect_probes()
    decision = decide(results)
    if not decision.alert:
        return 0
    webhook = os.environ.get("WEBHOOK_URL", "").strip()
    if not webhook:
        sys.stderr.write("WEBHOOK_URL unset; cannot send alert\n")
        return 2
    host = socket.gethostname()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    msg = format_alert(decision, host=host, now_iso=now_iso)
    try:
        post_webhook(webhook, msg)
    except Exception as e:
        sys.stderr.write(f"webhook post failed: {e}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
