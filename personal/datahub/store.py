"""SQLite storage for the personal data hub.

The personal database is intentionally separate from the upstream database.
Only this module knows the physical schema; business code uses the typed
repository methods.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

from .models import (
    AccountPositionSnapshot,
    AccountSnapshot,
    AdjustFactor,
    BondYield,
    BrokerPosition,
    BrokerTrade,
    DailyBar,
    EtfShare,
    EtfSnapshot,
    FundNav,
    FuturesRank,
    IndexFutures,
    IndexValuation,
    LimitUpStats,
    MarginBalance,
    MarginStockRow,
    MarketBreadth,
    MarketTurnover,
    OptionPcr,
    QualityIssue,
    RestrictedRelease,
    SectorAmount,
    TradePlan,
    TradingStatus,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS instrument (
  code TEXT PRIMARY KEY,
  name TEXT,
  market TEXT NOT NULL DEFAULT 'cn',
  asset_type TEXT NOT NULL DEFAULT 'stock',
  lot_size INTEGER NOT NULL DEFAULT 100,
  tick_size REAL NOT NULL DEFAULT 0.01,
  currency TEXT NOT NULL DEFAULT 'CNY',
  status TEXT NOT NULL DEFAULT 'active',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_bar (
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  amount REAL NOT NULL,
  source TEXT NOT NULL,
  quality TEXT NOT NULL DEFAULT 'ok',
  ingested_at TEXT NOT NULL,
  PRIMARY KEY (code, trade_date, source)
);
CREATE INDEX IF NOT EXISTS ix_daily_bar_date ON daily_bar(trade_date);
CREATE INDEX IF NOT EXISTS ix_daily_bar_code_date ON daily_bar(code, trade_date);

CREATE TABLE IF NOT EXISTS adjust_factor (
  code TEXT NOT NULL,
  ex_date TEXT NOT NULL,
  factor REAL NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  PRIMARY KEY (code, ex_date, source)
);

CREATE TABLE IF NOT EXISTS trading_calendar (
  trade_date TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trading_status (
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  is_suspended INTEGER NOT NULL DEFAULT 0,
  is_st INTEGER NOT NULL DEFAULT 0,
  limit_up REAL,
  limit_down REAL,
  is_limit_up INTEGER NOT NULL DEFAULT 0,
  is_limit_down INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL,
  PRIMARY KEY (code, trade_date)
);

CREATE TABLE IF NOT EXISTS fund_nav (
  code TEXT NOT NULL,
  nav_date TEXT NOT NULL,
  nav REAL,
  acc_nav REAL,
  adj_nav REAL,
  source TEXT NOT NULL,
  PRIMARY KEY (code, nav_date, source)
);

CREATE TABLE IF NOT EXISTS etf_snapshot (
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  iopv REAL,
  close REAL,
  premium_pct REAL,
  volume REAL,
  amount REAL,
  source TEXT NOT NULL,
  PRIMARY KEY (code, trade_date, source)
);

CREATE TABLE IF NOT EXISTS market_breadth (
  trade_date TEXT PRIMARY KEY,
  up_count INTEGER NOT NULL DEFAULT 0,
  down_count INTEGER NOT NULL DEFAULT 0,
  flat_count INTEGER NOT NULL DEFAULT 0,
  sample_count INTEGER NOT NULL DEFAULT 0,
  up_vol_yi REAL,
  down_vol_yi REAL,
  up_amount_yi REAL,
  down_amount_yi REAL,
  adv_ratio REAL,
  trin REAL,
  trin_amount REAL,
  trin_pct REAL,
  interpretation TEXT,
  band TEXT,
  index_close REAL,
  index_chg_pct REAL,
  index_pos REAL,
  divergence INTEGER NOT NULL DEFAULT 0,
  signal_tag TEXT,
  signal_detail TEXT,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_futures (
  trade_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  close REAL,
  volume REAL,
  open_interest REAL,
  oi_chg REAL,
  index_close REAL,
  basis REAL,
  basis_pct REAL,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (trade_date, symbol)
);

CREATE TABLE IF NOT EXISTS margin_balance (
  trade_date TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  scope TEXT NOT NULL,
  rzye REAL,
  rqye REAL,
  rzrqye REAL,
  rzye_buy REAL,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (trade_date, scope_type, scope)
);

CREATE TABLE IF NOT EXISTS sync_state (
  dataset TEXT PRIMARY KEY,
  last_run_at TEXT NOT NULL,
  last_ok_at TEXT,
  last_ok_date TEXT,
  rows INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS market_turnover (
  trade_date TEXT PRIMARY KEY,
  sse_amount REAL,
  szse_amount REAL,
  total_amount REAL
);

CREATE TABLE IF NOT EXISTS limit_up_stats (
  trade_date TEXT PRIMARY KEY,
  zt_count INTEGER NOT NULL DEFAULT 0,
  first_board INTEGER NOT NULL DEFAULT 0,
  streak_ge2 INTEGER NOT NULL DEFAULT 0,
  max_streak INTEGER NOT NULL DEFAULT 0,
  zb_count INTEGER NOT NULL DEFAULT 0,
  zb_rate REAL,
  prev_zt_mean REAL,
  prev_zt_up_ratio REAL
);

CREATE TABLE IF NOT EXISTS option_pcr (
  trade_date TEXT NOT NULL,
  underlying TEXT NOT NULL,
  call_vol REAL,
  put_vol REAL,
  pcr_vol REAL,
  call_oi REAL,
  put_oi REAL,
  pcr_oi REAL,
  PRIMARY KEY (trade_date, underlying)
);

CREATE TABLE IF NOT EXISTS futures_rank (
  trade_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  contracts INTEGER NOT NULL DEFAULT 0,
  top20_buy REAL,
  top20_sell REAL,
  net REAL,
  net_ratio REAL,
  PRIMARY KEY (trade_date, symbol)
);

CREATE TABLE IF NOT EXISTS sector_amount (
  trade_date TEXT NOT NULL,
  board TEXT NOT NULL,
  amount_yi REAL,
  share_pct REAL,
  pct_chg REAL,
  PRIMARY KEY (trade_date, board)
);

CREATE TABLE IF NOT EXISTS etf_share (
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  share_yi REAL,
  PRIMARY KEY (trade_date, code)
);

CREATE TABLE IF NOT EXISTS bond_yield (
  trade_date TEXT PRIMARY KEY,
  cn_2y REAL,
  cn_10y REAL,
  us_2y REAL,
  us_10y REAL,
  spread_2y REAL,
  spread_10y REAL
);

CREATE TABLE IF NOT EXISTS index_valuation (
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  pe_ttm REAL,
  pe_ttm_equal REAL,
  pe_static REAL,
  pe_ttm_median REAL,
  close REAL,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (code, trade_date, source)
);
CREATE INDEX IF NOT EXISTS idx_index_valuation_date
  ON index_valuation(trade_date);

CREATE TABLE IF NOT EXISTS restricted_summary (
  release_date TEXT PRIMARY KEY,
  company_count INTEGER NOT NULL DEFAULT 0,
  shares REAL,
  market_value_yi REAL
);

CREATE TABLE IF NOT EXISTS data_quality_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset TEXT NOT NULL,
  code TEXT,
  trade_date TEXT,
  rule TEXT NOT NULL,
  severity TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_run (
  run_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  start_date TEXT,
  end_date TEXT,
  config_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_trade (
  run_id TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  side TEXT NOT NULL,
  quantity REAL NOT NULL,
  price REAL NOT NULL,
  gross_amount REAL NOT NULL,
  fee REAL NOT NULL,
  realized_pnl REAL NOT NULL DEFAULT 0,
  reason TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, trade_date, code, side, quantity, price)
);

CREATE TABLE IF NOT EXISTS trade_journal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  side TEXT NOT NULL,
  quantity REAL NOT NULL,
  price REAL NOT NULL,
  amount REAL NOT NULL,
  reason TEXT,
  analysis_id INTEGER,
  decision_signal_id INTEGER,
  order_id TEXT,
  stop_loss REAL,
  target_price REAL,
  mistake_type TEXT,
  notes TEXT,
  plan_id INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker_trade (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  row_hash TEXT NOT NULL UNIQUE,
  source_file TEXT NOT NULL DEFAULT '',
  line_no INTEGER NOT NULL DEFAULT 0,
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  side TEXT NOT NULL,
  category TEXT,
  quantity REAL,
  price REAL,
  amount REAL,
  fees REAL,
  cash_delta REAL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_broker_trade_date ON broker_trade(trade_date);

CREATE TABLE IF NOT EXISTS broker_position (
  code TEXT PRIMARY KEY,
  name TEXT,
  quantity REAL NOT NULL DEFAULT 0,
  avg_cost REAL,
  cost_value REAL,
  realized_pnl REAL NOT NULL DEFAULT 0,
  dividend_cash REAL NOT NULL DEFAULT 0,
  fees_total REAL NOT NULL DEFAULT 0,
  buy_count INTEGER NOT NULL DEFAULT 0,
  sell_count INTEGER NOT NULL DEFAULT 0,
  first_trade_date TEXT,
  last_trade_date TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS margin_stock (
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  rzye REAL,
  rzye_buy REAL,
  rqye REAL,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (trade_date, code)
);

CREATE TABLE IF NOT EXISTS account_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_alias TEXT NOT NULL DEFAULT '同花顺',
  as_of TEXT NOT NULL,
  cash REAL,
  available_cash REAL,
  market_value REAL,
  equity REAL,
  source TEXT NOT NULL DEFAULT 'ths_screenshot',
  source_file TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL DEFAULT '',
  ocr_engine TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (account_alias, as_of)
);
CREATE INDEX IF NOT EXISTS idx_account_snapshot_date
  ON account_snapshot(as_of);

CREATE TABLE IF NOT EXISTS account_position_snapshot (
  snapshot_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  quantity REAL NOT NULL DEFAULT 0,
  available_quantity REAL,
  avg_cost REAL,
  market_price REAL,
  market_value REAL,
  pnl REAL,
  PRIMARY KEY (snapshot_id, code),
  FOREIGN KEY (snapshot_id) REFERENCES account_snapshot(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trade_plan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_date TEXT NOT NULL,
  valid_until TEXT,
  code TEXT NOT NULL,
  name TEXT,
  side TEXT NOT NULL,
  entry_low REAL NOT NULL,
  entry_high REAL NOT NULL,
  stop_loss REAL,
  target_price REAL,
  risk_budget_pct REAL,
  risk_budget_amount REAL,
  max_position_pct REAL,
  requested_quantity REAL,
  account_snapshot_id INTEGER,
  status TEXT NOT NULL DEFAULT 'draft',
  thesis TEXT,
  catalyst TEXT,
  invalidation TEXT,
  horizon_days INTEGER,
  analysis_id INTEGER,
  decision_signal_id INTEGER,
  preview_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (account_snapshot_id) REFERENCES account_snapshot(id)
);
CREATE INDEX IF NOT EXISTS idx_trade_plan_date
  ON trade_plan(plan_date, status);
CREATE INDEX IF NOT EXISTS idx_trade_plan_code
  ON trade_plan(code, side);
"""


