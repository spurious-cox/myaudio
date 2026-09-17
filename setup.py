"""py2app build for MyAudio.app — v1.4

    ./venv/bin/python setup.py py2app
    cp -R dist/MyAudio.app /Applications/
"""

import re

from setuptools import setup

# One version, and it lives in myaudio/__init__.py. A second copy here
# shipped 1.27.0 in the Info.plist while the app itself said 1.28.0.
VERSION = re.search(r'"(.+?)"', open("myaudio/__init__.py").read()).group(1)

APP = ["main.py"]
# The agent ships INSIDE the bundle so a copy on another Mac has one to run.
# launchd still owns it -- that is what holds Local Network permission -- but
# the plist is now written at launch by agentclient.ensure_agent(), pointing
# at wherever this bundle actually is.
DATA_FILES = [("", ["helper/coreaudio_helper", "agent/myaudio_agent.py"])]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "icon/MyAudio.icns",
    "packages": [
        "myaudio",
        "pyatv",
        "aiohttp",
        "cffi",
        "miniaudio",
        "zeroconf",
        "cryptography",
        "charset_normalizer",
    ],
    # pyatv pulls miniaudio, whose cffi extension py2app misses on its own.
    "includes": ["_cffi_backend"],
    "plist": {
        "CFBundleName": "MyAudio",
        "CFBundleDisplayName": "MyAudio",
        "CFBundleIdentifier": "com.timmccoy.myaudioctl",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "13.0",
        # Python writes __pycache__ beside the source it imports, and inside a
        # signed bundle that BREAKS THE SEAL: codesign reports "a sealed
        # resource is missing or invalid" the moment the app has run once, and
        # a notarized copy on another Mac would be refused. The interpreter is
        # told not to write bytecode at all; the cost is import speed, which is
        # a few tens of milliseconds at launch.
        "LSEnvironment": {"PYTHONDONTWRITEBYTECODE": "1"},
        "NSHighResolutionCapable": True,
        # Shown in About MyAudio; py2app writes "Copyright not specified" otherwise.
        "NSHumanReadableCopyright": "Copyright © 2026 Tim McCoy. All rights reserved.",
        "CFBundleGetInfoString":
            "MyAudio — audio output panel for Bluetooth, AirPlay and built-in devices.",
        "NSLocalNetworkUsageDescription":
            "MyAudio finds your HomePods and Apple TV on the local network to show and adjust their volume.",
        "NSBluetoothAlwaysUsageDescription":
            "MyAudio connects and disconnects your paired Bluetooth headphones and speakers.",
        # NO NSBonjourServices. Declaring it turns into an allow-list that
        # restricts browsing to exactly those service types, and pyatv uses
        # more than can be listed reliably — with the key present every scan
        # returned zero devices. MyStuff omits it and discovery works.
    },
}

setup(
    name="MyAudio",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
