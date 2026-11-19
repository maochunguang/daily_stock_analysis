import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { Badge, Button, Card } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { personalApi } from '../../api/personal';
import type {
  BrokerImportSummary,
  BrokerJournalRow,
  BrokerPositionRow,
  BrokerSnapshot,
  TradePlan,
} from '../../types/personal';
import { TonghuashunImport } from './TonghuashunImport';
import { fileToBase64 } from './fileEncoding';

const TABLE_HEAD_CLASS =
  'border-b border-border/60 text-left text-xs uppercase tracking-[0.12em] text-secondary-text';
const TABLE_CELL_CLASS =
  'border-b border-border/40 py-2 pr-4 text-sm text-foreground whitespace-nowrap';

const COPY = {
  zh: {
    title: '账本（交割单 / 持仓 / 决策快照）',
    importTitle: '导入券商交割单',
    importHint:
      '支持 CSV/TSV/XLSX（GBK/UTF-8 自动识别）。列名不匹配时在下方填映射；导入自动去重、算成本并生成决策快照',
    choose: '选择文件',
    importBtn: '导入',
    importing: '导入中…',
    imported: '导入成功',
    rowsLabel: '行',
    journalLabel: '日志',
    skippedLabel: '跳过',
    warningsLabel: '注意',
    positionsTitle: '持仓（移动加权成本，含费）',
    journalTitle: '交易日志与决策快照',
    code: '代码',
    name: '名称',
    quantity: '数量',
    avgCost: '成本',
    realized: '已实现盈亏',
    dividend: '分红',
    fees: '费用',
    first: '首笔',
    last: '最近',
    side: '方向',
    price: '价格',
    amount: '金额',
    reason: '理由',
    snapshot: '当时市场',
    date: '日期',
    buy: '买入',
    sell: '卖出',
    noData: '暂无数据，先导入交割单',
    importFailed: '导入失败',
    emptyJournal: '暂无交易日志',
    planLabel: '关联交易计划（可选）',
    noPlan: '不关联',
    planHint: '只有代码和方向匹配的新成交会写入 plan_id',
    planLinked: '已关联计划成交',
  },
  en: {
    title: 'Ledger (statements / positions / decision snapshots)',
    importTitle: 'Import broker statement',
    importHint:
      'CSV/TSV/XLSX (GBK/UTF-8 auto). Map columns below if headers differ; import dedupes, computes cost and saves decision snapshots',
    choose: 'Choose file',
    importBtn: 'Import',
    importing: 'Importing…',
    imported: 'Imported',
    rowsLabel: 'rows',
    journalLabel: 'journal',
    skippedLabel: 'skipped',
    warningsLabel: 'warnings',
    positionsTitle: 'Positions (moving-average cost incl. fees)',
    journalTitle: 'Journal with decision snapshots',
    code: 'Code',
    name: 'Name',
    quantity: 'Qty',
    avgCost: 'Cost',
    realized: 'Realized P&L',
    dividend: 'Dividend',
    fees: 'Fees',
    first: 'First',
    last: 'Last',
    side: 'Side',
    price: 'Price',
    amount: 'Amount',
    reason: 'Reason',
    snapshot: 'Market at trade',
    date: 'Date',
    buy: 'Buy',
    sell: 'Sell',
    noData: 'No data yet — import a statement first',
    importFailed: 'Import failed',
    emptyJournal: 'Journal is empty',
    planLabel: 'Link trade plan (optional)',
    noPlan: 'No link',
    planHint: 'Only matching code/side fills receive plan_id',
    planLinked: 'Plan-linked fills',
  },
} as const;

function parseSnapshot(row: BrokerJournalRow): BrokerSnapshot | null {
  if (!row.snapshot) return null;
  if (typeof row.snapshot === 'object') return row.snapshot as BrokerSnapshot;
  try {
    return JSON.parse(row.snapshot) as BrokerSnapshot;
  } catch {
    return null;
  }
}

