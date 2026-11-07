"""Pairing as a real step, through an interactive bluetoothctl with its agent.

bluetoothctl's own agent asks on its terminal ("[agent] Confirm passkey
482913 (yes/no): "), so a one-shot `bluetoothctl pair` can't show the code
and waits until it times out. This runs bluetoothctl with pipes, makes its
agent the default one while pairing, reads what it says in a thread and
tells the panel (on the GTK main loop) what's happening: the code to
compare, the code to type on a keyboard, success, or what went wrong.
"""
import os
import re
import subprocess
import threading
import time

from gi.repository import GLib

from .bluez import ANSI, explain

CONFIRM = re.compile(r"Confirm passkey (\d+)")
DISPLAY = re.compile(r"\[agent\] (?:Passkey|PIN code): (\d+)")
AUTHORIZE = re.compile(r"Accept pairing \(yes/no\)")
SERVICE = re.compile(r"Authorize service .*\(yes/no\)")
ASK_PIN = re.compile(r"Enter (?:PIN code|passkey)")


class Session:
    """One pairing: pair -> trust -> connect (connect=False stops after
    trust). on_change(session) runs on the main loop after every step.

    state: "pairing" (waiting for the device), "confirm" (a code to compare;
    code set), "display" (a code to type on the device; code set),
    "authorize" (allow pairing, no code), "connecting", "done", "failed"
    (error set: what went wrong in plain words), "cancelled"."""

    TIMEOUT = 30          # seconds to answer a code (BlueZ gives up about then)

    def __init__(self, mac, name, kind, connect, on_change):
        self.mac, self.name, self.kind, self.connect = mac, name, kind, connect
        self.on_change = on_change
        self.state, self.code, self.error, self.asked_at = "pairing", "", "", 0.0
        self.paired = False
        self.proc = None
        self.buf = ""
        self.lock = threading.Lock()

    # ------------------------------------------------------------ control
    def start(self):
        try:
            self.proc = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, env={**os.environ, "LC_ALL": "C"})
        except OSError:
            self.fail("bluetoothctl isn't installed.")
            return
        threading.Thread(target=self.read, daemon=True).start()
        threading.Thread(target=self.watchdog, daemon=True).start()
        self.send("agent KeyboardDisplay")   # already on in interactive mode: harmless
        self.send("default-agent")
        self.send(f"pair {self.mac}")

    def send(self, line):
        try:
            self.proc.stdin.write((line + "\n").encode())
            self.proc.stdin.flush()
        except (OSError, ValueError, AttributeError):
            pass

    def answer(self, yes):
        """They match (yes) or they don't (no)."""
        if self.state in ("confirm", "authorize"):
            self.send("yes" if yes else "no")
            if yes:
                self.set("pairing")
            else:
                self.cancel()

    def cancel(self):
        if self.state in ("done", "failed", "cancelled"):
            self.stop()
            return
        if self.state in ("confirm", "authorize"):
            self.send("no")
        elif not self.paired:
            self.send(f"cancel-pairing {self.mac}")
        self.set("cancelled")
        GLib.timeout_add(600, lambda: (self.stop(), False)[1])

    def stop(self):
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            p.stdin.write(b"quit\n")
            p.stdin.flush()
        except (OSError, ValueError):
            pass
        threading.Thread(target=self._reap, args=(p,), daemon=True).start()

    @staticmethod
    def _reap(p):
        try:
            p.wait(2)
        except subprocess.TimeoutExpired:
            p.kill()

    @property
    def finished(self):
        return self.state in ("done", "failed", "cancelled")

    def left(self):
        """Seconds left to answer a code."""
        return max(0, int(self.TIMEOUT - (time.monotonic() - self.asked_at))) if self.asked_at else 0

    # ------------------------------------------------------------ reading
    def set(self, state, **kw):
        self.state = state
        for k, v in kw.items():
            setattr(self, k, v)
        if state in ("confirm", "display", "authorize"):
            self.asked_at = time.monotonic()
        GLib.idle_add(lambda: (self.on_change(self), False)[1])

    def fail(self, error):
        if not self.finished:
            self.set("failed", error=error)
            self.stop()

    def watchdog(self):
        start = time.monotonic()
        while not self.finished:
            time.sleep(1)
            if self.state in ("confirm", "authorize", "display") and self.asked_at and self.left() == 0:
                self.send("no")
                self.fail("Nobody answered in time: try again, and check the code on the device.")
            elif time.monotonic() - start > 90:
                self.fail("Device didn't answer: put it in pairing mode and try again.")

    def read(self):
        p = self.proc
        fd = p.stdout.fileno() if p else None
        while p is not None and not self.finished:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""
            if not chunk:
                if not self.finished:
                    self.fail("bluetoothctl stopped: is the Bluetooth service running?")
                return
            self.buf += ANSI.sub("", chunk.decode("utf-8", "replace")).replace("\r", "\n")
            self.scan()

    def scan(self):
        """Look at what bluetoothctl said since last time."""
        text, mac = self.buf, self.mac.upper()
        consumed = 0
        for m in re.finditer(r"[^\n]*(?:\n|$)", text):
            line = m.group(0)
            if not line:
                break
            done_line = line.endswith("\n")
            s = line.strip()
            # Prompts end without a newline: handle them as they come.
            if not done_line and not re.search(r"\(yes/no\):?\s*$|: $", s + " "):
                break
            consumed = m.end()
            self.line(s, mac)
        self.buf = text[consumed:]

    def line(self, s, mac):
        if not s:
            return
        if (m := CONFIRM.search(s)):
            self.set("confirm", code=m.group(1).zfill(6))
        elif (m := DISPLAY.search(s)):
            self.set("display", code=m.group(1))
        elif AUTHORIZE.search(s):
            self.set("authorize", code="")
        elif SERVICE.search(s):
            self.send("yes")          # a service of the device we're pairing
        elif ASK_PIN.search(s):
            self.send("")
            self.fail("This device wants a PIN typed in, which setu can't do yet: "
                      "pair it once with bluetoothctl in a terminal.")
        elif "Pairing successful" in s or "AlreadyExists" in s:
            self.paired = True
            self.send(f"trust {self.mac}")
            if self.connect:
                self.set("connecting", code=self.code)
                self.send(f"connect {self.mac}")
            else:
                self.set("done")
                self.stop()
        elif "Connection successful" in s and self.paired:
            self.set("done")
            self.stop()
        elif s.startswith("Failed to pair") or (s.startswith("Failed to connect") and self.paired):
            self.fail(explain(s))
        elif "not available" in s and mac in s.upper() and not self.paired:
            self.fail(explain("not available"))
        elif "No default controller available" in s:
            self.fail("No Bluetooth adapter: is it plugged in, or blocked (rfkill)?")
