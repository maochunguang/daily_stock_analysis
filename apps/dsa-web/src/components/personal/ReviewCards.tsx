import type React from 'react';
import { Landmark, RefreshCw, ShieldCheck, TrendingDown } from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Badge, Card } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type {
  PersonalBreadthRow,
  PersonalCompositeResponse,
  PersonalCrowdingResponse,
  PersonalFlowsResponse,
  PersonalFuturesRankRow,
  PersonalFuturesRow,
  PersonalIndexValuationCheckResponse,
  PersonalIndexValuationResponse,
  PersonalLimitUpRow,
  PersonalMacroResponse,
  PersonalMarginRow,
  PersonalPcrRow,
  PersonalValidationResponse,
  MarginStockEntry,
} from '../../types/personal';

/**
 * 深度复盘卡片注册表：新增指标 = 写一个 ReviewCardComponent 并往 REVIEW_CARDS
 * 追加一项（id 稳定即可），页面网格自动多一张卡，无需改动 PersonalPage。
 */

const REVIEW_COPY = {
  zh: {
    breadthTitle: '市场宽度（阿姆氏 TRIN）',
    futuresTitle: '股指期货做空压力',
    marginTitle: '融资余额',
    moreTitle: '更多指标（规划中）',
    trin: 'TRIN',
    band: '分位带',
    pct: '历史分位',
    advRatio: '上涨占比',
    up: '上涨',
    down: '下跌',
    index: '上证指数',
    divergence: '背离信号',
    interpretation: '判读',
    signalTop: '顶部信号',
    signalBottom: '底部信号',
    contract: '合约',
    futuresClose: '期货收盘',
    spot: '现货',
    basis: '基差',
    basisPct: '基差率',
    oi: '持仓量',
    oiChg: '持仓Δ',
    refresh: '更新',
    refreshing: '更新中…',
    rzye: '融资余额',
    rqye: '融券余额',
    board: '板块',
    total: '总计',
    chg5: '5日变化',
    buy: '融资买入',
    day: '日',
    breadthHint: '数据来自 easy-daily-trading 快照，更新：那边运行 tools/arms_index.py 后执行 import-arms',
    futuresHint: '贴水（基差为负）= 对冲/做空压力大；持仓量上升 = 空头建仓',
    marginHint: '板块行仅统计股票标的，与沪/深市汇总的差值≈ETF/债券/可转债口径',
    moreList: '北向资金活跃度 · 新基金发行 · 龙虎榜机构席位（事件型）',
    noData: '暂无数据，先同步数据集',
    unitYi: '亿',
    limitupTitle: '涨停梯队与亏钱效应',
    ztCount: '涨停',
    firstBoard: '首板',
    streakGe2: '2板+',
    maxStreak: '最高连板',
    zbCount: '炸板',
    zbRate: '炸板率',
    prevZtMean: '昨涨停今收益',
    prevZtUpRatio: '昨日涨停今日上涨占比',
    limitupHint: '炸板率>40% 或 昨涨停今收益深负 = 亏钱效应扩散；连板高度抬升 = 题材进入加速段',
    rankTitle: '期指会员持仓（前20）',
    top20Buy: '前20持买单量',
    top20Sell: '前20持卖单量',
    net: '净空头',
    netRatio: '净空占比',
    rankHint: '逆向指标：净空占比高分位 = 对冲拥挤，极端时反而接近阶段底；配合基差卡看"谁在做空"',
    pcrTitle: '期权 PCR（50ETF）',
    pcrVol: '成交量PCR',
    pcrOi: '持仓量PCR',
    callVol: '认购成交',
    putVol: '认沽成交',
    pcrHint: '逆向指标：PCR 高分位 = 恐慌定价，历史上常见阶段底；成交量口径（Tushare opt_daily）',
    flowsTitle: '资金面（两融占比 / ETF 份额 / 成交额）',
    marginRatio: '两融交易占比',
    marginRatioHint: '融资买入额 ÷ 全市场成交额；>10% 过热 / <7% 冰点',
    turnoverAmount: '全市场成交额',
    etfShare: 'ETF 份额',
    shareUnit: '亿份',
    flowsHint: 'ETF 份额暴增 = 宽基托底资金进场（份额序列自建，从启用日起积累）',
    crowdingTitle: '行业拥挤度',
    amountYi: '成交额',
    sharePct: '成交占比',
    sharePctile: '占比分位',
    crowdingHint: '板块成交占比 250 日分位 >90% = 拥挤警戒；样本随每日快照积累',
    macroTitle: '宏观锚（中美利差 / 解禁日历）',
    spread10y: '中美10Y利差',
    spread2y: '中美2Y利差',
    releaseCalendar: '未来60天解禁',
    releaseDate: '解禁日',
    releaseCount: '家数',
    releaseValue: '解禁市值',
    macroHint: '利差走阔压制风险偏好；解禁高峰注意持仓股供给冲击（月级别）',
    compositeTitle: '市场综合状态',
    scoreLabel: '综合分',
    kindPro: '顺势',
    kindContrarian: '逆向',
    pctile: '分位',
    samples: '样本',
    compositeHint: '各指标转为约一年滚动分位后平均（样本<20 自动跳过）；顺势高分位=过热，逆向高分位=恐慌',
    metricLabel: '指标',
    kindLabel: '类型',
    pending: '等待回填',
    code: '代码',
    name: '名称',
    marginStocksTitle: '持仓股两融',
    marginStocksHint: '融资余额升 = 杠杆资金进场；骤降 = 去杠杆（数据随定时同步积累，代码=自选股∪交割单持仓）',
    rzyeYi: '融资余额(亿)',
    buyYi: '融资买入(亿)',
    chg1: '余额日变化',
    valuationTitle: '指数估值分位（PE-TTM）',
    valuationPe: 'PE-TTM',
    valuationEqual: '等权',
    valuation1y: '近1年',
    valuation3y: '近3年',
    valuation5y: '近5年',
    valuationSamples: '样本',
    valuationUpdated: '更新',
    valuationWeek: '周',
    valuationMonth: '月',
    valuationLow: '低估区',
    valuationLowMid: '偏低',
    valuationMid: '中性',
    valuationHighMid: '偏高',
    valuationHigh: '高估区',
    valuationNoData: '暂无估值数据，先同步 valuation 数据集',
    valuationStale: '数据陈旧',
    valuationStaleUnit: '天',
    valuationInsufficient: '样本不足',
    valuationCheck: '交叉校验',
    valuationChecking: '校验中…',
    valuationCheckTitle: '官方交叉校验',
    valuationCheckLegu: '乐咕值',
    valuationCheckOfficial: '官方值',
    valuationCheckDiff: '偏差',
    valuationCheckStatus: '状态',
    valuationCheckOk: '一致',
    valuationCheckWarn: '口径差异',
    valuationCheckError: '需复核',
    valuationCheckUnavailable: '不可用',
    valuationCheckLatest: '最新',
    valuationCheckFailed: '交叉校验失败',
    valuationCheckNote:
      '官方源仅提供当前值（中证近 20 日、国证最新），用于水平校验，不参与历史分位；偏差不等于数据错误。',
    valuationHighRatio: '最高',
    valuationHint:
      '分位 = 当前 PE-TTM 在窗口内周频样本中的百分位（排名）；括号内为“当前 PE ÷ 该窗口最高 PE”。分位低只代表排名低，例如 2% 分位表示约 2% 的样本低于当前值，不等于当前值是最高的 2%。PE-TTM 为加权滚动市盈率，来源乐咕乐股；仅反映历史位置，不构成买卖建议。',
    healthTitle: '数据体检',
    healthScore: '健康分',
    healthOk: '正常',
    healthWarn: '注意',
    healthError: '异常',
    healthEmpty: '无数据',
    healthLatest: '最新',
    healthIssues: '问题',
    healthRun: '重新体检',
    healthOnline: '外部抽检',
    healthClean: '全部通过，未发现异常',
    healthHint:
      '规则：恒等式、取值域、交易日、环比跳变、跨指标（行业成交额 vs 全市场）与外部源抽检（交易所/中债/乐咕/中金所）',
  },
  en: {
    breadthTitle: 'Market breadth (TRIN)',
    futuresTitle: 'Index futures short pressure',
    marginTitle: 'Margin balance',
    moreTitle: 'More indicators (planned)',
    trin: 'TRIN',
    band: 'Band',
    pct: 'Percentile',
    advRatio: 'Adv ratio',
    up: 'Adv',
    down: 'Dec',
    index: 'SSE index',
    divergence: 'Divergence',
    interpretation: 'Reading',
    signalTop: 'Top signal',
    signalBottom: 'Bottom signal',
    contract: 'Contract',
    futuresClose: 'Futures',
    spot: 'Spot',
    basis: 'Basis',
    basisPct: 'Basis %',
    oi: 'Open interest',
    oiChg: 'OI Δ',
    refresh: 'Refresh',
    refreshing: 'Refreshing…',
    rzye: 'Fin. balance',
    rqye: 'Sec. lending',
    board: 'Board',
    total: 'Total',
    chg5: '5-day Δ',
    buy: 'Fin. buy',
    day: 'd',
    breadthHint: 'Snapshots from easy-daily-trading; refresh by running tools/arms_index.py there, then import-arms',
    futuresHint: 'Discount (negative basis) = heavy hedging/short pressure; rising OI = shorts building',
    marginHint: 'Board rows count stock instruments only; gap vs market summary ≈ ETF/bond scope',
    moreList: 'Northbound activity · New fund issuance · Institution seats (event-driven)',
    noData: 'No data yet — sync the dataset first',
    unitYi: '×1e8 CNY',
    limitupTitle: 'Limit-up ladder',
    ztCount: 'Limit-up',
    firstBoard: 'First board',
    streakGe2: '2+ boards',
    maxStreak: 'Max streak',
    zbCount: 'Broken',
    zbRate: 'Break rate',
    prevZtMean: 'Prev limit-up carry',
    prevZtUpRatio: 'Prev limit-up gainers',
    limitupHint: 'Break rate >40% or deep negative carry = losing effect; rising streaks = theme acceleration',
    rankTitle: 'CFFEX member positions (top-20)',
    top20Buy: 'Top-20 long OI',
    top20Sell: 'Top-20 short OI',
    net: 'Net short',
    netRatio: 'Net short %',
    rankHint: 'Contrarian: extreme net-short percentile = crowded hedge, often near lows; read with the basis card',
    pcrTitle: 'Option PCR (50ETF)',
    pcrVol: 'Volume PCR',
    pcrOi: 'OI PCR',
    callVol: 'Call vol',
    putVol: 'Put vol',
    pcrHint: 'Contrarian: high PCR percentile = panic pricing, historically near lows; volume basis (Tushare opt_daily)',
    flowsTitle: 'Funds (margin ratio / ETF shares / turnover)',
    marginRatio: 'Margin trading ratio',
    marginRatioHint: 'Margin buy ÷ market turnover; >10% overheated / <7% frozen',
    turnoverAmount: 'Market turnover',
    etfShare: 'ETF shares',
    shareUnit: '×1e8 units',
    flowsHint: 'Broad-ETF share spikes = national-team support (series accumulates from adoption)',
    crowdingTitle: 'Sector crowding',
    amountYi: 'Turnover',
    sharePct: 'Share %',
    sharePctile: 'Percentile',
    crowdingHint: 'Board turnover share 250-day percentile >90% = crowded; samples accumulate daily',
    macroTitle: 'Macro anchors (CN-US spread / release calendar)',
    spread10y: 'CN-US 10Y spread',
    spread2y: 'CN-US 2Y spread',
    releaseCalendar: 'Releases next 60d',
    releaseDate: 'Date',
    releaseCount: 'Companies',
    releaseValue: 'MV released',
    macroHint: 'Widening spread weighs on risk appetite; release peaks are monthly supply shocks',
    compositeTitle: 'Composite market state',
    scoreLabel: 'Score',
    kindPro: 'Pro-cyclical',
    kindContrarian: 'Contrarian',
    pctile: 'Pctile',
    samples: 'Samples',
    compositeHint: 'Each metric mapped to ~1-year rolling percentile then averaged (<20 samples skipped)',
    metricLabel: 'Metric',
    kindLabel: 'Kind',
    pending: 'backfilling',
    code: 'Code',
    name: 'Name',
    marginStocksTitle: 'Held-stock margin detail',
    marginStocksHint: 'Rising margin balance = leveraged money in; sharp drop = deleveraging (codes = watchlist ∪ ledger holdings)',
    rzyeYi: 'Margin balance (×1e8)',
    buyYi: 'Margin buy (×1e8)',
    chg1: 'Balance chg',
    valuationTitle: 'Index valuation percentile (PE-TTM)',
    valuationPe: 'PE-TTM',
    valuationEqual: 'Equal-wt',
    valuation1y: '1Y',
    valuation3y: '3Y',
    valuation5y: '5Y',
    valuationSamples: 'Samples',
    valuationUpdated: 'Updated',
    valuationWeek: 'w',
    valuationMonth: 'm',
    valuationLow: 'Cheap',
    valuationLowMid: 'Low',
    valuationMid: 'Neutral',
    valuationHighMid: 'High',
    valuationHigh: 'Expensive',
    valuationNoData: 'No valuation data yet — sync the valuation dataset first',
    valuationStale: 'Stale data',
    valuationStaleUnit: 'd',
    valuationInsufficient: 'Insufficient samples',
    valuationCheck: 'Cross-check',
    valuationChecking: 'Checking…',
    valuationCheckTitle: 'Official cross-check',
    valuationCheckLegu: 'Legu',
    valuationCheckOfficial: 'Official',
    valuationCheckDiff: 'Diff',
    valuationCheckStatus: 'Status',
    valuationCheckOk: 'Consistent',
    valuationCheckWarn: 'Methodology diff',
    valuationCheckError: 'Review',
    valuationCheckUnavailable: 'Unavailable',
    valuationCheckLatest: 'latest',
    valuationCheckFailed: 'Cross-check failed',
    valuationCheckNote:
      'Official sources publish only the current value (CSI: last 20 sessions; CNI: latest). Used for level checks, not percentile history; a difference is not automatically a data error.',
    valuationHighRatio: 'of high',
    valuationHint:
      'Percentile = rank of the current PE-TTM among weekly samples in the window; the parenthesised value is current PE ÷ that window’s highest PE. A low percentile means a low rank, not that PE is that percentage of the high (2% percentile ≠ 2% of the high). PE-TTM is the cap-weighted rolling PE from Legulegu; historical position only — not investment advice.',
    healthTitle: 'Data health check',
    healthScore: 'Health',
    healthOk: 'OK',
    healthWarn: 'Warn',
    healthError: 'Error',
    healthEmpty: 'Empty',
    healthLatest: 'Latest',
    healthIssues: 'Issues',
    healthRun: 'Re-check',
    healthOnline: 'Cross-source',
    healthClean: 'All checks passed',
    healthHint:
      'Rules: identities, ranges, trading days, jumps, cross-metric (sector vs turnover) and external spot checks (exchange/ChinaBond/Legu/CFFEX)',
  },
} as const;

