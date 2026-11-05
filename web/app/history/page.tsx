import { CalendarDays } from "lucide-react";
import Link from "next/link";

import { LineChart } from "@/components/charts/LineChart";
import { StatTile } from "@/components/StatTile";
import { CURRENCY_NAMES, FEATURED, formatDay, formatRate } from "@/lib/currencies";
import { ERAS, type Era, getLatest, getSeries } from "@/lib/rbz";

import { CurrencySelect, DayJump } from "./Controls";

export const metadata = { title: "History", description: "Every RBZ interbank rate since February 2019, day by day." };
export const revalidate = 900;

const RANGES = { "1m": 31, "6m": 183, "1y": 366, "5y": 1827, all: Infinity } as const;
type Range = keyof typeof RANGES;

export default async function History({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = await searchParams;
  const era: Era = q.era === "ZWL" ? "ZWL" : "ZWG";
  const range: Range = (q.range && q.range in RANGES ? q.range : "all") as Range;
  const log = q.scale === "log";
  const latest = await getLatest();
  const all = latest ? Object.keys(latest.rates) : FEATURED;
  const codes = [...FEATURED.filter((c) => all.includes(c)), ...all.filter((c) => !FEATURED.includes(c)).sort()];
  const code = (q.code ?? "USD").toUpperCase();
  const series = await getSeries(code, era);

  const last = series.at(-1)?.date;
  const cutoff = last && RANGES[range] !== Infinity
    ? new Date(Date.parse(`${last}T00:00:00Z`) - RANGES[range] * 86_400_000).toISOString().slice(0, 10)
    : "";
  const points = series.filter((p) => p.date >= cutoff);
  const first = points[0];
  const end = points.at(-1);
  const change = first && end ? (end.value - first.value) / first.value : null;
  const hi = points.reduce((m, p) => (p.value > m.value ? p : m), points[0] ?? { date: "", value: 0 });
  const lo = points.reduce((m, p) => (p.value < m.value ? p : m), points[0] ?? { date: "", value: 0 });

  const href = (over: Record<string, string | undefined>) => {
    const params = new URLSearchParams(Object.entries({ code, era, range, scale: log ? "log" : undefined, ...over })
      .filter((e): e is [string, string] => !!e[1] && !(e[0] === "code" && e[1] === "USD") && !(e[0] === "era" && e[1] === "ZWG") && !(e[0] === "range" && e[1] === "all")));
    const s = params.toString();
    return `/history${s ? `?${s}` : ""}`;
  };
  const unit = `${era} per ${code}`;

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">History</h1>
          <p className="mt-1 text-muted-foreground">Every RBZ interbank rate since February 2019. Click the chart to open any day&apos;s full sheet.</p>
        </div>
        <DayJump min="2019-02-01" max={latest?.date ?? ""} />
      </div>

      {/* filters: one row, above everything they scope */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-border bg-card p-3">
        <CurrencySelect
          value={code}
          codes={codes.map((c) => ({ code: c, name: CURRENCY_NAMES[c] ?? "" }))}
          hrefFor={Object.fromEntries(codes.map((c) => [c, href({ code: c })]))}
        />
        <Segmented label="Currency era" items={(Object.keys(ERAS) as Era[]).map((e) => ({ key: e, label: ERAS[e].label, href: href({ era: e }) }))} active={era} />
        <Segmented label="Range" items={(Object.keys(RANGES) as Range[]).map((r) => ({ key: r, label: r.toUpperCase(), href: href({ range: r }) }))} active={range} />
        <Segmented label="Scale" items={[{ key: "linear", label: "Linear", href: href({ scale: undefined }) }, { key: "log", label: "Log", href: href({ scale: "log" }) }]} active={log ? "log" : "linear"} />
      </div>

      {series.length === 0 ? (
        <p className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
          No {era} history for {code}. {era === "ZWG" ? "Try the ZWL era." : "Try the ZWG era."}
        </p>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label={`Latest, ${formatDay(end!.date)}`} value={formatRate(end!.value)} note={unit} />
            <StatTile label="Change over range" value={change === null ? "–" : `${change > 0 ? "+" : ""}${(change * 100).toFixed(2)}%`} note={`since ${formatDay(first!.date)}`} />
            <StatTile label="Range high" value={formatRate(hi.value)} note={formatDay(hi.date)} />
            <StatTile label="Range low" value={formatRate(lo.value)} note={formatDay(lo.date)} />
          </div>
          <section className="space-y-3 rounded-xl border border-border bg-card p-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-semibold">{unit}, mid rate</h2>
              <p className="text-xs text-muted-foreground">{ERAS[era].note} · {points.length} published days</p>
            </div>
            <LineChart
              points={points}
              title={`${unit}, mid rate, ${formatDay(first!.date)} to ${formatDay(end!.date)}`}
              unit={unit}
              digits={end!.value >= 1000 ? 2 : 4}
              log={log}
              dayHref={(d) => `/history/${d}`}
            />
          </section>
        </>
      )}

      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <CalendarDays className="h-4 w-4" />
        ZWL and ZWG are different currencies, so each has its own chart. The ZiG replaced the Zimbabwe dollar on 5 April 2024.{" "}
        <Link href="/docs#zwl" className="font-medium text-foreground underline-offset-4 hover:underline">More</Link>
      </p>
    </div>
  );
}

function Segmented({ label, items, active }: { label: string; items: { key: string; label: string; href: string }[]; active: string }) {
  return (
    <nav aria-label={label} className="inline-flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="inline-flex rounded-md border border-border p-0.5">
        {items.map((i) => (
          <Link key={i.key} href={i.href} aria-current={i.key === active ? "true" : undefined}
            className={`rounded px-2.5 py-1 text-xs font-medium ${i.key === active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
            {i.label}
          </Link>
        ))}
      </span>
    </nav>
  );
}
