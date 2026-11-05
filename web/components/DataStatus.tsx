import { CircleCheck, Clock } from "lucide-react";

import type { Day } from "@/lib/rbz";

/** The business day whose sheet should be out by now (Harare, UTC+2; RBZ publishes around 08:00). */
function expectedDate(now = new Date()): string {
  const harare = new Date(now.getTime() + 2 * 3_600_000);
  const d = new Date(Date.UTC(harare.getUTCFullYear(), harare.getUTCMonth(), harare.getUTCDate()));
  if (harare.getUTCHours() < 10) d.setUTCDate(d.getUTCDate() - 1); // today's sheet not due yet
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function harareTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Africa/Harare",
  });
}

export function DataStatus({ latest }: { latest: Day }) {
  const current = latest.date >= expectedDate();
  const when = new Date(`${latest.date}T00:00:00Z`).toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
      {current ? (
        <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
          <CircleCheck className="h-4 w-4" style={{ color: "var(--status-good)" }} /> Up to date
        </span>
      ) : (
        <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
          <Clock className="h-4 w-4" style={{ color: "var(--status-warning)" }} /> Waiting for RBZ&apos;s next sheet
        </span>
      )}
      <span>Latest RBZ sheet: <span className="text-foreground">{when}</span></span>
      <span>Retrieved from RBZ {harareTime(latest.source.retrieved_at)} (Harare)</span>
    </p>
  );
}
