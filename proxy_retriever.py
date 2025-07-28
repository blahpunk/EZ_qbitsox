import requests
import logging

PROXY_URLS = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"
]

def fetch_proxies():
    proxies = []
    for url in PROXY_URLS:
        try:
            response = requests.get(url)
            response.raise_for_status()
            proxy_list = response.text.splitlines()
            proxies.extend(proxy_list)
            logging.info(f"Fetched {len(proxy_list)} proxies from {url}")
        except requests.RequestException as e:
            logging.error(f"Failed to fetch proxies from {url}: {e}")
    return proxies

def save_proxies(proxies, filename="proxies.txt"):
    with open(filename, "w") as file:
        for proxy in proxies:
            file.write(f"{proxy}\n")
    logging.info(f"Saved {len(proxies)} proxies to {filename}")
