"""券商交割单导入（RM-12/RM-15）：解析 → 去重入库 → 持仓/成本核算 → 决策快照。

支持两种入口格式：

- **CSV/文本**（券商网页/客户端导出，GBK 或 UTF-8 编码自动探测，逗号/Tab 分隔）
- **XLSX**（openpyxl 可用时）

列名不固定，用**别名映射**解析（覆盖常见券商表头；未识别的表头会在
summary 里列出，可用 ``column_map={"原始列": "标准字段"}`` 强制指定）。

口径：

- ``side`` 归一为 buy / sell / dividend / interest / fee / other；
  数量≤0 的买入/卖出（配号、申购未成交、撤单）归为 other，不进持仓
- 成本采用**含费移动加权平均**；卖出实现盈亏 = 卖出净额 − 移动平均成本 × 数量
- 金额单位为元；数量单位为股（券商导出按手需先换算，V1 不做手数换算）
- 同一文件重复导入按 ``row_hash`` 幂等去重
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

from .decision import snapshot_json
from .models import BrokerPosition, BrokerTrade
from .store import PersonalStore

#: 标准字段 -> 认识的中文表头别名（按顺序尝试，先命中先占用）
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "trade_date": ("交易日期", "成交日期", "发生日期", "日期", "清算日期"),
    "code": ("证券代码", "股票代码", "代码", "证券代码(code)"),
    "name": ("证券名称", "股票名称", "证券简称", "名称"),
    "category": ("业务名称", "摘要", "操作", "交易类别", "业务标志", "方向", "买卖方向"),
    "quantity": ("成交数量", "成交数量(股)", "数量", "成交股数"),
    "price": ("成交价格", "成交均价", "成交价", "价格"),
    "amount": ("成交金额", "成交金额(元)", "金额", "发生金额"),
    "cash": ("清算金额", "发生金额", "资金余额", "发生资金", "资金变动"),
    "fees": ("手续费", "费用合计", "规费", "过户费", "印花税", "佣金", "其他费", "费用"),
}

BUY_KEYWORDS = ("买入", "申购", "认购", "配债", "配售", "买券")
SELL_KEYWORDS = ("卖出", "赎回", "卖券")
DIVIDEND_KEYWORDS = ("红利", "股息", "分红")
INTEREST_KEYWORDS = ("利息归本", "利息")
TRANSFER_KEYWORDS = ("划入", "划出", "转托管", "归本", "指定", "撤单", "配号", "中签")

CASH_ALIASES = ("清算金额", "发生金额", "资金余额", "发生资金", "资金变动")

_DATE_PATTERNS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S")
_NUMBER_STRIP = re.compile(r"[,%\s元]")


@dataclass
class ParseIssue:
    line_no: int
    reason: str
    raw: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"line_no": self.line_no, "reason": self.reason, "raw": self.raw[:80]}


@dataclass
class BrokerStatement:
    """Parsed statement: usable rows + skipped rows + header mapping."""

    trades: list[BrokerTrade] = field(default_factory=list)
    skipped: list[ParseIssue] = field(default_factory=list)
    column_map: dict[str, str] = field(default_factory=dict)
    unrecognized_headers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": len(self.trades),
            "skipped": [issue.as_dict() for issue in self.skipped[:20]],
            "skipped_total": len(self.skipped),
            "column_map": self.column_map,
            "unrecognized_headers": self.unrecognized_headers,
        }


@dataclass
class ImportSummary:
    filename: str
    imported: int = 0
    skipped_total: int = 0
    skipped: list[ParseIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    positions: list[BrokerPosition] = field(default_factory=list)
    journal_added: int = 0
    column_map: dict[str, str] = field(default_factory=dict)
    unrecognized_headers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "imported": self.imported,
            "skipped_total": self.skipped_total,
            "skipped": [issue.as_dict() for issue in self.skipped[:20]],
            "warnings": self.warnings,
            "positions": [position.__dict__ | _dates_iso(position) for position in self.positions],
            "journal_added": self.journal_added,
            "column_map": self.column_map,
            "unrecognized_headers": self.unrecognized_headers,
        }


def _dates_iso(position: BrokerPosition) -> dict[str, Any]:
    return {
        "first_trade_date": (
            position.first_trade_date.isoformat() if position.first_trade_date else None
        ),
        "last_trade_date": (
            position.last_trade_date.isoformat() if position.last_trade_date else None
        ),
    }


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------
def decode_statement(filename: str, content: bytes) -> str:
    """Decode CSV/text statement bytes; XLSX goes through openpyxl."""
    lower = (filename or "").lower()
    if lower.endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover
            raise ValueError("xlsx 支持需要 openpyxl") from exc
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        for row in sheet.iter_rows(values_only=True):
            writer.writerow(["" if value is None else str(value) for value in row])
        return buffer.getvalue()

    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def parse_statement(
    text: str,
    *,
    source_file: str = "",
    column_map: Mapping[str, str] | None = None,
) -> BrokerStatement:
    """Parse statement text into normalized trades."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return BrokerStatement()

    # 表头前常有「客户名称/账号」等说明行，分隔符取全体行中更常见的一个
    comma_total = sum(line.count(",") for line in lines)
    tab_total = sum(line.count("\t") for line in lines)
    delimiter = "\t" if tab_total > comma_total else ","
    table: list[list[str]] = []
    for row in csv.reader(lines, delimiter=delimiter):
        table.append([cell.strip() for cell in row])

    header_index, mapping, fee_columns = _find_header(table, column_map or {})
    if header_index is None:
        raise ValueError(
            "未识别表头：请确认列名，或用 column_map 指定（例如 "
            "{\"成交日期\": \"trade_date\", ...}）"
        )
    header = table[header_index]
    statement = BrokerStatement(column_map=dict(mapping))
    statement.unrecognized_headers = [
        cell
        for cell in header
        if cell and _alias_canonical(cell) == "" and cell not in set(mapping.values())
    ][:12]

    wanted = {name for name in ("trade_date", "code", "category") if name in mapping}
    if "trade_date" not in mapping or "code" not in mapping:
        raise ValueError("缺少必要的 日期/证券代码 列映射")

    for offset, row in enumerate(table[header_index + 1 :], start=header_index + 2):
        record = dict(zip(header, row))
        trade_date = _parse_date(record.get(mapping.get("trade_date", "")))
        raw_code = _clean_code(record.get(mapping.get("code", "")))
        if trade_date is None or not raw_code:
            if any(record.get(column) for column in record):
                statement.skipped.append(
                    ParseIssue(offset, "缺少日期或代码", ",".join(row))
                )
            continue
        category = (record.get(mapping.get("category", "")) or "").strip()
        quantity = _to_float(record.get(mapping.get("quantity", "")))
        price = _to_float(record.get(mapping.get("price", "")))
        amount = _to_float(record.get(mapping.get("amount", "")))
        cash = _to_float(record.get(mapping.get("cash", "")))
        fees = None
        fee_values = [
            value
            for column in fee_columns
            for value in [_to_float(record.get(column))]
            if value
        ]
        if fee_values:
            fees = sum(fee_values)

        side = classify_side(category, quantity, cash)
        if side in ("buy", "sell") and not quantity:
            # 配号/申购未成交/撤单等 0 数量行：保留记录，不进持仓
            side = "other"

        code = raw_code
        trade = BrokerTrade(
            trade_date=trade_date,
            code=code,
            side=side,
            name=(record.get(mapping.get("name", "")) or "").strip(),
            category=category,
            quantity=quantity,
            price=price,
            amount=amount,
            fees=fees,
            cash_delta=cash,
            source_file=source_file,
            line_no=offset,
            row_hash=_row_hash(source_file, offset, trade_date, code, side, quantity, price, amount, fees),
        )
        statement.trades.append(trade)
    return statement


