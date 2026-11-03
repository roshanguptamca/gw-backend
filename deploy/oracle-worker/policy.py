"""Fail-closed identity checks shared by deployment and worker startup."""

import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path

HOSTS = {"acc": "158.101.218.17", "production": "152.70.53.242"}
CAPABILITIES = {
    "lightweight": {"sast", "sca", "secrets", "iac", "api"},
    "website_passive": {"dast", "url_egress_restricted"},
}
CONFIG_KEYS = {
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_SSLMODE",
    "DB_SSLROOTCERT",
    "SECRET_KEY",
    "SECUREWISE_ENCRYPTION_KEY",
}
IDENTITY_PATH = Path("/etc/securewise/oracle-worker.json")
PROOF_PATH = "/etc/securewise/url-egress-verification.json"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def database_identity(config):
    """Exclude passwords so rotating credentials doesn't change database identity."""
    return digest(
        json.dumps(
            [
                config["DB_HOST"].lower(),
                str(int(config["DB_PORT"])),
                config["DB_NAME"],
                config["DB_USER"],
            ],
            separators=(",", ":"),
        )
    )


def protected_json(path):
    path = Path(path)
    for parent in (path, *path.parents):
        metadata = parent.lstat()
        if stat.S_ISLNK(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError("Configuration and its parents must be root-owned and not writable by others.")
    if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_mode & 0o007:
        raise ValueError("Configuration must be a regular file with no access for others.")
    return json.loads(path.read_text())


def validate(config, identity, environment, profile):
    if environment not in HOSTS or profile not in CAPABILITIES:
        raise ValueError("Unsupported deployment environment or worker profile.")
    if identity.get("environment") != environment or identity.get("host") != HOSTS[environment]:
        raise ValueError("VM enrollment does not match the selected environment.")
    if profile == "website_passive" and not re.fullmatch(r"[0-9a-f]{64}", identity.get("egress_ruleset_sha256", "")):
        raise ValueError("Website workers require an independently reviewed firewall fingerprint.")
    if set(config) != CONFIG_KEYS or any(
        not isinstance(value, str) or not value or "\x00" in value or "\n" in value or "\r" in value
        for value in config.values()
    ):
        raise ValueError("Worker configuration must contain exactly the required nonempty string keys.")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", config["DB_HOST"]) or not (
        config["DB_PORT"].isdigit() and 1 <= int(config["DB_PORT"]) <= 65535
    ):
        raise ValueError("A PostgreSQL DNS hostname and valid port are required.")
    if (
        config["DB_SSLMODE"] != "verify-full"
        or not config["DB_SSLROOTCERT"].startswith("/etc/securewise/certs/")
        or ".." in Path(config["DB_SSLROOTCERT"]).parts
    ):
        raise ValueError("Database TLS requires verify-full and a provisioned CA certificate.")
    try:
        key = base64.b64decode(config["SECUREWISE_ENCRYPTION_KEY"], altchars=b"-_", validate=True)
    except ValueError:
        raise ValueError("A valid explicit worker encryption key is required.") from None
    if len(key) != 32 or base64.urlsafe_b64encode(key).decode("ascii") != config["SECUREWISE_ENCRYPTION_KEY"]:
        raise ValueError("A valid explicit worker encryption key is required.")
    for expected, forbidden, actual in (
        ("database_sha256", "other_database_sha256", database_identity(config)),
        ("encryption_key_sha256", "other_encryption_key_sha256", digest(config["SECUREWISE_ENCRYPTION_KEY"])),
    ):
        fingerprints = (identity.get(expected, ""), identity.get(forbidden, ""))
        if not all(re.fullmatch(r"[0-9a-f]{64}", item) for item in fingerprints):
            raise ValueError("VM enrollment requires independently verified environment fingerprints.")
        if fingerprints[0] == fingerprints[1] or actual != fingerprints[0] or actual == fingerprints[1]:
            raise ValueError("Database or encryption key belongs to the wrong environment.")


def configure(config, environment, profile):
    """Replace inherited configuration; never load shell or dotenv secret files."""
    os.environ.clear()
    os.environ.update(config)
    os.environ.update(
        {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/var/lib/securewise-worker",
            "TMPDIR": f"/var/lib/securewise-managed-{environment}-{profile}",
            "DJANGO_SETTINGS_MODULE": "guidewisey.settings",
            "ENV": "ACC" if environment == "acc" else "PROD",
            "SECUREWISE_DEPLOYMENT_ENV": environment,
            "SECUREWISE_WORKER_PROFILE": profile,
            "SECUREWISE_RUNNER_TYPE": "linux_worker",
            "SECUREWISE_RUNNER_PROVIDER": "oracle",
            "FUTUREWISE_DISABLE_SCHEDULER": "true",
            "SECUREWISE_RUNTIME_BUILDS_ENABLED": "false",
            "SECUREWISE_AUTOPENTEST_EXPERIMENTAL_LOW_RESOURCE": "0",
            "SECUREWISE_URL_EGRESS_ENFORCED": "true" if profile == "website_passive" else "false",
            "SECUREWISE_URL_EGRESS_PROOF_FILE": PROOF_PATH,
        }
    )


def validate_settings(settings, config):
    database = settings.DATABASES["default"]
    options = database.get("OPTIONS", {})
    if (
        database.get("ENGINE") != "django.db.backends.postgresql"
        or any(
            str(database.get(field, "")) != config[f"DB_{field}"]
            for field in ("HOST", "PORT", "NAME", "USER", "PASSWORD")
        )
        or options.get("sslmode") != "verify-full"
        or options.get("sslrootcert") != config["DB_SSLROOTCERT"]
        or settings.SECRET_KEY != config["SECRET_KEY"]
        or getattr(settings, "SECUREWISE_ENCRYPTION_KEY", None) != config["SECUREWISE_ENCRYPTION_KEY"]
    ):
        raise ValueError("Effective Django configuration differs from the enrolled worker configuration.")
