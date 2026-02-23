#!/usr/bin/env python3
"""
fastest.py
Asynchronous proxy tester for SOCKS4, SOCKS5, and HTTP/HTTPS proxies.

- Tests prioritized for qBittorrent first:
    socks5-generic (basic SOCKS5 tunneling suitable for qBittorrent)
- Then tests only full web-capable proxies (usable in Firefox):
    socks5-web, socks4-web, http-full
- Measures bandwidth through the proxy using aiohttp-socks for web-capable types.
- Bandwidth = KB/s or 'failed'
"""

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import csv
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import socks  # PySocks
from typing import Optional, Tuple, List

# ---------- SETTINGS ----------
TEST_HOST = "example.org"
TEST_HTTP = f"http://{TEST_HOST}/"
TEST_HTTPS = f"https://{TEST_HOST}/"
TIMEOUT = 8.0
CONCURRENCY = 200
THREAD_WORKERS = 50
CSV_FIELDS = ["proxy", "type", "latency_ms", "status", "bandwidth_kb/s"]

# Targets to verify SOCKS5 tunneling (direct IP:port so DNS via proxy is not required)
GENERIC_TUNNEL_TARGETS: List[Tuple[str, int]] = [
    ("1.1.1.1", 80),
    ("8.8.8.8", 80),
    ("93.184.215.14", 80),  # example.org (as of now)
]

# Candidate URLs for bandwidth testing (pick first that works)
BANDWIDTH_URLS = [
    # Small-to-medium downloads; tested sequentially until one works
    "https://speed.cloudflare.com/__down?bytes=1048576",  # ~1MB
    "https://speed.hetzner.de/1MB.bin",
    "https://speedtest.tele2.net/1MB.zip",
    TEST_HTTPS,  # fallback to small page if large files blocked
]


# ---------- UTIL ----------
def _close_quietly(s):
    try:
        s.close()
    except Exception:
        pass


# ---------- SOCKS TESTS ----------
def blocking_socks_https_test(host: str, port: int, version: int, timeout: float):
    """Perform HTTPS GET via SOCKS proxy to verify DNS + TLS (web-capable)."""
    start = time.perf_counter()
    s = None
    try:
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5 if version == 5 else socks.SOCKS4, host, port, rdns=True)
        s.settimeout(timeout)
        s.connect((TEST_HOST, 443))
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(s, server_hostname=TEST_HOST)
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {TEST_HOST}\r\n"
            "User-Agent: fastest-proxy-checker\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        sock.sendall(req)
        data = sock.recv(512)
        elapsed = (time.perf_counter() - start) * 1000
        _close_quietly(sock)
        if any(x in data for x in [b"HTTP/1.1 200", b"HTTP/2 200", b"HTTP/1.1 301", b"HTTP/1.1 302"]):
            return True, 200, elapsed
        return False, None, elapsed
    except Exception:
        _close_quietly(s)
        return False, None, None


def blocking_socks5_generic_test(host: str, port: int, timeout: float):
    """
    Test SOCKS5 basic tunneling capability (for qBittorrent use).
    Success criteria:
      - SOCKS5 handshake succeeds
      - CONNECT to at least one target IP:port succeeds
      - We can send a small HTTP request and receive any bytes
    """
    s = None
    try:
        start = time.perf_counter()
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, host, port, rdns=False)
        s.settimeout(timeout)

        last_exc = None
        for tip, tport in GENERIC_TUNNEL_TARGETS:
            try:
                s.connect((tip, tport))
                # Minimal HTTP exchange to verify traffic flows through the tunnel
                s.sendall(b"GET / HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n")
                s.settimeout(timeout)
                data = s.recv(64)
                elapsed = (time.perf_counter() - start) * 1000
                if data is not None:
                    _close_quietly(s)
                    return True, elapsed
            except Exception as e:
                # Reset socket and try next target
                last_exc = e
                _close_quietly(s)
                s = socks.socksocket()
                s.set_proxy(socks.SOCKS5, host, port, rdns=False)
                s.settimeout(timeout)

        if last_exc:
            raise last_exc
        return False, None
    except Exception:
        _close_quietly(s)
        return False, None


# ---------- HTTP TEST ----------
async def aiohttp_proxy_test(proxy_url, test_url, timeout):
    start = time.perf_counter()
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        headers = {"User-Agent": "fastest-proxy-checker", "Accept-Encoding": "identity"}
        async with aiohttp.ClientSession(timeout=timeout_obj, trust_env=False) as session:
            async with session.get(test_url, proxy=proxy_url, headers=headers) as resp:
                elapsed = (time.perf_counter() - start) * 1000
                return resp.status in (200, 301, 302), resp.status, elapsed
    except Exception:
        return False, None, None


