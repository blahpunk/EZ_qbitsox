# firefox_proxy.py
import os
import re
import logging
import configparser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def find_firefox_profile():
    """
    Detects Firefox profile directory across normal, Snap, and Flatpak installs.
    Returns the absolute path to the active profile folder or None if not found.
    """
    possible_paths = [
        os.path.expanduser("~/.mozilla/firefox"),  # Classic install
        os.path.expanduser("~/.var/app/org.mozilla.firefox/.mozilla/firefox"),  # Flatpak
        os.path.expanduser("~/snap/firefox/common/.mozilla/firefox"),  # Snap
    ]

    for base in possible_paths:
        if not os.path.isdir(base):
            continue

        # 1. Directly look for .default or .default-release folders
        for d in os.listdir(base):
            if d.endswith(".default") or d.endswith(".default-release"):
                profile_path = os.path.join(base, d)
                logging.info(f"Detected Firefox profile: {profile_path}")
                return profile_path

        # 2. Fallback to profiles.ini lookup
        ini_path = os.path.join(base, "profiles.ini")
        if os.path.exists(ini_path):
            config = configparser.ConfigParser()
            config.read(ini_path)
            for section in config.sections():
                if config.has_option(section, "Path"):
                    rel = config.get(section, "Path")
                    abs_path = os.path.join(base, rel)
                    if os.path.isdir(abs_path):
                        logging.info(f"Detected Firefox profile via profiles.ini: {abs_path}")
                        return abs_path

    logging.error("No Firefox profile found in standard locations.")
    return None


def get_firefox_proxy():
    """
    Reads Firefox prefs.js for SOCKS proxy settings.
    Returns string like '127.0.0.1:9050' or 'No proxy configured'.
    """
    profile = find_firefox_profile()
    if not profile:
        return "Profile not found"

    prefs_path = os.path.join(profile, "prefs.js")
    if not os.path.exists(prefs_path):
        logging.error(f"prefs.js not found in {profile}")
        return "prefs.js not found"

    ip, port = None, None
    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            for line in f:
                if 'network.proxy.socks"' in line:
                    m = re.search(r'"network\.proxy\.socks",\s*"(.*?)"', line)
                    if m:
                        ip = m.group(1)
                if 'network.proxy.socks_port"' in line:
                    m = re.search(r'"network\.proxy\.socks_port",\s*(\d+)', line)
                    if m:
                        port = m.group(1)
        if ip and port:
            return f"{ip}:{port}"
        else:
            return "No proxy configured"
    except Exception as e:
        logging.error(f"Error reading Firefox prefs: {e}")
        return "Error reading prefs"


def set_firefox_proxy(proxy):
    """
    Modifies prefs.js to apply a SOCKS5 proxy for Firefox.
    """
    if ':' not in proxy:
        logging.error(f"Invalid proxy format: {proxy}")
        return False

    ip, port_s = proxy.split(':', 1)
    if not port_s.isdigit():
        logging.error(f"Invalid port: {port_s}")
        return False
    port = int(port_s)

    profile = find_firefox_profile()
    if not profile:
        logging.error("Firefox profile not found.")
        return False

    prefs_path = os.path.join(profile, "prefs.js")
    if not os.path.exists(prefs_path):
        logging.error(f"prefs.js not found in {profile}")
        return False

    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        def replace_or_add(lines, key, value):
            pattern = re.compile(rf'user_pref\("{re.escape(key)}",\s*.*\);')
            new_line = f'user_pref("{key}", {value});\n'
            for i, line in enumerate(lines):
                if pattern.match(line):
                    lines[i] = new_line
                    return lines
            lines.append(new_line)
            return lines

        # Enable SOCKS5 proxy in prefs.js
        lines = replace_or_add(lines, "network.proxy.type", "1")
        lines = replace_or_add(lines, "network.proxy.socks", f'"{ip}"')
        lines = replace_or_add(lines, "network.proxy.socks_port", str(port))
        lines = replace_or_add(lines, "network.proxy.socks_version", "5")
        lines = replace_or_add(lines, "network.proxy.socks_remote_dns", "true")

        with open(prefs_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        logging.info(f"Firefox SOCKS5 proxy set to {ip}:{port}")
        return True

    except Exception as e:
        logging.error(f"Error editing Firefox prefs: {e}")
        return False
