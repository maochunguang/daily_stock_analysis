"""Built-in OBV indicator plugin (example for the plugin SDK)."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


class OBVIndicator:
    name = "obv"
    version = "0.1.0"
    required_columns = ("close", "volume")

    def compute(self, df: pd.DataFrame, params: Mapping[str, Any]) -> pd.DataFrame:
        missing = [column for column in self.required_columns if column not in df.columns]
        if missing:
            raise ValueError(f"missing required columns: {', '.join(missing)}")

        window = int(params.get("window", 20))
        if window < 2:
            raise ValueError("window must be >= 2")

        out = pd.DataFrame(index=df.index)
        direction = df["close"].diff().fillna(0.0).apply(
            lambda value: 1 if value > 0 else (-1 if value < 0 else 0)
        )
        out["obv"] = (direction * df["volume"]).cumsum()
        out["obv_ma"] = out["obv"].rolling(window, min_periods=1).mean()
        close_change = df["close"].diff(window)
        obv_change = out["obv"].diff(window)
        out["obv_divergence"] = (close_change > 0) & (obv_change < 0)
        return out

    def summarize(self, df: pd.DataFrame, params: Mapping[str, Any]) -> dict[str, Any]:
        if df.empty:
            return {"obv": None, "obv_ma": None, "above_ma": None, "divergence": None}
        latest = df.iloc[-1]
        obv = float(latest["obv"])
        obv_ma = float(latest["obv_ma"])
        return {
            "obv": obv,
            "obv_ma": obv_ma,
            "above_ma": bool(obv > obv_ma),
            "divergence": bool(latest.get("obv_divergence", False)),
        }

    def render(self, summary: dict[str, Any], *, language: str = "zh") -> str:
        if summary.get("obv") is None:
            return ""
        if language in {"en", "ko"}:
            return (
                "\n### Custom Indicator: OBV\n"
                f"- OBV: {summary['obv']:.0f}\n"
                f"- OBV MA: {summary['obv_ma']:.0f}\n"
                f"- Above MA: {summary['above_ma']}\n"
                f"- Bearish divergence: {summary['divergence']}\n"
            )
        return (
            "\n### 自定义指标：OBV 能量潮\n"
            f"- OBV：{summary['obv']:.0f}\n"
            f"- OBV 均线：{summary['obv_ma']:.0f}\n"
            f"- 是否站上均线：{'是' if summary['above_ma'] else '否'}\n"
            f"- 是否出现顶背离：{'是' if summary['divergence'] else '否'}\n"
        )
