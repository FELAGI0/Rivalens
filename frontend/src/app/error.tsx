"use client";

/** Global error boundary: friendly UI instead of a white screen. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto max-w-md px-6 py-24">
      <h1 className="mb-4 font-serif text-2xl font-semibold">
        Что-то пошло не так
      </h1>
      <p className="mb-6 border-l-2 border-accent pl-4 text-sm text-fg-muted">
        {error.message || "Неожиданная ошибка"}
      </p>
      <p className="mb-8 text-sm text-fg-muted">
        Проверьте, что сервер доступен, и попробуйте ещё раз. Если проблема
        повторяется — выйдите из аккаунта и войдите заново.
      </p>
      <button
        onClick={reset}
        className="rounded-sm bg-accent px-4 py-2 text-sm font-medium text-on-accent transition-colors duration-150 hover:bg-accent-hover"
      >
        Попробовать снова
      </button>
    </main>
  );
}
