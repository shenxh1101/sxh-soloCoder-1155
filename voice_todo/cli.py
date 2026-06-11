import cmd
import sys
import os
import threading
import time
from datetime import datetime, date
from .config import Config
from .user_manager import UserManager
from .models import Task, Priority, TaskStatus
from .nlp.parser import parse_task_text
from .search import fuzzy_search, search_by_tag
from .speech.asr import recognize_speech, is_microphone_available
from .speech.tts import speak
from .export.ical import export_to_ical
from .briefing import speak_briefing, print_briefing, generate_briefing_text


def _format_task(task: Task, index: int = 0) -> str:
    status_icons = {TaskStatus.PENDING: "\u25CB", TaskStatus.DONE: "\u2713", TaskStatus.ARCHIVED: "\U0001F4E6"}
    icon = status_icons.get(task.status, "?")

    priority_icons = {
        Priority.LOW: "\U0001F7E2", Priority.MEDIUM: "\U0001F7E1",
        Priority.HIGH: "\U0001F7E0", Priority.URGENT: "\U0001F534",
    }
    p_icon = priority_icons.get(task.priority, "\u26AA")

    due_str = ""
    if task.due_date:
        try:
            dt = datetime.fromisoformat(task.due_date)
            due_str = f" \U0001F4C5 {dt.strftime('%m-%d %H:%M')}"
        except (ValueError, TypeError):
            pass

    tags_str = ""
    if task.tags:
        tags_str = " " + " ".join(f"#{t}" for t in task.tags)

    note_str = ""
    if task.note:
        note_str = f"\n      \u5907\u6CE8: {task.note}"

    recurrence_str = ""
    if task.is_template:
        recurrence_str = f" \U0001F504{task.recurrence_label}"

    reminder_str = ""
    if task.reminder_minutes is not None:
        reminder_str = f" \u23F0{task.reminder_label}"

    idx_str = f"[{index}] " if index else ""
    return f"  {icon} {p_icon} {idx_str}{task.title}{due_str}{recurrence_str}{reminder_str}{tags_str}{note_str}"


