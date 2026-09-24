MyAudio icon

MyAudio_1024.png is the master artwork (1024x1024, full bleed).
MyAudio.icns is built from it on Apple's macOS icon grid with:

    ~/My_Applications/KBD/venv/bin/python ~/bin/pixpro_make_icon.py \
        icon/MyAudio_1024.png --out icon --name MyAudio

setup.py bundles icon/MyAudio.icns. The earlier builder (build_icon.sh,
makeicon.swift) is retired; its files carry a .retired-20260923 suffix.
