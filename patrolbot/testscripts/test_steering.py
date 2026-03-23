from _common import refuse_if_service_running
from patrolbot.config import load_config
from patrolbot.logging_setup import setup_logging
from patrolbot.hardware.steering import SteeringController
import time

refuse_if_service_running()
config = load_config()
logger = setup_logging(config)
s = SteeringController(config, logger)

for fn in [s.center, s.left, s.center, s.right, s.center]:
    fn()
    time.sleep(0.8)
