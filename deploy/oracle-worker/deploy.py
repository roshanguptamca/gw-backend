"""Root-only, opt-in releases; legacy ACC services and firewall rules are never replaced."""

import argparse
import fcntl
import grp
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import traceback
import uuid
from pathlib import Path, PurePosixPath

from policy import HOSTS, IDENTITY_PATH, protected_json, validate

ROOT = Path("/opt/securewise/managed")
UNIT_DIR = Path("/etc/systemd/system")
RUN_DIR = Path("/run")
LOG = None


def run(*command, **kwargs):
    kwargs.setdefault("stdout", LOG)
    kwargs.setdefault("stderr", subprocess.STDOUT)
    return subprocess.run(command, check=True, timeout=900, **kwargs)


def managed_directory(path):
    path.mkdir(exist_ok=True, mode=0o755)
    if path.is_symlink() or path.stat().st_uid != 0:
        raise ValueError("Managed release directories must be root-owned directories, not symlinks.")
    path.chmod(0o755)


def extract(archive, destination):
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not (member.isfile() or member.isdir())
                or any(part == ".env" or part.startswith(".env.") for part in path.parts)
            ):
                raise ValueError("Release archive contains an unsafe path, link, or dotenv file.")
        source.extractall(destination, members=members, filter="data")


def service_unit(environment, profile):
    name = f"securewise-managed-{environment}-{profile}"
    current = ROOT / environment / profile / "current"
    runtime = f"{current}/venv/bin/python {current}/code/deploy/oracle-worker/runtime.py"
    website = profile == "website_passive"
    return f"""[Unit]
Description=Managed SecureWise {environment} {profile}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=securewise-worker
Group=securewise-worker
WorkingDirectory={current}/code
ExecStartPre={runtime} probe {environment} {profile}
ExecStart={runtime} worker {environment} {profile}
Restart=on-failure
RestartSec=10
TimeoutStopSec=45
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
StateDirectory={name}
StateDirectoryMode=0700
ReadWritePaths=/var/lib/{name}
CPUQuota={"40%" if website else "100%"}
MemoryHigh={"160M" if website else "640M"}
MemoryMax={"224M" if website else "768M"}
MemorySwapMax={"0" if website else "2G"}
TasksMax={"64" if website else "128"}
LimitNOFILE={"1024" if website else "2048"}
KillMode=mixed

[Install]
WantedBy=multi-user.target
"""


def switch(link, target):
    temporary = link.with_name(f".switch-{uuid.uuid4().hex}")
    temporary.symlink_to(target)
    temporary.replace(link)


def active(unit):
    return subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False, timeout=15).returncode == 0


def drain(unit, flag):
    flag.touch(mode=0o600)
    deadline = time.monotonic() + 600
    while active(unit):
        if time.monotonic() > deadline:
            raise RuntimeError("Drain timed out; worker was not killed. Leave it draining and investigate.")
        time.sleep(3)
    run("systemctl", "stop", unit)


def check_runtime(release, mode, environment, profile):
    name = f"securewise-managed-{environment}-{profile}"
    run(
        "systemd-run",
        "--quiet",
        "--wait",
        "--pipe",
        "--collect",
        "--property=User=securewise-worker",
        "--property=Group=securewise-worker",
        "--property=NoNewPrivileges=true",
        "--property=ProtectSystem=strict",
        "--property=ProtectHome=true",
        "--property=PrivateTmp=true",
        f"--property=StateDirectory={name}",
        "--property=StateDirectoryMode=0700",
        f"--property=ReadWritePaths=/var/lib/{name}",
        "--property=RuntimeMaxSec=100",
        "--working-directory",
        str(release / "code"),
        str(release / "venv/bin/python"),
        str(release / "code/deploy/oracle-worker/runtime.py"),
        mode,
        environment,
        profile,
    )


def egress(release, environment):
    run(
        "/usr/bin/python3.12",
        str(release / "code/deploy/oracle-worker/proof.py"),
        environment,
    )
    timers = [f"securewise-managed-egress@{environment}.timer"]
    if environment == "acc":
        timers.append("securewise-egress-proof.timer")
    if not any(active(timer) for timer in timers):
        raise ValueError("A root-owned egress-proof refresh timer must be active.")


