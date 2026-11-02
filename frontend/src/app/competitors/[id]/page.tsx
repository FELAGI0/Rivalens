"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { Button } from "@/components/Button";
import {
  checkCompetitor,
  deleteCompetitor,
  getCompetitor,
  listChanges,
  UnauthorizedError,
  type Change,
  type CompetitorDetail,
} from "@/lib/api";

function formatChange(change: Change): {
  label: string;
  emphasis: boolean;
} {
  const p = change.payload;
  switch (change.kind) {
    case "price_added":
      return { label: `Цена: +${String(p.value)}`, emphasis: true };
    case "price_removed":
      return { label: `Цена: −${String(p.value)}`, emphasis: true };
    case "heading_added":
      return { label: `Добавлен раздел: «${String(p.text)}»`, emphasis: false };
    case "heading_removed":
      return { label: `Убран раздел: «${String(p.text)}»`, emphasis: false };
    case "link_added":
      return { label: `Новая ссылка: ${String(p.href)}`, emphasis: false };
    case "link_removed":
      return { label: `Удалена ссылка: ${String(p.href)}`, emphasis: false };
    case "title":
      return {
        label: `${String(p.from)} → ${String(p.to)}`,
        emphasis: false,
      };
    default:
      return { label: `${change.kind}`, emphasis: false };
  }
}

function sortChanges(changes: Change[]): Change[] {
  const rank = (c: Change) => (c.kind.startsWith("price_") ? 0 : 1);
  return [...changes].sort((a, b) => rank(a) - rank(b));
}

function CompetitorPageContent() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const [detail, setDetail] = useState<CompetitorDetail | null>(null);
  const [changes, setChanges] = useState<Change[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      const [competitorDetail, changeList] = await Promise.all([
        getCompetitor(id),
        listChanges(id),
      ]);
      setDetail(competitorDetail);
      setChanges(sortChanges(changeList));
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

  async function handleDeleteConfirmed() {
    setConfirmDelete(false);
    setDeleting(true);
    try {
      await deleteCompetitor(id);
      router.replace("/"); // client-side: no full page reload
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        router.replace("/login");
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(false);
    }
  }

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
            ← К списку
          </Link>
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={deleting}
            className="inline-flex items-center justify-center rounded-sm px-3 py-2 text-sm text-fg-muted transition-colors duration-150 hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleting ? "Удаляем…" : "Удалить конкурента"}
          </button>
          <Button onClick={handleCheckNow} disabled={busy}>
            {busy && <span className="spinner" aria-hidden="true" />}
            {busy ? "Проверяем…" : "Проверить сейчас"}
          </Button>
        </div>
      </div>

      {error && (
        <p className="mb-8 border-l-2 border-accent pl-4 text-sm text-fg-muted">
          {error}
        </p>
      )}

      {!detail && !error && <p className="text-fg-muted">Загрузка…</p>}

      {detail && (
        <>
          <section className="mb-12">
            <h2 className="mb-4 text-sm font-medium uppercase text-fg-muted">
              Страницы
            </h2>
            {detail.pages.length === 0 ? (
              <p className="text-sm text-fg-muted">Страниц пока нет.</p>
            ) : (
              <ul className="divide-y divide-line border-y border-line">
                {detail.pages.map((page) => (
                  <li key={page.id} className="py-3">
                    <span className="font-mono text-sm">{page.url}</span>
                    <span className="ml-3 text-xs uppercase text-fg-muted">
                      {page.kind}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mb-12">
            <h2 className="mb-4 text-sm font-medium uppercase text-fg-muted">
              Последние изменения
            </h2>
            {changes.length === 0 ? (
              <p className="border-y border-line py-8 text-sm text-fg-muted">
                Изменений за последнее время нет. Следующая проверка — по
                расписанию (каждые 6 часов).
              </p>
            ) : (
              <ul className="divide-y divide-line border-t border-line">
                {changes.map((change) => {
                  const { label, emphasis } = formatChange(change);
                  return (
                    <li
                      key={change.id}
                      className="flex items-baseline justify-between gap-4 py-3"
                    >
                      <span
                        className={
                          emphasis
                            ? "text-lg font-semibold text-accent"
                            : "text-sm text-fg"
                        }
                      >
                        {label}
                      </span>
                      <span className="shrink-0 text-xs text-fg-muted">
                        {new Date(change.detected_at).toLocaleString("ru-RU")}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section>
            <h2 className="mb-4 text-sm font-medium uppercase text-fg-muted">
              Инсайты
            </h2>
            {detail.insights.length === 0 ? (
              <p className="border-y border-line py-8 text-sm text-fg-muted">
                Пока нет инсайтов. Первая проверка создаёт снапшот,
                следующая покажет изменения (обычно через 6 часов).
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

      <Footer />

      <ConfirmDialog
        open={confirmDelete}
        title="Удалить конкурента?"
        message={`«${detail?.competitor.name ?? ""}» — все снапшоты и инсайты будут удалены безвозвратно.`}
        confirmLabel="Удалить"
        variant="danger"
        onConfirm={() => void handleDeleteConfirmed()}
        onCancel={() => setConfirmDelete(false)}
      />
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
