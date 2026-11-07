#!/data/data/com.termux/files/usr/bin/bash
# Run from the checked-out repository in Termux (not a system shell).
set -euo pipefail
cd "$(dirname "$0")"

echo "Termux Instagram login setup. No proxy; no likes or follows."
if [[ "${PREFIX:-}" != *"com.termux"* ]]; then
  echo "Error: this script must be run inside the Termux app."
  exit 1
fi

# Native Android packages should be installed through Termux, not compiled
# from standard Linux wheels. Keep the environment isolated but allow
# Termux's pre-built site packages to be visible.
pkg update -y
pkg install -y python git python-pillow clang make pkg-config libffi openssl rust
mkdir -p "$HOME/.instagram_runner"
chmod 700 "$HOME/.instagram_runner"
python -m venv --system-site-packages "$HOME/.instagram_runner/venv"
source "$HOME/.instagram_runner/venv/bin/activate"

# Don't upgrade pip itself: some Termux builds disallow replacing it.
# Android wheels from the Termux index avoid expensive Rust builds
# where compatible packages are available.
python -m pip install --prefer-binary \
  --extra-index-url https://termux-user-repository.github.io/pypi/ \
  'git+https://github.com/subzeroid/aiograpi.git@872039d37a61e5d60e07d47d3a230eafc23085e8'

python -c 'from aiograpi import Client; from scripts.aiograpi_interactive_login import authenticate; print("Termux imports: PASS")'

echo "Installation passed. Login will ask for secrets privately here."
python scripts/aiograpi_interactive_login.py
