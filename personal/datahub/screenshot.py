"""Tonghuashun account/holdings screenshot parsing.

The image never leaves the host. OCR is local (RapidOCR/ONNX); only a
structured draft is returned to the caller. Confirmed snapshots are stored in
``account_snapshot`` / ``account_position_snapshot`` and remain separate from
the transaction-reconstructed ``broker_position`` ledger.
"""

from __future__ import annotations

import hashlib
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .models import AccountPositionSnapshot, AccountSnapshot
from .normalize import normalize_code
from .store import PersonalStore

MAX_IMAGE_SIDE = 2600
DEFAULT_MAX_IMAGE_MB = 8.0
OCR_ENGINE_NAME = "rapidocr_onnxruntime"


class ScreenshotError(ValueError):
    """A screenshot cannot be decoded or parsed."""


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: tuple[tuple[float, float], ...]
    score: float = 0.0

    @property
    def x0(self) -> float:
        return min(point[0] for point in self.box)

    @property
    def x1(self) -> float:
        return max(point[0] for point in self.box)

    @property
    def y0(self) -> float:
        return min(point[1] for point in self.box)

    @property
    def y1(self) -> float:
        return max(point[1] for point in self.box)

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return max(1.0, self.y1 - self.y0)


@dataclass(frozen=True)
class _Row:
    lines: tuple[OcrLine, ...]
    y0: float
    y1: float
    height: float

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


# Longest aliases win when a header token contains multiple field names.
FIELD_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("quantity_available", ("持仓/可用", "持仓可用", "持仓/可用数量", "数量/可用")),
    ("available_quantity", ("可用数量", "可用余额", "可卖数量", "可用", "可卖")),
    ("avg_cost", ("摊薄成本", "持仓成本", "成本价", "成本")),
    ("market_price", ("最新价", "当前价", "现价", "市价")),
    ("market_value", ("持仓市值", "参考市值", "市值")),
    ("pnl", ("浮动盈亏", "持仓盈亏", "当日盈亏", "盈亏")),
    ("quantity", ("持仓数量", "持股数量", "股票余额", "持仓", "数量")),
    ("code", ("证券代码", "股票代码", "代码")),
    ("name", ("证券名称", "股票名称", "名称")),
)

ACCOUNT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("equity", ("总资产", "资产总值", "账户资产", "资产合计")),
    ("available_cash", ("可用资金", "可用金额", "可用余额")),
    ("cash", ("资金余额", "现金余额", "账户余额")),
    ("market_value", ("持仓市值", "证券市值", "参考市值", "股票市值", "总市值")),
)

_NUMBER_RE = re.compile(
    r"[-+]?\d[\d,，.]*(?:\s*(?:万|亿))?"
)
_DATE_RE = re.compile(
    r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?"
)
_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")

_ENGINE: Any = None
_ENGINE_LOCK = threading.Lock()
_HEIF_REGISTERED = False


def recognize_image(
    content: bytes,
    *,
    filename: str = "",
    max_mb: float = DEFAULT_MAX_IMAGE_MB,
    enabled: bool = True,
) -> list[OcrLine]:
    """Run local OCR and return normalized lines with bounding boxes."""

    if not enabled:
        raise ScreenshotError("OCR 已在配置中关闭，请使用手工录入")
    image = _load_image(content, max_mb=max_mb, filename=filename)
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:  # pragma: no cover - exercised only in deployment
        raise ScreenshotError(
            "本地 OCR 未安装（rapidocr-onnxruntime），请安装依赖或使用手工录入"
        ) from exc

    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            try:
                _ENGINE = RapidOCR()
            except Exception as exc:  # pragma: no cover - model/runtime failure
                raise ScreenshotError(f"本地 OCR 初始化失败：{exc}") from exc
        array = np.asarray(image)[:, :, ::-1].copy()  # RGB -> BGR for OpenCV
        try:
            result, _ = _ENGINE(array)
        except Exception as exc:  # pragma: no cover - OCR runtime failure
            raise ScreenshotError(f"图片识别失败：{exc}") from exc
    return _normalize_ocr_result(result)


