import os
import subprocess
import sys
import sysconfig

from setuptools import setup


APP = ["clock_app.py"]


def extra_frameworks():
    """Bundle libffi when the active Python links _ctypes to an external copy."""
    linked_paths = []
    linked_names = []
    try:
        import _ctypes

        result = subprocess.run(
            ["otool", "-L", _ctypes.__file__],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines()[1:]:
            path = line.strip().split(" ", 1)[0]
            name = os.path.basename(path)
            if not name.startswith("libffi") or not name.endswith(".dylib"):
                continue
            if path.startswith("/") and not path.startswith("/usr/lib/"):
                linked_paths.append(path)
            linked_names.append(name)
    except Exception:
        pass

    lib_dirs = [
        sysconfig.get_config_var("LIBDIR"),
        os.path.join(sys.prefix, "lib"),
        os.path.join(sys.base_prefix, "lib"),
        os.path.join(os.path.dirname(sys.executable), "..", "lib"),
        os.environ.get("CONDA_PREFIX")
        and os.path.join(os.environ["CONDA_PREFIX"], "lib"),
    ]

    frameworks = []
    for path in linked_paths:
        if os.path.exists(path):
            frameworks.append(os.path.realpath(path))
    for lib_dir in lib_dirs:
        if not lib_dir:
            continue
        for name in linked_names:
            path = os.path.join(os.path.abspath(lib_dir), name)
            if os.path.exists(path):
                frameworks.append(os.path.realpath(path))

    return list(dict.fromkeys(frameworks))

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/StatusBarClock.icns",
    "packages": [
        "ntplib",
        "rumps",
    ],
    "excludes": [
        "tkinter",
        "tcl",
        "tk",
    ],
    "plist": {
        "CFBundleName": "StatusBarClock",
        "CFBundleDisplayName": "StatusBarClock",
        "CFBundleIdentifier": "com.local.statusbarclock",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "LSMinimumSystemVersion": "10.15",
        "LSUIElement": True,
        "NSHumanReadableCopyright": "Copyright © 2026",
    },
}

FRAMEWORKS = extra_frameworks()
if FRAMEWORKS:
    OPTIONS["frameworks"] = FRAMEWORKS

if __name__ == "__main__":
    setup(
        app=APP,
        name="StatusBarClock",
        options={"py2app": OPTIONS},
    )
