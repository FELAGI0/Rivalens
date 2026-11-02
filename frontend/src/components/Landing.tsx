import Link from "next/link";

import { Button } from "@/components/Button";
import { Footer } from "@/components/Footer";

function IconPrice() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-accent"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M14.5 9.5c-.5-1-1.5-1.5-2.5-1.5-1.4 0-2.5.9-2.5 2s1 1.7 2.5 2 2.5.9 2.5 2-1.1 2-2.5 2c-1 0-2-.5-2.5-1.5" />
      <path d="M12 6v2M12 16v2" />
    </svg>
  );
}

function IconPage() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-accent"
      aria-hidden="true"
    >
      <path d="M6 3h9l4 4v14H6z" />
      <path d="M15 3v4h4" />
      <path d="M9 12h7M9 16h5" />
    </svg>
  );
}

function IconJobs() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-accent"
      aria-hidden="true"
    >
      <rect x="3" y="7" width="18" height="13" rx="1" />
      <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
      <path d="M3 12h18" />
    </svg>
  );
}

const FEATURES = [
  {
    icon: IconPrice,
    title: "Цены",
    text: "Появление и исчезновение цен, спецпредложений и новых пакетов на страницах конкурентов.",
  },
  {
    icon: IconPage,
    title: "Новые страницы и разделы",
    text: "Запуск новых продуктов, лендингов, разделов «Тарифы» и «Контакты» — сразу после публикации.",
  },
  {
    icon: IconJobs,
    title: "Вакансии",
    text: "Новые вакансии конкурента — сигнал роста команды и смены фокуса разработки.",
  },
];

const STEPS = [
  "Добавьте конкурента — просто URL его сайта.",
  "Мы проверяем сайт каждые 6 часов и сравниваем со вчерашним состоянием.",
  "Если что-то изменилось — вы получаете готовый вывод на почту.",
];

const PLANS = [
  {
    name: "Free",
    price: "$0",
    features: "2 конкурента, проверка раз в день",
  },
  {
    name: "Pro",
    price: "$9/мес (~900 ₽)",
    features: "10 конкурентов, каждые 6 часов",
  },
  {
    name: "Business",
    price: "$29/мес (~2900 ₽)",
    features: "Без лимита конкурентов",
  },
];

export function Landing() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <header className="mb-20 flex items-center justify-between border-b border-line pb-4">
        <p className="font-serif text-2xl font-semibold text-fg">Rivalens</p>
        <nav className="flex items-center gap-4">
          <Link
            href="/login"
            className="text-sm text-fg-muted transition-colors duration-150 hover:text-fg"
          >
            Войти
          </Link>
          <Link
            href="/register"
            className="rounded-sm border border-line px-4 py-1.5 text-sm font-medium text-fg transition-colors duration-150 hover:border-fg-muted hover:bg-bg-subtle"
          >
            Регистрация
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="mb-24">
        <h1 className="mb-6 max-w-2xl font-serif text-4xl font-semibold leading-tight md:text-5xl">
          Следим за конкурентами. Присылаем выводы, а не сырые диффы.
        </h1>
        <p className="mb-10 max-w-xl leading-relaxed text-fg-muted">
          Rivalens каждый день проверяет сайты конкурентов: цены, новые
          страницы, вакансии. Если что-то изменилось — объясняем на русском
          и присылаем на почту.
        </p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Link
            href="/register"
            className="inline-flex items-center justify-center rounded-sm bg-accent px-6 py-3 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover"
          >
            Попробовать бесплатно
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-sm border border-line px-6 py-3 text-sm font-medium text-fg transition-colors duration-150 hover:border-fg-muted hover:bg-bg-subtle"
          >
            Войти
          </Link>
        </div>
      </section>

      {/* Что мониторим */}
      <section className="mb-24">
        <h2 className="mb-10 text-sm font-medium uppercase tracking-wide text-fg-muted">
          Что мониторим
        </h2>
        <div className="grid gap-10 md:grid-cols-3">
          {FEATURES.map((feature) => (
            <div key={feature.title}>
              <div className="mb-4">
                <feature.icon />
              </div>
              <h3 className="mb-2 font-medium">{feature.title}</h3>
              <p className="text-sm leading-relaxed text-fg-muted">
                {feature.text}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Пример инсайта */}
      <section className="mb-24">
        <h2 className="mb-10 text-sm font-medium uppercase tracking-wide text-fg-muted">
          Пример инсайта
        </h2>
        <figure className="border-y border-line py-10 md:px-8">
          <blockquote className="mb-6 max-w-2xl font-serif text-xl leading-relaxed md:text-2xl">
            «На главной Habr ротация ленты: ушли статьи про AI-генерацию
            ассетов, вместо них — тексты про SEO под нейросети и
            «Энтропию индустрии». Смещение интереса аудитории — от научпопа
            к AI-SEO/LLM-видимости.»
          </blockquote>
          <figcaption className="text-sm text-fg-muted">
            Rivalens, 2 ноября 2026, конкурент: habr.com
          </figcaption>
        </figure>
      </section>

      {/* Как работает */}
      <section className="mb-24">
        <h2 className="mb-10 text-sm font-medium uppercase tracking-wide text-fg-muted">
          Как работает
        </h2>
        <ol className="divide-y divide-line border-y border-line">
          {STEPS.map((step, index) => (
            <li key={step} className="flex gap-6 py-5">
              <span className="shrink-0 font-serif text-2xl text-accent">
                {index + 1}
              </span>
              <p className="pt-1 leading-relaxed">{step}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Тарифы */}
      <section className="mb-16">
        <h2 className="mb-10 text-sm font-medium uppercase tracking-wide text-fg-muted">
          Тарифы
        </h2>
        <div className="grid gap-10 md:grid-cols-3">
          {PLANS.map((p) => (
            <div key={p.name}>
              <h3 className="mb-1 font-serif text-xl font-semibold">
                {p.name}
              </h3>
              <p className="mb-2 text-lg font-semibold">{p.price}</p>
              <p className="text-sm text-fg-muted">{p.features}</p>
            </div>
          ))}
        </div>
        <div className="mt-10">
          <Link
            href="/register"
            className="inline-flex items-center justify-center rounded-sm bg-accent px-6 py-3 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover"
          >
            Начать бесплатно
          </Link>
        </div>
      </section>

      <Footer />
    </main>
  );
}
