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

export type CheckResult = {
  snapshots_created: number;
  changes_created: number;
  insight_id: string | null;
};

export type CompetitorDetail = {
  competitor: Competitor;
  pages: Page[];
  insights: Insight[];
};

export type User = {
  id: string;
  email: string;
  plan: string;
};

export class UnauthorizedError extends Error {}

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
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`API error ${response.status}: ${text}`);
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

export async function listInsights(id: string): Promise<Insight[]> {
  return request<Insight[]>(`/competitors/${id}/insights`);
}
