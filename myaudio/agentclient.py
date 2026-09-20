"""Client for the AirPlay agent — v1.7

The GUI cannot reach the network itself (see agent/myaudio_agent.py), so every
AirPlay operation goes over a Unix socket to the launchd-owned agent. Calls are
synchronous and cheap; the GUI already makes them from worker threads.
"""

import json
import logging
import os
import plistlib
import socket
import subprocess
import sys
import time

from .config import SUPPORT_DIR

log = logging.getLogger(__name__)

SOCKET_PATH = os.path.join(SUPPORT_DIR, "agent.sock")

# A refresh makes the agent rescan, so this has to clear the 8s scan plus the
# reconnects that follow it; the probe in `available` keeps its own short
# timeout. Restored from the pre-2026-09-14 source.
TIMEOUT = 25.0

LABEL = "com.timmccoy.myaudioagent"
PLIST_PATH = os.path.expanduser("~/Library/LaunchAgents/%s.plist" % LABEL)


def _bundle_root():
    """The .app this is running from, or None when running from a checkout."""
    contents = os.path.dirname(os.path.dirname(os.path.realpath(sys.executable)))
    root = os.path.dirname(contents)
    if root.endswith(".app") and os.path.isdir(os.path.join(contents, "Resources")):
        return root
    return None


def _job(bundle):
    """The launchd job this bundle needs, as a plist dictionary."""
    res = os.path.join(bundle, "Contents", "Resources")
    tag = "python%d.%d" % sys.version_info[:2]
    lib = os.path.join(res, "lib")
    return {
        "Label": LABEL,
        # The interpreter at its own path. Running a COPY of it named
        # MyAudioAgent does put that name in the Local Network prompt and in
        # Privacy & Security, which is what a released build wants -- but it is a
        # new binary to TCC, so discovery stays dead until the fresh grant takes
        # effect, and it did not come up during testing. Left for release, when a
        # stable Developer ID signature makes the grant survive rebuilds.
        "ProgramArguments": [
            os.path.join(bundle, "Contents", "MacOS", "python"),
            os.path.join(res, "myaudio_agent.py"),
        ],
        "EnvironmentVariables": {
            # Bytecode written next to the source breaks the bundle's signature,
            # and LSEnvironment does not reach a launchd job, so it is set again
            # here. The rest is what the interpreter needs to find its own
            # standard library and the packaged myaudio/pyatv.
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHOME": res,
            "PYTHONPATH": ":".join([
                os.path.join(lib, "python%d%d.zip" % sys.version_info[:2]),
                os.path.join(lib, tag),
                os.path.join(lib, tag, "lib-dynload"),
                res,
            ]),
        },
        "RunAtLoad": True,
        # Restart on a crash, but not on a clean exit -- the agent exits 0 when
        # it finds another one already serving the socket, and KeepAlive:true
        # would spin that into a restart loop.
        "KeepAlive": {"SuccessfulExit": False},
        "StandardErrorPath": os.path.expanduser("~/Library/Logs/MyAudioAgent.err.log"),
        # launchd defaults this to 256. The agent holds a socket per AirPlay
        # receiver plus mDNS sockets that accumulate; at 256 it can no longer
        # accept(), and every call from here returns empty.
        "SoftResourceLimits": {"NumberOfFiles": 4096},
    }


# When the agent was last bootstrapped by this process. The agent takes a few
# seconds to open its socket, and during that gap it is unreachable for a
# reason the user does not need to act on.
_bootstrapped_at = 0.0
STARTING_SECONDS = 20.0


def starting():
    """True when we have just started the agent and it is still coming up."""
    return 0 < (time.time() - _bootstrapped_at) < STARTING_SECONDS


