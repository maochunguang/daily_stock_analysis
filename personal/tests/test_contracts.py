import sqlite3
from datetime import date

from personal.contracts.upstream_db import UpstreamDB


def _create_upstream_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE analysis_history (
          id INTEGER PRIMARY KEY,
          code TEXT,
          name TEXT,
          report_type TEXT,
          sentiment_score INTEGER,
          operation_advice TEXT,
          trend_prediction TEXT,
          analysis_summary TEXT,
          raw_result TEXT,
          created_at TEXT,
          ideal_buy REAL,
          secondary_buy REAL,
          stop_loss REAL,
          take_profit REAL
        );
        CREATE TABLE portfolio_accounts (
          id INTEGER PRIMARY KEY,
          name TEXT,
          market TEXT,
          base_currency TEXT,
          is_active INTEGER,
          broker TEXT
        );
        CREATE TABLE portfolio_trades (
          id INTEGER PRIMARY KEY,
          account_id INTEGER,
          symbol TEXT,
          trade_date TEXT,
          side TEXT,
          quantity REAL,
          price REAL,
          fee REAL,
          tax REAL,
          currency TEXT,
          note TEXT
        );
        CREATE TABLE decision_signals (
          id INTEGER PRIMARY KEY,
          stock_code TEXT,
          market TEXT,
          action TEXT,
          created_at TEXT,
          score INTEGER,
          confidence REAL,
          entry_low REAL,
          entry_high REAL,
          stop_loss REAL,
          target_price REAL,
          horizon TEXT,
          reason TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO analysis_history
          (id, code, name, sentiment_score, operation_advice, raw_result, created_at)
        VALUES (1, '600519', '贵州茅台', 70, '买入',
                '{"decision_type": "buy"}', '2026-11-12 18:00:00')
        """
    )
    conn.execute(
        "INSERT INTO portfolio_accounts VALUES (1, 'main', 'cn', 'CNY', 1, 'futu')"
    )
    conn.execute(
        """
        INSERT INTO portfolio_trades
          (id, account_id, symbol, trade_date, side, quantity, price, fee, tax, currency, note)
        VALUES (1, 1, '600519', '2026-11-10', 'buy', 100, 1500.0, 5.0, 0.0, 'CNY', '')
        """
    )
    conn.execute(
        """
        INSERT INTO decision_signals
          (id, stock_code, market, action, created_at, score, confidence)
        VALUES (1, '600519', 'cn', 'buy', '2026-11-12 18:00:00', 70, 0.8)
        """
    )
    conn.commit()
    conn.close()


def test_reads_upstream_contracts(tmp_path):
    path = tmp_path / "upstream.db"
    _create_upstream_db(path)
    db = UpstreamDB(path)
    try:
        assert db.available
        assert db.missing_contracts() == []
        analyses = db.recent_analyses(limit=10)
        assert len(analyses) == 1
        assert analyses[0].code == "600519"
        assert analyses[0].raw_result == {"decision_type": "buy"}
        assert analyses[0].created_at is not None

        accounts = db.portfolio_accounts()
        assert accounts[0].name == "main"
        trades = db.portfolio_trades()
        assert trades[0].trade_date == date(2026, 11, 10)
        signals = db.recent_decision_signals()
        assert signals[0].action == "buy"
    finally:
        db.close()


def test_missing_database_is_reported(tmp_path):
    db = UpstreamDB(tmp_path / "missing.db")
    assert not db.available
    assert db.recent_analyses() == []
    assert db.missing_contracts()
