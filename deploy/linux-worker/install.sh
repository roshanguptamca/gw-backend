#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR=""
while (($#)); do
  case "$1" in
    --source)
      [[ $# -ge 2 ]] || { echo "--source requires a path" >&2; exit 2; }
      SOURCE_DIR="$2"
      shift 2
      ;;
    *)
      echo "Usage: sudo $0 --source /path/to/gw-backend" >&2
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

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Ubuntu/Debian apt-based Linux only." >&2
  exit 1
fi
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required; install OS packages explicitly, then rerun." >&2
  exit 1
}
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

python3 -m venv /opt/securewise/venv
/opt/securewise/venv/bin/pip install --requirement "$SOURCE_DIR/requirements.txt"
chown -R root:root /opt/securewise/venv
chmod -R go-w /opt/securewise/venv

install -d -o root -g securewise-worker -m 0750 /etc/securewise
install -d -o securewise-worker -g securewise-worker -m 0700 /var/lib/securewise-worker
install -o root -g root -m 0644 \
  "$(dirname "$0")/securewise-worker.service.example" \
  /etc/systemd/system/securewise-worker.service

systemctl daemon-reload
echo "Worker software installed. No service was started; no credentials, firewall rules, or Docker packages were changed."
echo "Create /etc/securewise/worker.env using a secret manager, then run:"
echo "  sudo systemctl enable --now securewise-worker"
