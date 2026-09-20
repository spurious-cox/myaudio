"""Routes the Mac's system audio to a device macOS will not expose to us — v1.3

WHY THIS EXISTS. CoreAudio has no device for an AirPlay speaker, so nothing in
coreaudio.py can make a HomePod the Mac's output. The only place macOS offers
that choice is its own interface, and the Sound settings pane publishes the
whole output list through the accessibility API: an outline called
OutputSourceTable whose rows carry the device name and a settable AXSelected.
Setting it is exactly what clicking the row does.

WHY SETTINGS AND NOT CONTROL CENTER. Control Center's Sound panel exposes the
same devices, as toggle buttons identified `sound-device-<name>`, and it is the
lighter-looking option. But its menu bar icon is absent from the accessibility
tree, so opening it means finding the icon on screen and clicking coordinates —
a screen-recording permission, and a position that moves whenever a menu bar
item comes or goes. The settings pane opens from a URL and needs neither.

It needs Accessibility permission, which the user grants once.
"""

import logging
import subprocess
import time

from AppKit import NSWorkspace, NSURL, NSRunningApplication
from ApplicationServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    AXUIElementSetAttributeValue,
    kAXErrorSuccess,
    kAXTrustedCheckOptionPrompt,
)

log = logging.getLogger(__name__)

PANE_URL = "x-apple.systempreferences:com.apple.Sound-Settings.extension"
TABLE_ID = "OutputSourceTable"
SETTINGS_APP = "System Settings"

# The pane draws before its table is populated, so a single look finds an empty
# window, and a cold launch of System Settings is slower still. These bound the
# wait rather than spinning forever on a pane that failed to open at all.
WAIT_SECONDS = 20.0
POLL_SECONDS = 0.2
# How long the list must hold still before it counts as complete.
SETTLE_SECONDS = 1.5
# How long a speaker is given to accept the stream once it has been picked.
TAKE_SECONDS = 10.0


def trusted():
    """True when this app already holds Accessibility permission."""
    return bool(AXIsProcessTrusted())


def request_trust():
    """Ask macOS to show its 'grant Accessibility' prompt. Returns the state now.

    The prompt is not modal to us and the answer arrives later — the user is
    sent to System Settings and may take a minute — so the caller has to treat
    False as 'not yet' rather than 'refused'.
    """
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))


def _attr(element, name):
    err, value = AXUIElementCopyAttributeValue(element, name, None)
    return value if err == kAXErrorSuccess else None


def _find(element, identifier, depth=0):
    if depth > 16:
        return None
    if _attr(element, "AXIdentifier") == identifier:
        return element
    for child in (_attr(element, "AXChildren") or []):
        found = _find(child, identifier, depth + 1)
        if found is not None:
            return found
    return None


def _texts(element, out=None, depth=0):
    out = [] if out is None else out
    if depth > 6:
        return out
    if _attr(element, "AXRole") == "AXStaticText":
        value = _attr(element, "AXValue")
        if value:
            out.append(str(value))
    for child in (_attr(element, "AXChildren") or []):
        _texts(child, out, depth + 1)
    return out


def _settings_app():
    """The running System Settings, found by process id.

    NSWorkspace's list of running applications is kept up to date by
    notifications, so in a worker thread with no run loop it can still name an
    app that has already quit — which made the pane look like it never opened
    and left a quit call pointing at a dead process. Asking the system for the
    pid each time avoids the stale list entirely.
    """
    found = subprocess.run(["/usr/bin/pgrep", "-x", SETTINGS_APP],
                           capture_output=True, text=True)
    if found.returncode != 0:
        return None
    pid = int(found.stdout.split()[0])
    return NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)


def _open_pane():
    """Open Sound settings. Returns True if we were the ones who launched it."""
    was_running = _settings_app() is not None
    NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(PANE_URL))
    return not was_running


