"use client";

import { useState } from "react";
import { ShieldAlert, ShieldCheck, Loader2, ArrowLeft, KeyRound } from "lucide-react";
import Link from "next/link";

type IntelXResult = {
  name: string;
  bucket: string;
  bucket_human: string;
  media_human: string;
  added: string;
  description: string;
  xscore: number;
  preview: string;
  selector: string;
  storage_id: string;
};

type SearchResult = {
  selector: string;
  results: IntelXResult[];
};

type PasswordResult = {
  count: number;
  breached: boolean;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function CheckPage() {
  const [selector, setSelector] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [password, setPassword] = useState("");
  const [pwResult, setPwResult] = useState<PasswordResult | null>(null);
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    if (selector.trim().length < 3) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await fetch(
        `${API_BASE}/api/intelx/search?selector=${encodeURIComponent(selector)}`
      );
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ?? `Request failed (${resp.status})`);
      }
      const data: SearchResult = await resp.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function onPasswordCheck(e: React.FormEvent) {
    e.preventDefault();
    if (!password) return;
    setPwLoading(true);
    setPwError(null);
    setPwResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/pwned/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ?? `Request failed (${resp.status})`);
      }
      const data: PasswordResult = await resp.json();
      setPwResult(data);
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setPwLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center px-4 py-10">
      <div className="w-full max-w-2xl">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </Link>

        <div className="flex items-center gap-3 mb-6">
          <ShieldAlert className="w-8 h-8" />
          <h1 className="text-2xl font-bold tracking-tight">Leak Search</h1>
        </div>

        {/* --- Selector search (IntelX) --- */}
        <section className="mb-10">
          <p className="text-sm text-muted-foreground mb-4">
            Search a selector (email, domain, IP, crypto address) across leaks,
            pastes and darknet sources via the Intelligence X API.
          </p>

          <form onSubmit={onSearch} className="flex gap-2 mb-6">
            <input
              type="text"
              value={selector}
              onChange={(e) => setSelector(e.target.value)}
              placeholder="alice@example.com"
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              required
            />
            <button
              type="submit"
              disabled={loading || selector.trim().length < 3}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? "Searching..." : "Search"}
            </button>
          </form>

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive mb-6">
              {error}
            </div>
          )}

          {result && (
            <div>
              {result.results.length === 0 ? (
                <div className="flex items-center gap-3 rounded-md border border-border bg-background p-6">
                  <ShieldCheck className="w-6 h-6 text-green-600" />
                  <div>
                    <div className="font-medium">No results found</div>
                    <div className="text-sm text-muted-foreground">
                      {result.selector} did not appear in any indexed source.
                    </div>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex items-center gap-2 mb-4">
                    <ShieldAlert className="w-5 h-5 text-destructive" />
                    <span className="font-medium">
                      {result.results.length} result
                      {result.results.length > 1 ? "s" : ""} for {result.selector}
                    </span>
                  </div>
                  <ul className="space-y-3">
                    {result.results.map((r, i) => (
                      <li
                        key={`${r.storage_id}-${i}`}
                        className="rounded-md border border-border bg-background p-4"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium">{r.name || r.bucket_human}</span>
                          <span className="text-xs text-muted-foreground">{r.added}</span>
                        </div>
                        <div className="flex flex-wrap gap-1 mb-2">
                          {r.bucket_human && (
                            <span className="rounded bg-muted px-2 py-0.5 text-xs">{r.bucket_human}</span>
                          )}
                          {r.media_human && (
                            <span className="rounded bg-muted px-2 py-0.5 text-xs">{r.media_human}</span>
                          )}
                          {r.xscore > 0 && (
                            <span className="rounded bg-muted px-2 py-0.5 text-xs">score {r.xscore}</span>
                          )}
                        </div>
                        {r.preview && (
                          <pre className="text-xs text-muted-foreground whitespace-pre-wrap bg-muted/50 rounded p-2 max-h-40 overflow-auto">
                            {r.preview}
                          </pre>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>

        {/* --- Password check (Pwned Passwords, free) --- */}
        <section className="border-t border-border pt-8">
          <div className="flex items-center gap-2 mb-2">
            <KeyRound className="w-5 h-5" />
            <h2 className="text-lg font-semibold">Password Breach Check</h2>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Check if a password has appeared in known breaches. Free, no API key
            required — uses the k-anonymity SHA-1 range search, so the password
            itself never leaves the lookup.
          </p>

          <form onSubmit={onPasswordCheck} className="flex gap-2 mb-6">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="enter a password to check"
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              required
            />
            <button
              type="submit"
              disabled={pwLoading || !password}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {pwLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              {pwLoading ? "Checking..." : "Check"}
            </button>
          </form>

          {pwError && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive mb-6">
              {pwError}
            </div>
          )}

          {pwResult && (
            <div>
              {pwResult.breached ? (
                <div className="flex items-start gap-3 rounded-md border border-destructive/50 bg-destructive/10 p-6">
                  <ShieldAlert className="w-6 h-6 text-destructive shrink-0" />
                  <div>
                    <div className="font-medium text-destructive">
                      Password found in {pwResult.count.toLocaleString()} breach
                      {pwResult.count === 1 ? "" : "es"}
                    </div>
                    <div className="text-sm text-muted-foreground mt-1">
                      This password has appeared in known data breaches and should
                      not be used anywhere.
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-3 rounded-md border border-border bg-background p-6">
                  <ShieldCheck className="w-6 h-6 text-green-600" />
                  <div>
                    <div className="font-medium">Password not found</div>
                    <div className="text-sm text-muted-foreground">
                      This password did not appear in any known breach.
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
