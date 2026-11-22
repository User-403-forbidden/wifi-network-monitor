"""
network_scanner.py

Scans YOUR OWN local network to find connected devices.
Works by:
  1. Figuring out your local subnet (e.g. 192.168.1.0/24)
  2. Pinging every address in that range (fills your OS's ARP table)
  3. Reading the ARP table to get IP + MAC address pairs
  4. Trying to resolve a hostname for each device
  5. Identifying each device's manufacturer from its MAC address
  6. Reading YOUR OWN WiFi connection's real band/speed from the OS

This only touches devices on your own local network — it does not
attempt to access, log into, or bypass anything on any device.
"""

import json
import platform
import re
import socket
import subprocess
import urllib.request
import urllib.error
import concurrent.futures

from device_kind import guess_device_kind


# ---------------------------------------------------------------------------
# Manufacturer (vendor) detection
# ---------------------------------------------------------------------------
#
# A handful of very common prefixes are kept locally so the app works
# instantly and offline for the most typical home devices. Anything not
# in this short list is looked up against a free public registry
# (macvendors.com) that mirrors the official IEEE manufacturer database —
# this covers essentially every manufacturer that has ever registered a
# network device, rather than the ~40 brands we could reasonably hand-type.
VENDOR_PREFIXES = {
    "F4:5C:89": "Apple", "A4:83:E7": "Apple", "3C:15:C2": "Apple",
    "88:66:A5": "Apple", "AC:BC:32": "Apple", "F0:18:98": "Apple",
    "A8:66:7F": "Apple", "00:1C:B3": "Apple",
    "8C:79:67": "Samsung", "5C:0A:5B": "Samsung", "E8:50:8B": "Samsung",
    "F4:F5:D8": "Google", "DA:A1:19": "Google", "54:60:09": "Google",
    "00:E0:FC": "Huawei", "48:7B:6B": "Huawei",
    "78:11:DC": "Xiaomi", "64:09:80": "Xiaomi",
    "68:54:FD": "Amazon", "44:65:0D": "Amazon",
    "00:50:F2": "Microsoft", "7C:1E:52": "Microsoft",
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi",
    "EC:FA:BC": "TP-Link", "50:C7:BF": "TP-Link", "A4:2B:B0": "TP-Link",
}

# In-memory cache so the same prefix is never looked up online twice in
# one run of the app.
_vendor_cache = {}


def is_randomized_mac(mac):
    """
    Detect whether a MAC address is a randomized / "private" address rather
    than the device's real, manufacturer-assigned one.

    This isn't a guess: it's defined by the IEEE 802 standard itself. The
    second bit of the first byte of a MAC address is the "locally
    administered" flag. Modern phones (iOS since 2020, Android since 10)
    turn this flag on by design when joining a WiFi network, specifically
    so apps and networks like this one can't identify or track the real
    device. When this flag is set, there is no real manufacturer prefix
    to look up — the phone is intentionally hiding it.
    """
    try:
        first_byte = mac.upper().replace("-", ":").split(":")[0]
        value = int(first_byte, 16)
        return bool(value & 0b00000010)
    except Exception:
        return False


def _lookup_vendor_online(prefix):
    """
    Look up a MAC prefix against a free public vendor registry.
    Returns a manufacturer name, or None if it can't be determined
    (no internet, rate-limited, or genuinely not registered).
    """
    if prefix in _vendor_cache:
        return _vendor_cache[prefix]

    try:
        url = f"https://api.macvendors.com/{prefix}"
        req = urllib.request.Request(url, headers={"User-Agent": "network-monitor-app"})
        with urllib.request.urlopen(req, timeout=2) as response:
            name = response.read().decode("utf-8").strip()
            _vendor_cache[prefix] = name
            return name
    except urllib.error.HTTPError:
        # 404 = not found in the registry, 429 = rate-limited. Either way,
        # we just don't have an answer right now.
        _vendor_cache[prefix] = None
        return None
    except Exception:
        # No internet, timeout, etc. Don't cache this — worth retrying later.
        return None


def get_vendor(mac):
    """
    Identify a device's manufacturer from its MAC address.

    Returns one of:
      - A real manufacturer name (e.g. "Apple, Inc.")
      - "Private address (phone is hiding its real ID)" for randomized MACs
      - "Unknown vendor" if it genuinely can't be determined
    """
    if is_randomized_mac(mac):
        return "Private address (phone is hiding its real ID)"

    prefix = mac.upper().replace("-", ":")[:8]

    if prefix in VENDOR_PREFIXES:
        return VENDOR_PREFIXES[prefix]

    online_result = _lookup_vendor_online(prefix)
    return online_result if online_result else "Unknown vendor"


# ---------------------------------------------------------------------------
# Finding devices on the network
# ---------------------------------------------------------------------------

def get_local_ip():
    """Find this computer's own IP address on the local network."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_subnet_prefix(local_ip):
    """Turn 192.168.1.42 into 192.168.1 (assumes a /24 network, the most common home setup)."""
    parts = local_ip.split(".")
    return ".".join(parts[:3])


def ping(ip):
    """Ping a single IP address. Returns True if it responds."""
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", "300", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]

    try:
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False


def ping_sweep(subnet_prefix, max_workers=50):
    """Ping every address from .1 to .254 in parallel to populate the ARP table."""
    ips = [f"{subnet_prefix}.{i}" for i in range(1, 255)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(ping, ips))


def get_arp_table():
    """Read the system's ARP table: a list of (ip, mac) pairs the OS already knows about."""
    system = platform.system().lower()
    devices = []

    try:
        if system == "windows":
            output = subprocess.check_output("arp -a", shell=True, text=True)
            pattern = r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-]{17})"
        else:
            output = subprocess.check_output(["arp", "-a"], text=True)
            pattern = r"\(([\d\.]+)\)\s+at\s+([0-9a-fA-F:]{17})"

        for match in re.finditer(pattern, output):
            ip, mac = match.group(1), match.group(2)
            devices.append({"ip": ip, "mac": mac.upper()})
    except Exception as e:
        print(f"Could not read ARP table: {e}")

    return devices


