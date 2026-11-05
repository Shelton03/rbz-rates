"""Find the daily PDFs on the RBZ site.

Two hops: the Exchange Rates listing links one article per month
("November 2026"); each month article has a table with one row per business
day, and a PDF link appears in a row once that day's rates are published.
Article IDs are not in date order, so we match on the month/year in the slug.
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE = "https://www.rbz.co.zw"
LISTING_URL = BASE + "/index.php/research/markets/exchange-rates"

MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
MONTH_LINK_RE = re.compile(r"/13-daily-exchange-rates/\d+-(?P<month>[a-z]+)-(?P<year>\d{4})/?$")
PDF_NAME_RE = re.compile(r"RATES_(?P<day>\d{1,2})_(?P<month>[A-Z]+)_(?P<year>\d{4})\.pdf$", re.I)


def find_month_pages(listing_html: str) -> dict[tuple[int, int], str]:
    """Return {(year, month): article_url}."""
    soup = BeautifulSoup(listing_html, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        m = MONTH_LINK_RE.search(a["href"])
        if m and m["month"] in MONTHS:
            found[(int(m["year"]), MONTHS.index(m["month"]) + 1)] = urljoin(BASE, a["href"])
    return found


def find_daily_pdfs(month_html: str, year: int, month: int) -> dict[dt.date, str]:
    """Return {date: pdf_url} for every day that has a published PDF."""
    soup = BeautifulSoup(month_html, "html.parser")
    out: dict[dt.date, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        day = None
        m = PDF_NAME_RE.search(href)
        if m:
            day = int(m["day"])
        else:  # fall back to the DATE cell of the table row
            tr = a.find_parent("tr")
            cell = tr.find("td") if tr else None
            if cell and cell.get_text(strip=True).isdigit():
                day = int(cell.get_text(strip=True))
        if day is None:
            continue
        try:
            out[dt.date(year, month, day)] = urljoin(BASE, href)
        except ValueError:
            continue
    return out


def guess_pdf_url(day: dt.date) -> str:
    """Fallback when a month article is missing: the filename pattern in use since 2024."""
    month = MONTHS[day.month - 1]
    return (f"{BASE}/documents/Exchange_Rates/{day.year}/{month.capitalize()}/"
            f"RATES_{day.day}_{month.upper()}_{day.year}.pdf")


# ---------------------------------------------------------------- older sheets

ARCHIVE_CDX = "https://web.archive.org/cdx/search/cdx"
# filenames RBZ has used: Rates-01-April-2021.pdf, 5-April-2019.pdf, Rates-1-April-2022.pdf,
# RATES_03_APRIL_2023-INTERBANK_RATE.pdf, RATES_10_APRIL_2024.pdf, RATES_5_NOVEMBER_2026.pdf
NOT_RATES_RE = re.compile(r"gold|coin|token|bond|tbill|treasury", re.I)
FILE_DATE_RE = re.compile(r"(?P<day>\d{1,2})[-_ ](?P<month>[A-Za-z]{3,9})[-_ ]?(?P<year>\d{4})")


def date_from_url(url: str) -> dt.date | None:
    """The sheet's date from its filename, whichever naming style RBZ used that year."""
    m = FILE_DATE_RE.search(url.rsplit("/", 1)[-1])
    if not m:
        return None
    month = next((i + 1 for i, name in enumerate(MONTHS) if name.startswith(m["month"].lower()[:3])), None)
    try:
        return dt.date(int(m["year"]), month, int(m["day"])) if month else None
    except ValueError:
        return None


def archived_pdf_urls(fetcher, year: int) -> dict[dt.date, tuple[str, str]]:
    """{date: (rbz.co.zw url, Internet Archive copy)} for one year, from the archive's index.

    RBZ's listing pages are behind bot protection and older filenames don't follow
    one pattern, so the archive's record of which PDFs existed is the reliable list.
    The PDF is fetched from rbz.co.zw; the archive's stored copy of the same file is
    the fallback when RBZ no longer serves that path (some 2019 links were recorded
    in lower case and RBZ's server is now case-sensitive).
    """
    query = (f"{ARCHIVE_CDX}?url=rbz.co.zw/documents/Exchange_Rates/{year}/&matchType=prefix"
             "&filter=mimetype:application/pdf&filter=statuscode:200&collapse=urlkey&fl=timestamp,original")
    text = fetcher.text(query)
    lines = [ln.split(" ", 1) for ln in text.splitlines() if ln.strip()]
    if lines and (len(lines[0]) != 2 or not lines[0][1].startswith("http")):
        raise ValueError("Internet Archive index unavailable: " + " ".join(text[:120].split()))
    out: dict[dt.date, tuple[str, str]] = {}
    # other documents share the folder (e.g. the Mosi-oa-Tunya gold coin price list); prefer "rate" files
    ranked = sorted(lines, key=lambda x: ("rate" not in x[1].rsplit("/", 1)[-1].lower(), x[1]))
    for stamp, original in ranked:
        name = original.rsplit("/", 1)[-1]
        if NOT_RATES_RE.search(name):
            continue
        day = date_from_url(original)
        if day and day.year == year:
            rbz = "https://www.rbz.co.zw" + original[original.index("/documents/"):]
            out.setdefault(day, (rbz, f"https://web.archive.org/web/{stamp}id_/{original}"))
    return out
