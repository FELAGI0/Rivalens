"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { Header } from "@/components/Header";
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
    <main className="mx-auto max-w-3xl p-6">
      <Header />

      <Link href="/" className="mb-4 inline-block text-blue-600 underline">
        &larr; Back to competitors
      </Link>

      {error && (
        <p className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-red-700">
          {error}
        </p>
      )}

      {!detail && !error && <p className="text-gray-500">Loading…</p>}

      {detail && (
        <>
          <h1 className="mb-6 text-3xl font-bold">
            {detail.competitor.name}
          </h1>

          <section className="mb-6 rounded border p-4">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Pages</h2>
              <button
                onClick={handleCheckNow}
                disabled={busy}
                className="rounded bg-blue-600 p-2 text-white disabled:opacity-50"
              >
                {busy ? "Checking…" : "Check now"}
              </button>
            </div>
            <ul className="space-y-1">
              {detail.pages.map((page) => (
                <li key={page.id}>
                  <span className="font-mono text-sm">{page.url}</span>
                  <span className="ml-2 rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                    {page.kind}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded border p-4">
            <h2 className="mb-2 text-lg font-semibold">Insights</h2>
            {detail.insights.length === 0 ? (
              <p className="text-gray-500">
                No insights yet. Click Check now.
              </p>
            ) : (
              <ul className="space-y-3">
                {detail.insights.map((insight) => (
                  <li key={insight.id} className="rounded border p-3">
                    <p className="mb-1 text-xs text-gray-500">
                      {new Date(insight.created_at).toLocaleString("ru-RU")}
                    </p>
                    <p>{insight.summary}</p>
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
