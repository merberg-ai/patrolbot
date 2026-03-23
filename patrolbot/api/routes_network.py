from __future__ import annotations

from flask import Flask, current_app, request
from patrolbot.services.network_manager import NetworkManager

def register_network_routes(app: Flask) -> None:
    @app.get('/api/network/status')
    def get_network_status():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        nm = NetworkManager(runtime.logger)
        status = nm.get_status()
        status['ok'] = True
        return status

    @app.get('/api/network/scan')
    def scan_networks():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        nm = NetworkManager(runtime.logger)
        networks = nm.scan_networks()
        return {'ok': True, 'networks': networks}

    @app.post('/api/network/connect')
    def connect_network():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        ssid = payload.get('ssid')
        password = payload.get('password', '')
        
        nm = NetworkManager(runtime.logger)
        result = nm.connect(ssid, password)
        return result
