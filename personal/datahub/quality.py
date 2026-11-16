"""Data quality checks for the personal data hub."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Iterable, Sequence

from .models import DailyBar, QualityIssue


def check_bars(
    bars: Sequence[DailyBar],
    *,
    max_jump_pct: float = 20.0,
) -> list[QualityIssue]:
    """Run OHLC / duplicate / jump checks on one symbol's daily bars."""

    issues: list[QualityIssue] = []
    ordered = sorted(bars, key=lambda bar: bar.trade_date)
    seen: Counter[date] = Counter(bar.trade_date for bar in ordered)
    for trade_date, count in seen.items():
        if count > 1:
            issues.append(
                QualityIssue(
                    dataset="daily_bar",
                    rule="duplicate_date",
                    severity="error",
                    code=ordered[0].code,
                    trade_date=trade_date,
                    detail=f"{count} rows for the same date",
                )
            )

    prev_close: float | None = None
    for bar in ordered:
        if bar.close <= 0 or bar.open <= 0 or bar.high <= 0 or bar.low <= 0:
            issues.append(
                QualityIssue(
                    dataset="daily_bar",
                    rule="non_positive_price",
                    severity="error",
                    code=bar.code,
                    trade_date=bar.trade_date,
                    detail=f"OHLC={bar.open}/{bar.high}/{bar.low}/{bar.close}",
                )
            )
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            issues.append(
                QualityIssue(
                    dataset="daily_bar",
                    rule="ohlc_inconsistent",
                    severity="error",
                    code=bar.code,
                    trade_date=bar.trade_date,
                    detail=f"OHLC={bar.open}/{bar.high}/{bar.low}/{bar.close}",
                )
            )
        if bar.volume < 0 or bar.amount < 0:
            issues.append(
                QualityIssue(
                    dataset="daily_bar",
                    rule="negative_volume_or_amount",
                    severity="error",
                    code=bar.code,
                    trade_date=bar.trade_date,
                    detail=f"volume={bar.volume}, amount={bar.amount}",
                )
            )
        if prev_close and prev_close > 0:
            jump = (bar.close - prev_close) / prev_close * 100.0
            if abs(jump) > max_jump_pct:
                issues.append(
                    QualityIssue(
                        dataset="daily_bar",
                        rule="extreme_jump",
                        severity="warn",
                        code=bar.code,
                        trade_date=bar.trade_date,
                        detail=f"close jump {jump:+.2f}% (check corporate action)",
                    )
                )
        prev_close = bar.close
    return issues


def cross_source_diff(
    primary: Sequence[DailyBar],
    secondary: Sequence[DailyBar],
    *,
    price_tolerance_pct: float = 0.5,
    volume_tolerance_pct: float = 20.0,
) -> list[QualityIssue]:
    """Compare two sources for the same symbol and report material differences."""

    primary_by_date = {bar.trade_date: bar for bar in primary}
    secondary_by_date = {bar.trade_date: bar for bar in secondary}
    common = sorted(set(primary_by_date) & set(secondary_by_date))
    issues: list[QualityIssue] = []
    for trade_date in common:
        left = primary_by_date[trade_date]
        right = secondary_by_date[trade_date]
        if left.close > 0:
            diff_pct = abs(left.close - right.close) / left.close * 100.0
            if diff_pct > price_tolerance_pct:
                issues.append(
                    QualityIssue(
                        dataset="cross_source",
                        rule="close_price_mismatch",
                        severity="warn",
                        code=left.code,
                        trade_date=trade_date,
                        detail=(
                            f"{left.source}={left.close} vs "
                            f"{right.source}={right.close} ({diff_pct:.2f}%)"
                        ),
                    )
                )
        if left.volume > 0:
            diff_pct = abs(left.volume - right.volume) / left.volume * 100.0
            if diff_pct > volume_tolerance_pct:
                issues.append(
                    QualityIssue(
                        dataset="cross_source",
                        rule="volume_mismatch",
                        severity="warn",
                        code=left.code,
                        trade_date=trade_date,
                        detail=(
                            f"{left.source}={left.volume} vs "
                            f"{right.source}={right.volume} ({diff_pct:.2f}%)"
                        ),
                    )
                )
    return issues


def missing_dates(
    bars: Iterable[DailyBar],
    expected_dates: Iterable[date],
    *,
    code: str = "",
) -> list[QualityIssue]:
    present = {bar.trade_date for bar in bars}
    return [
        QualityIssue(
            dataset="daily_bar",
            rule="missing_trading_day",
            severity="warn",
            code=code,
            trade_date=trade_date,
            detail="expected trading day has no bar",
        )
        for trade_date in sorted(set(expected_dates) - present)
    ]
