import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pencil, Plus, RefreshCw, Target } from 'lucide-react';
import { Badge, Button, Card, EmptyState, InlineAlert } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { personalApi } from '../../api/personal';
import type {
  AccountSnapshot,
  PortfolioRiskResponse,
  TradePlan,
  TradePlanStatus,
} from '../../types/personal';
import { PortfolioRiskCard } from './PortfolioRiskCard';
import { TradePlanEditor } from './TradePlanEditor';

const INPUT_CLASS =
  'input-surface input-focus-glow h-9 rounded-lg border bg-transparent px-3 text-sm text-foreground transition-all focus:outline-none';
const TABLE_HEAD_CLASS =
  'border-b border-border/60 text-left text-xs uppercase tracking-[0.12em] text-secondary-text';
const TABLE_CELL_CLASS = 'border-b border-border/40 py-2.5 pr-4 text-sm text-foreground';

const COPY = {
  zh: {
    title: '交易计划',
    hint: '先定义逻辑与失效条件，再做风险预算和仓位预演。计划与实际成交分开保存。',
    create: '新建计划',
    refresh: '刷新',
    all: '全部状态',
    draft: '草稿',
    active: '执行中',
    closed: '已结束',
    cancelled: '已取消',
    code: '代码',
    side: '方向',
    buy: '买入',
    sell: '卖出',
    range: '计划区间',
    status: '状态',
    progress: '执行进度',
    thesis: '投资逻辑',
    actions: '操作',
    edit: '编辑',
    noPlans: '还没有交易计划',
    noPlansHint: '先导入账户截图，再创建带风险预算的盘前计划。',
    noSnapshot: '没有账户快照，先在账本导入同花顺截图。',
    loadError: '加载交易计划失败',
    updateError: '更新计划状态失败',
    fills: '笔成交',
    vwap: 'VWAP',
    requested: '计划',
    plannedLoss: '计划亏损',
    noPreview: '未预演',
    loading: '加载中…',
  },
  en: {
    title: 'Trade plans',
    hint: 'Define thesis and invalidation first, then size the position with an explicit risk budget. Plans and fills stay separate.',
    create: 'New plan',
    refresh: 'Refresh',
    all: 'All statuses',
    draft: 'Draft',
    active: 'Active',
    closed: 'Closed',
    cancelled: 'Cancelled',
    code: 'Code',
    side: 'Side',
    buy: 'Buy',
    sell: 'Sell',
    range: 'Range',
    status: 'Status',
    progress: 'Execution',
    thesis: 'Thesis',
    actions: 'Actions',
    edit: 'Edit',
    noPlans: 'No trade plans yet',
    noPlansHint: 'Import an account screenshot, then create a pre-trade plan with a risk budget.',
    noSnapshot: 'No account snapshot. Import a Tonghuashun screenshot in the ledger first.',
    loadError: 'Failed to load trade plans',
    updateError: 'Failed to update plan status',
    fills: 'fills',
    vwap: 'VWAP',
    requested: 'Plan',
    plannedLoss: 'Planned loss',
    noPreview: 'Not previewed',
    loading: 'Loading…',
  },
} as const;

