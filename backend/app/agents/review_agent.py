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
# Wording that marks an opinion/proposal rather than a settled decision.
NOT_DECIDED = re.compile(r"의견|제안|가능하다는|가능할\s*것|검토(?:가)?\s*필요|논의(?:가)?\s*필요|필요하다는|생각|아닐까|미정|보류")


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
        """Finds a transcript spelling that sounds like `name` (see similar_name) —
        e.g. STT heard 이지훈 for 이지은, or 최유나 for 최윤아."""
        n = norm(name)
        if not 2 <= len(n) <= 4:
            return None
        if n in self.full_norm:
            return n
        text = self.full_norm
        for i in range(len(text) - len(n) + 1):
            cand = text[i : i + len(n)]
            if similar_name(cand, n):
                return cand
        return None


# ---- Korean name similarity ---------------------------------------------------------
_L = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_V = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_T = ["", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"]


def jamo(text: str) -> str:
    """'윤아' → 'ㅇㅠㄴㅇㅏ'. Non-syllables pass through."""
    out = []
    for ch in text:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out += [_L[c // 588], _V[c % 588 // 28], _T[c % 28]]
        else:
            out.append(ch)
    return "".join(out)


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def similar_name(a: str, b: str) -> bool:
    """Same surname (first syllable), same length, and at most two jamo edits apart.
    Catches typical STT confusions (이지은/이지훈, 최윤아/최유나 — linking sound)
    while rejecting different people (김민수/김민호 is 2 edits too, so callers must
    also require the match to be unique among attendees)."""
    a, b = norm(a), norm(b)
    if a == b or not (2 <= len(a) <= 4) or len(a) != len(b) or a[0] != b[0]:
        return False
    return _edit_distance(jamo(a[1:]), jamo(b[1:])) <= 2


def person_core(name: str) -> str:
    n = name.strip()
    for t in sorted(TITLES, key=len, reverse=True):
        n = re.sub(rf"\s*{t}$", "", n)
    return n.strip()


PEOPLE_SPLIT = re.compile(r"\s*(?:,|/|·|및|그리고|&|\s와\s|\s과\s)\s*")


def split_people(assignee: str) -> list[str]:
    """'최유나, 채김' → ['최유나', '채김']."""
    return [p.strip() for p in PEOPLE_SPLIT.split(assignee) if p.strip()]


def _grounded_person(name: str, g: Grounding, evidence: str, attendees: list[str]) -> bool:
    core = person_core(name)
    if len(norm(core)) >= 2 and (g.mentions(core) or norm(core) in norm(evidence)):
        return True
    # The speaker of the evidence utterance ("제가 하겠습니다") — diarized label or user-given name.
    seg = g.locate(evidence) if evidence else None
    if seg is not None and seg.speaker and norm(person_core(seg.speaker)) == norm(core):
        return True
    # A registered attendee whose name STT misheard still counts.
    return any(norm(person_core(a)) == norm(core) for a in attendees) and g.near_mention(core) is not None


def check_assignee(assignee: str, g: Grounding, evidence: str, attendees: list[str] = ()) -> str:  # type: ignore[assignment]
    """Keeps only the people who are actually mentioned; 미확인 if none are."""
    if not assignee or assignee == UNKNOWN:
        return UNKNOWN
    people = split_people(assignee)
    kept = [p for p in people if _grounded_person(p, g, evidence, list(attendees))]
    if not kept:
        return UNKNOWN
    return assignee.strip() if len(kept) == len(people) else ", ".join(kept)


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
    text = re.sub(r"화자\s*\d+", "", text)  # diarization labels are not figures
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
    # Deadlines of action items per grounding segment: a decision resting on the same
    # utterance *and* repeating that deadline is the assignment restated.
    action_deadlines: dict[int, list[str]] = {}
    for a in final.action_items:
        s = g.locate(a.evidence) or g.locate(a.task)
        if s is not None and a.deadline not in ("", UNKNOWN):
            action_deadlines.setdefault(id(s), []).append(norm(a.deadline))
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
        same_deadline = any(dl and dl in norm(d.content) for dl in action_deadlines.get(id(seg), []))
        if names_in_decision or same_deadline:
            notes.append(f"업무 배정으로 판단해 결정사항에서 제외: {d.content}")
            continue
        if NOT_DECIDED.search(d.content):
            notes.append(f"확정이 아닌 의견·제안으로 판단해 결정사항에서 제외: {d.content}")
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

    # "다음 회의에서 ~ 확인" with nobody assigned is a check for the next meeting, not a task.
    next_checks = [x.strip() for x in final.next_meeting_checks if x.strip()]
    kept_actions = []
    for item in actions:
        body = item.task.removeprefix(NEEDS_REVIEW).strip()
        if item.assignee == UNKNOWN and (NEXT_MEETING.search(body) or "다음회의" in norm(item.deadline)):
            next_checks.append(NEXT_MEETING.sub("", body).strip() or body)
            notes.append(f"담당자 없는 '다음 회의' 항목을 다음 회의 확인사항으로 이동: {item.task}")
        else:
            kept_actions.append(item)
    actions = kept_actions

    speakers = {sp for s in segments if (sp := s.speaker)}
    discussion = [
        DiscussionItem(
            topic=d.topic.strip(),
            content=d.content.strip() or UNKNOWN,
            # Only speakers that actually appear in the (diarized) transcript are kept.
            speaker=d.speaker.strip() if d.speaker.strip() in speakers else UNKNOWN,
            timestamp=ts_or_unknown(d.timestamp),
        )
        for d in final.discussion_items
        if d.topic.strip() or d.content.strip()
    ]
    covered = norm(" ".join(d.topic + d.content for d in discussion))
    for item in agenda:
        if norm(item) and norm(item) not in covered and not g.mentions(item):
            discussion.append(DiscussionItem(topic=item, content="회의에서 이 안건에 대한 논의가 확인되지 않았습니다.", speaker=UNKNOWN, timestamp=UNKNOWN))
            notes.append(f"안건 논의 확인 안 됨: {item}")

    open_final, next_final = _split_open_and_next(open_issues, next_checks)
    summary = final.meeting_summary.strip() or "요약을 생성하지 못했습니다."
    if not g.mentions("다음 회의") and not g.mentions("다음 미팅"):
        for label, text in [("요약", summary), *[(f"논의사항 '{d.topic}'", d.content) for d in discussion]]:
            if "다음회의" in norm(text) or "다음미팅" in norm(text):
                notes.append(f"{label}에 '다음 회의' 언급이 있지만 녹음에서는 다음 회의 이야기가 확인되지 않습니다. 원문을 확인하세요.")
    for label, text in [("요약", summary), *[(f"논의사항 '{d.topic}'", d.content) for d in discussion], *[("미결 사항", x) for x in open_final if not x.startswith(NEEDS_REVIEW)]]:
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
            open_issues=open_final,
            next_meeting_checks=next_final,
        ),
        notes=notes,
    )


NEXT_MEETING = re.compile(r"^\s*다음\s*회의(?:에서|때)?\s*")


def _split_open_and_next(open_issues: list[str], next_checks: list[str]) -> tuple[list[str], list[str]]:
    """De-duplicates within and across the two lists. An item that appears in both is
    kept once: under next-meeting checks if it says 다음 회의, otherwise as an open issue."""
    opens, nexts = _dedupe(open_issues), _dedupe(next_checks)
    final_open: list[str] = []
    for o in opens:
        twin = next((n for n in nexts if _same_item(o, n)), None)
        if twin is None:
            final_open.append(o)
        elif "다음회의" not in norm(o):
            nexts.remove(twin)
            final_open.append(o)
    return final_open, nexts


def _strip_unknown_suffix(text: str) -> str:
    """'서버 증설 예산 확인 미확인' → '서버 증설 예산 확인' (the marker belongs in fields, not sentences)."""
    t = text.strip()
    stripped = re.sub(rf"\s*\(?{UNKNOWN}\)?[.。]?$", "", t).strip()
    if stripped != t and re.search(r"[가-힣](이|가)$", stripped):
        # '…에 대한 결정이 미확인' → '…에 대한 결정 미정' (don't leave a dangling particle)
        stripped = stripped[:-1].rstrip() + " 미정"
    return stripped or t


def _core(text: str) -> str:
    """Comparable form: no '다음 회의에서' prefix, no trailing verb ending."""
    t = NEXT_MEETING.sub("", text.strip())
    t = re.sub(r"(하겠습니다|합니다|한다|하기로\s*함|필요|예정)[.。]?$", "", t.strip())
    return norm(t)


def _same_item(a: str, b: str, threshold: float = 0.85) -> bool:
    ca, cb = _core(a), _core(b)
    if not ca or not cb:
        return False
    return ca in cb or cb in ca or SequenceMatcher(None, ca, cb).ratio() >= threshold


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for x in items:
        if not any(_same_item(x, y) for y in out):
            out.append(x)
    return out
