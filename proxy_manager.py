import requests
import socket
import logging
import json
import time
import socks  # PySocks, install with: pip install PySocks
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CACHE_FILE = "proxies_cache.json"
SOURCES_FILE = "sources.txt"

def load_proxy_sources(filename=SOURCES_FILE):
    try:
        with open(filename, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"Proxy sources file '{filename}' not found.")
        return []

class ProxyManager:
    def __init__(self, sources_file=SOURCES_FILE):
        self.proxy_sources = load_proxy_sources(sources_file)
        self.proxies = {}  # { 'ip:port': { ...results... } }
        self.status = "Idle"
        self.last_update_timestamp = "Never"
        self.current_test_proxy = None
        self.current_test_index = 0
        self.total_proxies = 0

    def load_proxies(self):
        try:
            with open(CACHE_FILE, "r") as file:
                cache = json.load(file)
                self.proxies = cache.get("proxies", {})
                self.last_update_timestamp = cache.get("last_update", "Never")
                logging.info("Loaded proxies from cache")
        except FileNotFoundError:
            logging.info("No cache file found, starting fresh")

    def save_proxies(self):
        cache = {
            "proxies": self.proxies,
            "last_update": self.last_update_timestamp
        }
        with open(CACHE_FILE, "w") as file:
            json.dump(cache, file)
        logging.info("Saved proxies to cache")

    def fetch_proxies(self):
        self.status = "Fetching proxies..."
        fetched_proxies = set()
        for url in self.proxy_sources:
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                proxies = response.text.strip().split('\n')
                for proxy in proxies:
                    if proxy and proxy not in self.proxies:
                        # Initialize results for new proxy
                        self.proxies[proxy] = {
                            "tcp_connect": False,
                            "socks5_handshake": False,
                            "remote_connect": False,
                            "dns_ok": False,
                            "speed_ms": None,
                            "last_checked": None
                        }
                fetched_proxies.update(proxies)
                logging.info(f"Fetched {len(proxies)} proxies from {url}")
            except Exception as e:
                logging.error(f"Error fetching proxies from {url}: {e}")
        self.status = "Testing proxies..."

    def test_proxy(self, proxy):
        ip, port = proxy.split(':')
        port = int(port)
        result = {
            "tcp_connect": False,
            "socks5_handshake": False,
            "remote_connect": False,
            "dns_ok": False,
            "speed_ms": None,
            "last_checked": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        t0 = time.time()

        # TCP Connect
        try:
            s = socket.create_connection((ip, port), timeout=5)
            result["tcp_connect"] = True
            s.close()
        except Exception:
            pass

        # SOCKS5 handshake & relay check (using PySocks)
        if result["tcp_connect"]:
            try:
                sock = socks.socksocket()
                sock.set_proxy(socks.SOCKS5, ip, port)
                sock.settimeout(7)
                # Connect through proxy to public DNS server (1.1.1.1:53)
                sock.connect(("1.1.1.1", 53))
                result["socks5_handshake"] = True
                result["remote_connect"] = True
                try:
                    # Basic DNS test: send minimal payload, expect no disconnect
                    # (This does not send a valid DNS query, just checks we don't get instantly dropped)
                    sock.sendall(b"\x00")
                    result["dns_ok"] = True
                except Exception:
                    pass
                sock.close()
            except Exception:
                pass

        result["speed_ms"] = int((time.time() - t0) * 1000)
        self.proxies[proxy].update(result)

    def test_all_proxies(self, max_workers=5):
        self.total_proxies = len(self.proxies)
        sorted_keys = list(self.proxies.keys())
        self.status = f"Testing {self.total_proxies} proxies with up to {max_workers} threads..."

        def test_and_update(idx_proxy):
            idx, proxy = idx_proxy
            self.current_test_proxy = proxy
            self.current_test_index = idx + 1
            self.status = f"Testing proxy {idx+1} of {self.total_proxies}: {proxy}"
            self.test_proxy(proxy)
            return proxy

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all proxies; each thread does one full test_proxy at a time
            futures = [executor.submit(test_and_update, (idx, proxy)) for idx, proxy in enumerate(sorted_keys)]
            for future in as_completed(futures):
                pass  # Results already stored in self.proxies

        self.current_test_proxy = None
        self.current_test_index = 0
        self.total_proxies = 0
        self.sort_proxies()
        self.status = "Idle"
        self.last_update_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        self.save_proxies()

    def sort_proxies(self):
        def score(item):
            v = item[1]
            return (
                int(v.get("tcp_connect", False) and v.get("socks5_handshake", False) and v.get("remote_connect", False) and v.get("dns_ok", False)),
                -(v.get("speed_ms") or 999999)
            )
        self.proxies = dict(sorted(self.proxies.items(), key=score, reverse=True))

    def update_proxies(self):
        self.fetch_proxies()
        self.test_all_proxies()

    def get_status(self):
        return self.status

    def get_progress(self):
        return {
            "status": self.status,
            "current_proxy": self.current_test_proxy,
            "current_index": self.current_test_index,
            "total": self.total_proxies if self.total_proxies else len(self.proxies)
        }
