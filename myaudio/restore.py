"""Capture device state at launch, put it back on request, clear routing — v1.2

MyAudio is a remote control, not a session: every change it makes is written to
the real device and outlives the app. This module is the opt-in exception —
it photographs everything MyAudio is capable of changing when the window opens,
so "Restore devices to how I found them and exit" can undo a session's worth of
fiddling in one action.

Only state this app can actually change is captured. Anything altered from the
TV remote, Control Centre or another Mac is outside its reach and is left alone.

v1.1: an AirPlay output set that could NOT BE READ is recorded as None, not as
an empty list. Both were previously written as [], which reads back as "this
speaker sends its audio nowhere" -- a fact, not a failure. On 2026-08-21 the
agent was out of file descriptors, so the capture stored [] for the Apple TV
and the restore skipped silently; the TV was left sending its sound to the Mac
and stayed that way after MyAudio quit. A restore that cannot do its job now
says so in the log and in its own summary.

v1.2: clear_routing() sends every source's audio back to itself -- each Apple
TV plays only through its own speakers and Music plays only on this Mac. The
app runs it at launch and at quit, because a routing lives ON the device and
otherwise outlives the app.
"""

import json
import logging
import os

from . import bluetooth, coreaudio, musicroute
from .config import SUPPORT_DIR

# Persisted so a restore is still possible after the app is killed — the
# snapshot used to live only in the running process, so pkill destroyed the one
# thing needed to put the devices back.
STATE_PATH = os.path.join(SUPPORT_DIR, "opening_state.json")

log = logging.getLogger(__name__)


def capture(agent):
    """Photograph everything MyAudio can change. Cheap enough for launch."""
    snapshot = {"coreaudio": {}, "bluetooth": {}, "airplay": {}, "music": {}}

    for device in coreaudio.list_outputs(include_ignored=True):
        snapshot["coreaudio"][device["uid"]] = {
            "name": device["name"],
            "volume": device.get("volume"),
            "muted": device.get("muted", False),
            "was_default": device.get("isDefault", False),
        }

    for device in bluetooth.paired_audio_devices(force=True):
        snapshot["bluetooth"][device["address"]] = {
            "name": device["name"],
            "connected": device.get("connected", False),
        }

    for speaker in agent.poll():
        entry = {
            "name": speaker["name"],
            "volume": speaker.get("volume"),
            "power_on": speaker.get("power_on", True),
            "outputs": None,        # None = not read; [] = reads as "nowhere"
        }
        ok, options = agent.output_devices(speaker["key"])
        if ok:
            entry["outputs"] = [o["identifier"] for o in options if o["selected"]]
        else:
            # None means UNKNOWN. [] would mean "sends nowhere", which is a
            # real state this app can restore to -- and restoring to it on the
            # strength of a failed read is how the TV went silent.
            entry["outputs"] = None
            log.warning("could not read %s output set; it will not be restored",
                        speaker["name"])
        snapshot["airplay"][speaker["key"]] = entry

    speakers = musicroute.devices()
    if speakers:
        snapshot["music"] = {
            "master": musicroute.master_volume(),
            "devices": {s["name"]: {"volume": s.get("volume"), "selected": s["selected"]}
                        for s in speakers},
        }
    log.info("captured device state: %d outputs, %d bluetooth, %d airplay, music=%s",
             len(snapshot["coreaudio"]), len(snapshot["bluetooth"]),
             len(snapshot["airplay"]), bool(snapshot["music"]))
    save(snapshot)
    return snapshot


def save(snapshot):
    try:
        os.makedirs(SUPPORT_DIR, exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=1)
        os.replace(tmp, STATE_PATH)
    except OSError as exc:
        log.warning("could not save opening state: %s", exc)


