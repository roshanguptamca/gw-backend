import base64
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "deploy/oracle-worker"


@pytest.fixture
def modules(monkeypatch):
    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    policy = load("oracle_policy", "policy.py")
    monkeypatch.setitem(sys.modules, "policy", policy)
    return SimpleNamespace(
        policy=policy,
        deploy=load("oracle_deploy", "deploy.py"),
        runtime=load("oracle_runtime", "runtime.py"),
        proof=load("oracle_proof", "proof.py"),
    )


@pytest.fixture
def enrolled(modules):
    config = {
        "DB_HOST": "production.example.invalid",
        "DB_PORT": "5432",
        "DB_NAME": "production",
        "DB_USER": "production-worker",
        "DB_PASSWORD": "synthetic-password",
        "DB_SSLMODE": "verify-full",
        "DB_SSLROOTCERT": "/etc/securewise/certs/database.pem",
        "SECRET_KEY": "synthetic-django-key",
        "SECUREWISE_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"a" * 32).decode(),
    }
    identity = {
        "environment": "production",
        "host": modules.policy.HOSTS["production"],
        "database_sha256": modules.policy.database_identity(config),
        "other_database_sha256": "b" * 64,
        "encryption_key_sha256": modules.policy.digest(config["SECUREWISE_ENCRYPTION_KEY"]),
        "other_encryption_key_sha256": "c" * 64,
        "egress_ruleset_sha256": "d" * 64,
    }
    return config, identity


@pytest.mark.parametrize("profile", ["lightweight", "website_passive"])
def test_valid_independent_enrollment(modules, enrolled, profile):
    modules.policy.validate(*enrolled, "production", profile)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("DB_HOST", "acc.example.invalid"),
        ("DB_NAME", "acc"),
        ("DB_USER", "acc-worker"),
        ("DB_PORT", "0"),
        ("DB_PORT", "65536"),
        ("DB_PORT", "not-a-port"),
        ("DB_SSLMODE", "require"),
        ("DB_SSLROOTCERT", "/tmp/untrusted.pem"),
        ("DB_SSLROOTCERT", "/etc/securewise/certs/../untrusted.pem"),
        ("DB_PASSWORD", ""),
        ("DB_PASSWORD", "newline\ninjection"),
        ("SECUREWISE_ENCRYPTION_KEY", "not-a-key"),
        ("SECUREWISE_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"short").decode()),
        ("DATABASE_URL", "postgres://unexpected-override"),
        ("PYTHONPATH", "/tmp"),
        ("SECUREWISE_WORKER_PROFILE", "autopentest_api"),
    ],
)
def test_rejects_mismatched_or_unsafe_configuration(modules, enrolled, field, value):
    config, identity = enrolled
    config[field] = value
    with pytest.raises(ValueError):
        modules.policy.validate(config, identity, "production", "lightweight")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "acc"),
        ("host", "158.101.218.17"),
        ("database_sha256", "0" * 64),
        ("encryption_key_sha256", "0" * 64),
        ("other_database_sha256", ""),
        ("other_encryption_key_sha256", ""),
        ("egress_ruleset_sha256", ""),
    ],
)
def test_wrong_or_incomplete_host_enrollment_fails_closed(modules, enrolled, field, value):
    config, identity = enrolled
    identity[field] = value
    with pytest.raises(ValueError):
        modules.policy.validate(config, identity, "production", "website_passive")


@pytest.mark.parametrize(
    ("expected", "other"),
    [("database_sha256", "other_database_sha256"), ("encryption_key_sha256", "other_encryption_key_sha256")],
)
def test_environment_credentials_cannot_be_shared(modules, enrolled, expected, other):
    config, identity = enrolled
    identity[other] = identity[expected]
    with pytest.raises(ValueError, match="wrong environment"):
        modules.policy.validate(config, identity, "production", "lightweight")


def test_alternate_encoding_cannot_disguise_a_shared_encryption_key(modules, enrolled):
    config, identity = enrolled
    config["SECUREWISE_ENCRYPTION_KEY"] = base64.b64encode(b"\xff" * 32).decode()
    identity["encryption_key_sha256"] = modules.policy.digest(config["SECUREWISE_ENCRYPTION_KEY"])
    identity["other_encryption_key_sha256"] = modules.policy.digest(base64.urlsafe_b64encode(b"\xff" * 32).decode())
    with pytest.raises(ValueError, match="valid explicit worker encryption key"):
        modules.policy.validate(config, identity, "production", "lightweight")


