"""interp_server.py - Dronautics display smoothing on an AMD GPU (ROCm), using RIFE.

The laptop POSTs the drone's camera frames here (JPEG, ~15/s). For every new frame, RIFE
generates the in-between frame(s), so the phone sees 2x (or more) the frame rate.
DISPLAY ONLY: the drone's AI and control never see these synthetic frames.

Endpoints (port 8090):
  POST /frame       one JPEG frame from the laptop
  GET  /stream      MJPEG of the smoothed video (open in the phone's WebView, or a browser)
  GET  /stats       JSON: GPU, backend (ROCm/HIP or CUDA), model, timings, frame rates
  GET  /            a page showing the stream with the stats

Run on the AMD machine (from the Practical-RIFE folder, with train_log/ inside):
  python interp_server.py --rife-dir . --multi 2
Without RIFE weights it still runs, using a plain 50/50 blend, labeled as such.
"""
import argparse
import collections
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--rife-dir", default=".", help="folder that contains train_log/ (Practical-RIFE)")
parser.add_argument("--multi", type=int, default=2, help="output frames per input frame (2 = double the fps)")
parser.add_argument("--port", type=int, default=8090)
parser.add_argument("--scale", type=float, default=1.0, help="RIFE scale; 0.5 is faster on big frames")
parser.add_argument("--no-label", action="store_true", help="don't draw the small corner label")
parser.add_argument("--host", default="127.0.0.1", help="127.0.0.1 for rc-tunnel; 0.0.0.0 to listen everywhere")
parser.add_argument("--key", default="", help="secret required on every request (the rc-tunnel URL is public)")
args = parser.parse_args()


# ---------------------------------------------------------------- interpolation backend
class Blend:
    name = "blend (no RIFE weights found)"
    device = "cpu"
    backend = "none"

    def between(self, a, b, t):
        return cv2.addWeighted(a, 1 - t, b, t, 0)


