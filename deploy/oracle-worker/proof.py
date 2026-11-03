"""Refresh proof only for the exact root-enrolled, manually reviewed firewall."""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from policy import HOSTS, IDENTITY_PATH, PROOF_PATH, protected_json


def refresh(environment):
    identity = protected_json(IDENTITY_PATH)
    if identity.get("environment") != environment or identity.get("host") != HOSTS[environment]:
        raise ValueError("Firewall environment identity mismatch.")
    ruleset = subprocess.check_output(["nft", "list", "ruleset"], timeout=15)
    if hashlib.sha256(ruleset).hexdigest() != identity.get("egress_ruleset_sha256"):
        raise ValueError("Firewall no longer matches the reviewed deny-by-default ruleset.")
    subprocess.run(
        ["/bin/bash", str(Path(__file__).resolve().parents[1] / "linux-worker/verify.sh"), "--egress-only"],
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "SECUREWISE_URL_EGRESS_PROOF_FILE": PROOF_PATH},
        check=True,
        timeout=30,
    )


if __name__ == "__main__":
    try:
        if os.geteuid() != 0 or len(sys.argv) != 2 or sys.argv[1] not in HOSTS:
            raise ValueError("Root and an enrolled environment are required.")
        refresh(sys.argv[1])
    except Exception as exc:
        Path(PROOF_PATH).unlink(missing_ok=True)
        print(f"Egress verification failed ({type(exc).__name__}); proof invalidated.", file=sys.stderr)
        sys.exit(1)
