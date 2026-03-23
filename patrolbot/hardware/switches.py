from __future__ import annotations
class SwitchController:
    def __init__(self, config: dict, logger): self.config = config; self.logger = logger; self.states = {int(pin): False for pin in config['switches']['pins']}
    def set_switch(self, pin: int, state: bool) -> None: self.states[int(pin)] = bool(state); self.logger.info('Switch %s set to %s', pin, state)
    def all_off(self) -> None:
        for pin in list(self.states): self.states[pin] = False
        self.logger.info('All switches off')
