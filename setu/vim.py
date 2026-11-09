"""setu's vim keys, as data. NORMAL is the start; `/` types a filter. The
modes, counts, which-key strip, help (?) and palette (Space Space) are
Vyom's (vyom/keys.py, vyom/modal.py; Vyom ADR 0008). Space groups follow
Vayu's shared letters (a add, d delete, u toggles, y copy); p (power),
c (connection) and v (voice: sound output and audio mode) are setu's own.
While a pairing runs, only Enter and Esc work (its card says what they do).

An action "verb:arg" runs Plugin.v_<verb>(count, arg) in setu/__init__.py,
or Vyom's own (moved, nop...).
"""
from vyom.keys import Bind

B = Bind
GROUPS = {" p": "power", " c": "connection", " v": "sound"}


def moved(seq, to):
    """An old key that moved in v0.4 (for one release): says where to."""
    return B(seq, f"moved:{to}", "", hidden=True)


NORMAL = [
    B("<CR>", "activate", "Connect or disconnect the selected device (pairs a new one)"),
    B("dd", "remove", "Remove (unpair) the selected device (y confirms)"),
    B("r", "refresh", "Rescan for devices now"),
    # The old Ctrl keys: harmless, so they stay (Ctrl+Backspace moved to d d;
    # Ctrl+U is half a page up now, as in every vim tool).
    B("<C-b>", "power", "", mode="any", hidden=True),
    B("<C-o>", "output", "", mode="any", hidden=True),
    B("<C-p>", "pair:only", "", mode="any", hidden=True),
    moved("<C-BS>", "d d"),
]

LEADER = [
    B(" pp", "power", "Toggle Bluetooth on or off"),
    B(" aa", "pair:connect", "Start pairing with the selected device, then connect it"),
    B(" ap", "pair:only", "Start pairing with the selected device (pair and trust, without connecting)"),
    B(" cc", "conn:on", "Connect the selected device"),
    B(" cd", "conn:off", "Disconnect the selected device"),
    B(" vo", "output", "Set the selected headphones or speaker as the sound output"),
    B(" vm", "audiomode:music", "Switch the selected headphones to music (high quality, no mic)"),
    B(" vc", "audiomode:calls", "Switch the selected headphones to calls (with the mic)"),
    B(" uh", "unnamed", "Toggle unnamed nearby devices (show or hide them)"),
    B(" ya", "copy", "Copy the selected device's address"),
    B(" dd", "remove", "Remove (unpair) the selected device (y confirms)"),
]

PAIRING = [
    B("<CR>", "nop", "Confirm the pairing code matches (or try again after an error)"),
    B("<Esc>", "nop", "Cancel pairing"),
]

SECTIONS = [
    ("bluetooth", "normal", "Normal mode (where it opens; `/` types a filter)", NORMAL),
    ("bluetooth leader", "normal", "Leader (Space)", LEADER),
    ("bluetooth-pairing", "any", "While pairing", PAIRING),
]


def keys(_tab):
    return NORMAL + LEADER
