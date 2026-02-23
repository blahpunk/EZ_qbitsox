# qbittorrent_manager.py

import requests
import logging
import socket
import json
import time

class QBittorrentManager:
    def __init__(self, host='localhost', port=7070, username=None, password=None):
        self.base_url = f'http://{host}:{port}'
        self.api_url = f'{self.base_url}/api/v2'
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.logged_in = False
        self.last_login_attempt = 0
        self.login_interval = 10
        self.login()

    # ---------- AUTH ---------- #
    def login(self):
        if not self.username or not self.password:
            logging.error("Missing qBittorrent credentials. Set QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD in .env.")
            self.logged_in = False
            return False
        try:
            r = self.session.post(
                f"{self.api_url}/auth/login",
                data={'username': self.username, 'password': self.password},
                timeout=10
            )
            if r.text.strip() == "Ok.":
                self.logged_in = True
                logging.info("qBittorrent login OK")
                return True
        except Exception as e:
            logging.error(f"Login exception: {e}")
        self.logged_in = False
        return False

    def _check_auth(self):
        if self.logged_in:
            try:
                if self.session.get(f"{self.api_url}/app/version", timeout=5).ok:
                    return True
            except Exception:
                pass
        if time.time() - self.last_login_attempt > self.login_interval:
            self.last_login_attempt = time.time()
            logging.info("Session invalid, attempting re-login…")
            return self.login()
        return False

    def _get(self, path):
        self._check_auth()
        r = self.session.get(f"{self.api_url}{path}", timeout=10)
        if r.status_code in (401, 403) and self.login():
            r = self.session.get(f"{self.api_url}{path}", timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, path, data):
        self._check_auth()
        r = self.session.post(f"{self.api_url}{path}", data=data, timeout=10)
        if r.status_code in (401, 403) and self.login():
            r = self.session.post(f"{self.api_url}{path}", data=data, timeout=10)
        r.raise_for_status()
        return r

    # ---------- CORE ---------- #
    def get_current_proxy(self):
        try:
            prefs = self._get("/app/preferences")
            ptype = prefs.get("proxy_type")
            if ptype in ("None", None, "", 0, -1):
                return "No proxy configured"
            ip = prefs.get("proxy_ip", "")
            port = prefs.get("proxy_port", "")
            return f"{ip}:{port}" if ip and port else "Invalid proxy config"
        except Exception as e:
            logging.error(f"get_current_proxy error: {e}")
            return "Error"

    def set_proxy(self, proxy):
        if ":" not in proxy:
            logging.error(f"Invalid proxy format: {proxy}")
            return False
        ip, port_s = proxy.split(":", 1)
        if not port_s.isdigit():
            logging.error(f"Invalid port: {port_s}")
            return False
        port = int(port_s)

        try:
            prefs = self._get("/app/preferences")
            prefs.update({
                "proxy_type": "SOCKS5",           # <-- string, not numeric
                "proxy_ip": ip,
                "proxy_port": port,
                "proxy_auth_enabled": False,
                "proxy_username": "",
                "proxy_password": "",
                "proxy_peer_connections": True,
                "proxy_torrents_only": False,
                "proxy_hostname_lookup": True,
                "proxy_bittorrent": True,
                "proxy_misc": True,
                "proxy_rss": True,
                "force_proxy": True,
                "anonymous_mode": False
            })

            self._post("/app/setPreferences", data={'json': json.dumps(prefs)})

            verify = self._get("/app/preferences")
            if (
                verify.get("proxy_type") == "SOCKS5"
                and verify.get("proxy_ip") == ip
                and str(verify.get("proxy_port")) == str(port)
            ):
                logging.info(f"Proxy successfully set SOCKS5 {ip}:{port}")
                return True
            else:
                logging.error(f"Proxy not applied, verify shows: {verify.get('proxy_type')}")
                return False

        except Exception as e:
            logging.error(f"set_proxy error: {e}")
            return False

    def test_current_proxy_connection(self):
        current = self.get_current_proxy()
        if ":" not in current:
            return current
        try:
            ip, port = current.split(":", 1)
            with socket.create_connection((ip, int(port)), timeout=5):
                return "Active"
        except Exception as e:
            logging.error(f"Proxy test failed: {e}")
            return "Inactive"
