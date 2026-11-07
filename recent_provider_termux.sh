#!/data/data/com.termux/files/usr/bin/bash
# Read-only Instagram recent hashtag API. Never uses IG credentials.
set -euo pipefail
cd "$(dirname "$0")"
provider="${1:-socialfetch}"
tag="${2:-follow_for_follow}"
if [[ "$provider" != "socialfetch" && "$provider" != "openhandle" ]]; then
  echo "Usage: bash recent_provider_termux.sh [socialfetch|openhandle] [hashtag]"
  exit 2
fi
proot-distro login debian --shared-home -- bash -lc '
  cd /root/instagram_runner
  /root/.instagram_runner/venv-debian/bin/python scripts/hashtag_recent_provider.py "$@"
' bash "$tag" --provider "$provider" --hours 48
