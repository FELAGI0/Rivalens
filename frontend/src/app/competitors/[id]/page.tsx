"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { Button } from "@/components/Button";
import { Skeleton } from "@/components/Skeleton";
import {
  ApiError,
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

/** Currency symbol that follows the number, e.g. "4 900 ₽" -> "₽". */
function priceCurrency(value: string): string {
  const match = value.match(/[₽$€]/);
  return match ? match[0] : "";
}

type ChartPoint = { date: string; value: number; currency: string };

function chartPoints(history: PriceHistory): ChartPoint[] {
  // One point per day: the minimum price found that day (the "floor"
  // of the competitor's offer is what the visitor actually sees).
  const points: ChartPoint[] = [];
  for (const point of history.points) {
    const parsed: { value: number; currency: string }[] = [];
    for (const raw of point.prices) {
      const value = parsePrice(raw);
      if (value !== null) {
        parsed.push({ value, currency: priceCurrency(raw) });
      }
    }
    if (parsed.length === 0) continue;
    const min = parsed.reduce((a, b) => (b.value < a.value ? b : a));
    points.push({ date: point.date, value: min.value, currency: min.currency });
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

function PriceChart({ history, animate }: { history: PriceHistory; animate: boolean }) {
  const points = chartPoints(history);
  // Hovered / tapped point: drives the tooltip. Kept above the early
  // return so the hook order never changes.
  const [active, setActive] = useState<number | null>(null);

  if (points.length === 0) {
    return (
      <p className="border-y border-line py-8 text-sm text-fg-muted">
        Пока нет данных о ценах. Они появятся после нескольких проверок
        страницы с ценами.
      </p>
    );
  }

  const shouldDraw = animate && points.length > 1;

  // The plot is drawn in SVG; axis labels are HTML around it. SVG text
  // scales with the viewBox, which made 11px labels render at 5.6px on a
  // 375px screen. HTML labels keep their own size at every width.
  const width = 560;
  const height = 180;
  const padding = { top: 8, right: 8 };

  const values = points.map((p) => p.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  // Degenerate range: give the line some vertical breathing room.
  const span = maxValue - minValue || Math.max(maxValue * 0.1, 1);

  const innerWidth = width - padding.right;
  const innerHeight = height - padding.top;

  const xStep = points.length > 1 ? innerWidth / (points.length - 1) : 0;
  const xFor = (i: number) =>
    points.length > 1 ? i * xStep : innerWidth / 2;
  const yFor = (value: number) =>
    padding.top + innerHeight - ((value - minValue) / span) * innerHeight;

  const polyline = points.map((p, i) => `${xFor(i)},${yFor(p.value)}`).join(" ");

  // 3–4 X labels spread across the points.
  const labelCount = Math.min(4, points.length);
  const labelIndices: number[] = [];
  for (let i = 0; i < labelCount; i++) {
    labelIndices.push(
      Math.round((i * (points.length - 1)) / (labelCount - 1 || 1)),
    );
  }

  const yTicks = [maxValue, (minValue + maxValue) / 2, minValue];
  const currency = points[0]?.currency ?? "";
  const formatValue = (v: number) => Math.round(v).toLocaleString("ru-RU");

  const activePoint = active === null ? null : points[active];

  return (
    <figure className="m-0">
      <div className="flex gap-2">
        {/* Y axis: three HTML labels, aligned with the plot's top/mid/base. */}
        <div
          className="flex shrink-0 flex-col justify-between py-1 text-right text-xs tabular-nums text-fg-muted"
          aria-hidden="true"
        >
          {yTicks.map((tick, i) => (
            <span key={i}>{formatValue(tick)}</span>
          ))}
        </div>

        <div className="relative min-w-0 flex-1">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="block h-auto w-full"
            role="img"
            aria-label={`График изменения цены: от ${formatValue(
              minValue,
            )} до ${formatValue(maxValue)} ${currency}`}
          >
            <polyline
              points={polyline}
              fill="none"
              stroke="#E85D3D"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              className={shouldDraw ? "chart-line-draw" : undefined}
              style={shouldDraw ? { animationDelay: "200ms" } : undefined}
            />
            {points.map((p, i) => (
              <circle
                key={p.date}
                cx={xFor(i)}
                cy={yFor(p.value)}
                r={active === i ? 5 : 3}
                fill="#E85D3D"
                style={{ transition: "r 120ms ease-out" }}
              />
            ))}
            {/* Invisible hit areas: a 3px dot is far too small for a
                finger, so each point gets a 24-unit target (≈14px). */}
            {points.map((p, i) => (
              <circle
                key={`hit-${p.date}`}
                cx={xFor(i)}
                cy={yFor(p.value)}
                r={14}
                fill="transparent"
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onClick={() => setActive(i)}
                style={{ cursor: "pointer" }}
              />
            ))}
          </svg>

          {activePoint && active !== null && (
            <div
              role="tooltip"
              className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-sm border border-line bg-bg px-2 py-1 text-xs shadow-none"
              style={{
                left: `${(xFor(active) / width) * 100}%`,
                top: `${(yFor(activePoint.value) / height) * 100}%`,
                marginTop: "-10px",
              }}
            >
              <span className="whitespace-nowrap text-fg">
                {formatDateLabel(activePoint.date)} —{" "}
                <span className="tabular-nums">
                  {formatValue(activePoint.value)} {activePoint.currency}
                </span>
              </span>
            </div>
          )}
        </div>
      </div>

      {/* X axis: HTML row below the plot, same width as the plot. */}
      <div className="mt-2 flex justify-between pl-11 text-xs tabular-nums text-fg-muted">
        {labelIndices.map((i) => (
          <span key={i}>{formatDateLabel(points[i].date)}</span>
        ))}
      </div>

      <figcaption className="mt-3 pl-11 text-xs text-fg-muted">
        Минимум за день. Ниже — {formatValue(minValue)} {currency}, выше —{" "}
        {formatValue(maxValue)} {currency}. Наведите на точку, чтобы увидеть
        дату.
      </figcaption>
    </figure>
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
  // Rate-limit countdown (CP27): seconds until the check is allowed
  // again; the button stays disabled while it ticks. Separate from
  // checkBanner so the two lifecycles don't fight each other.
  const [retrySeconds, setRetrySeconds] = useState(0);
  const [countdownActive, setCountdownActive] = useState(false);
  // Staggered entrance animations run on the first load only — a
  // refresh after "Check now" must not re-animate the whole page.
  const [animated, setAnimated] = useState(false);

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
      setAnimated(true);
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
    // The banner self-destructs after 10 seconds — except the rate
    // countdown, which lives exactly as long as its countdown.
    if (checkBanner === null || countdownActive) return;
    const timer = setTimeout(() => setCheckBanner(null), 10_000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkBanner, countdownActive]);

  useEffect(() => {
    // Rate-limit countdown: ticks down every second. When it reaches
    // 0 the banner text clears itself (the flag says it's a countdown
    // banner, not an ordinary 10s one).
    if (retrySeconds <= 0) return;
    const timer = setTimeout(() => setRetrySeconds((s) => s - 1), 1_000);
    return () => clearTimeout(timer);
  }, [retrySeconds]);

  // Countdown banner text recomputed from retrySeconds while active.
  useEffect(() => {
    if (retrySeconds === 0 && countdownActive) {
      setCountdownActive(false);
      setCheckBanner(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retrySeconds, countdownActive]);

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
    setCountdownActive(false);
    try {
      const result = await checkCompetitor(id);
      await refresh();
      setError(null);
      // Red (error) banner ONLY when the fetch actually failed and
      // nothing was saved: pages_failed > 0 and no new snapshots.
      if (
        result.pages_failed > 0 &&
        result.pages_failed >= result.pages_checked &&
        result.pages_checked > 0 &&
        result.snapshots_created === 0
      ) {
        setCheckBanner(
          `Не удалось загрузить ни одну страницу конкурента ` +
            `(${result.pages_checked}). ` +
            "Сайт недоступен или отдаёт ошибку — проверьте URL. " +
            "Повторим по расписанию.",
        );
        setCheckBannerError(true);
        setCheckBannerAccent(false);
      } else {
        if (result.pages_failed > 0 && result.pages_checked > 0) {
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
      if (e instanceof ApiError && e.status === 429) {
        // Rate limit: start the countdown, keep the button disabled.
        const seconds = e.retryAfter ?? 60;
        setRetrySeconds(seconds);
        setCountdownActive(true);
        setCheckBanner(
          `Слишком частые проверки. Следующая попытка через ${seconds} сек.`,
        );
        setCheckBannerError(false);
        setCheckBannerAccent(false);
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
          <Button
            onClick={handleCheckNow}
            disabled={busy || countdownActive}
          >
            {busy && <span className="spinner" aria-hidden="true" />}
            {busy
              ? "Проверяем…"
              : countdownActive
                ? `Подождите ${retrySeconds} сек.`
                : "Проверить сейчас"}
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
          {countdownActive
            ? `Слишком частые проверки. Следующая попытка через ${retrySeconds} сек.`
            : checkBanner}
        </p>
      )}

      {!detail && !error && (
        <div className="space-y-3" aria-label="Загрузка">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

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
                {changes.map((change, i) => {
                  const { label, emphasis } = formatChange(change);
                  // Staggered entrance, first load only: 40ms per row,
                  // capped at 300ms so long lists don't keep the user
                  // waiting.
                  const delay = animated ? Math.min(i * 40, 300) : 0;
                  return (
                    <li
                      key={change.id}
                      className={`flex items-baseline justify-between gap-4 py-3 ${
                        delay > 0 ? "animate-fade-up" : ""
                      }`}
                      style={delay > 0 ? { animationDelay: `${delay}ms` } : undefined}
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
                  <PriceChart history={priceHistory} animate={animated} />
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
                {detail.insights.map((insight, i) => {
                  const delay = animated ? Math.min(i * 40, 300) : 0;
                  return (
                    <li
                      key={insight.id}
                      className={`border-b border-line py-6 md:flex md:gap-8 ${
                        delay > 0 ? "animate-fade-up" : ""
                      }`}
                      style={delay > 0 ? { animationDelay: `${delay}ms` } : undefined}
                    >
                      <p className="mb-2 shrink-0 text-xs text-fg-muted md:mb-0 md:w-36 md:pt-1">
                        {new Date(insight.created_at).toLocaleString("ru-RU")}
                      </p>
                      <p className="leading-relaxed">{insight.summary}</p>
                    </li>
                  );
                })}
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
