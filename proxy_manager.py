import requests
import socket
import logging
import json
import time
import socks  # PySocks, install with: pip install PySocks
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CACHE_FILE = "proxies_cache.json"
SOURCES_FILE = "sources.txt"
BANDWIDTH_TEST_URL = "http://speedtest.tele2.net/1MB.zip"  # 1MB file
BANDWIDTH_TEST_SIZE = 1024 * 1024  # 1MB in bytes

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
            self.proxies = {}
            self.last_update_timestamp = "Never"

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
                lines = response.text.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    match = re.match(r'^(socks5://|socks4://|http://|https://)?(.+)$', line, re.IGNORECASE)
                    if match:
                        proxy = match.group(2)
                    else:
                        proxy = line
                    if not re.match(r'^\d{1,3}(\.\d{1,3}){3}:\d+$', proxy):
                        continue
                    if proxy not in self.proxies:
                        self.proxies[proxy] = {
                            "tcp_connect": False,
                            "socks5_handshake": False,
                            "remote_connect": False,
                            "dns_ok": False,
                            "bandwidth_kbps": None,
                            "last_checked": None
                        }
                    fetched_proxies.add(proxy)
            except Exception as e:
                logging.error(f"Error fetching proxies from {url}: {e}")
        # *** Save after fetching, before testing! ***
        self.save_proxies()
        self.status = "Testing proxies..."

    def test_proxy(self, proxy):
        ip, port = proxy.split(':')
        port = int(port)
        result = {
            "tcp_connect": False,
            "socks5_handshake": False,
            "remote_connect": False,
            "dns_ok": False,
            "bandwidth_kbps": None,
            "last_checked": time.strftime('%Y-%m-%d %H:%M:%S')
        }

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
                sock.connect(("1.1.1.1", 53))
                result["socks5_handshake"] = True
                result["remote_connect"] = True
                try:
                    sock.sendall(b"\x00")
                    result["dns_ok"] = True
                except Exception:
                    pass
                sock.close()
            except Exception:
                pass

        # Bandwidth test (real download) - only if SOCKS5 handshake succeeded
        if result["socks5_handshake"]:
            try:
                session = requests.Session()
                session.proxies = {
                    "http": f"socks5://{ip}:{port}",
                    "https": f"socks5://{ip}:{port}",
                }
                t0 = time.time()
                resp = session.get(BANDWIDTH_TEST_URL, timeout=15, stream=True)
                total_bytes = 0
                for chunk in resp.iter_content(8192):
                    total_bytes += len(chunk)
                    if total_bytes >= BANDWIDTH_TEST_SIZE:
                        break
                elapsed = time.time() - t0
                if total_bytes > 0 and elapsed > 0:
                    kbps = (total_bytes / 1024) / elapsed
                    result["bandwidth_kbps"] = round(kbps, 1)
            except Exception:
                result["bandwidth_kbps"] = None

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
            futures = [executor.submit(test_and_update, (idx, proxy)) for idx, proxy in enumerate(sorted_keys)]
            for future in as_completed(futures):
                pass

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
            # Sort: all tests passed, then by bandwidth (descending)
            all_pass = int(v.get("tcp_connect") and v.get("socks5_handshake") and v.get("remote_connect") and v.get("dns_ok"))
            bandwidth = v.get("bandwidth_kbps") or 0
            return (all_pass, bandwidth)
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
