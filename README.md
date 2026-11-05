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

## Access: API keys and limits

| Access | Limit | How |
|---|---|---|
| No account | 100 requests/day per caller | just call it |
| Free account | 5,000 requests/day per key, up to 3 keys | sign in on the website with GitHub |

Keys go in `Authorization: Bearer <key>` or `X-API-Key`. Every `/v1` response has
`X-RateLimit-Limit` / `-Remaining` / `-Reset`. Only a SHA-256 hash of each key is stored;
anonymous callers are counted by a daily-rotating salted hash of their IP, never the IP itself.
Accounts, keys and per-day usage counts live in Cloudflare D1 (`worker/migrations/`),
handled by `rbz_rates/access.py`.

## Deploying (all free plans)

| Piece | Where | Folder |
|---|---|---|
| Scraper | GitHub Actions, hourly on business days | `rbz_rates/`, `.github/workflows/scrape.yml` |
| API + keys + usage | Cloudflare Workers (Python) + D1 | `worker/` |
| Website, sign-in, dashboard | Vercel (Next.js) | `web/` |

**1. API (Cloudflare).** Create an API token (template "Edit Cloudflare Workers", plus
**D1: Edit**), then add repo secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
`RBZ_ADMIN_SECRET` and `RBZ_ANON_SALT` (two long random strings: `openssl rand -base64 32`).
Run the `deploy` workflow. Its first run creates the D1 database; every run applies
migrations, deploys, and sets the Worker's secrets. Live at
`https://rbz-rates.<your-subdomain>.workers.dev/docs`. If the website's address isn't
`https://rbz-rates.vercel.app`, change `SITE_URL` in `worker/wrangler.jsonc`.

**2. GitHub sign-in.** Create an OAuth App at github.com/settings/developers with callback
`https://<your-site>.vercel.app/api/auth/callback/github`.

**3. Website (Vercel).** Import the repo, set **Root Directory** to `web`, and add the
environment variables listed in `web/.env.example` (`RBZ_ADMIN_SECRET` must equal the repo
secret of the same name). `OWNER_GITHUB_IDS` (your id: `gh api user --jq .id`) unlocks
`/admin`, the site-wide usage page.

After that, scrapes that commit new data redeploy the API, and pushes to `main` redeploy
the website.

### Running locally

```bash
worker/sync.sh                                        # copy the API modules into the Worker bundle
cd worker && uv sync
printf 'ADMIN_SECRET=dev\nANON_SALT=dev\n' > .dev.vars
npx wrangler d1 migrations apply rbz-rates --local
uv run pywrangler dev                                 # API on http://localhost:8787 (needs uv >= 0.13.4)

cd ../web && cp .env.example .env.local               # set RBZ_API_URL=http://localhost:8787, RBZ_ADMIN_SECRET=dev,
npm install && npm run dev                            # DEV_FAKE_USER=1:you to skip GitHub sign-in locally
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
