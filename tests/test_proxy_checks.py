from proxy_checks import extract_proxies, is_qb_download_ready, normalize_proxy_line


def test_normalize_proxy_line_accepts_common_formats():
    assert normalize_proxy_line("1.2.3.4:1080") == "1.2.3.4:1080"
    assert normalize_proxy_line("socks5://5.6.7.8:3128") == "5.6.7.8:3128"
    assert normalize_proxy_line("http://9.10.11.12:8080") == "9.10.11.12:8080"
    assert normalize_proxy_line("proxy=13.14.15.16:9999 # comment") == "13.14.15.16:9999"


def test_normalize_proxy_line_rejects_invalid_values():
    assert normalize_proxy_line("") is None
    assert normalize_proxy_line("# comment") is None
    assert normalize_proxy_line("300.1.1.1:1080") is None
    assert normalize_proxy_line("1.1.1.1:70000") is None
    assert normalize_proxy_line("not-a-proxy") is None


def test_extract_and_pass_logic():
    text = "\n".join([
        "socks5://1.1.1.1:1080",
        "1.1.1.1:1080",
        "2.2.2.2:9050",
        "badline",
    ])
    proxies = extract_proxies(text)
    assert proxies == {"1.1.1.1:1080", "2.2.2.2:9050"}

    assert is_qb_download_ready(
        {
            "tcp_connect": True,
            "socks5_handshake": True,
            "tracker_tcp": True,
            "tracker_udp": True,
        }
    )
    assert not is_qb_download_ready(
        {
            "tcp_connect": True,
            "socks5_handshake": True,
            "tracker_tcp": True,
            "tracker_udp": False,
        }
    )
