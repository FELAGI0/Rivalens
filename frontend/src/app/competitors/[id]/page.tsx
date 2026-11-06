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
  listPriceHistory,
  UnauthorizedError,
  type Change,
  type CompetitorDetail,
  type PriceChange,
  type PriceHistory,
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

function formatHours(from: string, to: string): string {
  const hours = Math.round(
    (new Date(to).getTime() - new Date(from).getTime()) / 3_600_000,
  );
  if (hours >= 1) return `через ${hours} ч.`;
  return "скоро (по расписанию)";
}

function bannerTextFor(result: {
  is_first_check: boolean;
  changes_created: number;
  pages_checked: number;
  pages_failed: number;
  checked_at: string;
  next_check_at: string | null;
}): string {
  const next = result.next_check_at
    ? formatHours(result.checked_at, result.next_check_at)
    : "по расписанию";
  if (result.is_first_check) {
    return "Первый снапшот создан. Пока не с чем сравнивать — изменения " +
      `появятся после следующей проверки (${next}) или когда ` +
      "контент изменится.";
  }
  if (result.changes_created === 0) {
    return `Проверено: ${result.pages_checked} стр., ${new Date(
      result.checked_at,
    ).toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    })}. Изменений нет. Следующая проверка — ${next}.`;
  }
  return `Проверено: ${result.pages_checked} стр., ` +
    `${result.changes_created} изменений, инсайт готов. Прокрутите вниз.`;
}

function parsePrice(value: string): number | null {
  const digits = value.replace(/[^\d]/g, "");
  if (digits === "") return null;
  return Number(digits);
}

type ChartPoint = { date: string; value: number };

function chartPoints(history: PriceHistory): ChartPoint[] {
  // One point per day: the minimum price found that day (the "floor"
  // of the competitor's offer is what the visitor actually sees).
  const points: ChartPoint[] = [];
  for (const point of history.points) {
    const values = point.prices
      .map(parsePrice)
      .filter((v): v is number => v !== null);
    if (values.length === 0) continue;
    points.push({ date: point.date, value: Math.min(...values) });
  }
  return points;
}

function formatDateLabel(date: string): string {
  const [year, month, day] = date.split("-");
  return `${day}.${month}`;
}

function formatPriceChangeDate(date: string): string {
  const [year, month, day] = date.split("-");
  const months = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
  ];
  return `${Number(day)} ${months[Number(month) - 1]}`;
}

type PriceChangeItem = {
  date: string;
  text: string;
  accent: boolean;
};

function buildPriceChangeItems(changes: PriceChange[]): PriceChangeItem[] {
  // A price swap lands as two rows (price_removed + price_added) on the
  // same day. Pair them back into a single «3990 ₽ → 4900 ₽ (поднял)».
  const items: PriceChangeItem[] = [];
  const pending = [...changes];

  while (pending.length > 0) {
    const change = pending.shift();
    if (!change) break;

    const dateLabel = formatPriceChangeDate(change.date);

    if (change.kind === "price_added" && change.from === "") {
      // Look for a removal on the same date to pair with.
      const pairIndex = pending.findIndex(
        (other) =>
          other.date === change.date && other.kind === "price_removed",
      );
      if (pairIndex !== -1) {
        const removed = pending.splice(pairIndex, 1)[0];
        const fromValue = parsePrice(removed.from);
        const toValue = parsePrice(change.to);
        const moved =
          fromValue !== null &&
          toValue !== null &&
          toValue > fromValue
            ? "поднял"
            : "снизил";
        items.push({
          date: change.date,
          text: `${dateLabel}: ${removed.from} → ${change.to} (${moved})`,
          accent: true,
        });
        continue;
      }
      items.push({
        date: change.date,
        text: `${dateLabel}: появилась цена ${change.to}`,
        accent: false,
      });
      continue;
    }

    if (change.kind === "price_removed" && change.to === "") {
      items.push({
        date: change.date,
        text: `${dateLabel}: пропала цена ${change.from}`,
        accent: true,
      });
      continue;
    }

    // Already-paired form straight from the API.
    if (change.from && change.to) {
      const fromValue = parsePrice(change.from);
      const toValue = parsePrice(change.to);
      const moved =
        fromValue !== null && toValue !== null && toValue > fromValue
          ? "поднял"
          : "снизил";
      items.push({
        date: change.date,
        text: `${dateLabel}: ${change.from} → ${change.to} (${moved})`,
        accent: true,
      });
    }
  }

  return items;
}

