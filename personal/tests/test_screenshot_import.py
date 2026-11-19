from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from personal.datahub.models import AccountPositionSnapshot, AccountSnapshot
from personal.datahub.screenshot import (
    OcrLine,
    ScreenshotError,
    build_account_snapshot,
    parse_ocr_lines,
)
from personal.datahub.store import PersonalStore


def line(text: str, x: float, y: float, width: float = 80, height: float = 20) -> OcrLine:
    return OcrLine(
        text=text,
        box=((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        score=0.96,
    )


def sample_lines() -> list[OcrLine]:
    return [
        line("截图日期 2026-11-19", 520, 0, 120),
        line("总资产", 0, 40),
        line("1,234,567.89", 90, 40),
        line("可用资金", 0, 75),
        line("123,456.78", 90, 75),
        line("持仓市值", 300, 75),
        line("1.10万", 400, 75, 60),
        line("代码", 0, 120, 40),
        line("名称", 80, 120, 50),
        line("持仓", 180, 120, 40),
        line("可用", 250, 120, 40),
        line("成本", 320, 120, 40),
        line("现价", 400, 120, 40),
        line("市值", 480, 120, 40),
        line("盈亏", 560, 120, 40),
        line("600519", 0, 160, 50),
        line("贵州茅台", 80, 160, 70),
        line("100", 180, 160, 30),
        line("100", 250, 160, 30),
        line("1500.00", 320, 160, 50),
        line("1600.00", 400, 160, 50),
        line("160000.00", 480, 160, 60),
        line("10000.00", 560, 160, 60),
        line("510300", 0, 200, 50),
        line("沪深300ETF", 80, 200, 80),
        line("10000", 180, 200, 40),
        line("8000", 250, 200, 35),
        line("4.100", 320, 200, 50),
        line("4.200", 400, 200, 50),
        line("42000.00", 480, 200, 55),
        line("1000.00", 560, 200, 50),
    ]


class TestParseOcrLines:
    def test_parses_account_and_positions(self):
        parsed = parse_ocr_lines(sample_lines())
        assert parsed["as_of"] == "2026-11-19"
        assert parsed["account"]["equity"] == pytest.approx(1_234_567.89)
        assert parsed["account"]["available_cash"] == pytest.approx(123_456.78)
        assert parsed["account"]["market_value"] == pytest.approx(11_000.0)
        assert len(parsed["positions"]) == 2
        maotai = parsed["positions"][0]
        assert maotai["code"] == "600519.SH"
        assert maotai["name"] == "贵州茅台"
        assert maotai["quantity"] == 100
        assert maotai["available_quantity"] == 100
        assert maotai["avg_cost"] == 1500
        assert maotai["market_value"] == 160000
        assert maotai["confidence"] == pytest.approx(0.96)

    def test_no_header_does_not_guess_positions(self):
        parsed = parse_ocr_lines(
            [
                line("总资产", 0, 0),
                line("100000", 90, 0),
                line("600519 贵州茅台 100股", 0, 40, 230),
            ]
        )
        assert parsed["positions"] == []
        assert any("未识别到持仓表" in warning for warning in parsed["warnings"])

    def test_repairs_ocr_thousands_separator_confusion(self):
        parsed = parse_ocr_lines(
            [
                line("总资产1.234.567.89", 0, 0, 220),
                line("可用资金123.456.78", 0, 35, 220),
            ]
        )
        assert parsed["account"]["equity"] == pytest.approx(1_234_567.89)
        assert parsed["account"]["available_cash"] == pytest.approx(123_456.78)

    def test_duplicate_codes_warn(self):
        rows = sample_lines()
        rows.append(line("600519", 0, 240, 50))
        rows.extend(
            [
                line("贵州茅台", 80, 240, 70),
                line("100", 180, 240, 30),
                line("100", 250, 240, 30),
                line("1500", 320, 240, 40),
                line("1600", 400, 240, 40),
                line("160000", 480, 240, 50),
                line("10000", 560, 240, 50),
            ]
        )
        parsed = parse_ocr_lines(rows)
        assert any("重复代码" in warning for warning in parsed["warnings"])


class TestBuildSnapshot:
    def test_numeric_suffix_and_fallbacks(self):
        draft = {
            "equity": "100万",
            "market_value": "80万",
            "positions": [
                {"code": "600519", "quantity": 100, "market_price": 1500},
                {"code": "510300", "quantity": 10000, "market_price": 4.2},
            ],
        }
        snapshot, warnings = build_account_snapshot(
            draft, account_alias="同花顺", as_of=date(2026, 11, 19)
        )
        assert snapshot.equity == 1_000_000
        assert snapshot.market_value == 800_000
        assert snapshot.cash == 200_000
        assert snapshot.positions[0].code == "600519.SH"
        assert snapshot.positions[0].market_value == 150_000
        assert any("现金由总资产" in warning for warning in warnings)

    def test_duplicate_code_rejected(self):
        with pytest.raises(ScreenshotError):
            build_account_snapshot(
                {
                    "equity": 100000,
                    "positions": [
                        {"code": "600519", "quantity": 100},
                        {"code": "600519.SH", "quantity": 100},
                    ],
                },
                account_alias="同花顺",
                as_of=date(2026, 11, 19),
            )

    def test_zero_quantity_ignored(self):
        snapshot, warnings = build_account_snapshot(
            {
                "equity": 100000,
                "positions": [{"code": "600519", "quantity": 0}],
            },
            account_alias="同花顺",
            as_of=date(2026, 11, 19),
        )
        assert snapshot.positions == ()
        assert any("数量为 0" in warning for warning in warnings)


class TestStoreIsolation:
    def test_same_day_upsert_keeps_one_snapshot_and_broker_untouched(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            snapshot_id = store.upsert_account_snapshot(
                AccountSnapshot(
                    account_alias="同花顺",
                    as_of=date(2026, 11, 19),
                    equity=100000,
                    cash=10000,
                    positions=(
                        AccountPositionSnapshot(
                            code="600519.SH", quantity=100, market_value=90000
                        ),
                    ),
                )
            )
            updated_id = store.upsert_account_snapshot(
                AccountSnapshot(
                    account_alias="同花顺",
                    as_of=date(2026, 11, 19),
                    equity=110000,
                    cash=10000,
                    positions=(
                        AccountPositionSnapshot(
                            code="600519.SH", quantity=100, market_value=100000
                        ),
                    ),
                )
            )
            assert snapshot_id == updated_id
            snapshots = store.list_account_snapshots()
            assert len(snapshots) == 1
            latest = store.get_latest_account_snapshot()
            assert latest["equity"] == 110000
            assert len(latest["positions"]) == 1
            assert store.account_position_codes() == ["600519.SH"]
            assert store.get_broker_positions() == []
            assert store.list_journal(limit=10) == []
        finally:
            store.close()

    def test_snapshot_lookup_by_id(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            snapshot_id = store.upsert_account_snapshot(
                AccountSnapshot(
                    account_alias="同花顺",
                    as_of=date(2026, 11, 19),
                    equity=100000,
                )
            )
            assert store.get_account_snapshot(snapshot_id)["equity"] == 100000
            assert store.get_account_snapshot(snapshot_id + 99) is None
        finally:
            store.close()
