import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Calculator, Save, ShieldAlert } from 'lucide-react';
import { Badge, Button, Drawer, InlineAlert } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { personalApi } from '../../api/personal';
import type {
  AccountSnapshot,
  TradePlan,
  TradePlanPreview,
  TradePlanRequest,
  TradePlanSide,
  TradePlanStatus,
} from '../../types/personal';

const INPUT_CLASS =
  'input-surface input-focus-glow h-10 w-full rounded-xl border bg-transparent px-3 text-sm text-foreground transition-all focus:outline-none';
const LABEL_CLASS = 'mb-1 block text-xs font-medium text-secondary-text';
const TEXTAREA_CLASS =
  'input-surface input-focus-glow min-h-[76px] w-full rounded-xl border bg-transparent px-3 py-2 text-sm text-foreground transition-all focus:outline-none';

const COPY = {
  zh: {
    create: '新建交易计划',
    edit: '编辑交易计划',
    date: '计划日期',
    validUntil: '有效期至',
    code: '代码',
    name: '名称',
    side: '方向',
    buy: '买入',
    sell: '卖出',
    entryLow: '计划价格下限',
    entryHigh: '计划价格上限',
    stop: '止损价',
    target: '目标价',
    riskMode: '风险预算方式',
    riskPct: '按总资产比例',
    riskAmount: '按金额',
    budget: '风险预算',
    maxPosition: '单票上限 %',
    requested: '计划数量（可选）',
    horizon: '持有周期（天）',
    status: '状态',
    draft: '草稿',
    active: '执行中',
    closed: '已结束',
    cancelled: '已取消',
    thesis: '投资逻辑',
    catalyst: '催化剂',
    invalidation: '逻辑失效条件',
    preview: '风险预演',
    recalculating: '计算中…',
    save: '保存计划',
    saving: '保存中…',
    previewFirst: '先做风险预演才能保存',
    noSnapshot: '没有账户快照，先在账本导入同花顺截图。',
    blockers: '无法保存',
    warnings: '风险提示',
    suggestedQty: '建议数量',
    plannedLoss: '计划亏损',
    riskUsed: '风险使用',
    entryFill: '保守成交价',
    postCash: '交易后现金',
    postWeight: '交易后单票',
    postTop5: '交易后 Top5',
    rewardRisk: '盈亏比',
    snapshotLabel: '账户快照',
    equity: '总资产',
    saveFailed: '保存失败',
    previewFailed: '预演失败',
  },
  en: {
    create: 'New trade plan',
    edit: 'Edit trade plan',
    date: 'Plan date',
    validUntil: 'Valid until',
    code: 'Code',
    name: 'Name',
    side: 'Side',
    buy: 'Buy',
    sell: 'Sell',
    entryLow: 'Entry low',
    entryHigh: 'Entry high',
    stop: 'Stop',
    target: 'Target',
    riskMode: 'Risk budget mode',
    riskPct: 'Percent of equity',
    riskAmount: 'Fixed amount',
    budget: 'Risk budget',
    maxPosition: 'Max position %',
    requested: 'Requested qty (optional)',
    horizon: 'Horizon (days)',
    status: 'Status',
    draft: 'Draft',
    active: 'Active',
    closed: 'Closed',
    cancelled: 'Cancelled',
    thesis: 'Thesis',
    catalyst: 'Catalyst',
    invalidation: 'Invalidation',
    preview: 'Risk preview',
    recalculating: 'Calculating…',
    save: 'Save plan',
    saving: 'Saving…',
    previewFirst: 'Run a risk preview before saving',
    noSnapshot: 'No account snapshot. Import a Tonghuashun screenshot in the ledger first.',
    blockers: 'Cannot save',
    warnings: 'Risk notes',
    suggestedQty: 'Suggested qty',
    plannedLoss: 'Planned loss',
    riskUsed: 'Risk used',
    entryFill: 'Conservative fill',
    postCash: 'Post-trade cash',
    postWeight: 'Post-trade name',
    postTop5: 'Post-trade Top5',
    rewardRisk: 'Reward/risk',
    snapshotLabel: 'Account snapshot',
    equity: 'Equity',
    saveFailed: 'Save failed',
    previewFailed: 'Preview failed',
  },
} as const;

