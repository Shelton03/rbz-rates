import { CURRENCY_NAMES, formatRate } from "@/lib/currencies";
import type { Day } from "@/lib/rbz";

export function RatesTable({ day, codes }: { day: Day; codes: string[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full text-sm sm:min-w-[640px]">
        <caption className="sr-only">ZWG per 1 unit of each currency, {day.date}</caption>
        <thead className="border-b border-border bg-muted/60 text-left text-xs text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">Currency</th>
            <th className="px-4 py-3 text-right font-medium">Mid (ZWG)</th>
            <th className="hidden px-4 py-3 text-right font-medium sm:table-cell">Bid</th>
            <th className="hidden px-4 py-3 text-right font-medium sm:table-cell">Ask</th>
            <th className="hidden px-4 py-3 text-right font-medium sm:table-cell">Per 1 USD</th>
          </tr>
        </thead>
        <tbody>
          {codes.map((code) => {
            const r = day.rates[code];
            return (
              <tr key={code} className="border-b border-border last:border-0 hover:bg-muted/40">
                <td className="px-4 py-2.5">
                  <span className="font-mono font-medium">{code}</span>
                  {r.aliases.length > 0 && <span className="ml-1 font-mono text-xs text-muted-foreground">/{r.aliases.join("/")}</span>}
                  <span className="block text-xs text-muted-foreground sm:ml-3 sm:inline sm:text-sm">{CURRENCY_NAMES[code] ?? ""}</span>
                </td>
                <td className="tnum px-4 py-2.5 text-right font-medium">{formatRate(r.zwg_per_unit.mid)}</td>
                <td className="tnum hidden px-4 py-2.5 text-right text-muted-foreground sm:table-cell">{formatRate(r.zwg_per_unit.bid)}</td>
                <td className="tnum hidden px-4 py-2.5 text-right text-muted-foreground sm:table-cell">{formatRate(r.zwg_per_unit.ask)}</td>
                <td className="tnum hidden px-4 py-2.5 text-right text-muted-foreground sm:table-cell">{code === "USD" ? "1" : formatRate(1 / r.usd_per_unit.mid)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
