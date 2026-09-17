"""Music.app AirPlay routing — v1.1

macOS offers no public API to route *system* audio to an AirPlay speaker, but
Music.app can be told which speakers to play through, and it accepts several at
once. That is the only way MyAudio can put this Mac's audio into another room.

Everything here is a no-op unless Music is already running — we never launch it
as a side effect of polling.
"""

import logging
import subprocess

log = logging.getLogger(__name__)

SEPARATOR = "\x1f"


def _osascript(script, timeout=10):
    try:
        proc = subprocess.run(["/usr/bin/osascript", "-e", script],
                              capture_output=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except (subprocess.SubprocessError, OSError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, proc.stderr.strip()
    return True, proc.stdout.strip()


def is_running():
    ok, out = _osascript('tell application "System Events" to '
                         '(name of processes) contains "Music"')
    return ok and out == "true"


COMPUTER_KIND = "computer"


def devices():
    """[{name, selected, kind, volume}] as Music sees them, [] if Music is down.

    Music keeps its own volume per speaker, separate from the Mac's output
    device level, so both are needed to explain a level that moves on its own.
    """
    if not is_running():
        return []
    script = (
        'set AppleScript\'s text item delimiters to "%s"\n'
        'tell application "Music"\n'
        '  set out to {}\n'
        '  repeat with d in AirPlay devices\n'
        '    set end of out to (name of d) & "%s" & (selected of d as text) '
        '& "%s" & (kind of d as text) & "%s" & (sound volume of d as text)\n'
        '  end repeat\n'
        '  return out as text\n'
        'end tell' % (SEPARATOR, SEPARATOR, SEPARATOR, SEPARATOR)
    )
    ok, out = _osascript(script)
    if not ok or not out:
        if not ok:
            log.warning("Music AirPlay query failed: %s", out)
        return []
    parts = out.split(SEPARATOR)
    found = []
    for i in range(0, len(parts) - 3, 4):
        try:
            volume = float(parts[i + 3])
        except ValueError:
            volume = None
        found.append({"name": parts[i],
                      "selected": parts[i + 1].strip().lower() == "true",
                      "kind": parts[i + 2],
                      "volume": volume})
    return found


def master_volume():
    """Music's overall volume — a third layer, above its per-speaker levels and
    below the Mac's output device. This one sitting at 28 was what made
    everything sound quiet regardless of the other two."""
    if not is_running():
        return None
    ok, out = _osascript('tell application "Music" to get sound volume')
    try:
        return float(out) if ok else None
    except ValueError:
        return None


def set_master_volume(value):
    """Music's overall level. Note this rescales every per-speaker level."""
    if not is_running():
        return False, "Music is not running"
    ok, out = _osascript('tell application "Music" to set sound volume to %d'
                         % max(0, min(100, int(round(value)))))
    return (True, "") if ok else (False, out[:100])


def set_selected(name, on):
    """Add or remove one speaker from Music's output set. Returns (ok, message)."""
    if not is_running():
        return False, "Music is not running"
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    if not on:
        # Music refuses to leave itself with no output, so hand playback back
        # to the Mac before dropping the speaker.
        computer = next((d["name"] for d in devices() if d["kind"] == COMPUTER_KIND), None)
        if computer and computer != name:
            _osascript('tell application "Music" to set selected of '
                       'AirPlay device "%s" to true'
                       % computer.replace("\\", "\\\\").replace('"', '\\"'))
    ok, out = _osascript('tell application "Music" to set selected of AirPlay device "%s" to %s'
                         % (escaped, "true" if on else "false"))
    if not ok:
        log.warning("Music routing to %s failed: %s", name, out)
        return False, (out.split(":")[-1].strip()[:100] or "could not change Music output")
    return True, ""
