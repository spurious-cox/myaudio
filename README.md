# MyAudio

A single panel for every audio output this Mac can reach — built-in speakers,
Bluetooth headphones, and AirPlay speakers on the network — with the volume of
each one in the same list.

## Requirements

* macOS 13 or later, Apple Silicon. There is no Intel build.
* Local network access, for finding AirPlay speakers.
* Bluetooth access, for connecting and disconnecting paired devices.

## Installing

Open the disk image and **drag MyAudio onto the Applications folder beside it**,
then open it from Applications.

Running it straight out of the disk image does not work properly. macOS keeps a
quarantined app in a temporary read-only copy, and MyAudio's network helper
cannot install itself from there. MyAudio detects this and says so rather than
failing silently.

## What it asks for

The first time it runs, macOS asks to allow local network access. **The prompt
names `python`, not MyAudio** — the part of MyAudio that scans the network is a
command-line helper, and macOS names that helper rather than the app. Allow it
or no AirPlay speaker will ever be found.

Bluetooth access is asked for separately, the first time you switch a Bluetooth
device on or off.

If you run Little Snitch or a similar filter, it will see the helper as a new
program and may block it silently. Symptom: the list shows your Bluetooth and
built-in devices but no AirPlay speakers at all.

## Hiding and unhiding

Every row has a **Hide** button on the right. Hiding a device removes it from
the list completely: it is not shown, not connected to, and not offered as a
destination for anything else. This is for devices you never use — a spare set
of headphones, a Mac in another room that advertises AirPlay.

**To bring one back**, use the **Hidden (n)…** button in the header. It appears
only when something is hidden, lists everything you have hidden by name, and
lets you restore them one at a time or all at once.

Hiding is per-Mac. It is remembered in
`~/Library/Application Support/MyAudio/devices.plist` and does not follow you to
another machine.

## What it can and cannot do

**Volume.** HomePod and HomePod mini report and accept an exact level. An Apple
TV only accepts up and down steps and reports no level at all, so its row shows
a dash rather than a percentage. Local and Bluetooth devices show a percentage.

**Switching output.** Turning a local or Bluetooth device on makes it this Mac's
output. Built-in outputs cannot be switched off — there is nowhere else for the
sound to go — and MyAudio says so rather than doing nothing.

**Sending this Mac's audio to an AirPlay speaker is not possible.** macOS does
not expose that to an application. Use the Sound section of Control Center. What
MyAudio does on an AirPlay row is set that speaker's own volume, and for a
device that has audio of its own — an Apple TV — route where *its* sound goes.

**Apple devices only.** HomePod, HomePod mini, Apple TV and AirPort Express are
recognized. A Sonos, Denon or AirPlay-2 television is found on the network and
then ignored.

**Apple TV pairing.** An Apple TV needs to be paired before its volume or
routing can be controlled. The row offers **Pair…** and shows the PIN prompt.

## Restore on exit

The switch at the bottom of the window puts every volume, connection and speaker
routing back to how it was when MyAudio opened, then quits. If any part of that
cannot be put back, MyAudio says so and stays open rather than quitting on a
restore that did not happen.

## The background agent

AirPlay speakers are found by a small launchd agent, not by the app — macOS
grants Local Network permission to a launchd process and not to the app
itself.

It **runs all the time**. Quitting MyAudio does not stop it: it keeps
scanning every thirty seconds, starts at login and survives a restart. That
is what makes the speaker list ready the moment you launch the app. It costs
one short network scan every thirty seconds, with no window and no Dock
icon.

It goes away for good only when the app is **deleted** — see below — or if
you stop it by hand for the session. The lines below are **Terminal**
commands: open Terminal (Applications ▸ Utilities ▸ Terminal, or
Command-Space and type `Terminal`), paste one in and press Return. None of
them needs a password.

```
launchctl bootout gui/$(id -u)/com.timmccoy.myaudioagent
```

Launching MyAudio starts it again and repoints its launchd entry at wherever
the app now lives. To start it by hand instead:

```
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.timmccoy.myaudioagent.plist
```

Both lines assume zsh, the macOS default shell. In tcsh, use `` `id -u` ``
in backticks rather than `$(id -u)`.

## Removing it

Quit MyAudio and drag it from Applications to the Trash. Its background
agent notices the app has gone within about two minutes, removes its own
launchd entry and stops — nothing is left running or loading at login.

To remove the agent immediately instead of waiting, or if it was not running
when the app was deleted:

```
launchctl bootout gui/$(id -u)/com.timmccoy.myaudioagent
rm -f ~/Library/LaunchAgents/com.timmccoy.myaudioagent.plist
```

Settings and logs, if you want those gone too:

```
rm -rf ~/Library/Application\ Support/MyAudio
rm -f ~/Library/Logs/MyAudio.log ~/Library/Logs/MyAudioAgent*.log
defaults delete com.timmccoy.myaudioctl
```

Installed with Homebrew? `brew uninstall --cask myaudio` does all of it, and
`brew uninstall --zap --cask myaudio` takes the settings and logs as well.

## Help

The **Help** button at the bottom right of the window covers what the app
does, the permissions it needs, which speakers it supports, and these
removal steps — so they are to hand without this file.

## Building

```
./build.sh          builds, signs with Developer ID, installs to /Applications
./release.sh        notarizes, staples, and wraps it in a DMG
```

`build.sh` installs the launchd agent by calling the app's own setup code, so
the path a new install depends on is exercised on every build.

## License

MIT. See [LICENSE](LICENSE).
