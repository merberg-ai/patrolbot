from __future__ import annotations
from flask import Flask, current_app, request
from patrolbot.services.bluetooth_manager import BluetoothManager
from patrolbot.config import load_runtime_config, save_runtime_config
from patrolbot.services.gamepad import GamepadService

def register_bluetooth_routes(app: Flask) -> None:
    @app.get('/api/bluetooth/service_status')
    def get_service_status():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        return {'ok': True, 'gamepad_enabled': bool(runtime.config.get('gamepad_enabled', True))}

    @app.post('/api/bluetooth/toggle_service')
    def toggle_gamepad_service():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        enabled = str(payload.get('enabled', 'true')).lower() == 'true'
        
        cfg = load_runtime_config()
        cfg['gamepad_enabled'] = enabled
        save_runtime_config(cfg)
        runtime.config['gamepad_enabled'] = enabled
        
        if enabled:
            if not getattr(runtime, 'gamepad', None):
                runtime.gamepad = GamepadService(runtime, runtime.logger)
            runtime.gamepad.start()
            try:
                import subprocess, sys
                if sys.platform.startswith('linux'):
                    subprocess.run(['rfkill', 'unblock', 'bluetooth'], check=False)
            except Exception:
                pass
        else:
            if getattr(runtime, 'gamepad', None):
                runtime.gamepad.stop()
                runtime.gamepad = None
            if BluetoothManager._instance:
                BluetoothManager._instance.stop_process()
                BluetoothManager._instance = None
            try:
                import subprocess, sys
                if sys.platform.startswith('linux'):
                    subprocess.run(['rfkill', 'block', 'bluetooth'], check=False)
            except Exception:
                pass
                
        return {'ok': True, 'gamepad_enabled': enabled}

    @app.post('/api/bluetooth/cmd')
    def bluetooth_command():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        cmd = payload.get('cmd', '')
        mac = payload.get('mac', '')
        
        bt = BluetoothManager.get_instance(runtime.logger)
        
        if cmd == 'scan_on':
            bt.start_scan()
        elif cmd == 'scan_off':
            bt.stop_scan()
        elif cmd == 'pair':
            bt.pair_device(mac)
        elif cmd == 'connect':
            bt.connect_device(mac)
        elif cmd == 'disconnect':
            bt.disconnect_device(mac)
        elif cmd == 'remove':
            bt.remove_device(mac)
        elif cmd == 'raw':
            raw_cmd = payload.get('raw_cmd', '')
            if raw_cmd:
                bt.send_command(raw_cmd)
        else:
            return {'ok': False, 'error': 'Unknown command'}, 400
            
        return {'ok': True, 'cmd': cmd}

    @app.get('/api/bluetooth/logs')
    def bluetooth_logs():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        bt = BluetoothManager.get_instance(runtime.logger)
        return {
            'ok': True, 
            'is_scanning': bt.is_scanning,
            'logs': bt.get_logs()
        }

    @app.get('/api/bluetooth/mapping')
    def get_gamepad_mapping():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        if getattr(runtime, 'gamepad', None):
             return {'ok': True, 'mapping': runtime.gamepad.mapping}
        return {'ok': False, 'error': 'Gamepad service not running'}

    @app.post('/api/bluetooth/mapping')
    def save_gamepad_mapping():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        payload = request.get_json(force=True, silent=True) or {}
        new_map = payload.get('mapping', {})
        if not new_map:
            return {'ok': False, 'error': 'No mapping provided'}
        
        # update live
        if getattr(runtime, 'gamepad', None):
            runtime.gamepad.mapping = new_map
            
        # save persistent
        cfg = load_runtime_config()
        cfg['gamepad_mapping'] = new_map
        save_runtime_config(cfg)
        
        # runtime config memory
        runtime.config['gamepad_mapping'] = new_map
        
        return {'ok': True}

    @app.post('/api/bluetooth/mapping/reset')
    def reset_gamepad_mapping():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        
        # Build the pristine default mapping
        default_map = GamepadService.DEFAULT_MAPPING.copy()
        
        # Apply to live service
        if getattr(runtime, 'gamepad', None):
            runtime.gamepad.mapping = default_map
            
        # Apply to persistent config
        cfg = load_runtime_config()
        cfg['gamepad_mapping'] = default_map
        save_runtime_config(cfg)
        
        # Apply to runtime config memory
        runtime.config['gamepad_mapping'] = default_map
        
        return {'ok': True, 'mapping': default_map}

    @app.get('/api/bluetooth/debug')
    def get_gamepad_debug():
        runtime = current_app.config['PATROLBOT_RUNTIME']
        gamepad = getattr(runtime, 'gamepad', None)
        if not gamepad:
            return {'ok': False, 'connected': False, 'error': 'Gamepad service not running'}

        device = getattr(gamepad, 'device', None)
        payload = {
            'ok': True,
            'connected': device is not None,
            'mapping': gamepad.mapping,
            'axis_state': gamepad.axis_state,
            'axis_info': gamepad.axis_info,
            'available_axes': getattr(gamepad, 'available_axes', []),
            'available_buttons': getattr(gamepad, 'available_buttons', []),
            'last_input_event': getattr(gamepad, 'last_input_event', None),
            'last_device_scan': getattr(gamepad, 'last_device_scan', []),
            'steer_target': gamepad._steer_target,
            'pan_target': gamepad._pan_target,
            'tilt_target': gamepad._tilt_target,
            'last_motor_cmd': gamepad._last_motor_cmd,
        }
        if device is not None:
            payload.update({
                'device_name': device.name,
                'device_path': getattr(device, 'path', None),
                'device_phys': getattr(device, 'phys', None),
            })
        return payload
