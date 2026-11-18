import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  Database,
  Gauge,
  PlugZap,
  RefreshCw,
  ServerCog,
  Sparkles,
} from 'lucide-react';
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
import { personalApi } from '../api/personal';
import {
  AppPage,
  Badge,
  Button,
  Card,
  EmptyState,
  InlineAlert,
  Loading,
  PageHeader,
  StatCard,
} from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { REVIEW_CARDS } from '../components/personal/ReviewCards';
import type {
  PersonalBacktestResponse,
  PersonalBreadthRow,
  PersonalCompositeResponse,
  PersonalCrowdingResponse,
  PersonalFlowsResponse,
  PersonalFuturesRankRow,
  PersonalLimitUpRow,
  PersonalMacroResponse,
  PersonalPcrRow,
  PersonalFuturesRow,
  PersonalMarginRow,
  PersonalPlugin,
  PersonalRun,
  PersonalStatus,
  PersonalSyncResponse,
  PersonalUpstreamRecent,
  PersonalValidationResponse,
} from '../types/personal';

type TabKey = 'overview' | 'review' | 'data' | 'backtest' | 'plugins' | 'qmt';

const INPUT_CLASS =
  'input-surface input-focus-glow h-11 w-full rounded-xl border bg-transparent px-4 text-sm text-foreground transition-all focus:outline-none';
const LABEL_CLASS = 'mb-2 block text-sm font-medium text-foreground';
const TABLE_HEAD_CLASS = 'border-b border-border/60 text-left text-xs uppercase tracking-[0.12em] text-secondary-text';
const TABLE_CELL_CLASS = 'border-b border-border/40 py-2.5 pr-4 text-sm text-foreground';

const COPY = {
  zh: {
    title: '个人扩展',
    description: '数据质量、成本回测、深度复盘、插件与 QMT 状态',
    refresh: '刷新',
    tabs: {
      overview: '总览',
      review: '深度复盘',
      data: '数据同步',
      backtest: '个人回测',
      plugins: '插件',
      qmt: 'QMT',
    },
    loading: '正在加载个人扩展状态…',
    loadError: '加载个人扩展状态失败',
    upstream: '上游 DSA',
    upstreamReady: '已连接',
    upstreamMissing: '未生成',
    personalDb: '个人库',
    symbols: '代码',
    sources: '数据源',
    plugins: '插件',
    qmt: 'QMT 桥',
    qmtReadonly: '只读/未启用',
    qmtEnabled: '交易已启用',
    coverage: '数据覆盖',
    recentRuns: '最近回测',
    recentAnalyses: '最近分析',
    quality: '数据质量事件',
    freshness: '数据新鲜度（定时同步）',
    freshnessHint: 'personal-sync 容器每天 06:00 / 12:00 各跑一轮增量同步；失败会保留最近一次错误',
    dsLastOk: '最近成功',
    dsDataDate: '数据日期',
    dsRows: '行数',
    dsError: '错误',
    noData: '暂无数据',
    dataset: '数据集',
    source: '数据源',
    codes: '代码（逗号分隔）',
    start: '开始日期',
    end: '结束日期',
    sync: '开始同步',
    syncing: '同步中…',
    syncDone: '同步完成',
    syncResult: '同步结果',
    datasetBars: '日线 Bars',
    datasetAdjust: '复权因子 Adjust',
    datasetCalendar: '交易日历 Calendar',
    datasetStatus: '交易状态 Status',
    crossCheck: '跨源校验',
    sourceAuto: 'auto（优先级 fallback）',
    sourceSynthetic: 'synthetic（离线测试）',
    sourceTushare: 'tushare',
    sourceBaostock: 'baostock',
    sourceAkshare: 'akshare',
    backtestKind: '类型',
    demo: 'Demo（合成数据）',
    replay: 'Replay（上游 AI 建议）',
    days: '历史天数',
    include: '信号来源',
    includeBoth: '分析 + 决策信号',
    includeAnalyses: '仅分析历史',
    includeSignals: '仅决策信号',
    saveRun: '保存到个人库',
    run: '运行',
    running: '回测中…',
    backtestDone: '回测完成',
    metrics: '绩效',
    equity: '净值曲线',
    trades: '交易明细',
    strategy: '策略',
    benchmark: '基准',
    finalCash: '期末现金',
    positions: '期末持仓',
    pluginList: '已加载插件',
    pluginErrors: '插件加载错误',
    permissions: '权限',
    qmtTitle: 'QMT 桥状态',
    qmtHint: 'QMT 桥运行在 Windows QMT 机器上；这里只做只读健康检查，不会下单。',
    qmtCheck: '检查连接',
    qmtChecking: '检查中…',
    qmtResult: 'QMT 桥返回',
    emptyPlugins: '没有加载到插件',
    upstreamUnavailable: '上游数据库不可用，生成一次上游分析后即可使用 Replay。',
  },
  en: {
    title: 'Personal Extension',
    description: 'Data quality, cost-aware backtests, deep review, plugins and QMT status',
    refresh: 'Refresh',
    tabs: {
      overview: 'Overview',
      review: 'Deep Review',
      data: 'Data',
      backtest: 'Backtest',
      plugins: 'Plugins',
      qmt: 'QMT',
    },
    loading: 'Loading personal extension status…',
    loadError: 'Failed to load personal extension status',
    upstream: 'Upstream DSA',
    upstreamReady: 'Connected',
    upstreamMissing: 'Not generated',
    personalDb: 'Personal DB',
    symbols: 'Symbols',
    sources: 'Sources',
    plugins: 'Plugins',
    qmt: 'QMT bridge',
    qmtReadonly: 'Read-only / disabled',
    qmtEnabled: 'Trading enabled',
    coverage: 'Data coverage',
    recentRuns: 'Recent backtests',
    recentAnalyses: 'Recent analyses',
    quality: 'Data quality events',
    freshness: 'Data freshness (scheduled sync)',
    freshnessHint: 'The personal-sync container runs at 06:00 and 12:00 daily; failures keep the last error visible',
    dsLastOk: 'Last success',
    dsDataDate: 'Data date',
    dsRows: 'Rows',
    dsError: 'Error',
    noData: 'No data',
    dataset: 'Dataset',
    source: 'Source',
    codes: 'Codes (comma separated)',
    start: 'Start',
    end: 'End',
    sync: 'Sync',
    syncing: 'Syncing…',
    syncDone: 'Sync complete',
    syncResult: 'Sync result',
    datasetBars: 'Daily bars',
    datasetAdjust: 'Adjustment factors',
    datasetCalendar: 'Trading calendar',
    datasetStatus: 'Trading status',
    crossCheck: 'Cross-source check',
    sourceAuto: 'auto (priority fallback)',
    sourceSynthetic: 'synthetic (offline test)',
    sourceTushare: 'tushare',
    sourceBaostock: 'baostock',
    sourceAkshare: 'akshare',
    backtestKind: 'Type',
    demo: 'Demo (synthetic)',
    replay: 'Replay (upstream AI advice)',
    days: 'History days',
    include: 'Signal source',
    includeBoth: 'Analyses + decision signals',
    includeAnalyses: 'Analyses only',
    includeSignals: 'Decision signals only',
    saveRun: 'Save to personal DB',
    run: 'Run',
    running: 'Running…',
    backtestDone: 'Backtest complete',
    metrics: 'Performance',
    equity: 'Equity curve',
    trades: 'Trades',
    strategy: 'Strategy',
    benchmark: 'Benchmark',
    finalCash: 'Final cash',
    positions: 'Final positions',
    pluginList: 'Loaded plugins',
    pluginErrors: 'Plugin load errors',
    permissions: 'Permissions',
    qmtTitle: 'QMT bridge status',
    qmtHint: 'The QMT bridge runs on the Windows QMT machine. This is a read-only health check.',
    qmtCheck: 'Check connection',
    qmtChecking: 'Checking…',
    qmtResult: 'QMT bridge response',
    emptyPlugins: 'No plugins loaded',
    upstreamUnavailable: 'Upstream database is unavailable. Run one upstream analysis to use Replay.',
  },
} as const;

