"use client";

import { KeyRound, Plus, TriangleAlert } from "lucide-react";
import { useActionState } from "react";

import { CopyButton } from "@/components/CopyButton";

import { createKeyAction, type CreateState } from "./actions";

export function CreateKey({ disabled }: { disabled: boolean }) {
  const [state, action, pending] = useActionState<CreateState, FormData>(createKeyAction, {});
  return (
    <div className="space-y-4">
      <form action={action} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor="key-name" className="sr-only">Key name</label>
        <input
          id="key-name" name="name" maxLength={60} placeholder="Key name, e.g. production" disabled={disabled || pending}
          className="h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm placeholder:text-muted-foreground disabled:opacity-50"
        />
        <button
          type="submit" disabled={disabled || pending}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          <Plus className="h-4 w-4" /> {pending ? "Creating…" : "Create key"}
        </button>
      </form>
      {state.error && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">{state.error}</p>
      )}
      {state.key && (
        <div role="status" className="space-y-2 rounded-lg border border-accent/50 bg-accent/10 p-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            <KeyRound className="h-4 w-4" /> New key &ldquo;{state.name}&rdquo;
          </p>
          <div className="flex items-center gap-2 rounded-md border border-border bg-card py-1 pl-3 pr-1 font-mono text-sm">
            <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap">{state.key}</code>
            <CopyButton text={state.key} label="Copy API key" />
          </div>
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <TriangleAlert className="mt-px h-3.5 w-3.5 shrink-0" />
            Copy it now. This is the only time it&apos;s shown; we store only a hash of it.
          </p>
        </div>
      )}
    </div>
  );
}
