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
    monkeypatch.setattr(pipeline, "SKIPPED", tmp_path / "skipped")
    monkeypatch.setattr(pipeline, "FORMATS", tmp_path / "formats.json")
    monkeypatch.setattr(pipeline, "_alerted", set())
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
    """worker/src/rbz_rates/ holds copies of the API modules (CI re-copies them before deploy)."""
    root = Path(__file__).parent.parent
    for name in ("api.py", "access.py"):
        assert (root / "worker/src/rbz_rates" / name).read_text() == (root / "rbz_rates" / name).read_text(), \
            "run: worker/sync.sh"


# ---------------------------------------------------------------- access control

@pytest.fixture
def gated(tmp_path, monkeypatch, day, pipe):
    """API client with the gate on: SQLite DB with the real migration applied."""
    import sqlite3

    import rbz_rates.access as access
    import rbz_rates.api as api
    (tmp_path / "daily").mkdir()
    (tmp_path / "daily" / "2026-11-05.json").write_text(json.dumps(day))
    pipe.rebuild_indexes()
    db = tmp_path / "access.db"
    sql = (Path(__file__).parent.parent / "worker/migrations/0001_access.sql").read_text()
    sqlite3.connect(db).executescript(sql)
    monkeypatch.setattr(api, "DATA", tmp_path)
    monkeypatch.setenv("RBZ_DB", str(db))
    monkeypatch.setenv("ADMIN_SECRET", "s3cret")
    monkeypatch.setenv("ANON_SALT", "salt")
    monkeypatch.setattr(access, "_local", None)
    monkeypatch.setattr(access, "_key_cache", {})
    monkeypatch.setattr(access, "ANON_DAILY", 3)
    monkeypatch.setattr(access, "KEY_DAILY", 5)
    api._load_file.cache_clear()
    from fastapi.testclient import TestClient
    return TestClient(api.app)


ADMIN = {"X-Admin-Secret": "s3cret"}


