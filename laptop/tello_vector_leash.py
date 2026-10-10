"""
tello_vector_leash.py - Drone Leash v3: the vector leash (see "Drone Leash v3 Blueprint").

One idea instead of a pile of rules:
  1. The camera places you:          P = (d cos b, d sin b)      d = K / box height, b = bearing
  2. The brace says which way you face, in the drone's frame:  phi = heading - drone yaw + C
  3. The leash sets a third point:   T = P + r (cos(phi + alpha), sin(phi + alpha))
  4. The drone flies toward T (fb, lr) and turns to keep you centered (yaw from b).
Turning your body moves T around the circle, so orbit falls out of the same math.

DRY_RUN = True  -> webcam + real brace; commands are only shown on screen (plus a top-down map)
DRY_RUN = False -> flies the Tello

Before flying, run the five calibration checks from the blueprint:
  1. Drone yaw sign:   turn the Tello clockwise by hand; "drone yaw" must rise. Else DRONE_YAW_SIGN = -1
  2. Brace sign:       turn your body to your right; "brace" heading must rise.  Else BRACE_SIGN = -1
  3. Distance K:       stand exactly 2 m away, whole body in frame, press k
  4. Camera angle:     HFOV_DEG = 2 x atan(x / 2), x = sideways step to the frame edge at 2 m
  5. Heading align:    stand centered, facing the drone while it faces you, press c

Keys (click the video window first):
  t = take off   l = land   f = follow on/off   g = gentle mode on/off (starts ON)
  k = set distance constant (standing 2 m away)  c = align headings (facing each other)
  h = brace heading on/off (off = just keep distance in front of you)
  y = yaw test: 1 second of turning right (proves the drone accepts turn commands)
  space = re-lock: follow whoever is nearest the center of the frame (stand there and press it)
  e = EMERGENCY motor stop (the drone drops; only to prevent a crash)   q = land and quit
"""
import csv
import json
import logging
import math
import os
import sys
import threading
import time

DRY_RUN = False
SERIAL_PORT = "COM9"  # the XIAO base station's port
BAUD = 115200
LOG_PATH = "base_log.csv"

# Signs from calibration steps 1 and 2: both headings must grow clockwise
DRONE_YAW_SIGN = 1
BRACE_SIGN = 1

# Camera
HFOV_DEG = 70.0        # approximate until measured (calibration step 4)
CONF = 0.4             # detection confidence; lower finds you more often in dim light
IMGSZ = 416            # smaller = faster detection
CAL_DIST_M = 2.0       # stand this far away and press k
K_DEFAULT = 1.1        # height constant until you press k (you fill about 55% of the frame height at 2 m)
KW_DEFAULT = 0.5       # width constant until you press k (you fill about 25% of the frame width at 2 m)
CLIP_MARGIN = 0.02     # box within 2% of the top or bottom edge = cut off -> use width for distance

# Leash geometry
LEASH_ANGLE = 0.0      # alpha: 0 = in front of you, 180 = behind you
R_INDOOR_MAX = 2.5     # caps the brace radius indoors (m)
D_MIN = 1.0            # never closer than this (m)
USE_BRACE_HEADING = True  # False = just keep distance in front of you (test step 5)

# Control
POS_GAIN = 20.0        # rc speed per meter of distance to the target
POS_DEADBAND = 0.30    # m: closer than this to the target = hold still
POS_SLEW = 8           # max change of lr/fb per loop (rc units): no jerks
POS_MAX = 35           # top forward/back/sideways speed (rc units)
YAW_PER_DEG = 3.0      # turning speed per degree you are off-center
YAW_KD = 0.3           # damping: counters how fast the bearing is changing (kills side-to-side hunting)
YAW_DEADBAND = 5.0     # degrees: closer to center than this = no turn
YAW_MIN = 10           # smallest turn command sent (tiny commands may not visibly turn the Tello)
YAW_MAX = 90
SMOOTH = 0.25          # blend of each new distance/bearing measurement (lower = smoother, slower)
SMOOTH_PHI = 0.3       # blend for your facing angle (the orbit input)
GENTLE_SCALE = 0.5     # gentle mode scales forward/back/sideways (not turning)

