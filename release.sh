#!/bin/zsh
# Notarize MyAudio.app and wrap it in a distributable DMG — v1.0.0
#
#   ./release.sh            (run ./build.sh first)
#
# WHY A DMG AND NOT A ZIP. An app launched from where it was unzipped is
# QUARANTINED, and Gatekeeper runs it from a read-only randomized copy under
# /AppTranslocation. sys.executable then points into a temp directory, so the
# launchd job MyAudio writes for its agent points there too and breaks the
# moment macOS cleans it up. Dragging out of a disk image is a MOVE, and a
# moved app is not translocated. MyAudio refuses to install its agent when it
# detects translocation, so a zip is not a workable way to ship it.
#
# WHY THE DMG IS NOTARIZED TOO. Stapling the app covers what gets dragged out;
# stapling the image covers what gets downloaded.
set -e
cd "${0:A:h}"

DEVID="4208ABA3EC12F24C1F09C7BB624EFF68B44259DB"
PROFILE="PixProNotary"
APP="/Applications/MyAudio.app"
OUTDIR="$HOME/My_Applications/MyAudio/dist-release"

[[ -d "$APP" ]] || { print -u2 "error: $APP is not installed — run ./build.sh"; exit 1; }
VERSION=$(plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")
mkdir -p "$OUTDIR"
DMG="$OUTDIR/MyAudio-$VERSION.dmg"

print "==> notarizing the app ($VERSION)"
if ! xcrun stapler validate "$APP" >/dev/null 2>&1; then
    ~/My_Applications/_signing/pixpro_release.sh all "$APP" --python
else
    print "    already notarized and stapled"
fi

print "==> building the disk image"
STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/READ ME FIRST.txt" <<TXT
MyAudio $VERSION

INSTALLING — DRAG IT, DO NOT RUN IT FROM HERE
    Drag MyAudio onto the Applications folder beside it, then open it from
    Applications. Running it straight out of this window leaves macOS holding
    it in a temporary copy, and its AirPlay agent cannot install itself from
    there. MyAudio will tell you if that happens.

WHAT IT ASKS FOR
    Local network access, so it can find your HomePods and Apple TV. The
    prompt names the helper that does the scanning, not MyAudio itself.
    Bluetooth access, to connect and disconnect paired headphones.

(c) 2026 Tim McCoy
TXT

# macOS 27 deprecated `hdiutil create -volname -srcfolder` and it fails with
# "Resource busy" on some folders; diskutil builds the same folder first time.
rm -f "$DMG"
diskutil image create from "$STAGE" --volumeName "MyAudio" --format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

print "==> signing and notarizing the disk image"
codesign --force --timestamp --sign "$DEVID" "$DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG"

print "==> results"
print "    dmg:     $DMG  ($(du -h "$DMG" | cut -f1))"
print "    stapled: app $(xcrun stapler validate "$APP" >/dev/null 2>&1 && echo YES || echo no), dmg $(xcrun stapler validate "$DMG" >/dev/null 2>&1 && echo YES || echo no)"
