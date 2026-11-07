# 4. Pair through an interactive bluetoothctl and its agent

**Status:** Accepted  
**Date:** 2026-11-07

## Context

Pairing a device that wants its code confirmed (most phones, speakers and computers with a
screen) needs a BlueZ *agent* to answer "does 482913 match?". `bluetoothctl pair <mac>` run as
a one-shot command registers bluetoothctl's own agent, which asks on a terminal nobody sees:
pairing hung until BlueZ gave up, and the user never saw the code.

## Decision

setu pairs through `bluetoothctl` run interactively with pipes: it makes its agent the default
one for the duration (`default-agent`), sends `pair`, `trust` and `connect`, and reads what
bluetoothctl says in a thread. "Confirm passkey", "Passkey" (a code to type on a keyboard) and
"Accept pairing" prompts become the pairing card's code and its They match / Cancel buttons;
the answer goes back as `yes` / `no`. Errors (`org.bluez.Error.*`, `br-connection-*`) are turned
into plain words. Connect, disconnect, remove and power stay one-shot commands.

A device that wants a PIN *typed in* on the computer (old headsets and keyboards) isn't handled:
setu says so and points to bluetoothctl in a terminal.

## Consequences

- The code shows big in the panel, with a 30-second countdown; nothing hangs.
- While setu pairs, its agent is the default one; BlueZ goes back to the previous default agent
  when it quits.
- It depends on bluetoothctl's prompt wording, which has been stable for years; a change would
  show as "Device didn't answer", not a hang (there's a watchdog).
