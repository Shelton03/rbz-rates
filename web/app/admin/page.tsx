import { notFound } from "next/navigation";

import { ColumnChart } from "@/components/charts/ColumnChart";
import { StatTile } from "@/components/StatTile";
import { siteStats } from "@/lib/admin";
import { currentUser, isOwner } from "@/lib/auth";
import { compact, lastDays, shortDay } from "@/lib/days";

export const metadata = { title: "Site usage", robots: { index: false } };
export const dynamic = "force-dynamic";

export default async function Admin() {
  const user = await currentUser();
  if (!isOwner(user)) notFound(); // don't reveal the page exists

  let stats;
  try {
    stats = await siteStats(30);
  } catch (e) {
    console.error("stats failed", e);
    return <p className="mx-auto max-w-5xl px-4 py-10 text-sm">Couldn&apos;t load usage from the API.</p>;
  }

  const days = lastDays(30);
  const byDay = new Map(stats.by_day.map((d) => [d.day, d]));
  const rows = days.map((d) => ({
    x: d,
    label: shortDay(d),
    values: { keyed: byDay.get(d)?.keyed || 0, anonymous: byDay.get(d)?.anonymous || 0 },
  }));
  const total = stats.by_day.reduce((s, d) => s + d.keyed + d.anonymous, 0);
  const today = byDay.get(days[days.length - 1]);
  const maxEndpoint = Math.max(1, ...stats.by_endpoint.map((e) => e.count));

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10 sm:px-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Site usage</h1>
        <p className="text-sm text-muted-foreground">Every /v1 request, last 30 days (UTC). Visible only to owners.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Requests, 30 days" value={compact(total)} />
        <StatTile label="Requests today" value={compact((today?.keyed || 0) + (today?.anonymous || 0))}
          note={`${today?.callers || 0} distinct callers`} />
        <StatTile label="Accounts" value={compact(stats.users)} />
        <StatTile label="Active keys" value={compact(stats.active_keys)} />
      </div>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <div>
          <h2 className="font-semibold">Requests per day</h2>
          <p className="text-sm text-muted-foreground">With an API key vs anonymous.</p>
        </div>
        <ColumnChart
          title="API requests per day by access type, last 30 days"
          rows={rows}
          series={[
            { key: "keyed", name: "With key", color: "var(--series-1)" },
            { key: "anonymous", name: "No key", color: "var(--series-2)" },
          ]}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-4 rounded-xl border border-border bg-card p-6">
          <h2 className="font-semibold">By endpoint</h2>
          {stats.by_endpoint.length ? (
            <ul className="space-y-3">
              {stats.by_endpoint.map((e) => (
                <li key={e.endpoint} className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="font-mono text-xs">{e.endpoint}</span>
                    <span className="tnum text-muted-foreground">{e.count.toLocaleString("en-US")}</span>
                  </div>
                  <div className="h-2 rounded-r" style={{ width: `${(e.count / maxEndpoint) * 100}%`, background: "var(--series-1)", minWidth: 2 }} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No requests yet.</p>
          )}
        </section>

        <section className="space-y-4 rounded-xl border border-border bg-card p-6">
          <h2 className="font-semibold">Top keys</h2>
          {stats.top_keys.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr><th className="pb-2 font-medium">Account</th><th className="pb-2 font-medium">Key</th><th className="pb-2 text-right font-medium">Requests</th></tr>
              </thead>
              <tbody>
                {stats.top_keys.map((k) => (
                  <tr key={k.prefix} className="border-t border-border">
                    <td className="py-2">@{k.login}</td>
                    <td className="py-2"><span className="font-mono text-xs text-muted-foreground">{k.prefix}…</span> {k.name}</td>
                    <td className="tnum py-2 text-right">{k.count.toLocaleString("en-US")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">No key usage yet.</p>
          )}
        </section>
      </div>
    </div>
  );
}
