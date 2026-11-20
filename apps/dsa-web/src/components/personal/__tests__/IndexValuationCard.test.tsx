import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  IndexValuationCard,
  type ReviewCardProps,
} from '../ReviewCards';
import type {
  PersonalIndexValuationCheckResponse,
  PersonalIndexValuationResponse,
  PersonalIndexValuationWindow,
} from '../../../types/personal';

function windowSummary(
  label: string,
  samples: number,
  percentile: number | null,
): PersonalIndexValuationWindow {
  return {
    label,
    days: label === '1y' ? 365 : label === '3y' ? 1095 : 1825,
    start: '2021-11-19',
    samples,
    min_samples: 10,
    percentile,
    zone: percentile === null ? null : percentile <= 20 ? 'low' : 'mid',
    pe_min: 10,
    pe_median: 12,
    pe_max: 20,
  };
}

const valuation: PersonalIndexValuationResponse = {
  rows: [
    {
      code: '000300.SH',
      name: '沪深300',
      available: true,
      source: 'legulegu',
      as_of: '2026-11-19',
      stale_days: 0,
      sample_freq: 'weekly',
      pe_ttm: 12.69,
      pe_ttm_equal: 28.73,
      pe_static: 13.25,
      pe_ttm_median: 18,
      close: 3984.84,
      windows: {
        '1y': windowSummary('1y', 52, 10.2),
        '3y': windowSummary('3y', 156, 22.4),
        '5y': windowSummary('5y', 260, 31.7),
      },
    },
  ],
  source: 'legulegu',
  as_of: '2026-11-19',
  windows: ['1y', '3y', '5y'],
  available: true,
};

const check: PersonalIndexValuationCheckResponse = {
  checked_at: '2026-11-19T20:00:00',
  note: '官方源只提供当前值；口径差异不等于数据错误。',
  warnings: ['科创50: 本地 95.85 vs 官方 85.57，偏差 +12.0%'],
  rows: [
    {
      code: '000300.SH',
      name: '沪深300',
      status: 'ok',
      detail: '偏差在 5% 内，当前水平一致',
      legu_pe: 13.25,
      official_pe: 13.77,
      official_date: '2026-11-19',
      official_source: '中证指数',
      official_metric: '中证 PE1（总股本）',
      legu_metric: 'pe_static',
      legu_label: '静态 PE（总股本）',
      diff_pct: -3.8,
    },
    {
      code: '000688.SH',
      name: '科创50',
      status: 'warn',
      detail: '5%-15% 口径差异，结合权重/股本口径理解',
      legu_pe: 95.85,
      official_pe: 85.57,
      official_date: '2026-11-19',
      official_source: '中证指数',
      official_metric: '中证 PE1（总股本）',
      legu_metric: 'pe_static',
      legu_label: '静态 PE（总股本）',
      diff_pct: 12,
    },
  ],
};

const baseProps: ReviewCardProps = {
  breadth: [],
  futures: [],
  margin: [],
  limitUp: [],
  pcr: [],
  rank: [],
  flows: null,
  crowding: null,
  macro: null,
  composite: null,
  valuation: null,
  valuationCheck: null,
  valuationCheckBusy: false,
  valuationCheckError: '',
  onCheckValuation: vi.fn(),
  marginStocks: [],
  validation: null,
  busy: false,
  onRefreshMarket: vi.fn(),
  onValidate: vi.fn(),
};

describe('IndexValuationCard', () => {
  it('renders PE and percentile windows and refreshes the dataset', () => {
    const onRefreshMarket = vi.fn();
    render(
      <IndexValuationCard
        {...baseProps}
        valuation={valuation}
        onRefreshMarket={onRefreshMarket}
      />,
    );

    expect(screen.getAllByText('沪深300').length).toBeGreaterThan(0);
    expect(screen.getByText('12.69')).toBeTruthy();
    expect(screen.getByText('10.2%')).toBeTruthy();
    expect(screen.getByText('31.7%')).toBeTruthy();
    expect(screen.getByText('低估区')).toBeTruthy();
    expect(screen.getAllByText('（最高 63.4%）')).toHaveLength(3);

    fireEvent.click(screen.getByRole('button', { name: /更新/ }));
    expect(onRefreshMarket).toHaveBeenCalledWith('valuation');
  });

  it('renders official cross-check results and triggers a check', () => {
    const onCheckValuation = vi.fn();
    render(
      <IndexValuationCard
        {...baseProps}
        valuation={valuation}
        valuationCheck={check}
        onCheckValuation={onCheckValuation}
      />,
    );

    expect(screen.getByText('官方交叉校验')).toBeTruthy();
    expect(screen.getByText('-3.8%')).toBeTruthy();
    expect(screen.getByText('口径差异')).toBeTruthy();
    expect(screen.getByText(/科创50: 本地 95.85/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '交叉校验' }));
    expect(onCheckValuation).toHaveBeenCalledTimes(1);
  });

  it('shows an explicit empty state before the dataset is synced', () => {
    render(<IndexValuationCard {...baseProps} valuation={null} />);
    expect(screen.getByText(/暂无估值数据/)).toBeTruthy();
  });

  it('adapts the sample suffix and source chip to the daily Tushare feed', () => {
    const daily: PersonalIndexValuationResponse = {
      ...valuation,
      source: 'tushare',
      rows: [
        {
          ...valuation.rows[0],
          source: 'tushare',
          sample_freq: 'daily' as const,
          pe_ttm_equal: null,
          windows: {
            '1y': windowSummary('1y', 244, 10.2),
            '3y': windowSummary('3y', 732, 22.4),
            '5y': windowSummary('5y', 1215, 31.7),
          },
        },
      ],
    };
    render(<IndexValuationCard {...baseProps} valuation={daily} />);
    expect(screen.getByText('Tushare 日频')).toBeTruthy();
    expect(screen.getByText('244日')).toBeTruthy();
  });
});
