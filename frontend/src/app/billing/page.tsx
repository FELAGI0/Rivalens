"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthGate } from "@/components/AuthGate";
import { Header } from "@/components/Header";
import {
  getPlan,
  setPlan,
  UnauthorizedError,
  type Plan,
} from "@/lib/api";

const PLANS: {
  name: string;
  limit: number | null;
  price: string;
  features: string;
}[] = [
  {
    name: "free",
    limit: 1,
    price: "$0",
    features: "1 competitor",
  },
  {
    name: "pro",
    limit: 10,
    price: "$9/mo",
    features: "10 competitors",
  },
  {
    name: "business",
    limit: null,
    price: "$29/mo",
    features: "Unlimited competitors",
  },
];

function BillingContent() {
  const router = useRouter();
  const [plan, setPlanState] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    try {
      setPlanState(await getPlan());
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

  async function handleSwitch(name: string) {
    setBusy(name);
    try {
      await setPlan(name);
      await refresh();
      setError(null);
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        router.replace("/login");
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6">
      <Header />

      <h1 className="mb-6 text-3xl font-bold">Your plan</h1>

      {error && (
        <p className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-red-700">
          {error}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {PLANS.map((p) => {
          const current = plan?.plan === p.name;
          return (
            <div
              key={p.name}
              className={`rounded border p-4 ${
                current ? "border-blue-600 ring-2 ring-blue-600" : "border-gray-300"
              }`}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="text-lg font-semibold capitalize">{p.name}</span>
                {current && (
                  <span className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white">
                    Current
                  </span>
                )}
              </div>
              <p className="mb-1 text-2xl font-bold">{p.price}</p>
              <p className="mb-4 text-sm text-gray-600">{p.features}</p>
              <button
                onClick={() => void handleSwitch(p.name)}
                disabled={busy !== null || current}
                className={`w-full rounded p-2 text-sm disabled:opacity-50 ${
                  current
                    ? "border border-gray-300 text-gray-500"
                    : "bg-blue-600 text-white hover:bg-blue-700"
                }`}
              >
                {busy === p.name
                  ? "Switching…"
                  : current
                    ? "Active"
                    : `Switch to ${p.name}`}
              </button>
            </div>
          );
        })}
      </div>

      {plan && (
        <p className="mt-4 text-sm text-gray-600">
          Usage: {plan.competitors_used} of{" "}
          {plan.competitors_limit === null
            ? "unlimited"
            : plan.competitors_limit}{" "}
          competitors
        </p>
      )}

      <p className="mt-6 text-xs text-gray-500">
        MVP: plan switching is free and instant, no payment processing yet.
      </p>
    </main>
  );
}

export default function BillingPage() {
  return (
    <AuthGate>
      <BillingContent />
    </AuthGate>
  );
}
