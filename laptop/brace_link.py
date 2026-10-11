"""brace_link.py - hears the wearables through the base station.

The base station prints one JSON line per packet:
  {"src":"P", ...}  brace: heading, accuracy, radius, buttons, GPS
  {"src":"G", ...}  glove: roll, pitch, clutch, pads
A background thread reads them so the main loop never waits on the serial port.
If the USB cable is unplugged, it keeps retrying until the base station is back.
The other way: buzz(effect) asks the base station to make the brace buzz.
"""
import csv
import json
import os
import threading
import time

import serial

import config


class BraceLink:
    def __init__(self, port=config.SERIAL_PORT, baud=config.BAUD, log_path=config.LOG_PATH):
        self.port, self.baud = port, baud
        self.latest = {}      # newest packet per source: {"P": {...}, "G": {...}}
        self.last_time = {}   # when each source last spoke
        self.lock = threading.Lock()
        self.connected = False
        self.ser = None                    # the open port, for buzz(); None while unplugged
        self.write_lock = threading.Lock()
        self.last_buzz = 0.0

        new_file = not os.path.exists(log_path)
        self.log_file = open(log_path, "a", newline="")
        self.log = csv.writer(self.log_file)
        if new_file:
            self.log.writerow(["time", "heading", "acc", "radius", "btn", "lat", "lon", "fix", "sats", "hacc_m"])

        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                with serial.Serial(self.port, self.baud, timeout=1) as ser:
                    self.connected, self.ser = True, ser
                    while True:
                        line = ser.readline().decode(errors="ignore").strip()
                        if line.startswith("{"):
                            self._handle(line)
            except (serial.SerialException, OSError):
                self.connected, self.ser = False, None
                time.sleep(1.0)  # base station unplugged or port busy: try again

    def buzz(self, effect):
        """Make the brace buzz (a DRV2605 effect number). Quietly does nothing if the base station is
        unplugged; at most one buzz every 0.3 s so they stay distinguishable."""
        now = time.time()
        if self.ser is None or now - self.last_buzz < 0.3:
            return False
        try:
            with self.write_lock:
                self.ser.write(f"BUZZ {int(effect)}\n".encode())
            self.last_buzz = now
            return True
        except (serial.SerialException, OSError):
            return False

    def _handle(self, line):
        try:
            packet = json.loads(line)
        except json.JSONDecodeError:
            return
        src = packet.get("src", "P")
        now = time.time()
        with self.lock:
            self.latest[src], self.last_time[src] = packet, now
        if src == "P":
            self.log.writerow([now] + [packet.get(k) for k in
                               ("heading", "acc", "radius", "btn", "lat", "lon", "fix", "sats", "hacc_m")])
            self.log_file.flush()

    def get(self, src="P"):
        """Returns (newest packet from that source or None, is_fresh)."""
        with self.lock:
            packet = self.latest.get(src)
            fresh = packet is not None and time.time() - self.last_time.get(src, 0) < config.LINK_TIMEOUT
            return (dict(packet) if packet else None), fresh
