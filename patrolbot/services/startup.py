from __future__ import annotations

import time

from patrolbot.hardware.battery import BatteryMonitor
from patrolbot.hardware.camera import CameraWrapper
from patrolbot.hardware.camera_servo import CameraServoController
from patrolbot.hardware.hat import HatContext
from patrolbot.hardware.lights import RgbEyes
from patrolbot.hardware.motors import MotorController
from patrolbot.hardware.registry import HardwareRegistry, RuntimeContext
from patrolbot.hardware.steering import SteeringController
from patrolbot.hardware.switches import SwitchController
from patrolbot.hardware.ultrasonic import UltrasonicSensor
from patrolbot.services.network_status import NetworkStatusService
from patrolbot.services.snapshots import SnapshotService
from patrolbot.services.status_leds import StatusLedService
from patrolbot.services.telemetry import TelemetryService
from patrolbot.state import RuntimeState


class StartupManager:
    def __init__(self, config: dict, logger):
        self.config = config
        self.logger = logger

    def _network_snapshot(self, runtime) -> None:
        service = runtime.network_status or NetworkStatusService(runtime.logger)
        runtime.network_status = service
        status = service.get_status()
        runtime.state.network_connected = bool(status.get('connected'))
        runtime.state.network_ssid = status.get('ssid')
        runtime.state.network_ip = status.get('ip')
        runtime.state.network_last_error = status.get('error')

    def _sync_sensor_state(self, runtime, slot: str, cfg_key: str, sensor_obj, probe: dict | None = None) -> None:
        cfg = runtime.config.get(cfg_key, {}) or {}
        use_mode = str(cfg.get('use_mode', 'safety_only' if cfg_key == 'ultrasonic' else 'off')).strip().lower()
        if use_mode not in {'off', 'safety_only', 'fusion'}:
            use_mode = 'off'
        entry = runtime.state.sensor_status.get(slot, {})
        entry['configured'] = bool(cfg.get('enabled', cfg_key == 'ultrasonic'))
        entry['enabled'] = bool(entry['configured']) and use_mode != 'off'
        entry['use_mode'] = use_mode
        if probe:
            entry.update(probe)
            entry['available'] = bool(probe.get('detected'))
            entry['last_probe_ts'] = time.time()
        else:
            entry.setdefault('initialized', bool(sensor_obj))
            entry.setdefault('detected', False)
            entry.setdefault('healthy', False)
            entry.setdefault('available', False)
        runtime.state.sensor_status[slot] = entry

    def _probe_sensor(self, runtime, cfg_key: str, slot: str):
        sensor = None
        try:
            sensor = UltrasonicSensor(runtime.config, runtime.logger, config_key=cfg_key)
            probe = sensor.probe(reads=3, valid_reads_required=1)
            self._sync_sensor_state(runtime, slot, cfg_key, sensor, probe)
            if probe.get('detected'):
                return sensor
            sensor.close()
            return None
        except Exception as exc:
            self.logger.warning('Failed to initialize %s: %s', cfg_key, exc)
            self._sync_sensor_state(runtime, slot, cfg_key, None, {
                'initialized': False,
                'detected': False,
                'healthy': False,
                'available': False,
                'last_error': str(exc),
                'details': None,
            })
            return None

    def initialize(self) -> RuntimeContext:
        registry = HardwareRegistry()
        state = RuntimeState()
        runtime = RuntimeContext(
            config=self.config,
            logger=self.logger,
            registry=registry,
            state=state,
            telemetry=None,
            status_leds=None,
            gamepad=None,
            tracking=None,
            patrol=None,
            network_status=None,
            snapshots=None,
        )
        try:
            registry.hat = HatContext(self.config, self.logger)
            registry.hat.initialize()

            registry.lights = RgbEyes(self.config, self.logger)
            registry.lights.initialize()
            registry.lights.off()

            runtime.status_leds = StatusLedService(registry.lights, state, self.config, self.logger)
            runtime.status_leds.set_state('BOOTING', reason='startup', force=True)

            registry.motors = MotorController(self.config, self.logger)
            registry.motors.stop()

            registry.steering = SteeringController(self.config, self.logger, registry.hat)
            registry.steering.center()
            state.steering_angle = registry.steering.angle

            registry.camera_servo = CameraServoController(self.config, self.logger, registry.hat)
            registry.camera_servo.home()
            state.pan_angle = registry.camera_servo.pan_angle
            state.tilt_angle = registry.camera_servo.tilt_angle

            registry.switches = SwitchController(self.config, self.logger)
            registry.switches.all_off()

            registry.ultrasonic = self._probe_sensor(runtime, 'ultrasonic', 'front_ultrasonic')
            registry.ultrasonic_rear = self._probe_sensor(runtime, 'ultrasonic_rear', 'rear_ultrasonic')
            registry.battery = BatteryMonitor(self.config, self.logger)

            runtime.snapshots = SnapshotService(self.config, self.logger)
            state.snapshot_count = len(runtime.snapshots.list_snapshots())

            registry.camera = CameraWrapper(self.config, self.logger)
            registry.camera.start()

            from patrolbot.services.patrol import PatrolService
            runtime.patrol = PatrolService(runtime, self.logger)
            runtime.patrol.start()

            self._network_snapshot(runtime)
            state.system_status = 'ready'
            runtime.status_leds.set_state('WIFI_CONNECTED' if state.network_connected else 'WIFI_ERROR', reason='startup network', force=True)

            runtime.telemetry = TelemetryService(runtime, self.logger)
            runtime.telemetry.poll_once()
            runtime.telemetry.start()
            return runtime
        except Exception:
            state.system_status = 'error'
            if getattr(runtime, 'status_leds', None):
                runtime.status_leds.set_state('ERROR', reason='startup failure', force=True)
            raise
