"""CLI: python -m rbz_rates.pipeline {update,backfill,recheck,refetch}

For each published day: discover the PDF link, download it into memory,
parse + normalise it, and write data/daily/<date>.json. The PDF bytes are
never written to disk; once parsed they are dropped. Each JSON keeps the
source URL, the PDF's sha256 and the retrieval time, so any figure can be
checked against the original on the RBZ site.

Afterwards data/latest.json and data/index.json are rebuilt. A parse failure
is written to data/failures/<date>.json (with the source URL) and makes the
run exit non-zero, so CI goes red the day RBZ changes the layout. Failed days
are retried on the next run, and `refetch` re-downloads and re-parses every
known day once a new parser has been added.

RBZ sometimes corrects a day by re-uploading its PDF. Every `update` re-checks
the most recent days with a conditional request (ETag / Last-Modified, so an
unchanged file costs a 304 and no download). If the PDF changed, the day is
re-parsed and the previous version is recorded under "revisions" in its JSON.
`recheck` does the same over a longer window.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

import httpx

from . import discover
from .fetch import Blocked, NotFound
from .normalize import normalise
from .parse import ShapeError, parse_pdf

DATA = Path(os.environ.get("RBZ_DATA_DIR", "data"))
DAILY, FAILURES = DATA / "daily", DATA / "failures"


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _load_day(key: str) -> dict | None:
    path = DAILY / f"{key}.json"
    return json.loads(path.read_text()) if path.exists() else None


def _fail(key: str, error: str, source: dict) -> bool:
    _write_json(FAILURES / f"{key}.json", {"date": key, "error": error, "source": source})
    print(f"FAILED {key}: {error}", file=sys.stderr)
    return False


def _ingest(key: str, url: str, fetched) -> bool:
    """Parse PDF bytes held in memory and write the day's JSON. The bytes are
    dropped as soon as they are parsed; nothing PDF-shaped touches disk.

    If the day already exists with a different sha256, the old version is
    appended to "revisions". If parsing fails, any existing JSON is kept.
    """
    source = {"url": url, "retrieved_at": _now(), "sha256": hashlib.sha256(fetched.content).hexdigest(),
              "etag": fetched.etag, "last_modified": fetched.last_modified}
    try:
        doc = parse_pdf(fetched.content)
    except Exception as e:  # ShapeError, or anything pdfminer raises on a damaged file
        return _fail(key, f"{type(e).__name__}: {e}" if not isinstance(e, ShapeError) else str(e), source)
    finally:
        fetched.content = None  # never persisted
    out = normalise(doc)
    if out["date"] != key:
        out["warnings"].append(f"PDF says {out['date']} but listed as {key}; using listing date")
        out["date"] = key
    out["source"] = source

    previous = _load_day(key)
    revisions = (previous or {}).get("revisions", [])
    if previous and previous["source"].get("sha256") != source["sha256"]:
        old = previous["source"]
        revisions = revisions + [{k: old.get(k) for k in ("sha256", "retrieved_at", "last_modified")}]
        changed = sorted(c for c in out["rates"]
                         if out["rates"][c]["zwg_per_unit"] != previous["rates"].get(c, {}).get("zwg_per_unit"))
        print(f"REVISED {key}: RBZ re-published the PDF; changed rates: {', '.join(changed) or 'none'}")
    if revisions:
        out["revisions"] = revisions

    _write_json(DAILY / f"{key}.json", out)
    (FAILURES / f"{key}.json").unlink(missing_ok=True)
    print(f"parsed {key}: {len(out['rates'])} currencies, {len(out['warnings'])} warnings")
    return True


def process(fetcher, key: str, url: str, missing_ok: bool = False) -> bool | None:
    """Download one PDF into memory, parse it, write its JSON.

    True on success, False on failure (recorded in data/failures/), None if the
    PDF does not exist and missing_ok is set (probing a day RBZ hasn't published).
    """
    try:
        fetched = fetcher.pdf(url)
    except NotFound as e:
        return None if missing_ok else _fail(key, f"404 {e}", {"url": url, "retrieved_at": _now()})
    except (ValueError, OSError, httpx.HTTPError, Blocked) as e:
        return _fail(key, str(e), {"url": url, "retrieved_at": _now()})
    return _ingest(key, url, fetched)


def recheck(fetcher, key: str) -> bool | None:
    """Has RBZ re-published this day's PDF? Re-parse it if so.

    True: changed and re-parsed. None: unchanged. False: changed but failed to
    parse (the existing data is kept and the failure recorded).
    """
    day = _load_day(key)
    src = day["source"]
    try:
        fetched = fetcher.pdf(src["url"], src.get("etag"), src.get("last_modified"))
    except NotFound:
        print(f"WARNING {key}: PDF no longer at {src['url']}; keeping existing data", file=sys.stderr)
        return None
    except (ValueError, OSError, httpx.HTTPError, Blocked) as e:
        print(f"WARNING {key}: recheck failed ({e}); keeping existing data", file=sys.stderr)
        return None
    if fetched.content is None:  # 304 Not Modified
        return None
    if hashlib.sha256(fetched.content).hexdigest() == src.get("sha256"):
        # same bytes; just remember the validators so next time is a cheap 304
        if (src.get("etag"), src.get("last_modified")) != (fetched.etag, fetched.last_modified):
            src.update(etag=fetched.etag, last_modified=fetched.last_modified)
            _write_json(DAILY / f"{key}.json", day)
        (FAILURES / f"{key}.json").unlink(missing_ok=True)
        return None
    return _ingest(key, src["url"], fetched)


def recheck_recent(fetcher, n: int | None) -> list[str]:
    """Recheck the n most recent parsed days (all if n is None). Returns failures."""
    dates = sorted(p.stem for p in DAILY.glob("*.json"))
    dates = dates if n is None else dates[-n:] if n > 0 else []
    return [key for key in dates if recheck(fetcher, key) is False]


def process_month(fetcher, year: int, month: int, month_url: str | None, force=False) -> list[str]:
    """Process every new day in a month. Returns the dates that failed.

    Uses the month article's PDF links when it is reachable. If there is no
    article, or the HTML pages are behind a bot challenge (the PDFs themselves
    are not), it falls back to probing each weekday's predictable PDF URL.
    """
    pdfs, probing = {}, False
    if month_url:
        try:
            pdfs = discover.find_daily_pdfs(fetcher.text(month_url), year, month)
        except (Blocked, NotFound) as e:
            print(f"month page unavailable ({e}); probing PDF URLs", file=sys.stderr)
    if not pdfs:
        pdfs, probing = _weekday_urls(year, month), True
    failed = []
    for day, url in sorted(pdfs.items()):
        key = day.isoformat()
        if (DAILY / f"{key}.json").exists() and not force:
            continue
        if process(fetcher, key, url, missing_ok=probing) is False:
            failed.append(key)
    return failed


def _weekday_urls(year: int, month: int) -> dict[dt.date, str]:
    today = dt.date.today()
    day, out = dt.date(year, month, 1), {}
    while day.month == month and day <= today:
        if day.weekday() < 5:
            out[day] = discover.guess_pdf_url(day)
        day += dt.timedelta(days=1)
    return out


def known_sources() -> dict[str, str]:
    """{date: source_url} for every day we have processed or tried to."""
    out = {}
    for folder in (FAILURES, DAILY):  # daily wins if both exist
        for p in folder.glob("*.json"):
            out[p.stem] = json.loads(p.read_text())["source"]["url"]
    return dict(sorted(out.items()))


def _month_pages(fetcher, url: str) -> dict:
    """{(year, month): article_url}, or {} if the listing is blocked (then we probe)."""
    try:
        months = discover.find_month_pages(fetcher.text(url))
    except Blocked as e:
        print(f"listing page blocked ({e}); probing PDF URLs instead", file=sys.stderr)
        return {}
    if not months:
        sys.exit(f"No month articles found at {url}; the site layout has changed")
    return months


def rebuild_indexes() -> None:
    """index.json, latest.json, and history/<CODE>.json (one file per currency,
    so a history query reads one file rather than one per day)."""
    dates = sorted(p.stem for p in DAILY.glob("*.json"))
    _write_json(DATA / "index.json", {"dates": dates, "count": len(dates)})
    series: dict[str, dict] = {}
    day = None
    for key in dates:
        day = json.loads((DAILY / f"{key}.json").read_text())
        for code, r in day["rates"].items():
            s = series.setdefault(code, {"currency": code, "aliases": r["aliases"], "points": []})
            s["aliases"] = r["aliases"]
            s["points"].append({"date": key, "zwg_per_unit": r["zwg_per_unit"]["mid"]})
    if day is not None:
        _write_json(DATA / "latest.json", day)
    for code, s in series.items():
        _write_json(DATA / "history" / f"{code}.json", s)
    for stale in (DATA / "history").glob("*.json"):
        if stale.stem not in series:
            stale.unlink()


# ---------------------------------------------------------------- commands

def cmd_update(args) -> int:
    from .fetch import Fetcher

    f = Fetcher()
    months = _month_pages(f, discover.LISTING_URL)
    today = dt.date.today()
    prev = (today.replace(day=1) - dt.timedelta(days=1))
    failed = recheck_recent(f, args.recheck)
    for ym in sorted({(today.year, today.month), (prev.year, prev.month)}):
        failed += process_month(f, *ym, months.get(ym))
    rebuild_indexes()
    return 1 if failed else 0


def cmd_backfill(args) -> int:
    from .fetch import Fetcher

    f = Fetcher()
    months = _month_pages(f, discover.LISTING_URL + "?limit=0")
    today = dt.date.today()
    candidates = months or {(args.year, m): None for m in range(1, 13)
                            if (args.year, m) <= (today.year, today.month)}
    wanted = [ym for ym in sorted(candidates) if ym[0] == args.year and (args.month is None or ym[1] == args.month)]
    failed = []
    for ym in wanted:
        failed += process_month(f, *ym, candidates[ym], force=args.force)
    rebuild_indexes()
    return 1 if failed else 0


def cmd_recheck(args) -> int:
    """Look for re-published PDFs over a longer window than `update` does."""
    from .fetch import Fetcher

    failed = recheck_recent(Fetcher(), None if args.all else args.days)
    rebuild_indexes()
    return 1 if failed else 0


def cmd_refetch(args) -> int:
    """Re-download and re-parse every known day (e.g. after adding a parser)."""
    from .fetch import Fetcher

    f = Fetcher()
    failed = [key for key, url in known_sources().items() if not process(f, key, url)]
    rebuild_indexes()
    return 1 if failed else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="rbz_rates")
    sub = p.add_subparsers(required=True)
    u = sub.add_parser("update", help="fetch this month and last month")
    u.add_argument("--recheck", type=int, default=5, metavar="N",
                   help="also check the N most recent days for re-published PDFs (default 5)")
    u.set_defaults(fn=cmd_update)
    b = sub.add_parser("backfill", help="fetch a whole year or month")
    b.add_argument("--year", type=int, required=True)
    b.add_argument("--month", type=int)
    b.add_argument("--force", action="store_true", help="re-fetch days that are already parsed")
    b.set_defaults(fn=cmd_backfill)
    r = sub.add_parser("recheck", help="check recent days for re-published PDFs")
    r.add_argument("--days", type=int, default=30, help="how many recent days (default 30)")
    r.add_argument("--all", action="store_true", help="every known day")
    r.set_defaults(fn=cmd_recheck)
    sub.add_parser("refetch", help="re-download and re-parse every known day").set_defaults(fn=cmd_refetch)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
