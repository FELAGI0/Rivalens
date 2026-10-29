"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { clearToken } from "@/lib/auth";

export function Header() {
  const router = useRouter();

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <header className="mb-6 flex items-center justify-between">
      <Link href="/" className="text-xl font-bold text-blue-600">
        Rivalens
      </Link>
      <button
        onClick={handleLogout}
        className="rounded border p-2 text-sm hover:bg-gray-50"
      >
        Logout
      </button>
    </header>
  );
}