def load():
    """The snapshot from the last launch, or None."""
    try:
        with open(STATE_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def clear_routing(agent):
    """Send every source's audio back to itself. Returns (changed, failed).

    An Apple TV's output set is emptied, which leaves it playing through its
    own speakers only. Music is left playing on this Mac alone. Volumes,
    Bluetooth connections and the Mac's own output are not touched.
    """
    changed = []
    failed = []

    speakers = musicroute.devices()
    for speaker in speakers:
        if speaker["selected"] and speaker["kind"] != musicroute.COMPUTER_KIND:
            ok, _ = musicroute.set_selected(speaker["name"], False)
            if ok:
                changed.append(f"Music off {speaker['name']}")
            else:
                failed.append(f"Music would not leave {speaker['name']}")

    for speaker in agent.poll():
        ok, options = agent.output_devices(speaker["key"])
        if not ok:
            # A HomePod has no output set to read; only a real failure on a
            # device that has one is worth reporting.
            if speaker.get("supports_output_devices"):
                failed.append(f"{speaker['name']} outputs could not be read")
            continue
        sending = [o["name"] for o in options if o["selected"]]
        if not sending:
            continue
        ok, _ = agent.set_output_devices(speaker["key"], [])
        if ok:
            changed.append(f"{speaker['name']} no longer sends to {', '.join(sending)}")
        else:
            failed.append(f"{speaker['name']} outputs would not clear")

    log.info("cleared routing: %d change(s): %s", len(changed), changed)
    if failed:
        log.warning("routing NOT fully cleared: %s", failed)
    return changed, failed


def restore(snapshot, agent):
    """Put everything back.

    Returns (changed, failed): what was put back, and what could NOT be, so a
    restore that silently achieved nothing can no longer look like success.
    """
    changed = []
    failed = []

    # Music first: routing changes can pull a speaker's hardware volume with
    # them, so undo it before restoring levels.
    music = snapshot.get("music") or {}
    if music and musicroute.is_running():
        for name, want in music.get("devices", {}).items():
            current = next((d for d in musicroute.devices() if d["name"] == name), None)
            if current is None:
                continue
            if current["selected"] != want["selected"]:
                ok, _ = musicroute.set_selected(name, want["selected"])
                if ok:
                    changed.append(f"Music {'to' if want['selected'] else 'off'} {name}")

    for key, want in snapshot.get("airplay", {}).items():
        if want.get("outputs") is None:
            # Never captured, so there is nothing trustworthy to put back.
            failed.append(f"{want['name']} outputs were never captured")
            log.warning("%s: output set was not captured; leaving it alone",
                        want["name"])
        else:
            ok, options = agent.output_devices(key)
            if not ok:
                failed.append(f"{want['name']} outputs could not be read")
                log.warning("%s: cannot read output set; NOT restored", want["name"])
            else:
                now = sorted(o["identifier"] for o in options if o["selected"])
                if now != sorted(want["outputs"]):
                    ok, _ = agent.set_output_devices(key, want["outputs"])
                    if ok:
                        changed.append(f"{want['name']} outputs restored")
                    else:
                        failed.append(f"{want['name']} outputs would not set")
                        log.warning("%s: set_output_devices refused", want["name"])
        live = next((s for s in agent.snapshot() if s["key"] == key), None)
        if live is None:
            continue
        if want.get("power_on") is not None and live.get("power_on") != want["power_on"]:
            agent.set_power(key, want["power_on"])
            changed.append(f"{want['name']} {'on' if want['power_on'] else 'off'}")
        if want.get("volume") is not None and live.get("volume") is not None:
            if abs(live["volume"] - want["volume"]) >= 1.0:
                ok, _ = agent.set_volume(key, want["volume"])
                if ok:
                    changed.append(f"{want['name']} volume {want['volume']:.0f}%")

    for address, want in snapshot.get("bluetooth", {}).items():
        live = next((d for d in bluetooth.paired_audio_devices(force=True)
                     if d["address"] == address), None)
        if live is None or live.get("connected") == want["connected"]:
            continue
        ok, _ = bluetooth.set_connected(address, want["connected"])
        if ok:
            changed.append(f"{want['name']} {'connected' if want['connected'] else 'disconnected'}")

    # Volumes before the default output, so the device we hand back is already
    # at the right level when it becomes active.
    current = {d["uid"]: d for d in coreaudio.list_outputs(include_ignored=True)}
    for uid, want in snapshot.get("coreaudio", {}).items():
        live = current.get(uid)
        if live is None or want["volume"] is None or live.get("volume") is None:
            continue
        if abs(live["volume"] - want["volume"]) >= 0.01:
            coreaudio.set_volume(uid, want["volume"])
            changed.append(f"{want['name']} volume {want['volume'] * 100:.0f}%")

    was_default = next((uid for uid, w in snapshot.get("coreaudio", {}).items()
                        if w.get("was_default")), None)
    if was_default and not current.get(was_default, {}).get("isDefault"):
        if coreaudio.set_default(was_default):
            changed.append(f"output back to {snapshot['coreaudio'][was_default]['name']}")

    if music and musicroute.is_running() and music.get("master") is not None:
        # Master last: it rescales every per-speaker level in Music.
        if abs((musicroute.master_volume() or 0) - music["master"]) >= 1.0:
            musicroute.set_master_volume(music["master"])
            changed.append(f"Music volume {music['master']:.0f}%")

    log.info("restore made %d change(s): %s", len(changed), changed)
    if failed:
        log.warning("restore COULD NOT complete %d item(s): %s", len(failed), failed)
    return changed, failed
