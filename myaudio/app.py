"""MyAudio — audio output panel — v1.2.1

v1.2: any device can be hidden from the list, and brought back from
the Hidden button in the header.
"""

import logging
import os
import subprocess
import threading
import time
import tkinter as tk

from . import __version__, bluetooth, coreaudio, devices, history, levelcsv, musicroute, restore
from . import helptext
from .agentclient import AgentClient, ensure_agent
from .config import VOLUME_STEP, Store

# Two palettes, chosen once at launch. The names below are used in about
# fifty places, so the appearance is switched by rebinding them rather than
# by touching every widget.
DARK = dict(bg="#1c1c1e", card="#2c2c2e", card_active="#33333a",
            text="#f2f2f7", dim="#8e8e93", accent="#30d5c8",
            warn="#ff9f0a", danger="#ff453a")
# The dark accents are too pale to read on white: the teal drops to 1.5:1 and
# the orange is worse. These are darkened until they carry their own weight
# on a light ground.
LIGHT = dict(bg="#f2f2f7", card="#ffffff", card_active="#e5e5ea",
             text="#1c1c1e", dim="#6e6e73", accent="#0a7d72",
             warn="#9a5b00", danger="#c9000f")


def system_is_dark():
    """True when macOS is in Dark appearance.

    AppleInterfaceStyle exists only in Dark mode — in Light the key is absent
    and `defaults read` exits non-zero, which is the documented way to tell.
    If the question cannot be answered the app stays dark, which is what it
    has always been.
    """
    try:
        found = subprocess.run(
            ["/usr/bin/defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=3)
    except Exception:
        return True
    return found.returncode == 0 and "dark" in found.stdout.lower()


_PALETTE = DARK if system_is_dark() else LIGHT
BG = _PALETTE["bg"]
CARD = _PALETTE["card"]
CARD_ACTIVE = _PALETTE["card_active"]
TEXT = _PALETTE["text"]
DIM = _PALETTE["dim"]
ACCENT = _PALETTE["accent"]
WARN = _PALETTE["warn"]
DANGER = _PALETTE["danger"]

KIND_LABELS = {"bluetooth": "Bluetooth", "airplay": "AirPlay", "local": "Output"}
POLL_MS = 2500

log = logging.getLogger(__name__)


def mkbtn(parent, text, command, width=3, bg=CARD_ACTIVE, fg=TEXT):
    """macOS tk.Button ignores bg, so buttons are Labels with click bindings."""
    label = tk.Label(parent, text=text, bg=bg, fg=fg, width=width,
                     font=("SF Pro Text", 13, "bold"), padx=6, pady=3, cursor="pointinghand")
    label.enabled = True
    # Base colours are re-read on mouse-out so a highlighted (active) button
    # keeps its colour instead of reverting to the default face.
    label.base_bg = bg
    label.base_fg = fg

    def click(_e):
        if label.enabled:
            command()

    label.bind("<Button-1>", click)
    label.bind("<Enter>", lambda _e: label.enabled and label.config(bg=ACCENT, fg=BG))
    label.bind("<Leave>", lambda _e: label.config(
        bg=label.base_bg, fg=label.base_fg if label.enabled else DIM))
    return label


def set_enabled(button, enabled, bg=CARD_ACTIVE, fg=TEXT):
    button.enabled = enabled
    button.base_bg = bg
    button.base_fg = fg
    button.config(fg=fg if enabled else DIM, bg=bg,
                  cursor="pointinghand" if enabled else "arrow")


TRACK_OFF = "#48484a"
TRACK_DISABLED = "#3a3a3c"
KNOB = "#ffffff"
KNOB_DISABLED = "#8e8e93"


class Switch(tk.Canvas):
    """A macOS-style pill toggle: accent when on, grey when off."""

    W, H = 46, 26

    def __init__(self, parent, command, bg=CARD, accent=ACCENT):
        super().__init__(parent, width=self.W, height=self.H, bg=bg,
                         highlightthickness=0, bd=0, cursor="pointinghand")
        self.command = command
        self.accent = accent
        self.on = False
        self.enabled = True
        self._render()
        self.bind("<Button-1>", self._click)

    def _render(self):
        self.delete("all")
        if not self.enabled:
            track = TRACK_DISABLED
        else:
            track = self.accent if self.on else TRACK_OFF
        r = self.H / 2
        self.create_oval(0, 0, self.H, self.H, fill=track, outline=track)
        self.create_oval(self.W - self.H, 0, self.W, self.H, fill=track, outline=track)
        self.create_rectangle(r, 0, self.W - r, self.H, fill=track, outline=track)
        knob_x = (self.W - self.H + 3) if self.on else 3
        colour = KNOB if self.enabled else KNOB_DISABLED
        self.create_oval(knob_x, 3, knob_x + self.H - 6, self.H - 3,
                         fill=colour, outline=colour)

    def set_state(self, on, enabled):
        if (on, enabled) != (self.on, self.enabled):
            self.on, self.enabled = on, enabled
            self._render()
        self.config(cursor="pointinghand" if enabled else "arrow")

    def _click(self, _event):
        if not self.enabled:
            return
        # Flip immediately. Waking a speaker and re-pointing Music can take a
        # couple of seconds, and a switch that sits still that long reads as a
        # dead control — which led to double-toggling. The next poll corrects
        # this if the action turns out to have failed.
        target = not self.on
        self.on = target
        self._render()
        self.command(target)


class DeviceCard(tk.Frame):
    def __init__(self, parent, app, row):
        super().__init__(parent, bg=CARD, padx=12, pady=9)
        self.app = app
        self.key = row.key
        self.columnconfigure(0, weight=1)

        self.name = tk.Label(self, bg=CARD, fg=TEXT, font=("SF Pro Text", 14, "bold"), anchor="w")
        self.name.grid(row=0, column=0, sticky="w")
        self.sub = tk.Label(self, bg=CARD, fg=DIM, font=("SF Pro Text", 11), anchor="w")
        self.sub.grid(row=1, column=0, sticky="w")

        self.switch = Switch(self, lambda on: self.app.set_power(self.key, on))
        self.switch.grid(row=0, column=1, rowspan=2, padx=(12, 16))

        self.volume = tk.Label(self, bg=CARD, fg=TEXT, font=("SF Mono", 13), width=5, anchor="e")
        self.volume.grid(row=0, column=3, rowspan=2, padx=(0, 10))

        self.speakers = mkbtn(self, "Speakers…",
                              lambda: self.app.choose_speakers(self.key), width=9,
                              fg=ACCENT)
        # Underlined and teal so it reads as the one thing to click on a row
        # whose switch has been removed.
        self.speakers.configure(font=("SF Pro Text", 13, "bold", "underline"))
        self.speakers.grid(row=0, column=2, rowspan=2, padx=(0, 10))

        self.pair = mkbtn(self, "Pair…", lambda: self.app.start_pairing(self.key), width=6)
        self.pair.grid(row=0, column=4, rowspan=2, columnspan=2, padx=2)
        self.minus = mkbtn(self, "–", lambda: self.app.step(self.key, -VOLUME_STEP))
        self.minus.grid(row=0, column=4, rowspan=2, padx=2)
        self.plus = mkbtn(self, "+", lambda: self.app.step(self.key, VOLUME_STEP))
        self.plus.grid(row=0, column=5, rowspan=2, padx=2)
        # Dimmed and last in the row: it is housekeeping, not a control anyone
        # reaches for while adjusting sound.
        self.hide = mkbtn(self, "Hide", lambda: self.app.hide_device(self.key),
                          width=5, fg=DIM)
        self.hide.grid(row=0, column=6, rowspan=2, padx=(8, 0))
        self.pair.grid_remove()

    def update_row(self, row):
        # On now means "audio is going here", so a separate "playing here"
        # label would just repeat it; colour alone marks the active output.
        self.name.config(text=row.name, fg=ACCENT if row.is_default else TEXT)

        # AirPlay rows carry an IP, which already identifies them as network
        # speakers, so the kind label is dropped to keep the window narrow.
        bits = [] if row.kind == "airplay" else [KIND_LABELS.get(row.kind, row.kind)]
        if row.detail:
            bits.append(row.detail)
        # Teal means audio is actually flowing — sending to another room or
        # receiving from one. Merely being powered on is not worth a colour,
        # or every row lights up and none of them stand out.
        if row.sending_to or row.receiving_from:
            sub_fg = ACCENT
        elif row.note and row.note != "not connected":
            sub_fg = WARN
        else:
            sub_fg = DIM
        self.sub.config(text="   ".join(bits) + (f"   • {row.note}" if row.note else ""),
                        fg=sub_fg)

        # An AirPlay row has no switch: its only action is Speakers…, and a
        # switch that cannot be clicked simply attracts clicks that do nothing.
        if row.kind == "airplay":
            self.switch.grid_remove()
        else:
            self.switch.grid()
            self.switch.set_state(row.on, row.can_toggle or row.can_select)

        # Every row that can send its audio somewhere gets the same control:
        # AirPlay devices send their own sound, the Mac sends Music.
        if row.can_send or (row.kind == "local" and row.music_name):
            self.speakers.grid()
        else:
            self.speakers.grid_remove()

        if row.needs_pairing or row.needs_airplay_pairing:
            self.minus.grid_remove()
            self.plus.grid_remove()
            self.pair.grid()
            self.volume.config(text="")
            return
        self.pair.grid_remove()
        self.minus.grid()
        self.plus.grid()
        self.volume.config(text="—" if row.volume is None else f"{row.volume:.0f}%",
                           fg=TEXT if row.on else DIM)
        for button in (self.minus, self.plus):
            set_enabled(button, row.can_step)


class PinDialog(tk.Toplevel):
    """Collects the code the speaker shows on screen."""

    def __init__(self, parent, device_name, on_submit):
        super().__init__(parent, bg=BG)
        self.withdraw()
        self.title("Pair")
        self.on_submit = on_submit
        self.transient(parent)
        self.resizable(False, False)

        body = tk.Frame(self, bg=BG, padx=20, pady=16)
        body.pack()
        tk.Label(body, text=f"Pair with {device_name}", bg=BG, fg=TEXT,
                 font=("SF Pro Text", 14, "bold")).pack(anchor="w")
        tk.Label(body, text="Enter the code shown on the device.", bg=BG, fg=DIM,
                 font=("SF Pro Text", 11)).pack(anchor="w", pady=(2, 10))

        self.entry = tk.Entry(body, bg=CARD_ACTIVE, fg=TEXT, insertbackground=TEXT,
                              font=("SF Mono", 16), justify="center", width=10,
                              relief="flat", highlightthickness=1, highlightbackground=DIM)
        self.entry.pack(pady=(0, 12))
        self.entry.bind("<Return>", lambda _e: self._submit())

        self.message = tk.Label(body, text="", bg=BG, fg=WARN, font=("SF Pro Text", 11))
        self.message.pack(anchor="w")

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x", pady=(10, 0))
        mkbtn(buttons, "Cancel", self._cancel, width=7).pack(side="right", padx=(6, 0))
        self.ok = mkbtn(buttons, "Pair", self._submit, width=7)
        self.ok.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        self.deiconify()
        self.entry.focus_set()
        self.grab_set()

    def _submit(self):
        pin = self.entry.get().strip()
        if not pin:
            self.message.config(text="Enter the code first.")
            return
        set_enabled(self.ok, False)
        self.message.config(text="Pairing…", fg=DIM)
        self.on_submit(pin)

    def _cancel(self):
        self.on_submit(None)

    def failed(self, message):
        set_enabled(self.ok, True)
        self.message.config(text=message, fg=WARN)
        self.entry.select_range(0, "end")
        self.entry.focus_set()


class SpeakerDialog(tk.Toplevel):
    """Choose which speakers a device sends its own audio to."""

    def __init__(self, parent, device_name, options, on_apply, subtitle=None):
        super().__init__(parent, bg=BG)
        # Build hidden: the window manager draws the frame before Tk fills it,
        # so an empty white shell appears first otherwise.
        self.withdraw()
        self.title(f"{device_name} speakers")
        self.on_apply = on_apply
        self.transient(parent)
        self.resizable(False, False)

        body = tk.Frame(self, bg=BG, padx=20, pady=16)
        body.pack()
        tk.Label(body, text="Choose location", bg=BG, fg=TEXT,
                 font=("SF Pro Text", 14, "bold")).pack(anchor="w")
        tk.Label(body, text=subtitle or f"Where {device_name} plays its own audio — "
                                       f"TV sound, not this Mac's.",
                 bg=BG, fg=DIM, font=("SF Pro Text", 11),
                 wraplength=380, justify="left").pack(anchor="w", pady=(2, 10))

        self.vars = {}
        for option in options:
            var = tk.BooleanVar(value=option["selected"])
            self.vars[option["identifier"]] = var
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=2)
            mark = tk.Label(row, bg=BG, fg=ACCENT if option["selected"] else DIM,
                            font=("SF Pro Text", 13), width=2,
                            text="◉" if option["selected"] else "○", cursor="pointinghand")
            mark.pack(side="left")
            label = tk.Label(row, text=option["name"], bg=BG, fg=TEXT,
                             font=("SF Pro Text", 13), cursor="pointinghand")
            label.pack(side="left")

            def toggle(_e, v=var, m=mark):
                v.set(not v.get())
                m.config(text="◉" if v.get() else "○", fg=ACCENT if v.get() else DIM)

            mark.bind("<Button-1>", toggle)
            label.bind("<Button-1>", toggle)

        if not options:
            tk.Label(body, text="No other speakers found.", bg=BG, fg=DIM,
                     font=("SF Pro Text", 12)).pack(anchor="w")

        self.message = tk.Label(body, text="", bg=BG, fg=WARN, font=("SF Pro Text", 11))
        self.message.pack(anchor="w", pady=(8, 0))

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x", pady=(10, 0))
        mkbtn(buttons, "Cancel", self._close, width=7).pack(side="right", padx=(6, 0))
        self.ok = mkbtn(buttons, "Apply", self._apply, width=7)
        self.ok.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.update_idletasks()
        self.deiconify()
        self.grab_set()

    def _apply(self):
        set_enabled(self.ok, False)
        self.message.config(text="Applying…", fg=DIM)
        self.on_apply([i for i, v in self.vars.items() if v.get()])

    def _close(self):
        self.grab_release()
        self.destroy()

    def failed(self, message):
        set_enabled(self.ok, True)
        self.message.config(text=message, fg=WARN)


class HelpDialog(tk.Toplevel):
    """What the app does, what it needs, and how to remove it.

    Scrolled rather than paged: the removal instructions are the part people
    come here for, and they should be reachable without hunting.
    """

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.withdraw()
        self.title("MyAudio Help")
        self.transient(parent)
        # maxsize() is the largest the window manager will allow, which on
        # macOS is the screen minus the menu bar and the Dock. Asking it is
        # better than measuring the screen and guessing at both.
        self.update_idletasks()
        max_w, max_h = self.maxsize()
        self.geometry("%dx%d+%d+%d" % (min(700, max_w), max_h, 120, 0))

        body = tk.Frame(self, bg=BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=f"MyAudio {__version__}", bg=BG, fg=TEXT,
                 font=("SF Pro Text", 15, "bold")).pack(anchor="w")
        # Said plainly and at the top: this toolkit gets no scroll events
        # from macOS, so the wheel does nothing and people need telling.
        tk.Label(body, text="Scroll by arrow keys  ·  Page Up / Page Down  ·  "
                            "or drag the scrollbar",
                 bg=BG, fg=ACCENT, font=("SF Pro Text", 13, "bold")
                 ).pack(anchor="w", pady=(6, 0))

        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        scroll = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        # Without this the inner frame keeps its requested width, so the text
        # never re-wraps to the window and the scrollbar measures the wrong
        # height.
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, pady=(10, 0))
        scroll.pack(side="right", fill="y", pady=(10, 0))

        def on_wheel(event):
            # Scroll by SIGN, not by delta. A Magic Mouse and a trackpad send
            # a stream of small smooth-scroll events whose delta can round to
            # zero, so multiplying by it scrolls nothing at all; a wheel mouse
            # sends larger steps and would fly. One line per event suits both,
            # because both send many.
            if event.delta:
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

        def on_touchpad(event):
            """Tk 9 sends precise scrolling here, not to <MouseWheel>.

            A Magic Mouse and a trackpad are "precise" devices: Tk 9.0 on
            macOS reports them as <<TouchpadScroll>>, and a window bound only
            to <MouseWheel> never scrolls at all. The delta packs two signed
            16-bit values, dx in the low half and dy in the high half.
            """
            packed = event.delta
            dy = (packed >> 16) & 0xFFFF
            if dy >= 0x8000:
                dy -= 0x10000
            if dy:
                canvas.yview_scroll(-1 if dy > 0 else 1, "units")
            return "break"

        def on_key(event):
            if event.keysym in ("Down", "Next"):
                canvas.yview_scroll(3 if event.keysym == "Down" else 15, "units")
            elif event.keysym in ("Up", "Prior"):
                canvas.yview_scroll(-3 if event.keysym == "Up" else -15, "units")
            elif event.keysym == "Home":
                canvas.yview_moveto(0)
            elif event.keysym == "End":
                canvas.yview_moveto(1)
            return "break"

        self._wheel = on_wheel
        self.bind_all("<MouseWheel>", on_wheel, add="+")
        self.bind_all("<<TouchpadScroll>>", on_touchpad, add="+")
        # Arrow keys, Page Up/Down and Home/End, so the window is usable with
        # no pointing device that scrolls at all.
        for key in ("<Up>", "<Down>", "<Prior>", "<Next>", "<Home>", "<End>"):
            self.bind(key, on_key)
        self.canvas = canvas
        canvas.focus_set()

        for title, paragraphs in helptext.SECTIONS:
            tk.Label(inner, text=title, bg=BG, fg=ACCENT,
                     font=("SF Pro Text", 13, "bold")).pack(anchor="w", pady=(12, 4))
            for text in paragraphs:
                # An indented line is a command to paste: shown in a mono face
                # so its spacing survives, and selectable for copying.
                if text.startswith("    "):
                    entry = tk.Entry(inner, bg=CARD, fg=TEXT, relief="flat",
                                     font=("SF Mono", 11), width=60,
                                     readonlybackground=CARD, highlightthickness=0)
                    entry.insert(0, text.strip())
                    entry.configure(state="readonly")
                    entry.pack(anchor="w", fill="x", pady=2)
                else:
                    tk.Label(inner, text=text, bg=BG, fg=DIM, justify="left",
                             wraplength=560, font=("SF Pro Text", 11)).pack(anchor="w")

        # padx/pady on a WIDGET take one distance, not the (top, bottom)
        # tuple pack() accepts. The tuple form threw "expected screen
        # distance" inside the button's callback, where nothing surfaces it,
        # so Help simply did nothing.
        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=20, pady=(0, 14))
        mkbtn(buttons, "Done", self._close, width=7).pack(side="right")
        # The same line as the header, repeated here: the window is tall
        # enough that the top of it is off screen by the time anyone is deep
        # enough to wonder how to keep going.
        # Shorter than the header line and anchored west: at the window's
        # width this shares the bar with the Done button, and the long form
        # was clipped at both ends.
        tk.Label(buttons, text="Arrow keys · Page Up/Down · drag the scrollbar",
                 bg=BG, fg=ACCENT, font=("SF Pro Text", 12, "bold"),
                 anchor="w").pack(side="left", fill="x", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.update_idletasks()
        self.deiconify()

    def _close(self):
        self.unbind_all("<MouseWheel>")
        self.destroy()


class HiddenDialog(tk.Toplevel):
    """The devices the user has hidden, and the way back."""

    def __init__(self, parent, hidden, on_show, on_show_all):
        super().__init__(parent, bg=BG)
        self.withdraw()
        self.title("Hidden devices")
        self.transient(parent)
        self.resizable(False, False)
        self.on_show = on_show

        body = tk.Frame(self, bg=BG, padx=20, pady=16)
        body.pack()
        tk.Label(body, text="Hidden devices", bg=BG, fg=TEXT,
                 font=("SF Pro Text", 14, "bold")).pack(anchor="w")
        tk.Label(body, text="These stay out of the list, and the agent does not connect "
                            "to hidden AirPlay speakers.",
                 bg=BG, fg=DIM, font=("SF Pro Text", 11),
                 wraplength=380, justify="left").pack(anchor="w", pady=(2, 10))

        self.rows = tk.Frame(body, bg=BG)
        self.rows.pack(fill="x")
        for key, name in hidden:
            self._add_row(key, name)

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x", pady=(12, 0))
        mkbtn(buttons, "Done", self._close, width=7).pack(side="right", padx=(6, 0))
        mkbtn(buttons, "Show all", lambda: (on_show_all(), self._close()),
              width=9).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.update_idletasks()
        self.deiconify()
        self.grab_set()

    def _add_row(self, key, name):
        row = tk.Frame(self.rows, bg=BG)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=name, bg=BG, fg=TEXT,
                 font=("SF Pro Text", 13), anchor="w").pack(side="left")

        def show():
            self.on_show(key)
            row.destroy()

        mkbtn(row, "Show", show, width=6, fg=ACCENT).pack(side="right")

    def _close(self):
        self.grab_release()
        self.destroy()


class MyAudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MyAudio")
        self.configure(bg=BG)

        self.store = Store()
        # All network work lives in the launchd agent; see agent/myaudio_agent.py.
        # The job is (re)installed here so the bundle works wherever it is put,
        # not just where it was built.
        self._agent_ok, self._agent_message = ensure_agent()
        if not self._agent_ok:
            log.error("agent setup failed: %s", self._agent_message)
        self.airplay = AgentClient()
        self._cards = {}
        self._snapshot = None
        self._busy = False
        self._fitted_rows = -1
        self._fitted_hint = False
        self._fitted_hidden = 0
        self._hidden = []
        self._pin_dialog = None
        self._speaker_dialog = None
        self._last_levels = None
        self._levels_csv = levelcsv.Recorder()
        self._opening_state = None
        self._row_errors = {}
        self._speaker_cache = {}

        header = tk.Frame(self, bg=BG, padx=16, pady=12)
        header.pack(fill="x")
        header.columnconfigure(1, weight=1)
        title = tk.Frame(header, bg=BG)
        title.grid(row=0, column=0, sticky="w")
        tk.Label(title, text="MyAudio", bg=BG, fg=TEXT,
                 font=("SF Pro Display", 20, "bold")).pack(side="left")
        tk.Label(title, text=f"v{__version__}", bg=BG, fg=DIM,
                 font=("SF Pro Text", 11)).pack(side="left", padx=(6, 0), pady=(6, 0))
        self.status = tk.Label(header, text="Scanning…", bg=BG, fg=DIM,
                               font=("SF Pro Text", 11), anchor="w")
        self.status.grid(row=0, column=1, sticky="w", padx=12)
        mkbtn(header, "Rescan", self.rescan, width=8).grid(row=0, column=2, sticky="e")
        self.source = tk.Label(header, text="", bg=BG, fg=DIM,
                               font=("SF Pro Text", 11), anchor="e")
        self.source.grid(row=1, column=2, sticky="e", pady=(4, 0))
        # Only shown when something IS hidden — an always-present button
        # advertising an empty list is just noise.
        self.hidden_button = mkbtn(header, "Hidden", self.show_hidden, width=12, fg=DIM)
        self.hidden_button.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.hidden_button.grid_remove()

        self.list_frame = tk.Frame(self, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 4))
        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=16, pady=(0, 10))
        self.restore_switch = Switch(footer, self._restore_and_exit, bg=BG, accent=DANGER)
        self.restore_switch.pack(side="left", padx=(0, 10))
        tk.Label(footer, bg=BG, fg=DIM, font=("SF Pro Text", 11), justify="left",
                 anchor="w", wraplength=460,
                 text="Restore devices to how I found them and exit — puts every volume, "
                      "connection and speaker routing back to what it was when MyAudio "
                      "opened, then quits.").pack(side="left", fill="x", expand=True)
        mkbtn(footer, "Help", self.show_help, width=6).pack(side="right", padx=(10, 0))

        self.hint = tk.Label(self, bg=BG, fg=WARN, font=("SF Pro Text", 11),
                             anchor="w", wraplength=600, justify="left")
        self.hint.pack(fill="x", padx=16, pady=(0, 12))
        self.hint.pack_forget()

        self.after(200, self._poll)
        # Photograph the devices as we found them, so the restore switch has
        # something to put back. Off the UI thread: it queries every device.
        threading.Thread(target=self._capture_opening_state, daemon=True).start()
        threading.Thread(target=self._prefetch_speakers, daemon=True).start()
        self._build_menu()
        self.protocol("WM_DELETE_WINDOW", self._close)
        # ⌘Q and the Quit menu item bypass WM_DELETE_WINDOW on macOS, so they
        # were terminating the app without saving preferences. Route them
        # through the same close path. Neither restores devices — that stays
        # deliberate, and is what the red switch is for.
        try:
            self.createcommand("::tk::mac::Quit", self._close)
        except tk.TclError:
            pass

    # -- agent plumbing --------------------------------------------------
    def _submit(self, call, on_done=None):
        """Run a blocking agent call off the UI thread, marshal the result back."""
        def work():
            try:
                result = call()
            except Exception as exc:
                result = (False, f"{type(exc).__name__}: {exc}"[:120])
            if on_done is not None:
                self.after(0, lambda: on_done(result))

        threading.Thread(target=work, daemon=True).start()

    # -- data ------------------------------------------------------------
    def _poll(self):
        if not self._busy:
            self._busy = True
            threading.Thread(target=self._refresh, daemon=True).start()
        self.after(POLL_MS, self._poll)

    def _build_menu(self):
        """An ordinary Help menu, NOT the system-managed one.

        A Tk menu named "help" is adopted by macOS, which adds its own
        "MyAudio Help" entry pointing at a help book this app does not have —
        so the menu showed two identical entries, one of them reporting that
        help is not available. An ordinary menu labelled Help carries only
        what is put in it.
        """
        menubar = tk.Menu(self)
        helpmenu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=helpmenu)
        helpmenu.add_command(label="MyAudio Help", command=self.show_help)
        helpmenu.add_command(label="MyAudio Version History",
                             command=self._show_history)
        self.configure(menu=menubar)

    def _prefetch_speakers(self):
        """Fetch the speaker lists up front so the dialog opens filled in.

        Asking the agent takes about a second, which was long enough to show an
        empty window before the rows arrived.
        """
        if self._snapshot is None:
            self.after(1500, lambda: threading.Thread(
                target=self._prefetch_speakers, daemon=True).start())
            return
        for row in self._snapshot.rows:
            if not row.can_send:
                continue
            ok, options = self.airplay.output_devices(row.key)
            if ok:
                self._speaker_cache[row.key] = options

    def _capture_opening_state(self):
        try:
            self._opening_state = restore.capture(self.airplay)
        except Exception:
            log.exception("could not capture opening device state")

    def show_help(self):
        HelpDialog(self)

    def _restore_and_exit(self, _on):
        if self._opening_state is None:
            self.status.config(text="Still reading the devices — try again in a moment.")
            self.restore_switch.set_state(False, True)
            return
        self.status.config(text="Restoring devices…")
        self.restore_switch.set_state(True, False)
        threading.Thread(target=self._do_restore, daemon=True).start()

    def _do_restore(self):
        try:
            changed, failed = restore.restore(self._opening_state, self.airplay)
        except Exception as exc:
            log.exception("restore failed")
            # Python clears `exc` when the except block ends, so the message has
            # to be taken now — the lambda below runs later, on the main thread.
            message = str(exc)
            self.after(0, lambda: self.status.config(text=f"Restore failed: {message}"))
            self.after(0, lambda: self.restore_switch.set_state(False, True))
            return
        log.info("restored %d setting(s) before exit", len(changed))
        if failed:
            # Do NOT quit on a partial restore. Quitting here is what let a
            # restore that put nothing back look exactly like one that worked,
            # and the devices were left as the session had them.
            log.warning("restore incomplete: %s", failed)
            summary = "; ".join(failed)
            self.after(0, lambda: self.status.config(
                text=f"Restore incomplete — {summary}"))
            self.after(0, lambda: self.restore_switch.set_state(False, True))
            return
        self.after(0, self._close)

    def _show_history(self):
        window = tk.Toplevel(self, bg=BG)
        window.title("MyAudio Version History")
        window.geometry("640x520")
        header = tk.Frame(window, bg=BG, padx=18, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="MyAudio — Version History", bg=BG, fg=TEXT,
                 font=("SF Pro Display", 17, "bold")).pack(anchor="w")
        tk.Label(header, text=history.GENERATED_BY, bg=BG, fg=DIM, justify="left",
                 font=("SF Pro Text", 11), wraplength=590).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        text = tk.Text(body, bg=CARD, fg=TEXT, font=("SF Pro Text", 12), wrap="word",
                       relief="flat", padx=12, pady=10, highlightthickness=0)
        bar = tk.Scrollbar(body, command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.tag_configure("version", foreground=ACCENT,
                           font=("SF Pro Text", 12, "bold"), spacing1=8)
        text.tag_configure("date", foreground=DIM, font=("SF Pro Text", 11))
        for version, date, summary in history.HISTORY:
            text.insert("end", f"v{version}", "version")
            text.insert("end", f"   {date}\n", "date")
            text.insert("end", f"{summary}\n")
        text.configure(state="disabled")

    def _audit_levels(self, snapshot):
        """Continuous audit trail of every level change, whatever caused it.

        Read from the sources rather than the rows on screen: the row list
        hides virtual devices and blanks unroutable ones, so auditing it would
        miss exactly the levels we are hunting.
        """
        levels = {}
        for device in coreaudio.list_outputs(include_ignored=True):
            if device.get("volume") is not None:
                levels[device["name"]] = round(device["volume"] * 100, 1)
            if device.get("muted"):
                levels[f"{device['name']} [muted]"] = True
        for speaker in self.airplay.snapshot():
            if speaker.get("volume") is not None:
                levels[f"{speaker['name']} [speaker]"] = speaker["volume"]
        # Every Music speaker, including the Mac itself — enabling an AirPlay
        # speaker hands loudness control of the Mac to ITS Music level rather
        # than the output device, which is invisible if only rows are audited.
        for speaker in snapshot.music:
            if speaker.get("volume") is not None:
                levels[f"{speaker['name']} [Music]"] = speaker["volume"]
                levels[f"{speaker['name']} [Music-on]"] = speaker["selected"]
        master = musicroute.master_volume()
        if master is not None:
            levels["Music [master]"] = master
        if self._last_levels is not None:
            changed = {k: f"{self._last_levels.get(k)}->{v}"
                       for k, v in levels.items() if self._last_levels.get(k) != v}
            if changed:
                log.info("volume changed: %s", changed)
        self._last_levels = levels
        self._levels_csv.record(levels)

    def _refresh(self):
        try:
            self.airplay.poll()
            snapshot = devices.build(self.store, self.airplay.snapshot(),
                                     self.airplay.last_scan_count)
            for row in snapshot.rows:
                if row.key in self._row_errors:
                    row.note = self._row_errors[row.key]
            self._audit_levels(snapshot)
        except Exception as exc:
            log.exception("refresh failed")
            snapshot = devices.Snapshot(rows=[], default_name=f"error: {exc}")
        finally:
            self._busy = False
        self.after(0, lambda: self._render(snapshot))

    def rescan(self):
        self.status.config(text="Scanning…")
        bluetooth.invalidate()
        self._submit(self.airplay.refresh,
                     lambda _r: threading.Thread(target=self._refresh, daemon=True).start())

    # -- actions ---------------------------------------------------------
    def step(self, key, delta):
        row = self._row(key)
        if row is None or not row.can_step:
            return
        if row.kind == "airplay":
            self._submit(lambda: self._step_airplay(key, row.name, delta),
                         lambda _r: threading.Thread(target=self._refresh, daemon=True).start())
            return
        if row.uid is None:
            return
        threading.Thread(target=self._step_local, args=(row, delta), daemon=True).start()

    def _step_airplay(self, key, name, delta):
        before = self._local_levels()
        result = self.airplay.step_volume(key, delta)
        time.sleep(0.5)
        self._log_side_effects(f"AirPlay volume {delta:+g} on {name}", before)
        return result

    def _step_local(self, row, delta):
        if not row.is_default:
            coreaudio.set_default(row.uid)
        current = row.volume if row.volume is not None else 0.0
        coreaudio.set_volume(row.uid, max(0.0, min(100.0, current + delta)) / 100.0)
        self._refresh()

    def set_power(self, key, on):
        row = self._row(key)
        if row is None:
            return
        if row.kind == "airplay":
            # The switch is power. Routing lives entirely in Speakers…, so the
            # two controls no longer overlap.
            if not row.can_toggle:
                self.status.config(text=f"{row.name} does not report a power state.")
                return
            self.status.config(
                text=f"Turning {row.name} {'on' if on else 'off'}…")
            self._submit(lambda: self.airplay.set_power(key, on),
                         lambda result: self._power_done(row.name, on, result))
            return
        if on:
            if row.is_default:
                return
            # A disconnected Bluetooth device has to be connected before macOS
            # will accept it as the output device.
            if row.can_toggle and row.address and not row.connected:
                self.status.config(text=f"Connecting {row.name}…")
                threading.Thread(target=self._connect_then_select, args=(row,), daemon=True).start()
            elif row.can_select:
                self.status.config(text=f"Switching output to {row.name}…")
                threading.Thread(target=self._make_default, args=(row,), daemon=True).start()
            return
        if row.can_toggle and row.connected and row.address:
            self.status.config(text=f"Disconnecting {row.name}…")
            threading.Thread(target=self._set_power, args=(row, on), daemon=True).start()
        elif row.kind == "local":
            self.status.config(
                text=f"{row.name} is a built-in output — pick another device to switch away from it.")

    def _connect_then_select(self, row):
        ok, err = bluetooth.set_connected(row.address, True)
        if not ok:
            self.after(0, lambda: self.status.config(text=f"Could not connect {row.name}: {err}"))
            self._refresh()
            return
        # CoreAudio needs a moment to publish the new output device.
        for _ in range(10):
            time.sleep(0.5)
            match = next((d for d in coreaudio.list_outputs()
                          if coreaudio.normalize_mac(row.address) in coreaudio.normalize_mac(d["uid"])), None)
            if match:
                coreaudio.set_default(match["uid"])
                break
        self._refresh()

    @staticmethod
    def _local_levels():
        return {d["name"]: round(d.get("volume") or 0.0, 3)
                for d in coreaudio.list_outputs()}

    def _log_side_effects(self, what, before):
        """Catch anything that moves a local device's volume behind our back —
        an AirPlay action should never touch the Mac's own outputs."""
        after = self._local_levels()
        changed = {k: (before.get(k), v) for k, v in after.items() if before.get(k) != v}
        if changed:
            log.warning("%s -> local output volumes moved: %s", what, changed)
        else:
            log.info("%s (no immediate local volume change)", what)

    def choose_speakers(self, key):
        row = self._row(key)
        if row is None:
            return
        if row.kind == "local":
            # The Mac's "own audio" is Music, so its destinations come from
            # Music rather than from an AirPlay device's output list.
            self.status.config(text="Reading Music speakers…")
            self._submit(musicroute.devices,
                         lambda speakers: self._music_speakers_ready(row.name, speakers))
            return
        if not row.can_send:
            return
        cached = self._speaker_cache.get(key)
        if cached:
            self._speakers_ready(key, row.name, (True, cached))
            # Refresh behind the open dialog so a stale list self-corrects.
            threading.Thread(target=self._prefetch_speakers, daemon=True).start()
            return
        self.status.config(text=f"Reading {row.name} speaker list…")
        self._submit(lambda: self.airplay.output_devices(key),
                     lambda result: self._speakers_ready(key, row.name, result))

    def _music_speakers_ready(self, name, speakers):
        if not speakers:
            self.status.config(text="Music is not running, so it has no speakers to list.")
            return
        options = [{"identifier": s["name"], "name": s["name"], "selected": s["selected"]}
                   for s in speakers]
        self.status.config(text="Choose where Music plays")
        self._speaker_dialog = SpeakerDialog(
            self, "Music", options, self._apply_music_speakers,
            subtitle="This Mac's music. Leave none ticked and it plays on the Mac.")

    def _apply_music_speakers(self, chosen):
        if self._speaker_dialog is not None:
            self._speaker_dialog._close()
            self._speaker_dialog = None
        self.status.config(text="Setting Music speakers…")
        self._submit(lambda: self._set_music_speakers(chosen),
                     lambda result: self._speakers_applied("Music", len(chosen), result))

    def _set_music_speakers(self, chosen):
        speakers = musicroute.devices()
        if not speakers:
            return False, "Music is not running"
        computer = next((s["name"] for s in speakers
                         if s["kind"] == musicroute.COMPUTER_KIND), None)
        wanted = set(chosen)
        # Music refuses to be left with no destination at all, so fall back to
        # the Mac rather than letting Apply silently fail.
        if not wanted and computer:
            wanted = {computer}
        for speaker in speakers:
            if speaker["selected"] != (speaker["name"] in wanted):
                musicroute.set_selected(speaker["name"], speaker["name"] in wanted)
        return True, ""

    def _speakers_ready(self, key, name, result):
        ok, options = result
        if not ok:
            self.status.config(text=f"Could not read speakers for {name}")
            return
        self.status.config(text=f"Choose where {name} plays its audio")
        self._speaker_dialog = SpeakerDialog(
            self, name, options,
            lambda identifiers: self._apply_speakers(key, name, identifiers))

    def _apply_speakers(self, key, name, identifiers):
        # Dismiss straight away — the call can take a couple of seconds, and a
        # dialog that sits there after Apply reads as a control that failed.
        if self._speaker_dialog is not None:
            self._speaker_dialog._close()
            self._speaker_dialog = None
        count = len(identifiers)
        self.status.config(text=f"Setting {name} speakers…")
        self._submit(lambda: self.airplay.set_output_devices(key, identifiers),
                     lambda result: self._speakers_applied(name, count, result))

    def _speakers_applied(self, name, count, result):
        threading.Thread(target=self._prefetch_speakers, daemon=True).start()
        ok, message = result
        if not ok:
            self.status.config(text=f"Could not set {name} speakers: {message}")
        else:
            self.status.config(
                text=f"{name} now also plays on {count} speaker(s)" if count
                else f"{name} now plays on itself only")
        threading.Thread(target=self._refresh, daemon=True).start()

    def _power_done(self, name, on, result):
        ok, message = result
        if not ok:
            self.status.config(text=f"Could not turn {name} {'on' if on else 'off'}: {message}")
        threading.Thread(target=self._refresh, daemon=True).start()

    def _set_power(self, row, on):
        ok, err = bluetooth.set_connected(row.address, on)
        if ok:
            self._row_errors.pop(row.key, None)
        else:
            self._row_errors[row.key] = err
            self.after(0, lambda: self.status.config(
                text=f"Could not {'connect' if on else 'disconnect'} {row.name}: {err}"))
        self._refresh()

    def _make_default(self, row):
        if not coreaudio.set_default(row.uid):
            self.after(0, lambda: self.status.config(text=f"Could not switch output to {row.name}"))
        self._refresh()

    # -- pairing ---------------------------------------------------------
    def start_pairing(self, key):
        row = self._row(key)
        if row is None:
            return
        protocol = "airplay" if row.needs_airplay_pairing else "companion"
        self.status.config(
            text=f"Starting {protocol} pairing with {row.name} — watch the screen for a code…")
        self._submit(lambda: self.airplay.begin_pairing(key, protocol),
                     lambda result: self._pairing_started(key, row.name, result))

    def _pairing_started(self, key, name, result):
        ok, message = result
        if not ok:
            self.status.config(text=f"Could not start pairing with {name}: {message}")
            return
        self.status.config(text=f"Enter the code shown on {name}")
        self._pin_dialog = PinDialog(self, name, lambda pin: self._pin_entered(key, name, pin))

    def _pin_entered(self, key, name, pin):
        if pin is None:
            self._close_pin_dialog()
            self._submit(lambda: self.airplay.cancel_pairing(key))
            self.status.config(text="Pairing cancelled")
            return
        self._submit(lambda: self.airplay.finish_pairing(key, pin),
                     lambda result: self._pairing_finished(name, result))

    def _pairing_finished(self, name, result):
        ok, message = result
        if ok:
            self._close_pin_dialog()
            self.status.config(text=f"Paired with {name}")
            return
        if self._pin_dialog is not None:
            self._pin_dialog.failed(message or "Pairing failed")

    def _close_pin_dialog(self):
        if self._pin_dialog is not None:
            self._pin_dialog.grab_release()
            self._pin_dialog.destroy()
            self._pin_dialog = None

    # -- hiding ----------------------------------------------------------
    def hide_device(self, key):
        row = self._row(key)
        name = row.name if row else key
        self.store.set_hidden(key, True)
        log.info("hid %s (%s)", name, key)
        self.status.config(text=f"Hid {name}")
        threading.Thread(target=self._refresh, daemon=True).start()

    def show_hidden(self):
        HiddenDialog(self, self._hidden, self._unhide, self._unhide_all)

    def _unhide(self, key):
        self.store.set_hidden(key, False)
        log.info("un-hid %s", key)
        threading.Thread(target=self._refresh, daemon=True).start()

    def _unhide_all(self):
        self.store.unhide_all()
        log.info("un-hid every device")
        threading.Thread(target=self._refresh, daemon=True).start()

    def _row(self, key):
        if self._snapshot is None:
            return None
        return next((r for r in self._snapshot.rows if r.key == key), None)

    # -- rendering -------------------------------------------------------
    def _render(self, snapshot):
        self._snapshot = snapshot
        if snapshot.default_name:
            self.status.config(text=f"Playing through {snapshot.default_name}")
        elif snapshot.rows:
            self.status.config(text="No active output")

        if snapshot.sources:
            self.source.config(text="Source: " + ", ".join(snapshot.sources), fg=ACCENT)
        else:
            self.source.config(text="Nothing playing", fg=DIM)

        wanted = {row.key for row in snapshot.rows}
        for key in [k for k in self._cards if k not in wanted]:
            self._cards.pop(key).destroy()

        for row in snapshot.rows:
            card = self._cards.get(row.key)
            if card is None:
                card = DeviceCard(self.list_frame, self, row)
                self._cards[row.key] = card
            card.update_row(row)
            card.pack_forget()
            card.pack(fill="x", pady=3)

        self._hidden = snapshot.hidden
        if snapshot.hidden:
            self.hidden_button.config(text=f"Hidden ({len(snapshot.hidden)})…")
            self.hidden_button.grid()
        else:
            self.hidden_button.grid_remove()

        if snapshot.hint:
            self.hint.config(text=snapshot.hint)
            self.hint.pack(fill="x", padx=16, pady=(0, 12))
        else:
            self.hint.pack_forget()

        if (len(snapshot.rows) != self._fitted_rows
                or bool(snapshot.hint) != self._fitted_hint
                or len(snapshot.hidden) != self._fitted_hidden):
            self._fitted_rows = len(snapshot.rows)
            self._fitted_hint = bool(snapshot.hint)
            self._fitted_hidden = len(snapshot.hidden)
            self._fit()

    def _fit(self):
        self.update_idletasks()
        width = max(self.winfo_reqwidth(), 640)
        height = min(self.winfo_reqheight(), self.winfo_screenheight() - 120)
        self.geometry(f"{width}x{height}")
        self.minsize(width, min(height, 320))

    def _close(self):
        self.store.save()
        self.destroy()


LOG_PATH = os.path.expanduser("~/Library/Logs/MyAudio.log")


def main():
    logging.basicConfig(
        filename=LOG_PATH, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    MyAudio().mainloop()
