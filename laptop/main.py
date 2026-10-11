r"""main.py - Dronautics laptop brain: brace + camera -> leash -> Tello.

Run:  ..\.venv\Scripts\python.exe main.py     (from the laptop folder)
Close the Arduino Serial Monitor first. Set DRY_RUN in config.py to test with the webcam.

Keys (click the video window first):
  t take off   l land   f follow on/off   e EMERGENCY motor stop   q land and quit
  o orbit on/off   i flip orbit direction   w watch on/off   g gentle on/off   n indoor/outdoor
  u / j  height target up / down
  h brace heading on/off   space re-lock on the person nearest the center
  y yaw test (1 s turn right)
  Calibration: a camera angle (stand centered, press, turn the drone slowly)
               k distance (stand exactly 2 m away)   c headings (face each other)
Glove: hold the clutch to fly by hand; release to return to the leash.
Brace: hold Closer 1 s = lock onto me (stand in front of the drone). It buzzes when locked / lost / follow on-off.
"""
import collections
import time

import cv2

import config as C
import hud
import leash as L
from brace_link import BraceLink
from drone import make_drone
from hub import Hub
from interp_uplink import InterpUplink
from vision import Vision


def main():
    link = BraceLink()
    vision = Vision()
    drone = make_drone()
    hub = Hub()              # phone app link (WebSocket 8765) and raw video (HTTP 8766)
    uplink = InterpUplink()  # AMD smoothing service, if config.INTERP_URL is set
    print(f"YOLO on: {'GPU (CUDA)' if vision.on_gpu else 'CPU'}   |   {'DRY RUN (webcam)' if drone.is_dry_run else 'TELLO'}")

    # calibration (changes live with keys a, k, c)
    hfov, k_h, k_w, k_set, c_align = C.HFOV_DEG, C.K_DEFAULT, C.KW_DEFAULT, False, None
    cal_active, cal_psi0, cal_est, cal_bad = False, 0.0, [], 0
    k_samples, k_until = None, 0.0   # distance calibration in progress (key k): frames collected so far
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
    radius_m, last_brace_radius = C.RADIUS_START, None
    target_height, height_cm = C.TARGET_HEIGHT_CM, None
    last_publish, last_lock, battery_pct = 0.0, None, None
    prev_btn, lock_request_until, buzzed_lost, prev_following = 0, 0.0, False, False  # brace lock + buzzes

    while True:
        loop_start = time.time()
        frame = drone.frame()
        if frame is None:
            time.sleep(0.01)
            continue

        psi_d = drone.yaw()
        height_cm = drone.height()
        yaw_hist.append((time.time(), psi_d))
        brace, brace_ok = link.get("P")
        glove, glove_ok = link.get("G")
        psi_p = C.BRACE_SIGN * brace["heading"] if brace else None
        # The laptop owns the radius. A brace press only says which way to step it.
        if brace and last_brace_radius is not None and brace["radius"] != last_brace_radius:
            step = C.RADIUS_STEP if brace["radius"] > last_brace_radius else -C.RADIUS_STEP
            radius_m = L.clamp(radius_m + step, C.RADIUS_MIN, C.RADIUS_MAX)
            hub.event(f"Radius {radius_m:.1f} m ({'Farther' if step > 0 else 'Closer'} on the brace)")
        if brace:
            last_brace_radius = brace["radius"]
        r = radius_m
        # GPS walking speed (outdoors). Its direction comes from the brace heading, so it needs c pressed.
        gps_v = L.gps_speed(brace) if brace_ok else 0.0
        gps_dir = use_heading and c_align is not None and psi_p is not None and brace_ok
        gps_used = False
        # brace "lock onto me" (Closer held 1 s): re-lock on whoever is nearest the middle of the picture
        btn = brace.get("btn", 0) if brace else 0
        if btn & 4 and not prev_btn & 4:
            vision.relock()
            lock_request_until = time.time() + C.LOCK_REQUEST_TIMEOUT_S
            hub.event("Lock requested from the brace: stand in front of the drone")
        prev_btn = btn

        # ---------- 1. camera: where are you? ----------
        uplink.send(frame)  # clean frame to the AMD smoothing service (display only, never used for control)
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
                world_rate = L.clamp(world_rate, -C.WORLD_RATE_MAX, C.WORLD_RATE_MAX)
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
                    hub.event(f"Camera angle calibrated: HFOV = {hfov:.1f} deg")
                    if cal_bad > len(cal_est) // 2:
                        hub.event("WARNING: picture moved the same way the drone turned: DRONE_YAW_SIGN is probably flipped")
            if k_samples is not None:  # distance calibration sample
                k_samples.append((det.size_h, det.size_w, det.clipped, det.offset))
        if k_samples is not None and (len(k_samples) >= C.CAL_K_FRAMES or now > k_until):
            new_kh, new_kw, problem = L.k_from_samples(k_samples)
            if problem:
                hub.event(f"Distance calibration refused: {problem}")
            else:
                k_h, k_w, k_set, d_s = new_kh, new_kw, True, None
                hub.event(f"Distance calibrated: K {k_h:.3f}  Kw {k_w:.3f} (median of {len(k_samples)} frames)")
            k_samples = None
        age = now - last_seen
        if age < C.FRESH_S:
            buzzed_lost = False  # seen again: the next loss buzzes again
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
            if gps_v and source == "brace" and d_s >= C.D_MIN:  # you're walking: move with you right away
                ff_lr, ff_fb = L.walk_feedforward(gps_v, phi_s)
                lr = int(L.clamp(lr + ff_lr, -C.POS_MAX, C.POS_MAX))
                fb = int(L.clamp(fb + ff_fb, -C.POS_MAX, C.POS_MAX))
                state, gps_used = f"LEASH + GPS lead ({gps_v:.1f} m/s)", True
            lr, fb = L.slew(lr, lr_prev), L.slew(fb, fb_prev)
            yaw = L.leash_yaw(b_now, world_rate)
            if d_s < C.D_MIN:
                state = "TOO CLOSE: backing away"
        elif d_s is not None and gps_v and gps_dir and age < C.GPS_DR_MAX_S:
            # camera lost you but GPS says you're walking: turn toward where you walked to
            pred_b, _ = L.predict_position(d_s, seen_bearing, psi_p + c_align, gps_v, age)
            yaw = L.yaw_command(L.wrap180(pred_b - psi_d))
            state, gps_used = f"GPS: turning where you walked ({gps_v:.1f} m/s)", True
        elif d_s is not None:
            state, yaw = L.lost_behavior(age, seen_bearing, psi_d, world_rate, exit_dir)
            if state.startswith(("SEARCH", "LOST")) and not buzzed_lost and (flying or drone.is_dry_run):
                buzzed_lost = True
                link.buzz(C.BUZZ_LOST)
                hub.event("Lost you: searching")
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
            ud = L.height_command(height_cm, target_height)  # hold the height in every mode, follow or not
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
            battery_pct = drone.battery()
            if battery_pct < C.LOW_BATTERY:
                hub.event("Battery low: landing")
                drone.land()
                flying = following = orbiting = False

        # ---------- 4. screen ----------
        hud.draw_people(frame, vision.everyone, det.box if det else None, vision.target_id)
        mode = ("FOLLOW" if following else "HOVER") + (" | GENTLE" if gentle else " | FULL") + (" | INDOOR" if C.INDOOR else " | OUTDOOR")
        if cal_active:
            mode += f" | CAMERA CAL {len(cal_est)}/{C.CAL_SAMPLES}: turn the drone slowly"
        if k_samples is not None:
            mode += f" | MEASURING DISTANCE {len(k_samples)}/{C.CAL_K_FRAMES}: hold still"
        gps = (f"GPS fix {brace['fix']} sats {brace['sats']}" if brace and "fix" in brace else "GPS -")
        if gps_v:
            gps += f" walking {gps_v:.1f} m/s" + (" (steering)" if gps_used else "" if gps_dir else " (press c to use)")
        hud.draw_lines(frame, [
            f"{mode} | {state} | lr {lr:+d} fb {fb:+d} ud {ud:+d} yaw {yaw:+d}{why}",
            (f"d {d_s:.2f} m{' (width)' if last_det and last_det.clipped else ''}  bearing {b_s:+.0f}  "
             f"r {r:.1f} m  facing from {source}" if d_s is not None else "d -  bearing -"),
            (f"drone yaw {psi_d:+.0f}  brace {round(psi_p) if psi_p is not None else '-'}  "
             f"K {k_h:.2f}{'' if k_set else ' (press k)'}  C {'set' if c_align is not None else 'press c'}  HFOV {hfov:.0f}"),
            (f"brace {'OK' if brace_ok else 'LOST'} | {gps} | glove {'OK' if glove_ok else '-'} | "
             f"{len(vision.everyone)} in view, lock #{vision.target_id if vision.target_id is not None else '-'}"),
            f"vision: {vision.note}",
            f"height {height_cm if height_cm is not None else '-'} cm -> target {target_height} cm  (u / j)",
        ])
        hud.draw_map(frame, d_s, b_s, r, tx, ty)
        cv2.imshow("Dronautics", frame)
        hub.push_frame(frame)
        if vision.target_id != last_lock:
            last_lock = vision.target_id
            hub.event(f"Lock: #{last_lock}" if last_lock is not None else "Lock: none")
        if lock_request_until and det and not vision.relock_requested:
            lock_request_until = 0.0
            link.buzz(C.BUZZ_LOCKED)
            hub.event(f"Locked on you (brace): #{vision.target_id if vision.target_id is not None else '-'}")
        elif lock_request_until and now > lock_request_until:
            lock_request_until = 0.0
            vision.relock_requested = False
            link.buzz(C.BUZZ_LOST)
            hub.event("Lock request: nobody in view. Stand in front of the drone and hold Closer again")
        if following != prev_following:
            prev_following = following
            link.buzz(C.BUZZ_FOLLOW_ON if following else C.BUZZ_FOLLOW_OFF)
        if now - last_publish > 0.1:
            last_publish = now
            hub.publish({
                "mode": "FOLLOW" if following else "HOVER", "state": state,
                "flying": flying, "following": following, "orbiting": orbiting, "orbit_dir": orbit_dir,
                "watch": watch, "gentle": gentle, "manual": manual, "dry_run": drone.is_dry_run, "indoor": C.INDOOR,
                "radius": round(radius_m, 2), "d": None if d_s is None else round(d_s, 2),
                "height": height_cm, "target_height": target_height,
                "bearing": None if b_s is None else round(b_s, 1),
                "heading": None if psi_p is None else round(psi_p, 1),
                "target": None if tx is None else {"x": round(tx, 2), "y": round(ty, 2)},
                "cmd": {"lr": lr, "fb": fb, "ud": ud, "yaw": yaw},
                "battery": 100 if drone.is_dry_run else battery_pct,
                "brace": {"ok": brace_ok, "acc": brace["acc"] if brace else None},
                "glove": {"ok": glove_ok, "clutch": glove["clutch"] if glove else 0},
                "gps": ({"fix": brace["fix"], "sats": brace["sats"], "lat": brace["lat"], "lon": brace["lon"],
                         "hacc": brace["hacc_m"], "speed": brace.get("speed"), "walking": gps_v, "used": gps_used}
                        if brace and "fix" in brace else None),
                "lock": vision.target_id, "people": len(vision.everyone),
                "calib": {"hfov": round(hfov, 1), "k_set": k_set, "c_set": c_align is not None},
                "interp": uplink.status(),
                "clients": hub.client_count,
            })
        if now - last_print > 1.0:
            last_print = now
            print(f"{state:30s} follow={following} flying={flying} brace={brace_ok} "
                  f"bearing={b_raw_last:+.1f} -> lr {lr:+d} fb {fb:+d} ud {ud:+d} yaw {yaw:+d}")

        # ---------- 5. keys and app commands ----------
        key = cv2.waitKey(1) & 0xFF
        for cmd in hub.poll_commands():
            action, value = cmd.get("action"), cmd.get("value", cmd.get("on"))
            if action == "radius" and value is not None:
                radius_m = L.clamp(float(value), C.RADIUS_MIN, C.RADIUS_MAX)
                hub.event(f"Radius {radius_m:.1f} m (app)")
            elif action == "radius_step" and value is not None:
                radius_m = L.clamp(radius_m + float(value), C.RADIUS_MIN, C.RADIUS_MAX)
                hub.event(f"Radius {radius_m:.1f} m (app)")
            elif action == "follow":
                following = bool(value)
            elif action == "orbit":
                orbiting = bool(value)
            elif action == "orbit_dir" and value is not None:
                orbit_dir = 1 if float(value) >= 0 else -1
            elif action == "watch":
                watch = bool(value)
            elif action == "gentle":
                gentle = bool(value)
            elif action == "height_step" and value is not None:
                target_height = int(L.clamp(target_height + float(value), C.HEIGHT_MIN_CM, C.HEIGHT_MAX_CM))
                hub.event(f"Height target {target_height} cm (app)")
            elif action == "indoor":
                C.apply_profile(bool(value))
            elif action in ("takeoff", "land", "emergency", "relock", "yawtest", "cal_angle", "cal_dist", "cal_align"):
                key = {"takeoff": ord("t"), "land": ord("l"), "emergency": ord("e"), "relock": ord(" "),
                       "yawtest": ord("y"), "cal_angle": ord("a"), "cal_dist": ord("k"), "cal_align": ord("c")}[action]
            if action in ("follow", "orbit", "orbit_dir", "watch", "gentle", "indoor"):
                hub.event(f"{action} = {value} (app)")
        if key == ord("t") and not flying:
            flying = drone.takeoff()
            hub.event("Take off" if flying else "Take off FAILED")
        elif key == ord("l") and flying:
            drone.land()
            flying = following = orbiting = False
            hub.event("Land")
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
        elif key in (ord("u"), ord("j")):
            step = C.HEIGHT_STEP_CM if key == ord("u") else -C.HEIGHT_STEP_CM
            target_height = int(L.clamp(target_height + step, C.HEIGHT_MIN_CM, C.HEIGHT_MAX_CM))
            hub.event(f"Height target {target_height} cm")
        elif key == ord("n"):
            C.apply_profile(not C.INDOOR)
            hub.event(f"Turning profile: {'INDOOR' if C.INDOOR else 'OUTDOOR'}")
        elif key == ord("h"):
            use_heading = not use_heading
        elif key == ord(" "):
            vision.relock()
        elif key == ord("y"):
            yaw_test_until = time.time() + 1.0
        elif key == ord("a"):
            if age < C.FRESH_S and abs(b_raw_last) < 4:
                cal_active, cal_psi0, cal_est, cal_bad = True, L.yaw_at(yaw_hist, time.time() - C.VIDEO_LAG_S), [], 0
                hub.event("Camera calibration: turn the drone slowly to one side until you near the edge")
            else:
                hub.event("Camera calibration: stand in view, centered, then press a")
        elif key == ord("k"):
            if last_det and age < C.FRESH_S:
                k_samples, k_until = [], time.time() + C.CAL_K_TIMEOUT_S
                hub.event(f"Distance calibration: hold still at {C.CAL_DIST_M:.0f} m, measuring...")
            else:
                hub.event(f"Distance calibration refused: stand {C.CAL_DIST_M:.0f} m away, whole body in view")
        elif key == ord("c"):
            if d_s is not None and age < C.FRESH_S and psi_p is not None:
                c_align = L.alignment_constant(psi_d, b_s, psi_p)
                hub.event(f"Headings aligned: C = {c_align:.1f}")
            else:
                hub.event("Can't align: need you in view and brace data")
        elif key == ord("e"):
            drone.emergency()
            flying = following = orbiting = False
            hub.event("EMERGENCY STOP")
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
