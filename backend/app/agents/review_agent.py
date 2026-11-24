"""Grounding checks: everything the LLM claims must be traceable to the transcript.

- decisions / action items: the quoted evidence must be found in the transcript;
  the timestamp is then taken from the matching segment (not trusted from the LLM).
  Unverifiable decisions are moved to open issues marked "[검증 필요]".
- assignee / deadline: kept only if they actually occur in the transcript.
- speaker: always 미확인 (Whisper output has no diarisation).
- agenda items with no discussion get an explicit "논의 확인되지 않음" entry.
"""

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.agents.llm_schemas import FinalMinutes
from app.schemas.meeting import UNKNOWN, ActionItemIn, Decision, DiscussionItem, MinutesUpdate
from app.services.stt_service import Segment

log = logging.getLogger(__name__)

NEEDS_REVIEW = "[검증 필요]"
TITLES = ("님", "씨", "과장", "대리", "차장", "부장", "팀장", "책임", "선임", "수석", "주임", "사원", "매니저", "프로", "이사", "상무", "전무", "대표")
DATE_TOKEN = re.compile(r"\d+\s*(?:월|일|주|시|분)|[월화수목금토일]요일|이번\s*주|다음\s*주|다다음\s*주|오늘|내일|모레|월말|월초|연말|주말|분기|상반기|하반기|\d{4}[-./]\d{1,2}[-./]\d{1,2}")
TS = re.compile(r"^\d{2}:\d{2}:\d{2}$")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def norm(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text).lower()


