"""The Help window's text — v2.5

Kept apart from the window that shows it so the wording can be edited without
touching layout code, and so the README can quote the same sentences.

Written for someone who did not build this app: Homebrew is not assumed
anywhere, least of all in the part that explains how to remove it.

v2.0 gathers every Terminal command into one section. They had been repeated
under the agent and under removal, which made both longer and left two places
to keep in step.

v2.5 names devices generically. Examples used the names on this Mac, which
mean nothing to anyone else reading them.

v2.4 describes the Speakers… menus, which are now the only way a HomePod is
given something to play.

v2.3 states plainly that the Mac plays through one speaker at a time, and
where several at once does exist.

v2.1 adds the section on playing through an AirPlay speaker, which needs
Accessibility permission and is the one thing in the app that opens another
window.

An indented line is rendered as a command in a selectable field.
"""

SECTIONS = (
    ("What MyAudio does", (
        "One panel for every audio output this Mac can reach: the built-in "
        "speakers, anything paired over Bluetooth, and AirPlay speakers on "
        "the network. Switch the output, set a volume, connect or disconnect "
        "a Bluetooth device, and send Music to an AirPlay speaker.",
        "The switch at the bottom left puts everything back the way it was "
        "when MyAudio opened — every volume, connection and routing — and "
        "quits.",
        "The Help button at the bottom right opens this window, and so does "
        "Help ▸ MyAudio Help in the menu bar.",
        "To move down this page use the arrow keys, Page Up and Page Down, "
        "or drag the scrollbar on the right. The mouse wheel does nothing "
        "here — the toolkit this window is drawn with receives no scroll "
        "events from macOS.",
    )),
    ("Playing through a HomePod", (
        "A HomePod has no switch, because it has no audio of its own — it "
        "plays what something else sends it. You choose it from a SPEAKERS… "
        "menu on whichever device is doing the playing:",
        "Speakers… on the Mac's own row sends the MUSIC APP to any speakers "
        "you tick, as many at once as you like.",
        "Speakers… on an Apple TV's row sends the APPLE TV's sound to any "
        "speakers you tick, again several at once, and this Mac can be one "
        "of them.",
        "Tick a speaker and its row says so straight away: it reads \"playing "
        "from\" and the name of whatever is feeding it, in teal, and its "
        "volume controls work while it plays. Until something is sending to "
        "it, the row says it is idle and points back at these menus.",
        "TWO DEVICES WITH THE SAME NAME cannot be told apart. The list shows "
        "both, and nothing in either one says which room it is, so rename one "
        "of them in the Home app before relying on the choice.",
    )),
    ("Playing through an Apple TV", (
        "An Apple TV has a switch, like any other output: turn it on and the "
        "Mac plays through it.",
        "macOS does not let an app route audio to an AirPlay speaker directly "
        "— the only place that choice exists is the Sound settings pane. So "
        "MyAudio opens that pane, picks the speaker, and closes it again. You "
        "will see the window appear for a second or two. If System Settings "
        "was already open, it is left open.",
        "This needs Accessibility permission, which macOS asks for the first "
        "time you use it: System Settings ▸ Privacy & Security ▸ "
        "Accessibility, then switch MyAudio on. Until it is granted, the "
        "AirPlay switches report what is missing rather than doing nothing.",
        "ONE SPEAKER AT A TIME. The Mac has a single output, and macOS "
        "offers no way to send it to two AirPlay speakers at once — not in "
        "Sound settings and not in Control Center, where picking a speaker "
        "replaces the one before it.",
        "Several speakers at once is something a SOURCE does, not the Mac. "
        "Use Speakers… on the Mac's own row to send the Music app to as many "
        "speakers as you like, or Speakers… on an Apple TV's row to send its "
        "audio to several, including this Mac.",
        "To stop playing through a speaker, switch a different output on. "
        "There is no 'off' for a speaker, because turning one off would have "
        "to pick somewhere else for the sound to go.",
        "An Apple TV that is asleep or not yet paired has no switch either, "
        "because macOS will not route to one that is not ready.",
    )),
    ("Permissions it needs", (
        "AirPlay speakers are found by a small background agent, because "
        "macOS grants Local Network permission to a launchd process and not "
        "to the app itself. The first time it runs, macOS asks whether to "
        "allow it to find devices on the local network. Say yes, or the "
        "AirPlay rows stay empty.",
        "Connecting and disconnecting Bluetooth devices needs Bluetooth "
        "permission. Without it the devices still appear and still show "
        "their volume, but the connect switch does nothing.",
        "Sending Music to a speaker drives the Music app, so macOS asks for "
        "permission to control it the first time.",
        "Playing the whole Mac through an AirPlay speaker needs Accessibility "
        "permission — see the section above.",
    )),
    ("Which speakers it supports", (
        "Apple speakers: HomePod, HomePod mini, Apple TV and AirPort "
        "Express. Other Macs advertising AirPlay are deliberately passed "
        "over — they are sources, not speakers.",
        "Third-party AirPlay speakers — Sonos, Denon, an AirPlay 2 "
        "television — are not supported. They are found by the scan and then "
        "set aside, and the panel says so rather than showing an empty list.",
    )),
    ("The background agent", (
        "The agent runs ALL THE TIME, not only while this window is open. "
        "Quitting MyAudio does not stop it, and neither does closing the "
        "window: it keeps scanning every thirty seconds, starts again at "
        "login, and survives a restart.",
        "That is deliberate. It is what makes the speaker list ready the "
        "moment you launch MyAudio instead of starting a scan, and it is the "
        "only arrangement macOS will grant Local Network permission to.",
        "It uses almost nothing while it sits there — one short network scan "
        "every thirty seconds, no window, no Dock icon.",
        "It goes away for good when you delete the app. To stop or start it "
        "yourself, see Using Terminal below.",
    )),
    ("Removing MyAudio", (
        "Quit MyAudio, then drag it from Applications to the Trash. The "
        "agent notices its app has gone, removes its own launchd entry and "
        "stops, within about two minutes. Nothing is left running or loading "
        "at login.",
        "Its settings and logs are small and harmless, but Using Terminal "
        "below says how to delete those too, and how to remove the agent by "
        "hand if you would rather not wait.",
        "Installed with Homebrew?  brew uninstall --cask myaudio  does all "
        "of it, and adding  --zap  takes the settings and logs as well.",
    )),
    ("Using Terminal", (
        "Everything below is typed into Terminal, not into MyAudio. Open it "
        "from Applications ▸ Utilities ▸ Terminal, or press Command-Space "
        "and type Terminal. Copy a line from here, paste it in, and press "
        "Return. None of these needs a password.",
        "Stop the agent for this session:",
        "    launchctl bootout gui/$(id -u)/com.timmccoy.myaudioagent",
        "Start it again — launching MyAudio also does this, and repoints it "
        "at wherever the app now lives:",
        "    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.timmccoy.myaudioagent.plist",
        "Remove the agent by hand, after deleting the app:",
        "    rm -f ~/Library/LaunchAgents/com.timmccoy.myaudioagent.plist",
        "Delete the settings and logs:",
        "    rm -rf ~/Library/Application\\ Support/MyAudio",
        "    rm -f ~/Library/Logs/MyAudio.log ~/Library/Logs/MyAudioAgent*.log",
        "    defaults delete com.timmccoy.myaudioctl",
        "These assume zsh, the standard macOS shell. In tcsh, write `id -u` "
        "in backticks rather than $(id -u).",
    )),
    ("When something looks wrong", (
        "No AirPlay speakers at all: the panel says which of the reasons it "
        "is — the agent is not running, the scan came back empty, the scan "
        "failed, or every device found was one it does not drive.",
        "An empty scan is almost always Local Network permission, or a "
        "firewall rule blocking the agent. System Settings ▸ Privacy & "
        "Security ▸ Local Network.",
        "The logs are ~/Library/Logs/MyAudio.log for the app and "
        "~/Library/Logs/MyAudioAgent.log for the agent.",
    )),
)