_PK_COLUMNS: dict[str, tuple[str, ...]] = {
    "market_turnover": ("trade_date",),
    "limit_up_stats": ("trade_date",),
    "option_pcr": ("trade_date", "underlying"),
    "futures_rank": ("trade_date", "symbol"),
    "sector_amount": ("trade_date", "board"),
    "etf_share": ("trade_date", "code"),
    "bond_yield": ("trade_date",),
    "restricted_summary": ("release_date",),
}


def _range_query(
    table: str,
    date_column: str,
    start: Optional[date],
    end: Optional[date],
    limit: int,
    params: list[Any],
) -> str:
    conditions = []
    if start:
        conditions.append(f"{date_column} >= ?")
        params.append(start.isoformat())
    if end:
        conditions.append(f"{date_column} <= ?")
        params.append(end.isoformat())
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    if limit and limit > 0:
        return (
            f"SELECT * FROM (SELECT * FROM {table}"
            + where
            + f" ORDER BY {date_column} DESC LIMIT ?) ORDER BY {date_column}"
        )
    return f"SELECT * FROM {table}" + where + f" ORDER BY {date_column}"


class PersonalStore:
    """SQLite repository for personal data."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.initialize()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def initialize(self) -> None:
        with self._transaction() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Lightweight column migration for databases created earlier."""
        wanted = {
            "trade_journal": (
                ("source", "TEXT NOT NULL DEFAULT 'manual'"),
                ("snapshot", "TEXT"),
                ("broker_trade_id", "INTEGER"),
                ("plan_id", "INTEGER"),
            ),
        }
        for table, columns in wanted.items():
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue
            for column, ddl in columns:
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trade_journal_plan "
            "ON trade_journal(plan_id)"
        )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "PersonalStore":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Bars
    # ------------------------------------------------------------------
    def upsert_bars(self, bars: Iterable[DailyBar]) -> int:
        rows = [
            (*bar.to_row(), _now_iso())
            for bar in bars
        ]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO daily_bar
                  (code, trade_date, open, high, low, close, volume, amount,
                   source, quality, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, trade_date, source) DO UPDATE SET
                  open=excluded.open, high=excluded.high, low=excluded.low,
                  close=excluded.close, volume=excluded.volume,
                  amount=excluded.amount, quality=excluded.quality,
                  ingested_at=excluded.ingested_at
                """,
                rows,
            )
        return len(rows)

    def get_bars(
        self,
        code: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
        source: Optional[str] = None,
        preferred_sources: Optional[Sequence[str]] = None,
    ) -> list[DailyBar]:
        """Read bars from exactly one source.

        Multiple sources are kept in the table for cross-source checks. Reads
        must never mix them, otherwise a synthetic smoke-test row can be mixed
        with a real BaoStock row and produce nonsense prices.
        """

        base_params: list[Any] = [code]
        base_where = " WHERE code = ?"
        if start:
            base_where += " AND trade_date >= ?"
            base_params.append(start.isoformat())
        if end:
            base_where += " AND trade_date <= ?"
            base_params.append(end.isoformat())

        chosen = source
        if chosen is None:
            sources = self._conn.execute(
                f"""
                SELECT source, COUNT(*) AS rows, MAX(ingested_at) AS last_seen
                FROM daily_bar
                {base_where}
                GROUP BY source
                """,
                base_params,
            ).fetchall()
            if not sources:
                return []
            counts = {
                row["source"]: (int(row["rows"]), row["last_seen"] or "")
                for row in sources
            }
            preferred = [
                candidate
                for candidate in (preferred_sources or ())
                if candidate in counts
            ]
            if preferred:
                # Prefer the source with the best coverage inside the requested
                # range; priority order breaks ties. A short priority series
                # must not shadow a longer fallback series.
                chosen = max(preferred, key=lambda name: counts[name][0])
            if chosen is None:
                chosen = max(counts, key=lambda name: counts[name])

        sql = "SELECT * FROM daily_bar" + base_where
        params = list(base_params)
        sql += " AND source = ?"
        params.append(chosen)
        sql += " ORDER BY trade_date"
        rows = self._conn.execute(sql, params).fetchall()
        return [_bar_from_row(row) for row in rows]

    def latest_bar_date(self, code: str) -> Optional[date]:
        row = self._conn.execute(
            "SELECT MAX(trade_date) AS d FROM daily_bar WHERE code = ?", (code,)
        ).fetchone()
        return date.fromisoformat(row["d"]) if row and row["d"] else None

    def get_bar_dates(
        self, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[date]:
        """Distinct bar dates across all codes/sources (calendar fallback)."""

        sql = "SELECT DISTINCT trade_date FROM daily_bar"
        where: list[str] = []
        params: list[Any] = []
        if start:
            where.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            where.append("trade_date <= ?")
            params.append(end.isoformat())
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY trade_date"
        return [
            date.fromisoformat(row["trade_date"])
            for row in self._conn.execute(sql, params).fetchall()
        ]

    # ------------------------------------------------------------------
    # Trading calendar
    # ------------------------------------------------------------------
    def upsert_trading_calendar(
        self, dates: Iterable[date], source: str = "derived"
    ) -> int:
        now = _now_iso()
        rows = [(item.isoformat(), source, now) for item in dates]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO trading_calendar (trade_date, source, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(trade_date) DO UPDATE SET
                  source=excluded.source, updated_at=excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def get_trading_dates(
        self, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[date]:
        sql = "SELECT trade_date FROM trading_calendar"
        where: list[str] = []
        params: list[Any] = []
        if start:
            where.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            where.append("trade_date <= ?")
            params.append(end.isoformat())
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY trade_date"
        return [
            date.fromisoformat(row["trade_date"])
            for row in self._conn.execute(sql, params).fetchall()
        ]

    # ------------------------------------------------------------------
    # Adjustment factors
    # ------------------------------------------------------------------
    def upsert_adjust_factors(self, factors: Iterable[AdjustFactor]) -> int:
        rows = [factor.to_row() for factor in factors]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO adjust_factor (code, ex_date, factor, reason, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code, ex_date, source) DO UPDATE SET
                  factor=excluded.factor, reason=excluded.reason
                """,
                rows,
            )
        return len(rows)

    def get_adjust_factors(self, code: str) -> list[AdjustFactor]:
        rows = self._conn.execute(
            "SELECT * FROM adjust_factor WHERE code = ? ORDER BY ex_date",
            (code,),
        ).fetchall()
        return [
            AdjustFactor(
                code=row["code"],
                ex_date=date.fromisoformat(row["ex_date"]),
                factor=float(row["factor"]),
                reason=row["reason"] or "",
                source=row["source"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Trading status
    # ------------------------------------------------------------------
    def upsert_trading_status(self, statuses: Iterable[TradingStatus]) -> int:
        rows = [status.to_row() for status in statuses]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO trading_status
                  (code, trade_date, is_suspended, is_st, limit_up, limit_down,
                   is_limit_up, is_limit_down, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, trade_date) DO UPDATE SET
                  is_suspended=excluded.is_suspended, is_st=excluded.is_st,
                  limit_up=excluded.limit_up, limit_down=excluded.limit_down,
                  is_limit_up=excluded.is_limit_up,
                  is_limit_down=excluded.is_limit_down, source=excluded.source
                """,
                rows,
            )
        return len(rows)

    def get_trading_status(self, code: str, trade_date: date) -> Optional[TradingStatus]:
        row = self._conn.execute(
            "SELECT * FROM trading_status WHERE code = ? AND trade_date = ?",
            (code, trade_date.isoformat()),
        ).fetchone()
        return _status_from_row(row) if row else None

    def get_trading_statuses(
        self, code: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> dict[date, TradingStatus]:
        sql = "SELECT * FROM trading_status WHERE code = ?"
        params: list[Any] = [code]
        if start:
            sql += " AND trade_date >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND trade_date <= ?"
            params.append(end.isoformat())
        rows = self._conn.execute(sql, params).fetchall()
        return {date.fromisoformat(row["trade_date"]): _status_from_row(row) for row in rows}

    # ------------------------------------------------------------------
    # Funds / ETF
    # ------------------------------------------------------------------
    def upsert_fund_nav(self, navs: Iterable[FundNav]) -> int:
        rows = [nav.to_row() for nav in navs]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO fund_nav (code, nav_date, nav, acc_nav, adj_nav, source)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, nav_date, source) DO UPDATE SET
                  nav=excluded.nav, acc_nav=excluded.acc_nav, adj_nav=excluded.adj_nav
                """,
                rows,
            )
        return len(rows)

    def get_fund_nav(
        self, code: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[FundNav]:
        sql = "SELECT * FROM fund_nav WHERE code = ?"
        params: list[Any] = [code]
        if start:
            sql += " AND nav_date >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND nav_date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY nav_date"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            FundNav(
                code=row["code"],
                nav_date=date.fromisoformat(row["nav_date"]),
                nav=row["nav"],
                acc_nav=row["acc_nav"],
                adj_nav=row["adj_nav"],
                source=row["source"],
            )
            for row in rows
        ]

    def upsert_etf_snapshots(self, snapshots: Iterable[EtfSnapshot]) -> int:
        rows = [snapshot.to_row() for snapshot in snapshots]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO etf_snapshot
                  (code, trade_date, iopv, close, premium_pct, volume, amount, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, trade_date, source) DO UPDATE SET
                  iopv=excluded.iopv, close=excluded.close,
                  premium_pct=excluded.premium_pct, volume=excluded.volume,
                  amount=excluded.amount
                """,
                rows,
            )
        return len(rows)

    def upsert_market_breadth(self, rows: Iterable[MarketBreadth]) -> int:
        payloads = [row.to_row() for row in rows]
        if not payloads:
            return 0
        now = _now_iso()
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO market_breadth
                  (trade_date, up_count, down_count, flat_count, sample_count,
                   up_vol_yi, down_vol_yi, up_amount_yi, down_amount_yi,
                   adv_ratio, trin, trin_amount, trin_pct,
                   interpretation, band, index_close, index_chg_pct, index_pos,
                   divergence, signal_tag, signal_detail, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date) DO UPDATE SET
                  up_count=excluded.up_count, down_count=excluded.down_count,
                  flat_count=excluded.flat_count, sample_count=excluded.sample_count,
                  up_vol_yi=excluded.up_vol_yi, down_vol_yi=excluded.down_vol_yi,
                  up_amount_yi=excluded.up_amount_yi, down_amount_yi=excluded.down_amount_yi,
                  adv_ratio=excluded.adv_ratio, trin=excluded.trin,
                  trin_amount=excluded.trin_amount, trin_pct=excluded.trin_pct,
                  interpretation=excluded.interpretation, band=excluded.band,
                  index_close=excluded.index_close, index_chg_pct=excluded.index_chg_pct,
                  index_pos=excluded.index_pos, divergence=excluded.divergence,
                  signal_tag=excluded.signal_tag, signal_detail=excluded.signal_detail,
                  source=excluded.source, updated_at=excluded.updated_at
                """,
                [
                    (
                        payload[0], payload[1], payload[2], payload[3], payload[4],
                        payload[5], payload[6], payload[7], payload[8], payload[9],
                        payload[10], payload[11], payload[12], payload[13],
                        payload[14], payload[15], payload[16], payload[17],
                        payload[18], payload[19], payload[20], payload[21], now,
                    )
                    for payload in payloads
                ],
            )
        return len(payloads)

    def get_market_breadth(
        self, start: Optional[date] = None, end: Optional[date] = None, limit: int = 0
    ) -> list[MarketBreadth]:
        """Market breadth rows ordered from oldest to newest.

        ``limit`` (when positive) keeps the most recent N days.
        """
        conditions = []
        params: list[Any] = []
        if start:
            conditions.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("trade_date <= ?")
            params.append(end.isoformat())
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        if limit and limit > 0:
            sql = (
                "SELECT * FROM (SELECT * FROM market_breadth"
                + where
                + " ORDER BY trade_date DESC LIMIT ?) ORDER BY trade_date"
            )
            params.append(int(limit))
        else:
            sql = "SELECT * FROM market_breadth" + where + " ORDER BY trade_date"
        result = [
            MarketBreadth(
                trade_date=date.fromisoformat(row["trade_date"]),
                up_count=row["up_count"],
                down_count=row["down_count"],
                flat_count=row["flat_count"],
                sample_count=row["sample_count"],
                up_vol_yi=row["up_vol_yi"],
                down_vol_yi=row["down_vol_yi"],
                up_amount_yi=row["up_amount_yi"],
                down_amount_yi=row["down_amount_yi"],
                adv_ratio=row["adv_ratio"],
                trin=row["trin"],
                trin_amount=row["trin_amount"],
                trin_pct=row["trin_pct"],
                interpretation=row["interpretation"] or "",
                band=row["band"] or "",
                index_close=row["index_close"],
                index_chg_pct=row["index_chg_pct"],
                index_pos=row["index_pos"],
                divergence=row["divergence"],
                signal_tag=row["signal_tag"] or "",
                signal_detail=row["signal_detail"] or "",
                source=row["source"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]
        return result

    def upsert_index_futures(self, rows: Iterable[IndexFutures]) -> int:
        payloads = [row.to_row() for row in rows]
        if not payloads:
            return 0
        now = _now_iso()
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO index_futures
                  (trade_date, symbol, close, volume, open_interest, oi_chg,
                   index_close, basis, basis_pct, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, symbol) DO UPDATE SET
                  close=excluded.close, volume=excluded.volume,
                  open_interest=excluded.open_interest, oi_chg=excluded.oi_chg,
                  index_close=excluded.index_close, basis=excluded.basis,
                  basis_pct=excluded.basis_pct, source=excluded.source,
                  updated_at=excluded.updated_at
                """,
                [payload + (now,) for payload in payloads],
            )
        return len(payloads)

    def get_index_futures(
        self,
        start: Optional[date] = None,
        end: Optional[date] = None,
        symbols: Optional[Sequence[str]] = None,
        limit: int = 0,
    ) -> list[IndexFutures]:
        """Futures rows ordered oldest -> newest (latest N days when limit > 0)."""
        conditions = []
        params: list[Any] = []
        if start:
            conditions.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("trade_date <= ?")
            params.append(end.isoformat())
        if symbols:
            placeholders = ",".join("?" for _ in symbols)
            conditions.append(f"symbol IN ({placeholders})")
            params.extend(symbols)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        if limit and limit > 0:
            sql = (
                "SELECT * FROM (SELECT * FROM index_futures"
                + where
                + " ORDER BY trade_date DESC LIMIT ?) ORDER BY trade_date"
            )
            params.append(int(limit))
        else:
            sql = "SELECT * FROM index_futures" + where + " ORDER BY trade_date"
        result = [
            IndexFutures(
                trade_date=date.fromisoformat(row["trade_date"]),
                symbol=row["symbol"],
                close=row["close"],
                volume=row["volume"],
                open_interest=row["open_interest"],
                oi_chg=row["oi_chg"],
                index_close=row["index_close"],
                basis=row["basis"],
                basis_pct=row["basis_pct"],
                source=row["source"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]
        return result

    def upsert_index_valuations(self, rows: Iterable[IndexValuation]) -> int:
        payloads = [row.to_row() for row in rows]
        if not payloads:
            return 0
        now = _now_iso()
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO index_valuation
                  (code, trade_date, name, pe_ttm, pe_ttm_equal, pe_static,
                   pe_ttm_median, close, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, trade_date, source) DO UPDATE SET
                  name=excluded.name, pe_ttm=excluded.pe_ttm,
                  pe_ttm_equal=excluded.pe_ttm_equal,
                  pe_static=excluded.pe_static,
                  pe_ttm_median=excluded.pe_ttm_median,
                  close=excluded.close, updated_at=excluded.updated_at
                """,
                [payload + (now,) for payload in payloads],
            )
        return len(payloads)

    def replace_index_valuations(
        self,
        code: str,
        rows: Iterable[IndexValuation],
        *,
        source: str = "legulegu",
    ) -> int:
        """Replace one index's full history for a source.

        The upstream endpoint returns the full weekly series on every call, so
        replacing avoids keeping a stale daily point from an earlier sync in
        the same week (which would over-weight recent observations when
        computing percentiles).
        """

        payloads = []
        for row in rows:
            payload = list(row.to_row())
            payload[-1] = source
            payloads.append(tuple(payload))
        if not payloads:
            return 0
        now = _now_iso()
        with self._transaction() as conn:
            conn.execute(
                "DELETE FROM index_valuation WHERE code = ? AND source = ?",
                (code, source),
            )
            conn.executemany(
                """
                INSERT INTO index_valuation
                  (code, trade_date, name, pe_ttm, pe_ttm_equal, pe_static,
                   pe_ttm_median, close, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [payload + (now,) for payload in payloads],
            )
        return len(payloads)

    def get_index_valuations(
        self,
        code: Optional[str] = None,
        start: Optional[date] = None,
        end: Optional[date] = None,
        source: Optional[str] = None,
        limit: int = 0,
    ) -> list[IndexValuation]:
        conditions: list[str] = []
        params: list[Any] = []
        if code:
            conditions.append("code = ?")
            params.append(code)
        if start:
            conditions.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("trade_date <= ?")
            params.append(end.isoformat())
        if source:
            conditions.append("source = ?")
            params.append(source)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        if limit and limit > 0:
            sql = (
                "SELECT * FROM (SELECT * FROM index_valuation"
                + where
                + " ORDER BY trade_date DESC LIMIT ?) ORDER BY code, trade_date"
            )
            params.append(int(limit))
        else:
            sql = (
                "SELECT * FROM index_valuation"
                + where
                + " ORDER BY code, trade_date"
            )
        return [
            IndexValuation(
                code=row["code"],
                trade_date=date.fromisoformat(row["trade_date"]),
                name=row["name"] or "",
                pe_ttm=row["pe_ttm"],
                pe_ttm_equal=row["pe_ttm_equal"],
                pe_static=row["pe_static"],
                pe_ttm_median=row["pe_ttm_median"],
                close=row["close"],
                source=row["source"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def upsert_margin_balance(self, rows: Iterable[MarginBalance]) -> int:
        payloads = [row.to_row() for row in rows]
        if not payloads:
            return 0
        now = _now_iso()
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO margin_balance
                  (trade_date, scope_type, scope, rzye, rqye, rzrqye, rzye_buy,
                   source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, scope_type, scope) DO UPDATE SET
                  rzye=excluded.rzye, rqye=excluded.rqye, rzrqye=excluded.rzrqye,
                  rzye_buy=excluded.rzye_buy, source=excluded.source,
                  updated_at=excluded.updated_at
                """,
                [payload + (now,) for payload in payloads],
            )
        return len(payloads)

    def get_margin_balance(
        self,
        start: Optional[date] = None,
        end: Optional[date] = None,
        scope_type: Optional[str] = None,
        limit: int = 0,
    ) -> list[MarginBalance]:
        """Margin rows ordered oldest -> newest (latest N days when limit > 0)."""
        conditions = []
        params: list[Any] = []
        if start:
            conditions.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("trade_date <= ?")
            params.append(end.isoformat())
        if scope_type:
            conditions.append("scope_type = ?")
            params.append(scope_type)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        if limit and limit > 0:
            sql = (
                "SELECT * FROM (SELECT * FROM margin_balance"
                + where
                + " ORDER BY trade_date DESC LIMIT ?) ORDER BY trade_date"
            )
            params.append(int(limit))
        else:
            sql = "SELECT * FROM margin_balance" + where + " ORDER BY trade_date"
        result = [
            MarginBalance(
                trade_date=date.fromisoformat(row["trade_date"]),
                scope_type=row["scope_type"],
                scope=row["scope"],
                rzye=row["rzye"],
                rqye=row["rqye"],
                rzrqye=row["rzrqye"],
                rzye_buy=row["rzye_buy"],
                source=row["source"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]
        return result

    # ------------------------------------------------------------------
    # Market indicators (turnover / limit-up / PCR / rank / crowding / rates)
    # ------------------------------------------------------------------
    def _upsert_generic(self, table: str, columns: tuple[str, ...], rows: list[tuple]) -> int:
        if not rows:
            return 0
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{col}=excluded.{col}" for col in columns[1:] if col != "updated_at"
        )
        with self._transaction() as conn:
            conn.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT({', '.join(_PK_COLUMNS[table])}) DO UPDATE SET {updates}",
                rows,
            )
        return len(rows)

    def upsert_market_turnover(self, rows: Iterable[MarketTurnover]) -> int:
        return self._upsert_generic(
            "market_turnover",
            ("trade_date", "sse_amount", "szse_amount", "total_amount"),
            [row.to_row() for row in rows],
        )

    def get_market_turnover(
        self, start: Optional[date] = None, end: Optional[date] = None, limit: int = 0
    ) -> list[MarketTurnover]:
        params: list[Any] = []
        sql = _range_query("market_turnover", "trade_date", start, end, limit, params)
        if limit and limit > 0:
            params.append(int(limit))
        return [
            MarketTurnover(
                trade_date=date.fromisoformat(row["trade_date"]),
                sse_amount=row["sse_amount"],
                szse_amount=row["szse_amount"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def upsert_limit_up_stats(self, rows: Iterable[LimitUpStats]) -> int:
        return self._upsert_generic(
            "limit_up_stats",
            (
                "trade_date", "zt_count", "first_board", "streak_ge2", "max_streak",
                "zb_count", "zb_rate", "prev_zt_mean", "prev_zt_up_ratio",
            ),
            [row.to_row() for row in rows],
        )

    def get_limit_up_stats(
        self, start: Optional[date] = None, end: Optional[date] = None, limit: int =0
    ) -> list[LimitUpStats]:
        params: list[Any] = []
        sql = _range_query("limit_up_stats", "trade_date", start, end, limit, params)
        if limit and limit > 0:
            params.append(int(limit))
        return [
            LimitUpStats(
                trade_date=date.fromisoformat(row["trade_date"]),
                zt_count=row["zt_count"],
                first_board=row["first_board"],
                streak_ge2=row["streak_ge2"],
                max_streak=row["max_streak"],
                zb_count=row["zb_count"],
                zb_rate=row["zb_rate"],
                prev_zt_mean=row["prev_zt_mean"],
                prev_zt_up_ratio=row["prev_zt_up_ratio"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def upsert_option_pcr(self, rows: Iterable[OptionPcr]) -> int:
        return self._upsert_generic(
            "option_pcr",
            (
                "trade_date", "underlying", "call_vol", "put_vol", "pcr_vol",
                "call_oi", "put_oi", "pcr_oi",
            ),
            [row.to_row() for row in rows],
        )

    def get_option_pcr(
        self,
        start: Optional[date] = None,
        end: Optional[date] = None,
        underlying: Optional[str] = None,
        limit: int = 0,
    ) -> list[OptionPcr]:
        conditions = []
        params: list[Any] = []
        if start:
            conditions.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("trade_date <= ?")
            params.append(end.isoformat())
        if underlying:
            conditions.append("underlying = ?")
            params.append(underlying)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        if limit and limit > 0:
            sql = (
                "SELECT * FROM (SELECT * FROM option_pcr"
                + where
                + " ORDER BY trade_date DESC LIMIT ?) ORDER BY trade_date"
            )
            params.append(int(limit))
        else:
            sql = "SELECT * FROM option_pcr" + where + " ORDER BY trade_date"
        return [
            OptionPcr(
                trade_date=date.fromisoformat(row["trade_date"]),
                underlying=row["underlying"],
                call_vol=row["call_vol"],
                put_vol=row["put_vol"],
                pcr_vol=row["pcr_vol"],
                call_oi=row["call_oi"],
                put_oi=row["put_oi"],
                pcr_oi=row["pcr_oi"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def upsert_futures_rank(self, rows: Iterable[FuturesRank]) -> int:
        return self._upsert_generic(
            "futures_rank",
            (
                "trade_date", "symbol", "contracts", "top20_buy", "top20_sell",
                "net", "net_ratio",
            ),
            [row.to_row() for row in rows],
        )

    def get_futures_rank(
        self, start: Optional[date] = None, end: Optional[date] = None, limit: int = 0
    ) -> list[FuturesRank]:
        params: list[Any] = []
        sql = _range_query("futures_rank", "trade_date", start, end, limit, params)
        if limit and limit > 0:
            params.append(int(limit))
        return [
            FuturesRank(
                trade_date=date.fromisoformat(row["trade_date"]),
                symbol=row["symbol"],
                contracts=row["contracts"],
                top20_buy=row["top20_buy"],
                top20_sell=row["top20_sell"],
                net=row["net"],
                net_ratio=row["net_ratio"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def upsert_sector_amount(self, rows: Iterable[SectorAmount]) -> int:
        return self._upsert_generic(
            "sector_amount",
            ("trade_date", "board", "amount_yi", "share_pct", "pct_chg"),
            [row.to_row() for row in rows],
        )

    def get_sector_amounts(
        self, start: Optional[date] = None, end: Optional[date] = None, limit: int = 0
    ) -> list[SectorAmount]:
        params: list[Any] = []
        sql = _range_query("sector_amount", "trade_date", start, end, limit, params)
        if limit and limit > 0:
            params.append(int(limit))
        return [
            SectorAmount(
                trade_date=date.fromisoformat(row["trade_date"]),
                board=row["board"],
                amount_yi=row["amount_yi"],
                share_pct=row["share_pct"],
                pct_chg=row["pct_chg"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def upsert_etf_share(self, rows: Iterable[EtfShare]) -> int:
        return self._upsert_generic(
            "etf_share",
            ("trade_date", "code", "name", "share_yi"),
            [row.to_row() for row in rows],
        )

    def get_etf_share(
        self, start: Optional[date] = None, end: Optional[date] = None, limit: int = 0
    ) -> list[EtfShare]:
        params: list[Any] = []
        sql = _range_query("etf_share", "trade_date", start, end, limit, params)
        if limit and limit > 0:
            params.append(int(limit))
        return [
            EtfShare(
                trade_date=date.fromisoformat(row["trade_date"]),
                code=row["code"],
                name=row["name"] or "",
                share_yi=row["share_yi"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def upsert_bond_yield(self, rows: Iterable[BondYield]) -> int:
        return self._upsert_generic(
            "bond_yield",
            (
                "trade_date", "cn_2y", "cn_10y", "us_2y", "us_10y",
                "spread_2y", "spread_10y",
            ),
            [row.to_row() for row in rows],
        )

    def get_bond_yield(
        self, start: Optional[date] = None, end: Optional[date] = None, limit: int = 0
    ) -> list[BondYield]:
        params: list[Any] = []
        sql = _range_query("bond_yield", "trade_date", start, end, limit, params)
        if limit and limit > 0:
            params.append(int(limit))
        return [
            BondYield(
                trade_date=date.fromisoformat(row["trade_date"]),
                cn_2y=row["cn_2y"],
                cn_10y=row["cn_10y"],
                us_2y=row["us_2y"],
                us_10y=row["us_10y"],
                spread_2y=row["spread_2y"],
                spread_10y=row["spread_10y"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def upsert_restricted_release(self, rows: Iterable[RestrictedRelease]) -> int:
        return self._upsert_generic(
            "restricted_summary",
            ("release_date", "company_count", "shares", "market_value_yi"),
            [row.to_row() for row in rows],
        )

    def get_restricted_release(
        self, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[RestrictedRelease]:
        params: list[Any] = []
        sql = _range_query(
            "restricted_summary", "release_date", start, end, 0, params
        )
        return [
            RestrictedRelease(
                release_date=date.fromisoformat(row["release_date"]),
                company_count=row["company_count"],
                shares=row["shares"],
                market_value_yi=row["market_value_yi"],
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def record_sync_state(
        self,
        dataset: str,
        *,
        ok: bool,
        rows: int = 0,
        message: str = "",
        ok_date: Optional[date] = None,
    ) -> None:
        """Track freshness/failures per dataset for the Web console (RM-05)."""
        now = _now_iso()
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO sync_state (dataset, last_run_at, last_ok_at, last_ok_date, rows, last_error)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset) DO UPDATE SET
                  last_run_at=excluded.last_run_at,
                  last_ok_at=COALESCE(excluded.last_ok_at, sync_state.last_ok_at),
                  last_ok_date=COALESCE(excluded.last_ok_date, sync_state.last_ok_date),
                  rows=CASE WHEN excluded.last_ok_at IS NOT NULL
                            THEN excluded.rows ELSE sync_state.rows END,
                  last_error=excluded.last_error
                """,
                (
                    dataset,
                    now,
                    now if ok else None,
                    ok_date.isoformat() if ok_date else None,
                    int(rows),
                    "" if ok else message,
                ),
            )

    def get_sync_state(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM sync_state ORDER BY dataset"
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Quality
    # ------------------------------------------------------------------
    def record_quality_events(self, issues: Iterable[QualityIssue]) -> int:
        rows = [
            (
                issue.dataset,
                issue.code,
                issue.trade_date.isoformat() if issue.trade_date else None,
                issue.rule,
                issue.severity,
                issue.detail,
                _now_iso(),
            )
            for issue in issues
        ]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO data_quality_event
                  (dataset, code, trade_date, rule, severity, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def list_quality_events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM data_quality_event ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(row) for row in rows]

    def clear_quality_events(self, dataset_prefix: str) -> int:
        """Drop previous validation snapshots so daily runs do not pile up."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM data_quality_event WHERE dataset LIKE ?",
                (f"{dataset_prefix}%",),
            )
        return cursor.rowcount or 0

    # ------------------------------------------------------------------
    # Backtest / journal
    # ------------------------------------------------------------------
    def save_backtest_run(
        self,
        run_id: str,
        mode: str,
        start: Optional[date],
        end: Optional[date],
        config: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO backtest_run
                  (run_id, mode, start_date, end_date, config_json, metrics_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  metrics_json=excluded.metrics_json, config_json=excluded.config_json
                """,
                (
                    run_id,
                    mode,
                    start.isoformat() if start else None,
                    end.isoformat() if end else None,
                    json.dumps(config, ensure_ascii=False, default=str),
                    json.dumps(metrics, ensure_ascii=False, default=str),
                    _now_iso(),
                ),
            )

    def save_backtest_trades(self, run_id: str, trades: Iterable[Any]) -> int:
        rows = [
            (
                run_id,
                trade.trade_date.isoformat(),
                trade.code,
                trade.side,
                float(trade.quantity),
                float(trade.price),
                float(trade.gross_amount),
                float(trade.fee),
                float(trade.realized_pnl),
                trade.reason,
            )
            for trade in trades
        ]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO backtest_trade
                  (run_id, trade_date, code, side, quantity, price,
                   gross_amount, fee, realized_pnl, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def list_backtest_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM backtest_run ORDER BY created_at DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        """Return lightweight row counts for the Web console."""

        tables = (
            "daily_bar",
            "adjust_factor",
            "trading_calendar",
            "trading_status",
            "fund_nav",
            "etf_snapshot",
            "market_breadth",
            "index_futures",
            "margin_balance",
            "market_turnover",
            "limit_up_stats",
            "option_pcr",
            "futures_rank",
            "sector_amount",
            "etf_share",
            "bond_yield",
            "index_valuation",
            "restricted_summary",
            "data_quality_event",
            "backtest_run",
            "trade_journal",
            "broker_trade",
            "broker_position",
            "account_snapshot",
            "account_position_snapshot",
            "trade_plan",
        )
        counts = {
            table: int(
                self._conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            )
            for table in tables
        }
        distinct = self._conn.execute(
            "SELECT COUNT(DISTINCT code) AS codes, COUNT(DISTINCT source) AS sources FROM daily_bar"
        ).fetchone()
        counts["symbols"] = int(distinct["codes"])
        counts["sources"] = int(distinct["sources"])
        return counts

    def coverage(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT code, source, COUNT(*) AS rows,
                   MIN(trade_date) AS start_date, MAX(trade_date) AS end_date
            FROM daily_bar
            GROUP BY code, source
            ORDER BY code, source
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def add_journal_entry(
        self,
        trade_date: date,
        code: str,
        side: str,
        quantity: float,
        price: float,
        amount: float,
        reason: str = "",
        analysis_id: Optional[int] = None,
        decision_signal_id: Optional[int] = None,
        order_id: Optional[str] = None,
        stop_loss: Optional[float] = None,
        target_price: Optional[float] = None,
        mistake_type: Optional[str] = None,
        notes: Optional[str] = None,
        source: str = "manual",
        snapshot: Optional[str] = None,
        broker_trade_id: Optional[int] = None,
        plan_id: Optional[int] = None,
    ) -> int:
        with self._transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_journal
                  (trade_date, code, side, quantity, price, amount, reason,
                   analysis_id, decision_signal_id, order_id, stop_loss,
                   target_price, mistake_type, notes, source, snapshot,
                   broker_trade_id, plan_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_date.isoformat(),
                    code,
                    side,
                    quantity,
                    price,
                    amount,
                    reason,
                    analysis_id,
                    decision_signal_id,
                    order_id,
                    stop_loss,
                    target_price,
                    mistake_type,
                    notes,
                    source,
                    snapshot,
                    broker_trade_id,
                    plan_id,
                    _now_iso(),
                ),
            )
            return int(cursor.lastrowid)

    def journal_has_broker_trade(self, broker_trade_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM trade_journal WHERE broker_trade_id = ? LIMIT 1",
            (int(broker_trade_id),),
        ).fetchone()
        return row is not None

    def list_journal(
        self,
        *,
        limit: int = 100,
        start: Optional[date] = None,
        end: Optional[date] = None,
        code: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if start:
            conditions.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("trade_date <= ?")
            params.append(end.isoformat())
        if code:
            conditions.append("code = ?")
            params.append(code)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(int(limit))
        rows = self._conn.execute(
            "SELECT * FROM trade_journal" + where
            + " ORDER BY trade_date DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Broker statements (交割单)
    # ------------------------------------------------------------------
    def upsert_broker_trades(self, trades: Iterable[BrokerTrade]) -> int:
        rows = [trade.to_row() + (_now_iso(),) for trade in trades]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO broker_trade
                  (row_hash, source_file, line_no, trade_date, code, name,
                   side, category, quantity, price, amount, fees, cash_delta,
                   created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(row_hash) DO UPDATE SET
                  source_file=excluded.source_file,
                  line_no=excluded.line_no,
                  name=excluded.name,
                  category=excluded.category,
                  quantity=excluded.quantity,
                  price=excluded.price,
                  amount=excluded.amount,
                  fees=excluded.fees,
                  cash_delta=excluded.cash_delta
                """,
                rows,
            )
        return len(rows)

    def get_broker_trades(
        self,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        code: Optional[str] = None,
    ) -> list[BrokerTrade]:
        conditions: list[str] = []
        params: list[Any] = []
        if start:
            conditions.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("trade_date <= ?")
            params.append(end.isoformat())
        if code:
            conditions.append("code = ?")
            params.append(code)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            "SELECT * FROM broker_trade" + where
            + " ORDER BY trade_date, id",
            params,
        ).fetchall()
        return [
            BrokerTrade(
                trade_date=date.fromisoformat(row["trade_date"]),
                code=row["code"],
                side=row["side"],
                name=row["name"] or "",
                category=row["category"] or "",
                quantity=row["quantity"],
                price=row["price"],
                amount=row["amount"],
                fees=row["fees"],
                cash_delta=row["cash_delta"],
                source_file=row["source_file"] or "",
                line_no=row["line_no"] or 0,
                row_hash=row["row_hash"] or "",
            )
            for row in rows
        ]

    def broker_trade_ids(self) -> list[int]:
        return [
            int(row["id"])
            for row in self._conn.execute("SELECT id FROM broker_trade").fetchall()
        ]

    def upsert_broker_positions(
        self, positions: Iterable[BrokerPosition]
    ) -> int:
        now = _now_iso()
        rows = [
            (
                position.code,
                position.name,
                position.quantity,
                position.avg_cost,
                position.cost_value,
                position.realized_pnl,
                position.dividend_cash,
                position.fees_total,
                position.buy_count,
                position.sell_count,
                position.first_trade_date.isoformat()
                if position.first_trade_date
                else None,
                position.last_trade_date.isoformat()
                if position.last_trade_date
                else None,
                now,
            )
            for position in positions
        ]
        if not rows:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO broker_position
                  (code, name, quantity, avg_cost, cost_value, realized_pnl,
                   dividend_cash, fees_total, buy_count, sell_count,
                   first_trade_date, last_trade_date, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                  name=excluded.name,
                  quantity=excluded.quantity,
                  avg_cost=excluded.avg_cost,
                  cost_value=excluded.cost_value,
                  realized_pnl=excluded.realized_pnl,
                  dividend_cash=excluded.dividend_cash,
                  fees_total=excluded.fees_total,
                  buy_count=excluded.buy_count,
                  sell_count=excluded.sell_count,
                  first_trade_date=excluded.first_trade_date,
                  last_trade_date=excluded.last_trade_date,
                  updated_at=excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def get_broker_positions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM broker_position ORDER BY cost_value DESC, code"
        ).fetchall()
        return [dict(row) for row in rows]

    def broker_position_codes(self) -> list[str]:
        return [
            row["code"]
            for row in self._conn.execute(
                "SELECT code FROM broker_position WHERE quantity > 0 ORDER BY code"
            ).fetchall()
        ]

    # ------------------------------------------------------------------
    # Account snapshots (screenshot/manual observations)
    # ------------------------------------------------------------------
    def upsert_account_snapshot(self, snapshot: AccountSnapshot) -> int:
        """Create or replace one alias+date snapshot and all its positions."""

        now = _now_iso()
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO account_snapshot
                  (account_alias, as_of, cash, available_cash, market_value,
                   equity, source, source_file, content_hash, ocr_engine,
                   created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_alias, as_of) DO UPDATE SET
                  cash=excluded.cash,
                  available_cash=excluded.available_cash,
                  market_value=excluded.market_value,
                  equity=excluded.equity,
                  source=excluded.source,
                  source_file=excluded.source_file,
                  content_hash=excluded.content_hash,
                  ocr_engine=excluded.ocr_engine,
                  updated_at=excluded.updated_at
                """,
                (
                    snapshot.account_alias,
                    snapshot.as_of.isoformat(),
                    snapshot.cash,
                    snapshot.available_cash,
                    snapshot.market_value,
                    snapshot.equity,
                    snapshot.source,
                    snapshot.source_file,
                    snapshot.content_hash,
                    snapshot.ocr_engine,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM account_snapshot WHERE account_alias = ? AND as_of = ?",
                (snapshot.account_alias, snapshot.as_of.isoformat()),
            ).fetchone()
            if row is None:
                raise RuntimeError("account snapshot upsert did not return an id")
            snapshot_id = int(row["id"])
            conn.execute(
                "DELETE FROM account_position_snapshot WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            if snapshot.positions:
                conn.executemany(
                    """
                    INSERT INTO account_position_snapshot
                      (snapshot_id, code, name, quantity, available_quantity,
                       avg_cost, market_price, market_value, pnl)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            snapshot_id,
                            position.code,
                            position.name,
                            position.quantity,
                            position.available_quantity,
                            position.avg_cost,
                            position.market_price,
                            position.market_value,
                            position.pnl,
                        )
                        for position in snapshot.positions
                    ],
                )
        return snapshot_id

    def get_account_positions(
        self, snapshot_id: int
    ) -> list[AccountPositionSnapshot]:
        rows = self._conn.execute(
            """
            SELECT * FROM account_position_snapshot
            WHERE snapshot_id = ?
            ORDER BY COALESCE(market_value, 0) DESC, code
            """,
            (int(snapshot_id),),
        ).fetchall()
        return [
            AccountPositionSnapshot(
                code=row["code"],
                name=row["name"] or "",
                quantity=float(row["quantity"] or 0.0),
                available_quantity=row["available_quantity"],
                avg_cost=row["avg_cost"],
                market_price=row["market_price"],
                market_value=row["market_value"],
                pnl=row["pnl"],
            )
            for row in rows
        ]

    def get_latest_account_snapshot(
        self,
        *,
        account_alias: Optional[str] = None,
        include_positions: bool = True,
    ) -> Optional[dict[str, Any]]:
        conditions = ""
        params: list[Any] = []
        if account_alias:
            conditions = " WHERE account_alias = ?"
            params.append(account_alias)
        row = self._conn.execute(
            "SELECT * FROM account_snapshot"
            + conditions
            + " ORDER BY as_of DESC, id DESC LIMIT 1",
            params,
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        if include_positions:
            payload["positions"] = self.get_account_positions(payload["id"])
        return payload

    def get_account_snapshot(
        self, snapshot_id: int, *, include_positions: bool = True
    ) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM account_snapshot WHERE id = ?", (int(snapshot_id),)
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        if include_positions:
            payload["positions"] = self.get_account_positions(payload["id"])
        return payload

    def account_position_codes(
        self, *, account_alias: Optional[str] = None
    ) -> list[str]:
        """Codes in the latest snapshot, for per-stock margin coverage."""

        snapshot = self.get_latest_account_snapshot(
            account_alias=account_alias, include_positions=True
        )
        if snapshot is None:
            return []
        return sorted(
            {
                position.code
                for position in snapshot.get("positions", [])
                if position.quantity > 0
            }
        )

    def list_account_snapshots(
        self, *, limit: int = 20, account_alias: Optional[str] = None
    ) -> list[dict[str, Any]]:
        conditions = ""
        params: list[Any] = []
        if account_alias:
            conditions = " WHERE s.account_alias = ?"
            params.append(account_alias)
        params.append(int(limit))
        rows = self._conn.execute(
            """
            SELECT s.*, COUNT(p.code) AS position_count
            FROM account_snapshot s
            LEFT JOIN account_position_snapshot p ON p.snapshot_id = s.id
            """
            + conditions
            + " GROUP BY s.id ORDER BY s.as_of DESC, s.id DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Trade plans
    # ------------------------------------------------------------------
    def create_trade_plan(self, plan: TradePlan) -> int:
        now = _now_iso()
        with self._transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_plan
                  (plan_date, valid_until, code, name, side, entry_low,
                   entry_high, stop_loss, target_price, risk_budget_pct,
                   risk_budget_amount, max_position_pct, requested_quantity,
                   account_snapshot_id, status, thesis, catalyst, invalidation,
                   horizon_days, analysis_id, decision_signal_id, preview_json,
                   created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _trade_plan_values(plan) + (now, now),
            )
            return int(cursor.lastrowid)

    def update_trade_plan(self, plan_id: int, plan: TradePlan) -> bool:
        with self._transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE trade_plan SET
                  plan_date=?, valid_until=?, code=?, name=?, side=?,
                  entry_low=?, entry_high=?, stop_loss=?, target_price=?,
                  risk_budget_pct=?, risk_budget_amount=?, max_position_pct=?,
                  requested_quantity=?, account_snapshot_id=?, status=?,
                  thesis=?, catalyst=?, invalidation=?, horizon_days=?,
                  analysis_id=?, decision_signal_id=?, preview_json=?,
                  updated_at=?
                WHERE id=?
                """,
                _trade_plan_values(plan) + (_now_iso(), int(plan_id)),
            )
            return cursor.rowcount > 0

    def update_trade_plan_status(self, plan_id: int, status: str) -> bool:
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE trade_plan SET status=?, updated_at=? WHERE id=?",
                (status, _now_iso(), int(plan_id)),
            )
            return cursor.rowcount > 0

    def get_trade_plan(self, plan_id: int) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM trade_plan WHERE id = ?", (int(plan_id),)
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload.update(self._plan_progress(int(plan_id)))
        return payload

    def list_trade_plans(
        self, *, status: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        conditions = ""
        params: list[Any] = []
        if status:
            conditions = " WHERE status = ?"
            params.append(status)
        params.append(int(limit))
        rows = self._conn.execute(
            "SELECT * FROM trade_plan"
            + conditions
            + " ORDER BY plan_date DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
        plans: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload.update(self._plan_progress(int(payload["id"])))
            plans.append(payload)
        return plans

    def _plan_progress(self, plan_id: int) -> dict[str, Any]:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS fill_count,
                   COALESCE(SUM(quantity), 0) AS filled_quantity,
                   COALESCE(SUM(ABS(amount)), 0) AS filled_amount,
                   MAX(trade_date) AS last_fill_date
            FROM trade_journal WHERE plan_id = ?
            """,
            (int(plan_id),),
        ).fetchone()
        quantity = float(row["filled_quantity"] or 0.0)
        amount = float(row["filled_amount"] or 0.0)
        return {
            "fill_count": int(row["fill_count"] or 0),
            "filled_quantity": quantity,
            "filled_amount": amount,
            "fill_vwap": (amount / quantity) if quantity > 0 else None,
            "last_fill_date": row["last_fill_date"],
        }

    # ------------------------------------------------------------------
    # Per-stock margin (持仓股两融)
    # ------------------------------------------------------------------
    def upsert_margin_stock(self, rows: Iterable[MarginStockRow]) -> int:
        now = _now_iso()
        values = [row.to_row() + (now,) for row in rows]
        if not values:
            return 0
        with self._transaction() as conn:
            conn.executemany(
                """
                INSERT INTO margin_stock
                  (trade_date, code, name, rzye, rzye_buy, rqye, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, code) DO UPDATE SET
                  name=excluded.name,
                  rzye=excluded.rzye,
                  rzye_buy=excluded.rzye_buy,
                  rqye=excluded.rqye,
                  source=excluded.source,
                  updated_at=excluded.updated_at
                """,
                values,
            )
        return len(values)

    def margin_stock_codes(self) -> list[str]:
        """Codes already present in per-stock margin history.

        They are included in later margin syncs so SSE rows written before the
        ``securityAbbr`` name fix can be refreshed even if the code was
        dropped from the current watchlist.
        """

        return [
            row["code"]
            for row in self._conn.execute(
                "SELECT DISTINCT code FROM margin_stock ORDER BY code"
            ).fetchall()
        ]

    def get_margin_stock(
        self,
        *,
        code: Optional[str] = None,
        start: Optional[date] = None,
        end: Optional[date] = None,
        limit: int = 0,
    ) -> list[MarginStockRow]:
        conditions: list[str] = []
        params: list[Any] = []
        if start:
            conditions.append("trade_date >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("trade_date <= ?")
            params.append(end.isoformat())
        if code:
            conditions.append("code = ?")
            params.append(code)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        if limit and limit > 0:
            sql = (
                "SELECT * FROM (SELECT * FROM margin_stock" + where
                + " ORDER BY trade_date DESC LIMIT ?) ORDER BY trade_date"
            )
            params.append(int(limit))
        else:
            sql = "SELECT * FROM margin_stock" + where + " ORDER BY trade_date"
        return [
            MarginStockRow(
                trade_date=date.fromisoformat(row["trade_date"]),
                code=row["code"],
                name=row["name"] or "",
                rzye=row["rzye"],
                rzye_buy=row["rzye_buy"],
                rqye=row["rqye"],
                source=row["source"] or "",
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]


def _trade_plan_values(plan: TradePlan) -> tuple[Any, ...]:
    return (
        plan.plan_date.isoformat(),
        plan.valid_until.isoformat() if plan.valid_until else None,
        plan.code,
        plan.name,
        plan.side,
        plan.entry_low,
        plan.entry_high,
        plan.stop_loss,
        plan.target_price,
        plan.risk_budget_pct,
        plan.risk_budget_amount,
        plan.max_position_pct,
        plan.requested_quantity,
        plan.account_snapshot_id,
        plan.status,
        plan.thesis,
        plan.catalyst,
        plan.invalidation,
        plan.horizon_days,
        plan.analysis_id,
        plan.decision_signal_id,
        plan.preview_json,
    )


def _bar_from_row(row: sqlite3.Row) -> DailyBar:
    return DailyBar(
        code=row["code"],
        trade_date=date.fromisoformat(row["trade_date"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        amount=float(row["amount"]),
        source=row["source"],
        quality=row["quality"],
    )


def _status_from_row(row: sqlite3.Row) -> TradingStatus:
    return TradingStatus(
        code=row["code"],
        trade_date=date.fromisoformat(row["trade_date"]),
        is_suspended=bool(row["is_suspended"]),
        is_st=bool(row["is_st"]),
        limit_up=row["limit_up"],
        limit_down=row["limit_down"],
        is_limit_up=bool(row["is_limit_up"]),
        is_limit_down=bool(row["is_limit_down"]),
        source=row["source"],
    )


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")
