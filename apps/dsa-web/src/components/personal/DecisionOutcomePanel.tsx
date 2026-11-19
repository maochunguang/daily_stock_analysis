import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, Search, Target } from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  Drawer,
  EmptyState,
  InlineAlert,
  Pagination,
  StatCard,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { personalApi } from '../../api/personal';
import type {
  JournalOutcomeRow,
  JournalOutcomesResponse,
} from '../../types/personal';

const INPUT_CLASS =
  'input-surface input-focus-glow h-9 rounded-lg border bg-transparent px-3 text-sm text-foreground transition-all focus:outline-none';
const TABLE_HEAD_CLASS =
  'border-b border-border/60 text-left text-xs uppercase tracking-[0.12em] text-secondary-text';
const TABLE_CELL_CLASS = 'border-b border-border/40 py-2.5 pr-3 text-sm text-foreground';

const COPY = {
  zh: {
    title: '决策结果',
    hint: '按成交日后第 N 个交易日评估；卖出方向已取反，MFE/MAE 为持有或卖出后的有利/不利波动。',
    horizon: '周期',
    days: '回看天数',
    code: '代码',
    codePlaceholder: '如 600519',
    side: '方向',
    all: '全部',
    buy: '买入',
    sell: '卖出',
    apply: '查询',
    refresh: '刷新',
    loadError: '加载决策结果失败',
    completed: '已完成',
    pending: '待观察',
    unavailable: '不可用',
    avg: '平均决策收益',
    median: '中位收益',
    win: '胜率',
    mae: '平均 MAE',
    mfe: '平均 MFE',
    planRange: '计划区间命中',
    sampleWarning: '完成样本不足 30，仅作观察，不作胜率结论。',
    date: '日期',
    status: '状态',
    aligned: '决策收益',
    excess: '超额',
    state: '当时市场',
    plan: '计划',
    detail: '详情',
    noRows: '没有符合条件的交易记录',
    noRowsHint: '导入交割单后，这里会自动计算 D+N 结果。',
    targetDate: '目标日',
    rawReturn: '价格涨跌',
    benchmark: '基准收益',
    maeFull: '最大不利波动',
    mfeFull: '最大有利波动',
    entry: '成交价',
    adjustedEntry: '复权成交价',
    planRangeDetail: '计划区间',
    planQty: '数量 / 计划',
    planStatus: '计划状态',
    barCount: '已走交易日',
    unableReason: '不可用原因',
    source: '行情源',
    rangeYes: '区间内',
    rangeNo: '区间外',
    loading: '计算中…',
    percentileNote: '收益为比例，页面已转换为 %',
  },
  en: {
    title: 'Decision outcomes',
    hint: 'Evaluated at the Nth trading bar after the trade. Sell-side direction is inverted; MAE/MFE describe favorable/adverse excursions.',
    horizon: 'Horizon',
    days: 'Lookback',
    code: 'Code',
    codePlaceholder: 'e.g. 600519',
    side: 'Side',
    all: 'All',
    buy: 'Buy',
    sell: 'Sell',
    apply: 'Search',
    refresh: 'Refresh',
    loadError: 'Failed to load outcomes',
    completed: 'Completed',
    pending: 'Pending',
    unavailable: 'Unavailable',
    avg: 'Mean decision return',
    median: 'Median return',
    win: 'Win rate',
    mae: 'Avg MAE',
    mfe: 'Avg MFE',
    planRange: 'Plan range hit',
    sampleWarning: 'Fewer than 30 completed samples — observational only, no win-rate conclusion.',
    date: 'Date',
    status: 'Status',
    aligned: 'Decision return',
    excess: 'Excess',
    state: 'Market then',
    plan: 'Plan',
    detail: 'Details',
    noRows: 'No matching journal entries',
    noRowsHint: 'Import a broker statement; D+N outcomes are calculated here automatically.',
    targetDate: 'Target date',
    rawReturn: 'Price move',
    benchmark: 'Benchmark',
    maeFull: 'Max adverse excursion',
    mfeFull: 'Max favorable excursion',
    entry: 'Entry',
    adjustedEntry: 'Adjusted entry',
    planRangeDetail: 'Plan range',
    planQty: 'Qty / plan',
    planStatus: 'Plan status',
    barCount: 'Bars elapsed',
    unableReason: 'Reason',
    source: 'Source',
    rangeYes: 'In range',
    rangeNo: 'Outside range',
    loading: 'Calculating…',
    percentileNote: 'Returns are fractions converted to % in the UI',
  },
} as const;