const METRIC_LABELS: Record<string, { zh: string; en: string }> = {
  total_return: { zh: '累计收益', en: 'Total return' },
  cagr: { zh: '年化收益', en: 'CAGR' },
  annual_vol: { zh: '年化波动', en: 'Volatility' },
  sharpe: { zh: 'Sharpe', en: 'Sharpe' },
  max_drawdown: { zh: '最大回撤', en: 'Max drawdown' },
  calmar: { zh: 'Calmar', en: 'Calmar' },
  benchmark_return: { zh: '基准收益', en: 'Benchmark' },
  excess_return: { zh: '超额收益', en: 'Excess return' },
  win_rate: { zh: '胜率', en: 'Win rate' },
  profit_factor: { zh: '盈亏比', en: 'Profit factor' },
  turnover: { zh: '换手率', en: 'Turnover' },
  total_fees: { zh: '总费用', en: 'Fees' },
  trade_count: { zh: '交易数', en: 'Trades' },
  closed_trade_count: { zh: '平仓数', en: 'Closed' },
};

function isoDaysAgo(days: number): string {
  const value = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  return value.toISOString().slice(0, 10);
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
}

function formatMetric(key: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (key.endsWith('_return') || key.endsWith('_drawdown') || key === 'annual_vol' || key === 'win_rate' || key === 'turnover') {
    return `${(Number(value) * 100).toFixed(2)}%`;
  }
  if (key === 'total_fees') return `¥${formatNumber(Number(value), 2)}`;
  if (key === 'trade_count' || key === 'closed_trade_count') return String(Math.round(Number(value)));
  return formatNumber(Number(value), 2);
}

function parseRunMetrics(run: PersonalRun): Record<string, number | null> {
  try {
    return JSON.parse(run.metrics_json) as Record<string, number | null>;
  } catch {
    return {};
  }
}

