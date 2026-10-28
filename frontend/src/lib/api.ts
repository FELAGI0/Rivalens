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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}/api/v1${path}`, init);
  } catch (e) {
    throw new Error(`Network error: ${e instanceof Error ? e.message : String(e)}`);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`API error ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
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
