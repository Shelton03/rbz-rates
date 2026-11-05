/** Wordmark: a small ascending-bars glyph and the project name. Deliberately not RBZ's branding. */
export function Logo() {
  return (
    <span className="inline-flex items-center gap-2 font-semibold tracking-tight">
      <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden="true">
        <rect x="1" y="1" width="22" height="22" rx="6" fill="var(--primary)" />
        <rect x="6" y="12" width="3" height="6" rx="1" fill="var(--primary-foreground)" />
        <rect x="10.5" y="9" width="3" height="9" rx="1" fill="var(--primary-foreground)" />
        <rect x="15" y="6" width="3" height="12" rx="1" fill="var(--accent)" />
      </svg>
      <span className="font-mono text-[15px]">rbz-rates</span>
    </span>
  );
}
