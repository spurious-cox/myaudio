"""CoreAudio + Bluetooth access via the bundled Swift helper — v1.1"""

import json
import logging
import os
import subprocess
import sys

log = logging.getLogger(__name__)

# Devices macOS exposes that are not real speakers the user would pick.
IGNORED_TRANSPORTS = {"virt"}

TRANSPORT_LABELS = {
    "bltn": "Built-in",
    "usb": "USB",
    "blue": "Bluetooth",
    "hdmi": "HDMI",
    "airp": "AirPlay",
    "aggr": "Aggregate",
    "virt": "Virtual",
}


def running_in_bundle():
    """True when we are the packaged app.

    IOBluetooth is TCC-guarded and macOS attributes it to the *responsible*
    process. Inside MyAudio.app that is the app, which declares the usage
    description. Run from a shell or a test script it is the shell, which does
    not — and the helper is SIGKILLed, leaving a crash report each time. So
    Bluetooth control is only attempted from the real bundle.
    """
    return "/MyAudio.app/" in sys.executable


def helper_path():
    resources = os.path.normpath(
        os.path.join(os.path.dirname(sys.executable), "..", "Resources", "coreaudio_helper"))
    if os.path.exists(resources):
        return resources
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "helper", "coreaudio_helper"))


def run(*args, timeout=15):
    """(ok, stdout, error) — never raises, so a helper fault can't kill a poll."""
    try:
        # Explicit UTF-8: a py2app bundle runs under an ASCII locale, and device
        # names carry curly apostrophes.
        proc = subprocess.run([helper_path(), *args], capture_output=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except (subprocess.SubprocessError, OSError) as exc:
        return False, "", str(exc)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        if proc.returncode < 0 or proc.returncode > 128:
            detail += " (killed — likely missing Bluetooth permission)"
        return False, "", detail
    return True, proc.stdout, ""


def _json(*args):
    ok, out, err = run(*args)
    if not ok:
        log.warning("helper %s failed: %s", args[0], err)
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def list_outputs(include_ignored=False):
    """Output devices. `include_ignored` keeps virtual devices too, which the
    device list hides but the volume audit still wants to watch."""
    devices = _json("list") or []
    if include_ignored:
        return devices
    return [d for d in devices if d.get("transport") not in IGNORED_TRANSPORTS]


def playing_sources():
    """Apps currently sending audio to an output device."""
    return _json("sources") or []


def bt_list():
    """Paired Bluetooth audio devices, or None if the helper cannot ask."""
    return _json("btlist")


def bt_set_connected(address, connected):
    # Connecting blocks until the device answers. Powered-off headphones simply
    # never reply, and 15s of a dead switch reads as the app being broken.
    ok, out, err = run("btconnect" if connected else "btdisconnect", address, timeout=8)
    if not ok and "timed out" in err.lower():
        err = "no response — is it powered on and in range?"
    return ok, out, err


def set_volume(uid, fraction):
    return run("setvol", uid, f"{max(0.0, min(1.0, fraction)):.4f}")[0]


def set_default(uid):
    return run("setdefault", uid)[0]


def normalize_mac(text):
    """Hex digits of a MAC, for matching a BT address against a CoreAudio UID."""
    return "".join(c for c in (text or "").lower() if c in "0123456789abcdef")