def test_password_rotation_preserves_database_identity(modules, enrolled):
    config, identity = enrolled
    config["DB_PASSWORD"] = "synthetic-rotated-password"
    assert modules.policy.database_identity(config) == identity["database_sha256"]


def test_release_parents_remain_traversable_under_secret_safe_umask(modules, tmp_path):
    path = tmp_path / "managed"
    mocked = Mock(wraps=path)
    mocked.stat.return_value = SimpleNamespace(st_uid=0)
    previous_mask = os.umask(0o077)
    try:
        modules.deploy.managed_directory(mocked)
    finally:
        os.umask(previous_mask)
    assert stat.S_IMODE(path.stat().st_mode) == 0o755


@pytest.mark.parametrize("symlink,uid", [(True, 0), (False, 1000)])
def test_managed_release_directory_rejects_untrusted_ownership(modules, symlink, uid):
    path = Mock()
    path.is_symlink.return_value = symlink
    path.stat.return_value = SimpleNamespace(st_uid=uid)
    with pytest.raises(ValueError):
        modules.deploy.managed_directory(path)
    path.chmod.assert_not_called()


def test_startup_removes_inherited_overrides_and_disables_experimental_scans(modules, enrolled, monkeypatch):
    monkeypatch.setattr(modules.policy.os, "environ", {"DATABASE_URL": "wrong-database", "HTTP_PROXY": "untrusted"})
    modules.policy.configure(enrolled[0], "production", "website_passive")
    environment = modules.policy.os.environ
    assert "DATABASE_URL" not in environment
    assert "HTTP_PROXY" not in environment
    assert environment["SECUREWISE_DEPLOYMENT_ENV"] == "production"
    assert environment["SECUREWISE_AUTOPENTEST_EXPERIMENTAL_LOW_RESOURCE"] == "0"
    assert environment["SECUREWISE_RUNTIME_BUILDS_ENABLED"] == "false"
    assert environment["SECUREWISE_URL_EGRESS_ENFORCED"] == "true"


@pytest.mark.parametrize("mismatch", ["HOST", "PORT", "NAME", "USER", "PASSWORD", "ENGINE", "tls", "secret", "key"])
def test_effective_django_settings_must_match_before_database_access(modules, enrolled, mismatch):
    config, _ = enrolled
    database = {key: config[f"DB_{key}"] for key in ("HOST", "PORT", "NAME", "USER", "PASSWORD")}
    database.update(
        ENGINE="django.db.backends.postgresql",
        OPTIONS={"sslmode": "verify-full", "sslrootcert": config["DB_SSLROOTCERT"]},
    )
    settings = SimpleNamespace(
        DATABASES={"default": database},
        SECRET_KEY=config["SECRET_KEY"],
        SECUREWISE_ENCRYPTION_KEY=config["SECUREWISE_ENCRYPTION_KEY"],
    )
    modules.policy.validate_settings(settings, config)
    if mismatch == "tls":
        database["OPTIONS"]["sslmode"] = "require"
    elif mismatch == "secret":
        settings.SECRET_KEY = "overridden"
    elif mismatch == "key":
        settings.SECUREWISE_ENCRYPTION_KEY = "overridden"
    else:
        database[mismatch] = "overridden"
    with pytest.raises(ValueError, match="Effective Django"):
        modules.policy.validate_settings(settings, config)


@pytest.mark.parametrize("unsafe", [None, "owner", "writable", "symlink", "world-readable", "parent"])
def test_secret_files_and_all_parents_must_be_protected(modules, monkeypatch, unsafe):
    metadata = SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=0)
    parent_metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
    parent = Mock()
    parent.lstat.return_value = parent_metadata
    path = Mock(parents=[parent])
    path.lstat.return_value = metadata
    path.stat.return_value = metadata
    path.read_text.return_value = "{}"
    monkeypatch.setattr(modules.policy, "Path", Mock(return_value=path))
    if unsafe == "owner":
        metadata.st_uid = 1000
    elif unsafe == "writable":
        metadata.st_mode |= 0o020
    elif unsafe == "symlink":
        metadata.st_mode = stat.S_IFLNK | 0o777
    elif unsafe == "world-readable":
        metadata.st_mode |= 0o004
    elif unsafe == "parent":
        parent_metadata.st_mode |= 0o002
    if unsafe is None:
        assert modules.policy.protected_json("synthetic") == {}
    else:
        with pytest.raises(ValueError):
            modules.policy.protected_json("synthetic")


