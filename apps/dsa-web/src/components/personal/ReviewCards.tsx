import type React from 'react';
import { Landmark, RefreshCw, TrendingDown } from 'lucide-react';
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
  PersonalFuturesRow,
  PersonalMarginRow,
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
    moreList: '股指期货会员持仓龙虎榜 · ETF 资金流 · 行业融资余额分布',
    noData: '暂无数据，先同步数据集',
    unitYi: '亿',
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
    moreList: 'Member position rankings · ETF flows · Margin by industry',
    noData: 'No data yet — sync the dataset first',
    unitYi: '×1e8 CNY',
  },
} as const;

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
  busy: boolean;
  onRefreshMarket: (dataset: 'futures' | 'margin') => void;
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

export const REVIEW_CARDS: ReadonlyArray<ReviewCardSlot> = [
  { id: 'breadth', component: BreadthCard },
  { id: 'futures', component: FuturesCard },
  { id: 'margin', component: MarginCard },
  { id: 'more', component: MoreCard },
];
