"""interp_uplink.py - sends the drone's camera frames to the AMD smoothing service (amd/interp_server.py).

Display only: these frames come out of the service interpolated for the phone; the control loop never
uses them. Runs on a background thread, drops frames instead of falling behind, and never blocks
main.py. Disabled when config.INTERP_URL is empty.
"""
import json
import threading
import time
import urllib.request

import cv2

import config as C


class InterpUplink:
    def __init__(self, url=C.INTERP_URL, fps=C.INTERP_FPS):
        self.url, self.fps = url.rstrip("/"), fps
        self.enabled = bool(self.url)
        self.ok = False
        self.stats = {}
        self._frame = None
        self._last_take = 0.0
        self._lock = threading.Condition()
        if self.enabled:
            threading.Thread(target=self._send_loop, daemon=True).start()
            threading.Thread(target=self._stats_loop, daemon=True).start()

    def send(self, frame):
        """Offer a frame; it's sent only if it's time for the next one (INTERP_FPS)."""
        if not self.enabled:
            return
        now = time.time()
        if now - self._last_take < 1.0 / self.fps:
            return
        self._last_take = now
        small = cv2.resize(frame, (640, 480)) if frame.shape[1] > 640 else frame.copy()
        with self._lock:
            self._frame = small
            self._lock.notify()

    def _send_loop(self):
        while True:
            with self._lock:
                while self._frame is None:
                    self._lock.wait()
                frame, self._frame = self._frame, None
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                continue
            try:
                req = urllib.request.Request(self.url + "/frame", data=buf.tobytes(),
                                             headers={"Content-Type": "image/jpeg"}, method="POST")
                urllib.request.urlopen(req, timeout=1.0).close()
                self.ok = True
            except Exception:
                self.ok = False
                time.sleep(0.5)

    def _stats_loop(self):
        while True:
            try:
                with urllib.request.urlopen(self.url + "/stats", timeout=1.5) as r:
                    self.stats = json.loads(r.read())
            except Exception:
                self.stats = {}
            time.sleep(2.0)

    def status(self):
        """For the app: where the smoothed stream lives and how it's doing."""
        if not self.enabled:
            return None
        return {"url": self.url + "/", "stream": self.url + "/stream", "ok": self.ok, **self.stats}
