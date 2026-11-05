import { ArrowRight, BadgeCheck, Database, FileSearch, KeyRound, Scale, ServerCog, UserRound } from "lucide-react";
import Link from "next/link";

import { CommandSnippet } from "@/components/CommandSnippet";
import { DataStatus } from "@/components/DataStatus";
import { RecentRates } from "@/components/RecentRates";
import { Sparkline } from "@/components/charts/Sparkline";
import { FEATURED, formatDay, formatRate } from "@/lib/currencies";
import { API_URL, getHistory, getRecentDays } from "@/lib/rbz";

export const revalidate = 900;

const ANON_DAILY = 100;
const KEY_DAILY = 5000;

export default async function Home() {
  const [recent, usdHistory] = await Promise.all([getRecentDays(2), getHistory("USD", 45)]);
  const latest = recent[0] ?? null;
  const usd = latest?.rates.USD?.zwg_per_unit.mid;
  const codes = latest
    ? [...FEATURED.filter((c) => c in latest.rates), ...Object.keys(latest.rates).filter((c) => !FEATURED.includes(c))]
    : [];

  return (
    <>
      {/* hero */}
      <section className="border-b border-border">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1.25fr_1fr] lg:py-24">
          <div className="space-y-6">
            <p className="inline-flex flex-wrap items-center gap-2 rounded-full border border-border bg-card px-3 py-1 font-mono text-xs text-muted-foreground">
              Unofficial <span aria-hidden>·</span> Open source <span aria-hidden>·</span> Free
            </p>
            <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              Zimbabwe&apos;s interbank exchange rates, as an API
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground text-pretty">
              Every rate the Reserve Bank of Zimbabwe publishes each business day, read from its PDF, checked for
              consistency and served as clean JSON. Light use needs no signup.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href="/signin" className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90">
                Get a free API key <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/docs" className="inline-flex items-center rounded-md border border-border bg-card px-4 py-2.5 text-sm font-medium hover:bg-muted">
                Read the docs
              </Link>
            </div>
            <div className="max-w-xl">
              <CommandSnippet command={`curl ${API_URL}/v1/convert?amount=100&from=USD&to=ZWG`} />
            </div>
          </div>

          <div className="self-center rounded-xl border border-border bg-card p-6 shadow-sm">
            {latest && usd ? (
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">US dollar, interbank mid</p>
                  <p className="mt-1 text-5xl font-semibold tracking-tight">
                    {formatRate(usd)} <span className="text-2xl font-medium text-muted-foreground">ZWG</span>
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    per 1 USD · {formatDay(latest.date)}
                  </p>
                </div>
                <Sparkline
                  title="ZWG per US dollar, last 30 business days"
                  points={usdHistory.slice(-30).map((p) => ({ date: p.date, value: p.zwg_per_unit }))}
                />
                <a href={latest.source.url} className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
                  <FileSearch className="h-3.5 w-3.5" /> Source: RBZ PDF for {formatDay(latest.date)}
                </a>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Live rates are temporarily unavailable.</p>
            )}
          </div>
        </div>
      </section>

      {/* rates */}
      <section id="rates" className="scroll-mt-14 border-b border-border bg-muted/40">
        <div className="mx-auto max-w-6xl space-y-6 px-4 py-16 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="space-y-2">
              <h2 className="text-2xl font-semibold tracking-tight">Latest rates</h2>
              <p className="text-muted-foreground">
                The last {recent.length || 3} sheets RBZ published, side by side. ZWG per 1 unit, mid rate. Each column links to its source PDF.
              </p>
              {latest && <DataStatus latest={latest} />}
            </div>
            <Link href="/docs#latest" className="text-sm font-medium text-accent hover:underline">
              Get these as JSON →
            </Link>
          </div>
          {latest && (
            <>
              <RecentRates days={recent} codes={codes.slice(0, FEATURED.length)} />
              <Link href="/rates" className="inline-flex items-center gap-1 text-sm font-medium hover:underline">
                All {codes.length} currencies <ArrowRight className="h-4 w-4" />
              </Link>
            </>
          )}
        </div>
      </section>

      {/* access tiers */}
      <section className="border-b border-border">
        <div className="mx-auto max-w-6xl space-y-8 px-4 py-16 sm:px-6">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-semibold tracking-tight">Free either way</h2>
            <p className="mt-1 text-muted-foreground">Try it without an account. Sign in with GitHub when you need more.</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Tier
              icon={<UserRound className="h-5 w-5" />}
              name="No account"
              quota={`${ANON_DAILY} requests / day`}
              points={["No signup, no key", "Every endpoint", "Limit counted per visitor, resets 00:00 UTC"]}
            />
            <Tier
              icon={<KeyRound className="h-5 w-5" />}
              name="Free account"
              quota={`${KEY_DAILY.toLocaleString("en-US")} requests / day per key`}
              points={["Sign in with GitHub", "Up to 3 API keys, revoke any time", "Usage dashboard per key"]}
              cta={{ href: "/signin", label: "Get a key" }}
              highlight
            />
          </div>
        </div>
      </section>

      {/* how it works */}
      <section className="border-b border-border bg-muted/40">
        <div className="mx-auto max-w-6xl space-y-8 px-4 py-16 sm:px-6">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
            <p className="mt-1 text-muted-foreground">
              The RBZ sheet isn&apos;t consistent about which way each rate is quoted. Every row is normalised to one
              direction, and checked against the USD rate before it&apos;s published.
            </p>
          </div>
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Step n={1} icon={<FileSearch className="h-5 w-5" />} title="Fetch" body="Each business day's PDF is fetched from rbz.co.zw within the hour it appears." />
            <Step n={2} icon={<ServerCog className="h-5 w-5" />} title="Parse in memory" body="The PDF is read, parsed and discarded. Only the numbers and its sha256 are kept." />
            <Step n={3} icon={<Scale className="h-5 w-5" />} title="Verify" body="Each row's direction is worked out from the numbers. Rows that don't add up are flagged." />
            <Step n={4} icon={<Database className="h-5 w-5" />} title="Serve" body="Rates go out as JSON, with corrections picked up if RBZ re-publishes a day." />
          </ol>
        </div>
      </section>

      {/* endpoints */}
      <section>
        <div className="mx-auto max-w-6xl space-y-6 px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight">Endpoints</h2>
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card font-mono text-sm">
            {[
              ["/v1/latest", "Latest published rates"],
              ["/v1/rates/{date}", "Rates in effect on a date (falls back to the last business day)"],
              ["/v1/convert?amount=&from=&to=", "Convert using RBZ's published rate for the pair"],
              ["/v1/history/{code}?from=&to=", "Daily series for one currency"],
              ["/v1/currencies", "Currency codes and aliases"],
            ].map(([path, desc]) => (
              <li key={path} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:gap-6">
                <span className="w-12 shrink-0 text-xs font-semibold text-accent">GET</span>
                <span className="min-w-0 sm:w-80">{path}</span>
                <span className="font-sans text-muted-foreground">{desc}</span>
              </li>
            ))}
          </ul>
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <BadgeCheck className="h-4 w-4 text-accent" />
            Full reference, parameters and examples in the{" "}
            <Link href="/docs" className="font-medium text-foreground underline-offset-4 hover:underline">docs</Link>.
          </p>
        </div>
      </section>
    </>
  );
}