# ---------- BANDWIDTH TEST ----------
async def measure_bandwidth(proxy: str, proxy_kind: str, timeout: float = TIMEOUT):
    """
    Download a test payload THROUGH the proxy and compute KB/s.
    - Streams response to avoid memory spikes.
    - Uses multiple candidate URLs; first successful is measured.
    Returns float (KB/s) or None ('failed').
    """
    connector = None
    try:
        if proxy_kind.startswith("socks5"):
            connector = ProxyConnector.from_url(f"socks5://{proxy}")
        elif proxy_kind.startswith("socks4"):
            connector = ProxyConnector.from_url(f"socks4://{proxy}")
        elif proxy_kind.startswith("http"):
            connector = ProxyConnector.from_url(f"http://{proxy}")
        else:
            return None

        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        headers = {"User-Agent": "fastest-proxy-checker", "Accept-Encoding": "identity"}

        async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj, trust_env=False) as session:
            for url in BANDWIDTH_URLS:
                start = time.perf_counter()
                total_bytes = 0
                try:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            continue
                        # Read at least 256KB or until EOF/timeout for stability
                        min_bytes = 256 * 1024
                        chunk_size = 16 * 1024
                        while True:
                            chunk = await resp.content.read(chunk_size)
                            if not chunk:
                                break
                            total_bytes += len(chunk)
                            # Early stop if enough data gathered
                            if total_bytes >= min_bytes:
                                break
                        elapsed = time.perf_counter() - start
                        if total_bytes > 0 and elapsed > 0:
                            kbps = (total_bytes / 1024.0) / elapsed
                            return kbps
                except Exception:
                    # try next URL
                    continue
    except Exception:
        return None
    finally:
        # aiohttp closes connector with session; nothing else to do
        pass
    return None


# ---------- CSV ----------
def ensure_csv(path: Path):
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


async def record_success(path: Path, lock, proxy, types_found, latency, status, bandwidth):
    joined_types = ";".join(types_found)
    bandwidth_display = "failed" if bandwidth is None else f"{bandwidth:.2f}"

    async with lock:
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow({
                "proxy": proxy,
                "type": joined_types,
                "latency_ms": f"{latency:.2f}" if latency else "",
                "status": status or "",
                "bandwidth_kb/s": bandwidth_display
            })
    print(f"\r{' ' * 60}\r{proxy:25} {joined_types:25} OK  {latency:.2f} ms  {bandwidth_display:>8}", flush=True)


# ---------- TEST WORKER ----------
async def test_proxy(proxy, executor, csv_path, csv_lock, idx, total):
    # proxy is "host:port"
    try:
        host, port = proxy.strip().split(":")
        port = int(port)
    except Exception:
        return

    loop = asyncio.get_event_loop()
    print(f"\rTesting {idx}/{total} ...", end="", flush=True)

    types_found: List[str] = []
    best_latency: Optional[float] = None
    last_status: Optional[int] = None

    # 1) PRIORITIZE: SOCKS5-generic (qBittorrent capability)
    ok_generic, latency_generic = await loop.run_in_executor(
        executor, blocking_socks5_generic_test, host, port, TIMEOUT
    )
    if ok_generic:
        types_found.append("socks5-generic")
        best_latency = latency_generic
        last_status = 200

        # 2) If generic passes, check for full SOCKS5 web capability
        ok5, status5, latency5 = await loop.run_in_executor(
            executor, blocking_socks_https_test, host, port, 5, TIMEOUT
        )
        if ok5:
            types_found.append("socks5-web")
            if best_latency is None or (latency5 is not None and latency5 < best_latency):
                best_latency = latency5
                last_status = status5

    # 3) SOCKS4 web-capable (independent)
    ok4, status4, latency4 = await loop.run_in_executor(
        executor, blocking_socks_https_test, host, port, 4, TIMEOUT
    )
    if ok4:
        types_found.append("socks4-web")
        if best_latency is None or (latency4 is not None and latency4 < best_latency):
            best_latency = latency4
            last_status = status4

    # 4) HTTP proxy must support both HTTP and HTTPS
    http_ok, http_status, http_latency = await aiohttp_proxy_test(f"http://{proxy}", TEST_HTTP, TIMEOUT)
    https_ok, https_status, https_latency = await aiohttp_proxy_test(f"http://{proxy}", TEST_HTTPS, TIMEOUT)
    if http_ok and https_ok:
        types_found.append("http-full")
        latencies = [l for l in [http_latency, https_latency] if l]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        if best_latency is None or (avg_latency and avg_latency < best_latency):
            best_latency = avg_latency
            last_status = https_status or http_status

    # Bandwidth: only for verified web-capable proxies (socks5-web, socks4-web, http-full)
    bandwidth = None
    bw_type = None
    if types_found:
        if "socks5-web" in types_found:
            bw_type = "socks5-web"
        elif "http-full" in types_found:
            bw_type = "http-full"
        elif "socks4-web" in types_found:
            bw_type = "socks4-web"

    if bw_type:
        bandwidth = await measure_bandwidth(proxy, bw_type)

    if types_found:
        await record_success(
            csv_path, csv_lock, proxy, types_found, best_latency or 0.0, last_status, bandwidth
        )


# ---------- MAIN ----------
async def run_all(infile: Path):
    proxies = [line.strip() for line in infile.read_text().splitlines() if line.strip()]
    total = len(proxies)
    if not proxies:
        print("No proxies found.")
        return

    csv_path = infile.with_suffix(".csv")
    ensure_csv(csv_path)

    executor = ThreadPoolExecutor(max_workers=THREAD_WORKERS)
    csv_lock = asyncio.Lock()
    sem = asyncio.Semaphore(CONCURRENCY)

    async def worker(p, i):
        async with sem:
            await test_proxy(p, executor, csv_path, csv_lock, i + 1, total)

    print(f"Testing {total} proxies -> {csv_path}")
    await asyncio.gather(*(worker(p, i) for i, p in enumerate(proxies)))
    executor.shutdown(wait=False)
    print(f"\nFinished. Results saved to {csv_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 fastest.py proxylist.txt")
        sys.exit(1)

    infile = Path(sys.argv[1])
    if not infile.exists():
        print(f"File not found: {infile}")
        sys.exit(1)

    asyncio.run(run_all(infile))


if __name__ == "__main__":
    main()
