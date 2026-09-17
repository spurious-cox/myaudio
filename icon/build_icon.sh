#!/bin/zsh
# Render the app icon and package it as MyAudio.icns — v1.0
set -e
cd "${0:A:h}"

swiftc -O makeicon.swift -o makeicon
./makeicon icon.png

rm -rf MyAudio.iconset
mkdir MyAudio.iconset
# The sizes macOS expects; iconutil rejects an iconset missing any of them.
for spec in "16:16x16" "32:16x16@2x" "32:32x32" "64:32x32@2x" \
            "128:128x128" "256:128x128@2x" "256:256x256" "512:256x256@2x" \
            "512:512x512" "1024:512x512@2x"; do
    px="${spec%%:*}"
    name="${spec##*:}"
    sips -z "$px" "$px" icon.png --out "MyAudio.iconset/icon_${name}.png" >/dev/null
done

iconutil -c icns MyAudio.iconset -o MyAudio.icns
rm -rf MyAudio.iconset
echo "wrote $(pwd)/MyAudio.icns"
