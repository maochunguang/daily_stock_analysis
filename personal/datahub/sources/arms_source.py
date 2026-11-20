"""Market breadth (TRIN / Arms Index) computed from Tushare full-market data.

Replaces the external ``easy-daily-trading`` snapshot dependency: one
``daily`` request per trading day carries every stock's ``change``/``vol``/
``amount``, from which the breadth aggregates follow directly.  The free
``import-arms`` snapshot path stays available as a manual fallback.

口径与 easy-daily-trading 对齐（保证与已导入的 265 天序列可比）：

- 市场范围：沪深 A 股，剔除北交所（``*.BJ``）与 ST（含 ``*ST``/``退``）
- 涨跌判定：按 ``change``（Tushare 已按除权基准计算当日涨跌）
- ``TRIN = (涨/跌家数) ÷ (涨/跌成交量)``；同时给出按成交额的 ``trin_amount``
- 单位与 ``MarketBreadth`` 一致：成交量亿股、成交额亿元
  （Tushare ``vol`` 为手 → 亿股 ×100/1e8；``amount`` 为千元 → 亿元 ×1000/1e8）
- 指数锚：上证指数 ``000001.SH``（``index_daily``），供卡片展示与背离判读
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Sequence

from ..breadth import compute_trin, interpret, trin_band
from ..models import MarketBreadth
from .base import SourceUnavailable

#: conservative pacing between ``daily`` calls (one per trading day)
MIN_INTERVAL_SECONDS = 0.35


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def aggregate_market_rows(
    rows: Sequence[dict[str, Any]],
    *,
    trade_date: date,
    name_map: dict[str, str],
    index_close: float | None = None,
    index_chg_pct: float | None = None,
    source: str = "tushare_arms",
) -> MarketBreadth | None:
    """Aggregate one session's full-market ``daily`` rows into breadth."""

    up = down = flat = 0
    up_vol = down_vol = 0.0
    up_amt = down_amt = 0.0
    for row in rows:
        code = str(row.get("ts_code") or "").strip()
        if not code or code.endswith(".BJ"):
            continue
        name = name_map.get(code, "")
        if "ST" in name.upper() or "退" in name:
            continue
        change = _to_float(row.get("change"))
        if change is None:
            # 没有涨跌值（如停牌无成交）按平盘不计入样本
            continue
        vol = _to_float(row.get("vol")) or 0.0
        amount = _to_float(row.get("amount")) or 0.0
        if change > 0:
            up += 1
            up_vol += vol
            up_amt += amount
        elif change < 0:
            down += 1
            down_vol += vol
            down_amt += amount
        else:
            flat += 1

    sample = up + down + flat
    if sample <= 0:
        return None
    up_vol_yi = round(up_vol / 1e6, 4) if up_vol else None
    down_vol_yi = round(down_vol / 1e6, 4) if down_vol else None
    up_amount_yi = round(up_amt / 1e5, 4) if up_amt else None
    down_amount_yi = round(down_amt / 1e5, 4) if down_amt else None
    adv_ratio = round(up / sample * 100, 2)
    trin = compute_trin(up, down, up_vol_yi or 0.0, down_vol_yi or 0.0)
    trin_amount = (
        round((up / down) / (up_amount_yi / down_amount_yi), 3)
        if down and up_amount_yi and down_amount_yi
        else None
    )
    band, _state = trin_band(trin)
    return MarketBreadth(
        trade_date=trade_date,
        up_count=up,
        down_count=down,
        flat_count=flat,
        sample_count=sample,
        up_vol_yi=up_vol_yi,
        down_vol_yi=down_vol_yi,
        up_amount_yi=up_amount_yi,
        down_amount_yi=down_amount_yi,
        adv_ratio=adv_ratio,
        trin=trin,
        trin_amount=trin_amount,
        interpretation=interpret(trin, adv_ratio),
        band=band,
        index_close=index_close,
        index_chg_pct=index_chg_pct,
        divergence=0,
        signal_tag="—",
        signal_detail="",
        source=source,
    )


class TushareArmsSource:
    """Compute TRIN breadth from official full-market daily data."""

    name = "tushare_arms"
    INDEX_CODE = "000001.SH"  # 上证指数

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str = "",
        timeout: float = 30.0,
        min_interval: float = MIN_INTERVAL_SECONDS,
    ):
        if client is None:
            if not token.strip():
                raise SourceUnavailable("TUSHARE_TOKEN is not configured")
            from .tushare_source import TushareSource

            client = TushareSource(token.strip(), timeout=timeout)
        self._client = client
        self.min_interval = min_interval
        self.calls = 0

    def _fetch(self, method: str, *args) -> Any:
        if self.calls:
            time.sleep(self.min_interval)
        self.calls += 1
        try:
            return getattr(self._client, method)(*args)
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize transport errors
            raise SourceUnavailable(f"tushare {method} request failed: {exc}") from exc

    def fetch_market_breadth(self, days: Sequence[date]) -> list[MarketBreadth]:
        """Compute one ``MarketBreadth`` per requested trading day."""

        wanted = sorted({day for day in days if day is not None})
        if not wanted:
            return []
        name_map = self._fetch("fetch_stock_name_map") or {}
        index = self._index_rows(wanted[0], wanted[-1])
        out: list[MarketBreadth] = []
        for day in wanted:
            rows = self._fetch("fetch_daily_by_date", day)
            breadth = aggregate_market_rows(
                rows,
                trade_date=day,
                name_map=name_map,
                index_close=index["close"].get(day),
                index_chg_pct=index["chg"].get(day),
                source=self.name,
            )
            if breadth is not None:
                out.append(breadth)
        if not out:
            raise SourceUnavailable("tushare arms returned no breadth rows")
        return out

    def _index_rows(self, start: date, end: date) -> dict[str, dict[date, float]]:
        close: dict[date, float] = {}
        chg: dict[date, float] = {}
        for row in self._fetch("fetch_index_daily", self.INDEX_CODE, start, end):
            day = _to_day(row.get("trade_date"))
            close_value = _to_float(row.get("close"))
            pre_close = _to_float(row.get("pre_close"))
            if day is None or close_value is None:
                continue
            close[day] = close_value
            if pre_close:
                chg[day] = round((close_value / pre_close - 1) * 100, 2)
        return {"close": close, "chg": chg}
