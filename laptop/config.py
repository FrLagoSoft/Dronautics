"""config.py - every setting in one place, grouped by system.
Values here are starting points; calibration keys (a, k, c) adjust some of them live."""

# ---------- run ----------
DRY_RUN = False           # True = webcam stands in for the drone, nothing flies
LOOP_HZ = 20              # control loop rate (commands per second)

# ---------- base station link ----------
SERIAL_PORT = "COM9"      # the base station XIAO's port (check in the Arduino IDE)
BAUD = 115200
LINK_TIMEOUT = 1.0        # seconds without packets = link lost
LOG_PATH = "brace_log.csv"

# ---------- signs (calibration checks 1 and 2: both headings must grow clockwise) ----------
DRONE_YAW_SIGN = 1
BRACE_SIGN = 1

# ---------- vision ----------
MODEL_PATH = "yolo11n.pt"
CONF = 0.4                # detection confidence; lower finds you more often in dim light
IMGSZ = 416               # smaller = faster detection
HFOV_DEG = 70.0           # camera's horizontal view, until auto-calibrated (key a)
CAL_SAMPLES = 15          # samples for the camera-angle auto-calibration
CAL_DIST_M = 2.0          # stand this far away and press k
K_DEFAULT = 1.1           # distance constant from box HEIGHT, until you press k
KW_DEFAULT = 0.5          # distance constant from box WIDTH, until you press k
CLIP_MARGIN = 0.02        # box within 2% of top/bottom edge = cut off -> use width
VIDEO_LAG_S = 0.30        # how old a frame is when it arrives
LOCK_MATCH = 0.55         # score needed to re-adopt the locked person (color + position)

# ---------- leash geometry ----------
LEASH_ANGLE = 0.0         # 0 = in front of you, 180 = behind you
R_INDOOR_MAX = 2.5        # caps the brace radius indoors (m)
D_MIN = 1.0               # never closer than this (m)
USE_BRACE_HEADING = True  # False = just keep distance in front of you

# ---------- control ----------
POS_GAIN = 20.0           # rc speed per meter of distance to the target
POS_DEADBAND = 0.30       # m: closer than this to the target = hold still
POS_MAX = 35              # top forward/back/sideways speed
POS_SLEW = 8              # max change of lr/fb per loop (no jerks)
YAW_PER_DEG = 3.0         # turning speed per degree you're off-center
YAW_DEADBAND = 5.0        # degrees: closer to center than this = no turn
YAW_MIN = 10              # smallest turn command sent
YAW_MAX = 90
YAW_FF = 0.2              # lead: extra turn per deg/s you're moving across the view
SMOOTH = 0.25             # blend for new distance/bearing measurements
SMOOTH_PHI = 0.3          # blend for your facing angle
GENTLE_SCALE = 0.5        # gentle mode scales forward/back/sideways (not turning)

# ---------- orbit ----------
ORBIT_SPEED = 20          # sideways speed while orbiting
ORBIT_YAW_FF = 12         # extra turn toward the center while orbiting

# ---------- losing and finding you ----------
FRESH_S = 0.5             # seen within this = normal control
HOLD_S = 1.5              # then look ahead along your path until this
SEARCH_S = 6.0            # then search toward the side you left until this; then hover
LOOK_LEAD_MAX = 60        # HOLD: how far ahead of the last spot it may look (deg)
SEARCH_SWEEP = 120        # SEARCH: how far past the last spot it looks (deg)
SEARCH_YAW = 30           # SEARCH: turning speed

# ---------- safety ----------
LOW_BATTERY = 20          # % -> land

# ---------- glove (manual control while the clutch is held) ----------
TILT_DEADBAND = 8         # degrees of hand tilt to ignore
TILT_GAIN = 1.5           # speed per degree beyond the deadband
TILT_MAX = 40
GLOVE_PITCH_SIGN = 1      # flip to -1 if tilting forward flies backward
GLOVE_ROLL_SIGN = 1       # flip to -1 if tilting right slides left
