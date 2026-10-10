"""leash.py - all the math, as pure functions (no camera, no drone, no hardware).
Frame: the drone's own. x out of its nose, y to its right, angles clockwise, meters.
See "Drone Leash: Build Logic and Math" for every formula here."""
import math

import config as C


# ---------- helpers ----------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def wrap180(a):
    """Angle to -180..180 degrees."""
    return (a + 180) % 360 - 180


def slew(value, prev, step=C.POS_SLEW):
    """Limit how fast a command may change per loop."""
    return int(clamp(value, prev - step, prev + step))


def yaw_at(history, t_query):
    """Drone yaw at an earlier moment, from (time, yaw) samples (nearest at or before)."""
    best = None
    for t_s, psi in history:
        if t_s <= t_query:
            best = psi
        else:
            break
    return best if best is not None else (history[0][1] if history else 0.0)


# ---------- camera measurement ----------
def bearing_from_offset(offset, hfov_deg):
    """Box offset (-1 left .. +1 right) -> bearing in degrees, right = positive."""
    return math.degrees(math.atan(offset * math.tan(math.radians(hfov_deg / 2))))


def distance_from_box(size_h, size_w, clipped, k_h, k_w):
    """Height is the better ruler; once the box is cut off at the frame edge, width takes over."""
    return k_w / max(size_w, 1e-3) if clipped else k_h / max(size_h, 1e-3)


def hfov_estimate(delta_deg, offset):
    """Camera-angle calibration: after the drone turns delta_deg, you appear at offset.
    Returns (estimate in degrees or None, sign_ok). Turning right must push you LEFT."""
    if not (0.3 < abs(offset) < 0.95 and abs(delta_deg) > 5):
        return None, True
    est = 2 * math.degrees(math.atan(abs(math.tan(math.radians(delta_deg))) / abs(offset)))
    if not 40 < est < 120:
        return None, True
    return est, offset * delta_deg < 0


# ---------- the vector leash ----------
def facing_in_drone_frame(psi_p, psi_d, c_align):
    """Your facing angle seen from the drone: phi = heading - drone yaw + C."""
    return wrap180(psi_p - psi_d + c_align)


def alignment_constant(psi_d0, beta0, psi_p0):
    """C, captured while you face the drone and it faces you."""
    return psi_d0 + beta0 + 180 - psi_p0


def target_point(d, b, phi, r, alpha=C.LEASH_ANGLE):
    """Person P and target T in the drone's frame: T = P + r(cos(phi+alpha), sin(phi+alpha))."""
    px, py = d * math.cos(math.radians(b)), d * math.sin(math.radians(b))
    a = math.radians(phi + alpha)
    return px, py, px + r * math.cos(a), py + r * math.sin(a)


def position_commands(d, px, py, tx, ty):
    """Target -> (lr, fb). Too close: the only allowed motion is straight away from you."""
    if d < C.D_MIN:
        away = C.D_MIN - d
        ex, ey = -px / d * away, -py / d * away
    elif math.hypot(tx, ty) < C.POS_DEADBAND:
        ex, ey = 0.0, 0.0
    else:
        ex, ey = tx, ty
    fb = int(round(clamp(C.POS_GAIN * ex, -C.POS_MAX, C.POS_MAX)))
    lr = int(round(clamp(C.POS_GAIN * ey, -C.POS_MAX, C.POS_MAX)))
    return lr, fb


def yaw_command(b):
    """Bearing -> turn command: dead zone in the middle, never too small to act on."""
    if abs(b) < C.YAW_DEADBAND:
        return 0
    y = clamp(C.YAW_PER_DEG * b, -C.YAW_MAX, C.YAW_MAX)
    if abs(y) < C.YAW_MIN:
        y = C.YAW_MIN if y > 0 else -C.YAW_MIN
    return int(round(y))


def leash_yaw(b_now, world_rate):
    """Turn toward your current bearing, plus a lead in the direction you're moving."""
    return int(clamp(yaw_command(b_now) + C.YAW_FF * world_rate, -C.YAW_MAX, C.YAW_MAX))


def orbit_commands(d, r, b_now, direction):
    """Circle at radius r: slide sideways, hold distance, pre-turn toward the center.
    Returns (lr, fb, yaw); direction +1 = right, -1 = left."""
    if d < C.D_MIN:
        return 0, -C.POS_MAX // 2, yaw_command(b_now)
    lr = direction * C.ORBIT_SPEED
    err = d - r
    fb = 0 if abs(err) < C.POS_DEADBAND else int(round(clamp(C.POS_GAIN * err, -C.POS_MAX, C.POS_MAX)))
    yaw = int(clamp(yaw_command(b_now) - direction * C.ORBIT_YAW_FF, -C.YAW_MAX, C.YAW_MAX))
    return lr, fb, yaw


# ---------- losing and finding you ----------
def lost_behavior(age, seen_bearing, psi_d, world_rate, exit_dir):
    """While you're out of view: (state, yaw). HOLD looks ahead along your path,
    SEARCH turns toward the side you left, LOST hovers."""
    if age < C.HOLD_S:
        lead = clamp(world_rate * age, -C.LOOK_LEAD_MAX, C.LOOK_LEAD_MAX)
        return "HOLD: looking where you were going", yaw_command(wrap180(seen_bearing + lead - psi_d))
    if age < C.SEARCH_S:
        err = wrap180(seen_bearing + exit_dir * C.SEARCH_SWEEP - psi_d)
        yaw = 0 if abs(err) < C.YAW_DEADBAND else (C.SEARCH_YAW if err > 0 else -C.SEARCH_YAW)
        return f"SEARCH {'right' if exit_dir > 0 else 'left'}: looking where you left", yaw
    return "LOST: hover", 0


# ---------- glove ----------
def tilt_to_speed(deg):
    if abs(deg) < C.TILT_DEADBAND:
        return 0
    return int(clamp(C.TILT_GAIN * (abs(deg) - C.TILT_DEADBAND), 0, C.TILT_MAX)) * (1 if deg > 0 else -1)


def glove_commands(glove):
    """Glove packet -> (lr, fb, ud, yaw). Index pad: sideways tilt turns. Middle pad: forward tilt climbs."""
    pitch_cmd = tilt_to_speed(C.GLOVE_PITCH_SIGN * glove["pitch"])
    roll_cmd = tilt_to_speed(C.GLOVE_ROLL_SIGN * glove["roll"])
    lr = fb = ud = yaw = 0
    if glove["pads"] & 2:
        ud = pitch_cmd
    else:
        fb = pitch_cmd
    if glove["pads"] & 1:
        yaw = roll_cmd
    else:
        lr = roll_cmd
    return lr, fb, ud, yaw
