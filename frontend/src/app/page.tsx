"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthGate } from "@/components/AuthGate";
import { Header } from "@/components/Header";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import {
  createCompetitor,
  getPlan,
  listCompetitors,
  UnauthorizedError,
  PaymentRequiredError,
  type Competitor,
  type Plan,
} from "@/lib/api";

function HomeContent() {
  const router = useRouter();
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [plan, setPlanState] = useState<Plan | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [limitHit, setLimitHit] = useState(false);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const [competitorList, planInfo] = await Promise.all([
        listCompetitors(),
        getPlan(),
      ]);
      setCompetitors(competitorList);
      setPlanState(planInfo);
      setError(null);
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        router.replace("/login");
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !url.trim()) return;
    setBusy(true);
    setLimitHit(false);
    try {
      await createCompetitor({ name: name.trim(), url: url.trim() });
      setName("");
      setUrl("");
      await refresh();
      setError(null);
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        router.replace("/login");
        return;
      }
      if (e instanceof PaymentRequiredError) {
        setLimitHit(true);
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const limitLabel =
    plan === null
      ? ""
      : `${plan.competitors_used} / ${
          plan.competitors_limit === null ? "∞" : plan.competitors_limit
        }`;

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <Header plan={plan ? plan.plan : null} />

      <h1 className="mb-2 text-4xl font-semibold">Your competitors</h1>
      {plan && (
        <p className="mb-12 text-sm text-fg-muted">
          Plan: {plan.plan} ({limitLabel}) —{" "}
          <Link href="/billing" className="text-accent underline-offset-4 hover:underline">
            Manage plan
          </Link>
        </p>
      )}

      <form onSubmit={handleAdd} className="mb-10 flex flex-col gap-2 sm:flex-row">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Competitor name"
          className="sm:w-56"
        />
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://competitor.example.com"
          className="flex-1"
        />
        <Button type="submit" disabled={busy} className="sm:w-auto">
          Add
        </Button>
      </form>

      {error && (
        <p className="mb-8 border-l-2 border-accent pl-4 text-sm text-fg-muted">
          {error}
        </p>
      )}

      {limitHit && (
        <div className="mb-8 border-l-2 border-accent pl-4">
          <p className="font-medium">Upgrade to add more competitors</p>
          <Link
            href="/billing"
            className="text-sm text-accent underline-offset-4 hover:underline"
          >
            Go to plans →
          </Link>
        </div>
      )}

      {competitors.length > 0 && (
        <ul className="divide-y divide-line border-t border-line">
          {competitors.map((competitor) => (
            <li
              key={competitor.id}
              className="group flex flex-col gap-3 py-5 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <p className="font-medium">{competitor.name}</p>
                <p className="truncate text-sm text-fg-muted">
                  {competitor.url}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Link
                  href={`/competitors/${competitor.id}`}
                  className="inline-flex items-center justify-center rounded-sm border border-line px-4 py-2 text-sm font-medium text-fg transition-colors duration-150 hover:border-fg-muted hover:bg-bg-subtle"
                >
                  View
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}

      {competitors.length === 0 && !error && !limitHit && (
        <p className="border-t border-line pt-8 text-fg-muted">
          No competitors yet. Add the first one above.
        </p>
      )}
    </main>
  );
}

export default function Home() {
  return (
    <AuthGate>
      <HomeContent />
    </AuthGate>
  );
}
