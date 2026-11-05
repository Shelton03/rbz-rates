"""Turn an RBZ daily interbank-rate PDF into raw rows.

The parser adapts to cosmetic changes RBZ has made over the years and refuses
to guess about structural ones:

  adapts:  title lines ("International Banking & Portfolio Management",
           "INTERBANK RATE"), header wording, date styles ("Thursday, 05 November
           2026", "Monday, April 01, 2019", "Monday, 03 April2023"), the local
           currency (RTGS$, ZWL, ZWG), thousands separators, '*' markers,
           code aliases (ZMW/ZMK), new or dropped currencies;
  refuses: anything that changes what the numbers mean, e.g. a row with a
           different number of columns. Those raise ShapeError.

Every sheet's layout is summarised as a Layout with a short fingerprint, so the
pipeline can tell when RBZ starts publishing a format it hasn't seen before
(and alert, even if parsing succeeded). Everything works on bytes in memory;
the PDF is never written to disk.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field

COLUMNS = 6  # USD index bid/ask/mid, then local-currency bid/ask/mid
NUM_RE = re.compile(r"^-?(?:\d[\d,]*(?:\.\d+)?|\.\d+)$")
ROW_RE = re.compile(r"^(?P<code>[A-Z]{3}(?:/[A-Z]{3})?)\s*(?P<star>\*)?(?P<rest>(?:\s+\S+)+)\s*$")
# weekday optional: some 2025 sheets print just "07 January2025"
_WEEKDAY = r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*)?"
DATE_RES = [
    (re.compile(r"(?<![\d.,])" + _WEEKDAY + r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s*(?P<month>[A-Za-z]{3,9}),?\s*(?P<year>\d{4})"), "dmy"),
    (re.compile(_WEEKDAY + r"(?P<month>[A-Za-z]{3,9})\s*(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s*(?P<year>\d{4})"), "mdy"),
]
MONTHS = {m[:3].lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
# local-currency labels seen in the header, normalised
ZIG_LAUNCH = dt.date(2024, 4, 5)  # first ZWG sheet
BASE_LABELS = {"ZWG": "ZWG", "ZIG": "ZWG", "ZWL": "ZWL", "RTGS$": "RTGS", "RTGS": "RTGS"}  # "ZIG": early ZiG sheets


class ShapeError(ValueError):
    """The document doesn't match what the parser can safely read."""

    def __init__(self, message: str, layout: "Layout | None" = None):
        super().__init__(message)
        self.layout = layout


class NoLocalRates(ShapeError):
    """A sheet with USD cross rates only and no local-currency columns. RBZ published some
    of these in 2019; there is no Zimbabwe-currency rate on them to serve."""


@dataclass
class Layout:
    """What a sheet looks like, independent of its numbers."""
    base: str | None                 # local currency: ZWG, ZWL, RTGS
    header: str                      # the column header line, normalised
    columns: dict[int, int]          # numbers-per-row -> how many rows had that many
    date_style: str | None           # "dmy" or "mdy"
    interbank_title: bool            # has the "INTERBANK RATE" line
    head: list[str] = field(default_factory=list)  # first lines, for alerts

    @property
    def signature(self) -> str:
        cols = ",".join(f"{n}x{c}" for n, c in sorted(self.columns.items()) if c >= 3) or "none"
        return (f"base={self.base};header={self.header};columns={cols};"
                f"date={self.date_style};interbank_title={'yes' if self.interbank_title else 'no'}")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.signature.encode()).hexdigest()[:8]


@dataclass
class RawRow:
    code: str                           # first code, e.g. "ZMW" from "ZMW/ZMK"
    aliases: list[str]                  # e.g. ["ZMK"]
    starred: bool                       # RBZ's '*' marker (unreliable, kept for reference)
    index: tuple[float, float, float]   # bid, ask, mid against USD, as published
    local: tuple[float, float, float]   # bid, ask, mid in the local-currency columns, as published
    local_decimals: int = 4             # fewest decimals printed among the local bid/ask/mid (rounding precision)


@dataclass
class ParsedDocument:
    parser: str
    base: str
    date: dt.date | None
    rows: list[RawRow] = field(default_factory=list)
    layout: Layout | None = None
    warnings: list[str] = field(default_factory=list)


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


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def _parse_date(text: str) -> tuple[dt.date | None, str | None]:
    for rx, style in DATE_RES:
        m = rx.search(text)
        if m and (month_no := MONTHS.get(m["month"][:3].lower())):
            try:
                return dt.date(int(m["year"]), month_no, int(m["day"])), style
            except ValueError:
                continue
    return None, None