def _find_header(
    table: Sequence[Sequence[str]], override: Mapping[str, str]
) -> tuple[int | None, dict[str, str], list[str]]:
    """Locate the header row; return (index, canonical->column, fee columns)."""
    best_index: int | None = None
    best_hits = 0
    for index, row in enumerate(table[:10]):
        hits = sum(1 for cell in row if _alias_canonical(cell))
        if hits > best_hits:
            best_index, best_hits = index, hits
    if best_index is None or best_hits < 2:
        return None, {}, []
    header = table[best_index]

    mapping: dict[str, str] = {}
    used: set[str] = set()
    # 1) explicit overrides win
    for raw_key, field_name in override.items():
        if field_name in COLUMN_ALIASES and raw_key in header:
            mapping[field_name] = raw_key
            used.add(raw_key)
    # 2) alias scan in canonical order (fees handled separately below)
    for field_name, aliases in COLUMN_ALIASES.items():
        if field_name == "fees" or field_name in mapping:
            continue
        for cell in header:
            if _alias_canonical(cell) == field_name and cell not in used:
                mapping[field_name] = cell
                used.add(cell)
                break
    # fee-like columns are summed: every fee column joins (手续费/印花税/过户费…)
    fee_columns = [
        cell for cell in header if cell not in used and _alias_canonical(cell) == "fees"
    ]
    if "fees" in mapping:  # explicit override narrows it to one column
        fee_columns = [mapping.pop("fees")]
    # cash(清算金额/发生金额) 通常与 amount(成交金额) 同义命中 "发生金额"，
    # 只有当它是独立列（amount 用了别的列）时才映射
    if "cash" not in mapping:
        for cell in header:
            if cell in used:
                continue
            if any(cell == alias or cell.startswith(alias) for alias in CASH_ALIASES):
                mapping["cash"] = cell
                used.add(cell)
                break
    return best_index, mapping, fee_columns