const PersonalPage: React.FC = () => {
  const { language } = useUiLanguage();
  const copy = COPY[language];
  const [tab, setTab] = useState<TabKey>('overview');
  const [status, setStatus] = useState<PersonalStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [syncDataset, setSyncDataset] = useState<'bars' | 'adjust' | 'calendar' | 'status'>('bars');
  const [syncSource, setSyncSource] = useState('auto');
  const [syncCodes, setSyncCodes] = useState('');
  const [syncStart, setSyncStart] = useState(isoDaysAgo(730));
  const [syncEnd, setSyncEnd] = useState(isoDaysAgo(0));
  const [syncCrossCheck, setSyncCrossCheck] = useState(true);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncResult, setSyncResult] = useState<PersonalSyncResponse | null>(null);
  const [syncError, setSyncError] = useState('');

  const [kind, setKind] = useState<'demo' | 'replay'>('demo');
  const [days, setDays] = useState(400);
  const [btStart, setBtStart] = useState(isoDaysAgo(365));
  const [btEnd, setBtEnd] = useState(isoDaysAgo(0));
  const [include, setInclude] = useState<'both' | 'analyses' | 'signals'>('both');
  const [saveRun, setSaveRun] = useState(false);
  const [btBusy, setBtBusy] = useState(false);
  const [btResult, setBtResult] = useState<PersonalBacktestResponse | null>(null);
  const [btError, setBtError] = useState('');

  const [upstream, setUpstream] = useState<PersonalUpstreamRecent | null>(null);
  const [qmtBusy, setQmtBusy] = useState(false);
  const [qmtResult, setQmtResult] = useState('');

  const [reviewBreadth, setReviewBreadth] = useState<PersonalBreadthRow[]>([]);
  const [reviewFutures, setReviewFutures] = useState<PersonalFuturesRow[]>([]);
  const [reviewMargin, setReviewMargin] = useState<PersonalMarginRow[]>([]);
  const [reviewLimitUp, setReviewLimitUp] = useState<PersonalLimitUpRow[]>([]);
  const [reviewPcr, setReviewPcr] = useState<PersonalPcrRow[]>([]);
  const [reviewRank, setReviewRank] = useState<PersonalFuturesRankRow[]>([]);
  const [reviewFlows, setReviewFlows] = useState<PersonalFlowsResponse | null>(null);
  const [reviewCrowding, setReviewCrowding] = useState<PersonalCrowdingResponse | null>(null);
  const [reviewMacro, setReviewMacro] = useState<PersonalMacroResponse | null>(null);
  const [reviewComposite, setReviewComposite] = useState<PersonalCompositeResponse | null>(null);
  const [reviewValidation, setReviewValidation] = useState<PersonalValidationResponse | null>(null);
  const [reviewLoaded, setReviewLoaded] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState('');

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await personalApi.status();
      setStatus(data);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadUpstream = useCallback(async () => {
    try {
      setUpstream(await personalApi.upstreamRecent());
    } catch {
      setUpstream(null);
    }
  }, []);

  const loadReview = useCallback(async () => {
    setReviewBusy(true);
    setReviewError('');
    try {
      const [
        breadthData,
        futuresData,
        marginData,
        limitUpData,
        pcrData,
        rankData,
        flowsData,
        crowdingData,
        macroData,
        compositeData,
        validationData,
      ] = await Promise.all([
        personalApi.breadth(30),
        personalApi.futures(30),
        personalApi.margin(30),
        personalApi.limitup(20),
        personalApi.pcr(20),
        personalApi.cffexRank(20),
        personalApi.flows(30),
        personalApi.crowding(30),
        personalApi.macro(120),
        personalApi.composite(),
        personalApi.marketValidate(400),
      ]);
      setReviewBreadth(breadthData.rows);
      setReviewFutures(futuresData.rows);
      setReviewMargin(marginData.rows);
      setReviewLimitUp(limitUpData.rows);
      setReviewPcr(pcrData.rows);
      setReviewRank(rankData.rows);
      setReviewFlows(flowsData);
      setReviewCrowding(crowdingData);
      setReviewMacro(macroData);
      setReviewComposite(compositeData);
      setReviewValidation(validationData);
      setReviewLoaded(true);
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setReviewBusy(false);
    }
  }, []);

  const handleMarketSync = useCallback(
    async (dataset: 'futures' | 'margin') => {
      setReviewBusy(true);
      try {
        await personalApi.marketSync({ dataset, start: isoDaysAgo(10), end: isoDaysAgo(0) });
        if (dataset === 'futures') {
          const data = await personalApi.futures(30);
          setReviewFutures(data.rows);
        } else {
          const data = await personalApi.margin(30);
          setReviewMargin(data.rows);
        }
      } catch (err) {
        setReviewError(err instanceof Error ? err.message : String(err));
      } finally {
        setReviewBusy(false);
      }
    },
    [],
  );

  const handleValidate = useCallback(async (online: boolean) => {
    setReviewBusy(true);
    try {
      setReviewValidation(await personalApi.marketValidate(400, online));
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setReviewBusy(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'review' && !reviewLoaded) {
      void loadReview();
    }
  }, [tab, reviewLoaded, loadReview]);

  useEffect(() => {
    document.title = `${copy.title} - DSA`;
    void loadStatus();
    void loadUpstream();
  }, [copy.title, loadStatus, loadUpstream]);

  useEffect(() => {
    if (status && !syncCodes) {
      setSyncCodes(status.settings.stock_list.join(','));
    }
  }, [status, syncCodes]);

  const chartData = useMemo(() => {
    if (!btResult || btResult.equity.length === 0) return [];
    const base = btResult.equity[0]?.value || 1;
    const benchmark = new Map((btResult.benchmark ?? []).map((point) => [point.date, point.value]));
    return btResult.equity.map((point) => ({
      date: point.date.slice(5),
      strategy: point.value / base,
      benchmark: benchmark.get(point.date) ?? null,
    }));
  }, [btResult]);

  const handleSync = async (event: React.FormEvent) => {
    event.preventDefault();
    setSyncBusy(true);
    setSyncError('');
    setSyncResult(null);
    try {
      const result = await personalApi.sync({
        dataset: syncDataset,
        source: syncSource,
        codes: syncCodes
          .split(/[,，\s]+/)
          .map((item) => item.trim())
          .filter(Boolean),
        start: syncStart || null,
        end: syncEnd || null,
        cross_check: syncCrossCheck,
      });
      setSyncResult(result);
      await loadStatus();
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : String(err));
    } finally {
      setSyncBusy(false);
    }
  };

  const handleBacktest = async (event: React.FormEvent) => {
    event.preventDefault();
    setBtBusy(true);
    setBtError('');
    try {
      const result =
        kind === 'demo'
          ? await personalApi.demo({ days, save: saveRun })
          : await personalApi.replay({
              start: btStart || null,
              end: btEnd || null,
              include,
              save: saveRun,
            });
      setBtResult(result);
      if (saveRun) await loadStatus();
    } catch (err) {
      setBtError(err instanceof Error ? err.message : String(err));
    } finally {
      setBtBusy(false);
    }
  };

  const handleQmt = async () => {
    setQmtBusy(true);
    try {
      const result = await personalApi.qmtHealth();
      setQmtResult(JSON.stringify(result, null, 2));
    } catch (err) {
      setQmtResult(err instanceof Error ? err.message : String(err));
    } finally {
      setQmtBusy(false);
    }
  };

  const renderPlugins = (plugins: PersonalPlugin[]) => {
    if (plugins.length === 0) {
      return (
        <EmptyState
          icon={<PlugZap className="h-6 w-6" />}
          title={copy.emptyPlugins}
          description="plugins/<name>/plugin.yaml"
        />
      );
    }
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {plugins.map((plugin) => (
          <div key={plugin.name} className="rounded-2xl border border-border/60 bg-card/60 p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold text-foreground">{plugin.display_name || plugin.name}</h3>
                <p className="mt-1 text-xs text-secondary-text">
                  {plugin.name} · {plugin.version} · {plugin.type}
                </p>
              </div>
              <Badge variant="info">{plugin.type}</Badge>
            </div>
            {plugin.description ? <p className="mt-3 text-sm text-secondary-text">{plugin.description}</p> : null}
            <p className="mt-3 text-xs text-muted-text">
              {copy.permissions}: {(plugin.permissions ?? []).join(', ') || 'none'}
            </p>
          </div>
        ))}
      </div>
    );
  };

  return (
    <AppPage className="space-y-5">
      <PageHeader
        eyebrow="Personal Layer"
        title={copy.title}
        description={copy.description}
        actions={
          <Button size="sm" variant="secondary" isLoading={loading} loadingText={copy.loading} onClick={() => void loadStatus()}>
            <RefreshCw className="h-4 w-4" />
            {copy.refresh}
          </Button>
        }
      />

      {error ? (
        <InlineAlert
          variant="danger"
          title={copy.loadError}
          message={error}
          action={
            <Button size="sm" variant="secondary" onClick={() => void loadStatus()}>
              {copy.refresh}
            </Button>
          }
        />
      ) : null}

      {loading && !status ? <Loading label={copy.loading} /> : null}

      <div className="flex flex-wrap gap-2">
        {(Object.keys(copy.tabs) as TabKey[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`inline-flex h-9 items-center gap-2 rounded-xl border px-3 text-sm font-medium transition-colors ${
              tab === key
                ? 'border-cyan/30 bg-cyan/10 text-cyan'
                : 'border-border/60 bg-card/60 text-secondary-text hover:bg-hover hover:text-foreground'
            }`}
          >
            {key === 'overview' ? <Activity className="h-4 w-4" /> : null}
            {key === 'review' ? <Gauge className="h-4 w-4" /> : null}
            {key === 'data' ? <Database className="h-4 w-4" /> : null}
            {key === 'backtest' ? <BarChart3 className="h-4 w-4" /> : null}
            {key === 'plugins' ? <PlugZap className="h-4 w-4" /> : null}
            {key === 'qmt' ? <ServerCog className="h-4 w-4" /> : null}
            {copy.tabs[key]}
          </button>
        ))}
      </div>

      {tab === 'overview' && status ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label={copy.upstream}
              value={status.upstream.available ? copy.upstreamReady : copy.upstreamMissing}
              hint={
                status.upstream.available
                  ? `analysis=${status.upstream.has_analysis_history} portfolio=${status.upstream.has_portfolio}`
                  : copy.upstreamMissing
              }
              tone={status.upstream.available ? 'success' : 'warning'}
              icon={<Activity className="h-5 w-5" />}
            />
            <StatCard
              label={copy.personalDb}
              value={`${status.storage.symbols ?? 0} / ${status.storage.sources ?? 0}`}
              hint={`${copy.symbols} / ${copy.sources} · ${status.storage.daily_bar ?? 0} bars`}
              tone="primary"
              icon={<Database className="h-5 w-5" />}
            />
            <StatCard
              label={copy.plugins}
              value={String(status.plugins.length)}
              hint={status.plugins.map((plugin) => plugin.name).join(', ') || copy.emptyPlugins}
              icon={<PlugZap className="h-5 w-5" />}
            />
            <StatCard
              label={copy.qmt}
              value={status.qmt.trading_enabled ? copy.qmtEnabled : copy.qmtReadonly}
              hint={status.qmt.bridge_url}
              tone={status.qmt.trading_enabled ? 'warning' : 'default'}
              icon={<ServerCog className="h-5 w-5" />}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card title={copy.coverage} variant="bordered">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className={TABLE_HEAD_CLASS}>
                      <th className="py-2 pr-4">Code</th>
                      <th className="py-2 pr-4">Source</th>
                      <th className="py-2 pr-4 text-right">Rows</th>
                      <th className="py-2 pr-4">Start</th>
                      <th className="py-2">End</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.coverage.length ? (
                      status.coverage.map((row) => (
                        <tr key={`${row.code}-${row.source}`}>
                          <td className={TABLE_CELL_CLASS}>{row.code}</td>
                          <td className={TABLE_CELL_CLASS}>
                            <Badge variant={row.source === 'synthetic' ? 'warning' : 'info'}>{row.source}</Badge>
                          </td>
                          <td className={`${TABLE_CELL_CLASS} text-right`}>{row.rows}</td>
                          <td className={TABLE_CELL_CLASS}>{row.start_date ?? '—'}</td>
                          <td className={TABLE_CELL_CLASS}>{row.end_date ?? '—'}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="py-3 text-sm text-secondary-text" colSpan={5}>
                          {copy.noData}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title={copy.recentRuns} variant="bordered">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className={TABLE_HEAD_CLASS}>
                      <th className="py-2 pr-4">Run</th>
                      <th className="py-2 pr-4">Mode</th>
                      <th className="py-2 pr-4">Period</th>
                      <th className="py-2 text-right">Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.recent_runs.length ? (
                      status.recent_runs.map((run) => {
                        const metrics = parseRunMetrics(run);
                        return (
                          <tr key={run.run_id}>
                            <td className={TABLE_CELL_CLASS}>{run.run_id}</td>
                            <td className={TABLE_CELL_CLASS}>{run.mode}</td>
                            <td className={TABLE_CELL_CLASS}>
                              {run.start_date ?? '—'} → {run.end_date ?? '—'}
                            </td>
                            <td className={`${TABLE_CELL_CLASS} text-right`}>
                              {formatMetric('total_return', metrics.total_return)}
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td className="py-3 text-sm text-secondary-text" colSpan={4}>
                          {copy.noData}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card title={copy.recentAnalyses} variant="bordered">
              {upstream && !upstream.available ? (
                <InlineAlert variant="warning" title={copy.upstreamUnavailable} message={upstream.missing ?? ''} />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className={TABLE_HEAD_CLASS}>
                        <th className="py-2 pr-4">Code</th>
                        <th className="py-2 pr-4">Name</th>
                        <th className="py-2 pr-4">Advice</th>
                        <th className="py-2 text-right">Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {upstream?.analyses?.length ? (
                        upstream.analyses.slice(0, 8).map((item) => (
                          <tr key={item.id}>
                            <td className={TABLE_CELL_CLASS}>{item.code}</td>
                            <td className={TABLE_CELL_CLASS}>{item.name ?? '—'}</td>
                            <td className={TABLE_CELL_CLASS}>{item.advice ?? '—'}</td>
                            <td className={`${TABLE_CELL_CLASS} text-right`}>{item.score ?? '—'}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="py-3 text-sm text-secondary-text" colSpan={4}>
                            {copy.noData}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title={copy.quality} variant="bordered">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className={TABLE_HEAD_CLASS}>
                      <th className="py-2 pr-4">Rule</th>
                      <th className="py-2 pr-4">Severity</th>
                      <th className="py-2">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.recent_quality.length ? (
                      status.recent_quality.slice(0, 8).map((event) => (
                        <tr key={event.id}>
                          <td className={TABLE_CELL_CLASS}>{event.rule}</td>
                          <td className={TABLE_CELL_CLASS}>
                            <Badge variant={event.severity === 'error' ? 'danger' : event.severity === 'warn' ? 'warning' : 'default'}>
                              {event.severity}
                            </Badge>
                          </td>
                          <td className={TABLE_CELL_CLASS}>{event.detail}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="py-3 text-sm text-secondary-text" colSpan={3}>
                          {copy.noData}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <Card title={copy.freshness} variant="bordered">
            <p className="mb-3 text-xs text-muted-text">{copy.freshnessHint}</p>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className={TABLE_HEAD_CLASS}>
                    <th className="py-2 pr-4">Dataset</th>
                    <th className="py-2 pr-4">{copy.dsLastOk}</th>
                    <th className="py-2 pr-4">{copy.dsDataDate}</th>
                    <th className="py-2 pr-4 text-right">{copy.dsRows}</th>
                    <th className="py-2">{copy.dsError}</th>
                  </tr>
                </thead>
                <tbody>
                  {status.sync_state?.length ? (
                    status.sync_state.map((state) => (
                      <tr key={state.dataset}>
                        <td className={TABLE_CELL_CLASS}>
                          <Badge variant={state.last_error ? 'danger' : 'success'}>{state.dataset}</Badge>
                        </td>
                        <td className={TABLE_CELL_CLASS}>{state.last_ok_at?.slice(0, 19).replace('T', ' ') ?? '—'}</td>
                        <td className={TABLE_CELL_CLASS}>{state.last_ok_date ?? '—'}</td>
                        <td className={`${TABLE_CELL_CLASS} text-right`}>{state.rows}</td>
                        <td className={TABLE_CELL_CLASS}>{state.last_error ?? ''}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="py-3 text-sm text-secondary-text" colSpan={5}>
                        {copy.noData}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      ) : null}

      {tab === 'review' ? (
        reviewError ? (
          <InlineAlert
            variant="danger"
            title={copy.loadError}
            message={reviewError}
            action={
              <Button size="sm" variant="secondary" onClick={() => void loadReview()}>
                {copy.refresh}
              </Button>
            }
          />
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {REVIEW_CARDS.map(({ id, component: CardComponent }) => (
              <CardComponent
                key={id}
                breadth={reviewBreadth}
                futures={reviewFutures}
                margin={reviewMargin}
                limitUp={reviewLimitUp}
                pcr={reviewPcr}
                rank={reviewRank}
                flows={reviewFlows}
                crowding={reviewCrowding}
                macro={reviewMacro}
                composite={reviewComposite}
                validation={reviewValidation}
                busy={reviewBusy}
                onRefreshMarket={(dataset) => void handleMarketSync(dataset)}
                onValidate={(online) => void handleValidate(online)}
              />
            ))}
          </div>
        )
      ) : null}

      {tab === 'data' ? (
        <Card title={copy.tabs.data} variant="bordered">
          <form className="grid gap-3 md:grid-cols-3" onSubmit={(event) => void handleSync(event)}>
            <label>
              <span className={LABEL_CLASS}>{copy.dataset}</span>
              <select className={INPUT_CLASS} value={syncDataset} onChange={(event) => setSyncDataset(event.target.value as 'bars' | 'adjust' | 'calendar' | 'status')}>
                <option value="bars">{copy.datasetBars}</option>
                <option value="adjust">{copy.datasetAdjust}</option>
                <option value="calendar">{copy.datasetCalendar}</option>
                <option value="status">{copy.datasetStatus}</option>
              </select>
            </label>
            <label>
              <span className={LABEL_CLASS}>{copy.source}</span>
              <select className={INPUT_CLASS} value={syncSource} onChange={(event) => setSyncSource(event.target.value)}>
                <option value="auto">{copy.sourceAuto}</option>
                <option value="synthetic">{copy.sourceSynthetic}</option>
                <option value="tushare">{copy.sourceTushare}</option>
                <option value="baostock">{copy.sourceBaostock}</option>
                <option value="akshare">{copy.sourceAkshare}</option>
              </select>
            </label>
            <label>
              <span className={LABEL_CLASS}>{copy.codes}</span>
              <input className={INPUT_CLASS} value={syncCodes} onChange={(event) => setSyncCodes(event.target.value)} placeholder="600519,000001,510050" />
            </label>
            <label>
              <span className={LABEL_CLASS}>{copy.start}</span>
              <input className={INPUT_CLASS} type="date" value={syncStart} onChange={(event) => setSyncStart(event.target.value)} />
            </label>
            <label>
              <span className={LABEL_CLASS}>{copy.end}</span>
              <input className={INPUT_CLASS} type="date" value={syncEnd} onChange={(event) => setSyncEnd(event.target.value)} />
            </label>
            <label className="flex items-end gap-2 pb-3 text-sm text-foreground">
              <input type="checkbox" checked={syncCrossCheck} onChange={(event) => setSyncCrossCheck(event.target.checked)} />
              {copy.crossCheck}
            </label>
            <div className="flex items-end">
              <Button type="submit" isLoading={syncBusy} loadingText={copy.syncing}>
                <Sparkles className="h-4 w-4" />
                {copy.sync}
              </Button>
            </div>
          </form>

          {syncError ? <InlineAlert className="mt-4" variant="danger" title={copy.syncResult} message={syncError} /> : null}
          {syncResult ? (
            <div className="mt-4 space-y-3">
              <InlineAlert
                variant={syncResult.results.some((result) => result.rows > 0) ? 'success' : 'warning'}
                title={copy.syncDone}
                message={`${syncResult.dataset} · ${syncResult.start} → ${syncResult.end}`}
              />
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className={TABLE_HEAD_CLASS}>
                      <th className="py-2 pr-4">Code</th>
                      <th className="py-2 pr-4">Source</th>
                      <th className="py-2 pr-4 text-right">Rows</th>
                      <th className="py-2 pr-4">Quality</th>
                      <th className="py-2 pr-4">Cross</th>
                      <th className="py-2 pr-4">Missing</th>
                      <th className="py-2 pr-4">Suspended</th>
                      <th className="py-2">Errors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {syncResult.results.map((result) => (
                      <tr key={`${result.code}-${result.source}`}>
                        <td className={TABLE_CELL_CLASS}>{result.code}</td>
                        <td className={TABLE_CELL_CLASS}>{result.source ?? '—'}</td>
                        <td className={`${TABLE_CELL_CLASS} text-right`}>{result.rows}</td>
                        <td className={TABLE_CELL_CLASS}>{result.quality_issues}</td>
                        <td className={TABLE_CELL_CLASS}>{result.cross_source_issues ?? 0}</td>
                        <td className={TABLE_CELL_CLASS}>{result.missing_days ?? 0}</td>
                        <td className={TABLE_CELL_CLASS}>{result.suspended_days ?? 0}</td>
                        <td className={TABLE_CELL_CLASS}>{result.errors.join('; ') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}

          {status ? (
            <div className="mt-6">
              <h3 className="mb-3 text-sm font-semibold text-foreground">{copy.coverage}</h3>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className={TABLE_HEAD_CLASS}>
                      <th className="py-2 pr-4">Code</th>
                      <th className="py-2 pr-4">Source</th>
                      <th className="py-2 pr-4 text-right">Rows</th>
                      <th className="py-2 pr-4">Start</th>
                      <th className="py-2">End</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.coverage.map((row) => (
                      <tr key={`${row.code}-${row.source}`}>
                        <td className={TABLE_CELL_CLASS}>{row.code}</td>
                        <td className={TABLE_CELL_CLASS}>{row.source}</td>
                        <td className={`${TABLE_CELL_CLASS} text-right`}>{row.rows}</td>
                        <td className={TABLE_CELL_CLASS}>{row.start_date ?? '—'}</td>
                        <td className={TABLE_CELL_CLASS}>{row.end_date ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </Card>
      ) : null}

      {tab === 'backtest' ? (
        <div className="space-y-4">
          <Card title={copy.tabs.backtest} variant="bordered">
            <form className="grid gap-3 md:grid-cols-3" onSubmit={(event) => void handleBacktest(event)}>
              <label>
                <span className={LABEL_CLASS}>{copy.backtestKind}</span>
                <select className={INPUT_CLASS} value={kind} onChange={(event) => setKind(event.target.value as 'demo' | 'replay')}>
                  <option value="demo">{copy.demo}</option>
                  <option value="replay">{copy.replay}</option>
                </select>
              </label>
              {kind === 'demo' ? (
                <label>
                  <span className={LABEL_CLASS}>{copy.days}</span>
                  <input
                    className={INPUT_CLASS}
                    type="number"
                    min={60}
                    max={3000}
                    value={days}
                    onChange={(event) => setDays(Number(event.target.value) || 400)}
                  />
                </label>
              ) : (
                <>
                  <label>
                    <span className={LABEL_CLASS}>{copy.start}</span>
                    <input className={INPUT_CLASS} type="date" value={btStart} onChange={(event) => setBtStart(event.target.value)} />
                  </label>
                  <label>
                    <span className={LABEL_CLASS}>{copy.end}</span>
                    <input className={INPUT_CLASS} type="date" value={btEnd} onChange={(event) => setBtEnd(event.target.value)} />
                  </label>
                  <label>
                    <span className={LABEL_CLASS}>{copy.include}</span>
                    <select className={INPUT_CLASS} value={include} onChange={(event) => setInclude(event.target.value as 'both' | 'analyses' | 'signals')}>
                      <option value="both">{copy.includeBoth}</option>
                      <option value="analyses">{copy.includeAnalyses}</option>
                      <option value="signals">{copy.includeSignals}</option>
                    </select>
                  </label>
                </>
              )}
              <label className="flex items-end gap-2 pb-3 text-sm text-foreground">
                <input type="checkbox" checked={saveRun} onChange={(event) => setSaveRun(event.target.checked)} />
                {copy.saveRun}
              </label>
              <div className="flex items-end">
                <Button type="submit" isLoading={btBusy} loadingText={copy.running}>
                  <BarChart3 className="h-4 w-4" />
                  {copy.run}
                </Button>
              </div>
            </form>
            {btError ? <InlineAlert className="mt-4" variant="danger" title={copy.tabs.backtest} message={btError} /> : null}
          </Card>

          {btResult ? (
            <>
              <Card title={copy.metrics} variant="bordered">
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-secondary-text">
                  <Badge variant="info">{btResult.kind}</Badge>
                  <span>
                    {btResult.start} → {btResult.end}
                  </span>
                  <span>signals={btResult.signals}</span>
                  {btResult.run_id ? <span>run={btResult.run_id}</span> : null}
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
                  {Object.keys(METRIC_LABELS).map((key) => {
                    const value = btResult.metrics[key];
                    const label = METRIC_LABELS[key][language];
                    const tone =
                      key.endsWith('_return') && typeof value === 'number'
                        ? value >= 0
                          ? 'text-success'
                          : 'text-danger'
                        : key === 'max_drawdown'
                          ? 'text-danger'
                          : 'text-foreground';
                    return (
                      <div key={key} className="rounded-xl border border-border/60 bg-card/60 px-3 py-2">
                        <div className="text-xs text-secondary-text">{label}</div>
                        <div className={`mt-1 text-lg font-semibold ${tone}`}>{formatMetric(key, value)}</div>
                      </div>
                    );
                  })}
                </div>
              </Card>

              <Card title={copy.equity} variant="bordered">
                {chartData.length > 1 ? (
                  <div className="h-72 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
                        <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} width={48} />
                        <Tooltip
                          contentStyle={{
                            background: 'hsl(var(--card))',
                            border: '1px solid hsl(var(--border))',
                            borderRadius: 12,
                            color: 'hsl(var(--foreground))',
                          }}
                        />
                        <Legend />
                        <Line type="monotone" dataKey="strategy" name={copy.strategy} stroke="var(--color-cyan)" strokeWidth={2} dot={false} />
                        {btResult.benchmark && btResult.benchmark.length > 1 ? (
                          <Line
                            type="monotone"
                            dataKey="benchmark"
                            name={copy.benchmark}
                            stroke="hsl(var(--muted-foreground))"
                            strokeDasharray="5 4"
                            strokeWidth={1.6}
                            dot={false}
                            connectNulls
                          />
                        ) : null}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="text-sm text-secondary-text">{copy.noData}</p>
                )}
              </Card>

              <Card title={copy.trades} variant="bordered">
                <div className="mb-2 text-xs text-secondary-text">
                  {btResult.trades.length} · {copy.finalCash} {btResult.final_cash.toFixed(2)} · {copy.positions}{' '}
                  {Object.keys(btResult.final_positions).length}
                </div>
                <div className="max-h-96 overflow-auto">
                  <table className="w-full">
                    <thead>
                      <tr className={TABLE_HEAD_CLASS}>
                        <th className="py-2 pr-4">Date</th>
                        <th className="py-2 pr-4">Code</th>
                        <th className="py-2 pr-4">Side</th>
                        <th className="py-2 pr-4 text-right">Qty</th>
                        <th className="py-2 pr-4 text-right">Price</th>
                        <th className="py-2 pr-4 text-right">Fee</th>
                        <th className="py-2 pr-4 text-right">P&L</th>
                        <th className="py-2">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {btResult.trades.length ? (
                        btResult.trades.slice(0, 300).map((trade, index) => (
                          <tr key={`${trade.date}-${trade.code}-${trade.side}-${index}`}>
                            <td className={TABLE_CELL_CLASS}>{trade.date}</td>
                            <td className={TABLE_CELL_CLASS}>{trade.code}</td>
                            <td className={TABLE_CELL_CLASS}>
                              <Badge variant={trade.side === 'buy' ? 'success' : 'danger'}>{trade.side}</Badge>
                            </td>
                            <td className={`${TABLE_CELL_CLASS} text-right`}>{trade.quantity}</td>
                            <td className={`${TABLE_CELL_CLASS} text-right`}>{trade.price.toFixed(2)}</td>
                            <td className={`${TABLE_CELL_CLASS} text-right`}>{trade.fee.toFixed(2)}</td>
                            <td className={`${TABLE_CELL_CLASS} text-right`}>{trade.realized_pnl.toFixed(2)}</td>
                            <td className={TABLE_CELL_CLASS}>{trade.reason}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td className="py-3 text-sm text-secondary-text" colSpan={8}>
                            {copy.noData}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          ) : null}
        </div>
      ) : null}

      {tab === 'plugins' && status ? (
        <Card title={copy.pluginList} variant="bordered">
          {renderPlugins(status.plugins)}
          {status.plugin_errors.length ? (
            <InlineAlert
              className="mt-4"
              variant="danger"
              title={copy.pluginErrors}
              message={status.plugin_errors.join('\n')}
            />
          ) : null}
        </Card>
      ) : null}

      {tab === 'qmt' ? (
        <Card title={copy.qmtTitle} variant="bordered">
          <p className="mb-4 text-sm text-secondary-text">{copy.qmtHint}</p>
          <Button onClick={() => void handleQmt()} isLoading={qmtBusy} loadingText={copy.qmtChecking}>
            <ServerCog className="h-4 w-4" />
            {copy.qmtCheck}
          </Button>
          {qmtResult ? (
            <>
              <h3 className="mt-5 text-sm font-semibold text-foreground">{copy.qmtResult}</h3>
              <pre className="mt-2 overflow-auto rounded-xl border border-border/60 bg-base/60 p-4 text-xs text-secondary-text">
                {qmtResult}
              </pre>
            </>
          ) : null}
        </Card>
      ) : null}
    </AppPage>
  );
};

export default PersonalPage;
