#!/data/data/com.termux/files/usr/bin/bash
# Official Meta Graph API, only read operations. Does not use IG private session.
set -euo pipefail
cd "$(dirname "$0")"
if [[ "${1:-}" == "--check-access" ]]; then
  :
elif [[ "${1:-}" == "--recent" && -n "${2:-}" ]]; then
  :
else
  echo "Usage: bash meta_graph_termux.sh --check-access"
  echo "   or: bash meta_graph_termux.sh --recent follow_for_follow"
  exit 2
fi
proot-distro login debian --shared-home -- bash -lc '
  cd /root/instagram_runner
  exec /root/.instagram_runner/venv-debian/bin/python scripts/meta_graph_recent.py "$@"
' bash "$@"
