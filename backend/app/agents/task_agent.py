"""Action item post-processing: merge duplicates, align assignees with attendees,
and correct attendee names that speech recognition misheard by one character."""

import re
from difflib import SequenceMatcher

from app.agents.review_agent import norm, person_core
from app.schemas.meeting import UNKNOWN, ActionItemIn, MinutesUpdate


def _one_off(a: str, b: str) -> bool:
    """Same length, same first character (surname), at most one differing character."""
    return len(a) == len(b) and 2 <= len(a) <= 4 and a != b and a[0] == b[0] and sum(x != y for x, y in zip(a, b, strict=True)) <= 1


def misheard_attendee(name: str, attendees: list[str]) -> str | None:
    """'이지훈 대리' → '이지은 대리' if exactly one attendee is a one-character variant."""
    core = norm(person_core(name))
    if any(norm(person_core(a)) == core for a in attendees):
        return None
    matches = [a for a in attendees if _one_off(core, norm(person_core(a)))]
    return matches[0] if len(matches) == 1 else None


def correct_names(m: MinutesUpdate, attendees: list[str]) -> list[str]:
    """Replaces misheard attendee names in the generated text (not in evidence quotes,
    which stay verbatim). Returns notes describing each correction."""
    fixes: dict[str, str] = {}
    for a in m.action_items:
        target = misheard_attendee(a.assignee, attendees) if a.assignee != UNKNOWN else None
        if target:
            fixes[person_core(a.assignee)] = person_core(target)
    if not fixes:
        return []

    def fix(text: str) -> str:
        for wrong, right in fixes.items():
            text = re.sub(re.escape(wrong), right, text)
        return text

    m.meeting_summary = fix(m.meeting_summary)
    for d in m.discussion_items:
        d.topic, d.content = fix(d.topic), fix(d.content)
    for dec in m.decisions:
        dec.content = fix(dec.content)
    for a in m.action_items:
        a.task, a.assignee = fix(a.task), fix(a.assignee)
    m.open_issues = [fix(x) for x in m.open_issues]
    m.next_meeting_checks = [fix(x) for x in m.next_meeting_checks]
    return [f"음성 인식 이름 '{w}'을(를) 참석자 '{r}'(으)로 보정" for w, r in fixes.items()]


def align_assignee(assignee: str, attendees: list[str]) -> str:
    """'이지은' → '이지은 대리' when that attendee was registered for the meeting."""
    if assignee == UNKNOWN:
        return assignee
    core = norm(person_core(assignee))
    for a in attendees:
        if core and core == norm(person_core(a)):
            return a
    return assignee


def _better(a: str, b: str) -> str:
    return b if a == UNKNOWN and b != UNKNOWN else a


def merge_duplicates(items: list[ActionItemIn], threshold: float = 0.8) -> list[ActionItemIn]:
    out: list[ActionItemIn] = []
    for item in items:
        twin = next((o for o in out if SequenceMatcher(None, norm(o.task), norm(item.task)).ratio() >= threshold), None)
        if twin is None:
            out.append(item)
            continue
        twin.assignee = _better(twin.assignee, item.assignee)
        twin.deadline = _better(twin.deadline, item.deadline)
        if not twin.evidence and item.evidence:
            twin.evidence, twin.timestamp = item.evidence, item.timestamp
    return out


def normalize(items: list[ActionItemIn], attendees: list[str]) -> list[ActionItemIn]:
    for i in items:
        i.assignee = align_assignee(i.assignee, attendees)
    return merge_duplicates(items)
