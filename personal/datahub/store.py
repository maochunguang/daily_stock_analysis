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
    DailyBar,
    EtfSnapshot,
    FundNav,
    QualityIssue,
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
