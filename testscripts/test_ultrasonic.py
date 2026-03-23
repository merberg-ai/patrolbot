from _common import refuse_if_service_running; from patrolbot.config import load_config; from patrolbot.logging_setup import setup_logging; from patrolbot.hardware.ultrasonic import UltrasonicSensor
refuse_if_service_running(); config=load_config(); logger=setup_logging(config); u=UltrasonicSensor(config, logger); print(f'Distance: {u.read_cm()} cm')
