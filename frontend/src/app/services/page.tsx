import Link from "next/link";

export const metadata = {
  title: "О сервисе — Rivalens",
  description: "Подробное описание услуг Rivalens: что делает сервис, как работает, что входит в тариф",
};

const STEPS = [
  "Вы добавляете URL конкурента в личном кабинете.",
  "Мы проверяем его страницы каждые 6 часов (на тарифе Pro) или раз в день (на Free).",
  "Если контент изменился — мы сравниваем с предыдущей версией, отправляем изменения в языковую модель и получаем краткий вывод.",
  "Вы получаете письмо с описанием изменения и интерпретацией. Например: «Конкурент снизил цену на 19%. Ваш пакет дороже — уязвимость для новых клиентов».",
];

const PLANS = [
  {
    name: "Free",
    description:
      "2 конкурента, проверка раз в день, email-уведомления.",
  },
  {
    name: "Pro (490 ₽/мес)",
    description:
      "10 конкурентов, проверка каждые 6 часов, история цен за 30 дней, email-уведомления.",
  },
  {
    name: "Business (1990 ₽/мес)",
    description:
      "Без лимита конкурентов, приоритетная поддержка, сводка по каждому аккаунту.",
  },
];

const NOT_DOING = [
  "Не собирает персональные данные посетителей сайтов конкурентов.",
  "Не взламывает сайты, не обходит авторизацию, не получает доступ к закрытым разделам.",
  "Не хранит сырой HTML дольше 90 дней.",
  "Не передаёт данные третьим лицам, кроме обработки через LLM (для генерации вывода).",
];

export default function ServicesPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="mb-8 text-4xl font-semibold">О сервисе Rivalens</h1>

      <div className="space-y-14 border-y border-line py-14">
        {/* Что делает */}
        <section>
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-fg-muted">
            Что делает Rivalens
          </h2>
          <p className="leading-relaxed">
            Rivalens — это сервис мониторинга сайтов конкурентов. Мы
            автоматически отслеживаем изменения на страницах ваших
            конкурентов (цены, новые разделы, вакансии, новые страницы) и
            присылаем вам готовый вывод на email — что именно изменилось и
            что это значит для вашего бизнеса.
          </p>
        </section>

        {/* Как это работает */}
        <section>
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-fg-muted">
            Как это работает
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

        {/* Что входит в тариф */}
        <section>
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-fg-muted">
            Что входит в тариф
          </h2>
          <dl className="divide-y divide-line border-y border-line">
            {PLANS.map((plan) => (
              <div key={plan.name} className="py-5 md:flex md:gap-8">
                <dt className="mb-1 font-medium md:mb-0 md:w-40">
                  {plan.name}
                </dt>
                <dd className="leading-relaxed text-fg-muted">
                  {plan.description}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        {/* Что сервис НЕ делает */}
        <section>
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-fg-muted">
            Что сервис НЕ делает
          </h2>
          <ul className="divide-y divide-line border-y border-line">
            {NOT_DOING.map((item) => (
              <li key={item} className="py-5 leading-relaxed">
                {item}
              </li>
            ))}
          </ul>
        </section>

        {/* Технические требования */}
        <section>
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-fg-muted">
            Технические требования
          </h2>
          <p className="leading-relaxed">
            Нужен только браузер и email. Ничего устанавливать не нужно.
            Сервис работает в облаке.
          </p>
        </section>

        {/* Возврат */}
        <section>
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-fg-muted">
            Возврат
          </h2>
          <p className="leading-relaxed">
            Если сервис не подошёл — вернём деньги в течение 14 дней
            после оплаты без вопросов. Напишите на{" "}
            <a
              href="mailto:rivalens@ya.ru"
              className="text-accent underline-offset-4 hover:underline"
            >
              rivalens@ya.ru
            </a>
            .
          </p>
        </section>

        {/* Контакты */}
        <section>
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-fg-muted">
            Контакты
          </h2>
          <p className="leading-relaxed">
            Email:{" "}
            <a
              href="mailto:rivalens@ya.ru"
              className="text-accent underline-offset-4 hover:underline"
            >
              rivalens@ya.ru
            </a>
            <br />
            Реквизиты:{" "}
            <Link
              href="/requisites"
              className="text-accent underline-offset-4 hover:underline"
            >
              /requisites
            </Link>
          </p>
        </section>
      </div>

      <p className="mt-10">
        <Link
          href="/"
          className="inline-flex items-center justify-center rounded-sm border border-line px-4 py-2 text-sm font-medium text-fg transition-colors duration-150 hover:border-fg-muted hover:bg-bg-subtle"
        >
          ← На главную
        </Link>
      </p>
    </main>
  );
}
