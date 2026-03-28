from __future__ import annotations

from flask import Flask, current_app, request
from patrolbot.services.network_manager import NetworkManager


def _sync_runtime_network(runtime, result: dict) -> None:
    runtime.state.network_connected = bool(result.get('connected', runtime.state.network_connected))
    runtime.state.network_ssid = result.get('ssid', runtime.state.network_ssid)
    runtime.state.network_ip = result.get('ip', runtime.state.network_ip)
    runtime.state.network_last_error = result.get('error')
    if runtime.telemetry:
        runtime.telemetry.poll_once()


def register_network_routes(app: Flask) -> None:
    @app.get('/api/network/status')
    def get_network_status():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        nm = NetworkManager(runtime.logger)
        status = nm.get_status()
        status['ok'] = True
        _sync_runtime_network(runtime, status)
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
        if result.get('ok'):
            status = nm.get_status()
            result.update({'connected': status.get('connected'), 'ssid': status.get('ssid'), 'ip': status.get('ip')})
            _sync_runtime_network(runtime, result)
        else:
            runtime.state.network_last_error = result.get('error')
        return result