def ensure_agent():
    """Install or refresh the launchd job, so a copy of this bundle anywhere
    gets an agent pointing at itself. Returns (ok, message)."""
    bundle = _bundle_root()
    if bundle is None:
        return True, "running from a checkout; build.sh owns the agent"

    # Gatekeeper runs a quarantined app from a read-only randomized copy under
    # AppTranslocation, and sys.executable then points into a temp directory
    # macOS will delete. A launchd job written from that path is broken the
    # moment the copy goes away, and a second agent started from the real bundle
    # fights this one for the socket. Translocation is avoided by MOVING the app
    # -- dragging it out of the DMG to Applications -- not by copying it.
    if "/AppTranslocation/" in bundle:
        log.error("running translocated from %s", bundle)
        return False, ("MyAudio is running from a temporary copy. Drag it to "
                       "your Applications folder and open it from there.")

    wanted = _job(bundle)
    try:
        with open(PLIST_PATH, "rb") as fh:
            current = plistlib.load(fh)
    except Exception:
        current = None
    if current == wanted:
        return True, "agent job already current"

    try:
        os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)
        with open(PLIST_PATH, "wb") as fh:
            plistlib.dump(wanted, fh)
    except OSError as exc:
        log.error("could not write %s: %s", PLIST_PATH, exc)
        return False, "could not write the agent's launchd job: %s" % exc

    # launchd caches a job's configuration: `kickstart -k` restarts the process
    # but keeps the old plist, so a changed one has to be booted out first.
    domain = "gui/%d" % os.getuid()
    service = "%s/%s" % (domain, LABEL)
    subprocess.run(["launchctl", "bootout", service], capture_output=True)

    # bootout returns before launchd has finished tearing the job down, and
    # bootstrapping onto a label that is still going away fails with EIO. Wait
    # for it to disappear rather than guessing at a sleep.
    for _ in range(50):
        gone = subprocess.run(["launchctl", "print", service],
                              capture_output=True).returncode != 0
        if gone:
            break
        time.sleep(0.1)

    result = subprocess.run(["launchctl", "bootstrap", domain, PLIST_PATH],
                            capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        log.error("launchctl bootstrap failed: %s", detail)
        return False, "could not start the AirPlay agent: %s" % detail

    log.info("agent job installed for %s", bundle)
    global _bootstrapped_at
    _bootstrapped_at = time.time()
    return True, "agent installed"


class AgentClient:
    def __init__(self, socket_path=SOCKET_PATH):
        self.socket_path = socket_path
        self.last_scan_count = None
        self.last_error = ""
        self._speakers = []

    @property
    def available(self):
        """Actually connect — a stale socket file outlives a killed agent and
        would otherwise read as "running"."""
        if not os.path.exists(self.socket_path):
            return False
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1.0)
        try:
            probe.connect(self.socket_path)
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def _call(self, cmd, **kwargs):
        payload = dict(kwargs, cmd=cmd)
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(TIMEOUT)
        try:
            conn.connect(self.socket_path)
            conn.sendall((json.dumps(payload) + "\n").encode())
            chunks = []
            while not chunks or not chunks[-1].endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            self.last_error = ""
            return json.loads(b"".join(chunks).decode())
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("agent call %s failed: %s", cmd, self.last_error)
            return {"ok": False, "message": self.last_error}
        finally:
            conn.close()

    # -- reads ------------------------------------------------------------
    def poll(self):
        """Refresh the cached speaker list. Returns the list."""
        result = self._call("snapshot")
        if result.get("ok"):
            self._speakers = result.get("speakers", [])
            self.last_scan_count = result.get("scan_count")
        else:
            self._speakers = []
            self.last_scan_count = None
        return self._speakers

    def snapshot(self):
        return list(self._speakers)

    # -- actions ----------------------------------------------------------
    def refresh(self):
        result = self._call("refresh")
        if result.get("ok"):
            self._speakers = result.get("speakers", [])
            self.last_scan_count = result.get("scan_count")
        return result.get("ok", False), result.get("message", "")

    def set_power(self, key, on):
        result = self._call("set_power", key=key, on=on)
        return result.get("ok", False), result.get("message", "")

    def step_volume(self, key, delta):
        result = self._call("step_volume", key=key, delta=delta)
        return result.get("ok", False), result.get("message", "")

    def set_volume(self, key, value):
        result = self._call("set_volume", key=key, value=value)
        return result.get("ok", False), result.get("message", "")

    def output_devices(self, key):
        result = self._call("output_devices", key=key)
        return result.get("ok", False), result.get("options", [])

    def set_output_devices(self, key, identifiers):
        result = self._call("set_output_devices", key=key, identifiers=identifiers)
        return result.get("ok", False), result.get("message", "")

    def begin_pairing(self, key, protocol="companion"):
        result = self._call("pair_begin", key=key, protocol=protocol)
        return result.get("ok", False), result.get("message", "")

    def finish_pairing(self, key, pin):
        result = self._call("pair_finish", key=key, pin=pin)
        return result.get("ok", False), result.get("message", "")

    def cancel_pairing(self, key):
        self._call("pair_cancel", key=key)