@pytest.mark.parametrize("name", ["../escape", "/absolute", ".env", "nested/.env.production"])
def test_archive_rejects_traversal_and_dotenv(modules, tmp_path, name):
    archive = tmp_path / "code.tar.gz"
    with tarfile.open(archive, "w:gz") as source:
        entry = tarfile.TarInfo(name)
        entry.size = 4
        source.addfile(entry, io.BytesIO(b"data"))
    with pytest.raises(ValueError, match="unsafe path"):
        modules.deploy.extract(archive, tmp_path / "release")
    assert not (tmp_path / "release").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_archive_rejects_links_and_special_files(modules, tmp_path, kind):
    archive = tmp_path / "code.tar.gz"
    with tarfile.open(archive, "w:gz") as source:
        entry = tarfile.TarInfo("unsafe")
        entry.type = kind
        entry.linkname = "/etc/passwd"
        source.addfile(entry)
    with pytest.raises(ValueError):
        modules.deploy.extract(archive, tmp_path / "release")


def test_safe_archive_is_extracted(modules, tmp_path):
    archive = tmp_path / "code.tar.gz"
    with tarfile.open(archive, "w:gz") as source:
        entry = tarfile.TarInfo("code.txt")
        entry.size = 4
        source.addfile(entry, io.BytesIO(b"data"))
    modules.deploy.extract(archive, tmp_path / "release")
    assert (tmp_path / "release/code.txt").read_bytes() == b"data"


@pytest.fixture
def activation(modules, monkeypatch, tmp_path):
    deploy = modules.deploy
    units, runtime, base = tmp_path / "units", tmp_path / "run", tmp_path / "deployment"
    for path in (units, runtime, base):
        path.mkdir()
    old, new = base / "old", base / "new"
    old.mkdir()
    new.mkdir()
    (base / "current").symlink_to(old)
    monkeypatch.setattr(deploy, "ROOT", tmp_path)
    monkeypatch.setattr(deploy, "UNIT_DIR", units)
    monkeypatch.setattr(deploy, "RUN_DIR", runtime)
    monkeypatch.setattr(deploy, "run", Mock())
    monkeypatch.setattr(deploy, "drain", Mock())
    monkeypatch.setattr(deploy, "check_runtime", Mock())
    monkeypatch.setattr(deploy, "egress", Mock())
    (units / "securewise-managed-production-website_passive.service").write_text(
        deploy.service_unit("production", "website_passive")
    )
    return deploy, base, old, new


def test_success_atomically_keeps_previous_release_and_config(activation):
    deploy, base, old, new = activation
    deploy.activate(base, new, "production", "website_passive")
    assert (base / "current").resolve() == new
    assert (base / "previous").resolve() == old
    deploy.egress.assert_called_once_with(new, "production")
    assert [call.args[1] for call in deploy.check_runtime.call_args_list] == ["probe", "health"]


def test_failed_new_heartbeat_restores_and_verifies_previous_release(activation):
    deploy, base, old, new = activation
    deploy.check_runtime.side_effect = [None, RuntimeError("unhealthy"), None]
    with pytest.raises(RuntimeError, match="unhealthy"):
        deploy.activate(base, new, "production", "website_passive")
    assert (base / "current").resolve() == old
    assert deploy.check_runtime.call_args.args == (old, "health", "production", "website_passive")
    assert deploy.drain.call_count == 2


def test_failed_first_deployment_leaves_service_stopped(activation):
    deploy, base, _, new = activation
    (base / "current").unlink()
    deploy.check_runtime.side_effect = [None, RuntimeError("unhealthy")]
    with pytest.raises(RuntimeError):
        deploy.activate(base, new, "production", "lightweight")
    assert not (base / "current").exists()
    deploy.run.assert_any_call("systemctl", "disable", "securewise-managed-production-lightweight.service")