def _row_numbers(line: str):
    """(code, starred, numeric tokens) if the line is a currency row, else None.

    Some 2019 sheets lost the "USD" label on the USD row, leaving just its numbers.
    A label-less row whose USD index is exactly 1 / 1 / 1 can only be the USD row.
    """
    line = line.strip()
    m = ROW_RE.match(line)
    if m:
        tokens = m["rest"].split()
        return (m["code"], bool(m["star"]), tokens) if all(NUM_RE.match(t) for t in tokens) else None
    tokens = line.split()
    if len(tokens) == COLUMNS and all(NUM_RE.match(t) for t in tokens) and all(_num(t) == 1 for t in tokens[:3]):
        return "USD", False, tokens
    return None


def describe(text: str) -> Layout:
    """Summarise the layout of a sheet's text, whether or not it can be parsed."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first_row = next((i for i, ln in enumerate(lines) if _row_numbers(ln)), len(lines))
    head = lines[:first_row]
    labels = Counter(BASE_LABELS[t] for ln in head for t in ln.upper().split() if t in BASE_LABELS)
    header_line = next((ln for ln in head if "CURRENCY" in ln.upper() and "BID" in ln.upper()), "")
    columns = Counter(len(r[2]) for ln in lines if (r := _row_numbers(ln)))
    _, style = _parse_date(text)
    return Layout(
        base=labels.most_common(1)[0][0] if labels else None,
        header=" ".join(header_line.upper().split()),
        columns=dict(columns),
        date_style=style,
        interbank_title=any("INTERBANK RATE" in ln.upper() for ln in head),
        head=lines[:8],
    )


def parse_text(text: str) -> ParsedDocument:
    layout = describe(text)
    if not layout.header:
        raise ShapeError("No column header (CURRENCY … BID … ASK) found", layout)
    if layout.base is None and layout.columns.get(3, 0) >= 10 and not layout.columns.get(COLUMNS):
        raise NoLocalRates("USD cross rates only: the sheet has no local-currency columns", layout)
    date, _ = _parse_date(text)
    inferred = None
    if layout.base is None and date is not None and date < ZIG_LAUNCH and layout.columns.get(COLUMNS, 0) >= 10:
        # a few 2019 sheets dropped the currency label line; everything before the ZiG was priced in ZWL
        inferred = "ZWL"
    elif layout.base is None:
        raise ShapeError("Couldn't tell which local currency the sheet is in (no ZWG/ZWL/RTGS$ label)", layout)
    if layout.columns.get(COLUMNS, 0) < 10:
        raise ShapeError(f"Rows don't have the expected {COLUMNS} numbers (found {layout.columns}); "
                         "the column layout has changed", layout)

    doc = ParsedDocument(parser="rbz-interbank-adaptive-v1", base=layout.base or inferred, date=date, layout=layout)
    if inferred:
        doc.warnings.append(f"The sheet has no currency label; {inferred} inferred from its date")
    for line in text.splitlines():
        r = _row_numbers(line)
        if not r:
            continue
        code, starred, tokens = r
        if len(tokens) != COLUMNS:
            doc.warnings.append(f"Skipped a {code} row with {len(tokens)} numbers instead of {COLUMNS}")
            continue
        codes = code.split("/")
        if codes[0] in {r.code for r in doc.rows}:
            doc.warnings.append(f"{codes[0]} appears twice on the sheet; kept the first row, skipped: {line.strip()}")
            continue
        nums = [_num(t) for t in tokens]
        doc.rows.append(RawRow(
            code=codes[0], aliases=codes[1:], starred=starred,
            index=tuple(nums[0:3]), local=tuple(nums[3:6]),
            local_decimals=min(_decimals(t) for t in tokens[3:6]),
        ))
    _validate(doc)
    return doc


def _validate(doc: ParsedDocument) -> None:
    codes = [r.code for r in doc.rows]
    if "USD" not in codes:
        raise ShapeError("No USD row found", doc.layout)
    if len(doc.rows) < 10:
        raise ShapeError(f"Only {len(doc.rows)} currency rows parsed", doc.layout)
    if len(set(codes)) != len(codes):
        raise ShapeError("Duplicate currency codes", doc.layout)
    usd = doc.rows[codes.index("USD")]
    if usd.index[2] != 1 or usd.local[2] <= 0:
        raise ShapeError(f"USD row looks wrong: {usd}", doc.layout)
    if doc.date is None:
        raise ShapeError("No publication date found in document", doc.layout)


def parse_pdf(pdf_bytes: bytes) -> ParsedDocument:
    return parse_text(pdf_to_text(pdf_bytes))
