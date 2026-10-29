"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { getToken } from "@/lib/auth";

/** Renders children only when a token exists; otherwise redirects to /login. */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return <p className="mx-auto max-w-3xl p-6 text-gray-500">Loading…</p>;
  }
  return <>{children}</>;
}
