"""Sound for Bluetooth audio devices through pactl (PipeWire's pipewire-pulse
or PulseAudio): what a device is doing (music in high quality, or calls
with the mic), switching between the two, and making it the sound output.
Without pactl the rest of setu works; these just don't show."""
import json
import shutil

from vyom import util


def have():
    return shutil.which("pactl") is not None


def _json(*args):
    code, out = util.run(["pactl", "-f", "json", *args], timeout=4)
    if code != 0 or not out:
        return []
    try:
        return json.loads(out)
    except ValueError:
        return []


def _addr(props):
    a = props.get("api.bluez5.address") or props.get("device.string") or ""
    return a.upper()


def _best(profiles, prefixes):
    """The available profile with the highest priority among these kinds."""
    cands = [(p.get("priority", 0), name) for name, p in profiles.items()
             if name.startswith(prefixes) and p.get("available", True) is not False]
    return max(cands)[1] if cands else None


MUSIC = ("a2dp",)
CALLS = ("headset-head-unit", "hfp", "hsp", "handsfree")


def state():
    """{MAC: {"card", "profile", "mode" ("music"|"calls"|"off"), "music",
    "calls" (the profiles to switch to), "sink", "playing", "default"}}."""
    if not have():
        return {}
    out = {}
    for c in _json("list", "cards"):
        if not c.get("name", "").startswith("bluez"):
            continue
        mac = _addr(c.get("properties", {}))
        if not mac:
            continue
        prof = c.get("active_profile", "") or ""
        profiles = c.get("profiles", {}) or {}
        mode = "music" if prof.startswith(MUSIC) else "calls" if prof.startswith(CALLS) else "off"
        out[mac] = {"card": c["name"], "profile": prof, "mode": mode,
                    "music": prof if mode == "music" else _best(profiles, MUSIC),
                    "calls": prof if mode == "calls" else _best(profiles, CALLS),
                    "sink": None, "playing": False, "default": False}
    if not out:
        return out
    _, default = util.run(["pactl", "get-default-sink"], timeout=3)
    for s in _json("list", "sinks"):
        mac = _addr(s.get("properties", {}))
        if mac in out and out[mac]["sink"] is None:
            out[mac]["sink"] = s.get("name")
            out[mac]["playing"] = s.get("state") == "RUNNING"
            out[mac]["default"] = s.get("name") == default.strip()
    return out


def doing(a):
    """What the device is doing, in words: "Playing · high quality"."""
    if not a:
        return ""
    if a["mode"] == "music":
        return "Playing · high quality" if a["playing"] else "Music · high quality"
    if a["mode"] == "calls":
        return "Calls · with mic"
    return "Sound off"


def set_profile(card, profile):
    return util.run(["pactl", "set-card-profile", card, profile], timeout=5)


def set_output(sink):
    return util.run(["pactl", "set-default-sink", sink], timeout=5)
