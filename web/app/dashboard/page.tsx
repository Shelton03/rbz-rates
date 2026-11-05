import { BarChart3, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { CodeBlock } from "@/components/CommandSnippet";
import { ColumnChart } from "@/components/charts/ColumnChart";
import { Meter } from "@/components/charts/Meter";
import { StatTile } from "@/components/StatTile";
import { listKeys, userUsage } from "@/lib/admin";
import { currentUser, isOwner } from "@/lib/auth";
import { compact, lastDays, shortDay } from "@/lib/days";
import { formatDay } from "@/lib/currencies";
import { API_URL } from "@/lib/rbz";

import { CreateKey } from "./KeyManager";
import { RevokeButton } from "./RevokeButton";

export const metadata = { title: "Dashboard" };
export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const user = await currentUser();
  if (!user) redirect("/signin?callbackUrl=/dashboard");

  let data;
  try {
    const [keys, usage] = await Promise.all([listKeys(user.id), userUsage(user.id, 30)]);
    data = { ...keys, usage: usage.rows };
  } catch (e) {
    console.error("dashboard load failed", e);
    return (
      <Shell login={user.login} owner={isOwner(user)}>
        <p role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 p-6 text-sm">
          Couldn&apos;t reach the API to load your keys. Please try again in a minute.
        </p>
      </Shell>
    );
  }

  const active = data.keys.filter((k) => !k.revoked_at);
  const revoked = data.keys.filter((k) => k.revoked_at);
  const days = lastDays(30);
  const perDay = new Map<string, number>();
  for (const r of data.usage) perDay.set(r.day, (perDay.get(r.day) || 0) + r.count);
  const rows = days.map((d) => ({ x: d, label: shortDay(d), values: { total: perDay.get(d) || 0 } }));
  const today = perDay.get(days[days.length - 1]) || 0;
  const month = [...perDay.values()].reduce((a, b) => a + b, 0);
  const exampleKey = active[0] ? `${active[0].prefix}…` : "rbz_your_key";

  return (
    <Shell login={user.login} owner={isOwner(user)}>
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label="Requests today" value={compact(today)} note="All your keys, UTC day" />
        <StatTile label="Last 30 days" value={compact(month)} />
        <StatTile label="Active keys" value={`${active.length} of ${data.max_keys}`} note={`${data.limit_per_key.toLocaleString("en-US")} requests/day each`} />
      </div>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <div>
          <h2 className="font-semibold">API keys</h2>
          <p className="text-sm text-muted-foreground">Send a key as <code className="font-mono text-xs">Authorization: Bearer &lt;key&gt;</code> or <code className="font-mono text-xs">X-API-Key</code>.</p>
        </div>
        <CreateKey disabled={active.length >= data.max_keys} />
        {active.length >= data.max_keys && (
          <p className="text-sm text-muted-foreground">You&apos;re at the limit of {data.max_keys} keys. Revoke one to create another.</p>
        )}
        {active.length > 0 ? (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {active.map((k) => (
              <li key={k.id} className="grid gap-3 p-4 sm:grid-cols-[1fr_14rem_auto] sm:items-center sm:gap-6">
                <div className="min-w-0">
                  <p className="font-medium">{k.name}</p>
                  <p className="font-mono text-xs text-muted-foreground">{k.prefix}…</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Created {formatDay(k.created_at.slice(0, 10))} · {k.last_used ? `last used ${formatDay(k.last_used)}` : "never used"}
                  </p>
                </div>
                <Meter value={k.today} limit={data.limit_per_key} label={`${k.name}: requests today`} />
                <RevokeButton id={k.id} name={k.name} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No keys yet. Create one above.</p>
        )}
        {revoked.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Revoked keys ({revoked.length})</summary>
            <ul className="mt-2 space-y-1 text-muted-foreground">
              {revoked.map((k) => (
                <li key={k.id}><span className="font-mono text-xs">{k.prefix}…</span> {k.name}, revoked {formatDay(k.revoked_at!.slice(0, 10))}</li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <div>
          <h2 className="flex items-center gap-2 font-semibold"><BarChart3 className="h-4 w-4" /> Requests per day</h2>
          <p className="text-sm text-muted-foreground">All your keys, last 30 days (UTC).</p>
        </div>
        <ColumnChart title="Your API requests per day, last 30 days" rows={rows} series={[{ key: "total", name: "Requests", color: "var(--series-1)" }]} />
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Quick start</h2>
        <CodeBlock
          title="curl"
          code={`curl -H "Authorization: Bearer ${exampleKey}" \\\n  "${API_URL}/v1/convert?amount=100&from=USD&to=ZWG"`}
        />
      </section>
    </Shell>
  );
}

function Shell({ login, owner, children }: { login: string; owner: boolean; children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Signed in as <span className="font-medium text-foreground">@{login}</span></p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          {owner && (
            <Link href="/admin" className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 hover:bg-muted">
              <ShieldCheck className="h-4 w-4" /> Site usage
            </Link>
          )}
          <a href="/api/auth/signout" className="rounded-md px-3 py-1.5 text-muted-foreground hover:text-foreground">Sign out</a>
        </div>
      </div>
      {children}
    </div>
  );
}
