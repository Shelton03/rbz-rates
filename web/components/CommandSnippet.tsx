import { CopyButton } from "./CopyButton";

/** A one-line command with a $ prompt and copy button. */
export function CommandSnippet({ command }: { command: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-card py-1.5 pl-4 pr-1.5 font-mono text-sm shadow-sm">
      <span className="select-none text-muted-foreground">$</span>
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap py-1.5">{command}</code>
      <CopyButton text={command} label="Copy command" />
    </div>
  );
}

/** A multi-line code block with a copy button. */
export function CodeBlock({ code, title }: { code: string; title?: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      {title && (
        <div className="flex items-center justify-between border-b border-border bg-muted/50 py-1 pl-4 pr-1.5">
          <span className="font-mono text-xs text-muted-foreground">{title}</span>
          <CopyButton text={code} />
        </div>
      )}
      <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}
