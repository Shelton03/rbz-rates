import Link from "next/link";

import { currentUser } from "@/lib/auth";

import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";

const GITHUB = "https://github.com/Shelton03/rbz-rates";

export async function SiteHeader() {
  const user = await currentUser();
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3">
        Skip to content
      </a>
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4 sm:px-6">
        <Link href="/" aria-label="rbz-rates home">
          <Logo />
        </Link>
        <span className="hidden rounded-full border border-border px-2 py-0.5 font-mono text-[11px] text-muted-foreground sm:inline">
          unofficial
        </span>
        <nav className="ml-auto flex items-center gap-1 text-sm">
          <Link href="/#rates" className="hidden rounded-md px-3 py-2 text-muted-foreground hover:text-foreground sm:block">
            Rates
          </Link>
          <Link href="/history" className="rounded-md px-3 py-2 text-muted-foreground hover:text-foreground">
            History
          </Link>
          <Link href="/docs" className="rounded-md px-3 py-2 text-muted-foreground hover:text-foreground">
            Docs
          </Link>
          <a href={GITHUB} className="hidden rounded-md px-3 py-2 text-muted-foreground hover:text-foreground sm:block">
            GitHub
          </a>
          <ThemeToggle />
          <Link
            href={user ? "/dashboard" : "/signin"}
            className="ml-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            {user ? "Dashboard" : "Get a key"}
          </Link>
        </nav>
      </div>
    </header>
  );
}
