#!/data/data/com.termux/files/usr/bin/bash
# Run no-cost read-only Instagram hashtag discovery in existing Termux Debian.
set -euo pipefail
cd "$(dirname "$0")"
tag="${1:-follow_for_follow}"
hours="${2:-0}"
proot-distro login debian --shared-home -- bash -lc '
  cd /root/instagram_runner
  exec /root/.instagram_runner/venv-instagrapi/bin/python -m scripts.instagram_web_recent "$@"
' bash "$tag" --hours "$hours"
