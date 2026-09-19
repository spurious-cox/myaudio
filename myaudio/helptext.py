"""The Help window's text — v2.0

Kept apart from the window that shows it so the wording can be edited without
touching layout code, and so the README can quote the same sentences.

Written for someone who did not build this app: Homebrew is not assumed
anywhere, least of all in the part that explains how to remove it.

v2.0 gathers every Terminal command into one section. They had been repeated
under the agent and under removal, which made both longer and left two places
to keep in step.

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
