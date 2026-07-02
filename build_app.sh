#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python setup.py py2app

echo "Built: $ROOT_DIR/dist/StatusBarClock.app"
