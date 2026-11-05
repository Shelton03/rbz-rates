"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export type LinePoint = { date: string; value: number };

const M = { top: 12, right: 12, bottom: 28, left: 64 };

const day = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function fmt(v: number, digits: number) {
  return v.toLocaleString("en-US", { minimumFractionDigits: Math.min(digits, 2), maximumFractionDigits: digits });
}

function axisLabel(v: number) {
  if (v >= 10_000) return `${Math.round(v / 1000).toLocaleString("en-US")}K`;
  if (v >= 100) return Math.round(v).toLocaleString("en-US");
  return v.toLocaleString("en-US", { maximumFractionDigits: v < 1 ? 4 : 2 });
}

function niceTicks(min: number, max: number, count = 5): number[] {
  if (max <= min) return [min];
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}

function logTicks(min: number, max: number): number[] {
  const out: number[] = [];
  for (let e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e++) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** e;
      if (v >= min && v <= max) out.push(v);
    }
  }
  return out.length >= 2 ? out : niceTicks(min, max);
}

/**
 * One series over time. The crosshair snaps to the nearest published day; arrow keys step
 * day by day; clicking (or Enter) opens that day's full sheet. Every value is in the table view.
 */
export function LineChart({
  points,
  title,
  unit,
  digits = 4,
  log = false,
  height = 320,
  dayHrefPrefix,
}: {
  points: LinePoint[];
  title: string;
  unit: string;
  digits?: number;
  log?: boolean;
  height?: number;
  /** e.g. "/history/": clicking a day opens `${dayHrefPrefix}${date}` (a string, so it can come from a server component) */
  dayHrefPrefix?: string;
}) {
  const dayHref = dayHrefPrefix ? (date: string) => `${dayHrefPrefix}${date}` : undefined;
  const router = useRouter();
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    if (!box.current) return;
    setWidth(Math.max(300, box.current.getBoundingClientRect().width));
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(300, e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  if (points.length < 2) {
    return <p className="py-16 text-center text-sm text-muted-foreground">Not enough published days in this range.</p>;
  }

  const t = points.map((p) => Date.parse(`${p.date}T00:00:00Z`));
  const values = points.map((p) => p.value);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const useLog = log && lo > 0;
  const pad = useLog ? 0 : (hi - lo) * 0.08 || hi * 0.05;
  const yMin = useLog ? lo * 0.9 : Math.max(0, lo - pad);
  const yMax = useLog ? hi * 1.1 : hi + pad;
  const innerW = width - M.left - M.right;
  const innerH = height - M.top - M.bottom;
  const x = (ms: number) => M.left + ((ms - t[0]) / (t[t.length - 1] - t[0] || 1)) * innerW;
  const y = useLog
    ? (v: number) => M.top + innerH - ((Math.log(v) - Math.log(yMin)) / (Math.log(yMax) - Math.log(yMin))) * innerH
    : (v: number) => M.top + innerH - ((v - yMin) / (yMax - yMin)) * innerH;
  const yTicks = (useLog ? logTicks(yMin, yMax) : niceTicks(yMin, yMax)).filter((v) => v >= yMin && v <= yMax);

  // x ticks: about one per 110px, on month or year boundaries
  const spanDays = (t[t.length - 1] - t[0]) / 86_400_000;
  const want = Math.max(2, Math.floor(innerW / 110));
  const monthsStep = [1, 2, 3, 6, 12, 24].find((m) => (spanDays / 30.4) / m <= want) ?? 24;
  const xTicks: number[] = [];
  const start = new Date(t[0]);
  for (let d = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1)); d.getTime() <= t[t.length - 1];
    d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + monthsStep, 1))) {
    if (monthsStep < 12 || d.getUTCMonth() === 0) xTicks.push(d.getTime());
  }
  const xLabel = (ms: number) =>
    new Date(ms).toLocaleDateString("en-GB", monthsStep >= 12 ? { year: "numeric", timeZone: "UTC" } : { month: "short", year: "2-digit", timeZone: "UTC" });

  const line = points.map((p, i) => `${i ? "L" : "M"}${x(t[i]).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const area = `${line}L${x(t[t.length - 1]).toFixed(1)},${M.top + innerH}L${x(t[0]).toFixed(1)},${M.top + innerH}Z`;

  function nearest(clientX: number, rect: DOMRect) {
    const ms = t[0] + ((clientX - rect.left - M.left) / innerW) * (t[t.length - 1] - t[0]);
    let a = 0, b = t.length - 1;
    while (b - a > 1) {
      const m = (a + b) >> 1;
      if (t[m] < ms) a = m; else b = m;
    }
    return Math.abs(t[a] - ms) <= Math.abs(t[b] - ms) ? a : b;
  }

  const shown = active ?? points.length - 1;
  const ax = x(t[shown]);

  return (
    <figure className="space-y-3">
      <div ref={box} className="relative">
        <svg
          width={width} height={height} role="img" aria-label={title} tabIndex={0}
          className="block cursor-crosshair touch-none outline-none"
          onPointerMove={(e) => setActive(nearest(e.clientX, e.currentTarget.getBoundingClientRect()))}
          onPointerLeave={() => setActive(null)}
          onClick={() => active !== null && dayHref && router.push(dayHref(points[active].date))}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
              e.preventDefault();
              const step = e.shiftKey ? 20 : 1;
              setActive((i) => Math.max(0, Math.min(points.length - 1, (i ?? points.length - 1) + (e.key === "ArrowLeft" ? -step : step))));
            } else if (e.key === "Enter" && dayHref) {
              router.push(dayHref(points[shown].date));
            }
          }}
        >
          {yTicks.map((v) => (
            <g key={v}>
              <line x1={M.left} x2={width - M.right} y1={y(v)} y2={y(v)} stroke="var(--viz-grid)" strokeWidth={1} shapeRendering="crispEdges" />
              <text x={M.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="tnum fill-muted-foreground text-[11px]">{axisLabel(v)}</text>
            </g>
          ))}
          <line x1={M.left} x2={width - M.right} y1={M.top + innerH} y2={M.top + innerH} stroke="var(--viz-axis)" strokeWidth={1} shapeRendering="crispEdges" />
          {xTicks.map((ms) => (
            <text key={ms} x={x(ms)} y={height - 8} textAnchor="middle" className="fill-muted-foreground text-[11px]">{xLabel(ms)}</text>
          ))}
          <path d={area} fill="var(--series-1)" fillOpacity={0.1} />
          <path d={line} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {active !== null && <line x1={ax} x2={ax} y1={M.top} y2={M.top + innerH} stroke="var(--viz-axis)" strokeWidth={1} />}
          <circle cx={ax} cy={y(points[shown].value)} r={4.5} fill="var(--series-1)" stroke="var(--card)" strokeWidth={2} />
        </svg>
        <div
          role="status" aria-live="polite"
          className="pointer-events-none absolute top-0 z-10 rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md"
          style={ax > width - 190 ? { right: width - ax + 10 } : { left: ax + 10 }}
        >
          <p className="text-muted-foreground">{day(points[shown].date)}</p>
          <p className="flex items-center gap-2">
            <span className="h-0.5 w-3 rounded-full" style={{ background: "var(--series-1)" }} />
            <strong className="tnum text-sm font-semibold">{fmt(points[shown].value, digits)}</strong>
            <span className="text-muted-foreground">{unit}</span>
          </p>
          {dayHref && <p className="mt-0.5 text-[11px] text-muted-foreground">{active === null ? "Latest · hover to explore" : "Click for that day's sheet"}</p>}
        </div>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer py-1.5 text-muted-foreground hover:text-foreground">View as table ({points.length} days)</summary>
        <div className="mt-2 max-h-80 overflow-auto rounded-md border border-border">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">{title}</caption>
            <thead className="sticky top-0 bg-muted">
              <tr><th className="px-3 py-2 font-medium">Day</th><th className="px-3 py-2 text-right font-medium">{unit}</th></tr>
            </thead>
            <tbody>
              {[...points].reverse().map((p) => (
                <tr key={p.date} className="border-t border-border">
                  <td className="px-3 py-1.5">{dayHref ? <a href={dayHref(p.date)} className="hover:underline">{p.date}</a> : p.date}</td>
                  <td className="tnum px-3 py-1.5 text-right">{fmt(p.value, digits)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