def parse_account_screenshot(
    content: bytes,
    *,
    filename: str = "",
    max_mb: float = DEFAULT_MAX_IMAGE_MB,
    enabled: bool = True,
) -> dict[str, Any]:
    """OCR + parse a screenshot into an editable account snapshot draft."""

    content_hash = hashlib.sha256(content).hexdigest()
    lines = recognize_image(
        content, filename=filename, max_mb=max_mb, enabled=enabled
    )
    parsed = parse_ocr_lines(lines)
    return {
        "filename": Path(filename).name if filename else "",
        "content_hash": content_hash,
        "ocr_engine": OCR_ENGINE_NAME,
        "draft": {
            "account_alias": "同花顺",
            "as_of": parsed["as_of"],
            "cash": parsed["account"].get("cash"),
            "available_cash": parsed["account"].get("available_cash"),
            "market_value": parsed["account"].get("market_value"),
            "equity": parsed["account"].get("equity"),
            "positions": parsed["positions"],
        },
        "warnings": parsed["warnings"],
        "line_count": len(lines),
    }


def parse_ocr_lines(lines: Sequence[OcrLine]) -> dict[str, Any]:
    """Parse OCR lines without touching image or database state.

    Account metrics are read only above the detected holdings header, which
    prevents per-row market values from being mistaken for account totals.
    """

    if not lines:
        return {
            "as_of": None,
            "account": {},
            "positions": [],
            "warnings": ["未识别到文字；请检查图片清晰度或改用手工录入"],
        }

    warnings: list[str] = []
    rows = _group_rows(lines)
    header_index, columns = _find_header(rows)
    table_top = rows[header_index].y0 if header_index is not None else None
    account_limit = (
        table_top - rows[header_index].height * 0.35
        if header_index is not None and table_top is not None
        else None
    )
    account = _parse_account_metrics(lines, max_y=account_limit)
    as_of = _detect_as_of(lines)

    positions: list[dict[str, Any]] = []
    if header_index is None or not columns:
        if _looks_like_holdings(lines):
            warnings.append("识别到疑似持仓内容，但表头列未完整识别；请手工补充代码/数量")
        else:
            warnings.append("未识别到持仓表；如只需录入总资产可继续，否则请手工录入")
    else:
        for row in rows[header_index + 1 :]:
            parsed = _parse_position_row(row, columns)
            if parsed is None:
                continue
            positions.append(parsed)

    if columns and not positions:
        warnings.append("持仓表头已识别，但没有解析出有效持仓行")
    if not account:
        warnings.append("未识别到总资产/可用资金；请手工补充后再确认")
    if positions:
        code_counts: dict[str, int] = {}
        for position in positions:
            code_counts[position["code"]] = code_counts.get(position["code"], 0) + 1
        duplicates = [code for code, count in code_counts.items() if count > 1]
        if duplicates:
            warnings.append("识别到重复代码，确认前请修正：" + ", ".join(duplicates))

    return {
        "as_of": as_of,
        "account": account,
        "positions": positions,
        "warnings": warnings,
    }


