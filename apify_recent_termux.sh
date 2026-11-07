#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
tag="${1:-follow_for_follow}"
proot-distro login debian --shared-home -- bash -lc '
  cd /root/instagram_runner
  /root/.instagram_runner/venv-debian/bin/python scripts/apify_recent_verified.py "$@"
' bash "$tag" --limit 20 --max-charge-usd 0.10
