#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python setup.py py2app

APP_PATH="$ROOT_DIR/dist/StatusBarClock.app"
DMG_PATH="$ROOT_DIR/dist/StatusBarClock.dmg"
DMG_STAGE="$(mktemp -d)"
trap 'rm -rf "$DMG_STAGE"' EXIT

ditto "$APP_PATH" "$DMG_STAGE/StatusBarClock.app"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create \
    -volname "StatusBarClock" \
    -srcfolder "$DMG_STAGE" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

echo "Built: $APP_PATH"
echo "Built: $DMG_PATH"
