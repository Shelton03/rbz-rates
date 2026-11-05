import { BadgeCheck, ChevronLeft, ChevronRight, FileText, Info, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CURRENCY_NAMES, FEATURED, formatDay, formatRate } from "@/lib/currencies";
import { getDay, getLatest, getSeries, perUnit } from "@/lib/rbz";

import { DayJump } from "../Controls";

export const revalidate = 900;

export async function generateMetadata({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  return { title: `Rates on ${date}` };
}

const longDay = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

export default async function DayPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(Date.parse(date))) notFound();

  const [day, latest, zwl, zwg] = await Promise.all([getDay(date), getLatest(), getSeries("USD", "ZWL"), getSeries("USD", "ZWG")]);
  if (!day) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-16 text-center sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">No sheet on or before {formatDay(date)}</h1>
        <p className="text-muted-foreground">History starts in February 2019.</p>
        <Link href="/history" className="font-medium text-accent hover:underline">Back to history</Link>
      </div>
    );
  }

  const dates = [...zwl, ...zwg].map((p) => p.date).sort();
  const i = dates.indexOf(day.date);
  const prev = i > 0 ? dates[i - 1] : undefined;
  const next = i >= 0 && i < dates.length - 1 ? dates[i + 1] : undefined;
  const base = day.base ?? "ZWG";
  const codes = [...FEATURED.filter((c) => c in day.rates), ...Object.keys(day.rates).filter((c) => !FEATURED.includes(c))];
  const verified = Object.values(day.rates).filter((r) => r.verified).length;
  const derived = Object.values(day.rates).filter((r) => r.derived_from).length;
  const total = codes.length;

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <nav className="flex flex-wrap items-center justify-between gap-3 text-sm" aria-label="Day navigation">
        <Link href="/history" className="text-muted-foreground hover:text-foreground">← History</Link>
        <div className="flex items-center gap-2">
          {prev ? <Link href={`/history/${prev}`} className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-3 py-1.5 hover:bg-muted"><ChevronLeft className="h-4 w-4" />{formatDay(prev)}</Link> : null}
          {next ? <Link href={`/history/${next}`} className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-3 py-1.5 hover:bg-muted">{formatDay(next)}<ChevronRight className="h-4 w-4" /></Link> : null}
        </div>
        <DayJump min="2019-02-01" max={latest?.date ?? ""} value={day.date} />
      </nav>

      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold tracking-tight">{longDay(day.date)}</h1>
          <span className="rounded-full border border-border px-2.5 py-0.5 font-mono text-xs">{base}</span>
        </div>
        {day.date !== date && (
          <p className="inline-flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 text-sm">
            <Info className="h-4 w-4" /> RBZ published no sheet for {longDay(date)} (weekend, holiday or not yet out). These are the rates in effect that day.
          </p>
        )}
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            {verified === total ? <BadgeCheck className="h-4 w-4 text-accent" /> : <TriangleAlert className="h-4 w-4" style={{ color: "var(--status-warning)" }} />}
            {verified} of {total} rows passed the consistency check{derived ? ` (${derived} derived from the USD column)` : ""}
          </span>
          <a href={day.source.url} className="inline-flex items-center gap-1 underline-offset-4 hover:text-foreground hover:underline"><FileText className="h-4 w-4" /> Source PDF</a>
          {day.revisions?.length ? <span>Re-published by RBZ {day.revisions.length}×</span> : null}
        </p>
        {base !== "ZWG" && (
          <p className="text-sm text-muted-foreground">
            Rates are in Zimbabwe dollars (ZWL), the currency before the ZiG. They can&apos;t be compared directly with ZWG rates.
          </p>
        )}
      </header>

      <div className="overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full min-w-[720px] text-sm">
          <caption className="sr-only">{base} per 1 unit of each currency on {day.date}</caption>
          <thead className="border-b border-border bg-muted/60 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Currency</th>
              <th className="px-4 py-3 text-right font-medium">Mid ({base})</th>
              <th className="px-4 py-3 text-right font-medium">Bid</th>
              <th className="px-4 py-3 text-right font-medium">Ask</th>
              <th className="px-4 py-3 text-right font-medium">Per 1 USD</th>
              <th className="px-4 py-3 font-medium">Check</th>
            </tr>
          </thead>
          <tbody>
            {codes.map((code) => {
              const r = day.rates[code];
              const q = perUnit(day, code);
              return (
                <tr key={code} className="border-b border-border last:border-0 hover:bg-muted/40">
                  <td className="px-4 py-2.5">
                    <Link href={`/history?code=${code}${base === "ZWL" ? "&era=ZWL" : ""}`} className="font-mono font-medium hover:underline">{code}</Link>
                    {r.aliases.length > 0 && <span className="ml-1 font-mono text-xs text-muted-foreground">/{r.aliases.join("/")}</span>}
                    <span className="ml-3 text-muted-foreground">{CURRENCY_NAMES[code] ?? ""}</span>
                  </td>
                  <td className="tnum px-4 py-2.5 text-right font-medium">{q ? formatRate(q.mid) : "–"}</td>
                  <td className="tnum px-4 py-2.5 text-right text-muted-foreground">{q ? formatRate(q.bid) : "–"}</td>
                  <td className="tnum px-4 py-2.5 text-right text-muted-foreground">{q ? formatRate(q.ask) : "–"}</td>
                  <td className="tnum px-4 py-2.5 text-right text-muted-foreground">{code === "USD" ? "1" : formatRate(1 / r.usd_per_unit.mid)}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">
                    {r.verified ? (r.derived_from ? "✓ derived" : "✓") : <span className="inline-flex items-center gap-1"><TriangleAlert className="h-3.5 w-3.5" style={{ color: "var(--status-warning)" }} />flagged</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {day.warnings.length > 0 && (
        <details className="rounded-xl border border-border bg-card p-4 text-sm">
          <summary className="cursor-pointer font-medium">Notes on this sheet ({day.warnings.length})</summary>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-muted-foreground">
            {day.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
