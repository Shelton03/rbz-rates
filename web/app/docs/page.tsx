import Link from "next/link";

import { CodeBlock } from "@/components/CommandSnippet";
import { API_URL } from "@/lib/rbz";

export const metadata = { title: "Docs" };

const NAV = [
  ["access", "Access & limits"],
  ["latest", "Latest rates"],
  ["rates", "Rates on a date"],
  ["convert", "Convert"],
  ["history", "History"],
  ["currencies", "Currencies"],
  ["fields", "Response fields"],
  ["errors", "Errors"],
  ["notes", "Data notes"],
];

export default function Docs() {
  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[13rem_1fr]">
      <nav aria-label="On this page" className="hidden lg:block">
        <ul className="sticky top-20 space-y-1 text-sm">
          {NAV.map(([id, label]) => (
            <li key={id}><a href={`#${id}`} className="block rounded-md px-2 py-1 text-muted-foreground hover:bg-muted hover:text-foreground">{label}</a></li>
          ))}
          <li className="pt-3"><a href={`${API_URL}/docs`} className="block px-2 text-accent hover:underline">Interactive reference →</a></li>
        </ul>
      </nav>

      <article className="min-w-0 space-y-12">
        <header className="space-y-3">
          <h1 className="text-3xl font-semibold tracking-tight">API documentation</h1>
          <p className="max-w-2xl text-muted-foreground">
            A read-only JSON API over the Reserve Bank of Zimbabwe&apos;s daily interbank rates. All endpoints are{" "}
            <code className="font-mono text-sm">GET</code>, return JSON, and allow cross-origin requests.
          </p>
          <CodeBlock title="Base URL" code={API_URL} />
        </header>

        <Section id="access" title="Access & limits">
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-xs text-muted-foreground">
                <tr><th className="px-4 py-2 font-medium">Access</th><th className="px-4 py-2 font-medium">Daily limit</th><th className="px-4 py-2 font-medium">How</th></tr>
              </thead>
              <tbody>
                <tr className="border-t border-border"><td className="px-4 py-2">No account</td><td className="tnum px-4 py-2">100 per visitor</td><td className="px-4 py-2">Just call it</td></tr>
                <tr className="border-t border-border"><td className="px-4 py-2">Free account</td><td className="tnum px-4 py-2">5,000 per key</td><td className="px-4 py-2"><Link href="/signin" className="text-accent hover:underline">Sign in with GitHub</Link>, create a key (up to 3)</td></tr>
              </tbody>
            </table>
          </div>
          <p>Send a key in either header (or, where headers aren&apos;t possible, as <code className="font-mono text-sm">?api_key=</code>):</p>
          <CodeBlock title="curl" code={`curl -H "Authorization: Bearer rbz_your_key" ${API_URL}/v1/latest\ncurl -H "X-API-Key: rbz_your_key" ${API_URL}/v1/latest`} />
          <p>
            Limits reset at 00:00 UTC. Every <code className="font-mono text-sm">/v1</code> response carries{" "}
            <code className="font-mono text-sm">X-RateLimit-Limit</code>, <code className="font-mono text-sm">X-RateLimit-Remaining</code> and{" "}
            <code className="font-mono text-sm">X-RateLimit-Reset</code>. Keep keys server-side: anything shipped to a browser can be copied.
          </p>
        </Section>

        <Endpoint id="latest" path="/v1/latest" title="Latest rates" desc="The most recently published day."
          example={`curl ${API_URL}/v1/latest`}
          response={`{
  "date": "2026-11-05",
  "base": "ZWG",
  "rates": {
    "USD": {
      "zwg_per_unit": { "bid": 25.8731, "ask": 27.1999, "mid": 26.5365 },
      "usd_per_unit": { "bid": 1.0, "ask": 1.0, "mid": 1.0 },
      "aliases": [],
      "verified": true,
      "as_published": { "starred": false, "index": {...}, "index_orientation": "units_per_usd", "zwg": {...}, "zwg_orientation": "zwg_per_unit" }
    },
    "ZAR": { "zwg_per_unit": { "bid": 1.5835, "ask": 1.665, "mid": 1.6231 }, ... },
    ...
  },
  "warnings": [],
  "source": { "url": "https://www.rbz.co.zw/documents/Exchange_Rates/2026/November/RATES_5_NOVEMBER_2026.pdf",
              "sha256": "72e1…", "retrieved_at": "2026-11-05T13:25:21+00:00" }
}`} />

        <Endpoint id="rates" path="/v1/rates/{date}" title="Rates on a date"
          desc="The rates in effect on a date (YYYY-MM-DD). RBZ publishes on business days only, so a weekend, holiday or not-yet-published date returns the most recent earlier day; check the date field. Dates before the first published day return 404."
          example={`curl ${API_URL}/v1/rates/2026-11-08   # a Sunday: returns 2026-11-05`} />

        <Endpoint id="convert" path="/v1/convert?amount=&from=&to=&date=" title="Convert"
          desc="Uses RBZ's own published figure for the pair: the USD column for X↔USD, the ZWG column for X↔ZWG. RBZ prints no direct rate for other pairs (e.g. GBP→ZAR), so those are crossed through USD. date is optional (latest by default); via says which figure was used."
          example={`curl "${API_URL}/v1/convert?amount=100&from=USD&to=ZAR"`}
          response={`{
  "date": "2026-11-05",
  "from": "USD", "to": "ZAR", "amount": 100.0,
  "rate": 16.3383,
  "result": 1633.83,
  "via": "direct (RBZ USD column)"
}`} />

        <Endpoint id="history" path="/v1/history/{code}?from=&to=" title="History"
          desc="ZWG per 1 unit (mid) for one currency on every published day in the range. to defaults to today. Aliases work (ZMK → ZMW)."
          example={`curl "${API_URL}/v1/history/USD?from=2026-10-01&to=2026-10-31"`}
          response={`{ "currency": "USD", "points": [ { "date": "2026-10-01", "zwg_per_unit": 26.7813 }, ... ] }`} />

        <Endpoint id="currencies" path="/v1/currencies" title="Currencies" desc="Codes in the latest sheet, with aliases."
          example={`curl ${API_URL}/v1/currencies`}
          response={`{ "USD": { "aliases": [] }, "ZMW": { "aliases": ["ZMK"] }, "MZN": { "aliases": ["MET"] }, ... }`} />

        <Section id="fields" title="Response fields">
          <dl className="divide-y divide-border rounded-lg border border-border text-sm">
            {[
              ["zwg_per_unit", "ZWG per 1 unit of the currency (bid, ask, mid). Always this direction, whatever RBZ printed."],
              ["usd_per_unit", "USD per 1 unit of the currency."],
              ["as_published", "The raw figures exactly as RBZ printed them, and which direction each column was in."],
              ["verified", "true when the row's figures agree with the USD rate (within 1%). false rows are kept as published and listed in warnings."],
              ["source", "The RBZ PDF the day came from, its sha256 and when it was fetched."],
              ["revisions", "Present only if RBZ re-published the day's PDF: the earlier versions' sha256 and timestamps."],
            ].map(([k, v]) => (
              <div key={k} className="grid gap-1 px-4 py-3 sm:grid-cols-[10rem_1fr]">
                <dt className="font-mono text-xs font-medium">{k}</dt><dd className="text-muted-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section id="errors" title="Errors">
          <p>Errors are JSON with a <code className="font-mono text-sm">detail</code> message.</p>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li><b className="text-foreground">400</b>: a malformed date or parameter.</li>
            <li><b className="text-foreground">401</b>: the API key is wrong or revoked.</li>
            <li><b className="text-foreground">404</b>: unknown currency, or no data on or before that date.</li>
            <li><b className="text-foreground">429</b>: daily limit reached; resets at 00:00 UTC.</li>
          </ul>
        </Section>

        <Section id="notes" title="Data notes">
          <ul className="list-disc space-y-2 pl-5 text-muted-foreground">
            <li>Rates appear within the hour RBZ publishes them, on business days (Harare time).</li>
            <li>If RBZ corrects a day by re-uploading its PDF, the new figures replace the old ones and the change is recorded under <code className="font-mono text-sm">revisions</code>.</li>
            <li>Legacy currencies (DEM, FRF, ITL, ESP) appear because RBZ still lists them.</li>
            <li>This is not an official RBZ service. Check the source PDF before relying on a figure.</li>
          </ul>
        </Section>
      </article>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

function Endpoint({ id, path, title, desc, example, response }: {
  id: string; path: string; title: string; desc: string; example: string; response?: string;
}) {
  return (
    <Section id={id} title={title}>
      <p className="font-mono text-sm"><span className="mr-2 font-semibold text-accent">GET</span>{path}</p>
      <p className="text-muted-foreground">{desc}</p>
      <CodeBlock title="Request" code={example} />
      {response && <CodeBlock title="Response" code={response} />}
    </Section>
  );
}