function PriceChart({ history }: { history: PriceHistory }) {
  const points = chartPoints(history);
  if (points.length === 0) {
    return (
      <p className="border-y border-line py-8 text-sm text-fg-muted">
        Пока нет данных о ценах. Они появятся после нескольких проверок
        страницы с ценами.
      </p>
    );
  }

  const width = 640;
  const height = 200;
  const padding = { top: 12, right: 12, bottom: 24, left: 48 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const values = points.map((p) => p.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  // Degenerate range: give the line some vertical breathing room.
  const span = maxValue - minValue || Math.max(maxValue * 0.1, 1);

  const xStep =
    points.length > 1 ? innerWidth / (points.length - 1) : 0;
  const xFor = (i: number) =>
    points.length > 1
      ? padding.left + i * xStep
      : padding.left + innerWidth / 2;
  const yFor = (value: number) =>
    padding.top +
    innerHeight -
    ((value - minValue) / span) * innerHeight;

  const linePoints = points.map(
    (p, i) => `${xFor(i)},${yFor(p.value)}`,
  );
  const polyline = linePoints.join(" ");

  // 3–4 X labels spread across the points.
  const labelCount = Math.min(4, points.length);
  const labelIndices: number[] = [];
  for (let i = 0; i < labelCount; i++) {
    labelIndices.push(
      Math.round((i * (points.length - 1)) / (labelCount - 1 || 1)),
    );
  }

  // Y axis: min / mid / max.
  const yTicks = [minValue, (minValue + maxValue) / 2, maxValue];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-auto w-full"
      role="img"
      aria-label="График изменения цены"
    >
      {/* Y axis labels */}
      {yTicks.map((tick) => (
        <text
          key={tick}
          x={padding.left - 8}
          y={yFor(tick) + 4}
          textAnchor="end"
          className="fill-current text-fg-muted"
          style={{ fontSize: 11 }}
        >
          {Math.round(tick).toLocaleString("ru-RU")}
        </text>
      ))}
      {/* X axis labels */}
      {labelIndices.map((i) => (
        <text
          key={i}
          x={xFor(i)}
          y={height - 6}
          textAnchor="middle"
          className="fill-current text-fg-muted"
          style={{ fontSize: 11 }}
        >
          {formatDateLabel(points[i].date)}
        </text>
      ))}
      {/* The line */}
      <polyline
        points={polyline}
        fill="none"
        stroke="#E85D3D"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* The dots */}
      {points.map((p, i) => (
        <circle
          key={p.date}
          cx={xFor(i)}
          cy={yFor(p.value)}
          r={3}
          fill="#E85D3D"
        />
      ))}
    </svg>
  );
}

