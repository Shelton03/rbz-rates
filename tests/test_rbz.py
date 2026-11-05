import datetime as dt
import json
from pathlib import Path

import pytest

from rbz_rates import discover
from rbz_rates.normalize import normalise
from rbz_rates.parse import ShapeError, parse_pdf, parse_text

FIX = Path(__file__).parent / "fixtures"
TEXT = (FIX / "RATES_5_NOVEMBER_2026.txt").read_text()


@pytest.fixture(scope="module")
def day():
    return normalise(parse_text(TEXT))


def test_parses_all_rows():
    doc = parse_text(TEXT)
    assert doc.date == dt.date(2026, 11, 5)
    assert len(doc.rows) == 40
    zmw = next(r for r in doc.rows if r.code == "ZMW")
    assert zmw.aliases == ["ZMK"]
    mwk = next(r for r in doc.rows if r.code == "MWK")
    assert mwk.index[2] == 1733.67  # thousands separator handled


@pytest.mark.parametrize("code, expected", [
    ("USD", 26.5365),
    ("GBP", 35.8086),   # starred, published as ZWG per GBP
    ("XAU", 109503.6302),  # NOT starred, but also ZWG per unit
    ("CHF", 32.5943),   # USD column is CHF per USD, ZWG column is ZWG per CHF
    ("ZAR", 1 / 0.6161),  # published as ZAR per ZWG -> inverted
    ("CAD", 1 / 0.0526),  # starred, yet published as CAD per ZWG
    ("BWP", 1.8582),
])
def test_everything_is_zwg_per_unit(day, code, expected):
    assert day["rates"][code]["zwg_per_unit"]["mid"] == pytest.approx(expected, rel=1e-3)


def test_all_rows_internally_consistent(day):
    assert day["warnings"] == []
    assert all(r["verified"] for r in day["rates"].values())


def test_inversion_keeps_bid_below_ask(day):
    for code, r in day["rates"].items():
        q = r["zwg_per_unit"]
        assert q["bid"] <= q["mid"] <= q["ask"], code


@pytest.mark.parametrize("header, expected", [
    ("Thursday, 05 November 2026", dt.date(2026, 11, 5)),
    ("Wednesday, November 4, 2026", dt.date(2026, 11, 4)),
])
def test_both_date_styles(header, expected):
    text = TEXT.replace("Thursday, 05 November 2026", header, 1)
    assert parse_text(text).date == expected


def test_unknown_layout_is_rejected():
    with pytest.raises(ShapeError):
        parse_text("RTGS$ RATES\nUSD 1 1 1 2.5 2.6 2.55\n" * 5)


def test_inconsistent_row_is_flagged():
    broken = TEXT.replace("ZAR 16.3369 16.3397 16.33830 0.6006 0.6315 0.6161",
                          "ZAR 16.3369 16.3397 16.33830 0.9006 0.9315 0.9161")
    out = normalise(parse_text(broken))
    assert out["rates"]["ZAR"]["verified"] is False
    assert any("ZAR" in w for w in out["warnings"])


def _render_pdf(text: str) -> bytes:
    """Render text to a PDF in memory (no file on disk)."""
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.splitlines():
        c.drawString(40, y, line)
        y -= 16
    c.save()
    return buf.getvalue()


def test_real_pdf_round_trip():
    """Render the fixture to a PDF and parse it through pdfplumber."""
    doc = parse_pdf(_render_pdf(TEXT))
    assert len(doc.rows) == 40 and doc.date == dt.date(2026, 11, 5)


class FakeFetcher:
    """Serves PDFs from a dict; supports conditional requests via a fake ETag."""

    def __init__(self, pages: dict[str, str], pdfs: dict[str, bytes]):
        self.pages, self.pdfs, self.calls = pages, pdfs, []

    def text(self, url):
        return self.pages[url]

    def pdf(self, url, etag=None, last_modified=None):
        import hashlib

        from rbz_rates.fetch import FetchedPDF, NotFound
        self.calls.append(url)
        if url not in self.pdfs:
            raise NotFound(url)
        content = self.pdfs[url]
        tag = '"' + hashlib.md5(content).hexdigest() + '"'
        if etag == tag:
            return FetchedPDF(None, tag, "Thu, 05 Nov 2026 05:55:38 GMT")
        return FetchedPDF(content, tag, "Thu, 05 Nov 2026 05:55:38 GMT")


