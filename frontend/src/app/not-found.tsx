import Link from "next/link";

export const metadata = {
  title: "Страница не найдена — Rivalens",
};

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[100svh] max-w-3xl flex-col justify-center px-6 py-16">
      <p className="mb-4 font-serif text-6xl font-semibold text-accent">404</p>
      <h1 className="mb-4 font-serif text-3xl font-semibold">
        Страница не найдена
      </h1>
      <p className="mb-10 max-w-md leading-relaxed text-fg-muted">
        Такой страницы нет или она переехала. Проверьте адрес — или вернитесь
        к конкурентам.
      </p>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Link
          href="/"
          className="inline-flex w-fit items-center justify-center rounded-sm bg-accent px-5 py-2.5 text-sm font-medium text-on-accent transition-colors duration-150 hover:bg-accent-hover"
        >
          ← На главную
        </Link>
        <a
          href="mailto:rivalens@ya.ru"
          className="inline-flex w-fit items-center justify-center rounded-sm border border-line px-5 py-2.5 text-sm font-medium text-fg transition-colors duration-150 hover:border-fg-muted hover:bg-bg-subtle"
        >
          Написать в поддержку
        </a>
      </div>
    </main>
  );
}