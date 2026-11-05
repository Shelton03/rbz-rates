import "server-only";

export const API_URL = (process.env.RBZ_API_URL || "https://rbz-rates.sheltonmutambirwa.workers.dev").replace(/\/$/, "");

export type Quote = { bid: number; ask: number; mid: number };
export type Rate = {
  zwg_per_unit: Quote;
  usd_per_unit: Quote;
  aliases: string[];
  verified: boolean;
};
export type Day = {
  date: string;
  rates: Record<string, Rate>;
  source: { url: string; sha256?: string; retrieved_at: string };
  warnings: string[];
};
export type Point = { date: string; zwg_per_unit: number };

/** Public API call from the server, cached for 15 minutes (the scraper checks RBZ hourly). */
async function get<T>(path: string): Promise<T | null> {
  try {
    const headers: Record<string, string> = {};
    if (process.env.RBZ_API_KEY) headers.Authorization = `Bearer ${process.env.RBZ_API_KEY}`;
    const res = await fetch(`${API_URL}${path}`, { headers, next: { revalidate: 900 } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // API down or not deployed yet: pages render without live data
  }
}

export const getLatest = () => get<Day>("/v1/latest");

export async function getHistory(code: string, days: number): Promise<Point[]> {
  const from = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
  const res = await get<{ points: Point[] }>(`/v1/history/${code}?from=${from}`);
  return res?.points ?? [];
}

/**
 * The latest published day plus the `extra` business days before it, newest first.
 * Uses the USD history to find which dates were published, then fetches each day.
 */
export async function getRecentDays(extra = 2): Promise<Day[]> {
  const latest = await getLatest();
  if (!latest) return [];
  const from = new Date(Date.parse(`${latest.date}T00:00:00Z`) - 21 * 86_400_000).toISOString().slice(0, 10);
  const series = await get<{ points: Point[] }>(`/v1/history/USD?from=${from}&to=${latest.date}`);
  const earlier = (series?.points ?? []).map((p) => p.date).filter((d) => d < latest.date).slice(-extra).reverse();
  const days = await Promise.all(earlier.map((d) => get<Day>(`/v1/rates/${d}`)));
  return [latest, ...days.filter((d): d is Day => d !== null && d.date !== latest.date)];
}
