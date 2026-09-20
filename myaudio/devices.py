"""Merges the CoreAudio, Bluetooth and AirPlay views into one device list — v1.8

v1.3: devices the user has hidden are dropped from the row list, and the
hidden set is read from the store so a hidden AirPlay speaker still lists.

v1.4: AirPlay rows can be selected as the system output, through sysoutput.
Once macOS is routing to one it may also publish it as a CoreAudio device, so
matching local rows are folded into the AirPlay row rather than listed twice.

v1.5: while the agent is still starting, the empty list says so instead of
telling the user to relaunch the app they just opened.

v1.6: when the Mac is routed to an AirPlay speaker, CoreAudio publishes one
device called "AirPlay" — never the speaker's name — so that row is folded
into the speaker it belongs to instead of being listed as an output of its own.

v1.7: several speakers can play at once, so that fold names a set rather than
one speaker, and every speaker in it shows as active.

v1.8: only a device with audio of its own — an Apple TV — offers a switch. A
HomePod is fed by something else, so its row reports, sets volume, and says
where the choice is made.
"""

import os
import socket
from dataclasses import dataclass, field

from . import agentclient, bluetooth, coreaudio, musicroute

KIND_ORDER = {"bluetooth": 0, "airplay": 1, "local": 2}

# "Mac Studio Speakers" and "Studio Display Speakers" are easy to confuse, and
# they are very different hardware — one small internal driver versus the
# display's array.
DISPLAY_NAMES = {"Mac Studio Speakers": "Mac Studio (internal)"}


@dataclass
class Row:
    key: str
    name: str
    kind: str
    on: bool
    volume: float | None = None       # 0-100, None when the device won't report one
    can_step: bool = False
    is_default: bool = False
    uid: str | None = None            # CoreAudio UID, when the Mac can route to it
    transport: str = ""               # CoreAudio transport: usb, blue, airp, bltn
    address: str = ""                 # Bluetooth MAC, for connect/disconnect
    connected: bool = False           # Bluetooth link is up (independent of `on`)
    can_toggle: bool = False          # On/Off can connect/disconnect this device
    can_select: bool = False          # On can make this the active output
    needs_pairing: bool = False
    power_on: bool = True             # AirPlay speaker is awake (vs standby)
    needs_airplay_pairing: bool = False  # second pairing, for output-device control
    supports_output_devices: bool = False
    can_send: bool = False             # has audio of its own worth sending on
    music_name: str = ""              # matching Music.app AirPlay speaker
    music_on: bool = False            # Music is currently playing through it
    music_volume: float | None = None # Music's own level for it (separate layer)
    music_owns_volume: bool = False    # Music is driving this speaker's level
    receiving_from: str = ""           # another device is feeding this speaker
    sending_to: list = field(default_factory=list)   # speakers this device feeds
    model: str = ""                    # HomePodMini, Gen4K, ...
    error: str = ""                    # last failed action, shown on the row
    detail: str = ""
    note: str = ""

    @property
    def sort_key(self):
        return (KIND_ORDER.get(self.kind, 9), self.name.lower())


@dataclass
class Snapshot:
    rows: list = field(default_factory=list)
    default_name: str = ""
    sources: list = field(default_factory=list)
    hint: str = ""
    music: list = field(default_factory=list)   # raw Music.app speaker levels
    hidden: list = field(default_factory=list)  # [(key, name)] the user hid


def _is_source(airplay_row):
    """True for an AirPlay device with audio of its own — an Apple TV.

    A HomePod only plays what something else sends it, which decides both
    whether it can forward audio and whether it gets a switch.
    """
    return (airplay_row.get("supports_output_devices", False)
            and airplay_row.get("model", "").lower().startswith(("gen", "appletv")))


def _row_is_source(row):
    """_is_source, for a built Row rather than the agent's dict."""
    return (row.supports_output_devices
            and row.model.lower().startswith(("gen", "appletv")))