def activate(base, release, environment, profile):
    unit = f"securewise-managed-{environment}-{profile}.service"
    flag = RUN_DIR / f"securewise-managed-{environment}-{profile}.drain"
    current = base / "current"
    previous = current.resolve() if current.is_symlink() else None
    unit_path = UNIT_DIR / unit
    unit_content = service_unit(environment, profile)
    if unit_path.exists() and unit_path.read_text() != unit_content:
        raise ValueError("Managed unit differs from the reviewed template; review changes manually.")
    if profile == "website_passive":
        egress(release, environment)
    check_runtime(release, "probe", environment, profile)
    if unit_path.exists():
        drain(unit, flag)
    try:
        unit_path.write_text(unit_content)
        run("systemctl", "daemon-reload")
        switch(current, release)
        flag.unlink(missing_ok=True)
        run("systemctl", "start", unit)
        check_runtime(release, "health", environment, profile)
        run("systemctl", "is-active", "--quiet", unit)
        run("systemctl", "enable", unit)
        if previous:
            switch(base / "previous", previous)
    except Exception:
        # Never kill an in-flight job to claim a successful rollback.
        drain(unit, flag)
        if previous:
            switch(current, previous)
            flag.unlink(missing_ok=True)
            run("systemctl", "start", unit)
            check_runtime(previous, "health", environment, profile)
            print("Previous release and configuration restored and healthy.", file=sys.stderr)
        else:
            run("systemctl", "disable", unit)
            current.unlink(missing_ok=True)
            print("First installation failed; service left stopped.", file=sys.stderr)
        raise


def deploy(args):
    identity = protected_json(IDENTITY_PATH)
    config = json.loads(args.config.read_text())
    validate(config, identity, args.environment, args.profile)
    certificate = Path(config["DB_SSLROOTCERT"])
    for path in (certificate, *certificate.parents):
        metadata = path.lstat()
        if path.is_symlink() or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError("The database CA and its parents must be root-owned and protected.")
    if not certificate.is_file():
        raise ValueError("The provisioned database CA is missing.")
    base = ROOT / args.environment / args.profile
    for path in (ROOT, ROOT / args.environment, base, base / "releases"):
        managed_directory(path)
    with (ROOT / args.environment / "deployment.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.rollback:
            release = base / "previous"
            if not release.is_symlink() or release.resolve().parent != base / "releases":
                raise ValueError("No previous managed release is available.")
            previous_config = protected_json(release.resolve() / "config.json")
            validate(previous_config, identity, args.environment, args.profile)
            activate(base, release.resolve(), args.environment, args.profile)
            print("Previous managed release activated and verified.")
            return
        legacy = (
            "securewise-website-worker.service" if args.profile == "website_passive" else "securewise-worker.service"
        )
        if active(legacy):
            raise ValueError("Legacy worker is active; an operator must approve and perform migration first.")
        run("/usr/bin/python3.12", "-c", "import sys; assert sys.version_info[:2] == (3, 12)")
        release = base / "releases" / f"{args.revision}-{uuid.uuid4().hex[:8]}"
        release.mkdir(parents=True)
        extract(args.archive, release / "code")
        # The source release remains root-owned and immutable to the worker user.
        for directory, _, files in os.walk(release):
            Path(directory).chmod(0o755)
            for filename in files:
                path = Path(directory) / filename
                path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
        config_path = release / "config.json"
        config_path.write_text(json.dumps(config))
        os.chown(config_path, 0, grp.getgrnam("securewise-worker").gr_gid)
        config_path.chmod(0o640)
        previous_mask = os.umask(0o022)
        try:
            run("/usr/bin/python3.12", "-m", "venv", str(release / "venv"))
            run(
                str(release / "venv/bin/pip"),
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "-r",
                str(release / "code/requirements-securewise-worker-lightweight.txt"),
            )
        finally:
            os.umask(previous_mask)
        activate(base, release, args.environment, args.profile)
        print(f"Managed worker release {args.revision} is healthy.")


def main():
    global LOG
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", choices=tuple(HOSTS))
    parser.add_argument("profile", choices=("lightweight", "website_passive"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--revision", default="")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run through the approved root deployment account.")
    if not args.rollback and (not args.archive or not re.fullmatch(r"[0-9a-f]{40}", args.revision)):
        parser.error("Deployment requires a tracked-source archive and full commit SHA.")
    os.umask(0o077)
    log_directory = Path("/var/log/securewise-worker-deployments")
    log_directory.mkdir(mode=0o700, exist_ok=True)
    log_path = log_directory / f"{args.environment}-{args.profile}-{uuid.uuid4().hex}.log"
    with log_path.open("x") as log:
        LOG = log
        print(f"Restricted VM diagnostics: {log_path}")
        try:
            deploy(args)
        except Exception:
            traceback.print_exc(file=log)
            raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Deployment failed ({type(exc).__name__}); no exception payload logged.", file=sys.stderr)
        sys.exit(1)
