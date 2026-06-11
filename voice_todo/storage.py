import os
import json
import copy
from datetime import datetime, timedelta, date
from typing import Optional
from .models import Task, TaskStatus, Priority


def _parse_due_datetime(due_date: str) -> Optional[datetime]:
    if not due_date:
        return None
    try:
        return datetime.fromisoformat(due_date)
    except (ValueError, TypeError):
        return None


class TaskStorage:
    def __init__(self, user_dir: str):
        self.tasks_path = os.path.join(user_dir, "tasks.json")
        self.archive_path = os.path.join(user_dir, "archive.json")
        self.templates_path = os.path.join(user_dir, "templates.json")
        self.briefing_state_path = os.path.join(user_dir, "briefing_state.json")
        self.user_config_path = os.path.join(user_dir, "user_config.json")
        self._tasks: dict[str, Task] = {}
        self._archived: dict[str, Task] = {}
        self._templates: dict[str, Task] = {}
        self._user_config: dict = {}
        self.load()

    def load(self):
        self._tasks = self._load_json(self.tasks_path)
        self._archived = self._load_json(self.archive_path)
        self._templates = self._load_json(self.templates_path)
        if os.path.exists(self.user_config_path):
            with open(self.user_config_path, "r", encoding="utf-8") as f:
                self._user_config = json.load(f)
        if os.path.exists(self.briefing_state_path):
            with open(self.briefing_state_path, "r", encoding="utf-8") as f:
                self._briefing_state = json.load(f)
        else:
            self._briefing_state = {}

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
        self._save_json(self.templates_path, self._templates)

    def add_task(self, task: Task):
        if task.is_template:
            self._templates[task.task_id] = task
        else:
            self._tasks[task.task_id] = task
        self.save()

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id) or self._archived.get(task_id) or self._templates.get(task_id)

    def delete_task(self, task_id: str):
        self._tasks.pop(task_id, None)
        self._archived.pop(task_id, None)
        self._templates.pop(task_id, None)
        self.save()

    def archive_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id) or self._templates.get(task_id)
        if not task:
            return False
        if task.is_template:
            self._templates.pop(task_id, None)
        else:
            del self._tasks[task_id]
        task.archive()
        self._archived[task_id] = task
        self.save()
        return True

    def restore_task(self, task_id: str) -> bool:
        task = self._archived.get(task_id)
        if not task:
            return False
        task.restore()
        if task.is_template:
            self._templates[task_id] = task
        else:
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

    def list_templates(self) -> list[Task]:
        tasks = list(self._templates.values())
        tasks.sort(key=lambda t: t.created_at, reverse=True)
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
            "templates": len(self._templates),
        }

    def set_reminder(self, task_id: str, minutes: Optional[int]):
        task = self.get_task(task_id)
        if not task:
            return False
        task.reminder_minutes = minutes
        self.save()
        return True

    def get_due_reminders(self, window_minutes: int = 15) -> list[Task]:
        now = datetime.now()
        result = []
        for t in self._tasks.values():
            if t.status != TaskStatus.PENDING:
                continue
            if t.reminder_minutes is None:
                continue
            dt = _parse_due_datetime(t.due_date)
            if dt is None:
                continue
            remind_at = dt - timedelta(minutes=t.reminder_minutes)
            time_diff = (remind_at - now).total_seconds()
            if 0 <= time_diff <= window_minutes * 60:
                result.append(t)
        result.sort(key=lambda t: t.due_date or "")
        return result

    def get_all_reminders(self) -> list[Task]:
        result = []
        for t in self._tasks.values():
            if t.status != TaskStatus.PENDING:
                continue
            if t.reminder_minutes is not None and t.due_date:
                result.append(t)
        result.sort(key=lambda t: t.due_date or "")
        return result

    def has_reminded(self, task_id: str) -> bool:
        reminded = self._briefing_state.get("reminded_ids", [])
        return task_id in reminded

    def mark_reminded(self, task_id: str):
        reminded = self._briefing_state.get("reminded_ids", [])
        if task_id not in reminded:
            reminded.append(task_id)
        self._briefing_state["reminded_ids"] = reminded[-50:]
        self._save_briefing_state()

    def clear_old_reminders(self):
        all_ids = set()
        for t in self._tasks.values():
            if t.reminder_minutes is not None and t.due_date:
                all_ids.add(t.task_id)
        reminded = self._briefing_state.get("reminded_ids", [])
        self._briefing_state["reminded_ids"] = [rid for rid in reminded if rid in all_ids]
        self._save_briefing_state()

    def generate_recurring_tasks(self) -> list[Task]:
        now = datetime.now()
        today = now.date()
        generated = []
        for template in list(self._templates.values()):
            instances = self._generate_from_template(template, today)
            for inst in instances:
                inst.source_template_id = template.task_id
                self._tasks[inst.task_id] = inst
                generated.append(inst)
        if generated:
            self.save()
        return generated

    def _generate_from_template(self, template: Task, today: date) -> list[Task]:
        generated = []
        rule = template.recurrence
        if not rule:
            return generated

        existing_instances = [
            t for t in self._tasks.values()
            if t.source_template_id == template.task_id
        ]
        existing = {}
        for t in existing_instances:
            if t.due_date:
                try:
                    d = datetime.fromisoformat(t.due_date).date().isoformat()
                    existing[d] = t
                except (ValueError, TypeError):
                    pass

        lookahead = 14
        for offset in range(lookahead + 1):
            target_date = today + timedelta(days=offset)
            if target_date.isoformat() in existing:
                continue
            should_create = False
            result_date = None

            if rule == "daily":
                should_create = True
                result_date = target_date
            elif rule.startswith("weekly:"):
                try:
                    wd = int(rule.split(":")[1])
                    if target_date.weekday() == wd:
                        should_create = True
                        result_date = target_date
                except (ValueError, IndexError):
                    pass
            elif rule.startswith("monthly:"):
                try:
                    target_day = int(rule.split(":")[1])
                    if target_date.day == target_day:
                        should_create = True
                        result_date = target_date
                except (ValueError, IndexError):
                    pass

            if should_create and result_date:
                inst = copy.deepcopy(template)
                inst.task_id = Task.__dataclass_fields__["task_id"].default_factory()
                inst.recurrence = None
                inst.reminder_minutes = template.reminder_minutes
                inst.created_at = datetime.now().isoformat()
                due_dt = datetime.combine(result_date, datetime.min.time())
                if template.due_date:
                    try:
                        tm = datetime.fromisoformat(template.due_date).time()
                        due_dt = datetime.combine(result_date, tm)
                    except (ValueError, TypeError):
                        pass
                inst.due_date = due_dt.isoformat()
                generated.append(inst)
        return generated

    def get_briefing_state(self) -> dict:
        return self._briefing_state

    def set_briefing_done(self, briefing_date: str):
        self._briefing_state["last_briefing_date"] = briefing_date
        self._save_briefing_state()

    def _save_briefing_state(self):
        with open(self.briefing_state_path, "w", encoding="utf-8") as f:
            json.dump(self._briefing_state, f, ensure_ascii=False, indent=2)

    def get_user_config(self, key: str, default=None):
        return self._user_config.get(key, default)

    def set_user_config(self, key: str, value):
        self._user_config[key] = value
        with open(self.user_config_path, "w", encoding="utf-8") as f:
            json.dump(self._user_config, f, ensure_ascii=False, indent=2)