@pytest.fixture
def pipe(tmp_path, monkeypatch):
    import rbz_rates.pipeline as pipeline
    monkeypatch.setattr(pipeline, "DATA", tmp_path)
    monkeypatch.setattr(pipeline, "DAILY", tmp_path / "daily")
    monkeypatch.setattr(pipeline, "FAILURES", tmp_path / "failures")
    return pipeline


def test_pipeline_never_persists_pdfs(pipe, tmp_path):
    html = (FIX / "month_page.html").read_text()
    urls = discover.find_daily_pdfs(html, 2026, 11)
    good = _render_pdf(TEXT)
    pdfs = {u: good for d, u in urls.items() if d.day != 2}  # the 2nd isn't there (404)
    f = FakeFetcher({"month": html}, pdfs)

    failed = pipe.process_month(f, 2026, 11, "month")
    pipe.rebuild_indexes()

    assert failed == ["2026-11-02"]
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert not [p for p in files if p.suffix.lower() == ".pdf"]
    assert not [p for p in files if p.read_bytes().startswith(b"%PDF")]
    assert sorted(p.name for p in (tmp_path / "daily").iterdir()) == [
        "2026-11-03.json", "2026-11-04.json", "2026-11-05.json"]
    out = json.loads((tmp_path / "daily" / "2026-11-05.json").read_text())
    assert out["source"]["url"] == urls[dt.date(2026, 11, 5)]
    assert len(out["source"]["sha256"]) == 64
    assert json.loads((tmp_path / "index.json").read_text())["count"] == 3
    assert (tmp_path / "failures" / "2026-11-02.json").exists()

    # next run: parsed days are skipped, the failed day is retried
    f.calls.clear()
    f.pdfs[urls[dt.date(2026, 11, 2)]] = good
    assert pipe.process_month(f, 2026, 11, "month") == []
    assert f.calls == [urls[dt.date(2026, 11, 2)]]
    assert not (tmp_path / "failures" / "2026-11-02.json").exists()

    # refetch re-downloads every known day from its recorded source URL
    assert set(pipe.known_sources().values()) == set(urls.values())


def test_discovery():
    html = (FIX / "month_page.html").read_text()
    pdfs = discover.find_daily_pdfs(html, 2026, 11)
    assert sorted(pdfs) == [dt.date(2026, 11, d) for d in (2, 3, 4, 5)]  # 6th, 9th not published yet
    assert pdfs[dt.date(2026, 11, 5)].endswith("RATES_5_NOVEMBER_2026.pdf")
    months = discover.find_month_pages(html)
    assert set(months) == {(2026, 11), (2026, 3)}
    assert discover.guess_pdf_url(dt.date(2026, 11, 5)) == pdfs[dt.date(2026, 11, 5)]


def test_api(tmp_path, monkeypatch, day, pipe):
    (tmp_path / "daily").mkdir()
    (tmp_path / "daily" / "2026-11-05.json").write_text(json.dumps(day))
    pipe.rebuild_indexes()
    import rbz_rates.api as api
    monkeypatch.setattr(api, "DATA", tmp_path)
    api._load_file.cache_clear()
    from fastapi.testclient import TestClient

    c = TestClient(api.app)
    assert c.get("/v1/latest").json()["date"] == "2026-11-05"
    assert c.get("/v1/rates/2026-11-08").json()["date"] == "2026-11-05"  # Sunday -> Thursday
    assert c.get("/v1/rates/2026-11-01").status_code == 404
    h = c.get("/v1/history/USD", params={"from": "2026-11-01"}).json()
    assert h["points"] == [{"date": "2026-11-05", "zwg_per_unit": 26.5365}]
    assert c.get("/v1/history/ZMK", params={"from": "2026-11-01"}).json()["points"][0]["zwg_per_unit"] == \
        day["rates"]["ZMW"]["zwg_per_unit"]["mid"]  # alias
    assert c.get("/v1/history/XYZ", params={"from": "2026-11-01"}).status_code == 404
    assert c.get("/v1/history/USD", params={"from": "banana"}).status_code == 400
    conv = lambda f, t, a=1: c.get("/v1/convert", params={"amount": a, "from": f, "to": t}).json()
    # USD pairs use RBZ's USD column exactly as printed, not a ZWG cross
    r = conv("USD", "ZAR", 100)
    assert r["rate"] == pytest.approx(16.3383, abs=1e-9) and r["result"] == pytest.approx(1633.83)
    assert conv("GBP", "USD")["rate"] == pytest.approx(1.3494, abs=1e-9)
    assert conv("USD", "CHF")["rate"] == pytest.approx(0.81415, abs=1e-9)
    # ZWG pairs use the ZWG column as printed (inverted where RBZ prints units per ZWG)
    assert conv("USD", "ZWG")["rate"] == pytest.approx(26.5365, abs=1e-9)
    assert conv("ZWG", "ZAR")["rate"] == pytest.approx(0.6161, abs=1e-9)
    assert conv("ZWG", "ZMK")["rate"] == pytest.approx(0.7645, abs=1e-9)  # alias, printed as ZMW per ZWG
    assert conv("GBP", "ZWG")["rate"] == pytest.approx(35.8086, abs=1e-9)
    # other pairs cross through USD, never ZWG
    r = conv("GBP", "ZAR")
    assert r["rate"] == pytest.approx(1.3494 * 16.3383, rel=1e-9) and "USD" in r["via"]


