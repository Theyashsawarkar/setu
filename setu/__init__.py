"""setu (सेतु, "bridge"): Bluetooth for Vyom, through BlueZ (bluetoothctl).

Your devices, connected first, with their battery levels; while the
panel is open it discovers nearby ones too. Enter connects or
disconnects; a nearby device pairs, trusts and connects in one go.
"""
import re
import subprocess

from gi.repository import GLib, Gtk

from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

# keybind: Vyom/bluetooth | Enter | Connect or disconnect the selected device (pairs a new one)
# keybind: Vyom/bluetooth | Ctrl+P | Pair and trust the selected device
# keybind: Vyom/bluetooth | Ctrl+Backspace | Remove (unpair) the selected device
# keybind: Vyom/bluetooth | Ctrl+B | Turn Bluetooth on or off

ICONS = {"audio-headset": "\U000f02cb", "audio-headphones": "\U000f02cb", "audio-card": "\U000f04c3",
         "input-mouse": "\U000f037d", "input-keyboard": "\U000f030c", "input-gaming": "\U000f0297",
         "phone": "\U000f011c", "computer": "\U000f0322", "input-tablet": "\U000f04f7"}


def bt(*args, timeout=10):
    return util.run(["bluetoothctl", *args], timeout=timeout)


def info(mac):
    _, out = bt("info", mac)
    d = {"mac": mac}
    for line in out.splitlines():
        if ":" in line:
            k, v = line.strip().split(":", 1)
            d[k.strip()] = v.strip()
    m = re.search(r"\((\d+)\)", d.get("Battery Percentage", ""))
    d["battery"] = int(m.group(1)) if m else None
    return d


