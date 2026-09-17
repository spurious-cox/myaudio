"""AirPlay speakers (HomePod, Apple TV) via pyatv — v1.2

Holds a persistent pyatv connection per speaker so volume reads are cheap and
the roster can grow and shrink as devices appear on and leave the network.

v1.1: a dead connection is dropped so the next scan rebuilds it, and one bad
speaker no longer aborts the whole refresh.
v1.2: hidden speakers are skipped entirely — not connected, not offered
as an output target.
"""

import asyncio
import logging

import ifaddr

import pyatv
from pyatv.const import (DeviceState, FeatureName, FeatureState, PairingRequirement,
                         PowerState, Protocol)
from pyatv.exceptions import BlockedStateError

log = logging.getLogger(__name__)

SCAN_INTERVAL = 30
SCAN_TIMEOUT = 8

# pyatv reports these as speakers we can drive; anything else on the network
# (other Macs advertising AirPlay) is noise for this app.
SPEAKER_MODELS = ("homepod", "airport", "appletv", "gen4k", "gen4", "gen3", "homepodmini")


def local_addresses():
    """This Mac's own IPv4 addresses, so it can be told apart from other Macs
    advertising AirPlay. Only this one is wanted as a destination."""
    found = set()
    try:
        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if isinstance(ip.ip, str) and "." in ip.ip:
                    found.add(ip.ip)
    except Exception:
        pass
    return found


def speaker_uuid(conf):
    """The AirPlay "psi" property is the id other devices use to address this
    receiver as an output. It is published in the scan, so it needs no
    connection — and Macs advertise it even though they refuse to report it
    over the protocol."""
    for service in conf.services:
        psi = (getattr(service, "properties", {}) or {}).get("psi")
        if psi:
            return psi
    return None


class AirPlaySpeaker:
    def __init__(self, conf):
        self.identifier = conf.identifier
        self.key = f"airplay:{conf.identifier}"
        self.name = conf.name
        self.address = str(conf.address)
        self.model = conf.device_info.model.name
        self.conf = conf
        self.atv = None
        self.volume = None
        self.absolute = False
        self.needs_pairing = False
        self.error = ""
        self.power_on = None       # None = device does not report a power state
        self.supports_power = False
        self.playing = False       # audio actually coming out of it right now
        # Choosing which speakers a device sends ITS audio to arrives over the
        # AirPlay protocol, which pairs separately from Companion.
        self.supports_output_devices = False
        self.needs_airplay_pairing = False
        # The UUID other devices use to address this speaker as an output. It
        # is NOT derivable from the MAC-style scan identifier (Bedroom is
        # 4E:04:CE:D5:76:31 but 4C04CED5-7631-... as an output), so it has to
        # be read from the speaker itself.
        self.output_uuid = None
        # A speaker fed by another device reports device_state Idle — it is a
        # passive receiver — so "is sound coming out" has to come from whether
        # some other device lists it as an output.
        self.receiving_from = ""
        self.sending_to = []       # names of speakers this device feeds

    @property
    def connected(self):
        return self.atv is not None


