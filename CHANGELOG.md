# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

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
