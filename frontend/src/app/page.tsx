"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { createCompetitor, listCompetitors, type Competitor } from "@/lib/api";

export default function Home() {
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setCompetitors(await listCompetitors());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !url.trim()) return;
    setBusy(true);
    try {
      await createCompetitor({ name: name.trim(), url: url.trim() });
      setName("");
      setUrl("");
      await refresh();
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-6 text-3xl font-bold">Rivalens</h1>

      <form onSubmit={handleAdd} className="mb-6 flex flex-wrap gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Competitor name"
          className="flex-1 rounded border p-2"
        />
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://competitor.example.com"
          className="flex-1 rounded border p-2"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-blue-600 p-2 text-white disabled:opacity-50"
        >
          Add
        </button>
      </form>

      {error && (
        <p className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-red-700">
          {error}
        </p>
      )}

      <ul className="space-y-3">
        {competitors.map((competitor) => (
          <li key={competitor.id} className="rounded border p-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-semibold">{competitor.name}</span>
                <span className="ml-2 text-gray-500">{competitor.url}</span>
              </div>
              <Link
                href={`/competitors/${competitor.id}`}
                className="rounded bg-blue-600 p-2 text-white"
              >
                View
              </Link>
            </div>
          </li>
        ))}
      </ul>

      {competitors.length === 0 && !error && (
        <p className="text-gray-500">No competitors yet.</p>
      )}
    </main>
  );
}