def build_account_snapshot(
    draft: Mapping[str, Any],
    *,
    account_alias: str,
    as_of: date,
    source_file: str = "",
    content_hash: str = "",
    ocr_engine: str = "",
) -> tuple[AccountSnapshot, list[str]]:
    """Validate an edited draft and build the immutable snapshot payload."""

    alias = str(account_alias or draft.get("account_alias") or "同花顺").strip()
    if not alias:
        raise ScreenshotError("账户别名不能为空")
    if len(alias) > 40:
        raise ScreenshotError("账户别名过长")

    cash = _optional_float(draft.get("cash"), "现金")
    available_cash = _optional_float(draft.get("available_cash"), "可用资金")
    market_value = _optional_float(draft.get("market_value"), "持仓市值")
    equity = _optional_float(draft.get("equity"), "总资产")
    warnings: list[str] = []

    positions: list[AccountPositionSnapshot] = []
    seen: set[str] = set()
    raw_positions = draft.get("positions") or []
    if not isinstance(raw_positions, Iterable) or isinstance(
        raw_positions, (str, bytes, Mapping)
    ):
        raise ScreenshotError("positions 必须是数组")
    for index, raw in enumerate(raw_positions, start=1):
        if not isinstance(raw, Mapping):
            raise ScreenshotError(f"第 {index} 行持仓格式无效")
        raw_code = str(raw.get("code") or "").strip()
        if not raw_code:
            if _optional_float(raw.get("quantity"), "数量") in (None, 0.0):
                continue
            raise ScreenshotError(f"第 {index} 行持仓缺少代码")
        code = normalize_code(raw_code)
        if code in seen:
            raise ScreenshotError(f"持仓代码重复：{code}")
        seen.add(code)
        quantity = _optional_float(raw.get("quantity"), f"{code} 数量") or 0.0
        if quantity < 0:
            raise ScreenshotError(f"{code} 数量不能为负")
        if quantity == 0:
            warnings.append(f"{code} 数量为 0，已忽略")
            continue
        available = _optional_float(
            raw.get("available_quantity"), f"{code} 可用数量"
        )
        avg_cost = _optional_float(raw.get("avg_cost"), f"{code} 成本")
        market_price = _optional_float(raw.get("market_price"), f"{code} 现价")
        row_value = _optional_float(raw.get("market_value"), f"{code} 市值")
        pnl = _optional_float(raw.get("pnl"), f"{code} 盈亏")
        for label, value in (
            ("可用数量", available),
            ("成本", avg_cost),
            ("现价", market_price),
            ("市值", row_value),
        ):
            if value is not None and value < 0:
                raise ScreenshotError(f"{code} {label}不能为负")
        if available is not None and available > quantity + 1e-6:
            warnings.append(f"{code} 可用数量大于持仓数量，请核对")
        if row_value is None and market_price is not None:
            row_value = round(quantity * market_price, 2)
        positions.append(
            AccountPositionSnapshot(
                code=code,
                name=str(raw.get("name") or "").strip(),
                quantity=quantity,
                available_quantity=available,
                avg_cost=avg_cost,
                market_price=market_price,
                market_value=row_value,
                pnl=pnl,
            )
        )

    computed_mv = sum(position.market_value or 0.0 for position in positions)
    if market_value is None and positions:
        market_value = round(computed_mv, 2)
        warnings.append("持仓市值由各行市值汇总得到")
    if market_value is not None and positions and computed_mv > 0:
        if abs(computed_mv - market_value) / market_value > 0.10:
            warnings.append("各持仓市值合计与账户持仓市值相差超过 10%，请核对")
    if cash is None and available_cash is not None:
        cash = available_cash
        warnings.append("现金按可用资金填入")
    if equity is None:
        if cash is not None and market_value is not None:
            equity = round(cash + market_value, 2)
            warnings.append("总资产由现金 + 持仓市值计算得到")
        elif market_value is not None:
            equity = market_value
            warnings.append("缺少现金，总资产暂按持仓市值计算")
    if cash is None and equity is not None and market_value is not None:
        cash = round(equity - market_value, 2)
        warnings.append("现金由总资产 - 持仓市值计算得到")
    if equity is not None and equity <= 0:
        raise ScreenshotError("总资产必须大于 0")

    snapshot = AccountSnapshot(
        account_alias=alias,
        as_of=as_of,
        cash=cash,
        available_cash=available_cash,
        market_value=market_value,
        equity=equity,
        source="ths_screenshot",
        source_file=Path(source_file).name if source_file else "",
        content_hash=content_hash,
        ocr_engine=ocr_engine,
        positions=tuple(positions),
    )
    return snapshot, warnings


def confirm_account_snapshot(
    store: PersonalStore,
    draft: Mapping[str, Any],
    *,
    account_alias: str,
    as_of: date,
    source_file: str = "",
    content_hash: str = "",
    ocr_engine: str = "",
) -> tuple[int, AccountSnapshot, list[str]]:
    snapshot, warnings = build_account_snapshot(
        draft,
        account_alias=account_alias,
        as_of=as_of,
        source_file=source_file,
        content_hash=content_hash,
        ocr_engine=ocr_engine,
    )
    snapshot_id = store.upsert_account_snapshot(snapshot)
    return snapshot_id, snapshot, warnings