// eslint-disable-next-line react-refresh/only-export-components -- display labels are co-located with the card registry
export const FUTURES_SYMBOL_LABELS: Record<string, string> = {
  IF: '沪深300',
  IH: '上证50',
  IC: '中证500',
  IM: '中证1000',
};

export interface ReviewCardProps {
  breadth: PersonalBreadthRow[];
  futures: PersonalFuturesRow[];
  margin: PersonalMarginRow[];
  limitUp: PersonalLimitUpRow[];
  pcr: PersonalPcrRow[];
  rank: PersonalFuturesRankRow[];
  flows: PersonalFlowsResponse | null;
  crowding: PersonalCrowdingResponse | null;
  macro: PersonalMacroResponse | null;
  composite: PersonalCompositeResponse | null;
  valuation: PersonalIndexValuationResponse | null;
  valuationCheck: PersonalIndexValuationCheckResponse | null;
  valuationCheckBusy: boolean;
  valuationCheckError: string;
  onCheckValuation: () => void;
  marginStocks: MarginStockEntry[];
  validation: PersonalValidationResponse | null;
  busy: boolean;
  onRefreshMarket: (dataset: 'futures' | 'margin' | 'valuation') => void;
  onValidate: (online: boolean) => void;
}

export type ReviewCardComponent = React.FC<ReviewCardProps>;

