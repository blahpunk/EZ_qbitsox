import requests
import logging

QBITTORRENT_URL = "http://localhost:7070/api/v2/app/preferences"

def get_current_proxy():
    try:
        response = requests.get(QBITTORRENT_URL)
        response.raise_for_status()
        settings = response.json()
        proxy_host = settings.get("proxy_ip")
        proxy_port = settings.get("proxy_port")
        return f"{proxy_host}:{proxy_port}"
    except requests.RequestException as e:
        logging.error(f"Failed to get current proxy settings from qBittorrent: {e}")
        return None

def set_proxy(proxy_ip, proxy_port):
    try:
        data = {
            "proxy_ip": proxy_ip,
            "proxy_port": proxy_port,
            "proxy_type": 2  # SOCKS5 proxy
        }
        response = requests.post(QBITTORRENT_URL, json=data)
        response.raise_for_status()
        logging.info(f"Set qBittorrent proxy to {proxy_ip}:{proxy_port}")
    except requests.RequestException as e:
        logging.error(f"Failed to set proxy settings: {e}")