# Timing and safety
LOOP_HZ = 20
LINK_TIMEOUT = 1.0     # brace silent this long -> hover
FRESH_S = 0.5          # seen within this -> normal leash
HOLD_S = 1.5           # lost under this -> hold position, turn toward the last bearing; else hover
LOW_BATTERY = 20       # % -> land
LOCK_MATCH = 0.55      # how well a person must match the locked target (color + position) to be re-adopted


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def wrap180(a):
    return (a + 180) % 360 - 180


def measure(offset, size_h, size_w, clipped, k_h, k_w):
    """Camera box -> (distance d in m, bearing b in degrees, right = positive).
    Height is the better ruler, but once you're close enough that the box is cut off at the
    top or bottom, height stops growing. Then the box WIDTH takes over."""
    b = math.degrees(math.atan(offset * math.tan(math.radians(HFOV_DEG / 2))))
    d = k_w / max(size_w, 1e-3) if clipped else k_h / max(size_h, 1e-3)
    return d, b


def target_point(d, b, phi, r, alpha=LEASH_ANGLE):
    """Person P and target T in the drone's frame (x forward, y right, meters)."""
    px, py = d * math.cos(math.radians(b)), d * math.sin(math.radians(b))
    a = math.radians(phi + alpha)
    return px, py, px + r * math.cos(a), py + r * math.sin(a)


def yaw_command(b, b_rate=0.0):
    """Bearing (deg) and its rate (deg/s) -> turning command, damped, never too small to act on."""
    if abs(b) < YAW_DEADBAND:
        return 0
    y = clamp(YAW_PER_DEG * b - YAW_KD * b_rate, -YAW_MAX, YAW_MAX)
    if abs(y) < YAW_MIN:
        y = YAW_MIN if y > 0 else -YAW_MIN
    return int(round(y))


def commands(d, b, px, py, tx, ty):
    """Target in the drone's frame -> (lr, fb, yaw) rc values."""
    if d < D_MIN:
        # Too close: the only allowed motion is straight away from the person
        away = D_MIN - d
        ex, ey = -px / d * away, -py / d * away
    elif math.hypot(tx, ty) < POS_DEADBAND:
        ex, ey = 0.0, 0.0
    else:
        ex, ey = tx, ty
    fb = int(round(clamp(POS_GAIN * ex, -POS_MAX, POS_MAX)))
    lr = int(round(clamp(POS_GAIN * ey, -POS_MAX, POS_MAX)))
    return lr, fb, yaw_command(b)


def torso_signature(cv2, frame, box):
    """Color histogram of the torso (middle of the box): a cheap 'what does my person look like'."""
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    roi = frame[int(y1 + 0.25 * bh):int(y1 + 0.6 * bh), int(x1 + 0.25 * bw):int(x1 + 0.75 * bw)]
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def pick_target(cv2, frame, boxes, target_id, signature, last_center, w, h):
    """Choose which person to follow.
    1. The locked tracker ID, if it's still in the frame.
    2. Otherwise the person whose torso colors and position best match the one we locked.
    3. With nothing locked yet: the largest (closest) person.
    Returns (box, track_id, score) or (None, None, 0)."""
    xyxy = boxes.xyxy.tolist()
    ids = boxes.id.int().tolist() if boxes.id is not None else [None] * len(xyxy)
    if target_id is not None and target_id in ids:
        i = ids.index(target_id)
        return xyxy[i], target_id, 1.0
    if signature is not None:
        best, best_score = None, 0.0
        for box, tid in zip(xyxy, ids):
            sig = torso_signature(cv2, frame, box)
            if sig is None:
                continue
            color = max(0.0, cv2.compareHist(signature, sig, cv2.HISTCMP_CORREL))
            cx, cy = (box[0] + box[2]) / 2 / w, (box[1] + box[3]) / 2 / h
            dist = math.hypot(cx - last_center[0], cy - last_center[1])  # 0 = same spot, 1 = far
            score = 0.7 * color + 0.3 * max(0.0, 1 - dist * 2)
            if score > best_score:
                best, best_score = (box, tid), score
        if best is not None and best_score >= LOCK_MATCH:
            return best[0], best[1], best_score
        return None, None, best_score
    i = max(range(len(xyxy)), key=lambda j: (xyxy[j][2] - xyxy[j][0]) * (xyxy[j][3] - xyxy[j][1]))
    return xyxy[i], ids[i], 1.0