function parsePreview(plan: TradePlan): Record<string, unknown> {
  if (!plan.preview_json) return {};
  try {
    const parsed = JSON.parse(plan.preview_json) as unknown;
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

export const TradePlanPanel: React.FC = () => {
  const { language } = useUiLanguage();
  const copy = COPY[language];
  const [plans, setPlans] = useState<TradePlan[]>([]);
  const [risk, setRisk] = useState<PortfolioRiskResponse | null>(null);
  const [snapshot, setSnapshot] = useState<AccountSnapshot | null>(null);
  const [statusFilter, setStatusFilter] = useState<TradePlanStatus | ''>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [actionId, setActionId] = useState<number | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<TradePlan | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [planData, riskData, snapshotData] = await Promise.all([
        personalApi.tradePlans(statusFilter),
        personalApi.portfolioRisk(),
        personalApi.accountSnapshotLatest(),
      ]);
      setPlans(planData.plans);
      setRisk(riskData);
      setSnapshot(snapshotData.snapshot);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const changeStatus = async (plan: TradePlan, status: TradePlanStatus) => {
    setActionId(plan.id);
    setActionError('');
    try {
      await personalApi.tradePlanStatus(plan.id, status);
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionId(null);
    }
  };

  const intendedQuantity = useMemo(() => {
    const mapping: Record<number, number | null> = {};
    for (const plan of plans) {
      const preview = parsePreview(plan);
      const suggested = preview.suggested_quantity;
      mapping[plan.id] =
        plan.requested_quantity ??
        (typeof suggested === 'number' ? suggested : null);
    }
    return mapping;
  }, [plans]);

  return (
    <div className="space-y-4">
      <Card title={copy.title} variant="bordered">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="max-w-3xl text-sm text-secondary-text">{copy.hint}</p>
            {!snapshot ? <p className="mt-2 text-sm text-warning">{copy.noSnapshot}</p> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className={INPUT_CLASS}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as TradePlanStatus | '')}
            >
              <option value="">{copy.all}</option>
              <option value="draft">{copy.draft}</option>
              <option value="active">{copy.active}</option>
              <option value="closed">{copy.closed}</option>
              <option value="cancelled">{copy.cancelled}</option>
            </select>
            <Button variant="secondary" size="sm" onClick={() => void load()} isLoading={loading}>
              <RefreshCw className="h-4 w-4" />
              {copy.refresh}
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!snapshot}
              onClick={() => {
                setEditing(null);
                setEditorOpen(true);
              }}
            >
              <Plus className="h-4 w-4" />
              {copy.create}
            </Button>
          </div>
        </div>
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
        {actionError ? (
          <InlineAlert className="mt-3" variant="danger" title={copy.updateError} message={actionError} />
        ) : null}

        <div className="mt-4 overflow-x-auto">
          {loading ? (
            <p className="text-sm text-secondary-text">{copy.loading}</p>
          ) : plans.length === 0 ? (
            <EmptyState
              title={copy.noPlans}
              description={copy.noPlansHint}
              icon={<Target className="h-6 w-6" />}
              action={
                snapshot ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setEditing(null);
                      setEditorOpen(true);
                    }}
                  >
                    {copy.create}
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <table className="w-full min-w-[980px]">
              <thead>
                <tr className={TABLE_HEAD_CLASS}>
                  <th className="py-2 pr-4">{copy.code}</th>
                  <th className="py-2 pr-4">{copy.side}</th>
                  <th className="py-2 pr-4">{copy.range}</th>
                  <th className="py-2 pr-4">{copy.status}</th>
                  <th className="py-2 pr-4">{copy.progress}</th>
                  <th className="py-2 pr-4">{copy.thesis}</th>
                  <th className="py-2 text-right">{copy.actions}</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => {
                  const preview = parsePreview(plan);
                  const target = intendedQuantity[plan.id];
                  return (
                    <tr key={plan.id}>
                      <td className={TABLE_CELL_CLASS}>
                        <div className="font-medium">
                          {plan.code} {plan.name ? <span className="text-secondary-text">{plan.name}</span> : null}
                        </div>
                        <div className="text-xs text-muted-text">{plan.plan_date}</div>
                      </td>
                      <td className={TABLE_CELL_CLASS}>
                        <Badge variant={plan.side === 'buy' ? 'success' : 'danger'}>
                          {plan.side === 'buy' ? copy.buy : copy.sell}
                        </Badge>
                      </td>
                      <td className={`${TABLE_CELL_CLASS} whitespace-nowrap`}>
                        {plan.entry_low.toFixed(3)} ~ {plan.entry_high.toFixed(3)}
                        <div className="text-xs text-muted-text">
                          {copy.plannedLoss}:{' '}
                          {typeof preview.planned_loss === 'number'
                            ? preview.planned_loss.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
                            : copy.noPreview}
                        </div>
                      </td>
                      <td className={TABLE_CELL_CLASS}>
                        <select
                          className="input-surface input-focus-glow h-8 rounded-lg border bg-transparent px-2 text-xs text-foreground focus:outline-none"
                          value={plan.status}
                          disabled={actionId === plan.id}
                          onChange={(event) =>
                            void changeStatus(plan, event.target.value as TradePlanStatus)
                          }
                        >
                          <option value="draft">{copy.draft}</option>
                          <option value="active">{copy.active}</option>
                          <option value="closed">{copy.closed}</option>
                          <option value="cancelled">{copy.cancelled}</option>
                        </select>
                      </td>
                      <td className={TABLE_CELL_CLASS}>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge variant={plan.fill_count > 0 ? 'success' : 'default'}>
                            {plan.fill_count} {copy.fills}
                          </Badge>
                          <span className="text-xs text-secondary-text">
                            {plan.filled_quantity.toLocaleString()} / {target?.toLocaleString() ?? '—'}
                          </span>
                        </div>
                        {plan.fill_vwap !== null ? (
                          <div className="text-xs text-muted-text">
                            VWAP {plan.fill_vwap.toFixed(3)}
                          </div>
                        ) : null}
                      </td>
                      <td className={`${TABLE_CELL_CLASS} max-w-[260px]`}>
                        <p className="line-clamp-2">{plan.thesis || '—'}</p>
                        {plan.invalidation ? (
                          <p className="mt-1 line-clamp-1 text-xs text-warning">{plan.invalidation}</p>
                        ) : null}
                      </td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>
                        <Button
                          size="xsm"
                          variant="secondary"
                          onClick={() => {
                            setEditing(plan);
                            setEditorOpen(true);
                          }}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                          {copy.edit}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Card>

      <PortfolioRiskCard risk={risk} />

      <TradePlanEditor
        isOpen={editorOpen}
        plan={editing}
        snapshot={snapshot}
        defaultBudgetPct={risk?.limits?.default_budget_pct ?? 1}
        defaultMaxPositionPct={risk?.limits?.max_single_pct ?? 20}
        onClose={() => setEditorOpen(false)}
        onSaved={() => void load()}
      />
    </div>
  );
};
