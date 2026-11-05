export const metadata = { title: "Privacy" };

export default function Privacy() {
  return (
    <article className="mx-auto max-w-2xl space-y-6 px-4 py-12 text-muted-foreground sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground">Privacy</h1>
      <p>This is a small open-source project. It keeps as little as it can.</p>
      <h2 className="text-lg font-semibold text-foreground">If you sign in</h2>
      <ul className="list-disc space-y-1 pl-5">
        <li>Your GitHub user id, username and email address, to link your keys to you.</li>
        <li>Your API keys, as one-way hashes only. Nobody, including us, can read a key back.</li>
        <li>Request counts per key, per endpoint, per day. Not the requests themselves.</li>
      </ul>
      <h2 className="text-lg font-semibold text-foreground">If you use the API without a key</h2>
      <p>
        To apply the daily limit, requests are counted against a hash of your IP address mixed with a secret and the
        date. The hash changes every day and your IP address itself is never stored.
      </p>
      <h2 className="text-lg font-semibold text-foreground">Hosting</h2>
      <p>
        The API runs on Cloudflare and this site on Vercel; both keep short-lived request logs under their own policies.
        There are no ads, trackers or analytics scripts on this site.
      </p>
      <h2 className="text-lg font-semibold text-foreground">Deleting your data</h2>
      <p>
        Revoke your keys from the dashboard at any time. To delete your account entirely, open an issue on{" "}
        <a href="https://github.com/Shelton03/rbz-rates/issues" className="underline underline-offset-4">GitHub</a>.
      </p>
    </article>
  );
}
