from settings_store import SecureSettingsStore


def test_secure_settings_round_trip(tmp_path):
    store = SecureSettingsStore(data_dir=str(tmp_path))

    defaults = store.load()
    assert defaults["qbittorrent"]["host"] == "127.0.0.1"

    saved = store.save(
        {
            "qbittorrent": {
                "host": "localhost",
                "port": 8181,
                "username": "alice",
                "password": "secret",
            },
            "auto_apply": {"enabled": True, "interval_minutes": 15},
        }
    )

    assert saved["qbittorrent"]["host"] == "localhost"
    assert saved["qbittorrent"]["password"] == "secret"

    loaded = store.load()
    assert loaded["qbittorrent"]["port"] == 8181
    assert loaded["auto_apply"]["enabled"] is True
