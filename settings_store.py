import copy
import json
import os
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_SETTINGS: Dict[str, Any] = {
    "qbittorrent": {
        "host": "127.0.0.1",
        "port": 8080,
        "username": "admin",
        "password": "",
    },
    "service": {
        "scan_interval_minutes": 30,
        "retest_after_minutes": 180,
        "max_workers": 50,
        "connect_timeout_seconds": 7,
        "source_timeout_seconds": 20,
    },
    "auto_apply": {
        "enabled": False,
        "interval_minutes": 60,
    },
}


def deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class SecureSettingsStore:
    def __init__(self, data_dir: str = "data", key_env_var: str = "EZ_QBITSOX_SECRET_KEY") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.key_env_var = key_env_var
        self.key_path = self.data_dir / ".settings_key"
        self.enc_path = self.data_dir / "secure_settings.enc"

        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        env_key = os.getenv(self.key_env_var)
        if env_key:
            key = env_key.encode("utf-8")
            Fernet(key)
            return key

        if self.key_path.exists():
            key = self.key_path.read_bytes().strip()
            Fernet(key)
            return key

        key = Fernet.generate_key()
        self.key_path.write_bytes(key + b"\n")
        os.chmod(self.key_path, 0o600)
        return key

    def load(self) -> Dict[str, Any]:
        defaults = copy.deepcopy(DEFAULT_SETTINGS)
        if not self.enc_path.exists():
            return defaults

        try:
            raw = self.enc_path.read_bytes()
            decrypted = self._fernet.decrypt(raw)
            stored = json.loads(decrypted.decode("utf-8"))
            if not isinstance(stored, dict):
                return defaults
            return deep_merge(defaults, stored)
        except (InvalidToken, OSError, ValueError, json.JSONDecodeError):
            return defaults

    def save(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self.load()
        merged = deep_merge(current, updates)

        payload = json.dumps(merged, sort_keys=True).encode("utf-8")
        encrypted = self._fernet.encrypt(payload)

        tmp_path = self.enc_path.with_suffix(".tmp")
        tmp_path.write_bytes(encrypted)
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(self.enc_path)
        return merged


def sanitize_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    clean = copy.deepcopy(settings)
    qb = clean.get("qbittorrent", {})
    qb["password_set"] = bool(qb.get("password"))
    qb["password"] = ""
    return clean