def _alias_canonical(cell: str) -> str:
    cell = (cell or "").strip()
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if cell == alias or cell.startswith(alias):
                return field_name
    return ""


def classify_side(category: str, quantity: float | None, cash: float | None) -> str:
    """业务名称 -> 规范方向；无业务名称时按资金变动方向兜底。"""
    text = (category or "").strip()
    if text:
        if any(keyword in text for keyword in DIVIDEND_KEYWORDS):
            return "dividend"
        if any(keyword in text for keyword in INTEREST_KEYWORDS) and "融资" not in text:
            return "interest"
        if any(keyword in text for keyword in TRANSFER_KEYWORDS) and not any(
            keyword in text for keyword in BUY_KEYWORDS + SELL_KEYWORDS
        ):
            return "other"
        if any(keyword in text for keyword in BUY_KEYWORDS):
            return "buy"
        if any(keyword in text for keyword in SELL_KEYWORDS):
            return "sell"
    if cash is not None and cash < 0:
        return "buy"
    if cash is not None and cash > 0:
        return "sell"
    return "other"


# ----------------------------------------------------------------------
# Positions
# ----------------------------------------------------------------------
def compute_positions(
    trades: Iterable[BrokerTrade],
) -> tuple[list[BrokerPosition], list[str]]:
    """Moving-average cost per code over the full trade history."""
    ordered = sorted(trades, key=lambda trade: (trade.trade_date, trade.line_no))
    buckets: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for trade in ordered:
        bucket = buckets.setdefault(
            trade.code,
            {
                "name": "",
                "quantity": 0.0,
                "cost_value": 0.0,
                "realized_pnl": 0.0,
                "dividend_cash": 0.0,
                "fees_total": 0.0,
                "buy_count": 0,
                "sell_count": 0,
                "first": None,
                "last": None,
            },
        )
        bucket["name"] = trade.name or bucket["name"]
        bucket["first"] = bucket["first"] or trade.trade_date
        bucket["last"] = trade.trade_date

        quantity = trade.quantity or 0.0
        fees = trade.fees or 0.0
        amount = trade.amount
        gross = abs(amount) if amount is not None else abs((trade.price or 0.0) * quantity)
        bucket["fees_total"] += fees

        if trade.side == "dividend":
            bucket["dividend_cash"] += gross or (trade.cash_delta or 0.0)
        elif trade.side == "fee":
            pass
        elif trade.side == "buy":
            bucket["quantity"] += quantity
            bucket["cost_value"] += gross + fees
            bucket["buy_count"] += 1
        elif trade.side == "sell":
            held = bucket["quantity"]
            if held <= 0:
                warnings.append(f"{trade.trade_date} {trade.code} 卖出 {quantity:g} 股但无持仓（跳过成本核算）")
                continue
            matched = min(quantity, held)
            avg_cost = bucket["cost_value"] / held
            proceeds = gross - fees
            bucket["realized_pnl"] += proceeds - avg_cost * matched
            if quantity > held:
                warnings.append(
                    f"{trade.trade_date} {trade.code} 卖出 {quantity:g} 股超过持仓 {held:g} 股，按 {held:g} 股核算"
                )
            bucket["quantity"] = max(0.0, held - quantity)
            bucket["cost_value"] = avg_cost * bucket["quantity"]
            bucket["sell_count"] += 1
        # interest / other rows only record fees

    positions: list[BrokerPosition] = []
    for code, bucket in sorted(buckets.items()):
        quantity = bucket["quantity"]
        positions.append(
            BrokerPosition(
                code=code,
                name=bucket["name"],
                quantity=quantity,
                avg_cost=round(bucket["cost_value"] / quantity, 4) if quantity else None,
                cost_value=round(bucket["cost_value"], 2) if quantity else None,
                realized_pnl=round(bucket["realized_pnl"], 2),
                dividend_cash=round(bucket["dividend_cash"], 2),
                fees_total=round(bucket["fees_total"], 2),
                buy_count=bucket["buy_count"],
                sell_count=bucket["sell_count"],
                first_trade_date=bucket["first"],
                last_trade_date=bucket["last"],
            )
        )
    return positions, warnings


