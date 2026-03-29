from __future__ import annotations

import threading


class StatusLedService:
    PRIORITY = {
        'BATTERY_CRITICAL': 100,
        'ERROR': 90,
        'WIFI_ERROR': 80,
        'TRAPPED': 70,
        'OBSTACLE_DETECTED': 60,
        'VISION_ACTIVE': 55,
        'PATROL_ACTIVE': 50,
        'WIFI_CONNECTED': 40,
        'READY': 30,
        'BOOTING': 10,
        'OFF': 0,
    }

    def __init__(self, lights, state, config: dict, logger):
        self.lights = lights
        self.state = state
        self.config = config
        self.logger = logger
        self.colors = config['lights']['colors']
        self.current_state = 'OFF'
        self.custom_color = None
        self.battery_critical = False
        self._pattern = None
        self._stop_event = threading.Event()
        self._blink_thread = None

    def _start_pattern(self, pattern: str) -> None:
        if self._pattern == pattern and self._blink_thread and self._blink_thread.is_alive():
            return
        self._stop_pattern()
        self._pattern = pattern
        self._stop_event.clear()
        self._blink_thread = threading.Thread(target=self._blink_loop, name='patrolbot-led-pattern', daemon=True)
        self._blink_thread.start()

    def _stop_pattern(self) -> None:
        self._stop_event.set()
        self._blink_thread = None
        self._pattern = None

    def _blink_loop(self) -> None:
        import time
        lights_cfg = self.config.get('lights', {})
        critical_interval = float(lights_cfg.get('critical_blink_interval_s', 0.5))
        police_interval = float(lights_cfg.get('police_interval_s', 0.25))
        red = self.colors.get('battery_critical', [255, 0, 0])
        blue = self.colors.get('police_blue', [0, 0, 255])
        amber = self.colors.get('obstacle_detected', [255, 180, 0])
        purple = self.colors.get('trapped', [255, 0, 120])
        off = self.colors.get('off', [0, 0, 0])
        left_red = True
        while not self._stop_event.is_set():
            pattern = self._pattern
            if pattern == 'BATTERY_CRITICAL':
                self.lights.set_both(*red)
                self.state.led_state = 'BATTERY_CRITICAL'
                if self._stop_event.wait(critical_interval):
                    break
                self.lights.set_both(*off)
                if self._stop_event.wait(critical_interval):
                    break
            elif pattern == 'POLICE':
                if left_red:
                    self.lights.set_left(*red); self.lights.set_right(*blue)
                else:
                    self.lights.set_left(*blue); self.lights.set_right(*red)
                left_red = not left_red
                self.state.led_state = 'POLICE'
                if self._stop_event.wait(police_interval):
                    break
            elif pattern == 'TRAPPED':
                self.lights.set_both(*purple)
                if self._stop_event.wait(critical_interval):
                    break
                self.lights.set_both(*amber)
                if self._stop_event.wait(critical_interval):
                    break
            else:
                break

    def set_state(self, state_name: str, reason: str | None = None, force: bool = False) -> None:
        state_name = (state_name or 'OFF').upper()
        if not force:
            current_priority = self.PRIORITY.get(self.current_state, 0)
            next_priority = self.PRIORITY.get(state_name, 0)
            if current_priority > next_priority and state_name not in {'READY', 'OFF'}:
                return
        self.current_state = state_name
        self.state.status_led_reason = reason
        if self.current_state != 'CUSTOM':
            self.custom_color = None
        self.apply()

    def set_custom_color(self, r: int, g: int, b: int) -> None:
        self.current_state = 'CUSTOM'
        self.custom_color = [int(r), int(g), int(b)]
        self.apply()

    def set_battery_critical(self, active: bool) -> None:
        active = bool(active)
        if self.battery_critical == active:
            return
        self.battery_critical = active
        self.apply()

    def apply_runtime_status(self, runtime) -> None:
        state = runtime.state
        if self.battery_critical:
            self.set_state('BATTERY_CRITICAL', reason='battery critical', force=True)
            return
        if not state.network_connected:
            self.set_state('WIFI_ERROR', reason='wifi disconnected', force=True)
            return
        if state.patrol_drive_state == 'trapped':
            self.set_state('TRAPPED', reason='patrol trapped', force=True)
            return
        if state.patrol_drive_state == 'obstacle_detected':
            self.set_state('OBSTACLE_DETECTED', reason='obstacle detected', force=True)
            return
        if state.vision_enabled:
            self.set_state('VISION_ACTIVE', reason='vision active', force=True)
            return
        if state.patrol_enabled:
            self.set_state('PATROL_ACTIVE', reason='patrol active', force=True)
            return
        if state.network_connected:
            self.set_state('READY', reason='ready', force=True)
            return
        self.set_state('OFF', reason='idle', force=True)

    def apply(self) -> None:
        if self.battery_critical:
            self.state.led_state = 'BATTERY_CRITICAL'
            self.state.led_custom = None
            self._start_pattern('BATTERY_CRITICAL')
            return

        if self.current_state == 'POLICE':
            self.state.led_state = 'POLICE'
            self.state.led_custom = None
            self._start_pattern('POLICE')
            return

        if self.current_state == 'TRAPPED':
            self.state.led_state = 'TRAPPED'
            self.state.led_custom = None
            self._start_pattern('TRAPPED')
            return

        self._stop_pattern()

        if self.current_state == 'CUSTOM' and self.custom_color is not None:
            color = self.custom_color
        else:
            color = self.colors.get(self.current_state.lower(), self.colors.get('off', [0, 0, 0]))

        self.lights.set_both(*color)
        self.state.led_state = self.current_state
        self.state.led_custom = None if self.custom_color is None else {'r': color[0], 'g': color[1], 'b': color[2]}

    def close(self) -> None:
        self._stop_pattern()
