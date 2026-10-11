"""hub.py - the phone app's window into the laptop.

Two small servers, both on background threads, both optional (main.py runs fine with no app):
  * WebSocket on port 8765:  laptop -> app  {"type":"state", ...} about 10x a second
                                            {"type":"event","text":"..."} for the feed
                             app -> laptop  {"action":"radius","value":2.0}, {"action":"follow","on":true}, ...
  * HTTP on port 8766:       /stream = MJPEG video (open it in a WebView), /frame.jpg = one frame

The app connects to ws://<laptop ip>:8765 and http://<laptop ip>:8766/stream.
"""
import asyncio
import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

WS_PORT = 8765
VIDEO_PORT = 8766
HOTSPOT_PREFIX = "172.20.10."  # iPhone Personal Hotspot always uses 172.20.10.0/28


def local_addresses():
    """This laptop's IPv4 addresses, without loopback and dead 169.254 ones."""
    import socket
    try:
        addrs = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        addrs = []
    return [a for a in addrs if not a.startswith(("127.", "169.254."))]


def print_phone_addresses():
    addrs = local_addresses()
    hotspot = [a for a in addrs if a.startswith(HOTSPOT_PREFIX)]
    print("-" * 60)
    if hotspot:
        print(f"PHONE LINK: iPhone hotspot up. In the app use {hotspot[0]}")
        print(f"            Safari test: http://{hotspot[0]}:{VIDEO_PORT}/")
    else:
        print("PHONE LINK: no iPhone hotspot address (172.20.10.x) on this laptop.")
        print("            Plug the iPhone in by USB with Personal Hotspot ON, then restart.")
    others = [a for a in addrs if not a.startswith(HOTSPOT_PREFIX)]
    if others:
        print(f"            other addresses: {', '.join(others)}")
    print("-" * 60)
# This is the logic behind a hotspot being used. If there's a hotspot through an open port, the phone will connect automatically. this is why I put the phone in the USB

class Hub:
    def __init__(self):
        self.clients = set()
        self.commands = queue.Queue()
        self.loop = None
        self.latest_jpeg = None
        self.jpeg_lock = threading.Lock()
        self.last_frame_push = 0.0
        self.client_count = 0
        threading.Thread(target=self._ws_thread, daemon=True).start()
        threading.Thread(target=self._video_thread, daemon=True).start()
        print_phone_addresses()

    # ---------- WebSocket ----------
    def _ws_thread(self):
        try:
            import websockets
        except ImportError:
            print("hub: 'websockets' not installed, app link disabled (pip install websockets)")
            return

        async def handler(websocket, *_):
            self.clients.add(websocket)
            self.client_count = len(self.clients)
            try:
                async for message in websocket:
                    try:
                        cmd = json.loads(message)
                        if isinstance(cmd, dict) and "action" in cmd:
                            self.commands.put(cmd)
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass
            finally:
                self.clients.discard(websocket)
                self.client_count = len(self.clients)

        async def serve():
            async with websockets.serve(handler, "0.0.0.0", WS_PORT):
                await asyncio.Future()

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(serve())
        except OSError as err:
            print(f"hub: WebSocket port {WS_PORT} busy ({err}); app link disabled")

    def _send_all(self, payload):
        if not self.clients or self.loop is None:
            return
        text = json.dumps(payload)

        async def go():
            for ws in list(self.clients):
                try:
                    await ws.send(text)
                except Exception:
                    self.clients.discard(ws)

        asyncio.run_coroutine_threadsafe(go(), self.loop)

    def publish(self, state):
        """Send the current state to every connected app."""
        state = dict(state)
        state["type"] = "state"
        state["t"] = time.time()
        self._send_all(state)

    def event(self, text):
        """A line for the app's command feed. Also printed locally."""
        print(text)
        self._send_all({"type": "event", "t": time.time(), "text": text})

    def poll_commands(self):
        """All commands the app sent since the last call."""
        out = []
        while True:
            try:
                out.append(self.commands.get_nowait())
            except queue.Empty:
                return out

    # ---------- video ----------
    def push_frame(self, frame, fps=10):
        """Keep the newest frame as JPEG for the app (at most `fps` times a second)."""
        now = time.time()
        if now - self.last_frame_push < 1.0 / fps:
            return
        self.last_frame_push = now
        small = cv2.resize(frame, (640, 480)) if frame.shape[1] > 640 else frame
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with self.jpeg_lock:
                self.latest_jpeg = buf.tobytes()

    def _video_thread(self):
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/frame.jpg"):
                    with hub.jpeg_lock:
                        data = hub.latest_jpeg
                    if data is None:
                        self.send_response(503)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(data)
                elif self.path.startswith("/stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    try:
                        last = None
                        while True:
                            with hub.jpeg_lock:
                                data = hub.latest_jpeg
                            if data is not None and data is not last:
                                last = data
                                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                                 + f"Content-Length: {len(data)}\r\n\r\n".encode() + data + b"\r\n")
                                self.wfile.flush()
                            time.sleep(0.05)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html><body style='margin:0;background:#000'>"
                                     b"<img src='/stream' style='width:100%'></body></html>")

            def log_message(self, *args):
                pass

        try:
            ThreadingHTTPServer(("0.0.0.0", VIDEO_PORT), Handler).serve_forever()
        except OSError as err:
            print(f"hub: video port {VIDEO_PORT} busy ({err}); video stream disabled")
