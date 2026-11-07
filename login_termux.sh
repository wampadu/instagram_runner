#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

echo "Instagram private login setup for Termux"
echo "This installs an unofficial client. It does not automate likes/follows."
echo "Credentials and verification codes are entered locally, never uploaded."
if [[ "${PREFIX:-}" != *"com.termux"* ]]; then
  echo "Run this script inside the Termux Android app."
  exit 1
fi

pkg update -y
pkg install -y python git clang make pkg-config libffi openssl rust
mkdir -p "$HOME/.instagram_runner"
chmod 700 "$HOME/.instagram_runner"
python -m venv "$HOME/.instagram_runner/venv"
source "$HOME/.instagram_runner/venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel
# Pinned source revision includes improved handling of missing Instagram encryption keys.
python -m pip install 'git+https://github.com/subzeroid/aiograpi.git@872039d37a61e5d60e07d47d3a230eafc23085e8'
python -c 'from aiograpi import Client; from scripts.aiograpi_interactive_login import authenticate; print("Termux imports: PASS")'
echo "Starting one interactive login attempt."
python scripts/aiograpi_interactive_login.py
