# manprox.py

import json
import re
import sys
import time
import logging

CACHE_FILE = "proxies_cache.json"

def parse_proxy_line(line):
    """
    Accepts lines like:
        socks5://1.2.3.4:1080
        1.2.3.4:1080
    Returns normalized "ip:port" or None if invalid.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    match = re.match(r'^(?:\w+://)?(\d{1,3}(?:\.\d{1,3}){3}:\d+)$', line)
    if not match:
        return None

    return match.group(1)

def load_manual_proxies(filename):
    proxies = {}
    try:
        with open(filename, "r") as f:
            for line in f:
                proxy = parse_proxy_line(line)
                if proxy:
                    proxies[proxy] = {
                        "tcp_connect": False,
                        "socks5_handshake": False,
                        "remote_connect": False,
                        "dns_ok": False,
                        "bandwidth_kbps": None,
                        "tracker_tcp_ok": False,
                        "tracker_udp_ok": False,
                        "last_checked": None
                    }
        logging.info(f"Loaded {len(proxies)} valid proxies from {filename}")
    except FileNotFoundError:
        logging.error(f"File '{filename}' not found.")
        sys.exit(1)

    return proxies

def save_proxies_to_cache(proxies):
    cache = {
        "proxies": proxies,
        "last_update": time.strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)
    logging.info(f"Saved {len(proxies)} proxies to {CACHE_FILE}")

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if len(sys.argv) < 2:
        print("Usage: python3 manprox.py <manual_proxies.txt>")
        sys.exit(1)

    filename = sys.argv[1]
    proxies = load_manual_proxies(filename)

    if not proxies:
        logging.warning("No valid proxies found. Exiting without creating cache.")
        sys.exit(0)

    save_proxies_to_cache(proxies)
    print(f"✅ Created '{CACHE_FILE}' with {len(proxies)} proxies.")

if __name__ == "__main__":
    main()
