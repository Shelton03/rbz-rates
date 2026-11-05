"""Turn an RBZ daily interbank-rate PDF into raw rows.

The parser is deliberately strict: if the document doesn't look like a layout
we know, it raises ShapeError instead of guessing. Everything works on bytes
in memory; the PDF is never written to disk. Once a new parser is written,
past days can be re-downloaded and re-parsed with `refetch`.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass, field

NUM = r"-?[\d,]*\.?\d+"
ROW_RE = re.compile(
    rf"^(?P<code>[A-Z]{{3}}(?:/[A-Z]{{3}})?)\s*(?P<star>\*)?\s+"
    rf"(?P<nums>(?:{NUM}\s+){{5}}{NUM})\s*$"
)
# RBZ alternates between "Thursday, 05 November 2026" and "Wednesday, November 4, 2026"
_WEEKDAY = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
DATE_RES = [
    (re.compile(_WEEKDAY + r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+),?\s+(?P<year>\d{4})"), "dmy"),
    (re.compile(_WEEKDAY + r"(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})"), "mdy"),
]
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


class ShapeError(ValueError):
    """The document does not match any known layout."""


@dataclass
class RawRow:
    code: str                      # first code, e.g. "ZMW" from "ZMW/ZMK"
    aliases: list[str]             # e.g. ["ZMK"]
    starred: bool                  # RBZ's '*' marker (unreliable, kept for reference)
    index: tuple[float, float, float]   # bid, ask, mid against USD, as published
    local: tuple[float, float, float]   # bid, ask, mid in the ZWG columns, as published


@dataclass
class ParsedDocument:
    parser: str
    base: str
    date: dt.date | None
    rows: list[RawRow] = field(default_factory=list)


def _drop_overlapping_spaces(page):
    """RBZ pads cells with space glyphs, and the last one sits on top of the
    first digit. Sorted by x, it lands inside the number ("1 6.33830"), so drop
    any space that overlaps a visible character on the same line."""
    visible = [c for c in page.chars if not c["text"].isspace()]

    def keep(obj) -> bool:
        if obj.get("object_type") != "char" or not obj["text"].isspace():
            return True
        return not any(abs(c["top"] - obj["top"]) < 1 and c["x0"] < obj["x1"] - 0.1 and obj["x0"] < c["x1"] - 0.1
                       for c in visible)
    return page.filter(keep)


def pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes, entirely in memory (nothing touches disk)."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = [_drop_overlapping_spaces(page).extract_text() or "" for page in pdf.pages]
    text = "\n".join(pages)
    if len(text.strip()) < 50:
        raise ShapeError("No extractable text; the PDF may be a scan and need OCR")
    return text


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _parse_date(text: str) -> dt.date | None:
    for rx, _ in DATE_RES:
        m = rx.search(text)
        if m and (month_no := MONTHS.get(m["month"].lower())):
            return dt.date(int(m["year"]), month_no, int(m["day"]))
    return None


# --- Layout: ZWG interbank sheet (current since the ZiG introduction) ---------

def _matches_zwg_v1(text: str) -> bool:
    head = text[:400].upper()
    return all(k in head for k in ("INTERBANK RATE", "BID", "ASK", "MID")) and "ZWG" in head


def _parse_zwg_v1(text: str) -> ParsedDocument:
    doc = ParsedDocument(parser="zwg-interbank-v1", base="ZWG", date=_parse_date(text))
    for line in text.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        codes = m["code"].split("/")
        nums = [_num(n) for n in m["nums"].split()]
        doc.rows.append(RawRow(
            code=codes[0], aliases=codes[1:], starred=bool(m["star"]),
            index=tuple(nums[0:3]), local=tuple(nums[3:6]),
        ))
    return doc


PARSERS = [("zwg-interbank-v1", _matches_zwg_v1, _parse_zwg_v1)]


def parse_text(text: str) -> ParsedDocument:
    for _name, matches, parse in PARSERS:
        if matches(text):
            doc = parse(text)
            _validate(doc)
            return doc
    raise ShapeError("Header not recognised: " + " ".join(text[:200].split()))


def _validate(doc: ParsedDocument) -> None:
    codes = [r.code for r in doc.rows]
    if "USD" not in codes:
        raise ShapeError("No USD row found")
    if len(doc.rows) < 10:
        raise ShapeError(f"Only {len(doc.rows)} currency rows parsed")
    if len(set(codes)) != len(codes):
        raise ShapeError("Duplicate currency codes")
    usd = doc.rows[codes.index("USD")]
    if usd.index[2] != 1 or usd.local[2] <= 0:
        raise ShapeError(f"USD row looks wrong: {usd}")
    if doc.date is None:
        raise ShapeError("No publication date found in document")


def parse_pdf(pdf_bytes: bytes) -> ParsedDocument:
    return parse_text(pdf_to_text(pdf_bytes))