class Plugin(Base):
    name, title, icon, color = "setu", "Bluetooth", "\U000f00af", "blue"
    placeholder = "Filter devices…"
    preview = True
    preview_width = 280
    live = 3
    hints = [Hint("↵", "connect / disconnect"), Hint("⌃P", "pair"), Hint("⌃⌫", "remove"), Hint("⌃B", "on/off")]
    empty_text = "No devices yet: nearby ones show up as they're found"

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.scan = None
        self.switch = None

    def available(self):
        return ("Controller" in bt("show")[1], "no Bluetooth controller")

    def header_extra(self):
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.set_can_focus(False)
        self.switch.set_tooltip_text("Bluetooth on/off (Ctrl+B)")
        self.handler = self.switch.connect("state-set", lambda _s, on: (self.power(on), False)[1])
        return self.switch

    def powered(self):
        return "Powered: yes" in bt("show")[1]

    def power(self, on):
        self.background(lambda: bt("power", "on" if on else "off"), lambda _r: self.refresh())

    def opened(self, args):
        super().opened(args)
        self.start_scan()

    def closed(self):
        if self.scan and self.scan.poll() is None:
            self.scan.terminate()
        self.scan = None
        util.spawn(["bluetoothctl", "scan", "off"])

    def start_scan(self):
        if self.scan is None or self.scan.poll() is not None:
            try:
                self.scan = subprocess.Popen(["bluetoothctl", "--timeout", "60", "scan", "on"],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                self.scan = None

    def search(self, q):
        on = self.powered()
        GLib.idle_add(self.sync_switch, on)
        if not on:
            return [Row("Bluetooth is off", "Ctrl+B or the switch turns it on", icon="\U000f00b2", color="red",
                        data={"kind": "off"})]
        _, out = bt("devices")
        devs = [info(l.split()[1]) for l in out.splitlines() if l.startswith("Device ")]
        groups = {"Connected": [], "Paired": [], "Nearby": []}
        for d in devs:
            name = d.get("Name") or d.get("Alias") or d["mac"]
            if q and util.fuzzy(q, name) is None:
                continue
            g = "Connected" if d.get("Connected") == "yes" else "Paired" if d.get("Paired") == "yes" else "Nearby"
            if g == "Nearby" and name.replace("-", ":") == d["mac"].replace("-", ":"):
                continue  # nameless beacons: noise
            groups[g].append(self.row(d, name, g))
        rows = []
        for title, items in groups.items():
            if items:
                rows.append(Section(title))
                rows += items
        return rows

    def row(self, d, name, group):
        icon = ICONS.get(d.get("Icon", ""), "\U000f00af")
        kind = (d.get("Icon") or "device").replace("audio-", "").replace("input-", "")
        sub = {"Connected": "Connected", "Paired": "Paired · Enter connects", "Nearby": "Enter pairs"}[group]
        meta = f"\U000f0079 {d['battery']}%" if d["battery"] is not None else ""
        return Row(name, f"{sub} · {kind}", icon=icon, color="blue" if group == "Connected" else "gray",
                   meta=meta, data={"kind": "dev", "group": group, "name": name, **d})

    def build_preview(self, row):
        d = row.data or {}
        if d.get("kind") != "dev":
            return None
        parts = [ui.hbox(ui.label(ICONS.get(d.get("Icon", ""), "\U000f00af"), "setu-big"),
                         ui.vbox(ui.title(d["name"]), ui.meta(d["group"]), spacing=2), spacing=12)]
        if d["battery"] is not None:
            parts.append(ui.vbox(ui.meta(f"Battery {d['battery']}%"), ui.progress(d["battery"] / 100), spacing=4))
        parts.append(ui.kv([("Address", d["mac"]), ("Paired", d.get("Paired", "no")),
                            ("Trusted", d.get("Trusted", "no")), ("Type", d.get("Icon", "unknown"))]))
        btns = []
        if d["group"] == "Connected":
            btns.append(("Disconnect", lambda: self.act(d), "danger"))
        elif d["group"] == "Paired":
            btns.append(("Connect", lambda: self.act(d), "primary"))
        else:
            btns.append(("Pair & connect", lambda: self.act(d), "primary"))
        if d["group"] != "Nearby":
            btns.append(("Remove", lambda: self.remove(d)))
        parts.append(ui.buttons(btns))
        return ui.vbox(*parts, spacing=12)

    def act(self, d):
        mac, name = d["mac"], d["name"]
        if d["group"] == "Connected":
            self.set_status(f"disconnecting {name}…")
            work = lambda: bt("disconnect", mac)
        elif d["group"] == "Paired":
            self.set_status(f"connecting {name}…")
            work = lambda: bt("connect", mac, timeout=25)
        else:
            self.set_status(f"pairing {name}…")
            def work():
                r = bt("pair", mac, timeout=30)
                bt("trust", mac)
                return bt("connect", mac, timeout=25) if r[0] == 0 else r

        def done(r):
            code = r[0] if isinstance(r, tuple) else 1
            self.set_status("" if code == 0 else f"{name}: didn't work (is it in pairing mode?)")
            if code == 0:
                util.notify("Bluetooth", f"{name}: done", icon="bluetooth")
            self.refresh()
        self.background(work, done)

    def remove(self, d):
        self.background(lambda: bt("remove", d["mac"]), lambda _r: self.refresh())

    def activate(self, row, mods):
        d = row.data or {}
        if d.get("kind") == "off":
            self.power(True)
        elif d.get("kind") == "dev":
            self.act(d)
        return False

    def sync_switch(self, on):
        if self.switch is not None and self.switch.get_active() != on:
            self.switch.handler_block(self.handler)
            self.switch.set_active(on)
            self.switch.handler_unblock(self.handler)
        return False

    def key(self, name, row, mods):
        if "ctrl" not in mods:
            return False
        d = (row.data or {}) if row else {}
        if name == "b":
            self.power(not self.powered())
        elif name == "p" and d.get("kind") == "dev":
            self.background(lambda: (bt("pair", d["mac"], timeout=30), bt("trust", d["mac"])), lambda _r: self.refresh())
        elif name == "BackSpace" and d.get("kind") == "dev":
            self.remove(d)
        else:
            return False
        return True
