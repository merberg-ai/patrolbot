from __future__ import annotations

import subprocess
import logging
import socket
from typing import Dict, List, Any

class NetworkManager:
    """Service to handle Wi-Fi interactions via nmcli."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        
    def _run_nmcli(self, args: List[str]) -> subprocess.CompletedProcess:
        try:
            # We use timeout in case nmcli hangs
            return subprocess.run(['nmcli'] + args, capture_output=True, text=True, timeout=15)
        except FileNotFoundError:
            self.logger.warning("nmcli not found. Cannot perform network operations.")
            return subprocess.CompletedProcess(args=['nmcli'] + args, returncode=-1, stdout='', stderr='nmcli not found')
        except subprocess.TimeoutExpired:
            self.logger.error("nmcli command timed out.")
            return subprocess.CompletedProcess(args=['nmcli'] + args, returncode=-2, stdout='', stderr='timeout')
        except Exception as e:
            self.logger.error(f"nmcli error: {e}")
            return subprocess.CompletedProcess(args=['nmcli'] + args, returncode=-3, stdout='', stderr=str(e))

    def get_status(self) -> Dict[str, Any]:
        """Get the currently connected Wi-Fi SSID and IP address."""
        status = {'connected': False, 'ssid': None, 'ip': '127.0.0.1'}
        
        # Try to get IP (fallback method to socket if nmcli fails or isn't detailed enough)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('8.8.8.8', 80))
                status['ip'] = s.getsockname()[0]
        except Exception:
            pass

        # Use nmcli to find active connection
        res = self._run_nmcli(['-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'])
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 2 and parts[0] == 'yes':
                    status['connected'] = True
                    # Reconstruct SSID in case it had colons (escaped by nmcli or just split)
                    status['ssid'] = ':'.join(parts[1:]).replace('\\:', ':')
                    break
        elif res.returncode == -1:
            # Mock status for development without nmcli
            status['connected'] = True
            status['ssid'] = 'Mock-WiFi-Network'
            
        return status

    def scan_networks(self) -> List[Dict[str, Any]]:
        """Scan for available Wi-Fi networks."""
        networks = []
        # Ask nmcli to rescan first
        self._run_nmcli(['dev', 'wifi', 'rescan'])
        
        # Then list networks
        res = self._run_nmcli(['-t', '-f', 'SSID,BSSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'])
        if res.returncode == 0 and res.stdout:
            seen_ssids = set()
            for line in res.stdout.strip().split('\n'):
                # nmcli escapes colons in the output using \:
                # We need to parse carefully or just rely on standard split if we ignore colons in SSID
                # Actually, a better way is to avoid using ':' as field separator since MAC and maybe SSID has it.
                # But '-t' defaults to ':'
                # Let's handle escaping: replace '\:' with a placeholder, split by ':', then restore
                line_safe = line.replace('\\:', '__COLON__')
                parts = line_safe.split(':')
                
                # Should be at least 4 parts: SSID, BSSID (mac), SIGNAL, SECURITY
                # But BSSID itself has colons which were escaped... wait, nmcli escapes them?
                # Actually BSSID colons DO get escaped by nmcli -t, e.g. 00\:11\:22\:33\:44\:55
                # So replacing \: with __COLON__ works.
                
                if len(parts) >= 4:
                    ssid = parts[0].replace('__COLON__', ':').strip()
                    if not ssid or ssid == '--': continue  # Hidden network
                    
                    bssid = parts[1].replace('__COLON__', ':')
                    signal = int(parts[2]) if parts[2].isdigit() else 0
                    security = parts[3].replace('__COLON__', ':')
                    
                    if ssid not in seen_ssids:
                        seen_ssids.add(ssid)
                        networks.append({
                            'ssid': ssid,
                            'bssid': bssid,
                            'signal': signal,
                            'security': security
                        })
        elif res.returncode == -1:
            # Mock data
            networks = [
                {'ssid': 'Mock-WiFi-Network', 'bssid': '00:11:22:33:44:01', 'signal': 80, 'security': 'WPA2'},
                {'ssid': 'Neighbors-WiFi', 'bssid': '00:11:22:33:44:02', 'signal': 40, 'security': 'WPA2'},
                {'ssid': 'Public-Guest', 'bssid': '00:11:22:33:44:03', 'signal': 60, 'security': ''}
            ]
            
        # Sort by signal strength
        networks.sort(key=lambda x: x['signal'], reverse=True)
        return networks

    def connect(self, ssid: str, password: str = "") -> Dict[str, Any]:
        """Connect to a Wi-Fi network and save the profile."""
        if not ssid:
            return {'ok': False, 'error': 'SSID is required'}
            
        args = ['dev', 'wifi', 'connect', ssid]
        if password:
            args.extend(['password', password])
            
        res = self._run_nmcli(args)
        
        if res.returncode == 0:
            return {'ok': True, 'message': f"Successfully connected to {ssid}"}
        elif res.returncode == -1:
            # Mock success
            return {'ok': True, 'message': f"Mock successfully connected to {ssid}"}
        else:
            return {'ok': False, 'error': res.stderr.strip() or res.stdout.strip() or 'Unknown nmcli error'}
