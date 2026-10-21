# 3. Use bluetoothctl for BlueZ

**Status:** Accepted  
**Date:** 2026-10-19

## Context

BlueZ is the Bluetooth stack everywhere on Linux; `bluetoothctl` ships with it.

## Decision

setu drives `bluetoothctl` for devices, battery levels, discovery, pairing and power, in the background.

## Consequences

- Works wherever BlueZ does.
- Discovery runs only while the panel is open.
