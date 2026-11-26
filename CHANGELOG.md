# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

## v0.5.0 -- 2026-11-26

- **A new look: the picked device, big.** No more cards and rings: connected devices are the list's first rows, each with its battery at the right (the lower bud for earbuds) and a peach speaker mark on the sound output. The device you pick shows on the right as a showcase: its icon in glass, its name and state, the batteries as one strip of numbers (Left · Right · Case for earbuds), the audio mode, round buttons with their keys under them, and one quiet line of details. "Pair only" has its own icon.
- **Works every time, no reboot.** Connecting tries again (up to three times) when BlueZ fails in a way a second try fixes, and counts a device that connected despite an error as connected; a device that's away gets one more try, a refusal none. A chip that stopped answering (after sleep, mostly) shows "Bluetooth isn't answering" with **Reset** (`Enter`): it restarts the controller with an rfkill block and unblock, no root and no reboot. The NotReady error names Space p p, not the old Ctrl+B.
- **Turning Bluetooth on lifts a soft block.** When Bluetooth was blocked by rfkill (or switched off somewhere else), Turn on only told you to run `rfkill unblock bluetooth`; now it does that itself and turns the adapter on, and says so if a switch or the airplane-mode key is what's blocking it. The Turn on button shows Enter, not the old Ctrl+B.
- The panel no longer opens wider than the others when earbuds report every battery (it now fits the card: "L 82% · R 76% · Case 34%"); the playing line uses the card's room before it cuts off; the Nearby hint names the real key to show unnamed devices (Space u h, not Ctrl+U).
- New screenshots in the Spatial look, taken with made-up demo data (WebP, sharp on high-density screens).
- **A calmer Bluetooth panel.** The header says only what's unusual ("Visible as …" when others can find this computer; "Searching" while it looks), not "Named … · hidden" every time. Device cards have a lit edge, and the one you're on is brighter glass with a light rim instead of a thick white frame. The device's details are one quiet list, and its buttons sit side by side (Disconnect and Remove, Connect and Remove, Pair & connect and Pair only).
- The website, closer to Vayu's own: the tool's screenshot blurred behind the page, a centred hero with the logo and the verse, the page you're on as the white pill, glass "On this page" and footer panels, releases as cards. No glow behind the logo, no coloured line beside the verse.
- **Spatial look**: rounder, borderless glass cards, gauges and pairing card; an unknown earbud gauge is drawn dashed.
- The website has Vayu's Spatial look: graphite glass, a floating navigation bar, near-white for links and the main button, and the tool's own colour only as its signature (the logo's glow, the shloka's line, the release dots). No more all-caps labels.

## v0.4.0 -- 2026-11-09

- **Earbuds' left, right and case batteries, each on its own**, from Google Fast Pair: the buds announce them (with a charging flag) in their Bluetooth LE advertisements, which setu reads with a quiet LE scan of its own while the panel is open (listening only; the scan stops when it closes). Three gauges side by side in the preview (red at 20% or less, yellow at 40% or less, a green bolt while charging, — for a part that didn't say), `L 100 · R 90` and a ring each on the card. BlueZ's single level stays for devices that don't say more. Matched to the connected device by name; the advertiser's own entry no longer shows in Nearby.
- `tests/`: the Fast Pair parser (a real OnePlus Nord Buds 3 Pro advertisement, charging, the discoverable form, short and malformed data), run in CI. `SETU_FASTPAIR_FAKE` (a JSON of name → service data) feeds it for screenshots and tests.

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
