from __future__ import annotations
class HatContext:
    def __init__(self, config: dict, logger):
        self.config = config; self.logger = logger; self.initialized = False
    def initialize(self) -> None:
        self.logger.info('Initializing shared HAT context'); self.initialized = True
    def close(self) -> None:
        if self.initialized:
            self.logger.info('Closing shared HAT context'); self.initialized = False
