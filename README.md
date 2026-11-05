# rbz-rates

An unofficial, open-source mirror of the Reserve Bank of Zimbabwe's daily
interbank exchange rates, as JSON.

RBZ publishes the rates as one PDF per business day
([source page](https://www.rbz.co.zw/index.php/research/markets/exchange-rates)).
This project downloads each PDF into memory, parses it, normalises the numbers
and publishes them as plain JSON files plus an optional HTTP API. PDFs are never
written to disk: each JSON records the source URL and the PDF's sha256 instead,
so any figure can be checked against the original on the RBZ site.

## Using the data

No server needed. Once the repo is on GitHub, the JSON is served for free:

```
https://cdn.jsdelivr.net/gh/Shelton03/rbz-rates@main/data/latest.json
https://cdn.jsdelivr.net/gh/Shelton03/rbz-rates@main/data/daily/2026-11-05.json
https://cdn.jsdelivr.net/gh/Shelton03/rbz-rates@main/data/index.json
```

Every rate is **ZWG per 1 unit of the currency**, with `bid`, `ask` and `mid`:

```json
{
  "date": "2026-11-05",
  "base": "ZWG",
  "rates": {
    "USD": { "zwg_per_unit": { "bid": 25.8731, "ask": 27.1999, "mid": 26.5365 }, ... },
    "ZAR": { "zwg_per_unit": { "bid": 1.5835, "ask": 1.6650, "mid": 1.6231 }, ... }
  },
  "source": { "url": "...RATES_5_NOVEMBER_2026.pdf", "sha256": "...", "retrieved_at": "..." }
}
```

Each currency also carries `usd_per_unit`, its `aliases` (ZMW/ZMK, MZN/MET),
a `verified` flag, and `as_published` with the raw figures exactly as RBZ printed them.

## Why the normalisation matters

The RBZ sheet is not consistent about direction. Row by row:

| Currency | USD column means | ZWG column means |
|---|---|---|
| GBP, EUR, AUD, XAU, BWP | USD per 1 unit | ZWG per 1 unit |
| CHF | units per 1 USD | ZWG per 1 unit |
| ZAR, JPY, NOK, CAD, CNY, ... | units per 1 USD | units per 1 ZWG |

The `*` marker in the PDF does not tell you which: CAD is starred but behaves
like ZAR; XAU and BWP are unstarred but behave like GBP. So the normaliser
works it out from the numbers: given the USD rate, only one of four
interpretations reproduces the published figure. A row where none fits is kept
as published, marked `"verified": false`, and listed under `warnings`.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[api,dev]"
python -m rbz_rates.pipeline update            # this month + last month
python -m rbz_rates.pipeline backfill --year 2026
python -m rbz_rates.pipeline recheck --days 30 # look for re-published PDFs further back
python -m rbz_rates.pipeline refetch           # re-download + re-parse every known day
uvicorn rbz_rates.api:app                      # optional HTTP API
pytest
```

API endpoints: `/v1/latest`, `/v1/rates/{date}` (falls back to the previous
business day), `/v1/currencies`, `/v1/history/{code}?from=&to=`,
`/v1/convert?amount=&from=&to=&date=`.

`/v1/convert` returns the `rate` and uses RBZ's printed figure for the pair:
the USD column for X/USD, the ZWG column for X/ZWG. RBZ prints no direct rate
for other pairs (e.g. GBP/ZAR), so those are crossed through USD, never ZWG.
`via` says which was used.

## Deploying the API (Cloudflare Workers, free plan)

`worker/` runs the same FastAPI app as a [Python Worker](https://developers.cloudflare.com/workers/languages/python/),
with `data/` deployed alongside it as static assets (read through the `ASSETS` binding).
Free plan: 100,000 requests/day, no card needed, Workers Logs on.

One-time setup:

1. Create a Cloudflare account, then an API token from the "Edit Cloudflare Workers" template.
2. Add repo secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
3. Run the `deploy` workflow once by hand (Actions tab). The API is then live at
   `https://rbz-rates.<your-subdomain>.workers.dev/docs`.

After that, every scrape that commits new data redeploys automatically, as does
any push that changes `rbz_rates/api.py` or `worker/`.

Run the Worker locally (needs uv >= 0.13.4 and Node):

```bash
cp rbz_rates/api.py worker/src/rbz_api.py      # the Worker bundles a copy; a test checks it is current
cd worker && uv sync && uv run pywrangler dev  # http://localhost:8787/docs
```

## How it works

```
RBZ listing page -> month article -> daily PDF links      (discover.py)
        |
        v
PDF bytes, in memory only                                   (fetch.py)
        |
        v
parse.py (layout detection) -> normalize.py                 (PDF discarded here)
        |
        v
data/daily/<date>.json, data/latest.json, data/index.json
```

`.github/workflows/scrape.yml` runs `update` hourly during Harare business
hours and commits new data. If RBZ changes the layout, the parser refuses to
guess: the error and source URL go to `data/failures/`, the workflow goes red,
and the day is retried on every run. Add a parser for the new layout in
`parse.py` (`PARSERS`) and run `refetch`.

RBZ's HTML pages sit behind bot protection (Radware), but the PDFs do not.
When the listing or month page is challenged, the pipeline falls back to
probing each weekday's predictable PDF URL; a 404 just means "not published"
(weekend, holiday, or not out yet).

### Corrections

RBZ sometimes fixes a day by re-uploading its PDF. Every `update` re-checks
the 5 most recent days (`--recheck N` to change) with a conditional request,
so an unchanged file costs a `304 Not Modified` and no download. If a PDF has
changed, the day is re-parsed and the previous version is listed in the day's
JSON under `revisions` (sha256, retrieved_at, last_modified); the field only
appears on days that have been revised. A revised PDF that fails to parse
leaves the existing data in place and turns the build red. The API picks up
revised days without a restart.

## Known limits

- Only the current ZWG layout is parsed. Older sheets (ZWL / RTGS$ era, 2019-2024)
  are recorded under `data/failures/` until their layouts are added.
- Legacy currencies (DEM, FRF, ITL, ESP, CYP) appear because RBZ still lists them.
- This is not an official RBZ service. Check the source PDF before relying on a
  figure for anything important.

## License

MIT for the code. The rates themselves are published by the Reserve Bank of Zimbabwe.
