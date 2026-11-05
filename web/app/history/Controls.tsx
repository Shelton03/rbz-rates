"use client";

import { useRouter } from "next/navigation";

export function CurrencySelect({ codes, value, hrefFor }: { codes: { code: string; name: string }[]; value: string; hrefFor: Record<string, string> }) {
  const router = useRouter();
  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Currency</span>
      <select
        value={value}
        onChange={(e) => router.push(hrefFor[e.target.value])}
        className="h-9 rounded-md border border-border bg-card px-2 text-sm"
      >
        {codes.map((c) => (
          <option key={c.code} value={c.code}>{c.code}{c.name ? ` · ${c.name}` : ""}</option>
        ))}
      </select>
    </label>
  );
}

export function DayJump({ min, max, value }: { min: string; max: string; value?: string }) {
  const router = useRouter();
  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Go to a day</span>
      <input
        type="date" min={min} max={max} defaultValue={value}
        onChange={(e) => e.target.value && router.push(`/history/${e.target.value}`)}
        className="h-9 rounded-md border border-border bg-card px-2 text-sm"
      />
    </label>
  );
}
