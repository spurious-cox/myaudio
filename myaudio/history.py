"""Version history shown under Help ▸ Version History — v1.2

Newest first. Every future release must add an entry here — the window reads
this list directly, so an unrecorded version is a visibly stale history.

The numbers restart at 1.0.0 with the first public release. Everything above
that in age, up to 1.27.0, belongs to the July development series, so read the
dates rather than the numbers.
"""

GENERATED_BY = (
    "This history was written by Claude (Anthropic's Claude Code), which built "
    "MyAudio with Tim McCoy on 25–26 July 2026. Each entry says what changed "
    "and why."
)

# (version, date, summary)
HISTORY = [
    ("1.4.3", "2026-09-23",
     "A new icon showing the TV, headphones, Mac, Apple TV and HomePods that "
     "MyAudio connects, placed on the standard macOS icon grid."),
    ("1.4.2", "2026-09-19",
     "The version history had not been written since July, so the window "
     "showed nothing about any of the released versions. Every release since "
     "is recorded, and the note above explains why the numbers restart."),
    ("1.4.1", "2026-09-19",
     "Help reached from an open dialog reported that no help was available: a "
     "dialog with no menu of its own is given the stock one by macOS. Every "
     "dialog now shares the app's menu. The help text also names devices "
     "generically instead of using the names on the Mac it was written on."),
    ("1.4.0", "2026-09-19",
     "Only a device with audio of its own — an Apple TV — has a switch. A "
     "HomePod plays what something else sends it, so its row reports, sets "
     "volume, and says to choose it from a Speakers… menu. Two switches for "
     "one speaker contradicted each other as soon as one showed teal."),
    ("1.3.0", "2026-09-19",
     "Playing through several AirPlay speakers at once was attempted and "
     "removed: macOS replaces the output rather than adding to it, in Control "
     "Center as much as in Sound settings. Several speakers at once belongs to "
     "a source — the Music app, or an Apple TV — which Speakers… already does."),
    ("1.1.0", "2026-09-19",
     "The Mac can play through an AirPlay speaker. CoreAudio has no device for "
     "one, so MyAudio opens the Sound settings pane, selects the speaker and "
     "closes it again; it needs Accessibility permission. While streaming, "
     "CoreAudio calls the output simply “AirPlay”, so the speaker it really is "
     "gets named on its own row. The hint to relaunch no longer appears while "
     "the agent is still starting."),
    ("1.0.5", "2026-09-18",
     "A Help window, reachable from the menu and a button at the bottom right, "
     "and an agent that removes its own launchd job once the app is deleted."),
    ("1.0.1", "2026-09-17",
     "The AirPlay list says why it is empty when every device found was one "
     "MyAudio does not drive, rather than showing nothing."),
    ("1.0.0", "2026-09-17",
     "First public release."),
    ("1.27.0", "2026-07-26",
     "Speaker lists are fetched shortly after the app opens and kept up to "
     "date, so Choose location appears already filled in instead of pausing "
     "to ask the devices."),
    ("1.26.1", "2026-07-26",
     "Dialogs appeared as an empty white window before filling in. They are "
     "now built hidden and shown complete."),
    ("1.26.0", "2026-07-26",
     "Applying a speaker choice looked like it had failed: the Apple TV takes "
     "about five seconds to report the change, and the rows were only rebuilt "
     "on the 30-second scan, so nothing moved for up to half a minute. The app "
     "now waits for the device to confirm and updates immediately. The dialog "
     "is titled “Choose location”."),
    ("1.25.1", "2026-07-26",
     "The running version is now shown beside the MyAudio title."),
    ("1.25.0", "2026-07-26",
     "Speakers… now appears only on devices that have audio of their own to "
     "send — the Apple TV and the Mac. HomePods could forward audio too, but "
     "having none of their own, the control only led to routing silence "
     "between them and wondering why nothing played."),
    ("1.24.0", "2026-07-26",
     "The Speakers… control is now teal and underlined, so it reads as the "
     "actionable thing on rows whose switch was removed."),
    ("1.23.1", "2026-07-26",
     "Fixed the Speakers… and Pair dialogs, which had been crashing on open "
     "since v1.19.1 and so never appeared. A change meant for the main window "
     "was applied to the dialogs as well, leaving them calling a method they "
     "do not have."),
    ("1.23.0", "2026-07-26",
     "Removed the switch from AirPlay rows altogether. It had no action left "
     "once routing moved to Speakers…, so it only attracted clicks that did "
     "nothing. Those rows now show their status in words and offer one "
     "control: Speakers…."),
    ("1.22.0", "2026-07-26",
     "Switches on AirPlay rows were teal whenever the speaker had power, which "
     "is always — so every row looked selected at startup. They are now "
     "indicators showing whether sound is actually coming out of that device, "
     "and Speakers… is the only routing control."),
    ("1.21.1", "2026-07-26",
     "Teal was marking any powered-on speaker, so every row lit up and none "
     "stood out. It now marks only audio actually flowing — sending to a room "
     "or receiving from one. The Apple TV row also names its own control: "
     "“Speakers… for TV sound in other rooms”."),
    ("1.21.0", "2026-07-26",
     "The switch on an AirPlay row was still routing Music, so clicking a room "
     "expecting TV sound quietly sent music there instead. Routing now lives "
     "only in Speakers…, and the switch is simply power. Each row also says "
     "what it is doing — “sending to” or “playing from”, naming the other "
     "device, or a prompt to use Speakers… when it is doing nothing."),
    ("1.20.0", "2026-07-26",
     "Replaced the ♪ Music button with a Speakers… picker on the Mac's row, so "
     "every row now works the same way: Speakers… chooses where that device's "
     "audio goes. The old button was on by default and only ever switched off, "
     "which read as pointless. Choosing no speakers now falls back to the Mac "
     "rather than leaving Music with nowhere to play."),
    ("1.19.1", "2026-07-26",
     "⌘Q and the Quit menu bypassed the app's close handler on macOS, so "
     "preferences were not saved when quitting that way. Both now take the "
     "same path as the close button. Neither restores devices — that remains "
     "the red switch's job."),
    ("1.19.0", "2026-07-26",
     "The opening snapshot is now saved to disk, so devices can be put back "
     "even when the app is killed rather than closed through the restore "
     "switch. Rebuilding no longer leaves speakers playing in another room."),
    ("1.18.0", "2026-07-26",
     "The Mac now appears as a destination for TV audio. Every AirPlay receiver "
     "publishes its speaker id in its network advert, including Macs — reading "
     "that replaces the previous guesswork, so the picker lists everything on "
     "the network without needing to connect to it first. Apply now closes the "
     "speaker dialog immediately instead of sitting there during the call."),
    ("1.17.0", "2026-07-26",
     "The Speakers… picker only offered devices that report their own output "
     "UUID, which Macs refuse to do — so the Mac could never be chosen as a "
     "destination for TV audio, even though the Apple TV can send to it. Every "
     "receiver named in any output set is now remembered and offered "
     "thereafter. Added the Mac as a Music destination you can switch off, so "
     "music can play in one room only. Bluetooth connect failures now appear on "
     "the device's own row, and give up after 8 seconds instead of 15."),
    ("1.16.1", "2026-07-26",
     "Stopped the Bluetooth helper crashing when run outside the app. macOS "
     "blames the launching process for Bluetooth access, so diagnostic runs "
     "from a terminal were killed and left a crash report each time. It now "
     "only attempts Bluetooth control from the real app bundle."),
    ("1.16.0", "2026-07-26",
     "Added “Restore devices to how I found them and exit” — a red switch that "
     "photographs every device level, routing and connection at launch and puts "
     "them back on the way out. Added this Version History under Help."),
    ("1.15.2", "2026-07-26",
     "With the background agent stopped, the AirPlay list went empty with no "
     "explanation; the app now says the agent is not running and how to start it."),
    ("1.15.1", "2026-07-26",
     "The agent left a stale socket file behind when stopped, which made a dead "
     "agent look alive. It now handles SIGTERM and cleans up, and the app tests "
     "the socket by connecting rather than trusting the file exists."),
    ("1.15.0", "2026-07-26",
     "A speaker being fed by another device reports itself as idle, so its "
     "switch stayed off while sound was audibly coming out. The app now works "
     "out who is feeding whom and shows “playing from …”."),
    ("1.14.1", "2026-07-25",
     "AirPlay switches did nothing when Music was closed, because that switch "
     "routes Music. They now grey out and say “open Music to play here”."),
    ("1.14.0", "2026-07-25",
     "Speaker picker finished: output devices are addressed by a UUID that is "
     "not derivable from the network identifier, so each speaker is asked for "
     "its own. Sending the wrong one failed silently."),
    ("1.13.0", "2026-07-25",
     "Added the Speakers… picker for choosing which speakers a device sends its "
     "own audio to."),
    ("1.12.0", "2026-07-25",
     "Added output-device control through the agent, and fixed the app and agent "
     "overwriting each other's preferences file — which had already cost one "
     "AirPlay pairing."),
    ("1.11.0", "2026-07-25",
     "Added AirPlay-protocol pairing, separate from the existing Companion "
     "pairing, which is what unlocks sending TV audio to other speakers."),
    ("1.10.0", "2026-07-25",
     "Added the app icon and the copyright shown in About MyAudio."),
    ("1.9.0", "2026-07-25",
     "Added a temporary CSV recorder to trace volume changes; it caught Music "
     "overwriting a speaker's hardware volume when streaming starts."),
    ("1.8.0", "2026-07-25",
     "Volume auditing extended to Music's own per-speaker and master levels, "
     "which turned out to explain loudness changing with no visible cause."),
    ("1.7.0", "2026-07-25",
     "Replaced the On/Off radio pair with a single slider switch."),
    ("1.6.0", "2026-07-25",
     "“On” now means audio is actually coming out of a device, rather than "
     "merely that it exists, so only the device in use appears on."),
    ("1.5.0", "2026-07-25",
     "AirPlay rows trimmed to IP and status, and given an active/idle state."),
    ("1.4.0", "2026-07-25",
     "Added Music routing so the Mac's music can play on a HomePod — the only "
     "way to move this Mac's audio to an AirPlay speaker."),
    ("1.3.0", "2026-07-25",
     "Moved all network work into a background agent. macOS will not grant an "
     "app bundle Local Network access on this Mac, but will grant it to a "
     "launchd process, so AirPlay only works from there."),
    ("1.2.0", "2026-07-25",
     "Added power control for AirPlay speakers, reading their true power state."),
    ("1.1.0", "2026-07-25",
     "Bluetooth devices can be connected and disconnected; added the playing-"
     "source line and output switching."),
    ("1.0.0", "2026-07-25",
     "First build: Bluetooth, AirPlay and built-in outputs in one window with "
     "volume control and live status."),
]
