import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ImagePlus, Plus, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { Badge, Button, Card, EmptyState, InlineAlert } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { personalApi } from '../../api/personal';
import type { AccountPosition, AccountSnapshot, AccountSnapshotDraft } from '../../types/personal';
import { fileToBase64 } from './fileEncoding';

const INPUT_CLASS =
  'input-surface input-focus-glow h-10 w-full rounded-xl border bg-transparent px-3 text-sm text-foreground transition-all focus:outline-none';
const LABEL_CLASS = 'mb-1 block text-xs font-medium text-secondary-text';
const TABLE_HEAD_CLASS =
  'border-b border-border/60 text-left text-xs uppercase tracking-[0.12em] text-secondary-text';
const TABLE_CELL_CLASS = 'border-b border-border/40 py-2 pr-3 text-sm text-foreground';

interface EditablePosition {
  code: string;
  name: string;
  quantity: string;
  available_quantity: string;
  avg_cost: string;
  market_price: string;
  market_value: string;
  pnl: string;
}

interface EditableDraft {
  account_alias: string;
  as_of: string;
  cash: string;
  available_cash: string;
  market_value: string;
  equity: string;
  positions: EditablePosition[];
}

const COPY = {
  zh: {
    title: '同花顺截图导入',
    hint: '本地 OCR，图片不上传云端；识别结果需要核对后确认。只生成账户快照，不改动交割单持仓。',
    choose: '选择截图',
    manual: '手工录入',
    parsing: '识别中…',
    image: '截图',
    noImage: '未选择图片',
    accountAlias: '账户别名',
    asOf: '快照日期',
    equity: '总资产',
    cash: '现金',
    availableCash: '可用资金',
    marketValue: '持仓市值',
    positions: '持仓明细',
    addRow: '加一行',
    remove: '删除',
    code: '代码',
    name: '名称',
    quantity: '数量',
    available: '可用',
    avgCost: '成本',
    price: '现价',
    marketValueShort: '市值',
    pnl: '盈亏',
    confirm: '确认保存快照',
    saving: '保存中…',
    saved: '账户快照已保存',
    warnings: '识别提示',
    error: '操作失败',
    latest: '最新账户快照',
    noSnapshot: '还没有账户快照，先导入一张同花顺资产/持仓截图',
    refresh: '刷新',
    alias: '账户',
    positionsCount: '持仓',
    confirmTitle: '请核对后再保存',
    confirmHint: 'OCR 可能把数字、列或账户项识别错；确认后会覆盖同日同账户的旧快照。',
    unsupported: '支持 PNG/JPEG/WebP/HEIC，最大 8MB',
    codeRequired: '持仓缺少代码',
    asOfRequired: '请填写快照日期',
    savedWarnings: '保存提示',
    noRows: '暂无持仓行',
  },
  en: {
    title: 'Tonghuashun screenshot import',
    hint: 'Local OCR; images never leave this host. Review before confirming. This creates an account snapshot only and never overwrites statement-derived positions.',
    choose: 'Choose screenshot',
    manual: 'Manual entry',
    parsing: 'Recognizing…',
    image: 'Screenshot',
    noImage: 'No image selected',
    accountAlias: 'Account alias',
    asOf: 'Snapshot date',
    equity: 'Equity',
    cash: 'Cash',
    availableCash: 'Available cash',
    marketValue: 'Market value',
    positions: 'Positions',
    addRow: 'Add row',
    remove: 'Remove',
    code: 'Code',
    name: 'Name',
    quantity: 'Qty',
    available: 'Available',
    avgCost: 'Cost',
    price: 'Price',
    marketValueShort: 'Value',
    pnl: 'P&L',
    confirm: 'Confirm snapshot',
    saving: 'Saving…',
    saved: 'Account snapshot saved',
    warnings: 'OCR notes',
    error: 'Action failed',
    latest: 'Latest account snapshot',
    noSnapshot: 'No account snapshot yet — import a Tonghuashun asset/holdings screenshot',
    refresh: 'Refresh',
    alias: 'Account',
    positionsCount: 'Positions',
    confirmTitle: 'Review before saving',
    confirmHint: 'OCR can misread numbers or columns. Confirming replaces the same alias/date snapshot.',
    unsupported: 'PNG/JPEG/WebP/HEIC up to 8MB',
    codeRequired: 'Position is missing a code',
    asOfRequired: 'Snapshot date is required',
    savedWarnings: 'Save notes',
    noRows: 'No position rows',
  },
} as const;

