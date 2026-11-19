import type {
  AccountScreenshotParseResponse,
  AccountSnapshot,
  AccountSnapshotConfirmRequest,
  AccountSnapshotConfirmResponse,
  BrokerImportSummary,
  BrokerJournalRow,
  BrokerPositionRow,
  AccountPosition,
  JournalOutcomesResponse,
  MarginStockEntry,
  PersonalBacktestResponse,
  PersonalBreadthRow,
  PersonalBrokerImportRequest,
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
  PersonalValidationResponse,
  PortfolioRiskResponse,
  TradePlan,
  TradePlanPreview,
  TradePlanRequest,
  TradePlanStatus,
} from '../types/personal';

function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg);
        }
        return typeof item === 'string' ? item : JSON.stringify(item);
      })
      .join('; ');
  }
  if (detail && typeof detail === 'object') {
    if ('message' in detail) return String((detail as { message: unknown }).message);
    if ('detail' in detail) return formatDetail((detail as { detail: unknown }).detail);
    return JSON.stringify(detail);
  }
  return String(detail ?? '');
}

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
        ? formatDetail((payload as { detail: unknown }).detail)
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
  marketValidate: (days = 400, online = false) =>
    request<PersonalValidationResponse>(
      `/market/validate?days=${days}&online=${online ? 'true' : 'false'}`,
    ),
  marketSync: (body: PersonalMarketSyncRequest) =>
    request<PersonalMarketSyncResponse>('/market/sync', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  marginStocks: (days = 30) =>
    request<{ stocks: MarginStockEntry[] }>(`/margin/stocks?days=${days}`),
  brokerImport: (body: PersonalBrokerImportRequest) =>
    request<BrokerImportSummary>('/broker/import', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  brokerPositions: () =>
    request<{ positions: BrokerPositionRow[] }>('/broker/positions'),
  brokerJournal: (limit = 100) =>
    request<{ journal: BrokerJournalRow[] }>(`/broker/journal?limit=${limit}`),
  accountSnapshotParse: (body: { filename: string; content_b64: string }) =>
    request<AccountScreenshotParseResponse>('/account-snapshots/parse', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  accountSnapshotConfirm: (body: AccountSnapshotConfirmRequest) =>
    request<AccountSnapshotConfirmResponse>('/account-snapshots', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  accountSnapshotLatest: () =>
    request<{ snapshot: AccountSnapshot | null }>('/account-snapshots/latest'),
  portfolioRisk: () => request<PortfolioRiskResponse>('/portfolio/risk'),
  tradePlans: (status?: TradePlanStatus | '') =>
    request<{ plans: TradePlan[] }>(
      `/trade-plans?limit=200${status ? `&status=${status}` : ''}`,
    ),
  tradePlan: (id: number) =>
    request<{ plan: TradePlan }>(`/trade-plans/${id}`),
  tradePlanPreview: (body: TradePlanRequest) =>
    request<{ plan: Partial<TradePlan>; preview: TradePlanPreview }>(
      '/trade-plans/preview',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  tradePlanCreate: (body: TradePlanRequest) =>
    request<{ plan: TradePlan; preview: TradePlanPreview }>('/trade-plans', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  tradePlanUpdate: (id: number, body: TradePlanRequest) =>
    request<{ plan: TradePlan; preview: TradePlanPreview }>(`/trade-plans/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  tradePlanStatus: (id: number, status: TradePlanStatus) =>
    request<{ plan: TradePlan }>(`/trade-plans/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  journalOutcomes: (params: {
    horizon?: number;
    days?: number;
    code?: string;
    side?: string;
    limit?: number;
  } = {}) => {
    const search = new URLSearchParams();
    search.set('horizon', String(params.horizon ?? 20));
    search.set('days', String(params.days ?? 365));
    search.set('limit', String(params.limit ?? 200));
    if (params.code) search.set('code', params.code);
    if (params.side) search.set('side', params.side);
    return request<JournalOutcomesResponse>(`/journal/outcomes?${search.toString()}`);
  },
};

export type { AccountPosition };
