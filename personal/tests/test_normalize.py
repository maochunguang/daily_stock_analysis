from datetime import date

from personal.datahub.normalize import is_etf_code, normalize_code, parse_date


def test_normalize_a_share_codes():
    assert normalize_code("600519") == "600519.SH"
    assert normalize_code("000001") == "000001.SZ"
    assert normalize_code("300750") == "300750.SZ"
    assert normalize_code("920493") == "920493.BJ"
    assert normalize_code("sh600519") == "600519.SH"
    assert normalize_code("600519.SH") == "600519.SH"


def test_normalize_etf_codes():
    assert normalize_code("510050") == "510050.SH"
    assert normalize_code("159915") == "159915.SZ"
    assert is_etf_code("510050.SH")
    assert is_etf_code("159915.SZ")
    assert not is_etf_code("600519.SH")


def test_parse_date_formats():
    assert parse_date("2026-11-12") == date(2026, 11, 12)
    assert parse_date("20261112") == date(2026, 11, 12)
    assert parse_date(date(2026, 11, 12)) == date(2026, 11, 12)
