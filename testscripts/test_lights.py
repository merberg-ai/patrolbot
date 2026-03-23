from _common import refuse_if_service_running
from patrolbot.config import load_config
from patrolbot.logging_setup import setup_logging
from patrolbot.hardware.lights import RgbEyes
import time

refuse_if_service_running()
config = load_config()
logger = setup_logging(config)
lights = RgbEyes(config, logger)
lights.initialize()
for color in [
    (0, 0, 0),
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 255),
    (255, 180, 0),
    (0, 0, 0),
]:
    lights.set_both(*color)
    time.sleep(0.8)
lights.close()
