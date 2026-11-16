"""QMT bridge: runs on the Windows machine where QMT/miniQMT is logged in.

Default mode is ``mock`` so the endpoint contract can be tested without QMT.
Set ``QMT_MODE=xtquant`` and ``QMT_USERDATA_MINI`` to use the real adapter.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

TOKEN = os.getenv("QMT_BRIDGE_TOKEN", "")
MODE = os.getenv("QMT_MODE", "mock").strip().lower()


class OrderRequest(BaseModel):
    account_id: str
    code: str
    side: str
    quantity: int
    price: Optional[float] = None
    price_type: str = "limit"
    idempotency_key: str
    strategy: str = "dsa_personal"
    remark: str = ""


@dataclass
class MockAdapter:
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)

    def connect(self) -> bool:
        return True

    def quote(self, codes: list[str]) -> dict[str, Any]:
        return {"mode": "mock", "quotes": {code: {"last": None} for code in codes}}

    def positions(self) -> list[dict[str, Any]]:
        return []

    def orders_list(self) -> list[dict[str, Any]]:
        return list(self.orders.values())

    def trades(self) -> list[dict[str, Any]]:
        return []

    def place(self, request: OrderRequest) -> dict[str, Any]:
        for order in self.orders.values():
            if order["idempotency_key"] == request.idempotency_key:
                return order
        order_id = f"mock-{uuid.uuid4().hex[:12]}"
        order = {
            "order_id": order_id,
            "idempotency_key": request.idempotency_key,
            "status": "SUBMITTED",
            "code": request.code,
            "side": request.side,
            "quantity": request.quantity,
            "price": request.price,
            "created_at": time.time(),
        }
        self.orders[order_id] = order
        return order

    def cancel(self, order_id: str) -> dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError(order_id)
        order["status"] = "CANCELLED"
        return order


class XtQuantAdapter:
    """Thin wrapper around xtquant. Imported lazily, Windows only."""

    def __init__(self) -> None:
        try:
            from xtquant import xtconstant, xtdata
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount
        except ImportError as exc:  # pragma: no cover - Windows only
            raise RuntimeError(
                "xtquant is not importable; copy the xtquant folder from the QMT "
                "installation into this Python environment"
            ) from exc
        self.xtdata = xtdata
        self.xtconstant = xtconstant
        self.trader = XtQuantTrader(
            os.environ["QMT_USERDATA_MINI"], int(time.time()) % 100000
        )
        self.account_id = os.getenv("QMT_ACCOUNT_ID", "")
        self.account = StockAccount(self.account_id)
        self.trader.start()
        self.connected = self.trader.connect() == 0
        if self.connected:
            self.trader.subscribe(self.account)

    def quote(self, codes: list[str]) -> dict[str, Any]:
        return {"mode": "xtquant", "quotes": self.xtdata.get_full_tick(codes)}

    def positions(self) -> list[dict[str, Any]]:
        positions = self.trader.query_stock_positions(self.account)
        return [vars(item) for item in positions]

    def orders_list(self) -> list[dict[str, Any]]:
        orders = self.trader.query_stock_orders(self.account)
        return [vars(item) for item in orders]

    def trades(self) -> list[dict[str, Any]]:
        trades = self.trader.query_stock_trades(self.account)
        return [vars(item) for item in trades]

    def place(self, request: OrderRequest) -> dict[str, Any]:
        if request.side.lower() not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        side = (
            self.xtconstant.STOCK_BUY
            if request.side.lower() == "buy"
            else self.xtconstant.STOCK_SELL
        )
        price_type = (
            self.xtconstant.FIX_PRICE
            if request.price_type.lower() == "limit"
            else self.xtconstant.LATEST_PRICE
        )
        order_id = self.trader.order_stock(
            self.account,
            request.code,
            side,
            int(request.quantity),
            price_type,
            float(request.price or 0.0),
            request.strategy,
            f"{request.idempotency_key}|{request.remark}",
        )
        return {"order_id": str(order_id), "status": "SUBMITTED"}

    def cancel(self, order_id: str) -> dict[str, Any]:
        result = self.trader.cancel_order_stock(self.account, int(order_id))
        return {"order_id": order_id, "result": result}


def _build_adapter():
    if MODE == "xtquant":
        return XtQuantAdapter()
    return MockAdapter()


ADAPTER = _build_adapter()

app = FastAPI(title="DSA QMT Bridge", version="0.1.0")


def require_token(authorization: Optional[str] = Header(default=None)) -> None:
    if not TOKEN:
        return
    expected = f"Bearer {TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid bridge token")


@app.get("/health", dependencies=[Depends(require_token)])
def health() -> dict[str, Any]:
    return {"ok": True, "mode": MODE, "connected": getattr(ADAPTER, "connected", True)}


@app.get("/quote", dependencies=[Depends(require_token)])
def quote(codes: str) -> dict[str, Any]:
    return ADAPTER.quote([item.strip() for item in codes.split(",") if item.strip()])


@app.get("/positions", dependencies=[Depends(require_token)])
def positions() -> dict[str, Any]:
    return {"positions": ADAPTER.positions()}


@app.get("/orders", dependencies=[Depends(require_token)])
def orders() -> dict[str, Any]:
    return {"orders": ADAPTER.orders_list()}


@app.get("/trades", dependencies=[Depends(require_token)])
def trades() -> dict[str, Any]:
    return {"trades": ADAPTER.trades()}


@app.post("/orders", dependencies=[Depends(require_token)])
def place_order(request: OrderRequest) -> dict[str, Any]:
    try:
        return ADAPTER.place(request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/orders/{order_id}/cancel", dependencies=[Depends(require_token)])
def cancel_order(order_id: str) -> dict[str, Any]:
    try:
        return ADAPTER.cancel(order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="order not found") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/reconcile", dependencies=[Depends(require_token)])
def reconcile() -> dict[str, Any]:
    return {
        "positions": ADAPTER.positions(),
        "orders": ADAPTER.orders_list(),
        "trades": ADAPTER.trades(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("QMT_BRIDGE_HOST", "0.0.0.0"), port=int(os.getenv("QMT_BRIDGE_PORT", "8710")))
