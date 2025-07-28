import requests
import socket
import logging
import json
import time

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
        self.proxies = {}  # Format: { 'ip:port': { 'status': 'Active/Inactive/Unknown', 'last_checked': 'timestamp' } }
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
                        self.proxies[proxy] = {"status": "Unknown", "last_checked": None}
                fetched_proxies.update(proxies)
                logging.info(f"Fetched {len(proxies)} proxies from {url}")
            except Exception as e:
                logging.error(f"Error fetching proxies from {url}: {e}")
        self.status = "Testing proxies..."

    def test_proxy(self, proxy):
        ip, port = proxy.split(':')
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(5)
        try:
            test_socket.connect((ip, int(port)))
            self.proxies[proxy]["status"] = 'Active'
        except:
            self.proxies[proxy]["status"] = 'Inactive'
        finally:
            self.proxies[proxy]["last_checked"] = time.strftime('%Y-%m-%d %H:%M:%S')
            test_socket.close()

    def test_all_proxies(self):
        self.total_proxies = len(self.proxies)
        for idx, proxy in enumerate(self.proxies.keys(), 1):
            self.current_test_proxy = proxy
            self.current_test_index = idx
            self.status = f"Testing proxy {idx} of {self.total_proxies}: {proxy}"
            self.test_proxy(proxy)
        self.current_test_proxy = None
        self.current_test_index = 0
        self.total_proxies = 0
        self.sort_proxies()
        self.status = "Idle"
        self.last_update_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        self.save_proxies()

    def sort_proxies(self):
        # Sort proxies: Active first, then Inactive, then Unknown
        def status_order(item):
            s = item[1]["status"]
            return 1 if s == "Active" else (2 if s == "Inactive" else 3)
        self.proxies = dict(sorted(self.proxies.items(), key=status_order))

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