function localToday(): string {
  const value = new Date();
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function emptyPosition(): EditablePosition {
  return {
    code: '',
    name: '',
    quantity: '',
    available_quantity: '',
    avg_cost: '',
    market_price: '',
    market_value: '',
    pnl: '',
  };
}

function emptyDraft(): EditableDraft {
  return {
    account_alias: '同花顺',
    as_of: localToday(),
    cash: '',
    available_cash: '',
    market_value: '',
    equity: '',
    positions: [],
  };
}

function formatNumber(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === '' ? '' : String(value);
}

function draftFromOcr(draft: AccountSnapshotDraft): EditableDraft {
  return {
    account_alias: draft.account_alias || '同花顺',
    as_of: draft.as_of || localToday(),
    cash: formatNumber(draft.cash),
    available_cash: formatNumber(draft.available_cash),
    market_value: formatNumber(draft.market_value),
    equity: formatNumber(draft.equity),
    positions: draft.positions.map((position) => ({
      code: position.code,
      name: position.name || '',
      quantity: formatNumber(position.quantity),
      available_quantity: formatNumber(position.available_quantity),
      avg_cost: formatNumber(position.avg_cost),
      market_price: formatNumber(position.market_price),
      market_value: formatNumber(position.market_value),
      pnl: formatNumber(position.pnl),
    })),
  };
}

function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function toPosition(row: EditablePosition): AccountPosition {
  return {
    code: row.code.trim(),
    name: row.name.trim(),
    quantity: numberOrNull(row.quantity) ?? 0,
    available_quantity: numberOrNull(row.available_quantity),
    avg_cost: numberOrNull(row.avg_cost),
    market_price: numberOrNull(row.market_price),
    market_value: numberOrNull(row.market_value),
    pnl: numberOrNull(row.pnl),
  };
}

export const TonghuashunImport: React.FC = () => {
  const { language } = useUiLanguage();
  const copy = COPY[language];
  const fileRef = useRef<HTMLInputElement>(null);
  const imageUrlRef = useRef<string | null>(null);
  const [snapshot, setSnapshot] = useState<AccountSnapshot | null>(null);
  const [draft, setDraft] = useState<EditableDraft | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [ocrWarnings, setOcrWarnings] = useState<string[]>([]);
  const [saveWarnings, setSaveWarnings] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [contentHash, setContentHash] = useState('');
  const [ocrEngine, setOcrEngine] = useState('');
  const [sourceFile, setSourceFile] = useState('');

  const loadLatest = useCallback(async () => {
    try {
      const payload = await personalApi.accountSnapshotLatest();
      setSnapshot(payload.snapshot);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void loadLatest();
  }, [loadLatest]);

  useEffect(() => {
    return () => {
      if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
    };
  }, []);

  const replaceImageUrl = (url: string | null) => {
    if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
    imageUrlRef.current = url;
    setImageUrl(url);
  };

  const handleFile = useCallback(async (file: File) => {
    if (file.size > 8 * 1024 * 1024) {
      setError(`${copy.unsupported}: ${file.name}`);
      return;
    }
    setBusy(true);
    setError('');
    setOcrWarnings([]);
    setSaveWarnings([]);
    replaceImageUrl(URL.createObjectURL(file));
    try {
      const contentB64 = await fileToBase64(file);
      const result = await personalApi.accountSnapshotParse({
        filename: file.name,
        content_b64: contentB64,
      });
      setDraft(draftFromOcr(result.draft));
      setOcrWarnings(result.warnings);
      setContentHash(result.content_hash);
      setOcrEngine(result.ocr_engine);
      setSourceFile(result.filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDraft(emptyDraft());
      setContentHash('');
      setOcrEngine('manual');
      setSourceFile(file.name);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }, [copy.unsupported]);

  const startManual = () => {
    replaceImageUrl(null);
    setDraft(emptyDraft());
    setOcrWarnings([]);
    setSaveWarnings([]);
    setContentHash('');
    setOcrEngine('manual');
    setSourceFile('');
    setError('');
  };

  const updateDraft = (patch: Partial<EditableDraft>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current));
  };

  const updatePosition = (index: number, field: keyof EditablePosition, value: string) => {
    setDraft((current) => {
      if (!current) return current;
      const positions = current.positions.map((row, rowIndex) =>
        rowIndex === index ? { ...row, [field]: value } : row,
      );
      return { ...current, positions };
    });
  };

  const addPosition = () => {
    setDraft((current) =>
      current ? { ...current, positions: [...current.positions, emptyPosition()] } : current,
    );
  };

  const removePosition = (index: number) => {
    setDraft((current) =>
      current
        ? { ...current, positions: current.positions.filter((_, rowIndex) => rowIndex !== index) }
        : current,
    );
  };

  const save = async () => {
    if (!draft) return;
    if (!draft.as_of) {
      setError(copy.asOfRequired);
      return;
    }
    const missingCode = draft.positions.find((row) => !row.code.trim());
    if (missingCode) {
      setError(copy.codeRequired);
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await personalApi.accountSnapshotConfirm({
        account_alias: draft.account_alias.trim() || '同花顺',
        as_of: draft.as_of,
        cash: numberOrNull(draft.cash),
        available_cash: numberOrNull(draft.available_cash),
        market_value: numberOrNull(draft.market_value),
        equity: numberOrNull(draft.equity),
        positions: draft.positions.map(toPosition),
        source_file: sourceFile,
        content_hash: contentHash,
        ocr_engine: ocrEngine,
      });
      setSnapshot(result.snapshot);
      setSaveWarnings(result.warnings);
      setOcrWarnings([]);
      setDraft(null);
      replaceImageUrl(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const accountFields: Array<{
    key: keyof Pick<EditableDraft, 'equity' | 'cash' | 'available_cash' | 'market_value'>;
    label: string;
  }> = [
    { key: 'equity', label: copy.equity },
    { key: 'cash', label: copy.cash },
    { key: 'available_cash', label: copy.availableCash },
    { key: 'market_value', label: copy.marketValue },
  ];

  return (
    <Card title={copy.title} variant="bordered" className="xl:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-secondary-text">{copy.hint}</p>
        <div className="flex flex-wrap gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.heic,.heif,image/*"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />
          <Button variant="primary" size="sm" isLoading={busy} onClick={() => fileRef.current?.click()}>
            <Upload className="h-4 w-4" />
            {busy ? copy.parsing : copy.choose}
          </Button>
          <Button variant="secondary" size="sm" onClick={startManual}>
            <ImagePlus className="h-4 w-4" />
            {copy.manual}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => void loadLatest()}>
            {copy.refresh}
          </Button>
        </div>
      </div>
      <p className="mt-2 text-xs text-muted-text">{copy.unsupported}</p>

      {error ? (
        <InlineAlert className="mt-3" variant="danger" title={copy.error} message={error} />
      ) : null}
      {saveWarnings.length ? (
        <InlineAlert
          className="mt-3"
          variant="warning"
          title={copy.savedWarnings}
          message={saveWarnings.join('；')}
        />
      ) : null}
      {ocrWarnings.length ? (
        <InlineAlert
          className="mt-3"
          variant="warning"
          title={copy.warnings}
          message={ocrWarnings.join('；')}
        />
      ) : null}

      {draft ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(260px,0.8fr)_minmax(0,2fr)]">
          <div className="space-y-3">
            <p className={LABEL_CLASS}>{copy.image}</p>
            {imageUrl ? (
              <img
                src={imageUrl}
                alt={copy.image}
                className="max-h-80 w-full rounded-xl border border-border/60 object-contain bg-elevated/30"
              />
            ) : (
              <div className="rounded-xl border border-dashed border-border/60 p-6 text-sm text-secondary-text">
                {copy.noImage}
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              <label>
                <span className={LABEL_CLASS}>{copy.accountAlias}</span>
                <input
                  aria-label={copy.accountAlias}
                  className={INPUT_CLASS}
                  value={draft.account_alias}
                  onChange={(event) => updateDraft({ account_alias: event.target.value })}
                />
              </label>
              <label>
                <span className={LABEL_CLASS}>{copy.asOf}</span>
                <input
                  aria-label={copy.asOf}
                  type="date"
                  className={INPUT_CLASS}
                  value={draft.as_of}
                  onChange={(event) => updateDraft({ as_of: event.target.value })}
                />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {accountFields.map((field) => (
                <label key={field.key}>
                  <span className={LABEL_CLASS}>{field.label}</span>
                  <input
                    aria-label={field.label}
                    inputMode="decimal"
                    className={INPUT_CLASS}
                    value={draft[field.key]}
                    onChange={(event) => updateDraft({ [field.key]: event.target.value })}
                  />
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-text">{copy.confirmHint}</p>
            <Button
              variant="primary"
              className="w-full"
              isLoading={busy}
              loadingText={copy.saving}
              onClick={() => void save()}
            >
              <ShieldCheck className="h-4 w-4" />
              {copy.confirm}
            </Button>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-medium text-foreground">
                {copy.positions} · {draft.positions.length}
              </p>
              <Button variant="secondary" size="xsm" onClick={addPosition}>
                <Plus className="h-3.5 w-3.5" />
                {copy.addRow}
              </Button>
            </div>
            <div className="overflow-x-auto rounded-xl border border-border/50">
              <table className="w-full min-w-[920px]">
                <thead>
                  <tr className={TABLE_HEAD_CLASS}>
                    <th className="px-2 py-2">{copy.code}</th>
                    <th className="px-2 py-2">{copy.name}</th>
                    <th className="px-2 py-2 text-right">{copy.quantity}</th>
                    <th className="px-2 py-2 text-right">{copy.available}</th>
                    <th className="px-2 py-2 text-right">{copy.avgCost}</th>
                    <th className="px-2 py-2 text-right">{copy.price}</th>
                    <th className="px-2 py-2 text-right">{copy.marketValueShort}</th>
                    <th className="px-2 py-2 text-right">{copy.pnl}</th>
                    <th className="px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {draft.positions.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="px-3 py-5 text-center text-sm text-secondary-text">
                        {copy.noRows}
                      </td>
                    </tr>
                  ) : (
                    draft.positions.map((row, index) => (
                      <tr key={`${row.code}-${index}`}>
                        {(
                          [
                            'code',
                            'name',
                            'quantity',
                            'available_quantity',
                            'avg_cost',
                            'market_price',
                            'market_value',
                            'pnl',
                          ] as Array<keyof EditablePosition>
                        ).map((field) => (
                          <td key={field} className={`${TABLE_CELL_CLASS} px-1 py-1`}>
                            <input
                              inputMode={field === 'code' || field === 'name' ? 'text' : 'decimal'}
                              className="input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-2 text-sm text-foreground focus:outline-none"
                              value={row[field]}
                              onChange={(event) => updatePosition(index, field, event.target.value)}
                            />
                          </td>
                        ))}
                        <td className={`${TABLE_CELL_CLASS} px-1 py-1`}>
                          <button
                            type="button"
                            aria-label={copy.remove}
                            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-danger/30 text-danger hover:bg-danger/10"
                            onClick={() => removePosition(index)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : loaded && snapshot ? (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="success">
              {copy.latest} · {snapshot.as_of}
            </Badge>
            <Badge variant="default">
              {copy.alias} {snapshot.account_alias}
            </Badge>
            <Badge variant="info">
              {copy.positionsCount} {snapshot.positions.length}
            </Badge>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-4">
            {[
              [copy.equity, snapshot.equity],
              [copy.cash, snapshot.cash],
              [copy.availableCash, snapshot.available_cash],
              [copy.marketValue, snapshot.market_value],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl border border-border/50 bg-elevated/20 p-3">
                <p className="text-xs text-secondary-text">{label}</p>
                <p className="mt-1 text-lg font-semibold text-foreground">
                  {value === null || value === undefined
                    ? '—'
                    : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}
                </p>
              </div>
            ))}
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className={TABLE_HEAD_CLASS}>
                  <th className="py-2 pr-4">{copy.code}</th>
                  <th className="py-2 pr-4">{copy.name}</th>
                  <th className="py-2 pr-4 text-right">{copy.quantity}</th>
                  <th className="py-2 pr-4 text-right">{copy.available}</th>
                  <th className="py-2 pr-4 text-right">{copy.avgCost}</th>
                  <th className="py-2 pr-4 text-right">{copy.price}</th>
                  <th className="py-2 pr-4 text-right">{copy.marketValueShort}</th>
                  <th className="py-2 text-right">{copy.pnl}</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.positions.map((row) => (
                  <tr key={row.code}>
                    <td className={TABLE_CELL_CLASS}>{row.code}</td>
                    <td className={TABLE_CELL_CLASS}>{row.name || '—'}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>{row.quantity.toLocaleString()}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      {row.available_quantity?.toLocaleString() ?? '—'}
                    </td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>{row.avg_cost?.toFixed(3) ?? '—'}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>{row.market_price?.toFixed(3) ?? '—'}</td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      {row.market_value?.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) ?? '—'}
                    </td>
                    <td className={`${TABLE_CELL_CLASS} text-right`}>
                      <span className={(row.pnl ?? 0) < 0 ? 'text-rose-600' : 'text-emerald-600'}>
                        {row.pnl?.toFixed(2) ?? '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : loaded ? (
        <EmptyState
          className="mt-4"
          title={copy.noSnapshot}
          description={copy.unsupported}
          action={
            <Button variant="secondary" onClick={startManual}>
              {copy.manual}
            </Button>
          }
        />
      ) : null}
    </Card>
  );
};