export const LedgerPanel: React.FC = () => {
  const { language } = useUiLanguage();
  const copy = COPY[language];
  const fileRef = useRef<HTMLInputElement>(null);
  const [positions, setPositions] = useState<BrokerPositionRow[]>([]);
  const [journal, setJournal] = useState<BrokerJournalRow[]>([]);
  const [summary, setSummary] = useState<BrokerImportSummary | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [activePlans, setActivePlans] = useState<TradePlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState('');

  const reload = useCallback(async () => {
    try {
      const [positionsData, journalData] = await Promise.all([
        personalApi.brokerPositions(),
        personalApi.brokerJournal(200),
      ]);
      setPositions(positionsData.positions);
      setJournal(journalData.journal);
      try {
        const plansData = await personalApi.tradePlans('');
        setActivePlans(
          plansData.plans.filter(
            (plan) => plan.status !== 'closed' && plan.status !== 'cancelled',
          ),
        );
      } catch {
        // A plan endpoint failure must not hide the working ledger.
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void reload().finally(() => setLoaded(true));
  }, [reload]);

  const handleFile = useCallback(
    async (file: File) => {
      setBusy(true);
      setError('');
      setSummary(null);
      try {
        const payload = {
          filename: file.name,
          content_b64: await fileToBase64(file),
          plan_id: selectedPlanId ? Number(selectedPlanId) : null,
        };
        const result = await personalApi.brokerImport(payload);
        setSummary(result);
        await reload();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
        if (fileRef.current) fileRef.current.value = '';
      }
    },
    [reload, selectedPlanId],
  );

  const held = positions.filter((row) => row.quantity > 0);
  const closed = positions.filter(
    (row) => row.quantity === 0 && (row.realized_pnl !== 0 || row.dividend_cash !== 0),
  );

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <TonghuashunImport />

      <Card title={copy.importTitle} variant="bordered" className="xl:col-span-2">
        <p className="text-sm text-secondary-text">{copy.importHint}</p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="min-w-[220px]">
            <span className="mb-1 block text-xs text-secondary-text">{copy.planLabel}</span>
            <select
              className="input-surface input-focus-glow h-10 w-full rounded-xl border bg-transparent px-3 text-sm text-foreground focus:outline-none"
              value={selectedPlanId}
              onChange={(event) => setSelectedPlanId(event.target.value)}
            >
              <option value="">{copy.noPlan}</option>
              {activePlans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  #{plan.id} {plan.plan_date} {plan.side === 'buy' ? copy.buy : copy.sell} {plan.code}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-xs text-muted-text">{copy.planHint}</span>
          </label>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.txt,.xlsx,.xlsm"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />
          <Button
            variant="primary"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="mr-1.5 h-4 w-4" />
            {busy ? copy.importing : `${copy.choose} / ${copy.importBtn}`}
          </Button>
          {summary ? (
            <span className="text-sm text-emerald-600">
              {copy.imported}: {summary.imported} {copy.rowsLabel} · {copy.journalLabel} +
              {summary.journal_added}
              {summary.skipped_total ? ` · ${copy.skippedLabel} ${summary.skipped_total}` : ''}
              {summary.plan_id
                ? ` · ${copy.planLinked} ${summary.plan_linked}`
                : ''}
            </span>
          ) : null}
        </div>
        {summary?.unrecognized_headers?.length ? (
          <p className="mt-2 text-xs text-amber-600">
            unmapped: {summary.unrecognized_headers.join(', ')}
          </p>
        ) : null}
        {summary?.warnings?.length ? (
          <ul className="mt-2 space-y-1 text-xs text-secondary-text">
            {summary.warnings.map((warning, index) => (
              <li key={index}>! {warning}</li>
            ))}
          </ul>
        ) : null}
        {error ? (
          <p className="mt-2 text-sm text-rose-600">
            {copy.importFailed}: {error}
          </p>
        ) : null}
      </Card>

      <Card title={copy.positionsTitle} variant="bordered" className="xl:col-span-2">
        {!loaded ? (
          <p className="text-sm text-secondary-text">…</p>
        ) : held.length === 0 && closed.length === 0 ? (
          <p className="text-sm text-secondary-text">{copy.noData}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className={TABLE_HEAD_CLASS}>
                  <th className="py-2 pr-4">{copy.code}</th>
                  <th className="py-2 pr-4">{copy.name}</th>
                  <th className="py-2 pr-4 text-right">{copy.quantity}</th>
                  <th className="py-2 pr-4 text-right">{copy.avgCost}</th>
                  <th className="py-2 pr-4 text-right">{copy.realized}</th>
                  <th className="py-2 pr-4 text-right">{copy.dividend}</th>
                  <th className="py-2 pr-4 text-right">{copy.fees}</th>
                  <th className="py-2 text-right">{copy.last}</th>
                </tr>
              </thead>
              <tbody>
                {[...held, ...closed].map((row) => (
                  <tr key={row.code}>
                    <td className={TABLE_CELL_CLASS}>{row.code}</td>
                    <td className={TABLE_CELL_CLASS}>{row.name || '—'}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>{row.quantity.toLocaleString()}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      {row.avg_cost?.toFixed(3) ?? '—'}
                    </td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      <span className={row.realized_pnl < 0 ? 'text-rose-600' : 'text-emerald-600'}>
                        {row.realized_pnl.toFixed(2)}
                      </span>
                    </td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      {row.dividend_cash ? row.dividend_cash.toFixed(2) : '—'}
                    </td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>{row.fees_total.toFixed(2)}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>{row.last_trade_date ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={copy.journalTitle} variant="bordered" className="xl:col-span-2">
        {!loaded ? (
          <p className="text-sm text-secondary-text">…</p>
        ) : journal.length === 0 ? (
          <p className="text-sm text-secondary-text">{copy.emptyJournal}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className={TABLE_HEAD_CLASS}>
                  <th className="py-2 pr-4">{copy.date}</th>
                  <th className="py-2 pr-4">{copy.code}</th>
                  <th className="py-2 pr-4">{copy.side}</th>
                  <th className="py-2 pr-4 text-right">{copy.quantity}</th>
                  <th className="py-2 pr-4 text-right">{copy.price}</th>
                  <th className="py-2 pr-4 text-right">{copy.amount}</th>
                  <th className="py-2 pr-4">{copy.reason}</th>
                  <th className="py-2">{copy.snapshot}</th>
                </tr>
              </thead>
              <tbody>
                {journal.map((row) => {
                  const snapshot = parseSnapshot(row);
                  const composite = snapshot?.composite;
                  const breadth = snapshot?.breadth;
                  return (
                    <tr key={row.id}>
                      <td className={TABLE_CELL_CLASS}>{row.trade_date}</td>
                      <td className={TABLE_CELL_CLASS}>{row.code}</td>
                      <td className={TABLE_CELL_CLASS}>
                        <Badge variant={row.side === 'buy' ? 'success' : 'danger'}>
                          {row.side === 'buy' ? copy.buy : copy.sell}
                        </Badge>
                      </td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>{row.quantity.toLocaleString()}</td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>{row.price.toFixed(3)}</td>
                      <td className={`${TABLE_CELL_CLASS} text-right`}>{row.amount.toFixed(2)}</td>
                      <td className={TABLE_CELL_CLASS}>{row.reason || '—'}</td>
                      <td className={TABLE_CELL_CLASS}>
                        {composite?.score !== null && composite?.score !== undefined ? (
                          <span className="inline-flex flex-wrap items-center gap-1.5">
                            <Badge variant={composite.score >= 60 ? 'danger' : composite.score <= 40 ? 'info' : 'default'}>
                              {composite.score} {composite.state}
                            </Badge>
                            {breadth?.trin !== null && breadth?.trin !== undefined ? (
                              <Badge variant="default">{`TRIN ${breadth.trin.toFixed(2)} ${breadth.band}`}</Badge>
                            ) : null}
                            {composite.components
                              .filter((component) =>
                                ['pcr_vol', 'futures_net_ratio'].includes(component.metric),
                              )
                              .map((component) => (
                                <Badge key={component.metric} variant="warning">
                                  {`${component.label} ${component.percentile ?? '—'}%`}
                                </Badge>
                              ))}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
