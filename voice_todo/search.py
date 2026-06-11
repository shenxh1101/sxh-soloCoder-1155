from thefuzz import fuzz, process
from .models import Task


def fuzzy_search(tasks: list[Task], query: str, threshold: int = 40) -> list[tuple[Task, int]]:
    if not query.strip():
        return [(t, 100) for t in tasks]
    results = []
    for task in tasks:
        scores = []
        scores.append(fuzz.partial_ratio(query.lower(), task.title.lower()))
        if task.note:
            scores.append(fuzz.partial_ratio(query.lower(), task.note.lower()))
        for tag in task.tags:
            scores.append(fuzz.partial_ratio(query.lower(), tag.lower()))
        best = max(scores) if scores else 0
        if best >= threshold:
            results.append((task, best))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def search_by_tag(tasks: list[Task], tag: str) -> list[Task]:
    tag_lower = tag.lower().strip()
    return [t for t in tasks if any(tag_lower in t.lower() for t in t.tags)]