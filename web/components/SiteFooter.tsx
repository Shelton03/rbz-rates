import Link from "next/link";

import { Logo } from "./Logo";

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-muted/40">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm sm:grid-cols-[2fr_1fr_1fr] sm:px-6">
        <div className="space-y-3">
          <Logo />
          <p className="max-w-md text-muted-foreground">
            An unofficial, open-source mirror of the Reserve Bank of Zimbabwe&apos;s daily interbank rates. Not affiliated
            with or endorsed by the Reserve Bank of Zimbabwe. Check the source PDF before relying on a figure.
          </p>
        </div>
        <div className="space-y-2">
          <p className="font-medium">Project</p>
          <ul className="space-y-0.5 text-muted-foreground">
            <li><Link href="/docs" className="inline-block py-1 hover:text-foreground">Documentation</Link></li>
            <li><a href="https://github.com/Shelton03/rbz-rates" className="inline-block py-1 hover:text-foreground">Source code</a></li>
            <li><Link href="/privacy" className="inline-block py-1 hover:text-foreground">Privacy</Link></li>
          </ul>
        </div>
        <div className="space-y-2">
          <p className="font-medium">Source data</p>
          <ul className="space-y-0.5 text-muted-foreground">
            <li>
              <a href="https://www.rbz.co.zw/index.php/research/markets/exchange-rates" className="inline-block py-1 hover:text-foreground">
                RBZ exchange rates
              </a>
            </li>
            <li className="py-1">MIT License</li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
