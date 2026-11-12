"use client";

import Link from "next/link";

import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";

export default function BillingFailPage() {
  return (
    <main className="mx-auto flex min-h-[100svh] max-w-3xl flex-col px-6 py-16">
      <Header />
      <div className="flex flex-1 flex-col justify-center">
        <h1 className="mb-4 font-serif text-4xl font-semibold">
          Оплата не прошла
        </h1>
        <p className="mb-10 leading-relaxed text-fg-muted">
          Деньги не списаны. Попробуйте снова или выберите другой способ
          оплаты. Если ошибка повторяется — напишите на{" "}
          <a
            href="mailto:rivalens@ya.ru"
            className="text-accent underline-offset-4 hover:underline"
          >
            rivalens@ya.ru
          </a>
          .
        </p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Link
            href="/billing"
            className="inline-flex w-fit items-center justify-center rounded-sm bg-accent px-5 py-2.5 text-sm font-medium text-on-accent transition-colors duration-150 hover:bg-accent-hover"
          >
            Попробовать снова
          </Link>
          <Link
            href="/"
            className="inline-flex w-fit items-center justify-center rounded-sm border border-line px-5 py-2.5 text-sm font-medium text-fg transition-colors duration-150 hover:border-fg-muted hover:bg-bg-subtle"
          >
            ← На главную
          </Link>
        </div>
      </div>
      <Footer />
    </main>
  );
}