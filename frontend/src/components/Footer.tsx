import Link from "next/link";

export function Footer() {
  return (
    <footer className="mt-16 border-t border-line pt-6 pb-2 text-sm text-fg-muted">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p>© {new Date().getFullYear()} Rivalens</p>
        <nav className="flex gap-6">
          <Link
            href="/billing"
            className="underline-offset-4 transition-colors duration-150 hover:text-fg hover:underline"
          >
            Тарифы
          </Link>
          <Link
            href="/services"
            className="underline-offset-4 transition-colors duration-150 hover:text-fg hover:underline"
          >
            О сервисе
          </Link>
          <Link
            href="/requisites"
            className="underline-offset-4 transition-colors duration-150 hover:text-fg hover:underline"
          >
            Реквизиты
          </Link>
        </nav>
      </div>
      <div className="mt-4 flex flex-col gap-1 sm:flex-row sm:gap-6">
        <span className="uppercase tracking-wide">Поддержка</span>
        <a
          href="https://t.me/olll07"
          className="underline-offset-4 transition-colors duration-150 hover:text-fg hover:underline"
          target="_blank"
          rel="noopener noreferrer"
        >
          Telegram
        </a>
        <a
          href="mailto:rivalens@ya.ru"
          className="underline-offset-4 transition-colors duration-150 hover:text-fg hover:underline"
        >
          Email
        </a>
        <span className="text-xs text-fg-muted sm:ml-auto">
          Возврат и вопросы по оплате — на эти же контакты
        </span>
      </div>
    </footer>
  );
}
