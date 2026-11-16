"""Read-only access to the upstream SQLite database.

This module is the only place that knows upstream table names and columns.
Personal business code must consume the typed models instead of raw SQL.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from .models import (
    AnalysisRecord,
    DecisionSignalRecord,
    PortfolioAccount,
    PortfolioTradeRecord,
)

REQUIRED_TABLES = {
    "analysis_history": {
        "id",
        "code",
        "raw_result",
        "created_at",
        "operation_advice",
        "sentiment_score",
    },
    "portfolio_accounts": {"id", "name", "market", "base_currency"},
    "portfolio_trades": {
        "account_id",
        "symbol",
        "trade_date",
        "side",
        "quantity",
        "price",
    },
    "decision_signals": {"id", "stock_code", "market", "action", "created_at"},
}


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _parse_date(value: Any) -> Optional[date]:
    parsed = _parse_datetime(value)
    return parsed.date() if parsed else None


def _parse_json(value: Any) -> Optional[dict[str, Any]]:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


class UpstreamDB:
    """Read-only adapter over the upstream SQLite database."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def available(self) -> bool:
        return self.path.is_file()

    def _connect(self) -> sqlite3.Connection:
        if not self.available:
            raise FileNotFoundError(f"upstream database not found: {self.path}")
        if self._conn is None:
            uri = f"file:{quote(str(self.path.resolve()), safe='/')}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def list_tables(self) -> list[str]:
        if not self.available:
            return []
        rows = self._connect().execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]

    def table_columns(self, table: str) -> set[str]:
        if not self.available:
            return set()
        rows = self._connect().execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}

    def table_exists(self, table: str) -> bool:
        return table in self.list_tables()

    def missing_contracts(self) -> list[str]:
        if not self.available:
            return [f"database missing: {self.path}"]
        missing: list[str] = []
        for table, columns in REQUIRED_TABLES.items():
            if not self.table_exists(table):
                missing.append(f"table missing: {table}")
                continue
            actual = self.table_columns(table)
            for column in sorted(columns - actual):
                missing.append(f"column missing: {table}.{column}")
        return missing

    # ------------------------------------------------------------------
    # Typed queries
    # ------------------------------------------------------------------
    def recent_analyses(
        self, code: Optional[str] = None, limit: int = 50
    ) -> list[AnalysisRecord]:
        if not self.available:
            return []
        sql = """
            SELECT id, code, name, report_type, sentiment_score,
                   operation_advice, trend_prediction, analysis_summary,
                   raw_result, created_at, ideal_buy, secondary_buy,
                   stop_loss, take_profit
            FROM analysis_history
        """
        params: list[Any] = []
        if code:
            sql += " WHERE code = ?"
            params.append(code)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        rows = self._connect().execute(sql, params).fetchall()
        return [
            AnalysisRecord(
                id=row["id"],
                code=row["code"],
                name=row["name"],
                report_type=row["report_type"],
                sentiment_score=row["sentiment_score"],
                operation_advice=row["operation_advice"],
                trend_prediction=row["trend_prediction"],
                analysis_summary=row["analysis_summary"],
                raw_result=_parse_json(row["raw_result"]),
                created_at=_parse_datetime(row["created_at"]),
                ideal_buy=row["ideal_buy"],
                secondary_buy=row["secondary_buy"],
                stop_loss=row["stop_loss"],
                take_profit=row["take_profit"],
            )
            for row in rows
        ]

    def portfolio_accounts(self) -> list[PortfolioAccount]:
        if not self.available:
            return []
        rows = self._connect().execute(
            """
            SELECT id, name, market, base_currency, is_active, broker
            FROM portfolio_accounts
            ORDER BY id
            """
        ).fetchall()
        return [
            PortfolioAccount(
                id=row["id"],
                name=row["name"],
                market=row["market"] or "cn",
                base_currency=row["base_currency"] or "CNY",
                is_active=bool(row["is_active"]),
                broker=row["broker"],
            )
            for row in rows
        ]

    def portfolio_trades(
        self, account_id: Optional[int] = None, limit: int = 200
    ) -> list[PortfolioTradeRecord]:
        if not self.available:
            return []
        sql = """
            SELECT id, account_id, symbol, trade_date, side, quantity,
                   price, fee, tax, currency, note
            FROM portfolio_trades
        """
        params: list[Any] = []
        if account_id is not None:
            sql += " WHERE account_id = ?"
            params.append(int(account_id))
        sql += " ORDER BY trade_date DESC, id DESC LIMIT ?"
        params.append(int(limit))
        rows = self._connect().execute(sql, params).fetchall()
        records: list[PortfolioTradeRecord] = []
        for row in rows:
            trade_date = _parse_date(row["trade_date"])
            if trade_date is None:
                continue
            records.append(
                PortfolioTradeRecord(
                    id=row["id"],
                    account_id=row["account_id"],
                    symbol=row["symbol"],
                    trade_date=trade_date,
                    side=row["side"],
                    quantity=float(row["quantity"]),
                    price=float(row["price"]),
                    fee=float(row["fee"] or 0.0),
                    tax=float(row["tax"] or 0.0),
                    currency=row["currency"] or "CNY",
                    note=row["note"],
                )
            )
        return records

    def recent_decision_signals(self, limit: int = 200) -> list[DecisionSignalRecord]:
        if not self.available:
            return []
        rows = self._connect().execute(
            """
            SELECT id, stock_code, market, action, created_at, score,
                   confidence, entry_low, entry_high, stop_loss,
                   target_price, horizon, reason
            FROM decision_signals
            ORDER BY created_at DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [
            DecisionSignalRecord(
                id=row["id"],
                stock_code=row["stock_code"],
                market=row["market"],
                action=row["action"],
                created_at=_parse_datetime(row["created_at"]),
                score=row["score"],
                confidence=row["confidence"],
                entry_low=row["entry_low"],
                entry_high=row["entry_high"],
                stop_loss=row["stop_loss"],
                target_price=row["target_price"],
                horizon=row["horizon"],
                reason=row["reason"],
            )
            for row in rows
        ]