def _make_key(c, user="42", name="laptop"):
    assert c.put(f"/admin/users/{user}", json={"login": "shelton"}, headers=ADMIN).status_code == 200
    r = c.post(f"/admin/users/{user}/keys", json={"name": name}, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


def test_anonymous_daily_limit(gated):
    for i in range(3):
        r = gated.get("/v1/latest")
        assert r.status_code == 200 and r.headers["x-ratelimit-remaining"] == str(2 - i)
    r = gated.get("/v1/latest", headers={"Origin": "https://example.com"})
    assert r.status_code == 429
    assert "/dashboard" in r.json()["detail"]                       # tells them where to get a key
    assert r.headers["access-control-allow-origin"] == "*"          # browsers can read the error
    assert r.headers["x-ratelimit-reset"].endswith("T00:00:00Z")
    assert gated.get("/docs").status_code == 200                    # docs are never counted


def test_api_key_lifecycle(gated):
    created = _make_key(gated)
    key = created["key"]
    assert key.startswith("rbz_")
    auth = {"Authorization": f"Bearer {key}"}
    r = gated.get("/v1/convert", params={"amount": 1, "from": "USD", "to": "ZAR"}, headers=auth)
    assert r.status_code == 200 and r.headers["x-ratelimit-limit"] == "5"
    assert gated.get("/v1/latest", headers={"X-API-Key": key}).status_code == 200
    assert gated.get("/v1/latest", params={"api_key": key}).status_code == 200
    assert gated.get("/v1/latest", headers={"X-API-Key": "rbz_wrong"}).status_code == 401

    keys = gated.get("/admin/users/42/keys", headers=ADMIN).json()["keys"]
    assert keys[0]["today"] == 3 and keys[0]["prefix"] == key[:10] and "hash" not in keys[0]
    assert "key" not in keys[0]                                     # the full key is never shown again
    usage = gated.get("/admin/users/42/usage", headers=ADMIN).json()["rows"]
    assert {(u["endpoint"], u["count"]) for u in usage} == {("/v1/convert", 1), ("/v1/latest", 2)}

    for _ in range(2):
        assert gated.get("/v1/latest", headers=auth).status_code == 200
    r = gated.get("/v1/latest", headers=auth)
    assert r.status_code == 429 and "/dashboard" not in r.json()["detail"]

    assert gated.delete(f"/admin/users/42/keys/{created['id']}", headers=ADMIN).status_code == 200
    assert gated.get("/v1/latest", headers=auth).status_code == 401  # revoked: rejected immediately
    assert gated.delete(f"/admin/users/42/keys/{created['id']}", headers=ADMIN).status_code == 404


def test_key_limits_and_admin_auth(gated):
    for i in range(3):
        _make_key(gated, name=f"k{i}")
    r = gated.post("/admin/users/42/keys", json={"name": "fourth"}, headers=ADMIN)
    assert r.status_code == 409
    assert gated.post("/admin/users/nobody/keys", json={"name": "x"}, headers=ADMIN).status_code == 404
    assert gated.get("/admin/stats").status_code == 401                         # no secret
    assert gated.get("/admin/stats", headers={"X-Admin-Secret": "nope"}).status_code == 401
    other = gated.get("/admin/users/99/keys", headers=ADMIN).json()["keys"]
    assert other == []                                                          # keys are per user
    gated.get("/v1/latest")
    s = gated.get("/admin/stats", headers=ADMIN).json()
    assert s["users"] == 1 and s["active_keys"] == 3
    assert s["by_day"][0]["anonymous"] == 1 and s["by_endpoint"][0]["endpoint"] == "/v1/latest"
    assert "/admin/stats" not in gated.get("/openapi.json").text                # admin hidden from docs


# ---------------------------------------------------------------- older (ZWL-era) sheets & format changes

OLD = {name: (FIX / name).read_text() for name in
       ("RATES_1_APRIL_2019.txt", "RATES_3_APRIL_2023.txt", "RATES_2_APRIL_2024.txt")}


@pytest.mark.parametrize("name, date, rows", [
    ("RATES_1_APRIL_2019.txt", dt.date(2019, 4, 1), 39),   # "Monday, April 01, 2019", no INTERBANK RATE line
    ("RATES_3_APRIL_2023.txt", dt.date(2023, 4, 3), 40),   # "Monday, 03 April2023"
    ("RATES_2_APRIL_2024.txt", dt.date(2024, 4, 2), 41),   # includes a pre-launch ZIG row
])
def test_zwl_era_sheets_parse(name, date, rows):
    doc = parse_text(OLD[name])
    assert doc.base == "ZWL" and doc.date == date and len(doc.rows) == rows
    out = normalise(doc)
    assert "zwl_per_unit" in out["rates"]["USD"] and "zwg_per_unit" not in out["rates"]["USD"]
    assert out["rates"]["USD"]["as_published"]["zwl_orientation"] == "zwl_per_unit"


def test_layouts_get_distinct_fingerprints():
    fps = {parse_text(t).layout.fingerprint for t in [*OLD.values(), TEXT]}
    assert len(fps) == 4


def test_coarse_zwl_rows_are_derived_from_usd_column():
    out = normalise(parse_text(OLD["RATES_2_APRIL_2024.txt"]))
    zar = out["rates"]["ZAR"]
    assert zar["as_published"]["zwl"]["mid"] == 0.0009                 # what RBZ printed
    assert zar["derived_from"] == "usd" and zar["verified"] is True
    assert zar["zwl_per_unit"]["mid"] == pytest.approx(22447.5305 / 18.9322, rel=1e-6)
    cad = out["rates"]["CAD"]                                           # printed as 0.0001: can't confirm
    assert cad["derived_from"] == "usd" and cad["verified"] is False
    assert any("CAD" in w and "coarsely" in w for w in out["warnings"])
    assert out["rates"]["ZIG"]["verified"] is False                     # genuinely inconsistent: flagged


def test_real_inconsistency_is_kept_and_flagged():
    out = normalise(parse_text(OLD["RATES_3_APRIL_2023.txt"]))
    assert out["rates"]["XAU"]["verified"] is False and "derived_from" not in out["rates"]["XAU"]
    assert any(w.startswith("XAU: published figures are not internally consistent") for w in out["warnings"])


def test_structural_change_is_refused_with_layout():
    seven = "\n".join(ln + " 1.0" if ln[:3].isupper() and ln[:3].isalpha() and any(c.isdigit() for c in ln) else ln
                      for ln in TEXT.splitlines())
    with pytest.raises(ShapeError) as e:
        parse_text(seven)
    assert "7" in str(e.value) and e.value.layout is not None and e.value.layout.columns.get(7)


def test_misread_columns_are_not_published():
    """Columns read shifted by one (e.g. a merged cell): the numbers stop reconciling, so the sheet is refused."""
    def shift(ln):
        parts = ln.split()
        if len(parts) >= 7 and parts[0] != "USD" and parts[0][:3].isalpha() and parts[0][:3].isupper():
            nums = parts[-6:]
            return " ".join(parts[:-6] + nums[1:] + nums[:1])
        return ln
    with pytest.raises(ShapeError, match="don't reconcile"):
        normalise(parse_text("\n".join(shift(ln) for ln in TEXT.splitlines())))


def test_filename_dates():
    assert discover.date_from_url("x/2019/Apr/5-April-2019.pdf") == dt.date(2019, 4, 5)
    assert discover.date_from_url("x/Rates-1-April-2022.pdf") == dt.date(2022, 4, 1)
    assert discover.date_from_url("x/RATES_03_APRIL_2023-INTERBANK_RATE.pdf") == dt.date(2023, 4, 3)
    assert discover.date_from_url("x/notes.pdf") is None


def test_new_format_currency_and_failure_alerts(pipe, tmp_path, monkeypatch):
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setenv("RBZ_ALERTS_FILE", str(alerts))
    monkeypatch.setattr(pipe, "FORMATS", tmp_path / "formats.json")
    monkeypatch.setattr(pipe, "_alerted", set())
    url = "https://www.rbz.co.zw/documents/x.pdf"
    f = FakeFetcher({}, {url: _render_pdf(TEXT)})

    assert pipe.process(f, "2026-11-05", url)               # bootstrap: registry empty, no alert
    assert not alerts.exists()
    assert pipe.process(f, "2026-11-05", url)               # known format, known currencies: no alert
    assert not alerts.exists()

    # a sheet with a new header wording and a new currency: published, but alerted
    changed = TEXT.replace("CURRENCY INDICES", "CURRENCY INDEX").replace(
        "XAF ", "XYZ 1.0000 1.0000 1.00000 26.5365 26.5365 26.5365\nXAF ", 1)
    f.pdfs[url] = _render_pdf(changed)
    assert pipe.process(f, "2026-11-06", url)
    kinds = [json.loads(ln)["id"].split("-")[0] for ln in alerts.read_text().splitlines()]
    assert kinds == ["format", "currency"]

    # an unparseable sheet: not published, alerted once even if seen twice in a run
    f.pdfs[url] = _render_pdf("\n".join(ln + " 9" if ln.startswith(("USD", "ZAR", "GBP")) else ln
                                        for ln in TEXT.splitlines()).replace("BID", "OFFER"))
    assert pipe.process(f, "2026-11-09", url) is False
    assert pipe.process(f, "2026-11-10", url) is False
    lines = [json.loads(ln) for ln in alerts.read_text().splitlines()]
    assert [ln["id"].split("-")[0] for ln in lines] == ["format", "currency", "failure"]
    assert "not published" in lines[-1]["body"] and url in lines[-1]["body"]


def test_api_on_zwl_era_day(tmp_path, monkeypatch, pipe):
    (tmp_path / "daily").mkdir()
    for name, key in (("RATES_2_APRIL_2024.txt", "2024-04-02"), ("RATES_5_NOVEMBER_2026.txt", "2026-11-05")):
        out = normalise(parse_text((FIX / name).read_text()))
        out["source"] = {"url": "x", "retrieved_at": "x"}
        (tmp_path / "daily" / f"{key}.json").write_text(json.dumps(out))
    pipe.rebuild_indexes()
    import rbz_rates.api as api
    monkeypatch.setattr(api, "DATA", tmp_path)
    api._load_file.cache_clear()
    from fastapi.testclient import TestClient
    c = TestClient(api.app)
    conv = lambda f, t, d: c.get("/v1/convert", params={"amount": 1, "from": f, "to": t, "date": d})

    r = conv("USD", "ZWL", "2024-04-02").json()
    assert r["rate"] == pytest.approx(22447.5305) and r["via"] == "direct (RBZ ZWL column)"
    assert conv("ZAR", "ZWL", "2024-04-02").json()["rate"] == pytest.approx(22447.5305 / 18.9322, rel=1e-6)  # derived
    assert conv("USD", "ZWG", "2024-04-02").status_code == 404     # ZWG didn't exist yet
    assert conv("USD", "ZWL", "2026-11-05").status_code == 404     # ZWL no longer does
    assert conv("USD", "ZWG", "2026-11-05").json()["rate"] == pytest.approx(26.5365)

    h = c.get("/v1/history/USD", params={"from": "2024-01-01"}).json()
    assert h["base"] == "ZWG" and h["points"] == [{"date": "2026-11-05", "zwg_per_unit": 26.5365}]
    h = c.get("/v1/history/USD", params={"from": "2024-01-01", "base": "ZWL"}).json()
    assert h["points"] == [{"date": "2024-04-02", "zwl_per_unit": 22447.5305}]
    assert c.get("/v1/history/ZWL", params={"from": "2024-01-01", "base": "ZWL"}).json()["points"][0]["zwl_per_unit"] == 1.0
    assert c.get("/v1/history/USD", params={"from": "2024-01-01", "base": "EUR"}).status_code == 400


def test_unlabelled_usd_row_2019():
    """Some 2019 sheets print the USD row without its label; an index of exactly 1/1/1 identifies it."""
    text = OLD["RATES_1_APRIL_2019.txt"].replace("USD 1 1 1.0000", "1 1 1.0000", 1)
    doc = parse_text(text)
    assert doc.rows[0].code == "USD" and doc.rows[0].local[2] == 3.0231
    assert normalise(doc)["rates"]["USD"]["verified"]
    # a label-less row that isn't 1/1/1 is not taken for anything
    assert parse_text(text.replace("ZAR 14.2963", "14.2963", 1)).rows[1].code != "ZAR"


def test_usd_row_out_of_step_with_crosses_2019():
    """30 Aug 2019: every cross implies 10.52 ZWL/USD but the USD row says 10.71. Published as printed, flagged."""
    out = normalise(parse_text((FIX / "RATES_30_AUGUST_2019.txt").read_text()))
    assert len(out["rates"]) == 40 and not any(r["verified"] for r in out["rates"].values())
    assert "imply 1 USD = 10.5189 ZWL" in out["warnings"][0]
    assert out["rates"]["GBP"]["zwl_per_unit"]["mid"] == 12.8224          # as printed


def test_usd_only_sheets_skipped_before_zig_but_alert_after(pipe, tmp_path, monkeypatch):
    from rbz_rates.parse import NoLocalRates
    usd_only = (FIX / "RATES_7_AUGUST_2019.txt").read_text()
    with pytest.raises(NoLocalRates):
        parse_text(usd_only)
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setenv("RBZ_ALERTS_FILE", str(alerts))
    url = "https://www.rbz.co.zw/documents/x.pdf"
    f = FakeFetcher({}, {url: _render_pdf(usd_only)})
    assert pipe.process(f, "2019-08-07", url) is None                  # skipped, not failed
    assert (tmp_path / "skipped" / "2019-08-07.json").exists() and not alerts.exists()
    assert pipe.process(f, "2026-11-06", url) is False                 # today: a real change
    assert (tmp_path / "failures" / "2026-11-06.json").exists()
    assert "failure" in alerts.read_text()


def test_early_zig_label_duplicates_and_zeros():
    zig = TEXT.replace("ZWG ZWG ZWG", "ZIG ZIG ZIG")                          # Apr-Jun 2024 label
    assert parse_text(zig).base == "ZWG"
    dup = TEXT.replace("XAF ", "ARS 822.4000 822.5000 822.45000 30.1 30.2 30.15\nXAF ", 1)
    doc = parse_text(dup)                                                     # ARS twice (Jan 2024)
    assert [r.code for r in doc.rows].count("ARS") == 1 and any("ARS appears twice" in w for w in doc.warnings)
    out = normalise(parse_text((FIX / "RATES_22_FEBRUARY_2024.txt").read_text()))  # CAD printed 0.0000
    cad = out["rates"]["CAD"]
    assert cad["derived_from"] == "usd" and cad["verified"] is False
    assert cad["zwl_per_unit"]["mid"] == pytest.approx(13466.4147 / 1.34805, rel=1e-6)


def test_gold_coin_documents_are_not_rate_sheets():
    assert discover.NOT_RATES_RE.search("27_December_2023_Gold_Coin__Token_Price.pdf")
    assert not discover.NOT_RATES_RE.search("RATES_27_DECEMBER_2023-INTERBANK_RATE.pdf")


def test_date_without_weekday_2025():
    doc = parse_text((FIX / "RATES_7_JANUARY_2025.txt").read_text())   # "07 January2025"
    assert doc.date == dt.date(2025, 1, 7) and doc.base == "ZWG"


def test_history_reads_old_format_files(tmp_path, monkeypatch, day, pipe):
    """A deploy can pair new API code with history files from before the base/mid format."""
    (tmp_path / "daily").mkdir()
    (tmp_path / "daily" / "2026-11-05.json").write_text(json.dumps(day))
    pipe.rebuild_indexes()
    (tmp_path / "history" / "USD.json").write_text(json.dumps(
        {"currency": "USD", "aliases": [], "points": [{"date": "2026-11-05", "zwg_per_unit": 26.5365}]}))
    import rbz_rates.api as api
    monkeypatch.setattr(api, "DATA", tmp_path)
    api._load_file.cache_clear()
    from fastapi.testclient import TestClient
    r = TestClient(api.app).get("/v1/history/USD", params={"from": "2026-11-01"})
    assert r.status_code == 200 and r.json()["points"] == [{"date": "2026-11-05", "zwg_per_unit": 26.5365}]