# ----------------------------------------------------------------------
# Image loading
# ----------------------------------------------------------------------
def _load_image(content: bytes, *, max_mb: float, filename: str):
    if not content:
        raise ScreenshotError("图片内容为空")
    max_bytes = int(max_mb * 1024 * 1024)
    if max_bytes > 0 and len(content) > max_bytes:
        raise ScreenshotError(f"图片超过 {max_mb:g}MB 限制")
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ScreenshotError("缺少 Pillow，无法读取图片") from exc

    suffix = Path(filename).suffix.lower() if filename else ""
    if suffix in {".heic", ".heif"}:
        _register_heif()
    try:
        with Image.open(_bytes_reader(content)) as opened:
            image = ImageOps.exif_transpose(opened)
            image = image.convert("RGB")
            if max(image.size) > MAX_IMAGE_SIDE:
                image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            return image.copy()
    except Exception as exc:
        raise ScreenshotError(f"无法解码图片：{exc}") from exc


def _bytes_reader(content: bytes):
    from io import BytesIO

    return BytesIO(content)


def _register_heif() -> None:
    global _HEIF_REGISTERED
    if _HEIF_REGISTERED:
        return
    try:
        import pillow_heif
    except ImportError as exc:
        raise ScreenshotError("HEIC/HEIF 图片需要 pillow-heif 依赖") from exc
    pillow_heif.register_heif_opener()
    _HEIF_REGISTERED = True


# ----------------------------------------------------------------------
# OCR result normalization
# ----------------------------------------------------------------------
def _normalize_ocr_result(result: Any) -> list[OcrLine]:
    lines: list[OcrLine] = []
    if result is None:
        return lines
    txts = getattr(result, "txts", None)
    boxes = getattr(result, "boxes", None)
    scores = getattr(result, "scores", None)
    if txts is not None and boxes is not None:
        score_values = list(scores) if scores is not None else [0.0] * len(txts)
        for box, text, score in zip(boxes, txts, score_values):
            lines.append(_line_from_parts(box, text, score))
        return lines
    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                box = item[0]
                text = item[1]
                score = item[2] if len(item) >= 3 else 0.0
                lines.append(_line_from_parts(box, text, score))
    return lines


def _line_from_parts(box: Any, text: Any, score: Any) -> OcrLine:
    points: list[tuple[float, float]] = []
    for point in box:
        if len(point) >= 2:
            points.append((float(point[0]), float(point[1])))
    if not points:
        raise ScreenshotError("OCR 返回了无效坐标")
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        score_value = 0.0
    return OcrLine(text=str(text), box=tuple(points), score=score_value)


# ----------------------------------------------------------------------
# Row and table parsing
# ----------------------------------------------------------------------
def _group_rows(lines: Sequence[OcrLine]) -> list[_Row]:
    ordered = sorted(lines, key=lambda line: (line.y_center, line.x_center))
    groups: list[list[OcrLine]] = []
    for line in ordered:
        if not groups:
            groups.append([line])
            continue
        group = groups[-1]
        tolerance = max(8.0, min(line.height, max(item.height for item in group)) * 0.65)
        center = sum(item.y_center for item in group) / len(group)
        if abs(line.y_center - center) <= tolerance:
            group.append(line)
        else:
            groups.append([line])
    rows = []
    for group in groups:
        y0 = min(item.y0 for item in group)
        y1 = max(item.y1 for item in group)
        rows.append(
            _Row(
                lines=tuple(sorted(group, key=lambda item: item.x_center)),
                y0=y0,
                y1=y1,
                height=max(1.0, y1 - y0),
            )
        )
    return rows


def _find_header(rows: Sequence[_Row]) -> tuple[int | None, dict[str, float]]:
    best_index: int | None = None
    best_fields: dict[str, float] = {}
    for index, row in enumerate(rows):
        fields = _header_columns(row)
        if len(fields) > len(best_fields):
            best_index = index
            best_fields = fields
    if best_index is None or len(best_fields) < 3:
        return None, {}
    if "code" not in best_fields and "name" not in best_fields:
        return None, {}
    return best_index, best_fields


def _header_columns(row: _Row) -> dict[str, float]:
    columns: dict[str, float] = {}
    for line in row.lines:
        tokens = [
            token
            for token in re.split(r"[\s/|]+", _norm(line.text))
            if token
        ]
        if len(tokens) <= 1:
            field = _header_field(_norm(line.text))
            if field:
                columns.setdefault(field, line.x_center)
            continue
        for index, token in enumerate(tokens):
            field = _header_field(token)
            if not field:
                continue
            if len(tokens) == 1:
                center = line.x_center
            else:
                width = max(1.0, line.x1 - line.x0)
                center = line.x0 + width * (index + 0.5) / len(tokens)
            columns.setdefault(field, center)
    return columns


