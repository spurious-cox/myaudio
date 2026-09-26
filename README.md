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

**Playing this Mac through an Apple TV.** Switch it on and the Mac plays
through it, like any other output. CoreAudio has no device for an AirPlay
speaker, so MyAudio opens the Sound settings pane, selects the speaker there
and closes it again — the window appears for a second or two, and is left open
if it already was. This needs Accessibility permission, which macOS asks for
the first time. There is no "off" for a speaker: switch another output on
instead. A speaker that is asleep or unpaired has no switch, because macOS
will not route to it.

**A HomePod has no switch.** It has no audio of its own — it plays what
something else sends it — so it is chosen from a **Speakers…** menu on whatever
is doing the playing: the Mac's own row sends the Music app to any speakers you
tick, an Apple TV's row sends the Apple TV's sound to any you tick, and this Mac
can be one of them. Several speakers at once works that way; the HomePod's row
then reads "playing from" and the name of whatever is feeding it, in teal, and
its volume controls work while it plays. An idle HomePod's row says so and points back at those menus.

**One speaker at a time for the Mac itself.** The Mac has one output device, and
macOS offers no way to send it to two AirPlay speakers together: Control
Center's Sound panel replaces the selection just as the settings pane does.

**Two devices with the same name cannot be told apart.** Nothing in the list
distinguishes them, so rename one in the Home app before relying on the choice.
Where MyAudio would have to pick between them — switching the Mac's output — it
refuses and says so rather than playing into the wrong room.

An AirPlay row also sets that speaker's own volume, and for a device with
audio of its own — an Apple TV — routes where *its* sound goes.

**Apple devices only.** HomePod, HomePod mini, Apple TV and AirPort Express are
recognized. A Sonos, Denon or AirPlay-2 television is found on the network and
then ignored.

**Apple TV pairing.** An Apple TV needs to be paired before its volume or
routing can be controlled. The row offers **Pair…** and shows the PIN prompt.

## Routing is cleared at launch and quit

Opening MyAudio and quitting it both clear speaker routing: every Apple TV goes
back to playing through its own speakers, and Music back to this Mac. An Apple
TV stores its routing itself, so without this it would go on sending its sound
elsewhere after MyAudio had quit. Volumes and Bluetooth connections are left as
they are.

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

**Help ▸ Check for Updates…** compares your copy with the newest release on
GitHub and offers its download page when there is a newer one.

## Building

```
./build.sh          builds, signs with Developer ID, installs to /Applications
./release.sh        notarizes, staples, and wraps it in a DMG
```

`build.sh` installs the launchd agent by calling the app's own setup code, so
the path a new install depends on is exercised on every build.

## Problems or suggestions

Open an issue: https://github.com/spurious-cox/myaudio/issues

## License

MIT. See [LICENSE](LICENSE).
