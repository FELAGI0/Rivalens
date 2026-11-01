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
        <ThemeToggle />
        <Button variant="ghost" onClick={handleLogout} className="px-3 py-1.5">
          Logout
        </Button>
      </div>
    </header>
  );
}
