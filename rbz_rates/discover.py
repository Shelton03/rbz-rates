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
