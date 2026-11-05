"use client";

import { useFormStatus } from "react-dom";

import { revokeKeyAction } from "./actions";

function Submit({ name }: { name: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit" disabled={pending}
      onClick={(e) => { if (!confirm(`Revoke "${name}"? Apps using it will stop working within a minute.`)) e.preventDefault(); }}
      className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:border-destructive/60 hover:text-destructive disabled:opacity-50"
    >
      {pending ? "Revoking…" : "Revoke"}
    </button>
  );
}

export function RevokeButton({ id, name }: { id: string; name: string }) {
  return (
    <form action={revokeKeyAction}>
      <input type="hidden" name="id" value={id} />
      <Submit name={name} />
    </form>
  );
}
