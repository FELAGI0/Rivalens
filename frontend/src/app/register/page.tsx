"use client";

import { useState } from "react";
import Link from "next/link";

import { login, register } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await register(email.trim(), password);
      // Log in right away to get the token.
      const token = await login(email.trim(), password);
      setToken(token);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-md p-6">
      <h1 className="mb-6 text-3xl font-bold">Rivalens</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="email" className="mb-1 block text-sm">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded border p-2"
            required
          />
        </div>
        <div>
          <label htmlFor="password" className="mb-1 block text-sm">
            Password (min 8 chars)
          </label>
          <input
            id="password"
            type="password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded border p-2"
            required
          />
        </div>
        {error && (
          <p className="rounded border border-red-300 bg-red-50 p-3 text-red-700">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-blue-600 p-2 text-white disabled:opacity-50"
        >
          {busy ? "Creating…" : "Register"}
        </button>
      </form>

      <p className="mt-4 text-sm text-gray-600">
        Already registered?{" "}
        <Link href="/login" className="text-blue-600 underline">
          Sign in
        </Link>
      </p>
    </main>
  );
}
