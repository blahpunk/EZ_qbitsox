from qbittorrent_client import QBittorrentClient


def test_proxy_type_mapping_for_string_backed_qb_versions():
    assert QBittorrentClient._desired_proxy_type_value('None') == 'SOCKS5'
    assert QBittorrentClient._is_socks5_proxy_type('SOCKS5') is True


def test_proxy_type_mapping_for_numeric_backed_qb_versions():
    assert QBittorrentClient._desired_proxy_type_value(0) == 2
    assert QBittorrentClient._is_socks5_proxy_type(2) is True
    assert QBittorrentClient._is_socks5_proxy_type(0) is False
