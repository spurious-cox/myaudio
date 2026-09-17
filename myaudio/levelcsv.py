"""Diagnostic recorder for every volume level, every poll — v1.0

TEMPORARY. This exists to explain why audible loudness changes while the
displayed device volume does not. Set ENABLED = False (or delete the call in
app.py) once that is understood.

Long format — one row per level per poll — because the set of devices changes
as speakers come and go, which a fixed column header could not survive:

    timestamp, key, value, changed

`changed` is 1 when the value differs from the previous poll, so the file can
be filtered down to just the transitions in Numbers.
"""

import csv
import logging
import os
import threading
from datetime import datetime

ENABLED = False   # diagnostic finished 2026-07-25: caught Music overwriting speaker volume on stream start
PATH = os.path.expanduser("~/Library/Logs/MyAudio-levels.csv")

log = logging.getLogger(__name__)


class Recorder:
    def __init__(self, path=PATH):
        self.path = path
        self._previous = {}
        self._lock = threading.Lock()
        self._failed = False

    def record(self, levels):
        if not ENABLED or self._failed:
            return
        stamp = datetime.now().isoformat(timespec="milliseconds")
        with self._lock:
            rows = [(stamp, key, value, 1 if self._previous.get(key) != value else 0)
                    for key, value in sorted(levels.items())]
            self._previous = dict(levels)
            try:
                new_file = not os.path.exists(self.path)
                with open(self.path, "a", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    if new_file:
                        writer.writerow(["timestamp", "key", "value", "changed"])
                    writer.writerows(rows)
            except OSError as exc:
                # Never let diagnostics break the app; log once and give up.
                self._failed = True
                log.warning("level CSV disabled, cannot write %s: %s", self.path, exc)
