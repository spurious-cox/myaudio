"""Headless check of discovery + merge, without opening the GUI."""

import asyncio
import time

from myaudio import bluetooth, coreaudio, devices
from myaudio.airplay import AirPlayManager
from myaudio.config import Store


async def main():
    store = Store()
    print("== CoreAudio ==")
    for d in coreaudio.list_outputs():
        print(f"  {d['name']:<28} {d['transport']:<6} vol={d['volume']} default={d['isDefault']}")

    print("\n== Bluetooth paired audio ==")
    for d in bluetooth.paired_audio_devices(force=True):
        print(f"  {d['name']:<28} connected={d['connected']} battery={d['battery']!r}")

    print("\n== AirPlay (scanning) ==")
    manager = AirPlayManager(store)
    t0 = time.monotonic()
    await manager.refresh()
    print(f"  scan+connect took {time.monotonic() - t0:.1f}s")
    for s in manager.snapshot():
        print(f"  {s['name']:<28} on={s['on']} vol={s['volume']} absolute={s['absolute']} "
              f"pair={s['needs_pairing']} err={s['error']!r}")

    print("\n== Merged rows ==")
    snap = devices.build(store, manager.snapshot())
    print(f"  default output: {snap.default_name}")
    for r in snap.rows:
        print(f"  [{r.kind:<9}] {r.name:<28} on={str(r.on):<5} vol={r.volume} "
              f"step={r.can_step} note={r.note!r}")

    print("\n== Plist ==")
    print(" ", store.path)
    for k, v in store.known_devices().items():
        print(f"  {k:<40} {v}")

    await manager.close()
    await asyncio.sleep(0.5)


asyncio.run(main())
