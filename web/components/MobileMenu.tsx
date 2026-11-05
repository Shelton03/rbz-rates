"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const LINKS = [
  { href: "/#rates", label: "Rates" },
  { href: "/history", label: "History" },
  { href: "/docs", label: "Docs" },
  { href: "https://github.com/Shelton03/rbz-rates", label: "GitHub" },
];

/** Nav for small screens: a menu button with a drop-down panel that closes on navigation or outside tap. */
export function MobileMenu() {
  const [open, setOpen] = useState(false);
  const path = usePathname();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={ref} className="relative md:hidden">
      <button
        type="button" aria-expanded={open} aria-controls="mobile-nav" aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>
      {open && (
        <nav id="mobile-nav" className="absolute right-0 top-12 z-50 w-56 rounded-xl border border-border bg-card p-2 shadow-lg">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)}
              className="block rounded-md px-3 py-2.5 text-sm text-foreground hover:bg-muted">
              {l.label}
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
}
