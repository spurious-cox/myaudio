"""Paired Bluetooth audio devices — v1.1

Prefers the Swift helper (IOBluetooth), which can also connect and disconnect.
IOBluetooth is TCC-guarded, so when that is unavailable the roster falls back to
system_profiler, which is read-only but always works.
"""

import json
import logging
import subprocess
import threading
import time

from . import coreaudio

log = logging.getLogger(__name__)

AUDIO_MINOR_TYPES = {"headphones", "headset", "speaker", "audio", "loudspeaker", "microphone"}

# system_profiler costs ~0.2s, so the pairing roster is cached; live connect
# state comes from CoreAudio and is not subject to this delay.
CACHE_TTL = 15
_cache = {"at": 0.0, "value": []}
_cache_lock = threading.Lock()

# Set once we learn whether the helper's IOBluetooth calls survive TCC.
_can_control = None


def can_control():
    """True when the helper can connect/disconnect, False when read-only."""
    return bool(_can_control)


def paired_audio_devices(force=False):
    """[{address, name, connected, battery}] for paired Bluetooth audio devices."""
    with _cache_lock:
        if not force and time.monotonic() - _cache["at"] < CACHE_TTL:
            return list(_cache["value"])
    found = _read()
    with _cache_lock:
        _cache["at"] = time.monotonic()
        _cache["value"] = found
    return list(found)


def invalidate():
    with _cache_lock:
        _cache["at"] = 0.0


def set_connected(address, connected):
    """(ok, error) — connect or disconnect a paired Bluetooth device."""
    ok, _out, err = coreaudio.bt_set_connected(address, connected)
    if ok:
        invalidate()
    else:
        log.warning("bluetooth %s failed for %s: %s",
                    "connect" if connected else "disconnect", address, err)
    return ok, err


def _read():
    global _can_control
    if not coreaudio.running_in_bundle():
        # Outside the app bundle the helper would be TCC-killed; use the
        # read-only path instead of generating a crash report.
        if _can_control is None:
            log.info("not running from the app bundle — Bluetooth control disabled")
        _can_control = False
        return _system_profiler()
    helper = coreaudio.bt_list()
    if helper is not None:
        if _can_control is not True:
            log.info("Bluetooth control available via IOBluetooth")
        _can_control = True
        # The helper knows nothing about battery levels; system_profiler does.
        batteries = {d["address"]: d["battery"] for d in _system_profiler()}
        for device in helper:
            device["battery"] = batteries.get(device["address"], "")
        return helper
    if _can_control is not False:
        log.warning("Bluetooth control unavailable — falling back to system_profiler (read-only)")
    _can_control = False
    return _system_profiler()


def _is_audio(info):
    minor = (info.get("device_minorType") or "").lower()
    if any(word in minor for word in AUDIO_MINOR_TYPES):
        return True
    return "a2dp" in (info.get("device_services") or "").lower()


def _battery(info):
    left = info.get("device_batteryLevelLeft")
    right = info.get("device_batteryLevelRight")
    single = info.get("device_batteryLevelMain") or info.get("device_batteryLevel")
    if left and right:
        return f"{left} / {right}"
    return single or left or right or ""


def _system_profiler():
    try:
        raw = subprocess.run(
            ["/usr/sbin/system_profiler", "-json", "SPBluetoothDataType"],
            capture_output=True, timeout=20, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
        blocks = json.loads(raw)["SPBluetoothDataType"]
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, IndexError):
        return []

    found = []
    for block in blocks:
        for field, connected in (("device_connected", True), ("device_not_connected", False)):
            for entry in block.get(field, []):
                for name, info in entry.items():
                    if not isinstance(info, dict) or not _is_audio(info):
                        continue
                    found.append({
                        "address": info.get("device_address", ""),
                        "name": name,
                        "connected": connected,
                        "battery": _battery(info),
                    })
    return found