def _header_field(token: str) -> str | None:
    compact = _norm(token)
    exact: list[tuple[str, str]] = []
    prefixed: list[tuple[str, str]] = []
    for field, aliases in FIELD_ALIASES:
        for alias in aliases:
            alias_norm = _norm(alias)
            if compact == alias_norm:
                exact.append((field, alias_norm))
            elif compact.startswith(alias_norm) or compact.endswith(alias_norm):
                prefixed.append((field, alias_norm))
    if exact:
        return sorted(exact, key=lambda item: len(item[1]), reverse=True)[0][0]
    if prefixed:
        return sorted(prefixed, key=lambda item: len(item[1]), reverse=True)[0][0]
    return None


def _parse_position_row(
    row: _Row, columns: Mapping[str, float]
) -> dict[str, Any] | None:
    if not row.lines:
        return None
    all_text = " ".join(line.text for line in row.lines)
    # Skip repeated headers and obvious account-summary rows.
    if sum(1 for line in row.lines if _header_field(_norm(line.text))) >= 3:
        return None
    if any(
        alias in _norm(all_text)
        for _field, aliases in ACCOUNT_ALIASES
        for alias in aliases
        if alias in all_text
    ):
        return None

    cells: dict[str, list[tuple[float, str, float]]] = {
        field: [] for field in columns
    }
    for line in row.lines:
        field = _nearest_column(line.x_center, columns)
        if field is None:
            continue
        cells[field].append((line.x_center, line.text, line.score))

    def text_for(field: str) -> str:
        values = cells.get(field) or []
        if not values:
            return ""
        return " ".join(item[1] for item in sorted(values, key=lambda item: item[0]))

    code_text = text_for("code")
    code_match = _CODE_RE.search(code_text.replace(" ", ""))
    if code_match is None:
        code_match = _CODE_RE.search(_norm(all_text))
    if code_match is None:
        return None
    code = normalize_code(code_match.group(1))

    name = text_for("name").strip()
    if not name:
        remainder = _norm(code_text).replace(code_match.group(1), "").strip()
        name = remainder

    quantity = None
    available = None
    quantity_available = text_for("quantity_available")
    if quantity_available:
        pair = _number_values(quantity_available)
        if pair:
            quantity = pair[0]
            available = pair[1] if len(pair) > 1 else None
    if quantity is None:
        quantity = _first_number(text_for("quantity"))
    if available is None:
        available = _first_number(text_for("available_quantity"))
    market_price = _first_number(text_for("market_price"))
    market_value = _first_number(text_for("market_value"))
    avg_cost = _first_number(text_for("avg_cost"))
    pnl = _first_number(text_for("pnl"))

    if quantity is None or quantity <= 0:
        # Do not guess from arbitrary numbers: codes, P&L and percentages can
        # easily be mistaken for a quantity. The review screen lets the user add
        # the row manually instead.
        return None
    if market_value is None and market_price is not None:
        market_value = round(quantity * market_price, 2)

    score_values = [line.score for line in row.lines if line.score > 0]
    confidence = min(score_values) if score_values else 0.0
    return {
        "code": code,
        "name": name,
        "quantity": quantity,
        "available_quantity": available,
        "avg_cost": avg_cost,
        "market_price": market_price,
        "market_value": market_value,
        "pnl": pnl,
        "confidence": round(confidence, 3),
    }


def _nearest_column(
    x_center: float, columns: Mapping[str, float]
) -> str | None:
    ordered = sorted(columns.items(), key=lambda item: item[1])
    if not ordered:
        return None
    best_field, best_x = min(ordered, key=lambda item: abs(item[1] - x_center))
    distances = [
        abs(ordered[i + 1][1] - ordered[i][1])
        for i in range(len(ordered) - 1)
        if ordered[i + 1][1] > ordered[i][1]
    ]
    max_distance = max(40.0, (min(distances) * 0.65) if distances else 120.0)
    if abs(best_x - x_center) > max_distance:
        return None
    return best_field


