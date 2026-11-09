# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

## v0.3.0 -- 2026-11-09

- **Vim keys** (Vyom 0.7): setu opens in NORMAL mode, where letters are keys
  and typing changes nothing; `/` (or `i`) types a filter, `Esc` goes back.
  `Space` is the leader, with a which-key strip; `?` lists every key and
  `Space Space` is a palette of every action.
- **New keys**: `Space p p` turns Bluetooth on or off, `Space a a` / `a p`
  pair and connect / pair only, `Space c c` / `c d` connect / disconnect,
  `Space v o` makes it the sound output, **`Space v m` / `v c` switch
  headphones to music / calls** (that switch was mouse-only), `Space u h`
  shows unnamed devices, `Space y a` copies the address, `r` rescans.
- **Remove asks with one question**: `dd` (or `Space d d`) asks
  "Remove …?", `y` removes and any other key keeps it, instead of pressing
  twice.
- **Typing is safe**: `Ctrl+Backspace` deletes a word in the filter again
  (it removed a device); it now says remove moved to `dd`. `Ctrl+U` scrolls
  half a page up, as in every vim tool (unnamed devices: `Space u h`).
  `Ctrl+B`, `Ctrl+O` and `Ctrl+P` still work.
- While a pairing runs, every key but `Enter` and `Esc` is ignored.
- Keys are data (`setu/vim.py`); `scripts/keybinds.py` writes the
  `# keybind:` lines and the README table from it (`--check` in CI).
- Needs Vyom 0.7.0.

## v0.2.1 -- 2026-11-08

- The Bluetooth switch is Vyom's `ui.switch()` (Vyom 0.6.2), with its own fix for GTK's
  baselines warning, instead of setu's copy of it.

## v0.2.0 -- 2026-11-07

A new look, and pairing you can see.

- Connected devices are cards at the top, two per row, each with a battery ring: green, yellow
  under 20% ("charge soon"), red under 10% ("plug it in"). Devices UPower reports several
  batteries for (earbuds left, right, case) show each one.
- Headphones and speakers say what they're doing: "Playing · high quality" or "Calls · with mic",
  and which one is the sound output. The preview has a Music / Calls switch, and `Ctrl+O` makes
  the selected device the sound output (needs `pactl`).
- Paired devices say when they were last connected, and "Out of range" when they couldn't be reached.
- Nearby devices are sorted closest first, with signal bars and a word (Close, Near, Far).
  Unnamed beacons hide behind `Ctrl+U` ("Ctrl+U shows 6 unnamed").
- The header says the name other devices see ("Visible as ...") and, in yellow, "Looking for
  devices" while it searches.
- Pairing is a step of its own: the 6-digit code shown big to compare with the device, "They
  match" (`Enter`) or Cancel (`Esc`), the steps Found, Confirm code, Connect, and a countdown.
  Before, a device that asked for a code made pairing hang until it timed out.
- Errors say why in plain words ("Device didn't answer: put it in pairing mode"), on the row and
  in the preview.
- Remove asks first: `Ctrl+Backspace` twice (`Esc` keeps the device).
- No `bluetoothctl`, no Bluetooth service, no adapter or Bluetooth off: a clear message with how
  to fix it, instead of the tool being left out.
- Needs Vyom 0.6.

- Every corner is rounded: the website's callouts.
- A logo and a shloka at the top of the README and the website: every Vayu tool has them now.
- Screenshots in the README and on the website.

## v0.1.3 -- 2026-10-21

- A website (GitHub Pages, https://theyashsawarkar.github.io/setu/): the README as a home page, the
  changelog, and architecture decision records (`docs/adr/`), built from these files by
  `scripts/build-site.py`; CI checks the site is up to date.

## v0.1.2 -- 2026-10-21

- Documentation for open source: a logo and banner, a full README (features,
  install, usage, configuration, troubleshooting, the whole Vyom family),
  CONTRIBUTING, SECURITY and CODE_OF_CONDUCT, issue and pull request
  templates, and CI (compiles, checks plugin.toml and that every key is
  documented).

## v0.1.1 -- 2026-10-19

- Keys are spelled out (Ctrl+Enter, Shift+Enter, Backspace) instead of symbols
  (⌃↵, ⇧↵, ⌫) in the footer and on rows and buttons.

## v0.1.0 -- 2026-10-19

- First release, as its own repository: bluetooth. Replaces bluetooth-picker.py in Vayu.
- Your devices, connected first, each with its **battery level** and the right icon (headphones, mouse, keyboard, phone…).
- **Discovers nearby devices while the panel is open**; nameless beacons are left out.
- `Enter` connects or disconnects; a nearby device **pairs, trusts and connects** in one go.
- Remove (unpair), and a Bluetooth on/off switch.
