"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { getPlan, UnauthorizedError } from "@/lib/api";

/** Plan names for the message; anything unknown falls back to a generic line. */
const PLAN_LABELS: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  business: "Business",
};

function SuccessContent() {
  const searchParams = useSearchParams();
  // YooKassa returns the user to this page without the plan in the URL,
  // so ?plan= (when present) is a shortcut and GET /billing/plan is the
  // real source: by the time the webhook has run, the plan is active.
  const fromQuery = searchParams.get("plan");
  const [plan, setPlan] = useState<string | null>(
    fromQuery ? (PLAN_LABELS[fromQuery] ?? null) : null,
  );

  useEffect(() => {
    let cancelled = false;
    getPlan()
      .then((info) => {
        if (cancelled) return;
        // The query param names the plan the user just paid for; the
        // endpoint may still report the old one for a few seconds while
        // the webhook lands. Paid plans in the URL win over a match.
        const fromApi = PLAN_LABELS[info.plan] ?? null;
        setPlan((prev) => (prev && prev !== "Free" ? prev : fromApi));
      })
      .catch((e) => {
        // Unauthenticated or offline: the query param (if any) stands.
        if (e instanceof UnauthorizedError) return;
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <Header />
      <h1 className="mb-4 font-serif text-4xl font-semibold">Оплата прошла</h1>
      <p className="mb-10 leading-relaxed text-fg-muted">
        {plan
          ? `Тариф ${plan} активируется в течение минуты.`
          : "Тариф активируется в течение минуты."}{" "}
        Если через несколько минут изменение не отобразилось — напишите на{" "}
        <a
          href="mailto:rivalens@ya.ru"
          className="text-accent underline-offset-4 hover:underline"
        >
          rivalens@ya.ru
        </a>
        .
      </p>
      <Link
        href="/billing"
        className="inline-flex w-fit items-center justify-center rounded-sm border border-line px-4 py-2 text-sm font-medium text-fg transition-colors duration-150 hover:border-fg-muted hover:bg-bg-subtle"
      >
        ← К тарифам
      </Link>
    </>
  );
}

export default function BillingSuccessPage() {
  return (
    <main className="mx-auto flex min-h-[100svh] max-w-3xl flex-col px-6 py-16">
      <div className="flex flex-1 flex-col justify-center">
        <Suspense fallback={null}>
          <SuccessContent />
        </Suspense>
      </div>
      <Footer />
    </main>
  );
}