class AirPlayManager:
    def __init__(self, store, on_change=None):
        self.store = store
        self.on_change = on_change or (lambda: None)
        self.speakers = {}
        self._pairing = {}
        self._pairing_protocol = {}
        self._lock = asyncio.Lock()
        # Every AirPlay receiver on the network, by its advertised speaker id.
        # Includes Macs, which are valid destinations but not devices we drive.
        self.targets = {}
        # None = no scan yet, -1 = scan raised, 0 = ran but saw nothing.
        self.last_scan_count = None

    def snapshot(self):
        """Plain dicts for the GUI thread — never hand out live pyatv objects."""
        return [{
            "key": s.key,
            "name": s.name,
            "kind": "airplay",
            "model": s.model,
            "address": s.address,
            "connected": s.connected,
            # "on" is whether sound is coming out of it, not merely whether it
            # has power — a powered but idle speaker reads as off.
            "on": bool(s.playing or s.receiving_from or s.sending_to),
            "playing": s.playing,
            "power_on": s.connected if s.power_on is None else s.power_on,
            "can_toggle": s.supports_power and s.connected,
            "supports_output_devices": s.supports_output_devices,
            "receiving_from": s.receiving_from,
            "sending_to": list(s.sending_to),
            "needs_airplay_pairing": s.needs_airplay_pairing,
            "volume": s.volume,
            "absolute": s.absolute,
            "needs_pairing": s.needs_pairing,
            "error": s.error,
        } for s in self.speakers.values()]

    async def run_forever(self):
        while True:
            try:
                await self.refresh()
            except Exception:
                log.exception("AirPlay refresh failed")
            await asyncio.sleep(SCAN_INTERVAL)

    async def refresh(self):
        async with self._lock:
            await self._scan()
            await self._poll_volumes()
            self._update_receivers()
        self.on_change()

    async def _scan(self):
        loop = asyncio.get_running_loop()
        try:
            found = await pyatv.scan(loop, timeout=SCAN_TIMEOUT)
        except Exception:
            log.exception("scan failed")
            self.last_scan_count = -1
            return
        log.info("scan saw %d device(s): %s", len(found),
                 ", ".join(c.name for c in found) or "none")
        if not found:
            found = await self._unicast_scan(loop)
        self.last_scan_count = len(found)

        seen = set()
        self.targets = {}
        mine = local_addresses()
        # A hidden speaker is skipped outright: not polled, not connected, and
        # not offered as somewhere to send audio. The cleanup loop below then
        # disconnects one that was hidden while it was live.
        hidden = self.store.hidden_keys()
        for conf in found:
            uuid = speaker_uuid(conf)
            if not uuid or f"airplay:{conf.identifier}" in hidden:
                continue
            # Real speakers, plus this Mac. Other people's Macs advertise
            # AirPlay too but are not speakers in this house — and the Apple TV
            # silently refuses them anyway, so offering them only misleads.
            if self._is_speaker(conf) or str(conf.address) in mine:
                self.targets[uuid] = conf.name
        for conf in found:
            if not self._is_speaker(conf):
                continue
            key = f"airplay:{conf.identifier}"
            if key in hidden:
                continue
            seen.add(key)
            speaker = self.speakers.get(key)
            if speaker is None:
                speaker = AirPlaySpeaker(conf)
                self.speakers[key] = speaker
            else:
                speaker.conf = conf
                speaker.name = conf.name
            speaker.output_uuid = speaker_uuid(conf) or speaker.output_uuid
            if not speaker.connected:
                await self._connect(speaker)

        for key in [k for k in self.speakers if k not in seen]:
            await self._disconnect(self.speakers.pop(key))

    async def _unicast_scan(self, loop):
        """Multicast browsing can be blocked while unicast still works, so
        retry the addresses we saw last time."""
        hosts = self.store.known_addresses("airplay")
        if not hosts:
            return []
        try:
            found = await pyatv.scan(loop, timeout=SCAN_TIMEOUT, hosts=hosts)
        except Exception:
            log.exception("unicast scan failed")
            return []
        log.info("unicast scan of %s saw %d device(s): %s", hosts, len(found),
                 ", ".join(c.name for c in found) or "none")
        return found

    @staticmethod
    def _is_speaker(conf):
        model = conf.device_info.model.name.lower()
        if any(tag in model for tag in SPEAKER_MODELS):
            return True
        # A Mac advertising AirPlay is a source, not a speaker we want to list.
        return False

    def _credentials_for(self, speaker, protocol=Protocol.Companion):
        """Credentials are stored per protocol; the bare key is the original
        Companion entry, kept so existing pairings keep working."""
        if protocol is Protocol.Companion:
            creds = self.store.credentials(speaker.key)
            if creds is None and speaker.model.lower().startswith(("gen", "appletv")):
                creds = self.store.credentials("apple_tv")
            return creds
        return self.store.credentials(f"{speaker.key}:{protocol.name.lower()}")

    async def _connect(self, speaker):
        conf = speaker.conf
        creds = self._credentials_for(speaker)
        airplay_creds = self._credentials_for(speaker, Protocol.AirPlay)
        needs = [s for s in conf.services if s.pairing == PairingRequirement.Mandatory]
        if needs and not creds:
            speaker.needs_pairing = True
            speaker.error = "pairing required"
            return
        if creds:
            # Companion alone is enough to drive volume; handing the same
            # credentials to AirPlay/RAOP makes the connect fail.
            conf.set_credentials(Protocol.Companion, creds)
        if airplay_creds:
            conf.set_credentials(Protocol.AirPlay, airplay_creds)
        try:
            speaker.atv = await pyatv.connect(conf, asyncio.get_running_loop())
            speaker.needs_pairing = False
            speaker.error = ""
            log.info("connected %s (%s) creds=%s", speaker.name, speaker.model, bool(creds))
        except Exception as exc:
            speaker.atv = None
            speaker.error = str(exc)[:80]
            log.warning("connect failed for %s (%s): %s", speaker.name, speaker.model, exc)

    async def _disconnect(self, speaker):
        if speaker.atv is not None:
            try:
                speaker.atv.close()
            except Exception:
                pass
            speaker.atv = None

    async def _poll_volumes(self):
        for speaker in self.speakers.values():
            if not speaker.connected:
                continue
            try:
                await self._poll_speaker(speaker)
            except BlockedStateError:
                # pyatv shields a connection the moment it dies, but the object
                # stays non-None -- so `connected` kept reading True and _scan
                # never rebuilt it. Drop it; the next scan reconnects.
                log.warning("connection to %s went dead; dropping it", speaker.name)
                await self._disconnect(speaker)
            except Exception:
                # One unreachable speaker must not abort the whole refresh --
                # _update_receivers() and on_change() come after this loop.
                log.exception("polling %s failed", speaker.name)

    async def _poll_speaker(self, speaker):
        features = speaker.atv.features
        speaker.supports_power = (
            features.get_feature(FeatureName.TurnOn).state == FeatureState.Available
            and features.get_feature(FeatureName.TurnOff).state == FeatureState.Available)
        if features.get_feature(FeatureName.PowerState).state == FeatureState.Available:
            try:
                speaker.power_on = speaker.atv.power.power_state == PowerState.On
            except Exception:
                speaker.power_on = None
        try:
            state = (await speaker.atv.metadata.playing()).device_state
            speaker.playing = state == DeviceState.Playing
        except Exception:
            speaker.playing = False
        speaker.supports_output_devices = (
            features.get_feature(FeatureName.SetOutputDevices).state == FeatureState.Available)
        # Only the Apple TV can forward its audio to other speakers, and it
        # needs AirPlay credentials on top of Companion to expose that.
        speaker.needs_airplay_pairing = (
            not speaker.supports_output_devices
            and speaker.model.lower().startswith(("gen", "appletv"))
            and self._credentials_for(speaker, Protocol.AirPlay) is None)
        if speaker.output_uuid is None:
            try:
                for device in (speaker.atv.audio.output_devices or []):
                    if device.name == speaker.name:
                        speaker.output_uuid = device.identifier
                        break
            except Exception:
                pass
        speaker.absolute = features.get_feature(FeatureName.SetVolume).state == FeatureState.Available
        if features.get_feature(FeatureName.Volume).state == FeatureState.Available:
            try:
                speaker.volume = float(speaker.atv.audio.volume)
            except Exception:
                speaker.volume = None
        else:
            speaker.volume = None
        self.store.remember(speaker.key, speaker.name, "airplay",
                            speaker.volume, speaker.address)

    def _update_receivers(self):
        """Mark speakers that another device is currently feeding."""
        by_uuid = {s.output_uuid: s for s in self.speakers.values() if s.output_uuid}
        for speaker in self.speakers.values():
            speaker.receiving_from = ""
            speaker.sending_to = []
        for source in self.speakers.values():
            if not source.connected or not source.supports_output_devices:
                continue
            try:
                targets = source.atv.audio.output_devices or []
            except Exception:
                continue
            for target in targets:
                # Remember every receiver we see named, so devices that will
                # not report their own UUID (Macs) can still be offered later.
                self.store.remember_output_target(target.identifier, target.name)
            for target in targets:
                if target.identifier == source.output_uuid:
                    continue   # a device always lists itself
                source.sending_to.append(
                    self.targets.get(target.identifier)
                    or self.store.known_output_targets().get(target.identifier)
                    or target.name)
                receiver = by_uuid.get(target.identifier)
                if receiver is not None:
                    receiver.receiving_from = source.name

    async def output_devices(self, key):
        """(ok, [{identifier, name, selected}]) — speakers this device feeds."""
        speaker = self.speakers.get(key)
        if speaker is None or not speaker.connected:
            return False, []
        if not speaker.supports_output_devices:
            return False, []
        try:
            current = {d.identifier for d in (speaker.atv.audio.output_devices or [])}
        except Exception as exc:
            log.warning("output_devices read failed for %s: %r", speaker.name, exc)
            return False, []
        # Every AirPlay receiver seen in the scan, plus anything remembered
        # from a previous session, minus this device itself.
        candidates = dict(self.store.known_output_targets())
        candidates.update(self.targets)
        options = [{"identifier": identifier, "name": name,
                    "selected": identifier in current}
                   for identifier, name in candidates.items()
                   if identifier != speaker.output_uuid]
        options.sort(key=lambda o: o["name"].lower())
        return True, options

    async def set_output_devices(self, key, identifiers):
        """Point a device's audio at the given speakers. Returns (ok, message)."""
        speaker = self.speakers.get(key)
        if speaker is None or not speaker.connected:
            return False, "device is not reachable"
        if not speaker.supports_output_devices:
            return False, f"{speaker.name} cannot redirect its audio"
        # Always keep the device itself, otherwise it stops playing its own sound.
        wanted = list(identifiers)
        if speaker.output_uuid and speaker.output_uuid not in wanted:
            wanted.insert(0, speaker.output_uuid)
        try:
            await speaker.atv.audio.set_output_devices(*wanted)
        except Exception as exc:
            log.warning("set_output_devices failed for %s: %r", speaker.name, exc)
            return False, self._describe(exc)
        log.info("%s now outputs to %s", speaker.name, wanted)
        # The Apple TV takes a few seconds to report the new set, and the
        # receiver map is otherwise only rebuilt on the 30s scan — so without
        # this the rows sit unchanged long enough to look like a failure.
        await asyncio.sleep(5)
        self._update_receivers()
        self.on_change()
        return True, ""

    async def set_power(self, key, on):
        """Turn an AirPlay speaker on or off. Returns (ok, message)."""
        speaker = self.speakers.get(key)
        if speaker is None or not speaker.connected:
            return False, "device is not reachable"
        if not speaker.supports_power:
            return False, f"{speaker.name} does not support power control"
        try:
            if on:
                await speaker.atv.power.turn_on()
            else:
                await speaker.atv.power.turn_off()
        except Exception as exc:
            log.warning("power %s failed for %s: %r", on, speaker.name, exc)
            return False, self._describe(exc)
        await asyncio.sleep(1.0)
        await self._poll_volumes()
        self.on_change()
        return True, ""

    async def set_volume(self, key, value):
        """Absolute volume, for restoring a captured level."""
        speaker = self.speakers.get(key)
        if speaker is None or not speaker.connected or not speaker.absolute:
            return False, "cannot set an absolute volume on this speaker"
        try:
            await speaker.atv.audio.set_volume(max(0.0, min(100.0, float(value))))
        except Exception as exc:
            return False, self._describe(exc)
        # Re-read, or the cached snapshot keeps reporting the old level and
        # callers cannot tell whether the write landed.
        await self._poll_volumes()
        self.on_change()
        return True, ""

    async def step_volume(self, key, delta):
        speaker = self.speakers.get(key)
        if speaker is None or not speaker.connected:
            return False
        try:
            if speaker.absolute and speaker.volume is not None:
                target = max(0.0, min(100.0, speaker.volume + delta))
                await speaker.atv.audio.set_volume(target)
                speaker.volume = target
            elif delta > 0:
                await speaker.atv.audio.volume_up()
            else:
                await speaker.atv.audio.volume_down()
        except Exception as exc:
            speaker.error = str(exc)[:80]
            return False
        await self._poll_volumes()
        self.on_change()
        return True

    # -- pairing ---------------------------------------------------------
    @staticmethod
    def _describe(exc):
        """pyatv raises several exceptions with an empty message."""
        text = str(exc).strip() or type(exc).__name__
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "ConnectionFailed" in type(exc).__name__:
            text += " — no reply, is the device awake?"
        return text[:120]

    async def begin_pairing(self, key, protocol_name="companion"):
        """Ask the speaker to show a PIN. Returns (ok, message)."""
        speaker = self.speakers.get(key)
        if speaker is None:
            return False, "device is no longer on the network"
        protocol = Protocol.AirPlay if protocol_name == "airplay" else Protocol.Companion
        self._pairing_protocol[key] = protocol
        await self._disconnect(speaker)
        try:
            pairing = await pyatv.pair(speaker.conf, protocol, asyncio.get_running_loop())
        except Exception as exc:
            log.warning("%s pairing setup failed for %s: %r", protocol.name, speaker.name, exc)
            return False, self._describe(exc)
        try:
            await pairing.begin()
        except Exception as exc:
            log.warning("pairing begin failed for %s: %r", speaker.name, exc)
            # Without this the aiohttp session behind the handler leaks.
            try:
                await pairing.close()
            except Exception:
                pass
            return False, self._describe(exc)
        self._pairing[key] = pairing
        return True, ""

    async def finish_pairing(self, key, pin):
        """Submit the PIN shown on the device. Returns (ok, message)."""
        pairing = self._pairing.pop(key, None)
        speaker = self.speakers.get(key)
        if pairing is None or speaker is None:
            return False, "pairing was not started"
        try:
            pairing.pin(pin)
            await pairing.finish()
            if not pairing.has_paired:
                await pairing.close()
                return False, "device rejected that code"
            protocol = self._pairing_protocol.pop(key, Protocol.Companion)
            service = speaker.conf.get_service(protocol)
            # pyatv can report has_paired and still leave the service without
            # credentials. Storing that None reached plistlib as an unwritable
            # value, and the store had already taken it in memory by then.
            creds = getattr(service, "credentials", None) if service else None
            if not creds:
                await pairing.close()
                log.warning("%s pairing for %s finished with no credentials",
                            protocol.name, speaker.name)
                return False, f"{protocol.name} pairing returned no credentials"
            # Companion keeps the bare key so pairings made before protocols
            # were distinguished continue to resolve.
            store_key = key if protocol is Protocol.Companion else f"{key}:{protocol.name.lower()}"
            self.store.set_credentials(store_key, creds)
            log.info("paired %s over %s", speaker.name, protocol.name)
            await pairing.close()
        except Exception as exc:
            # close() is what releases the aiohttp session; skipping it here
            # leaked one per failure ("Unclosed client session").
            try:
                await pairing.close()
            except Exception:
                pass
            log.warning("pairing finish failed for %s over %s: %r",
                        speaker.name, self._pairing_protocol.get(key, Protocol.Companion).name, exc)
            return False, self._describe(exc)
        await self._connect(speaker)
        await self._poll_volumes()
        self.on_change()
        return True, ""

    async def cancel_pairing(self, key):
        pairing = self._pairing.pop(key, None)
        if pairing is not None:
            try:
                await pairing.close()
            except Exception:
                pass

    async def close(self):
        for key in list(self._pairing):
            await self.cancel_pairing(key)
        for speaker in list(self.speakers.values()):
            await self._disconnect(speaker)
