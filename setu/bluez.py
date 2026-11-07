"""BlueZ through bluetoothctl: the adapter, the devices, and plain-words
errors. Everything here runs in a worker thread (never touches widgets)."""
import re
import shutil
from concurrent.futures import ThreadPoolExecutor

from vyom import util

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
MAC = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")


def have():
    return shutil.which("bluetoothctl") is not None


def bt(*args, timeout=10):
    return util.run(["bluetoothctl", *args], timeout=timeout)


def props(text):
    """`Key: value` lines of bluetoothctl show/info as a dict (repeated keys,
    like UUID, keep the first)."""
    d = {}
    for line in ANSI.sub("", text).splitlines():
        line = line.strip()
        if ":" in line and not line.startswith(("Controller ", "Device ")):
            k, v = line.split(":", 1)
            d.setdefault(k.strip(), v.strip())
    return d


def number(v):
    """`0x4e (78)` -> 78; None when there's none."""
    m = re.search(r"\((-?\d+)\)", v or "")
    return int(m.group(1)) if m else None


def adapter():
    """The adapter's state: {"state": "ok"|"off"|"none"|"nodaemon"|"missing",
    "alias", "discoverable", "discovering"}."""
    if not have():
        return {"state": "missing"}
    code, out = bt("show", timeout=4)
    if code == 127 or "Waiting to connect to bluetoothd" in out and "Controller" not in out:
        return {"state": "nodaemon"}
    if "Controller" not in out:
        return {"state": "none"}
    p = props(out)
    return {"state": "ok" if p.get("Powered") == "yes" else "off",
            "alias": p.get("Alias") or p.get("Name") or "this computer",
            "discoverable": p.get("Discoverable") == "yes",
            "discovering": p.get("Discovering") == "yes",
            "blocked": p.get("PowerState") == "off-blocked"}


def info(mac):
    _, out = bt("info", mac, timeout=4)
    d = props(out)
    d["mac"] = mac
    d["battery"] = number(d.get("Battery Percentage"))
    d["rssi"] = number(d.get("RSSI"))
    return d


def unnamed(mac, name):
    return not name or name.replace("-", ":").upper() == mac.upper()


def listed(*filt):
    _, out = bt("devices", *filt, timeout=4)
    found = []
    for line in ANSI.sub("", out).splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2 and parts[0] == "Device" and MAC.match(parts[1]):
            found.append((parts[1], parts[2] if len(parts) > 2 else ""))
    return found


def devices(with_unnamed=False):
    """(devices, number of unnamed ones left out). Unnamed devices (beacons,
    nameless BLE gadgets) aren't even asked about unless they're wanted (or
    paired: a paired device always shows)."""
    paired = {m for m, _ in listed("Paired")}
    macs, hidden = [], 0
    for mac, name in listed():
        if unnamed(mac, name) and not with_unnamed and mac not in paired:
            hidden += 1
        else:
            macs.append(mac)
    with ThreadPoolExecutor(8) as ex:
        return list(ex.map(info, macs)), hidden


def kind(d):
    """What the device is, in a word ("Headphones", "Mouse")."""
    icon = d.get("Icon", "")
    return {"audio-headset": "Headset", "audio-headphones": "Headphones", "audio-card": "Speaker",
            "input-mouse": "Mouse", "input-keyboard": "Keyboard", "input-gaming": "Game controller",
            "input-tablet": "Tablet", "phone": "Phone", "computer": "Computer", "video-display": "Display",
            "camera-video": "Camera", "printer": "Printer", "multimedia-player": "Player",
            "audio-input-microphone": "Microphone"}.get(icon, "Device")


def is_audio(d):
    return d.get("Icon", "").startswith(("audio-", "multimedia")) or any(
        u in str(d.get("UUID", "")) for u in ("Audio Sink", "Headset", "Handsfree"))


# bluetoothctl errors, said plainly: what went wrong and what to do.
ERRORS = [
    ("AuthenticationFailed", "The codes didn't match, or the device said no: try again."),
    ("AuthenticationRejected", "The device said no: accept the pairing on it and try again."),
    ("AuthenticationCanceled", "Pairing was cancelled."),
    ("AuthenticationTimeout", "Device didn't answer: put it in pairing mode and try again."),
    ("ConnectionAttemptFailed", "Device didn't answer: put it in pairing mode and try again."),
    ("page-timeout", "Device didn't answer: is it on and close by?"),
    ("not available", "Device is gone: it stopped being visible. Put it in pairing mode."),
    ("AlreadyConnected", "It's already connected."),
    ("InProgress", "Already busy with this device: wait a moment and try again."),
    ("NotReady", "Bluetooth isn't ready: turn it on with Ctrl+B."),
    ("profile-unavailable", "Connected, but there's nothing to use: the device may need to be paired again."),
    ("abort-by-local", "Connecting was stopped on this computer."),
    ("abort-by-remote", "The device hung up: it may be connected to something else."),
    ("Canceled", "Cancelled."),
    ("timed out", "Device didn't answer in time: is it on and close by?"),
]


def explain(text):
    t = ANSI.sub("", text or "")
    for key, words in ERRORS:
        if key.lower() in t.lower():
            return words
    m = re.search(r"Failed to \w+: (\S+)", t)
    return f"It didn't work ({m.group(1).split('.')[-1]})." if m else "It didn't work: is the device on and close by?"


def unreachable(text):
    t = (text or "").lower()
    return any(k in t for k in ("page-timeout", "not available", "host is down", "timed out", "connectionattemptfailed"))


def upower_batteries():
    """{MAC: [(label, percent)]} for devices UPower reports more than one
    battery for (earbuds left / right / case, a keyboard with a dock...).
    BlueZ itself has one battery per device, so most devices aren't here:
    only what's really reported shows."""
    if not shutil.which("upower"):
        return {}
    code, out = util.run(["upower", "-d"], timeout=4)
    if code != 0:
        return {}
    found = {}
    for block in out.split("\n\n"):
        mac = None
        m = re.search(r"([0-9A-Fa-f]{2}[:_]){5}[0-9A-Fa-f]{2}", block)
        if m and ("native-path" in block or "serial" in block):
            mac = m.group(0).replace("_", ":").upper()
        pct = re.search(r"percentage:\s*([\d.]+)%", block)
        if not mac or not pct:
            continue
        kind = ""
        for line in block.splitlines():
            s = line.strip()
            if s and ":" not in s and not s.startswith("Device"):
                kind = s
        model = re.search(r"model:\s*(.+)", block)
        found.setdefault(mac, []).append([kind, model.group(1).strip() if model else "", int(float(pct.group(1)))])
    out = {}
    for mac, items in found.items():
        if len(items) < 2:
            continue
        kinds = [k for k, _, _ in items]
        labels = []
        for k, model, _ in items:
            lab = k if kinds.count(k) == 1 else f"{k} {model}"
            labels.append((lab or model or "Battery").strip().capitalize())
        out[mac] = [(lab, p) for lab, (_, _, p) in zip(labels, items)]
    return out
