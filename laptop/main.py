"""main.py - Drone Leash laptop brain. STEP 1 of 6: hear the brace.

Run:  .venv\\Scripts\\python.exe main.py      (Ctrl+C to stop)
Close the Arduino Serial Monitor first: only one program can use the port.
"""
import time

import config
from brace_link import BraceLink


def brace_line(p, ok):
    if p is None:
        return "brace: no packets yet"
    gps = (f"GPS fix {p['fix']} sats {p['sats']} {p['lat']:.6f},{p['lon']:.6f} +/-{p['hacc_m']:.1f} m"
           if "fix" in p else "GPS: not in packet")
    return (f"brace {'OK  ' if ok else 'LOST'} | heading {p['heading']:6.1f} acc {p['acc']} | "
            f"radius {p['radius']:2d} m btn {p['btn']} | {gps}")


def glove_line(g, ok):
    if g is None:
        return None
    return (f"glove {'OK  ' if ok else 'LOST'} | roll {g['roll']:+6.1f} pitch {g['pitch']:+6.1f} | "
            f"clutch {g['clutch']} pads {g['pads']}")


def main():
    link = BraceLink()
    print(f"Listening on {config.SERIAL_PORT}...")
    try:
        while True:
            if not link.connected:
                print(f"waiting for the base station on {config.SERIAL_PORT}...")
            else:
                p, p_ok = link.get("P")
                g, g_ok = link.get("G")
                print(brace_line(p, p_ok))
                gl = glove_line(g, g_ok)
                if gl:
                    print(gl)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
