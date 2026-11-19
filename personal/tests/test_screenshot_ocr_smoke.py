"""Optional local end-to-end OCR smoke test.

Skipped when RapidOCR or a CJK font is unavailable (e.g. a minimal CI image).
The rest of the suite uses fake OCR boxes and never depends on model files.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from personal.datahub.screenshot import parse_account_screenshot

CJK_FONTS = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)


def _font_path() -> str | None:
    return next((path for path in CJK_FONTS if Path(path).exists()), None)


@pytest.mark.skipif(
    importlib.util.find_spec("rapidocr_onnxruntime") is None,
    reason="rapidocr-onnxruntime not installed",
)
@pytest.mark.skipif(_font_path() is None, reason="CJK font not available")
def test_real_ocr_parses_holdings_screenshot():
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(_font_path() or "", 22)
    image = Image.new("RGB", (980, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 15), "总资产  1,234,567.89", font=font, fill="black")
    draw.text((500, 15), "可用资金  123,456.78", font=font, fill="black")
    headers = [
        ("代码", 30),
        ("名称", 120),
        ("持仓", 280),
        ("可用", 380),
        ("成本", 480),
        ("现价", 590),
        ("市值", 700),
        ("盈亏", 850),
    ]
    for text, x in headers:
        draw.text((x, 70), text, font=font, fill="#555555")
    row = ("600519", "贵州茅台", "100", "100", "1500.00", "1600.00", "160000.00", "10000.00")
    for (_, x), text in zip(headers, row):
        draw.text((x, 120), text, font=font, fill="black")

    buffer = Path("/tmp/dsa_ocr_smoke.png")
    image.save(buffer)
    try:
        result = parse_account_screenshot(buffer.read_bytes(), filename="ths.png")
    finally:
        buffer.unlink(missing_ok=True)

    assert result["draft"]["equity"] == pytest.approx(1_234_567.89)
    assert result["draft"]["available_cash"] == pytest.approx(123_456.78)
    assert result["draft"]["positions"][0]["code"] == "600519.SH"
    assert result["draft"]["positions"][0]["quantity"] == 100
    assert result["draft"]["positions"][0]["market_value"] == 160000
