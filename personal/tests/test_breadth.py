import json
from datetime import date

from personal.datahub.breadth import (
    compute_trin,
    interpret,
    load_easy_daily_snapshots,
    percentile_of,
    trin_band,
)
from personal.datahub.store import PersonalStore

# 2026-11-17 实测快照（easy-daily-trading），作为口径回归基准。
SNAPSHOT = {
    "date": "2026-11-17",
    "up": 1192,
    "down": 3717,
    "flat": 117,
    "up_vol_yi": 306.61,
    "down_vol_yi": 623.52,
    "up_amt_yi": 5225.1,
    "down_amt_yi": 8966.9,
    "trin": 0.652,
    "trin_amt": 0.55,
    "adv_ratio": 23.7,
    "total": 5026,
    "signal": "中低位｜普跌+量能尚可 → 弱势整理",
    "band": "中低位",
    "pct": 32.6,
    "index": 3584.58,
    "index_chg": -0.5,
    "index_pos": 0.0,
    "signal_detail": [],
    "signal_tag": "—",
    "divergence": 0,
}


class TestTrinBands:
    def test_band_matches_a_share_calibration(self):
        assert trin_band(0.405) == ("极低", "量能极度集中")
        assert trin_band(0.652) == ("中低位", "偏强")
        assert trin_band(1.0) == ("中高位", "中性")
        assert trin_band(1.5) == ("高位", "量能撤离")
        assert trin_band(2.8) == ("极高", "恐慌/背离")
        assert trin_band(None) == ("—", "数据不足")

    def test_interpret_uses_adv_ratio_context(self):
        # 与快照完全一致：普跌 + 中低位 TRIN = 弱势整理
        assert interpret(0.652, 23.7) == "中低位｜普跌+量能尚可 → 弱势整理"
        # 同样 TRIN 0.4：普涨 = 健康，普跌 = 抱团避险，分化 = 结构性
        assert "强势健康" in interpret(0.4, 70.0)
        assert "常近短期底" in interpret(0.4, 15.0)
        assert "结构性行情" in interpret(0.4, 50.0)
        assert interpret(None) == "数据不足"

    def test_percentile(self):
        history = [0.5] * 30 + [1.0] * 70
        assert percentile_of(0.652, history) == 30.0
        assert percentile_of(None, history) is None
        assert percentile_of(0.652, []) is None

    def test_compute_trin_div_zero(self):
        assert compute_trin(10, 0, 1.0, 1.0) is None
        # (10/20) ÷ (2.0/1.0) = 0.5 / 2 = 0.25
        assert compute_trin(10, 20, 2.0, 1.0) == 0.25


class TestSnapshotLoader:
    def test_load_snapshot_fields(self, tmp_path):
        path = tmp_path / "2026-11-17.json"
        path.write_text(json.dumps(SNAPSHOT), encoding="utf-8")
        rows = list(load_easy_daily_snapshots(tmp_path))
        assert len(rows) == 1
        row = rows[0]
        assert row.trade_date == date(2026, 11, 17)
        assert row.up_count == 1192
        assert row.down_count == 3717
        assert row.flat_count == 117
        assert row.sample_count == 5026
        assert row.up_vol_yi == 306.61
        assert row.up_amount_yi == 5225.1
        assert row.trin == 0.652
        assert row.trin_amount == 0.55
        assert row.trin_pct == 32.6
        assert row.band == "中低位"
        assert row.interpretation == "中低位｜普跌+量能尚可 → 弱势整理"
        assert row.index_close == 3584.58
        assert row.index_chg_pct == -0.5
        assert row.divergence == 0
        assert row.source == "easy_daily_trading"

    def test_signal_detail_joined(self, tmp_path):
        payload = dict(SNAPSHOT, signal_detail=["⚠️ 顶部量能背离（20日新高+量能跟不上）"])
        (tmp_path / "2026-11-10.json").write_text(json.dumps(payload), encoding="utf-8")
        rows = list(load_easy_daily_snapshots(tmp_path))
        assert "顶部量能背离" in rows[0].signal_detail

    def test_broken_file_is_skipped(self, tmp_path):
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        (tmp_path / "2026-11-17.json").write_text(json.dumps(SNAPSHOT), encoding="utf-8")
        rows = list(load_easy_daily_snapshots(tmp_path))
        assert len(rows) == 1

    def test_missing_directory_yields_nothing(self, tmp_path):
        assert list(load_easy_daily_snapshots(tmp_path / "nope")) == []


class TestStoreRoundtrip:
    def test_upsert_get_stats(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            rows = list(load_easy_daily_snapshots(_snapshot_dir(tmp_path)))
            assert len(rows) == 2
            assert store.upsert_market_breadth(rows) == 2
            # 幂等：重复导入不产生重复行
            assert store.upsert_market_breadth(rows) == 2
            stored = store.get_market_breadth()
            assert [r.trade_date for r in stored] == [
                date(2026, 11, 14),
                date(2026, 11, 17),
            ]
            assert stored[-1].trin == 0.652
            assert store.stats()["market_breadth"] == 2
            recent = store.get_market_breadth(limit=1)
            assert [r.trade_date for r in recent] == [date(2026, 11, 17)]
            start_window = store.get_market_breadth(
                start=date(2026, 11, 16), end=date(2026, 11, 17)
            )
            assert len(start_window) == 1
        finally:
            store.close()


def _snapshot_dir(tmp_path):
    target = tmp_path / "daily"
    target.mkdir()
    (target / "2026-11-14.json").write_text(
        json.dumps(dict(SNAPSHOT, date="2026-11-14", trin=1.02, band="中高位")),
        encoding="utf-8",
    )
    (target / "2026-11-17.json").write_text(json.dumps(SNAPSHOT), encoding="utf-8")
    return target