def test_first_install_does_not_try_to_stop_a_nonexistent_unit(activation):
    deploy, base, _, new = activation
    (base / "current").unlink()
    deploy.activate(base, new, "production", "lightweight")
    deploy.drain.assert_not_called()
    assert (base / "current").resolve() == new


def test_preflight_failure_never_changes_running_release(activation):
    deploy, base, old, new = activation
    deploy.check_runtime.side_effect = RuntimeError("wrong database")
    with pytest.raises(RuntimeError):
        deploy.activate(base, new, "production", "lightweight")
    assert (base / "current").resolve() == old
    deploy.drain.assert_not_called()


def test_drain_failure_does_not_replace_running_release(activation):
    deploy, base, old, new = activation
    deploy.drain.side_effect = RuntimeError("job still running")
    with pytest.raises(RuntimeError, match="job still running"):
        deploy.activate(base, new, "production", "website_passive")
    assert (base / "current").resolve() == old
    deploy.run.assert_not_called()


def test_unit_drift_requires_manual_review_before_deployment(activation):
    deploy, base, old, new = activation
    (deploy.UNIT_DIR / "securewise-managed-production-website_passive.service").write_text("unreviewed unit")
    with pytest.raises(ValueError, match="review changes manually"):
        deploy.activate(base, new, "production", "website_passive")
    assert (base / "current").resolve() == old
    deploy.check_runtime.assert_not_called()


def test_firewall_failure_never_switches_release(activation):
    deploy, base, old, new = activation
    deploy.egress.side_effect = RuntimeError("changed firewall")
    with pytest.raises(RuntimeError):
        deploy.activate(base, new, "production", "website_passive")
    assert (base / "current").resolve() == old
    deploy.check_runtime.assert_not_called()
    deploy.drain.assert_not_called()


def test_drain_timeout_never_kills_running_jobs(modules, monkeypatch, tmp_path):
    monkeypatch.setattr(modules.deploy, "active", Mock(return_value=True))
    monkeypatch.setattr(modules.deploy.time, "monotonic", Mock(side_effect=[0, 601]))
    command = Mock()
    monkeypatch.setattr(modules.deploy, "run", command)
    with pytest.raises(RuntimeError, match="not killed"):
        modules.deploy.drain("synthetic.service", tmp_path / "drain")
    assert (tmp_path / "drain").exists()
    command.assert_not_called()


@pytest.mark.parametrize("profile", ["lightweight", "website_passive"])
def test_generated_unit_keeps_restricted_runtime_and_no_legacy_paths(modules, profile):
    unit = modules.deploy.service_unit("production", profile)
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ProtectHome=true" in unit
    assert f"runtime.py probe production {profile}" in unit
    assert "/opt/securewise/backend" not in unit
    assert "EnvironmentFile=" not in unit
    if profile == "website_passive":
        assert "MemoryMax=224M" in unit
        assert "MemorySwapMax=0" in unit


def test_firewall_refresh_rejects_changed_ruleset_before_writing_proof(modules, enrolled, monkeypatch):
    monkeypatch.setattr(modules.proof, "protected_json", Mock(return_value=enrolled[1]))
    monkeypatch.setattr(modules.proof.subprocess, "check_output", Mock(return_value=b"changed ruleset"))
    verify = Mock()
    monkeypatch.setattr(modules.proof.subprocess, "run", verify)
    with pytest.raises(ValueError, match="reviewed deny-by-default"):
        modules.proof.refresh("production")
    verify.assert_not_called()


def test_firewall_refresh_delegates_to_existing_restricted_verifier(modules, enrolled, monkeypatch):
    identity = enrolled[1]
    identity["egress_ruleset_sha256"] = modules.proof.hashlib.sha256(b"reviewed").hexdigest()
    monkeypatch.setattr(modules.proof, "protected_json", Mock(return_value=identity))
    monkeypatch.setattr(modules.proof.subprocess, "check_output", Mock(return_value=b"reviewed"))
    verify = Mock()
    monkeypatch.setattr(modules.proof.subprocess, "run", verify)
    modules.proof.refresh("production")
    assert verify.call_args.args[0][-1] == "--egress-only"
    assert verify.call_args.kwargs["env"]["SECUREWISE_URL_EGRESS_PROOF_FILE"] == modules.policy.PROOF_PATH


