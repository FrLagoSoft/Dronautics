"""drone.py - the Tello, or the webcam standing in for it, behind one interface.

Both offer: frame(), yaw(), send(lr, fb, ud, yaw), takeoff(), land(), emergency(),
battery(), close(). Commands are -100..100. yaw() already applies DRONE_YAW_SIGN.
"""
import logging

import cv2

import config as C


class DryRunDrone:
    """Webcam instead of the drone. Nothing flies; yaw stays 0."""
    is_dry_run = True

    def __init__(self):
        self.cam = cv2.VideoCapture(0)

    def frame(self):
        ok, img = self.cam.read()
        return img if ok else None

    def yaw(self):
        return 0.0

    def send(self, lr, fb, ud, yaw):
        pass

    def takeoff(self):
        return True

    def land(self):
        pass

    def emergency(self):
        pass

    def battery(self):
        return 100

    def close(self):
        self.cam.release()


class TelloDrone:
    is_dry_run = False

    def __init__(self):
        from djitellopy import Tello

        class HideRcSpam(logging.Filter):  # rc commands go out 20x a second; keep the terminal readable
            def filter(self, record):
                return "'rc " not in record.getMessage()

        self.tello = Tello()
        self.tello.connect()
        Tello.LOGGER.addFilter(HideRcSpam())
        print("Battery:", self.tello.get_battery(), "%")
        self.tello.streamon()
        self.reader = self.tello.get_frame_read()

    def frame(self):
        img = self.reader.frame
        # djitellopy delivers RGB; OpenCV expects BGR. If colors look wrong, remove the conversion.
        return None if img is None else cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def yaw(self):
        return C.DRONE_YAW_SIGN * float(self.tello.get_yaw())

    def send(self, lr, fb, ud, yaw):
        self.tello.send_rc_control(int(lr), int(fb), int(ud), int(yaw))

    def takeoff(self):
        try:
            self.tello.takeoff()
            return True
        except Exception as err:
            print(f"TAKEOFF FAILED: {err!r}  battery {self.tello.get_battery()}%  "
                  f"temperature {self.tello.get_temperature():.0f} C")
            return False

    def land(self):
        self.tello.land()

    def emergency(self):
        self.tello.emergency()

    def battery(self):
        return self.tello.get_battery()

    def close(self):
        self.tello.streamoff()
        self.tello.end()


def make_drone():
    return DryRunDrone() if C.DRY_RUN else TelloDrone()
