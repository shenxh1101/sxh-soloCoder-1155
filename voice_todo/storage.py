import os
import json
from datetime import datetime, timedelta
from typing import Optional
from .models import Task, TaskStatus


class TaskStorage:
    def __init__(self, user_dir: str):
        self.tasks_path = os.path.join(user_dir, "tasks.json")
        self.archive_path = os.path.join(user_dir, "archive.json")
        self._tasks: dict[str, Task] = {}
        self._archived: dict[str, Task] = {}
        self.load()

    def load(self):
        self._tasks = self._load_json(self.tasks_path)
        self._archived = self._load_json(self.archive_path)

    def _load_json(self, path: str) -> dict[str, Task]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {tid: Task.from_dict(t) for tid, t in data.items()}

    def _save_json(self, path: str, data: dict[str, Task]):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {tid: t.to_dict() for tid, t in data.items()},
                f, ensure_ascii=False, indent=2,
            )

    def save(self):
        active = {tid: t for tid, t in self._tasks.items() if t.status != TaskStatus.ARCHIVED}
        archived = {tid: t for tid, t in self._tasks.items() if t.status == TaskStatus.ARCHIVED}
        archived.update(self._archived)
        self._save_json(self.tasks_path, active)
        self._save_json(self.archive_path, archived)

    def add_task(self, task: Task):
        self._tasks[task.task_id] = task
        self.save()

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id) or self._archived.get(task_id)

    def delete_task(self, task_id: str):
        self._tasks.pop(task_id, None)
        self._archived.pop(task_id, None)
        self.save()

    def archive_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.archive()
        self._archived[task_id] = task
        del self._tasks[task_id]
        self.save()
        return True

    def restore_task(self, task_id: str) -> bool:
        task = self._archived.get(task_id)
        if not task:
            return False
        task.restore()
        self._tasks[task_id] = task
        del self._archived[task_id]
        self.save()
        return True

    def mark_done(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.mark_done()
        self.save()
        return True

    def mark_pending(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.mark_pending()
        self.save()
        return True

    def list_active(self) -> list[Task]:
        tasks = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        tasks.sort(key=lambda t: (t.priority.value, t.created_at), reverse=True)
        return tasks

    def list_done(self) -> list[Task]:
        tasks = [t for t in self._tasks.values() if t.status == TaskStatus.DONE]
        tasks.sort(key=lambda t: t.completed_at or "", reverse=True)
        return tasks

    def list_archived(self) -> list[Task]:
        tasks = list(self._archived.values())
        tasks.sort(key=lambda t: t.archived_at or "", reverse=True)
        return tasks

    def list_all(self) -> list[Task]:
        tasks = list(self._tasks.values()) + list(self._archived.values())
        return tasks

    def list_today(self) -> list[Task]:
        today = datetime.now().strftime("%Y-%m-%d")
        result = []
        for t in self._tasks.values():
            if t.status != TaskStatus.PENDING:
                continue
            if t.due_date and t.due_date[:10] == today:
                result.append(t)
            elif not t.due_date:
                result.append(t)
        result.sort(key=lambda t: (t.priority.value, t.created_at), reverse=True)
        return result

    def list_upcoming(self, days: int = 7) -> list[Task]:
        today = datetime.now().date()
        end_date = today + timedelta(days=days)
        result = []
        for t in self._tasks.values():
            if t.status != TaskStatus.PENDING:
                continue
            if not t.due_date:
                continue
            try:
                due_date = datetime.fromisoformat(t.due_date).date()
                if today <= due_date <= end_date:
                    result.append(t)
            except (ValueError, TypeError):
                continue
        result.sort(key=lambda t: t.due_date or "")
        return result

    def get_stats(self) -> dict:
        active = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        done = [t for t in self._tasks.values() if t.status == TaskStatus.DONE]
        archived = list(self._archived.values())
        today_tasks = self.list_today()
        return {
            "active": len(active),
            "done": len(done),
            "archived": len(archived),
            "today": len(today_tasks),
        }