def _table():
    """The output list, once the pane has drawn it."""
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        app = _settings_app()
        if app is not None:
            element = AXUIElementCreateApplication(app.processIdentifier())
            for window in (_attr(element, "AXWindows") or []):
                table = _find(window, TABLE_ID)
                if table is not None:
                    return table
        time.sleep(POLL_SECONDS)
    return None


def _rows(table):
    return [r for r in (_attr(table, "AXChildren") or [])
            if _attr(r, "AXRole") == "AXRow"]


def _settled_rows(table, want=None):
    """The output rows, once macOS has finished adding to them.

    The pane lists the wired and Bluetooth outputs immediately and appends
    AirPlay speakers a second or two later, so reading the table as soon as it
    exists reports a Mac with no speakers on the network. Waiting for the row
    count to hold still — or for the name we came for — fixes that without
    guessing at a fixed delay.
    """
    deadline = time.time() + WAIT_SECONDS
    rows = _rows(table)
    unchanged_since = time.time()
    while time.time() < deadline:
        if want is not None and any(_row_name(r) == want for r in rows):
            return rows
        time.sleep(POLL_SECONDS)
        current = _rows(table)
        if len(current) != len(rows):
            rows = current
            unchanged_since = time.time()
            continue
        rows = current
        if time.time() - unchanged_since >= SETTLE_SECONDS:
            return rows
    return rows


def _row_name(row):
    # Each row reads as [name, kind] — "Bedroom", "AirPlay".
    texts = _texts(row)
    return texts[0] if texts else ""


def close_settings(launched):
    """Put System Settings away, but only if opening the pane started it.

    Quitting a window the user had open themselves would lose whatever they
    were doing in it.
    """
    if not launched:
        return
    app = _settings_app()
    if app is not None:
        app.terminate()


def outputs():
    """[(name, kind, selected)] for every output macOS will route to.

    Returns an empty list when Accessibility is not granted or the pane never
    appeared, which the caller reports rather than retrying.
    """
    if not trusted():
        return []
    launched = _open_pane()
    try:
        table = _table()
        if table is None:
            return []
        found = []
        for row in _settled_rows(table):
            texts = _texts(row)
            if not texts:
                continue
            kind = texts[1] if len(texts) > 1 else ""
            found.append((texts[0], kind, bool(_attr(row, "AXSelected"))))
        return found
    finally:
        close_settings(launched)


def select(name):
    """Make `name` the system output. Returns (ok, message).

    `name` is the device's own name as macOS knows it, which is the name
    MyAudio holds as the row key — not a display name it substitutes.
    """
    if not trusted():
        return False, "MyAudio needs Accessibility permission to switch to this speaker."
    launched = _open_pane()
    try:
        table = _table()
        if table is None:
            return False, "Could not read the Sound settings output list."

        rows = _settled_rows(table, want=name)
        matches = [r for r in rows if _row_name(r) == name]
        if not matches:
            offered = ", ".join(_row_name(r) for r in rows) or "nothing"
            return False, f"macOS does not offer {name} as an output. It lists: {offered}."
        # Two devices can share a name, and there is nothing in the row to tell
        # them apart, so refuse rather than route to the wrong room.
        if len(matches) > 1:
            return False, f"More than one output is called {name} — switch it in Sound settings."

        row = matches[0]
        if _attr(row, "AXSelected"):
            return True, f"{name} is already the output."

        err = AXUIElementSetAttributeValue(row, "AXSelected", True)
        if err != kAXErrorSuccess:
            return False, f"macOS refused to switch to {name}."

        # Read it back: the write can succeed while the device declines. An
        # idle speaker takes several seconds to accept the stream, and a
        # two-second window reported a failure for a switch that then
        # completed on its own — so wait long enough for a sleeping HomePod.
        deadline = time.time() + TAKE_SECONDS
        while time.time() < deadline:
            time.sleep(0.2)
            if _attr(row, "AXSelected"):
                log.info("output switched to %s", name)
                return True, f"Output switched to {name}."
        log.warning("%s did not take the output within %.0fs", name, TAKE_SECONDS)
        return False, f"{name} did not take the output — try once more."
    finally:
        close_settings(launched)