function pct(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`;
}

function number(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? '—' : value.toFixed(digits);
}

function statusVariant(status: JournalOutcomeRow['status']): 'success' | 'warning' | 'danger' {
  if (status === 'completed') return 'success';
  if (status === 'pending') return 'warning';
  return 'danger';
}

export const DecisionOutcomePanel: React.FC = () => {
  const { language } = useUiLanguage();
  const copy = COPY[language];
  const [horizon, setHorizon] = useState(20);
  const [days, setDays] = useState(365);
  const [side, setSide] = useState('');
  const [codeInput, setCodeInput] = useState('');
  const [codeQuery, setCodeQuery] = useState('');
  const [payload, setPayload] = useState<JournalOutcomesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<JournalOutcomeRow | null>(null);
  const requestId = useRef(0);
  const pageSize = 20;

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    try {
      const result = await personalApi.journalOutcomes({
        horizon,
        days,
        side: side || undefined,
        code: codeQuery || undefined,
        limit: 1000,
      });
      if (id === requestId.current) {
        setPayload(result);
        setPage(1);
      }
    } catch (err) {
      if (id === requestId.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [horizon, days, side, codeQuery]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = payload?.summary;
  const rows = useMemo(() => payload?.rows ?? [], [payload]);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pageRows = useMemo(
    () => rows.slice((page - 1) * pageSize, page * pageSize),
    [rows, page],
  );

  const submitCode = (event: React.FormEvent) => {
    event.preventDefault();
    setCodeQuery(codeInput.trim());
    setPage(1);
  };

  return (
    <div className="space-y-4">
      <Card title={copy.title} variant="bordered">
        <p className="text-sm text-secondary-text">{copy.hint}</p>
        <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={submitCode}>
          <label>
            <span className="mb-1 block text-xs text-secondary-text">{copy.horizon}</span>
            <select
              className={INPUT_CLASS}
              value={horizon}
              onChange={(event) => setHorizon(Number(event.target.value))}
            >
              {[1, 5, 20, 60].map((value) => (
                <option key={value} value={value}>
                  D+{value}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="mb-1 block text-xs text-secondary-text">{copy.days}</span>
            <select
              className={INPUT_CLASS}
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
            >
              {[30, 90, 365, 730, 1825].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="mb-1 block text-xs text-secondary-text">{copy.side}</span>
            <select
              className={INPUT_CLASS}
              value={side}
              onChange={(event) => setSide(event.target.value)}
            >
              <option value="">{copy.all}</option>
              <option value="buy">{copy.buy}</option>
              <option value="sell">{copy.sell}</option>
            </select>
          </label>
          <label>
            <span className="mb-1 block text-xs text-secondary-text">{copy.code}</span>
            <input
              className={INPUT_CLASS}
              value={codeInput}
              placeholder={copy.codePlaceholder}
              onChange={(event) => setCodeInput(event.target.value)}
            />
          </label>
          <Button type="submit" variant="primary" size="sm" disabled={loading}>
            <Search className="h-4 w-4" />
            {copy.apply}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            isLoading={loading}
            loadingText={copy.loading}
            onClick={() => void load()}
          >
            <RefreshCw className="h-4 w-4" />
            {copy.refresh}
          </Button>
        </form>

        {error ? (
          <InlineAlert
            className="mt-3"
            variant="danger"
            title={copy.loadError}
            message={error}
            action={
              <Button size="sm" variant="secondary" onClick={() => void load()}>
                {copy.refresh}
              </Button>
            }
          />
        ) : null}
      </Card>

      {summary ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label={`D+${summary.horizon} · ${copy.completed}`}
              value={summary.completed}
              hint={`${copy.pending} ${summary.pending} · ${copy.unavailable} ${summary.unavailable}`}
            />
            <StatCard
              label={copy.avg}
              value={pct(summary.aligned_mean)}
              hint={`${copy.median} ${pct(summary.aligned_median)}`}
              tone={(summary.aligned_mean ?? 0) >= 0 ? 'success' : 'danger'}
            />
            <StatCard
              label={copy.win}
              value={pct(summary.win_rate, 1)}
              hint={`CI ${pct(summary.win_rate_ci[0], 1)} ~ ${pct(summary.win_rate_ci[1], 1)}`}
              tone={summary.sample_warning ? 'warning' : 'default'}
            />
            <StatCard
              label={`${copy.mae} / ${copy.mfe}`}
              value={`${pct(summary.avg_mae)} / ${pct(summary.avg_mfe)}`}
              hint={`${copy.planRange} ${pct(summary.plan_entry_in_range_rate, 1)}`}
            />
          </div>
          {summary.sample_warning ? (
            <InlineAlert variant="warning" title={copy.win} message={copy.sampleWarning} />
          ) : null}
        </>
      ) : null}

      <Card title={`D+${horizon}`} variant="bordered">
        {loading ? (
          <p className="text-sm text-secondary-text">{copy.loading}</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title={copy.noRows}
            description={copy.noRowsHint}
            icon={<Target className="h-6 w-6" />}
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px]">
                <thead>
                  <tr className={TABLE_HEAD_CLASS}>
                    <th className="py-2 pr-3">{copy.date}</th>
                    <th className="py-2 pr-3">{copy.code}</th>
                    <th className="py-2 pr-3">{copy.side}</th>
                    <th className="py-2 pr-3">{copy.status}</th>
                    <th className="py-2 pr-3 text-right">{copy.aligned}</th>
                    <th className="py-2 pr-3 text-right">{copy.excess}</th>
                    <th className="py-2 pr-3 text-right">{copy.mae}</th>
                    <th className="py-2 pr-3 text-right">{copy.mfe}</th>
                    <th className="py-2 pr-3">{copy.state}</th>
                    <th className="py-2 pr-3">{copy.plan}</th>
                    <th className="py-2 text-right">{copy.detail}</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => (
                    <tr key={`${row.journal_id}-${row.horizon}`}>
                      <td className={TABLE_CELL_CLASS}>{row.trade_date}</td>
                      <td className={TABLE_CELL_CLASS}>{row.code}</td>
                      <td className={TABLE_CELL_CLASS}>
                        <Badge variant={row.side === 'buy' ? 'success' : 'danger'}>
                          {row.side === 'buy' ? copy.buy : copy.sell}
                        </Badge>
                      </td>
                      <td className={TABLE_CELL_CLASS}>
                        <Badge variant={statusVariant(row.status)}>{copy[row.status]}</Badge>
                      </td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>
                        <span className={(row.aligned_return ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}>
                          {pct(row.aligned_return)}
                        </span>
                      </td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>{pct(row.excess_return)}</td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>{pct(row.mae)}</td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>{pct(row.mfe)}</td>
                      <td className={TABLE_CELL_CLASS}>
                        {row.composite_state ? (
                          <Badge variant="default">
                            {row.composite_state} {row.composite_score ?? ''}
                          </Badge>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className={TABLE_CELL_CLASS}>
                        {row.plan_id ? (
                          <div className="flex flex-col gap-1">
                            <Badge variant={row.entry_in_plan_range ? 'success' : 'warning'}>
                              {row.entry_in_plan_range ? copy.rangeYes : copy.rangeNo}
                            </Badge>
                            <span className="text-xs text-muted-text">#{row.plan_id}</span>
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>
                        <Button size="xsm" variant="secondary" onClick={() => setSelected(row)}>
                          {copy.detail}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              className="mt-4"
              currentPage={page}
              totalPages={totalPages}
              onPageChange={setPage}
            />
          </>
        )}
      </Card>

      <Drawer
        isOpen={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? `${selected.trade_date} ${selected.code}` : copy.detail}
      >
        {selected ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge variant={statusVariant(selected.status)}>{copy[selected.status]}</Badge>
              <Badge variant={selected.side === 'buy' ? 'success' : 'danger'}>
                {selected.side === 'buy' ? copy.buy : copy.sell}
              </Badge>
              <Badge variant="info">D+{selected.horizon}</Badge>
              {selected.composite_state ? (
                <Badge variant="default">
                  {copy.state}: {selected.composite_state}
                </Badge>
              ) : null}
            </div>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              {[
                [copy.entry, number(selected.price)],
                [copy.adjustedEntry, number(selected.entry_price_adjusted)],
                [copy.targetDate, selected.target_date || '—'],
                [copy.barCount, `${selected.bar_count} / ${selected.horizon}`],
                [copy.rawReturn, pct(selected.asset_return)],
                [copy.aligned, pct(selected.aligned_return)],
                [copy.benchmark, pct(selected.benchmark_return)],
                [copy.excess, pct(selected.excess_return)],
                [copy.maeFull, pct(selected.mae)],
                [copy.mfeFull, pct(selected.mfe)],
                [copy.source, selected.stock_source || '—'],
                [copy.unableReason, selected.unable_reason || '—'],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-border/50 bg-elevated/20 p-3">
                  <dt className="text-xs text-secondary-text">{label}</dt>
                  <dd className="mt-1 break-words text-sm font-medium text-foreground">{value}</dd>
                </div>
              ))}
            </dl>
            {selected.plan_id ? (
              <div className="rounded-2xl border border-cyan/20 bg-cyan/5 p-4 text-sm">
                <p className="font-medium text-cyan">
                  {copy.plan} #{selected.plan_id} · {selected.plan_status || '—'}
                </p>
                <p className="mt-1 text-secondary-text">
                  {copy.planRangeDetail}: {number(selected.plan_entry_low)} ~ {number(selected.plan_entry_high)}
                </p>
                <p className="mt-1 text-secondary-text">
                  {copy.planQty}: {number(selected.quantity, 0)} / {number(selected.plan_suggested_quantity, 0)}
                  {selected.entry_deviation !== null && selected.entry_deviation !== undefined
                    ? ` · deviation ${pct(selected.entry_deviation)}`
                    : ''}
                </p>
              </div>
            ) : null}
          </div>
        ) : null}
      </Drawer>
    </div>
  );
};
