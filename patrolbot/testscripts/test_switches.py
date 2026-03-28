from _common import refuse_if_service_running; from patrolbot.config import load_config; from patrolbot.logging_setup import setup_logging; from patrolbot.hardware.switches import SwitchController; import time
refuse_if_service_running(); config=load_config(); logger=setup_logging(config); s=SwitchController(config, logger)
for pin in config['switches']['pins']: s.set_switch(pin, True); time.sleep(.4); s.set_switch(pin, False)
s.all_off()
