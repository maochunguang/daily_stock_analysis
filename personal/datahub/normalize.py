"""Symbol and record normalization."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

ETF_PREFIXES = ("51", "52", "56", "58", "15", "16", "18")


def normalize_code(raw: str) -> str:
    """Normalize an A-share / ETF code to ``600519.SH`` style.

    Accepts ``600519``, ``sh600519``, ``600519.SH``, ``SZ000001``.
    """

    text = str(raw).strip().upper()
    if not text:
        raise ValueError("empty stock code")

    for suffix in (".SH", ".SZ", ".BJ", ".OF"):
        if text.endswith(suffix):
            body = text[: -len(suffix)]
            if body.isdigit():
                return f"{body.zfill(6)}{suffix}"
            return text

    lowered = text.lower()
    if lowered.startswith(("sh", "sz", "bj")):
        prefix, body = lowered[:2], lowered[2:]
        if body.isdigit():
            return f"{body.zfill(6)}.{prefix.upper()}"

    if text.isdigit():
        body = text.zfill(6)
        if body.startswith("6"):
            return f"{body}.SH"
        if body.startswith(("0", "3")):
            return f"{body}.SZ"
        if body.startswith(("4", "8", "9")):
            return f"{body}.BJ"
        if body.startswith(ETF_PREFIXES):
            return f"{body}.SH" if body.startswith(("51", "52", "56", "58")) else f"{body}.SZ"
        return f"{body}.SZ"

    return text


def is_etf_code(code: str) -> bool:
    body = code.split(".")[0]
    return len(body) == 6 and body.startswith(ETF_PREFIXES)


def is_index_code(code: str) -> bool:
    """Tushare-style index codes: ``000xxx.SH`` (上证系列), ``399xxx.SZ``
    (深证系列), ``899xxx.BJ`` (北证系列). No A-share stock shares these
    prefix/suffix combinations, so the test is unambiguous."""

    body = code.split(".")[0]
    suffix = code.rsplit(".", 1)[-1].upper() if "." in code else ""
    if len(body) != 6 or not body.isdigit():
        return False
    if suffix == "SH":
        return body.startswith("000")
    if suffix == "SZ":
        return body.startswith("399")
    if suffix == "BJ":
        return body.startswith("899")
    return False


def is_fund_code(code: str) -> bool:
    return code.upper().endswith(".OF")


def parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported date value: {value!r}")


def coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
