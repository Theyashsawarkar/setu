"""setu (सेतु, "bridge"): Bluetooth for Vyom, through BlueZ (bluetoothctl).

Connected devices come first in the list, each with its battery and, for
headphones and speakers, what they're doing (music in high quality or
calls with the mic); the one picked shows big on the right. Below: paired devices that aren't connected, and the
devices nearby (found while the panel is open), closest first. Pairing is
a step of its own: the 6-digit code shown big, to compare with the device.
"""
import subprocess
import time

from gi.repository import GLib, Gtk, Pango
from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

from . import audio, bluez, fastpair, vim
from .pairing import Session

# KEYBINDS (generated from setu/vim.py by scripts/keybinds.py; don't edit by hand)
# keybind: Vyom/bluetooth:normal | Enter | Connect or disconnect the selected device (pairs a new one)
# keybind: Vyom/bluetooth:normal | d d | Remove (unpair) the selected device (y confirms)
# keybind: Vyom/bluetooth:normal | r | Rescan for devices now
# keybind: Vyom/bluetooth leader:normal | Space p p | Toggle Bluetooth on or off
# keybind: Vyom/bluetooth leader:normal | Space a a | Start pairing with the selected device, then connect it
# keybind: Vyom/bluetooth leader:normal | Space a p | Start pairing with the selected device (pair and trust, without connecting)
# keybind: Vyom/bluetooth leader:normal | Space c c | Connect the selected device
# keybind: Vyom/bluetooth leader:normal | Space c d | Disconnect the selected device
# keybind: Vyom/bluetooth leader:normal | Space v o | Set the selected headphones or speaker as the sound output
# keybind: Vyom/bluetooth leader:normal | Space v m | Switch the selected headphones to music (high quality, no mic)
# keybind: Vyom/bluetooth leader:normal | Space v c | Switch the selected headphones to calls (with the mic)
# keybind: Vyom/bluetooth leader:normal | Space u h | Toggle unnamed nearby devices (show or hide them)
# keybind: Vyom/bluetooth leader:normal | Space y a | Copy the selected device's address
# keybind: Vyom/bluetooth leader:normal | Space d d | Remove (unpair) the selected device (y confirms)
# keybind: Vyom/bluetooth-pairing | Enter | Confirm the pairing code matches (or try again after an error)
# keybind: Vyom/bluetooth-pairing | Esc | Cancel pairing
# END KEYBINDS

BT, BT_OFF = "\U000f00af", "\U000f00b2"
ICONS = {"audio-headset": "\U000f02cb", "audio-headphones": "\U000f02cb", "audio-card": "\U000f04c3",
         "input-mouse": "\U000f037d", "input-keyboard": "\U000f030c", "input-gaming": "\U000f0297",
         "phone": "\U000f011c", "computer": "\U000f0322", "input-tablet": "\U000f04f7",
         "video-display": "\U000f0379", "multimedia-player": "\U000f075a"}
CHECK, VOLUME, EYE, EYE_OFF, CASE = "\U000f012c", "\U000f057e", "\U000f0208", "\U000f0209", "\U000f03d7"
LINK, LINK_OFF, DELETE, CLOSE, POWER = "\U000f0337", "\U000f0338", "\U000f01b4", "\U000f0156", "\U000f0425"
BOLT, BATTERY = "\U000f0241", "\U000f0079"
PART_NAMES = {"left": "Left", "right": "Right", "case": "Case"}
SHORT = {"Left": "L", "Right": "R"}   # a card's battery line: "L 82% · R 76% · Case 34%"


def icon_of(d):
    return ICONS.get(d.get("Icon", ""), BT)


def charge(p):
    """(colour, words) for a battery level: red under 10%, yellow under 20%."""
    if p < 10:
        return "red", "plug it in"
    if p < 20:
        return "yellow", "charge soon"
    return "green", ""


def part_color(level):
    """A bud's or the case's colour: red at 20% or less, yellow at 40% or less."""
    if level is None:
        return "gray"
    if level <= 20:
        return "red"
    if level <= 40:
        return "yellow"
    return "green"


def signal(rssi):
    """(bars, word, colour) for a received signal strength."""
    if rssi is None:
        return -1, "", ""
    if rssi >= -60:
        return 4, "Close", "green"
    if rssi >= -70:
        return 3, "Near", "green"
    if rssi >= -82:
        return 2, "Far", "yellow"
    return 1, "Far", "yellow"


