import requests
import logging

PROXY_URLS = [
"https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
"https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
"https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
"https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
"https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt",
"https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
"https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
"https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies.txt",
"https://raw.githubusercontent.com/proxifly/free-proxy-list/refs/heads/main/proxies/all/data.txt",
"https://raw.githubusercontent.com/clarketm/proxy-list/refs/heads/master/proxy-list-raw.txt",
"https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/HTTPS_RAW.txt",
"https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/SOCKS4_RAW.txt",
"https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/SOCKS5_RAW.txt",
"https://raw.githubusercontent.com/officialputuid/KangProxy/refs/heads/KangProxy/socks5/socks5.txt",
"https://raw.githubusercontent.com/officialputuid/KangProxy/refs/heads/KangProxy/socks4/socks4.txt",
"https://raw.githubusercontent.com/officialputuid/KangProxy/refs/heads/KangProxy/https/https.txt",
"https://raw.githubusercontent.com/officialputuid/KangProxy/refs/heads/KangProxy/http/http.txt",
"https://raw.githubusercontent.com/vakhov/fresh-proxy-list/refs/heads/master/socks5.txt",
"https://raw.githubusercontent.com/vakhov/fresh-proxy-list/refs/heads/master/socks4.txt",
"https://raw.githubusercontent.com/vakhov/fresh-proxy-list/refs/heads/master/http.txt",
"https://raw.githubusercontent.com/vakhov/fresh-proxy-list/refs/heads/master/https.txt",
"https://raw.githubusercontent.com/vakhov/fresh-proxy-list/refs/heads/master/proxylist.txt",
"https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/http.txt",
"https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/socks4.txt",
"https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/socks5.txt",
"https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
"https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/refs/heads/main/http.txt",
"https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/refs/heads/main/socks4.txt",
"https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/refs/heads/main/socks5.txt",
"https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/refs/heads/main/socks5_checked.txt",
"https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/refs/heads/main/http_checked.txt",
"https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/refs/heads/main/socks4_checked.txt",
"https://raw.githubusercontent.com/iplocate/free-proxy-list/refs/heads/main/protocols/socks5.txt",
"https://raw.githubusercontent.com/iplocate/free-proxy-list/refs/heads/main/protocols/socks4.txt",
"https://raw.githubusercontent.com/iplocate/free-proxy-list/refs/heads/main/protocols/https.txt",
"https://raw.githubusercontent.com/iplocate/free-proxy-list/refs/heads/main/protocols/http.txt",
"https://raw.githubusercontent.com/iplocate/free-proxy-list/refs/heads/main/all-proxies.txt",
"https://raw.githubusercontent.com/ebrasha/abdal-proxy-hub/refs/heads/main/socks5-proxy-list-by-EbraSha.txt",
"https://raw.githubusercontent.com/ebrasha/abdal-proxy-hub/refs/heads/main/http-proxy-list-by-EbraSha.txt",
"https://raw.githubusercontent.com/ebrasha/abdal-proxy-hub/refs/heads/main/socks4-proxy-list-by-EbraSha.txt",
"https://raw.githubusercontent.com/ebrasha/abdal-proxy-hub/refs/heads/main/https-proxy-list-by-EbraSha.txt"
]

def fetch_proxies():
    proxies = []
    for url in PROXY_URLS:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            proxy_list = [line.strip() for line in response.text.splitlines() if line.strip()]
            proxies.extend(proxy_list)
            logging.info(f"Fetched {len(proxy_list)} proxies from {url}")
        except requests.RequestException as e:
            logging.error(f"Failed to fetch proxies from {url}: {e}")

    # Deduplicate and normalize
    unique_proxies = sorted(set(proxies))
    logging.info(f"Total unique proxies fetched: {len(unique_proxies)}")
    return unique_proxies

"def save_proxies(proxies, filename="proxies.txt","):
    with open(filename, "w") as file:
        for proxy in proxies:
            file.write(f"{proxy}\n")
    logging.info(f"Saved {len(proxies)} proxies to {filename}")
