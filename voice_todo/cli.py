import cmd
import sys
import os
from datetime import datetime
from .config import Config
from .user_manager import UserManager
from .models import Task, Priority, TaskStatus
from .nlp.parser import parse_task_text
from .search import fuzzy_search, search_by_tag
from .speech.asr import recognize_speech, is_microphone_available
from .speech.tts import speak
from .export.ical import export_to_ical
from .briefing import speak_briefing, print_briefing


def _format_task(task: Task, index: int = 0) -> str:
    status_icons = {TaskStatus.PENDING: "○", TaskStatus.DONE: "✓", TaskStatus.ARCHIVED: "📦"}
    icon = status_icons.get(task.status, "?")

    priority_icons = {
        Priority.LOW: "🟢", Priority.MEDIUM: "🟡",
        Priority.HIGH: "🟠", Priority.URGENT: "🔴",
    }
    p_icon = priority_icons.get(task.priority, "⚪")

    due_str = ""
    if task.due_date:
        try:
            dt = datetime.fromisoformat(task.due_date)
            due_str = f" 📅 {dt.strftime('%m-%d %H:%M')}"
        except (ValueError, TypeError):
            pass

    tags_str = ""
    if task.tags:
        tags_str = " " + " ".join(f"#{t}" for t in task.tags)

    note_str = ""
    if task.note:
        note_str = f"\n      备注: {task.note}"

    idx_str = f"[{index}] " if index else ""
    return f"  {icon} {p_icon} {idx_str}{task.title}{due_str}{tags_str}{note_str}"