def ago(t):
    s = max(0, time.time() - t)
    if s < 90:
        return "just now"
    for size, unit in ((86400 * 30, "month"), (86400 * 7, "week"), (86400, "day"), (3600, "hour"), (60, "minute")):
        if s >= size:
            n = int(s // size)
            return f"{n} {unit}{'s' if n > 1 else ''} ago"
    return "just now"


class Plugin(Base):
    name, title, icon, color = "setu", "Bluetooth", BT, "blue"
    placeholder = "Filter devices…"
    preview = True
    preview_width = 330
    live = 3
    hints = [Hint("Enter", "connect / disconnect"), Hint("Space v o", "sound output"), Hint("Space a p", "pair"),
             Hint("d d", "remove"), Hint("Space p p", "on / off")]
    modal = True                # vim keys (Vyom 0.7): NORMAL first, / filters
    start_mode = "normal"
    key_groups = vim.GROUPS
    empty_text = ""

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.scan = None
        self.switch = None
        self.chipbox = None
        self.adapter = {"state": "ok"}
        self.audio = {}
        self.ubats = {}
        self.hidden = 0
        self.show_unnamed = False
        self.resetting = False
        self.session = None
        self.errors = {}          # mac -> what went wrong last time, in words
        self.unreach = {}         # mac -> when it last couldn't be reached
        self.busy = {}            # mac -> "Connecting…" while an action runs
        self.seen = util.load_state("setu-last-connected", {})
        self.seen_saved = 0.0
        self.fp = fastpair.Scanner()   # left / right / case from Fast Pair advertisements
        self.is_open = False

    def available(self):
        return True, ""   # no bluetoothctl / no adapter: the panel says so, clearly

    # ------------------------------------------------------------ header
    def header_extra(self):
        self.chipbox = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        self.switch = ui.switch(False, self.power, "Bluetooth on or off (Space p p)")
        self.handler = self.switch.handler
        box = ui.hbox(self.chipbox, self.switch, spacing=10)
        box.set_valign(Gtk.Align.CENTER)
        return box

    def sync_header(self):
        a = self.adapter
        if self.switch is not None:
            on = a.get("state") == "ok"
            self.switch.set_visible(a.get("state") in ("ok", "off"))
            if self.switch.get_active() != on:
                self.switch.handler_block(self.handler)
                self.switch.set_active(on)
                self.switch.handler_unblock(self.handler)
        if self.chipbox is not None:
            while (c := self.chipbox.get_first_child()) is not None:
                self.chipbox.remove(c)
            if a.get("state") == "ok" and not self.session:
                # Only what's unusual is said: this computer can be found by others.
                if a.get("discoverable"):
                    self.chipbox.append(ui.chip(f"Visible as {a['alias']}", "yellow", EYE))
                if a.get("discovering"):
                    dot = ui.label("●", "setu-pulse")
                    scan = ui.hbox(dot, ui.label("Searching"), spacing=6, cls="chip")
                    scan.set_tooltip_text(f"Finding devices nearby. Others can't find {a['alias']} "
                                          "by searching, but pairing from here works.")
                    scan.add_css_class("c-yellow")
                    scan.set_valign(Gtk.Align.CENTER)
                    self.chipbox.append(scan)
            if a.get("state") == "ok" and self.panel is not None:
                self.start_scan()
        return False

    # ------------------------------------------------------------ lifecycle
    def opened(self, args):
        super().opened(args)
        self.start_scan()
        self.is_open = True
        self.background(self.fp.start)

    def closed(self):
        self.is_open = False
        self.background(self.fp.stop)       # our LE scan ends with the panel
        if self.session is not None:
            self.session.cancel()
            self.end_session()
        if self.scan and self.scan.poll() is None:
            self.scan.terminate()
        self.scan = None
        if bluez.have():
            util.spawn(["bluetoothctl", "scan", "off"])

    def start_scan(self):
        if not bluez.have() or self.adapter.get("state") != "ok":
            return
        if self.scan is None or self.scan.poll() is not None:
            try:
                self.scan = subprocess.Popen(["bluetoothctl", "--timeout", "60", "scan", "on"],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                self.scan = None

    def power(self, on):
        blocked = bool(self.adapter.get("blocked")) and on
        self.set_status("turning Bluetooth on…" if on else "turning Bluetooth off…")

        def work():
            # A soft block (rfkill, or an earlier "off" somewhere else) is lifted
            # first: logind lets the seat's user do it. A hard block (a switch)
            # can't be, and says so.
            if blocked and bluez.unblock() != 0:
                return "blocked"
            return bluez.bt("power", "on" if on else "off")[0]

        def done(r):
            if r == "blocked":
                self.set_status("Bluetooth is blocked by a switch or the airplane-mode key", "bad")
            elif r:
                self.set_status("Bluetooth didn't turn " + ("on" if on else "off"), "bad")
            else:
                self.set_status("")
            self.refresh()
        self.background(work, done)

    # ------------------------------------------------------------ the list
    def search(self, q):
        if self.session is not None:
            self.empty_text = ""
            return []
        a = bluez.adapter()
        self.adapter = a
        GLib.idle_add(self.sync_header)
        if a["state"] != "ok":
            return []
        devs, self.hidden = bluez.devices(self.show_unnamed)
        connected = [d for d in devs if d.get("Connected") == "yes"]
        self.audio = audio.state() if any(bluez.is_audio(d) for d in connected) else {}
        self.ubats = bluez.upower_batteries() if connected else {}
        now = time.time()
        for d in connected:
            self.seen[d["mac"]] = now
            self.unreach.pop(d["mac"], None)
        if connected and now - self.seen_saved > 60:
            self.seen_saved = now
            util.save_state("setu-last-connected", self.seen)

        # Fast Pair: what earbuds said in their advertisements, matched to the
        # connected device by its name (the advertiser has an address of its
        # own); two connected devices with one name: no guess, nothing shown.
        if connected and self.is_open and not self.fp.on:
            self.fp.start()                 # Bluetooth came on while the panel was open
        readings = self.fp.read(now) if connected else {}
        if not self.is_open:
            self.fp.stop()                  # the panel closed while this ran
        names = [d.get("Alias") or d.get("Name") or "" for d in connected]
        matched = set()
        for d, name in zip(connected, names):
            r = readings.get(name)
            if r and names.count(name) == 1:
                d["fp"] = r
                if r.get("address"):
                    matched.add(r["address"].upper())
        devs = [d for d in devs if d["mac"].upper() not in matched or d.get("Connected") == "yes"]

        conn, paired, near = [], [], []
        for d in devs:
            d["name"] = d.get("Alias") or d.get("Name") or ""
            if bluez.unnamed(d["mac"], d["name"]):
                d["name"] = "Unnamed device"
            if q and util.fuzzy(q, f"{d['name']} {bluez.kind(d)} {d['mac']}") is None:
                continue
            if d.get("Connected") == "yes":
                d["group"] = "Connected"
                conn.append(d)
            elif d.get("Paired") == "yes":
                d["group"] = "Paired"
                paired.append(d)
            else:
                d["group"] = "Nearby"
                near.append(d)
        near.sort(key=lambda d: (d["rssi"] is None, -(d["rssi"] or 0), d["name"].lower()))
        rows = [Section("Connected", len(conn), "Enter disconnects")] if conn else []
        rows += [self.row(d) for d in conn]
        if paired:
            rows.append(Section("Paired, not connected", len(paired), "Enter connects"))
            rows += [self.row(d) for d in paired]
        if self.hidden:
            note = f"closest first · Space u h shows {self.hidden} unnamed"
        elif self.show_unnamed:
            note = "closest first · Space u h hides them"
        else:
            note = "closest first"
        if near or (not q and (self.hidden or self.show_unnamed)):
            rows.append(Section("Nearby", len(near), note))
            rows += [self.row(d) for d in near]
        self.empty_text = "" if conn else ("Nothing here yet: nearby devices show up as they're found"
                                           if not q else "No device matches")
        return rows

    def batteries(self, d):
        """[(label, percent)]: the earbuds' own (Fast Pair: left, right, case)
        when they say, UPower's separate ones when it reports several, else
        BlueZ's one, else none."""
        fp = d.get("fp")
        if fp:
            return [(PART_NAMES[k], p["level"]) for k, p in fp["parts"].items() if p["level"] is not None]
        if d["mac"].upper() in self.ubats:
            return self.ubats[d["mac"].upper()]
        return [("", d["battery"])] if d["battery"] is not None else []

    def row(self, d):
        mac, g, kind = d["mac"], d["group"], bluez.kind(d)
        chips = []
        if mac in self.busy:
            chips.append((self.busy[mac], "yellow"))
        elif mac in self.errors and g != "Connected" and mac not in self.unreach:
            chips.append(("Didn't work", "red"))
        if g == "Paired":
            sub = kind
            if mac in self.seen:
                sub += f" · last connected {ago(self.seen[mac])}"
            if mac in self.unreach and mac not in self.busy:
                chips.append(("Out of range", "gray"))
            return Row(d["name"], sub, icon=icon_of(d), color="blue", chips=chips, data={"kind": "dev", **d})
        if g == "Nearby":
            lvl, word, col = signal(d["rssi"])
            sub = f"{kind} · Enter pairs" if d["name"] != "Unnamed device" else f"{mac} · {kind}"
            if d["rssi"] is None:
                sub += " · not heard just now"
            return Row(d["name"], sub, icon=icon_of(d), color="gray", chips=chips, level=lvl, level_text=word,
                       level_color=col, data={"kind": "dev", **d})
        # Connected: what it's doing (or what it is), the sound output as a
        # peach mark after the name, its battery at the right (the lower bud
        # for earbuds), green / yellow / red by charge.
        a = self.audio.get(mac.upper())
        bats = self.batteries(d)
        meta, mcol = "", ""
        if bats:
            buds = [p for lab, p in bats if lab != "Case"] or [p for _, p in bats]
            low = min(buds)
            meta, mcol = f"{BATTERY} {low}%", charge(low)[0]
        r = Row(d["name"], audio.doing(a) if a else kind, icon=icon_of(d), color="blue", chips=chips,
                badge=VOLUME if a and a["default"] else "", badge_color="peach", meta=meta, data={"kind": "dev", **d})
        r.meta_color = mcol      # Vyom 0.8.1 colours it; an older one shows it plain
        return r

    # ------------------------------------------------------------ the strip
    def build_strip(self):
        if self.session is not None:
            return self.pairing_card()
        st = self.adapter.get("state")
        self.show_preview(st == "ok")
        if st == "missing":
            return self.trouble("bluetoothctl isn't installed",
                                "setu talks to Bluetooth through BlueZ: install it (bluez and bluez-utils), "
                                "then start the service: systemctl enable --now bluetooth.", "red")
        if st == "nodaemon":
            return self.trouble("The Bluetooth service isn't running",
                                "Start it: systemctl enable --now bluetooth.", "red")
        if st == "stuck":
            return self.trouble_fix("Bluetooth isn't answering",
                                    "The chip or the service stopped responding. Reset wakes it again, no reboot needed.")
        if st == "none":
            return self.trouble_fix("No Bluetooth adapter found",
                                    "It may have stopped after sleep. Reset tries to wake it; if it's a USB "
                                    "adapter, check it's plugged in.")
        if st == "off":
            body = ui.vbox(ui.label("Bluetooth is off", "hero-title", xalign=0),
                           ui.label("Your devices can't connect until it's on.", "hero-sub", xalign=0), spacing=4)
            body.set_hexpand(True)
            return ui.hero(ui.tile(BT_OFF, "gray", 22, "tile"), body,
                           ui.button("Turn on", lambda: self.power(True), "primary", POWER, "Enter"),
                           color="gray")
        # Bluetooth is on: connected devices are the list's first rows (A1,
        # 2026-11-26); the strip only speaks when nothing is connected.
        items = self.panel.items if self.panel else []
        if any((r.data or {}).get("group") == "Connected" for r, _w in items):
            return None
        if self.panel and self.query():
            return None
        body = ui.vbox(ui.label("Nothing connected", "hero-title", xalign=0),
                       ui.label("Pick a device below and press Enter to connect it.", "hero-sub", xalign=0),
                       spacing=4)
        return ui.hero(ui.tile(BT, "blue", 22, "tile"), body, color="gray")

    def query(self):
        try:
            return self.panel.entry.get_text()
        except AttributeError:
            return ""

    def trouble_fix(self, title, text):
        """A trouble card with a Reset button (Enter) that wakes the chip."""
        body = ui.vbox(ui.label(title, "hero-title", xalign=0),
                       ui.label(text, "hero-sub", xalign=0, wrap=True), spacing=4)
        body.set_hexpand(True)
        return ui.hero(ui.tile(BT_OFF, "yellow", 22, "tile"), body,
                       ui.button("Reset Bluetooth", self.reset, "primary", POWER, "Enter"), color="yellow")

    def reset(self):
        if self.resetting:
            return
        self.resetting = True
        self.set_status("resetting Bluetooth…")

        def done(st):
            self.resetting = False
            if st in ("ok", "off"):
                self.set_status("")
            else:
                self.set_status("Bluetooth still isn't answering: a reboot may be needed", "bad")
            self.refresh()
        self.background(bluez.reset, done)

    def trouble(self, title, text, color):
        n = ui.notice(title, text, color)
        n.add_css_class("setu-trouble")
        return n

    # ------------------------------------------------------------ the preview
    def build_preview(self, row):
        """A1, the showcase (2026-11-26): the device as a big glass icon, its
        name and state under it, the batteries as one strip of numbers, the
        audio mode, then round buttons with their keys, and one quiet line
        of details at the bottom."""
        d = row.data or {}
        if d.get("kind") != "dev":
            return None
        mac, g = d["mac"], d["group"]
        a = self.audio.get(mac.upper()) if g == "Connected" else None
        chips = []
        if mac in self.busy:
            chips.append((self.busy[mac], "yellow"))
        elif g == "Connected":
            chips.append(("Connected", "green", CHECK))
        elif g == "Paired":
            chips.append(("Paired", "gray"))
        else:
            chips.append(("Not paired", "gray"))
        if a and a["default"]:
            chips.append(("Sound output", "peach", VOLUME))
        if g == "Paired" and mac in self.unreach:
            chips.append(("Out of range", "gray"))
        icon = ui.label(icon_of(d), "glyph", "setu-hero-glyph")
        hero = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        hero.add_css_class("setu-hero-icon")
        if g == "Nearby":
            hero.add_css_class("setu-hero-quiet")
        icon.set_hexpand(True)
        hero.append(icon)
        name = ui.label(d["name"], "setu-hero-name", justify=Gtk.Justification.CENTER,
                        ellipsize=Pango.EllipsizeMode.END, max_width_chars=10)
        chiprow = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        for c in chips:
            chiprow.append(ui.chip(*c))
        parts = [hero, ui.vbox(name, chiprow, spacing=8)]
        if mac in self.errors:
            parts.append(ui.notice("Didn't work", self.errors[mac], "red"))
        strip = self.stats(d)
        if strip is not None:
            parts.append(strip)
        if a:
            if a["music"] and a["calls"]:
                cur = a["mode"] if a["mode"] in ("music", "calls") else ""
                seg = ui.segmented([("music", "Music · high quality"), ("calls", "Calls · with mic")], cur,
                                   lambda k, d=d: self.set_mode(d, k))
                seg.set_tooltip_text("Space v m music · Space v c calls")
                parts.append(seg)
            else:
                parts.append(ui.label(audio.doing(a), "setu-hero-meta", justify=Gtk.Justification.CENTER))
        parts.append(self.actions(d, a))
        meta = [bluez.kind(d)]
        if g != "Nearby":
            meta.append("trusted" if d.get("Trusted") == "yes" else "not trusted")
        if g == "Paired" and mac in self.seen:
            meta.append(f"last connected {ago(self.seen[mac])}")
        if g == "Nearby":
            lvl, word, _col = signal(d["rssi"])
            meta.append(f"{word.lower()} · {d['rssi']} dBm" if lvl >= 0 else "not heard just now")
        meta.append(mac)
        foot = ui.label(" · ".join(meta), "setu-hero-meta", justify=Gtk.Justification.CENTER, wrap=True)
        foot.set_vexpand(True)
        foot.set_valign(Gtk.Align.END)
        parts.append(foot)
        box = ui.vbox(*parts, spacing=18, cls="setu-stage")
        box.set_vexpand(True)
        return box

    def stats(self, d):
        """The batteries as one calm strip: a number, a thin line under it,
        the name. Earbuds show left, right and case (— when one didn't say:
        in the case, or the case closed); anything else its one battery."""
        cells = []
        fp = d.get("fp")
        if fp:
            for key in fastpair.PARTS:
                p = fp["parts"][key]
                cells.append((PART_NAMES[key], p["level"], p["charging"]))
        else:
            for lab, p in self.batteries(d):
                cells.append((lab or "Battery", p, False))
        if not cells:
            return None
        grid = Gtk.Grid(column_homogeneous=True)
        grid.add_css_class("setu-stats")
        for i, (lab, lvl, charging) in enumerate(cells):
            col = (part_color(lvl) if fp else charge(lvl)[0]) if lvl is not None else "gray"
            if lvl is None:
                num = ui.label("—", "setu-stat-num", "setu-quiet")
            else:
                num = ui.hbox(ui.label(str(lvl), "setu-stat-num"), ui.label("%", "setu-stat-unit", valign=Gtk.Align.END),
                              spacing=1)
                num.set_halign(Gtk.Align.CENTER)
                if charging:
                    num.append(ui.label(BOLT, "glyph", "t-green", "setu-bolt", valign=Gtk.Align.CENTER))
            bar = ui.progress((lvl or 0) / 100, col)
            cell = ui.vbox(num, bar, ui.label(lab, "setu-stat-name"), spacing=7, cls="setu-stat")
            if i:
                cell.add_css_class("setu-stat-next")
            if lvl is None:
                cell.set_tooltip_text("Not reported: in the case, or the case is closed")
            grid.attach(cell, i, 0, 1, 1)
        return grid

    def round_action(self, glyph, text, keys, callback, kind=""):
        """A round glass button, its name and its keys under it."""
        b = Gtk.Button(halign=Gtk.Align.CENTER)
        b.add_css_class("setu-round")
        if kind:
            b.add_css_class(f"setu-round-{kind}")
        b.set_child(ui.label(glyph, "glyph"))
        b.set_tooltip_text(f"{text} ({keys})")
        b.connect("clicked", lambda *_: callback())
        cap = ui.keycap(keys)
        cap.set_halign(Gtk.Align.CENTER)
        return ui.vbox(b, ui.label(text, "setu-round-name"), cap, spacing=6, cls="setu-act")

    def actions(self, d, a):
        """What you can do: the main action, the sound output for audio, then
        Remove in red (d d asks first). White is the one Enter does when it
        isn't a disconnect."""
        g = d["group"]
        rem = (DELETE, "Remove", "d d", lambda: self.remove(d), "danger")
        if g == "Connected":
            acts = []
            if a:
                acts.append((VOLUME, "Sound output", "Space v o", lambda: self.output(d), "on" if a["default"] else ""))
            acts += [(LINK_OFF, "Disconnect", "Enter", lambda: self.act(d), ""), rem]
        elif g == "Paired":
            acts = [(LINK, "Connect", "Enter", lambda: self.act(d), "primary"), rem]
        else:
            acts = [(LINK, "Pair & connect", "Enter", lambda: self.act(d), "primary"),
                    (BT, "Pair only", "Space a p", lambda: self.pair(d, False), "")]
        row = Gtk.Box(spacing=26, halign=Gtk.Align.CENTER)
        for glyph, text, keys, cb, kind in acts:
            row.append(self.round_action(glyph, text, keys, cb, kind))
        return row

    # ------------------------------------------------------------ actions
    def act(self, d):
        mac, name, g = d["mac"], d["name"], d["group"]
        if g == "Nearby":
            self.pair(d, True)
            return
        self.errors.pop(mac, None)
        if g == "Connected":
            self.busy[mac] = "Disconnecting…"
            work = lambda: util.run_full(["bluetoothctl", "disconnect", mac], timeout=15)
        else:
            self.busy[mac] = "Connecting…"
            work = lambda: bluez.connect(mac)
        self.set_status(f"{self.busy[mac].lower()[:-1]} {name}…")
        self.refresh_keep()

        def done(r):
            self.busy.pop(mac, None)
            if isinstance(r, tuple) and len(r) == 2:      # bluez.connect: (ok, text)
                ok, text, code = r[0], r[1], 0
            else:
                code, out, err = r if isinstance(r, tuple) else (1, "", str(r))
                text = f"{out}\n{err}"
                ok = code == 0 and "Failed" not in text
            if ok:
                self.set_status("")
                self.unreach.pop(mac, None)
                if g != "Connected":
                    self.seen[mac] = time.time()
                    util.save_state("setu-last-connected", self.seen)
            else:
                self.errors[mac] = bluez.explain(text if text.strip() else "timed out")
                if bluez.unreachable(text) or code == 127:
                    self.unreach[mac] = time.time()
                self.set_status(f"{name}: {self.errors[mac]}")
            self.refresh_keep()
        self.background(work, done)

    def refresh_keep(self):
        if self.panel:
            self.panel.refresh_now(keep_selection=True)

    def remove(self, d):
        """Asks first (y removes, any other key keeps it): it has to be paired again to use it."""
        def go():
            self.set_status(f"removing {d['name']}…")
            self.background(lambda: bluez.bt("remove", d["mac"]), lambda _r: (self.set_status(""), self.refresh()))
        self.confirm(f"Remove {d['name']}? You'll have to pair it again to use it.", go)

    def output(self, d):
        a = self.audio.get(d["mac"].upper())
        if not a:
            self.set_status("Not a sound device (or pactl isn't installed)")
            return
        if a["default"]:
            self.set_status(f"{d['name']} is already the sound output")
            return
        self.set_status(f"sound goes to {d['name']}…")

        def work():
            if not a["sink"] and a["music"]:
                audio.set_profile(a["card"], a["music"])
                for _ in range(10):
                    time.sleep(0.3)
                    sink = (audio.state().get(d["mac"].upper()) or {}).get("sink")
                    if sink:
                        return audio.set_output(sink)
                return (1, "")
            return audio.set_output(a["sink"]) if a["sink"] else (1, "")
        self.background(work, lambda r: (self.set_status("" if isinstance(r, tuple) and r[0] == 0
                                                         else "couldn't switch the sound output"),
                                          self.refresh_keep()))

    def set_mode(self, d, mode):
        a = self.audio.get(d["mac"].upper())
        if not a or not a.get(mode) or a["mode"] == mode:
            return
        self.set_status("switching to calls with the mic…" if mode == "calls" else "switching to music…")
        self.background(lambda: audio.set_profile(a["card"], a[mode]),
                        lambda r: (self.set_status("" if isinstance(r, tuple) and r[0] == 0
                                                   else "couldn't switch: the device may not allow it"),
                                   self.refresh_keep()))

    # ------------------------------------------------------------ pairing
    def pair(self, d, connect):
        if d.get("Paired") == "yes" and not connect:
            self.set_status(f"{d['name']} is already paired")
            return
        if self.session is not None:
            return
        self.errors.pop(d["mac"], None)
        self.session = Session(d["mac"], d["name"], d.get("Icon", ""), connect, self.session_changed)
        self.session.dev = d
        self.show_preview(False)
        self.session.start()
        self.panel.refresh_strip() if self.panel else None
        self.refresh()
        self.sync_header()
        GLib.timeout_add_seconds(1, self.tick)

    def show_preview(self, on):
        box = self.panel.preview_box if self.panel else None
        sw = box.get_ancestor(Gtk.ScrolledWindow) if box is not None else None
        if sw is not None:
            sw.set_visible(on)

    def tick(self):
        s = self.session
        if s is None:
            return False
        if s.state in ("confirm", "authorize"):
            self.set_status(f"times out in {s.left()} s")
        elif s.state == "display":
            self.set_status(f"times out in {s.left()} s")
        elif s.state in ("pairing", "connecting"):
            self.set_status("")
        return not s.finished

    def session_changed(self, s):
        if s is not self.session:
            return
        if self.panel:
            self.panel.refresh_strip()
        if s.state == "done":
            self.set_status("")
            self.seen[s.mac] = time.time()
            util.save_state("setu-last-connected", self.seen)
            util.notify("Bluetooth", f"{s.name}: {'connected' if s.connect else 'paired'}", icon="bluetooth")
            GLib.timeout_add(1400, lambda: (self.end_session(s), False)[1])
        elif s.state == "cancelled":
            self.set_status("")
            GLib.timeout_add(500, lambda: (self.end_session(s), False)[1])
        elif s.state == "failed":
            self.set_status("")
        self.tick()

    def end_session(self, s=None):
        if s is not None and s is not self.session:
            return
        if self.session is not None:
            if self.session.state == "failed":
                self.errors[self.session.mac] = self.session.error
            self.session.stop()
        self.session = None
        self.set_status("")
        self.sync_header()        # the preview comes back with the list (build_strip)
        self.refresh_keep()

    def pairing_card(self):
        s = self.session
        d = getattr(s, "dev", {})
        kind = bluez.kind(d).lower()
        steps = [("Found", "done")]
        if s.state in ("confirm", "authorize", "display"):
            steps += [("Confirm code" if s.code else "Allow", "now"), ("Connect" if s.connect else "Trust", "todo")]
        elif s.state == "pairing":
            steps += [("Pair", "now"), ("Connect" if s.connect else "Trust", "todo")]
        elif s.state == "connecting":
            steps += [("Pair", "done"), ("Connect", "now")]
        elif s.state == "done":
            steps += [("Pair", "done"), ("Connect" if s.connect else "Trust", "done")]
        else:
            steps += [("Pair", "todo")]
        title = {"confirm": f"Pair with {s.name}?", "authorize": f"Pair with {s.name}?",
                 "display": f"Type this code on {s.name}", "pairing": f"Pairing with {s.name}…",
                 "connecting": f"Connecting to {s.name}…", "done": f"{s.name} is ready",
                 "failed": f"Couldn't pair with {s.name}", "cancelled": "Pairing cancelled"}[s.state]
        note = {"confirm": f"Check that the {kind} shows the same code.",
                "authorize": f"The {kind} wants to pair with this computer.",
                "display": "Type it on the device, then press Enter on it.",
                "pairing": "Keep it in pairing mode and close by.",
                "connecting": "Paired and trusted: it will reconnect by itself from now on.",
                "done": "Connected." if s.connect else "Paired and trusted.",
                "failed": "", "cancelled": ""}[s.state]
        parts = [ui.tile(icon_of(d), "blue", 30, "setu-pair-tile"),
                 ui.label(title, "setu-pair-title", wrap=True, justify=Gtk.Justification.CENTER)]
        if note:
            parts.append(ui.label(note, "setu-pair-note", wrap=True, justify=Gtk.Justification.CENTER))
        if s.code and s.state in ("confirm", "display"):
            code = s.code if len(s.code) != 6 else f"{s.code[:3]} {s.code[3:]}"
            parts.append(ui.label(code, "setu-code"))
        st = ui.steps(steps)
        st.set_halign(Gtk.Align.CENTER)
        parts.append(st)
        if s.state == "failed":
            parts.append(ui.notice("What went wrong", s.error, "red"))
            btns = [("Try again", self.retry, "primary", "", "Enter"), ("Back", lambda: self.end_session(), "", "", "Esc")]
        elif s.state in ("confirm", "authorize"):
            btns = [("They match" if s.code else "Allow", lambda: s.answer(True), "primary", CHECK, "Enter"),
                    ("Cancel", lambda: s.answer(False), "", CLOSE, "Esc")]
        elif s.state in ("done", "cancelled"):
            btns = []
        else:
            btns = [("Cancel", s.cancel, "", CLOSE, "Esc")]
        if btns:
            b = ui.buttons(btns)
            b.set_halign(Gtk.Align.CENTER)
            parts.append(b)
        card = ui.vbox(*parts, spacing=10, cls="setu-pair")
        card.add_css_class({"failed": "setu-pair-red", "done": "setu-pair-green"}.get(s.state, "setu-pair-yellow"))
        card.set_halign(Gtk.Align.CENTER)
        for p in parts:
            if not p.has_css_class("notice"):
                p.set_halign(Gtk.Align.CENTER)
        return card

    def retry(self):
        s = self.session
        if s is None:
            return
        d, connect = s.dev, s.connect
        self.session = None
        s.stop()
        self.pair(d, connect)

    # ------------------------------------------------------------ keys
    def activate(self, row, mods):
        d = row.data or {}
        if d.get("kind") == "dev":
            self.act(d)
        return False

    def key(self, name, row, mods):
        s = self.session
        if s is not None:
            if name in ("Return", "KP_Enter"):
                if s.state in ("confirm", "authorize"):
                    s.answer(True)
                elif s.state == "failed":
                    self.retry()
                elif s.state == "done":
                    self.end_session()
                return True
            if name == "Escape":
                if s.state in ("confirm", "authorize"):
                    s.answer(False)
                elif s.finished:
                    self.end_session()
                else:
                    s.cancel()
                return True
            return True      # nothing else while pairing (the card says Enter / Esc)
        if name in ("Return", "KP_Enter") and self.adapter.get("state") == "off":
            self.power(True)
            return True
        if name in ("Return", "KP_Enter") and self.adapter.get("state") in ("stuck", "none"):
            self.reset()
            return True
        return False

    # ------------------------------------------------------------ vim keys
    def keys(self, tab):
        return vim.keys(tab)

    def device(self, paired=False):
        """The selected device's data, or None (with a word why)."""
        row = self.panel.selected_row() if self.panel else None
        d = (row.data or {}) if row else {}
        if d.get("kind") != "dev":
            self.set_status("no device selected", "bad")
            return None
        if paired and d.get("group") == "Nearby":
            self.set_status(f"{d['name']} isn't paired", "bad")
            return None
        return d

    def v_power(self, _n, _a):
        st = self.adapter.get("state")
        if st in ("ok", "off"):
            self.power(st == "off")
        else:
            self.set_status("no Bluetooth adapter to turn on", "bad")

    def v_pair(self, _n, how):
        if (d := self.device()):
            self.pair(d, how == "connect")

    def v_conn(self, _n, want):
        if not (d := self.device()):
            return
        on = d.get("group") == "Connected"
        if (want == "on") == on:
            self.set_status(f"{d['name']} is already {'connected' if on else 'disconnected'}")
            return
        self.act(d)

    def v_output(self, _n, _a):
        if (d := self.device(paired=True)):
            self.output(d)

    def v_audiomode(self, _n, mode):
        if not (d := self.device(paired=True)):
            return
        a = self.audio.get(d["mac"].upper())
        if not a or not (a.get("music") and a.get("calls")):
            self.set_status(f"{d['name']} has no music / calls modes (or isn't connected)", "bad")
            return
        self.set_mode(d, mode)

    def v_unnamed(self, _n, _a):
        self.show_unnamed = not self.show_unnamed
        self.set_status("showing unnamed devices" if self.show_unnamed else "unnamed devices hidden", "ok")
        self.refresh_keep()

    def v_copy(self, _n, _a):
        if (d := self.device()):
            util.copy(d["mac"])
            self.set_status(f"copied {d['mac']}", "ok")

    def v_remove(self, _n, _a):
        if (d := self.device(paired=True)):
            self.remove(d)

    def v_refresh(self, _n, _a):
        self.start_scan()
        self.refresh_keep()
