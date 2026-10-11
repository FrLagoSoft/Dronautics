"""interp_uplink.py - sends the drone's camera frames to the AMD smoothing service (amd/interp_server.py).

Display only: these frames come out of the service interpolated for the phone; the control loop never
uses them. Built for a slow, far-away link (a public tunnel over a phone hotspot):
  * keeps its HTTPS connections open instead of reconnecting for every frame
  * several senders (INTERP_WORKERS, default 3) work in parallel, so slow round trips overlap
  * every frame carries a sequence number; the server drops any that arrive out of order
  * smaller frames (INTERP_WIDTH, default 480 px wide) and lighter JPEGs
Disabled when config.INTERP_URL is empty. Never blocks main.py.
"""
import collections
import http.client
import itertools
import json
import threading
import time
import urllib.parse
import urllib.request

import cv2

import config as C
#This was a pain to set up. It works though, you can see the width of the stream is set up to work alongside the AMD Instance. 
#it continously sets up a connection to the instance and then sends over frames to it. the video is a bit choppy but it works at double the framerate.

class InterpUplink:
    def __init__(self, url=C.INTERP_URL, fps=C.INTERP_FPS, token=None, width=None, workers=None):
        if token is None:
            token = getattr(C, "INTERP_TOKEN", "") or getattr(C, "INTERP_KEY", "")
        self.url, self.fps, self.token = url.rstrip("/"), fps, token
        self.width = width or getattr(C, "INTERP_WIDTH", 384)
        self.quality = getattr(C, "INTERP_JPEG_QUALITY", 70)
        self.enabled = bool(self.url)
        self.ok, self.error, self.stats = False, None, {}
        self.headers = {"Authorization": f"token {token}"} if token else {}
        parts = urllib.parse.urlsplit(self.url) if self.enabled else None
        self.https = bool(parts and parts.scheme == "https")
        self.host = parts.hostname if parts else None
        self.port = parts.port if parts else None
        self.path = parts.path.rstrip("/") if parts else ""
        self._queue = collections.deque(maxlen=2)   # only the newest frames wait; old ones are dropped
        self._cond = threading.Condition()
        self._seq = itertools.count(1)
        self._last_take = 0.0
        workers = workers or getattr(C, "INTERP_WORKERS", 3)
        if self.enabled:
            for _ in range(workers):
                threading.Thread(target=self._send_loop, daemon=True).start()
            threading.Thread(target=self._stats_loop, daemon=True).start()

    def send(self, frame):
        """Offer a frame; it's queued only if it's time for the next one (INTERP_FPS)."""
        if not self.enabled:
            return
        now = time.time()
        if now - self._last_take < 1.0 / self.fps:
            return
        self._last_take = now
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (self.width, int(h * self.width / w))) if w > self.width else frame.copy()
        with self._cond:
            self._queue.append((next(self._seq), small))
            self._cond.notify()

    def _connect(self):
        cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=3)

    def _send_loop(self):
        conn = None
        while True:
            with self._cond:
                while not self._queue:
                    self._cond.wait()
                seq, frame = self._queue.popleft()
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if not ok:
                continue
            try:
                if conn is None:
                    conn = self._connect()
                conn.request("POST", self.path + "/frame", body=buf.tobytes(),
                             headers={"Content-Type": "image/jpeg", "X-Seq": str(seq), **self.headers})
                resp = conn.getresponse()
                resp.read()
                self.ok = resp.status in (200, 204)
                self.error = None if self.ok else f"HTTP {resp.status}"
            except Exception as err:
                self.ok, self.error = False, repr(err)
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
                time.sleep(0.5)

    def _stats_loop(self):
        while True:
            try:
                req = urllib.request.Request(self.url + "/stats", headers=self.headers)
                with urllib.request.urlopen(req, timeout=3) as r:
                    self.stats = json.loads(r.read())
            except Exception:
                self.stats = {}
            time.sleep(2.0)

    def status(self):
        """For the app: where the smoothed stream lives and how it's doing."""
        if not self.enabled:
            return None
        q = f"?token={self.token}" if self.token else ""
        public = (getattr(C, "INTERP_PUBLIC_URL", "") or self.url).rstrip("/")
        return {"url": public + "/" + q, "stream": public + "/stream" + q,
                "ok": self.ok, "error": self.error, **self.stats}
