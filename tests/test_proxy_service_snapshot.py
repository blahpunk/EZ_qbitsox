from proxy_service import ProxyService
from settings_store import SecureSettingsStore


def test_snapshot_shows_only_passed_sources_and_proxies(tmp_path):
    data_dir = tmp_path / "data"
    sources_file = tmp_path / "sources.txt"
    sources_file.write_text("https://example.com/a.txt\nhttps://example.com/b.txt\n", encoding="utf-8")

    store = SecureSettingsStore(data_dir=str(data_dir))
    service = ProxyService(settings_store=store, sources_file=str(sources_file), data_dir=str(data_dir))

    service.state["sources"] = {
        "https://example.com/a.txt": {
            "url": "https://example.com/a.txt",
            "fetched_count": 50,
            "valid_count": 40,
            "passing_count": 3,
            "last_fetch": "2026-03-03T00:00:00+00:00",
        },
        "https://example.com/b.txt": {
            "url": "https://example.com/b.txt",
            "fetched_count": 20,
            "valid_count": 20,
            "passing_count": 0,
            "last_fetch": "2026-03-03T00:00:00+00:00",
        },
    }
    service.state["proxies"] = {
        "1.1.1.1:1080": {
            "passed": True,
            "latency_ms": 20.5,
            "last_tested": "2026-03-03T01:00:00+00:00",
            "sources": ["https://example.com/a.txt"],
            "checks": {
                "tcp_connect": True,
                "socks5_handshake": True,
                "tracker_tcp": True,
                "tracker_udp": True,
            },
        },
        "2.2.2.2:1080": {
            "passed": False,
            "latency_ms": None,
            "last_tested": "2026-03-03T01:00:00+00:00",
            "sources": ["https://example.com/b.txt"],
            "checks": {
                "tcp_connect": True,
                "socks5_handshake": False,
                "tracker_tcp": False,
                "tracker_udp": False,
            },
        },
    }

    snapshot = service.get_snapshot()

    assert len(snapshot["sources"]) == 1
    assert snapshot["sources"][0]["url"] == "https://example.com/a.txt"

    assert len(snapshot["passed_proxies"]) == 1
    assert snapshot["passed_proxies"][0]["proxy"] == "1.1.1.1:1080"
