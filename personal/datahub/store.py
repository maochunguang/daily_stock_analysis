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
    AdjustFactor,
    BondYield,
    DailyBar,
    EtfShare,
    EtfSnapshot,
    FundNav,
    FuturesRank,
    IndexFutures,
    LimitUpStats,
    MarginBalance,
    MarketBreadth,
    MarketTurnover,
    OptionPcr,
    QualityIssue,
    RestrictedRelease,
    SectorAmount,
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
  created_at TEXT NOT NULL
);
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
            "restricted_summary",
            "data_quality_event",
            "backtest_run",
            "trade_journal",
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
    ) -> int:
        with self._transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_journal
                  (trade_date, code, side, quantity, price, amount, reason,
                   analysis_id, decision_signal_id, order_id, stop_loss,
                   target_price, mistake_type, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    _now_iso(),
                ),
            )
            return int(cursor.lastrowid)


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
