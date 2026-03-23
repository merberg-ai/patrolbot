from __future__ import annotations
import socket
class NetworkStatusService:
    def get_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('8.8.8.8', 80)); return s.getsockname()[0]
        except OSError:
            return '127.0.0.1'
