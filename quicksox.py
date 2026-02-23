#!/usr/bin/env python3
"""
quicksox.py (streamed version)

- Tests SOCKS5 proxies for qBittorrent compatibility.
- Writes PASS results to CSV as they are found (immediate flush).
- Displays live progress count and only PASS results in terminal.
- Measures latency and download bandwidth (KB/s).

Usage:
    python3 quicksox.py soxlist.txt
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import socket
import sys
import time
import csv
from pathlib import Path
import argparse
import threading

# ---------- Config ----------
TEST_HOST = "example.org"
TEST_PORT = 80
SOCKS5_GREETING = b"\x05\x01\x00"
CONNECT_CMD = 0x01
ATYP_DOMAIN = 0x03
TIMEOUT = 6.0
CONCURRENCY = 200
READ_BYTES = 1024 * 128  # bytes to read for bandwidth measurement
# ----------------------------

csv_lock = threading.Lock()

def parse_proxy_line(line: str):
    line = line.strip()
    if not line or ":" not in line:
        return None
    host, port = line.split(":", 1)
    try:
        port = int(port)
    except ValueError:
        return None
    return host.strip(), port

def test_proxy_socks5(host: str, port: int, timeout: float = TIMEOUT):
    proxy_label = f"{host}:{port}"
    start_time = time.perf_counter()
    s = None
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
    except Exception:
        return None

    try:
        s.sendall(SOCKS5_GREETING)
        resp = s.recv(2)
        if len(resp) < 2 or resp[0] != 0x05 or resp[1] != 0x00:
            return None

        # SOCKS5 CONNECT using domain (forces remote DNS)
        host_bytes = TEST_HOST.encode()
        req = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + TEST_PORT.to_bytes(2, "big")
        s.sendall(req)
        resp = s.recv(10)
        if len(resp) < 2 or resp[1] != 0x00:
            return None

        http_req = f"GET / HTTP/1.1\r\nHost: {TEST_HOST}\r\nConnection: close\r\n\r\n".encode()
        s.sendall(http_req)

        total_bytes = 0
        first_time = None
        start_dl = time.perf_counter()
        while time.perf_counter() - start_dl < timeout:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if first_time is None:
                    first_time = time.perf_counter()
                if total_bytes >= READ_BYTES:
                    break
            except socket.timeout:
                break
            except Exception:
                break

        if total_bytes == 0:
            return None

        elapsed_total = time.perf_counter() - start_time
        latency_ms = round(elapsed_total * 1000, 1)
        dl_duration = max((time.perf_counter() - (first_time or start_dl)), 0.001)
        bandwidth_kbps = round((total_bytes / 1024) / dl_duration, 1)

        return {
            "proxy": proxy_label,
            "latency_ms": latency_ms,
            "bandwidth_kbps": bandwidth_kbps
        }

    except Exception:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass

def worker(idx, total, proxy, timeout, csv_writer, csv_file):
    host, port = proxy
    result = test_proxy_socks5(host, port, timeout)
    print(f"[{idx}/{total}] {host}:{port}", end="\r", flush=True)
    if result:
        line = f"PASS {result['proxy']} {result['latency_ms']}ms {result['bandwidth_kbps']}KB/s"
        print(" " * 60 + "\r" + line)
        with csv_lock:
            csv_writer.writerow(result)
            csv_file.flush()

def main():
    parser = argparse.ArgumentParser(description="quicksox.py - SOCKS5 proxy tester for qBittorrent")
    parser.add_argument("infile", help="Input file with host:port lines")
    parser.add_argument("--concurrency", "-c", type=int, default=CONCURRENCY, help="Concurrent workers")
    parser.add_argument("--timeout", "-t", type=float, default=TIMEOUT, help="Timeout seconds per proxy")
    args = parser.parse_args()

    infile = Path(args.infile)
    if not infile.exists():
        print(f"File not found: {infile}")
        sys.exit(1)

    with open(infile, "r", encoding="utf-8", errors="ignore") as f:
        proxies = [parse_proxy_line(x) for x in f if parse_proxy_line(x)]
    total = len(proxies)
    if not total:
        print("No valid proxies found.")
        sys.exit(1)

    out_csv = infile.with_name(infile.stem + "_pass.csv")
    fields = ["proxy", "latency_ms", "bandwidth_kbps"]

    print(f"Testing {total} proxies — concurrency={args.concurrency}, timeout={args.timeout}s\n")

    with open(out_csv, "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=fields)
        writer.writeheader()

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [
                executor.submit(worker, idx, total, proxy, args.timeout, writer, cf)
                for idx, proxy in enumerate(proxies, start=1)
            ]
            for _ in as_completed(futures):
                pass

        elapsed = round(time.perf_counter() - start, 1)
        print(f"\nCompleted in {elapsed}s")
        print(f"Results saved to {out_csv}")

if __name__ == "__main__":
    main()