class BraceLink:
    """Reads the base station's JSON lines in the background, keeps the newest one, and logs each to CSV."""

    def __init__(self, port, baud, log_path):
        import serial
        self.latest, self.last_time = None, 0.0
        self.lock = threading.Lock()
        self.ser = serial.Serial(port, baud, timeout=1)
        new_file = not os.path.exists(log_path)
        self.log_file = open(log_path, "a", newline="")
        self.log = csv.writer(self.log_file)
        if new_file:
            self.log.writerow(["time", "heading", "radius", "btn"])
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            line = self.ser.readline().decode(errors="ignore").strip()
            if not line.startswith("{"):
                continue
            try:
                packet = json.loads(line)
            except json.JSONDecodeError:
                continue
            if packet.get("src", "P") != "P":
                continue  # brace packets only (the glove has its own fields)
            now = time.time()
            with self.lock:
                self.latest, self.last_time = packet, now
            self.log.writerow([now, packet.get("heading"), packet.get("radius"), packet.get("btn")])
            self.log_file.flush()

    def get(self):
        with self.lock:
            fresh = self.latest is not None and time.time() - self.last_time < LINK_TIMEOUT
            return (dict(self.latest) if self.latest else None), fresh


def draw_map(cv2, frame, d, b, phi, r, tx, ty):
    """Top-down map in the corner: drone at the bottom, nose up, 40 px per meter."""
    h, w = frame.shape[:2]
    size, s = 220, 40
    x0, y0 = w - size - 10, 10
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + size, y0 + size), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    ox, oy = x0 + size // 2, y0 + size - 25

    def pt(x_fwd, y_right):
        return int(ox + y_right * s), int(oy - x_fwd * s)

    cv2.drawMarker(frame, (ox, oy), (255, 255, 255), cv2.MARKER_TRIANGLE_UP, 14, 2)
    if d is None:
        cv2.putText(frame, "no person yet", (x0 + 50, y0 + 110), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        return
    px, py = d * math.cos(math.radians(b)), d * math.sin(math.radians(b))
    cv2.circle(frame, pt(px, py), int(r * s), (120, 120, 120), 1)
    cv2.line(frame, (ox, oy), pt(px, py), (180, 180, 180), 1)
    cv2.circle(frame, pt(px, py), 6, (255, 255, 255), -1)
    if tx is not None:
        cv2.line(frame, pt(px, py), pt(tx, ty), (40, 120, 255), 2)       # orange: brace leg
        cv2.arrowedLine(frame, (ox, oy), pt(tx, ty), (255, 140, 40), 2)  # blue: what it flies
        cv2.circle(frame, pt(tx, ty), 6, (255, 140, 40), 2)
    cv2.putText(frame, "map: 1 m = 40 px", (x0 + 8, y0 + size - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)


def main():
    import cv2
    import serial
    import torch
    from ultralytics import YOLO

    device = 0 if torch.cuda.is_available() else "cpu"
    print(f"YOLO on: {'GPU (CUDA)' if device == 0 else 'CPU'}")

    try:
        brace = BraceLink(SERIAL_PORT, BAUD, LOG_PATH)
    except serial.SerialException as err:
        sys.exit(f"Could not open {SERIAL_PORT}: {err}\n"
                 "Check SERIAL_PORT, and close the Arduino Serial Monitor and receiver.py first.")
    model = YOLO("yolo11n.pt")

    if DRY_RUN:
        cam = cv2.VideoCapture(0)

        def get_frame():
            ok, frame = cam.read()
            return frame if ok else None

        def send(lr, fb, yaw):
            pass

        def drone_yaw():
            return 0.0
    else:
        from djitellopy import Tello

        tello = Tello()
        tello.connect()
        print("Battery:", tello.get_battery(), "%")

        class HideRcSpam(logging.Filter):
            def filter(self, record):
                return "'rc " not in record.getMessage()

        Tello.LOGGER.addFilter(HideRcSpam())
        tello.streamon()
        reader = tello.get_frame_read()

        def get_frame():
            frame = reader.frame
            return None if frame is None else cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        def send(lr, fb, yaw):
            tello.send_rc_control(lr, fb, 0, yaw)

        def drone_yaw():
            return float(tello.get_yaw())

    flying = following = False
    gentle, use_heading = True, USE_BRACE_HEADING
    k_dist, k_w, k_set, c_align = K_DEFAULT, KW_DEFAULT, False, None
    b_raw_last, b_rate, b_prev_t = 0.0, 0.0, 0.0
    phi_s = None
    lr_prev = fb_prev = 0
    last_size_w = None
    yaw_test_until = 0.0
    last_print = 0.0
    target_id, signature, last_center, n_people = None, None, (0.5, 0.5), 0
    relock = False
    d_s = b_s = None
    last_size, last_seen, seen_bearing = None, 0.0, None
    last_battery_check = 0.0

    while True:
        loop_start = time.time()
        frame = get_frame()
        if frame is None:
            time.sleep(0.01)
            continue
        h, w = frame.shape[:2]
        psi_d = DRONE_YAW_SIGN * drone_yaw()
        packet, link_ok = brace.get()
        psi_p = BRACE_SIGN * packet["heading"] if packet else None
        radius = packet["radius"] if packet else 3
        r = clamp(radius, D_MIN + 0.3, R_INDOOR_MAX)

        # 1) Camera: where are you? (tracked with IDs, locked onto one person)
        boxes = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0], conf=CONF,
                            imgsz=IMGSZ, device=device, quantize=16 if device == 0 else None, verbose=False)[0].boxes
        now = time.time()
        n_people = len(boxes)
        clipped = False
        for bx in boxes.xyxy.tolist():  # everyone else in gray
            cv2.rectangle(frame, (int(bx[0]), int(bx[1])), (int(bx[2]), int(bx[3])), (140, 140, 140), 1)
        if relock and n_people:  # space: lock onto whoever is closest to the center of the frame
            target_id, signature = None, None
            j = min(range(n_people), key=lambda i: abs((boxes.xyxy[i][0] + boxes.xyxy[i][2]) / 2 - w / 2))
            target_id = boxes.id.int().tolist()[j] if boxes.id is not None else None
            relock = False
        box, tid, match = (None, None, 0.0)
        if n_people:
            box, tid, match = pick_target(cv2, frame, boxes, target_id, signature, last_center, w, h)
        if box is not None:
            x1, y1, x2, y2 = box
            if tid is not None and (target_id is None or signature is None or tid != target_id):
                target_id, signature = tid, torso_signature(cv2, frame, box)  # (re)lock
            last_center = ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h)
            offset = ((x1 + x2) / 2 - w / 2) / (w / 2)
            last_size = (y2 - y1) / h
            last_size_w = (x2 - x1) / w
            clipped = y1 < CLIP_MARGIN * h or y2 > (1 - CLIP_MARGIN) * h
            d_raw, b_raw = measure(offset, last_size, last_size_w, clipped, k_dist, k_w)
            if b_prev_t:
                dt = max(now - b_prev_t, 1e-3)
                b_rate = 0.5 * b_rate + 0.5 * (b_raw - b_raw_last) / dt
            b_prev_t = now
            if d_s is None:
                d_s, b_s = d_raw, b_raw
            else:
                d_s += SMOOTH * (d_raw - d_s)
                b_s += SMOOTH * (b_raw - b_s)
            b_raw_last = b_raw
            last_seen, seen_bearing = now, psi_d + b_raw
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 165, 255), 2)
            cv2.putText(frame, f"LOCK #{target_id}", (int(x1), int(y1) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2)
        age = now - last_seen

        # 2-4) The leash
        lr = fb = yaw = 0
        phi = tx = ty = None
        source = "-"
        if d_s is not None and age < FRESH_S:
            state = "LEASH"
            if use_heading and c_align is not None and psi_p is not None and link_ok:
                phi_raw, source = wrap180(psi_p - psi_d + c_align), "brace"
            else:
                phi_raw, source = b_s + 180, "front"
            phi_s = phi_raw if phi_s is None else phi_s + SMOOTH_PHI * wrap180(phi_raw - phi_s)
            phi = phi_s
            px, py, tx, ty = target_point(d_s, b_s, phi, r)
            lr, fb, _ = commands(d_s, b_s, px, py, tx, ty)
            lr = int(clamp(lr, lr_prev - POS_SLEW, lr_prev + POS_SLEW))  # ease into changes
            fb = int(clamp(fb, fb_prev - POS_SLEW, fb_prev + POS_SLEW))
            yaw = yaw_command(b_raw_last, b_rate)  # newest bearing, damped by how fast it moves
            if d_s < D_MIN:
                state = "TOO CLOSE: backing away"
        elif d_s is not None and age < HOLD_S:
            state = "HOLD: turning to last spot"
            yaw = yaw_command(wrap180(seen_bearing - psi_d))
        else:
            state = "LOST: hover" if d_s is not None else "NO PERSON YET"

        # Safety, in priority order
        why_still = ""
        if not link_ok:
            state = "BRACE LINK LOST: turn only"
            lr = fb = 0  # no moving without the brace, but turning to keep you centered is allowed
        if not following:
            lr = fb = yaw = 0
            why_still = "  (follow OFF: press f)"
        elif not flying and not DRY_RUN:
            lr = fb = yaw = 0
            why_still = "  (not flying: press t)"
        if now < yaw_test_until:
            lr, fb, yaw, state = 0, 0, 40, "YAW TEST: should turn right"
        if gentle:
            lr, fb = int(lr * GENTLE_SCALE), int(fb * GENTLE_SCALE)
        lr_prev, fb_prev = lr, fb
        send(lr, fb, yaw)
        if not DRY_RUN and flying and now - last_battery_check > 5:
            last_battery_check = now
            if tello.get_battery() < LOW_BATTERY:
                print("Battery low: landing")
                following = False
                tello.land()
                flying = False

        # Screen
        mode = ("FOLLOW" if following else "HOVER") + (" | GENTLE" if gentle else " | FULL")
        lines = [
            f"{mode} | {state} | lr {lr:+d} fb {fb:+d} yaw {yaw:+d}{why_still}",
            (f"d {d_s:.2f} m{' (from width)' if clipped else ''}  bearing {b_s:+.0f}  r {r:.1f} m  facing from {source}"
             if d_s is not None else "d -  bearing -"),
            (f"drone yaw {psi_d:+.0f}  brace {psi_p if psi_p is None else round(psi_p)}  "
             f"K {k_dist:.2f}{'' if k_set else ' (press k)'}  C {'set' if c_align is not None else 'press c'}"),
            f"brace {'OK' if link_ok else 'LOST'} | heading {'ON' if use_heading else 'OFF'} | "
            f"{n_people} in view, lock #{target_id if target_id is not None else '-'} (space = re-lock on center)",
        ]
        for i, text in enumerate(lines):
            cv2.putText(frame, text, (10, 22 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        draw_map(cv2, frame, d_s, b_s, phi, r, tx, ty)
        if now - last_print > 1.0:
            last_print = now
            print(f"{state:28s} follow={following} flying={flying} link={link_ok} "
                  f"bearing={b_raw_last:+.1f} -> yaw {yaw:+d}  lr {lr:+d} fb {fb:+d}")
        cv2.imshow("Drone Leash v3", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("t") and not flying:
            if DRY_RUN:
                flying = True
            else:
                try:
                    tello.takeoff()
                    flying = True
                except Exception as err:
                    print(f"TAKEOFF FAILED: {err!r}")
                    print(f"  battery {tello.get_battery()}%  temperature {tello.get_temperature():.0f} C")
        elif key == ord("l") and flying:
            following = False
            if not DRY_RUN:
                tello.land()
            flying = False
        elif key == ord("f"):
            following = not following
        elif key == ord(" "):
            relock = True
        elif key == ord("g"):
            gentle = not gentle
        elif key == ord("y"):
            yaw_test_until = time.time() + 1.0
            print("Yaw test: 1 s of turning right")
        elif key == ord("h"):
            use_heading = not use_heading
        elif key == ord("k"):
            if last_size and age < FRESH_S:
                k_dist, k_w, k_set, d_s = CAL_DIST_M * last_size, CAL_DIST_M * last_size_w, True, None
                print(f"Distance constants: height K = {k_dist:.3f}, width Kw = {k_w:.3f}")
            else:
                print("Can't set K: stand 2 m away, whole body in frame")
        elif key == ord("c"):
            if d_s is not None and age < FRESH_S and psi_p is not None:
                c_align = psi_d + b_s + 180 - psi_p
                print(f"Headings aligned: C = {c_align:.1f}")
            else:
                print("Can't align: need you in view and brace data")
        elif key == ord("e"):
            if not DRY_RUN:
                tello.emergency()
            flying = following = False
        elif key == ord("q"):
            break
        if key in map(ord, "tlfghkce"):
            print(f"[{chr(key)}] flying={flying} follow={following} gentle={gentle} heading={use_heading}")

        time.sleep(max(0.0, 1.0 / LOOP_HZ - (time.time() - loop_start)))

    if DRY_RUN:
        cam.release()
    else:
        if flying:
            tello.land()
        tello.streamoff()
        tello.end()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()