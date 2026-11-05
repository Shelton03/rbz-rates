"""Read-only HTTP API over data/.

Locally:            uvicorn rbz_rates.api:app        (reads files under $RBZ_DATA_DIR, default data/)
Cloudflare Workers: see worker/                       (reads the same files through the ASSETS binding)
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request

DATA = Path(os.environ.get("RBZ_DATA_DIR", "data"))
app = FastAPI(title="RBZ Exchange Rates",
              description="Unofficial mirror of Reserve Bank of Zimbabwe daily interbank rates. "
                          "Rates are as published by RBZ; check the source PDF before relying on a figure.")


# ---------------------------------------------------------------- data access

class FileStore:
    """JSON files on local disk. Cached on mtime, so a revised day is picked up without a restart."""

    async def read(self, rel: str) -> dict | None:
        path = DATA / rel
        try:
            return _load_file(path, path.stat().st_mtime_ns)
        except FileNotFoundError:
            return None


@lru_cache(maxsize=512)
def _load_file(path: Path, _mtime: int) -> dict:
    return json.loads(path.read_text())


class AssetStore:
    """JSON files deployed as Cloudflare Workers static assets. A deployment's
    assets never change, so each isolate caches what it has read."""

    def __init__(self, assets):
        self.assets, self.cache = assets, {}

    async def read(self, rel: str) -> dict | None:
        if rel not in self.cache:
            resp = await self.assets.fetch(f"https://assets.local/{rel}")
            self.cache[rel] = json.loads(await resp.text()) if resp.status == 200 else None
        return self.cache[rel]


_asset_store: AssetStore | None = None


def get_store(request: Request):
    global _asset_store
    env = request.scope.get("env")  # set by the Workers runtime; absent under uvicorn
    if env is not None:
        if _asset_store is None:
            _asset_store = AssetStore(env.ASSETS)
        return _asset_store
    return FileStore()


# ---------------------------------------------------------------- lookups

async def _dates(store) -> list[str]:
    index = await store.read("index.json")
    if not index or not index["dates"]:
        raise HTTPException(503, "No data yet")
    return index["dates"]


async def _day(store, date: str) -> dict:
    day = await store.read(f"daily/{date}.json")
    if day is None:
        raise HTTPException(503, f"Data for {date} is listed but missing")
    return day


async def _resolve(store, date: str | None) -> dict:
    dates = await _dates(store)
    if date is None:
        return await _day(store, dates[-1])
    _check_date(date, "date")
    # RBZ only publishes on business days: use the latest rate on or before the date
    i = bisect.bisect_right(dates, date)
    if i == 0:
        raise HTTPException(404, f"No rates on or before {date}")
    return await _day(store, dates[i - 1])


def _check_date(value: str, name: str) -> None:
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"{name} must be YYYY-MM-DD")


def _entry(day: dict, code: str) -> tuple[str, dict | None]:
    """(canonical code, rate entry); entry is None for ZWG itself."""
    code = code.upper()
    if code == "ZWG":
        return code, None
    for c, r in day["rates"].items():
        if c == code or code in r["aliases"]:
            return c, r
    raise HTTPException(404, f"Unknown currency {code}")


def _per_unit(r: dict, column: str) -> tuple[float, float]:
    """USD or ZWG per 1 unit as a fraction (num, den) of the printed mid.

    Kept as a fraction so a figure RBZ prints as "units per USD/ZWG" is used
    exactly as printed rather than round-tripped through a stored reciprocal.
    """
    pub = r["as_published"]
    value, orientation = (pub["index"]["mid"], pub["index_orientation"]) if column == "USD" \
        else (pub["zwg"]["mid"], pub["zwg_orientation"])
    return (value, 1.0) if orientation.endswith("_per_unit") else (1.0, value)


def _pair_rate(day: dict, frm: str, to: str) -> tuple[float, str]:
    """Units of `to` per 1 unit of `frm`, using RBZ's published figure for the pair.

    X/USD uses the USD column and X/ZWG the ZWG column, exactly as printed.
    RBZ prints no direct rate for other pairs, so those are crossed through
    USD (the base RBZ quotes its indices against), never through ZWG.
    """
    f, fr = _entry(day, frm)
    t, tr = _entry(day, to)
    if f == t:
        return 1.0, "same currency"
    if "ZWG" in (f, t):
        if t == "ZWG":
            n, d = _per_unit(fr, "ZWG")
        else:
            d, n = _per_unit(tr, "ZWG")
        return n / d, "direct (RBZ ZWG column)"
    fn, fd = _per_unit(fr, "USD")
    tn, td = _per_unit(tr, "USD")
    via = "direct (RBZ USD column)" if "USD" in (f, t) else "cross via USD (RBZ USD column)"
    return (fn * td) / (fd * tn), via


# ---------------------------------------------------------------- endpoints

@app.get("/v1/latest")
async def latest(store=Depends(get_store)):
    return await _resolve(store, None)


@app.get("/v1/rates/{date}")
async def rates_on(date: str, store=Depends(get_store)):
    """Rates in effect on a date (falls back to the previous published day)."""
    return await _resolve(store, date)


@app.get("/v1/currencies")
async def currencies(store=Depends(get_store)):
    day = await _resolve(store, None)
    return {c: {"aliases": r["aliases"]} for c, r in day["rates"].items()}


@app.get("/v1/history/{code}")
async def history(code: str, start: str = Query(..., alias="from"), end: str = Query(None, alias="to"),
                  store=Depends(get_store)):
    """ZWG per 1 unit (mid) on every published day in the range."""
    end = end or dt.date.today().isoformat()
    _check_date(start, "from")
    _check_date(end, "to")
    code = code.upper()
    if code == "ZWG":
        points = [{"date": d, "zwg_per_unit": 1.0} for d in await _dates(store) if start <= d <= end]
        return {"currency": code, "points": points}
    series = await store.read(f"history/{code}.json")
    if series is None:  # maybe an alias, e.g. ZMK -> ZMW
        canonical, _ = _entry(await _resolve(store, None), code)
        series = await store.read(f"history/{canonical}.json")
        if series is None:
            raise HTTPException(404, f"Unknown currency {code}")
    points = [p for p in series["points"] if start <= p["date"] <= end]
    return {"currency": code, "points": points}


@app.get("/v1/convert")
async def convert(amount: float, frm: str = Query(..., alias="from"), to: str = Query(...),
                  date: str | None = None, store=Depends(get_store)):
    day = await _resolve(store, date)
    rate, via = _pair_rate(day, frm, to)
    return {"date": day["date"], "from": frm.upper(), "to": to.upper(), "amount": amount,
            "rate": round(rate, 10), "result": round(amount * rate, 6), "via": via}
