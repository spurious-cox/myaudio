#!/bin/zsh
# Build, sign and install MyAudio.app  — v1.5
#
# Signing uses the Apple Development certificate (renewed 2026-08-05, valid to
# 2027-08-05). A STABLE signing identity is what keeps Little Snitch rules alive
# across rebuilds: an ad-hoc signature makes Little Snitch store a checksum
# instead, so every new build trips "The program has been modified!" and
# silently drops network access until re-approved.
#
# Two things to know about this identity:
#
#   * It is selected by SHA-1 HASH, not by name. The expired 2023 certificate is
#     still in the keychain under exactly the same name, and signing by name can
#     pick the dead one.
#   * --timestamp is not optional. A timestamped signature stays valid after the
#     certificate expires; without it, every app signed here breaks in Aug 2027.
#
# When the certificate is renewed again, put the new hash here:
#   security find-identity -p codesigning | grep "Apple Development"
#
# The previous self-signed identity ("MyAudio Local Signing", valid to 2036) is
# still in the keychain and remains a working fallback. To go back to it, set
# SIGN_ID to that name and drop --timestamp. If it is ever lost, re-import:
#   security import signing/myaudio.p12 -k ~/Library/Keychains/login.keychain-db \
#       -P myaudio -T /usr/bin/codesign
set -e
cd "${0:A:h}"

# Developer ID, not Apple Development. Apple Development signs code for the
# machines in your team only -- on any other Mac the signature is invalid and
# macOS refuses to launch it, which "Open Anyway" does not waive. Developer ID
# is the distribution identity and the only one notarization accepts.
# Notarize separately:  pixpro_release.sh all /Applications/MyAudio.app --python
SIGN_ID="4208ABA3EC12F24C1F09C7BB624EFF68B44259DB"

if ! security find-identity -p codesigning | grep -q "$SIGN_ID"; then
    echo "error: signing identity $SIGN_ID not in keychain — see header of this script" >&2
    exit 1
fi

echo "==> restoring devices to the running session's opening state"
# Killing the app skips its restore switch, which would otherwise leave
# speakers, routing and volumes wherever the session left them. The snapshot is
# on disk, so this works even though the process is about to be killed.
./venv/bin/python restore_now.py || true

echo "==> killing any running instance"
pkill -x MyAudio 2>/dev/null || true
sleep 1

echo "==> building"
rm -rf build dist
./venv/bin/python setup.py py2app >/dev/null

echo "==> copying the Tcl/Tk script libraries into the bundle"
# py2app relinks the tcl and tk dylibs into Contents/Frameworks but leaves their
# script libraries behind, and the path compiled into those dylibs points at
# this machine's Homebrew. Without these the app dies on any other Mac with
# "Cannot find a usable init.tcl". main.py points TCL_LIBRARY/TK_LIBRARY here.
TCLTK="$(brew --prefix tcl-tk)/lib"
for d in tcl9.0 tk9.0; do
    [[ -d "$TCLTK/$d" ]] || { print -u2 "error: $TCLTK/$d not found"; exit 1; }
    ditto "$TCLTK/$d" "dist/MyAudio.app/Contents/Resources/lib/$d"
done

echo "==> py2app drops the exec bit on the helper; restoring"
chmod +x dist/MyAudio.app/Contents/Resources/coreaudio_helper

# A copy of the interpreter named MyAudioAgent is what a released build should
# run -- TCC labels whichever binary makes the network calls, and "python" in the
# Local Network prompt is not shippable. It is not built here yet: the rename is
# a new identity to TCC, and the grant did not come into effect during testing.
# Revisit with the Developer ID signature, which is stable across rebuilds.

echo "==> signing with Developer ID ($SIGN_ID)"
# --deep skips plain binaries under Resources, so sign the helper first, then
# the bundle (outermost last, or the app signature is invalidated).
codesign --force --timestamp --sign "$SIGN_ID" \
    --identifier com.timmccoy.myaudio.helper \
    dist/MyAudio.app/Contents/Resources/coreaudio_helper
# protobuf arrives from pyatv INSIDE python314.zip, and nothing can codesign a
# file inside a zip -- Apple rejects the whole submission for
# google/_upb/_message.abi3.so being unsigned, with no timestamp and no
# Developer ID. Listing it in setup.py's packages does not work either:
# `google` is a namespace package with no __init__.py, and modulegraph fails
# the build with "No module named 'google'". So it is lifted out into the real
# lib directory, where the signing pass can reach it, and dropped from the zip.
ZIP="dist/MyAudio.app/Contents/Resources/lib/python314.zip"
if unzip -l "$ZIP" 2>/dev/null | grep -q "google/_upb/.*\.so"; then
    echo "==> lifting protobuf out of python314.zip so it can be signed"
    unzip -qo "$ZIP" "google/*" -d dist/MyAudio.app/Contents/Resources/lib/python3.14/
    zip -qd "$ZIP" "google/*" >/dev/null
fi

codesign --force --deep --timestamp --sign "$SIGN_ID" dist/MyAudio.app

echo "==> installing to /Applications"
rm -rf /Applications/MyAudio.app
cp -R dist/MyAudio.app /Applications/
chmod +x /Applications/MyAudio.app/Contents/Resources/coreaudio_helper
xattr -dr com.apple.quarantine /Applications/MyAudio.app 2>/dev/null || true

echo "==> installing the AirPlay agent through the app's own ensure_agent()"
# The installed bundle writes its own launchd job, pointing at wherever it is,
# so a copy on another Mac sets itself up the same way. Calling that here means
# the path everyone else depends on is exercised on every build, rather than
# staying untested until someone installs the release. The agent still runs
# under launchd -- that is what holds Local Network permission.
AR="/Applications/MyAudio.app/Contents/Resources"
PYTHONDONTWRITEBYTECODE=1 PYTHONHOME="$AR" \
PYTHONPATH="$AR/lib/python314.zip:$AR/lib/python3.14:$AR/lib/python3.14/lib-dynload:$AR" \
    /Applications/MyAudio.app/Contents/MacOS/python -c \
    'from myaudio.agentclient import ensure_agent
ok, msg = ensure_agent()
print("   ", msg)
raise SystemExit(0 if ok else 1)'
sleep 2
echo "    agent processes: $(pgrep -f 'MyAudioAgent|myaudio_agent.py' | wc -l | tr -d ' ')"

echo "==> installed:"
codesign -dv /Applications/MyAudio.app 2>&1 | grep -E "Identifier=|Authority="
plutil -extract CFBundleShortVersionString raw /Applications/MyAudio.app/Contents/Info.plist
echo "==> running instances: $(pgrep -x MyAudio | wc -l | tr -d ' ')"
