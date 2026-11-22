"""
device_kind.py

Best-effort guess of what KIND of device something is (phone, laptop,
TV, etc.) based on its vendor name and hostname.

Important honesty note: there is no field in networking that says
"I am a phone" - this is a heuristic based on common naming patterns
(e.g. a hostname containing "iPhone", a vendor known mainly for making
TVs). It can be wrong, especially for devices with randomized MAC
addresses or generic hostnames.
"""

ICONS = {
    "phone": "📱",
    "tablet": "📱",
    "laptop": "💻",
    "computer": "💻",
    "tv": "📺",
    "speaker": "🔊",
    "printer": "🖨",
    "router": "📶",
    "pi": "🍓",
    "console": "🎮",
    "unknown": "💠",
}


def guess_device_kind(vendor, hostname):
    """Returns a short string key (see ICONS above) guessing the device type."""
    text = f"{vendor} {hostname}".lower()

    if any(k in text for k in ("iphone",)):
        return "phone"
    if any(k in text for k in ("ipad",)):
        return "tablet"
    if any(k in text for k in ("macbook", "imac", "mac mini", "mac-")):
        return "laptop"
    if any(k in text for k in ("android", "galaxy", "pixel", "redmi", "oneplus", "realme")):
        return "phone"
    if any(k in text for k in ("appletv", "apple tv", "roku", "chromecast", "firetv",
                                "fire tv", "smart-tv", "smarttv", "bravia", "androidtv")):
        return "tv"
    if any(k in text for k in ("echo", "alexa", "sonos", "google home", "nest mini", "homepod")):
        return "speaker"
    if any(k in text for k in ("printer", "deskjet", "officejet", "laserjet")):
        return "printer"
    if any(k in text for k in ("raspberry",)):
        return "pi"
    if any(k in text for k in ("playstation", "xbox", "nintendo", "switch")):
        return "console"
    if any(k in text for k in ("tp-link", "netgear", "linksys", "asus router",
                                "router", "gateway", "d-link")):
        return "router"
    if any(k in text for k in ("laptop", "notebook", "desktop-", "pc-", "dell",
                                "lenovo", "thinkpad", "hp-", "surface")):
        return "computer"

    return "unknown"


def get_icon(kind):
    return ICONS.get(kind, ICONS["unknown"])