def fmt_ts(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_ts(ts: str) -> float | None:
    if not TS.match(ts or ""):
        return None
    h, m, s = (int(x) for x in ts.split(":"))
    return h * 3600 + m * 60 + s


@dataclass
class Grounding:
    segments: list[Segment]
    full_norm: str = field(init=False)

    def __post_init__(self) -> None:
        self.full_norm = norm(" ".join(s.text for s in self.segments))

    def locate(self, quote: str, threshold: float = 0.6) -> Segment | None:
        """Finds the segment a quote came from (exact after normalisation, else fuzzy over 1–3 segment windows)."""
        q = norm(quote)
        if len(q) < 4:
            return None
        # 1) exact match inside a single segment
        for seg in self.segments:
            if q in norm(seg.text):
                return seg
        # 2) exact or fuzzy match across 1–3 adjacent segments (quotes may span a split)
        best_window: list[Segment] | None = None
        best_score = 0.0
        for i in range(len(self.segments)):
            for width in (1, 2, 3):
                window = self.segments[i : i + width]
                if len(window) < width:
                    break
                text = norm(" ".join(s.text for s in window))
                if q in text:
                    score = 1.0
                else:
                    sm = SequenceMatcher(None, q, text, autojunk=False)
                    # quick_ratio is a cheap upper bound — skip hopeless candidates.
                    if sm.real_quick_ratio() < max(threshold, best_score) or sm.quick_ratio() < max(threshold, best_score):
                        continue
                    score = sm.ratio()
                if score > best_score:
                    best_window, best_score = window, score
        if best_window is None or best_score < threshold:
            return None
        # Timestamp = the segment within the window that overlaps the quote most.
        return max(best_window, key=lambda s: SequenceMatcher(None, q, norm(s.text), autojunk=False).find_longest_match(0, len(q), 0, len(norm(s.text))).size)

    def mentions(self, text: str) -> bool:
        n = norm(text)
        return bool(n) and n in self.full_norm

    def near_mention(self, name: str) -> str | None:
        """Finds a transcript spelling of `name` that differs by at most one character
        (same first character, i.e. surname) — e.g. STT heard 이지훈 for 이지은."""
        n = norm(name)
        if not 2 <= len(n) <= 4:
            return None
        if n in self.full_norm:
            return n
        text = self.full_norm
        for i in range(len(text) - len(n) + 1):
            cand = text[i : i + len(n)]
            if cand[0] == n[0] and sum(a != b for a, b in zip(cand, n, strict=True)) <= 1:
                return cand
        return None


def person_core(name: str) -> str:
    n = name.strip()
    for t in sorted(TITLES, key=len, reverse=True):
        n = re.sub(rf"\s*{t}$", "", n)
    return n.strip()


def check_assignee(assignee: str, g: Grounding, evidence: str, attendees: list[str] = ()) -> str:  # type: ignore[assignment]
    if not assignee or assignee == UNKNOWN:
        return UNKNOWN
    core = person_core(assignee)
    if len(norm(core)) >= 2 and (g.mentions(core) or norm(core) in norm(evidence)):
        return assignee.strip()
    # A registered attendee whose name STT misheard by one character still counts.
    if any(norm(person_core(a)) == norm(core) for a in attendees) and g.near_mention(core):
        return assignee.strip()
    return UNKNOWN


_NATIVE_TENS = {"열": 10, "스물": 20, "스무": 20, "서른": 30, "마흔": 40, "쉰": 50, "예순": 60, "일흔": 70, "여든": 80, "아흔": 90}
_NATIVE_ONES = {"하나": 1, "한": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "석": 3, "넷": 4, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}
_SINO = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_NATIVE_RE = re.compile(
    rf"({'|'.join(sorted(_NATIVE_TENS, key=len, reverse=True))})?({'|'.join(sorted(_NATIVE_ONES, key=len, reverse=True))})?"
)
# Sino-Korean numbers only when they contain 십/백 (e.g. 십이, 이십삼, 백) — single
# syllables like 이/사/오 are far more often ordinary words.
_SINO_RE = re.compile(r"([일이삼사오육칠팔구]?백)?([일이삼사오육칠팔구]?십)([일이삼사오육칠팔구])?|([일이삼사오육칠팔구]?백)")


def korean_numbers(text: str) -> set[str]:
    """Digit strings for Korean numerals in `text` (STT often writes 열두, 스물세, 십이월)."""
    found: set[str] = set()
    for m in _NATIVE_RE.finditer(text):
        tens, ones = m.group(1), m.group(2)
        if tens or (ones and len(ones) > 1) or (ones and m.end() < len(text) and text[m.end()] in " 개명건번시달주"):
            found.add(str(_NATIVE_TENS.get(tens or "", 0) + _NATIVE_ONES.get(ones or "", 0)))
    for m in _SINO_RE.finditer(text):
        whole = m.group(0)
        if not whole:
            continue
        value = 0
        hundreds = m.group(1) or m.group(4)
        if hundreds:
            value += 100 * (_SINO.get(hundreds[0], 1) if len(hundreds) > 1 else 1)
        if m.group(2):
            value += 10 * (_SINO.get(m.group(2)[0], 1) if len(m.group(2)) > 1 else 1)
        if m.group(3):
            value += _SINO[m.group(3)]
        found.add(str(value))
    found.discard("0")
    return found


def ungrounded_numbers(text: str, g: Grounding, extra: str = "") -> list[str]:
    """Numbers in generated prose that never occur in the transcript (or the meeting
    info the user typed) — e.g. a model inventing "21건" or "90%"."""
    source = " ".join(s.text for s in g.segments) + " " + extra
    known = set(NUMBER.findall(source)) | korean_numbers(source)
    return [n for n in dict.fromkeys(NUMBER.findall(text)) if n not in known]


def check_deadline(deadline: str, g: Grounding, evidence: str) -> str:
    if not deadline or deadline == UNKNOWN:
        return UNKNOWN
    if g.mentions(deadline) or norm(deadline) in norm(evidence):
        return deadline.strip()
    tokens = DATE_TOKEN.findall(deadline)
    if tokens and all(g.mentions(t) for t in tokens):
        return deadline.strip()
    return UNKNOWN


@dataclass
class ReviewResult:
    minutes: MinutesUpdate
    notes: list[str]


def review(
    final: FinalMinutes,
    segments: list[Segment],
    agenda: list[str],
    duration: float | None = None,
    attendees: list[str] | None = None,
    meeting_info: str = "",
) -> ReviewResult:
    attendees = attendees or []
    g = Grounding(segments)
    notes: list[str] = []
    max_t = duration if duration is not None else (segments[-1].end if segments else 0)

    def ts_or_unknown(ts: str) -> str:
        t = parse_ts(ts)
        return ts if t is not None and t <= max_t + 1 else UNKNOWN

    decisions: list[Decision] = []
    open_issues = [_strip_unknown_suffix(x) for x in final.open_issues if x.strip()]
    # Segments that ground an action item: a "decision" resting on the same utterance
    # is a task assignment, which belongs in action items only.
    action_segments = {id(s) for a in final.action_items if (s := g.locate(a.evidence) or g.locate(a.task)) is not None}
    # Policy/schedule decisions rarely name a person; one that names an action item's
    # assignee ("이지은 대리가 금요일까지 재검증") is an assignment.
    assignee_cores = {c for a in final.action_items if a.assignee not in ("", UNKNOWN) and len(c := norm(person_core(a.assignee))) >= 2}
    for d in final.decisions:
        if not d.content.strip():
            continue
        seg = g.locate(d.evidence) or g.locate(d.content)
        if seg is None:
            open_issues.append(f"{NEEDS_REVIEW} {d.content.strip()} (전사문에서 근거를 찾지 못한 결정사항)")
            notes.append(f"결정사항 근거 없음: {d.content}")
            continue
        names_in_decision = [n for n in assignee_cores if n in norm(d.content) or n in norm(d.evidence)]
        if id(seg) in action_segments or names_in_decision:
            notes.append(f"업무 배정으로 판단해 결정사항에서 제외: {d.content}")
            continue
        decisions.append(Decision(content=d.content.strip(), evidence=d.evidence.strip() or seg.text, timestamp=fmt_ts(seg.start)))

    actions: list[ActionItemIn] = []
    for a in final.action_items:
        if not a.task.strip():
            continue
        seg = g.locate(a.evidence) or g.locate(a.task)
        evidence = a.evidence.strip() if seg else ""
        assignee = check_assignee(a.assignee, g, evidence, attendees)
        deadline = check_deadline(a.deadline, g, evidence)
        if a.assignee not in ("", UNKNOWN) and assignee == UNKNOWN:
            notes.append(f"담당자 근거 없음 → 미확인: {a.assignee} ({a.task})")
        if a.deadline not in ("", UNKNOWN) and deadline == UNKNOWN:
            notes.append(f"기한 근거 없음 → 미확인: {a.deadline} ({a.task})")
        task = a.task.strip()
        if seg is None:
            task = f"{NEEDS_REVIEW} {task}"
            notes.append(f"후속 업무 근거 없음: {a.task}")
        actions.append(ActionItemIn(task=task, assignee=assignee, deadline=deadline, evidence=evidence, timestamp=fmt_ts(seg.start) if seg else UNKNOWN))

    discussion = [
        DiscussionItem(topic=d.topic.strip(), content=d.content.strip() or UNKNOWN, speaker=UNKNOWN, timestamp=ts_or_unknown(d.timestamp))
        for d in final.discussion_items
        if d.topic.strip() or d.content.strip()
    ]
    covered = norm(" ".join(d.topic + d.content for d in discussion))
    for item in agenda:
        if norm(item) and norm(item) not in covered and not g.mentions(item):
            discussion.append(DiscussionItem(topic=item, content="회의에서 이 안건에 대한 논의가 확인되지 않았습니다.", speaker=UNKNOWN, timestamp=UNKNOWN))
            notes.append(f"안건 논의 확인 안 됨: {item}")

    summary = final.meeting_summary.strip() or "요약을 생성하지 못했습니다."
    for label, text in [("요약", summary), *[(f"논의사항 '{d.topic}'", d.content) for d in discussion], *[("미결 사항", x) for x in open_issues if not x.startswith(NEEDS_REVIEW)]]:
        bad = ungrounded_numbers(text, g, meeting_info)
        if bad:
            notes.append(f"{label}의 수치 {', '.join(bad)}은(는) 전사문에서 확인되지 않습니다. 원문을 확인하세요.")

    if notes:
        log.info("Review notes (%d): %s", len(notes), "; ".join(notes))
    return ReviewResult(
        minutes=MinutesUpdate(
            meeting_summary=summary,
            discussion_items=discussion,
            decisions=decisions,
            action_items=actions,
            open_issues=_dedupe(open_issues),
            next_meeting_checks=_dedupe([x.strip() for x in final.next_meeting_checks if x.strip()]),
        ),
        notes=notes,
    )


def _strip_unknown_suffix(text: str) -> str:
    """'서버 증설 예산 확인 미확인' → '서버 증설 예산 확인' (the marker belongs in fields, not sentences)."""
    t = text.strip()
    stripped = re.sub(rf"\s*\(?{UNKNOWN}\)?[.。]?$", "", t).strip()
    return stripped or t


def _dedupe(items: list[str], threshold: float = 0.85) -> list[str]:
    out: list[str] = []
    for x in items:
        if not any(SequenceMatcher(None, norm(x), norm(y)).ratio() >= threshold for y in out):
            out.append(x)
    return out
