import { authHeaders, clearToken } from "./auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Competitor = {
  id: string;
  name: string;
  url: string;
  active: boolean;
  created_at: string;
};

export type Page = {
  id: string;
  url: string;
  kind: string;
  active: boolean;
};

export type Insight = {
  id: string;
  period_start: string;
  period_end: string;
  summary: string;
  created_at: string;
};

export type Change = {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  detected_at: string;
};

export async function listChanges(
  id: string,
  limit: number = 50,
): Promise<Change[]> {
  return request<Change[]>(`/competitors/${id}/changes?limit=${limit}`);
}

export type CheckResult = {
  snapshots_created: number;
  changes_created: number;
  insight_id: string | null;
  checked_at: string;
  pages_checked: number;
  next_check_at: string | null;
  is_first_check: boolean;
};

export type CompetitorDetail = {
  competitor: Competitor;
  pages: Page[];
  insights: Insight[];
  total_checks: number;
  last_checked_at: string | null;
  next_check_at: string | null;
};

export type User = {
  id: string;
  email: string;
  plan: string;
};

export type Plan = {
  plan: string;
  competitors_used: number;
  competitors_limit: number | null;
};

export class UnauthorizedError extends Error {}
export class PaymentRequiredError extends Error {}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}/api/v1${path}`, {
      ...init,
      headers: {
        ...(init?.headers ?? {}),
        ...authHeaders(),
      },
    });
  } catch (e) {
    throw new Error(
      `Network error: ${e instanceof Error ? e.message : String(e)}`,
    );
  }
  if (response.status === 401) {
    clearToken();
    throw new UnauthorizedError("unauthorized");
  }
  if (response.status === 402) {
    throw new PaymentRequiredError("plan limit reached");
  }
  if (!response.ok) {
    // Prefer the backend's detail field, fall back to raw body text.
    const text = await response.text().catch(() => "");
    let detail = text;
    if (text) {
      try {
        const parsed = JSON.parse(text) as { detail?: string };
        if (parsed.detail) detail = parsed.detail;
      } catch {
        // not JSON — keep raw text
      }
    }
    throw new Error(`API error ${response.status}: ${detail}`);
  }
  // 204 No Content (and empty 200s) have no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function login(
  email: string,
  password: string,
): Promise<string> {
  const response = await fetch(`${API}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Login failed (${response.status}): ${text}`);
  }
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

export async function register(
  email: string,
  password: string,
): Promise<User> {
  const response = await fetch(`${API}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Registration failed (${response.status}): ${text}`);
  }
  return response.json() as Promise<User>;
}

export async function getMe(): Promise<User> {
  return request<User>("/auth/me");
}

export async function getPlan(): Promise<Plan> {
  return request<Plan>("/billing/plan");
}

export async function setPlan(plan: string): Promise<Plan> {
  return request<Plan>("/billing/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
}

export async function checkout(
  plan: string,
): Promise<{ confirmation_url: string }> {
  return request<{ confirmation_url: string }>("/billing/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
}

export async function listCompetitors(): Promise<Competitor[]> {
  return request<Competitor[]>("/competitors");
}

export async function createCompetitor(input: {
  name: string;
  url: string;
}): Promise<Competitor> {
  return request<Competitor>("/competitors", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function getCompetitor(id: string): Promise<CompetitorDetail> {
  return request<CompetitorDetail>(`/competitors/${id}`);
}

export async function checkCompetitor(id: string): Promise<CheckResult> {
  return request<CheckResult>(`/competitors/${id}/check`, { method: "POST" });
}

export async function deleteCompetitor(id: string): Promise<void> {
  await request<void>(`/competitors/${id}`, { method: "DELETE" });
}

export async function listInsights(id: string): Promise<Insight[]> {
  return request<Insight[]>(`/competitors/${id}/insights`);
}
