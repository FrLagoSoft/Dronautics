"""config.py - THIS IS THE HUB WHERE EVERYTHING EXISTS. LIKE SERIOUSLY. EVERY SETTING IS HERE. 
Values here are starting points; calibration keys (a, k, c) adjust some of them live."""
import os

# ---------- run ----------
DRY_RUN = False          # True = webcam stands in for the drone, nothing flies (This is just a test tool, nothing serious)
LOOP_HZ = 20              # control loop rate (commands per second). Remember how it's said it takes 20 commands / second? it's true! 

# ---------- base station link ----------
SERIAL_PORT = "COM9"      # the base station XIAO's port (check in the Arduino IDE) THIS IS SPECIFIC TO YOUR COMPUTER. MINE WAS COM9, CAUSE I WANTED TO.
BAUD = 115200
LINK_TIMEOUT = 1.0        # seconds without packets = link lost. You can turn this up if you want to, but I don't think it's a good idea.
LOG_PATH = "brace_log.csv"

# ---------- signs (calibration checks 1 and 2: both headings must grow clockwise) ----------
DRONE_YAW_SIGN = 1 #This basically just spins the drone in the opposite direction of the brace, just to calibrate the drone
BRACE_SIGN = 1

# ---------- vision ---------- All of these variables will be commented on for their usage, here you go: 
MODEL_PATH = "yolo11n.pt"
CONF = 0.4                # detection confidence; lower finds you more often in dim light
IMGSZ = 416               # smaller = faster detection
HFOV_DEG = 70.0           # camera's horizontal view, until auto-calibrated (key a)
CAL_SAMPLES = 15          # samples for the camera-angle auto-calibration
CAL_DIST_M = 2.0          # stand this far away and press k
CAL_K_FRAMES = 12         # k measures over this many frames (~1 s) and takes the median
CAL_K_TIMEOUT_S = 3.0     # give up if it can't collect them in this long
CAL_K_MAX_SPREAD = 0.12   # box height may vary this much (12%) during the measurement
CAL_K_MAX_SPREAD_W = 0.20 # box width varies more (arms), so it gets more slack when calibrating from width
K_DEFAULT = 1.1           # distance constant from box HEIGHT, until you press k
KW_DEFAULT = 0.5          # distance constant from box WIDTH, until you press k
CLIP_MARGIN = 0.02        # box within 2% of top/bottom edge = cut off -> use width
VIDEO_LAG_S = 0.30        # how old a frame is when it arrives
LOCK_MATCH = 0.55         # score needed to re-adopt the locked person (color + position)
LOCK_LOST_S = 1.5         # tracker lost them and nobody matches for this long -> re-lock on whoever is nearest
SIG_REFRESH_S = 0.5       # how often the remembered torso colors blend toward what's seen now

# ---------- leash geometry ----------
LEASH_ANGLE = 0.0         # 0 = in front of you, 180 = behind you
RADIUS_START = 2.5        # leash radius at startup (m), same as the old fixed value. The laptop owns it:
RADIUS_STEP = 0.4         #   each brace press or app IN/OUT changes it by this much,
RADIUS_MIN = 1.3          #   and it always stays inside these limits.
RADIUS_MAX = 4.0
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

# ---------- altitude hold (adjust live: keys u / j, or the height buttons in the app) ----------
TARGET_HEIGHT_CM = 130    # the Tello hovers ~80-100 cm after takeoff; this lifts it to about chest height
HEIGHT_STEP_CM = 10       # each u / j / app press moves the target by this much
HEIGHT_MIN_CM = 60        # never hold lower than this
HEIGHT_MAX_CM = 200       # never higher (indoor ceilings are ~240-270 cm)
HEIGHT_GAIN = 0.6         # up/down speed per cm of height error
HEIGHT_DEADBAND_CM = 8    # closer than this to the target = no up/down
HEIGHT_MAX_UD = 30        # top climb/descend speed

# ---------- GPS walking speed (outdoors only; indoors there's no fix and this switches itself off) ----------
GPS_FIX_MIN = 2           # 2 = 2D fix or better
GPS_SACC_MAX = 0.6        # m/s: ignore speed readings less certain than this
GPS_WALK_MIN = 0.35       # m/s: slower than this = standing (GPS speed jitters around 0.1-0.2)
GPS_FF_RC_PER_MPS = 30    # follow lead: rc command per m/s you walk (tune outdoors)
GPS_FF_MAX = 25           # the lead never adds more than this
GPS_DR_MAX_S = 6.0        # lost you: keep turning toward where GPS says you walked for this long

# ---------- brace feedback (buzzes sent through the base station; DRV2605 effect numbers) ----------
BUZZ_LOCKED = 12          # Triple Click: locked onto you (after the brace "lock onto me" hold)
BUZZ_LOST = 52            # Pulsing Strong: lost you (it has started searching)
BUZZ_FOLLOW_ON = 58       # Transition Click: follow switched on
BUZZ_FOLLOW_OFF = 7       # Soft Bump: follow switched off
LOCK_REQUEST_TIMEOUT_S = 3.0  # brace lock request with nobody in view gives up after this

# ---------- safety ----------
LOW_BATTERY = 20          # % -> land

# ---------- glove (manual control while the clutch is held) ----------
TILT_DEADBAND = 8         # degrees of hand tilt to ignore
TILT_GAIN = 1.5           # speed per degree beyond the deadband
TILT_MAX = 40
GLOVE_PITCH_SIGN = 1      # flip to -1 if tilting forward flies backward
GLOVE_ROLL_SIGN = 1       # flip to -1 if tilting right slides left

# ---------- AMD display smoothing (amd/interp_server.py on the AMD GPU) ----------
INTERP_URL = "https://rc-132ae48ec40c2ebd.radeon.firstdg.ai"  # where the laptop sends frames; "" = off
INTERP_FPS = 12                                         # frames per second sent for smoothing
INTERP_TOKEN = os.environ.get("INTERP_TOKEN", "")    # the server's --key; set $env:INTERP_TOKEN before main.py
INTERP_KEY = INTERP_TOKEN    
INTERP_PUBLIC_URL = ""                                   # stream URL for the phone if different; "" = INTERP_URL

# ---------- indoor / outdoor turning (switch live: key n, or the INDOOR toggle in the app) ----------
# Indoors you barely move and short detection misses are common, so the drone waits longer before
# guessing, guesses less, and searches a smaller arc. Outdoors keeps the original, more predictive values.
# I did this feature partly due to how many people are indoors when places are crowded. So. 
INDOOR = True             # profile at startup
PROFILES = {
    "indoor": dict(FRESH_S=1.0, LOOK_LEAD_MAX=15, YAW_FF=0.1, SEARCH_SWEEP=45, SEARCH_YAW=20, WORLD_RATE_MAX=45),
    "outdoor": dict(FRESH_S=0.5, LOOK_LEAD_MAX=60, YAW_FF=0.2, SEARCH_SWEEP=120, SEARCH_YAW=30, WORLD_RATE_MAX=120),
}

#Local profile override for multiple profile usage, if you switch IP ports often
def apply_profile(indoor):
    """Overwrite the turning settings above with one profile. Everything reads them live, so this
    takes effect on the next control loop."""
    global INDOOR
    INDOOR = bool(indoor)
    globals().update(PROFILES["indoor" if INDOOR else "outdoor"])


apply_profile(INDOOR)
