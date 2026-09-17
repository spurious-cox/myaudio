"""Persistent store for MyAudio — v1.1

Remembers every device ever discovered plus its last known volume, so the app
can render a familiar list before any scan finishes.

v1.1: also remembers which devices the user has hidden.
"""

import json
import os
import plistlib
import threading

APP_NAME = "MyAudio"
SUPPORT_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
PLIST_PATH = os.path.join(SUPPORT_DIR, "devices.plist")

# MyStuff already paired with the Apple TV; reuse its credentials rather than
# making the user run through pairing a second time.
MYSTUFF_STATE = os.path.expanduser("~/Library/Application Support/MyStuff/state.json")

VOLUME_STEP = 5.0


class Store:
    def __init__(self, path=PLIST_PATH):
        self.path = path
        self._lock = threading.RLock()
        self._data = self._load()
        self._dirty_credentials = set()
        self._dirty_hidden = False
        self._hidden_mtime = None
        self._seed_credentials()

    def _load(self):
        try:
            with open(self.path, "rb") as fh:
                data = plistlib.load(fh)
        except (FileNotFoundError, plistlib.InvalidFileException, OSError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("devices", {})
        data.setdefault("credentials", {})
        data.setdefault("output_targets", {})
        data.setdefault("hidden", [])
        return data

    def _seed_credentials(self):
        if self._data["credentials"].get("apple_tv"):
            return
        try:
            with open(MYSTUFF_STATE) as fh:
                creds = json.load(fh).get("apple_tv", {}).get("credentials")
        except (OSError, ValueError):
            return
        if creds:
            with self._lock:
                self._data["credentials"]["apple_tv"] = creds
                self._dirty_credentials.add("apple_tv")
            self.save()

    def save(self):
        """Merge over what is on disk rather than replacing it.

        The GUI and the launchd agent each hold a Store and both write this
        file. A plain overwrite meant whichever saved last silently discarded
        the other's work — that is how an AirPlay pairing made by the agent
        vanished on the app's next refresh.
        """
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            merged = self._load()
            merged["devices"].update(self._data["devices"])
            merged.setdefault("output_targets", {}).update(
                self._data.get("output_targets", {}))
            # Only keys this process actually set may overwrite disk.
            for key in self._dirty_credentials:
                if key in self._data["credentials"]:
                    merged["credentials"][key] = self._data["credentials"][key]
            # Same rule for the hidden list: the agent never sets it, so only a
            # process that actually changed it may overwrite what is on disk.
            if self._dirty_hidden:
                merged["hidden"] = list(self._data.get("hidden", []))
            self._data = merged
            tmp = self.path + ".tmp"
            with open(tmp, "wb") as fh:
                plistlib.dump(self._data, fh)
            os.replace(tmp, self.path)

    # -- devices ---------------------------------------------------------
    def known_devices(self):
        with self._lock:
            return dict(self._data["devices"])

    def remember(self, key, name, kind, volume=None, address=None):
        with self._lock:
            entry = self._data["devices"].setdefault(key, {})
            entry["name"] = name
            entry["kind"] = kind
            if volume is not None:
                entry["volume"] = float(volume)
            if address:
                entry["address"] = address

    def known_addresses(self, kind):
        """Remembered IPs, so discovery can fall back to unicast."""
        with self._lock:
            return [e["address"] for e in self._data["devices"].values()
                    if e.get("kind") == kind and e.get("address")]

    def last_volume(self, key):
        with self._lock:
            value = self._data["devices"].get(key, {}).get("volume")
        return float(value) if value is not None else None

    def forget(self, key):
        with self._lock:
            self._data["devices"].pop(key, None)

    # -- hidden devices --------------------------------------------------
    def hidden_keys(self):
        """Devices the user has hidden, re-read when the file changes.

        The GUI hides a device and the AGENT has to stop connecting to it, but
        each process holds its own Store — so this checks the mtime rather than
        trusting the copy loaded at startup.
        """
        with self._lock:
            try:
                mtime = os.path.getmtime(self.path)
            except OSError:
                mtime = None
            if mtime != self._hidden_mtime:
                self._hidden_mtime = mtime
                self._data["hidden"] = list(self._load().get("hidden", []))
            return set(self._data.get("hidden", []))

    def is_hidden(self, key):
        return key in self.hidden_keys()

    def set_hidden(self, key, hidden=True):
        with self._lock:
            keys = set(self._data.get("hidden", []))
            keys.add(key) if hidden else keys.discard(key)
            self._data["hidden"] = sorted(keys)
            self._dirty_hidden = True
        self.save()

    def unhide_all(self):
        with self._lock:
            self._data["hidden"] = []
            self._dirty_hidden = True
        self.save()

    def hidden_devices(self):
        """[(key, name)] for the hidden list — names come from the device
        memory, since a hidden device is no longer in any snapshot."""
        known = self.known_devices()
        return sorted(((k, known.get(k, {}).get("name", k)) for k in self.hidden_keys()),
                      key=lambda pair: pair[1].lower())

    # -- output targets --------------------------------------------------
    def remember_output_target(self, identifier, name):
        """AirPlay receivers we have seen named in some device's output set.

        A Mac will not report its own output UUID (NotSupportedError), so the
        only way to learn it is to notice it in another device's outputs. Once
        seen it is remembered, so it can be offered from then on.
        """
        with self._lock:
            targets = self._data.setdefault("output_targets", {})
            if targets.get(identifier) == name:
                return
            targets[identifier] = name
        self.save()

    def known_output_targets(self):
        with self._lock:
            return dict(self._data.get("output_targets", {}))

    # -- credentials -----------------------------------------------------
    def credentials(self, key):
        with self._lock:
            return self._data["credentials"].get(key)

    def set_credentials(self, key, value):
        """A credential is a string; anything else cannot be written to the
        plist, and taking it in memory first left the store holding a value
        that every later save would trip over too."""
        if not isinstance(value, str) or not value:
            raise ValueError(f"refusing to store a non-string credential for {key}")
        with self._lock:
            self._data["credentials"][key] = value
            self._dirty_credentials.add(key)
        self.save()
