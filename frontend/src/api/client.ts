import type {
  AIAnswer, AlgorithmPlugin, Analytics, AsEvent, ExecutionState,
  ExecutionSummary, ViewDescriptor,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly problem: Record<string, any> = {},
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let problem: Record<string, any> = {};
    try {
      problem = await response.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      problem.detail ?? problem.title ?? response.statusText,
      response.status,
      problem,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export interface RunOptions {
  granularity?: string;
  lifters?: boolean | null;
  maxSeconds?: number;
  useCache?: boolean;
}

export interface RunResponse {
  execution_id: string;
  status: string;
  cached: boolean;
  event_count: number;
  capability_report: ExecutionSummary["capability_report"];
  error: ExecutionSummary["error"];
  ws: string;
}

export const api = {
  health: () => request<Record<string, any>>("/health"),

  run: (source: string, options: RunOptions = {}) =>
    request<RunResponse>("/executions", {
      method: "POST",
      body: JSON.stringify({
        source,
        granularity: options.granularity ?? "standard",
        options: {
          lifters: options.lifters ?? null,
          max_seconds: options.maxSeconds,
          use_cache: options.useCache ?? null,
        },
      }),
    }),

  runAlgorithm: (id: string, inputs: Record<string, any>, options: RunOptions = {}) =>
    request<RunResponse>(`/algorithms/${id}/run`, {
      method: "POST",
      body: JSON.stringify({
        inputs,
        granularity: options.granularity ?? "standard",
        options: { lifters: options.lifters ?? null, use_cache: options.useCache ?? null },
      }),
    }),

  summary: (id: string) => request<ExecutionSummary>(`/executions/${id}`),

  events: (id: string, offset = 0, limit = 20000) =>
    request<{ events: AsEvent[]; total: number; next_offset: number | null }>(
      `/executions/${id}/events?offset=${offset}&limit=${limit}`,
    ),

  allEvents: async (id: string, total: number) => {
    const out: AsEvent[] = [];
    let offset = 0;
    while (offset < total) {
      const page = await api.events(id, offset, 20000);
      out.push(...page.events);
      if (!page.events.length) break;
      offset += page.events.length;
    }
    return out;
  },

  state: (id: string, step: number) =>
    request<ExecutionState>(`/executions/${id}/state?step=${step}`),

  views: (id: string, step: number) =>
    request<{ plan: ViewDescriptor[] }>(`/executions/${id}/views?step=${step}`),

  analytics: (id: string) => request<Analytics>(`/executions/${id}/analytics`),

  ask: (id: string, body: Record<string, any>) =>
    request<AIAnswer>(`/executions/${id}/ai`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  algorithms: () =>
    request<{ algorithms: AlgorithmPlugin[]; problems: Record<string, string[]> }>(
      "/algorithms",
    ),

  algorithm: (id: string) => request<AlgorithmPlugin>(`/algorithms/${id}`),

  analyze: (source: string) =>
    request<Record<string, any>>("/analyze", {
      method: "POST",
      body: JSON.stringify({ source }),
    }),

  generateInput: (body: Record<string, any>) =>
    request<{ value: any; spec: Record<string, any> }>("/inputs/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  benchmark: (body: Record<string, any>) =>
    request<Record<string, any>>("/benchmarks", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
