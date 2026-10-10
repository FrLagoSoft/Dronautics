r"""main.py - Dronautics laptop brain: brace + camera -> leash -> Tello.

Run:  ..\.venv\Scripts\python.exe main.py     (from the laptop folder)
Close the Arduino Serial Monitor first. Set DRY_RUN in config.py to test with the webcam.

Keys (click the video window first):
  t take off   l land   f follow on/off   e EMERGENCY motor stop   q land and quit
  o orbit on/off   i flip orbit direction   w watch on/off   g gentle on/off
  h brace heading on/off   space re-lock on the person nearest the center
  y yaw test (1 s turn right)
  Calibration: a camera angle (stand centered, press, turn the drone slowly)
               k distance (stand exactly 2 m away)   c headings (face each other)
Glove: hold the clutch to fly by hand; release to return to the leash.
"""
import collections
import time

import cv2

import config as C
import hud
import leash as L
from brace_link import BraceLink
from drone import make_drone
from vision import Vision


def main():
    link = BraceLink()
    vision = Vision()
    drone = make_drone()
    print(f"YOLO on: {'GPU (CUDA)' if vision.on_gpu else 'CPU'}   |   {'DRY RUN (webcam)' if drone.is_dry_run else 'TELLO'}")

    # calibration (changes live with keys a, k, c)
    hfov, k_h, k_w, k_set, c_align = C.HFOV_DEG, C.K_DEFAULT, C.KW_DEFAULT, False, None
    cal_active, cal_psi0, cal_est, cal_bad = False, 0.0, [], 0
    # modes
    flying = following = orbiting = False
    gentle, watch, use_heading, orbit_dir = True, True, C.USE_BRACE_HEADING, 1
    # what we know about you
    d_s = b_s = phi_s = None
    last_seen, seen_bearing, b_raw_last = 0.0, None, 0.0
    world_rate, exit_dir = 0.0, 1
    last_det = None
    yaw_hist = collections.deque(maxlen=60)
    lr_prev = fb_prev = 0
    yaw_test_until = last_print = last_battery = 0.0

    while True:
        loop_start = time.time()
        frame = drone.frame()
        if frame is None:
            time.sleep(0.01)
            continue

        psi_d = drone.yaw()
        yaw_hist.append((time.time(), psi_d))
        brace, brace_ok = link.get("P")
        glove, glove_ok = link.get("G")
        psi_p = C.BRACE_SIGN * brace["heading"] if brace else None
        r = L.clamp(brace["radius"] if brace else 3, C.D_MIN + 0.3, C.R_INDOOR_MAX)

        # ---------- 1. camera: where are you? ----------
        det = vision.find(frame)
        now = time.time()
        if det:
            last_det = det
            d_raw = L.distance_from_box(det.size_h, det.size_w, det.clipped, k_h, k_w)
            b_raw = L.bearing_from_offset(det.offset, hfov)
            d_s = d_raw if d_s is None else d_s + C.SMOOTH * (d_raw - d_s)
            b_s = b_raw if b_s is None else b_s + C.SMOOTH * (b_raw - b_s)
            b_raw_last = b_raw
            psi_frame = L.yaw_at(yaw_hist, now - C.VIDEO_LAG_S)   # where the drone pointed when the frame was taken
            new_bearing = psi_frame + b_raw                        # where you were, in the world
            if seen_bearing is not None and now - last_seen < 1.0:
                world_rate = 0.7 * world_rate + 0.3 * L.wrap180(new_bearing - seen_bearing) / max(now - last_seen, 1e-3)
            last_seen, seen_bearing = now, new_bearing
            if abs(world_rate) > 5:
                exit_dir = 1 if world_rate > 0 else -1
            elif abs(b_raw) > 8:
                exit_dir = 1 if b_raw > 0 else -1
            if cal_active:  # camera-angle calibration sample
                est, sign_ok = L.hfov_estimate(L.wrap180(psi_frame - cal_psi0), det.offset)
                if est:
                    cal_est.append(est)
                    cal_bad += 0 if sign_ok else 1
                if len(cal_est) >= C.CAL_SAMPLES:
                    cal_est.sort()
                    hfov, cal_active = cal_est[len(cal_est) // 2], False
                    print(f"Camera angle calibrated: HFOV = {hfov:.1f} deg")
                    if cal_bad > len(cal_est) // 2:
                        print("WARNING: picture moved the same way the drone turned: DRONE_YAW_SIGN is probably flipped")
        age = now - last_seen
        b_now = L.wrap180(seen_bearing - psi_d) if seen_bearing is not None else None

        # ---------- 2. decide ----------
        lr = fb = ud = yaw = 0
        tx = ty = None
        source = "-"
        if d_s is not None and age < C.FRESH_S and orbiting:
            state = f"ORBIT {'right' if orbit_dir > 0 else 'left'}"
            lr, fb, yaw = L.orbit_commands(d_s, r, b_now, orbit_dir)
            lr, fb = L.slew(lr, lr_prev), L.slew(fb, fb_prev)
        elif d_s is not None and age < C.FRESH_S:
            state = "LEASH"
            if use_heading and c_align is not None and psi_p is not None and brace_ok:
                phi_raw, source = L.facing_in_drone_frame(psi_p, psi_d, c_align), "brace"
            else:
                phi_raw, source = b_s + 180, "front"
            phi_s = phi_raw if phi_s is None else phi_s + C.SMOOTH_PHI * L.wrap180(phi_raw - phi_s)
            px, py, tx, ty = L.target_point(d_s, b_s, phi_s, r)
            lr, fb = L.position_commands(d_s, px, py, tx, ty)
            lr, fb = L.slew(lr, lr_prev), L.slew(fb, fb_prev)
            yaw = L.leash_yaw(b_now, world_rate)
            if d_s < C.D_MIN:
                state = "TOO CLOSE: backing away"
        elif d_s is not None:
            state, yaw = L.lost_behavior(age, seen_bearing, psi_d, world_rate, exit_dir)
        else:
            state = "NO PERSON YET"

        # glove overrides everything while its clutch is held
        manual = bool(glove_ok and glove and glove.get("clutch"))
        if manual:
            lr, fb, ud, yaw = L.glove_commands(glove)
            state = "GLOVE MANUAL"

        # ---------- 3. safety, always last ----------
        why = ""
        if not manual:
            if not brace_ok:
                state, lr, fb = "BRACE LINK LOST: turn only", 0, 0
            if not following:
                lr = fb = ud = 0
                if not watch:
                    yaw = 0
                why = "  (follow OFF: turning only)" if watch else "  (follow OFF)"
        if not flying and not drone.is_dry_run:
            lr = fb = ud = yaw = 0
            why = "  (not flying: press t)"
        if now < yaw_test_until:
            lr, fb, ud, yaw, state = 0, 0, 0, 40, "YAW TEST: should turn right"
        if gentle and not manual:
            fb = int(fb * C.GENTLE_SCALE)
            if not orbiting:
                lr = int(lr * C.GENTLE_SCALE)
        lr_prev, fb_prev = lr, fb
        drone.send(lr, fb, ud, yaw)

        if flying and not drone.is_dry_run and now - last_battery > 5:
            last_battery = now
            if drone.battery() < C.LOW_BATTERY:
                print("Battery low: landing")
                drone.land()
                flying = following = orbiting = False

        # ---------- 4. screen ----------
        hud.draw_people(frame, vision.everyone, det.box if det else None, vision.target_id)
        mode = ("FOLLOW" if following else "HOVER") + (" | GENTLE" if gentle else " | FULL")
        if cal_active:
            mode += f" | CAMERA CAL {len(cal_est)}/{C.CAL_SAMPLES}: turn the drone slowly"
        gps = (f"GPS fix {brace['fix']} sats {brace['sats']}" if brace and "fix" in brace else "GPS -")
        hud.draw_lines(frame, [
            f"{mode} | {state} | lr {lr:+d} fb {fb:+d} ud {ud:+d} yaw {yaw:+d}{why}",
            (f"d {d_s:.2f} m{' (width)' if last_det and last_det.clipped else ''}  bearing {b_s:+.0f}  "
             f"r {r:.1f} m  facing from {source}" if d_s is not None else "d -  bearing -"),
            (f"drone yaw {psi_d:+.0f}  brace {round(psi_p) if psi_p is not None else '-'}  "
             f"K {k_h:.2f}{'' if k_set else ' (press k)'}  C {'set' if c_align is not None else 'press c'}  HFOV {hfov:.0f}"),
            (f"brace {'OK' if brace_ok else 'LOST'} | {gps} | glove {'OK' if glove_ok else '-'} | "
             f"{len(vision.everyone)} in view, lock #{vision.target_id if vision.target_id is not None else '-'}"),
        ])
        hud.draw_map(frame, d_s, b_s, r, tx, ty)
        cv2.imshow("Dronautics", frame)
        if now - last_print > 1.0:
            last_print = now
            print(f"{state:30s} follow={following} flying={flying} brace={brace_ok} "
                  f"bearing={b_raw_last:+.1f} -> lr {lr:+d} fb {fb:+d} ud {ud:+d} yaw {yaw:+d}")

        # ---------- 5. keys ----------
        key = cv2.waitKey(1) & 0xFF
        if key == ord("t") and not flying:
            flying = drone.takeoff()
        elif key == ord("l") and flying:
            drone.land()
            flying = following = orbiting = False
        elif key == ord("f"):
            following = not following
        elif key == ord("o"):
            orbiting = not orbiting
        elif key == ord("i"):
            orbit_dir = -orbit_dir
        elif key == ord("w"):
            watch = not watch
        elif key == ord("g"):
            gentle = not gentle
        elif key == ord("h"):
            use_heading = not use_heading
        elif key == ord(" "):
            vision.relock()
        elif key == ord("y"):
            yaw_test_until = time.time() + 1.0
        elif key == ord("a"):
            if age < C.FRESH_S and abs(b_raw_last) < 4:
                cal_active, cal_psi0, cal_est, cal_bad = True, L.yaw_at(yaw_hist, time.time() - C.VIDEO_LAG_S), [], 0
                print("Camera calibration: turn the drone slowly to one side until you near the edge")
            else:
                print("Camera calibration: stand in view, centered, then press a")
        elif key == ord("k"):
            if last_det and age < C.FRESH_S:
                k_h, k_w, k_set, d_s = C.CAL_DIST_M * last_det.size_h, C.CAL_DIST_M * last_det.size_w, True, None
                print(f"Distance constants: K {k_h:.3f}  Kw {k_w:.3f}")
            else:
                print("Can't set K: stand 2 m away, whole body in view")
        elif key == ord("c"):
            if d_s is not None and age < C.FRESH_S and psi_p is not None:
                c_align = L.alignment_constant(psi_d, b_s, psi_p)
                print(f"Headings aligned: C = {c_align:.1f}")
            else:
                print("Can't align: need you in view and brace data")
        elif key == ord("e"):
            drone.emergency()
            flying = following = orbiting = False
        elif key == ord("q"):
            break
        if key != 255 and key != ord("q"):
            print(f"[{chr(key)}] flying={flying} follow={following} orbit={orbiting} watch={watch} gentle={gentle}")

        time.sleep(max(0.0, 1.0 / C.LOOP_HZ - (time.time() - loop_start)))

    if flying:
        drone.land()
    drone.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
