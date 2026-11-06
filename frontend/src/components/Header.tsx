"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/Button";
import { clearToken } from "@/lib/auth";

export function Header({ plan }: { plan?: string | null }) {
  const router = useRouter();

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  function handleRestartTour() {
    // Replay the onboarding: clear the completion flag and notify the
    // dashboard (custom event) to reopen the tour in place.
    try {
      localStorage.removeItem("onboarding_completed");
    } catch {
      // storage disabled — the tour will not persist completion anyway
    }
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("rivalens:restart-tour"));
    }
    router.push("/");
  }

  return (
    <header className="mb-12 flex items-center justify-between border-b border-line pb-4">
      <Link href="/" className="font-serif text-2xl font-semibold text-fg">
        Rivalens
      </Link>
      <div className="flex items-center gap-3">
        {plan && (
          <span className="hidden text-sm text-fg-muted sm:inline">
            {plan}
          </span>
        )}
        <button
          type="button"
          onClick={handleRestartTour}
          className="hidden text-sm text-fg-muted underline-offset-4 transition-colors duration-150 hover:text-fg hover:underline sm:inline"
        >
          Как это работает?
        </button>
        <ThemeToggle />
        <Button variant="ghost" onClick={handleLogout} className="px-3 py-1.5">
          Выйти
        </Button>
      </div>
    </header>
  );
}
