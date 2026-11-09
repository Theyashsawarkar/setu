"""Earbuds' batteries, left / right / case, from Google Fast Pair.

BlueZ gives a device one battery level. Fast Pair earbuds (Pixel Buds,
OnePlus, Sony, JBL, Nothing, Realme…) say more in their Bluetooth LE
advertisements (service data 0xFE2C): each bud and the case, with a
"charging" flag. setu only listens: an LE scan while the panel is open,
nothing is ever sent to the buds.

The advertisement (after the first byte, version and flags) is a run of
fields, each a byte whose high nibble is the length and low nibble the
type, then that many bytes. Type 3 or 4 (battery, shown / hidden in the
phone's UI) holds three bytes: left, right, case; bit 7 is "charging",
bits 0-6 the level (0-100, 0x7F unknown). A 3-byte advertisement is the
discoverable form (just the model ID): no battery.

parse() is pure (no GTK, no D-Bus) so it's tested; Scanner talks to BlueZ
over D-Bus and runs in a worker thread.
"""
import json
import logging
import os
import time

log = logging.getLogger("vyom.setu")

FAST_PAIR = "0000fe2c-0000-1000-8000-00805f9b34fb"
PARTS = ("left", "right", "case")
STALE = 120          # seconds without a new advertisement: shown as "as of …"


def part(byte):
    """{"level": 0-100 or None, "charging": bool} from one battery byte."""
    level = byte & 0x7F
    if level == 0x7F or level > 100:
        return {"level": None, "charging": False}
    return {"level": level, "charging": bool(byte & 0x80)}


def parse(data):
    """{"left": part, "right": part, "case": part} from Fast Pair service
    data, or None when it carries no battery (discoverable form, other
    fields only, too short, malformed)."""
    data = bytes(data or b"")
    if len(data) <= 3:              # the discoverable form: a model ID only
        return None
    i = 1                           # byte 0: version and flags
    while i < len(data):
        head = data[i]
        n, kind = head >> 4, head & 0x0F
        body = data[i + 1:i + 1 + n]
        if len(body) < n:           # cut short: nothing more to trust
            return None
        if kind in (3, 4) and n >= 3:
            parts = {name: part(b) for name, b in zip(PARTS, body[:3])}
            if all(p["level"] is None for p in parts.values()):
                return None
            return parts
        i += 1 + n
    return None


def compact(parts):
    """"L 100 · R 90 · case 40", the charging ones with ⚡; unknowns left out."""
    out = []
    for name, short in (("left", "L"), ("right", "R"), ("case", "case")):
        p = parts.get(name) or {}
        if p.get("level") is not None:
            out.append(f"{short} {p['level']}" + ("⚡" if p.get("charging") else ""))
    return " · ".join(out)


class Scanner:
    """An LE scan of our own (Transport le, every advertisement reported)
    while the panel is open, and what Fast Pair devices last said, by name.
    BlueZ keeps one discovery per D-Bus client, so this one adds to (never
    replaces) bluetoothctl's `scan on`, and stop() ends only ours."""

    def __init__(self):
        self.bus = None
        self.on = False
        self.last = {}       # object path -> (rssi, data hex): to tell when it was heard again
        self.heard = {}      # object path -> when its advertisement last changed
        self.readings = {}   # name -> {"parts": ..., "at": time, "path": object path, "address": ...}

    def _bus(self):
        if self.bus is None:
            from gi.repository import Gio
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        return self.bus

    def _call(self, path, iface, method, args=None):
        return self._bus().call_sync("org.bluez", path, iface, method, args, None, 0, 4000, None)

    def adapter(self):
        objs = self._call("/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects").unpack()[0]
        for path, ifs in objs.items():
            if "org.bluez.Adapter1" in ifs and ifs["org.bluez.Adapter1"].get("Powered"):
                return path, objs
        return None, objs

    def fake(self):
        """Tests and screenshots: SETU_FASTPAIR_FAKE names a JSON file of
        {"device name": "service data hex"}; no D-Bus, no scan."""
        path = os.environ.get("SETU_FASTPAIR_FAKE")
        if not path:
            return None
        try:
            with open(path) as f:
                return {k: bytes.fromhex(v) for k, v in json.load(f).items()}
        except (OSError, ValueError):
            return {}

    def start(self):
        """Begin listening (idempotent). Any failure: no per-part battery,
        the rest of setu carries on."""
        if self.on or self.fake() is not None:
            return
        try:
            from gi.repository import GLib
            path, _ = self.adapter()
            if not path:
                return
            self._call(path, "org.bluez.Adapter1", "SetDiscoveryFilter",
                       GLib.Variant("(a{sv})", ({"Transport": GLib.Variant("s", "le"),
                                                 "DuplicateData": GLib.Variant("b", True)},)))
            self._call(path, "org.bluez.Adapter1", "StartDiscovery")
            self.on, self.path = True, path
        except Exception:     # noqa: BLE001  (no BlueZ on D-Bus, already discovering…)
            self.on = False

    def stop(self):
        if not self.on:
            return
        self.on = False
        try:
            self._call(self.path, "org.bluez.Adapter1", "StopDiscovery")
        except Exception as e:     # noqa: BLE001  (Bluetooth went off meanwhile: nothing to stop)
            log.debug("StopDiscovery: %s", e)

    def read(self, now=None):
        """Look at what BlueZ heard; update and return self.readings."""
        now = now or time.time()
        fake = self.fake()
        if fake is not None:
            for name, data in fake.items():
                parts = parse(data)
                if parts:
                    self.readings[name] = {"parts": parts, "at": now, "path": "", "address": ""}
            return self.readings
        try:
            _, objs = self.adapter()
        except Exception:     # noqa: BLE001
            return self.readings
        for path, ifs in objs.items():
            d = ifs.get("org.bluez.Device1")
            if not d:
                continue
            raw = (d.get("ServiceData") or {}).get(FAST_PAIR)
            name = d.get("Name") or d.get("Alias")
            if raw is None or not name:
                continue
            data = bytes(raw)
            key = (d.get("RSSI"), data.hex())
            if self.last.get(path) != key:          # heard again (RSSI or data moved)
                self.last[path] = key
                self.heard[path] = now
            parts = parse(data)
            if parts is None:
                continue
            at = self.heard.get(path, now)
            old = self.readings.get(name)
            if old is None or at >= old["at"]:
                self.readings[name] = {"parts": parts, "at": at, "path": path, "address": d.get("Address", "")}
        return self.readings
