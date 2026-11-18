import base64
import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from personal.datahub.broker import (
    classify_side,
    compute_positions,
    decode_statement,
    import_statement,
    parse_statement,
)
from personal.datahub.models import BrokerTrade, MarginStockRow
from personal.datahub.store import PersonalStore

STATEMENT = """客户名称：测试  资金账号：12345
交易日期,证券代码,证券名称,业务名称,成交数量,成交价格,成交金额,手续费,印花税,过户费,发生金额
2026-10-09,600519,贵州茅台,证券买入,100,1500.00,150000.00,75.00,0.00,1.50,-150076.50
2026-10-16,600519,贵州茅台,证券卖出,100,1560.00,156000.00,78.00,156.00,1.56,155764.44
2026-10-16,600519,贵州茅台,红利入账,0,0,842.00,0,0,0,842.00
2026-10-20,300274,阳光电源,证券买入,500,80.00,40000.00,20.00,0.00,2.00,-40022.00
2026-10-21,300274,阳光电源,新股配号,0,0,0.00,0,0,0,0.00
2026-10-23,300274,阳光电源,证券卖出,300,88.00,26400.00,13.20,26.40,1.32,26359.08
2026-10-30,510300,沪深300ETF,担保品买入,10000,4.10,41000.00,10.00,0.00,0.00,-41010.00
2026-11-03,510300,沪深300ETF,担保品卖出,4000,4.30,17200.00,8.00,0.00,0.00,17192.00
"""


@pytest.fixture()
def store(tmp_path):
    db = PersonalStore(tmp_path / "personal.db")
    try:
        yield db
    finally:
        db.close()


class TestParseStatement:
    def test_parse_classify_and_fee_sum(self):
        statement = parse_statement(STATEMENT, source_file="交割单.csv")
        assert statement.column_map["trade_date"] == "交易日期"
        assert statement.column_map["amount"] == "成交金额"
        assert len(statement.trades) == 8
        sides = [(trade.code, trade.side) for trade in statement.trades]
        assert sides == [
            ("600519", "buy"),
            ("600519", "sell"),
            ("600519", "dividend"),
            ("300274", "buy"),
            ("300274", "other"),  # 新股配号 0 数量
            ("300274", "sell"),
            ("510300", "buy"),  # 担保品买入
            ("510300", "sell"),
        ]
        buy = statement.trades[0]
        assert buy.fees == 76.5  # 手续费+印花税+过户费合计
        assert buy.cash_delta == -150076.5

    def test_gbk_and_tab_decoding(self):
        gbk_bytes = STATEMENT.encode("gbk")
        assert "证券买入" in decode_statement("a.csv", gbk_bytes)
        tsv = STATEMENT.replace(",", "\t")
        statement = parse_statement(tsv, source_file="a.txt")
        assert len(statement.trades) == 8

    def test_unmapped_headers_raise(self):
        with pytest.raises(ValueError):
            parse_statement("代码,方向\n600519,买\n", source_file="x.csv")

    def test_column_map_override(self):
        mapped = parse_statement(
            STATEMENT, source_file="a.csv", column_map={"业务名称": "category"}
        )
        assert mapped.column_map["category"] == "业务名称"


class TestClassifySide:
    def test_categories(self):
        assert classify_side("融资买入", 100, -1) == "buy"
        assert classify_side("融券卖出", 100, 1) == "sell"
        assert classify_side("买券还券", 100, -1) == "buy"
        assert classify_side("红利入账", 0, 842) == "dividend"
        assert classify_side("利息归本", 0, 12.3) == "interest"
        assert classify_side("担保品划入", 0, 0) == "other"
        assert classify_side("新股配号", 0, 0) == "other"
        assert classify_side("", None, -100) == "buy"  # 资金方向兜底
        assert classify_side("", None, 200) == "sell"


class TestComputePositions:
    def test_moving_average_cost_and_realized(self):
        statement = parse_statement(STATEMENT, source_file="a.csv")
        positions, warnings = compute_positions(statement.trades)
        by_code = {position.code: position for position in positions}
        assert not warnings
        maotai = by_code["600519"]
        assert maotai.quantity == 0
        assert maotai.realized_pnl == pytest.approx(5687.94)
        assert maotai.dividend_cash == pytest.approx(842.0)
        assert maotai.fees_total == pytest.approx(312.06)
        solar = by_code["300274"]
        assert solar.quantity == 200
        assert solar.avg_cost == pytest.approx(80.044)
        assert solar.realized_pnl == pytest.approx(2345.88)
        etf = by_code["510300"]
        assert etf.quantity == 6000
        assert etf.avg_cost == pytest.approx(4.101)
        assert etf.realized_pnl == pytest.approx(788.0)

    def test_oversell_warns(self):
        trades = [
            BrokerTrade(trade_date=date(2026, 10, 9), code="600519", side="sell",
                        quantity=100, price=10.0, amount=1000.0),
        ]
        positions, warnings = compute_positions(trades)
        assert any("无持仓" in warning for warning in warnings)
        assert positions[0].realized_pnl == 0


