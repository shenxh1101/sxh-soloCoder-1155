import os
from datetime import datetime
from icalendar import Calendar, Event
from ..models import Task, TaskStatus


def export_to_ical(tasks: list[Task], output_path: str, title: str = "语音待办事项"):
    cal = Calendar()
    cal.add("prodid", "-//VoiceTodo//voice_todo//CN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", title)

    for task in tasks:
        if not task.due_date:
            continue
        try:
            dt = datetime.fromisoformat(task.due_date)
        except (ValueError, TypeError):
            continue

        event = Event()
        event.add("summary", task.title)
        event.add("dtstart", dt)
        event.add("dtend", dt)
        event.add("dtstamp", datetime.now())
        if task.note:
            event.add("description", task.note)
        if task.priority:
            event.add("priority", task.priority.value)
        event.add("uid", f"{task.task_id}@voice_todo")
        event.add("status", "CONFIRMED" if task.status != TaskStatus.DONE else "CANCELLED")
        cal.add_component(event)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    return output_path