class Rife:
    def __init__(self, rife_dir, scale):
        import torch
        from torch.nn import functional as F
        self.torch, self.F, self.scale = torch, F, scale
        if not torch.cuda.is_available():
            raise RuntimeError("no GPU visible to PyTorch")
        torch.set_grad_enabled(False)
        sys.path.insert(0, os.path.abspath(rife_dir))
        from train_log.RIFE_HDv3 import Model  # noqa: E402  (ships with the RIFE weights)
        self.model = Model()
        if not hasattr(self.model, "version"):
            self.model.version = 0
        self.model.load_model(os.path.join(rife_dir, "train_log"), -1)
        self.model.eval()
        self.model.device()
        self.dev = torch.device("cuda")  # on ROCm builds, "cuda" is the AMD GPU
        self.device = torch.cuda.get_device_name(0)
        self.backend = f"ROCm/HIP {torch.version.hip}" if getattr(torch.version, "hip", None) else f"CUDA {torch.version.cuda}"
        self.name = f"RIFE {getattr(self.model, 'version', '?')}"

    def _tensor(self, img, pad):
        t = self.torch.from_numpy(np.ascontiguousarray(img.transpose(2, 0, 1))).to(self.dev).unsqueeze(0).float() / 255.0
        return self.F.pad(t, pad)

    def between(self, a, b, t):
        h, w = a.shape[:2]
        step = max(128, int(128 / self.scale))
        ph, pw = ((h - 1) // step + 1) * step, ((w - 1) // step + 1) * step
        pad = (0, pw - w, 0, ph - h)
        out = self.model.inference(self._tensor(a, pad), self._tensor(b, pad), t, self.scale)
        return (out[0] * 255).clamp(0, 255).byte().cpu().numpy().transpose(1, 2, 0)[:h, :w].copy()


try:
    engine = Rife(args.rife_dir, args.scale)
except Exception as err:  # weights missing, no GPU, ...: keep the pipeline alive and say so
    print(f"RIFE unavailable ({err!r}); using a plain blend.")
    engine = Blend()
print(f"Interpolation: {engine.name} on {engine.device} [{engine.backend}], {args.multi}x")


# ---------------------------------------------------------------- pipeline
incoming = {"frame": None}
incoming_lock = threading.Condition()
out_frames = collections.deque(maxlen=16)         # (jpeg bytes, synthetic?)
out_lock = threading.Lock()
stats = {"frames_in": 0, "frames_out": 0, "interp_ms": 0.0, "in_interval": 1 / 15, "last_in": 0.0,
         "late_dropped": 0, "last_seq": 0}
seq_lock = threading.Lock()


def label(img, synthetic):
    if args.no_label:
        return img
    tag = f"AMD smoothing {args.multi}x" + (" (generated)" if synthetic else "")
    cv2.putText(img, tag, (8, img.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def worker():
    prev = None
    while True:
        with incoming_lock:
            while incoming["frame"] is None:
                incoming_lock.wait()
            cur, incoming["frame"] = incoming["frame"], None
        outputs = []
        if prev is not None and prev.shape == cur.shape:
            t0 = time.time()
            for i in range(1, args.multi):
                outputs.append((engine.between(prev, cur, i / args.multi), True))
            stats["interp_ms"] = 0.8 * stats["interp_ms"] + 0.2 * (time.time() - t0) * 1000
        outputs.append((cur, False))
        prev = cur
        encoded = []
        for img, synthetic in outputs:
            ok, buf = cv2.imencode(".jpg", label(img.copy(), synthetic), [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                encoded.append((buf.tobytes(), synthetic))
        with out_lock:
            out_frames.extend(encoded)


threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------- HTTP
PAGE = b"""<html><body style='margin:0;background:#000;color:#ddd;font-family:sans-serif'>
<img id='v' style='width:100%'><pre id='s' style='margin:8px'></pre>
<script>const q=location.search;document.getElementById('v').src='stream'+q;
setInterval(async()=>{const r=await fetch('stats'+q);document.getElementById('s').textContent=
JSON.stringify(await r.json(),null,1)},1000)</script></body></html>"""


def authorized(handler):
    """With --key: accept 'Authorization: token <key>', 'X-Key: <key>', or ?key= / ?token= in the URL."""
    if not args.key:
        return True
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(handler.path).query)
    return (handler.headers.get("Authorization", "") == f"token {args.key}"
            or handler.headers.get("X-Key", "") == args.key
            or q.get("key", [""])[0] == args.key or q.get("token", [""])[0] == args.key)


class Handler(BaseHTTPRequestHandler):
    def deny(self):
        self.send_response(401)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"unauthorized: add ?key=<your key>")

    def do_POST(self):
        if not authorized(self):
            return self.deny()
        if not self.path.startswith("/frame"):
            self.send_response(404)
            self.end_headers()
            return
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            self.send_response(400)
            self.end_headers()
            return
        seq = int(self.headers.get("X-Seq", "0") or 0)
        if seq:
            with seq_lock:
                if seq <= stats["last_seq"]:
                    stats["late_dropped"] += 1   # an older frame overtaken by a newer one: skip it
                    self.send_response(204)
                    self.end_headers()
                    return
                stats["last_seq"] = seq
        now = time.time()
        if stats["last_in"]:
            stats["in_interval"] = 0.8 * stats["in_interval"] + 0.2 * min(1.0, now - stats["last_in"])
        stats["last_in"] = now
        stats["frames_in"] += 1
        with incoming_lock:
            incoming["frame"] = img  # if the GPU is busy, older frames are simply replaced
            incoming_lock.notify()
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if not authorized(self):
            return self.deny()
        if self.path.startswith("/stats"):
            body = json.dumps({
                "model": engine.name, "device": engine.device, "backend": engine.backend, "multi": args.multi,
                "interp_ms": round(stats["interp_ms"], 1),
                "fps_in": round(1 / max(stats["in_interval"], 1e-3), 1),
                "fps_out": round(args.multi / max(stats["in_interval"], 1e-3), 1),
                "frames_in": stats["frames_in"], "frames_out": stats["frames_out"],
                "late_dropped": stats["late_dropped"],
                "receiving": time.time() - stats["last_in"] < 2.0,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                buffering = True
                while True:
                    with out_lock:
                        n = len(out_frames)
                        if buffering and n < args.multi + 1:      # build a small cushion against network jitter
                            item = None
                        else:
                            buffering = False
                            while len(out_frames) > 3 * (args.multi + 1):  # far behind: skip ahead
                                out_frames.popleft()
                            item = out_frames.popleft() if out_frames else None
                            if item is None:
                                buffering = True                   # ran dry: rebuild the cushion
                    if item is None:
                        time.sleep(0.005)
                        continue
                    data = item[0]
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                     + f"Content-Length: {len(data)}\r\n\r\n".encode() + data + b"\r\n")
                    self.wfile.flush()
                    stats["frames_out"] += 1
                    time.sleep(max(0.0, stats["in_interval"] / args.multi - 0.002))  # spread frames evenly
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


print(f"Listening on {args.host}:{args.port}: POST /frame, GET /stream, /stats, /"
      + ("  (key required)" if args.key else "  (NO key: anyone with the URL can use it)"))
ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
