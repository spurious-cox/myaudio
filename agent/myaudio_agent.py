"""MyAudio AirPlay agent — v1.3

Runs under launchd, OUTSIDE the app bundle, and owns every network operation.

Why this exists: on this Mac macOS will not grant Local Network access to the
MyAudio app bundle — it never appears in Privacy & Security ▸ Local Network and
is never prompted for, across three bundle IDs, two install paths and three
signing configurations. A launchd-run command-line process IS prompted ("Allow
Python to find devices on local networks?") and can hold the permission. A
child process of the app would inherit the app's denial, so the agent must be
owned by launchd, not spawned by the GUI.

The GUI talks to it over a Unix socket, which is local IPC and needs no
network permission at all.
"""

import asyncio
import json
import signal
import subprocess
import logging
import os
import resource
import socket
import sys

# Two layouts: in development this file sits in agent/ beside the myaudio
# package, and in the bundle it sits in Resources/ while the package is under
# Resources/lib/python3.14 (already on PYTHONPATH from the plist). Only the
# development case needs a path entry, and adding the bundle one would be a
# directory with no myaudio in it.
_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if os.path.isdir(os.path.join(_root, "myaudio")):
    sys.path.insert(0, _root)

from myaudio.airplay import AirPlayManager
from myaudio.config import SUPPORT_DIR, Store

SOCKET_PATH = os.path.join(SUPPORT_DIR, "agent.sock")
LOG_PATH = os.path.expanduser("~/Library/Logs/MyAudioAgent.log")

log = logging.getLogger("myaudio.agent")


async def dispatch(request, manager):
    cmd = request.get("cmd")
    if cmd == "snapshot":
        return {"ok": True, "speakers": manager.snapshot(),
                "scan_count": manager.last_scan_count}
    if cmd == "refresh":
        await manager.refresh()
        return {"ok": True, "speakers": manager.snapshot(),
                "scan_count": manager.last_scan_count}
    if cmd == "set_power":
        ok, message = await manager.set_power(request["key"], request["on"])
        return {"ok": ok, "message": message}
    if cmd == "step_volume":
        ok = await manager.step_volume(request["key"], request["delta"])
        return {"ok": bool(ok), "message": ""}
    if cmd == "pair_begin":
        ok, message = await manager.begin_pairing(
            request["key"], request.get("protocol", "companion"))
        return {"ok": ok, "message": message}
    if cmd == "pair_finish":
        ok, message = await manager.finish_pairing(request["key"], request["pin"])
        return {"ok": ok, "message": message}
    if cmd == "set_volume":
        ok, message = await manager.set_volume(request["key"], request["value"])
        return {"ok": ok, "message": message}
    if cmd == "output_devices":
        ok, options = await manager.output_devices(request["key"])
        return {"ok": ok, "options": options}
    if cmd == "set_output_devices":
        ok, message = await manager.set_output_devices(request["key"], request["identifiers"])
        return {"ok": ok, "message": message}
    if cmd == "pair_cancel":
        await manager.cancel_pairing(request["key"])
        return {"ok": True, "message": ""}
    return {"ok": False, "message": f"unknown command {cmd!r}"}


def make_handler(manager):
    async def handle(reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            if not line:
                return
            response = await dispatch(json.loads(line), manager)
        except Exception as exc:
            log.exception("request failed")
            response = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
        try:
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    return handle


async def watch_for_removal(stopping, interval=30, strikes=3):
    """Take the launchd job down when the app it belongs to is deleted.

    Deleting the app does not stop this process — a running binary keeps its
    files open — but it does make the job unstartable: launchd retries the
    missing executable forever and reports EX_CONFIG, and the plist outlives
    the app with nothing left to remove it. Only the still-running agent can
    clean up, so it watches for its own bundle going away.

    The strike count matters. An install does `rm -rf` then `cp -R`, so the
    bundle really is absent for a second or two while this agent is running;
    self-destructing there would break a routine upgrade. Three misses at
    thirty seconds means a real deletion is caught inside two minutes and an
    install is never noticed.
    """
    bundle = bundle_path()
    if bundle is None:
        return
    missing = 0
    while not stopping.is_set():
        await asyncio.sleep(interval)
        if os.path.exists(bundle):
            missing = 0
            continue
        missing += 1
        log.info("app bundle missing (%d of %d): %s", missing, strikes, bundle)
        if missing < strikes:
            continue
        log.info("app is gone — removing the launchd job and exiting")
        plist = os.path.expanduser(
            "~/Library/LaunchAgents/com.timmccoy.myaudioagent.plist")
        try:
            os.unlink(plist)
        except OSError:
            pass
        stopping.set()
        # bootout ends this process, so it is the last thing done.
        subprocess.run(["/bin/launchctl", "bootout",
                        "gui/%d/com.timmccoy.myaudioagent" % os.getuid()],
                       capture_output=True)
        return


def bundle_path():
    """The .app this agent is running from, or None outside a bundle."""
    here = os.path.dirname(os.path.realpath(__file__))
    parts = here.split(os.sep)
    for i in range(len(parts) - 1, 0, -1):
        if parts[i].endswith(".app"):
            return os.sep.join(parts[:i + 1])
    return None


async def main():
    os.makedirs(SUPPORT_DIR, exist_ok=True)
    # A socket file left by a crash blocks bind() and has to go -- but so does a
    # socket a LIVE agent is serving, and unlinking that one leaves it running
    # and unreachable while this process answers in its place. Connecting tells
    # the two apart: a refused connection means nobody is listening.
    if os.path.exists(SOCKET_PATH):
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1.0)
        try:
            probe.connect(SOCKET_PATH)
            log.error("another agent is already serving %s; this one is exiting",
                      SOCKET_PATH)
            return
        except OSError:
            os.unlink(SOCKET_PATH)
        finally:
            probe.close()

    store = Store()
    manager = AirPlayManager(store)
    asyncio.ensure_future(manager.run_forever())

    server = await asyncio.start_unix_server(make_handler(manager), path=SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o600)
    # The plist raises this from launchd's default of 256. At 256 the agent
    # runs out of descriptors, can no longer accept(), and every GUI call
    # comes back empty -- so the live value is worth stating outright.
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    log.info("open-file limit: soft=%s hard=%s", soft, hard)
    log.info("agent listening on %s", SOCKET_PATH)

    # launchctl unload sends SIGTERM, whose default action kills the process
    # outright — no finally, no cleanup. Catch it so the socket is removed.
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopping.set)
    asyncio.ensure_future(watch_for_removal(stopping))
    try:
        async with server:
            await stopping.wait()
            log.info("agent stopping")
    finally:
        # Leave no stale socket behind; a leftover file is inert but confusing,
        # and the client uses its presence to decide the agent is up.
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    logging.basicConfig(
        filename=LOG_PATH, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
