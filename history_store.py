"""
history_store.py

Keeps a small local record of devices seen on your network over time,
so the app can:
  - tell you when a new/unknown device joins
  - show you a simple history view (first seen / last seen per device)

Everything is stored in a single JSON file in your own home folder
(~/.network_monitor_history.json). Nothing here is sent anywhere.
"""

import json
import os
import datetime

HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".network_monitor_history.json")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return {"known_devices": {}, "scans": []}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("known_devices", {})
            data.setdefault("scans", [])
            return data
    except Exception:
        return {"known_devices": {}, "scans": []}


def save_history(data):
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Could not save history: {e}")


def record_scan(devices):
    """
    Updates the history file with this scan's results.

    Returns (new_devices, is_first_ever_scan):
      new_devices       - list of device dicts not seen in any earlier scan
      is_first_ever_scan - True if there was no history at all before this
                            (so "new devices" just means "first baseline",
                            not something worth alerting about)
    """
    history = load_history()
    is_first_ever = len(history["known_devices"]) == 0

    now = _now()
    new_devices = []

    for dev in devices:
        mac = dev["mac"]
        if mac not in history["known_devices"]:
            history["known_devices"][mac] = {
                "first_seen": now,
                "last_seen": now,
                "vendor": dev["vendor"],
                "last_hostname": dev["hostname"],
            }
            new_devices.append(dev)
        else:
            history["known_devices"][mac]["last_seen"] = now
            history["known_devices"][mac]["last_hostname"] = dev["hostname"]
            # Vendor lookups can improve over time (e.g. online lookup
            # succeeds on a later scan) - keep the most informative one.
            if history["known_devices"][mac]["vendor"] in ("Unknown vendor", ""):
                history["known_devices"][mac]["vendor"] = dev["vendor"]

    history["scans"].append({
        "timestamp": now,
        "count": len(devices),
        "macs": [d["mac"] for d in devices],
    })
    history["scans"] = history["scans"][-200:]  # keep the file from growing forever

    save_history(history)
    return new_devices, is_first_ever


def get_known_devices():
    return load_history()["known_devices"]


def get_recent_scans(limit=50):
    scans = load_history()["scans"]
    return list(reversed(scans[-limit:]))