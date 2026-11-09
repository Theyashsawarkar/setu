"""setu (सेतु, "bridge"): Bluetooth for Vyom, through BlueZ (bluetoothctl).

Connected devices are cards at the top, each with its battery ring and,
for headphones and speakers, what they're doing (music in high quality or
calls with the mic). Below: paired devices that aren't connected, and the
devices nearby (found while the panel is open), closest first. Pairing is
a step of its own: the 6-digit code shown big, to compare with the device.
"""
import subprocess
import time

from gi.repository import GLib, Gtk, Pango

from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

from . import vim

from . import audio, bluez
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


def icon_of(d):
    return ICONS.get(d.get("Icon", ""), BT)


def charge(p):
    """(colour, words) for a battery level: red under 10%, yellow under 20%."""
    if p < 10:
        return "red", "plug it in"
    if p < 20:
        return "yellow", "charge soon"
    return "green", ""


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
    preview_width = 290
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
        self.session = None
        self.errors = {}          # mac -> what went wrong last time, in words
        self.unreach = {}         # mac -> when it last couldn't be reached
        self.busy = {}            # mac -> "Connecting…" while an action runs
        self.cards = {}
        self.seen = util.load_state("setu-last-connected", {})
        self.seen_saved = 0.0

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
                if a.get("discoverable"):
                    self.chipbox.append(ui.chip(f"Visible as {a['alias']}", "gray", EYE))
                else:
                    c = ui.chip(f"Named {a['alias']} · hidden", "gray", EYE_OFF)
                    c.set_tooltip_text("Other devices can't find this computer by searching, "
                                       "but pairing from here works")
                    self.chipbox.append(c)
                if a.get("discovering"):
                    dot = ui.label("●", "setu-pulse")
                    scan = ui.hbox(dot, ui.label("Looking for devices"), spacing=6, cls="chip")
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

    def closed(self):
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
        if self.adapter.get("blocked") and on:
            self.set_status("Bluetooth is blocked: rfkill unblock bluetooth (or the airplane-mode key)")
            return
        self.set_status("turning Bluetooth on…" if on else "turning Bluetooth off…")
        self.background(lambda: bluez.bt("power", "on" if on else "off"),
                        lambda _r: (self.set_status(""), self.refresh()))

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
        rows = [self.row(d) for d in conn]          # shown as cards in the strip
        if paired:
            rows.append(Section("Paired, not connected", len(paired), "Enter connects"))
            rows += [self.row(d) for d in paired]
        if self.hidden:
            note = f"closest first · Ctrl+U shows {self.hidden} unnamed"
        elif self.show_unnamed:
            note = "closest first · Ctrl+U hides unnamed"
        else:
            note = "closest first"
        if near or (not q and (self.hidden or self.show_unnamed)):
            rows.append(Section("Nearby", len(near), note))
            rows += [self.row(d) for d in near]
        self.empty_text = "" if conn else ("Nothing here yet: nearby devices show up as they're found"
                                           if not q else "No device matches")
        return rows

    def batteries(self, d):
        """[(label, percent)]: UPower's separate ones (left, right, case) when
        it reports several, else BlueZ's one, else none."""
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
        return Row(d["name"], kind, icon=icon_of(d), color="blue", data={"kind": "dev", **d})

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
        if st == "none":
            return self.trouble("No Bluetooth adapter found",
                                "Is it plugged in, or blocked? rfkill unblock bluetooth, or the airplane-mode key.",
                                "red")
        if st == "off":
            body = ui.vbox(ui.label("Bluetooth is off", "hero-title", xalign=0),
                           ui.label("Your devices can't connect until it's on.", "hero-sub", xalign=0), spacing=4)
            body.set_hexpand(True)
            return ui.hero(ui.tile(BT_OFF, "gray", 22, "tile"), body,
                           ui.button("Turn on", lambda: self.power(True), "primary", POWER, "Ctrl+B"),
                           color="gray")
        # Bluetooth is on: the connected devices as cards, two per row.
        items = self.panel.items if self.panel else []
        conn = [(i, r) for i, (r, w) in enumerate(items) if (r.data or {}).get("group") == "Connected"]
        for _i, (r, w) in enumerate(items):
            if (r.data or {}).get("group") == "Connected":
                w.set_visible(False)       # the card stands for it
        self.cards = {}
        if not conn:
            if self.panel and self.query():
                return None
            body = ui.vbox(ui.label("Nothing connected", "hero-title", xalign=0),
                           ui.label("Pick a device below and press Enter to connect it.", "hero-sub", xalign=0),
                           spacing=4)
            return ui.hero(ui.tile(BT, "blue", 22, "tile"), body, color="gray")
        grid = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        for n, (i, r) in enumerate(conn):
            card = self.card(r.data, i)
            grid.attach(card, n % 2, n // 2, 1, 1)
        if len(conn) == 1:
            grid.attach(Gtk.Box(), 1, 0, 1, 1)
        self.highlight()
        return ui.vbox(ui.section("Connected", len(conn), "Enter disconnects"), grid, spacing=6)

    def query(self):
        try:
            return self.panel.entry.get_text()
        except AttributeError:
            return ""

    def trouble(self, title, text, color):
        n = ui.notice(title, text, color)
        n.add_css_class("setu-trouble")
        return n

    def card(self, d, index):
        bats = self.batteries(d)
        glyph = ui.label(icon_of(d), "glyph", "setu-card-icon")
        if len(bats) == 1:
            p = bats[0][1]
            visual = ui.ring(p / 100, charge(p)[0], 58, 5, glyph)
        elif bats:
            rings = []
            for lab, p in bats:
                inner = ui.label(CASE if lab.lower() == "case" else (lab[:1] or "?"), "setu-mini")
                rings.append(ui.ring(p / 100, charge(p)[0], 40, 4, inner))
            visual = ui.hbox(*rings, spacing=4)
        else:
            visual = ui.tile(icon_of(d), "blue", 22, "setu-noring")
        lines = [ui.label(d["name"], "setu-card-name", xalign=0, ellipsize=Pango.EllipsizeMode.END)]
        if len(bats) == 1:
            p = bats[0][1]
            col, words = charge(p)
            lines.append(ui.label(f"{p}%" + (f" · {words}" if words else ""), f"t-{col}", "setu-card-line",
                                  xalign=0, ellipsize=Pango.EllipsizeMode.END))
        elif bats:
            ok = [f"{lab} {p}%" for lab, p in bats if charge(p)[0] == "green"]
            low = [(lab, p) for lab, p in bats if charge(p)[0] != "green"]
            if ok:
                lines.append(ui.label(" · ".join(ok), "setu-card-line", xalign=0, ellipsize=Pango.EllipsizeMode.END))
            for lab, p in low:
                col, words = charge(p)
                lines.append(ui.label(f"{lab} {p}% · {words}", f"t-{col}", "setu-card-line", xalign=0,
                                      ellipsize=Pango.EllipsizeMode.END))
        a = self.audio.get(d["mac"].upper())
        if a:
            what = ui.hbox(ui.label(VOLUME, "glyph", "t-peach" if a["default"] else "t-gray"),
                           ui.label(audio.doing(a), "setu-card-line", ellipsize=Pango.EllipsizeMode.END), spacing=5)
            lines.append(what)
        else:
            lines.append(ui.label(bluez.kind(d), "setu-card-line", "setu-quiet", xalign=0))
        text = ui.vbox(*lines[:3], spacing=2)
        text.set_hexpand(True)
        text.set_valign(Gtk.Align.CENTER)
        card = ui.hbox(visual, text, spacing=12, cls="setu-card")
        low = [p for _, p in bats if p < 10]
        if low:
            card.add_css_class("setu-card-low")
        click = Gtk.GestureClick()
        click.connect("pressed", lambda g, n, _x, _y, i=index: self.card_clicked(i, n))
        card.add_controller(click)
        self.cards[d["mac"]] = card
        return card

    def card_clicked(self, index, n):
        if self.panel:
            self.panel.select(index)
            if n == 2:
                self.panel.activate(index, set())

    def highlight(self):
        row = self.panel.selected_row() if self.panel else None
        mac = (row.data or {}).get("mac") if row else None
        for m, c in self.cards.items():
            if m == mac:
                c.add_css_class("setu-picked")
            else:
                c.remove_css_class("setu-picked")

    # ------------------------------------------------------------ the preview
    def build_preview(self, row):
        self.highlight()
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
        head = ui.hbox(ui.tile(icon_of(d), "blue", 26, "setu-big-tile"),
                       ui.vbox(ui.title(d["name"]), ui.chips(*chips), spacing=6), spacing=12)
        parts = [head]
        if mac in self.errors:
            parts.append(ui.notice("Didn't work", self.errors[mac], "red"))
        for lab, p in self.batteries(d):
            col, words = charge(p)
            parts.append(ui.meter(f"{lab} battery".strip().capitalize() if lab else "Battery",
                                  f"{p}%" + (f" · {words}" if words else ""), p / 100, col))
        if a:
            box = [ui.label("Audio", "meter-name", xalign=0)]
            if a["music"] and a["calls"]:
                cur = a["mode"] if a["mode"] in ("music", "calls") else ""
                box.append(ui.segmented([("music", "Music · high quality"), ("calls", "Calls · with mic")], cur,
                                        lambda k, d=d: self.set_mode(d, k)))
                box.append(ui.label("Space v m music · Space v c calls", "meter-name", xalign=0))
            else:
                box.append(ui.label(audio.doing(a), "p-body", xalign=0))
            parts.append(ui.soft(*box, spacing=8))
        kv = [("Type", bluez.kind(d))]
        if g != "Nearby":
            kv.append(("Trusted", "Yes · reconnects by itself" if d.get("Trusted") == "yes" else "No"))
        if g == "Paired" and mac in self.seen:
            kv.append(("Last connected", ago(self.seen[mac])))
        if g == "Nearby":
            lvl, word, _col = signal(d["rssi"])
            kv.append(("Signal", f"{word} · {d['rssi']} dBm" if lvl >= 0 else "Not heard just now"))
        kv.append(("Address", mac))
        parts.append(ui.kv(kv))
        parts.append(self.preview_buttons(d, a))
        return ui.vbox(*parts, spacing=12)

    def preview_buttons(self, d, a):
        g = d["group"]
        rows = []
        if g == "Connected":
            first = [("Disconnect", lambda: self.act(d), "", LINK_OFF, "Enter")]
            if a and not a["default"]:
                rows.append(ui.buttons([("Make sound output", lambda: self.output(d), "", VOLUME, "Space v o")]))
        elif g == "Paired":
            first = [("Connect", lambda: self.act(d), "primary", LINK, "Enter")]
        else:
            first = [("Pair & connect", lambda: self.act(d), "primary", LINK, "Enter")]
            rows.append(ui.buttons(first))
            rows.append(ui.buttons([("Pair only", lambda: self.pair(d, False), "", "", "Space a p")]))
            return ui.vbox(*rows, spacing=8)
        rem = ("Remove", lambda: self.remove(d), "danger", DELETE, "d d")
        rows.insert(0, ui.buttons(first))
        rows.append(ui.buttons([rem]))
        return ui.vbox(*rows, spacing=8)

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
            work = lambda: util.run_full(["bluetoothctl", "connect", mac], timeout=25)
        self.set_status(f"{self.busy[mac].lower()[:-1]} {name}…")
        self.refresh_keep()

        def done(r):
            self.busy.pop(mac, None)
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
