from datetime import date, datetime

from personal.backtest.replay import (
    advice_to_action,
    signals_from_analyses,
    signals_from_decision_signals,
)
from personal.contracts.models import AnalysisRecord, DecisionSignalRecord


def test_advice_mapping():
    assert advice_to_action("买入") == "buy"
    assert advice_to_action("加仓") == "buy"
    assert advice_to_action("减仓") == "sell"
    assert advice_to_action("卖出") == "sell"
    assert advice_to_action("持有") is None
    assert advice_to_action("观望") is None
    assert advice_to_action("不建议买入") is None
    assert advice_to_action("") is None


def test_signals_from_analyses_dedup():
    records = [
        AnalysisRecord(
            id=1,
            code="600519",
            operation_advice="买入",
            created_at=datetime(2026, 1, 5, 18, 0),
        ),
        AnalysisRecord(
            id=2,
            code="600519",
            operation_advice="买入",
            created_at=datetime(2026, 1, 5, 19, 0),
        ),
        AnalysisRecord(
            id=3,
            code="000001",
            operation_advice="减仓",
            created_at=datetime(2026, 1, 6, 18, 0),
        ),
    ]
    signals = signals_from_analyses(records)
    assert len(signals) == 2
    assert signals[0].code == "600519.SH"
    assert signals[0].action == "buy"
    assert signals[1].code == "000001.SZ"
    assert signals[1].action == "sell"


def test_signals_from_decision_signals():
    records = [
        DecisionSignalRecord(
            id=1,
            stock_code="600519",
            market="cn",
            action="buy",
            created_at=datetime(2026, 1, 5, 18, 0),
        ),
        DecisionSignalRecord(
            id=2,
            stock_code="600519",
            market="cn",
            action="hold",
            created_at=datetime(2026, 1, 6, 18, 0),
        ),
        DecisionSignalRecord(
            id=3,
            stock_code="300750",
            market="cn",
            action="reduce",
            created_at=datetime(2026, 1, 7, 18, 0),
        ),
    ]
    signals = signals_from_decision_signals(records)
    assert [(signal.code, signal.action) for signal in signals] == [
        ("600519.SH", "buy"),
        ("300750.SZ", "sell"),
    ]