def _is_airplay_output(row):
    """True for the placeholder CoreAudio device macOS adds while it streams to
    an AirPlay speaker. It is identified by transport, not by its name, which
    is the bare word "AirPlay" and could in principle be a device's own."""
    return row.transport == "airp"


def build(store, airplay_rows, scan_count=None, airplay_outputs=()):
    outputs = coreaudio.list_outputs()
    paired = bluetooth.paired_audio_devices()

    by_uid = {d["uid"]: d for d in outputs}
    claimed = set()
    rows = []

    for device in paired:
        mac = coreaudio.normalize_mac(device["address"])
        match = None
        if mac:
            for uid, out in by_uid.items():
                if out.get("transport") == "blue" and mac in coreaudio.normalize_mac(uid):
                    match = out
                    break
        key = f"bt:{device['address']}"
        toggle = bluetooth.can_control()
        if match is not None:
            claimed.add(match["uid"])
            volume = _percent(match.get("volume"))
            store.remember(key, device["name"], "bluetooth", volume)
            is_default = match.get("isDefault", False)
            rows.append(Row(
                key=key, name=device["name"], kind="bluetooth", on=is_default,
                volume=volume, can_step=match.get("canSetVolume", False),
                is_default=is_default, uid=match["uid"],
                address=device["address"], connected=True, can_toggle=toggle,
                can_select=True, detail=device["battery"],
                note="muted" if match.get("muted")
                else ("" if is_default else "connected"),
            ))
        else:
            store.remember(key, device["name"], "bluetooth")
            connected = device.get("connected", False)
            rows.append(Row(
                key=key, name=device["name"], kind="bluetooth", on=connected,
                # Paired-but-unrouted: no live volume to show, so show none
                # rather than a remembered figure that looks current.
                volume=None, can_step=False,
                address=device["address"], connected=connected, can_toggle=toggle,
                detail=device["battery"],
                note="no audio route yet" if connected else "not connected",
            ))

    for row in airplay_rows:
        # The radio shows whether sound is coming out; the note carries the
        # underlying power state so nothing is hidden by that simplification.
        note = ""
        if row["needs_pairing"]:
            note = "pairing required"
        elif row.get("needs_airplay_pairing"):
            note = "pair to send TV audio to speakers"
        elif row["error"]:
            note = row["error"]
        elif not row.get("power_on", True):
            note = "standby"
        elif not row["on"]:
            note = "on · idle"
        if not row["absolute"] and row["connected"] and not note:
            note = "relative volume only"
        rows.append(Row(
            key=row["key"], name=row["name"], kind="airplay", on=row["on"],
            volume=row["volume"], can_step=row["connected"],
            # Indicator only. Routing lives in Speakers…, and a switch that
            # merely toggles power sat teal on every row and meant nothing.
            can_toggle=False, needs_pairing=row["needs_pairing"],
            # The switch selects: it makes this device the Mac's output, which
            # sysoutput does through the Sound settings pane because CoreAudio
            # cannot. Only a device with audio of its own gets one. Sending the
            # Mac to a HomePod does work, but a HomePod is normally fed by
            # something else, and two ways to start it playing — a switch here
            # and a Speakers… menu there — contradict each other the moment one
            # shows teal and the other does not.
            can_select=(_is_source(row) and not row["needs_pairing"]
                        and row.get("power_on", True)),
            power_on=row.get("power_on", True),
            receiving_from=row.get("receiving_from", ""),
            sending_to=row.get("sending_to", []),
            model=row.get("model", ""),
            needs_airplay_pairing=row.get("needs_airplay_pairing", False),
            supports_output_devices=row.get("supports_output_devices", False),
            # A HomePod can technically forward audio, but it has none of its
            # own — offering the control only invites routing silence around.
            can_send=_is_source(row),
            detail=row["address"], note=note,
        ))

    for uid, out in by_uid.items():
        if uid in claimed:
            continue
        transport = out.get("transport", "")
        # A Bluetooth device can reach CoreAudio before the cached pairing
        # roster catches up, so classify it by transport rather than dropping it.
        kind = "bluetooth" if transport == "blue" else "local"
        key = f"ca:{uid}"
        volume = _percent(out.get("volume"))
        store.remember(key, out["name"], kind, volume)
        is_default = out.get("isDefault", False)
        rows.append(Row(
            key=key, name=DISPLAY_NAMES.get(out["name"], out["name"]),
            kind=kind, on=is_default, volume=volume,
            can_step=out.get("canSetVolume", False), is_default=is_default,
            can_select=True, uid=uid, transport=transport,
            detail=coreaudio.TRANSPORT_LABELS.get(transport, transport),
            note="muted" if out.get("muted") else "",
        ))

    music = _attach_music_routing(rows)
    for row in rows:
        if row.kind != "airplay":
            continue
        # Say plainly what the device is doing and, when it is doing nothing
        # interesting, point at the control that makes it useful.
        if row.needs_pairing or row.needs_airplay_pairing or row.note in (
                "pairing required", "pair to send TV audio to speakers"):
            continue
        if row.sending_to:
            row.note = "playing in " + ", ".join(sorted(row.sending_to))
        elif row.receiving_from:
            row.note = f"playing from {row.receiving_from}"
        elif not row.power_on:
            row.note = "standby"
        elif _row_is_source(row):
            row.note = "TV sound to Speakers…"
        else:
            # A HomePod has no switch, so an idle one has to say where the
            # choice that starts it playing is actually made.
            row.note = "idle · choose it in a Speakers… menu"
    rows.sort(key=lambda r: r.sort_key)
    store.save()
    # Read the active output BEFORE hiding anything: hiding the device that is
    # currently playing must not blank the "Playing through …" line, or the
    # sound has no visible source at all.
    # While the Mac plays through an AirPlay speaker, CoreAudio publishes a
    # device named "AirPlay" — a generic name for whichever speaker it is, with
    # nothing in it to say which. Listing it would add a meaningless row and
    # leave the speaker's own row looking inactive, so it is folded into the
    # speakers named by `airplay_outputs`, which is what the app last routed
    # to. Without those names the row is still dropped: a row called "AirPlay"
    # tells the user nothing they can act on.
    airplay_names = {r.name: r for r in rows if r.kind == "airplay"}
    kept = []
    for row in rows:
        if row.kind == "local" and row.uid and _is_airplay_output(row):
            # One placeholder device covers however many speakers are playing,
            # so its active state is given to each of them.
            for name in airplay_outputs:
                twin = airplay_names.get(name)
                if twin is None:
                    continue
                twin.is_default = twin.is_default or row.is_default
                twin.uid = twin.uid or row.uid
                if twin.volume is None:
                    twin.volume = row.volume
                    twin.can_step = twin.can_step or row.can_step
            continue
        # A speaker can also appear under its own name, on a Mac that does
        # publish one; fold that in the same way rather than listing it twice.
        twin = airplay_names.get(row.name) if row.kind == "local" else None
        if twin is not None and twin is not row:
            twin.is_default = twin.is_default or row.is_default
            twin.uid = twin.uid or row.uid
            continue
        kept.append(row)
    rows = kept

    default = next((r.name for r in rows if r.is_default), "")
    hidden_keys = store.hidden_keys()
    # From the store, NOT from rows: the agent skips hidden AirPlay speakers
    # entirely, so one never reaches this list and deriving the hidden set from
    # rows left it empty. The header button then did not appear and the only
    # way to unhide a speaker was to edit the plist by hand.
    hidden = store.hidden_devices()
    rows = [r for r in rows if r.key not in hidden_keys]
    sources = [s["name"] for s in coreaudio.playing_sources() if s.get("name")]
    hint = ""
    # A stopped agent reports no scan count at all, which previously fell
    # through every branch and left an empty list with no explanation.
    if not _agent_reachable():
        if agentclient.starting():
            # Launch just bootstrapped the agent and it has not opened its
            # socket yet. Telling someone to quit and relaunch the app they
            # have this second launched reads as a fault, when the speakers
            # are seconds away.
            hint = "Starting the AirPlay agent — speakers will appear in a moment."
        else:
            # Quitting and relaunching MyAudio is the fix most people want, and
            # it repoints the entry as well. `bootstrap` is the counterpart to
            # the `bootout` in Help; `load` is its deprecated predecessor.
            hint = ("AirPlay agent is not running, so no speakers can be found. "
                    "Quit and relaunch MyAudio to start it, or run:  launchctl bootstrap "
                    "gui/$(id -u) ~/Library/LaunchAgents/com.timmccoy.myaudioagent.plist")
    elif scan_count == 0:
        hint = _no_speakers_hint()
    elif scan_count == -1:
        hint = "AirPlay scan failed — see ~/Library/Logs/MyAudio.log"
    elif scan_count and not any(r.kind == "airplay" for r in rows):
        hint = _filtered_out_hint(scan_count)
    return Snapshot(rows=rows, default_name=default,
                    sources=sorted(set(sources)), hint=hint, music=music,
                    hidden=hidden)


