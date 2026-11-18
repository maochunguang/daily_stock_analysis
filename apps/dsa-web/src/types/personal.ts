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
  sync_state?: PersonalSyncState[];
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

export interface PersonalSyncState {
  dataset: string;
  last_run_at: string | null;
  last_ok_at: string | null;
  last_ok_date: string | null;
  rows: number;
  last_error: string | null;
}

export interface PersonalLimitUpRow {
  trade_date: string;
  zt_count: number;
  first_board: number;
  streak_ge2: number;
  max_streak: number;
  zb_count: number;
  zb_rate: number | null;
  prev_zt_mean: number | null;
  prev_zt_up_ratio: number | null;
}

export interface PersonalPcrRow {
  trade_date: string;
  call_vol: number | null;
  put_vol: number | null;
  pcr_vol: number | null;
  call_oi: number | null;
  put_oi: number | null;
  pcr_oi: number | null;
}

export interface PersonalFuturesRankRow {
  trade_date: string;
  symbol: string;
  contracts: number;
  top20_buy: number | null;
  top20_sell: number | null;
  net: number | null;
  net_ratio: number | null;
}

export interface PersonalFlowsResponse {
  margin_ratio: Array<{ trade_date: string; ratio_pct: number }>;
  turnover: Array<{ trade_date: string; total_amount_yi: number | null }>;
  etf_share: Array<{ trade_date: string; code: string; name: string; share_yi: number | null }>;
}

export interface PersonalCrowdingRow {
  board: string;
  amount_yi: number | null;
  share_pct: number | null;
  pct_chg: number | null;
  share_pctile: number | null;
  samples: number;
}

export interface PersonalCrowdingResponse {
  trade_date: string | null;
  rows: PersonalCrowdingRow[];
}

export interface PersonalMacroResponse {
  bond_yield: Array<{
    trade_date: string;
    cn_10y: number | null;
    us_10y: number | null;
    spread_10y: number | null;
    spread_2y: number | null;
  }>;
  release: Array<{
    release_date: string;
    company_count: number;
    market_value_yi: number | null;
  }>;
}

export interface PersonalCompositeComponent {
  metric: string;
  label: string;
  kind: 'pro' | 'contrarian';
  value: number | null;
  percentile: number | null;
  sample_count: number;
}

export interface PersonalCompositeResponse {
  score: number | null;
  state: string;
  components: PersonalCompositeComponent[];
}

export interface PersonalValidationFinding {
  dataset: string;
  rule: string;
  severity: 'error' | 'warn' | 'info';
  detail: string;
  trade_date: string | null;
}

export interface PersonalValidationDataset {
  dataset: string;
  label: string;
  status: 'ok' | 'warn' | 'error' | 'empty';
  rows: number;
  latest: string | null;
  expected_latest: string | null;
  errors: number;
  warnings: number;
  findings: PersonalValidationFinding[];
}

export interface PersonalValidationResponse {
  generated_at: string;
  start: string;
  end: string;
  score: number;
  status: 'ok' | 'warn' | 'error' | 'empty';
  online: boolean;
  counts: Record<string, number>;
  datasets: PersonalValidationDataset[];
  findings: PersonalValidationFinding[];
}

export interface BrokerPositionRow {
  code: string;
  name: string;
  quantity: number;
  avg_cost: number | null;
  cost_value: number | null;
  realized_pnl: number;
  dividend_cash: number;
  fees_total: number;
  buy_count: number;
  sell_count: number;
  first_trade_date: string | null;
  last_trade_date: string | null;
  updated_at?: string;
}

export interface BrokerSnapshotComponent {
  metric: string;
  label: string;
  kind: 'pro' | 'contrarian';
  percentile: number | null;
  value: number | null;
}

export interface BrokerSnapshot {
  trade_date: string;
  composite: {
    score: number | null;
    state: string;
    components: BrokerSnapshotComponent[];
  };
  breadth?: {
    trin: number | null;
    band: string;
    adv_ratio: number | null;
    interpretation: string;
  };
  limit_up?: { zt_count: number; zb_rate: number | null; max_streak: number };
  turnover_yi?: number;
  sector_top?: { board: string; share_pct: number | null };
  margin_stock?: {
    rzye: number | null;
    rzye_buy: number | null;
    rzye_chg_5d_pct?: number;
  };
}

export interface BrokerJournalRow {
  id: number;
  trade_date: string;
  code: string;
  side: string;
  quantity: number;
  price: number;
  amount: number;
  reason: string | null;
  source: string | null;
  snapshot: BrokerSnapshot | string | null;
}

export interface BrokerImportSummary {
  filename: string;
  imported: number;
  skipped_total: number;
  skipped: Array<{ line_no: number; reason: string; raw: string }>;
  warnings: string[];
  positions: BrokerPositionRow[];
  journal_added: number;
  column_map: Record<string, string>;
  unrecognized_headers: string[];
}

export interface PersonalBrokerImportRequest {
  filename: string;
  content_b64: string;
  column_map?: Record<string, string>;
}

export interface MarginStockPoint {
  trade_date: string;
  rzye: number | null;
  rzye_buy: number | null;
  rqye: number | null;
}

export interface MarginStockEntry {
  code: string;
  name: string;
  trade_date: string;
  rzye: number | null;
  rzye_buy: number | null;
  rqye: number | null;
  rzye_chg_pct: number | null;
  series: MarginStockPoint[];
}
