import { redirect } from "next/navigation";

import { currentUser } from "@/lib/auth";

import { SignInButton } from "./SignInButton";

export const metadata = { title: "Sign in" };

export default async function SignIn({ searchParams }: { searchParams: Promise<{ callbackUrl?: string; error?: string }> }) {
  const { callbackUrl, error } = await searchParams;
  const target = callbackUrl?.startsWith("/") ? callbackUrl : "/dashboard";
  if (await currentUser()) redirect(target);
  return (
    <section className="mx-auto flex max-w-sm flex-col gap-6 px-4 py-20">
      <div className="space-y-2 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Get a free API key</h1>
        <p className="text-sm text-muted-foreground">
          Sign in with GitHub to create up to 3 keys, each good for 5,000 requests a day, and see their usage.
        </p>
      </div>
      <div className="space-y-4 rounded-xl border border-border bg-card p-6">
        {error && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
            Sign-in didn&apos;t complete. Please try again.
          </p>
        )}
        <SignInButton callbackUrl={target} />
        <p className="text-center text-xs text-muted-foreground">
          We store your GitHub user id, username and email. See <a href="/privacy" className="underline underline-offset-4">privacy</a>.
        </p>
      </div>
    </section>
  );
}
