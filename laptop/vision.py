"""vision.py - finds people with YOLO (on the GPU when available) and locks onto ONE of them.

The lock remembers the target's tracker ID and the colors of their torso. If the tracker
loses the ID, it re-adopts whoever best matches those colors near the last spot, and
ignores everyone else. It never stays stuck: if nobody matches for LOCK_LOST_S seconds
(or there is only one person in view) it re-locks on its own. `note` says what it's doing.
"""
import math
import time
from dataclasses import dataclass

import cv2
import torch
from ultralytics import YOLO

import config as C


@dataclass
class Detection:
    box: tuple          # (x1, y1, x2, y2) pixels
    offset: float       # -1 far left .. +1 far right
    size_h: float       # box height / frame height
    size_w: float       # box width / frame width
    clipped: bool       # box touches the top or bottom edge (too close for height)
    track_id: object


def torso_signature(frame, box):
    """Color histogram of the torso: the middle of the box."""
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    roi = frame[int(y1 + 0.25 * bh):int(y1 + 0.6 * bh), int(x1 + 0.25 * bw):int(x1 + 0.75 * bw)]
    if roi.size == 0:
        return None
    hist = cv2.calcHist([cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def _center(box, w, h):
    return (box[0] + box[2]) / 2 / w, (box[1] + box[3]) / 2 / h


def _area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


class Vision:
    def __init__(self):
        self.device = 0 if torch.cuda.is_available() else "cpu"
        self.model = YOLO(C.MODEL_PATH)
        self.target_id = None
        self.signature = None
        self.sig_time = 0.0
        self.last_center = (0.5, 0.5)
        self.lost_since = None    # when the tracker dropped our ID and nobody matched
        self.relock_requested = False
        self.everyone = []        # all boxes this frame, for drawing
        self.note = "no lock yet"  # one line about the lock, for the HUD

    @property
    def on_gpu(self):
        return self.device == 0

    def relock(self):
        """Next frame: lock onto whoever is nearest the center."""
        self.relock_requested = True

    def _pick(self, frame, xyxy, ids, w, h):
        """Which box is our person. Returns (box, id); (None, None) = nobody this frame."""
        now = time.time()
        if self.target_id is not None and self.target_id in ids:
            self.lost_since = None
            self.note = f"locked #{self.target_id}"
            return xyxy[ids.index(self.target_id)], self.target_id

        if self.signature is not None:
            # The tracker lost our ID. Same torso colors near the last spot?
            best, best_score = None, 0.0
            for box, tid in zip(xyxy, ids):
                sig = torso_signature(frame, box)
                if sig is None:
                    continue
                color = max(0.0, cv2.compareHist(self.signature, sig, cv2.HISTCMP_CORREL))
                cx, cy = _center(box, w, h)
                dist = math.hypot(cx - self.last_center[0], cy - self.last_center[1])
                score = 0.7 * color + 0.3 * max(0.0, 1 - dist * 2)
                if score > best_score:
                    best, best_score = (box, tid), score
            if best and best_score >= C.LOCK_MATCH:
                self.lost_since = None
                self.note = f"re-adopted {'#%s' % best[1] if best[1] is not None else '(no tracker id)'} by color ({best_score:.2f})"
                return best

            # Nobody matches. Don't stay stuck: take the only person, or wait briefly then re-lock.
            if self.lost_since is None:
                self.lost_since = now
            waited = now - self.lost_since
            if len(xyxy) == 1:
                self.note = "only one person in view: taking them"
            elif waited < C.LOCK_LOST_S:
                self.note = f"lost: best color match {best_score:.2f} < {C.LOCK_MATCH}, re-lock in {C.LOCK_LOST_S - waited:.1f}s"
                return None, None
            else:
                self.note = f"lost for {waited:.1f}s: re-locking nearest the last spot"
            self.signature, self.lost_since = None, None
            j = min(range(len(xyxy)), key=lambda i: math.hypot(_center(xyxy[i], w, h)[0] - self.last_center[0],
                                                                _center(xyxy[i], w, h)[1] - self.last_center[1]))
            return xyxy[j], ids[j]

        # Nothing locked yet: the biggest person (the closest one).
        i = max(range(len(xyxy)), key=lambda j: _area(xyxy[j]))
        self.note = "auto-lock: biggest person in view"
        return xyxy[i], ids[i]

    def find(self, frame):
        """Returns the locked person's Detection, or None."""
        h, w = frame.shape[:2]
        boxes = self.model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0], conf=C.CONF,
                                 imgsz=C.IMGSZ, device=self.device, half=self.on_gpu, verbose=False)[0].boxes
        xyxy = boxes.xyxy.tolist()
        ids = boxes.id.int().tolist() if boxes.id is not None else [None] * len(xyxy)
        self.everyone = xyxy
        if not xyxy:
            self.note = "nobody in view" if self.target_id is None else f"#{self.target_id} out of view"
            return None
        if self.relock_requested:
            j = min(range(len(xyxy)), key=lambda i: abs((xyxy[i][0] + xyxy[i][2]) / 2 - w / 2))
            self.target_id, self.signature, self.lost_since, self.relock_requested = ids[j], None, None, False
        box, tid = self._pick(frame, xyxy, ids, w, h)
        if box is None:
            return None
        now = time.time()
        if tid is not None and (self.signature is None or tid != self.target_id):
            self.target_id, self.signature, self.sig_time = tid, torso_signature(frame, box), now
        elif self.signature is not None and now - self.sig_time > C.SIG_REFRESH_S:
            # keep the remembered colors current as the light changes (slow blend)
            sig = torso_signature(frame, box)
            if sig is not None:
                self.signature = cv2.normalize(0.8 * self.signature + 0.2 * sig, None)
                self.sig_time = now
        x1, y1, x2, y2 = box
        self.last_center = _center(box, w, h)
        return Detection(
            box=(x1, y1, x2, y2),
            offset=((x1 + x2) / 2 - w / 2) / (w / 2),
            size_h=(y2 - y1) / h,
            size_w=(x2 - x1) / w,
            clipped=y1 < C.CLIP_MARGIN * h or y2 > (1 - C.CLIP_MARGIN) * h,
            track_id=self.target_id,
        )
