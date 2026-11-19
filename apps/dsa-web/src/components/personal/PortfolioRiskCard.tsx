import type React from 'react';
import { ShieldAlert, Wallet } from 'lucide-react';
import { Badge, Card, EmptyState, InlineAlert, StatCard } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { PortfolioRiskResponse } from '../../types/personal';

const TABLE_HEAD_CLASS =
  'border-b border-border/60 text-left text-xs uppercase tracking-[0.12em] text-secondary-text';
const TABLE_CELL_CLASS = 'border-b border-border/40 py-2 pr-4 text-sm text-foreground';

const COPY = {
  zh: {
    title: '组合风险',
    unavailable: '暂无组合风险',
    unavailableHint: '先在账本导入同花顺账户截图，再创建交易计划。',
    equity: '账户总资产',
    cash: '现金比例',
    concentration: 'Top1 / Top5',
    marketRisk: 'Beta / 年化波动',
    coverage: '行情覆盖',
    stale: '快照已过期',
    positions: '持仓权重与风险',
    code: '代码',
    name: '名称',
    weight: '权重',
    value: '市值',
    beta: 'Beta',
    volatility: '波动率',
    liquidity: '退出天数',
    correlations: '高相关持仓',
    warnings: '风险提示',
    asOf: '快照日期',
    hhi: 'HHI',
    noPositions: '快照没有持仓',
  },
  en: {
    title: 'Portfolio risk',
    unavailable: 'No portfolio risk',
    unavailableHint: 'Import a Tonghuashun account screenshot in the ledger first.',
    equity: 'Account equity',
    cash: 'Cash ratio',
    concentration: 'Top1 / Top5',
    marketRisk: 'Beta / volatility',
    coverage: 'Market-data coverage',
    stale: 'Snapshot is stale',
    positions: 'Position weights and risk',
    code: 'Code',
    name: 'Name',
    weight: 'Weight',
    value: 'Value',
    beta: 'Beta',
    volatility: 'Volatility',
    liquidity: 'Exit days',
    correlations: 'Highly correlated holdings',
    warnings: 'Risk notes',
    asOf: 'Snapshot date',
    hhi: 'HHI',
    noPositions: 'Snapshot has no positions',
  },
} as const;

function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '—' : `${value.toFixed(digits)}%`;
}

function money(value: number | null | undefined): string {
  return value === null || value === undefined
    ? '—'
    : value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

export const PortfolioRiskCard: React.FC<{ risk: PortfolioRiskResponse | null }> = ({ risk }) => {
  const { language } = useUiLanguage();
  const copy = COPY[language];

  if (!risk || !risk.available) {
    return (
      <Card title={copy.title} variant="bordered">
        <EmptyState
          title={copy.unavailable}
          description={risk?.reason || copy.unavailableHint}
          icon={<Wallet className="h-6 w-6" />}
        />
      </Card>
    );
  }

  return (
    <Card title={copy.title} variant="bordered">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge variant="info">
          {copy.asOf} {risk.as_of || '—'}
        </Badge>
        {risk.stale ? <Badge variant="warning">{copy.stale}</Badge> : null}
        <Badge variant="default">{copy.coverage} {pct(risk.market_data_coverage_pct, 0)}</Badge>
        {risk.account_alias ? <Badge variant="default">{risk.account_alias}</Badge> : null}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label={copy.equity} value={money(risk.equity)} hint={`HHI ${risk.hhi ?? '—'}`} />
        <StatCard
          label={copy.cash}
          value={pct(risk.cash_pct)}
          hint={`${copy.concentration}: ${pct(risk.top1_pct)} / ${pct(risk.top5_pct)}`}
          tone={(risk.cash_pct ?? 100) < (risk.limits?.min_cash_pct ?? 0) ? 'warning' : 'default'}
        />
        <StatCard
          label={copy.concentration}
          value={`${pct(risk.top1_pct)} / ${pct(risk.top5_pct)}`}
          hint={`${risk.position_count ?? 0} positions`}
          tone={
            (risk.top1_pct ?? 0) > (risk.limits?.max_single_pct ?? 100) ||
            (risk.top5_pct ?? 0) > (risk.limits?.max_top5_pct ?? 100)
              ? 'danger'
              : 'default'
          }
        />
        <StatCard
          label={copy.marketRisk}
          value={`${risk.beta?.toFixed(2) ?? '—'} / ${pct(risk.volatility_pct)}`}
          hint={`ETF ${pct(risk.etf_pct)} · Stock ${pct(risk.stock_pct)}`}
        />
      </div>

      {risk.warnings.length ? (
        <InlineAlert
          className="mt-3"
          variant="warning"
          title={copy.warnings}
          message={risk.warnings.join('；')}
        />
      ) : null}

      <div className="mt-4 overflow-x-auto">
        <p className="mb-2 text-sm font-medium text-foreground">{copy.positions}</p>
        {risk.positions.length === 0 ? (
          <p className="text-sm text-secondary-text">{copy.noPositions}</p>
        ) : (
          <table className="w-full min-w-[720px]">
            <thead>
              <tr className={TABLE_HEAD_CLASS}>
                <th className="py-2 pr-4">{copy.code}</th>
                <th className="py-2 pr-4">{copy.name}</th>
                <th className="py-2 pr-4 text-right">{copy.weight}</th>
                <th className="py-2 pr-4 text-right">{copy.value}</th>
                <th className="py-2 pr-4 text-right">{copy.beta}</th>
                <th className="py-2 pr-4 text-right">{copy.volatility}</th>
                <th className="py-2 text-right">{copy.liquidity}</th>
              </tr>
            </thead>
            <tbody>
              {risk.positions.slice(0, 12).map((row) => (
                <tr key={row.code}>
                  <td className={TABLE_CELL_CLASS}>
                    {row.code} {row.asset_type === 'etf' ? <Badge variant="info">ETF</Badge> : null}
                  </td>
                  <td className={TABLE_CELL_CLASS}>{row.name || '—'}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{pct(row.weight_pct, 2)}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{money(row.market_value)}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{row.beta?.toFixed(2) ?? '—'}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>{pct(row.volatility_pct)}</td>
                  <td className={`${TABLE_CELL_CLASS} text-right`}>
                    {row.liquidation_days?.toFixed(2) ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {risk.correlations?.length ? (
        <div className="mt-3">
          <p className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
            <ShieldAlert className="h-4 w-4 text-warning" />
            {copy.correlations}
          </p>
          <div className="flex flex-wrap gap-2">
            {risk.correlations.slice(0, 5).map((row) => (
              <Badge key={`${row.code_a}-${row.code_b}`} variant="warning">
                {row.code_a} / {row.code_b} {row.correlation.toFixed(2)}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  );
};