function CompetitorPageContent() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const [detail, setDetail] = useState<CompetitorDetail | null>(null);
  const [changes, setChanges] = useState<Change[]>([]);
  const [priceHistory, setPriceHistory] = useState<PriceHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [checkBanner, setCheckBanner] = useState<string | null>(null);
  const [checkBannerAccent, setCheckBannerAccent] = useState(false);
  const [checkBannerError, setCheckBannerError] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      const [competitorDetail, changeList, history] = await Promise.all([
        getCompetitor(id),
        listChanges(id),
        listPriceHistory(id),
      ]);
      setDetail(competitorDetail);
      setChanges(sortChanges(changeList));
      setPriceHistory(history);
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

  useEffect(() => {
    // The banner self-destructs after 10 seconds.
    if (checkBanner === null) return;
    const timer = setTimeout(() => setCheckBanner(null), 10_000);
    return () => clearTimeout(timer);
  }, [checkBanner]);

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
    setCheckBanner(null); // a new check replaces the old banner
    setCheckBannerError(false);
    try {
      const result = await checkCompetitor(id);
      await refresh();
      setError(null);
      if (result.pages_failed >= result.pages_checked && result.pages_checked > 0) {
        // Every fetch failed: the site is likely down or unreachable.
        setCheckBanner(
          `Не удалось загрузить ни одну страницу конкурента ` +
            `(${result.pages_checked} из ${result.pages_checked}). ` +
            "Сайт недоступен или отдаёт ошибку — проверьте URL. " +
            "Повторим по расписанию.",
        );
        setCheckBannerError(true);
        setCheckBannerAccent(false);
      } else {
        if (result.pages_failed > 0) {
          setCheckBanner(
            `Часть страниц не загрузилась (${result.pages_failed} из ` +
              `${result.pages_checked}). ${bannerTextFor(result)}`,
          );
        } else {
          setCheckBanner(bannerTextFor(result));
        }
        setCheckBannerError(false);
        setCheckBannerAccent(result.changes_created > 0);
      }
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
        <p
          role="alert"
          className="mb-8 rounded-sm border border-accent bg-bg-subtle p-3 text-sm text-accent"
        >
          {error}
        </p>
      )}

      {checkBanner && (
        <p
          role={checkBannerError ? "alert" : "status"}
          className={`mb-8 rounded-sm border px-4 py-3 text-sm leading-relaxed ${
            checkBannerError
              ? "border-accent bg-bg-subtle text-accent"
              : checkBannerAccent
                ? "border-accent bg-bg-subtle text-accent"
                : "border-line bg-bg-subtle text-fg-muted"
          }`}
        >
          {checkBanner}
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
                Изменений за последнее время нет. Следующая проверка —{" "}
                {detail.next_check_at
                  ? `${new Date(detail.next_check_at).toLocaleString("ru-RU")}.`
                  : "по расписанию."}
                {detail.total_checks > 0 &&
                  detail.last_checked_at &&
                  ` Проверено ${detail.total_checks} раз, последняя — ${new Date(
                    detail.last_checked_at,
                  ).toLocaleString("ru-RU")}.`}
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

          <section className="mb-12">
            <h2 className="mb-4 text-sm font-medium uppercase text-fg-muted">
              История цен (за 30 дней)
            </h2>
            {priceHistory &&
            (priceHistory.points.length > 0 ||
              priceHistory.changes.length > 0) ? (
              <>
                <div className="border-y border-line py-4">
                  <PriceChart history={priceHistory} />
                </div>
                {priceHistory.changes.length > 0 && (
                  <ul className="divide-y divide-line border-b border-line">
                    {buildPriceChangeItems(priceHistory.changes).map(
                      (item, index) => (
                        <li key={index} className="py-3 text-sm">
                          {item.accent ? (
                            <span className="text-accent">{item.text}</span>
                          ) : (
                            <span className="text-fg-muted">{item.text}</span>
                          )}
                        </li>
                      ),
                    )}
                  </ul>
                )}
              </>
            ) : (
              <p className="border-y border-line py-8 text-sm text-fg-muted">
                Пока нет данных о ценах. Они появятся после нескольких
                проверок страницы с ценами.
              </p>
            )}
          </section>

          <section>
            <h2 className="mb-4 text-sm font-medium uppercase text-fg-muted">
              Инсайты
            </h2>
            {detail.insights.length === 0 ? (
              <p className="border-y border-line py-8 text-sm text-fg-muted">
                Пока изменений нет. Мы проверяем по расписанию
                {detail.next_check_at
                  ? ` (следующая — ${new Date(
                      detail.next_check_at,
                    ).toLocaleString("ru-RU")})`
                  : ""}
                — если конкурент что-то изменит, пришлём на почту и покажем
                здесь.
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
