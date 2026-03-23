from _common import refuse_if_service_running
from patrolbot.config import load_config
from patrolbot.logging_setup import setup_logging
from patrolbot.hardware.camera_servo import CameraServoController
import time

refuse_if_service_running()
config = load_config()
logger = setup_logging(config)
c = CameraServoController(config, logger)
c.home()
time.sleep(0.8)
c.pan_left()
time.sleep(0.8)
c.pan_right()
time.sleep(0.8)
c.tilt_up()
time.sleep(0.8)
c.tilt_down()
time.sleep(0.8)
c.home()
