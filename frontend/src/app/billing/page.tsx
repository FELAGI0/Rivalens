"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthGate } from "@/components/AuthGate";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { Button } from "@/components/Button";
import {
  checkout,
  getPlan,
  setPlan,
  UnauthorizedError,
  type Plan,
} from "@/lib/api";

const PLANS: {
  name: string;
  limit: number | null;
  price: string;
  originalPrice: string | null;
  discountBadge: string | null;
  features: string;
}[] = [
  {
    name: "free",
    limit: 2,
    price: "$0",
    originalPrice: null,
    discountBadge: null,
    features: "2 конкурента",
  },
  {
    name: "pro",
    limit: 10,
    price: "490 ₽/мес",
    originalPrice: "900 ₽/мес",
    discountBadge: "−45%",
    features: "10 конкурентов",
  },
  {
    name: "business",
    limit: null,
    price: "1990 ₽/мес",
    originalPrice: "2900 ₽/мес",
    discountBadge: "−31%",
    features: "Без ограничений",
  },
];

// Plan hierarchy: downgrade/same via setPlan, upgrade via checkout.
const PLAN_RANK: Record<string, number> = {
  free: 0,
  pro: 1,
  business: 2,
};

const PLAN_LABELS: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  business: "Business",
};

function BillingContent() {
  const router = useRouter();
  const [plan, setPlanState] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [downgrade, setDowngrade] = useState<string | null>(null);

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
    // Upgrade: money moves via YooKassa.
    setBusy(planName);
    try {
      const { confirmation_url } = await checkout(planName);
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

  async function handleDowngrade(planName: string) {
    // Downgrade or re-choose: free, instant. Behind a confirm dialog.
    setDowngrade(null);
    setBusy(planName);
    try {
      await setPlan(planName);
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

  function buttonFor(p: { name: string; price: string }) {
    if (!plan) {
      return (
        <Button variant="ghost" disabled className="w-full">
          …
        </Button>
      );
    }
    const current = plan.plan;
    const isCurrent = current === p.name;
    const isUpgrade =
      PLAN_RANK[p.name] !== undefined && PLAN_RANK[p.name] > PLAN_RANK[current];

    if (isCurrent) {
      return (
        <Button variant="ghost" disabled className="w-full">
          Активен
        </Button>
      );
    }
    if (isUpgrade) {
      return (
        <Button
          variant="primary"
          onClick={() => void handlePay(p.name)}
          disabled={busy !== null}
          className="w-full"
        >
          {busy === p.name ? "Создаём платёж…" : `Оплатить ${PLAN_LABELS[p.name]} — ${p.price}`}
        </Button>
      );
    }
    return (
      <Button
        variant="ghost"
        onClick={() => setDowngrade(p.name)}
        disabled={busy !== null}
        className="w-full"
      >
        {busy === p.name ? "Переключаем…" : `Перейти на ${PLAN_LABELS[p.name]}`}
      </Button>
    );
  }

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
              <div className="mb-1">
                {p.originalPrice && (
                  <span className="mr-2 text-sm text-fg-muted line-through">
                    {p.originalPrice}
                  </span>
                )}
                <span className="text-2xl font-semibold">{p.price}</span>
                {p.discountBadge && (
                  <span className="ml-2 text-xs font-semibold uppercase tracking-wide text-accent">
                    {p.discountBadge}
                  </span>
                )}
              </div>
              <p className="mb-5 text-sm text-fg-muted">{p.features}</p>
              {buttonFor(p)}
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-xs text-fg-faint">
        Оплата через ЮKassa. Понижение тарифа — бесплатно и мгновенно.
      </p>

      <Footer />

      <ConfirmDialog
        open={downgrade !== null}
        title={`Понизить тариф до ${downgrade ? PLAN_LABELS[downgrade] : ""}?`}
        message={
          downgrade === "free"
            ? "Лимит конкурентов уменьшится до 2. Уже добавленные сверх лимита не удалятся, но новые добавить будет нельзя."
            : "Лимит конкурентов уменьшится до 10. Уже добавленные сверх лимита не удалятся, но новые добавить будет нельзя."
        }
        confirmLabel="Понизить"
        onCancel={() => setDowngrade(null)}
        onConfirm={() => downgrade && void handleDowngrade(downgrade)}
      />
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
