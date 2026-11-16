import sqlite3
from datetime import date

from personal.backtest.replay import replay_upstream
from personal.backtest.types import BacktestConfig
from personal.contracts.upstream_db import UpstreamDB
from personal.datahub.models import DailyBar
from personal.datahub.store import PersonalStore


def _prepare_upstream(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE analysis_history (
          id INTEGER PRIMARY KEY, code TEXT, name TEXT, report_type TEXT,
          sentiment_score INTEGER, operation_advice TEXT, trend_prediction TEXT,
          analysis_summary TEXT, raw_result TEXT, created_at TEXT,
          ideal_buy REAL, secondary_buy REAL, stop_loss REAL, take_profit REAL
        );
        CREATE TABLE portfolio_accounts (
          id INTEGER PRIMARY KEY, name TEXT, market TEXT, base_currency TEXT,
          is_active INTEGER, broker TEXT
        );
        CREATE TABLE portfolio_trades (
          id INTEGER PRIMARY KEY, account_id INTEGER, symbol TEXT,
          trade_date TEXT, side TEXT, quantity REAL, price REAL, fee REAL,
          tax REAL, currency TEXT, note TEXT
        );
        CREATE TABLE decision_signals (
          id INTEGER PRIMARY KEY, stock_code TEXT, market TEXT, action TEXT,
          created_at TEXT, score INTEGER, confidence REAL, entry_low REAL,
          entry_high REAL, stop_loss REAL, target_price REAL, horizon TEXT,
          reason TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO analysis_history
          (id, code, name, sentiment_score, operation_advice, created_at)
        VALUES (1, '600519', '贵州茅台', 70, '买入', '2026-01-05 18:00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO analysis_history
          (id, code, name, sentiment_score, operation_advice, created_at)
        VALUES (2, '600519', '贵州茅台', 30, '卖出', '2026-01-06 18:00:00')
        """
    )
    conn.commit()
    conn.close()


def _bar(day: int, open_price: float, close: float) -> DailyBar:
    return DailyBar(
        code="600519.SH",
        trade_date=date(2026, 1, day),
        open=open_price,
        high=max(open_price, close),
        low=min(open_price, close),
        close=close,
        volume=10_000,
        amount=close * 10_000,
        source="test",
    )


def test_replay_upstream_end_to_end(tmp_path):
    upstream_path = tmp_path / "upstream.db"
    _prepare_upstream(upstream_path)

    store = PersonalStore(tmp_path / "personal.db")
    store.upsert_bars(
        [
            _bar(5, 9.0, 9.5),
            _bar(6, 9.8, 10.2),
            _bar(7, 10.4, 10.8),
            _bar(8, 10.9, 11.2),
        ]
    )
    db = UpstreamDB(upstream_path)
    config = BacktestConfig(
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        initial_cash=100_000,
        max_positions=2,
        max_position_pct=0.5,
    )
    try:
        result, signals = replay_upstream(db, store, config)
        assert len(signals) == 2
        assert len(result.trades) == 2
        assert result.metrics["total_return"] > 0
    finally:
        db.close()
        store.close()
