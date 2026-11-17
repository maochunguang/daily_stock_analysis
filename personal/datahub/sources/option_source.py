"""ETF-option PCR adapter (Tushare, raw HTTP).

用户 Tushare 免费档有 `opt_basic` / `opt_daily` 权限。PCR 按**成交量口径**计算：
`opt_daily` 按交易日返回当日有行情的合约，未成交合约对成交量贡献为 0，
因此成交量 PCR 是完整口径；持仓量 PCR 只覆盖有行情合约，作参考列。

注意 Tushare 对 `opt_basic`（1次/分钟）等接口限频，合约表本地缓存
``data/opt_basic_sse.json``，TTL 7 天（新合约上市频率远低于此）。
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from ..models import OptionPcr
from .base import SourceUnavailable

TUSHARE_API = "http://api.tushare.pro"
PCR_UNDERLYINGS: tuple[str, ...] = ("50ETF", "300ETF")
BASIC_CACHE_TTL_DAYS = 7


class OptionPcrSource:
    name = "tushare_option_pcr"

    def __init__(self, token: str, cache_dir: str | Path = "data"):
        self.token = token
        self.cache_dir = Path(cache_dir)
        if not token:
            raise SourceUnavailable("tushare token is not configured")

    def fetch_option_pcr(self, start: date, end: date) -> list[OptionPcr]:
        contracts = self._load_contracts()
        by_code = {row["ts_code"]: row for row in contracts}
        rows: list[OptionPcr] = []
        day = start
        while day <= end:
            trade_date = day.strftime("%Y%m%d")
            items = self._opt_daily(trade_date)
            if items is None:
                day = date.fromordinal(day.toordinal() + 1)
                continue
            aggregates = self._aggregate(items, by_code)
            for underlying in PCR_UNDERLYINGS:
                agg = aggregates.get(underlying)
                if not agg:
                    continue
                rows.append(
                    OptionPcr(
                        trade_date=day,
                        underlying=underlying,
                        call_vol=agg["call_vol"],
                        put_vol=agg["put_vol"],
                        pcr_vol=(
                            round(agg["put_vol"] / agg["call_vol"], 3)
                            if agg["call_vol"] > 0
                            else None
                        ),
                        call_oi=agg["call_oi"],
                        put_oi=agg["put_oi"],
                        pcr_oi=(
                            round(agg["put_oi"] / agg["call_oi"], 3)
                            if agg["call_oi"] > 0
                            else None
                        ),
                    )
                )
            day = date.fromordinal(day.toordinal() + 1)
            time.sleep(0.4)
        return rows

    # ------------------------------------------------------------------
    def _aggregate(self, items: list[list], by_code: dict[str, dict]) -> dict:
        out = {
            underlying: {
                "call_vol": 0.0,
                "put_vol": 0.0,
                "call_oi": 0.0,
                "put_oi": 0.0,
            }
            for underlying in PCR_UNDERLYINGS
        }
        fields = ["ts_code", "trade_date", "exchange", "pre_settle", "pre_close",
                  "open", "high", "low", "close", "settle", "vol", "amount", "oi"]
        for row in items:
            record = dict(zip(fields, row))
            contract = by_code.get(record["ts_code"])
            if contract is None:
                continue
            name = contract.get("name") or ""
            underlying = next(
                (u for u in PCR_UNDERLYINGS if name.startswith(u)), None
            )
            if underlying is None:
                continue
            kind = contract.get("call_put")
            bucket = out[underlying]
            vol = _f(record.get("vol"))
            oi = _f(record.get("oi"))
            if kind == "C":
                bucket["call_vol"] += vol
                bucket["call_oi"] += oi
            elif kind == "P":
                bucket["put_vol"] += vol
                bucket["put_oi"] += oi
        return out

    def _opt_daily(self, trade_date: str) -> list[list] | None:
        response = self._call("opt_daily", trade_date=trade_date, exchange="SSE")
        data = response.get("data")
        if not data:
            return None
        return data.get("items") or []

    def _load_contracts(self) -> list[dict]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.cache_dir / "opt_basic_sse.json"
        if cache_file.exists():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                fetched = datetime.fromisoformat(payload["fetched_at"])
                if datetime.now() - fetched < timedelta(days=BASIC_CACHE_TTL_DAYS):
                    return payload["contracts"]
            except Exception:
                pass
        response = self._call("opt_basic", exchange="SSE")
        data = response.get("data")
        if not data:
            raise SourceUnavailable("opt_basic returned no data")
        fields = data["fields"]
        contracts = [dict(zip(fields, item)) for item in data["items"]]
        cache_file.write_text(
            json.dumps(
                {"fetched_at": datetime.now().isoformat(), "contracts": contracts},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return contracts

    def _call(self, method: str, **params) -> dict:
        body = json.dumps(
            {"api_name": method, "token": self.token, "params": params, "fields": ""}
        ).encode("utf-8")
        request = urllib.request.Request(
            TUSHARE_API, data=body, headers={"Content-Type": "application/json"}
        )
        last_error: Exception | None = None
        attempt = 0
        while attempt < 5:
            attempt += 1
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("code") == 0:
                    return payload
                message = str(payload.get("msg") or payload.get("code"))
                # 40203 频率超限：快进快出的重试只会刷新限频窗口，等满一分钟再试
                if "频率超限" in message:
                    last_error = RuntimeError(message)
                    time.sleep(62)
                    continue
                last_error = RuntimeError(message)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(1.5 * attempt)
        raise SourceUnavailable(f"tushare {method} failed: {last_error}")


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
