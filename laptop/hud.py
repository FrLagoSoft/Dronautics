"""hud.py - what you see on the video window: status lines, boxes, and the top-down map."""
import math

import cv2
#Yolo logic for the drone.
#It's split into different body parts. Mostly because of the drone's camera being... really small.  
GREEN, WHITE, GRAY, ORANGE, BLUE = (0, 255, 0), (255, 255, 255), (140, 140, 140), (0, 165, 255), (255, 140, 40)


def draw_people(frame, everyone, locked_box, lock_id):
    for bx in everyone:
        cv2.rectangle(frame, (int(bx[0]), int(bx[1])), (int(bx[2]), int(bx[3])), GRAY, 1)
    if locked_box:
        x1, y1, x2, y2 = (int(v) for v in locked_box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), ORANGE, 2)
        cv2.putText(frame, f"LOCK #{lock_id}", (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, ORANGE, 2)


def draw_lines(frame, lines):
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (10, 22 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 2)


def draw_map(frame, d, b, r, tx, ty, scale=40):
    """Drone at the bottom, nose up. You (white), leash circle, target (blue), the brace leg (orange)."""
    h, w = frame.shape[:2]
    size = 220
    x0, y0 = w - size - 10, 10
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + size, y0 + size), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    ox, oy = x0 + size // 2, y0 + size - 25

    def pt(x_fwd, y_right):
        return int(ox + y_right * scale), int(oy - x_fwd * scale)

    cv2.drawMarker(frame, (ox, oy), WHITE, cv2.MARKER_TRIANGLE_UP, 14, 2)
    if d is None:
        cv2.putText(frame, "no person yet", (x0 + 50, y0 + 110), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        return
    px, py = d * math.cos(math.radians(b)), d * math.sin(math.radians(b))
    cv2.circle(frame, pt(px, py), int(r * scale), (120, 120, 120), 1)
    cv2.line(frame, (ox, oy), pt(px, py), (180, 180, 180), 1)
    cv2.circle(frame, pt(px, py), 6, WHITE, -1)
    if tx is not None:
        cv2.line(frame, pt(px, py), pt(tx, ty), ORANGE, 2)
        cv2.arrowedLine(frame, (ox, oy), pt(tx, ty), BLUE, 2)
        cv2.circle(frame, pt(tx, ty), 6, BLUE, 2)
    cv2.putText(frame, f"map: 1 m = {scale} px", (x0 + 8, y0 + size - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
