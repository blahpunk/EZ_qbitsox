# proxy_manager.py

import requests
import socket
import logging
import json
import time
import socks  # PySocks
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import struct

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CACHE_FILE = "proxies_cache.json"
SOURCES_FILE = "sources.txt"
BANDWIDTH_TEST_URL = "http://speedtest.tele2.net/1MB.zip"
BANDWIDTH_TEST_SIZE = 1024 * 1024

TRACKER_TCP_HOST = "tracker.opentrackr.org"
TRACKER_TCP_PORT = 1337
TRACKER_UDP_HOST = "tracker.opentrackr.org"
TRACKER_UDP_PORT = 1337


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
        self.proxies = {}
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
        cache = {"proxies": self.proxies, "last_update": self.last_update_timestamp}
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
                    # Normalize by removing prefixes like socks5:// or http://
                    line = re.sub(r'^(https?|socks4|socks5)://', '', line, flags=re.IGNORECASE)
                    # Only keep valid IP:PORT pairs
                    if re.match(r'^\d{1,3}(\.\d{1,3}){3}:\d+$', line):
                        fetched_proxies.add(line)
            except Exception as e:
                logging.error(f"Error fetching proxies from {url}: {e}")

        # Validate IPs and ports strictly
        clean_proxies = []
        for proxy in fetched_proxies:
            ip, port = proxy.split(':')
            try:
                if all(0 <= int(octet) <= 255 for octet in ip.split('.')) and 1 <= int(port) <= 65535:
                    clean_proxies.append(proxy)
            except ValueError:
                continue

        # Deduplicate and sort
        unique_proxies = sorted(set(clean_proxies))
        logging.info(f"Fetched {len(unique_proxies)} valid unique proxies from sources.")

        for proxy in unique_proxies:
            if proxy not in self.proxies:
                self.proxies[proxy] = {
                    "tcp_connect": False,
                    "socks5_handshake": False,
                    "remote_connect": False,
                    "dns_ok": False,
                    "http_ok": False,
                    "https_ok": False,
                    "http_proxy_ok": False,
                    "https_proxy_ok": False,
                    "bandwidth_kbps": None,
                    "tracker_tcp_ok": False,
                    "tracker_udp_ok": False,
                    "last_checked": None
                }

        self.save_proxies()
        self.status = "Testing proxies..."

    def test_tracker_tcp(self, ip, port):
        try:
            sock = socks.socksocket()
            sock.set_proxy(socks.SOCKS5, ip, port)
            sock.settimeout(7)
            addr = socket.gethostbyname(TRACKER_TCP_HOST)
            sock.connect((addr, TRACKER_TCP_PORT))
            sock.close()
            return True
        except Exception:
            return False

    def test_tracker_udp(self, ip, port):
        try:
            sock = socks.socksocket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.set_proxy(socks.SOCKS5, ip, port)
            sock.settimeout(7)
            addr = socket.gethostbyname(TRACKER_UDP_HOST)
            conn_id = 0x41727101980
            action = 0
            tx_id = 12345
            packet = struct.pack(">QLL", conn_id, action, tx_id)
            sock.sendto(packet, (addr, TRACKER_UDP_PORT))
            resp, _ = sock.recvfrom(16)
            if len(resp) >= 16:
                resp_action, resp_tx_id = struct.unpack(">LL", resp[:8])
                sock.close()
                return resp_action == 0 and resp_tx_id == tx_id
            sock.close()
            return False
        except Exception:
            return False

    def test_proxy(self, proxy):
        ip, port = proxy.split(':')
        port = int(port)
        result = {
            "tcp_connect": False,
            "socks5_handshake": False,
            "remote_connect": False,
            "dns_ok": False,
            "http_ok": False,
            "https_ok": False,
            "http_proxy_ok": False,
            "https_proxy_ok": False,
            "bandwidth_kbps": None,
            "tracker_tcp_ok": False,
            "tracker_udp_ok": False,
            "last_checked": time.strftime('%Y-%m-%d %H:%M:%S')
        }

        try:
            s = socket.create_connection((ip, port), timeout=5)
            result["tcp_connect"] = True
            s.close()
        except Exception:
            pass

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

        if result["socks5_handshake"]:
            try:
                session = requests.Session()
                session.proxies = {"http": f"socks5://{ip}:{port}", "https": f"socks5://{ip}:{port}"}
                r_http = session.get("http://example.com", timeout=10)
                if r_http.status_code == 200:
                    result["http_ok"] = True
            except Exception:
                pass

            try:
                session = requests.Session()
                session.proxies = {"http": f"socks5://{ip}:{port}", "https": f"socks5://{ip}:{port}"}
                r_https = session.get("https://example.com", timeout=10)
                if r_https.status_code == 200:
                    result["https_ok"] = True
            except Exception:
                pass

            try:
                session = requests.Session()
                session.proxies = {"http": f"socks5://{ip}:{port}", "https": f"socks5://{ip}:{port}"}
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
                pass

            result["tracker_tcp_ok"] = self.test_tracker_tcp(ip, port)
            result["tracker_udp_ok"] = self.test_tracker_udp(ip, port)

        try:
            session = requests.Session()
            session.proxies = {"http": f"http://{ip}:{port}"}
            r_http = session.get("http://example.com", timeout=10)
            if r_http.status_code == 200:
                result["http_proxy_ok"] = True
        except Exception:
            pass

        try:
            session = requests.Session()
            session.proxies = {"https": f"http://{ip}:{port}"}
            r_https = session.get("https://example.com", timeout=10)
            if r_https.status_code == 200:
                result["https_proxy_ok"] = True
        except Exception:
            pass

        self.proxies[proxy].update(result)

    def test_all_proxies(self, max_workers=20):
        self.total_proxies = len(self.proxies)
        sorted_keys = list(self.proxies.keys())
        self.status = f"Testing {self.total_proxies} proxies..."

        def test_and_update(idx_proxy):
            idx, proxy = idx_proxy
            self.current_test_proxy = proxy
            self.current_test_index = idx + 1
            self.status = f"Testing proxy {idx+1} of {self.total_proxies}: {proxy}"
            self.test_proxy(proxy)
            return proxy

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(test_and_update, (idx, proxy)) for idx, proxy in enumerate(sorted_keys)]
            for _ in as_completed(futures):
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
            web_s5 = int(v.get("http_ok") and v.get("https_ok"))
            web_direct = int(v.get("http_proxy_ok") and v.get("https_proxy_ok"))
            bandwidth = v.get("bandwidth_kbps") or 0
            tracker = int(v.get("tracker_tcp_ok", False)) + int(v.get("tracker_udp_ok", False))
            return (web_direct, web_s5, tracker, bandwidth)
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


# End of proxy_manager.py
