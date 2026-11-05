"use client";

import { useEffect, useRef, useState } from "react";

type P = { date: string; value: number };

/** Trend line: de-emphasised line, latest point in the accent; hover shows any day's value. */
export function Sparkline({ points, title, digits = 4 }: { points: P[]; title: string; digits?: number }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(320);
  const [active, setActive] = useState<number | null>(null);
  const height = 64;
  const pad = { x: 6, y: 8 };

  useEffect(() => {
    if (!box.current) return;
    setWidth(Math.max(160, box.current.getBoundingClientRect().width)); // measure now, not on the next frame
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(160, e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  if (points.length < 2) return null;
  const vals = points.map((p) => p.value);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i: number) => pad.x + (i / (points.length - 1)) * (width - 2 * pad.x);
  const y = (v: number) => pad.y + (1 - (v - min) / span) * (height - 2 * pad.y);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const last = points.length - 1;
  const shown = active ?? last;

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - pad.x) / (width - 2 * pad.x)) * (points.length - 1));
    setActive(Math.max(0, Math.min(last, i)));
  }

  return (
    <div ref={box} className="relative">
      <svg
        width={width} height={height} role="img" aria-label={title} className="block cursor-crosshair touch-none"
        onPointerMove={onMove} onPointerLeave={() => setActive(null)}
      >
        <path d={d} fill="none" stroke="var(--muted-foreground)" strokeOpacity={0.6} strokeWidth={2}
          strokeLinejoin="round" strokeLinecap="round" />
        {active !== null && (
          <line x1={x(active)} x2={x(active)} y1={0} y2={height} stroke="var(--viz-axis)" strokeWidth={1} />
        )}
        <circle cx={x(shown)} cy={y(points[shown].value)} r={4.5} fill="var(--series-1)" stroke="var(--card)" strokeWidth={2} />
      </svg>
      <p className="tnum mt-1 flex justify-between text-xs text-muted-foreground" aria-live="polite">
        <span>{new Date(`${points[shown].date}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}</span>
        <span className="font-medium text-foreground">{points[shown].value.toFixed(digits)}</span>
      </p>
      <table className="sr-only">
        <caption>{title}</caption>
        <tbody>
          {points.map((p) => (
            <tr key={p.date}><td>{p.date}</td><td>{p.value}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