def test_recheck_picks_up_republished_pdf(pipe, tmp_path):
    html = (FIX / "month_page.html").read_text()
    url = discover.find_daily_pdfs(html, 2026, 11)[dt.date(2026, 11, 5)]
    f = FakeFetcher({}, {url: _render_pdf(TEXT)})
    assert pipe.process(f, "2026-11-05", url)
    first = json.loads((tmp_path / "daily" / "2026-11-05.json").read_text())
    assert first["source"]["etag"] and "revisions" not in first

    # unchanged: conditional request, nothing rewritten
    mtime = (tmp_path / "daily" / "2026-11-05.json").stat().st_mtime_ns
    assert pipe.recheck(f, "2026-11-05") is None
    assert (tmp_path / "daily" / "2026-11-05.json").stat().st_mtime_ns == mtime

    # RBZ corrects the ZAR row and re-uploads
    f.pdfs[url] = _render_pdf(TEXT.replace("0.6006 0.6315 0.6161", "0.6106 0.6415 0.6261", 1))
    assert pipe.recheck_recent(f, 5) == []
    second = json.loads((tmp_path / "daily" / "2026-11-05.json").read_text())
    assert second["rates"]["ZAR"]["as_published"]["zwg"]["mid"] == 0.6261
    assert second["source"]["sha256"] != first["source"]["sha256"]
    assert second["revisions"] == [{"sha256": first["source"]["sha256"],
                                    "retrieved_at": first["source"]["retrieved_at"],
                                    "last_modified": first["source"]["last_modified"]}]

    # a broken re-upload keeps the good data and records the failure
    f.pdfs[url] = b"%PDF-1.7 garbage"
    assert pipe.recheck(f, "2026-11-05") is False
    assert json.loads((tmp_path / "daily" / "2026-11-05.json").read_text()) == second
    assert (tmp_path / "failures" / "2026-11-05.json").exists()


def test_fetcher_conditional_request(monkeypatch):
    """The real Fetcher against a mock server: 200 with validators, then 304."""
    import httpx

    from rbz_rates import fetch
    monkeypatch.setattr(fetch, "DELAY_SECONDS", 0)
    body, tag = b"%PDF-1.7 fake", '"abc"'

    def handler(req):
        if req.headers.get("if-none-match") == tag:
            return httpx.Response(304, headers={"etag": tag})
        return httpx.Response(200, content=body, headers={"etag": tag, "last-modified": "Thu, 05 Nov 2026 05:55:38 GMT"})

    f = fetch.Fetcher()
    f.client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": fetch.USER_AGENT})
    url = "https://www.rbz.co.zw/documents/x.pdf"
    first = f.pdf(url)
    assert first.content == body and first.etag == tag
    again = f.pdf(url, first.etag, first.last_modified)
    assert again.content is None and again.last_modified == first.last_modified


def test_worker_bundles_current_api():
    """worker/src/rbz_api.py is a copy of rbz_rates/api.py (CI re-copies it before deploy)."""
    root = Path(__file__).parent.parent
    assert (root / "worker/src/rbz_api.py").read_text() == (root / "rbz_rates/api.py").read_text(), \
        "run: cp rbz_rates/api.py worker/src/rbz_api.py"
