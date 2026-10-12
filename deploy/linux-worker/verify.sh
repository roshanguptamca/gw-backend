#!/usr/bin/env bash
set -Eeuo pipefail

BACKEND_DIR="${SECUREWISE_BACKEND_DIR:-/opt/securewise/backend}"
PYTHON="${SECUREWISE_PYTHON:-/opt/securewise/venv/bin/python}"
LIGHTWEIGHT=0
CHECK_CONNECTIVITY=0
CHECK_URL_EGRESS=0
EGRESS_ONLY=0
for argument in "$@"; do
  case "$argument" in
    --lightweight)
      LIGHTWEIGHT=1
      export SECUREWISE_WORKER_PROFILE=lightweight
      if [[ -z "${SECUREWISE_PYTHON:-}" ]]; then
        PYTHON=/opt/securewise/venv-lightweight/bin/python
      fi
      ;;
    --check-connectivity) CHECK_CONNECTIVITY=1 ;;
    --check-url-egress) CHECK_URL_EGRESS=1 ;;
    --egress-only) CHECK_URL_EGRESS=1; EGRESS_ONLY=1 ;;
    *)
      echo "Usage: $0 [--lightweight] [--check-connectivity] [--check-url-egress|--egress-only]" >&2
      exit 2
      ;;
  esac
done

if (( ! EGRESS_ONLY )); then
[[ -f "$BACKEND_DIR/manage.py" ]] || { echo "Backend not found: $BACKEND_DIR" >&2; exit 1; }
[[ -x "$PYTHON" ]] || { echo "Worker Python not found: $PYTHON" >&2; exit 1; }

printf 'OS: '
uname -srm
printf 'Python: '
"$PYTHON" --version
printf 'Runner architecture: '
python3 -c 'import platform; print(platform.machine())'

if (( LIGHTWEIGHT )); then
  echo "Scanner profile: lightweight (Semgrep, Trivy, Gitleaks, ZAP, Docker, browser and URL execution disabled)"
else
  for scanner in semgrep trivy gitleaks zap-baseline.py docker; do
    if command -v "$scanner" >/dev/null 2>&1; then
      printf '%s: available\n' "$scanner"
    else
      printf '%s: unavailable\n' "$scanner"
    fi
  done

  if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
      echo "Docker daemon: reachable for the current user"
    else
      echo "Docker CLI: present; daemon unavailable to the current user"
    fi
  fi
fi

if (( LIGHTWEIGHT )); then
  "$PYTHON" "$BACKEND_DIR/manage.py" securewise_worker --help --skip-checks >/dev/null
  if (( CHECK_CONNECTIVITY )); then
    "$PYTHON" "$BACKEND_DIR/manage.py" securewise_worker --check-connectivity --skip-checks
  else
    echo "Database check not run. Add --check-connectivity to perform an offline-only registration and heartbeat check."
  fi
else
  "$PYTHON" "$BACKEND_DIR/manage.py" check --database default
  "$PYTHON" "$BACKEND_DIR/manage.py" securewise_worker --help >/dev/null
fi

if systemctl is-active --quiet securewise-worker; then
  echo "Worker service: active"
else
  echo "Worker service: inactive"
fi
fi

if (( CHECK_URL_EGRESS )); then
  PROOF_FILE="${SECUREWISE_URL_EGRESS_PROOF_FILE:-/etc/securewise/url-egress-verification.json}"
  [[ $EUID -eq 0 ]] || { echo "Run egress verification as root." >&2; exit 1; }
  PROOF_DIR="$(dirname "$PROOF_FILE")"
  [[ -d "$PROOF_DIR" && ! -L "$PROOF_DIR" ]] || {
    echo "Proof directory must exist and must not be a symlink." >&2
    exit 1
  }
  read -r PROOF_DIR_UID PROOF_DIR_MODE < <(stat -c '%u %a' "$PROOF_DIR")
  [[ "$PROOF_DIR_UID" == "0" ]] || { echo "Proof directory must be root-owned." >&2; exit 1; }
  (( (8#$PROOF_DIR_MODE & 0022) == 0 )) || {
    echo "Proof directory must not be group/world writable." >&2
    exit 1
  }
  [[ ! -L "$PROOF_FILE" ]] || { echo "Refusing to write through a symlink proof path." >&2; exit 1; }
  RULESET="$(nft list ruleset)"
  TABLE="$(nft list table inet securewise_egress)"
  OUTPUT_CHAIN="$(awk '/chain output[[:space:]]*[{]/ {in_chain=1} in_chain {print} in_chain && /^[[:space:]]*}/ {exit}' <<<"$TABLE")"
  for required in "hook output" "policy drop" "ip daddr @blocked_ipv4 drop" "ip6 daddr @blocked_ipv6 drop"; do
    grep -Fq "$required" <<<"$OUTPUT_CHAIN" || {
      echo "Egress policy verification failed: missing '$required'." >&2
      exit 1
    }
  done
  for network in "0.0.0.0/8" "10.0.0.0/8" "100.64.0.0/10" "127.0.0.0/8" \
    "169.254.0.0/16" "172.16.0.0/12" "192.168.0.0/16" "224.0.0.0/4" \
    "::/128" "::1/128" "fc00::/7" "fe80::/10" "ff00::/8"; do
    # nft prints single IPv6 addresses (/128) without the prefix length.
    single="${network%/128}"
    grep -Fq "$network" <<<"$TABLE" ||
      { [[ "$single" != "$network" ]] && grep -Eq "(^|[[:space:],{])${single}([[:space:],}]|\$)" <<<"$TABLE"; } || {
      echo "Egress policy verification failed: forbidden range $network missing." >&2
      exit 1
    }
  done
  RULESET_SHA256="$(printf '%s' "$RULESET" | sha256sum | awk '{print $1}')"
  CHECKED_AT="$(date +%s)"
  HOSTNAME_VALUE="$(hostname)"
  umask 077
  printf '{"verified":true,"hostname":"%s","checked_at":%s,"ruleset_sha256":"%s"}\n' \
    "$HOSTNAME_VALUE" "$CHECKED_AT" "$RULESET_SHA256" >"$PROOF_FILE"
  chown root:root "$PROOF_FILE"
  chmod 0644 "$PROOF_FILE"
  echo "URL egress policy structure checked; this does not replace external firewall review or target-side testing."
fi
