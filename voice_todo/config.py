import os
import json
from pathlib import Path

DEFAULT_CONFIG = {
    "asr_engine": "google",
    "asr_language": "zh-CN",
    "tts_rate": 160,
    "tts_voice": "",
    "briefing_time": "08:00",
    "data_dir": "",
}


class Config:
    def __init__(self, base_dir: str = ""):
        if not base_dir:
            base_dir = os.path.join(str(Path.home()), ".voice_todo")
        self.base_dir = base_dir
        self.users_dir = os.path.join(base_dir, "users")
        self.config_path = os.path.join(base_dir, "config.json")
        os.makedirs(self.users_dir, exist_ok=True)
        self._data = {}
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        for key, default in DEFAULT_CONFIG.items():
            if key not in self._data:
                self._data[key] = default

    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def user_dir(self, username: str) -> str:
        user_dir = os.path.join(self.users_dir, username)
        os.makedirs(user_dir, exist_ok=True)
        return user_dir