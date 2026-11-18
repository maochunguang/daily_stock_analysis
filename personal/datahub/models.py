"""Canonical data models for the personal data hub."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DailyBar:
    code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    source: str = "unknown"
    quality: str = "ok"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.trade_date.isoformat(),
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.amount,
            self.source,
            self.quality,
        )


@dataclass(frozen=True)
class AdjustFactor:
    code: str
    ex_date: date
    factor: float
    reason: str = ""
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.ex_date.isoformat(),
            self.factor,
            self.reason,
            self.source,
        )


@dataclass(frozen=True)
class TradingStatus:
    code: str
    trade_date: date
    is_suspended: bool = False
    is_st: bool = False
    limit_up: float | None = None
    limit_down: float | None = None
    is_limit_up: bool = False
    is_limit_down: bool = False
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.trade_date.isoformat(),
            int(self.is_suspended),
            int(self.is_st),
            self.limit_up,
            self.limit_down,
            int(self.is_limit_up),
            int(self.is_limit_down),
            self.source,
        )


@dataclass(frozen=True)
class FundNav:
    code: str
    nav_date: date
    nav: float | None = None
    acc_nav: float | None = None
    adj_nav: float | None = None
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.nav_date.isoformat(),
            self.nav,
            self.acc_nav,
            self.adj_nav,
            self.source,
        )


@dataclass(frozen=True)
class EtfSnapshot:
    code: str
    trade_date: date
    iopv: float | None = None
    close: float | None = None
    premium_pct: float | None = None
    volume: float | None = None
    amount: float | None = None
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.trade_date.isoformat(),
            self.iopv,
            self.close,
            self.premium_pct,
            self.volume,
            self.amount,
            self.source,
        )


@dataclass(frozen=True)
class MarketBreadth:
    """One day of market-wide breadth aggregates (TRIN / Arms Index).

    Volume columns are in 亿股 and amount columns in 亿元 so every source
    (imported snapshots, full-market daily pulls) stores the same unit.
    """

    trade_date: date
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    sample_count: int = 0
    up_vol_yi: float | None = None
    down_vol_yi: float | None = None
    up_amount_yi: float | None = None
    down_amount_yi: float | None = None
    adv_ratio: float | None = None
    trin: float | None = None
    trin_amount: float | None = None
    trin_pct: float | None = None
    interpretation: str = ""
    band: str = ""
    index_close: float | None = None
    index_chg_pct: float | None = None
    index_pos: float | None = None
    divergence: int = 0
    signal_tag: str = ""
    signal_detail: str = ""
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.up_count,
            self.down_count,
            self.flat_count,
            self.sample_count,
            self.up_vol_yi,
            self.down_vol_yi,
            self.up_amount_yi,
            self.down_amount_yi,
            self.adv_ratio,
            self.trin,
            self.trin_amount,
            self.trin_pct,
            self.interpretation,
            self.band,
            self.index_close,
            self.index_chg_pct,
            self.index_pos,
            self.divergence,
            self.signal_tag,
            self.signal_detail,
            self.source,
        )


@dataclass(frozen=True)
class IndexFutures:
    """One day of a CFFEX index-futures main contract (IF/IH/IC/IM).

    ``basis``/``basis_pct`` compare the futures close with the spot index
    close; deep discount (贴水) signals hedging/short pressure.
    """

    trade_date: date
    symbol: str
    close: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    oi_chg: float | None = None
    index_close: float | None = None
    basis: float | None = None
    basis_pct: float | None = None
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.symbol,
            self.close,
            self.volume,
            self.open_interest,
            self.oi_chg,
            self.index_close,
            self.basis,
            self.basis_pct,
            self.source,
        )


@dataclass(frozen=True)
class MarginBalance:
    """One day of margin-financing balances for a market or board scope.

    All monetary values are in yuan (元). ``scope_type`` is ``market``
    (沪市/深市/总计) or ``board`` (沪主板/科创板/深主板/创业板, stock
    instruments only — ETFs/bonds are excluded from board rows).
    """

    trade_date: date
    scope_type: str
    scope: str
    rzye: float | None = None
    rqye: float | None = None
    rzrqye: float | None = None
    rzye_buy: float | None = None
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.scope_type,
            self.scope,
            self.rzye,
            self.rqye,
            self.rzrqye,
            self.rzye_buy,
            self.source,
        )


@dataclass(frozen=True)
class QualityIssue:
    dataset: str
    rule: str
    severity: str
    code: str | None = None
    trade_date: date | None = None
    detail: str = ""

@dataclass(frozen=True)
class MarketTurnover:
    """Exchange daily turnover (股票标的, yuan) — denominator for margin ratio."""

    trade_date: date
    sse_amount: float | None = None
    szse_amount: float | None = None

    @property
    def total_amount(self) -> float | None:
        if self.sse_amount is None or self.szse_amount is None:
            return None
        return self.sse_amount + self.szse_amount

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.sse_amount,
            self.szse_amount,
            self.total_amount,
        )


@dataclass(frozen=True)
class LimitUpStats:
    """Daily limit-up structure: ladder height, broken boards, carry trade."""

    trade_date: date
    zt_count: int = 0
    first_board: int = 0
    streak_ge2: int = 0
    max_streak: int = 0
    zb_count: int = 0
    zb_rate: float | None = None
    prev_zt_mean: float | None = None
    prev_zt_up_ratio: float | None = None

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.zt_count,
            self.first_board,
            self.streak_ge2,
            self.max_streak,
            self.zb_count,
            self.zb_rate,
            self.prev_zt_mean,
            self.prev_zt_up_ratio,
        )


@dataclass(frozen=True)
class OptionPcr:
    """ETF-option put/call aggregates for one underlying (volume + OI)."""

    trade_date: date
    underlying: str
    call_vol: float | None = None
    put_vol: float | None = None
    pcr_vol: float | None = None
    call_oi: float | None = None
    put_oi: float | None = None
    pcr_oi: float | None = None

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.underlying,
            self.call_vol,
            self.put_vol,
            self.pcr_vol,
            self.call_oi,
            self.put_oi,
            self.pcr_oi,
        )


@dataclass(frozen=True)
class FuturesRank:
    """CFFEX top-20 member long/short open interest per product."""

    trade_date: date
    symbol: str
    contracts: int = 0
    top20_buy: float | None = None
    top20_sell: float | None = None
    net: float | None = None
    net_ratio: float | None = None

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.symbol,
            self.contracts,
            self.top20_buy,
            self.top20_sell,
            self.net,
            self.net_ratio,
        )


@dataclass(frozen=True)
class SectorAmount:
    """One industry board's turnover for crowding percentile."""

    trade_date: date
    board: str
    amount_yi: float | None = None
    share_pct: float | None = None
    pct_chg: float | None = None

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.board,
            self.amount_yi,
            self.share_pct,
            self.pct_chg,
        )