def _attach_music_routing(rows):
    """Tag rows Music can play through. Local outputs are skipped: they all map
    onto Music's single "computer" entry, so a control there would light up
    every local row at once and decide nothing."""
    speakers = musicroute.devices()
    if not speakers:
        return []
    by_name = {s["name"]: s for s in speakers}
    computer = next((s for s in speakers if s["kind"] == musicroute.COMPUTER_KIND), None)
    if computer is not None:
        # Music treats the whole Mac as one destination. Attach it to the row
        # that is currently the active output, so there is exactly one place to
        # switch the Mac off as a Music destination instead of three or none.
        active_local = next((r for r in rows if r.kind == "local" and r.is_default), None)
        if active_local is not None:
            active_local.music_name = computer["name"]
            active_local.music_on = computer["selected"]
            active_local.music_volume = computer.get("volume")
    for row in rows:
        match = by_name.get(row.name)
        if match is None or row.kind == "local":
            continue
        row.music_name = match["name"]
        row.music_on = match["selected"]
        row.music_volume = match.get("volume")
        # Music writes its own slider value onto the speaker's hardware volume a
        # few seconds after it starts streaming (measured 2026-07-25: Bedroom
        # 55.4 -> 22.0 unprompted). Flag it so the level appearing to move on
        # its own has a visible explanation.
        if (row.music_on and row.volume is not None and match.get("volume") is not None
                and abs(row.volume - match["volume"]) < 1.5):
            row.music_owns_volume = True
    return speakers


