from __future__ import annotations

import threading
import time
from typing import Optional


try:
    import evdev
except ImportError:
    evdev = None


class GamepadService:
    """
    Background service that scans for and connects to a Bluetooth/USB gamepad.

    Intended default mapping for patrolbot:
      - Left stick X: steering left/right
      - Left stick click: center steering
      - Left trigger: brake / reverse
      - Right trigger: accelerate forward
      - Right stick: camera pan / tilt
      - Right stick click: camera home

    The previous implementation had three big problems:
      1) forward/reverse defaults were swapped,
      2) trigger values assumed a fixed 0..1023 range,
      3) stick motion ignored steering/camera invert + center config and used
         hardcoded 90-degree math.

    This version learns axis ranges from evdev, normalizes safely, and maps
    stick position directly to servo targets with light smoothing.
    """

    DEFAULT_MAPPING = {
        'throttle_fwd': 'ABS_RZ',       # Right Trigger
        'throttle_rev': 'ABS_Z',        # Left Trigger
        'steering': 'ABS_X',            # Left Stick X
        'pan': 'ABS_RX',                # Right Stick X
        'tilt': 'ABS_RY',               # Right Stick Y
        'pan_left': None,
        'pan_right': None,
        'tilt_up': None,
        'tilt_down': None,
        'estop_toggle': 'BTN_B',
        'lights_toggle': 'BTN_A',       # A button
        'tracking_toggle': None,        # Empty by default
        'camera_home': None,
        'steering_center': None
    }

    KEY_ALIASES = {
        'BTN_A': 'BTN_SOUTH', 'BTN_SOUTH': 'BTN_A',
        'BTN_B': 'BTN_EAST',  'BTN_EAST': 'BTN_B',
        'BTN_X': 'BTN_NORTH', 'BTN_NORTH': 'BTN_X',
        'BTN_Y': 'BTN_WEST',  'BTN_WEST': 'BTN_Y',
        'BTN_TR2': 'BTN_TR',  'BTN_TR': 'BTN_TR2',
        'BTN_TL2': 'BTN_TL',  'BTN_TL': 'BTN_TL2',
        'BTN_SELECT': 'BTN_BACK', 'BTN_BACK': 'BTN_SELECT',
        'BTN_START': 'BTN_MODE', 'BTN_MODE': 'BTN_START',
        'BTN_GUIDE': 'BTN_HOME', 'BTN_HOME': 'BTN_GUIDE',
    }

    def __init__(self, runtime, logger):
        self.runtime = runtime
        self.logger = logger
        self._thread = None
        self._btn_thread = None
        self._stop_event = threading.Event()
        self.device: Optional[evdev.InputDevice] = None
        self._btn_held = set()

        cfg = self.runtime.config
        self.mapping = cfg.get('gamepad_mapping', self.DEFAULT_MAPPING.copy())
        self.stick_deadzone = int(cfg.get('gamepad_stick_deadzone', 8000))
        self.trigger_deadzone = float(cfg.get('gamepad_trigger_deadzone', 0.06))
        self.servo_update_rate_s = float(cfg.get('gamepad_servo_update_rate_s', 0.05))
        self.steering_alpha = float(cfg.get('gamepad_steering_alpha', 0.35))
        self.camera_alpha = float(cfg.get('gamepad_camera_alpha', 0.15))

        self.axis_state = {
            'ABS_X': 0, 'ABS_Y': 0,
            'ABS_RX': 0, 'ABS_RY': 0,
            'ABS_Z': 0, 'ABS_RZ': 0,
            'ABS_BRAKE': 0, 'ABS_GAS': 0,
            'ABS_HAT0X': 0, 'ABS_HAT0Y': 0,
        }
        self.axis_info: dict[str, tuple[int, int, int]] = {}
        self.available_axes: list[str] = []
        self.available_buttons: list[str] = []
        self.last_device_scan: list[dict[str, object]] = []
        self.last_input_event: dict[str, object] | None = None
        self.last_servo_update = 0.0
        self._steer_target = None
        self._pan_target = None
        self._tilt_target = None
        self._last_motor_cmd: tuple[str, int] | None = None

    def start(self):
        if evdev is None:
            self.logger.warning("evdev not installed; gamepad support disabled.")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._connection_loop, name='patrolbot-gamepad', daemon=True)
        self._thread.start()
        self._btn_thread = threading.Thread(target=self._button_hold_loop, name='patrolbot-gamepad-btns', daemon=True)
        self._btn_thread.start()
        self.logger.info("Gamepad background service started.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread = None
        if self._btn_thread:
            self._btn_thread = None
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def _score_device(self, dev: evdev.InputDevice) -> tuple[int, dict[str, object]]:
        info: dict[str, object] = {
            'path': getattr(dev, 'path', ''),
            'name': getattr(dev, 'name', '') or 'Unknown input device',
            'score': 0,
            'axes': [],
            'buttons': [],
        }

        try:
            caps = dev.capabilities()
        except Exception as exc:
            info['error'] = str(exc)
            return 0, info

        name = str(info['name']).lower()
        if any(token in name for token in ('xbox', 'gamepad', 'controller', 'joystick')):
            info['score'] = int(info['score']) + 3

        abs_codes = []
        for entry in caps.get(evdev.ecodes.EV_ABS, []):
            code = entry[0] if isinstance(entry, tuple) else entry
            axis_name = evdev.ecodes.ABS.get(code)
            if isinstance(axis_name, list):
                axis_name = axis_name[0]
            if axis_name:
                abs_codes.append(axis_name)

        key_codes = []
        for entry in caps.get(evdev.ecodes.EV_KEY, []):
            code = entry[0] if isinstance(entry, tuple) else entry
            key_name = evdev.ecodes.KEY.get(code)
            if isinstance(key_name, list):
                key_name = key_name[0]
            if key_name:
                key_codes.append(key_name)

        info['axes'] = sorted(set(abs_codes))
        info['buttons'] = sorted(set(key_codes))

        preferred_axes = {
            'ABS_X': 2, 'ABS_Y': 2,
            'ABS_RX': 2, 'ABS_RY': 2,
            'ABS_Z': 2, 'ABS_RZ': 2,
            'ABS_GAS': 2, 'ABS_BRAKE': 2,
            'ABS_HAT0X': 1, 'ABS_HAT0Y': 1,
        }
        preferred_buttons = {
            'BTN_SOUTH': 1, 'BTN_A': 1, 'BTN_EAST': 1, 'BTN_B': 1,
            'BTN_THUMBL': 1, 'BTN_THUMBR': 1, 'BTN_TL': 1, 'BTN_TR': 1,
            'BTN_TL2': 1, 'BTN_TR2': 1, 'BTN_START': 1, 'BTN_SELECT': 1,
            'BTN_MODE': 1,
        }

        score = int(info['score'])
        for axis_name, points in preferred_axes.items():
            if axis_name in info['axes']:
                score += points
        for key_name, points in preferred_buttons.items():
            if key_name in info['buttons']:
                score += points

        if info['axes'] and info['buttons']:
            score += 2

        info['score'] = score
        return score, info

    def _find_gamepad(self) -> Optional[evdev.InputDevice]:
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        candidates: list[tuple[int, evdev.InputDevice, dict[str, object]]] = []
        scanned: list[dict[str, object]] = []

        for dev in devices:
            try:
                score, info = self._score_device(dev)
            except Exception as exc:
                score, info = 0, {
                    'path': getattr(dev, 'path', ''),
                    'name': getattr(dev, 'name', '') or 'Unknown input device',
                    'score': 0,
                    'error': str(exc),
                }

            scanned.append(info)
            if score > 0:
                candidates.append((score, dev, info))

        self.last_device_scan = sorted(scanned, key=lambda item: (int(item.get('score', 0)), str(item.get('name', ''))), reverse=True)

        if not candidates:
            self.available_axes = []
            self.available_buttons = []
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_dev, best_info = candidates[0]
        self._load_axis_info(best_dev)
        self.available_axes = list(best_info.get('axes', []))
        self.available_buttons = list(best_info.get('buttons', []))
        self.logger.info(
            "Gamepad connected: %s at %s (score=%s axes=%s buttons=%s)",
            best_dev.name,
            best_dev.path,
            best_score,
            self.available_axes,
            self.available_buttons,
        )
        return best_dev

    def _load_axis_info(self, dev: evdev.InputDevice) -> None:
        self.axis_info = {}
        self.available_axes = []
        self.available_buttons = []
        try:
            caps = dev.capabilities(absinfo=True)
            for code, absinfo in caps.get(evdev.ecodes.EV_ABS, []):
                axis_name = evdev.ecodes.ABS.get(code)
                if isinstance(axis_name, list):
                    axis_name = axis_name[0]
                if not axis_name:
                    continue
                minimum = int(getattr(absinfo, 'min', 0))
                maximum = int(getattr(absinfo, 'max', 0))
                flat = int(getattr(absinfo, 'flat', 0))
                self.axis_info[axis_name] = (minimum, maximum, flat)
                self.available_axes.append(axis_name)

            for entry in caps.get(evdev.ecodes.EV_KEY, []):
                code = entry[0] if isinstance(entry, tuple) else entry
                key_name = evdev.ecodes.KEY.get(code)
                if isinstance(key_name, list):
                    key_name = key_name[0]
                if key_name:
                    self.available_buttons.append(key_name)

            self.available_axes = sorted(set(self.available_axes))
            self.available_buttons = sorted(set(self.available_buttons))

            if self.axis_info:
                self.logger.info("Gamepad axis ranges detected: %s", self.axis_info)
        except Exception as exc:
            self.logger.warning("Unable to read gamepad axis ranges: %s", exc)
            self.axis_info = {}
            self.available_axes = []
            self.available_buttons = []

    def _connection_loop(self):
        while not self._stop_event.is_set():
            if self.device is None:
                try:
                    self.device = self._find_gamepad()
                    self._last_motor_cmd = None
                    self._steer_target = None
                    self._pan_target = None
                    self._tilt_target = None
                except Exception as e:
                    self.logger.warning("Error searching for gamepad: %s", e)

                if self.device is None:
                    self._stop_event.wait(3.0)
                    continue

            try:
                self._read_events()
            except (OSError, getattr(evdev, 'EvdevError', OSError)) as e:
                self.logger.warning("Gamepad disconnected or error reading: %s", e)
                try:
                    self.device.close()
                except Exception:
                    pass
                self.device = None
                self._stop_event.wait(1.0)
            except Exception as e:
                self.logger.exception("Unexpected error in gamepad loop: %s", e)
                self.device = None
                self._stop_event.wait(3.0)

    def _normalize_stick(self, axis_name: str, value: int) -> float:
        minimum, maximum, flat = self.axis_info.get(axis_name, (-32768, 32767, 0))
        center = (minimum + maximum) / 2.0
        magnitude = max(1.0, (maximum - minimum) / 2.0)
        deadzone = max(self.stick_deadzone, flat)
        offset = float(value) - center
        if abs(offset) <= deadzone:
            return 0.0
        out = offset / magnitude
        if out > 1.0:
            return 1.0
        if out < -1.0:
            return -1.0
        return out

    def _normalize_trigger(self, axis_name: str, value: int) -> float:
        minimum, maximum, flat = self.axis_info.get(axis_name, (0, 1023, 0))
        
        # Windows BT Xbox controllers often report triggers as full -32768 to 32767 axes
        # resting at ~32767 or exactly in the middle. We must detect and rely on the same stick logic.
        if minimum < 0:
            val = self._normalize_stick(axis_name, value)
            # Triggers only care about the "pressed" direction. If resting at 32767, pulling decreases it.
            # Convert the -1 to 1 range into a 0 to 1 magnitude throttle.
            return abs(val)

        if maximum <= minimum:
            return 0.0
        out = (float(value) - float(minimum)) / float(maximum - minimum)
        if out < 0.0:
            out = 0.0
        if out > 1.0:
            out = 1.0
        if out < self.trigger_deadzone:
            return 0.0
        return out

    def _read_events(self):
        for event in self.device.read_loop():
            if self._stop_event.is_set():
                break

            if event.type == evdev.ecodes.EV_KEY:
                key_name = evdev.ecodes.KEY.get(event.code)
                if isinstance(key_name, list):
                    key_name = key_name[0]
                if not key_name:
                    key_name = f"BTN_{event.code}"
                
                # Expose the state so the frontend debug/mapping endpoints can read it
                self.axis_state[key_name] = event.value
                self.last_input_event = {'type': 'button', 'code': key_name, 'value': int(event.value), 'ts': time.time()}
                
                if event.value == 1:
                    self._handle_button(key_name, is_down=True)
                elif event.value == 0:
                    self._handle_button(key_name, is_down=False)

            elif event.type == evdev.ecodes.EV_ABS:
                abs_code = evdev.ecodes.ABS[event.code]
                if isinstance(abs_code, list):
                    abs_code = abs_code[0]
                self.axis_state[abs_code] = event.value
                self.last_input_event = {'type': 'axis', 'code': abs_code, 'value': int(event.value), 'ts': time.time()}

    def _handle_button(self, keycode, is_down: bool):
        if not self.runtime or not self.runtime.registry:
            return

        reg = self.runtime.registry
        m = self.mapping

        def is_mapped(action_name):
            mapped_key = m.get(action_name)
            if not mapped_key:
                return False
            if keycode == mapped_key:
                return True
            alias1 = self.KEY_ALIASES.get(keycode)
            alias2 = self.KEY_ALIASES.get(mapped_key)
            if alias1 and alias1 == mapped_key:
                return True
            if alias2 and alias2 == keycode:
                return True
            return False

        holdable = ['pan_left', 'pan_right', 'tilt_up', 'tilt_down']
        for act in holdable:
            if is_mapped(act):
                if is_down:
                    self._btn_held.add(act)
                else:
                    self._btn_held.discard(act)

        if not is_down:
            return

        if is_mapped('estop_toggle'):
            if reg.motors.estop_latched:
                reg.motors.clear_estop()
                self.logger.info("Gamepad: E-STOP cleared by button toggle")
            else:
                reg.motors.emergency_stop(latch=True)
                self.logger.warning("Gamepad: E-STOP triggered by button toggle!")

        elif is_mapped('lights_toggle'):
            if hasattr(self.runtime, 'status_leds') and self.runtime.status_leds:
                self.runtime.status_leds.cycle_preset()
                self.logger.info("Gamepad: Lights cycled to next preset")

        elif is_mapped('tracking_toggle'):
            if hasattr(self.runtime, 'tracking') and self.runtime.tracking:
                self.runtime.tracking.toggle()
                self.logger.info("Gamepad: Tracking toggled")

        elif is_mapped('camera_home'):
            tracking_enabled = getattr(self.runtime.state, 'tracking_enabled', False)
            if reg.camera_servo and not tracking_enabled:
                reg.camera_servo.home()
                self._pan_target = reg.camera_servo.pan_angle
                self._tilt_target = reg.camera_servo.tilt_angle

        elif is_mapped('steering_center'):
            if reg.steering:
                reg.steering.center()
                self._steer_target = reg.steering.angle

    def _button_hold_loop(self):
        while not self._stop_event.is_set():
            if self._btn_held and getattr(self, 'runtime', None) and self.runtime.registry:
                reg = self.runtime.registry
                moved = False
                tracking_enabled = getattr(self.runtime.state, 'tracking_enabled', False)
                if reg.camera_servo and not tracking_enabled:
                    if 'pan_left' in self._btn_held:
                        reg.camera_servo.pan_left()
                        self._pan_target = reg.camera_servo.pan_angle
                        moved = True
                    elif 'pan_right' in self._btn_held:
                        reg.camera_servo.pan_right()
                        self._pan_target = reg.camera_servo.pan_angle
                        moved = True
                    
                    if 'tilt_up' in self._btn_held:
                        reg.camera_servo.tilt_up()
                        self._tilt_target = reg.camera_servo.tilt_angle
                        moved = True
                    elif 'tilt_down' in self._btn_held:
                        reg.camera_servo.tilt_down()
                        self._tilt_target = reg.camera_servo.tilt_angle
                        moved = True
                        
                if moved:
                    self.last_servo_update = time.monotonic()
            
            # Continuously process all smoothed axis positions and motor states
            if self.device is not None:
                self._process_axes()

            time.sleep(self.servo_update_rate_s)

    def _set_motor_state(self, command: str, speed: int = 0) -> None:
        reg = self.runtime.registry
        command_key = (command, int(speed))
        if self._last_motor_cmd == command_key:
            return

        try:
            if command == 'forward':
                reg.motors.forward(speed)
            elif command == 'backward':
                reg.motors.backward(speed)
            else:
                reg.motors.stop()
            self._last_motor_cmd = command_key
        except RuntimeError as e:
            self.runtime.logger.debug("Gamepad motor command blocked: %s", e)
            self._last_motor_cmd = None

    def _process_axes(self):
        if not self.runtime or not self.runtime.registry:
            return

        reg = self.runtime.registry
        now = time.monotonic()
        m = self.mapping

        # Triggers: RT forward, LT reverse.
        fwd_axis = m.get('throttle_fwd', 'ABS_RZ')
        rev_axis = m.get('throttle_rev', 'ABS_Z')
        forward_throttle = self._normalize_trigger(fwd_axis, self.axis_state.get(fwd_axis, 0))
        reverse_throttle = self._normalize_trigger(rev_axis, self.axis_state.get(rev_axis, 0))
        net = forward_throttle - reverse_throttle

        if net > self.trigger_deadzone:
            self._set_motor_state('forward', int(net * 100))
        elif net < -self.trigger_deadzone:
            self._set_motor_state('backward', int(abs(net) * 100))
        else:
            self._set_motor_state('stop', 0)

        # Steering: map stick position directly around configured center/range.
        steer_axis = m.get('steering', 'ABS_X')
        steer_norm = self._normalize_stick(steer_axis, self.axis_state.get(steer_axis, 0))
        if getattr(reg.steering, 'invert', False):
            steer_norm *= -1.0
        steer_center = reg.steering.center_angle
        steer_left_range = max(0, steer_center - reg.steering.min_angle)
        steer_right_range = max(0, reg.steering.max_angle - steer_center)
        raw_steer = steer_center + (steer_norm * (steer_right_range if steer_norm >= 0 else steer_left_range))

        if self._steer_target is None:
            self._steer_target = reg.steering.angle
        self._steer_target = (self.steering_alpha * raw_steer) + ((1.0 - self.steering_alpha) * self._steer_target)
        steer_out = int(round(self._steer_target))
        if abs(reg.steering.angle - steer_out) >= 1:
            reg.steering.set_angle(steer_out)

        # Camera: direct stick-to-angle mapping, honoring invert + center.
        tracking_enabled = getattr(self.runtime.state, 'tracking_enabled', False)
        
        moved = False
        if not tracking_enabled:
            pan_axis = m.get('pan', 'ABS_RX')
            tilt_axis = m.get('tilt', 'ABS_RY')
            pan_norm = self._normalize_stick(pan_axis, self.axis_state.get(pan_axis, 0))
            tilt_norm = self._normalize_stick(tilt_axis, self.axis_state.get(tilt_axis, 0))

            if getattr(reg.camera_servo, 'pan_invert', False):
                pan_norm *= -1.0
            if getattr(reg.camera_servo, 'tilt_invert', False):
                tilt_norm *= -1.0

            pan_center = reg.camera_servo.pan_center
            pan_left_range = max(0, pan_center - reg.camera_servo.pan_min)
            pan_right_range = max(0, reg.camera_servo.pan_max - pan_center)
            raw_pan = pan_center + (pan_norm * (pan_right_range if pan_norm >= 0 else pan_left_range))

            tilt_center = reg.camera_servo.tilt_center
            tilt_up_range = max(0, tilt_center - reg.camera_servo.tilt_min)
            tilt_down_range = max(0, reg.camera_servo.tilt_max - tilt_center)
            # Note: tilt_norm > 0 means stick up, which implies decreasing the angle (moving towards min)
            # tilt_norm < 0 means stick down, which implies increasing the angle (moving towards max)
            if tilt_norm > 0:
                raw_tilt = tilt_center - (tilt_norm * tilt_up_range)
            else:
                raw_tilt = tilt_center + (abs(tilt_norm) * tilt_down_range)

            if self._pan_target is None:
                self._pan_target = reg.camera_servo.pan_angle
            if self._tilt_target is None:
                self._tilt_target = reg.camera_servo.tilt_angle

            self._pan_target = (self.camera_alpha * raw_pan) + ((1.0 - self.camera_alpha) * self._pan_target)
            self._tilt_target = (self.camera_alpha * raw_tilt) + ((1.0 - self.camera_alpha) * self._tilt_target)

            pan_out = int(round(self._pan_target))
            tilt_out = int(round(self._tilt_target))
            
            if abs(reg.camera_servo.pan_angle - pan_out) >= 1:
                reg.camera_servo.set_pan(pan_out)
                moved = True
            if abs(reg.camera_servo.tilt_angle - tilt_out) >= 1:
                reg.camera_servo.set_tilt(tilt_out)
                moved = True
        else:
            # Sync targets so the servo doesn't snap back when tracking ends
            self._pan_target = reg.camera_servo.pan_angle
            self._tilt_target = reg.camera_servo.tilt_angle

        if moved or abs(reg.steering.angle - steer_out) >= 0:
            self.last_servo_update = now
