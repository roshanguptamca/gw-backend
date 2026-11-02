"""Runtime metadata and Docker failure paths, with every subprocess mocked."""

import subprocess
from unittest.mock import Mock

import pytest

from apps.securewise.runtime import docker_runner


@pytest.mark.parametrize(
    ("language", "filename", "content", "version"),
    [
        ("python", "pyproject.toml", '[project]\nrequires-python = ">=3.11"', "3.11"),
        ("python", ".python-version", "3.12.2", "3.12.2"),
        ("node", "package.json", '{"engines":{"node":">=20.1"}}', "20.1"),
        ("node", ".nvmrc", "v22.1.0", "22.1.0"),
        ("go", "go.mod", "module example.test/app\ngo 1.22.1\n", "1.22.1"),
        ("ruby", "Gemfile.lock", "RUBY VERSION\n   ruby 3.2.1\n", "3.2.1"),
        ("php", "composer.json", '{"require":{"php":"^8.2"}}', "8.2"),
    ],
)
def test_runtime_version_is_read_without_executing_repository(tmp_path, language, filename, content, version):
    (tmp_path / filename).write_text(content)
    assert docker_runner._version_from_repo(tmp_path, language) == version


@pytest.mark.parametrize("language", ["python", "node", "go", "ruby", "php"])
def test_missing_runtime_metadata_has_no_invented_version(tmp_path, language):
    assert docker_runner._version_from_repo(tmp_path, language) == ""


@pytest.mark.parametrize(
    ("language", "managers", "filename", "expected"),
    [
        ("python", ("poetry",), "", "poetry install --only main"),
        ("python", ("pipenv",), "", "pipenv install --system --deploy"),
        ("python", (), "requirements.txt", "pip install --no-cache-dir -r requirements.txt"),
        ("python", (), "pyproject.toml", "pip install --no-cache-dir ."),
        ("node", (), "pnpm-lock.yaml", "pnpm install --frozen-lockfile"),
        ("node", (), "yarn.lock", "yarn install --frozen-lockfile"),
        ("node", (), "npm-shrinkwrap.json", "npm ci"),
        ("node", (), "package.json", "npm install"),
        ("go", (), "go.mod", "go mod download"),
        ("php", (), "composer.json", "composer install --no-dev"),
        ("ruby", (), "Gemfile", "bundle install"),
    ],
)
def test_install_commands_preserve_lockfile_and_package_manager_choices(
    tmp_path, language, managers, filename, expected
):
    if filename:
        (tmp_path / filename).touch()
    assert expected in docker_runner._package_install_command(tmp_path, language, managers)


@pytest.mark.parametrize(
    ("stdout", "returncode", "expected"),
    [
        ('["name=rootless", "name=seccomp"]', 0, True),
        ('["name=seccomp"]', 0, False),
        ("invalid", 0, False),
        ("[]", 1, False),
    ],
)
def test_rootless_detection_requires_valid_daemon_evidence(monkeypatch, stdout, returncode, expected):
    monkeypatch.setattr(docker_runner, "is_docker_daemon_available", lambda: (True, ""))
    monkeypatch.setattr(docker_runner.subprocess, "run", Mock(return_value=Mock(stdout=stdout, returncode=returncode)))
    assert docker_runner.is_docker_rootless() is expected


@pytest.mark.parametrize("operation", ["is_docker_rootless", "is_docker_image_available", "create_isolated_network"])
@pytest.mark.parametrize("error", [OSError("unavailable"), subprocess.TimeoutExpired("docker", 5)])
def test_docker_availability_failures_are_reported(monkeypatch, operation, error):
    monkeypatch.setattr(docker_runner, "is_docker_daemon_available", lambda: (True, ""))
    monkeypatch.setattr(docker_runner.subprocess, "run", Mock(side_effect=error))
    result = getattr(docker_runner, operation)(*(() if operation == "is_docker_rootless" else ("synthetic",)))
    assert (result[0] if isinstance(result, tuple) else result) is False


@pytest.mark.parametrize(
    ("returncode", "stdout", "expected"),
    [(0, "200\n", 200), (0, "log line\n403\n", 403), (0, "invalid", None), (0, "", None), (1, "200", None)],
)
def test_network_probe_validates_status_and_keeps_restrictions(monkeypatch, returncode, stdout, expected):
    run = Mock(return_value=Mock(returncode=returncode, stdout=stdout))
    monkeypatch.setattr(docker_runner.subprocess, "run", run)
    assert docker_runner.probe_network_url("isolated-test-network", "http://synthetic:8080/health") == expected
    command = run.call_args.args[0]
    assert command[command.index("--network") + 1] == "isolated-test-network"
    assert "--cap-drop" in command and "no-new-privileges" in command
    assert "--privileged" not in command


@pytest.mark.parametrize("error", [OSError("missing"), subprocess.TimeoutExpired("docker", 10)])
def test_network_probe_and_logs_handle_unavailable_daemon(monkeypatch, error):
    monkeypatch.setattr(docker_runner.subprocess, "run", Mock(side_effect=error))
    assert docker_runner.probe_network_url("isolated", "http://synthetic/") is None
    assert docker_runner.get_logs("synthetic") == ""


def test_network_creation_failure_preserves_diagnostic(monkeypatch):
    run = Mock(return_value=Mock(returncode=1, stderr="network denied", stdout=""))
    monkeypatch.setattr(docker_runner.subprocess, "run", run)
    assert docker_runner.create_isolated_network("synthetic") == (False, "network denied")
    assert "--internal" in run.call_args.args[0]


def test_logs_include_both_output_streams(monkeypatch):
    monkeypatch.setattr(
        docker_runner.subprocess, "run", Mock(return_value=Mock(returncode=0, stdout="application", stderr="warning"))
    )
    assert docker_runner.get_logs("synthetic") == "applicationwarning"
