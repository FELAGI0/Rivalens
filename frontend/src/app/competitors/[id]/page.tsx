"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { Header } from "@/components/Header";
import { Button } from "@/components/Button";
import {
  checkCompetitor,
  getCompetitor,
  UnauthorizedError,
  type CompetitorDetail,
} from "@/lib/api";

function CompetitorPageContent() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const [detail, setDetail] = useState<CompetitorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      setDetail(await getCompetitor(id));
      setError(null);
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        router.replace("/login");
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id, router]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleCheckNow() {
    setBusy(true);
    try {
      await checkCompetitor(id);
      await refresh();
      setError(null);
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        router.replace("/login");
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <Header />

      <div className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="mb-1 truncate text-4xl font-semibold">
            {detail?.competitor.name ?? "…"}
          </h1>
          {detail && (
            <p className="truncate text-sm text-fg-muted">
              {detail.competitor.url}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-sm border border-line px-4 py-2 text-sm font-medium text-fg transition-colors duration-150 hover:border-fg-muted hover:bg-bg-subtle"
          >
            ← Back
          </Link>
          <Button onClick={handleCheckNow} disabled={busy}>
            {busy && <span className="spinner" aria-hidden="true" />}
            {busy ? "Checking…" : "Check now"}
          </Button>
        </div>
      </div>

      {error && (
        <p className="mb-8 border-l-2 border-accent pl-4 text-sm text-fg-muted">
          {error}
        </p>
      )}

      {!detail && !error && <p className="text-fg-muted">Loading…</p>}

      {detail && (
        <>
          <section className="mb-12">
            <h2 className="mb-4 text-sm font-medium uppercase text-fg-muted">
              Pages
            </h2>
            {detail.pages.length === 0 ? (
              <p className="text-sm text-fg-muted">No pages yet.</p>
            ) : (
              <ul className="divide-y divide-line border-y border-line">
                {detail.pages.map((page) => (
                  <li key={page.id} className="py-3">
                    <span className="font-mono text-sm">{page.url}</span>
                    <span className="ml-3 text-xs uppercase tracking-wide text-fg-muted">
                      {page.kind}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h2 className="mb-4 text-sm font-medium uppercase text-fg-muted">
              Insights
            </h2>
            {detail.insights.length === 0 ? (
              <p className="border-y border-line py-8 text-sm text-fg-muted">
                No insights yet. First check creates a snapshot; the second
                run with changes generates an insight.
              </p>
            ) : (
              <ul className="border-t border-line">
                {detail.insights.map((insight) => (
                  <li
                    key={insight.id}
                    className="border-b border-line py-6 md:flex md:gap-8"
                  >
                    <p className="mb-2 shrink-0 text-xs text-fg-muted md:mb-0 md:w-36 md:pt-1">
                      {new Date(insight.created_at).toLocaleString("ru-RU")}
                    </p>
                    <p className="leading-relaxed">{insight.summary}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}

export default function CompetitorPage() {
  return (
    <AuthGate>
      <CompetitorPageContent />
    </AuthGate>
  );
}