class TestImport:
    def test_import_positions_journal_and_dedupe(self, store):
        summary = import_statement(store, "交割单.csv", STATEMENT.encode("gbk"))
        assert summary.imported == 8
        assert summary.journal_added == 6  # 只为 buy/sell 记日志
        assert not summary.warnings
        held = [position for position in summary.positions if position.quantity > 0]
        assert {position.code for position in held} == {"300274", "510300"}

        again = import_statement(store, "交割单.csv", STATEMENT.encode("gbk"))
        assert again.imported == 8
        assert store.list_journal(limit=200).__len__() == 6  # 幂等

    def test_journal_snapshot_records_market_state(self, store):
        # 给 10-09 播种市场数据，快照应包含综合分量与当日信息
        from personal.datahub.models import (
            LimitUpStats,
            MarketBreadth,
            MarketTurnover,
            SectorAmount,
        )

        store.upsert_market_turnover(
            [MarketTurnover(trade_date=date(2026, 10, 9), sse_amount=5e11, szse_amount=5e11)]
        )
        store.upsert_limit_up_stats(
            [LimitUpStats(trade_date=date(2026, 10, 9), zt_count=40, zb_rate=0.3)]
        )
        store.upsert_sector_amount(
            [
                SectorAmount(trade_date=date(2026, 10, 9), board="半导体",
                             amount_yi=300.0, share_pct=4.2, pct_chg=1.0),
                SectorAmount(trade_date=date(2026, 10, 9), board="白酒",
                             amount_yi=500.0, share_pct=7.5, pct_chg=0.5),
            ]
        )
        rows = [
            MarketBreadth(
                trade_date=date(2026, 10, 9), up_count=1000, down_count=3800,
                flat_count=150, sample_count=4950, adv_ratio=20.2, trin=1.1,
                band="低位", interpretation="恐慌", source="easy_daily_trading",
            )
        ]
        store.upsert_market_breadth(rows)
        import_statement(store, "交割单.csv", STATEMENT.encode("gbk"))
        journal = store.list_journal(limit=200)
        entry = next(row for row in journal if row["code"] == "600519" and row["side"] == "buy")
        snapshot = json.loads(entry["snapshot"])
        assert snapshot["trade_date"] == "2026-10-09"
        assert snapshot["breadth"]["trin"] == 1.1
        assert snapshot["limit_up"]["zt_count"] == 40
        assert snapshot["sector_top"] == {"board": "白酒", "share_pct": 7.5}
        assert entry["source"] == "broker"

    def test_margin_stock_roundtrip(self, store):
        rows = [
            MarginStockRow(trade_date=date(2026, 11, 17), code="600519",
                           name="贵州茅台", rzye=1.0e9, rzye_buy=5.0e7, rqye=2.0e7),
            MarginStockRow(trade_date=date(2026, 11, 18), code="600519",
                           name="贵州茅台", rzye=1.02e9, rzye_buy=4.5e7, rqye=2.1e7),
        ]
        assert store.upsert_margin_stock(rows) == 2
        series = store.get_margin_stock(code="600519")
        assert [row.trade_date for row in series] == [row.trade_date for row in rows]
        assert series[-1].rzye == 1.02e9
        assert store.broker_position_codes() == []


class TestApi:
    def test_broker_import_and_positions(self, client):
        encoded = base64.b64encode(STATEMENT.encode("utf-8")).decode()
        response = client.post(
            "/api/broker/import",
            json={"filename": "交割单.csv", "content_b64": encoded},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["imported"] == 8
        assert payload["journal_added"] == 6

        positions = client.get("/api/broker/positions")
        assert positions.status_code == 200
        held = [row for row in positions.json()["positions"] if row["quantity"] > 0]
        assert {row["code"] for row in held} == {"300274", "510300"}

        journal = client.get("/api/broker/journal?limit=10")
        assert journal.status_code == 200
        entry = journal.json()["journal"][0]
        assert entry["snapshot"]["trade_date"]

    def test_margin_stocks_endpoint(self, client):
        sample = "交易日期,证券代码,证券名称,业务名称,成交数量,成交价格,成交金额\n2026-11-17,600519,贵州茅台,证券买入,100,1500,150000\n"
        payload = {
            "filename": "x.csv",
            "content_b64": base64.b64encode(sample.encode("utf-8")).decode(),
        }
        imported = client.post("/api/broker/import", json=payload)
        assert imported.status_code == 200
        assert client.get("/api/broker/positions").json()["positions"][0]["code"] == "600519"
        stocks = client.get("/api/margin/stocks?days=30")
        assert stocks.status_code == 200
        assert stocks.json()["stocks"] == []  # 未同步明细时为空