@pytest.mark.parametrize("problem", ["offline", "stale", "wrong-profile", "extra-capability", "missing-capability"])
def test_health_rejects_stale_or_incorrect_registration(modules, problem):
    from django.utils import timezone

    now = timezone.now()
    registration = SimpleNamespace(
        status="online",
        last_seen_at=now,
        capabilities=["dast", "url_egress_restricted"],
        metrics={"worker_profile": "website_passive"},
    )
    assert modules.runtime.check_registration(registration, "website_passive", now.timestamp() - 10)
    if problem == "offline":
        registration.status = "offline"
    elif problem == "stale":
        registration.last_seen_at -= timedelta(seconds=46)
    elif problem == "wrong-profile":
        registration.metrics["worker_profile"] = "autopentest_api"
    elif problem == "extra-capability":
        registration.capabilities.append("docker_daemon")
    else:
        registration.capabilities.pop()
    assert not modules.runtime.check_registration(registration, "website_passive", now.timestamp() - 100)


def test_templates_contain_no_environment_credentials(modules):
    config = json.loads((SCRIPTS / "production-config.example.json").read_text())
    assert set(config) == modules.policy.CONFIG_KEYS
    assert all(value == "" for value in config.values())


def test_effective_configuration_is_validated_before_app_startup(modules, enrolled, monkeypatch):
    import django

    setup = Mock()
    monkeypatch.setattr(django, "setup", setup)
    monkeypatch.setattr(sys, "argv", ["runtime.py", "probe", "production", "lightweight"])
    monkeypatch.setattr(modules.runtime, "protected_json", Mock(side_effect=enrolled))
    monkeypatch.setattr(modules.runtime, "configure", Mock())
    monkeypatch.setattr(modules.runtime, "validate_settings", Mock(side_effect=ValueError("wrong database")))
    with pytest.raises(ValueError, match="wrong database"):
        modules.runtime.main()
    setup.assert_not_called()


@pytest.mark.parametrize(
    "environment,branch,rules,revision,allowed",
    [
        ("acc", "refs/heads/feature/reviewed", [], "a" * 40, True),
        (
            "production",
            "refs/heads/main",
            [{"type": "required_reviewers", "reviewers": [{"type": "Team"}], "prevent_self_review": True}],
            "a" * 40,
            True,
        ),
        ("production", "refs/heads/main", [], "a" * 40, False),
        (
            "production",
            "refs/heads/main",
            [{"type": "required_reviewers", "reviewers": [], "prevent_self_review": True}],
            "a" * 40,
            False,
        ),
        (
            "production",
            "refs/heads/main",
            [{"type": "required_reviewers", "reviewers": [{"type": "Team"}], "prevent_self_review": False}],
            "a" * 40,
            False,
        ),
        (
            "production",
            "refs/heads/feature/unreviewed",
            [{"type": "required_reviewers", "reviewers": [{"type": "Team"}], "prevent_self_review": True}],
            "a" * 40,
            False,
        ),
        ("acc", "refs/heads/main", [], "main; unexpected-command", False),
    ],
)
def test_actual_workflow_guard_requires_protected_production_approval(
    tmp_path, environment, branch, rules, revision, allowed
):
    workflow = yaml.load(
        (SCRIPTS.parents[1] / ".github/workflows/oracle-workers.yml").read_text(), Loader=yaml.BaseLoader
    )
    guard = workflow["jobs"]["deploy"]["steps"][0]["run"]
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s" "$MOCK_GH_RESPONSE"\n')
    gh.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", guard],
        env={
            "PATH": f"{tmp_path}:{os.defpath}",
            "ENVIRONMENT": environment,
            "WORKFLOW_REF": branch,
            "REVISION": revision,
            "REPOSITORY": "synthetic/backend",
            "MOCK_GH_RESPONSE": json.dumps({"protection_rules": rules}),
        },
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert (result.returncode == 0) is allowed, result.stderr.decode()
