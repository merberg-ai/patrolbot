from __future__ import annotations

from patrolbot.services.network_manager import NetworkManager


class NetworkStatusService:
    def __init__(self, logger):
        self.logger = logger
        self.manager = NetworkManager(logger)

    def get_status(self) -> dict:
        try:
            status = self.manager.get_status()
            status.setdefault('connected', False)
            status.setdefault('ssid', None)
            status.setdefault('ip', '127.0.0.1')
            status.setdefault('error', None)
            return status
        except Exception as exc:
            return {
                'connected': False,
                'ssid': None,
                'ip': '127.0.0.1',
                'error': str(exc),
            }
