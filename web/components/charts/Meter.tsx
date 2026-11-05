import { AlertTriangle, OctagonX } from "lucide-react";

/** Usage against a limit. Fill: accent, then warning from 80%, critical at the limit (always with icon + label). */
export function Meter({ value, limit, label }: { value: number; limit: number; label: string }) {
  const share = Math.min(1, value / limit);
  const state = value >= limit ? "critical" : share >= 0.8 ? "warning" : "ok";
  const fill = state === "critical" ? "var(--status-critical)" : state === "warning" ? "var(--status-warning)" : "var(--series-1)";
  return (
    <div className="space-y-1.5">
      <div
        className="h-2 overflow-hidden rounded-full" style={{ background: "var(--meter-track)" }}
        role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={limit} aria-valuenow={value}
      >
        <div className="h-full rounded-full" style={{ width: `${share * 100}%`, background: fill }} />
      </div>
      <p className="tnum flex items-center gap-1.5 text-xs text-muted-foreground">
        {state === "critical" && <OctagonX className="h-3.5 w-3.5" style={{ color: "var(--status-critical)" }} />}
        {state === "warning" && <AlertTriangle className="h-3.5 w-3.5" style={{ color: "var(--status-warning)" }} />}
        <span>
          <strong className="font-medium text-foreground">{value.toLocaleString("en-US")}</strong> of{" "}
          {limit.toLocaleString("en-US")} today
          {state === "critical" ? " · limit reached" : state === "warning" ? " · near limit" : ""}
        </span>
      </p>
    </div>
  );
}
