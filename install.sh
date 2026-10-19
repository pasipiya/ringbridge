#!/usr/bin/env bash
# Install ringbridge as a systemd user service running from this checkout.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/ringbridge"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

for pkg in python3-dbus python3-gi; do
    dpkg -s "$pkg" >/dev/null 2>&1 || echo "warning: $pkg not installed (needed for desktop sources): sudo apt install $pkg"
done
command -v baresip >/dev/null || echo "note: baresip not installed (needed for the sip channel): sudo apt install baresip"

mkdir -p "$CONFIG_DIR" "$UNIT_DIR"
if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
    install -m 600 "$REPO/config.example.toml" "$CONFIG_DIR/config.toml"
    echo "Created $CONFIG_DIR/config.toml: edit it, then run this script again."
    exit 0
fi
chmod 600 "$CONFIG_DIR/config.toml"

sed "s|@REPO@|$REPO|g" "$REPO/systemd/ringbridge.service" > "$UNIT_DIR/ringbridge.service"
systemctl --user daemon-reload
systemctl --user enable ringbridge.service
systemctl --user restart ringbridge.service
echo "ringbridge installed and running. Logs: journalctl --user -u ringbridge -f"