# ----------------------------------------------------------------------
# Account summary parsing
# ----------------------------------------------------------------------
def _parse_account_metrics(
    lines: Sequence[OcrLine], *, max_y: float | None
) -> dict[str, float]:
    candidates = [line for line in lines if max_y is None or line.y_center <= max_y]
    account: dict[str, float] = {}
    for field, aliases in ACCOUNT_ALIASES:
        if field in account:
            continue
        value = _metric_value(candidates, aliases)
        if value is not None:
            account[field] = value
    return account


def _metric_value(lines: Sequence[OcrLine], aliases: Sequence[str]) -> float | None:
    alias_values = tuple(_norm(alias) for alias in aliases)
    matches: list[tuple[float, float, OcrLine]] = []
    for line in lines:
        text = _norm(line.text)
        for alias in alias_values:
            position = text.find(alias)
            if position < 0:
                continue
            tail = text[position + len(alias) :]
            numbers = _number_values(tail)
            if numbers:
                matches.append((line.score, -len(tail), line))
                break
            nearest = _nearest_number_line(lines, line)
            if nearest is not None:
                matches.append((line.score, -abs(nearest.x_center - line.x1), nearest))
                break
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    chosen = matches[0][2]
    values = _number_values(chosen.text)
    return values[-1] if values else None


def _nearest_number_line(
    lines: Sequence[OcrLine], label: OcrLine
) -> OcrLine | None:
    candidates: list[tuple[float, OcrLine]] = []
    for line in lines:
        if line is label:
            continue
        if not _number_values(line.text):
            continue
        dy = abs(line.y_center - label.y_center)
        if dy > max(30.0, label.height * 1.8):
            continue
        dx = line.x0 - label.x1
        if dx < -10:
            continue
        candidates.append((abs(dx) + dy * 2.0, line))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _detect_as_of(lines: Sequence[OcrLine]) -> str | None:
    found: list[date] = []
    for line in lines:
        for match in _DATE_RE.finditer(_norm(line.text)):
            try:
                found.append(
                    date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                )
            except ValueError:
                continue
    if not found:
        return None
    return max(found).isoformat()


def _looks_like_holdings(lines: Sequence[OcrLine]) -> bool:
    text = _norm(" ".join(line.text for line in lines))
    return "持仓" in text or "市值" in text or bool(_CODE_RE.search(text))


# ----------------------------------------------------------------------
# Values
# ----------------------------------------------------------------------
def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    return re.sub(r"\s+", "", normalized)


def _number_values(text: str) -> list[float]:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    values: list[float] = []
    for match in _NUMBER_RE.finditer(normalized):
        raw = match.group(0).strip()
        try:
            multiplier = 1.0
            if raw.endswith("万"):
                multiplier = 10_000.0
                raw = raw[:-1]
            elif raw.endswith("亿"):
                multiplier = 100_000_000.0
                raw = raw[:-1]
            cleaned = _normalize_number_separators(raw)
            if not cleaned or cleaned in {"+", "-"}:
                continue
            values.append(float(cleaned) * multiplier)
        except ValueError:
            continue
    return values


def _normalize_number_separators(raw: str) -> str:
    """Repair OCR confusion between thousands separators and decimal points.

    Tesseract/RapidOCR frequently reads ``123,456.78`` as ``123.456.78``.
    Multiple dots are treated as thousands separators; a final group of two
    digits is preserved as the decimal part. A single dot remains a decimal
    point (prices such as ETF ``4.100`` must not be collapsed).
    """

    text = raw.replace("，", ",").strip().strip(".,")
    if text.count(".") > 1:
        parts = text.split(".")
        if len(parts[-1]) == 2 and all(part.isdigit() for part in parts):
            text = "".join(parts[:-1]) + "." + parts[-1]
        else:
            text = "".join(parts)
    return text.replace(",", "")


def _first_number(text: str) -> float | None:
    values = _number_values(text)
    return values[0] if values else None


def _optional_float(value: Any, label: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        values = _number_values(str(value))
        if not values:
            raise ScreenshotError(f"{label}不是有效数字")
        number = values[0]
    if number != number or number in (float("inf"), float("-inf")):
        raise ScreenshotError(f"{label}不是有限数字")
    return number


__all__ = [
    "DEFAULT_MAX_IMAGE_MB",
    "OCR_ENGINE_NAME",
    "OcrLine",
    "ScreenshotError",
    "build_account_snapshot",
    "confirm_account_snapshot",
    "parse_account_screenshot",
    "parse_ocr_lines",
    "recognize_image",
]
