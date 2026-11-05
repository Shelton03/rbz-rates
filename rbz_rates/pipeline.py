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

Format changes: every sheet's layout is fingerprinted (see parse.Layout) and
recorded in data/formats.json, along with every currency code seen. The first
time a new format or currency appears, or a sheet can't be parsed, an alert is
printed and, if RBZ_ALERTS_FILE is set, appended to it as a JSON line; the
scrape workflow turns those into GitHub issues that notify the owner by email.
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
from .parse import Layout, NoLocalRates, ShapeError, parse_text, pdf_to_text

DATA = Path(os.environ.get("RBZ_DATA_DIR", "data"))
DAILY, FAILURES, SKIPPED = DATA / "daily", DATA / "failures", DATA / "skipped"
FORMATS = DATA / "formats.json"
ZIG_LAUNCH = dt.date(2024, 4, 5)  # first ZWG sheet; before this RBZ priced in ZWL / RTGS$


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


# ---------------------------------------------------------------- format registry & alerts

_alerted: set[str] = set()


def _alert(alert_id: str, title: str, body: str) -> None:
    """Report something the owner should look at, once per run per id."""
    if alert_id in _alerted:
        return
    _alerted.add(alert_id)
    print(f"ALERT {title}", file=sys.stderr)
    path = os.environ.get("RBZ_ALERTS_FILE")
    if path:
        with open(path, "a") as f:
            f.write(json.dumps({"id": alert_id, "title": title, "body": body}) + "\n")


def _registry() -> dict:
    reg = json.loads(FORMATS.read_text()) if FORMATS.exists() else {}
    reg.setdefault("formats", {})
    reg.setdefault("currencies", {})
    return reg


def _layout_md(layout: Layout | None) -> str:
    if layout is None:
        return "_No layout could be read from the file._"
    cols = ", ".join(f"{c} rows with {n} numbers" for n, c in sorted(layout.columns.items())) or "no rows"
    head = "\n".join(layout.head)
    return (f"- Local currency: `{layout.base}`\n- Header: `{layout.header or '(none found)'}`\n"
            f"- Rows: {cols}\n- Date style: `{layout.date_style}`\n"
            f"- \"INTERBANK RATE\" title line: {'yes' if layout.interbank_title else 'no'}\n"
            f"- Fingerprint: `{layout.fingerprint}` (`{layout.signature}`)\n\n"
            f"First lines of the sheet:\n\n```text\n{head}\n```")


def _record_success(key: str, url: str, layout: Layout, codes: list[str]) -> None:
    reg = _registry()
    fp = layout.fingerprint
    entry = reg["formats"].get(fp)
    if entry is None:
        reg["formats"][fp] = {"signature": layout.signature, "base": layout.base,
                              "first_seen": key, "last_seen": key, "example": url}
        if reg["currencies"]:  # an empty registry is being bootstrapped: nothing to compare with
            _alert(f"format-{fp}", f"New RBZ sheet format {fp} (parsed OK) on {key}",
                   f"The sheet for **{key}** uses a layout not seen before. It parsed and every check "
                   f"passed, so it has been published, but please give it a look.\n\n- PDF: {url}\n"
                   f"{_layout_md(layout)}")
    else:
        entry["first_seen"], entry["last_seen"] = min(entry["first_seen"], key), max(entry["last_seen"], key)
    new_codes = [c for c in codes if c not in reg["currencies"]]
    if new_codes and reg["currencies"]:
        _alert(f"currency-{'-'.join(sorted(new_codes))}",
               f"New currency on the RBZ sheet: {', '.join(sorted(new_codes))} ({key})",
               f"The sheet for **{key}** lists {', '.join(sorted(new_codes))}, which hasn't appeared before. "
               f"It has been published as usual.\n\n- PDF: {url}")
    for c in codes:
        seen = reg["currencies"].setdefault(c, {"first_seen": key, "last_seen": key})
        seen["first_seen"], seen["last_seen"] = min(seen["first_seen"], key), max(seen["last_seen"], key)
    _write_json(FORMATS, reg)


def _record_failure(key: str, url: str, error: str, layout: Layout | None) -> None:
    fp = layout.fingerprint if layout else "unreadable"
    _alert(f"failure-{fp}", f"RBZ sheet could not be parsed: format {fp} ({key})",
           f"The sheet for **{key}** was **not published**: {error}\n\n- PDF: {url}\n{_layout_md(layout)}\n\n"
           "If RBZ changed the layout, adjust `rbz_rates/parse.py` and run `python -m rbz_rates.pipeline refetch`. "
           "Days that fail are retried on every run.")


# ---------------------------------------------------------------- ingest