interface FormState {
  plan_date: string;
  valid_until: string;
  code: string;
  name: string;
  side: TradePlanSide;
  entry_low: string;
  entry_high: string;
  stop_loss: string;
  target_price: string;
  risk_mode: 'pct' | 'amount';
  risk_budget_pct: string;
  risk_budget_amount: string;
  max_position_pct: string;
  requested_quantity: string;
  status: TradePlanStatus;
  thesis: string;
  catalyst: string;
  invalidation: string;
  horizon_days: string;
}

function localToday(): string {
  const value = new Date();
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function value(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

function formFromPlan(
  plan: TradePlan | null,
  defaultBudgetPct: number,
  defaultMaxPositionPct: number,
): FormState {
  return {
    plan_date: plan?.plan_date || localToday(),
    valid_until: plan?.valid_until || '',
    code: plan?.code || '',
    name: plan?.name || '',
    side: plan?.side || 'buy',
    entry_low: value(plan?.entry_low),
    entry_high: value(plan?.entry_high),
    stop_loss: value(plan?.stop_loss),
    target_price: value(plan?.target_price),
    risk_mode: plan?.risk_budget_amount !== null && plan?.risk_budget_amount !== undefined ? 'amount' : 'pct',
    risk_budget_pct: value(plan?.risk_budget_pct ?? defaultBudgetPct),
    risk_budget_amount: value(plan?.risk_budget_amount),
    max_position_pct: value(plan?.max_position_pct ?? defaultMaxPositionPct),
    requested_quantity: value(plan?.requested_quantity),
    status: plan?.status || 'draft',
    thesis: plan?.thesis || '',
    catalyst: plan?.catalyst || '',
    invalidation: plan?.invalidation || '',
    horizon_days: value(plan?.horizon_days),
  };
}

function numberOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function toRequest(form: FormState, plan: TradePlan | null, snapshot: AccountSnapshot | null): TradePlanRequest {
  return {
    plan_date: form.plan_date || null,
    valid_until: form.valid_until || null,
    code: form.code.trim(),
    name: form.name.trim(),
    side: form.side,
    entry_low: numberOrNull(form.entry_low) ?? 0,
    entry_high: numberOrNull(form.entry_high) ?? 0,
    stop_loss: numberOrNull(form.stop_loss),
    target_price: numberOrNull(form.target_price),
    risk_budget_pct: form.risk_mode === 'pct' ? numberOrNull(form.risk_budget_pct) : null,
    risk_budget_amount:
      form.risk_mode === 'amount' ? numberOrNull(form.risk_budget_amount) : null,
    max_position_pct: numberOrNull(form.max_position_pct),
    requested_quantity: numberOrNull(form.requested_quantity),
    account_snapshot_id: snapshot?.id ?? plan?.account_snapshot_id ?? null,
    status: form.status,
    thesis: form.thesis.trim(),
    catalyst: form.catalyst.trim(),
    invalidation: form.invalidation.trim(),
    horizon_days: numberOrNull(form.horizon_days),
    analysis_id: plan?.analysis_id ?? null,
    decision_signal_id: plan?.decision_signal_id ?? null,
  };
}

interface TradePlanEditorProps {
  isOpen: boolean;
  plan: TradePlan | null;
  snapshot: AccountSnapshot | null;
  defaultBudgetPct?: number;
  defaultMaxPositionPct?: number;
  onClose: () => void;
  onSaved: () => void;
}

export const TradePlanEditor: React.FC<TradePlanEditorProps> = ({
  isOpen,
  plan,
  snapshot,
  defaultBudgetPct = 1,
  defaultMaxPositionPct = 20,
  onClose,
  onSaved,
}) => {
  const { language } = useUiLanguage();
  const copy = COPY[language];
  const [form, setForm] = useState<FormState>(() =>
    formFromPlan(plan, defaultBudgetPct, defaultMaxPositionPct),
  );
  const [preview, setPreview] = useState<TradePlanPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    setForm(formFromPlan(plan, defaultBudgetPct, defaultMaxPositionPct));
    setPreview(null);
    setError('');
  }, [isOpen, plan, defaultBudgetPct, defaultMaxPositionPct]);

  const update = <K extends keyof FormState>(key: K, next: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: next }));
    setPreview(null);
    setError('');
  };

  const request = useMemo(() => toRequest(form, plan, snapshot), [form, plan, snapshot]);
  const canPreview = Boolean(snapshot) && Boolean(form.code.trim()) && !previewing;

  const runPreview = async () => {
    setPreviewing(true);
    setError('');
    try {
      const result = await personalApi.tradePlanPreview(request);
      setPreview(result.preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPreview(null);
    } finally {
      setPreviewing(false);
    }
  };

  const save = async () => {
    if (!preview || preview.blockers.length) return;
    setBusy(true);
    setError('');
    try {
      if (plan?.id) {
        await personalApi.tradePlanUpdate(plan.id, request);
      } else {
        await personalApi.tradePlanCreate(request);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(`${copy.saveFailed}: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title={plan ? copy.edit : copy.create} width="max-w-3xl">
      <div className="space-y-4">
        {!snapshot ? (
          <InlineAlert variant="warning" title={copy.noSnapshot} message={copy.noSnapshot} />
        ) : (
          <div className="flex flex-wrap gap-2">
            <Badge variant="success">
              {copy.snapshotLabel} {snapshot.as_of}
            </Badge>
            <Badge variant="default">
              {copy.equity} {snapshot.equity?.toLocaleString('zh-CN') ?? '—'}
            </Badge>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label>
            <span className={LABEL_CLASS}>{copy.date}</span>
            <input
              type="date"
              className={INPUT_CLASS}
              value={form.plan_date}
              onChange={(event) => update('plan_date', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.validUntil}</span>
            <input
              type="date"
              className={INPUT_CLASS}
              value={form.valid_until}
              onChange={(event) => update('valid_until', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.side}</span>
            <select
              className={INPUT_CLASS}
              value={form.side}
              onChange={(event) => update('side', event.target.value as TradePlanSide)}
            >
              <option value="buy">{copy.buy}</option>
              <option value="sell">{copy.sell}</option>
            </select>
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.status}</span>
            <select
              className={INPUT_CLASS}
              value={form.status}
              onChange={(event) => update('status', event.target.value as TradePlanStatus)}
            >
              <option value="draft">{copy.draft}</option>
              <option value="active">{copy.active}</option>
              <option value="closed">{copy.closed}</option>
              <option value="cancelled">{copy.cancelled}</option>
            </select>
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.code}</span>
            <input
              className={INPUT_CLASS}
              value={form.code}
              placeholder="600519"
              onChange={(event) => update('code', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.name}</span>
            <input
              className={INPUT_CLASS}
              value={form.name}
              onChange={(event) => update('name', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.entryLow}</span>
            <input
              inputMode="decimal"
              className={INPUT_CLASS}
              value={form.entry_low}
              onChange={(event) => update('entry_low', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.entryHigh}</span>
            <input
              inputMode="decimal"
              className={INPUT_CLASS}
              value={form.entry_high}
              onChange={(event) => update('entry_high', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.stop}</span>
            <input
              inputMode="decimal"
              className={INPUT_CLASS}
              value={form.stop_loss}
              onChange={(event) => update('stop_loss', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.target}</span>
            <input
              inputMode="decimal"
              className={INPUT_CLASS}
              value={form.target_price}
              onChange={(event) => update('target_price', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.riskMode}</span>
            <select
              className={INPUT_CLASS}
              value={form.risk_mode}
              onChange={(event) => update('risk_mode', event.target.value as 'pct' | 'amount')}
            >
              <option value="pct">{copy.riskPct}</option>
              <option value="amount">{copy.riskAmount}</option>
            </select>
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.budget}</span>
            <input
              inputMode="decimal"
              className={INPUT_CLASS}
              value={form.risk_mode === 'pct' ? form.risk_budget_pct : form.risk_budget_amount}
              onChange={(event) =>
                update(
                  form.risk_mode === 'pct' ? 'risk_budget_pct' : 'risk_budget_amount',
                  event.target.value,
                )
              }
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.maxPosition}</span>
            <input
              inputMode="decimal"
              className={INPUT_CLASS}
              value={form.max_position_pct}
              onChange={(event) => update('max_position_pct', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.requested}</span>
            <input
              inputMode="decimal"
              className={INPUT_CLASS}
              value={form.requested_quantity}
              onChange={(event) => update('requested_quantity', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.horizon}</span>
            <input
              inputMode="numeric"
              className={INPUT_CLASS}
              value={form.horizon_days}
              onChange={(event) => update('horizon_days', event.target.value)}
            />
          </label>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <label>
            <span className={LABEL_CLASS}>{copy.thesis}</span>
            <textarea
              className={TEXTAREA_CLASS}
              value={form.thesis}
              onChange={(event) => update('thesis', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.catalyst}</span>
            <textarea
              className={TEXTAREA_CLASS}
              value={form.catalyst}
              onChange={(event) => update('catalyst', event.target.value)}
            />
          </label>
          <label>
            <span className={LABEL_CLASS}>{copy.invalidation}</span>
            <textarea
              className={TEXTAREA_CLASS}
              value={form.invalidation}
              onChange={(event) => update('invalidation', event.target.value)}
            />
          </label>
        </div>

        {error ? <InlineAlert variant="danger" title={copy.saveFailed} message={error} /> : null}
        {preview?.blockers.length ? (
          <InlineAlert
            variant="danger"
            title={copy.blockers}
            message={preview.blockers.join('；')}
          />
        ) : null}
        {preview?.warnings.length ? (
          <InlineAlert
            variant="warning"
            title={copy.warnings}
            message={preview.warnings.join('；')}
          />
        ) : null}

        {preview ? (
          <div className="rounded-2xl border border-cyan/20 bg-cyan/5 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-cyan">
              <ShieldAlert className="h-4 w-4" />
              {copy.preview}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                [copy.suggestedQty, preview.suggested_quantity.toLocaleString()],
                [copy.entryFill, preview.entry_fill.toFixed(3)],
                [
                  copy.plannedLoss,
                  preview.planned_loss === null
                    ? '—'
                    : preview.planned_loss.toLocaleString('zh-CN', { maximumFractionDigits: 2 }),
                ],
                [copy.riskUsed, preview.risk_used_pct === null ? '—' : `${preview.risk_used_pct.toFixed(1)}%`],
                [
                  copy.postCash,
                  preview.post_trade_cash === null
                    ? '—'
                    : preview.post_trade_cash.toLocaleString('zh-CN', { maximumFractionDigits: 2 }),
                ],
                [copy.postWeight, preview.post_trade_position_weight_pct === null ? '—' : `${preview.post_trade_position_weight_pct.toFixed(1)}%`],
                [copy.postTop5, preview.post_trade_top5_pct === null ? '—' : `${preview.post_trade_top5_pct.toFixed(1)}%`],
                [copy.rewardRisk, preview.reward_risk ?? '—'],
              ].map(([label, display]) => (
                <div key={String(label)} className="rounded-xl border border-border/50 bg-card/60 p-3">
                  <p className="text-xs text-secondary-text">{label}</p>
                  <p className="mt-1 text-lg font-semibold text-foreground">{display}</p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-secondary-text">{copy.previewFirst}</p>
        )}

        <div className="flex flex-wrap justify-end gap-2 border-t border-border/50 pt-4">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {language === 'zh' ? '取消' : 'Cancel'}
          </Button>
          <Button
            variant="secondary"
            onClick={() => void runPreview()}
            isLoading={previewing}
            loadingText={copy.recalculating}
            disabled={!canPreview}
          >
            <Calculator className="h-4 w-4" />
            {copy.preview}
          </Button>
          <Button
            variant="primary"
            onClick={() => void save()}
            isLoading={busy}
            loadingText={copy.saving}
            disabled={!preview || preview.blockers.length > 0}
          >
            <Save className="h-4 w-4" />
            {copy.save}
          </Button>
        </div>
      </div>
    </Drawer>
  );
};
