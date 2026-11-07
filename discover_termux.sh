#!/data/data/com.termux/files/usr/bin/bash
# Run saved-session read-only post discovery from Termux.
set -euo pipefail
cd "$(dirname "$0")"
if [[ "${PREFIX:-}" != *"com.termux"* ]]; then
  echo "Open this from Termux."
  exit 1
fi
if (( $# == 0 )); then
  echo "Usage: bash discover_termux.sh toronto [torontophotography] --max-age-hours 48"
  exit 2
fi
proot-distro login debian --shared-home -- bash -lc '
  set -e
  cd /root/instagram_runner
  /root/.instagram_runner/venv-debian/bin/python scripts/aiograpi_discover_posts.py "$@"
' bash "$@"
