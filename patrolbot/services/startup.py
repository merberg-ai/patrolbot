from __future__ import annotations

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
from patrolbot.services.status_leds import StatusLedService
from patrolbot.services.telemetry import TelemetryService
from patrolbot.state import RuntimeState


class StartupManager:
    def __init__(self, config: dict, logger):
        self.config = config
        self.logger = logger

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
        )
        try:
            registry.hat = HatContext(self.config, self.logger)
            registry.hat.initialize()

            registry.lights = RgbEyes(self.config, self.logger)
            registry.lights.initialize()
            registry.lights.off()

            runtime.status_leds = StatusLedService(registry.lights, state, self.config, self.logger)
            runtime.status_leds.set_state('BOOTING')

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

            registry.ultrasonic = UltrasonicSensor(self.config, self.logger)
            if self.config.get('ultrasonic_rear', {}).get('enabled', False):
                try:
                    registry.ultrasonic_rear = UltrasonicSensor(self.config, self.logger, config_key='ultrasonic_rear')
                except Exception as exc:
                    self.logger.warning('Failed to initialize rear ultrasonic: %s', exc)
            registry.battery = BatteryMonitor(self.config, self.logger)

            registry.camera = CameraWrapper(self.config, self.logger)
            registry.camera.start()

            from patrolbot.services.patrol import PatrolService
            runtime.patrol = PatrolService(runtime, self.logger)
            runtime.patrol.start()

            runtime.telemetry = TelemetryService(runtime, self.logger)
            runtime.telemetry.poll_once()
            runtime.telemetry.start()
            return runtime
        except Exception:
            if getattr(runtime, 'status_leds', None):
                runtime.status_leds.set_state('ERROR')
            raise