@dataclass(frozen=True)
class EtfShare:
    """Daily snapshot of a broad-base ETF's fund share (亿份)."""

    trade_date: date
    code: str
    name: str = ""
    share_yi: float | None = None

    def to_row(self) -> tuple:
        return (self.trade_date.isoformat(), self.code, self.name, self.share_yi)


@dataclass(frozen=True)
class BondYield:
    """CN/US government bond yields (%) and spreads (pct points)."""

    trade_date: date
    cn_2y: float | None = None
    cn_10y: float | None = None
    us_2y: float | None = None
    us_10y: float | None = None
    spread_2y: float | None = None
    spread_10y: float | None = None

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.cn_2y,
            self.cn_10y,
            self.us_2y,
            self.us_10y,
            self.spread_2y,
            self.spread_10y,
        )


@dataclass(frozen=True)
class RestrictedRelease:
    """Market-level restricted-share release calendar (daily aggregates)."""

    release_date: date
    company_count: int = 0
    shares: float | None = None
    market_value_yi: float | None = None

    def to_row(self) -> tuple:
        return (
            self.release_date.isoformat(),
            self.company_count,
            self.shares,
            self.market_value_yi,
        )


@dataclass(frozen=True)
class BrokerTrade:
    """One parsed row of a broker deal statement (交割单/对账单).

    ``side`` is normalized: buy / sell / dividend / interest / fee / other.
    Monetary values are in yuan. ``row_hash`` dedupes re-imports of the same
    file (and identical rows across files).
    """

    trade_date: date
    code: str
    side: str
    name: str = ""
    category: str = ""
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    fees: float | None = None
    cash_delta: float | None = None
    source_file: str = ""
    line_no: int = 0
    row_hash: str = ""

    def to_row(self) -> tuple:
        return (
            self.row_hash,
            self.source_file,
            self.line_no,
            self.trade_date.isoformat(),
            self.code,
            self.name,
            self.side,
            self.category,
            self.quantity,
            self.price,
            self.amount,
            self.fees,
            self.cash_delta,
        )


@dataclass(frozen=True)
class BrokerPosition:
    """Per-code position computed from broker trades (moving-average cost)."""

    code: str
    name: str = ""
    quantity: float = 0.0
    avg_cost: float | None = None
    cost_value: float | None = None
    realized_pnl: float = 0.0
    dividend_cash: float = 0.0
    fees_total: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    first_trade_date: date | None = None
    last_trade_date: date | None = None


@dataclass(frozen=True)
class MarginStockRow:
    """Per-stock margin-financing row for watchlist/holdings codes (yuan)."""

    trade_date: date
    code: str
    name: str = ""
    rzye: float | None = None
    rzye_buy: float | None = None
    rqye: float | None = None
    source: str = "exchange_margin"

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.code,
            self.name,
            self.rzye,
            self.rzye_buy,
            self.rqye,
            self.source,
        )
