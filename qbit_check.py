# qbit_check.py
#
# Diagnostic utility to inspect qBittorrent Web API behavior regarding proxy settings.
# Usage:
#   python3 qbit_check.py [HOST] [PORT] [USERNAME] [PASSWORD]
#
# Example:
#   python3 qbit_check.py localhost 7070 admin 12345
#
# It will:
#   - Login to the WebUI API
#   - Fetch /app/version and /app/preferences
#   - Print all proxy- and network-related fields in full
#   - Attempt to detect current schema (legacy or new)
#   - Print any writable keys that seem relevant

import requests
import json
import sys
import logging

def main():
    if len(sys.argv) < 5:
        print("Usage: python3 qbit_check.py [HOST] [PORT] [USERNAME] [PASSWORD]")
        sys.exit(1)

    host, port, user, pw = sys.argv[1:5]
    base_url = f"http://{host}:{port}"
    api_url = f"{base_url}/api/v2"
    session = requests.Session()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    def login():
        try:
            r = session.post(f"{api_url}/auth/login", data={'username': user, 'password': pw}, timeout=10)
            if r.text.strip() == "Ok.":
                logging.info("✅ Login successful")
                return True
            else:
                logging.error(f"❌ Login failed: {r.text.strip()}")
                return False
        except Exception as e:
            logging.error(f"❌ Login exception: {e}")
            return False

    if not login():
        sys.exit(1)

    def safe_get(path):
        try:
            r = session.get(f"{api_url}{path}", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logging.error(f"❌ GET {path} failed: {e}")
            return {}

    # ---- Get Version ----
    version = safe_get("/app/version")
    logging.info(f"qBittorrent API version: {version}")

    # ---- Get Preferences ----
    prefs = safe_get("/app/preferences")
    if not prefs:
        logging.error("❌ Failed to fetch preferences, aborting.")
        sys.exit(1)

    print("\n=== RAW /app/preferences JSON ===")
    print(json.dumps(prefs, indent=2))

    print("\n=== PROXY-RELATED FIELDS ===")
    proxy_keys = [k for k in prefs.keys() if "proxy" in k or "network" in k or "host" in k or "port" in k]
    for k in sorted(proxy_keys):
        print(f"{k:30s}: {prefs.get(k)}")

    # ---- Deep check for nested structures ----
    print("\n=== NESTED STRUCTURE ANALYSIS ===")

    def recursive_scan(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                keypath = f"{path}.{k}" if path else k
                if any(x in k.lower() for x in ["proxy", "network", "host", "port"]):
                    print(f"{keypath:50s}: {v}")
                if isinstance(v, (dict, list)):
                    recursive_scan(v, keypath)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                recursive_scan(item, f"{path}[{i}]")

    recursive_scan(prefs)

    # ---- Schema Detection ----
    print("\n=== SCHEMA DETECTION ===")
    if "proxy_type" in prefs:
        print("Detected: Legacy schema (flat keys, proxy_type present).")
    elif "network" in prefs and isinstance(prefs["network"], dict):
        print("Detected: New schema (nested 'network.proxy' structure).")
    else:
        print("Detected: Unknown schema — neither legacy nor new standard fields found.")

    # ---- Suggested writable keys ----
    print("\n=== SUGGESTED WRITABLE KEYS (Likely relevant for forcing SOCKS5) ===")
    suggested = [
        "proxy_type", "proxy_ip", "proxy_port", "proxy_auth_enabled",
        "proxy_username", "proxy_password", "proxy_peer_connections",
        "proxy_torrents_only", "proxy_hostnames", "force_proxy",
        "anonymous_mode",
        "network.proxy.enabled", "network.proxy.type", "network.proxy.host",
        "network.proxy.port", "network.proxy.resolve_hostnames_through_proxy"
    ]
    for key in suggested:
        parts = key.split(".")
        node = prefs
        try:
            for p in parts:
                if isinstance(node, dict):
                    node = node[p]
                else:
                    node = None
                    break
            print(f"{key:50s}: {node}")
        except Exception:
            pass

    print("\n=== DONE ===")
    print("Inspect the above output — post or review the proxy-related section to identify correct writable fields.")


if __name__ == "__main__":
    main()
