# setu

**setu** (सेतु, "bridge") — Bluetooth. A tool for [Vyom](https://github.com/Theyashsawarkar/vyom), the keyboard-driven panels of [Vayu](https://github.com/Theyashsawarkar/vayu); in Vayu it replaces bluetooth-picker.py.

> Bluetooth: devices with battery levels, discovery while open, connect, disconnect, pair, remove, power.

## Features

- Your devices, connected first, each with its **battery level** and the right icon (headphones, mouse, keyboard, phone…).
- **Discovers nearby devices while the panel is open**; nameless beacons are left out.
- `Enter` connects or disconnects; a nearby device **pairs, trusts and connects** in one go.
- Remove (unpair), and a Bluetooth on/off switch.

## Keys

| Key | Action |
|---|---|
| `Enter` | Connect or disconnect the selected device (pairs a new one) |
| `Ctrl+P` | Pair and trust the selected device |
| `Ctrl+Backspace` | Remove (unpair) the selected device |
| `Ctrl+B` | Turn Bluetooth on or off |
| `Esc` | close |

Every Vyom panel also has: `Up`/`Down` (or `Ctrl+K`/`Ctrl+J`) to move, `Page Up`/`Page Down`, `Tab` to switch to the next tool.

## Requirements

- [Vyom](https://github.com/Theyashsawarkar/vyom) 0.2 or newer (Python 3.11+, GTK 4, gtk4-layer-shell, a layer-shell compositor)
- `bluetoothctl`

## Install

```sh
git clone https://github.com/Theyashsawarkar/setu ~/.local/share/vyom/plugins/setu
vyom reload        # or log out and in
vyom setu         # open it (again: close it)
```

Bind it to a key, e.g. in sway:

```
bindsym $mod+<key> exec vyom setu
```

Update: `git -C ~/.local/share/vyom/plugins/setu pull && vyom reload`. `vyom list` shows every installed tool and why one would be skipped.

## License

MIT.
