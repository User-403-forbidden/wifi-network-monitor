"""
gui.py

The desktop window for the network scanner, built with Tkinter
(included with Python, so no extra install needed).

Run this file to open the app: python gui.py
(See README.md for how to package it as a double-click app.)

Features:
- A loading screen while the first scan runs
- A home-screen dashboard with summary stats
- Dark/light theme toggle
- Device type icons (best-effort guess: phone/laptop/TV/etc.)
- Scan history saved locally, with a History view
- A popup notification when a new/unknown device joins your network
- A toolbar with working buttons: Scan Now, Auto-Refresh, Export CSV,
  Clear Labels, History, Theme
- A sortable device table with editable labels
"""

import csv
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

from network_scanner import scan_network, get_own_wifi_info
from device_kind import get_icon
import history_store


# ---------- Color themes ----------
THEMES = {
    "dark": {
        "bg": "#1e2229", "card": "#2a2f3a", "tree_bg": "#262b35",
        "accent": "#4da3ff", "text": "#eaecef", "subtext": "#9aa3b2",
        "good": "#3ecf8e", "warn": "#f2b84b",
    },
    "light": {
        "bg": "#f2f4f7", "card": "#ffffff", "tree_bg": "#ffffff",
        "accent": "#2a7de1", "text": "#1c1f26", "subtext": "#5b6472",
        "good": "#1f9d66", "warn": "#b9780a",
    },
}


class LoadingScreen(tk.Toplevel):
    """A small borderless splash window shown while the app does its first scan."""

    def __init__(self, parent, colors):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=colors["bg"])

        width, height = 360, 200
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        tk.Label(self, text="📶", bg=colors["bg"], fg=colors["accent"],
                  font=("Arial", 36)).pack(pady=(30, 5))
        tk.Label(self, text="My Network Monitor", bg=colors["bg"], fg=colors["text"],
                  font=("Arial", 14, "bold")).pack()
        self.status_text = tk.StringVar(value="Scanning your network...")
        tk.Label(self, textvariable=self.status_text, bg=colors["bg"],
                  fg=colors["subtext"], font=("Arial", 9)).pack(pady=(5, 15))

        self.progress = ttk.Progressbar(self, mode="indeterminate", length=260)
        self.progress.pack()
        self.progress.start(12)

    def close(self):
        self.progress.stop()
        self.destroy()


class StatCard(tk.Frame):
    """A small stat box for the dashboard (e.g. 'Total devices: 7')."""

    def __init__(self, parent, title, colors, accent_key="accent"):
        super().__init__(parent, bg=colors["card"], padx=16, pady=10)
        self.colors = colors
        self.accent_key = accent_key
        self.title_text = title
        self.value_label = tk.Label(self, text="--", bg=colors["card"],
                                      fg=colors[accent_key], font=("Arial", 20, "bold"))
        self.value_label.pack(anchor="w")
        self.title_label = tk.Label(self, text=title, bg=colors["card"],
                                      fg=colors["subtext"], font=("Arial", 9))
        self.title_label.pack(anchor="w")

    def set_value(self, value):
        self.value_label.config(text=str(value))

    def apply_theme(self, colors):
        self.colors = colors
        self.config(bg=colors["card"])
        self.value_label.config(bg=colors["card"], fg=colors[self.accent_key])
        self.title_label.config(bg=colors["card"], fg=colors["subtext"])


class Toast(tk.Toplevel):
    """A small auto-dismissing popup in the corner, used for new-device alerts."""

    def __init__(self, parent, colors, title, message):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=colors["card"])
        self.attributes("-topmost", True)

        width, height = 320, 90
        x = parent.winfo_x() + parent.winfo_width() - width - 20
        y = parent.winfo_y() + 50
        self.geometry(f"{width}x{height}+{x}+{y}")

        frame = tk.Frame(self, bg=colors["card"], padx=12, pady=10,
                          highlightbackground=colors["warn"], highlightthickness=2)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=title, bg=colors["card"], fg=colors["warn"],
                  font=("Arial", 10, "bold"), anchor="w").pack(fill="x")
        tk.Label(frame, text=message, bg=colors["card"], fg=colors["text"],
                  font=("Arial", 9), anchor="w", justify="left", wraplength=290).pack(fill="x")

        self.after(6000, self.destroy)


