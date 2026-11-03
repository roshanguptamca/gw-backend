"""Guard startup and verify worker health without claiming jobs in probe/health modes."""

import argparse
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

from policy import CAPABILITIES, IDENTITY_PATH, configure, protected_json, validate, validate_settings


def check_registration(registration, profile, after):
    from django.utils import timezone

    return bool(
        registration
        and registration.status == "online"
        and registration.last_seen_at.timestamp() > after
        and registration.last_seen_at >= timezone.now() - timedelta(seconds=45)
        and set(registration.capabilities) == CAPABILITIES[profile]
        and registration.metrics.get("worker_profile") == profile
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("worker", "probe", "health"))
    parser.add_argument("environment", choices=("acc", "production"))
    parser.add_argument("profile", choices=tuple(CAPABILITIES))
    args = parser.parse_args()
    release = Path(__file__).resolve().parents[2]
    config = protected_json(release.parent / "config.json")
    identity = protected_json(IDENTITY_PATH)
    validate(config, identity, args.environment, args.profile)
    configure(config, args.environment, args.profile)
    if args.profile == "website_passive":
        os.environ["SECUREWISE_URL_EGRESS_RULESET_SHA256"] = identity["egress_ruleset_sha256"]
    # Read effective settings before app startup or any database connection.
    sys.path.insert(0, str(release))
    from django.conf import settings

    validate_settings(settings, config)
    import django

    django.setup()
    from django.core.management import call_command
    from django.utils import timezone

    from apps.securewise.models import SecureWiseWorkerRegistration
    from apps.securewise.services.runners import discover_runner_capabilities

    if set(discover_runner_capabilities().capabilities) != CAPABILITIES[args.profile]:
        raise ValueError("Worker capability discovery does not match its restricted profile.")
    worker_id = f"oracle-{args.environment}-{args.profile}"
    if args.mode == "probe":
        call_command("securewise_worker", check_connectivity=True, worker_id=worker_id, skip_checks=True)
    elif args.mode == "worker":
        call_command(
            "securewise_worker",
            worker_id=worker_id,
            poll_interval=3,
            skip_checks=True,
            drain_file=f"/run/securewise-managed-{args.environment}-{args.profile}.drain",
        )
    else:
        deadline = time.monotonic() + 70
        first_seen = None
        started = timezone.now().timestamp()
        while time.monotonic() < deadline:
            registration = SecureWiseWorkerRegistration.objects.filter(worker_id=worker_id).first()
            if check_registration(registration, args.profile, started):
                if first_seen is None:
                    first_seen = registration.last_seen_at
                elif registration.last_seen_at > first_seen:
                    print("Worker startup, advancing heartbeat, profile and exact capabilities verified.")
                    return
            time.sleep(3)
        raise ValueError("Worker health verification timed out.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Django/driver exceptions can include connection strings. Never echo them to CI.
        print(
            f"Worker operation failed ({type(exc).__name__}); details suppressed to protect credentials.",
            file=sys.stderr,
        )
        sys.exit(1)
