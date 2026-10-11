r"""phone_test.py - test the phone link WITHOUT the drone, brace, or camera.

Runs the same hub as main.py (WebSocket 8765, video 8766) with fake drone data and a moving
test picture. If the app shows "Drone Found!" and the map moves, the phone link works; any
remaining problem is on the drone side, not the phone side.

Run:  ..\.venv\Scripts\python.exe phone_test.py     (from the laptop folder)
"""
import math
import time

import cv2
import numpy as np

from hub import Hub

hub = Hub()
hub.event("phone_test: link OK")
radius, following, t0, last_clients = 2.5, False, time.time(), -1
print("Waiting for the app... (Ctrl+C to stop)")
while True:
    t = time.time() - t0
    for cmd in hub.poll_commands():
        hub.event(f"got {cmd}")
        if cmd.get("action") == "radius_step":
            radius = min(4.0, max(1.3, radius + float(cmd["value"])))
        elif cmd.get("action") == "follow":
            following = bool(cmd.get("on"))
    if hub.client_count != last_clients:
        last_clients = hub.client_count
        print(f"apps connected: {last_clients}")
    d, b = 2.2 + 0.4 * math.sin(t / 3), 25 * math.sin(t / 2)
    hub.publish({
        "mode": "FOLLOW" if following else "HOVER", "state": "PHONE TEST", "flying": False,
        "following": following, "orbiting": False, "orbit_dir": 1, "watch": True, "gentle": True,
        "manual": False, "dry_run": True, "radius": round(radius, 2), "d": round(d, 2), "bearing": round(b, 1),
        "heading": 0.0, "target": {"x": round(d + radius, 2), "y": 0.0},
        "cmd": {"lr": int(20 * math.sin(t / 2.5)), "fb": int(25 * math.sin(t / 4)),   # fake movement, so the
                "ud": int(15 * math.sin(t / 6)), "yaw": int(30 * math.sin(t / 3))},     # app's arrows animate
        "battery": 100, "height": int(110 + 20 * math.sin(t / 6)), "target_height": 130, "indoor": True,
        "brace": {"ok": False, "acc": None}, "glove": {"ok": False, "clutch": 0}, "gps": None,
        "lock": None, "people": 0, "calib": {"hfov": 70.0, "k_set": False, "c_set": False},
        "interp": None, "clients": hub.client_count,
    })
    frame = np.full((480, 640, 3), (60, 85, 107), np.uint8)
    x = int(320 + 220 * math.sin(t))
    cv2.circle(frame, (x, 240), 40, (232, 239, 246), -1)
    cv2.putText(frame, f"PHONE TEST {t:5.1f}s", (150, 420), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (232, 239, 246), 2)
    hub.push_frame(frame)
    time.sleep(0.1)
