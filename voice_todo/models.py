import uuid
import json
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

    @classmethod
    def from_str(cls, s: str) -> "Priority":
        mapping = {
            "低": cls.LOW, "low": cls.LOW, "l": cls.LOW,
            "中": cls.MEDIUM, "medium": cls.MEDIUM, "m": cls.MEDIUM,
            "高": cls.HIGH, "high": cls.HIGH, "h": cls.HIGH,
            "紧急": cls.URGENT, "urgent": cls.URGENT, "u": cls.URGENT,
        }
        return mapping.get(s.lower(), cls.MEDIUM)

    def label_cn(self) -> str:
        return {self.LOW: "低", self.MEDIUM: "中", self.HIGH: "高", self.URGENT: "紧急"}[self]


class TaskStatus(Enum):
    PENDING = "pending"
    DONE = "done"
    ARCHIVED = "archived"


@dataclass
class Task:
    title: str
    note: str = ""
    due_date: Optional[str] = None
    priority: Priority = Priority.MEDIUM
    tags: list = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    archived_at: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        d = dict(d)
        d["priority"] = Priority(d["priority"])
        d["status"] = TaskStatus(d["status"])
        return cls(**d)

    def mark_done(self):
        self.status = TaskStatus.DONE
        self.completed_at = datetime.now().isoformat()

    def mark_pending(self):
        self.status = TaskStatus.PENDING
        self.completed_at = None

    def archive(self):
        self.status = TaskStatus.ARCHIVED
        self.archived_at = datetime.now().isoformat()

    def restore(self):
        self.status = TaskStatus.PENDING
        self.archived_at = None