"use client";

import { useEffect, useRef, useState } from "react";

export type Series = { key: string; name: string; color: string };
export type Row = { x: string; label: string; values: Record<string, number> };

const MAX_BAR = 24; // px: bars never fill their slot
const GAP = 2; // px: surface gap between stacked segments and adjacent bars
const RADIUS = 4; // px: rounded data-end, square at the baseline
const M = { top: 12, right: 8, bottom: 28, left: 44 };

const fmt = (n: number) => n.toLocaleString("en-US");
const compact = (n: number) => (n >= 10_000 ? `${Math.round(n / 1000)}K` : fmt(n));

function niceMax(max: number, ticks = 4): { top: number; step: number } {
  if (max <= 0) return { top: ticks, step: 1 };
  const raw = max / ticks;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const s = step < 1 ? 1 : step;
  return { top: Math.ceil(max / s) * s, step: s };
}

/** Rect with rounded top corners only (square at the baseline). */
function topRounded(x: number, y: number, w: number, h: number, r: number) {
  r = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

/**
 * Columns over time, one series or stacked. Hover or focus a column for its values;
 * every value is also in the table view below the chart.
 */
export function ColumnChart({
  rows,
  series,
  height = 220,
  title,
  unit = "requests",
}: {
  rows: Row[];
  series: Series[];
  height?: number;
  title: string;
  unit?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    if (!box.current) return;
    setWidth(Math.max(280, box.current.getBoundingClientRect().width)); // measure now, not on the next frame
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const totals = rows.map((r) => series.reduce((s, se) => s + (r.values[se.key] || 0), 0));
  const { top, step } = niceMax(Math.max(0, ...totals));
  const innerW = width - M.left - M.right;
  const innerH = height - M.top - M.bottom;
  const band = innerW / Math.max(rows.length, 1);
  const barW = Math.max(2, Math.min(MAX_BAR, band - GAP));
  const y = (v: number) => M.top + innerH - (v / top) * innerH;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const labelEvery = Math.max(1, Math.ceil(rows.length / Math.max(2, Math.floor(innerW / 64))));
  const empty = totals.every((t) => t === 0);

  const tipRow = active === null ? null : rows[active];
  const tipX = active === null ? 0 : M.left + band * active + band / 2;

  return (
    <figure className="space-y-3">
      {series.length > 1 && (
        <ul className="flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Legend">
          {series.map((s) => (
            <li key={s.key} className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-[2px]" style={{ background: s.color }} />
              {s.name}
            </li>
          ))}
        </ul>
      )}
      <div ref={box} className="relative" onPointerLeave={() => setActive(null)}>
        <svg width={width} height={height} role="img" aria-label={title} className="block overflow-visible">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)}
                stroke={t === 0 ? "var(--viz-axis)" : "var(--viz-grid)"} strokeWidth={1} shapeRendering="crispEdges" />
              <text x={M.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="tnum fill-muted-foreground text-[11px]">
                {compact(t)}
              </text>
            </g>
          ))}
          {rows.map((r, i) => {
            const x = M.left + band * i + (band - barW) / 2;
            let base = 0;
            const nonZero = series.filter((s) => (r.values[s.key] || 0) > 0);
            const lastKey = nonZero[nonZero.length - 1]?.key;
            return (
              <g key={r.x} opacity={active === null || active === i ? 1 : 0.45} style={{ transition: "opacity 120ms" }}>
                {nonZero.map((s, k) => {
                  const v = r.values[s.key];
                  const yTop = y(base + v);
                  let yBottom = y(base);
                  base += v;
                  if (k > 0 && yBottom - yTop > GAP) yBottom -= GAP; // surface gap between segments
                  const h = Math.max(1, yBottom - yTop);
                  return s.key === lastKey ? (
                    <path key={s.key} d={topRounded(x, yTop, barW, h, RADIUS)} fill={s.color} />
                  ) : (
                    <rect key={s.key} x={x} y={yTop} width={barW} height={h} fill={s.color} />
                  );
                })}
                {i % labelEvery === 0 && (
                  <text x={x + barW / 2} y={height - 8} textAnchor="middle" className="fill-muted-foreground text-[11px]">
                    {r.label}
                  </text>
                )}
                {/* hit target: the whole column slot, larger than the mark */}
                <rect
                  x={M.left + band * i} y={M.top} width={band} height={innerH} fill="transparent"
                  tabIndex={0} role="button"
                  aria-label={`${r.label}: ${series.map((s) => `${s.name} ${fmt(r.values[s.key] || 0)}`).join(", ")}`}
                  onPointerEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
                  className="outline-none"
                />
              </g>
            );
          })}
        </svg>
        {empty && (
          <p className="pointer-events-none absolute inset-x-0 top-1/3 text-center text-sm text-muted-foreground">
            No {unit} in this period yet
          </p>
        )}
        {tipRow && (
          <div
            role="status"
            className="pointer-events-none absolute top-0 z-10 min-w-36 rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md"
            style={tipX > width - 170 ? { right: width - tipX + 10 } : { left: tipX + 10 }}
          >
            <p className="mb-1 text-muted-foreground">{tipRow.label}</p>
            {series.map((s) => (
              <p key={s.key} className="flex items-center gap-2">
                <span className="h-0.5 w-3 rounded-full" style={{ background: s.color }} />
                <strong className="tnum font-semibold text-foreground">{fmt(tipRow.values[s.key] || 0)}</strong>
                <span className="text-muted-foreground">{s.name}</span>
              </p>
            ))}
          </div>
        )}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">View as table</summary>
        <div className="mt-2 max-h-72 overflow-auto rounded-md border border-border">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">{title}</caption>
            <thead className="sticky top-0 bg-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Day</th>
                {series.map((s) => <th key={s.key} className="px-3 py-2 text-right font-medium">{s.name}</th>)}
                {series.length > 1 && <th className="px-3 py-2 text-right font-medium">Total</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.x} className="border-t border-border">
                  <td className="px-3 py-1.5">{r.x}</td>
                  {series.map((s) => <td key={s.key} className="tnum px-3 py-1.5 text-right">{fmt(r.values[s.key] || 0)}</td>)}
                  {series.length > 1 && <td className="tnum px-3 py-1.5 text-right">{fmt(totals[i])}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
