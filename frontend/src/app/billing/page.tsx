"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthGate } from "@/components/AuthGate";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { Button } from "@/components/Button";
import {
  checkout,
  getPlan,
  UnauthorizedError,
  type Plan,
} from "@/lib/api";

const PLANS: {
  name: string;
  limit: number | null;
  price: string;
  features: string;
}[] = [
  { name: "free", limit: 2, price: "$0", features: "2 конкурента" },
  { name: "pro", limit: 10, price: "900 ₽/мес", features: "10 конкурентов" },
  { name: "business", limit: null, price: "2900 ₽/мес", features: "Без ограничений" },
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

  async function handlePay(planName: string) {
    setBusy(planName);
    try {
      const { confirmation_url } = await checkout(planName);
      // Hosted checkout: leave the app, YooKassa returns to /billing/success
      window.location.href = confirmation_url;
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

  const PLAN_LABELS: Record<string, string> = {
    free: "Free",
    pro: "Pro",
    business: "Business",
  };

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <Header plan={plan ? `Тариф: ${plan.plan}` : null} />

      <h1 className="mb-2 text-4xl font-semibold">Ваш тариф</h1>
      {plan && (
        <p className="mb-10 text-sm text-fg-muted">
          {plan.competitors_used} из{" "}
          {plan.competitors_limit === null
            ? "неограниченного числа"
            : plan.competitors_limit}{" "}
          конкурентов
        </p>
      )}

      {error && (
        <p className="mb-8 border-l-2 border-accent pl-4 text-sm text-fg-muted">
          {error}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {PLANS.map((p) => {
          const current = plan?.plan === p.name;
          return (
            <div
              key={p.name}
              className={`rounded-sm p-5 ${
                current
                  ? "border-2 border-accent"
                  : "border border-line transition-colors duration-150 hover:border-fg-muted"
              }`}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="font-serif text-xl font-semibold">
                  {PLAN_LABELS[p.name] ?? p.name}
                </span>
                {current && (
                  <span className="text-xs uppercase tracking-wide text-accent">
                    Текущий
                  </span>
                )}
              </div>
              <p className="mb-1 text-2xl font-semibold">{p.price}</p>
              <p className="mb-5 text-sm text-fg-muted">{p.features}</p>
              {p.name === "free" ? (
                <Button
                  variant="ghost"
                  disabled
                  className="w-full"
                >
                  {current ? "Активен" : "Бесплатный"}
                </Button>
              ) : (
                <Button
                  variant={current ? "ghost" : "primary"}
                  onClick={() => void handlePay(p.name)}
                  disabled={busy !== null || current}
                  className="w-full"
                >
                  {busy === p.name
                    ? "Создаём платёж…"
                    : current
                      ? "Активен"
                      : `Оплатить ${PLAN_LABELS[p.name]} — ${p.price}`}
                </Button>
              )}
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-xs text-fg-faint">
        Оплата через ЮKassa. Тариф активируется после подтверждения
        платежа — обычно в течение минуты.
      </p>

      <Footer />
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
