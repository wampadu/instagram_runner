#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
proot-distro login debian --shared-home -- bash -lc '
  set -euo pipefail
  python3 -m venv /root/.instagram_runner/venv-instagrapi
  /root/.instagram_runner/venv-instagrapi/bin/python -m pip install --disable-pip-version-check -q "instagrapi==3.2.6"
  cd /root/instagram_runner
  /root/.instagram_runner/venv-instagrapi/bin/python scripts/compare_old_instagrapi.py --tag follow_for_follow --amount 6
'
