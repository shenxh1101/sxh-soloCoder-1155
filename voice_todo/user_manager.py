import os
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
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

    def export_user(self, username: str, output_path: str) -> str:
        user_dir = self.config.user_dir(username)
        if not os.path.isdir(user_dir):
            raise ValueError(f"用户 '{username}' 不存在")
        output_path = os.path.abspath(output_path)
        if not output_path.endswith(".zip"):
            output_path += ".zip"
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(user_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, user_dir)
                    zf.write(file_path, arcname)
                    info = zf.getinfo(arcname)
                    info.comment = f"VoiceTodo/{username}/{arcname}".encode("utf-8")
            manifest = {
                "username": username,
                "exported_at": datetime.now().isoformat(),
                "version": "1.1",
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        return output_path

    def import_user(self, zip_path: str, new_username: str = "") -> str:
        zip_path = os.path.abspath(zip_path)
        if not os.path.isfile(zip_path):
            raise ValueError(f"文件不存在: {zip_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            if "manifest.json" not in zf.namelist():
                raise ValueError("不是有效的用户数据包（缺少 manifest.json）")

            manifest_data = zf.read("manifest.json")
            manifest = json.loads(manifest_data)

            if not new_username:
                new_username = manifest.get("username", "imported_user")

        user_dir = self.config.user_dir(new_username)

        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if member == "manifest.json":
                    continue
                target_path = os.path.join(user_dir, member)
                if member.endswith("/"):
                    os.makedirs(target_path, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zf.open(member) as src, open(target_path, "wb") as dst:
                    dst.write(src.read())

        self._storages.pop(new_username, None)
        storage = self.switch_user(new_username)
        storage.load()
        return new_username