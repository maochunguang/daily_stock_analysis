export interface PersonalCoverageRow {
  code: string;
  source: string;
  rows: number;
  start_date: string | null;
  end_date: string | null;
}

export interface PersonalPlugin {
  name: string;
  version: string;
  type: string;
  display_name: string;
  description?: string;
  permissions?: string[];
}

export interface PersonalRun {
  run_id: string;
  mode: string;
  start_date: string | null;
  end_date: string | null;
  metrics_json: string;
  created_at: string;
}

export interface PersonalQualityEvent {
  id: number;
  dataset: string;
  code: string | null;
  trade_date: string | null;
  rule: string;
  severity: string;
  detail: string;
  created_at: string;
}

export interface PersonalUpstreamStatus {
  available: boolean;
  has_analysis_history: boolean;
  has_portfolio: boolean;
  has_decision_signals: boolean;
  missing: string[];
}

export interface PersonalStatus {
  app: { version: string };
  settings: {
    root: string;
    personal_db: string;
    upstream_db: string;
    stock_list: string[];
    data_source_priority: string[];
  };
  upstream: PersonalUpstreamStatus;
  storage: Record<string, number>;
  coverage: PersonalCoverageRow[];
  plugins: PersonalPlugin[];
  plugin_errors: string[];
  recent_runs: PersonalRun[];
  recent_quality: PersonalQualityEvent[];
  qmt: {
    bridge_url: string;
    trading_enabled: boolean;
    require_confirm: boolean;
  };
}

export interface PersonalSyncResult {
  code: string;
  source: string | null;
  rows: number;
  quality_issues: number;
  cross_source_issues?: number;
  missing_days?: number;
  suspended_days?: number;
  errors: string[];
}

export interface PersonalSyncResponse {
  dataset: string;
  start: string;
  end: string;
  results: PersonalSyncResult[];
}

export interface PersonalEquityPoint {
  date: string;
  value: number;
}

export interface PersonalTrade {
  date: string;
  code: string;
  side: string;
  quantity: number;
  price: number;
  gross_amount: number;
  fee: number;
  realized_pnl: number;
  reason: string;
}

export interface PersonalBacktestResponse {
  kind: string;
  start: string;
  end: string;
  signals: number;
  metrics: Record<string, number | null>;
  equity: PersonalEquityPoint[];
  benchmark: PersonalEquityPoint[] | null;
  trades: PersonalTrade[];
  final_cash: number;
  final_positions: Record<string, number>;
  run_id?: string;
}

export interface PersonalUpstreamRecent {
  available: boolean;
  missing?: string;
  analyses: Array<{
    id: number;
    code: string;
    name: string | null;
    advice: string | null;
    score: number | null;
    created_at: string | null;
  }>;
  signals: Array<{
    id: number;
    code: string;
    action: string;
    score: number | null;
    confidence: number | null;
    created_at: string | null;
  }>;
}

export interface PersonalQmtHealth {
  ok: boolean;
  detail: unknown;
}

export interface PersonalBreadthRow {
  trade_date: string;
  up_count: number;
  down_count: number;
  flat_count: number;
  sample_count: number;
  up_vol_yi: number | null;
  down_vol_yi: number | null;
  up_amount_yi: number | null;
  down_amount_yi: number | null;
  adv_ratio: number | null;
  trin: number | null;
  trin_amount: number | null;
  trin_pct: number | null;
  interpretation: string;
  band: string;
  index_close: number | null;
  index_chg_pct: number | null;
  index_pos: number | null;
  divergence: number;
  signal_tag: string;
  signal_detail: string;
  source: string;
}

export interface PersonalFuturesRow {
  trade_date: string;
  symbol: string;
  close: number | null;
  volume: number | null;
  open_interest: number | null;
  oi_chg: number | null;
  index_close: number | null;
  basis: number | null;
  basis_pct: number | null;
  source: string;
}

export interface PersonalMarginRow {
  trade_date: string;
  scope_type: 'market' | 'board';
  scope: string;
  rzye: number | null;
  rqye: number | null;
  rzrqye: number | null;
  rzye_buy: number | null;
  source: string;
}

export interface PersonalMarketSyncResponse {
  dataset: string;
  start: string;
  end: string;
  rows: number;
  latest_date: string | null;
  message: string;
}
