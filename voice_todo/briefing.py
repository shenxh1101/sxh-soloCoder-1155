from datetime import datetime, date
from .models import Task, Priority
from .speech.tts import speak


def generate_briefing_text(tasks: list[Task], username: str = "") -> str:
    today = date.today()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    today_str = f"{today.year}年{today.month}月{today.day}日 {weekday_cn[today.weekday()]}"

    parts = [f"早上好！今天是{today_str}。"]

    today_tasks = []
    upcoming_tasks = []

    for t in tasks:
        if t.due_date:
            try:
                due_dt = datetime.fromisoformat(t.due_date)
                due_date = due_dt.date()
                if due_date == today:
                    today_tasks.append(t)
                else:
                    upcoming_tasks.append(t)
            except (ValueError, TypeError):
                upcoming_tasks.append(t)
        else:
            upcoming_tasks.append(t)

    if today_tasks:
        parts.append(f"你今天有{len(today_tasks)}个待办事项：")
        for i, t in enumerate(today_tasks, 1):
            priority_label = t.priority.label_cn() if hasattr(t.priority, 'label_cn') else "中"
            extra = ""
            if t.due_date:
                try:
                    due_time = datetime.fromisoformat(t.due_date).strftime("%H:%M")
                    extra = f"，时间：{due_time}"
                except (ValueError, TypeError):
                    pass
            parts.append(f"第{i}项：{t.title}，优先级{priority_label}{extra}。")
    else:
        parts.append("你今天没有设定截止日期的待办事项。")

    if upcoming_tasks:
        pending = [t for t in upcoming_tasks if t.status.value == "pending"]
        parts.append(f"你还有{len(pending)}个未完成的事项。")

    parts.append("祝你今天工作顺利！")
    return "\n".join(parts)


def speak_briefing(tasks: list[Task], username: str = "", rate: int = 160):
    text = generate_briefing_text(tasks, username)
    speak(text, rate=rate, blocking=True)


def print_briefing(tasks: list[Task], username: str = ""):
    text = generate_briefing_text(tasks, username)
    print("\n" + "=" * 50)
    print(text)
    print("=" * 50 + "\n")