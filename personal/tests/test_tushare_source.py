import io
import json
from datetime import date

import pytest

from personal.datahub.sources.base import SourceUnavailable
from personal.datahub.sources.tushare_source import TushareSource


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._payload


def test_tushare_daily_parsing(monkeypatch):
    payload = {
        "code": 0,
        "msg": None,
        "data": {
            "fields": [
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "vol",
                "amount",
            ],
            "items": [["20260105", 10.0, 10.5, 9.8, 10.2, 1000, 1020]],
        },
    }
    monkeypatch.setattr(
        "personal.datahub.sources.tushare_source.urllib.request.urlopen",
        lambda *args, **kwargs: _FakeResponse(payload),
    )
    bars = TushareSource("token").fetch_daily_bars(
        "600519", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert len(bars) == 1
    assert bars[0].code == "600519.SH"
    assert bars[0].close == 10.2
    assert bars[0].volume == 100_000  # 手 -> 股
    assert bars[0].amount == 1_020_000  # 千元 -> 元


def test_tushare_permission_error(monkeypatch):
    payload = {"code": 40203, "msg": "no permission", "data": None}
    monkeypatch.setattr(
        "personal.datahub.sources.tushare_source.urllib.request.urlopen",
        lambda *args, **kwargs: _FakeResponse(payload),
    )
    with pytest.raises(SourceUnavailable, match="40203"):
        TushareSource("token").fetch_daily_bars(
            "600519", date(2026, 1, 1), date(2026, 1, 31)
        )