function Tier({ icon, name, quota, points, cta, highlight }: {
  icon: React.ReactNode; name: string; quota: string; points: string[]; cta?: { href: string; label: string }; highlight?: boolean;
}) {
  return (
    <div className={`flex flex-col rounded-xl border bg-card p-6 ${highlight ? "border-accent/60 shadow-sm" : "border-border"}`}>
      <div className="flex items-center gap-2 text-muted-foreground">{icon}<span className="font-medium text-foreground">{name}</span></div>
      <p className="mt-4 text-2xl font-semibold tracking-tight">{quota}</p>
      <ul className="mt-4 flex-1 space-y-2 text-sm text-muted-foreground">
        {points.map((p) => (
          <li key={p} className="flex gap-2"><span className="text-accent" aria-hidden>✓</span>{p}</li>
        ))}
      </ul>
      {cta && (
        <Link href={cta.href} className="mt-6 inline-flex w-fit items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">
          {cta.label} <ArrowRight className="h-4 w-4" />
        </Link>
      )}
    </div>
  );
}

function Step({ n, icon, title, body }: { n: number; icon: React.ReactNode; title: string; body: string }) {
  return (
    <li className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between text-muted-foreground">
        {icon}
        <span className="font-mono text-xs">0{n}</span>
      </div>
      <p className="mt-4 font-medium">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </li>
  );
}
