"""Meeting minutes → DOCX (python-docx).

Section order (same as the web view):
1 회의 개요 · 2 회의 목적 · 3 참석자 · 4 주요 논의사항 · 5 의사결정 사항 ·
6 담당자별 후속 업무 · 7 미결 사항 · 8 다음 회의 확인사항
"""

import logging
import re
import unicodedata
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from docx import Document as DocxDocument
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from sqlalchemy.orm import Session

from app.models import Document, Meeting
from app.schemas.meeting import UNKNOWN, MinutesOut
from app.services import meeting_service, storage

log = logging.getLogger(__name__)

FONT = "맑은 고딕"  # Word on Windows; Word for Mac substitutes Apple SD Gothic Neo
KST = ZoneInfo("Asia/Seoul")
GRAY = RGBColor(0x6B, 0x72, 0x80)
ORANGE = RGBColor(0xB4, 0x53, 0x09)
HEADER_FILL = "E8EAF6"
STATUS_LABEL = {"PENDING": "대기", "IN_PROGRESS": "진행 중", "DONE": "완료"}


class DocumentError(Exception):
    pass


def safe_filename(meeting: Meeting) -> str:
    """'20261124_방카슈랑스_테스트_회의_회의록.docx' — no path or reserved characters."""
    title = unicodedata.normalize("NFC", meeting.title)
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title)
    title = re.sub(r"\s+", "_", title.strip())[:80].strip("._") or "회의"
    return f"{meeting.meeting_date:%Y%m%d}_{title}_회의록.docx"


def _set_font(run, size: float | None = None, bold: bool | None = None, color: RGBColor | None = None) -> None:
    run.font.name = FONT
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _para(doc_or_cell, text: str = "", *, size: float = 10, bold: bool = False, color: RGBColor | None = None, style: str | None = None, space_after: float = 4):
    p = doc_or_cell.add_paragraph(style=style) if style else doc_or_cell.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    if text:
        _add_text(p, text, size=size, bold=bold, color=color)
    return p


def _add_text(p, text: str, *, size: float = 10, bold: bool = False, color: RGBColor | None = None) -> None:
    """Adds text; the 미확인 marker is shown in orange so it is never read as data."""
    parts = re.split(f"({UNKNOWN})", text)
    for part in parts:
        if not part:
            continue
        run = p.add_run(part)
        _set_font(run, size, bold, ORANGE if part == UNKNOWN else color)


def _heading(doc, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    _set_font(run, 13, True, RGBColor(0x1E, 0x29, 0x3B))
    # bottom border under section headings
    ppr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "C7CAD9")):
        bottom.set(qn(k), v)
    bdr.append(bottom)
    ppr.append(bdr)


def _shade(cell, fill: str) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def _cell_text(cell, text: str, *, bold: bool = False, size: float = 9.5, color: RGBColor | None = None) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    _add_text(p, text, size=size, bold=bold, color=color)


def _fix_table_layout(t, widths_cm: list[float]) -> None:
    """Fixed layout with explicit widths and borders, so every viewer (Word, Pages,
    Quick Look, LibreOffice) renders the same grid instead of auto-shrinking it."""
    tblpr = t._tbl.tblPr
    for tag in ("w:tblW", "w:tblLayout", "w:tblBorders"):
        old = tblpr.find(qn(tag))
        if old is not None:
            tblpr.remove(old)
    tblw = OxmlElement("w:tblW")
    tblw.set(qn("w:w"), str(int(sum(widths_cm) * 567)))  # 1 cm = 567 twips
    tblw.set(qn("w:type"), "dxa")
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{edge}")
        for k, v in (("w:val", "single"), ("w:sz", "4"), ("w:space", "0"), ("w:color", "BFC3D4")):
            b.set(qn(k), v)
        borders.append(b)
    tblpr.append(tblw)
    tblpr.append(layout)
    tblpr.append(borders)
    grid = t._tbl.tblGrid
    for col, w in zip(grid.findall(qn("w:gridCol")), widths_cm, strict=True):
        col.set(qn("w:w"), str(int(w * 567)))
    t.autofit = False
    for row in t.rows:
        for i, w in enumerate(widths_cm):
            row.cells[i].width = Cm(w)


def _table(doc, headers: list[str], rows: list[list[str]], widths_cm: list[float]):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        _cell_text(c, h, bold=True)
        _shade(c, HEADER_FILL)
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            _cell_text(cells[i], v)
    _fix_table_layout(t, widths_cm)
    return t