class VoiceTodoCLI(cmd.Cmd):
    intro = """
\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557
\u2551        \U0001F399\uFE0F  \u8BED\u97F3\u5F85\u529E\u4E8B\u9879\u7BA1\u7406\u5DE5\u5177  v1.1        \u2551
\u2551                                              \u2551
\u2551  \u8F93\u5165 help \u67E5\u770B\u6240\u6709\u547D\u4EE4                       \u2551
\u2551  \u8F93\u5165 exit \u9000\u51FA\u7A0B\u5E8F                           \u2551
\u255A\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255D
"""
    prompt = "\U0001F4CB> "

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.user_manager = UserManager(self.config)
        self.user_manager.switch_user("default")
        self.storage = self.user_manager.get_storage()
        self._last_view: list[Task] = []
        self._reminder_thread = None
        self._reminder_running = False
        self._startup_check()

    def _startup_check(self):
        self.storage.clear_old_reminders()
        generated = self.storage.generate_recurring_tasks()
        if generated:
            print(f"\U0001F504 \u5DF2\u81EA\u52A8\u751F\u6210 {len(generated)} \u4E2A\u5468\u671F\u4EFB\u52A1")
        self._start_reminder_thread()
        self._check_auto_briefing()

    def _check_auto_briefing(self):
        briefing_time_str = self.config.get("briefing_time", "08:00")
        briefing_state = self.storage.get_briefing_state()
        last_date = briefing_state.get("last_briefing_date", "")
        today_str = date.today().isoformat()

        if last_date == today_str:
            return

        now = datetime.now()
        try:
            h, m = map(int, briefing_time_str.split(":"))
        except (ValueError, TypeError):
            return

        if now.hour < h or (now.hour == h and now.minute < m):
            return

        tasks = self.storage.list_today()
        if not tasks:
            self.storage.set_briefing_done(today_str)
            return

        print("\n\u23F0 \u6BCF\u65E5\u7B80\u62A5\u65F6\u95F4\u5230\u4E86\uFF0C\u6B63\u5728\u64AD\u62A5\u4ECA\u65E5\u5F85\u529E\u4E8B\u9879...")
        try:
            speak_briefing(tasks, self.user_manager.current_user,
                          rate=int(self.config.get("tts_rate", 160)))
        except Exception:
            print_briefing(tasks, self.user_manager.current_user)
        self.storage.set_briefing_done(today_str)

    def _start_reminder_thread(self):
        if self._reminder_thread and self._reminder_thread.is_alive():
            return
        self._reminder_running = True
        self._reminder_thread = threading.Thread(target=self._reminder_loop, daemon=True)
        self._reminder_thread.start()

    def _reminder_loop(self):
        while self._reminder_running:
            try:
                due = self.storage.get_due_reminders(window_minutes=30)
                for task in due:
                    if not self.storage.has_reminded(task.task_id):
                        self.storage.mark_reminded(task.task_id)
                        reminder_text = self._build_reminder_text(task)
                        print(f"\n\u23F0 {reminder_text}")
                        try:
                            speak(reminder_text, blocking=False)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(30)

    def _build_reminder_text(self, task: Task) -> str:
        parts = [f"\u63D0\u9192: {task.title}"]
        if task.due_date:
            try:
                dt = datetime.fromisoformat(task.due_date)
                remaining = dt - datetime.now()
                mins = max(0, int(remaining.total_seconds() / 60))
                if mins < 60:
                    parts.append(f"\uFF0C\u8FD8\u6709 {mins} \u5206\u949F\u5230\u671F")
                else:
                    parts.append(f"\uFF0C\u8FD8\u6709 {mins // 60} \u5C0F\u65F6 {mins % 60} \u5206\u949F\u5230\u671F")
            except (ValueError, TypeError):
                pass
        return "".join(parts)

    def do_user(self, arg: str):
        """\u5207\u6362\u7528\u6237: user <\u7528\u6237\u540D>\uFF1B\u4E0D\u5E26\u53C2\u6570\u67E5\u770B\u5F53\u524D\u7528\u6237"""
        if not arg.strip():
            users = self.user_manager.list_users()
            current = self.user_manager.current_user
            print(f"\n\u5F53\u524D\u7528\u6237: {current}")
            print(f"\u6240\u6709\u7528\u6237: {', '.join(users)}")
            return
        try:
            self.storage = self.user_manager.switch_user(arg.strip())
            self._last_view = []
            self.storage.clear_old_reminders()
            self.storage.generate_recurring_tasks()
            print(f"\u2705 \u5DF2\u5207\u6362\u5230\u7528\u6237: {arg.strip()}")
        except Exception as e:
            print(f"\u274C \u5207\u6362\u5931\u8D25: {e}")

    def do_list(self, arg: str):
        """\u5217\u51FA\u4EFB\u52A1: list [today|done|archive|all|tag:<\u6807\u7B7E>|search:<\u5173\u952E\u8BCD>|upcoming|templates]"""
        arg = arg.strip().lower()

        if arg == "today":
            tasks = self.storage.list_today()
            label = "\u4ECA\u65E5\u5F85\u529E"
        elif arg == "done":
            tasks = self.storage.list_done()
            label = "\u5DF2\u5B8C\u6210"
        elif arg in ("archive", "archived"):
            tasks = self.storage.list_archived()
            label = "\u5DF2\u5F52\u6863"
        elif arg == "all":
            tasks = self.storage.list_all()
            label = "\u5168\u90E8\u4EFB\u52A1"
        elif arg.startswith("tag:"):
            tag = arg[4:].strip()
            tasks = search_by_tag(self.storage.list_active(), tag)
            label = f"\u6807\u7B7E #{tag}"
        elif arg.startswith("search:"):
            query = arg[7:].strip()
            results = fuzzy_search(self.storage.list_all(), query)
            tasks = [t for t, _ in results]
            label = f"\u641C\u7D22: {query}"
        elif arg == "upcoming":
            tasks = self.storage.list_upcoming()
            label = "\u672A\u67657\u5929"
        elif arg == "templates":
            tasks = self.storage.list_templates()
            label = "\u5468\u671F\u6A21\u677F"
        else:
            tasks = self.storage.list_active()
            label = "\u5F85\u529E\u4E8B\u9879"

        self._last_view = tasks
        self._print_task_list(tasks, label)

    def do_add(self, arg: str):
        """\u6DFB\u52A0\u4EFB\u52A1: add <\u4EFB\u52A1\u5185\u5BB9> [#\u6807\u7B7E] [(\u4F18\u5148\u7EA7)] [\u65F6\u95F4\u63CF\u8FF0]"""
        if not arg.strip():
            print("\u274C \u8BF7\u8F93\u5165\u4EFB\u52A1\u5185\u5BB9\u3002\u4F8B\u5982: add \u660E\u5929\u4E0B\u5348\u4E09\u70B9\u5F00\u4F1A #\u5DE5\u4F5C (\u9AD8)")
            return

        parsed = parse_task_text(arg.strip())
        task = Task(
            title=parsed["title"],
            due_date=parsed["due_date"] or None,
            tags=parsed["tags"],
            priority=Priority.from_str(parsed["priority"]),
        )
        default_reminder = self.storage.get_user_config("default_reminder_minutes")
        if default_reminder is not None and task.due_date:
            task.reminder_minutes = int(default_reminder)

        self.storage.add_task(task)
        print(f"\u2705 \u5DF2\u6DFB\u52A0\u4EFB\u52A1: [{task.task_id}] {task.title}")
        if task.due_date:
            try:
                dt = datetime.fromisoformat(task.due_date)
                print(f"   \U0001F4C5 \u622A\u6B62: {dt.strftime('%Y-%m-%d %H:%M')}")
            except (ValueError, TypeError):
                pass
        if task.tags:
            print(f"   \U0001F3F7\uFE0F  \u6807\u7B7E: {', '.join(task.tags)}")
        print(f"   \u26A1 \u4F18\u5148\u7EA7: {task.priority.label_cn()}")

    def do_voice(self, arg: str):
        """\u8BED\u97F3\u8F93\u5165: voice - \u901A\u8FC7\u9EA6\u514B\u98CE\u5F55\u97F3\u5E76\u81EA\u52A8\u89E3\u6790\u4E3A\u4EFB\u52A1"""
        if not is_microphone_available():
            print("\u274C \u672A\u68C0\u6D4B\u5230\u9EA6\u514B\u98CE\u8BBE\u5907\u6216 PyAudio \u672A\u5B89\u88C5\u3002")
            print("   \u8BF7\u5B89\u88C5 PyAudio: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio")
            print("   \u4E5F\u53EF\u4EE5\u4F7F\u7528 add \u547D\u4EE4\u76F4\u63A5\u8F93\u5165\u6587\u5B57\u6DFB\u52A0\u4EFB\u52A1\u3002")
            return

        try:
            lang = self.config.get("asr_language", "zh-CN")
            engine = self.config.get("asr_engine", "google")
            text = recognize_speech(language=lang, engine=engine)
        except RuntimeError as e:
            print(f"\u274C {e}")
            return

        if not text:
            print("\u26A0\uFE0F \u672A\u8BC6\u522B\u5230\u6709\u6548\u5185\u5BB9")
            return

        print(f"\n\U0001F4DD \u8BC6\u522B\u7ED3\u679C: {text}")
        confirm = input("\u786E\u8BA4\u6DFB\u52A0\u6B64\u4EFB\u52A1? (Y/n/\u7F16\u8F91): ").strip()
        if confirm.lower() == "n":
            print("\u5DF2\u53D6\u6D88")
            return
        if confirm and confirm.lower() != "y":
            text = confirm

        parsed = parse_task_text(text)
        task = Task(
            title=parsed["title"],
            due_date=parsed["due_date"] or None,
            tags=parsed["tags"],
            priority=Priority.from_str(parsed["priority"]),
        )
        self.storage.add_task(task)
        print(f"\u2705 \u5DF2\u6DFB\u52A0\u4EFB\u52A1: [{task.task_id}] {task.title}")

    def do_done(self, arg: str):
        """\u5B8C\u6210\u4EFB\u52A1: done <\u4EFB\u52A1ID\u6216\u5E8F\u53F7>"""
        task = self._resolve_task(arg)
        if not task:
            return
        if task.is_template:
            print("\u274C \u5468\u671F\u6A21\u677F\u4E0D\u80FD\u76F4\u63A5\u5B8C\u6210\uFF0C\u8BF7\u64CD\u4F5C\u6A21\u677F\u751F\u6210\u7684\u5177\u4F53\u4EFB\u52A1")
            return
        self.storage.mark_done(task.task_id)
        print(f"\u2705 \u5DF2\u5B8C\u6210: {task.title}")

    def do_undo(self, arg: str):
        """\u64A4\u9500\u5B8C\u6210: undo <\u4EFB\u52A1ID\u6216\u5E8F\u53F7>"""
        task = self._resolve_task(arg)
        if not task:
            return
        self.storage.mark_pending(task.task_id)
        print(f"\U0001F504 \u5DF2\u6062\u590D\u4E3A\u5F85\u529E: {task.title}")

    def do_edit(self, arg: str):
        """\u7F16\u8F91\u4EFB\u52A1: edit <\u4EFB\u52A1ID\u6216\u5E8F\u53F7>"""
        task = self._resolve_task(arg)
        if not task:
            return

        print(f"\n\u6B63\u5728\u7F16\u8F91: {task.title}")
        print(f"\u5F53\u524D\u4FE1\u606F:")
        print(f"  \u6807\u9898: {task.title}")
        print(f"  \u5907\u6CE8: {task.note or '(\u65E0)'}")
        print(f"  \u622A\u6B62: {task.due_date or '(\u65E0)'}")
        print(f"  \u6807\u7B7E: {', '.join(task.tags) if task.tags else '(\u65E0)'}")
        print(f"  \u4F18\u5148\u7EA7: {task.priority.label_cn()}")
        print(f"  \u63D0\u9192: {task.reminder_label}")
        print(f"  \u5468\u671F: {task.recurrence_label or '\u65E0'}")
        print()

        new_title = input("\u65B0\u6807\u9898 (\u56DE\u8F66\u8DF3\u8FC7): ").strip()
        if new_title:
            task.title = new_title

        new_note = input("\u65B0\u5907\u6CE8 (\u56DE\u8F66\u8DF3\u8FC7): ").strip()
        if new_note:
            task.note = new_note

        new_due = input("\u65B0\u622A\u6B62\u65F6\u95F4 (\u5982: \u660E\u5929\u4E0B\u5348\u4E09\u70B9, \u56DE\u8F66\u8DF3\u8FC7): ").strip()
        if new_due:
            parsed = parse_task_text(new_due)
            task.due_date = parsed["due_date"] or None

        new_tags = input("\u65B0\u6807\u7B7E (\u7A7A\u683C\u5206\u9694, \u56DE\u8F66\u8DF3\u8FC7): ").strip()
        if new_tags:
            task.tags = [t.strip().lstrip("#") for t in new_tags.split()]

        new_pri = input("\u65B0\u4F18\u5148\u7EA7 (\u4F4E/\u4E2D/\u9AD8/\u7D27\u6025, \u56DE\u8F66\u8DF3\u8FC7): ").strip()
        if new_pri:
            task.priority = Priority.from_str(new_pri)

        new_reminder = input("\u63D0\u9192\u63D0\u524D\u5206\u949F\u6570 (0=\u51C6\u70B9, \u8F93\u5165'off'\u5173\u95ED\u63D0\u9192, \u56DE\u8F66\u8DF3\u8FC7): ").strip()
        if new_reminder:
            if new_reminder.lower() == "off":
                task.reminder_minutes = None
            else:
                try:
                    task.reminder_minutes = int(new_reminder)
                except ValueError:
                    print("\u26A0\uFE0F \u65E0\u6548\u7684\u5206\u949F\u6570\uFF0C\u4FDD\u6301\u539F\u503C")

        self.storage.save()
        print(f"\u2705 \u4EFB\u52A1\u5DF2\u66F4\u65B0: {task.title}")

    def do_note(self, arg: str):
        """\u6DFB\u52A0\u5907\u6CE8: note <\u4EFB\u52A1ID> <\u5907\u6CE8\u5185\u5BB9>"""
        parts = arg.strip().split(maxsplit=1)
        if len(parts) < 2:
            print("\u7528\u6CD5: note <\u4EFB\u52A1ID\u6216\u5E8F\u53F7> <\u5907\u6CE8\u5185\u5BB9>")
            return
        task = self._resolve_task(parts[0])
        if not task:
            return
        task.note = parts[1]
        self.storage.save()
        print(f"\u2705 \u5907\u6CE8\u5DF2\u6DFB\u52A0: {task.title}")

    def do_archive(self, arg: str):
        """\u5F52\u6863\u4EFB\u52A1: archive <\u4EFB\u52A1ID\u6216\u5E8F\u53F7>"""
        task = self._resolve_task(arg)
        if not task:
            return
        self.storage.archive_task(task.task_id)
        print(f"\U0001F4E6 \u5DF2\u5F52\u6863: {task.title}")

    def do_restore(self, arg: str):
        """\u6062\u590D\u5F52\u6863\u4EFB\u52A1: restore <\u4EFB\u52A1ID\u6216\u5E8F\u53F7> (\u9700\u5148 list archive \u67E5\u770B\u5F52\u6863\u5217\u8868)"""
        task = self._resolve_task(arg)
        if not task:
            print("\u672A\u627E\u5230\u8BE5\u5F52\u6863\u4EFB\u52A1\uFF0C\u4F7F\u7528 'list archive' \u67E5\u770B\u5F52\u6863\u5217\u8868\u540E\u518D\u64CD\u4F5C")
            return
        if task.status != TaskStatus.ARCHIVED:
            print("\u8BE5\u4EFB\u52A1\u672A\u88AB\u5F52\u6863")
            return
        self.storage.restore_task(task.task_id)
        print(f"\U0001F504 \u5DF2\u6062\u590D: {task.title}")

    def do_delete(self, arg: str):
        """\u5220\u9664\u4EFB\u52A1: delete <\u4EFB\u52A1ID\u6216\u5E8F\u53F7>"""
        task = self._resolve_task(arg)
        if not task:
            return
        confirm = input(f"\u786E\u5B9A\u5220\u9664\u4EFB\u52A1 '{task.title}'? (y/N): ").strip().lower()
        if confirm == "y":
            self.storage.delete_task(task.task_id)
            print(f"\U0001F5D1\uFE0F  \u5DF2\u5220\u9664: {task.title}")
        else:
            print("\u5DF2\u53D6\u6D88")

    def do_tag(self, arg: str):
        """\u7BA1\u7406\u6807\u7B7E: tag <\u4EFB\u52A1ID> <\u6807\u7B7E1> [\u6807\u7B7E2...]"""
        task = self._resolve_task(arg)
        if not task:
            return
        print(f"\u5F53\u524D\u6807\u7B7E: {', '.join(task.tags) if task.tags else '(\u65E0)'}")
        new_tags = input("\u65B0\u6807\u7B7E (\u7A7A\u683C\u5206\u9694, \u7559\u7A7A\u6E05\u9664\u6240\u6709): ").strip()
        if new_tags:
            task.tags = [t.strip().lstrip("#") for t in new_tags.split()]
        else:
            task.tags = []
        self.storage.save()
        print(f"\u2705 \u6807\u7B7E\u5DF2\u66F4\u65B0: [{task.task_id}] {task.title}")

    def do_priority(self, arg: str):
        """\u8BBE\u7F6E\u4F18\u5148\u7EA7: priority <\u4EFB\u52A1ID> <\u4F4E|\u4E2D|\u9AD8|\u7D27\u6025>"""
        parts = arg.strip().split(maxsplit=1)
        if len(parts) < 2:
            print("\u7528\u6CD5: priority <\u4EFB\u52A1ID\u6216\u5E8F\u53F7> <\u4F4E|\u4E2D|\u9AD8|\u7D27\u6025>")
            return
        task = self._resolve_task(parts[0])
        if not task:
            return
        task.priority = Priority.from_str(parts[1])
        self.storage.save()
        print(f"\u2705 \u4F18\u5148\u7EA7\u5DF2\u66F4\u65B0: [{task.task_id}] {task.title} \u2192 {task.priority.label_cn()}")

    def do_remind(self, arg: str):
        """\u8BBE\u7F6E\u63D0\u9192: remind <\u4EFB\u52A1ID> <\u5206\u949F\u6570|off>"""
        parts = arg.strip().split(maxsplit=1)
        if len(parts) < 2:
            print("\u7528\u6CD5: remind <\u4EFB\u52A1ID\u6216\u5E8F\u53F7> <\u5206\u949F\u6570|off>")
            print("  \u4F8B\u5982: remind 1 30     (\u63D0\u524D30\u5206\u949F\u63D0\u9192)")
            print("  \u4F8B\u5982: remind 1 off    (\u5173\u95ED\u63D0\u9192)")
            return

        task = self._resolve_task(parts[0])
        if not task:
            return

        if parts[1].lower() == "off":
            minutes = None
        else:
            try:
                minutes = int(parts[1])
                if minutes < 0:
                    print("\u274C \u63D0\u524D\u5206\u949F\u6570\u4E0D\u80FD\u4E3A\u8D1F\u6570")
                    return
            except ValueError:
                print("\u274C \u8BF7\u8F93\u5165\u6709\u6548\u7684\u5206\u949F\u6570\u6216 'off'")
                return

        self.storage.set_reminder(task.task_id, minutes)
        if minutes is None:
            print(f"\u2705 \u5DF2\u5173\u95ED\u63D0\u9192: {task.title}")
        elif minutes == 0:
            print(f"\u2705 \u5DF2\u8BBE\u7F6E\u51C6\u70B9\u63D0\u9192: {task.title}")
        else:
            print(f"\u2705 \u5DF2\u8BBE\u7F6E\u63D0\u524D{minutes}\u5206\u949F\u63D0\u9192: {task.title}")

    def do_reminders(self, arg: str):
        """\u67E5\u770B\u6240\u6709\u5F85\u63D0\u9192\u4EFB\u52A1: reminders"""
        tasks = self.storage.get_all_reminders()
        if not tasks:
            print("\n  (\u6CA1\u6709\u8BBE\u7F6E\u63D0\u9192\u7684\u4EFB\u52A1)")
            print("  \u4F7F\u7528 remind <\u5E8F\u53F7> <\u5206\u949F\u6570> \u4E3A\u4EFB\u52A1\u8BBE\u7F6E\u63D0\u9192\n")
            return
        self._last_view = tasks
        self._print_task_list(tasks, "\u5F85\u63D0\u9192\u4EFB\u52A1")

    def do_recurring(self, arg: str):
        """\u7BA1\u7406\u5468\u671F\u4EFB\u52A1: recurring add|list|delete <\u53C2\u6570>"""
        parts = arg.strip().split(maxsplit=2)
        cmd = parts[0].lower() if parts else ""

        if cmd == "list" or not cmd:
            templates = self.storage.list_templates()
            self._last_view = templates
            self._print_task_list(templates, "\u5468\u671F\u6A21\u677F")
            return

        if cmd == "add":
            if len(parts) < 2:
                print("\u7528\u6CD5: recurring add daily|\u6BCF\u5929|\u6BCF\u5468\u4E00|...|\u6BCF\u67081\u53F7 <\u4EFB\u52A1\u5185\u5BB9>")
                print("  \u4F8B\u5982: recurring add \u6BCF\u5929 \u65E9\u4E0A\u516B\u70B9\u5F00\u4F1A #\u5DE5\u4F5C (\u9AD8)")
                print("  \u4F8B\u5982: recurring add \u6BCF\u5468\u4E00 \u63D0\u4EA4\u5468\u62A5")
                print("  \u4F8B\u5982: recurring add \u6BCF\u67081\u53F7 \u8FD8\u623F\u8D37")
                return

            rule_part = parts[1]
            task_part = parts[2] if len(parts) > 2 else ""

            if not task_part:
                print("\u274C \u8BF7\u63D0\u4F9B\u4EFB\u52A1\u5185\u5BB9")
                return

            recurrence = self._parse_recurrence(rule_part)
            if not recurrence:
                print(f"\u274C \u4E0D\u652F\u6301\u7684\u5468\u671F\u89C4\u5219: {rule_part}")
                print("  \u652F\u6301: \u6BCF\u5929/daily, \u6BCF\u5468\u4E00~\u6BCF\u5468\u65E5, \u6BCF\u67081\u53F7~\u6BCF\u670828\u53F7")
                return

            parsed = parse_task_text(task_part)
            task = Task(
                title=parsed["title"],
                due_date=parsed["due_date"] or None,
                tags=parsed["tags"],
                priority=Priority.from_str(parsed["priority"]),
                recurrence=recurrence,
            )
            self.storage.add_task(task)
            print(f"\u2705 \u5DF2\u521B\u5EFA\u5468\u671F\u6A21\u677F: [{task.task_id}] {task.title} \U0001F504{task.recurrence_label}")
            generated = self.storage.generate_recurring_tasks()
            if generated:
                print(f"   \U0001F504 \u5DF2\u81EA\u52A8\u751F\u6210 {len(generated)} \u4E2A\u4EFB\u52A1\u5B9E\u4F8B")
            return

        if cmd == "delete":
            if len(parts) < 2:
                print("\u7528\u6CD5: recurring delete <\u6A21\u677FID\u6216 list\u4E2D\u7684\u5E8F\u53F7>")
                print("  \u5148\u7528 'list templates' \u67E5\u770B\u6A21\u677F\u5217\u8868")
                return
            task = self._resolve_task(parts[1])
            if not task:
                return
            if not task.is_template:
                print("\u274C \u8BE5\u4EFB\u52A1\u4E0D\u662F\u5468\u671F\u6A21\u677F")
                return
            self.storage.delete_task(task.task_id)
            print(f"\U0001F5D1\uFE0F  \u5DF2\u5220\u9664\u5468\u671F\u6A21\u677F: {task.title}")
            return

        if cmd == "help":
            print("""
\u5468\u671F\u4EFB\u52A1\u547D\u4EE4:
  recurring list              \u67E5\u770B\u6240\u6709\u5468\u671F\u6A21\u677F
  recurring add <\u89C4\u5219> <\u5185\u5BB9>   \u6DFB\u52A0\u5468\u671F\u4EFB\u52A1
  recurring delete <\u5E8F\u53F7>       \u5220\u9664\u5468\u671F\u6A21\u677F

\u89C4\u5219\u683C\u5F0F:
  \u6BCF\u5929/daily          \u6BCF\u5929\u91CD\u590D
  \u6BCF\u5468\u4E00~daily     \u6BCF\u5468\u7684\u67D0\u4E00\u5929 (\u7528 0-6 \u6216 \u4E00~\u65E5)
  \u6BCF\u67081\u53F7~28\u53F7    \u6BCF\u6708\u7684\u67D0\u4E00\u5929
""")
            return

        print(f"\u672A\u77E5\u547D\u4EE4: {cmd}\uFF0C\u8F93\u5165 recurring help \u67E5\u770B\u5E2E\u52A9")

    def _parse_recurrence(self, rule: str) -> str:
        rule = rule.strip().lower()
        if rule in ("daily", "\u6BCF\u5929"):
            return "daily"

        weekday_names = {
            "\u4E00": 0, "\u4E8C": 1, "\u4E09": 2, "\u56DB": 3,
            "\u4E94": 4, "\u516D": 5, "\u65E5": 6, "\u5929": 6,
        }

        for name, wd in weekday_names.items():
            if rule in (f"\u6BCF\u5468{name}", f"weekly:{wd}"):
                return f"weekly:{wd}"

        match = None
        import re as _re
        m = _re.match(r"weekly:(\d)", rule)
        if m:
            wd = int(m.group(1))
            if 0 <= wd <= 6:
                return f"weekly:{wd}"

        m = _re.match(r"\u6BCF\u6708(\d{1,2})\u53F7?", rule)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 28:
                return f"monthly:{day}"
        m = _re.match(r"monthly:(\d{1,2})", rule)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 28:
                return f"monthly:{day}"

        return ""

    def do_search(self, arg: str):
        """\u6A21\u7CCA\u641C\u7D22: search <\u5173\u952E\u8BCD>"""
        if not arg.strip():
            print("\u8BF7\u8F93\u5165\u641C\u7D22\u5173\u952E\u8BCD")
            return
        results = fuzzy_search(self.storage.list_all(), arg.strip())
        if not results:
            print("\u672A\u627E\u5230\u5339\u914D\u7684\u4EFB\u52A1")
            return
        tasks = [t for t, _ in results]
        self._last_view = tasks
        self._print_task_list(tasks, f"\u641C\u7D22\u7ED3\u679C ({len(results)}\u9879)")

    def do_briefing(self, arg: str):
        """\u6BCF\u65E5\u7B80\u62A5: briefing [speak] - \u663E\u793A\u6216\u64AD\u62A5\u4ECA\u65E5\u5F85\u529E"""
        tasks = self.storage.list_today()
        if "speak" in arg.lower():
            speak_briefing(tasks, self.user_manager.current_user,
                          rate=int(self.config.get("tts_rate", 160)))
        else:
            print_briefing(tasks, self.user_manager.current_user)

    def do_export(self, arg: str):
        """\u5BFC\u51FAiCal: export [\u6587\u4EF6\u8DEF\u5F84] - \u9ED8\u8BA4\u5BFC\u51FA\u5230\u684C\u9762"""
        tasks = self.storage.list_active()
        if not arg.strip():
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            path = os.path.join(desktop, "voice_todo_tasks.ics")
        else:
            path = arg.strip()

        try:
            export_to_ical(tasks, path)
            print(f"\u2705 \u5DF2\u5BFC\u51FA {len(tasks)} \u4E2A\u4EFB\u52A1\u5230: {path}")
        except Exception as e:
            print(f"\u274C \u5BFC\u51FA\u5931\u8D25: {e}")

    def do_export_user(self, arg: str):
        """\u5BFC\u51FA\u7528\u6237\u6570\u636E: export_user [\u7528\u6237\u540D] [\u8F93\u51FA\u8DEF\u5F84]"""
        parts = arg.strip().split(maxsplit=1)
        username = parts[0].strip() if parts else self.user_manager.current_user
        output = parts[1].strip() if len(parts) > 1 else ""

        if not output:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            output = os.path.join(desktop, f"voice_todo_{username}.zip")

        try:
            result = self.user_manager.export_user(username, output)
            print(f"\u2705 \u5DF2\u5BFC\u51FA\u7528\u6237 '{username}' \u6570\u636E\u5230: {result}")
        except Exception as e:
            print(f"\u274C \u5BFC\u51FA\u5931\u8D25: {e}")

    def do_import_user(self, arg: str):
        """\u5BFC\u5165\u7528\u6237\u6570\u636E: import_user <zip\u6587\u4EF6\u8DEF\u5F84> [\u65B0\u7528\u6237\u540D]"""
        parts = arg.strip().split(maxsplit=1)
        if not parts[0]:
            print("\u7528\u6CD5: import_user <zip\u6587\u4EF6\u8DEF\u5F84> [\u65B0\u7528\u6237\u540D]")
            return

        zip_path = parts[0].strip()
        new_name = parts[1].strip() if len(parts) > 1 else ""

        try:
            result_name = self.user_manager.import_user(zip_path, new_name)
            print(f"\u2705 \u5DF2\u5BFC\u5165\u7528\u6237\u6570\u636E\uFF0C\u7528\u6237\u540D: {result_name}")
            print(f"   \u4F7F\u7528 'user {result_name}' \u5207\u6362\u5230\u8BE5\u7528\u6237")
        except Exception as e:
            print(f"\u274C \u5BFC\u5165\u5931\u8D25: {e}")

    def do_stats(self, arg: str):
        """\u67E5\u770B\u7EDF\u8BA1\u4FE1\u606F"""
        stats = self.storage.get_stats()
        print(f"\n{'=' * 40}")
        print(f"  \U0001F4CA \u7EDF\u8BA1\u4FE1\u606F (\u7528\u6237: {self.user_manager.current_user})")
        print(f"  {'\u2500' * 36}")
        print(f"  \U0001F534 \u5F85\u529E: {stats['active']}")
        print(f"  \u2705 \u5DF2\u5B8C\u6210: {stats['done']}")
        print(f"  \U0001F4E6 \u5DF2\u5F52\u6863: {stats['archived']}")
        print(f"  \U0001F4C5 \u4ECA\u65E5\u4EFB\u52A1: {stats['today']}")
        print(f"  \U0001F504 \u5468\u671F\u6A21\u677F: {stats['templates']}")
        print(f"{'=' * 40}\n")

    def do_speak(self, arg: str):
        """TTS\u8BED\u97F3\u5408\u6210: speak <\u6587\u5B57\u5185\u5BB9>"""
        if not arg.strip():
            print("\u8BF7\u8F93\u5165\u8981\u6717\u8BFB\u7684\u6587\u5B57")
            return
        speak(arg.strip())

    def do_config(self, arg: str):
        """\u67E5\u770B\u6216\u4FEE\u6539\u914D\u7F6E: config [key] [value]"""
        parts = arg.strip().split(maxsplit=2)
        if not parts[0]:
            for key, value in sorted(self.config._data.items()):
                print(f"  {key}: {value}")
            return
        if len(parts) == 1:
            print(f"  {parts[0]}: {self.config.get(parts[0], '(\u672A\u8BBE\u7F6E)')}")
        else:
            self.config.set(parts[0], parts[1])
            print(f"\u2705 {parts[0]} = {parts[1]}")

    def do_exit(self, arg: str):
        """\u9000\u51FA\u7A0B\u5E8F"""
        self._reminder_running = False
        print("\U0001F44B \u518D\u89C1!")
        return True

    def do_quit(self, arg: str):
        return self.do_exit(arg)

    def do_EOF(self, arg):
        print()
        return self.do_exit(arg)

    def _resolve_task(self, arg: str, pool: list = None):
        if pool is None:
            pool = self._last_view
        if not pool:
            pool = self.storage.list_active()
        arg = arg.strip()
        if not arg:
            print("\u274C \u8BF7\u63D0\u4F9B\u4EFB\u52A1ID\u6216\u5E8F\u53F7")
            return None

        for task in pool:
            if task.task_id == arg:
                return task

        try:
            idx = int(arg)
            if 1 <= idx <= len(pool):
                return pool[idx - 1]
        except ValueError:
            pass

        print(f"\u274C \u672A\u627E\u5230\u4EFB\u52A1: {arg}")
        return None

    def _print_task_list(self, tasks: list[Task], label: str):
        print(f"\n{'=' * 50}")
        print(f"  \U0001F4CB {label} ({len(tasks)}\u9879)")
        print(f"{'=' * 50}")
        if not tasks:
            print("  (\u6682\u65E0\u4EFB\u52A1)")
        else:
            for i, t in enumerate(tasks, 1):
                print(_format_task(t, i))
        print(f"{'=' * 50}\n")

    def emptyline(self):
        pass

    def default(self, line: str):
        print(f"\u672A\u77E5\u547D\u4EE4: {line}\uFF0C\u8F93\u5165 help \u67E5\u770B\u53EF\u7528\u547D\u4EE4")


def main():
    cli = VoiceTodoCLI()
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\n\U0001F44B \u518D\u89C1!")
        sys.exit(0)


if __name__ == "__main__":
    main()