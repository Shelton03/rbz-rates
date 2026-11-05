import { timingSafeEqual } from "node:crypto";

import { revalidateTag } from "next/cache";

import { DATA_TAG } from "@/lib/rbz";

/**
 * Purge the cached API data so pages show new rates immediately.
 * Called by the deploy workflow right after the API is deployed with new data.
 */
export async function POST(request: Request) {
  const secret = process.env.RBZ_ADMIN_SECRET; // the same server-to-server secret the API admin calls use
  const given = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  const ok = !!secret && given.length === secret.length && timingSafeEqual(Buffer.from(given), Buffer.from(secret));
  if (!ok) return Response.json({ detail: "Unauthorized" }, { status: 401 });
  revalidateTag(DATA_TAG, { expire: 0 });
  return Response.json({ revalidated: DATA_TAG, at: new Date().toISOString() });
}