export interface ReviewCardSlot {
  id: string;
  component: ReviewCardComponent;
}

function useReviewCopy() {
  const { language } = useUiLanguage();
  return REVIEW_COPY[language];
}

function yi(value: number | null | undefined, digits = 1, suffix = '亿'): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) / 1e8).toFixed(digits)}${suffix}`;
}

function signed(value: number | null | undefined, digits = 2, suffix = ''): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const num = Number(value);
  return `${num > 0 ? '+' : ''}${num.toFixed(digits)}${suffix}`;
}

function signedYi(value: number | null | undefined, suffix = '亿'): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const num = Number(value) / 1e8;
  return `${num > 0 ? '+' : ''}${num.toFixed(1)}${suffix}`;
}

const CHART_TOOLTIP_STYLE = {
  background: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 12,
  color: 'hsl(var(--foreground))',
};

const TABLE_HEAD_CLASS =
  'border-b border-border/60 text-left text-xs uppercase tracking-[0.12em] text-secondary-text';
const TABLE_CELL_CLASS =
  'border-b border-border/40 py-2 pr-4 text-sm text-foreground';

/* ------------------------------------------------------------------ */
/* 市场宽度（阿姆氏 TRIN）                                              */
/* ------------------------------------------------------------------ */

export const BreadthCard: ReviewCardComponent = ({ breadth }) => {
  const copy = useReviewCopy();
  const latest = breadth.length ? breadth[breadth.length - 1] : null;
  const recent = breadth.slice(-30);
  const chartData = recent
    .filter((row) => row.trin !== null)
    .map((row) => ({ date: row.trade_date.slice(5), trin: row.trin }));

  if (!latest) {
    return (
      <Card title={copy.breadthTitle} variant="bordered" className="xl:col-span-2">
        <p className="text-sm text-secondary-text">{copy.noData}</p>
        <p className="mt-2 text-xs text-muted-text">{copy.breadthHint}</p>
      </Card>
    );
  }

  const signal =
    latest.signal_tag === '顶部信号'
      ? { label: copy.signalTop, variant: 'danger' as const }
      : latest.signal_tag === '底部信号'
        ? { label: copy.signalBottom, variant: 'success' as const }
        : null;

  return (
    <Card title={copy.breadthTitle} variant="bordered" className="xl:col-span-2">
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <div className="text-3xl font-semibold text-foreground">
            {latest.trin?.toFixed(3) ?? '—'}
          </div>
          <div className="mt-1 text-xs text-secondary-text">{copy.trin}</div>
        </div>
        <Badge variant="info">{latest.band || '—'}</Badge>
        <div className="text-sm text-secondary-text">
          {copy.pct} {latest.trin_pct?.toFixed(0) ?? '—'}% · {copy.advRatio}{' '}
          {latest.adv_ratio?.toFixed(1) ?? '—'}%
        </div>
        <div className="text-sm text-secondary-text">
          {copy.index} {latest.index_close?.toFixed(2) ?? '—'}（
          <span className={latest.index_chg_pct && latest.index_chg_pct < 0 ? 'text-emerald-600' : 'text-rose-600'}>
            {signed(latest.index_chg_pct, 2, '%')}
          </span>
          ）
        </div>
        {signal ? <Badge variant={signal.variant}>{signal.label}</Badge> : null}
      </div>

      <p className="mt-3 text-sm text-foreground">{copy.interpretation}: {latest.interpretation || '—'}</p>
      {latest.signal_detail ? (
        <p className="mt-1 text-xs text-secondary-text">{latest.signal_detail}</p>
      ) : null}

      <div className="mt-4 h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
            <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={44} />
            <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
            <Line
              type="monotone"
              dataKey="trin"
              name={copy.trin}
              stroke="var(--color-cyan)"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className={TABLE_HEAD_CLASS}>
              <th className="py-2 pr-4">{copy.day}</th>
              <th className="py-2 pr-4">{copy.trin}</th>
              <th className="py-2 pr-4">{copy.pct}</th>
              <th className="py-2 pr-4">{copy.up}</th>
              <th className="py-2 pr-4">{copy.down}</th>
              <th className="py-2">{copy.interpretation}</th>
            </tr>
          </thead>
          <tbody>
            {breadth.slice(-5).reverse().map((row) => (
              <tr key={row.trade_date}>
                <td className={TABLE_CELL_CLASS}>{row.trade_date}</td>
                <td className={TABLE_CELL_CLASS}>{row.trin?.toFixed(3) ?? '—'}</td>
                <td className={TABLE_CELL_CLASS}>{row.trin_pct?.toFixed(0) ?? '—'}%</td>
                <td className={TABLE_CELL_CLASS}>{row.up_count}</td>
                <td className={TABLE_CELL_CLASS}>{row.down_count}</td>
                <td className={TABLE_CELL_CLASS}>{row.interpretation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-muted-text">
        {copy.breadthHint} · {latest.trade_date}（{latest.source}）
      </p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 股指期货做空压力                                                     */
/* ------------------------------------------------------------------ */

export const FuturesCard: ReviewCardComponent = ({ futures, busy, onRefreshMarket }) => {
  const copy = useReviewCopy();
  const symbols = ['IF', 'IH', 'IC', 'IM'];
  const latestBySymbol = new Map<string, PersonalFuturesRow>();
  for (const row of futures) {
    latestBySymbol.set(row.symbol, row);
  }
  const chartData = (() => {
    const byDate = new Map<string, Record<string, number | null>>();
    for (const row of futures.slice(-120)) {
      if (row.basis_pct === null) continue;
      const key = row.trade_date.slice(5);
      const entry = byDate.get(key) ?? {};
      entry[row.symbol] = row.basis_pct;
      byDate.set(key, entry);
    }
    return Array.from(byDate.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([date, values]) => ({ date, ...values }));
  })();
  const SERIES_COLORS: Record<string, string> = {
    IF: 'var(--color-cyan)',
    IH: '#f59e0b',
    IC: '#8b5cf6',
    IM: '#10b981',
  };

  return (
    <Card title={copy.futuresTitle} variant="bordered">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => onRefreshMarket('futures')}
          disabled={busy}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/60 bg-card/60 px-2.5 text-xs font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
          {busy ? copy.refreshing : copy.refresh}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className={TABLE_HEAD_CLASS}>
              <th className="py-2 pr-4">{copy.contract}</th>
              <th className="py-2 pr-4 text-right">{copy.futuresClose}</th>
              <th className="py-2 pr-4 text-right">{copy.spot}</th>
              <th className="py-2 pr-4 text-right">{copy.basis}</th>
              <th className="py-2 pr-4 text-right">{copy.basisPct}</th>
              <th className="py-2 pr-4 text-right">{copy.oi}</th>
              <th className="py-2 text-right">{copy.oiChg}</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map((symbol) => {
              const row = latestBySymbol.get(symbol);
              return (
                <tr key={symbol}>
                  <td className={TABLE_CELL_CLASS}>
                    {symbol} · {FUTURES_SYMBOL_LABELS[symbol]}
                  </td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{row?.close?.toFixed(1) ?? '—'}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{row?.index_close?.toFixed(1) ?? '—'}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{signed(row?.basis, 1)}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>
                    <span className={row?.basis_pct !== null && row?.basis_pct !== undefined && row.basis_pct < 0 ? 'text-rose-600' : 'text-emerald-600'}>
                      {signed(row?.basis_pct, 2, '%')}
                    </span>
                  </td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>
                    {row?.open_interest ? row.open_interest.toLocaleString() : '—'}
                  </td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{signed(row?.oi_chg, 0)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {chartData.length > 1 ? (
        <div className="mt-3 h-44 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
              <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={48} unit="%" />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Legend />
              {symbols.map((symbol) => (
                <Line
                  key={symbol}
                  type="monotone"
                  dataKey={symbol}
                  name={`${symbol} ${FUTURES_SYMBOL_LABELS[symbol]}`}
                  stroke={SERIES_COLORS[symbol]}
                  strokeWidth={1.6}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-3 text-sm text-secondary-text">{copy.noData}</p>
      )}

      <p className="mt-3 flex items-center gap-1 text-xs text-muted-text">
        <TrendingDown className="h-3.5 w-3.5" />
        {copy.futuresHint}
      </p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 融资余额                                                             */
/* ------------------------------------------------------------------ */

export const MarginCard: ReviewCardComponent = ({ margin, busy, onRefreshMarket }) => {
  const copy = useReviewCopy();
  const byDate = new Map<string, PersonalMarginRow[]>();
  for (const row of margin) {
    const list = byDate.get(row.trade_date) ?? [];
    list.push(row);
    byDate.set(row.trade_date, list);
  }
  const dates = Array.from(byDate.keys()).sort();
  const latest = dates.length ? byDate.get(dates[dates.length - 1])! : [];
  const prev = dates.length > 5 ? byDate.get(dates[dates.length - 6]) : undefined;
  const latestTotal = latest.find((row) => row.scope === copy.total);
  const prevTotal = prev?.find((row) => row.scope === copy.total);
  const chg5 =
    latestTotal?.rzye !== null &&
    latestTotal?.rzye !== undefined &&
    prevTotal?.rzye !== null &&
    prevTotal?.rzye !== undefined
      ? latestTotal.rzye - prevTotal.rzye
      : null;
  const boards = latest
    .filter((row) => row.scope_type === 'board')
    .sort((a, b) => (b.rzye ?? 0) - (a.rzye ?? 0));
  const marketRows = latest.filter((row) => row.scope_type === 'market' && row.scope !== copy.total);
  const chartData = dates
    .slice(-20)
    .map((day) => {
      const total = byDate.get(day)?.find((row) => row.scope === copy.total);
      return { date: day.slice(5), rzye: total?.rzye !== null && total?.rzye !== undefined ? total.rzye / 1e8 : null };
    });

  return (
    <Card title={copy.marginTitle} variant="bordered">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => onRefreshMarket('margin')}
          disabled={busy}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/60 bg-card/60 px-2.5 text-xs font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
          {busy ? copy.refreshing : copy.refresh}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div>
          <div className="text-3xl font-semibold text-foreground">
            {latestTotal ? yi(latestTotal.rzye, 1, copy.unitYi) : '—'}
          </div>
          <div className="mt-1 text-xs text-secondary-text">{copy.rzye} · {copy.total}</div>
        </div>
        <div className="text-sm text-secondary-text">
          {copy.chg5}{' '}
          <span className={chg5 !== null && chg5 >= 0 ? 'text-rose-600' : 'text-emerald-600'}>
            {chg5 === null ? '—' : signedYi(chg5, copy.unitYi)}
          </span>
        </div>
        {marketRows.map((row) => (
          <div key={row.scope} className="text-sm text-secondary-text">
            {row.scope} {yi(row.rzye, 1, copy.unitYi)}
          </div>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className={TABLE_HEAD_CLASS}>
              <th className="py-2 pr-4">{copy.board}</th>
              <th className="py-2 pr-4 text-right">{copy.rzye}</th>
              <th className="py-2 pr-4 text-right">{copy.buy}</th>
              <th className="py-2 text-right">{copy.rqye}</th>
            </tr>
          </thead>
          <tbody>
            {boards.map((row) => (
              <tr key={row.scope}>
                <td className={TABLE_CELL_CLASS}>
                  <span className="inline-flex items-center gap-1.5">
                    <Landmark className="h-3.5 w-3.5 text-secondary-text" />
                    {row.scope}
                  </span>
                </td>
                <td className={`${TABLE_CELL_CLASS} text-right`}>{yi(row.rzye, 1, copy.unitYi)}</td>
                <td className={`${TABLE_CELL_CLASS} text-right`}>{yi(row.rzye_buy, 1, copy.unitYi)}</td>
                <td className={`${TABLE_CELL_CLASS} text-right`}>{row.rqye ? yi(row.rqye, 1, copy.unitYi) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {chartData.length > 1 ? (
        <div className="mt-3 h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
              <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={52} />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Line
                type="monotone"
                dataKey="rzye"
                name={copy.rzye}
                stroke="var(--color-cyan)"
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-3 text-sm text-secondary-text">{copy.noData}</p>
      )}

      <p className="mt-3 text-xs text-muted-text">{copy.marginHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 指数估值分位（PE-TTM）                                                */
/* ------------------------------------------------------------------ */

function valuationZoneMeta(
  percentile: number | null,
  copy: ReturnType<typeof useReviewCopy>,
): { label: string; text: string; bar: string } {
  if (percentile === null) {
    return {
      label: copy.valuationInsufficient,
      text: 'text-secondary-text',
      bar: 'bg-secondary-text/40',
    };
  }
  if (percentile <= 20) {
    return { label: copy.valuationLow, text: 'text-success', bar: 'bg-success' };
  }
  if (percentile <= 40) {
    return { label: copy.valuationLowMid, text: 'text-success', bar: 'bg-success/60' };
  }
  if (percentile <= 60) {
    return { label: copy.valuationMid, text: 'text-cyan', bar: 'bg-cyan/60' };
  }
  if (percentile <= 80) {
    return { label: copy.valuationHighMid, text: 'text-warning', bar: 'bg-warning' };
  }
  return { label: copy.valuationHigh, text: 'text-danger', bar: 'bg-danger' };
}

export const IndexValuationCard: ReviewCardComponent = ({
  valuation,
  valuationCheck,
  valuationCheckBusy,
  valuationCheckError,
  busy,
  onRefreshMarket,
  onCheckValuation,
}) => {
  const copy = useReviewCopy();
  const { language } = useUiLanguage();
  if (!valuation || !valuation.available) {
    return (
      <Card title={copy.valuationTitle} variant="bordered" className="xl:col-span-2">
        <p className="text-sm text-secondary-text">{copy.valuationNoData}</p>
        <p className="mt-2 text-xs text-muted-text">{copy.valuationHint}</p>
      </Card>
    );
  }

  const rows = valuation.rows.filter((row) => row.available);
  const staleRows = rows.filter((row) => (row.stale_days ?? 0) > 7);
  const windows = [
    ['1y', copy.valuation1y],
    ['3y', copy.valuation3y],
    ['5y', copy.valuation5y],
  ] as const;
  const freqSuffix = (freq: string) =>
    freq === 'weekly' ? copy.valuationWeek : freq === 'monthly' ? copy.valuationMonth : '';
  const checkBadge = (status: string) => {
    if (status === 'ok') return { variant: 'success' as const, label: copy.valuationCheckOk };
    if (status === 'warn') return { variant: 'warning' as const, label: copy.valuationCheckWarn };
    if (status === 'error') return { variant: 'danger' as const, label: copy.valuationCheckError };
    return { variant: 'default' as const, label: copy.valuationCheckUnavailable };
  };

  return (
    <Card title={copy.valuationTitle} variant="bordered" className="xl:col-span-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-secondary-text">
          {valuation.as_of ? `${copy.valuationUpdated} ${valuation.as_of}` : ''}
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onCheckValuation}
            disabled={valuationCheckBusy}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/60 bg-card/60 px-2.5 text-xs font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:opacity-50"
          >
            <ShieldCheck className={`h-3.5 w-3.5 ${valuationCheckBusy ? 'animate-pulse' : ''}`} />
            {valuationCheckBusy ? copy.valuationChecking : copy.valuationCheck}
          </button>
          <button
            type="button"
            onClick={() => onRefreshMarket('valuation')}
            disabled={busy}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/60 bg-card/60 px-2.5 text-xs font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
            {busy ? copy.refreshing : copy.refresh}
          </button>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[720px]">
          <thead>
            <tr className={TABLE_HEAD_CLASS}>
              <th className="py-2 pr-4">{copy.name}</th>
              <th className="py-2 pr-4 text-right">{copy.valuationPe}</th>
              {windows.map(([key, label]) => (
                <th key={key} className="py-2 pr-4 text-right">
                  {label}
                </th>
              ))}
              <th className="py-2 pr-4 text-right">{copy.valuationSamples}</th>
              <th className="py-2 text-right">{copy.valuationUpdated}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const oneYear = row.windows['1y'];
              return (
                <tr key={row.code}>
                  <td className={TABLE_CELL_CLASS}>
                    <div className="font-medium text-foreground">{row.name}</div>
                    <div className="text-xs text-muted-text">{row.code}</div>
                  </td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>
                    <div className="font-semibold text-foreground">
                      {row.pe_ttm?.toFixed(2) ?? '—'}
                    </div>
                    <div className="text-[10px] text-muted-text">
                      {copy.valuationEqual} {row.pe_ttm_equal?.toFixed(2) ?? '—'}
                    </div>
                  </td>
                  {windows.map(([key]) => {
                    const window = row.windows[key];
                    const meta = valuationZoneMeta(window?.percentile ?? null, copy);
                    const percentile = window?.percentile ?? null;
                    const highRatio =
                      row.pe_ttm != null && window?.pe_max != null && window.pe_max > 0
                        ? (row.pe_ttm / window.pe_max) * 100
                        : null;
                    const ratioText =
                      highRatio === null
                        ? ''
                        : language === 'zh'
                          ? `（最高 ${highRatio.toFixed(1)}%）`
                          : ` (${highRatio.toFixed(1)}% of high)`;
                    return (
                      <td key={key} className={`${TABLE_CELL_CLASS} text-right`}>
                        <div className="flex flex-col items-end gap-1">
                          <span className={`text-sm font-medium ${meta.text}`}>
                            {percentile === null ? '—' : `${percentile.toFixed(1)}%`}
                            {ratioText ? (
                              <span className="text-[10px] font-normal text-muted-text">
                                {ratioText}
                              </span>
                            ) : null}
                          </span>
                          <div className="h-1 w-14 overflow-hidden rounded-full bg-border/50">
                            <div
                              className={`h-full rounded-full ${meta.bar}`}
                              style={{ width: `${percentile === null ? 0 : Math.max(2, percentile)}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-muted-text">{meta.label}</span>
                        </div>
                      </td>
                    );
                  })}
                  <td className={`${TABLE_CELL_CLASS} text-right text-xs text-secondary-text`}>
                    {oneYear ? `${oneYear.samples}${freqSuffix(row.sample_freq)}` : '—'}
                  </td>
                  <td className={`${TABLE_CELL_CLASS} text-right text-xs text-secondary-text`}>
                    {row.as_of ?? '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {valuationCheckError ? (
        <p className="mt-3 text-xs text-danger">
          {copy.valuationCheckFailed}: {valuationCheckError}
        </p>
      ) : null}

      {valuationCheck ? (
        <div className="mt-4 border-t border-border/50 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-foreground">{copy.valuationCheckTitle}</h4>
            <span className="text-xs text-muted-text">{valuationCheck.checked_at}</span>
          </div>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead>
                <tr className={TABLE_HEAD_CLASS}>
                  <th className="py-2 pr-4">{copy.name}</th>
                  <th className="py-2 pr-4 text-right">{copy.valuationCheckLegu}</th>
                  <th className="py-2 pr-4 text-right">{copy.valuationCheckOfficial}</th>
                  <th className="py-2 pr-4 text-right">{copy.valuationCheckDiff}</th>
                  <th className="py-2">{copy.valuationCheckStatus}</th>
                </tr>
              </thead>
              <tbody>
                {valuationCheck.rows.map((row) => {
                  const badge = checkBadge(row.status);
                  return (
                    <tr key={row.code}>
                      <td className={TABLE_CELL_CLASS}>
                        <div className="font-medium text-foreground">{row.name}</div>
                        <div className="text-[10px] text-muted-text">
                          {row.legu_label ?? '—'} / {row.official_metric ?? '—'}
                        </div>
                      </td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>
                        {row.legu_pe?.toFixed(2) ?? '—'}
                      </td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>
                        <div>{row.official_pe?.toFixed(2) ?? '—'}</div>
                        <div className="text-[10px] text-muted-text">
                          {row.official_source ?? '—'} ·{' '}
                          {row.official_date ?? copy.valuationCheckLatest}
                        </div>
                      </td>
                      <td
                        className={`${TABLE_CELL_CLASS} text-right ${
                          row.diff_pct === null
                            ? 'text-secondary-text'
                            : Math.abs(row.diff_pct) <= 5
                              ? 'text-success'
                              : 'text-warning'
                        }`}
                      >
                        {row.diff_pct === null
                          ? '—'
                          : `${row.diff_pct > 0 ? '+' : ''}${row.diff_pct.toFixed(1)}%`}
                      </td>
                      <td className={TABLE_CELL_CLASS}>
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                        <div className="mt-1 text-[10px] text-muted-text">{row.detail}</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {valuationCheck.warnings.length ? (
            <ul className="mt-2 space-y-1">
              {valuationCheck.warnings.map((warning, index) => (
                <li key={`${warning}-${index}`} className="text-xs text-warning">
                  {warning}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="mt-2 text-xs text-muted-text">{valuationCheck.note}</p>
        </div>
      ) : null}

      {staleRows.length ? (
        <p className="mt-3 text-xs text-warning">
          {copy.valuationStale} {staleRows[0].stale_days} {copy.valuationStaleUnit}:{' '}
          {staleRows.map((row) => row.name).join(', ')}
        </p>
      ) : null}
      <p className="mt-3 text-xs text-muted-text">{copy.valuationHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 扩展占位卡                                                            */
/* ------------------------------------------------------------------ */

const MoreCard: ReviewCardComponent = () => {
  const copy = useReviewCopy();
  return (
    <div className="rounded-2xl border border-dashed border-border/60 p-6">
      <h3 className="text-sm font-semibold text-secondary-text">{copy.moreTitle}</h3>
      <p className="mt-2 text-sm text-muted-text">{copy.moreList}</p>
      <p className="mt-3 text-xs text-muted-text">
        RM-31 · docs/ROADMAP_PERSONAL.md — REVIEW_CARDS 注册表里加一项即可
      </p>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* 涨停梯队与亏钱效应                                                    */
/* ------------------------------------------------------------------ */

export const LimitUpCard: ReviewCardComponent = ({ limitUp }) => {
  const copy = useReviewCopy();
  const latest = limitUp.length ? limitUp[limitUp.length - 1] : null;
  const chartData = limitUp.slice(-30).map((row) => ({
    date: row.trade_date.slice(5),
    zt: row.zt_count,
    carry: row.prev_zt_mean,
  }));

  if (!latest) {
    return (
      <Card title={copy.limitupTitle} variant="bordered">
        <p className="text-sm text-secondary-text">{copy.noData}</p>
        <p className="mt-2 text-xs text-muted-text">{copy.limitupHint}</p>
      </Card>
    );
  }

  return (
    <Card title={copy.limitupTitle} variant="bordered">
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <div className="text-3xl font-semibold text-foreground">{latest.zt_count}</div>
          <div className="mt-1 text-xs text-secondary-text">{copy.ztCount}</div>
        </div>
        <div className="text-sm text-secondary-text">
          {copy.firstBoard} {latest.first_board} · {copy.streakGe2} {latest.streak_ge2} · {copy.maxStreak}{' '}
          <span className="font-semibold text-foreground">{latest.max_streak}</span>
        </div>
        <div className="text-sm text-secondary-text">
          {copy.zbRate}{' '}
          {latest.zb_rate !== null ? (
            <Badge variant={latest.zb_rate >= 0.4 ? 'danger' : 'success'}>
              {(latest.zb_rate * 100).toFixed(0)}%
            </Badge>
          ) : (
            '—'
          )}
        </div>
        <div className="text-sm text-secondary-text">
          {copy.prevZtMean}{' '}
          <span
            className={
              latest.prev_zt_mean !== null && latest.prev_zt_mean < 0
                ? 'text-emerald-600'
                : 'text-rose-600'
            }
          >
            {signed(latest.prev_zt_mean, 2, '%')}
          </span>
          {latest.prev_zt_up_ratio !== null ? `（${latest.prev_zt_up_ratio.toFixed(0)}% ${copy.prevZtUpRatio}）` : ''}
        </div>
      </div>

      {chartData.length > 1 ? (
        <div className="mt-3 h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
              <YAxis yAxisId="l" tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={36} />
              <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={40} unit="%" />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Legend />
              <Line yAxisId="l" type="monotone" dataKey="zt" name={copy.ztCount} stroke="var(--color-cyan)" strokeWidth={2} dot={false} />
              <Line yAxisId="r" type="monotone" dataKey="carry" name={copy.prevZtMean} stroke="#f59e0b" strokeWidth={1.6} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-3 text-sm text-secondary-text">{copy.noData}</p>
      )}

      <p className="mt-3 text-xs text-muted-text">{copy.limitupHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 期指会员持仓（前 20）                                                 */
/* ------------------------------------------------------------------ */

export const FuturesRankCard: ReviewCardComponent = ({ rank }) => {
  const copy = useReviewCopy();
  const symbols = ['IF', 'IH', 'IC', 'IM'];
  const latestBySymbol = new Map<string, PersonalFuturesRankRow>();
  for (const row of rank) {
    latestBySymbol.set(row.symbol, row);
  }
  const chartData = (() => {
    const byDate = new Map<string, Record<string, number | null>>();
    for (const row of rank.slice(-120)) {
      if (row.net_ratio === null) continue;
      const key = row.trade_date.slice(5);
      const entry = byDate.get(key) ?? {};
      entry[row.symbol] = row.net_ratio;
      byDate.set(key, entry);
    }
    return Array.from(byDate.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([date, values]) => ({ date, ...values }));
  })();
  const SERIES_COLORS: Record<string, string> = {
    IF: 'var(--color-cyan)', IH: '#f59e0b', IC: '#8b5cf6', IM: '#10b981',
  };

  return (
    <Card title={copy.rankTitle} variant="bordered">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className={TABLE_HEAD_CLASS}>
              <th className="py-2 pr-4">{copy.contract}</th>
              <th className="py-2 pr-4 text-right">{copy.top20Buy}</th>
              <th className="py-2 pr-4 text-right">{copy.top20Sell}</th>
              <th className="py-2 pr-4 text-right">{copy.net}</th>
              <th className="py-2 text-right">{copy.netRatio}</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map((symbol) => {
              const row = latestBySymbol.get(symbol);
              return (
                <tr key={symbol}>
                  <td className={TABLE_CELL_CLASS}>{symbol} · {FUTURES_SYMBOL_LABELS[symbol]}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{row?.top20_buy?.toLocaleString() ?? '—'}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{row?.top20_sell?.toLocaleString() ?? '—'}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{signed(row?.net, 0)}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>
                    <span className={row?.net_ratio !== null && row?.net_ratio !== undefined && row.net_ratio > 0 ? 'text-rose-600' : 'text-emerald-600'}>
                      {signed(row?.net_ratio !== undefined && row?.net_ratio !== null ? row.net_ratio * 100 : null, 2, '%')}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {chartData.length > 1 ? (
        <div className="mt-3 h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
              <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={52} />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Legend />
              {symbols.map((symbol) => (
                <Line
                  key={symbol}
                  type="monotone"
                  dataKey={symbol}
                  name={`${symbol} ${FUTURES_SYMBOL_LABELS[symbol]}`}
                  stroke={SERIES_COLORS[symbol]}
                  strokeWidth={1.6}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-3 text-sm text-secondary-text">{copy.noData}</p>
      )}

      <p className="mt-3 text-xs text-muted-text">{copy.rankHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 期权 PCR                                                              */
/* ------------------------------------------------------------------ */

export const PcrCard: ReviewCardComponent = ({ pcr }) => {
  const copy = useReviewCopy();
  const latest = pcr.length ? pcr[pcr.length - 1] : null;
  const chartData = pcr.slice(-30).map((row) => ({
    date: row.trade_date.slice(5),
    pcr: row.pcr_vol,
  }));

  if (!latest) {
    return (
      <Card title={copy.pcrTitle} variant="bordered">
        <p className="text-sm text-secondary-text">{copy.noData}</p>
        <p className="mt-2 text-xs text-muted-text">{copy.pcrHint}</p>
      </Card>
    );
  }

  return (
    <Card title={copy.pcrTitle} variant="bordered">
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <div className="text-3xl font-semibold text-foreground">
            {latest.pcr_vol?.toFixed(3) ?? '—'}
          </div>
          <div className="mt-1 text-xs text-secondary-text">{copy.pcrVol}</div>
        </div>
        <div className="text-sm text-secondary-text">
          {copy.pcrOi} {latest.pcr_oi?.toFixed(3) ?? '—'}
        </div>
        <div className="text-sm text-secondary-text">
          {copy.callVol} {(latest.call_vol ?? 0).toLocaleString()} · {copy.putVol} {(latest.put_vol ?? 0).toLocaleString()}
        </div>
      </div>

      {chartData.length > 1 ? (
        <div className="mt-3 h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
              <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={44} />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Line type="monotone" dataKey="pcr" name={copy.pcrVol} stroke="var(--color-cyan)" strokeWidth={2} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-3 text-sm text-secondary-text">{copy.noData}</p>
      )}

      <p className="mt-3 text-xs text-muted-text">{copy.pcrHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 资金面（两融占比 / ETF 份额 / 成交额）                                 */
/* ------------------------------------------------------------------ */

function signedRatio(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}`;
}

export const FlowsCard: ReviewCardComponent = ({ flows }) => {
  const copy = useReviewCopy();
  if (!flows || (flows.margin_ratio.length === 0 && flows.etf_share.length === 0)) {
    return (
      <Card title={copy.flowsTitle} variant="bordered">
        <p className="text-sm text-secondary-text">{copy.noData}</p>
        <p className="mt-2 text-xs text-muted-text">{copy.flowsHint}</p>
      </Card>
    );
  }
  const ratioLatest = flows.margin_ratio.length ? flows.margin_ratio[flows.margin_ratio.length - 1] : null;
  const chartData = flows.margin_ratio.slice(-30).map((row) => ({
    date: row.trade_date.slice(5),
    ratio: row.ratio_pct,
  }));
  const byDate = new Map<string, PersonalFlowsResponse['etf_share']>();
  for (const row of flows.etf_share) {
    const list = byDate.get(row.trade_date) ?? [];
    list.push(row);
    byDate.set(row.trade_date, list);
  }
  const dates = Array.from(byDate.keys()).sort();
  const etfLatest = dates.length ? byDate.get(dates[dates.length - 1]) ?? [] : [];
  const etfPrev = dates.length > 1 ? byDate.get(dates[dates.length - 2]) ?? [] : [];
  const prevByCode = new Map(etfPrev.map((row) => [row.code, row.share_yi]));

  return (
    <Card title={copy.flowsTitle} variant="bordered">
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <div className="text-3xl font-semibold text-foreground">
            {ratioLatest ? `${ratioLatest.ratio_pct.toFixed(2)}%` : '—'}
          </div>
          <div className="mt-1 text-xs text-secondary-text">{copy.marginRatio}</div>
        </div>
        {ratioLatest ? (
          <Badge variant={ratioLatest.ratio_pct >= 10 ? 'danger' : ratioLatest.ratio_pct <= 7 ? 'success' : 'info'}>
            {ratioLatest.ratio_pct >= 10 ? '过热' : ratioLatest.ratio_pct <= 7 ? '冰点' : '中性'}
          </Badge>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-muted-text">{copy.marginRatioHint}</p>

      {chartData.length > 1 ? (
        <div className="mt-3 h-36 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
              <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={44} unit="%" />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Line type="monotone" dataKey="ratio" name={copy.marginRatio} stroke="var(--color-cyan)" strokeWidth={2} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      {etfLatest.length ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className={TABLE_HEAD_CLASS}>
                <th className="py-2 pr-4">{copy.etfShare}</th>
                <th className="py-2 pr-4 text-right">{copy.shareUnit}</th>
                <th className="py-2 text-right">{copy.day}</th>
              </tr>
            </thead>
            <tbody>
              {etfLatest.map((row) => {
                const prev = prevByCode.get(row.code);
                const chg =
                  row.share_yi !== null && prev !== null && prev !== undefined
                    ? row.share_yi - prev
                    : null;
                return (
                  <tr key={row.code}>
                    <td className={TABLE_CELL_CLASS}>{row.name || row.code}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>{row.share_yi?.toFixed(1) ?? '—'}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      <span
                        className={
                          chg !== null && chg > 0
                            ? 'text-rose-600'
                            : chg !== null && chg < 0
                              ? 'text-emerald-600'
                              : 'text-secondary-text'
                        }
                      >
                        {chg === null ? '—' : signedRatio(chg)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <p className="mt-3 text-xs text-muted-text">{copy.flowsHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 行业拥挤度                                                            */
/* ------------------------------------------------------------------ */

export const CrowdingCard: ReviewCardComponent = ({ crowding }) => {
  const copy = useReviewCopy();
  if (!crowding || crowding.rows.length === 0) {
    return (
      <Card title={copy.crowdingTitle} variant="bordered">
        <p className="text-sm text-secondary-text">{copy.noData}</p>
        <p className="mt-2 text-xs text-muted-text">{copy.crowdingHint}</p>
      </Card>
    );
  }
  return (
    <Card title={copy.crowdingTitle} variant="bordered">
      <p className="mb-2 text-xs text-secondary-text">{crowding.trade_date}</p>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className={TABLE_HEAD_CLASS}>
              <th className="py-2 pr-4">{copy.board}</th>
              <th className="py-2 pr-4 text-right">{copy.amountYi}</th>
              <th className="py-2 pr-4 text-right">{copy.sharePct}</th>
              <th className="py-2 text-right">{copy.sharePctile}</th>
            </tr>
          </thead>
          <tbody>
            {crowding.rows.map((row) => (
              <tr key={row.board}>
                <td className={TABLE_CELL_CLASS}>
                  <span className={row.pct_chg !== null && row.pct_chg < 0 ? 'text-emerald-600' : 'text-rose-600'}>
                    {row.board}
                  </span>
                </td>
                <td className={`${TABLE_CELL_CLASS} text-right`}>{row.amount_yi?.toFixed(1) ?? '—'}</td>
                <td className={`${TABLE_CELL_CLASS} text-right`}>{row.share_pct?.toFixed(2) ?? '—'}%</td>
                <td className={`${TABLE_CELL_CLASS} text-right`}>
                  <Badge variant={(row.share_pctile ?? 0) >= 90 ? 'danger' : (row.share_pctile ?? 0) >= 75 ? 'warning' : 'default'}>
                    {row.share_pctile?.toFixed(0) ?? '—'}%
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-muted-text">{copy.crowdingHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 宏观锚（中美利差 / 解禁日历）                                          */
/* ------------------------------------------------------------------ */

export const MacroCard: ReviewCardComponent = ({ macro }) => {
  const copy = useReviewCopy();
  if (!macro || (macro.bond_yield.length === 0 && macro.release.length === 0)) {
    return (
      <Card title={copy.macroTitle} variant="bordered">
        <p className="text-sm text-secondary-text">{copy.noData}</p>
      </Card>
    );
  }
  const spread = macro.bond_yield.filter((row) => row.spread_10y !== null);
  const latestSpread = spread.length ? spread[spread.length - 1] : null;
  const chartData = spread.slice(-120).map((row) => ({
    date: row.trade_date.slice(5),
    spread: row.spread_10y,
  }));

  return (
    <Card title={copy.macroTitle} variant="bordered">
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <div className="text-3xl font-semibold text-foreground">
            {latestSpread ? `${latestSpread.spread_10y?.toFixed(2)}%` : '—'}
          </div>
          <div className="mt-1 text-xs text-secondary-text">{copy.spread10y}</div>
        </div>
        {latestSpread ? (
          <div className="text-sm text-secondary-text">
            {copy.spread2y} {latestSpread.spread_2y?.toFixed(2) ?? '—'}%
          </div>
        ) : null}
      </div>

      {chartData.length > 1 ? (
        <div className="mt-3 h-36 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
              <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={48} unit="%" />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
              <Line type="monotone" dataKey="spread" name={copy.spread10y} stroke="#8b5cf6" strokeWidth={2} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      {macro.release.length ? (
        <>
          <h4 className="mt-4 text-sm font-semibold text-foreground">{copy.releaseCalendar}</h4>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className={TABLE_HEAD_CLASS}>
                  <th className="py-2 pr-4">{copy.releaseDate}</th>
                  <th className="py-2 pr-4 text-right">{copy.releaseCount}</th>
                  <th className="py-2 text-right">{copy.releaseValue}</th>
                </tr>
              </thead>
              <tbody>
                {macro.release.slice(0, 10).map((row) => (
                  <tr key={row.release_date}>
                    <td className={TABLE_CELL_CLASS}>{row.release_date}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>{row.company_count}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      {row.market_value_yi !== null ? row.market_value_yi.toFixed(1) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      <p className="mt-3 text-xs text-muted-text">{copy.macroHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 综合状态（多指标分位印证）                                             */
/* ------------------------------------------------------------------ */

export const CompositeCard: ReviewCardComponent = ({ composite }) => {
  const copy = useReviewCopy();
  if (!composite) {
    return (
      <Card title={copy.compositeTitle} variant="bordered" className="xl:col-span-2">
        <p className="text-sm text-secondary-text">{copy.pending}</p>
      </Card>
    );
  }
  return (
    <Card title={copy.compositeTitle} variant="bordered" className="xl:col-span-2">
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <div className="text-3xl font-semibold text-foreground">
            {composite.score !== null ? composite.score.toFixed(0) : '—'}
          </div>
          <div className="mt-1 text-xs text-secondary-text">{copy.scoreLabel}</div>
        </div>
        <Badge
          variant={
            composite.score !== null && composite.score >= 75
              ? 'danger'
              : composite.score !== null && composite.score <= 25
                ? 'success'
                : 'info'
          }
        >
          {composite.state}
        </Badge>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className={TABLE_HEAD_CLASS}>
              <th className="py-2 pr-4">{copy.metricLabel}</th>
              <th className="py-2 pr-4">{copy.kindLabel}</th>
              <th className="py-2 pr-4 text-right">{copy.pctile}</th>
              <th className="py-2 text-right">{copy.samples}</th>
            </tr>
          </thead>
          <tbody>
            {composite.components.map((component) => (
              <tr key={component.metric}>
                <td className={TABLE_CELL_CLASS}>{component.label}</td>
                <td className={TABLE_CELL_CLASS}>
                  <Badge variant={component.kind === 'pro' ? 'info' : 'warning'}>
                    {component.kind === 'pro' ? copy.kindPro : copy.kindContrarian}
                  </Badge>
                </td>
                <td className={`${TABLE_CELL_CLASS} text-right`}>{component.percentile?.toFixed(0) ?? '—'}%</td>
                <td className={`${TABLE_CELL_CLASS} text-right`}>{component.sample_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-muted-text">{copy.compositeHint}</p>
    </Card>
  );
};

/* ------------------------------------------------------------------ */
/* 持仓股两融（RM-42）                                                  */
/* ------------------------------------------------------------------ */
const MARGIN_STOCK_COLORS = ['#38bdf8', '#f59e0b', '#8b5cf6', '#10b981', '#ef4444', '#6366f1'];

export const MarginStocksCard: ReviewCardComponent = ({ marginStocks }) => {
  const copy = useReviewCopy();
  const stocks = marginStocks ?? [];
  const dates = Array.from(
    new Set(stocks.flatMap((stock) => stock.series.map((point) => point.trade_date))),
  ).sort();
  const chartData = dates.slice(-30).map((dateValue) => {
    const point: Record<string, string | number | null> = { date: dateValue.slice(5) };
    stocks.forEach((stock) => {
      const match = stock.series.find((item) => item.trade_date === dateValue);
      point[stock.code] = match?.rzye != null ? Number((match.rzye / 1e8).toFixed(2)) : null;
    });
    return point;
  });

  return (
    <Card title={copy.marginStocksTitle} variant="bordered" className="xl:col-span-2">
      {stocks.length === 0 ? (
        <p className="text-sm text-secondary-text">{copy.noData}</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className={TABLE_HEAD_CLASS}>
                  <th className="py-2 pr-4">{copy.code}</th>
                  <th className="py-2 pr-4">{copy.name}</th>
                  <th className="py-2 pr-4 text-right">{copy.rzyeYi}</th>
                  <th className="py-2 pr-4 text-right">{copy.chg1}</th>
                  <th className="py-2 text-right">{copy.buyYi}</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((stock) => (
                  <tr key={stock.code}>
                    <td className={TABLE_CELL_CLASS}>{stock.code}</td>
                    <td className={TABLE_CELL_CLASS}>{stock.name || '—'}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      {stock.rzye != null ? (stock.rzye / 1e8).toFixed(2) : '—'}
                    </td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      <span className={stock.rzye_chg_pct != null && stock.rzye_chg_pct < 0 ? 'text-rose-600' : 'text-emerald-600'}>
                        {signed(stock.rzye_chg_pct, 2, '%')}
                      </span>
                    </td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      {stock.rzye_buy != null ? (stock.rzye_buy / 1e8).toFixed(2) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {chartData.length > 1 && stocks.length <= 6 ? (
            <div className="mt-4 h-44 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} width={56} />
                  <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {stocks.map((stock, index) => (
                    <Line
                      key={stock.code}
                      type="monotone"
                      dataKey={stock.code}
                      stroke={MARGIN_STOCK_COLORS[index % MARGIN_STOCK_COLORS.length]}
                      dot={false}
                      strokeWidth={1.6}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : null}
          <p className="mt-3 text-xs text-muted-text">{copy.marginStocksHint}</p>
        </>
      )}
    </Card>
  );
};

const HEALTH_BADGE: Record<
  PersonalValidationResponse['status'],
  { variant: 'success' | 'warning' | 'danger' | 'info'; labelKey: 'healthOk' | 'healthWarn' | 'healthError' | 'healthEmpty' }
> = {
  ok: { variant: 'success', labelKey: 'healthOk' },
  warn: { variant: 'warning', labelKey: 'healthWarn' },
  error: { variant: 'danger', labelKey: 'healthError' },
  empty: { variant: 'info', labelKey: 'healthEmpty' },
};

export const HealthCard: ReviewCardComponent = ({ validation, onValidate, busy }) => {
  const copy = useReviewCopy();
  const issues = validation
    ? validation.findings.filter((item) => item.severity !== 'info').slice(0, 12)
    : [];

  return (
    <Card title={copy.healthTitle} variant="bordered" className="xl:col-span-2">
      {!validation ? (
        <p className="text-sm text-secondary-text">{copy.noData}</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <ShieldCheck className="h-8 w-8 text-secondary-text" />
            <div>
              <div className="text-3xl font-semibold text-foreground">{validation.score}</div>
              <div className="text-xs text-secondary-text">{copy.healthScore} / 100</div>
            </div>
            <Badge variant={HEALTH_BADGE[validation.status].variant}>
              {copy[HEALTH_BADGE[validation.status].labelKey]}
            </Badge>
            <span className="text-xs text-muted-text">{validation.generated_at.replace('T', ' ')}</span>
            {validation.online ? <Badge variant="info">online</Badge> : null}
            <div className="ml-auto flex gap-2">
              <button
                type="button"
                onClick={() => onValidate(false)}
                disabled={busy}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/60 bg-card/60 px-2.5 text-xs font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
                {copy.healthRun}
              </button>
              <button
                type="button"
                onClick={() => onValidate(true)}
                disabled={busy}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/60 bg-card/60 px-2.5 text-xs font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:opacity-50"
              >
                {copy.healthOnline}
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {validation.datasets.map((item) => (
              <div key={item.dataset} className="rounded-lg border border-border/50 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm text-foreground">{item.label}</span>
                  <Badge variant={HEALTH_BADGE[item.status].variant}>
                    {copy[HEALTH_BADGE[item.status].labelKey]}
                  </Badge>
                </div>
                <div className="mt-1 text-xs text-secondary-text">
                  {copy.healthLatest} {item.latest ?? '—'} · {copy.healthIssues}{' '}
                  {item.errors + item.warnings}
                </div>
              </div>
            ))}
          </div>

          {issues.length ? (
            <ul className="mt-4 space-y-1.5">
              {issues.map((item, index) => (
                <li key={`${item.dataset}-${item.rule}-${index}`} className="text-xs text-secondary-text">
                  <Badge variant={item.severity === 'error' ? 'danger' : 'warning'}>
                    {item.severity === 'error' ? copy.healthError : copy.healthWarn}
                  </Badge>{' '}
                  <span className="font-medium text-foreground">{item.dataset}</span> · {item.detail}
                  {item.trade_date ? `（${item.trade_date}）` : ''}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-emerald-600">{copy.healthClean}</p>
          )}

          <p className="mt-3 text-xs text-muted-text">{copy.healthHint}</p>
        </>
      )}
    </Card>
  );
};

// eslint-disable-next-line react-refresh/only-export-components -- registry is the page's extension point
export const REVIEW_CARDS: ReadonlyArray<ReviewCardSlot> = [
  { id: 'health', component: HealthCard },
  { id: 'composite', component: CompositeCard },
  { id: 'valuation', component: IndexValuationCard },
  { id: 'breadth', component: BreadthCard },
  { id: 'futures', component: FuturesCard },
  { id: 'rank', component: FuturesRankCard },
  { id: 'margin', component: MarginCard },
  { id: 'marginstocks', component: MarginStocksCard },
  { id: 'limitup', component: LimitUpCard },
  { id: 'pcr', component: PcrCard },
  { id: 'flows', component: FlowsCard },
  { id: 'crowding', component: CrowdingCard },
  { id: 'macro', component: MacroCard },
  { id: 'more', component: MoreCard },
];
