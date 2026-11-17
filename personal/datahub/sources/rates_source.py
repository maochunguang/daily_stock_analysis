"""Macro anchors: CN/US bond yields and restricted-share release calendar.

- 中美国债收益率（东财，日频全量历史一张表）：中美利差是人民币风险资产定价锚。
- 限售解禁汇总（东财）：日级别解禁家数/数量/实际解禁市值（元）。
"""

from __future__ import annotations

from datetime import date

from ..models import BondYield, RestrictedRelease
from .base import SourceUnavailable


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BondSource:
    name = "em_bond_yield"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_bond_yield(self, start: date, end: date) -> list[BondYield]:
        ak = self._ak()
        fetch = getattr(ak, "bond_zh_us_yield_em", None) or getattr(
            ak, "bond_zh_us_rate", None
        )
        if fetch is None:
            raise SourceUnavailable("no CN/US bond yield interface")
        frame = fetch()
        if frame is None or frame.empty:
            return []
        rows: list[BondYield] = []
        for _, row in frame.iterrows():
            day = self._parse_day(row.get("日期"))
            if day is None or not (start <= day <= end):
                continue
            cn_2y = _to_float(row.get("中国国债收益率2年"))
            cn_10y = _to_float(row.get("中国国债收益率10年"))
            us_2y = _to_float(row.get("美国国债收益率2年"))
            us_10y = _to_float(row.get("美国国债收益率10年"))
            rows.append(
                BondYield(
                    trade_date=day,
                    cn_2y=cn_2y,
                    cn_10y=cn_10y,
                    us_2y=us_2y,
                    us_10y=us_10y,
                    spread_2y=(
                        round(cn_2y - us_2y, 4)
                        if cn_2y is not None and us_2y is not None
                        else None
                    ),
                    spread_10y=(
                        round(cn_10y - us_10y, 4)
                        if cn_10y is not None and us_10y is not None
                        else None
                    ),
                )
            )
        return rows

    @staticmethod
    def _parse_day(value) -> date | None:
        text = str(value)[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None


class ReleaseSource:
    name = "em_restricted_release"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_release_summary(self, start: date, end: date) -> list[RestrictedRelease]:
        ak = self._ak()
        fetch = getattr(ak, "stock_restricted_release_summary_em", None)
        if fetch is None:
            raise SourceUnavailable("restricted release interface missing")
        frame = fetch(
            symbol="全部股票",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if frame is None or frame.empty:
            return []
        rows: list[RestrictedRelease] = []
        for _, row in frame.iterrows():
            day = self._parse_day(row.get("解禁时间"))
            if day is None:
                continue
            rows.append(
                RestrictedRelease(
                    release_date=day,
                    company_count=int(_to_float(row.get("当日解禁股票家数")) or 0),
                    shares=_to_float(row.get("实际解禁数量")),
                    market_value_yi=(
                        round(mv / 1e8, 2)
                        if (mv := _to_float(row.get("实际解禁市值"))) is not None
                        else None
                    ),
                )
            )
        return rows

    @staticmethod
    def _parse_day(value) -> date | None:
        text = str(value)[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
