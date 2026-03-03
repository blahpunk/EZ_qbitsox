import json
from typing import Any, Dict, Tuple

import requests


class QBittorrentClient:
    def __init__(self, host: str, port: int, username: str, password: str, timeout: int = 10) -> None:
        self.base_url = f"http://{host}:{port}"
        self.api_url = f"{self.base_url}/api/v2"
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout
        self.session = requests.Session()

    def login(self) -> Tuple[bool, str]:
        if not self.username or not self.password:
            return False, "Missing qBittorrent username/password"

        try:
            response = self.session.post(
                f"{self.api_url}/auth/login",
                data={"username": self.username, "password": self.password},
                timeout=self.timeout,
            )
            if response.status_code == 200 and response.text.strip() == "Ok.":
                return True, "Authenticated"
            return False, f"qBittorrent auth failed: {response.text.strip()}"
        except requests.RequestException as exc:
            return False, f"qBittorrent auth error: {exc}"

    def _get_preferences(self) -> Tuple[bool, Any]:
        ok, message = self.login()
        if not ok:
            return False, message

        try:
            response = self.session.get(f"{self.api_url}/app/preferences", timeout=self.timeout)
            response.raise_for_status()
            return True, response.json()
        except requests.RequestException as exc:
            return False, f"Failed to read preferences: {exc}"

    def current_proxy(self) -> Tuple[bool, str]:
        ok, prefs_or_err = self._get_preferences()
        if not ok:
            return False, str(prefs_or_err)

        prefs = prefs_or_err
        proxy_type = prefs.get("proxy_type")
        if proxy_type in (0, "None", None, "", -1):
            return True, "No proxy configured"

        ip = str(prefs.get("proxy_ip") or "").strip()
        port = str(prefs.get("proxy_port") or "").strip()
        if not ip or not port:
            return True, "Proxy configured but missing host/port"
        return True, f"{ip}:{port}"

    def test_connection(self) -> Tuple[bool, Dict[str, str]]:
        ok, message = self.login()
        if not ok:
            return False, {"message": message}

        version = ""
        try:
            version_response = self.session.get(f"{self.api_url}/app/version", timeout=self.timeout)
            version_response.raise_for_status()
            version = version_response.text.strip()
        except requests.RequestException as exc:
            return False, {"message": f"Connected but failed reading version: {exc}"}

        ok, current_proxy = self.current_proxy()
        if not ok:
            return False, {"message": str(current_proxy), "version": version}

        return True, {
            "message": f"Connected to qBittorrent {version}",
            "version": version,
            "current_proxy": current_proxy,
        }

    def set_socks5_proxy(self, proxy: str) -> Tuple[bool, str]:
        if ":" not in proxy:
            return False, "Proxy must be in ip:port format"

        ip, port_text = proxy.split(":", 1)
        if not port_text.isdigit():
            return False, "Proxy port must be numeric"

        port = int(port_text)
        if not (1 <= port <= 65535):
            return False, "Proxy port out of range"

        ok, prefs_or_err = self._get_preferences()
        if not ok:
            return False, str(prefs_or_err)

        prefs = prefs_or_err
        proxy_type_value = self._desired_proxy_type_value(prefs.get("proxy_type"))
        payload: Dict[str, Any] = {
            "proxy_type": proxy_type_value,
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
        }

        # qBittorrent ignores unknown keys, but we keep payload aligned to keys that exist.
        filtered_payload = {k: v for k, v in payload.items() if k in prefs}
        if not filtered_payload:
            filtered_payload = payload

        try:
            response = self.session.post(
                f"{self.api_url}/app/setPreferences",
                data={"json": json.dumps(filtered_payload)},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return False, f"Failed to set proxy: {exc}"

        ok, current_or_err = self.current_proxy()
        if not ok:
            return False, str(current_or_err)

        ok, prefs_or_err = self._get_preferences()
        if not ok:
            return False, str(prefs_or_err)

        verify = prefs_or_err
        verify_ip = str(verify.get("proxy_ip") or "").strip()
        verify_port = str(verify.get("proxy_port") or "").strip()
        verify_type = verify.get("proxy_type")

        if (
            current_or_err == proxy
            and verify_ip == ip
            and verify_port == str(port)
            and self._is_socks5_proxy_type(verify_type)
        ):
            return True, f"qBittorrent proxy set to {proxy}"
        return False, f"qBittorrent did not report expected proxy (got: {current_or_err})"

    @staticmethod
    def _desired_proxy_type_value(current_type: Any) -> Any:
        if isinstance(current_type, str):
            return "SOCKS5"
        return 2

    @staticmethod
    def _is_socks5_proxy_type(proxy_type: Any) -> bool:
        if isinstance(proxy_type, str):
            return proxy_type.strip().upper() == "SOCKS5"
        try:
            return int(proxy_type) == 2
        except (TypeError, ValueError):
            return False
