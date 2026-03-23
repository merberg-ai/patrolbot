from __future__ import annotations

import collections
import pexpect
import threading
import time
from typing import List, Dict, Optional

class BluetoothManager:
    """
    Subprocess wrapper for `bluetoothctl` to manage device discovery and pairing
    from the web API. Output is streamed to an internal deque for a live UI console.
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls, logger) -> BluetoothManager:
        if cls._instance is None:
            cls._instance = BluetoothManager(logger)
        return cls._instance

    def __init__(self, logger):
        self.logger = logger
        self.log_queue = collections.deque(maxlen=200) # Holds the last 200 lines of console output
        self.is_scanning = False
        
        self.child: Optional[pexpect.spawn] = None
        self._thread = None
        self._stop_event = threading.Event()
        
        self.start_process()

    def start_process(self):
        if self._thread and self._thread.is_alive():
            return
            
        try:
            # Spawn bluetoothctl interactive session
            self.child = pexpect.spawn('bluetoothctl', encoding='utf-8', timeout=2.0)
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._read_loop, name='patrolbot-btctl', daemon=True)
            self._thread.start()
            
            # Setup default state
            self.send_command('power on')
            self.send_command('agent on')
            self.send_command('default-agent')
            self.log_message("System: Bluetooth Manager Initialized.")
        except Exception as e:
            self.logger.warning("Could not start bluetoothctl (Not on Linux?): %s", e)
            self.log_message(f"Error: Could not start command - {e}")
            
    def stop_process(self):
        self._stop_event.set()
        if self.child:
            try:
                self.child.close()
            except Exception:
                pass
            self.child = None
            
    def log_message(self, msg: str):
        if msg and msg.strip():
            # Strip bash ANSI escape codes (colors)
            clean = msg.strip()
            if not clean.startswith('[') and not clean.startswith('Device'):
                clean = '> ' + clean
            self.log_queue.append(clean)

    def _read_loop(self):
        while not self._stop_event.is_set():
            if not self.child or not self.child.isalive():
                break
                
            try:
                # Non-blocking read line by line
                line = self.child.readline()
                if line:
                    self.log_message(line)
            except pexpect.TIMEOUT:
                pass
            except pexpect.EOF:
                break
            except Exception as e:
                self.logger.warning("bluetoothctl read error: %s", e)
                break
                
    def send_command(self, cmd: str):
        self.log_message(f"$ {cmd}")
        if self.child and self.child.isalive():
            try:
                self.child.sendline(cmd)
            except Exception as e:
                self.log_message(f"Error sending command: {e}")
        else:
            self.log_message("Error: bluetoothctl process is not running.")
            
    # High-level API Methods
    def start_scan(self):
        self.is_scanning = True
        self.send_command('scan on')
        
    def stop_scan(self):
        self.is_scanning = False
        self.send_command('scan off')
        
    def pair_device(self, mac: str):
        self.send_command(f'pair {mac}')
        # Usually requires trusting to auto-reconnect later
        threading.Timer(2.0, lambda: self.send_command(f'trust {mac}')).start()
        threading.Timer(4.0, lambda: self.send_command(f'connect {mac}')).start()
        
    def connect_device(self, mac: str):
        self.send_command(f'connect {mac}')
        
    def disconnect_device(self, mac: str):
        self.send_command(f'disconnect {mac}')
        
    def remove_device(self, mac: str):
        self.send_command(f'remove {mac}')
        
    def get_logs(self) -> List[str]:
        return list(self.log_queue)
