import argparse
from io import StringIO
from unittest.mock import Mock

from django.core.management.base import CommandError

import pytest

from apps.securewise.management.commands import securewise_runtime_digest, securewise_worker


def test_digest_command_reports_exact_repository_digest(monkeypatch, tmp_path):
    digest = Mock(return_value="a" * 64)
    monkeypatch.setattr(securewise_runtime_digest, "repository_tree_sha256", digest)
    output = StringIO()
    command = securewise_runtime_digest.Command(stdout=output, stderr=StringIO())
    parser = argparse.ArgumentParser()
    command.add_arguments(parser)
    command.handle(**vars(parser.parse_args([str(tmp_path)])))
    digest.assert_called_once_with(str(tmp_path))
    assert output.getvalue().strip() == "a" * 64


@pytest.mark.parametrize("error", [OSError("unreadable repository"), ValueError("unsafe repository")])
def test_digest_command_exposes_validation_failures(monkeypatch, error):
    monkeypatch.setattr(securewise_runtime_digest, "repository_tree_sha256", Mock(side_effect=error))
    with pytest.raises(CommandError, match=str(error)):
        securewise_runtime_digest.Command(stdout=StringIO(), stderr=StringIO()).handle(repository_path="/synthetic")


def test_worker_command_rejects_nonpositive_poll_interval():
    with pytest.raises(CommandError, match="greater than zero"):
        securewise_worker.Command(stdout=StringIO(), stderr=StringIO()).handle(poll_interval=0)


def test_connectivity_probe_never_claims_a_job(monkeypatch):
    register = Mock(return_value=Mock(capabilities=[]))
    heartbeat, process = Mock(), Mock()
    monkeypatch.setattr(securewise_worker, "register_worker", register)
    monkeypatch.setattr(securewise_worker, "heartbeat_worker", heartbeat)
    monkeypatch.setattr(securewise_worker, "process_next_job", process)
    output = StringIO()
    securewise_worker.Command(stdout=output, stderr=StringIO()).handle(
        poll_interval=1, check_connectivity=True, worker_id="synthetic-worker", once=False
    )
    worker_id = register.call_args.args[0]
    assert worker_id.startswith("synthetic-worker-probe-")
    assert register.call_args.kwargs == {"status": "offline"}
    heartbeat.assert_called_once_with(worker_id, include_offline=True)
    process.assert_not_called()
    assert "no jobs were claimed" in output.getvalue()


def test_worker_poll_reports_jobs_and_sleeps_only_when_idle(monkeypatch):
    register = Mock(return_value=Mock(capabilities=["sast"]))
    process = Mock(side_effect=[("scan", "synthetic-job"), None, KeyboardInterrupt()])
    sleep = Mock()
    monkeypatch.setattr(securewise_worker, "register_worker", register)
    monkeypatch.setattr(securewise_worker, "heartbeat_worker", Mock())
    monkeypatch.setattr(securewise_worker, "process_next_job", process)
    monkeypatch.setattr(securewise_worker.time, "sleep", sleep)
    output = StringIO()
    with pytest.raises(KeyboardInterrupt):
        securewise_worker.Command(stdout=output, stderr=StringIO()).handle(
            poll_interval=3, check_connectivity=False, worker_id="synthetic-worker", once=False
        )
    sleep.assert_called_once_with(3)
    assert "Processed scan job synthetic-job" in output.getvalue()


def test_drain_stops_before_claiming_and_marks_worker_offline(monkeypatch, tmp_path):
    registration = Mock(capabilities=["sast"])
    process = Mock()
    monkeypatch.setattr(securewise_worker, "register_worker", Mock(return_value=registration))
    monkeypatch.setattr(securewise_worker, "process_next_job", process)
    drain_file = tmp_path / "drain"
    drain_file.touch()
    securewise_worker.Command(stdout=StringIO(), stderr=StringIO()).handle(
        poll_interval=1, check_connectivity=False, worker_id="synthetic", once=False, drain_file=str(drain_file)
    )
    process.assert_not_called()
    assert registration.status == "offline"
    registration.save.assert_called_once_with(update_fields=["status"])


def test_drain_finishes_current_job_without_claiming_another(monkeypatch, tmp_path):
    registration = Mock(capabilities=["sast"])
    drain_file = tmp_path / "drain"

    def finish_job(**kwargs):
        drain_file.touch()
        return "scan", "synthetic-job"

    process = Mock(side_effect=finish_job)
    monkeypatch.setattr(securewise_worker, "register_worker", Mock(return_value=registration))
    monkeypatch.setattr(securewise_worker, "heartbeat_worker", Mock())
    monkeypatch.setattr(securewise_worker, "process_next_job", process)
    output = StringIO()
    securewise_worker.Command(stdout=output, stderr=StringIO()).handle(
        poll_interval=1, check_connectivity=False, worker_id="synthetic", once=False, drain_file=str(drain_file)
    )
    process.assert_called_once()
    assert "Processed scan job synthetic-job" in output.getvalue()
    assert registration.status == "offline"
