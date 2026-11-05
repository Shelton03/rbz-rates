import "server-only";

import { API_URL } from "./rbz";

/** Calls the Worker's /admin API with the shared secret. Server-only: never import from a client component. */
async function admin<T>(path: string, init: RequestInit = {}): Promise<T> {
  const secret = process.env.RBZ_ADMIN_SECRET;
  if (!secret) throw new Error("RBZ_ADMIN_SECRET is not set");
  const res = await fetch(`${API_URL}/admin${path}`, {
    ...init,
    cache: "no-store",
    headers: { "X-Admin-Secret": secret, "Content-Type": "application/json", ...init.headers },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new AdminError(res.status, (body as { detail?: string }).detail || res.statusText);
  return body as T;
}

export class AdminError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  revoked_at: string | null;
  last_used: string | null;
  today: number;
};
export type UsageRow = { day: string; key_id: string; endpoint: string; count: number };
export type Stats = {
  since: string;
  by_day: { day: string; keyed: number; anonymous: number; callers: number }[];
  by_endpoint: { endpoint: string; count: number }[];
  top_keys: { name: string; prefix: string; login: string; count: number }[];
  users: number;
  active_keys: number;
};

export const upsertUser = (id: string, login: string, email?: string | null) =>
  admin(`/users/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ login, email: email ?? null }) });

export const listKeys = (userId: string) =>
  admin<{ keys: ApiKey[]; limit_per_key: number; max_keys: number }>(`/users/${encodeURIComponent(userId)}/keys`);

export const createKey = (userId: string, name: string) =>
  admin<{ id: string; name: string; key: string }>(`/users/${encodeURIComponent(userId)}/keys`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });

export const revokeKey = (userId: string, keyId: string) =>
  admin(`/users/${encodeURIComponent(userId)}/keys/${encodeURIComponent(keyId)}`, { method: "DELETE" });

export const userUsage = (userId: string, days = 30) =>
  admin<{ since: string; rows: UsageRow[] }>(`/users/${encodeURIComponent(userId)}/usage?days=${days}`);

export const siteStats = (days = 30) => admin<Stats>(`/stats?days=${days}`);
