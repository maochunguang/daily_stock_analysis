"""Official current index PE for cross-checking the Legulegu history.

Legulegu provides the long weekly history needed for percentiles.  The index
providers publish an independent current value that can validate the *level*:

- 中证指数 ``indicator/{code}indicator.xls``: ``市盈率1（总股本）`` is the
  total-share PE1; it is compared with Legulegu's static ``addLyrPe`` because
  both use the total-share base.
- 国证指数 ``index_all_cni``: ``PE滚动`` is the rolling/TTM PE and matches
  Legulegu's ``addTtmPe``.

The official endpoints only expose the latest value (CSI: recent 20 sessions),
so they are used for a level cross-check, never for the 1/3/5-year percentile
history.  A difference is not automatically a data bug: weighting, share base
and earnings timing can differ.  The report labels that explicitly.

CSI is fetched directly instead of through ``ak.index_value_csindex`` because
the Docker image pins akshare 1.19.x, which does not expose that helper.
"""

from __future__ import annotations

import io
from typing import Any

from .base import SourceUnavailable

CSI_XLS_URL = (
    "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
    "autofile/indicator/{symbol}indicator.xls"
)

#: code -> how to compare the official current value with the stored series.
OFFICIAL_VALUATION_TARGETS: dict[str, dict[str, str]] = {
    "000300.SH": {
        "source": "csindex",
        "symbol": "000300",
        "official_field": "市盈率1",
        "official_metric": "中证 PE1（总股本）",
        "legu_metric": "pe_static",
        "legu_label": "乐咕静态 PE",
    },
    "000688.SH": {
        "source": "csindex",
        "symbol": "000688",
        "official_field": "市盈率1",
        "official_metric": "中证 PE1（总股本）",
        "legu_metric": "pe_static",
        "legu_label": "乐咕静态 PE",
    },
    "399006.SZ": {
        "source": "cni",
        "symbol": "399006",
        "official_field": "PE滚动",
        "official_metric": "国证 PE滚动（TTM）",
        "legu_metric": "pe_ttm",
        "legu_label": "乐咕 PE-TTM",
    },
    "399673.SZ": {
        "source": "cni",
        "symbol": "399673",
        "official_field": "PE滚动",
        "official_metric": "国证 PE滚动（TTM）",
        "legu_metric": "pe_ttm",
        "legu_label": "乐咕 PE-TTM",
    },
}


def _ak():
    try:
        import akshare as ak
    except ImportError as exc:  # pragma: no cover - image has akshare
        raise SourceUnavailable("akshare is not installed") from exc
    return ak


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _format_csi_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10] or None


def _parse_csindex_frame(frame: Any, target: dict[str, str]) -> dict[str, Any]:
    """Pick the latest PE1 row from a CSI indicator frame."""

    if frame is None or frame.empty:
        raise SourceUnavailable(f"中证指数 {target['symbol']} 无估值数据")
    columns = [str(column) for column in frame.columns]
    date_column = next((column for column in columns if "日期" in column), None)
    pe_column = next((column for column in columns if "市盈率1" in column), None)
    if date_column is None or pe_column is None:
        raise SourceUnavailable(
            f"中证指数 {target['symbol']} 表头缺少日期/市盈率1"
        )
    records = frame.to_dict("records")
    latest = max(records, key=lambda row: str(row.get(date_column) or ""))
    value = _to_float(latest.get(pe_column))
    if value is None:
        raise SourceUnavailable(
            f"中证指数 {target['symbol']} 缺少 {target['official_field']}"
        )
    return {
        "official_pe": value,
        "official_date": _format_csi_date(latest.get(date_column)),
        "official_source": "中证指数",
        "official_metric": target["official_metric"],
    }


def _fetch_csindex(target: dict[str, str]) -> dict[str, Any]:
    try:
        import pandas as pd
        import requests
    except ImportError as exc:  # pragma: no cover - image has both
        raise SourceUnavailable("requests/pandas is not installed") from exc

    url = CSI_XLS_URL.format(symbol=target["symbol"])
    try:
        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - normalize transport errors
        raise SourceUnavailable(f"中证指数下载失败: {exc}") from exc
    try:
        frame = pd.read_excel(io.BytesIO(response.content))
    except Exception as exc:  # noqa: BLE001 - normalize parse errors
        raise SourceUnavailable(f"中证指数表格解析失败: {exc}") from exc
    return _parse_csindex_frame(frame, target)


def _fetch_cni_frame(frame: Any, symbol: str) -> dict[str, Any]:
    for row in frame.to_dict("records"):
        if str(row.get("指数代码") or "").zfill(6) != symbol:
            continue
        value = _to_float(row.get("PE滚动"))
        if value is None:
            break
        return {
            "official_pe": value,
            # CNI's list endpoint has no date column; it is the latest close.
            "official_date": None,
            "official_source": "国证指数",
            "official_metric": "国证 PE滚动（TTM）",
        }
    raise SourceUnavailable(f"国证指数 {symbol} 无估值数据")


def fetch_official_valuations(
    codes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return official current values keyed by index code.

    Per-code failures become ``{"error": ...}``; the caller can still show the
    other indexes instead of failing the whole cross-check.
    """

    selected = list(codes or OFFICIAL_VALUATION_TARGETS)
    results: dict[str, dict[str, Any]] = {}
    cni_codes = [
        code
        for code in selected
        if OFFICIAL_VALUATION_TARGETS.get(code, {}).get("source") == "cni"
    ]
    cni_frame = None
    cni_error: Exception | None = None
    if cni_codes:
        try:
            cni_frame = _ak().index_all_cni()
        except Exception as exc:  # noqa: BLE001 - report per source
            cni_error = exc

    for code in selected:
        target = OFFICIAL_VALUATION_TARGETS.get(code)
        if target is None:
            results[code] = {"error": f"未配置官方校验源: {code}"}
            continue
        try:
            if target["source"] == "csindex":
                results[code] = _fetch_csindex(target)
            else:
                if cni_error is not None:
                    raise SourceUnavailable(f"国证指数请求失败: {cni_error}")
                assert cni_frame is not None
                results[code] = _fetch_cni_frame(cni_frame, target["symbol"])
        except Exception as exc:  # noqa: BLE001 - one source must not hide others
            results[code] = {"error": str(exc)}
    return results
