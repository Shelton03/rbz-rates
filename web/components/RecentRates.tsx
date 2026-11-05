import { ArrowDownRight, ArrowRight, ArrowUpRight, BadgeCheck, FileText, TriangleAlert } from "lucide-react";

import { CURRENCY_NAMES, formatRate } from "@/lib/currencies";
import type { Day } from "@/lib/rbz";

const dayLabel = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

/**
 * Mid rates for the latest published day and the days before it, side by side, with each
 * column linked to its RBZ source PDF, so readers can check the figures and see they move sensibly.
 */
export function RecentRates({ days, codes }: { days: Day[]; codes: string[] }) {
  const [latest, prev] = days;
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full text-sm sm:min-w-[680px]">
        <caption className="sr-only">ZWG per 1 unit, mid rate, for the last {days.length} published days</caption>
        <thead className="border-b border-border bg-muted/60 text-left text-xs text-muted-foreground">
          <tr>
            <th className="px-4 py-3 align-top font-medium">Currency</th>
            {days.map((d, i) => {
              const total = Object.keys(d.rates).length;
              const ok = Object.values(d.rates).filter((r) => r.verified).length;
              return (
                <th key={d.date} className={`px-4 py-3 text-right align-top font-medium ${i > 0 ? "hidden sm:table-cell" : ""}`}>
                  <span className={i === 0 ? "text-foreground" : ""}>{dayLabel(d.date)}</span>
                  {i === 0 && <span className="ml-1.5 rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent">latest</span>}
                  <span className="mt-1 flex items-center justify-end gap-2 font-normal">
                    <span className="inline-flex items-center gap-0.5" title={`${ok} of ${total} rows passed the consistency check`}>
                      {ok === total ? <BadgeCheck className="h-3.5 w-3.5 text-accent" /> : <TriangleAlert className="h-3.5 w-3.5" style={{ color: "var(--status-warning)" }} />}
                      {ok}/{total}
                    </span>
                    <a href={d.source.url} className="-my-1.5 inline-flex items-center gap-0.5 py-1.5 underline-offset-2 hover:text-foreground hover:underline" aria-label={`RBZ source PDF for ${d.date}`}>
                      <FileText className="h-3.5 w-3.5" /> PDF
                    </a>
                  </span>
                </th>
              );
            })}
            {prev && <th className="px-4 py-3 text-right align-top font-medium">Day change</th>}
          </tr>
        </thead>
        <tbody>
          {codes.map((code) => {
            const now = latest.rates[code]?.zwg_per_unit.mid;
            const before = prev?.rates[code]?.zwg_per_unit.mid;
            const change = now && before ? (now - before) / before : null;
            return (
              <tr key={code} className="border-b border-border last:border-0 hover:bg-muted/40">
                <td className="px-4 py-2.5">
                  <span className="font-mono font-medium">{code}</span>
                  <span className="ml-3 hidden text-muted-foreground sm:inline">{CURRENCY_NAMES[code] ?? ""}</span>
                </td>
                {days.map((d, i) => {
                  const v = d.rates[code]?.zwg_per_unit.mid;
                  return (
                    <td key={d.date} className={`tnum px-4 py-2.5 text-right ${i === 0 ? "font-medium" : "hidden text-muted-foreground sm:table-cell"}`}>
                      {v === undefined ? "–" : formatRate(v)}
                    </td>
                  );
                })}
                {prev && (
                  <td className="tnum px-4 py-2.5 text-right text-muted-foreground">
                    {change === null ? "–" : <Change value={change} />}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Direction by arrow and sign, not colour: a moving exchange rate is neither good nor bad. */
function Change({ value }: { value: number }) {
  const pct = (value * 100).toFixed(2);
  if (Math.abs(value) < 0.00005) return <span className="inline-flex items-center gap-1"><ArrowRight className="h-3.5 w-3.5" />0.00%</span>;
  const Icon = value > 0 ? ArrowUpRight : ArrowDownRight;
  return <span className="inline-flex items-center gap-1"><Icon className="h-3.5 w-3.5" />{value > 0 ? "+" : ""}{pct}%</span>;
}