def get_hostname(ip):
    """Try to resolve a friendly hostname for an IP. Falls back to 'Unknown'."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "Unknown"


def scan_network():
    """
    Full scan: ping sweep the local subnet, then read the ARP table,
    then try to resolve a hostname + manufacturer for each device found.

    Returns a list of dicts:
      [{"ip", "mac", "hostname", "vendor"}, ...]
    plus this computer's own local IP.
    """
    local_ip = get_local_ip()
    subnet_prefix = get_subnet_prefix(local_ip)

    print(f"Scanning your network: {subnet_prefix}.0/24 ...")
    ping_sweep(subnet_prefix)

    raw_devices = get_arp_table()

    devices = []
    seen_ips = set()

    def enrich(d):
        hostname = get_hostname(d["ip"])
        vendor = get_vendor(d["mac"])
        kind = guess_device_kind(vendor, hostname)
        return {"ip": d["ip"], "mac": d["mac"], "hostname": hostname,
                "vendor": vendor, "kind": kind}

    unique_raw = []
    for d in raw_devices:
        if d["ip"] not in seen_ips:
            seen_ips.add(d["ip"])
            unique_raw.append(d)

    # Hostname + vendor lookups each involve some waiting (DNS / network
    # calls), so do them in parallel rather than one device at a time.
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        devices = list(executor.map(enrich, unique_raw))

    devices.sort(key=lambda d: d["ip"] != local_ip)
    return devices, local_ip


# ---------------------------------------------------------------------------
# Your OWN WiFi connection's real band / speed
# ---------------------------------------------------------------------------
#
# Important honesty note: this information (exact frequency band, link
# speed, signal strength) is only ever known by two parties: your own
# computer, and your router. There is no network message that broadcasts
# "here is my exact speed" to other devices — so this function can only
# ever describe YOUR OWN connection, not anyone else's. For other
# devices, the only accurate source is your router's own admin page.

def get_own_wifi_info():
    """
    Best-effort read of this computer's own WiFi connection details
    directly from the operating system. Returns a dict; any field that
    can't be determined on this system is left as None.
    """
    info = {"ssid": None, "band": None, "standard": None,
            "link_speed_mbps": None, "signal": None}

    system = platform.system().lower()

    try:
        if system == "windows":
            output = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"], text=True, errors="ignore"
            )
            for raw_line in output.splitlines():
                line = raw_line.strip()
                if line.startswith("SSID") and "BSSID" not in line:
                    info["ssid"] = line.split(":", 1)[1].strip()
                elif line.startswith("Radio type"):
                    info["standard"] = line.split(":", 1)[1].strip()
                elif line.startswith("Channel"):
                    try:
                        channel = int(line.split(":", 1)[1].strip())
                        info["band"] = "5 GHz" if channel > 14 else "2.4 GHz"
                    except ValueError:
                        pass
                elif line.startswith("Receive rate"):
                    info["link_speed_mbps"] = line.split(":", 1)[1].strip() + " Mbps"
                elif line.startswith("Signal"):
                    info["signal"] = line.split(":", 1)[1].strip()

        elif system == "darwin":
            output = subprocess.check_output(
                ["system_profiler", "SPAirPortDataType"], text=True
            )
            for raw_line in output.splitlines():
                line = raw_line.strip()
                if line.startswith("Channel:"):
                    value = line.split(":", 1)[1].strip()
                    info["band"] = "5 GHz" if "/5" in value or value.startswith(
                        ("36", "40", "44", "48", "149", "153", "157", "161")
                    ) else "2.4 GHz"
                elif line.startswith("PHY Mode:"):
                    info["standard"] = line.split(":", 1)[1].strip()
                elif line.startswith("Tx Rate:"):
                    info["link_speed_mbps"] = line.split(":", 1)[1].strip() + " Mbps"
                elif line.startswith("Signal / Noise:"):
                    info["signal"] = line.split(":", 1)[1].strip()

        else:  # Linux
            output = subprocess.check_output(
                ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,FREQ,RATE", "dev", "wifi"],
                text=True,
            )
            for raw_line in output.splitlines():
                parts = raw_line.split(":")
                if len(parts) >= 5 and parts[0] == "yes":
                    info["ssid"] = parts[1]
                    info["signal"] = parts[2] + "%"
                    freq_text = parts[3]
                    try:
                        freq_mhz = float(freq_text.split()[0])
                        info["band"] = "5 GHz" if freq_mhz > 4000 else "2.4 GHz"
                    except (ValueError, IndexError):
                        pass
                    info["link_speed_mbps"] = parts[4]
                    break

    except Exception as e:
        print(f"Could not read WiFi interface details: {e}")

    return info


if __name__ == "__main__":
    found, me = scan_network()
    print(f"\nYour device: {me}\n")
    print(f"{'IP Address':<16} {'MAC Address':<20} {'Vendor':<30} {'Hostname'}")
    print("-" * 95)
    for dev in found:
        print(f"{dev['ip']:<16} {dev['mac']:<20} {dev['vendor']:<30} {dev['hostname']}")
    print(f"\nFound {len(found)} device(s) on your network.")

    wifi = get_own_wifi_info()
    print("\nYour own WiFi connection:")
    for key, value in wifi.items():
        print(f"  {key}: {value if value else 'Not available on this system'}")