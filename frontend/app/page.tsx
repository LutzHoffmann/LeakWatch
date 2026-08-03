import { ShieldAlert } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <div className="flex items-center gap-3">
        <ShieldAlert className="w-10 h-10" />
        <h1 className="text-3xl font-bold tracking-tight">LeakWatch</h1>
      </div>
      <p className="text-lg text-muted-foreground">
        Credential Leak Monitor — Dashboard coming soon.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full max-w-2xl">
        {[
          { label: "Overview", value: "Last 10 alerts" },
          { label: "Search", value: "Full-text over leaks" },
          { label: "Settings", value: "Domains & channels" },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-lg border border-border p-4 bg-background shadow-sm"
          >
            <div className="text-sm font-medium">{card.label}</div>
            <div className="text-sm text-muted-foreground">{card.value}</div>
          </div>
        ))}
      </div>
    </main>
  );
}
