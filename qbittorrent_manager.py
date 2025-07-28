import requests
import logging
import socket
import json  # Make sure to add this import

class QBittorrentManager:
    def __init__(self, host='localhost', port=7070, username='admin', password='870621345a'):
        self.base_url = f'http://{host}:{port}'
        self.api_url = f'{self.base_url}/api/v2'
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.logged_in = False
        self.login()

    def login(self):
        try:
            response = self.session.post(
                f"{self.api_url}/auth/login",
                data={'username': self.username, 'password': self.password},
                timeout=10
            )
            if response.text == "Ok.":
                self.logged_in = True
                logging.info("Successfully logged in to qBittorrent Web UI")
                return True
            logging.error(f"Login failed. Response: {response.text}")
            return False
        except Exception as e:
            logging.error(f"Login exception: {str(e)}")
            return False

    def get_current_proxy(self):
        if not self._check_auth():
            return "Error: Not authenticated"
            
        try:
            response = self.session.get(f"{self.api_url}/app/preferences")
            response.raise_for_status()
            prefs = response.json()
            
            if prefs.get('proxy_type') == 0:  # 0 means no proxy
                return "No proxy configured"
                
            proxy_ip = prefs.get('proxy_ip', '')
            proxy_port = prefs.get('proxy_port', '')
            return f"{proxy_ip}:{proxy_port}" if proxy_ip and proxy_port else "Invalid proxy config"
            
        except Exception as e:
            logging.error(f"Error getting proxy settings: {str(e)}")
            return "Error"

    def set_proxy(self, proxy):
        if not self._check_auth():
            return False

        try:
            # Validate proxy format
            if ':' not in proxy:
                logging.error(f"Invalid proxy format (missing port): {proxy}")
                return False

            ip, port = proxy.split(':')
            if not port.isdigit():
                logging.error(f"Invalid port number: {port}")
                return False

            port = int(port)

            # Fetch full preferences first!
            resp = self.session.get(f"{self.api_url}/app/preferences")
            resp.raise_for_status()
            prefs = resp.json()

            # Update just the proxy-related fields
            # For SOCKS5
            prefs.update({
                'proxy_type': "SOCKS5",   # Set as string
                'proxy_ip': ip,
                'proxy_port': port,
                'proxy_peer_connections': True,
                'proxy_torrents_only': False,
                'proxy_auth_enabled': False,
                'force_proxy': True
            })


            # Now send the ENTIRE updated prefs back
            set_resp = self.session.post(
                f"{self.api_url}/app/setPreferences",
                data={'json': json.dumps(prefs)}
            )

            if set_resp.status_code == 200:
                logging.info(f"Successfully set proxy to {ip}:{port}")
                return True
            else:
                logging.error(f"Failed to set proxy. Status: {set_resp.status_code}, Response: {set_resp.text}")
                return False

        except Exception as e:
            logging.error(f"Error setting proxy: {str(e)}")
            return False


    def test_current_proxy_connection(self):
        current_proxy = self.get_current_proxy()
        if not current_proxy or ":" not in current_proxy:
            return current_proxy
            
        try:
            ip, port = current_proxy.split(':')
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((ip, int(port)))
                return "Active"
        except Exception as e:
            logging.error(f"Proxy connection test failed: {str(e)}")
            return "Inactive"

    def _check_auth(self):
        if not self.logged_in:
            logging.info("Session not authenticated, attempting login...")
            return self.login()
        return True