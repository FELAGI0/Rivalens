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
        Something went wrong
      </h1>
      <p className="mb-6 border-l-2 border-accent pl-4 text-sm text-fg-muted">
        {error.message || "Unexpected error"}
      </p>
      <p className="mb-8 text-sm text-fg-muted">
        Check that the backend is reachable, then try again. If the problem
        persists, try logging out and back in.
      </p>
      <button
        onClick={reset}
        className="rounded-sm bg-accent px-4 py-2 text-sm font-medium text-on-accent transition-colors duration-150 hover:bg-accent-hover"
      >
        Try again
      </button>
    </main>
  );
}
