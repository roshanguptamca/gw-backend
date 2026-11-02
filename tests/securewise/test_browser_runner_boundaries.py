import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.securewise.services import browser_pentest


@pytest.fixture
def tester():
    session = Mock(timeout_seconds=30, status="running")
    session.get_auth_config.return_value = {"users": [], "journeys": []}
    return browser_pentest.BrowserSecurityTester(
        session, Mock(), "synthetic-isolated-network", "http://securewise-runtime-0123456789:8080"
    )


@pytest.fixture
def browser_process(monkeypatch):
    process = Mock()
    process.poll.return_value = 0
    process.wait.return_value = 0
    popen = Mock(return_value=process)
    monkeypatch.setattr(browser_pentest.subprocess, "Popen", popen)
    cleanup = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(browser_pentest.subprocess, "run", cleanup)
    monkeypatch.setattr(browser_pentest, "is_docker_image_available", lambda image: True)
    active = {}
    selector = Mock()

    def register(stream, events, label):
        active[stream] = SimpleNamespace(fileobj=stream, data=label)

    selector.register.side_effect = register
    selector.unregister.side_effect = active.pop
    selector.get_map.side_effect = lambda: dict(active)
    selector.select.side_effect = lambda **kwargs: [(key, None) for key in list(active.values())]
    monkeypatch.setattr(browser_pentest.selectors, "DefaultSelector", lambda: selector)
    stdout = iter([b'{"results":[{"key":"logout","status":"passed"}]}', b""])
    stderr = iter([b'{"progress":50}\n', b""])
    monkeypatch.setattr(
        browser_pentest.os,
        "read",
        lambda fd, limit: next(stdout if fd == process.stdout.fileno() else stderr),
    )
    process.stdout.fileno.return_value = 101
    process.stderr.fileno.return_value = 102
    return SimpleNamespace(process=process, popen=popen, cleanup=cleanup)


def test_browser_execution_enforces_sandbox_and_consumes_progress(tester, browser_process):
    results = tester._execute({"path": "/login"}, [{"key": "logout"}])
    assert results == [{"key": "logout", "status": "passed"}]
    assert tester.session.progress == 45 and tester.scan.progress == 45
    payload = json.loads(browser_process.process.stdin.write.call_args.args[0])
    assert payload["target"] == "http://securewise-runtime-0123456789:8080"
    command = browser_process.popen.call_args.args[0]
    assert command[command.index("--network") + 1] == "synthetic-isolated-network"
    assert "--read-only" in command and "no-new-privileges" in command
    assert "--privileged" not in command and "-v" not in command
    browser_process.process.stdin.close.assert_called_once()
    assert browser_process.cleanup.call_args.args[0][:3] == ["docker", "rm", "-f"]


@pytest.mark.parametrize("returncode", [1, 137])
def test_browser_nonzero_exit_is_not_reported_as_success(tester, browser_process, returncode):
    browser_process.process.wait.return_value = returncode
    with pytest.raises(RuntimeError, match="runner failed"):
        tester._execute({}, [])
    browser_process.cleanup.assert_called_once()


@pytest.mark.parametrize("payload", [b"invalid-json", b"[]", b'{"results":{}}'])
def test_browser_invalid_output_still_cleans_up(monkeypatch, tester, browser_process, payload):
    reads = iter([payload, b"", b"", b""])
    monkeypatch.setattr(browser_pentest.os, "read", lambda *args: next(reads))
    with pytest.raises(RuntimeError, match="invalid output|could not complete"):
        tester._execute({}, [])
    browser_process.cleanup.assert_called_once()


def test_browser_cleanup_requires_proof_that_container_is_gone(tester, browser_process):
    browser_process.cleanup.side_effect = [
        Mock(returncode=1),
        Mock(returncode=0, stdout="still-running"),
    ]
    with pytest.raises(RuntimeError, match="cleanup could not be verified"):
        tester._execute({}, [])


def test_browser_cleanup_can_confirm_container_already_removed(tester, browser_process):
    browser_process.cleanup.side_effect = [Mock(returncode=1), Mock(returncode=0, stdout="")]
    assert tester._execute({}, [])[0]["status"] == "passed"


def test_browser_process_start_failure_reports_error_and_cleans_up(tester, browser_process):
    browser_process.popen.side_effect = OSError("docker unavailable")
    with pytest.raises(RuntimeError, match="could not complete"):
        tester._execute({}, [])
    browser_process.cleanup.assert_called_once()


def test_browser_cleanup_failure_is_not_silently_ignored(tester, browser_process):
    browser_process.cleanup.side_effect = subprocess.TimeoutExpired("docker", 10)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        tester._execute({}, [])


@pytest.mark.parametrize("line", [b"invalid", b"{}", b'{"progress":null}'])
def test_invalid_progress_does_not_update_scan(tester, line):
    tester._update_progress(line)
    tester.session.save.assert_not_called()
    tester.scan.save.assert_not_called()


def test_progress_is_capped_below_completion_until_results_are_final(tester):
    tester._update_progress(b'{"progress":200}')
    assert tester.session.progress == 95
    assert tester.scan.progress == 95
