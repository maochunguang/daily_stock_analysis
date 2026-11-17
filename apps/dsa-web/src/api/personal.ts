import type {
  PersonalBacktestResponse,
  PersonalBreadthRow,
  PersonalCompositeResponse,
  PersonalCrowdingResponse,
  PersonalFlowsResponse,
  PersonalFuturesRankRow,
  PersonalFuturesRow,
  PersonalLimitUpRow,
  PersonalMacroResponse,
  PersonalMarginRow,
  PersonalMarketSyncResponse,
  PersonalPcrRow,
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

export interface PersonalMarketSyncRequest {
  dataset:
    | 'futures'
    | 'margin'
    | 'turnover'
    | 'zt'
    | 'pcr'
    | 'cffex_rank'
    | 'sector'
    | 'etf_share'
    | 'bond'
    | 'release';
  start: string | null;
  end: string | null;
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
  breadth: (days = 30) =>
    request<{ rows: PersonalBreadthRow[] }>(`/market/breadth?days=${days}`),
  futures: (days = 30) =>
    request<{ rows: PersonalFuturesRow[] }>(`/market/futures?days=${days}`),
  margin: (days = 30) =>
    request<{ rows: PersonalMarginRow[] }>(`/market/margin?days=${days}`),
  limitup: (days = 20) =>
    request<{ rows: PersonalLimitUpRow[] }>(`/market/limitup?days=${days}`),
  pcr: (days = 20) =>
    request<{ underlying: string; rows: PersonalPcrRow[] }>(`/market/pcr?days=${days}`),
  cffexRank: (days = 20) =>
    request<{ rows: PersonalFuturesRankRow[] }>(`/market/cffex-rank?days=${days}`),
  flows: (days = 30) =>
    request<PersonalFlowsResponse>(`/market/flows?days=${days}`),
  crowding: (days = 30) =>
    request<PersonalCrowdingResponse>(`/market/crowding?days=${days}`),
  macro: (days = 120) =>
    request<PersonalMacroResponse>(`/market/macro?days=${days}`),
  composite: () => request<PersonalCompositeResponse>('/market/composite'),
  marketSync: (body: PersonalMarketSyncRequest) =>
    request<PersonalMarketSyncResponse>('/market/sync', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};
