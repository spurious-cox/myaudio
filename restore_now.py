"""Restore devices to the state captured at the app's last launch.

Used when MyAudio is killed rather than exited through the restore switch —
a rebuild, say — so the devices do not keep whatever the session left behind.

    ./venv/bin/python restore_now.py
"""
import sys

sys.path.insert(0, "/Users/timmccoy/My_Applications/MyAudio")

from myaudio import restore
from myaudio.agentclient import AgentClient

state = restore.load()
if state is None:
    print("no saved opening state — nothing to restore")
    raise SystemExit(0)

changes, failures = restore.restore(state, AgentClient())
print(f"restored {len(changes)} setting(s)")
for change in changes:
    print(f"  {change}")
if failures:
    # Printed loudly: build.sh runs this before killing the app, and a silent
    # partial restore there is how the devices kept a session's changes.
    print(f"COULD NOT restore {len(failures)} item(s):")
    for failure in failures:
        print(f"  !! {failure}")
    raise SystemExit(1)
