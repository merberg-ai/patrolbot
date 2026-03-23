from __future__ import annotations
from flask import Flask, current_app, request

def register_lights_routes(app: Flask) -> None:
    @app.post('/api/lights/off')
    def lights_off():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        runtime.status_leds.set_state('OFF')
        return {'ok': True, 'state': 'OFF'}

    @app.post('/api/lights/color')
    def lights_color():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        r, g, b = int(payload.get('r', 0)), int(payload.get('g', 0)), int(payload.get('b', 0))
        runtime.status_leds.set_custom_color(r, g, b)
        return {'ok': True, 'state': 'CUSTOM', 'color': {'r': r, 'g': g, 'b': b}}

    @app.post('/api/lights/state')
    def lights_state():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        state = str(payload.get('state', 'READY')).upper()
        runtime.status_leds.set_state(state)
        return {'ok': True, 'state': runtime.state.led_state}
