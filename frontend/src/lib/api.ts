import { authHeaders, clearToken } from "./auth";

// Backend default port 8001 — 8000 is taken by another project
// (BioPhysLab) on this machine, see CLAUDE.md.
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

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
  pages_failed: number;
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

export type PricePoint = {
  date: string;
  prices: string[];
};

export type PriceChange = {
  date: string;
  from: string;
  to: string;
  kind: string;
};

export type PriceHistory = {
  points: PricePoint[];
  changes: PriceChange[];
};

export async function listPriceHistory(
  id: string,
  days: number = 30,
): Promise<PriceHistory> {
  return request<PriceHistory>(
    `/competitors/${id}/price-history?days=${days}`,
  );
}

export type User = {
  id: string;
  email: string;
  plan: string;
};

export type PlanOffer = {
  name: string;
  original_price: number;
  discount_price: number;
  limit: number | null;
};

export type Plan = {
  plan: string;
  competitors_used: number;
  competitors_limit: number | null;
  offers: PlanOffer[];
};

export class UnauthorizedError extends Error {}
export class PaymentRequiredError extends Error {}

/** HTTP error with status + parsed FastAPI detail, for human mapping in pages. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  /** Seconds until a retry is allowed (429 rate limit responses). */
  readonly retryAfter: number | null;

  constructor(status: number, detail: string, retryAfter: number | null = null) {
    super(detail || `API error ${status}`);
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
  }
}

/** Turn a failed response into an ApiError with the backend's detail. */
async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text().catch(() => "");
  let detail = "";
  let retryAfter: number | null = null;
  if (text) {
    try {
      const parsed = JSON.parse(text) as {
        detail?: string | { msg?: string }[];
        retry_after?: number;
      };
      if (typeof parsed.detail === "string") {
        detail = parsed.detail;
      } else if (Array.isArray(parsed.detail)) {
        // FastAPI 422 validation errors arrive as a list of {msg, ...}.
        detail = parsed.detail.map((d) => d.msg ?? "").join("; ");
      }
      if (
        typeof parsed.retry_after === "number" &&
        parsed.retry_after > 0
      ) {
        retryAfter = parsed.retry_after;
      }
    } catch {
      // not JSON — keep raw text
      detail = text;
    }
  }
  if (retryAfter === null) {
    const header = response.headers.get("retry-after");
    const parsedHeader = header === null ? NaN : Number(header);
    if (Number.isFinite(parsedHeader) && parsedHeader > 0) {
      retryAfter = parsedHeader;
    }
  }
  return new ApiError(
    response.status,
    humanizeDetail(response.status, detail),
    retryAfter,
  );
}

/** Backend detail strings are English/log-facing; users read this. */
const DETAIL_MESSAGES: Record<string, string> = {
  "payment unavailable":
    "Оплата временно недоступна. Напишите на rivalens@ya.ru.",
  "unknown plan": "Такого тарифа нет.",
  "plan already active": "Этот тариф уже активен.",
  "use checkout for upgrade":
    "Для перехода на старший тариф нужна оплата.",
  "invalid or missing token": "Сессия истекла. Войдите заново.",
};

function humanizeDetail(status: number, detail: string): string {
  const mapped = DETAIL_MESSAGES[detail];
  if (mapped) return mapped;
  // A 502 is always an upstream failure; never show the raw text.
  if (status === 502) {
    return "Сервис временно недоступен. Попробуйте позже или напишите на rivalens@ya.ru.";
  }
  return detail;
}

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
    throw await toApiError(response);
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
  let response: Response;
  try {
    response = await fetch(`${API}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch (e) {
    throw new Error(
      `Network error: ${e instanceof Error ? e.message : String(e)}`,
    );
  }
  if (!response.ok) {
    throw await toApiError(response);
  }
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

export async function register(
  email: string,
  password: string,
): Promise<User> {
  let response: Response;
  try {
    response = await fetch(`${API}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch (e) {
    throw new Error(
      `Network error: ${e instanceof Error ? e.message : String(e)}`,
    );
  }
  if (!response.ok) {
    throw await toApiError(response);
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
