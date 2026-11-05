"use server";

import { revalidatePath } from "next/cache";

import { AdminError, createKey, revokeKey, upsertUser } from "@/lib/admin";
import { currentUser } from "@/lib/auth";

export type CreateState = { key?: string; name?: string; error?: string };

export async function createKeyAction(_prev: CreateState, form: FormData): Promise<CreateState> {
  const user = await currentUser();
  if (!user) return { error: "Please sign in again." };
  const name = String(form.get("name") || "").trim().slice(0, 60) || "Default";
  try {
    await upsertUser(user.id, user.login, user.email); // idempotent; covers a failed upsert at sign-in
    const created = await createKey(user.id, name);
    revalidatePath("/dashboard");
    return { key: created.key, name: created.name };
  } catch (e) {
    return { error: e instanceof AdminError ? e.message : "Couldn't create the key. Please try again." };
  }
}

export async function revokeKeyAction(form: FormData): Promise<void> {
  const user = await currentUser();
  if (!user) return;
  const id = String(form.get("id") || "");
  try {
    await revokeKey(user.id, id);
  } catch (e) {
    console.error("revoke failed", e);
  }
  revalidatePath("/dashboard");
}
