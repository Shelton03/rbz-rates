import "server-only";

import { getServerSession, type NextAuthOptions } from "next-auth";
import GitHub from "next-auth/providers/github";

import { upsertUser } from "./admin";

type GitHubProfile = { id: number | string; login: string; email?: string | null };

export const authOptions: NextAuthOptions = {
  providers: [
    GitHub({ clientId: process.env.GITHUB_ID ?? "", clientSecret: process.env.GITHUB_SECRET ?? "" }),
  ],
  session: { strategy: "jwt" }, // no session database; accounts live in the API's D1
  pages: { signIn: "/signin" },
  callbacks: {
    async signIn({ profile }) {
      const p = profile as GitHubProfile | undefined;
      if (!p?.id) return false;
      try {
        await upsertUser(String(p.id), p.login, p.email);
      } catch (e) {
        console.error("upsertUser failed", e); // retried when they create a key
      }
      return true;
    },
    async jwt({ token, profile }) {
      const p = profile as GitHubProfile | undefined;
      if (p?.id) {
        token.uid = String(p.id);
        token.login = p.login;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.uid as string;
        session.user.login = token.login as string;
      }
      return session;
    },
  },
};

export type SiteUser = { id: string; login: string; name?: string | null; email?: string | null; image?: string | null };

/** The signed-in user, or null. */
export async function currentUser(): Promise<SiteUser | null> {
  // Local development without a GitHub OAuth app: DEV_FAKE_USER="<github id>:<login>".
  // Next.js sets NODE_ENV=production for every build, so this never applies on Vercel.
  if (process.env.NODE_ENV === "development" && process.env.DEV_FAKE_USER) {
    const [id, login] = process.env.DEV_FAKE_USER.split(":");
    return { id, login: login || "dev" };
  }
  const session = await getServerSession(authOptions);
  const u = session?.user;
  return u?.id ? { id: u.id, login: u.login, name: u.name, email: u.email, image: u.image } : null;
}

export function isOwner(user: SiteUser | null): boolean {
  const owners = (process.env.OWNER_GITHUB_IDS || "").split(",").map((s) => s.trim()).filter(Boolean);
  return !!user && owners.includes(user.id);
}
