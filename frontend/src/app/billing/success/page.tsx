import Link from "next/link";

export const metadata = {
  title: "Оплата прошла — Rivalens",
};

export default function BillingSuccessPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6 py-16">
      <h1 className="mb-4 text-4xl font-semibold">Оплата прошла</h1>
      <p className="mb-10 leading-relaxed text-fg-muted">
        Тариф Pro активируется в течение минуты. Если через несколько
        минут тариф всё ещё Free — напишите на{" "}
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
    </main>
  );
}
