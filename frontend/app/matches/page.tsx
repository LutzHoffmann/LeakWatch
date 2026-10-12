"use client";

import { useEffect, useState } from "react";
import { ShieldAlert, Loader2, ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";

type Credential = {
  kind: string;
  value: string;
  pair_id: string | null;
};

type Match = {
  id: number;
  created_at: string;
  domain: string;
  reason: string;
  credential: Credential;
  paired_credential: Credential | null;
  source: string;
  url: string;
  fetched_at: string;
};

type MatchesResponse = {
  matches: Match[];
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function maskPassword(pw: string) {
  if (!pw) return "";
  if (pw.length <= 2) return "•".repeat(pw.length);
  return pw[0] + "•".repeat(Math.max(pw.length - 2, 2)) + pw[pw.length - 1];
}

export default function MatchesPage() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());

  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/matches?limit=100`);
        if (!resp.ok) throw new Error(`Request failed (${resp.status})`);
        const data: MatchesResponse = await resp.json();
        setMatches(data.matches);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Request failed");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function toggleReveal(id: number) {
    setRevealed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <main className="min-h-screen flex flex-col items-center px-4 py-10">
      <div className="w-full max-w-3xl">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </Link>

        <div className="flex items-center gap-3 mb-6">
          <ShieldAlert className="w-8 h-8" />
          <h1 className="text-2xl font-bold tracking-tight">Found Leaks</h1>
        </div>

        <p className="text-sm text-muted-foreground mb-6">
          Credential matches discovered by the watch pipeline across the
          monitored sources. Each row shows the leaked credential and, where
          available, the associated email+password combination.
        </p>

        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading matches...
          </div>
        )}

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive mb-6">
            {error}
          </div>
        )}

        {!loading && !error && matches.length === 0 && (
          <div className="rounded-md border border-border bg-background p-6 text-sm text-muted-foreground">
            No matches yet. Matches appear here once a watch cycle finds
            credentials for one of your monitored domains.
          </div>
        )}

        {!loading && matches.length > 0 && (
          <ul className="space-y-3">
            {matches.map((m) => {
              const isEmail = m.credential.kind === "email";
              const hasPair = m.paired_credential !== null;
              const showPw = revealed.has(m.id);
              return (
                <li
                  key={m.id}
                  className="rounded-md border border-border bg-background p-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {m.source}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {m.fetched_at}
                    </span>
                  </div>

                  {hasPair ? (
                    <div className="font-mono text-sm space-y-1">
                      <div>
                        <span className="text-muted-foreground">email: </span>
                        <span className="font-medium">
                          {m.credential.kind === "email"
                            ? m.credential.value
                            : m.paired_credential!.value}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">password: </span>
                        <span className="font-medium">
                          {showPw
                            ? m.credential.kind === "password"
                                ? m.credential.value
                                : m.paired_credential!.value
                            : maskPassword(
                                m.credential.kind === "password"
                                  ? m.credential.value
                                  : m.paired_credential!.value
                              )}
                        </span>
                        <button
                          onClick={() => toggleReveal(m.id)}
                          className="ml-2 text-xs text-muted-foreground underline hover:text-foreground"
                        >
                          {showPw ? "hide" : "reveal"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="font-mono text-sm">
                      <span className="text-muted-foreground">{m.credential.kind}: </span>
                      <span className="font-medium">{m.credential.value}</span>
                    </div>
                  )}

                  <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="rounded bg-muted px-2 py-0.5">
                      domain: {m.domain}
                    </span>
                    {m.url && (
                      <a
                        href={m.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 hover:text-foreground"
                      >
                        source <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </main>
  );
}
