"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { login } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const token = await login(email.trim(), password);
      setToken(token);
      router.replace("/");
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6 py-16">
      <h1 className="mb-2 font-serif text-3xl font-semibold">Rivalens</h1>
      <p className="mb-10 text-sm text-fg-muted">
        Мониторинг конкурентов в одном письме.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm">
            Email
          </label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm">
            Пароль
          </label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && (
          <p className="border-l-2 border-accent pl-4 text-sm text-fg-muted">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Входим…" : "Войти"}
        </Button>
      </form>

      <p className="mt-8 text-sm text-fg-muted">
        Нет аккаунта?{" "}
        <Link href="/register" className="text-accent underline-offset-4 hover:underline">
          Зарегистрироваться
        </Link>
      </p>
    </main>
  );
}
