import { FileSearch } from "lucide-react";
import Link from "next/link";

import { RatesTable } from "@/components/RatesTable";
import { formatDay } from "@/lib/currencies";
import { getLatest } from "@/lib/rbz";

export const metadata = { title: "All rates" };
export const revalidate = 3600;

export default async function Rates() {
  const latest = await getLatest();
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-12 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">All rates</h1>
          <p className="mt-1 text-muted-foreground">
            {latest ? `Every currency RBZ published for ${formatDay(latest.date)}. ` : "Unavailable right now. "}
            ZWG per 1 unit of each currency.
          </p>
        </div>
        <Link href="/docs#latest" className="inline-block py-1.5 text-sm font-medium text-accent hover:underline">Get these as JSON →</Link>
      </div>
      {latest && (
        <>
          <RatesTable day={latest} codes={Object.keys(latest.rates)} />
          <a href={latest.source.url} className="inline-flex items-center gap-1 py-1.5 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
            <FileSearch className="h-4 w-4" /> Source: RBZ PDF for {formatDay(latest.date)}
          </a>
        </>
      )}
    </div>
  );
}
