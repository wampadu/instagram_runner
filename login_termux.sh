#!/data/data/com.termux/files/usr/bin/bash
# Interactive login for Termux on Android, using Debian's glibc-compatible
# Python wheels instead of compiling unsupported Android Rust dependencies.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${PREFIX:-}" != *"com.termux"* ]]; then
  echo "Run this script inside the Termux Android app."
  exit 1
fi

echo "Setting up a private Linux Python environment inside Termux."
echo "No root, proxy, Instagram write actions, or remote credential upload."

pkg install -y proot-distro
if ! proot-distro login debian -- /bin/true >/dev/null 2>&1; then
  proot-distro install debian:bookworm
fi

# --shared-home maps the Termux home into Debian /root. This makes
# the repo and private session persistent without using Android storage.
proot-distro login debian --shared-home -- bash -lc '
  set -euo pipefail
  cd /root/instagram_runner
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates git python3 python3-pip python3-venv
  mkdir -p /root/.instagram_runner
  chmod 700 /root/.instagram_runner
  python3 -m venv /root/.instagram_runner/venv-debian
  source /root/.instagram_runner/venv-debian/bin/activate
  python -m pip install --disable-pip-version-check --prefer-binary \
    "git+https://github.com/subzeroid/aiograpi.git@872039d37a61e5d60e07d47d3a230eafc23085e8"
  python -c "from aiograpi import Client; from scripts.aiograpi_interactive_login import authenticate; print(\"Debian Python imports: PASS\")"
  echo "Installation complete. Instagram will ask for credentials privately in this terminal."
  python scripts/aiograpi_interactive_login.py
'