AGENT_SOCKET = os.path.expanduser("~/Library/Application Support/MyAudio/agent.sock")


def _agent_reachable():
    """Connect rather than stat: a stale socket file survives a killed agent."""
    if not os.path.exists(AGENT_SOCKET):
        return False
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(1.0)
    try:
        probe.connect(AGENT_SOCKET)
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _no_speakers_hint():
    """Reached only when the agent IS up but its scan came back empty."""
    return ("No AirPlay speakers found. The agent is running but its scan came back empty — "
            "check Python is enabled in System Settings ▸ Privacy & Security ▸ Local Network, "
            "and that Little Snitch has no deny rule for Python. See ~/Library/Logs/MyAudioAgent.log")


def _filtered_out_hint(count):
    """Devices answered the scan, and every one of them was set aside.

    Without this the list is simply empty, which reads as "broken" when the
    truth is "nothing here is a speaker this app drives". On a network of
    Macs that is correct and expected; on a network of third-party speakers
    it is a limitation worth stating outright.
    """
    return ("%d AirPlay device%s answered, but none is a speaker MyAudio can "
            "control. It drives Apple speakers — HomePod, Apple TV, AirPort — "
            "so other Macs are passed over, and third-party AirPlay speakers "
            "(Sonos, Denon, an AirPlay 2 television) are not supported."
            % (count, "" if count == 1 else "s"))


def _percent(value):
    return None if value is None else round(float(value) * 100, 1)

