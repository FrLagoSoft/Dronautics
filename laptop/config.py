"""config.py - every setting in one place. Later steps add their sections here."""

# ---------- base station link ----------
SERIAL_PORT = "COM9"      # the base station XIAO's port (check in the Arduino IDE)
BAUD = 115200
LINK_TIMEOUT = 1.0        # seconds without packets = link lost
LOG_PATH = "brace_log.csv"