def _ingest(key: str, url: str, fetched) -> bool:
    """Parse PDF bytes held in memory and write the day's JSON. The bytes are
    dropped as soon as they are parsed; nothing PDF-shaped touches disk.

    If the day already exists with a different sha256, the old version is
    appended to "revisions". If parsing fails, any existing JSON is kept.
    """
    source = {"url": url, "retrieved_at": _now(), "sha256": hashlib.sha256(fetched.content).hexdigest(),
              "etag": fetched.etag, "last_modified": fetched.last_modified}
    try:
        text = pdf_to_text(fetched.content)
        doc = parse_text(text)
        out = normalise(doc)
    except NoLocalRates as e:
        if dt.date.fromisoformat(key) < ZIG_LAUNCH:
            # some 2019 sheets carry USD cross rates only: nothing to publish, nothing wrong
            _write_json(SKIPPED / f"{key}.json", {"date": key, "reason": str(e), "source": source})
            (FAILURES / f"{key}.json").unlink(missing_ok=True)
            print(f"skipped {key}: {e}")
            return None
        _record_failure(key, url, str(e), e.layout)  # today this would mean RBZ dropped the local rates
        return _fail(key, str(e), source)
    except ShapeError as e:
        _record_failure(key, url, str(e), e.layout)
        return _fail(key, str(e), source)
    except Exception as e:  # anything pdfminer raises on a damaged file
        _record_failure(key, url, f"{type(e).__name__}: {e}", None)
        return _fail(key, f"{type(e).__name__}: {e}", source)
    finally:
        fetched.content = None  # never persisted
    if out["date"] != key:
        out["warnings"].append(f"PDF says {out['date']} but listed as {key}; using listing date")
        out["date"] = key
    out["source"] = source

    previous = _load_day(key)
    revisions = (previous or {}).get("revisions", [])
    if previous and previous["source"].get("sha256") != source["sha256"]:
        old = previous["source"]
        revisions = revisions + [{k: old.get(k) for k in ("sha256", "retrieved_at", "last_modified")}]
        field = f"{out['base'].lower()}_per_unit"
        changed = sorted(c for c in out["rates"]
                         if out["rates"][c][field] != previous["rates"].get(c, {}).get(field))
        print(f"REVISED {key}: RBZ re-published the PDF; changed rates: {', '.join(changed) or 'none'}")
    if revisions:
        out["revisions"] = revisions

    _write_json(DAILY / f"{key}.json", out)
    (FAILURES / f"{key}.json").unlink(missing_ok=True)
    _record_success(key, url, doc.layout, list(out["rates"]))
    print(f"parsed {key}: {out['base']}, {len(out['rates'])} currencies, {len(out['warnings'])} warnings")
    return True


def process(fetcher, key: str, url: str, missing_ok: bool = False, fallback: str | None = None) -> bool | None:
    """Download one PDF into memory, parse it, write its JSON.

    True on success, False on failure (recorded in data/failures/), None if the
    PDF does not exist and missing_ok is set (probing a day RBZ hasn't published).
    fallback: another copy of the same file (the Internet Archive's) to use if RBZ returns 404.
    """
    try:
        fetched = fetcher.pdf(url)
    except NotFound as e:
        if fallback:
            print(f"{key}: not at {url}; using the Internet Archive's copy", file=sys.stderr)
            return process(fetcher, key, fallback, missing_ok)
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
    """Guessed URLs for each weekday; only meaningful in the ZWG era, whose filenames follow one pattern."""
    today = dt.date.today()
    day, out = dt.date(year, month, 1), {}
    while day.month == month and day <= today:
        if day.weekday() < 5 and day >= ZIG_LAUNCH:
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
            base = day.get("base", "ZWG")
            s["points"].append({"date": key, "base": base, "mid": r[f"{base.lower()}_per_unit"]["mid"]})
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


def _archived_with_retry(fetcher, year: int) -> dict[dt.date, str]:
    import time

    for attempt in range(5):
        try:
            return discover.archived_pdf_urls(fetcher, year)
        except (ValueError, OSError, httpx.HTTPError, Blocked) as e:
            print(f"archive index for {year} unavailable ({str(e)[:80]}); retry {attempt + 1}/5", file=sys.stderr)
            time.sleep(60)
    print(f"archive index for {year} still unavailable; only guessed ZWG-era URLs will be tried", file=sys.stderr)
    return {}


def cmd_backfill(args) -> int:
    """Fetch a whole year (or month): exact URLs from the Internet Archive's index of
    rbz.co.zw (older filenames follow no single pattern), plus guessed URLs for any
    ZWG-era weekday the archive missed. PDFs are fetched from rbz.co.zw."""
    from .fetch import Fetcher

    f = Fetcher(timeout=90)
    archived = {d: urls for d, urls in _archived_with_retry(f, args.year).items()
                if args.month is None or d.month == args.month}
    guessed = {}
    for m in ([args.month] if args.month else range(1, 13)):
        if (args.year, m) <= (dt.date.today().year, dt.date.today().month):
            guessed.update({d: u for d, u in _weekday_urls(args.year, m).items() if d not in archived})
    print(f"backfill {args.year}{'-%02d' % args.month if args.month else ''}: "
          f"{len(archived)} sheets in the archive index, {len(guessed)} guessed ZWG-era days")
    failed = []
    targets = {**{d: (u, None) for d, u in guessed.items()}, **archived}
    for day, (url, copy) in sorted(targets.items()):
        key = day.isoformat()
        if ((DAILY / f"{key}.json").exists() or (SKIPPED / f"{key}.json").exists()) and not args.force:
            continue
        if process(f, key, url, missing_ok=day in guessed, fallback=copy) is False:
            failed.append(key)
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
