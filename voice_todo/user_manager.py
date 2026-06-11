import os
from .config import Config
from .storage import TaskStorage


class UserManager:
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self._current_user: str = "default"
        self._storages: dict[str, TaskStorage] = {}

    @property
    def current_user(self) -> str:
        return self._current_user

    def switch_user(self, username: str):
        username = username.strip()
        if not username:
            raise ValueError("用户名不能为空")
        self._current_user = username
        if username not in self._storages:
            user_dir = self.config.user_dir(username)
            self._storages[username] = TaskStorage(user_dir)
        return self._storages[username]

    def get_storage(self, username: str = None) -> TaskStorage:
        username = username or self._current_user
        if username not in self._storages:
            user_dir = self.config.user_dir(username)
            self._storages[username] = TaskStorage(user_dir)
        return self._storages[username]

    def list_users(self) -> list[str]:
        users = []
        if os.path.exists(self.config.users_dir):
            for name in os.listdir(self.config.users_dir):
                user_path = os.path.join(self.config.users_dir, name)
                if os.path.isdir(user_path):
                    users.append(name)
        if not users:
            users.append("default")
            self.config.user_dir("default")
        if "default" not in users:
            users.insert(0, "default")
        return users

    def create_user(self, username: str) -> TaskStorage:
        username = username.strip()
        if not username:
            raise ValueError("用户名不能为空")
        return self.switch_user(username)