class HistoryWindow(tk.Toplevel):
    """Shows every device ever seen, with first/last seen timestamps."""

    def __init__(self, parent, colors):
        super().__init__(parent)
        self.title("Device History")
        self.geometry("620x420")
        self.configure(bg=colors["bg"])

        tk.Label(self, text="🕑 All Devices Ever Seen on Your Network",
                  bg=colors["bg"], fg=colors["text"], font=("Arial", 12, "bold"),
                  padx=14, pady=10).pack(anchor="w")

        columns = ("vendor", "hostname", "first_seen", "last_seen")
        tree = ttk.Treeview(self, columns=columns, show="headings")
        tree.heading("vendor", text="Vendor")
        tree.heading("hostname", text="Last Hostname")
        tree.heading("first_seen", text="First Seen")
        tree.heading("last_seen", text="Last Seen")
        tree.column("vendor", width=160)
        tree.column("hostname", width=150)
        tree.column("first_seen", width=140)
        tree.column("last_seen", width=140)
        tree.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        known = history_store.get_known_devices()
        rows = sorted(known.items(), key=lambda kv: kv[1].get("first_seen", ""), reverse=True)
        for mac, info in rows:
            tree.insert("", "end", values=(
                info.get("vendor", "Unknown"),
                info.get("last_hostname", "Unknown"),
                info.get("first_seen", "?"),
                info.get("last_seen", "?"),
            ))

        if not rows:
            tk.Label(self, text="No history yet - run a scan first.",
                      bg=colors["bg"], fg=colors["subtext"]).pack(pady=20)


class NetworkMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("My Network Monitor")
        self.root.geometry("900x580")
        self.root.minsize(760, 480)

        self.theme_name = "dark"
        self.colors = THEMES[self.theme_name]

        self.custom_labels = {}
        self.auto_refresh_on = tk.BooleanVar(value=False)
        self.auto_refresh_job = None
        self.last_devices = []
        self.last_local_ip = None
        self.wifi_info = {}
        self._themed_frames = []   # (widget, role) for bg recoloring
        self._themed_labels = []   # (widget, role) for fg recoloring
        self._sort_reverse = {}

        self.root.configure(bg=self.colors["bg"])
        self._build_style()
        self._build_header()
        self._build_toolbar()
        self._build_dashboard()
        self._build_wifi_panel()
        self._build_table()
        self._build_statusbar()

        self.root.withdraw()
        self.splash = LoadingScreen(self.root, self.colors)
        self.root.after(200, self.start_scan, True)

    # ---------------- Theming helpers ----------------

    def _reg_frame(self, widget, role="bg"):
        self._themed_frames.append((widget, role))
        return widget

    def _reg_label(self, widget, role="text"):
        self._themed_labels.append((widget, role))
        return widget

    def _build_style(self):
        c = self.colors
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Treeview", background=c["tree_bg"], fieldbackground=c["tree_bg"],
                         foreground=c["text"], rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background=c["card"], foreground=c["text"],
                         font=("Arial", 9, "bold"), borderwidth=0)
        style.map("Treeview", background=[("selected", c["accent"])])

        style.configure("Accent.TButton", background=c["accent"], foreground="white",
                         font=("Arial", 9, "bold"), padding=6)
        style.map("Accent.TButton", background=[("active", c["accent"])])

        style.configure("Flat.TButton", background=c["card"], foreground=c["text"],
                         font=("Arial", 9), padding=6)
        style.map("Flat.TButton", background=[("active", c["card"])])

        style.configure("Toggle.TCheckbutton", background=c["bg"], foreground=c["text"],
                         font=("Arial", 9))

    def _build_header(self):
        c = self.colors
        header = self._reg_frame(tk.Frame(self.root, bg=c["bg"], padx=16, pady=14))
        header.pack(fill="x")

        self.title_label = self._reg_label(
            tk.Label(header, text="🏠 Home Network", bg=c["bg"], fg=c["text"],
                      font=("Arial", 18, "bold")), "text"
        )
        self.title_label.pack(side="left")

        self.network_info_label = self._reg_label(
            tk.Label(header, text="", bg=c["bg"], fg=c["subtext"], font=("Arial", 10)),
            "subtext"
        )
        self.network_info_label.pack(side="left", padx=(12, 0))

    def _build_toolbar(self):
        c = self.colors
        toolbar = self._reg_frame(tk.Frame(self.root, bg=c["bg"], padx=16, pady=4))
        toolbar.pack(fill="x")

        self.scan_button = ttk.Button(toolbar, text="🔄  Scan Now", style="Accent.TButton",
                                        command=self.start_scan)
        self.scan_button.pack(side="left")

        ttk.Checkbutton(toolbar, text="Auto-refresh (30s)", variable=self.auto_refresh_on,
                         style="Toggle.TCheckbutton", command=self.toggle_auto_refresh
                         ).pack(side="left", padx=(12, 0))

        self.theme_button = ttk.Button(toolbar, text="🌙  Dark", style="Flat.TButton",
                                         command=self.toggle_theme)
        self.theme_button.pack(side="left", padx=(12, 0))

        ttk.Button(toolbar, text="🕑  History", style="Flat.TButton",
                   command=self.open_history).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="⬇  Export CSV", style="Flat.TButton",
                   command=self.export_csv).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="🗑  Clear Labels", style="Flat.TButton",
                   command=self.clear_labels).pack(side="right")

    def _build_dashboard(self):
        c = self.colors
        dash = self._reg_frame(tk.Frame(self.root, bg=c["bg"], padx=16, pady=10))
        dash.pack(fill="x")

        self.card_total = StatCard(dash, "Total devices", c, "accent")
        self.card_total.pack(side="left", padx=(0, 10))
        self.card_known = StatCard(dash, "Known brands", c, "good")
        self.card_known.pack(side="left", padx=(0, 10))
        self.card_unknown = StatCard(dash, "Unknown / private", c, "warn")
        self.card_unknown.pack(side="left")

    def _build_wifi_panel(self):
        c = self.colors
        panel = self._reg_frame(tk.Frame(self.root, bg=c["card"], padx=16, pady=10), "card")
        panel.pack(fill="x", padx=16, pady=(0, 6))

        self._reg_label(
            tk.Label(panel, text="📡 Your WiFi Connection", bg=c["card"], fg=c["text"],
                      font=("Arial", 10, "bold")), "text_on_card"
        ).pack(anchor="w")

        self.wifi_detail_label = self._reg_label(
            tk.Label(panel, text="Reading your connection details...", bg=c["card"],
                      fg=c["subtext"], font=("Arial", 9), justify="left"), "subtext_on_card"
        )
        self.wifi_detail_label.pack(anchor="w", pady=(4, 0))
        self.wifi_panel = panel

    def _build_table(self):
        c = self.colors
        table_frame = self._reg_frame(tk.Frame(self.root, bg=c["bg"], padx=16, pady=6))
        table_frame.pack(fill="both", expand=True)

        columns = ("ip", "type", "mac", "vendor", "hostname", "speed", "label")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")

        headings = {
            "ip": "IP Address", "type": "Type", "mac": "MAC Address", "vendor": "Brand",
            "hostname": "Hostname", "speed": "Speed / Frequency",
            "label": "Your Label (double-click to edit)",
        }
        widths = {"ip": 105, "type": 50, "mac": 135, "vendor": 160, "hostname": 130,
                  "speed": 140, "label": 140}

        for col, text in headings.items():
            anchor = "center" if col == "type" else "w"
            self.tree.heading(col, text=text, command=lambda c=col: self.sort_by(c))
            self.tree.column(col, width=widths[col], anchor=anchor)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.edit_label)

    def _build_statusbar(self):
        c = self.colors
        self.status_label = self._reg_label(
            tk.Label(self.root, text="Ready.", bg=c["card"], fg=c["subtext"],
                      font=("Arial", 9), anchor="w", padx=16, pady=6), "subtext_on_card"
        )
        self.status_label.pack(fill="x", side="bottom")

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.colors = THEMES[self.theme_name]
        c = self.colors

        self.root.configure(bg=c["bg"])
        self._build_style()  # rebuild ttk styles with new colors

        for widget, role in self._themed_frames:
            widget.config(bg=c["card"] if role == "card" else c["bg"])

        for widget, role in self._themed_labels:
            if role == "text":
                widget.config(bg=c["bg"], fg=c["text"])
            elif role == "subtext":
                widget.config(bg=c["bg"], fg=c["subtext"])
            elif role == "text_on_card":
                widget.config(bg=c["card"], fg=c["text"])
            elif role == "subtext_on_card":
                widget.config(bg=c["card"], fg=c["subtext"])

        for card in (self.card_total, self.card_known, self.card_unknown):
            card.apply_theme(c)

        self.theme_button.config(text="☀️  Light" if self.theme_name == "dark" else "🌙  Dark")

    # ---------------- Scanning ----------------

    def start_scan(self, first_run=False):
        self.scan_button.config(state="disabled", text="Scanning...")
        self.status_label.config(text="Scanning your network... this can take a few seconds.")
        thread = threading.Thread(target=self.run_scan, args=(first_run,), daemon=True)
        thread.start()

    def run_scan(self, first_run=False):
        try:
            devices, local_ip = scan_network()
            wifi_info = get_own_wifi_info()
        except Exception as e:
            self.root.after(0, lambda: self.handle_scan_error(e, first_run))
            return
        self.root.after(0, lambda: self.display_results(devices, local_ip, wifi_info, first_run))

    def handle_scan_error(self, error, first_run):
        if first_run:
            self.splash.close()
            self.root.deiconify()
        self.status_label.config(text=f"Scan failed: {error}")
        self.scan_button.config(state="normal", text="🔄  Scan Now")

    def display_results(self, devices, local_ip, wifi_info=None, first_run=False):
        self.last_devices = devices
        self.last_local_ip = local_ip
        if wifi_info is not None:
            self.wifi_info = wifi_info
            self._update_wifi_panel(wifi_info)

        self.tree.delete(*self.tree.get_children())

        known_count = 0
        for dev in devices:
            label = self.custom_labels.get(dev["mac"], "")
            display_hostname = dev["hostname"]
            is_this_computer = dev["ip"] == local_ip
            if is_this_computer:
                display_hostname += "  (this computer)"

            vendor_text = dev["vendor"]
            if "Private address" not in vendor_text and vendor_text != "Unknown vendor":
                known_count += 1

            if is_this_computer:
                band = self.wifi_info.get("band") or "?"
                speed = self.wifi_info.get("link_speed_mbps") or "?"
                speed_text = f"{band}, {speed}"
            else:
                speed_text = "Check router admin page"

            icon = get_icon(dev.get("kind", "unknown"))

            self.tree.insert(
                "", "end",
                values=(dev["ip"], icon, dev["mac"], vendor_text, display_hostname,
                         speed_text, label)
            )

        self.card_total.set_value(len(devices))
        self.card_known.set_value(known_count)
        self.card_unknown.set_value(len(devices) - known_count)

        subnet = ".".join(local_ip.split(".")[:3]) + ".0/24"
        self.network_info_label.config(text=f"·  {subnet}  ·  You: {local_ip}")

        now = datetime.now().strftime("%H:%M:%S")
        self.status_label.config(text=f"Found {len(devices)} device(s). Last scanned at {now}.")
        self.scan_button.config(state="normal", text="🔄  Scan Now")

        # Record to history and check for new/unknown devices
        new_devices, is_first_ever = history_store.record_scan(devices)
        if new_devices and not is_first_ever:
            self._show_new_device_alert(new_devices)

        if first_run:
            self.splash.close()
            self.root.deiconify()

        if self.auto_refresh_on.get():
            self.auto_refresh_job = self.root.after(30000, self.start_scan)

    def _update_wifi_panel(self, wifi_info):
        ssid = wifi_info.get("ssid") or "Unknown"
        band = wifi_info.get("band") or "Not available"
        standard = wifi_info.get("standard") or "Not available"
        speed = wifi_info.get("link_speed_mbps") or "Not available"
        signal = wifi_info.get("signal") or "Not available"

        text = (
            f"Network: {ssid}    Band: {band}    Standard: {standard}    "
            f"Link speed: {speed}    Signal: {signal}\n"
            f"Note: this is only available for THIS computer — other devices' "
            f"exact speed isn't visible over the network, so check your router's "
            f"admin page for theirs."
        )
        self.wifi_detail_label.config(text=text)

    def _show_new_device_alert(self, new_devices):
        names = ", ".join(
            d["vendor"] if "Unknown" not in d["vendor"] and "Private" not in d["vendor"]
            else d["ip"]
            for d in new_devices[:3]
        )
        more = f" (+{len(new_devices) - 3} more)" if len(new_devices) > 3 else ""
        Toast(self.root, self.colors, "⚠ New device joined your network",
              f"{names}{more}")

    # ---------------- Toolbar actions ----------------

    def toggle_auto_refresh(self):
        if self.auto_refresh_on.get():
            self.status_label.config(text="Auto-refresh enabled: scanning every 30 seconds.")
            self.auto_refresh_job = self.root.after(30000, self.start_scan)
        else:
            if self.auto_refresh_job:
                self.root.after_cancel(self.auto_refresh_job)
                self.auto_refresh_job = None
            self.status_label.config(text="Auto-refresh disabled.")

    def open_history(self):
        HistoryWindow(self.root, self.colors)

    def export_csv(self):
        if not self.last_devices:
            messagebox.showinfo("No data", "Run a scan first before exporting.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV file", "*.csv")],
            initialfile="network_devices.csv", title="Save device list as...",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["IP Address", "Type", "MAC Address", "Brand", "Hostname",
                              "Speed / Frequency", "Your Label"])
            for dev in self.last_devices:
                label = self.custom_labels.get(dev["mac"], "")
                is_this_computer = dev["ip"] == self.last_local_ip
                if is_this_computer:
                    speed_text = f"{self.wifi_info.get('band', '?')}, {self.wifi_info.get('link_speed_mbps', '?')}"
                else:
                    speed_text = "Check router admin page"
                writer.writerow([dev["ip"], dev.get("kind", "unknown"), dev["mac"],
                                  dev["vendor"], dev["hostname"], speed_text, label])

        self.status_label.config(text=f"Exported {len(self.last_devices)} device(s) to {path}")

    def clear_labels(self):
        if not self.custom_labels:
            return
        if messagebox.askyesno("Clear labels", "Remove all your custom device labels?"):
            self.custom_labels = {}
            if self.last_devices:
                self.display_results(self.last_devices, self.last_local_ip, self.wifi_info)
            self.status_label.config(text="All labels cleared.")

    # ---------------- Table interaction ----------------

    def sort_by(self, col):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        reverse = self._sort_reverse.get(col, False)
        items.sort(reverse=reverse)
        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)
        self._sort_reverse[col] = not reverse

    def edit_label(self, event):
        """Let the user double-click the Label column to name a device."""
        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item_id or column != "#7":  # #7 = the "label" column
            return

        values = self.tree.item(item_id, "values")
        mac = values[2]
        x, y, width, height = self.tree.bbox(item_id, column)

        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, values[6])
        entry.focus()

        def save_label(event=None):
            new_label = entry.get()
            self.custom_labels[mac] = new_label
            new_values = (values[0], values[1], values[2], values[3],
                          values[4], values[5], new_label)
            self.tree.item(item_id, values=new_values)
            entry.destroy()

        entry.bind("<Return>", save_label)
        entry.bind("<FocusOut>", save_label)


if __name__ == "__main__":
    root = tk.Tk()
    app = NetworkMonitorApp(root)
    root.mainloop()