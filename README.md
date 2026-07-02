# StatusBarClock

StatusBarClock is a small macOS menu bar clock built with Python, rumps, and AppKit. It renders the time as native menu bar text, so the title keeps normal macOS sizing instead of being squeezed into a bitmap icon.

[中文文档](README-zh.md)

## Features

- Show a city-prefixed clock in the macOS menu bar, for example `Tokyo 09:41`.
- Choose from built-in IANA time zones or enter a custom time zone name.
- Customize the menu bar text color with presets or a HEX value.
- Toggle seconds, date display, and 24-hour time.
- Sync display time against an NTP server without changing the system clock.
- Choose from built-in NTP servers, including `time.apple.com`.
- Enable or disable launch at login from the menu.
- Store user settings in `~/Library/Application Support/StatusBarClock/config.json`.

## Requirements

- macOS 10.15 or later
- Python 3.9 or later

Project dependencies are listed in `requirements.txt`. Runtime dependencies:

- `rumps`
- `pyobjc-framework-Cocoa`
- `ntplib`

`py2app` is included in the same file for local app packaging.
The build configuration also bundles external `libffi` automatically when the active Python requires it, so both native Python installs and Conda Python environments can use the same build script.

## Run From Source

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python clock_app.py
```

## Build The App

```bash
./build_app.sh
```

The packaged app is created at:

```text
dist/StatusBarClock.app
```

The app icon is configured in `setup.py` and uses:

```text
assets/StatusBarClock.icns
```

The editable SVG source is:

```text
assets/logo.svg
```

## Install

After building, copy the app bundle to `/Applications`:

```bash
cp -R dist/StatusBarClock.app /Applications/
```

Then open `StatusBarClock.app`. Because local builds are unsigned, macOS may block the first launch. If that happens, right-click the app and choose `Open`, or allow it from System Settings.

## Notes

StatusBarClock never changes the macOS system clock. NTP sync only calculates an offset and applies it to the time shown in the menu bar.

The current build script creates an unsigned local app. For public binary releases, sign and notarize the app with an Apple Developer ID.
