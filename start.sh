#!/usr/bin/env bash
# Image Forensics Inspector - macOS / Linux launcher
# Usage:
#   ./start.sh           : create venv, install deps, launch Web UI
#   ./start.sh --demo    : also prepare demo images and run a demo analysis first
set -e
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -d .venv ]; then
    echo "Creating Python virtualenv..."
    "$PYTHON_BIN" -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install --disable-pip-version-check -r requirements.txt

if [ "${1:-}" = "--demo" ]; then
    echo
    echo "=== Running one-click demo (data prep + analysis) ==="
    python demo.py
    echo
fi

URL="http://127.0.0.1:5000"
echo
echo "Starting Image Forensics Inspector at $URL"
echo "Press Ctrl+C to stop."
echo

# Best-effort browser open: macOS uses 'open', Linux uses 'xdg-open'
if command -v open >/dev/null 2>&1; then
    (sleep 1.5 && open "$URL") &
elif command -v xdg-open >/dev/null 2>&1; then
    (sleep 1.5 && xdg-open "$URL") &
fi

python webapp.py --host 127.0.0.1 --port 5000
