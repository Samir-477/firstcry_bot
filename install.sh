#!/usr/bin/env bash
# Clone-and-run setup for Linux/macOS.
#   git clone <repo> && cd firstcry_bot && bash install.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Creating virtualenv"
python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

echo "==> Checking configuration"
if [ ! -f .env ]; then
    echo "    No .env found. Copy .env.example to .env and fill it in,"
    echo "    or run:  ./venv/bin/python setup_telegram.py"
    exit 1
fi

echo "==> Checking your FirstCry session"
./venv/bin/python check_session.py || {
    echo
    echo "    Session has expired or is missing. On a machine with a browser:"
    echo "      python import_cookies.py"
    echo "    then copy session.json here."
    exit 1
}

echo
echo "==> Ready. Start the bots with:"
echo "      ./venv/bin/python run_all.py"
