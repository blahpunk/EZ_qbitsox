import random
import re
import socket
import struct
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Set

import socks

TRACKER_HOST = "tracker.opentrackr.org"
TRACKER_PORT = 1337
try:
    TRACKER_IP = socket.gethostbyname(TRACKER_HOST)
except OSError:
    TRACKER_IP = TRACKER_HOST

IP_PORT_PATTERN = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_proxy_line(line: str) -> Optional[str]:
    cleaned = line.strip()
    if not cleaned or cleaned.startswith("#"):
        return None

    cleaned = cleaned.replace("socks5h://", "socks5://")
    cleaned = cleaned.replace("Socks5://", "socks5://")
    cleaned = cleaned.replace("socks5://", "")
    cleaned = cleaned.replace("socks4://", "")
    cleaned = cleaned.replace("http://", "")
    cleaned = cleaned.replace("https://", "")

    match = IP_PORT_PATTERN.search(cleaned)
    if not match:
        return None

    ip = match.group(1)
    port_text = match.group(2)

    octets = ip.split(".")
    if len(octets) != 4:
        return None

    try:
        if any(not (0 <= int(octet) <= 255) for octet in octets):
            return None
        port = int(port_text)
        if not (1 <= port <= 65535):
            return None
    except ValueError:
        return None

    return f"{ip}:{port}"


def extract_proxies(text: str) -> Set[str]:
    proxies: Set[str] = set()
    for line in text.splitlines():
        normalized = normalize_proxy_line(line)
        if normalized:
            proxies.add(normalized)
    return proxies


def is_qb_download_ready(checks: Dict[str, bool]) -> bool:
    return all(
        checks.get(flag, False)
        for flag in (
            "tcp_connect",
            "socks5_handshake",
            "tracker_tcp",
            "tracker_udp",
        )
    )


class ProxyTester:
    def __init__(self, timeout_seconds: int = 7) -> None:
        self.timeout_seconds = timeout_seconds

    def test(self, proxy: str) -> Dict[str, object]:
        ip, port_text = proxy.split(":", 1)
        port = int(port_text)

        checks = {
            "tcp_connect": False,
            "socks5_handshake": False,
            "tracker_tcp": False,
            "tracker_udp": False,
        }
        latency_ms: Optional[float] = None
        failure_reason = "unreachable"

        try:
            with socket.create_connection((ip, port), timeout=self.timeout_seconds):
                checks["tcp_connect"] = True
        except OSError:
            return self._result(checks, latency_ms, failure_reason)

        try:
            sock = socks.socksocket()
            sock.set_proxy(socks.SOCKS5, ip, port, rdns=True)
            sock.settimeout(self.timeout_seconds)

            start = time.perf_counter()
            sock.connect((TRACKER_IP, TRACKER_PORT))
            latency_ms = round((time.perf_counter() - start) * 1000, 2)

            checks["socks5_handshake"] = True
            checks["tracker_tcp"] = True
            sock.close()
        except OSError:
            return self._result(checks, latency_ms, "socks5 or tracker tcp failed")

        try:
            udp_sock = socks.socksocket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.set_proxy(socks.SOCKS5, ip, port, rdns=True)
            udp_sock.settimeout(self.timeout_seconds)

            tx_id = random.randint(1, 0xFFFFFFFF)
            packet = struct.pack(">QLL", 0x41727101980, 0, tx_id)
            udp_sock.sendto(packet, (TRACKER_IP, TRACKER_PORT))
            response, _ = udp_sock.recvfrom(1024)

            if len(response) >= 16:
                action, returned_tx_id = struct.unpack(">LL", response[:8])
                checks["tracker_udp"] = action == 0 and returned_tx_id == tx_id
            udp_sock.close()
        except OSError:
            checks["tracker_udp"] = False

        if not checks["tracker_udp"]:
            return self._result(checks, latency_ms, "tracker udp failed")

        return self._result(checks, latency_ms, "")

    @staticmethod
    def _result(checks: Dict[str, bool], latency_ms: Optional[float], failure_reason: str) -> Dict[str, object]:
        passed = is_qb_download_ready(checks)
        return {
            "checks": checks,
            "passed": passed,
            "latency_ms": latency_ms,
            "failure_reason": "" if passed else failure_reason,
            "checked_at": utc_now_iso(),
        }
