"""TDD for vm_health_check — vertical slices."""
import os
from unittest.mock import patch, MagicMock
import pytest
from vm_health_check import (
    ProbeResult, decide, format_alert,
    probe_http, probe_systemd_active, main,
)


def test_decide_no_alert_when_all_ok():
    results = [
        ProbeResult(name="hermes", ok=True, detail=""),
        ProbeResult(name="shim", ok=True, detail=""),
    ]
    decision = decide(results)
    assert decision.alert is False
    assert decision.failed == []


def test_decide_alerts_with_failing_check_names():
    results = [
        ProbeResult(name="hermes", ok=True, detail=""),
        ProbeResult(name="shim", ok=False, detail="connection refused"),
        ProbeResult(name="queue", ok=False, detail="500 internal error"),
    ]
    decision = decide(results)
    assert decision.alert is True
    names = [r.name for r in decision.failed]
    assert names == ["shim", "queue"]


def test_format_alert_includes_host_ts_and_each_failed_check():
    results = [
        ProbeResult(name="shim", ok=False, detail="connection refused"),
        ProbeResult(name="queue", ok=False, detail="HTTP 500"),
    ]
    msg = format_alert(decide(results), host="nanoclaw-az", now_iso="2026-06-10T03:00:00Z")
    assert "nanoclaw-az" in msg
    assert "2026-06-10T03:00:00Z" in msg
    assert "shim" in msg and "connection refused" in msg
    assert "queue" in msg and "HTTP 500" in msg


def test_probe_http_ok_on_200():
    with patch("vm_health_check.urlopen") as m:
        m.return_value.__enter__.return_value.status = 200
        r = probe_http("shim", "http://127.0.0.1:8403/v1/models")
        assert r.ok is True
        assert r.name == "shim"


def test_probe_http_fails_on_non_2xx():
    with patch("vm_health_check.urlopen") as m:
        m.return_value.__enter__.return_value.status = 503
        r = probe_http("shim", "http://127.0.0.1:8403/v1/models")
        assert r.ok is False
        assert "503" in r.detail


def test_probe_http_fails_on_exception():
    with patch("vm_health_check.urlopen", side_effect=OSError("connection refused")):
        r = probe_http("shim", "http://127.0.0.1:8403/v1/models")
        assert r.ok is False
        assert "connection refused" in r.detail


def test_probe_systemd_active_true_when_systemctl_returns_active():
    fake = MagicMock(returncode=0, stdout="active\n", stderr="")
    with patch("vm_health_check.subprocess.run", return_value=fake):
        r = probe_systemd_active("hermes")
        assert r.ok is True
        assert r.name == "hermes"


def test_probe_systemd_active_false_with_state_in_detail():
    fake = MagicMock(returncode=3, stdout="failed\n", stderr="")
    with patch("vm_health_check.subprocess.run", return_value=fake):
        r = probe_systemd_active("hermes")
        assert r.ok is False
        assert "failed" in r.detail


def test_main_posts_to_webhook_on_failure():
    failing = [ProbeResult(name="shim", ok=False, detail="connection refused")]
    with patch("vm_health_check.collect_probes", return_value=failing), \
         patch("vm_health_check.post_webhook") as mpost, \
         patch.dict(os.environ, {"WEBHOOK_URL": "https://example.com/hook"}):
        rc = main()
    assert rc == 1
    assert mpost.called
    args = mpost.call_args
    assert args[0][0] == "https://example.com/hook"
    assert "shim" in args[0][1]


def test_main_silent_on_success():
    ok = [ProbeResult(name="shim", ok=True)]
    with patch("vm_health_check.collect_probes", return_value=ok), \
         patch("vm_health_check.post_webhook") as mpost, \
         patch.dict(os.environ, {"WEBHOOK_URL": "https://example.com/hook"}):
        rc = main()
    assert rc == 0
    assert not mpost.called


def test_main_exits_2_when_webhook_url_missing_and_alert():
    failing = [ProbeResult(name="shim", ok=False, detail="x")]
    with patch("vm_health_check.collect_probes", return_value=failing), \
         patch("vm_health_check.post_webhook") as mpost, \
         patch.dict(os.environ, {}, clear=True):
        rc = main()
    assert rc == 2
    assert not mpost.called
