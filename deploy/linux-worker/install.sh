#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR=""
LIGHTWEIGHT=0
while (($#)); do
  case "$1" in
    --source)
      [[ $# -ge 2 ]] || { echo "--source requires a path" >&2; exit 2; }
      SOURCE_DIR="$2"
      shift 2
      ;;
    --lightweight)
      LIGHTWEIGHT=1
      shift
      ;;
    *)
      echo "Usage: sudo $0 --source /path/to/gw-backend [--lightweight]" >&2
      exit 2
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo after reviewing the script; no firewall or Docker changes are made." >&2
  exit 1
fi
[[ -n "$SOURCE_DIR" ]] || { echo "--source is required" >&2; exit 2; }
SOURCE_DIR="$(realpath "$SOURCE_DIR")"
[[ -f "$SOURCE_DIR/manage.py" && -f "$SOURCE_DIR/requirements.txt" ]] || {
  echo "Source directory must contain manage.py and requirements.txt" >&2
  exit 1
}
REQUIREMENTS_FILE="$SOURCE_DIR/requirements.txt"
SERVICE_FILE="$(dirname "$0")/securewise-worker.service.example"
VENV_DIR=/opt/securewise/venv
if (( LIGHTWEIGHT )); then
  REQUIREMENTS_FILE="$SOURCE_DIR/requirements-securewise-worker-lightweight.txt"
  SERVICE_FILE="$(dirname "$0")/securewise-worker-lightweight.service.example"
  VENV_DIR=/opt/securewise/venv-lightweight
  [[ -f "$REQUIREMENTS_FILE" ]] || {
    echo "Lightweight worker requirements not found: $REQUIREMENTS_FILE" >&2
    exit 1
  }
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Ubuntu/Debian apt-based Linux only." >&2
  exit 1
fi
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required; install OS packages explicitly, then rerun." >&2
  exit 1
}
if (( LIGHTWEIGHT )); then
  python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' || {
    echo "Lightweight worker mode requires Python 3.12; found $(python3 --version)." >&2
    exit 1
  }
  [[ -f "$SERVICE_FILE" && -f "$(dirname "$0")/securewise-worker-connectivity-check.service.example" ]] || {
    echo "Lightweight systemd service templates are missing." >&2
    exit 1
  }
fi
python3 -m venv --help >/dev/null 2>&1 || {
  echo "Python venv support is required; install the matching OS venv package explicitly." >&2
  exit 1
}

if ! id securewise-worker >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/securewise-worker --create-home \
    --shell /usr/sbin/nologin securewise-worker
fi
install -d -o root -g root -m 0755 /opt/securewise
if [[ -e /opt/securewise/backend && ! -L /opt/securewise/backend ]]; then
  echo "/opt/securewise/backend exists and is not a symlink; refusing to replace it." >&2
  exit 1
fi
ln -sfn "$SOURCE_DIR" /opt/securewise/backend

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --requirement "$REQUIREMENTS_FILE"
chown -R root:root "$VENV_DIR"
chmod -R go-w "$VENV_DIR"

install -d -o root -g securewise-worker -m 0750 /etc/securewise
install -d -o securewise-worker -g securewise-worker -m 0700 /var/lib/securewise-worker
install -o root -g root -m 0644 \
  "$SERVICE_FILE" \
  /etc/systemd/system/securewise-worker.service
if (( LIGHTWEIGHT )); then
  install -o root -g root -m 0644 \
    "$(dirname "$0")/securewise-worker-connectivity-check.service.example" \
    /etc/systemd/system/securewise-worker-connectivity-check.service
fi

systemctl daemon-reload
if (( LIGHTWEIGHT )); then
  echo "Lightweight worker profile installed. Static repository scans only; no service was started."
else
  echo "Worker software installed. No service was started; no credentials, firewall rules, or Docker packages were changed."
fi
echo "No credentials, firewall rules, or Docker packages were changed."
echo "Create /etc/securewise/worker.env using a secret manager, then run:"
echo "  sudo systemctl enable --now securewise-worker"
