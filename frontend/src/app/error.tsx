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
    <main className="mx-auto max-w-md p-6">
      <h1 className="mb-4 text-2xl font-bold">Something went wrong</h1>
      <p className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-red-700">
        {error.message || "Unexpected error"}
      </p>
      <p className="mb-6 text-sm text-gray-600">
        Check that the backend is reachable, then try again. If the problem
        persists, try logging out and back in.
      </p>
      <button
        onClick={reset}
        className="rounded bg-blue-600 p-2 text-white hover:bg-blue-700"
      >
        Try again
      </button>
    </main>
  );
}