def _bullets(doc, items: list[str], numbered: bool = False) -> None:
    if not items:
        _para(doc, "없음", color=GRAY)
        return
    for i, x in enumerate(items, 1):
        _para(doc, f"{i}. {x}" if numbered else f"• {x}", space_after=2)


def render_docx(meeting: Meeting, minutes: MinutesOut) -> bytes:
    doc = DocxDocument()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)  # A4
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10)
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    doc.core_properties.title = f"{meeting.title} 회의록"
    doc.core_properties.author = "Personal AI Work Assistant"

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(title.add_run("회 의 록"), 20, True)
    sub = _para(doc, meeting.title, size=12, bold=True)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    _heading(doc, "1. 회의 개요")
    overview = [
        ["회의명", meeting.title],
        ["일시", f"{meeting.meeting_date:%Y년 %m월 %d일}"],
        ["안건", "\n".join(f"{i}. {a}" for i, a in enumerate(meeting.agenda, 1)) or "-"],
        ["작성", f"로컬 AI 초안({minutes.llm_model or '-'})" + (" · 사용자 검토·수정" if minutes.edited else "")],
    ]
    t = _table(doc, ["항목", "내용"], overview, [3.0, 14.0])
    for row in t.rows[1:]:
        _shade(row.cells[0], "F5F6FA")
    _para(doc, "", space_after=2)
    _para(doc, "요약", bold=True, space_after=2)
    _para(doc, minutes.meeting_summary)

    _heading(doc, "2. 회의 목적")
    _para(doc, meeting.purpose or "-")

    _heading(doc, "3. 참석자")
    _para(doc, ", ".join(meeting.attendees) or "-")

    _heading(doc, "4. 주요 논의사항")
    if minutes.discussion_items:
        _table(doc, ["주제", "내용", "시각"], [[d.topic, d.content, d.timestamp] for d in minutes.discussion_items], [4.0, 10.8, 2.2])
    else:
        _para(doc, "없음", color=GRAY)

    _heading(doc, "5. 의사결정 사항")
    if minutes.decisions:
        for i, d in enumerate(minutes.decisions, 1):
            _para(doc, f"{i}. {d.content}", bold=True, space_after=1)
            if d.evidence:
                _para(doc, f"   근거: “{d.evidence}” ({d.timestamp})", size=8.5, color=GRAY)
    else:
        _para(doc, "없음", color=GRAY)

    _heading(doc, "6. 담당자별 후속 업무")
    if minutes.action_items:
        _table(
            doc,
            ["No", "업무", "담당자", "기한", "상태"],
            [[str(i), a.task, a.assignee, a.deadline, STATUS_LABEL.get(a.status, a.status)] for i, a in enumerate(minutes.action_items, 1)],
            [1.0, 8.4, 3.0, 3.0, 1.6],
        )
    else:
        _para(doc, "없음", color=GRAY)

    _heading(doc, "7. 미결 사항")
    _bullets(doc, minutes.open_issues)

    _heading(doc, "8. 다음 회의 확인사항")
    _bullets(doc, minutes.next_meeting_checks)

    _para(doc, "", space_after=8)
    note = _para(
        doc,
        f"본 회의록은 로컬 AI가 회의 녹음을 바탕으로 작성한 초안을 기반으로 합니다. ‘{UNKNOWN}’은 회의에서 확인되지 않은 항목입니다. "
        f"생성: {datetime.now(KST):%Y-%m-%d %H:%M}",
        size=8,
        color=GRAY,
    )
    note.alignment = WD_ALIGN_PARAGRAPH.LEFT

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def export(db: Session, meeting: Meeting) -> Document:
    """Renders the current minutes and stores the file + a documents row."""
    minutes = meeting_service.minutes_out(db, meeting.id)
    if minutes is None:
        raise DocumentError("회의록이 아직 없습니다. AI 분석이 끝난 뒤 다시 시도하세요.")
    data = render_docx(meeting, minutes)
    doc = Document(meeting_id=meeting.id, filename=safe_filename(meeting), stored_path="", size_bytes=len(data))
    db.add(doc)
    db.flush()
    path = storage.meeting_dir("exports", meeting.id) / f"{doc.id}.docx"
    path.write_bytes(data)
    doc.stored_path = storage.relative(path)
    db.commit()
    log.info("Exported DOCX for meeting %s: %s (%d bytes)", meeting.id, doc.filename, len(data))
    return doc


def delete(db: Session, doc: Document) -> None:
    storage.resolve(doc.stored_path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