# ----------------------------------------------------------------------
# Import pipeline
# ----------------------------------------------------------------------
def import_statement(
    store: PersonalStore,
    filename: str,
    content: bytes,
    *,
    column_map: Mapping[str, str] | None = None,
    with_journal: bool = True,
) -> ImportSummary:
    """Full import: parse -> upsert -> recompute positions -> journal snapshots."""
    text = decode_statement(filename, content)
    statement = parse_statement(text, source_file=filename, column_map=column_map)
    summary = ImportSummary(
        filename=filename,
        skipped_total=len(statement.skipped),
        skipped=statement.skipped,
        column_map=statement.column_map,
        unrecognized_headers=statement.unrecognized_headers,
    )
    if not statement.trades:
        summary.warnings.append("没有可导入的成交行")
        return summary

    summary.imported = store.upsert_broker_trades(statement.trades)

    all_trades = store.get_broker_trades()
    positions, warnings = compute_positions(all_trades)
    store.upsert_broker_positions(positions)
    summary.warnings.extend(warnings)
    summary.positions = [
        position for position in positions if position.quantity > 0 or position.realized_pnl
    ]

    if with_journal:
        for trade in statement.trades:
            if trade.side not in ("buy", "sell"):
                continue
            trade_id = _trade_id_by_hash(store, trade.row_hash)
            if trade_id is None or store.journal_has_broker_trade(trade_id):
                continue
            price = trade.price
            if price is None and trade.quantity and trade.amount:
                price = round(abs(trade.amount) / trade.quantity, 4)
            store.add_journal_entry(
                trade.trade_date,
                trade.code,
                trade.side,
                trade.quantity or 0.0,
                price or 0.0,
                abs(trade.amount or 0.0),
                reason=trade.category,
                source="broker",
                broker_trade_id=trade_id,
                snapshot=snapshot_json(store, trade.trade_date, trade.code),
            )
            summary.journal_added += 1
    return summary


def _trade_id_by_hash(store: PersonalStore, row_hash: str) -> int | None:
    row = store._conn.execute(
        "SELECT id FROM broker_trade WHERE row_hash = ?", (row_hash,)
    ).fetchone()
    return int(row["id"]) if row else None


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------
def _row_hash(*parts: Any) -> str:
    payload = "|".join("" if value is None else str(value) for value in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _parse_date(value) -> date | None:
    text = _clean_text(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    for pattern in _DATE_PATTERNS:
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.date()
        except ValueError:
            continue
    if len(digits) >= 8:
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    return None


def _clean_code(value) -> str:
    text = _clean_text(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:6]


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float(value) -> float | None:
    text = _NUMBER_STRIP.sub("", _clean_text(value))
    if not text or text in {"-", "--", "—"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number


__all__ = [
    "BrokerStatement",
    "ImportSummary",
    "classify_side",
    "compute_positions",
    "decode_statement",
    "import_statement",
    "parse_statement",
]
