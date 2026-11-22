# My Network Monitor

A desktop app that scans **your own home WiFi network** and shows you
every device connected to it — IP, MAC address, guessed device type,
manufacturer, and your own WiFi connection's real band/speed.

It works using your computer's own ping + ARP table (the same info your
router's admin page already shows you) plus a free public manufacturer
registry for brand lookup. It does not access, log into, or bypass
anything on any device.

## Requirements

- Python 3.8 or newer
- No extra packages needed — everything used is in Python's standard library.
- Internet access (used only for brand/manufacturer lookups of unknown devices).

## How to run it (as a script)

1. Open this folder in VS Code.
2. Open a terminal (Terminal > New Terminal).
3. Run:
   ```
   python gui.py
   ```
   (macOS/Linux may need `python3 gui.py`.) Use **Run Without Debugging**
   (Ctrl+F5 / Cmd+F5) if running from VS Code's Run menu.

## How to package it as a double-click app

This turns the script into a standalone app you can launch like any other
program — no terminal, no "python gui.py" needed.

1. Install the packaging tool (one-time):
   ```
   pip install pyinstaller
   ```
2. From inside this folder, build it:
   ```
   pyinstaller --onefile --windowed --name "NetworkMonitor" gui.py
   ```
3. Your app appears in a new `dist` folder:
   - Windows: `dist/NetworkMonitor.exe`
   - macOS: `dist/NetworkMonitor.app` (or a Unix executable, depending on setup)
   - Linux: `dist/NetworkMonitor`

   Double-click it to run — no Python or terminal required.

**Notes:**
- You must build it on the same type of operating system you want to run
  it on (build on Windows for a Windows app, macOS for a Mac app, etc.) —
  PyInstaller doesn't cross-build between operating systems.
- The first launch may be slightly slower as it unpacks; this is normal
  for `--onefile` builds.
- macOS may show a security warning for an unsigned app the first time —
  right-click the app and choose "Open" to bypass this once.

## Files

- `network_scanner.py` — scanning logic: finds devices, looks up
  manufacturers, reads your own WiFi connection details.
- `device_kind.py` — best-effort guess of device type (phone/laptop/TV/etc.)
  for the icon shown in the table. This is a heuristic based on naming
  patterns, not a certainty.
- `history_store.py` — saves a local record of devices seen over time to
  `~/.network_monitor_history.json` (your home folder). Used for the
  History view and new-device alerts. Nothing in this file leaves your
  computer.
- `gui.py` — the desktop window. Run this one.

## Features

- **Home-screen dashboard**: total devices, known brands, unknown/private count
- **Your WiFi Connection panel**: your real band, standard, speed, and signal
- **Device type icons**: best-effort 📱💻📺🔊🖨 guesses per device
- **Dark/Light theme toggle**
- **Scan history**: tracks every device ever seen, with first/last-seen times
- **New device alerts**: a popup appears when an unrecognized device joins
  (after your first baseline scan)
- **Export to CSV**, **custom device labels**, **sortable columns**,
  **auto-refresh every 30 seconds**

## A note on scope and privacy

This tool only scans the network your computer is currently connected to,
and only stores data locally on your own computer. The one thing that
leaves your machine is a lookup of the first 3 bytes of an unrecognized
MAC address (the manufacturer code only, never the full address) sent to
a free public vendor-lookup service, used purely to show you the brand.

## Ideas to extend further

- Show devices sorted by "most recently joined"
- Let labels persist across runs (currently they reset each time you open the app)
- A graph of device count over time, using the saved scan history