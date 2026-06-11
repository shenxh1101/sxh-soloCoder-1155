import re
from datetime import datetime, timedelta, date

WEEKDAY_CN = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
WEEKDAY_NUM = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}

CN_DIGIT_MAP = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
    "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19,
    "二十": 20, "二十一": 21, "二十二": 22, "二十三": 23,
}


def _cn_to_digit(text: str) -> int:
    if text in CN_DIGIT_MAP:
        return CN_DIGIT_MAP[text]
    return None

CN_NUM_RE = r"([零一二两三四五六七八九十][一二三四五六七八九]?|二十[一二三四]?|\d{1,2})"


def _parse_num(text: str) -> int:
    if text.isdigit():
        return int(text)
    return _cn_to_digit(text) or 0


TIME_PATTERNS = [
    (re.compile(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?"), "full_date"),
    (re.compile(r"(\d{1,2})月(\d{1,2})日?"), "month_day"),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "iso_date"),
    (re.compile(r"明天"), "tomorrow"),
    (re.compile(r"后天"), "day_after_tomorrow"),
    (re.compile(r"大后天"), "day_after_day_after_tomorrow"),
    (re.compile(r"今天"), "today"),
    (re.compile(r"下下周([一二三四五六日天])"), "next_next_weekday"),
    (re.compile(r"下周([一二三四五六日天])"), "next_weekday"),
    (re.compile(r"下星期([一二三四五六日天])"), "next_weekday"),
    (re.compile(r"本周([一二三四五六日天])"), "this_weekday"),
    (re.compile(r"星期([一二三四五六日天])"), "this_weekday"),
    (re.compile(r"周([一二三四五六日天])"), "this_weekday"),
    (re.compile(r"下个月(\d{1,2})号?"), "next_month_day"),
    (re.compile(r"下个?月"), "next_month"),
    (re.compile(r"下周"), "next_week"),
    (re.compile(r"下下个?月"), "next_next_month"),
    (re.compile(r"下下周"), "next_next_week"),
    (re.compile(r"([零一二两三四五六七八九十]+|\d+)个?天后"), "days_later_cn"),
    (re.compile(r"([零一二两三四五六七八九十]+|\d+)天后"), "days_later_cn"),
    (re.compile(r"([零一二两三四五六七八九十]+|\d+)个?天?后"), "days_later_cn"),
    (re.compile(CN_NUM_RE + "个?(星期|周)后"), "weeks_later_cn"),
]

TIME_OF_DAY = [
    (re.compile(r"(早上|早晨|上午)" + CN_NUM_RE + "点半"), lambda m: f"{_parse_num(m.group(2)):02d}:30"),
    (re.compile(r"(下午)" + CN_NUM_RE + "点半"), lambda m: f"{_parse_num(m.group(2)) + 12:02d}:30" if _parse_num(m.group(2)) != 12 else "12:30"),
    (re.compile(r"(晚上)" + CN_NUM_RE + "点半"), lambda m: f"{_parse_num(m.group(2)) + 12:02d}:30" if _parse_num(m.group(2)) <= 11 else f"{_parse_num(m.group(2)):02d}:00"),
    (re.compile(r"(早上|早晨|上午)" + CN_NUM_RE + "点"), lambda m: f"{_parse_num(m.group(2)):02d}:00"),
    (re.compile(r"(中午)" + CN_NUM_RE + "点"), lambda m: f"12:00"),
    (re.compile(r"(下午)" + CN_NUM_RE + "点"), lambda m: f"{_parse_num(m.group(2)) + 12:02d}:00" if _parse_num(m.group(2)) != 12 else "12:00"),
    (re.compile(r"(晚上)" + CN_NUM_RE + "点"), lambda m: f"{_parse_num(m.group(2)) + 12:02d}:00" if _parse_num(m.group(2)) <= 11 else f"{_parse_num(m.group(2)):02d}:00"),
    (re.compile(r"(\d{1,2})[点:：](\d{1,2})"), lambda m: f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"),
    (re.compile(CN_NUM_RE + "点半"), lambda m: f"{_parse_num(m.group(1)):02d}:30"),
    (re.compile(CN_NUM_RE + "点"), lambda m: f"{_parse_num(m.group(1)):02d}:00"),
]

TAG_PATTERN = re.compile(r"[#＃](\S+)")
PRIORITY_PATTERNS = [
    (re.compile(r"[（(](紧急|urgent|高|high|中|medium|低|low)[）)]"), "priority"),
]
PRIORITY_MAP = {
    "紧急": "urgent", "urgent": "urgent",
    "高": "high", "high": "high",
    "中": "medium", "medium": "medium",
    "低": "low", "low": "low",
}


def _get_weekday_date(weekday_cn: str, reference: date = None) -> date:
    if reference is None:
        reference = date.today()
    target_wd = WEEKDAY_CN.get(weekday_cn, WEEKDAY_CN.get("一", 0))
    current_wd = reference.weekday()
    diff = target_wd - current_wd
    if diff <= 0:
        diff += 7
    return reference + timedelta(days=diff)


def _get_next_weekday_date(weekday_cn: str, reference: date = None) -> date:
    if reference is None:
        reference = date.today()
    target_wd = WEEKDAY_CN.get(weekday_cn, WEEKDAY_CN.get("一", 0))
    current_wd = reference.weekday()
    diff = target_wd - current_wd + 7
    return reference + timedelta(days=diff)


def _get_next_next_weekday_date(weekday_cn: str, reference: date = None) -> date:
    if reference is None:
        reference = date.today()
    target_wd = WEEKDAY_CN.get(weekday_cn, WEEKDAY_CN.get("一", 0))
    current_wd = reference.weekday()
    diff = target_wd - current_wd + 14
    return reference + timedelta(days=diff)


def parse_datetime(text: str, reference: date = None) -> tuple[str, str]:
    if reference is None:
        reference = date.today()

    result_date = None
    remaining = text

    for pattern, ptype in TIME_PATTERNS:
        m = pattern.search(remaining)
        if m:
            try:
                if ptype == "full_date":
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    result_date = date(y, mo, d)
                elif ptype == "month_day":
                    mo, d = int(m.group(1)), int(m.group(2))
                    result_date = date(reference.year, mo, d)
                    if result_date < reference:
                        result_date = date(reference.year + 1, mo, d)
                elif ptype == "iso_date":
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    result_date = date(y, mo, d)
                elif ptype == "tomorrow":
                    result_date = reference + timedelta(days=1)
                elif ptype == "day_after_tomorrow":
                    result_date = reference + timedelta(days=2)
                elif ptype == "day_after_day_after_tomorrow":
                    result_date = reference + timedelta(days=3)
                elif ptype == "today":
                    result_date = reference
                elif ptype == "next_weekday":
                    result_date = _get_next_weekday_date(m.group(1), reference)
                elif ptype == "this_weekday":
                    result_date = _get_weekday_date(m.group(1), reference)
                elif ptype == "next_next_weekday":
                    result_date = _get_next_next_weekday_date(m.group(1), reference)
                elif ptype == "next_month_day":
                    day = int(m.group(1))
                    mo = reference.month + 1
                    y = reference.year
                    if mo > 12:
                        mo = 1
                        y += 1
                    result_date = date(y, mo, min(day, 28))
                elif ptype == "days_later_cn":
                    days = _parse_num(m.group(1))
                    result_date = reference + timedelta(days=days)
                elif ptype == "weeks_later_cn":
                    weeks = _parse_num(m.group(1))
                    result_date = reference + timedelta(weeks=weeks)
                elif ptype == "next_month":
                    mo = reference.month + 1
                    y = reference.year
                    if mo > 12:
                        mo = 1
                        y += 1
                    result_date = date(y, mo, 1)
                elif ptype == "next_week":
                    result_date = reference + timedelta(days=7)
                elif ptype == "next_next_month":
                    mo = reference.month + 2
                    y = reference.year
                    if mo > 12:
                        mo -= 12
                        y += 1
                    result_date = date(y, mo, 1)
                elif ptype == "next_next_week":
                    result_date = reference + timedelta(days=14)

                remaining = remaining[:m.start()] + remaining[m.end():]
                break
            except (ValueError, IndexError):
                continue

    time_str = "00:00"
    for pattern, extractor in TIME_OF_DAY:
        m = pattern.search(remaining)
        if m:
            try:
                time_str = extractor(m) if callable(extractor) else extractor
                remaining = remaining[:m.start()] + remaining[m.end():]
            except (ValueError, IndexError):
                continue
            break

    if result_date is None:
        return remaining.strip(), ""

    datetime_str = f"{result_date.isoformat()}T{time_str}:00"
    return remaining.strip(), datetime_str


def parse_tags(text: str) -> tuple[str, list[str]]:
    tags = []
    remaining = text
    for m in TAG_PATTERN.finditer(text):
        tag = m.group(1).strip().rstrip(",.，。、")
        if tag and tag not in tags:
            tags.append(tag)
        remaining = remaining.replace(m.group(0), "", 1)
    return remaining.strip(), tags


def parse_priority(text: str) -> tuple[str, str]:
    for pattern, _ in PRIORITY_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).lower()
            priority = PRIORITY_MAP.get(raw, PRIORITY_MAP.get(raw.split("/")[0], "medium"))
            text = text[:m.start()] + text[m.end():]
            return text.strip(), priority
    return text.strip(), "medium"


def parse_task_text(text: str, reference: date = None) -> dict:
    cleaned, tags = parse_tags(text)
    cleaned, priority = parse_priority(cleaned)
    title, due_date = parse_datetime(cleaned, reference)
    title = title.strip().rstrip(",.，。、;；").strip()
    if not title:
        title = text.strip().rstrip(",.，。、;；").strip()
    result = {
        "title": title,
        "due_date": due_date,
        "tags": tags,
        "priority": priority,
    }
    return result