class VoiceTodoCLI(cmd.Cmd):
    intro = """
╔══════════════════════════════════════════════╗
║        🎙️  语音待办事项管理工具  v1.0        ║
║                                              ║
║  输入 help 查看所有命令                       ║
║  输入 exit 退出程序                           ║
╚══════════════════════════════════════════════╝
"""
    prompt = "📋> "

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.user_manager = UserManager(self.config)
        self.user_manager.switch_user("default")
        self.storage = self.user_manager.get_storage()

    def do_user(self, arg: str):
        """切换用户: user <用户名>；不带参数查看当前用户"""
        if not arg.strip():
            users = self.user_manager.list_users()
            current = self.user_manager.current_user
            print(f"\n当前用户: {current}")
            print(f"所有用户: {', '.join(users)}")
            return
        try:
            self.storage = self.user_manager.switch_user(arg.strip())
            print(f"✅ 已切换到用户: {arg.strip()}")
        except Exception as e:
            print(f"❌ 切换失败: {e}")

    def do_list(self, arg: str):
        """列出任务: list [today|done|archive|all|tag:<标签>|search:<关键词>|upcoming]"""
        arg = arg.strip().lower()

        if arg == "today" or arg == "":
            tasks = self.storage.list_today()
            label = "今日待办"
        elif arg == "done":
            tasks = self.storage.list_done()
            label = "已完成"
        elif arg in ("archive", "archived"):
            tasks = self.storage.list_archived()
            label = "已归档"
        elif arg == "all":
            tasks = self.storage.list_all()
            label = "全部任务"
        elif arg.startswith("tag:"):
            tag = arg[4:].strip()
            tasks = search_by_tag(self.storage.list_active(), tag)
            label = f"标签 #{tag}"
        elif arg.startswith("search:"):
            query = arg[7:].strip()
            results = fuzzy_search(self.storage.list_all(), query)
            tasks = [t for t, _ in results]
            label = f"搜索: {query}"
        elif arg == "upcoming":
            tasks = self.storage.list_upcoming()
            label = "未来7天"
        else:
            tasks = self.storage.list_active()
            label = "待办事项"

        print(f"\n{'=' * 50}")
        print(f"  📋 {label} ({len(tasks)}项)")
        print(f"{'=' * 50}")
        if not tasks:
            print("  (暂无任务)")
        else:
            for i, t in enumerate(tasks, 1):
                print(_format_task(t, i))
        print(f"{'=' * 50}\n")

    def do_add(self, arg: str):
        """添加任务: add <任务内容> [#标签] [(优先级)] [时间描述]"""
        if not arg.strip():
            print("❌ 请输入任务内容。例如: add 明天下午三点开会 #工作 (高)")
            return

        parsed = parse_task_text(arg.strip())
        task = Task(
            title=parsed["title"],
            due_date=parsed["due_date"] or None,
            tags=parsed["tags"],
            priority=Priority.from_str(parsed["priority"]),
        )
        self.storage.add_task(task)
        print(f"✅ 已添加任务: [{task.task_id}] {task.title}")
        if task.due_date:
            try:
                dt = datetime.fromisoformat(task.due_date)
                print(f"   📅 截止: {dt.strftime('%Y-%m-%d %H:%M')}")
            except (ValueError, TypeError):
                pass
        if task.tags:
            print(f"   🏷️  标签: {', '.join(task.tags)}")
        print(f"   ⚡ 优先级: {task.priority.label_cn()}")

    def do_voice(self, arg: str):
        """语音输入: voice - 通过麦克风录音并自动解析为任务"""
        if not is_microphone_available():
            print("❌ 未检测到麦克风设备或 PyAudio 未安装。")
            print("   请安装 PyAudio: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio")
            print("   也可以使用 add 命令直接输入文字添加任务。")
            return

        try:
            lang = self.config.get("asr_language", "zh-CN")
            engine = self.config.get("asr_engine", "google")
            text = recognize_speech(language=lang, engine=engine)
        except RuntimeError as e:
            print(f"❌ {e}")
            return

        if not text:
            print("⚠️ 未识别到有效内容")
            return

        print(f"\n📝 识别结果: {text}")
        confirm = input("确认添加此任务? (Y/n/编辑): ").strip()
        if confirm.lower() == "n":
            print("已取消")
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
        print(f"✅ 已添加任务: [{task.task_id}] {task.title}")

    def do_done(self, arg: str):
        """完成任务: done <任务ID或序号>"""
        task = self._resolve_task(arg)
        if not task:
            return
        self.storage.mark_done(task.task_id)
        print(f"✅ 已完成: {task.title}")

    def do_undo(self, arg: str):
        """撤销完成: undo <任务ID或序号>"""
        task = self._resolve_task(arg)
        if not task:
            return
        self.storage.mark_pending(task.task_id)
        print(f"🔄 已恢复为待办: {task.title}")

    def do_edit(self, arg: str):
        """编辑任务: edit <任务ID或序号>"""
        task = self._resolve_task(arg)
        if not task:
            return

        print(f"\n正在编辑: {task.title}")
        print(f"当前信息:")
        print(f"  标题: {task.title}")
        print(f"  备注: {task.note or '(无)'}")
        print(f"  截止: {task.due_date or '(无)'}")
        print(f"  标签: {', '.join(task.tags) if task.tags else '(无)'}")
        print(f"  优先级: {task.priority.label_cn()}")
        print()

        new_title = input("新标题 (回车跳过): ").strip()
        if new_title:
            task.title = new_title

        new_note = input("新备注 (回车跳过): ").strip()
        if new_note:
            task.note = new_note

        new_due = input("新截止时间 (如: 明天下午三点, 回车跳过): ").strip()
        if new_due:
            parsed = parse_task_text(new_due)
            task.due_date = parsed["due_date"] or None

        new_tags = input("新标签 (空格分隔, 回车跳过): ").strip()
        if new_tags:
            task.tags = [t.strip().lstrip("#") for t in new_tags.split()]

        new_pri = input("新优先级 (低/中/高/紧急, 回车跳过): ").strip()
        if new_pri:
            task.priority = Priority.from_str(new_pri)

        self.storage.save()
        print(f"✅ 任务已更新: {task.title}")

    def do_note(self, arg: str):
        """添加备注: note <任务ID> <备注内容>"""
        parts = arg.strip().split(maxsplit=1)
        if len(parts) < 2:
            print("用法: note <任务ID或序号> <备注内容>")
            return
        task = self._resolve_task(parts[0])
        if not task:
            return
        task.note = parts[1]
        self.storage.save()
        print(f"✅ 备注已添加: {task.title}")

    def do_archive(self, arg: str):
        """归档任务: archive <任务ID或序号>"""
        task = self._resolve_task(arg)
        if not task:
            return
        self.storage.archive_task(task.task_id)
        print(f"📦 已归档: {task.title}")

    def do_restore(self, arg: str):
        """恢复归档任务: restore <任务ID或序号>"""
        all_archived = self.storage.list_archived()
        task = self._resolve_task(arg, pool=all_archived)
        if not task:
            print("未找到该归档任务，使用 'list archive' 查看所有归档任务")
            return
        self.storage.restore_task(task.task_id)
        print(f"🔄 已恢复: {task.title}")

    def do_delete(self, arg: str):
        """删除任务: delete <任务ID或序号>"""
        task = self._resolve_task(arg)
        if not task:
            return
        confirm = input(f"确定删除任务 '{task.title}'? (y/N): ").strip().lower()
        if confirm == "y":
            self.storage.delete_task(task.task_id)
            print(f"🗑️  已删除: {task.title}")
        else:
            print("已取消")

    def do_tag(self, arg: str):
        """管理标签: tag <任务ID> <标签1> [标签2...]"""
        task = self._resolve_task(arg)
        if not task:
            return
        print(f"当前标签: {', '.join(task.tags) if task.tags else '(无)'}")
        new_tags = input("新标签 (空格分隔, 留空清除所有): ").strip()
        if new_tags:
            task.tags = [t.strip().lstrip("#") for t in new_tags.split()]
        else:
            task.tags = []
        self.storage.save()
        print(f"✅ 标签已更新: [{task.task_id}] {task.title}")

    def do_priority(self, arg: str):
        """设置优先级: priority <任务ID> <低|中|高|紧急>"""
        parts = arg.strip().split(maxsplit=1)
        if len(parts) < 2:
            print("用法: priority <任务ID或序号> <低|中|高|紧急>")
            return
        task = self._resolve_task(parts[0])
        if not task:
            return
        task.priority = Priority.from_str(parts[1])
        self.storage.save()
        print(f"✅ 优先级已更新: [{task.task_id}] {task.title} → {task.priority.label_cn()}")

    def do_search(self, arg: str):
        """模糊搜索: search <关键词>"""
        if not arg.strip():
            print("请输入搜索关键词")
            return
        results = fuzzy_search(self.storage.list_all(), arg.strip())
        if not results:
            print("未找到匹配的任务")
            return
        print(f"\n🔍 搜索结果 ({len(results)}项):")
        for i, (task, score) in enumerate(results, 1):
            print(f"  [{i}] (匹配度:{score}%) {_format_task(task)}")

    def do_briefing(self, arg: str):
        """每日简报: briefing [speak] - 显示或播报今日待办"""
        tasks = self.storage.list_today()
        if "speak" in arg.lower():
            speak_briefing(tasks, self.user_manager.current_user)
        else:
            print_briefing(tasks, self.user_manager.current_user)

    def do_export(self, arg: str):
        """导出iCal: export [文件路径] - 默认导出到桌面"""
        tasks = self.storage.list_active()
        if not arg.strip():
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            path = os.path.join(desktop, "voice_todo_tasks.ics")
        else:
            path = arg.strip()

        try:
            export_to_ical(tasks, path)
            print(f"✅ 已导出 {len(tasks)} 个任务到: {path}")
        except Exception as e:
            print(f"❌ 导出失败: {e}")

    def do_stats(self, arg: str):
        """查看统计信息"""
        stats = self.storage.get_stats()
        print(f"\n{'=' * 40}")
        print(f"  📊 统计信息 (用户: {self.user_manager.current_user})")
        print(f"  {'─' * 36}")
        print(f"  🔴 待办: {stats['active']}")
        print(f"  ✅ 已完成: {stats['done']}")
        print(f"  📦 已归档: {stats['archived']}")
        print(f"  📅 今日任务: {stats['today']}")
        print(f"{'=' * 40}\n")

    def do_speak(self, arg: str):
        """TTS语音合成: speak <文字内容>"""
        if not arg.strip():
            print("请输入要朗读的文字")
            return
        speak(arg.strip())

    def do_config(self, arg: str):
        """查看或修改配置: config [key] [value]"""
        parts = arg.strip().split(maxsplit=2)
        if not parts[0]:
            for key, value in sorted(self.config._data.items()):
                print(f"  {key}: {value}")
            return
        if len(parts) == 1:
            print(f"  {parts[0]}: {self.config.get(parts[0], '(未设置)')}")
        else:
            self.config.set(parts[0], parts[1])
            print(f"✅ {parts[0]} = {parts[1]}")

    def do_exit(self, arg: str):
        """退出程序"""
        print("👋 再见!")
        return True

    def do_quit(self, arg: str):
        return self.do_exit(arg)

    def do_EOF(self, arg):
        print()
        return self.do_exit(arg)

    def _resolve_task(self, arg: str, pool: list = None):
        if pool is None:
            pool = self.storage.list_active()
        arg = arg.strip()
        if not arg:
            print("❌ 请提供任务ID或序号")
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

        print(f"❌ 未找到任务: {arg}")
        return None

    def emptyline(self):
        pass

    def default(self, line: str):
        print(f"未知命令: {line}，输入 help 查看可用命令")


def main():
    cli = VoiceTodoCLI()
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\n👋 再见!")
        sys.exit(0)


if __name__ == "__main__":
    main()