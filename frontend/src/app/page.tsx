"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthGate } from "@/components/AuthGate";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { Landing } from "@/components/Landing";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { OnboardingTour } from "@/components/OnboardingTour";
import { Skeleton } from "@/components/Skeleton";
import { getToken } from "@/lib/auth";
import {
  ApiError,
  createCompetitor,
  deleteCompetitor,
  getPlan,
  listCompetitors,
  setPlan,
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
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  // Skeletons show until the first refresh lands; re-fetches (after
  // add/delete) must not flash the skeleton again.
  const [listLoaded, setListLoaded] = useState(false);
  // Onboarding for new users: shown once, until completed/skipped.
  const [showOnboarding, setShowOnboarding] = useState(false);

  const ONBOARDING_KEY = "onboarding_completed";

  function completeOnboarding() {
    try {
      localStorage.setItem(ONBOARDING_KEY, "true");
    } catch {
      // storage disabled — the tour just shows again next visit
    }
    setShowOnboarding(false);
  }

  async function refresh() {
    try {
      const [competitorList, planInfo] = await Promise.all([
        listCompetitors(),
        getPlan(),
      ]);
      setCompetitors(competitorList);
      setPlanState(planInfo);
      setError(null);
      setListLoaded(true);
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

  useEffect(() => {
    // New user (no completion flag): open the tour on the dashboard.
    try {
      if (localStorage.getItem(ONBOARDING_KEY) !== "true") {
        setShowOnboarding(true);
      }
    } catch {
      // storage unavailable — no tour
    }
    // "Как это работает?" in the Header clears the flag and signals
    // here to reopen the tour in place (no remount on the same route).
    function restartTour() {
      setShowOnboarding(true);
    }
    window.addEventListener("rivalens:restart-tour", restartTour);
    return () =>
      window.removeEventListener("rivalens:restart-tour", restartTour);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !url.trim()) return;
    // Client-side mirror of the backend's URL validation: instant
    // feedback instead of a 422 round trip.
    try {
      const parsed = new URL(url.trim());
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        throw new Error("protocol");
      }
    } catch {
      setError("Проверьте URL: нужен http:// или https://.");
      return;
    }
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
      if (e instanceof ApiError) {
        if (e.status === 422) {
          setError("Проверьте URL: нужен http:// или https://.");
        } else if (e.status === 400) {
          setError("Некорректные данные.");
        } else if (e.status === 500) {
          setError("Что-то пошло не так. Попробуйте позже.");
        } else {
          setError(e.detail);
        }
        return;
      }
      if (e instanceof Error && e.message.startsWith("Network error")) {
        setError("Сервер недоступен. Проверьте соединение.");
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteConfirmed(id: string) {
    setConfirmId(null);
    setDeleting((prev) => new Set(prev).add(id));
    try {
      await deleteCompetitor(id);
      // Optimistic update: no refetch, the row just disappears.
      setCompetitors((prev) => prev.filter((c) => c.id !== id));
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        router.replace("/login");
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
      // The competitor stays in the list — the delete did not happen.
    } finally {
      setDeleting((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  const confirmName =
    competitors.find((c) => c.id === confirmId)?.name ?? "";

  const limitLabel =
    plan === null
      ? ""
      : `${plan.competitors_used} / ${
          plan.competitors_limit === null ? "∞" : plan.competitors_limit
        }`;

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <Header plan={plan ? `Тариф: ${plan.plan}` : null} />

      <h1 className="mb-2 text-4xl font-semibold">Ваши конкуренты</h1>
      {plan && (
        <p className="mb-12 text-sm text-fg-muted">
          Тариф: {plan.plan} ({limitLabel}) —{" "}
          <Link href="/billing" className="text-accent underline-offset-4 hover:underline">
            Сменить тариф
          </Link>
        </p>
      )}

      <form onSubmit={handleAdd} className="mb-10 flex flex-col gap-2 sm:flex-row">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Название конкурента"
          className="sm:w-56"
        />
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://пример.ру"
          className="flex-1"
        />
        <Button type="submit" disabled={busy} className="sm:w-auto">
          Добавить
        </Button>
      </form>

      {error && (
        <p
          role="alert"
          className="mb-8 rounded-sm border border-accent bg-bg-subtle p-3 text-sm text-accent"
        >
          {error}
        </p>
      )}

      {limitHit && (
        <div className="mb-8 border-l-2 border-accent pl-4">
          <p className="font-medium">Лимит тарифа достигнут</p>
          <Link
            href="/billing"
            className="text-sm text-accent underline-offset-4 hover:underline"
          >
            Перейти на Pro →
          </Link>
        </div>
      )}

      {!listLoaded && (
        <div className="space-y-2 border-t border-line pt-4" aria-label="Загрузка">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}

      {listLoaded && competitors.length > 0 && (
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
                  Открыть
                </Link>
                <button
                  type="button"
                  onClick={() => setConfirmId(competitor.id)}
                  disabled={deleting.has(competitor.id)}
                  className="inline-flex items-center justify-center rounded-sm px-3 py-2 text-sm text-fg-muted transition-colors duration-150 hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {deleting.has(competitor.id) ? "Удаляем…" : "Удалить"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {listLoaded && competitors.length === 0 && !error && !limitHit && (
        <p className="border-t border-line pt-8 text-fg-muted">
          Пока нет конкурентов. Добавьте первого — увидите, как работает
          мониторинг.
        </p>
      )}

      {plan?.plan === "free" && (
        <p className="mt-10 border-t border-line pt-4 text-xs text-fg-muted">
          На Free — 2 конкурента. Pro — 10 конкурентов, 490 ₽/мес
          (скидка запуска). Окупается первой сделкой.{" "}
          <Link
            href="/billing"
            className="text-accent underline-offset-4 hover:underline"
          >
            Подробнее
          </Link>
        </p>
      )}

      <Footer />

      <ConfirmDialog
        open={confirmId !== null}
        title="Удалить конкурента?"
        message={`«${confirmName}» — все снапшоты и инсайты будут удалены безвозвратно.`}
        confirmLabel="Удалить"
        variant="danger"
        onConfirm={() => confirmId && void handleDeleteConfirmed(confirmId)}
        onCancel={() => setConfirmId(null)}
      />

      <OnboardingTour
        open={showOnboarding}
        onComplete={completeOnboarding}
        onSkip={completeOnboarding}
      />
    </main>
  );
}

export default function Home() {
  const router = useRouter();
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    // Public landing for anonymous visitors; the dashboard behind it.
    if (!getToken()) {
      setAuthed(false);
      return;
    }
    setAuthed(true);
  }, [router]);

  if (authed === null) {
    return null; // avoid a landing flash before localStorage is read
  }
  if (!authed) {
    return <Landing />;
  }
  return (
    <AuthGate>
      <HomeContent />
    </AuthGate>
  );
}
