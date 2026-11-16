import type {
  PersonalBacktestResponse,
  PersonalPlugin,
  PersonalQmtHealth,
  PersonalStatus,
  PersonalSyncResponse,
  PersonalUpstreamRecent,
} from '../types/personal';

const BASE = '/personal-api/api';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
    ...init,
  });
  const text = await response.text();
  let payload: unknown = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return payload as T;
}

export interface PersonalSyncRequest {
  dataset: 'bars' | 'adjust' | 'calendar' | 'status';
  source: string;
  codes: string[] | null;
  start: string | null;
  end: string | null;
  cross_check?: boolean | null;
}

export interface PersonalDemoRequest {
  days: number;
  save: boolean;
}

export interface PersonalReplayRequest {
  start: string | null;
  end: string | null;
  include: 'both' | 'analyses' | 'signals';
  save: boolean;
}

export const personalApi = {
  status: () => request<PersonalStatus>('/status'),
  plugins: () => request<{ plugins: PersonalPlugin[]; errors: string[] }>('/plugins'),
  sync: (body: PersonalSyncRequest) =>
    request<PersonalSyncResponse>('/data/sync', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  demo: (body: PersonalDemoRequest) =>
    request<PersonalBacktestResponse>('/backtest/demo', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  replay: (body: PersonalReplayRequest) =>
    request<PersonalBacktestResponse>('/backtest/replay', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  upstreamRecent: () => request<PersonalUpstreamRecent>('/upstream/recent?limit=20'),
  qmtHealth: () => request<PersonalQmtHealth>('/qmt/health'),
};
