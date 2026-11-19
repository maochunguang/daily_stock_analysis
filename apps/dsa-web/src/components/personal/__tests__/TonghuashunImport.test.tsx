import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { TonghuashunImport } from '../TonghuashunImport';

const { latest, confirm } = vi.hoisted(() => ({
  latest: vi.fn(),
  confirm: vi.fn(),
}));

vi.mock('../../../api/personal', () => ({
  personalApi: {
    accountSnapshotLatest: latest,
    accountSnapshotConfirm: confirm,
  },
}));

function renderPanel() {
  return render(
    <UiLanguageProvider>
      <TonghuashunImport />
    </UiLanguageProvider>,
  );
}

describe('TonghuashunImport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    latest.mockResolvedValue({ snapshot: null });
    confirm.mockResolvedValue({
      snapshot_id: 1,
      snapshot: {
        id: 1,
        account_alias: '同花顺',
        as_of: '2026-11-19',
        cash: 20000,
        available_cash: 20000,
        market_value: 80000,
        equity: 100000,
        source: 'ths_screenshot',
        source_file: '',
        content_hash: '',
        ocr_engine: 'manual',
        positions: [],
      },
      warnings: [],
    });
  });

  it('supports manual entry and confirms an editable snapshot', async () => {
    renderPanel();
    await waitFor(() => expect(latest).toHaveBeenCalled());
    fireEvent.click(screen.getAllByRole('button', { name: /Manual entry/ })[0]);

    fireEvent.change(screen.getByLabelText('Equity'), { target: { value: '100000' } });
    fireEvent.change(screen.getByLabelText('Cash'), { target: { value: '20000' } });
    fireEvent.change(screen.getByLabelText('Market value'), { target: { value: '80000' } });
    fireEvent.click(screen.getByRole('button', { name: /Confirm snapshot/ }));

    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(confirm.mock.calls[0][0]).toMatchObject({
      account_alias: '同花顺',
      equity: 100000,
      cash: 20000,
      market_value: 80000,
      positions: [],
      ocr_engine: 'manual',
    });
    expect(await screen.findByText(/Latest account snapshot/)).toBeTruthy();
  });

  it('shows the empty state when no snapshot exists', async () => {
    renderPanel();
    expect(await screen.findByText(/No account snapshot yet/)).toBeTruthy();
  });
});
