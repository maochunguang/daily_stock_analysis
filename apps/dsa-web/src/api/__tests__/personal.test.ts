import { afterEach, describe, expect, it, vi } from 'vitest';
import { personalApi } from '../personal';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('personalApi account/plan endpoints', () => {
  it('sends plan_id when importing a statement', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ imported: 1, plan_id: 7, plan_linked: 1 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await personalApi.brokerImport({
      filename: 'deal.csv',
      content_b64: 'YQ==',
      plan_id: 7,
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toMatchObject({
      filename: 'deal.csv',
      plan_id: 7,
    });
  });

  it('uses the margin stocks endpoint mounted by the personal API', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ stocks: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await personalApi.marginStocks(30);

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      '/personal-api/api/margin/stocks?days=30',
    );
  });

  it('uses the index valuation endpoint for the deep-review card', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ rows: [], available: false, source: 'legulegu' }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await personalApi.indexValuation();

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      '/personal-api/api/market/index-valuation',
    );
  });

  it('uses the index valuation cross-check endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ rows: [], warnings: [], note: '' }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await personalApi.indexValuationCheck();

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      '/personal-api/api/market/index-valuation/check',
    );
  });

  it('builds journal outcome query params', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ rows: [], summary: {}, horizon: 20 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await personalApi.journalOutcomes({
      horizon: 60,
      days: 730,
      code: '600519',
      side: 'buy',
      limit: 100,
    });

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/journal/outcomes?');
    expect(String(url)).toContain('horizon=60');
    expect(String(url)).toContain('days=730');
    expect(String(url)).toContain('code=600519');
    expect(String(url)).toContain('side=buy');
  });

  it('formats FastAPI validation detail arrays', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: [{ loc: ['body', 'entry_low'], msg: 'must be positive' }] },
          422,
        ),
      ),
    );
    await expect(
      personalApi.tradePlanPreview({
        plan_date: null,
        valid_until: null,
        code: '600519',
        name: '',
        side: 'buy',
        entry_low: -1,
        entry_high: 10,
        stop_loss: 9,
        target_price: 12,
        risk_budget_pct: 1,
        risk_budget_amount: null,
        max_position_pct: 20,
        requested_quantity: null,
        account_snapshot_id: null,
        status: 'draft',
        thesis: '',
        catalyst: '',
        invalidation: '',
        horizon_days: null,
        analysis_id: null,
        decision_signal_id: null,
      }),
    ).rejects.toThrow('must be positive');
  });
});
