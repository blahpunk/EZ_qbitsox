from qbittorrent_client import QBittorrentClient


def test_qb_connection_test_fails_without_credentials():
    client = QBittorrentClient(host='127.0.0.1', port=8080, username='', password='')
    ok, details = client.test_connection()

    assert ok is False
    assert 'Missing qBittorrent username/password' in details['message']
