#!/usr/bin/env bash
# One-shot setup for a fresh Ubuntu server.
#   scp -r first_cry user@server:~/    then    bash ~/first_cry/deploy/setup.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="$(whoami)"

echo "==> Installing Python"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip

echo "==> Creating virtualenv"
cd "$APP_DIR"
python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

echo "==> Checking configuration"
missing=0
for f in .env session.json; do
    if [ ! -f "$APP_DIR/$f" ]; then
        echo "    MISSING: $f  (copy it up from your laptop)"
        missing=1
    fi
done
[ "$missing" -eq 1 ] && echo "    Fix the above, then rerun this script." && exit 1

echo "==> Verifying the session still works"
./venv/bin/python check_session.py || {
    echo "    Session is dead. Run import_cookies.py on your laptop and copy session.json up again."
    exit 1
}

echo "==> Installing systemd service"
sed -e "s|/home/botuser/first_cry|$APP_DIR|g" \
    -e "s|^User=.*|User=$SERVICE_USER|" \
    "$APP_DIR/deploy/firstcry-bots.service" | sudo tee /etc/systemd/system/firstcry-bots.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable firstcry-bots
sudo systemctl restart firstcry-bots

echo
echo "==> Done. The bots are running and will start automatically on boot."
echo
echo "   status :  sudo systemctl status firstcry-bots"
echo "   logs   :  journalctl -u firstcry-bots -f"
echo "   stop   :  sudo systemctl stop firstcry-bots"
echo "   restart:  sudo systemctl restart firstcry-bots"
