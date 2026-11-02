import Link from "next/link";

export const metadata = {
  title: "Реквизиты — Rivalens",
  description: "Реквизиты самозанятого для оплаты через ЮKassa",
};

export default function RequisitesPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="mb-8 text-4xl font-semibold">Реквизиты</h1>

      <div className="border-y border-line py-8">
        <dl className="space-y-4">
          <div className="md:flex md:gap-8">
            <dt className="mb-1 text-sm text-fg-muted md:mb-0 md:w-56">
              Форма оказания услуг
            </dt>
            <dd>Сервис Rivalens предоставляется самозанятым.</dd>
          </div>
          <div className="md:flex md:gap-8">
            <dt className="mb-1 text-sm text-fg-muted md:mb-0 md:w-56">ФИО</dt>
            <dd>Мирошниченко Артём Николаевич</dd>
          </div>
          <div className="md:flex md:gap-8">
            <dt className="mb-1 text-sm text-fg-muted md:mb-0 md:w-56">ИНН</dt>
            <dd className="font-mono">312731467617</dd>
          </div>
          <div className="md:flex md:gap-8">
            <dt className="mb-1 text-sm text-fg-muted md:mb-0 md:w-56">Email</dt>
            <dd>
              <a
                href="mailto:rivalens@ya.ru"
                className="text-accent underline-offset-4 hover:underline"
              >
                rivalens@ya.ru
              </a>
            </dd>
          </div>
          <div className="md:flex md:gap-8">
            <dt className="mb-1 text-sm text-fg-muted md:mb-0 md:w-56">
              Налоговый режим
            </dt>
            <dd>Налог на профессиональный доход (НПД)</dd>
          </div>
        </dl>
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
